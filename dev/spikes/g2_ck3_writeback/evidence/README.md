# Evidence ledger

Read-only legacy sample inspection found active `combats` records with side
army IDs, men-at-arms/levy entries, fractional `current` and `soft_casualties`,
and separate `army_regiments.cached.current`, `regiments`, and `combat_results`.
This supports inspecting multiple linked records; it does not establish which
mutations CK3 will preserve or how to resolve an active battle.

## Selected existing save (user authorized existing-save use)

Disposable copy:
`C:\Users\Matux\OneDrive\Documents\Paradox Interactive\Crusader Kings III\save games\CW2_G2_BEFORE.ck3`

Verified byte-identical to `King_Matuxia_of_Badajoz_908_08_27.ck3` and the
isolated intake snapshot `../results/run-002/before.ck3`. SHA-256:
`dd278de2fb3522cb5833c4d1c3c532e54c26d1c56b5625f9b7f783cde8c93128`.

The archive contains text gamestate and `ironman=no`; save metadata identifies
version 1.19.0.6. This is an existing snapshot, not a newly created paused
manual save. Pause state and compatibility with the current playset remain
runtime checks.

Combat `2717908992` is in phase `main`:

| Side | Army ID | Initial men | Current fighting men | Synthetic loss |
| --- | --- | ---: | ---: | ---: |
| Attacker | 570426519 | 571 | 340.09632 | 38 |
| Defender | 503317436 | 528 | 421.48395 | 75 |

`run-002/linked_records.json` traces both armies to 15 army-regiment records
and their backing regiment records. `synthetic_result.json` binds the plan to
the snapshot and combat; its attacker victory is deliberately synthetic.

Three preflight tests pass: nested-scope parsing, unchanged archive copy with
duplicate-plan/wrong-combat/tamper rejection, and unsupported binary rejection.
These do not prove apply idempotency. No save mutation or battle resolution
is implemented yet. Original campaign hashes remain unchanged.

The earlier `run-001` is retained as a failed inspection attempt: the parser
mistook the outer `combats` manager and inner table for duplicate sections.
The corrected parser explicitly follows manager/table nesting.
