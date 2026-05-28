---
name: sp-archetype
description: Profile any SP by 20-80 scouting ratings on Stuff/Movement/Control with archetype label, career-arc trajectory, multi-year archetype shifts, and historical comp matching with T+1/T+2 outcomes. Three modes — profile (single pitcher deep dive), scan (league-wide trajectory shifts), comps (find historical comps for a profile). Built on 1,353 SP-years 2015-2026 with calibrated archetype stickiness (retention rates) and decline base rates. Use whenever the user asks "what kind of pitcher is X", "is X breaking out / declining", "who does X compare to historically", or wants to evaluate whether a pitcher's archetype change is real vs noise.
---

# sp-archetype — multi-mode SP profiling skill

Profile starting pitchers across three orthogonal scouting dimensions (Stuff, Movement, Control), assign archetype labels from a 27-cell matrix, and trace career trajectories with historical comp matching.

**Trigger phrases:** "what kind of pitcher is X", "profile X", "rate X on 20-80", "is X breaking out", "is X declining", "who does X compare to", "find comps for X", "archetype trajectory for X", "scan for breakout candidates", "scan for declining SPs".

---

## OUTPUT REQUIREMENT — always show S/M/C ratings

**Every output of this skill must surface the raw 20-80 ratings (S=, M=, C=) for every pitcher mentioned**, regardless of mode (profile / scan / comps) and regardless of archetype label. The archetype is a categorical summary; the underlying numbers are the actual information. Two pitchers with the same `PURE_STUFF` label can have S=60/M=55/C=50 vs S=79/M=56/C=46 — the ratings are decision-grade, the label is at-a-glance shorthand.

Standard format: `Player Name (S=66 M=59 C=48)` inline, or as dedicated columns in tables. Never report an archetype label without the underlying ratings alongside.

This is especially load-bearing for boundary cases: a pitcher labeled `MOVE_CTRL_ACE` with M=60 (EDGE) is a fundamentally different bet than one with M=68 (SOLID), and only the numbers tell you that.

---

## Empirical Foundation

### The 20-80 scouting scale
Standard scout rating — `50 = league average`, `10 points = 1 SD`, capped `[20, 80]`.
Within-year scaled (so 80 in 2023 = 80 in 2019, normalized to that year's pool).

### Three orthogonal domains
Each pitcher-year rated on:

| Domain | Components averaged | Direction |
|---|---|---|
| **STUFF** | K% + SwStr% + CSW% | higher = better |
| **MOVEMENT** | HR/BF + Barrel% + HardHit% + GB% + xwOBA-contact | composite HR/hard-contact limit |
| **CONTROL** | BB% | lower BB% = higher rating |

**STUFF sub-decomposition** identifies *which* component drives the rating:
- `K_DRIVEN` — K% is highest component (putaway artist)
- `WHIFF_LED` — SwStr% is highest (swing-and-miss monster)
- `CSW_LED` — CSW% is highest (command + zone work)
- `BALANCED` — all components within 8 points

**Velocity sub-tier** (qualifier on STUFF — tested 2026-05-28, NOT a 4th domain):
- `POWER`    — velo_rating ≥ 60 (top 16% by mph within year)
- `BALANCED` — velo_rating 40-59
- `FINESSE`  — velo_rating < 40

Velocity has partial r ≈ +0.065 vs FP/start after S+M+C control — too small for its own domain (incremental R² only +0.001) but meaningful as a stuff-sub-classifier. Same STUFF rating with POWER vs FINESSE velocity points to different breakout mechanisms:
- **POWER + PLUS Stuff** = "Power Stuff" archetype: Skubal 25, Cole 19, Burnes 21, Soriano 26, Misiorowski 26 (velo=80!)
- **FINESSE + PLUS Stuff** = "Finesse Stuff" archetype: Bumgarner 15, Imanaga 26, Sale 24, Hendricks 16, Aaron Nola

These two flavors of high-STUFF have similar FP/start outcomes but different career trajectories (finesse depends more on command durability; power depends more on health/velo retention).

**Pitch arsenal label** (2021+ coverage only — from pitch_features parquets):
- Primary group: FB / SL / CB / CH / FS (slider/curve/changeup/splitter)
- Secondary group: 2nd-most-used pitch if usage ≥ 10%
- Label format: `<PRI>_HEAVY` if primary ≥ 55%, else `<PRI>_<SEC>` (e.g., `FB_SL` = FB-led, slider 2nd)
- Arsenal entropy: Shannon entropy of pitch mix (lower = one-pitch reliant)

Empirically, within PURE_STUFF the pitch archetype DOES differentiate outcomes:
- `FB_CB` (FB + curve 2nd): mean 18.4 — Soriano 26, Glasnow 26, deGrom-like
- `FB_FS` (FB + splitter 2nd): mean 18.1 — Imanaga 26, Yamamoto
- `FB_HEAVY` (>55% FB reliance): mean 15.1 — Misiorowski, Schlittler
- `FB_SL` (FB + slider 2nd): mean 14.4 — Sale, Wheeler (most common type)
- `FB_CH` (FB + changeup 2nd): mean 13.1 — softer outcomes

### Archetype matrix (27 cells)
Each domain bucketed `PLUS` (≥60) / `AVG` (40-59) / `MINUS` (<40) → 27 possible archetypes. 24 populated in 2015-2026 data. Sorted by historical mean FP/start:

| Cell | Archetype | Hist mean FP/s | Canonical example |
|---|---|---|---|
| PLUS/PLUS/PLUS | MT_RUSHMORE | 18.5 | Kershaw 15-16, Skubal 24, deGrom 18 |
| PLUS/PLUS/AVG | STUFF_PLUS_MOVE | 16.2 | Burnes 21, Sale 24, Arrieta 15 |
| PLUS/AVG/PLUS | STUFF_PLUS_CTRL | 15.9 | Scherzer 15, Cole peak, Skubal 25 |
| AVG/PLUS/PLUS | MOVE_CTRL_ACE | 15.3 | Greinke 15, Wheeler 21, Fried 22 |
| PLUS/AVG/AVG | PURE_STUFF | 14.8 | Strider 23, Glasnow, Soriano 26 |
| AVG/PLUS/AVG | PURE_MOVEMENT | 13.6 | Arrieta, Alcantara 22, Fried 22 |
| PLUS/AVG/MINUS | WILD_FIREBALLER | 13.0 | Snell, McClanahan, Cease 22 |
| AVG/AVG/PLUS | PURE_CONTROL | 11.9 | Verlander 22, Woo 25, Bassitt |
| AVG/AVG/AVG | AVERAGE_4_5 | 10.8 | Generic mid-rotation |
| AVG/AVG/MINUS | WILD_MID | 9.1 | Senga 23, Blanco 24 |
| MINUS/AVG/PLUS | JUNKBALLER | 9.0 | Colon 16, Cueto 22 |
| AVG/MINUS/AVG | GENERIC_HR_PRONE | 8.1 | Kennedy 16, Rodón 24 |
| MINUS/AVG/AVG | FILLER | 7.6 | Leake, Williams 18 |
| MINUS/AVG/MINUS | LIABILITY | 6.7 | Rodón 18, Keller 19 |
| MINUS/MINUS/AVG | PIT_CHF | 4.9 | Gonsolin 23, Heaney 25 |

Mean FP/start declines **monotonically** from MT_RUSHMORE → PIT_CHF — the matrix is internally consistent.

### Boundary risk — how durable is the archetype label? (added 2026-05-28)

The 27-cell matrix uses hard thresholds: `PLUS ≥ 60`, `AVG = 40-59`, `MINUS < 40`. A pitcher with `MOVEMENT = 61` is technically PLUS-movement but one bad season flips them to AVG. A pitcher with `MOVEMENT = 70` is well inside PLUS — the label is durable.

For each pitcher-year, compute:
- `bd_S`, `bd_M`, `bd_C` — distance from each rating to its nearest threshold (40 or 60)
- `boundary_distance` — min across all three (the dimension closest to flipping)
- `boundary_tier`:
  - `EDGE` (boundary_distance ≤ 2) — one bad rating point would flip the archetype label
  - `NEAR_EDGE` (3-5) — close but not adjacent; meaningful skill change required to flip
  - `SOLID` (6+) — well inside the cell; label is genuinely durable

**Validated 2026-05-28** (n=603 historical T+1 transitions):
- EDGE retention: **35%** (label flips easily)
- NEAR_EDGE retention: **44%**
- SOLID retention: **66%** (label nearly 2× more sticky than EDGE)

**Implication for profile reading:** when a pitcher gets a fancy archetype label (PURE_STUFF, MT_RUSHMORE, etc.) but `boundary_tier = EDGE`, the label is more advisory than predictive. Many "transitions out" in the historical stickiness data are actually boundary wobble (e.g., `MOVEMENT` dropped from 61 to 58 → AVERAGE_4_5 without any real skill change). Don't over-anchor to a fragile label.

**Canonical PURE_MOVEMENT case study:** of the 8 historical POST_PEAK PURE_MOVEMENT pitcher-years with valid T+1, none "retained" — but Max Fried 2026 (M=65, NEAR_EDGE) is materially safer than George Kirby 2026 (M=60, full EDGE). The boundary tier tells you which post-peak PURE_MOVEMENT label to trust.

### Age tier (added 2026-05-28)

Each pitcher-year tagged with `age_tier`:
- `PRE_PEAK`  — age ≤ 26 (pre-peak development phase)
- `PEAK`      — age 27-31 (typical peak production window)
- `POST_PEAK` — age ≥ 32 (post-peak / decline phase)

Age tier conditions BOTH stickiness AND comp matching:

**Stickiness varies sharply by age tier** (PURE_STUFF example):
- PRE_PEAK retention: 18% (transient — young pitchers still finding identity)
- PEAK retention: **31%** (most durable — established identity)
- POST_PEAK retention: 15% (transient — declining out of arch)

**AVERAGE_4_5 POST_PEAK retention: 66%** — old slot-fillers very sticky (they've stabilized at the floor).
**MT_RUSHMORE PEAK retention: 50%** (n=6) vs 38% overall — peak-age elite more durable.

**Age-matched comps reduce T+1 FP/s prediction MAE by ~4%** (2.28 → 2.19, p=0.08, n=440 historical pitcher-years). Optimal window: ±3 years. Default comp matching uses age-matched within ±3 years; if pool < 8 cands, fall back to all-age with `age_diff_penalty` weighting.

### Archetype stickiness (year-over-year retention)
**Most reliable labels** — pitchers tend to stay year-to-year:
- AVERAGE_4_5: 59%, JUNKBALLER 56%, WILD_FIREBALLER 50%

**Volatile labels** — frequent transitions:
- PURE_MOVEMENT: 20% (46% become AVERAGE_4_5)
- STUFF_PLUS_MOVE: 7% (43% become PURE_STUFF)
- MOVE_CTRL_ACE: 0/11 retained — peak seasons only

**Multi-year sustained archetypes are stickier** — retention rises from 35% (1st year in arch) → 54% (2nd) → **69% (3rd)**. Always check streak length.

### Decline base rates (use as context, not alert)
- Overall T+1 decline rate (FP/s drop ≥3 OR archetype tier drop): ~30%
- **Elite tier (FP/s ≥ 14): 59% T+1 decline** — more than half regress
- **Counter-intuitive finding:** elite pitcher-years with STUFF/SwStr/velo *dropping at year T* actually have LOWER T+1 decline rate (mean reversion already absorbed). Do not use prior-year drops as decline predictor.

### Breakout-prediction validity (from prior validation)
- MOVE archetype matches predict breakout at **44% rate** (vs 5% baseline) — 9× lift
- STUFF_loose (high K%, walks) matches predict at **29%** — 6× lift
- STUFF_clean matches predict at 8% — only 1.6× lift

---

## Data sources

All built by `scripts/xfp/build_sp_archetypes.py` (runs in `refresh_dashboards.py` step 2.6):

```
data/research/sp_ratings_master.csv               — 1,353 pitcher-years 2015-2026 with full 20-80 ratings
data/research/sp_archetype_career_panel.parquet   — same + T+1/T+2 outcomes
data/research/sp_archetype_definitions.json       — 27 cell labels with descriptions
data/research/sp_archetype_stickiness.json        — retention rates per archetype
data/research/sp_decline_baselines.json           — base rates for context framing
```

---

## Modes

### Mode 1 — Profile a single pitcher: `/sp-archetype <name>`

Example: `/sp-archetype Cam Schlittler`

```python
import pandas as pd, json
from pathlib import Path
REPO = Path(r'c:\Users\Joshua\plv_clone')

master = pd.read_csv(REPO / 'data/research/sp_ratings_master.csv')
careers = pd.read_parquet(REPO / 'data/research/sp_archetype_career_panel.parquet')
stick = json.load(open(REPO / 'data/research/sp_archetype_stickiness.json'))

# Find pitcher across all years
name_pattern = 'Schlittler'  # or full name
rows = master[master['player_name'].str.contains(name_pattern, case=False, na=False)]
```

**Output sections** (in this order):
1. **Current rating snapshot** — Lead with `S=X M=Y C=Z (velo=V)` on the first line. Follow with the 9-component breakdown (K/SwStr/CSW, HRrate/Barrel/HardHit/GB/xCON, BB). Include age + age tier.
2. **Full label** — e.g., `STUFF_PLUS_CTRL / WHIFF_LED / POWER / FB_HEAVY / PEAK / SOLID` (archetype + stuff-subtype + velo-tier + pitch-archetype + age-tier + boundary-tier). Always pair with `(S=X M=Y C=Z)` on the same line so the label is never disconnected from the numbers.
3. **Boundary risk** — `boundary_distance` value + tier + which domain is closest to flipping. E.g., "boundary distance = 2 → EDGE; MOVEMENT=61 is 1 point from flipping the PLUS-movement label"
4. **Age-conditioned stickiness** — retention% for this archetype AT THIS AGE TIER (not just overall). E.g., "PURE_STUFF PEAK retention: 31%, your age tier — vs 18% PRE_PEAK and 15% POST_PEAK"
5. **Career arc** — year-by-year archetype trail with FP/start AND age AND boundary tier. **Format each line with S/M/C explicit:** `2024 (age 28) STUFF_PLUS_CTRL [S=72 M=55 C=64] EDGE, FP/s=17.3`
6. **Verdict** — 1-2 sentences synthesizing what kind of pitcher they are and what the data says about durability, weighted by both age tier and boundary tier (SOLID labels deserve more weight than EDGE labels). Reference specific S/M/C values when arguing the verdict (e.g., "S=79 is the strongest stuff rating in the 2026 cohort").

### Mode 2 — League-wide trajectory scan: `/sp-archetype scan`

Surface 2025→2026 archetype shifts (upward and downward) with roster status:

```python
careers = pd.read_parquet(REPO / 'data/research/sp_archetype_career_panel.parquet')
arch_q = master.groupby('archetype')['fp_per_start'].mean()

# 2025 → 2026 transitions with archetype quality delta
current_year = 2026
careers['arch_q'] = careers['archetype'].map(arch_q)
careers['prev_arch'] = careers.groupby('pitcher')['archetype'].shift(1)
careers['prev_arch_q'] = careers.groupby('pitcher')['arch_q'].shift(1)
careers['dQ'] = careers['arch_q'] - careers['prev_arch_q']

shifts = careers[(careers['year']==current_year) & careers['prev_arch'].notna() &
                 (careers['archetype'] != careers['prev_arch'])]
upward = shifts[shifts['dQ'] > 1.5].sort_values('dQ', ascending=False)
downward = shifts[shifts['dQ'] < -1.5].sort_values('dQ')
```

Then enrich with roster status from `app.espn_connector` (see `/roster-verify` pattern).

**Output sections:**
1. **Upward shifts on YOUR roster** (holds — validating real breakouts)
2. **Upward shifts available as FA** (actionable adds)
3. **Upward shifts rostered elsewhere** (trade targets)
4. **Decline on YOUR roster** (sell-high / drop candidates)
5. **Decline as FA** (avoid these adds despite ownership %)

**Table format requirement:** every row must include columns for `S`, `M`, `C` (current year ratings) and `dS`, `dM`, `dC` (deltas vs prior year). Boundary tier as a separate column. The archetype label is shorthand — readers need the underlying numbers to evaluate whether a shift is real (large dS/dM/dC) or boundary wobble (small deltas crossing a threshold).

Standard row layout:
```
Player | Status | Baseline arch | 2026 arch | S | M | C | dS | dM | dC | bd_tier | dFP
```

Sample-size caveat: 2026 ratings based on ≤11 GS. Flag pitchers with `gs < 7` as "sample-thin" and note that the dS/dM/dC could compress with more starts.

### Mode 3 — Find historical comps for a pitcher: `/sp-archetype comps <name>`

Given any pitcher, find the K=5-8 closest historical SP-seasons (Euclidean distance in S/M/C space, **age-matched ±3 years by default**) and report their T+1 / T+2 outcomes. Validated 2026-05-28: age-matching reduces prediction MAE by ~4%. This is the most directly actionable mode.

```python
from scipy.spatial.distance import cdist

careers = pd.read_parquet(REPO / 'data/research/sp_archetype_career_panel.parquet')

def find_comps(query_S, query_M, query_C, query_age=None, exclude_pitcher=None, k=8,
               exclude_inprogress=True, current_year=2026, age_window=3):
    """Default: age-matched comps within ±3 years. Falls back to all-age if pool < k."""
    cands = careers.copy()
    if exclude_inprogress:
        cands = cands[cands['year'] != current_year]
    if exclude_pitcher is not None:
        cands = cands[cands['pitcher'] != exclude_pitcher]
    cands = cands[cands['next_fp'].notna()]

    # Try age-matched first
    if query_age is not None and 'age' in cands.columns:
        age_matched = cands[(cands['age'] >= query_age - age_window) &
                            (cands['age'] <= query_age + age_window)]
        if len(age_matched) >= k:
            cands = age_matched
        # else fall back to all-age

    qv = np.array([[query_S, query_M, query_C]])
    Xc = cands[['STUFF','MOVEMENT','CONTROL']].values
    dists = cdist(Xc, qv, metric='euclidean').flatten()
    cands = cands.assign(distance=dists).sort_values('distance').head(k)
    return cands
```

**Output:**
1. **Query profile** on its own line — `Query: Player Name (S=66 M=59 C=48), age 24, archetype PURE_STUFF [NEAR_EDGE]`. Always lead with the S/M/C of the query before listing comps.
2. **Top 5-8 comps** with year, name, **S/M/C of the comp**, FP/s in comp year, distance, T+1 FP/s, T+1 archetype, T+2 FP/s. Standard column layout:
   ```
   Year | Player | Age | S | M | C | FP/s | dist | T+1 FP/s | T+1 arch
   ```
3. **Aggregate T+1 stats** — mean T+1 FP/s, % broke out (T+1 FP/s ≥ 14), % declined (drop ≥3), % sustained
4. **Quality flag** — if mean comp distance > 5.0, note "wide distance — query profile is unusual, comp set may not be highly representative"

---

## Step-by-Step Execution

### Step 0: Verify data freshness
Check that `data/research/sp_ratings_master.csv` was rebuilt today. If stale (>24h), suggest running `refresh_dashboards.py` or `build_sp_archetypes.py` directly.

### Step 1: Disambiguate pitcher (for Mode 1 / Mode 3)
- Use `str.contains(case=False)` against `player_name` column (which is "Last, First" format)
- If multiple matches, list and disambiguate by team / current year
- For collisions: consult `plv_clone/utils/name_match.py` (KNOWN_COLLISIONS)

### Step 2: Pull all years for that pitcher
- Show every season they had ≥ 4 GS (2026) or ≥ 20 GS (prior years)
- Most recent year is the focus; prior years for trajectory context

### Step 3: For Mode 3, ALWAYS exclude the query pitcher's own seasons from comp candidates
Self-matching gives degenerate results.

### Step 4: Format output with markdown tables, year-sorted

---

## Anti-patterns to avoid

0. **Reporting an archetype label without the S/M/C ratings alongside.** The label is shorthand; the numbers are the actual information. Two pitchers labeled PURE_STUFF with S=60 vs S=79 are fundamentally different bets. ALWAYS pair labels with raw ratings in every output, every mode.

1. **Treating 1st-year-in-archetype as durable** — stickiness data says single-year labels have only 35% retention. Flag streak length.
2. **Using prior-year process drops as "decline early warning"** — counter to intuition, those pitchers regress LESS in T+1 (already mean-reverted). The decline baseline for elite SPs is 59% regardless of process indicators; frame as base-rate context, not actionable alert.
3. **Comparing across years without within-year normalization** — z-scores are computed within each year's qualified pool. "STUFF=65 in 2019" and "STUFF=65 in 2023" are equivalent within-year percentiles, NOT equivalent raw K%.
4. **Acting on 2026 in-progress ratings with <6 GS** — sample-thin. Note caveat in output.
5. **Trusting MT_RUSHMORE / MOVE_CTRL_ACE / STUFF_PLUS_MOVE labels for forward projection** — these archetypes have <40% retention rate. Most who reach them regress to a lower archetype the following year.
6. **Recommending an add purely on archetype label without roster availability check** — see `/roster-verify` pre-condition rule. Cross-check `get_all_teams()` before any "go pick up X" recommendation.

---

## Integration with other skills

| Skill | Relationship |
|---|---|
| `/sp-breakout-signal` | Complementary — that skill is rolling-window outcome-based (good starts); this skill is process-based (ratings + archetype). Use both. |
| `/fa-sp-pool` | Upstream — that skill surfaces FA SPs; this skill profiles them by archetype + finds historical comps. |
| `/fa-pickup-deep-dive` | Companion — one-pitcher deep dive; this skill adds the 20-80 + comp lens. |
| `/sp-week-plan` | Consumer — archetype context informs which start to trust this week. |
| `/league-deep-audit` | Upstream — that audit profiles all 8 rosters; archetype labels can be a column in its output. |
| `/roster-verify` | Pre-condition — always verify roster status before recommending any add. |

---

## Example session

User: "Who does Cam Schlittler compare to historically? He looks like a breakout."

```
Mode: /sp-archetype comps Cam Schlittler

Output:

Query: Cam Schlittler 2026 (S=67 M=59 C=67), age 25 (PRE_PEAK)
  Archetype: STUFF_PLUS_CTRL / WHIFF_LED / POWER / FB_HEAVY / PRE_PEAK / EDGE
  Components: K=67, SwStr=73, CSW=60 (SwStr drives stuff) | HR=64, Barrel=55, GB=56 | BB=67
  Velo: 75 (95.2 mph, 80th percentile within 2026)
  Arsenal: 90% FB, 7% CB, 3% SL — heavily fastball-reliant
  Boundary: distance=1 → EDGE; MOVEMENT=59 is 1 point from flipping the AVG-movement label to PLUS (would become MT_RUSHMORE)

Top 8 age-matched historical comps (Euclidean distance in S/M/C):
| Year | Player          | Age | S  | M  | C  | FP/s  | Dist | T+1 FP/s | T+1 arch         |
|------|-----------------|-----|----|----|----|-------|------|----------|------------------|
| 2022 | Aaron Nola      | 29  | 65 | 58 | 65 | 17.36 | 2.8  | 13.01    | PURE_CONTROL     |
| 2017 | Clayton Kershaw | 29  | 66 | 58 | 68 | 18.96 | 3.0  | 15.61    | PURE_CONTROL     |
| 2021 | Clayton Kershaw | 33  | 64 | 60 | 63 | 14.14 | 3.5  | 16.24    | MT_RUSHMORE      |
| 2019 | Max Scherzer    | 34  | 72 | 57 | 65 | 19.08 | 5.7  | 18.81    | STUFF_PLUS_CTRL  |
| 2015 | Matt Harvey     | 26  | 65 | 56 | 64 | 16.94 | 5.9  |  9.62    | PURE_CONTROL     |
| 2024 | Logan Gilbert   | 27  | 64 | 56 | 70 | 17.03 | 6.2  | 14.52    | PURE_STUFF       |
| 2015 | Jacob deGrom    | 27  | 66 | 57 | 63 | 17.51 | 6.3  | 14.06    | AVERAGE_4_5      |
| 2025 | Nathan Eovaldi  | 35  | 61 | 56 | 64 | 17.40 | 6.6  | 10.13    | PURE_CONTROL     |

Aggregate T+1 outcomes (n=8):
  Mean FP/s T+1: 14.00
  Breakout rate (T+1 >= 14): 62%
  Decline rate (T+1 drop >= 3): 38%

Verdict: Schlittler (S=67 M=59 C=67) clusters with peak-era Kershaw (S=66 M=58 C=68)
and deGrom 2015 (S=66 M=57 C=63) — the comp set is strong. 62% T+1 breakout-or-sustain
rate is well above the 30% elite base rate. POWER velo tier + FB_HEAVY arsenal makes him
a "power stuff, one-pitch-elite" type. EDGE boundary tier is the caution: M=59 is 1 point
from MT_RUSHMORE; if M ticks up another point with more sample, the archetype upgrades.
Sample caveat: only 7 GS in 2026.
```

---

## Note on data coverage

- **20-80 ratings + archetype + stickiness + comps**: 2015-2026 (full coverage)
- **Velo tier**: 2015-2026 (avg_velo from `sp_multiyr_2015_2025.csv`)
- **Pitch arsenal / pitch_archetype**: **2021-2026 ONLY** (pitch_features parquets start in 2021)
- Pre-2021 pitcher-years will have `pitch_archetype` = NaN. The skill should not infer a pitch archetype for those years; report it as "(no arsenal data)" when applicable.
