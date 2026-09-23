# Crusader Wars 2 experiments

This repository tracks the source, tests, and evidence for a proposed bridge
between Crusader Kings III and vanilla Total War: THREE KINGDOMS. It does not
contain the installed games, the old Crusader Wars application, CK3 saves, or
extracted game assets. Those stay on the local machine and are ignored by git.

The current G1 proof covers a generated Three Kingdoms Records battle and
attributed survivor counts. Its result callback did not export the winner.
G2 has an isolated CK3 preflight plan, but no externally resolved battle or
engine-verified save write-back. Do not use an experimental AFTER save as a
replacement for a campaign save.

## Local interface

Open [Bridge Lab](dev/frontend/index.html) in a browser. It reads a G1 JSONL
log or a prepared G2 JSON plan selected through the browser; it cannot change
game files. No build step or server is needed. See the [frontend notes](dev/frontend/README.md)
for the file formats and focused tests.

For the mod-pack probe, see [the G1 runbook](dev/spikes/g1_3k_io/RUNBOOK.md).
The probe still uses RPFM from the locally installed Crusader Wars v1.4.2
folder. The [codebase map](dev/CODEBASE_MAP.md), [burndown](dev/BURNDOWN.md),
and [G2 notes](dev/spikes/g2_ck3_writeback/README.md) track the gates.