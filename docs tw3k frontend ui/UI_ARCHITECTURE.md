# CW2 Launcher — UI & Config Architecture

> **Ledger of record:** `docs tw3k frontend ui/schemas/config.schema.json`  
> **Runtime ledger:** `config/cw2_config.json` (created from schema defaults on first run)  
> Refer to `Canon: Crusader Wars 2 — UI_Mapping Architecture.pdf` for the original UI-mapping canvas.

---

## 1 · Component map

```
dev/app/ui/
├── index.html      Main shell: header (brand + tally SVG + ⚙ gear), step rail, <main>, drawer, settings overlay
└── app.js          All view logic, actions, settings panel IIFE
dev/app/
├── bridge.py       pywebview js_api — every call() target lives here
└── config.py       Options ledger: load / validate / save / checksum / check_slots
docs tw3k frontend ui/
├── schemas/
│   └── config.schema.json   THE ONE LEDGER (JSON Schema 2020-12 subset)
└── UI_ARCHITECTURE.md       This file
```

---

## 2 · Config flow

```
config.schema.json  ──[load]──►  config.py:effective()  ──►  Bridge.config (dict)
                                        │                           │
                              with_defaults() seeds                 │
                              cw2_config.json on first run          │
                                                                    ▼
                                                         bridge.get_config()  ◄──── JS: call('get_config')
                                                         bridge.save_config(patch)  ◄── JS: call('save_config', pending)
                                                                    │
                                                         config.save(base, patch)
                                                         ├─ validate(schema, merged)
                                                         └─ atomic write  cw2_config.json
```

**Key invariant:** `additionalProperties: false` in the schema means **any key not declared in `properties` is rejected at validation time** — in Python by `config.validate()`, which is called on every `load()` and `save()`. Unknown keys never reach the bridge's `self.config` dict.

---

## 3 · Options ledger (schema summary)

| Key | Type | Default | Allowed values / constraints | Notes |
|-----|------|---------|------------------------------|-------|
| `show_mode` | string | `"dramatic"` | `"dramatic"` · `"tactical"` · `"minimal"` | Controls frontend battle-opener navigation |
| `army_scale_factor` | number | `1.0` | `> 0` (`exclusiveMinimum: 0`) | Multiplier on top of CK3→3K base scaling |
| `auto_battle_report` | boolean | `true` | — | Writes summary to run folder on result read |
| `enable_tw3k_screenshots` | boolean | `false` | — | Screenshot seam (no capture backend yet) |
| `domain_focus` | string | `"wei"` | `"wei"` · `"shu"` · `"wu"` · `"custom"` | Dynasty lens for unit colouring |
| `injectivity_strict` | boolean | `true` | — | Raise on first bijection violation in `slots.registry.json` |
| ~~`cut_3d_voice`~~ | — | **UNDEFINED** | — | **Formally UNDEFINED (turn-2 §4).** Not in `properties`; rejected by `additionalProperties: false`. Must never be added. |

---

## 4 · Settings panel (UI layer)

The ⚙ gear button in the launcher header opens a step-independent modal overlay.

### Lifecycle

1. `A.openSettings()` → `call('get_config')` → populate `baseline`
2. User edits fields → changes accumulate in `pending` (only diffed keys)
3. **Save** → `call('save_config', pending)` → bridge merges into ledger → writes `cw2_config.json` atomically
4. **Cancel / Escape / backdrop click** → discard `pending`, close overlay

### Field controls by schema type

| Schema type | Control | ID pattern |
|-------------|---------|------------|
| `enum` | Segmented buttons (`.seg-sm-btn`) | `data-field` + `data-val` |
| `boolean` | Toggle chip (`<input type="checkbox">`) | `cfg-{key}` |
| `number` | Numeric spinner (`<input type="number">`) | `cfg-{key}` |

### Bridge surface (js_api)

| Method | Signature | Returns |
|--------|-----------|---------|
| `get_config` | `()` | `{ok, config, path, sha256, slots_ok}` |
| `save_config` | `(patch: object)` | `{ok, config, path, sha256}` or `{error}` |

Both are already implemented in `bridge.py` (lines 208–228) and exposed through `get_health`'s `config` sub-block for at-a-glance validity display on the Setup screen.

---

## 5 · Slot injectivity rail

`config.check_slots(base, strict)` checks `config/slots.registry.json` (if present) for the CK3 character ↔ CW2 slot bijection. Violations surface in `Bridge._config_block()` → `get_health().config.slots_violations`. `injectivity_strict: true` (the default) causes `_load_config()` to raise on first violation.

---

## 6 · Screenshot seam

`config.maybe_request_screenshots(run_dir, enabled)` is the seam for `enable_tw3k_screenshots`. When `true` it writes `screenshots_requested.flag` to the run folder. No capture backend exists yet; the flag is a future hook. The config plumbing is already in place.

---

## 7 · Design tokens (CSS)

| Token | Value | Usage |
|-------|-------|-------|
| `--patina-950` | `#112021` | Page bg, overlay tint |
| `--patina-900` | `#16292a` | Body bg, modal bg |
| `--patina-800` | `#1c3432` | Panel, input bg |
| `--bronze` | `#b8924f` | Active state mid |
| `--bronze-hi` | `#dcbb7a` | Active text, focus ring |
| `--verdigris` | `#72b8a3` | Done/success dots |
| `--cinnabar` | `#c8372d` | Error/bad, CTA |
| `--bone` | `#e8dfcb` | Primary text |
| `--bone-dim` | `#aca693` | Secondary text |
| `--accent-dim` | `rgba(184,146,79,.18)` | Settings active-button bg |

---

*Last updated: 2026-09-26 — settings panel, bridge wiring, schema audit.*
