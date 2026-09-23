# Native 3K evidence — 2026-09-23

Inspected installed build 20435474. Source paths below are **inside game packs**.
Full extracted CA files remain local temporary/build outputs.

## Correction to the handoff

The earlier search sampled `fast.pack`, `data_ep.pack`, `data_bl.pack`, and
`database.pack`. The missing implementations are in **`data.pack`**. Absence
from the sampled packs was not absence from the game.

| Native source | Observed evidence |
| --- | --- |
| `data.pack:script/battle/default_battle/battle_start.lua` | Loads script libraries and creates `battle_manager:new(empire_battle:new())`. |
| `data.pack:script/_lib/lib_mod_loader.lua` | Battle branch loads `/script/_lib/mod/` and `/script/battle/mod/`; `ModLog` uses `io.open`. |
| `data.pack:script/_lib/lib_battle_manager.lua:1067` | `register_results_callbacks` registers `Battle Results`; `process_results` reads `get_bool1()`. True is player victory; false logs player loss. No draw enum here. |
| `data.pack:script/_lib/lib_battle_script_unit.lua:1056` | Native code calls `number_of_men_alive()` and `initial_number_of_men()`. |
| `data.pack:script/_lib/lib_generated_battle.lua:226` | Native code calls unit `name()` to get an army script name. Our six names are unique, unlike some vanilla grouped names. |
| `data.pack:script/_lib/lib_generated_battle.lua:1494` | Native victory helper itself uses routing heuristics and warns when it cannot determine a winner. Do not adopt this as authoritative outcome. |
| `data.pack:script/battle/historical_battle/historical_battle_xinyang/battle.xml` | Two alliances, native unit types, retinue IDs, general metadata, placement, battle-script link, map and victory conditions. |
| `data.pack:script/battle/historical_battle/historical_battle_red_cliff/battle.xml` | Records Liu Bei general definition. |
| `database.pack:db/battles_tables/data__` | `3k_main_historical_battle_xinyang` has a specification pointing to that XML. `release`, `multiplayer`, `singleplayer` are false in this row; actual historical-menu availability still requires observation. |
| `data.pack:ui/frontend ui/historical_battles.twui.xml` | Dedicated historical-battle page, start-battle button and Romance checkbox. |

Xingyang XML SHA-256:
`77a3643b93a964dc83115296144e7e9b333035446ff7065f5fa5c51f1459dc55`.

## Implementation decision

Test a separate mod pack overriding the existing Records XML and its scenario
script. Keep the native map and initial deployment coordinates. Clone the
general metadata from locally installed XML; replace line units with the
candidate militia and remove reinforcements. The application generates the
pack and a unique run ID; the script records per-unit initial/alive counts and
the result callback. Runtime behaviour remains unverified.

The bundled RPFM 3.99.109 `set-file-type` command panics in clap argument
decoding. `pack create` already creates PFH5 type-3 mod packs. The builder
checks that header, adds two files, and verifies their internal paths with
`pack list`. It never invokes the broken command.

## Verification ledger

- Result reader: rejects foreign runs, roster substitution/duplication, invalid
  counts, missing result, and repeated battle attempts.
- Lua 5.1 harness: verifies JSON encoding, phase callbacks, six unit rows,
  initial vs final counts, and true/false/null result values with mock objects.
- Native build: two XML sources parse; pack construction and listing pass.
- Clean extraction from installed `data.pack`: build passes without the earlier
  temporary extraction. Re-extracting the generated pack reproduces both files
  byte-for-byte; XML contains exactly two three-unit armies, unique names and
  no reinforcements.
- Five automated tests passed, including a Lua 5.1 mock harness and removal
  refusing a changed pack while preserving unrelated files. (Superseded: twelve
  tests pass after the result-hook fix; install `lupa` for the Lua harness.)
- Packaged Windows EXE: hidden startup smoke test exits 0 and verifies the
  bundled Lua resource. UI interaction and in-game operation are not covered.
- Real 3K battle / winner / count comparison: **pending**.
- G1 remains open; no points burned.

## First operator screenshots (updated build 25370317)

The operator reached Battle → New → Historical Battle → Battle of Xingyang.
This confirms the historical frontend is reachable. The next battlefield
screenshot shows 12 player units, three generals and 723 soldiers, not the
probe's three-unit player roster. No probe JSONL was found. The installed pack
must therefore not be counted as a successful roster injection.

The preceding menu screenshot had a marked Romance checkbox. The battlefield
count is consistent with nine 80-man units plus three single-entity heroes,
so Romance selection is the leading explanation, not yet a confirmed cause.
Both native versions have 12 player units; the probe currently overrides only
the Records XML path. Next test: return to Xingyang, ensure the Romance box is
empty, then inspect the deployed roster before fighting.

## Records deployment succeeded

On build 25370317 the next screenshot shows three player units and 181 soldiers.
The live probe produced `start` and `deployed` JSONL events for run
`9ce5f8c1f80046d392113783e6b9160b`. All six unique script names, native unit
types and alliance assignments match the staged manifest. Each side has a
21-man general bodyguard, 80 Ji Militia and 80 Archer Militia. A validated
initial snapshot is preserved in `records_start_observed.json`.

This demonstrates that the external Records roster override and initial
soldier-count logging work on the updated build. Final outcome and survivor
capture are still pending; G1 remains open.

## Completed live fight: survivors verified, winner callback missing

The operator's result screen reports attacker Cao Cao's Close Victory, with
143 survivors versus Liu Bei's 106. The same run's `complete` event contains
attacker counts 7/56/80 and defender counts 9/47/50, matching both totals.
See `records_completed_observed.json`. Starting strength was 181 per side,
so observed losses are 38 and 75 soldiers respectively.

No `result` event was emitted: `player_won` remains null in all captured
events. The strict reader correctly rejects this incomplete outcome rather
than substituting the screenshot or routing heuristics. This is a verified
staged battle with attributable survivor export, but not yet verified
machine-readable winner export. Investigate the native result-command callback
and/or another authoritative winner query before G1 completion or CK3 apply.

## Result hook investigation and fix (build 25370317, 2026-09-23)

The battle libraries were re-extracted from the updated `data.pack`; the earlier
line references were from build 20435474. Findings:

- `script/_lib/lib_battle_manager.lua:1063-1076` (updated build):
  `register_results_callbacks` registers a `Battle Results` command handler;
  `process_results` reads `get_bool1()` (true = player victory). The doc comment
  states these old-style handlers "won't get called until the battle results
  screen is shown". No such command arrived during the completed live fight and
  no `CW2_G1_ERROR` was logged, so our callback registered but the engine never
  sent the command in that session.
- `script/_lib/lib_battle_manager.lua:535`: the manager constructor registers
  `VictoryCountdown` phase → `self.battle_is_won = true`. That phase fired in
  the live run, so the flag is an engine-set outcome signal, unlike the routing
  heuristics in `lib_generated_battle` that remain forbidden as authority.
- `script/battle/historical_battle/historical_battle_xinyang/battle_script.lua`
  is a 13-line loader for `battle_script_behaviour` (via the `_romance`
  package path); the native behaviour script registers no results callbacks,
  so nothing native was broken by our replacement.
- The updated build's `historical_battle_xinyang/battle.xml` is byte-identical
  to build 20435474 (same SHA-256 in both run manifests).

Probe changes (3K-side only): `probe.lua` now emits exactly one `result` event,
preferring the engine `Battle Results` callback; if none arrived 5s after the
`Complete` phase it falls back to `bm.battle_is_won` and labels the event
`result_source: victory_countdown_fallback`. A late engine result is preserved
as a separate `engine_result` event, never a second result. Every event carries
the battle identifier, and `probe.py` rejects events whose battle differs from
the staged run, unknown result sources, and late engine results that
contradict the recorded outcome. The old installed pack from run
`9ce5f8c1f80046d392113783e6b9160b` predates this fix and must not be replayed;
remove it and prepare a fresh run.
