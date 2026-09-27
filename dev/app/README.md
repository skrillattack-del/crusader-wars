# Launcher

pywebview window (`main.py`) around `bridge.py`; the UI is `ui/index.html`
(its script is `ui/app.js`, inlined). Steps: start in CK3, pick the battle,
roll armies, fight in 3K, read the result, return to CK3. The title-bar gear
opens the Options panel, which edits `config/cw2_config.json` through the bridge.

- Run: `python dev/app/main.py` (from source; `pip install -r dev/requirements.txt` first)
- Tests: `python -m unittest discover -s dev/app -p "test_*.py"`; UI: `node dev/app/ui/index.smoke.cjs`
- Self-check without a window: `python dev/app/main.py --smoke-test`

Two looks, switched by the header plaques: **Crusader Kings III** (dark,
parchment, red brush) and **Three Kingdoms** (teal, gold frames, dragons).
The choice is kept in `cw2-launcher-session.json` (`get_skin`/`set_skin`), not
the options ledger. Artwork in `ui/skins/` is cropped from the concept mockups
in `docs launcher gui/`, whose origin and licence are unconfirmed, so replace it
before any public release. `ui/skins/ck3/paper.jpg` is Natural Paper by Mihaela
Hinayon (Transparent Textures, CC BY-SA 3.0); Cinzel and Crimson Text are
SIL OFL (licences alongside).

Runs (`runs/`), playset backups (`backups/`) and `cw2-launcher-session.json`
are written in this folder and are git-ignored. The battle pack stages the
rolled armies on the Records Xingyang map; in 3K the CRUSADER WARS II lobby
shows both armies and FIGHT opens that battle (steps logged in the run's
`frontend.log`). Writing results
into CK3 saves is off; each result stays in its run folder as
`observed_result.json`. After the result, **Return to CK3** (`close_3k`,
then `return_to_ck3`) closes Three Kingdoms (graceful `taskkill`, then `/F`)
and relaunches CK3 through Steam; its Continue button resumes the campaign
named in CK3's `continue_game.json` (CK3 has no launch flag that loads a
save, so that click is the player's).
