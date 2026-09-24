# Crusader Wars 2

Fight Crusader Kings III battles in Total War: THREE KINGDOMS.

**Play:** double-click `dev/dist/CW2-Launcher.exe` (or the desktop shortcut).
Pause in CK3 while a battle is on and save, then in the launcher: load the save,
pick the battle, roll armies (Records or Romance), Prepare and install, fight in
3K, read the result.

**Build:** `powershell -ExecutionPolicy Bypass -File dev/build_launcher.ps1`.
Needs Python 3.12 with pywebview and PyInstaller, and RPFM's CLI in
`dev/tools/rpfm/` (git-ignored).

**Layout:** `dev/app` launcher, `dev/battle_math` army scaling and rolls,
`dev/spikes/*` the pack builder, CK3 save reader and extractor, `dev/mod` the
CK3 mod (local only, see `docs/third_party/CW1_LICENCE.md`).

Game installs, saves and anything extracted from the games stay out of git.
