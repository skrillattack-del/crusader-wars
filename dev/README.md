# dev

- `app/`: the launcher (`python app/main.py`, tests: `python -m unittest discover -s app`, UI: `node app/ui/index.smoke.cjs`). `app/config.py` loads the options ledger (`config/cw2_config.json`, validated against `schemas/config.schema.json`), checksums it and runs the `config/slots.registry.json` injectivity rail.
- `battle_math/`: shared-scale staging, seeded unit rolls, casualty rates back to CK3.
- `spikes/g1_3k_io`: builds the `crusader_wars_2` battle pack from a rolled roster (`probe.py`, battle script `probe.lua`, in-game lobby `frontend_lobby.lua` with its layout and art in `lobby/`), installs it and reads results. `lobby/make_art.ps1` repaints the lobby art.
- `spikes/g2_ck3_writeback`: CK3 save reader and patcher.
- `spikes/e1_extractor`, `spikes/g3_frontend`: encounter extractor; earlier full-army and auto-open experiments (superseded by `g1_3k_io`).
- `requirements.txt`: pywebview for the launcher window; lupa for the Lua test harnesses.

Run each folder's tests from inside it (two spikes both have a `test_probe.py`).
