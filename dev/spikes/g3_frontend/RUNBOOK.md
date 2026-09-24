# G1 live experiment

## What is ready

[CW2-G1-Probe.exe](../../dist/CW2-G1-Probe.exe) builds an experimental mod pack
that replaces the Records version of Xingyang (`historical_battle_xinyang`).
It keeps native map and placement metadata, replaces the armies with Cao Cao
and Liu Bei, each with one Ji Militia and one Archer Militia, and replaces the
scenario script with our logger. Six unique script names identify the units.
It removes the original reinforcements and scenario behaviour.

The original candidate JSON used a Liu Bei hero. This experiment instead uses
the Records `3k_main_general_earth_liu_bei` definition found in the native Red
Cliff XML. The generated `run.json` records this change. General equipment and
appearance are copied from local native XML; no Attila units are used.

## Operator steps

Local handoff: the installed probe (run `9ce5f8c1f80046d392113783e6b9160b`)
predates the result-hook fix and its log already contains a completed fight
without a result event. Do not replay it. Close 3K, Remove probe, then begin a
fresh run at step 1 so the rebuilt executable stages the result-emitting
script.

1. Close Three Kingdoms. Open the executable and check the game/RPFM paths.
2. Click **Prepare and install**. Keep the generated run folder. Enable
   `cw2_g1_probe` in 3K's mod manager. Use a single-player test without other
   battle-overriding mods.
3. Open 3K. Select **Historical Battles → Xingyang**, internal name `xinyang`.
   Select Records / uncheck Romance. Menu wording and reachability must be
   verified on the installed build; if this entry is missing, report that.
4. At deployment verify **three unit cards per side**: Cao Cao vs Liu Bei,
   Ji Militia, Archer Militia. Menu artwork still describes the vanilla battle;
   inspect the actual loaded battlefield roster. Do not manually rebuild it.
5. Record mode, unit-size setting and each card's initial soldier count. Fight
   to the results screen; record winner and final soldier counts. Do not infer
   survival from health bars. Ideally win this first test as Cao Cao.
6. Click **Read result**. It requires one initial snapshot, one result callback,
   matching run ID, all six unique names/types/sides, and valid soldier counts.
   Compare `observed_result.json` with the game results. Keep the original
   `<run_id>.jsonl` too. An exception is evidence, not a completed gate.
7. Close 3K, then **Remove probe**. Only a pack matching this run's recorded
   SHA-256 is removed. CA's packs and CK3 saves are never edited.

Each attempt needs a new Prepare operation after removal. Replaying an old
probe produces multiple starts/results and is deliberately rejected.

## Failure evidence and limitations

- No JSONL: the script has not proved it loaded. Inspect `lua_mod_log.txt` in
  the game folder for `CW2_G1_ERROR`. Retain the pack and run manifest.
- No result event (all three runs on 2026-09-23): the engine `Battle Results`
  command never fired. The 5s `victory_countdown_fallback` also never fired,
  because battle timers stop at `Complete`, and it was unsound anyway:
  `battle_is_won` is set when either side's countdown begins. The probe now
  decides at `Complete` with no timer, from unit state: the side whose every
  unit is routing or dead lost (`result_source: routing_state`). If neither or
  both sides meet that, `player_won` is null and the reader rejects the run. The
  engine callback, when it fires first, is recorded as `engine_callback`; a late
  one becomes a cross-checked `engine_result` event. Replaying this rule on the
  three archived logs gives player victory each time, matching the result screen.
- Vanilla roster: likely wrong mode, inactive pack or override conflict.
- Native DB `release`/`singleplayer` flags for this battle are false, but the
  game also ships a dedicated historical UI. These flags alone do not establish
  menu availability. Test before adding database overrides.
- Start only: soldier access worked, but the results callback did not finish.
- The engine callback reports player victory as a boolean. False is preserved
  as `non_victory`, with no guessed winner. Draw/defeat/abandonment handling
  remains open; do not apply this observation to CK3.
- The Lua harness uses mocks. Pack round-trip and EXE startup checks are local
  tooling tests, not proof of a playable injected battle.
- This experiment does not auto-click the historical menu, map CK3 armies,
  resolve CK3 battles, or provide the complete V1 application.

G1 closes only after externally staged rosters and real attributable outcome
and surviving-soldier counts work through this same path. A second run changing
one unit is required to demonstrate that external edits affect the loaded army.
