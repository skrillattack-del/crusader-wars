# CW2 Frontend Design — V1 stub (rev 1.1)

Status: proposal, owner Matuxy. Lives in `docs/design/` beside `cw2_launcher_mockup.html`.
Scope is the burndown's V1 goal only: **one CK3 encounter → one playable 3K battle with vanilla units → a result save CK3 can load.**

The mockup **is** the V1 frontend with a fake backend (`MockBridge`). Replace the bridge, keep the screens.

## Changes in rev 1.1 (from the agent's code read)

| Area | rev 1.0 said | rev 1.1 says | Why |
|---|---|---|---|
| Army size | 18 slots per side | up to **3 generals + 18 units = 21 cards**; generals = ceil(units ÷ 6) | Generals are unit cards in 3K |
| Who generals are | commander only | commander, then highest-prowess knights, topped up with generic captains | CK3 already exports knights with prowess |
| Prowess tilt | commander's prowess for the whole army | **each general's prowess tilts their own retinue** | Uses data we have; makes knights matter |
| Battle result | `winner: 0\|1` | `player_side`, `player_outcome: victory\|non_victory`, `source` | `observed_result.json` has no side-indexed winner. V1 doesn't need one: write-back uses losses only |
| Write-back | patch the user's save after a backup | **never touch the user's save**; install a new `_AFTER` save into the CK3 save folder | `apply.py` already works this way; adopt it as an invariant |
| CK3 running | blocks write-back | **warning only** | Writing a new file is safe; the risk is continuing the old session, which the copy addresses |
| Preview | new dry-run in the patcher | **split `mutate_gamestate` into plan + apply** | It is already pure text-in/text-out |
| Step 5 name | Write back | **Install save** | Matches what actually happens |

---

## 1. Stack decision

| Choice | Pick | Why |
|---|---|---|
| Launcher shell | **pywebview** (WebView2 on Windows) | Backend is Python. No server, no ports. One PyInstaller exe. |
| Probe app | stays **Tkinter/ttk** | It works; don't churn it. |
| Bridge Lab (`frontend/`) | stays a separate read-only dev viewer | Different audience. Merge later only if the evidence drawer grows into it. |
| Launcher UI, V1 | the mockup's vanilla HTML/JS, bridge swapped | Zero build step. |
| Launcher UI, later | Svelte 5 once screens > 5 | Not before V1. |
| Backend ↔ UI | `js_api=Bridge()`; events via `window.evaluate_js("window.cw2.emit(...)")` | Promises one way, events the other. |
| Fonts | bundle Young Serif, Atkinson Hyperlegible, Noto Serif SC (subset 左右合) in `app/ui/fonts/` | Must run offline. |

## 2. Repo layout

```
dev/
  app/
    main.py          # window + Bridge wiring
    bridge.py        # js_api class (section 5)
    roll.py          # army sizing + prowess tilt (section 6), pure, unit tested
    ui/index.html    # mockup screens minus MockBridge; G1-scope copy (see dev/app/README.md)
    ui/fonts/
  tools/rpfm/rpfm_cli.exe      # git-ignored (already in place)
  dist/runs/<timestamp>/       # git-ignored; probe + apply outputs
docs/design/
  FRONTEND_DESIGN.md
  cw2_launcher_mockup.html
.githooks/pre-commit           # 5 MB guard
```

Tool paths resolve: env var (`CW2_RPFM_CLI`) → `config.toml` → `dev/tools/rpfm/rpfm_cli.exe`.

Built status (G1 scope): `dev/app` + `dev/build_launcher.ps1` produce
`dev/dist/CW2-Launcher.exe` (pywebview 6, WebView2). The bridge wires the
verified probe pipeline; encounter extraction, the roster roll and write-back
report honest not-integrated errors, so the encounter/roster/write-back screens
temporarily show the staged probe battle instead of CK3 data. Fonts are not
bundled yet: the app runs offline on the CSS fallback stacks. The canonical
mockup is `docs/design/cw2_launcher_mockup.html`; the root copy went stale
after the generals revision and should be refreshed or removed.

## 3. Screens (a strict sequence, so the rail is numbered)

| # | Screen | Shows | Primary action |
|---|---|---|---|
| 1 | Check setup | CK3 exe, 3K exe, CK3 save folder, RPFM CLI; whether CK3 is running (info only) | Load encounter from save |
| 2 | Review encounter | per side: commander, knights with prowess, men, levies, MAA, and the 3K army (generals + units = cards); force-ratio bar | Roll armies |
| 3 | Roll armies | seed + Roll again; per general: role, prowess, units led, tier-chance bar, unit table; install progress | Prepare and install → Continue to battle |
| 4 | Fight in 3K | launch; then the player's outcome with its source; per-side 3K losses, loss share, CK3 losses | Launch Three Kingdoms → Read battle result → Review changes |
| 5 | Install save | field-level before/after; input save name + hash (unchanged); new save name | Install save to CK3 |

Action names stay identical from button to log to message: *Roll armies / rolled*, *Prepare and install / installed*, *Install save to CK3 / installed*.

## 4. State machine

```
SETUP ─paths ok─▶ ENCOUNTER ─roll─▶ ROSTER ─install ok─▶ PACK_INSTALLED ─launch─▶ IN_BATTLE
                                     ▲ │ reroll (seed)                                  │ result read
                                     └─┘                                                ▼
SETUP ◀─new battle─ SEALED ◀─install save ok─ REVIEW_CHANGES ◀──────────────────────────┘
                                    │ fails → stay, reason shown, nothing written
```

The rail only goes back to reached steps. Reroll locks after the pack is installed. Going back never repeats side effects.

## 5. Bridge contract

```python
class Bridge:
    def get_health(self) -> dict: ...          # {"ck3_running": bool, "paths": [PathCheck]}
    def set_path(self, key: str) -> dict: ...  # native dialog → updated PathCheck
    def get_encounter(self) -> dict: ...       # Encounter
    def roll_roster(self, encounter: dict, seed: int) -> dict: ...   # Roster via roll.py
    def prepare_and_install(self, roster: dict) -> dict: ...         # emits "install"; {"pack","sha256"}
    def launch_3k(self) -> dict: ...           # {"pid"}
    def read_result(self) -> dict: ...         # BattleResult, from observed_result.json
    def preview_changes(self) -> dict: ...     # ChangePlan = plan_mutations(...), writes nothing
    def install_save(self) -> dict: ...        # apply → run folder → copy to CK3 saves; raises "exists"
```

```ts
type PathCheck = { key: "ck3_exe"|"tk_exe"|"ck3_saves"|"rpfm_cli"; label: string; value: string; ok: boolean };
type Person    = { name: string; prowess: number };
type Side      = { role: "Attacker"|"Defender"; name: string; commander: Person; knights: Person[];
                   men: number; levies: number; maa: number };
type Encounter = { id: string; save: string; date: string; location: string; terrain: string; sides: [Side, Side] };
type General   = Person & { role: "Commander"|"Knight"|"Captain"; retinue: number;
                   probs: [number, number, number, number];
                   units: { tier: 0|1|2|3; name: string; key?: string; count: number }[] };
type RolledSide = { cards: number; retinue: number; generals: General[] };
type Roster    = { seed: number; sides: [RolledSide, RolledSide] };
type BattleResult = {
  player_side: 0|1;
  player_outcome: "victory" | "non_victory";
  source: "engine_callback" | "routing_state" | "victory_countdown_fallback";
  sides: { tk_men: number; tk_lost: number; ck3_men: number; ck3_lost: number }[];  // from per-unit survivors
};
type ChangePlan = { input_save: string; input_sha256: string; output_save: string;
                    changes: { path: string; before: number; after: number }[] };
```

### The one backend refactor: plan / apply split

`mutate_gamestate()` is already pure. Split it so the preview and the install share one code path:

```python
@dataclass(frozen=True)
class Change:
    path: str       # "armies › 1043 › regiments › 0 › current"
    span: tuple[int, int]   # byte offsets of the value in the input text
    before: int
    after: int

def plan_mutations(text: str, result: dict) -> list[Change]: ...
def apply_mutations(text: str, changes: list[Change]) -> str: ...   # splice spans back to front

def mutate_gamestate(text: str, result: dict) -> str:               # existing tests keep passing
    return apply_mutations(text, plan_mutations(text, result))
```

Test: for every G2 fixture, `mutate_gamestate` output is byte-identical before and after the refactor.

### Feeding real results into the plan

`preflight.plan` currently writes `synthetic_result.json` with fixed losses (38 and 75). The bridge instead builds the result from `observed_result.json`: per side, `loss_share = 1 − Σ survivors ÷ Σ starting men`, then `ck3_lost = round(ck3_men × loss_share)`, split across regiments by size. Synthetic stays as a test fixture only.

### Result source (hand to Cline, don't edit mid-change)

`probe.lua` emits `victory_countdown_fallback`; `probe.py read` accepts only `engine_callback` and `routing_state`, so a real fallback result is rejected. Proposal: accept all three, carry `source` through to `observed_result.json`, and let the UI label the fallback as lower confidence.

## 6. Army and roll math (reference; the mockup JS mirrors it)

```python
import math, random

PRIOR = (0.40, 0.30, 0.20, 0.10)   # Levy, Line, Veteran, Elite
BETA = 0.6                          # tilt strength
MAX_RETINUE, PER_GENERAL, MAX_GENERALS = 18, 6, 3   # verify with a staged full army
CAPTAIN_PROWESS = 5

def army_for(men_a: int, men_b: int) -> list[dict]:
    big = max(men_a, men_b)
    out = []
    for m in (men_a, men_b):
        retinue = max(1, round(MAX_RETINUE * m / big))
        generals = min(MAX_GENERALS, math.ceil(retinue / PER_GENERAL))
        out.append({"retinue": retinue, "generals": generals, "cards": retinue + generals})
    return out

def generals_of(commander: dict, knights: list[dict], g: int) -> list[dict]:
    ranked = sorted(knights, key=lambda k: k["prowess"], reverse=True)
    picks = [commander, *ranked][:g]
    return picks + [{"name": "Captain", "prowess": CAPTAIN_PROWESS}] * (g - len(picks))

def tier_probs(prowess: int) -> list[float]:
    p = min(max(prowess / 20, 0.0), 2.0)
    w = [pi * math.exp(BETA * p * k) for k, pi in enumerate(PRIOR)]
    s = sum(w)
    return [x / s for x in w]

def roll_side(side: dict, army: dict, pool: list[list[str]], rng: random.Random) -> list[dict]:
    left, out = army["retinue"], []
    for g in generals_of(side["commander"], side["knights"], army["generals"]):
        n = min(PER_GENERAL, left); left -= n
        probs = tier_probs(g["prowess"])
        units = []
        for _ in range(n):
            k = rng.choices(range(4), probs)[0]
            units.append((k, rng.choice(pool[k])))
        out.append({**g, "retinue": n, "probs": probs, "units": units})
    return out
```

Worked check (mockup data): 8,400 vs 5,100 men → 3 generals + 18 units = 21 cards vs 2 generals + 11 units = 13 cards. Ivar (22) leads 6 with a 30% elite chance; Osberht (12) out-prowesses his own commander Ælla (9), so his 5 units roll better than hers. Loss shares 27.6% and 75.8% → 2,315 and 3,865 CK3 losses.

Unit names in the mockup are placeholders; the real pool is vanilla `land_units_tables` keys (via RPFM) bucketed by a hand-written `tiers.toml`. The Python RNG is authoritative; the UI only displays what the bridge returns.

## 7. Invariants

1. **The user's save is never modified.** Input is read-only; output is a new file.
2. **Never overwrite any save.** If the output name exists in the CK3 save folder, `install_save` raises `exists` and writes nothing.
3. **Preview and install share one plan.** `install_save` applies exactly the `ChangePlan` the user saw (store it on the bridge; don't re-plan).
4. **Hashes in the log.** Input save SHA-256, pack SHA-256, output save SHA-256.
5. **Seeds are logged.** Seed + encounter id reproduce any roster.
6. **Installed pack = displayed roster.** Reroll locks after install.
7. **CK3 running is a warning, not a gate.** Show it on screens 1 and 5; tell the player to load the new save from the main menu.

## 8. Visual tokens

Concept: the two-half **tiger tally** (虎符). Left half CK3, right half 3K; they close one notch per finished step, and a cinnabar 合 seal stamps them when the result save is installed. The only animation in the app.

| Token | Hex | Use |
|---|---|---|
| patina-950 | `#112021` | header, drawer |
| patina-900 | `#16292a` | page |
| patina-800 | `#1c3432` | panels |
| verdigris | `#72b8a3` | ok, done, after-values, Line tier |
| bronze | `#b8924f` | tally, current step, Veteran tier |
| bronze-hi | `#dcbb7a` | Elite tier |
| cinnabar | `#c8372d` | primary action, seal, error notices |
| bone | `#e8dfcb` | text |

Type: Young Serif for headings, Atkinson Hyperlegible for everything else, Noto Serif SC for the three tally glyphs. Tabular figures in number columns. Keyboard reachable, visible focus, reduced motion respected, works at 860 px and below.

## 9. Acceptance, mapped to the burndown

| Burndown item | Frontend done when |
|---|---|
| G1 (3K in/out) | Screen 3 uses the real pack writer + RPFM verify; screen 4 reads a real `observed_result.json`, including a fallback-sourced one |
| G2 (CK3 write-back) | Screen 5 shows `plan_mutations` output; install goes through `apply_mutations`; G2 fixtures byte-identical after the split |
| Extractor | Screen 2 renders a real `Encounter` with knights |
| Manifest | Pack, input and output hashes plus seed in the evidence log |
| Roster roll | `roll.py` tests: `army_for` caps at 21 cards, `tier_probs` sums to 1, captains fill missing knights, seed reproducibility |
| Round-trip | Real save → battle → install; CK3 loads the `_AFTER` save with the expected regiment sizes |
| Runbook | Screenshot of each screen in the runbook |

## 10. Still open

1. Staged full army: does 3K accept 3 generals × 6 units from the pack, and does `MAX_RETINUE` hold?
2. Does the extractor path see knights? (Upstream Crusader Wars read knights and their prowess from `console_history.txt`; check what CW2's extractor uses.)
3. Output save naming: `CW2_<encounter id>_AFTER.ck3` proposed. Does CK3 list it without a restart?
4. License: upstream `farayC/Crusader-Wars` has a `LICENCE` file at repo root; pull it into `docs/third_party/` before reusing any upstream code or mapper XML.
