# dev

- `app/`: the launcher (`python app/main.py`, tests: `python -m unittest discover -s app`, UI: `node app/ui/index.smoke.cjs`).
- `battle_math/`: shared-scale staging, seeded unit rolls, casualty rates back to CK3.
- `spikes/g1_3k_io`: builds and installs the `crusader_wars_2` battle pack and reads results.
- `spikes/g2_ck3_writeback`: CK3 save reader and patcher.
- `spikes/e1_extractor`, `spikes/g3_frontend`: encounter extractor; full armies and auto-open.
- `build_launcher.ps1`: builds `dist/CW2-Launcher.exe`.

Run each folder's tests from inside it (two spikes both have a `test_probe.py`).
