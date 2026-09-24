# CW2 launcher (G1 scope)

The launcher mockup shipped as a real Windows app: a pywebview window around
the verified G1 probe pipeline. Per docs/design/FRONTEND_DESIGN.md, the shell is
pywebview and the UI is the mockup's screens with the MockBridge deleted.

What is real in this build:
- `get_health`: live path checks (CK3 exe, 3K exe, CK3 save folder, RPFM CLI)
  and process detection for both games.
- `get_encounter` / `roll_roster`: the staged G1 probe battle and its fixed
  roster (Cao Cao vs Liu Bei, one general + two units per side). Honest
  labels, not CK3 data: the encounter extractor does not exist yet.
- `prepare_and_install` / `launch_3k` / `read_result` / `remove_probe`: the
  verified probe pipeline (`spikes/g1_3k_io/probe.py`). Pack progress is
  pushed to the UI as `install` events while building.
- `preview_writeback` / `apply_writeback`: honest "not integrated yet" errors.
  No screen fakes CK3 data.

Every bridge method returns `{'ok': ...}` or `{'error': msg}`; the UI turns
`error` into a JS exception, so behaviour does not depend on how pywebview
serialises Python exceptions across the bridge.

UI divergence from the mockup (deliberate, G1 scope):
- Encounter/roster screens show the staged probe battle instead of CK3
  levies/knights and the seed roll (nothing is rolled yet).
- The battle screen adds a "Remove probe pack" button and renders per-unit
  survivors with the result source and its limitation note.
- The write-back screen states it is not integrated instead of faking a diff.
- Fonts are not bundled yet (offline fallback stacks); FRONTEND_DESIGN.md
  still tracks that task. The canonical mockup (`docs/design/`) is the source
  this UI derives from; the root copy went stale after the generals revision.

When the extractor, roster roll and write-back are integrated, these screens
converge back to the mockup.

Run from source: `python dev/app/main.py`
Build: `powershell -ExecutionPolicy Bypass -File dev/build_launcher.ps1`
  -> `dev/dist/CW2-Launcher.exe` (PyInstaller onefile, windowed; needs the
  WebView2 runtime, standard on Windows 10/11).
Tests: `python -m unittest discover -s dev/app -p "test_*.py"`
UI smoke (Node): `node dev/app/ui/index.smoke.cjs`
Frozen self-check: `CW2-Launcher.exe --smoke-test` (exit 0 on success).

Session and run evidence are written beside the exe (`dev/dist` when built):
`cw2-launcher-session.json` and `runs/<timestamp>/`, exactly like the probe
exe. Use one tool per run: prepare and remove must share one session file.
