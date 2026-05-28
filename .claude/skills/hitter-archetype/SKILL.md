---
name: hitter-archetype
description: Profile any hitter by 20-80 scouting ratings on Contact/Power/Discipline (plus SB overlay) with archetype label, career-arc trajectory, multi-year archetype shifts, and historical comp matching with T+1/T+2 outcomes. Three modes — profile (single hitter deep dive), scan (league-wide trajectory shifts), comps (find historical comps for a profile). Built on 3,485 batter-years 2015-2026 with calibrated archetype stickiness (retention rates) and decline base rates. Use whenever the user asks "what kind of hitter is X", "is X breaking out / declining", "who does X compare to historically", or wants to evaluate whether a hitter's archetype change is real vs noise.
---

# hitter-archetype — multi-mode hitter profiling skill

Profile hitters across three orthogonal scouting dimensions (Contact, Power, Discipline) with a Speed/SB overlay, assign archetype labels from a 27-cell matrix, and trace career trajectories with historical comp matching.

**Trigger phrases:** "what kind of hitter is X", "profile X", "rate X on 20-80", "is X breaking out", "is X declining", "who does X compare to", "find comps for X", "archetype trajectory for X", "scan for breakout hitters", "scan for declining hitters".

---

## OUTPUT REQUIREMENT — always show C/P/D/SB ratings

**Every output of this skill must surface the raw 20-80 ratings (C=, P=, D=, SB=) for every hitter mentioned**, regardless of mode (profile / scan / comps) and regardless of archetype label. The archetype is a categorical summary; the underlying numbers are the actual information. Two hitters with the same `PURE_HITTER` label can have C=60/P=55/D=50 vs C=78/P=56/D=46 — the ratings are decision-grade, the label is at-a-glance shorthand.

Standard format: `Player Name (C=66 P=59 D=48 SB=55)` inline, or as dedicated columns in tables. Never report an archetype label without the underlying ratings alongside.

This is especially load-bearing for boundary cases: a hitter labeled `CONTACT_POWER` with P=60 (EDGE) is a fundamentally different bet than one with P=68 (SOLID), and only the numbers tell you that.

SB is rated for every hitter but is NOT part of the archetype label — it is an orthogonal overlay (HI_SB / MOD_SB / NON_RUNNER) reported alongside the C/P/D archetype. SB is also excluded from the comp-distance metric in Mode 3 (explicit design decision — comps are matched on the archetype-driving dimensions only, SB is presented as context).

---

## Empirical Foundation

### The 20-80 scouting scale
Standard scout rating — `50 = league average`, `10 points = 1 SD`, capped `[20, 80]`.
Within-year scaled (so 80 in 2023 = 80 in 2019, normalized to that year's pool).

### Three orthogonal domains + SB overlay
Each batter-year rated on:

| Domain | Components averaged | Direction |
|---|---|---|
| **CONTACT** | contact_pct + K%_inv + BABIP + xwOBA-on-contact | higher = better (K% inverted so K-avoidance folds in) |
| **POWER** | Barrel% + HardHit% + ISO + HR-rate + Pull-FB% | higher = more thump |
| **DISCIPLINE** | BB% + Chase%_inv + Z-Swing% | higher = better plate skill |
| **SB (overlay)** | SB-rate + Sprint speed | speed/running, NOT in archetype label |

**CONTACT sub-decomposition** identifies *which* component drives the rating:
- `PURE_CONTACT` — contact_pct is highest component (bat-on-ball artist)
- `BAT_TO_BALL_KING` — K%_inv is highest (elite K-avoidance)
- `CONTACT_QUALITY` — xCON is highest (drives damage on contact)
- `BALANCED` — all components within 8 points

**POWER sub-decomposition:**
- `ELITE_RAW` — Barrel + HardHit are top components (raw thump)
- `BARREL_KING` — Barrel% is highest (optimal launch consistency)
- `PURE_HR` — HRrate is highest (over-the-fence specialist)
- `PULL_LIFT` — PullFB% drives the rating (mechanical/swing-path power)
- `GAP_POWER` — high ISO with low HR-rate (doubles-driven, not HR-driven)
- `BALANCED`

**DISCIPLINE sub-decomposition:**
- `PURE_PATIENCE` — BB% is highest (walk machine)
- `SELECTIVE_AGGRESSIVE` — low Chase + high ZSwing (attack in zone, lay off out of zone)
- `PASSIVE_WALKS` — high BB but low ZSwing (walks-via-taking)
- `BALANCED`

**SB overlay tiers** (qualifier on athletic profile — NOT a 4th archetype domain):
- `HI_SB`       — SB rating ≥ 60 (top 16% within year)
- `MOD_SB`      — SB rating 45-59
- `NON_RUNNER`  — SB rating < 45

SB has partial r ≈ +0.04 vs FP/PA after C+P+D control — too small for its own domain but meaningful as athletic-sub-classifier. Same CONTACT_POWER rating with HI_SB vs NON_RUNNER points to different fantasy profiles:
- **HI_SB + CONTACT_POWER** = "5-tool" profile: Witt 24, Acuña 23 peak, Trout 15, Ramírez peak
- **NON_RUNNER + CONTACT_POWER** = "thump-only" profile: Alvarez 19, Olson, Soto post-speed

These profiles have similar FP/PA ceilings but different floor/category profiles for H2H purposes.

**Spray archetype** (2021+ coverage only — from batted-ball direction):
- `PULL_HEAVY`     — pull rate ≥ 45% (lift-and-pull approach)
- `OPPO_LEAN`      — oppo rate ≥ 30% (uses whole field, contact-leaning)
- `BALANCED_SPRAY` — neither

Within PURE_HITTER and CONTACT_POWER, the spray archetype differentiates outcomes — PULL_HEAVY tends to higher HR rate but more shift-vulnerability; OPPO_LEAN tends to higher BABIP durability through aging.

### Archetype matrix (27 cells)
Each archetype-driving domain bucketed `PLUS` (≥60) / `AVG` (40-59) / `MINUS` (<40) on C/P/D → 27 possible archetypes. Loaded from `data/research/hitter_archetype_definitions.json`. Sorted by historical mean FP/PA:

| Cell (C/P/D) | Archetype | Description |
|---|---|---|
| PLUS/PLUS/PLUS | GOAT_TIER | Trout-tier: all three domains elite |
| PLUS/PLUS/AVG | CONTACT_POWER | Contact + thump, average eye (Witt, Yelich 18) |
| PLUS/PLUS/MINUS | AGGRESSIVE_STAR | Hits everything hard, swings at everything |
| PLUS/AVG/PLUS | CONTACT_EYE | High AVG + walks, modest power (Betts, Arraez+) |
| PLUS/AVG/AVG | PURE_HITTER | Contact-led star, league-avg pop (Ramírez peak, Arraez) |
| PLUS/AVG/MINUS | CONTACT_HACKER | Hits for AVG, hacks at everything |
| PLUS/MINUS/PLUS | SLAP_AND_WALK | Bat-to-ball + walks, no thump |
| PLUS/MINUS/AVG | SLAP_HITTER | Pure slap-and-dash |
| PLUS/MINUS/MINUS | AGGRESSIVE_SLAP | Slap with no patience |
| AVG/PLUS/PLUS | POWER_EYE | Power + walks, average bat-to-ball |
| AVG/PLUS/AVG | POWER_HITTER | League-avg contact with elite power (Olson, Soto post-decl) |
| AVG/PLUS/MINUS | ALL_OR_NOTHING | Power-or-K bat |
| AVG/AVG/PLUS | BALANCED_EYE | Average across the board with patience |
| AVG/AVG/AVG | AVERAGE_HITTER | Generic regular |
| AVG/AVG/MINUS | AVG_HACKER | Average bat, no patience |
| AVG/MINUS/PLUS | SECONDARY_LEADOFF | OBP-only, no thump |
| AVG/MINUS/AVG | GENERIC_NO_POWER | Light-hitting regular |
| AVG/MINUS/MINUS | NO_POWER_HACKER | Empty-bag everyday player |
| MINUS/PLUS/PLUS | THREE_TRUE_OUTCOMES | TTO archetype (Schwarber, Gallo) |
| MINUS/PLUS/AVG | POWER_K | Power w/ K problems |
| MINUS/PLUS/MINUS | POWER_HACKER | Pure dinger threat, swings out of shoes |
| MINUS/AVG/PLUS | PATIENT_K | Walks a ton, K's a ton |
| MINUS/AVG/AVG | BACKUP_BAT | Replacement-level bench bat |
| MINUS/AVG/MINUS | K_PRONE_FILLER | High-K, no other tool |
| MINUS/MINUS/PLUS | WALK_ONLY_FRINGE | Walks are the only tool |
| MINUS/MINUS/AVG | FRINGE | Marginal MLB bat |
| MINUS/MINUS/MINUS | BUST | All three domains MINUS |

Mean FP/PA declines roughly monotonically from GOAT_TIER → BUST — the matrix is internally consistent.

### Boundary risk — how durable is the archetype label?

The 27-cell matrix uses hard thresholds: `PLUS ≥ 60`, `AVG = 40-59`, `MINUS < 40`. A hitter with `POWER = 61` is technically PLUS-power but one bad season flips them to AVG. A hitter with `POWER = 70` is well inside PLUS — the label is durable.

For each batter-year, compute:
- `bd_C`, `bd_P`, `bd_D` — distance from each rating to its nearest threshold (40 or 60)
- `boundary_distance` — min across all three (the dimension closest to flipping)
- `boundary_tier`:
  - `EDGE` (boundary_distance ≤ 2) — one bad rating point would flip the archetype label
  - `NEAR_EDGE` (3-5) — close but not adjacent; meaningful skill change required to flip
  - `SOLID` (6+) — well inside the cell; label is genuinely durable

**Validated 2026-05-28** (loaded from `hitter_boundary_validation.json`):
- EDGE retention: **28.5%** (n=1023) — label flips easily
- NEAR_EDGE retention: **43.4%** (n=647)
- SOLID retention: **56.1%** (n=189) — label nearly 2× more sticky than EDGE

Same direction and magnitude as the SP boundary validation — ~2× spread between EDGE and SOLID confirms labels in the SOLID interior are genuinely durable. Don't over-anchor to a fragile EDGE label.

### Age tier

Hitters peak earlier than pitchers. Each batter-year tagged with `age_tier`:
- `PRE_PEAK`  — age ≤ 25 (pre-peak development phase)
- `PEAK`      — age 26-30 (typical peak production window)
- `POST_PEAK` — age ≥ 31 (post-peak / decline phase)

Age tier conditions BOTH stickiness AND comp matching. Default comp matching uses age-matched within ±3 years; if pool < 8 cands, fall back to all-age.

### Archetype stickiness (year-over-year retention)

Loaded from `data/research/hitter_archetype_stickiness.json`. 22 of 27 archetypes have enough YoY transitions (n≥8) for stickiness data; rarer cells fall back to overall base rate.

**General pattern** — labels stabilize with streak length: 1st-year-in-arch retention is lowest, multi-year sustained archetypes are stickier. Always check streak length.

### Decline base rates (use as context, not alert)

Loaded from `data/research/hitter_decline_baselines.json`:
- Overall T+1 decline rate (FP/PA drop ≥ 0.05 OR archetype tier drop): **33.6%**
- **Elite tier (FP/PA ≥ 0.657, top decile): 55.8% T+1 decline** — more than half regress

Slightly less brutal than SP elite decline (59%) but similar story. **Methodology note** — same as SP: elite T+1 decline is a base rate, not an actionable alert; pre-decline process drops correlate with mean reversion not amplified decline. Do not use prior-year skill drops as a "decline imminent" signal.

---

## Data sources

All built by `scripts/xfp/build_hitter_archetypes.py` (runs in `refresh_dashboards.py` step 2.7):

```
data/research/hitter_ratings_master.csv               — 3,485 batter-years 2015-2026 (excl 2020) with full 20-80 ratings
data/research/hitter_archetype_career_panel.parquet   — same + T+1/T+2 outcomes (source for Mode 3)
data/research/hitter_archetype_definitions.json       — 27 cell labels with descriptions
data/research/hitter_archetype_stickiness.json        — retention rates per archetype + per-age-tier
data/research/hitter_decline_baselines.json           — base rates for context framing
data/research/hitter_boundary_validation.json         — EDGE/NEAR_EDGE/SOLID retention rates
```

Panel size: **3,485 batter-years, 974 unique batters, 2015-2026 (excludes 2020 COVID)**.
PA floor: **250 PA for full season, 80 PA for in-progress current year.**

---

## Modes

### Mode 1 — Profile a single hitter: `/hitter-archetype <name>`

Example: `/hitter-archetype Bobby Witt Jr.`

```python
import pandas as pd, json
from pathlib import Path
REPO = Path(r'c:\Users\Joshua\plv_clone')

master = pd.read_csv(REPO / 'data/research/hitter_ratings_master.csv')
careers = pd.read_parquet(REPO / 'data/research/hitter_archetype_career_panel.parquet')
stick = json.load(open(REPO / 'data/research/hitter_archetype_stickiness.json'))

# Find hitter across all years
name_pattern = 'Witt'
rows = master[master['player_name'].str.contains(name_pattern, case=False, na=False)]
```

**Output sections** (in this order):
1. **Current rating snapshot** — Lead with `C=X P=Y D=Z SB=W` on the first line. Follow with the component breakdown (Contact/K_inv/BABIP/xCON, Barrel/HardHit/ISO/HRrate/PullFB, BB/Chase_inv/ZSwing, SBrate/Sprint). Include age + age tier.
2. **Full label** — e.g., `CONTACT_POWER / PURE_CONTACT / ELITE_RAW / SELECTIVE_AGGRESSIVE / HI_SB / PULL_HEAVY / PRE_PEAK / NEAR_EDGE` (archetype + C-subtype + P-subtype + D-subtype + SB-tier + spray + age-tier + boundary-tier). Always pair with `(C=X P=Y D=Z SB=W)` on the same line so the label is never disconnected from the numbers.
3. **Boundary risk** — `boundary_distance` value + tier + which domain is closest to flipping. E.g., "boundary distance = 1 → EDGE; POWER=61 is 1 point from flipping the PLUS-power label"
4. **Age-conditioned stickiness** — retention% for this archetype AT THIS AGE TIER (not just overall), pulled from `hitter_archetype_stickiness.json` per-age block if available.
5. **Career arc** — year-by-year archetype trail with FP/PA AND age AND boundary tier. **Format each line with C/P/D/SB explicit:** `2024 (age 24) CONTACT_POWER [C=75 P=63 D=51 SB=69] NEAR_EDGE, FP/PA=0.842`
6. **Verdict** — 1-2 sentences synthesizing what kind of hitter they are and what the data says about durability, weighted by both age tier and boundary tier (SOLID labels deserve more weight than EDGE labels). Reference specific C/P/D values when arguing the verdict.

### Mode 2 — League-wide trajectory scan: `/hitter-archetype scan`

Surface 2025→2026 archetype shifts (upward and downward) with roster status:

```python
careers = pd.read_parquet(REPO / 'data/research/hitter_archetype_career_panel.parquet')
arch_q = master.groupby('archetype')['fp_per_pa'].mean()

# 2025 → 2026 transitions with archetype quality delta
current_year = 2026
careers['arch_q'] = careers['archetype'].map(arch_q)
careers['prev_arch'] = careers.groupby('batter')['archetype'].shift(1)
careers['prev_arch_q'] = careers.groupby('batter')['arch_q'].shift(1)
careers['dQ'] = careers['arch_q'] - careers['prev_arch_q']

shifts = careers[(careers['year']==current_year) & careers['prev_arch'].notna() &
                 (careers['archetype'] != careers['prev_arch'])]
upward = shifts[shifts['dQ'] > 0.05].sort_values('dQ', ascending=False)
downward = shifts[shifts['dQ'] < -0.05].sort_values('dQ')
```

Then enrich with roster status from `app.espn_connector` (see `/roster-verify` pattern).

**Output sections:**
1. **Upward shifts on YOUR roster** (holds — validating real breakouts)
2. **Upward shifts available as FA** (actionable adds)
3. **Upward shifts rostered elsewhere** (trade targets)
4. **Decline on YOUR roster** (sell-high / drop candidates)
5. **Decline as FA** (avoid these adds despite ownership %)

**Table format requirement:** every row must include columns for `C`, `P`, `D`, `SB` (current year ratings) and `dC`, `dP`, `dD` (deltas vs prior year on the archetype-driving dimensions). Boundary tier as a separate column. The archetype label is shorthand — readers need the underlying numbers to evaluate whether a shift is real (large dC/dP/dD) or boundary wobble (small deltas crossing a threshold).

Standard row layout:
```
Player | Status | Baseline arch | 2026 arch | C | P | D | SB | dC | dP | dD | bd_tier | dFP/PA
```

Sample-size caveat: 2026 ratings based on partial PA. Flag hitters with `pa < 80` as "sample-thin" and note that the deltas could compress with more PA.

### Mode 3 — Find historical comps for a hitter: `/hitter-archetype comps <name>`

Given any hitter, find the K=5-8 closest historical batter-seasons (Euclidean distance in **C/P/D space only — SB is excluded by design**, age-matched ±3 years by default) and report their T+1 / T+2 outcomes. This is the most directly actionable mode.

```python
from scipy.spatial.distance import cdist

careers = pd.read_parquet(REPO / 'data/research/hitter_archetype_career_panel.parquet')

def find_comps(query_C, query_P, query_D, query_age=None, exclude_batter=None, k=8,
               exclude_inprogress=True, current_year=2026, age_window=3):
    """Default: age-matched comps within +/- 3 years on C/P/D space only.
    SB is intentionally excluded from the distance metric (overlay, not archetype-driving).
    Falls back to all-age if pool < k."""
    cands = careers.copy()
    if exclude_inprogress:
        cands = cands[cands['year'] != current_year]
    if exclude_batter is not None:
        cands = cands[cands['batter'] != exclude_batter]
    # Also exclude future seasons (no leakage)
    if query_age is not None and 'year' in cands.columns:
        pass  # year-level filter applied via current_year above
    cands = cands[cands['next_fp_per_pa'].notna()]

    # Try age-matched first
    if query_age is not None and 'age' in cands.columns:
        age_matched = cands[(cands['age'] >= query_age - age_window) &
                            (cands['age'] <= query_age + age_window)]
        if len(age_matched) >= k:
            cands = age_matched

    qv = np.array([[query_C, query_P, query_D]])
    Xc = cands[['CONTACT','POWER','DISCIPLINE']].values  # SB intentionally excluded
    dists = cdist(Xc, qv, metric='euclidean').flatten()
    cands = cands.assign(distance=dists).sort_values('distance').head(k)
    return cands
```

**Output:**
1. **Query profile** on its own line — `Query: Player Name (C=75 P=63 D=51 SB=69), age 24, archetype CONTACT_POWER [NEAR_EDGE]`. Always lead with the C/P/D/SB of the query before listing comps. Note SB on the query line for context but it does NOT drive comp selection.
2. **Top 5-8 comps** with year, name, **C/P/D/SB of the comp**, FP/PA in comp year, distance (C/P/D only), T+1 FP/PA, T+1 archetype, T+2 FP/PA. Standard column layout:
   ```
   Year | Player | Age | C | P | D | SB | FP/PA | dist | T+1 FP/PA | T+1 arch
   ```
3. **Aggregate T+1 stats** — mean T+1 FP/PA, % broke out (T+1 FP/PA gain ≥ 0.05), % declined (drop ≥ 0.05), % sustained
4. **Quality flag** — if mean comp distance > 5.0, note "wide distance — query profile is unusual, comp set may not be highly representative"

---

## Step-by-Step Execution

### Step 0: Verify data freshness
Check that `data/research/hitter_ratings_master.csv` was rebuilt today. If stale (>24h), suggest running `refresh_dashboards.py` or `build_hitter_archetypes.py` directly.

### Step 1: Disambiguate hitter (for Mode 1 / Mode 3)
- Use `str.contains(case=False)` against `player_name` column
- If multiple matches, list and disambiguate by team / current year
- **Same-name MLB players** (canonical: Max Muncy LAD 3B vs ATH C) — use `plv_clone.utils.name_match.resolve_batter_id(name, team=..., position=...)` per `/player-id-resolve`. Required before any dict-keyed batter lookup.

### Step 2: Pull all years for that hitter
- Show every season with PA ≥ 250 (prior years) or PA ≥ 80 (2026 in-progress)
- Most recent year is the focus; prior years for trajectory context

### Step 3: For Mode 3, ALWAYS exclude the query batter's own seasons AND all years ≥ query year
Self-matching gives degenerate results; future-year inclusion causes leakage.

### Step 4: Format output with markdown tables, year-sorted

---

## Anti-patterns to avoid

0. **Reporting an archetype label without the C/P/D/SB ratings alongside.** The label is shorthand; the numbers are the actual information. Two hitters labeled CONTACT_POWER with C=60 vs C=78 are fundamentally different bets. ALWAYS pair labels with raw ratings in every output, every mode.

1. **Treating 1st-year-in-archetype as durable** — stickiness data says single-year labels have lower retention. Flag streak length.
2. **Using prior-year process drops as "decline early warning"** — counter to intuition, hitters with skill drops at year T regress LESS in T+1 (already mean-reverted). The decline baseline for elite hitters is 55.8% regardless of process indicators; frame as base-rate context, not actionable alert.
3. **Comparing across years without within-year normalization** — z-scores are computed within each year's qualified pool. "POWER=65 in 2019" and "POWER=65 in 2023" are equivalent within-year percentiles, NOT equivalent raw ISO.
4. **Acting on 2026 in-progress ratings with <80 PA** — sample-thin. Note caveat in output.
5. **Trusting GOAT_TIER / CONTACT_POWER / POWER_EYE labels for forward projection at EDGE boundary** — fragile labels. Cross-check `boundary_tier`. SOLID labels deserve far more weight than EDGE.
6. **Including SB in the comp-distance metric.** SB is a rated overlay shown alongside C/P/D for context, but Mode 3 distances are computed in C/P/D space only — explicit design decision so comp selection isn't dominated by speed when the question is about hitting profile.
7. **Recommending an add purely on archetype label without roster availability check** — see `/roster-verify` pre-condition rule. Cross-check `get_all_teams()` before any "go pick up X" recommendation.

---

## Integration with other skills

This skill is **process-based** (ratings + archetype). The outcome-based / Statcast-decomposition counterparts are listed below. Parallel relationship to SP skills: `/sp-archetype` is process-based vs `/sp-breakout-signal` is outcome-based for SPs.

| Skill | Relationship |
|---|---|
| `/breakout-sustainability` | Complementary — outcome-based "is this hot streak real" deep-dive for a single hitter. Use both. |
| `/hitter-sustainability` | Complementary — 9-marker Statcast skill decomposition with sweep mode. Process vs Statcast-decomp views. |
| `/hitter-compare` | Companion — head-to-head 2-6 hitter comparison; this skill adds the 20-80 + comp lens. |
| `/savant-compare` | Companion — Baseball Savant percentile views; this skill adds archetype + historical comp matching. |
| `/slump-or-decline` | Companion — slump diagnostic; this skill provides the process baseline for what "normal" looks like for them. |
| `/fa-replacement-pool` | Upstream — surfaces FA hitters; this skill profiles them by archetype + finds historical comps. |
| `/fa-pickup-deep-dive` | Companion — one-hitter deep dive; this skill adds the 20-80 + comp lens. |
| `/league-deep-audit` | Upstream — that audit profiles all 8 rosters; archetype labels can be a column in its output. |
| `/roster-verify` | Pre-condition — always verify roster status before recommending any add. |
| `/player-id-resolve` | Pre-condition — required before any name → batter-ID lookup to prevent same-name collisions. |

---

## Example session

User: "Who does Bobby Witt Jr. compare to historically? Is his 2024 breakout sustainable?"

```
Mode: /hitter-archetype comps Bobby Witt Jr.

Output:

Query: Bobby Witt Jr. 2024 (C=75 P=63 D=51 SB=69), age 24 (PRE_PEAK)
  Archetype: CONTACT_POWER / PURE_CONTACT / ELITE_RAW / SELECTIVE_AGGRESSIVE / HI_SB / PRE_PEAK / NEAR_EDGE
  Components: Contact=72, K_inv=78, BABIP=74, xCON=76 | Barrel=64, HardHit=63, ISO=66, HRrate=60, PullFB=62 | BB=49, Chase_inv=53, ZSwing=51 | SBrate=72, Sprint=66
  Boundary: distance=3 -> NEAR_EDGE; DISCIPLINE=51 is the closest dimension to flipping (need -11 to MINUS, +9 to PLUS)

Top 8 age-matched historical comps (Euclidean distance in C/P/D — SB shown for context only):
| Year | Player           | Age | C  | P  | D  | SB | Archetype       | FP/PA  | T+1 FP/PA |
|------|------------------|-----|----|----|----|----|-----------------|--------|-----------|
| 2018 | Christian Yelich | 27  | 73 | 64 | 54 | 62 | CONTACT_POWER   | 0.819  | 0.905     |
| 2019 | Ketel Marte      | 26  | 71 | 57 | 53 | 54 | PURE_HITTER     | 0.807  | 0.690     |
| 2017 | Jose Ramirez     | 25  | 69 | 56 | 52 | 58 | PURE_HITTER     | 0.828  | 0.861     |
| 2015 | Mike Trout       | 24  | 68 | 71 | 56 | 61 | CONTACT_POWER   | 0.714  | 0.800     |
| 2017 | Carlos Correa    | 23  | 68 | 58 | 53 | 49 | PURE_HITTER     | 0.755  | 0.502     |
| 2019 | Yordan Alvarez   | 22  | 68 | 71 | 54 | 44 | CONTACT_POWER   | 0.816  | 0.659     |
| 2019 | Mookie Betts     | 27  | 71 | 58 | 61 | 56 | CONTACT_EYE     | 0.767  | 0.693     |
| 2021 | Luis Robert Jr.  | 24  | 70 | 57 | 48 | 56 | PURE_HITTER     | 0.693  | 0.564     |

Aggregate T+1 outcomes (n=8):
  Mean FP/PA T+1: 0.709
  Range: 0.502 - 0.905
  Decline rate (T+1 drop >= 0.05): 62% (5/8)

Verdict: Witt 2024 (C=75 P=63 D=51 SB=69) clusters with peak-era Yelich 2018 (C=73 P=64 D=54)
and a young Trout (C=68 P=71 D=56) — comp set is elite young hitters. T+1 outcomes range 0.50-0.91
with mean ~0.71. Witt's 2024 FP/PA = 0.842 is at the upper tail of comps. T+1 mean reversion
expected (5/8 comps declined T+1, base rate matches elite-tier 55.8% decline). NEAR_EDGE
boundary on DISCIPLINE is the only fragility — if BB rate ticks up another point the label
upgrades toward GOAT_TIER. PRE_PEAK age + HI_SB overlay = exceptional fantasy profile.
```

---

## When NOT to use this skill

- **SP analysis** — use `/sp-archetype` instead
- **Sub-250-PA full-season hitters / in-season callups with <80 PA** — no rating yet, sample too thin for archetype assignment
- **Counting-stat decisions** (HR race, SB chase, week-by-week R+RBI projections) — use ESPN dashboards / matchup.html
- **Slump diagnosis** — use `/slump-or-decline` for the dedicated 3-test convergence panel; this skill provides context, not slump verdict
- **Hot-streak validation** — use `/breakout-sustainability` for outcome-based hot-streak decomp; this skill is the process companion

---

## Note on data coverage

- **20-80 ratings + archetype + stickiness + comps**: 2015-2026 (full coverage, **excludes 2020 COVID**)
- **Spray archetype**: **2021-2026 ONLY** (batted-ball direction parquets start in 2021)
- Pre-2021 batter-years will have `spray_archetype` = NaN. The skill should not infer a spray archetype for those years; report it as "(no spray data)" when applicable.
- Daily refresh via `scripts/xfp/build_hitter_archetypes.py` (step 2.7 of `refresh_dashboards.py`).
