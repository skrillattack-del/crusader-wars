"""Crusader Wars 2 launcher: a pywebview window whose js_api is dev/app/bridge.py.

Runs from source: `python dev/app/main.py`. Runs, backups and session state are
written beside this file (dev/app/runs, dev/app/backups, cw2-launcher-session.json).
"""
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='Crusader Wars 2 launcher.')
    parser.add_argument('--smoke-test', action='store_true',
                        help='verify assets and the bridge without opening a window')
    args = parser.parse_args()

    index = HERE / 'ui' / 'index.html'
    if not index.is_file():
        raise RuntimeError(f'Launcher UI asset is missing: {index}')

    from bridge import Bridge
    bridge = Bridge(base=HERE)

    if args.smoke_test:
        health = bridge.get_health()
        if health.get('error') or not health.get('paths'):
            raise RuntimeError(f'health check failed: {health}')
        if not health.get('config', {}).get('valid'):
            raise RuntimeError(f'options ledger is invalid: {health["config"]}')
        # A fixed battle: the newest CK3 save may be a binary autosave or hold no battle.
        sides = [{'role': role, 'name': role, 'fighting': men} for role, men in (('Attacker', 340.0), ('Defender', 421.0))]
        roster = bridge.roll_roster({'sides': sides}, seed=1)
        if roster.get('error') or not all(side['generals'] for side in roster['sides']):
            raise RuntimeError(f'roster roll failed: {roster}')
        skins = HERE / 'ui' / 'skins'
        for art in ('ck3/cinzel.ttf', 'ck3/two.jpg', 'ck3/rail.jpg',
                    '3k/head.jpg', '3k/dragon.jpg'):
            if not (skins / art).is_file():
                raise RuntimeError(f'Launcher skin asset is missing: {skins / art}')
        import webview  # the window library: pip install pywebview
        print('launcher smoke OK')
        return

    import webview
    window = webview.create_window('Crusader Wars 2', str(index), js_api=bridge,
                                   width=1000, height=780, min_size=(720, 560))
    bridge.attach(window)
    webview.start()


if __name__ == '__main__':
    main()
