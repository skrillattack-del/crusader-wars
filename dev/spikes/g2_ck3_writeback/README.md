# G2: isolated CK3 write-back experiment

Status: **active; intake/preflight implemented, save mutation and reload proof pending**.

**AFTER-save audit:** another implementation generated an AFTER archive, but
comparison proves it changed only combat records and skipped the backing army
tables. Its `applied` journal status is not engine verification. The apply entry
point is disabled pending correction; see [review](evidence/AFTER_SAVE_REVIEW.md).
Do not load that artifact as the planned G2 validation candidate.
Keep the legacy Crusader Wars mod unchanged. Prefer a save/restart approach;
create a companion mod only if the engine mechanics require it. Do not build
the full extractor or connect Three Kingdoms results yet.

## Operator input

An existing save has now been selected under the user's authorization:
`CW2_G2_BEFORE.ck3` in OneDrive Documents' CK3 save-games folder. Its verified
copy and bound plan are in `results/run-002`; see the [evidence ledger](evidence/README.md).
No new save needs to be created to continue inspection. For the eventual live
check, load only the disposable copy and pause immediately. Preserve the
original King Matuxia save. A patched `AFTER` save is not available yet.

Create a disposable, non-Ironman campaign with an active battle. Pause it and
make a manual save named `CW2_G2_BEFORE.ck3`. Provide its path. The intake tool
copies it to a new experiment directory and hashes both source and copy.
Never use a real campaign as the write-back target. A plaintext/debug save may
be necessary if the supplied save is binary/tokenized; those files fail closed.

From the workspace root:

```powershell
python dev/spikes/g2_ck3_writeback/patcher/preflight.py intake --save "FULL_PATH_TO_CW2_G2_BEFORE.ck3" --out dev/spikes/g2_ck3_writeback/results/run-001
python dev/spikes/g2_ck3_writeback/patcher/preflight.py plan --run dev/spikes/g2_ck3_writeback/results/run-001 --combat-id ACTUAL_COMBAT_ID
```

Inspect `inventory.json` to select the actual operator battle; never simply
choose the first combat in a campaign. `plan` re-reads the snapshot, checks its
fingerprint and binds an explicitly synthetic result to real side/army IDs.
Losses are fixed test values 38 and 75, not scaled 3K losses. The plan refuses
insufficient observed fighting strength and cannot overwrite an existing plan.
It does **not** write a patched save, resolve a battle or claim apply idempotency.

## Remaining implementation and acceptance

1. Inspect the selected battle's combat, army, army-regiment and backing
   regiment records. Determine which counts are authoritative and which are
   caches. Legacy samples contain fractional fighting men and soft casualties.
2. Implement a narrowly scoped patch into a **new** `CW2_G2_AFTER.ck3`, preserving
   the original and unrelated records. Do not merely delete the combat block
   or change `combat_results`: defeat, pursuit, war score and army state need
   coherent engine behaviour.
3. Before publishing a patched save, reserve a semantic encounter/result key
   in a durable journal. Interrupted pending entries block retry until reconciled.
   Reject a different fingerprint, duplicate result and conflicting result for
   the same encounter. Prepared plans are not committed applications.
4. Reload in CK3, inspect losses and battle resolution, advance time and save
   again. Compare the reloaded state with expected counts; account for any
   ordinary reinforcement separately. Commit only after this engine proof.
5. Reapply the same result and a renamed equivalent; both must fail closed.

G2 completes only after this real reload/time-advance and duplicate-rejection
test. A parser test or generated patch alone is insufficient.
