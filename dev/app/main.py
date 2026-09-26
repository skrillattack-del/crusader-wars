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
        if health.get('error') or not health.get('paths'):
            raise RuntimeError(f'health check failed: {health}')
        # A fixed battle: the newest CK3 save may be a binary autosave or hold no battle.
        sides = [{'role': role, 'name': role, 'fighting': men} for role, men in (('Attacker', 340.0), ('Defender', 421.0))]
        roster = bridge.roll_roster({'sides': sides}, seed=1)
        if roster.get('error') or not all(side['generals'] for side in roster['sides']):
            raise RuntimeError(f'roster roll failed: {roster}')
        if getattr(sys, 'frozen', False):
            import probe
            for resource in ('probe.lua', 'frontend_open.lua'):
                if not (probe.HERE / resource).is_file():
                    raise RuntimeError(f'Packaged Lua resource is missing: {resource}')
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
