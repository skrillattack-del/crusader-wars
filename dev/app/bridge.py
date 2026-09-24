"""CW2 launcher bridge: the real G1 probe pipeline behind the mockup screens.

CK3 comes first: the launcher reads the newest CK3 save (G2's read-only intake),
lists the battles in progress, and rolls both armies from vanilla 3K units at
the shared scale in dev/battle_math. Integrated from the G1 spike: build and
install the probe pack (removing a previous pack only when it matches a
recorded run), launch Three Kingdoms, read the strict result, remove the pack.
Not yet: staging the rolled roster (the pack still stages the proven 1 general
+ 2 units a side until the full-army spike) and CK3 write-back.

Every public method returns an envelope: {'ok': True, ...} or {'error': msg}.
The UI turns 'error' into a JS exception, so behaviour does not depend on how
pywebview serialises Python exceptions across the bridge.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
from datetime import datetime

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parents[0] / 'spikes' / 'g1_3k_io'),
           str(_HERE.parents[0] / 'spikes' / 'g2_ck3_writeback' / 'patcher'),
           str(_HERE.parents[0] / 'battle_math'), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import probe  # G1 spike: build, install, uninstall, read_result
import preflight  # G2 spike: read-only save intake and combat inventory
from roll import MODES, roll
from scale import stage

CK3_EXE = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\binaries\ck3.exe')
def _ck3_saves():
    # OneDrive often redirects Documents; prefer whichever copy actually has CK3 saves.
    home = Path(os.environ.get('USERPROFILE', str(Path.home())))
    roots = [Path(os.environ['OneDrive']) / 'Documents'] if os.environ.get('OneDrive') else []
    roots += [home / 'OneDrive' / 'Documents', home / 'Documents']
    folders = [r / 'Paradox Interactive' / 'Crusader Kings III' / 'save games' for r in roots]
    return next((f for f in folders if f.is_dir()), folders[-1])

CK3_SAVES = _ck3_saves()
STEAM_3K = 'steam://rungameid/779340'
STEAM_CK3 = 'steam://rungameid/1158310'
ARMY_OWNER = re.compile(r'type=army\b[^{}]*?owner=(\d+)[^{}]*?army=(\d+)')
STAGING_NOTE = ('Prepare and install still stages the proven probe roster (1 general + 2 units '
                'a side, Records Xingyang) until the full-army spike proves rolled rosters load.')
SESSION_NAME = 'cw2-launcher-session.json'

# Mirrors the roster probe.generate() stages into the Records Xingyang battle.
# Keep in sync with probe.py when the staged roster changes.
STAGED_SIDES = [
    {'role': 'Attacker', 'name': 'Cao Cao', 'faction': 'cao_cao',
     'units': [
         {'kind': 'general', 'key': '3k_main_general_earth_cao_cao', 'name': 'Cao Cao (Earth general)'},
         {'kind': 'unit', 'key': '3k_main_unit_wood_ji_militia', 'name': 'Ji Militia'},
         {'kind': 'unit', 'key': '3k_main_unit_water_archer_militia', 'name': 'Archer Militia'},
     ]},
    {'role': 'Defender', 'name': 'Liu Bei', 'faction': 'liu_bei',
     'units': [
         {'kind': 'general', 'key': '3k_main_general_earth_liu_bei', 'name': 'Liu Bei (Earth general)'},
         {'kind': 'unit', 'key': '3k_main_unit_wood_ji_militia', 'name': 'Ji Militia'},
         {'kind': 'unit', 'key': '3k_main_unit_water_archer_militia', 'name': 'Archer Militia'},
     ]},
]

NOT_INTEGRATED = ('CK3 write-back is not integrated into the launcher yet. The '
                  'G2 spike (dev/spikes/g2_ck3_writeback) is pre-integration; '
                  'this run keeps its result as observed_result.json in the '
                  'run folder for the future patcher.')


def _default_tasklist(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result.returncode, result.stdout

class Bridge:
    """js_api for the launcher window. See dev/app/ui/index.html for callers."""

    def __init__(self, base=None, game=None, cli=None, tasklist=None, saves=None):
        self.base = Path(base) if base else self._default_base()
        self.game = Path(game) if game else probe.GAME
        self.saves = Path(saves) if saves else CK3_SAVES
        self._save_cache = None
        self.cli = Path(cli) if cli else self._find_cli()
        self._tasklist = tasklist or _default_tasklist
        self._window = None
        self.session = {'output': None}
        state = self.base / SESSION_NAME
        if state.is_file():
            try:
                self.session.update(json.loads(state.read_text(encoding='utf-8')))
            except (ValueError, OSError):
                pass

    @staticmethod
    def _default_base():
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        return _HERE

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
            raise ValueError('Close Three Kingdoms before changing the probe pack.')

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

    # ---- js_api surface (names match the mockup contract) --------------

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
                    'paths': paths,
                    'gates': {'ck3': self.saves.is_dir(),
                              'probe': all(p['ok'] for p in paths
                                           if p['key'] in ('tk_exe', 'rpfm_cli'))}}
        except Exception as exc:
            return {'error': str(exc)}

    def _latest_save(self):
        saves = [p for p in self.saves.glob('*.ck3') if p.is_file()]
        if not saves:
            raise ValueError(f'No .ck3 saves in {self.saves}. Pause during a battle in CK3 and save.')
        return max(saves, key=lambda p: p.stat().st_mtime)

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
        battles = []
        for row in rows:
            sides = []
            for role in ('attacker', 'defender'):
                data = row[role]
                commander_id = data.get('commander')
                char_ids = data.get('characters', [])
                knights = []
                for cid in char_ids:
                    if cid == commander_id: continue
                    rng = random.Random(int(cid))
                    knights.append({'name': f'Knight {cid}', 'prowess': rng.randint(5, 25)})
                commander = None
                if commander_id:
                    rng = random.Random(int(commander_id))
                    commander = {'name': f'Commander {commander_id}', 'prowess': rng.randint(10, 30)}
                sides.append({'role': role.title(), 'army_ids': data['army_ids'],
                              'name': f"{role.title()} · army {', '.join(data['army_ids'])}",
                              'initial': float(data['initial_men']),
                              'fighting': float(data['total_fighting_men']),
                              'commander': commander,
                              'knights': knights,
                              'yours': any(owner.get(a) in players for a in data['army_ids'])})
            battles.append({'combat_id': row['combat_id'], 'phase': row['phase'], 'sides': sides,
                            'yours': any(s['yours'] for s in sides)})
        data = {'date': date.group(1) if date else None, 'battles': battles}
        self._save_cache = (key, data)
        return data

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
                    'phase': chosen['phase'], 'yours': chosen['yours'],
                    'battles': [{'combat_id': b['combat_id'], 'yours': b['yours'], 'phase': b['phase'],
                                 'men': [round(s['fighting']) for s in b['sides']]} for b in battles],
                    'sides': chosen['sides']}
        except Exception as exc:
            return {'error': str(exc)}

    def roll_roster(self, encounter=None, seed=None, mode='records'):
        """Stage both sides at one scale and roll vanilla 3K units onto the cards.

        mode: 'records' (generals lead a bodyguard card) or 'romance' (generals are single heroes).
        """
        try:
            if not encounter or len(encounter.get('sides') or []) != 2:
                raise ValueError('Pick a CK3 battle first.')
            if mode not in MODES:
                raise ValueError(f'Unknown mode {mode!r}; use records or romance.')
            seed = int(seed) if seed not in (None, '') else random.randrange(1, 10**7)
            scale, *staged = stage(*(float(s['fighting']) for s in encounter['sides']),
                                   general_size=MODES[mode]['general_size'])
            rolled = roll(encounter['sides'][0], encounter['sides'][1], *staged, seed, mode)
            sides = []
            for spec, side, generals in zip(encounter['sides'], staged, rolled):
                sides.append({'role': spec['role'], 'name': spec['name'], 'fighting': spec['fighting'],
                              'men': side.men, 'trim': side.trim, 'cards': side.cards,
                              'retinue': side.units, 'generals': generals})
            note = STAGING_NOTE + (' Romance staging is untested: the probe replaces only Records Xingyang.'
                                   if mode == 'romance' else '')
            return {'ok': True, 'seed': seed, 'mode': mode, 'deterministic': False, 'scale': scale,
                    'note': note, 'sides': sides}
        except Exception as exc:
            return {'error': str(exc)}

    def launch_ck3(self):
        try:
            os.startfile(STEAM_CK3)
            return {'ok': True, 'note': 'launched through Steam'}
        except Exception as exc:
            return {'error': str(exc)}

    def prepare_and_install(self, roster=None):
        try:
            self._require_3k_closed()
            if not (self.game / 'Three_Kingdoms.exe').is_file() or not self.cli.is_file():
                raise ValueError('Select the installed Three Kingdoms folder and rpfm_cli.exe.')
            target = self.game / 'data' / probe.PACK_NAME
            previous = self._run_for_installed_pack(target) if target.exists() else None
            if target.exists() and previous is None:
                raise ValueError('An unrecognised probe pack is installed: it matches no recorded run, '
                                 'so CW2 will not delete it. Remove it by hand.')
            output = self.base / 'runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            steps = [('Build and verify the probe pack with RPFM',
                      lambda: probe.build(self.game, self.cli, output)),
                     ('Install the pack into the Three Kingdoms data folder',
                      lambda: probe.install(self.game, output))]
            if previous:
                # Safe: the installed pack's SHA-256 matches this recorded run.
                steps.insert(0, ('Remove the previous probe pack',
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
            self._emit('install', {'index': len(steps), 'label': 'Record run evidence', 'status': 'done'})
            return {'ok': True, 'pack': probe.PACK_NAME,
                    'sha256': manifest['pack_sha256'], 'run': str(output),
                    'removed_previous': str(previous) if previous else None}
        except Exception as exc:
            return {'error': str(exc)}

    def launch_3k(self):
        try:
            os.startfile(STEAM_3K)
            return {'ok': True, 'pid': None,
                    'note': 'launched through Steam; the launcher does not track the process'}
        except Exception as exc:
            return {'error': str(exc)}

    def read_result(self):
        try:
            run = self._require_run()
            result = probe.read_result(run)
            sides = []
            for index, role in enumerate(('attacker', 'defender')):
                units = [u for u in result['units'] if u['alliance'] == index + 1]
                initial = sum(u['initial'] for u in units)
                survivors = sum(u['survivors'] for u in units)
                sides.append({'role': role, 'name': STAGED_SIDES[index]['name'],
                              'men': initial, 'lost': initial - survivors,
                              'units': [{'script_name': u['script_name'],
                                         'unit_type': u['unit_type'],
                                         'initial': u['initial'],
                                         'survivors': u['survivors'],
                                         'lost': u['initial'] - u['survivors'],
                                         'routing': u['routing']} for u in units]})
            return {'ok': True,
                    'winner': 0 if result['winner'] == 'attacker' else None,
                    'player_side': 0,
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
                raise ValueError('The installed probe pack matches no recorded run; refusing to remove it.')
            probe.uninstall(game, run)
            return {'ok': True, 'removed': probe.PACK_NAME,
                    'was_installed': True, 'run': str(run)}
        except Exception as exc:
            return {'error': str(exc)}

    def _run_for_installed_pack(self, target):
        """The recorded run whose pack SHA-256 matches the installed pack, or None.

        Checks this session's run first, then every run folder: the launcher's
        own and dev/dist/runs, where the probe exe records its runs.
        """
        installed_sha = probe.digest(target)
        candidates = []
        if self.session.get('output'):
            candidates.append(Path(self.session['output']) / 'run.json')
        for folder in dict.fromkeys((self.base / 'runs', _HERE.parent / 'dist' / 'runs')):
            candidates.extend(sorted(folder.glob('*/run.json')))
        for manifest_path in candidates:
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            if manifest.get('pack_sha256') == installed_sha:
                return manifest_path.parent
        return None

    def _get_run_dir(self):
        # Find the latest run folder
        runs_dir = _HERE.parents[0] / 'dist' / 'runs'
        if not runs_dir.exists():
            return None
        dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
        if not dirs:
            return None
        return max(dirs, key=lambda d: d.stat().st_mtime)

    def preview_writeback(self):
        """Build ck3_casualties, generate a synthetic_result structure, and plan mutations."""
        run_dir = self._get_run_dir()
        if not run_dir:
            return {'error': 'No run found.'}
        
        obs_path = run_dir / 'observed_result.json'
        if not obs_path.exists():
            return {'error': 'No observed result found.'}
        obs = json.loads(obs_path.read_text(encoding='utf-8'))
        
        from result_to_ck3 import ck3_casualties
        
        # We need the original CK3 side info from the encounter
        if not self._encounter:
            return {'error': 'No encounter loaded.'}
            
        encounter = self._encounter
        
        # Build the side data for ck3_casualties
        # It expects {'attacker': ck3_men, 'defender': ck3_men}
        # And {'attacker': (staged_initial, staged_survivors), ...}
        ck3_men = {s['role'].lower(): s['fighting'] for s in encounter['sides']}
        
        staged = {}
        for s in obs['units']:
            side_key = 'attacker' if s['alliance'] == 1 else 'defender'
            if side_key not in staged:
                staged[side_key] = [0, 0]
            staged[side_key][0] += s['initial']
            staged[side_key][1] += s['survivors']
            
        staged_tuples = {k: (v[0], v[1]) for k, v in staged.items()}
        winner = obs.get('winner')
        
        casualties = ck3_casualties(ck3_men, staged_tuples, winner)
        
        # Create a synthetic result for apply.py
        synthetic_result = {
            'result_id': obs['run_id'],
            'battle_id': encounter['combat_id'],
            'sides': {
                'attacker': {'synthetic_casualties': casualties.get('attacker', {}).get('dead', 0)},
                'defender': {'synthetic_casualties': casualties.get('defender', {}).get('dead', 0)}
            }
        }
        
        # Save synthetic_result to run folder for apply.py to use
        (run_dir / 'synthetic_result.json').write_text(json.dumps(synthetic_result, indent=2))
        
        try:
            import apply
            import preflight
            before_path = encounter['save']
            gamestate_text, kind = preflight.read_gamestate(before_path)
            
            # Write linked_records.json using preflight logic if it's missing
            linked_records_path = run_dir / 'linked_records.json'
            if not linked_records_path.exists():
                _, linked_records = preflight.intake(before_path, encounter['combat_id'])
                linked_records_path.write_text(json.dumps(linked_records, indent=2))
            else:
                linked_records = json.loads(linked_records_path.read_text(encoding='utf-8'))
                
            changes = apply.plan_mutations(gamestate_text, synthetic_result, linked_records)
            self._cached_changes = changes
            self._cached_gamestate = gamestate_text
            self._cached_kind = kind
            self._cached_run_dir = run_dir
            
            return {
                'casualties': casualties,
                'changes': [{'path': c.path, 'before': c.before, 'after': c.after} for c in changes]
            }
        except Exception as e:
            return {'error': str(e)}

    def apply_writeback(self):
        if not hasattr(self, '_cached_changes'):
            return {'error': 'Must preview writeback first.'}
            
        try:
            import apply
            import zipfile
            import json
            
            new_gamestate = apply.apply_mutations(self._cached_gamestate, self._cached_changes)
            
            out_name = f"CW2_{self._encounter['combat_id']}_AFTER.ck3"
            save_dir = Path(self._encounter['save']).parent
            final_out_path = save_dir / out_name
            tmp_out_path = self._cached_run_dir / 'tmp.ck3'
            
            if final_out_path.exists():
                return {'error': f'Output file {out_name} already exists.'}
            
            if self._cached_kind == 'zip':
                with zipfile.ZipFile(tmp_out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr('gamestate', new_gamestate.encode('utf-8'))
            else:
                tmp_out_path.write_bytes(new_gamestate.encode('utf-8'))
                
            tmp_out_path.replace(final_out_path)
            
            # Seal journal
            journal_path = self._cached_run_dir / 'journal.json'
            journal = {}
            if journal_path.exists():
                journal = json.loads(journal_path.read_text(encoding='utf-8'))
            synthetic_result = json.loads((self._cached_run_dir / 'synthetic_result.json').read_text())
            
            journal[synthetic_result['result_id']] = {
                'battle_id': synthetic_result['battle_id'],
                'status': 'applied'
            }
            journal_path.write_text(json.dumps(journal, indent=2))
            
            return {'status': 'success', 'after_save': str(final_out_path)}
        except Exception as e:
            return {'error': str(e)}



