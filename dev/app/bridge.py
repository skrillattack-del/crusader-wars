"""CW2 launcher bridge: the real G1 probe pipeline behind the mockup screens.

Integrated today (verified by the G1 spike): build and install the staged probe
pack, launch Three Kingdoms, read the strict battle result, remove the pack.
Not integrated and never faked: CK3 encounter extraction, the roster roll and
CK3 write-back - those report honest errors (see docs/design/FRONTEND_DESIGN.md
section 10).

Every public method returns an envelope: {'ok': True, ...} or {'error': msg}.
The UI turns 'error' into a JS exception, so behaviour does not depend on how
pywebview serialises Python exceptions across the bridge.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parents[0] / 'spikes' / 'g1_3k_io'), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import probe  # G1 spike: build, install, uninstall, read_result

CK3_EXE = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\binaries\ck3.exe')
CK3_SAVES = (Path(os.environ.get('USERPROFILE', str(Path.home())))
             / 'Documents' / 'Paradox Interactive' / 'Crusader Kings III' / 'save games')
STEAM_3K = 'steam://rungameid/779340'
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

    def __init__(self, base=None, game=None, cli=None, tasklist=None):
        self.base = Path(base) if base else self._default_base()
        self.game = Path(game) if game else probe.GAME
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
                 'value': str(CK3_SAVES), 'ok': CK3_SAVES.is_dir()},
                {'key': 'rpfm_cli', 'label': 'RPFM command line',
                 'value': str(self.cli), 'ok': self.cli.is_file()},
            ]
            return {'ok': True,
                    'ck3_running': self._process_running('ck3.exe'),
                    'tk_running': self._process_running('Three_Kingdoms.exe'),
                    'probe_installed': (self.game / 'data' / probe.PACK_NAME).exists(),
                    'paths': paths,
                    'gates': {'probe': all(p['ok'] for p in paths
                                           if p['key'] in ('tk_exe', 'rpfm_cli'))}}
        except Exception as exc:
            return {'error': str(exc)}

    def get_encounter(self):
        try:
            sides = [{'role': s['role'], 'name': s['name'],
                      'cards': len(s['units']), 'retinue': len(s['units']) - 1,
                      'units': json.loads(json.dumps(s['units']))} for s in STAGED_SIDES]
            return {'ok': True, 'id': 'g1-xinyang-records', 'entry': probe.BATTLE,
                    'location': 'Xingyang', 'mode': 'Records historical battle',
                    'note': ('G1 staged probe battle. The CK3 encounter extractor is '
                             'not integrated yet, so the launcher stages the fixed '
                             'probe roster instead of reading an encounter from a save.'),
                    'sides': sides}
        except Exception as exc:
            return {'error': str(exc)}

    def roll_roster(self, encounter=None, seed=None):
        """The G1 roster is fixed by the probe pack, not rolled.

        Kept under the mockup name so the UI contract stays stable for the
        real roll once the extractor is integrated; the seed is ignored. The
        shape mirrors the mockup's generals/retinue structure: one commanding
        general per side leading two unique retinue units.
        """
        try:
            sides = []
            for spec in STAGED_SIDES:
                general, units = spec['units'][0], spec['units'][1:]
                sides.append({'role': spec['role'], 'name': spec['name'],
                              'retinue': len(units), 'cards': len(spec['units']),
                              'generals': [{'name': spec['name'], 'role': 'Commander',
                                            'prowess': None, 'retinue': len(units),
                                            'units': json.loads(json.dumps(spec['units']))}]})
            return {'ok': True, 'seed': None, 'deterministic': True,
                    'note': ('The probe stages one commanding general and two unique '
                             'retinue units per side; nothing is rolled until the CK3 '
                             'extractor and roster roll are integrated.'),
                    'sides': sides}
        except Exception as exc:
            return {'error': str(exc)}

    def prepare_and_install(self, roster=None):
        try:
            self._require_3k_closed()
            if (self.game / 'data' / probe.PACK_NAME).exists():
                raise ValueError('Remove the installed probe before preparing a fresh run.')
            output = self.base / 'runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            steps = ((0, 'Build and verify the probe pack with RPFM',
                      lambda: probe.build(self.game, self.cli, output)),
                     (1, 'Install the pack into the Three Kingdoms data folder',
                      lambda: probe.install(self.game, output)))
            for index, label, step in steps:
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
            self._emit('install', {'index': 2, 'label': 'Record run evidence', 'status': 'done'})
            return {'ok': True, 'pack': probe.PACK_NAME,
                    'sha256': manifest['pack_sha256'], 'run': str(output)}
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
            run = None
            session_run = self.session.get('output')
            if session_run and (Path(session_run) / 'run.json').is_file():
                manifest = json.loads((Path(session_run) / 'run.json').read_text(encoding='utf-8'))
                if manifest.get('pack_sha256') == probe.digest(target):
                    run = Path(session_run)
            if run is None:
                run = self._find_run_for_installed_pack(target)
            if run is None:
                raise ValueError('The installed probe pack matches no recorded run; refusing to remove it.')
            probe.uninstall(game, run)
            return {'ok': True, 'removed': probe.PACK_NAME,
                    'was_installed': True, 'run': str(run)}
        except Exception as exc:
            return {'error': str(exc)}

    def _find_run_for_installed_pack(self, target):
        installed_sha = probe.digest(target)
        for manifest_path in sorted((self.base / 'runs').glob('*/run.json')):
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            if manifest.get('pack_sha256') == installed_sha:
                return manifest_path.parent
        return None

    def preview_writeback(self):
        return {'error': NOT_INTEGRATED}

    def apply_writeback(self):
        return {'error': NOT_INTEGRATED}



