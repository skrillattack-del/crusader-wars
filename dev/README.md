# Crusader Wars → Three Kingdoms

Target: a double-click Windows application that exports a CK3 encounter, stages
a vanilla Three Kingdoms battle, and safely returns its result to CK3.

**Current build is a G1 experiment, not the finished port.**

For a source-only status view, open the offline [Bridge Lab](frontend/index.html).
It inspects local G1 runtime logs and prepared G2 plans without installing
mods or editing saves. No build step is required for this frontend stub.

Double-click [CW2-G1-Probe.exe](dist/CW2-G1-Probe.exe). It prepares a separate
3K mod pack from two XML files in your installed game, installs that pack,
opens 3K on request, validates captured results, and removes its own pack.
Python is bundled; the local RPFM CLI is still required for pack operations.
The [G2 spike](spikes/g2_ck3_writeback/README.md) now provides CK3 save intake
and synthetic-result preflight. Actual write-back remains unimplemented.

Follow the [G1 runbook](spikes/g1_3k_io/RUNBOOK.md). The first real in-game run
has verified roster staging and survivor capture; winner export remains open.
[Native evidence](spikes/g1_3k_io/evidence/native_findings.md)
establishes a concrete historical-battle XML/script route to test.

Development: [codebase map](CODEBASE_MAP.md), [burndown](BURNDOWN.md).
Build with `powershell -ExecutionPolicy Bypass -File dev/build_probe.ps1`
from the repository root (Python 3.12 and PyInstaller 6.22.3 used locally).
Test with `python -m unittest discover -s dev/spikes/g1_3k_io -p "test_*.py" -v`.
The optional Lua 5.1 harness requires `lupa` (2.8 used locally).

Generated packs, extracted native files and executables are local build outputs.
Rebuild from a user's installed 3K files; do not package CA's source assets as
part of the port's source tree. This implementation does not copy CW1 C# code.
