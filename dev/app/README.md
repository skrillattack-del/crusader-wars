# Launcher

pywebview window (`main.py`) around `bridge.py`; the UI is `ui/index.html`
(its script is `ui/app.js`, inlined). Steps: start in CK3, pick the battle,
roll armies, fight in 3K, write back.

- Run: `python dev/app/main.py`
- Build: `powershell -ExecutionPolicy Bypass -File dev/build_launcher.ps1`
- Tests: `python -m unittest discover -s dev/app -p "test_*.py"`; UI: `node dev/app/ui/index.smoke.cjs`
- Self-check: `CW2-Launcher.exe --smoke-test`

Runs and `cw2-launcher-session.json` are written beside the exe. The battle
pack currently fights 1 general + 2 units a side; writing results into CK3
saves is off, and each result stays in its run folder as `observed_result.json`.
