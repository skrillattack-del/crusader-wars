# dev

- `app/`: the launcher (`python app/main.py`, tests: `python -m unittest discover -s app`, UI: `node app/ui/index.smoke.cjs`). `app/config.py` loads the options ledger (`config/cw2_config.json`, validated against `schemas/config.schema.json`), checksums it and runs the `config/slots.registry.json` injectivity rail.
- `battle_math/`: shared-scale staging, seeded unit rolls, casualty rates back to CK3.
- `spikes/g1_3k_io`: builds the `crusader_wars_2` battle pack from a rolled roster (`probe.py`, battle script `probe.lua`, frontend opener `frontend_open.lua`), installs it and reads results.
- `spikes/g2_ck3_writeback`: CK3 save reader and patcher.
- `spikes/e1_extractor`, `spikes/g3_frontend`: encounter extractor; earlier full-army and auto-open experiments (superseded by `g1_3k_io`).
- `build_launcher.ps1`: builds `dist/CW2-Launcher.exe`.

Run each folder's tests from inside it (two spikes both have a `test_probe.py`).
