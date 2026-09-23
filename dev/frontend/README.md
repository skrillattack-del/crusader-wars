# Bridge Lab

Open [index.html](index.html) directly in a browser. It is a static, offline
read-only interface; no build, localhost server, or login is required.

- **3K evidence** accepts the G1 probe's JSONL runtime log. It checks run ID,
  unit identities, soldier bounds, and replay events. A `complete` snapshot
  provides survivor counts; a winner is shown only when a valid `result`
  callback exists. The overview's archived figures are historical, not live.
- **CK3 plan** accepts only an unapplied, save-bound G2
  `synthetic_result.json` from preflight. The declared fingerprint and result
  ID are displayed, not cryptographically verified against a save. It never
  accepts `.ck3` archives or treats a synthetic outcome as a verified victory.

Selected files are parsed in browser memory. No game files are installed or
modified. For source-only validation from the repository root:

```sh
node --test dev/frontend/evidence.test.cjs
```

The test suite includes the archived G1 six-unit run and negative cases for
invalid or replayed evidence. Native game scripts and personal CK3 saves are
not part of this repository.