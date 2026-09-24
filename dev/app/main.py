"""Crusader Wars 2 launcher: a pywebview window whose js_api is dev/app/bridge.py.

Assets ship inside the exe (sys._MEIPASS); runs and session state are written
beside the exe.
"""
import argparse
from pathlib import Path
import sys


def _assets_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _data_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='Crusader Wars 2 launcher.')
    parser.add_argument('--smoke-test', action='store_true',
                        help='verify assets and the bridge without opening a window')
    args = parser.parse_args()

    index = _assets_root() / 'ui' / 'index.html'
    if not index.is_file():
        raise RuntimeError(f'Launcher UI asset is missing: {index}')

    from bridge import Bridge
    bridge = Bridge(base=_data_root())

    if args.smoke_test:
        health = bridge.get_health()
        encounter = bridge.get_encounter()
        roster = bridge.roll_roster(encounter)
        if health.get('error') or not health.get('paths'):
            raise RuntimeError(f'health check failed: {health}')
        if len(encounter.get('sides', [])) != 2:
            raise RuntimeError('staged encounter does not have two sides')
        if any(len(side.get('units', [])) != 3 for side in roster.get('sides', [])):
            raise RuntimeError('staged roster does not have three unit cards per side')
        if getattr(sys, 'frozen', False):
            import probe
            if not (probe.HERE / 'probe.lua').is_file():
                raise RuntimeError('Packaged Lua resource is missing.')
        import webview  # verifies pywebview and its Windows backend landed in the bundle
        print('launcher smoke OK')
        return

    import webview
    window = webview.create_window('Crusader Wars 2', str(index), js_api=bridge,
                                   width=1000, height=780, min_size=(720, 560))
    bridge.attach(window)
    webview.start()


if __name__ == '__main__':
    main()
