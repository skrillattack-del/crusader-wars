# Crusader Wars 2

Fight Crusader Kings III battles in Total War: THREE KINGDOMS.

**Play:** double-click `Crusader Wars 2.cmd` (it runs `dev/app/main.py` with the
project's `.venv`; a desktop shortcut can point at it), then in CK3
press **Fight this battle in Three Kingdoms** on a battle. The launcher picks up
the save, rolls both armies, installs the battle pack and starts 3K, which opens
the **CRUSADER WARS II** lobby. Check both armies, press **FIGHT**, fight the
battle, then read the result in the launcher and press
**Return to CK3** to continue your CK3 save.

**Setup:** Python 3.12 with `pip install -r dev/requirements.txt`, and RPFM's CLI
in `dev/tools/rpfm/` (git-ignored). There is no build step.

## How one battle flows

1. **CK3 mod** (`dev/mod/cw2_ck3_mod`): the battle button logs the battle name
   and autosaves.
2. **Launcher** (`dev/app/bridge.py`): `poll_battle` spots that save,
   `get_encounter` reads the combat from it, and `roll_roster` scales both
   sides and rolls 3K units (`dev/battle_math/scale.py`, `roll.py`). Each side
   gets up to 3 generals, each leading up to 6 units.
3. **Battle pack** (`dev/spikes/g1_3k_io/probe.py`): stages that roll on the
   Battle of Xingyang map — the Records XML for Records mode, the game's own
   `_romance` Xingyang XML for Romance mode (hero generals, 1 man each) — adds
   the battle script (`probe.lua`) that trims each card to its rolled size and
   logs the battle, and adds the in-game lobby: its script
   (`frontend_lobby.lua`), layout and art (`lobby/`). Everything is packed with
   RPFM into `crusader_wars_2.pack`.
4. **3K**: starts with only that pack enabled. The lobby adds
   Battle → **CRUSADER WARS II** to the main menu and opens itself once for a
   fresh battle, showing both CK3 commanders and the staged roll. **FIGHT**
   clicks Battle → Historical Battle → Xingyang → Start, ticking or unticking
   the Romance checkbox to match the run's mode.
5. **Result**: `read_result` checks the run's battle log against `run.json` and
   shows who won and each side's losses (a unit wiped out in 3K disappears from
   its results capture, so it is read back as fully lost). **Return to CK3**
   closes Three Kingdoms and starts CK3, whose Continue button resumes the
   campaign save. Writing results back into the CK3 save is off for now.

Each run keeps its pack, manifest and logs in `dev/app/runs/<time>/`. The
lobby logs every step to that run's `frontend.log`; 3K's own mod loader writes
`lua_frontend_mod_log.txt` in the game folder.

## Known issues (playtest, 25 Sep 2026)

- The in-game lobby (26 Sep) has only run against a mock of 3K's UI; it has not
  been seen in the game yet. If it doesn't appear, open Battle → Historical
  Battle → Xingyang by hand. Shuffle and Lock stay in the launcher: 3K loads
  one staged roll per launch.
- The trim takes effect after the battle's start snapshot, so trimmed men are
  counted as battle losses.
- Units that are smaller than 80 men in 3K keep their size, so a side can come
  out smaller than rolled: 1,023 men instead of 1,503 in the test.
- Every battle uses the Xingyang map and generic generals (Romance rolls the
  generic heroes `3k_main_hero_{metal,wood}_generic`; the native Romance
  Xingyang XML ships no generic earth hero). Romance staging is built and
  verified against the installed game files, but no Romance battle has been
  fought live yet.

**Layout:** `dev/app` launcher, `dev/battle_math` army scaling and rolls,
`dev/spikes/*` the pack builder, CK3 save reader and extractor, `dev/mod` the
CK3 mod (local only, see `docs/third_party/CW1_LICENCE.md`), `config/` the
options ledger, `schemas/` its contract.

## Options

One ledger holds every launcher option: `config/cw2_config.json`, validated
against `schemas/config.schema.json`. The launcher discovers it by walking up
from `dev/app` and seeds the defaults on a first run; the gear button in the
title bar opens an Options panel that edits it in-app (rejected keys bounce
back with the schema's complaint), the setup screen shows the effective
values, and every run folder keeps a `cw2_config.snapshot.json` of the ledger
it ran under.

- `show_mode` (`dramatic|tactical|minimal`): density of the result screen.
- `army_scale_factor`: scales both CK3 armies before staging (3K caps still apply).
- `auto_battle_report`: on, the Fight step advances to the result by itself.
- `domain_focus` (`wei|shu|wu|custom`): filters other factions' unique units
  out of rolls (faction tags are a playtest draft; `custom` keeps the full pool).
- `injectivity_strict`: guards `config/slots.registry.json`, the CK3 character
  ↔ CW2 general-slot bijection.
- `enable_tw3k_screenshots`: records the request in the run folder; no capture
  backend yet.
- `cut_3d_voice`: reserved, formally UNDEFINED (canon, turn-2 §4) — stored, but
  nothing reads it.

Game installs, saves and anything extracted from the games stay out of git.
