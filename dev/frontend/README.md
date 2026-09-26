# Crusader Wars II frontend study

Open [index.html](index.html) in a modern browser, or serve this directory with a static HTTP server. No build or package installation is needed. Images, fonts and Lucide 0.468.0 are bundled locally.

This is a standalone implementation of the supplied Hastings concept, not the launcher UI and not an injected Three Kingdoms menu. The existing `dev/app` launcher is unchanged. The artwork is temporary historical reference imagery, not the exact concept illustration; Bodiam Castle is scenery, not a reconstruction of Hastings in 1066.

## Interactions

- Shuffle cycles through six fixture rosters, preserving each army's unscaled total.
- Lock freezes the current roster and scale. Unlock permits changes again.
- Fight requires a locked roster and displays an explicit preview confirmation. It does not install packs, launch games or write CK3 saves.
- Back offers a reset to roll 03. Escape dismisses dialogs.
- Options persist in browser local storage under `cw2.frontend.options`. Presentation and scale affect the preview. Domain, reporting, screenshot and strict-mapping preferences are stored only; no engine behavior is implemented here.
- Army scale is limited to 0.1-10 for this preview. Each unit count is rounded before totals are summed.
- Unimplemented native menu entries are disabled. `cut_3d_voice` is not exposed.

## Verification

Syntax: `node --check dev/frontend/app.js` from the repository root.

Browser checks: shuffle changes the roster and wraps after six rolls; lock disables shuffle and scale; Fight cannot launch a game; saved options survive reload; desktop/mobile layouts do not overflow horizontally; local artwork and fonts load. Browser integration is independent of the existing launcher's smoke test.

## Asset sources

| Local asset | Source / author | License |
| --- | --- | --- |
| `assets/william.jpg` | [Bayeux Tapestry, William detail](https://commons.wikimedia.org/wiki/File:William_the_Conqueror_(TFA).jpg), reproduction by Myrabella | Public domain |
| `assets/harold.jpg` | [Bayeux Tapestry, Harold detail](https://commons.wikimedia.org/wiki/File:Bayeux_tapestry_stitches_detail..jpg) | Public domain |
| `assets/map.jpg` | [Hereford Mappa Mundi](https://commons.wikimedia.org/wiki/File:Hereford-Karte.jpg), unknown medieval author | Public domain |
| `assets/battlefield.jpg` | [Bodiam Castle](https://commons.wikimedia.org/wiki/File:Bodiam-castle-10My8-1197.jpg), Antony McCallum | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); original file unchanged, CSS cropping and toning |
| `assets/paper.jpg` | [Natural Paper](https://www.transparenttextures.com/natural-paper.html), Mihaela Hinayon, via Transparent Textures / Subtle Patterns; PNG content | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| `assets/lucide.min.js` | [Lucide 0.468.0](https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js) | [Bundled license](assets/LUCIDE-LICENSE.txt) |
| Cinzel | [Google Fonts](https://github.com/google/fonts/tree/main/ofl/cinzel) | [SIL OFL](assets/CINZEL-LICENSE.txt) |
| Crimson Text | [Google Fonts](https://github.com/google/fonts/tree/main/ofl/crimsontext) | [SIL OFL](assets/CRIMSON-LICENSE.txt) |