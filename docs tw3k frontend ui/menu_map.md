# TW3K Frontend — Main Menu Map

Source: screenshot 2026-09-26, build `v1.7.1 Build 12\6.37276` (modded).
Layout: left rail menu over blurred campaign-map backdrop. Emperor seal icon top-right.

## Menu tree

| Group | Item | Emphasis |
|---|---|---|
| CAMPAIGN | NEW | default focus (red banner) |
| CAMPAIGN | MULTIPLAYER | |
| BATTLE | NEW | |
| BATTLE | MULTIPLAYER | |
| BATTLE | DYNASTY MODE | |
| BATTLE | REPLAYS | |
| EXTRA | OPTIONS | |
| EXTRA | CREDITS | |
| EXTRA | DLC | |
| EXTRA | QUIT | |

## Observations

- Groups are underlined headers; items are not individually framed.
- Native component IDs are `btn_new_campaign`, `btn_new_battle`,
  `btn_dynasty_mode`, `btn_replays`, `btn_options`, and `version_number`.
- The current CW2 bridge does **not** intercept `CAMPAIGN > NEW`. Its opener follows
  `BATTLE > NEW` (`btn_new_battle`) → `HISTORICAL BATTLE`
  (`button_historical_battle`) → Xingyang → Records → Start. The proposed dedicated
  `BATTLE > CRUSADER WARS II` item in the mock-up is therefore a new frontend surface,
  not a rename of the existing hook.
- `EXTRA > OPTIONS` is where the [runtime config ledger](../schemas/config.schema.json)
  surface would live if exposed in-game; otherwise it stays launcher-side.
- `BATTLE > REPLAYS` is the native read-back surface for saved replays, but CW2 does not
  currently depend on it. `auto_battle_report` reads the run's probe JSONL directly;
  `enable_tw3k_screenshots` currently writes a request flag and has no capture backend.
- The bottom-right stamp is the `version_number` component, bound to
  `CcoGameCore.BuildNumberShort`. It is a possible visual anchor for a future runtime
  probe, but CW2 does not currently inspect it; installed/modded state is detected from
  files and the dedicated launch mod list.

## Probe attachment — resolved

- **G1 (active):** `probe.py` packs `frontend_open.lua` as
  `script/frontend/mod/cw2_open_battle.lua`. The native frontend mod loader runs it as
  Lua initializes, before the UI exists. It then listens for `UICreated`,
  `FrontendScreenTransition`, and a 500 ms `RealTimeTrigger`, detecting the current
  screen by visible component IDs rather than by a single named menu state.
- **G3 (superseded):** its generated opener listens only to
  `FrontendScreenTransition` and branches on `context:string()` values `main_menu` and
  `historical_battles`.
- The battle-side `probe.lua` is separate from both: it loads only after the replacement
  Xingyang battle XML starts.
- The current G1 route is covered by a Lua harness, but the repository's latest live
  note still records an opener failure after reaching Historical Battles. Treat the
  complete auto-open route as unverified until another live run passes.

Evidence: [`frontend_open.lua`](../dev/spikes/g1_3k_io/frontend_open.lua),
[`test_opener.py`](../dev/spikes/g1_3k_io/test_opener.py), and the superseded
[`g3_frontend/probe.py`](../dev/spikes/g3_frontend/probe.py).

## Dynasty Mode — separate mapping required

Dynasty Mode shares the low-level battle engine, but not CW2's implemented historical-
battle pipeline. It has its own frontend lobby (`ui/frontend ui/dynasty_mode.twui.xml`),
`CcoDynastyModeLobby` callbacks, map selection, result/loading surfaces, database tables,
and three scenario families under `script/battle/dynasty_battle/` (`dynasty_arid`,
`dynasty_subtropical`, and `dynasty_temperate`). Its first alliance is replaced from the
lobby selection at runtime.

CW2 currently overrides only the Records Xingyang historical battle and assumes that
scenario's two-alliance slot mapping. Dynasty Mode should remain out of scope until it
has a dedicated roster-injection, start, result, and replay/capture probe.
