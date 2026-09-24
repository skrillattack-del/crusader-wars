# G1: Three Kingdoms battle I/O

Status: **complete under the user's revised staging/survivor scope**.
The real Records battle loaded both generated armies and exported survivor
totals matching the result screen. Authoritative winner export (G1-H1) and a
changed-unit repeat remain mandatory for I1. This is a scope revision, not a
claim that the original full-outcome criterion passed. See BURNDOWN.md.

## Current experiment

The continuation found the missing battle libraries and native historical
roster XML in **`data.pack`**. See the [evidence correction](evidence/native_findings.md)
and [live runbook](RUNBOOK.md). A [double-click probe](../../dist/CW2-G1-Probe.exe)
now builds a separate Records-mode historical battle override and reads
correlated soldier-count logs. It has not yet been verified in a real battle.
The older custom-battle candidate and findings below are retained as history.

## Local evidence (2026-09-23)

- The Steam manifest for app `779340` lists `Total War THREE KINGDOMS`, build
  `20435474`, installed under `C:\Program Files (x86)\Steam\steamapps\common\Total War THREE KINGDOMS`.
- The root Steam shortcut launches `steam://rungameid/779340`; it is not a
  battle configuration or result channel.
- `Three_Kingdoms.exe` and the game's `data/` directory exist at that path.
- Installed `database.pack` contains `db/units_custom_battle_permissions_tables`
  and `db/custom_battle_unit_sets_to_units_tables`: these enumerate native unit
  IDs and eligibility, not a complete two-sided battle definition. Its
  `db/custom_battle_settings_tables` contains settings keys; the base pack's
  `db/battle_set_piece_armies_units_tables` entry has no data rows.
- The same pack includes `battle_set_piece_armies_tables`, its army/unit
  junction tables, and `battle_set_pieces_tables`. They describe fields for
  armies, factions, units and battle scripts, but all five related tables in
  this pack have **zero data rows**. They suggest a possible set-piece path;
  they do not demonstrate how to launch one in 3K.
- Installed `fast.pack` includes frontend Lua and logging helpers; the sampled
  entry scripts did not reveal a custom-battle launcher or survivor export. Its
  `script/_lib/lib_header.lua` names `lib_generated_battle` and
  `lib_battle_manager`, but those references alone do not prove a usable hook.
- At the first inspection no 3K staging/result interface was found. This is
  superseded by the native XML/Lua findings above; runtime proof remains open.

## Four questions to close

| Question | Discriminating proof | State |
| --- | --- | --- |
| 1. Legal battle army representation? | Capture a *3K-native* two-side battle with known vanilla unit IDs, general requirements and army limits; record exact file/table/script and version. | Native historical XML found; generated roster awaits runtime validation. |
| 2. Can we alter it externally? | Change one unit in a disposable copy using documented tools, launch and observe the replacement. | Mod pack generated; in-game effect pending. |
| 3. Can we enter that battle automatically? | From an external command or modded game entry, start **those exact two rosters** without rebuilding them manually in the 3K UI. | Unknown |
| 4. Can we read the result? | Through the *same path*, extract winner, starting and surviving **soldier** counts per unit (not HP); note routed/destroyed units and general state, or document which fields cannot be obtained. | Unknown |

## Reproducible candidate, not a battle file

[candidate_matchup.json](candidate_matchup.json) pins the same two sides for
every experiment. The native permissions table lists Ji Militia and Archer
Militia for both factions; it also lists the indicated Cao Cao and Liu Bei
general-unit keys with `general_unit=true`. General/unit compatibility, mode
(Records or Romance), retinue layout and army limits still require an in-game
check. The JSON is **our test vector**, not a Three Kingdoms input format.

1. First, in an unmodified 3K custom battle, try these sides and units by hand.
  Record mode, what the UI actually permits, the exact starting soldier counts
  for each unit, and whether a completed fight writes any new file in the game
  folder or the ThreeKingdoms user profile. This tests the candidates, **not G1**.
2. Inspect the *native* set-piece and frontend/mod-loading path in a disposable
  mod pack; prove that changing a candidate unit alters the battle the game
  loads **without** reselecting units in the UI. Never edit CA's packs in place.
3. Fight through that very same path, then compare files/logs before and after.
  Require a machine-readable winner and unit starting/surviving **soldier**
  counts that correlate with the original side and roster. A screenshot or
  auto-resolve estimate is insufficient.
4. Record exact pack/script/table, commands, game mode/build, log path, and
  observed output. Mark G1 done only if both steps 2 and 3 work.

Keep experiments and fixtures here, but leave the installed game and original
saves untouched. A one-off custom battle clicked together in the UI does not
prove external roster injection; a results screen alone does not prove
machine-readable extraction. If either side fails, record the evidence and
revisit the architecture before building CK3 mappings.
