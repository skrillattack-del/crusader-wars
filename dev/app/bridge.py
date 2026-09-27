"""Crusader Wars 2 launcher bridge (pywebview js_api).

Reads the newest CK3 save, lists battles in progress, rolls both armies from
vanilla 3K units (dev/battle_math), builds and installs the crusader_wars_2
battle pack, launches Three Kingdoms, reads the battle result and removes the
pack. A previous pack is replaced only when its SHA-256 matches a recorded run.

Every public method returns {'ok': True, ...} or {'error': msg}; the UI turns
'error' into a JS exception.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parents[0] / 'spikes' / 'g1_3k_io'),
           str(_HERE.parents[0] / 'spikes' / 'g2_ck3_writeback' / 'patcher'),
           str(_HERE.parents[0] / 'battle_math'), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import probe  # battle pack: build, install, uninstall, read_result
import preflight  # CK3 save reader: combat inventory
from roll import MODES, roll
from scale import stage
import config  # the options ledger: load/validate/checksum (cw2_config.json)

CK3_EXE = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\binaries\ck3.exe')
def _ck3_saves():
    # OneDrive often redirects Documents; prefer whichever copy actually has CK3 saves.
    home = Path(os.environ.get('USERPROFILE', str(Path.home())))
    roots = [Path(os.environ['OneDrive']) / 'Documents'] if os.environ.get('OneDrive') else []
    roots += [home / 'OneDrive' / 'Documents', home / 'Documents']
    folders = [r / 'Paradox Interactive' / 'Crusader Kings III' / 'save games' for r in roots]
    return next((f for f in folders if f.is_dir()), folders[-1])

CK3_SAVES = _ck3_saves()
STEAM_CK3 = 'steam://rungameid/1158310'
CW1_WORKSHOP_ID = '2977969008'  # Crusader Wars 'Ad Maiorem Gloriam' (Attila era)
STEAM_CW1_PAGE = f'steam://url/CommunityFilePage/{CW1_WORKSHOP_ID}'
CK3_MOD_FILE = 'cw2_ck3_bridge.mod'
CK3_MOD_ID = f'mod/{CK3_MOD_FILE}'  # the Paradox launcher's gameRegistryId
PARADOX_LAUNCHER = 'Paradox Launcher.exe'
ARMY_OWNER = re.compile(r'type=army\b[^{}]*?owner=(\d+)[^{}]*?army=(\d+)')
STAGING_NOTE = ('Three Kingdoms fights exactly this roll on the Records Xingyang map; '
                'units bigger than their card are trimmed at deployment.')
SESSION_NAME = 'cw2-launcher-session.json'
# Launcher looks (dev/app/ui/skins). A display preference, so it lives in the
# session file, not the options ledger.
SKINS = ('ck3', '3k')
# CW2's own 3K mod list; CA's launcher owns used_mods.txt (CW1 used used_mods_cw.txt for Attila).
TK_MOD_LIST = 'used_mods_cw2.txt'
# The CW2 button logs the battle name, then CK3 writes the save it triggered.
CW2_BATTLE_LINE = re.compile(r'(?m)^\[(\d\d):(\d\d):(\d\d)\][^\n]*?\(CW2_Battle:effect\): BATTLE_NAME:([^\r\n]*)')
SIGNAL_WINDOW = 300  # seconds allowed between that log line and the save
SAVE_SETTLE = 2  # seconds a save must stay unchanged before it is read
CLOSE_GRACE = 10  # seconds Three Kingdoms gets to close before taskkill /F


def _season(date):
    """'Winter'..'Autumn' for a CK3 date such as '1066.10.14'; None when it can't be read."""
    try:
        month = int(str(date).split('.')[1])
    except (IndexError, ValueError):
        return None
    return ('Winter', 'Spring', 'Summer', 'Autumn')[month % 12 // 3] if 1 <= month <= 12 else None


def _default_tasklist(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result.returncode, result.stdout

def _default_taskkill(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result.returncode, result.stdout

class Bridge:
    """js_api for the launcher window. See dev/app/ui/index.html for callers."""

    def __init__(self, base=None, game=None, cli=None, tasklist=None, saves=None,
                 ck3_mods=None, cw1_dir=None, mod_source=None, popen=None, taskkill=None):
        self.base = Path(base) if base else _HERE
        self.game = Path(game) if game else probe.GAME
        self.saves = Path(saves) if saves else CK3_SAVES
        self.ck3_mods = Path(ck3_mods) if ck3_mods else self.saves.parent / 'mod'
        self.cw1_dir = (Path(cw1_dir) if cw1_dir else CK3_EXE.parents[3] / 'workshop' / 'content'
                        / '1158310' / CW1_WORKSHOP_ID)
        self.mod_source = Path(mod_source) if mod_source else next(
            (p / 'mod' / 'cw2_ck3_mod' for p in (self.base, *self.base.parents, _HERE.parent)
             if (p / 'mod' / 'cw2_ck3_mod' / 'descriptor.mod').is_file()), None)
        self._save_cache = None
        # A button press shortly before the launcher opened still counts.
        self._signal_seen = time.time() - SIGNAL_WINDOW
        self._signal_pending = None
        self.cli = Path(cli) if cli else self._find_cli()
        self._tasklist = tasklist or _default_tasklist
        self._taskkill = taskkill or _default_taskkill
        self._popen = popen or subprocess.Popen
        self._window = None
        self.session = {'output': None}
        state = self.base / SESSION_NAME
        if state.is_file():
            try:
                self.session.update(json.loads(state.read_text(encoding='utf-8')))
            except (ValueError, OSError):
                pass
        self.config, self.config_path, self.config_sha256 = {}, None, None
        self.config_error = None
        self.slots_error = None
        self.slots_violations = []
        self._load_config()

    def _load_config(self):
        """(Re)load the options ledger; failures are surfaced, never fatal."""
        self.config_error = None
        try:
            self.config, self.config_path, self.config_sha256 = config.load(self.base)
        except ValueError as exc:
            self.config_error = str(exc)
            self.config, self.config_path, self.config_sha256 = {}, None, None
        self.slots_error = None
        self.slots_violations = []
        try:
            strict = bool(self.config.get('injectivity_strict', True))
            self.slots_violations, _ = config.check_slots(self.base, strict=strict)
        except ValueError as exc:
            self.slots_error = str(exc)

    def _config_block(self):
        return {'path': str(self.config_path) if self.config_path else None,
                'sha256': self.config_sha256,
                'valid': self.config_error is None and self.slots_error is None,
                'error': self.config_error or self.slots_error,
                'slots_violations': self.slots_violations}

    def _find_cli(self):
        override = os.environ.get('CW2_RPFM_CLI')
        if override:
            return Path(override)
        for parent in (self.base, *self.base.parents):
            candidate = parent / 'tools' / 'rpfm' / 'rpfm_cli.exe'
            if candidate.is_file():
                return candidate
        return Path('rpfm_cli.exe')

    def attach(self, window):
        """Receive the pywebview window so pack progress can be pushed as events."""
        self._window = window

    # ---- helpers -------------------------------------------------------

    def _save_session(self):
        (self.base / SESSION_NAME).write_text(json.dumps(self.session, indent=2), encoding='utf-8')

    def _process_running(self, image):
        code, out = self._tasklist(['tasklist', '/FI', f'IMAGENAME eq {image}', '/FO', 'CSV', '/NH'])
        return bool(code or image in out)

    def _require_3k_closed(self):
        if self._process_running('Three_Kingdoms.exe'):
            raise ValueError('Close Three Kingdoms before changing the battle pack.')

    def _require_run(self):
        if not self.session.get('output'):
            raise ValueError('Prepare a run first.')
        run = Path(self.session['output'])
        if not (run / 'run.json').is_file():
            raise ValueError('The recorded run folder is missing its manifest.')
        return run

    def _emit(self, type_, payload):
        if self._window is None:
            return
        try:
            self._window.evaluate_js(f'window.cw2.emit({json.dumps(type_)}, {json.dumps(payload)})')
        except Exception:
            pass  # progress events are cosmetic; the method return is authoritative

    # ---- js_api surface -------------------------------------------------

    def get_health(self):
        try:
            tk_exe = self.game / 'Three_Kingdoms.exe'
            paths = [
                {'key': 'ck3_exe', 'label': 'Crusader Kings III',
                 'value': str(CK3_EXE), 'ok': CK3_EXE.is_file()},
                {'key': 'tk_exe', 'label': 'Three Kingdoms',
                 'value': str(tk_exe), 'ok': tk_exe.is_file()},
                {'key': 'ck3_saves', 'label': 'CK3 save folder',
                 'value': str(self.saves), 'ok': self.saves.is_dir()},
                {'key': 'rpfm_cli', 'label': 'RPFM command line',
                 'value': str(self.cli), 'ok': self.cli.is_file()},
            ]
            return {'ok': True,
                    'ck3_running': self._process_running('ck3.exe'),
                    'tk_running': self._process_running('Three_Kingdoms.exe'),
                    'probe_installed': (self.game / 'data' / probe.PACK_NAME).exists(),
                    'ck3_mod': (self.ck3_mods / CK3_MOD_FILE).is_file(),
                    'in_playset': self._mod_in_playset(),
                    'mod_source': self.mod_source is not None,
                    'cw1_installed': self.cw1_dir.is_dir()
                                     or (self.ck3_mods / f'ugc_{CW1_WORKSHOP_ID}.mod').is_file(),
                    'paths': paths,
                    'config': self._config_block(),
                    'gates': {'ck3': self.saves.is_dir(),
                              'probe': all(p['ok'] for p in paths
                                           if p['key'] in ('tk_exe', 'rpfm_cli'))}}
        except Exception as exc:
            return {'error': str(exc)}

    def get_config(self):
        """The effective options ledger plus where it was found."""
        try:
            return {'ok': True, 'config': dict(self.config), 'path': str(self.config_path) if self.config_path else None,
                    'sha256': self.config_sha256,
                    'slots_ok': self.config_error is None and self.slots_error is None
                                and not self.slots_violations}
        except Exception as exc:
            return {'error': str(exc)}

    def save_config(self, patch=None):
        """Validate `patch` against the schema, merge it into the ledger, write back."""
        try:
            cfg, ledger, sha = config.save(self.base, patch)
            self.config, self.config_path, self.config_sha256 = cfg, ledger, sha
            strict = bool(cfg.get('injectivity_strict', True))
            self.slots_violations, _ = config.check_slots(self.base, strict=strict)
            self.slots_error = None
            return {'ok': True, 'config': dict(cfg), 'path': str(ledger), 'sha256': sha}
        except Exception as exc:
            return {'error': str(exc)}

    def get_skin(self):
        """The launcher look the player last picked; the first one by default."""
        skin = self.session.get('skin')
        return {'ok': True, 'skin': skin if skin in SKINS else SKINS[0], 'skins': list(SKINS)}

    def set_skin(self, skin=None):
        """Remember the launcher look in the session file."""
        try:
            if skin not in SKINS:
                raise ValueError(f'Unknown launcher look {skin!r}; expected one of {", ".join(SKINS)}')
            self.session['skin'] = skin
            self._save_session()
            return {'ok': True, 'skin': skin}
        except Exception as exc:
            return {'error': str(exc)}

    @staticmethod
    def _readable(path):
        """False for CK3's binary saves: header 'SAV01' + '01' or '03' (autosaves, exit saves).

        '00' and '02' are plain text (the CW2 button writes one); a file without the
        header is read as plain text too.
        """
        try:
            with open(path, 'rb') as file:
                head = file.read(7)
        except OSError:
            return False
        return not head.startswith(b'SAV01') or head[5:7] in (b'00', b'02')

    def _latest_save(self):
        saves = sorted((p for p in self.saves.glob('*.ck3') if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not saves:
            raise ValueError(f'No .ck3 saves in {self.saves}. Pause during a battle in CK3 and save.')
        readable = next((p for p in saves if self._readable(p)), None)
        if readable is None:
            raise ValueError('No readable CK3 save: every save is in CK3\'s binary format. '
                             'Press the crossed swords in a CK3 battle; it writes a readable save.')
        return readable

    @staticmethod
    def _top_block(text, key):
        """A top-level save section via its unindented line; G2's full scan only as a fallback.

        The full scan tokenises the whole ~200 MB gamestate in Python (about 30 s).
        """
        marker = f'\n{key}={{'
        start = text.find(marker)
        if start < 0 or text.find(marker, start + 1) >= 0:
            return preflight.unique(text, key)
        start += len(marker) - 1
        return text[start:preflight.block_end(text, start)]

    @staticmethod
    def _character(living, char_id):
        """{'id', 'name', 'martial', 'prowess'} for a character in the save's `living` block, or None."""
        if not char_id or not living:
            return None
        found = re.search(rf'(?m)^[ \t]*{re.escape(str(char_id))}=\{{', living)
        if not found:
            return None
        start = found.end() - 1
        block = living[start:preflight.block_end(living, start)]
        name = re.search(r'\bfirst_name="([^"]*)"', block)
        skills = re.search(r'\bskill=\{([^}]*)\}', block)
        values = [int(v) for v in skills.group(1).split()] if skills else []
        # CK3 skill order: diplomacy, martial, stewardship, intrigue, learning, prowess.
        return {'id': str(char_id), 'name': name.group(1) if name else None,
                'martial': values[1] if len(values) >= 6 else None,
                'prowess': values[5] if len(values) >= 6 else None}

    def _battles(self, path):
        """Active combats in a save, read-only, cached per file version."""
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if self._save_cache and self._save_cache[0] == key:
            return self._save_cache[1]
        text, _ = preflight.read_gamestate(path)
        rows = preflight.combat_rows(preflight.unique(self._top_block(text, 'combats'), 'combats'))
        played = re.search(r'currently_played_characters\s*=\s*\{([^}]*)\}', text)
        players = set(played.group(1).split()) if played else set()
        try:
            units = self._top_block(text, 'units')
        except ValueError:
            units = ''  # without unit records, no battle is marked as yours
        owner = {army: who for who, army in ARMY_OWNER.findall(units)}
        date = re.search(r'(?m)^date=([\d.]+)', text)
        try:
            living = self._top_block(text, 'living')
        except ValueError:
            living = ''  # without character records, commanders stay unnamed
        battles = []
        for row in rows:
            sides = []
            for role in ('attacker', 'defender'):
                data = row[role]
                sides.append({'role': role.title(), 'army_ids': data['army_ids'],
                              'name': f"{role.title()} · army {', '.join(data['army_ids'])}",
                              'initial': float(data['initial_men']),
                              'fighting': float(data['total_fighting_men']),
                              # The commander's name and skills come from the save's
                              # character records. Combat contribution rows do not
                              # identify knights, so none are listed.
                              'commander': self._character(living, data.get('commander')),
                              'knights': [],
                              'commander_id': data.get('commander'),
                              'leader_id': data.get('leader'),
                              'participant_ids': data.get('characters', []),
                              'yours': any(owner.get(a) in players for a in data['army_ids'])})
            battles.append({'combat_id': row['combat_id'], 'phase': row['phase'], 'sides': sides,
                            'yours': any(s['yours'] for s in sides)})
        data = {'date': date.group(1) if date else None, 'battles': battles}
        self._save_cache = (key, data)
        return data

    def _cw2_battle_for(self, save_mtime):
        """The battle name the CW2 button logged just before a save, or None."""
        log = self.saves.parent / 'logs' / 'debug.log'
        try:
            text = log.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None
        found = None
        for found in CW2_BATTLE_LINE.finditer(text):
            pass
        if found is None:
            return None
        h, m, s = (int(g) for g in found.groups()[:3])
        saved = datetime.fromtimestamp(save_mtime)
        # debug.log stamps only the time of day; compare modulo a day.
        gap = (saved.hour * 3600 + saved.minute * 60 + saved.second - (h * 3600 + m * 60 + s)) % 86400
        return (found.group(4).strip() or 'CK3 battle') if gap <= SIGNAL_WINDOW else None

    def poll_battle(self):
        """A save written by the CW2 battle button since the last poll: {'save': path, 'battle': name}.

        A save is reported once, after it has stopped changing; other saves are skipped.
        """
        try:
            try:
                path = self._latest_save()
            except ValueError:
                return {'ok': True, 'save': None}
            stat = path.stat()
            if stat.st_mtime <= self._signal_seen:
                return {'ok': True, 'save': None}
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if self._signal_pending != key or time.time() - stat.st_mtime < SAVE_SETTLE:
                self._signal_pending = key
                return {'ok': True, 'save': None}
            self._signal_seen, self._signal_pending = stat.st_mtime, None
            battle = self._cw2_battle_for(stat.st_mtime)
            if battle is None:
                return {'ok': True, 'save': None}
            return {'ok': True, 'save': str(path), 'save_name': path.name, 'battle': battle}
        except Exception as exc:
            return {'error': str(exc)}

    def get_encounter(self, save=None, combat_id=None):
        """Read the newest CK3 save (or `save`) and pick a battle in progress.

        Default pick: a battle with one of the player's own armies, else the
        largest. A vassal's or ally's army is not detected as yours, so the
        UI always lets the player choose.
        """
        try:
            path = Path(save) if save else self._latest_save()
            data = self._battles(path)
            battles = [b for b in data['battles'] if all(s['fighting'] > 0 for s in b['sides'])]
            if not battles:
                raise ValueError(f'{path.name} has no battle in progress. Save while armies are fighting.')
            chosen = next((b for b in battles if b['combat_id'] == str(combat_id)), None)
            if combat_id is not None and chosen is None:
                raise ValueError(f'Battle {combat_id} is not in {path.name}.')
            chosen = chosen or next((b for b in battles if b['yours']), None) or max(
                battles, key=lambda b: sum(s['fighting'] for s in b['sides']))
            return {'ok': True, 'id': f"ck3:{chosen['combat_id']}", 'combat_id': chosen['combat_id'],
                    'save': str(path), 'save_name': path.name, 'date': data['date'],
                    'season': _season(data['date']), 'battle': self._cw2_battle_for(path.stat().st_mtime),
                    'phase': chosen['phase'], 'yours': chosen['yours'],
                    'battles': [{'combat_id': b['combat_id'], 'yours': b['yours'], 'phase': b['phase'],
                                 'men': [round(s['fighting']) for s in b['sides']]} for b in battles],
                    'sides': chosen['sides']}
        except Exception as exc:
            return {'error': str(exc)}

    def roll_roster(self, encounter=None, seed=None, mode='records'):
        """Stage both sides at one scale and roll vanilla 3K units onto the cards.

        mode: 'records' (generals lead a bodyguard card) or 'romance' (generals are single heroes).
        The options ledger supplies army_scale_factor (both sides' CK3 men before staging)
        and domain_focus (faction filter for the unit pool).
        """
        try:
            if not encounter or len(encounter.get('sides') or []) != 2:
                raise ValueError('Pick a CK3 battle first.')
            if mode not in MODES:
                raise ValueError(f'Unknown mode {mode!r}; use records or romance.')
            factor = float(self.config.get('army_scale_factor') or 1.0)
            domain = self.config.get('domain_focus') or 'custom'
            seed = int(seed) if seed not in (None, '') else random.randrange(1, 10**7)
            scale, *staged = stage(*(float(s['fighting']) * factor for s in encounter['sides']),
                                   general_size=MODES[mode]['general_size'])
            rolled = roll(encounter['sides'][0], encounter['sides'][1], *staged, seed, mode,
                          domain_focus=domain)
            sides = []
            for spec, side, generals in zip(encounter['sides'], staged, rolled):
                sides.append({'role': spec['role'], 'name': spec['name'], 'fighting': spec['fighting'],
                              'yours': bool(spec.get('yours')), 'commander': spec.get('commander'),
                              'men': side.men, 'trim': side.trim, 'cards': side.cards,
                              'retinue': side.units, 'generals': generals})
            note = STAGING_NOTE + (f' Army scale x{factor:g} applied before staging.' if factor != 1.0 else '')
            note += (' Romance battles are not staged yet; the pack replaces Records Xingyang.'
                     if mode == 'romance' else '')
            return {'ok': True, 'seed': seed, 'mode': mode, 'deterministic': False, 'scale': scale,
                    # shown by the in-game lobby (probe.LOBBY)
                    'battle': encounter.get('battle'), 'date': encounter.get('date'),
                    'season': encounter.get('season'),
                    'note': note, 'applied': {'army_scale_factor': factor, 'domain_focus': domain,
                                              'show_mode': self.config.get('show_mode') or 'dramatic'},
                    'sides': sides}
        except Exception as exc:
            return {'error': str(exc)}

    def install_ck3_mod(self):
        """Register the CW2 CK3 mod with the Paradox launcher; the mod files stay where they are."""
        try:
            if self.mod_source is None:
                raise ValueError('The CW2 CK3 mod files are missing (expected dev/mod/cw2_ck3_mod).')
            self.ck3_mods.mkdir(parents=True, exist_ok=True)
            descriptor = (self.mod_source / 'descriptor.mod').read_text(encoding='utf-8')
            descriptor = re.sub(r'(?m)^path=.*\n?', '', descriptor).rstrip('\n')
            target = self.ck3_mods / CK3_MOD_FILE
            target.write_text(f'{descriptor}\npath="{self.mod_source.as_posix()}"\n', encoding='utf-8')
            return {'ok': True, 'mod_file': str(target)}
        except Exception as exc:
            return {'error': str(exc)}

    @property
    def _launcher_db(self):
        return self.ck3_mods.parent / 'launcher-v2.sqlite'

    def _mod_in_playset(self):
        """True when the CW2 mod is enabled in the Paradox launcher's active playset (read-only)."""
        if not self._launcher_db.is_file():
            return False
        try:
            con = sqlite3.connect(f'file:{self._launcher_db.as_posix()}?mode=ro', uri=True)
            try:
                row = con.execute(
                    'select pm.enabled from playsets_mods pm join mods m on m.id = pm.modId '
                    'join playsets p on p.id = pm.playsetId where p.isActive = 1 and m.gameRegistryId = ?',
                    (CK3_MOD_ID,)).fetchone()
            finally:
                con.close()
            return bool(row and row[0])
        except sqlite3.Error:
            return False

    def add_to_playset(self):
        """Enable the CW2 mod last in the active playset and switch Crusader Wars 1 off.

        Edits the Paradox launcher's database only while the launcher is closed, after a
        timestamped backup, and mirrors the change into dlc_load.json. Nothing is deleted.
        """
        try:
            if self._process_running(PARADOX_LAUNCHER):
                raise ValueError('Close the Paradox launcher first; it rewrites playsets while open.')
            db = self._launcher_db
            if not db.is_file():
                raise ValueError('The Paradox launcher database was not found. Open the Paradox launcher once, then try again.')
            backups = self.base / 'backups'
            backups.mkdir(parents=True, exist_ok=True)
            backup = backups / f"launcher-v2-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite"
            shutil.copy2(db, backup)
            con = sqlite3.connect(db)
            try:
                with con:
                    playsets = con.execute('select id, name from playsets where isActive = 1').fetchall()
                    if len(playsets) != 1:
                        raise ValueError('Expected exactly one active playset in the Paradox launcher.')
                    playset, playset_name = playsets[0]
                    mod = con.execute('select id from mods where gameRegistryId = ?', (CK3_MOD_ID,)).fetchone()
                    if mod is None:
                        raise ValueError('The Paradox launcher has not listed the CW2 mod yet. '
                                         'Open it once so it scans your mods, close it, then try again.')
                    row = con.execute('select 1 from playsets_mods where playsetId = ? and modId = ?',
                                      (playset, mod[0])).fetchone()
                    if row:
                        con.execute('update playsets_mods set enabled = 1 where playsetId = ? and modId = ?',
                                    (playset, mod[0]))
                    else:
                        last = con.execute('select coalesce(max(position), -1) from playsets_mods where playsetId = ?',
                                           (playset,)).fetchone()[0]
                        con.execute('insert into playsets_mods (playsetId, modId, enabled, position) values (?, ?, 1, ?)',
                                    (playset, mod[0], last + 1))
                    cw1 = con.execute(
                        'update playsets_mods set enabled = 0 where playsetId = ? and modId in '
                        '(select id from mods where steamId = ? or gameRegistryId = ?)',
                        (playset, CW1_WORKSHOP_ID, f'mod/ugc_{CW1_WORKSHOP_ID}.mod')).rowcount
            finally:
                con.close()
            load = self.ck3_mods.parent / 'dlc_load.json'
            data = json.loads(load.read_text(encoding='utf-8')) if load.is_file() else {}
            enabled = [m for m in data.get('enabled_mods', [])
                       if m not in (CK3_MOD_ID, f'mod/ugc_{CW1_WORKSHOP_ID}.mod')]
            data['enabled_mods'] = enabled + [CK3_MOD_ID]
            data.setdefault('disabled_dlcs', [])
            tmp = load.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
            os.replace(tmp, load)
            return {'ok': True, 'playset': playset_name, 'cw1_disabled': cw1, 'backup': str(backup)}
        except Exception as exc:
            return {'error': str(exc)}

    def open_cw1_page(self):
        """Open Crusader Wars 1's Workshop page; unsubscribing there makes Steam delete it."""
        try:
            os.startfile(STEAM_CW1_PAGE)
            return {'ok': True}
        except Exception as exc:
            return {'error': str(exc)}

    def launch_ck3(self):
        try:
            os.startfile(STEAM_CK3)
            return {'ok': True, 'note': 'launched through Steam'}
        except Exception as exc:
            return {'error': str(exc)}

    def prepare_and_install(self, roster=None):
        """Build a pack that stages `roster` (roll_roster's result), then install it."""
        try:
            if not roster or len(roster.get('sides') or []) != 2:
                raise ValueError('Roll the armies first.')
            self._require_3k_closed()
            if not (self.game / 'Three_Kingdoms.exe').is_file() or not self.cli.is_file():
                raise ValueError('Select the installed Three Kingdoms folder and rpfm_cli.exe.')
            target = self.game / 'data' / probe.PACK_NAME
            previous = self._run_for_installed_pack(target) if target.exists() else None
            if target.exists() and previous is None:
                raise ValueError('An unrecognised battle pack is installed: it matches no recorded run, '
                                 'so CW2 will not delete it. Remove it by hand.')
            # Remove the previous runtime log so read_result can't
            # accidentally read stale data from a different roster.
            if previous:
                try:
                    prev_manifest = json.loads((previous / 'run.json').read_text(encoding='utf-8'))
                    prev_log = Path(prev_manifest.get('log_path', ''))
                    if prev_log.is_file():
                        prev_log.unlink()
                except (ValueError, OSError, KeyError):
                    pass  # best-effort; the pack replacement is the authoritative guard
            output = self.base / 'runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            steps = [('Build and verify the battle pack with RPFM',
                      lambda: probe.build(self.game, self.cli, output, roster=roster)),
                     ('Install the pack into the Three Kingdoms data folder',
                      lambda: probe.install(self.game, output))]
            if previous:
                # Safe: the installed pack's SHA-256 matches this recorded run.
                steps.insert(0, ('Replace the previous battle pack',
                                 lambda: probe.uninstall(self.game, previous)))
            for index, (label, step) in enumerate(steps):
                self._emit('install', {'index': index, 'label': label, 'status': 'run'})
                try:
                    step()
                except Exception:
                    self._emit('install', {'index': index, 'label': label, 'status': 'fail'})
                    raise
                self._emit('install', {'index': index, 'label': label, 'status': 'done'})
            manifest = json.loads((output / 'run.json').read_text(encoding='utf-8'))
            self.session.update(output=str(output), game=str(self.game))
            self._save_session()
            (output / config.SNAPSHOT_NAME).write_text(json.dumps(
                {'sha256': self.config_sha256, 'config': self.config}, indent=2), encoding='utf-8')
            self._emit('install', {'index': len(steps), 'label': 'Record run evidence', 'status': 'done'})
            staged = [sum(1 for u in manifest['expected_units'] if u['alliance'] == a) for a in (1, 2)]
            return {'ok': True, 'pack': probe.PACK_NAME,
                    'sha256': manifest['pack_sha256'], 'run': str(output), 'staged': staged,
                    'removed_previous': str(previous) if previous else None}
        except Exception as exc:
            return {'error': str(exc)}

    def launch_3k(self):
        """Start Three Kingdoms with only the battle pack enabled, skipping CA's mod manager."""
        try:
            # A running 3K has already cached its battle XML. Launching a second
            # instance would load the old pack, not the one we just installed.
            if self._process_running('Three_Kingdoms.exe'):
                raise ValueError('Three Kingdoms is already running. Close it first so '
                                 'it loads the new battle pack on the next launch.')
            if not (self.game / 'data' / probe.PACK_NAME).is_file():
                raise ValueError('The battle pack is not installed. Send the armies to Three Kingdoms first.')
            if self.session.get('output'):
                config.maybe_request_screenshots(self.session['output'],
                                                 bool(self.config.get('enable_tw3k_screenshots')))
            (self.game / TK_MOD_LIST).write_text(f'mod "{probe.PACK_NAME}";\n', encoding='utf-8')
            process = self._popen([str(self.game / 'Three_Kingdoms.exe'), f'{TK_MOD_LIST};'],
                                  cwd=str(self.game))
            return {'ok': True, 'pid': process.pid, 'note': f'started with {TK_MOD_LIST}'}
        except Exception as exc:
            return {'error': str(exc)}

    def verify_pack(self):
        """Check the installed pack still matches the current run's manifest."""
        try:
            run = self._require_run()
            manifest = json.loads((run / 'run.json').read_text(encoding='utf-8'))
            target = self.game / 'data' / probe.PACK_NAME
            if not target.exists():
                return {'ok': True, 'match': False, 'reason': 'Pack not installed.'}
            installed_sha = probe.digest(target)
            match = installed_sha == manifest.get('pack_sha256')
            return {'ok': True, 'match': match,
                    'reason': None if match else 'Installed pack differs from the current run.'}
        except Exception as exc:
            return {'error': str(exc)}

    def read_result(self):
        try:
            run = self._require_run()
            config.maybe_request_screenshots(run, bool(self.config.get('enable_tw3k_screenshots')))
            result = probe.read_result(run)
            staged = json.loads((run / 'run.json').read_text(encoding='utf-8')).get('sides') or []
            names = {s.get('role', '').lower(): s['name'] for s in staged}
            roles = ('attacker', 'defender')
            # The player's side fights as 3K alliance 1 (probe.generate seats it there).
            alliance_of = {result['player_side']: 1}
            alliance_of[roles[1 - roles.index(result['player_side'])]] = 2
            sides = []
            for role in roles:
                units = [u for u in result['units'] if u['alliance'] == alliance_of[role]]
                initial = sum(u['initial'] for u in units)
                survivors = sum(u['survivors'] for u in units)
                sides.append({'role': role, 'name': names.get(role, role.title()),
                              'men': initial, 'lost': initial - survivors,
                              'units': [{'script_name': u['script_name'],
                                         'unit_type': u['unit_type'],
                                         'initial': u['initial'],
                                         'survivors': u['survivors'],
                                         'lost': u['initial'] - u['survivors'],
                                         'routing': u['routing']} for u in units]})
            return {'ok': True,
                    'winner': roles.index(result['winner']) if result['winner'] in roles else None,
                    'player_side': roles.index(result['player_side']),
                    'player_outcome': result['player_outcome'],
                    'result_source': result['result_source'],
                    'note': result['limitation'],
                    'battle': result['battle'], 'run_id': result['run_id'],
                    'sides': sides}
        except Exception as exc:
            return {'error': str(exc)}

    def remove_probe(self):
        """Remove the installed pack, adopting an orphaned run if needed.

        The probe exe and the launcher share one runs folder; a pack installed
        by the other tool has no entry in this session. Any recorded run
        manifest whose pack hash matches the installed pack authorises
        removal. An installed pack that matches no manifest is never removed.
        """
        try:
            self._require_3k_closed()
            game = Path(self.session.get('game') or self.game)
            target = game / 'data' / probe.PACK_NAME
            if not target.exists():
                return {'ok': True, 'removed': probe.PACK_NAME,
                        'was_installed': False, 'run': None}
            run = self._run_for_installed_pack(target)
            if run is None:
                raise ValueError('The installed battle pack matches no recorded run; refusing to remove it.')
            probe.uninstall(game, run)
            return {'ok': True, 'removed': probe.PACK_NAME,
                    'was_installed': True, 'run': str(run)}
        except Exception as exc:
            return {'error': str(exc)}

    def _run_for_installed_pack(self, target):
        """The recorded run whose pack SHA-256 matches the installed pack, or None.

        Checks this session's run first, then every folder in the launcher's runs.
        """
        installed_sha = probe.digest(target)
        candidates = []
        if self.session.get('output'):
            candidates.append(Path(self.session['output']) / 'run.json')
        candidates.extend(sorted((self.base / 'runs').glob('*/run.json')))
        for manifest_path in candidates:
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            if manifest.get('pack_sha256') == installed_sha:
                return manifest_path.parent
        return None

    def preview_writeback(self):
        return {
            'error': 'Writing results into CK3 saves is off in this build. The result is kept as observed_result.json in the run folder.'
        }

    def apply_writeback(self):
        return {
            'error': 'Writing results into CK3 saves is off in this build. The result is kept as observed_result.json in the run folder.'
        }

    def close_3k(self, timeout=None):
        """Ask Three Kingdoms to exit gently, then force it if it hangs.

        taskkill without /F lets the game shut down cleanly; /F is only sent
        once the process is still there `timeout` seconds later.
        """
        timeout = CLOSE_GRACE if timeout is None else max(0, timeout)
        try:
            if not self._process_running('Three_Kingdoms.exe'):
                return {'ok': True, 'was_running': False, 'forced': False, 'note': 'not running'}
            self._taskkill(['taskkill', '/IM', 'Three_Kingdoms.exe'])
            if self._wait_3k_closed(timeout):
                return {'ok': True, 'was_running': True, 'forced': False, 'note': 'closed gently'}
            self._taskkill(['taskkill', '/F', '/IM', 'Three_Kingdoms.exe'])
            if self._wait_3k_closed(timeout):
                return {'ok': True, 'was_running': True, 'forced': True, 'note': 'closed forcefully'}
            raise ValueError('Three Kingdoms refused to close. Close it by hand, '
                             'then press Return to CK3 again.')
        except Exception as exc:
            return {'error': str(exc)}

    def _wait_3k_closed(self, timeout):
        """True once Three Kingdoms is gone; polls until `timeout` runs out."""
        deadline = time.monotonic() + timeout
        while self._process_running('Three_Kingdoms.exe'):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.5)
        return True

    def return_to_ck3(self):
        """Close Three Kingdoms, then start CK3 so the player continues the save."""
        try:
            closed = self.close_3k()
            if closed.get('error'):
                return closed  # CK3 is never started while Three Kingdoms still runs
            os.startfile(STEAM_CK3)
            return {'ok': True, 'was_running': closed['was_running'], 'forced': closed['forced'],
                    'note': closed['note'], 'continue': self._ck3_continue()}
        except Exception as exc:
            return {'error': str(exc)}

    def _ck3_continue(self):
        """The save CK3's own Continue button will load (continue_game.json), or None.

        CK3 has no launch flag that loads a save, so the player presses Continue
        in its main menu; this names the campaign that click resumes.
        """
        try:
            data = json.loads((self.saves.parent / 'continue_game.json').read_text(encoding='utf-8'))
        except (ValueError, OSError):
            return None
        info = {'title': data.get('title'), 'desc': data.get('desc'), 'date': data.get('date')}
        return info if info['title'] or info['desc'] else None
