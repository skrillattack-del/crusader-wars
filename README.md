# Crusader Wars 2

Fight Crusader Kings III battles in Total War: THREE KINGDOMS.

**Play:** open `dev/dist/CW2-Launcher.exe` (or the desktop shortcut), then in CK3
press **Fight this battle in Three Kingdoms** on a battle. The launcher picks up
the save, rolls both armies, installs the battle pack and starts 3K, which opens
the battle by itself. Fight it, then read the result in the launcher.

**Build:** `powershell -ExecutionPolicy Bypass -File dev/build_launcher.ps1`.
Needs Python 3.12 with pywebview and PyInstaller, and RPFM's CLI in
`dev/tools/rpfm/` (git-ignored).

## How one battle flows

1. **CK3 mod** (`dev/mod/cw2_ck3_mod`): the battle button logs the battle name
   and autosaves.
2. **Launcher** (`dev/app/bridge.py`): `poll_battle` spots that save,
   `get_encounter` reads the combat from it, and `roll_roster` scales both
   sides and rolls 3K units (`dev/battle_math/scale.py`, `roll.py`). Each side
   gets up to 3 generals, each leading up to 6 units.
3. **Battle pack** (`dev/spikes/g1_3k_io/probe.py`): stages that roll on the
   Records Battle of Xingyang map (`battle.xml`), adds the battle script
   (`probe.lua`) that trims each card to its rolled size and logs the battle,
   and adds the frontend opener (`frontend_open.lua`). Everything is packed with
   RPFM into `crusader_wars_2.pack`.
4. **3K**: starts with only that pack enabled. The opener clicks
   Battle → Historical Battle → Xingyang → Start, once per run.
5. **Result**: `read_result` checks the run's battle log against `run.json` and
   shows who won and each side's losses. Writing results back into the CK3
   save is off for now.

Each run keeps its pack, manifest and logs in `dev/dist/runs/<time>/`. If the
opener stalls, its steps are in that run's `frontend.log`.

## Known issues (playtest, 25 Sep 2026)

- The opener reaches Historical Battles, then hits a Lua error in its UI search
  (`frontend_open.lua`), so the battle has to be selected by hand.
- The trim takes effect after the battle's start snapshot, so trimmed men are
  counted as battle losses.
- Units that are smaller than 80 men in 3K keep their size, so a side can come
  out smaller than rolled: 1,023 men instead of 1,503 in the test.
- Every battle uses the Xingyang map and generic generals. Romance mode is not
  staged yet.

**Layout:** `dev/app` launcher, `dev/battle_math` army scaling and rolls,
`dev/spikes/*` the pack builder, CK3 save reader and extractor, `dev/mod` the
CK3 mod (local only, see `docs/third_party/CW1_LICENCE.md`).

Game installs, saves and anything extracted from the games stay out of git.
