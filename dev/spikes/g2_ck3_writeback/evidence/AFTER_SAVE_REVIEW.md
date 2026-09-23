# AFTER save audit: rejected for the planned G2 test

The externally authored `apply.py` and `run-002/CW2_G2_AFTER.ck3` were reviewed
against the preserved BEFORE archive. See [machine-readable comparison](after_save_audit.json).

## Verified artifact findings

- Only combat `2717908992` changed. The entire root `armies` manager is
  unchanged, including both army-regiment caches and backing regiments.
- Attacker fighting total decreased by 38; defender fighting total by 75.
  Both `total_levy_men` fields stayed unchanged despite levy entry edits.
- Combat phase remains `main`. The patcher does not consume the synthetic
  `outcome` or implement battle resolution. Normal simulation continuing is
  not evidence of applying the requested external victory.
- Existing `journal.json` says `applied`. This records file generation only;
  no CK3 reload/time-advance validation supports that status.

## Code defects to address

1. Resolve `armies.army_regiments` and `armies.regiments`, not root-level tables.
   Missing records must raise, not silently skip.
2. Validate the actual snapshot SHA-256 and re-derive side/army/regiment links
   before edits. Validate loss bounds, types and conservation across layers.
3. The current rounding gives the last regiment the residual then clamps it;
   this can lose casualty conservation. Do not apply a whole regiment's loss
   to each backing record or only the first chunk. Respect chunk attribution.
4. Adding every casualty to `soft_casualties` is an unverified semantic choice;
   inspect/experiment before equating that with permanent soldier removal.
5. Reserve an encounter key durably before publishing output, reject pending
   conflicts, publish atomically without overwrite and retain archive metadata.
   Separate generated/pending from engine-verified committed state.
6. Prove the requested outcome resolves the encounter once, independently of
   ordinary CK3 simulation. Winner-by-natural-simulation is insufficient.

The public `apply()` entry point is temporarily fail-closed with this audit
reason. Its implementation and generated artifact remain intact for diagnosis.
Neither the BEFORE save nor existing journal has been rewritten. Do not reset
the journal to manufacture a successful retry; use a fresh audited attempt.
