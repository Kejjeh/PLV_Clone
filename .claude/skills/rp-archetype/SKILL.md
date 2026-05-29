---
name: rp-archetype
description: Profile any RP by 20-80 scouting ratings on Stuff/Control/Batted-Ball (3 domains, 6 sub-domains) with archetype label, career-arc trajectory, multi-year archetype shifts, role tags (CLOSER / HIGH_LEVERAGE / MULTI_INNING_BULK), and historical comp matching with T+1/T+2 outcomes. Three modes — profile (single RP deep dive), scan (league-wide trajectory shifts), comps (find historical comps for a profile). Built on 2,087 RP-years 2018-2026 (minus 2020) with calibrated archetype stickiness and decline base rates. Use whenever the user asks "what kind of RP is X", "is X breaking out / declining", "who does X compare to historically", or wants to evaluate whether a reliever's archetype change is real vs noise.
---

# rp-archetype — multi-mode RP profiling skill

Profile relievers across three orthogonal scouting dimensions (Stuff, Control, Batted-Ball), assign archetype labels from a 27-cell matrix, layer role tags, and trace career trajectories with historical comp matching.

**Trigger phrases:** "what kind of RP is X", "profile X", "rate X on 20-80", "is X breaking out", "is X declining", "who does X compare to", "find comps for X", "archetype trajectory for X", "scan for RP breakout candidates", "scan for declining RPs".

---

## OUTPUT REQUIREMENT — always show S/C/B ratings

**Every output of this skill must surface the raw 20-80 ratings (S=, C=, B=) for every RP mentioned**, regardless of mode (profile / scan / comps) and regardless of archetype label. The archetype is a categorical summary; the underlying numbers are the actual information. Two RPs with the same `PURE_STUFF_RP` label can have S=60/C=50/B=48 vs S=79/C=51/B=49 — the ratings are decision-grade, the label is at-a-glance shorthand.

Standard format: `Player Name (S=66 C=59 B=48)` inline, or as dedicated columns in tables. Also surface the 6 sub-domain ratings (SwM, CS, Velo, WalkAvoid, GB, Bulk) for the focus RP in profile mode.

---

## CRITICAL CAVEAT — RP projection signal is weak

- **T+1 R² = 0.246, T+2 R² = 0.259** (vs SP's T+1 R²=0.41). RP archetype outputs are **directional priors, not forecasts.** Median RP sees ~198 TBF/year vs SP 500-700 — noise dominates.
- Use this skill to answer **"who is this RP as a pitcher"** — NOT "is this RP good for fantasy" (use `xfp_rprs2_projections.csv` for that).
- **CLOSER tag persistence is 57.8% YoY** — slightly better than a coin flip. Don't over-weight the tag for next-year predictions; always verify current role via ESPN / recent box scores.
- **GB_TENDENCY is a stable identity axis but has ~zero empirical FP weight.** A sinkerballer can grade SOLID on BATTED_BALL without that meaning higher production than a non-sinkerballer with the same STUFF / CONTROL.
- **DAMAGE_SUPP is intentionally NOT a rated subdomain.** xwOBACON failed YoY stability (r=0.12). For "is this RP suppressing damage?" questions, report display columns (gb_pct, barrel_pct, hard_hit_pct, xwobacon) with the caveat that those are unstable signals at RP sample sizes.

---

## Empirical Foundation

### Three orthogonal main domains, six sub-domains

| Main domain | Sub-domains averaged | Direction |
|---|---|---|
| **STUFF** | SWING_MISS (K%/SwStr%) + VELO | higher = better |
| **CONTROL** | WALK_AVOID (BB%↓) + CALLED_STRIKE (CS%) | higher = better |
| **BATTED_BALL** | GB_TENDENCY (GB%) + BULK_IP (IP/appearance) | identity axis (low FP weight) |

All ratings within-year normalized to 20-80 (50 = league avg, 10 pts = 1 SD, clipped [20, 80]).

**Stuff sub-decomposition** (`stuff_subtype` column): `K_DRIVEN`, `WHIFF_LED`, `BALANCED`. **Velo tier**: `POWER` (velo ≥ 60), `BALANCED` (40-59), `FINESSE` (<40).

### Archetype matrix (27 cells)
Domains bucketed `PLUS` (≥60) / `AVG` (40-59) / `MINUS` (<40) → 27 archetypes (all populated). Top of the matrix by historical mean fp_per_g:

| Cell (S/C/B) | Archetype | n | Hist mean FP/g | Canonical example |
|---|---|---|---|---|
| PLUS/PLUS/PLUS | ELITE_CLOSER_STUFF | 8 | 4.95 | Edwin Díaz peak, Bautista 23 |
| PLUS/PLUS/AVG | LATE_INNING_STUFF_CTRL | 40 | 4.81 | Hader peak, Iglesias 24 |
| PLUS/AVG/PLUS | STUFF_GB_HYBRID | 19 | 4.72 | Devin Williams blend |
| PLUS/AVG/AVG | PURE_STUFF_RP | 180 | 4.08 | Mason Miller, Helsley pre-decline |
| AVG/PLUS/PLUS | GB_INNINGS_EATER | 58 | 3.88 | Holmes 23, Bednar 22 |
| PLUS/MINUS/MINUS | WILD_HIGH_LEVERAGE | 13 | 3.81 | Estévez 24 |
| PLUS/AVG/MINUS | STUFF_NO_BULK | 53 | 3.72 | Short-burst setup |
| AVG/PLUS/AVG | COMMAND_MIDDLE | 156 | 3.42 | Veteran middle-relief |
| PLUS/MINUS/AVG | WILD_FIREBALLER_RP | 42 | 3.40 | Chapman 23, Jansen 21 |
| AVG/AVG/PLUS | BULK_GB_RP | 161 | 3.25 | Bulk options |
| AVG/AVG/AVG | GENERIC_MIDDLE | 683 | 2.90 | Most common archetype |
| AVG/MINUS/AVG | AVG_STUFF_WILD | 151 | 2.46 | Walk-prone middle |
| MINUS/AVG/AVG | FILLER_RP | 130 | 2.18 | Up-and-down |
| MINUS/MINUS/AVG | STRUGGLING_RP | 18 | 1.40 | DFA candidates |
| MINUS/MINUS/MINUS | FRINGE_RP | 7 | 1.27 | Roster filler |

Full label set: `data/research/rp_archetype_definitions.json`.

### Role tags (orthogonal to archetype)
- **CLOSER** — primary save-getter for team (SV-rate threshold)
- **HIGH_LEVERAGE** — late-inning role (HLD + SV usage; legacy binary tag)
- **MULTI_INNING_BULK** — IP/appearance ≥ 1.4 (long-relief / bulk)
- **FIREMAN** — currently stubbed `False` across the panel. IS%/IR data is **not exposed** by the FG combined-stats JSON endpoint (confirmed by exhaustive key-dump 2026-05-29). Tag remains in the schema for forward compatibility but cannot fire until a different source (FG splits / B-Ref) is wired in v2.

A reliever can carry multiple tags. Role tags are **display only** — they describe usage, not skill, and aren't used in comp distance.

### Leverage tier (NEW 2026-05-29 — continuous replacement for binary HIGH_LEVERAGE)

Derived from FanGraphs **gmLI** (game-entry Leverage Index, average over the reliever's appearances). Join coverage on the qualifying cohort: **2,086 / 2,087 (99.95%)** RP-years 2018-2026 (no 2020).

| Tier | gmLI band | Meaning |
|---|---|---|
| `ELITE_LEVERAGE` | ≥ 1.5 | Primary closer / true high-leverage role (Munoz, Suarez, Diaz, Mason Miller) |
| `HIGH_LEVERAGE` | 1.2 – 1.49 | Setup / co-closer (Clase 25, Bednar) |
| `MID_LEVERAGE` | 0.85 – 1.19 | Middle relief w/ occasional late work |
| `LOW_LEVERAGE` | 0.5 – 0.84 | Long relief / blowout role |
| `GARBAGE_TIME` | < 0.5 | Mop-up only |

Falls back to the SV/HLD-derived binary tag when gmLI is null (pre-qualifier RPs only — should be rare).

**Verified 2025 distribution**: 54 ELITE / 71 HIGH / 95 MID / 49 LOW / 10 GARBAGE.

**Usage note**: `leverage_tier` is a usage/role signal, NOT a skill signal — it's a display column + filter, not part of the archetype label, sub-domains, or comp distance.

### Boundary risk (RP-calibrated, 2026-05-28)
- `boundary_distance` = min distance across S/C/B to nearest threshold (40 or 60)
- `boundary_tier`: `EDGE` (≤2), `NEAR_EDGE` (3-5), `SOLID` (6+)

**Validated retention rates (n=819 transitions):**
- EDGE: **27.2%** retention
- NEAR_EDGE: **33.5%**
- SOLID: **44.0%** (~1.6× more sticky than EDGE)

Lower overall retention than SP (RP labels are inherently noisier) — but the EDGE→SOLID spread still ranks label durability.

### Age tier
- `PRE_PEAK` — age ≤ 26
- `PEAK` — age 27-31
- `POST_PEAK` — age ≥ 32

Stickiness JSON breaks down retention by `by_age_tier` per archetype — consult for the specific RP under review.

### Decline base rates (`rp_decline_baselines.json`)
- Overall T+1 decline rate (fp_per_g drop ≥1 OR arch quality drop): **39.7%**
- Elite tier (fp_per_g ≥ 4.5): **55.9%** T+1 decline
- Treat as base-rate context for framing, not actionable per-RP signals (small-sample noise dominates).

---

## Data sources

All built by `scripts/xfp/build_rp_archetypes.py`:

```
data/research/rp_ratings_master.csv               — 2,087 RP-years 2018-2026 (no 2020), 20-80 ratings + tags
data/research/rp_archetype_career_panel.parquet   — same + T+1/T+2 outcomes (next_fp, next_arch, t2_fp)
data/research/rp_archetype_definitions.json       — 27 cell labels with descriptions
data/research/rp_archetype_stickiness.json        — retention rates per archetype, by age tier
data/research/rp_decline_baselines.json           — base rates for context framing
data/research/rp_boundary_validation.json         — EDGE/NEAR_EDGE/SOLID retention rates
```

---

## Modes

### Mode 1 — Profile a single RP: `/rp-archetype <name>`

Example: `/rp-archetype Mason Miller`

```python
import pandas as pd, json
from pathlib import Path
REPO = Path(r'c:\Users\Joshua\plv_clone')

master = pd.read_csv(REPO / 'data/research/rp_ratings_master.csv')
careers = pd.read_parquet(REPO / 'data/research/rp_archetype_career_panel.parquet')
stick = json.load(open(REPO / 'data/research/rp_archetype_stickiness.json'))

rows = master[master['player_name'].str.contains('Miller', case=False, na=False)]
```

**Output sections** (in order):
1. **Current snapshot** — Lead `S=X C=Y B=Z (velo=V)` on first line. Include age + age tier + role.
2. **6-subdomain breakdown** — SwM, CS, Velo, WalkAvoid, GB, Bulk (each 20-80) plus the raw stats (k_pct, bb_pct, swstr_pct, called_strike_rate, avg_velo, gb_pct, ip_per_appearance).
3. **Full label** — e.g., `PURE_STUFF_RP / K_DRIVEN / POWER / PEAK / EDGE` (archetype + stuff-subtype + velo-tier + age-tier + boundary-tier). Pair with `(S=X C=Y B=Z)` on the same line.
4. **Role tags** — `CLOSER=True, HIGH_LEVERAGE=True, MULTI_INNING_BULK=False`. Include current-season SV / HLD counts for context.
5. **Boundary risk** — `boundary_distance` + tier + which dimension is closest to flipping.
6. **Age-conditioned stickiness** — retention% for this archetype AT THIS AGE TIER from `rp_archetype_stickiness.json`'s `by_age_tier`. E.g., "PURE_STUFF_RP PEAK retention: X% (n=Y)". Fall back to overall retention if age tier sample is thin.
7. **Career arc** — year-by-year archetype trail with fp_per_g, age, boundary tier, and CLOSER tag. Format: `2024 (age 28) PURE_STUFF_RP [S=72 C=55 B=48] EDGE, CLOSER=True, fp/g=4.30`.
8. **T+1 / T+2 projections** — from `t1_fp_projection` / `t2_fp_projection` columns. **CAVEAT them every time**: "(model R²=0.25 — directional only)".
9. **Verdict** — 1-2 sentences synthesizing identity (process), weighted by boundary + age tier + role-tag durability. Reference specific S/C/B values. **Do not argue fantasy value** — that's rprs2's job.

### Mode 2 — League-wide trajectory scan: `/rp-archetype scan`

Surface 2025→2026 archetype shifts and role changes:

```python
careers = pd.read_parquet(REPO / 'data/research/rp_archetype_career_panel.parquet')
master = pd.read_csv(REPO / 'data/research/rp_ratings_master.csv')

arch_q = master.groupby('archetype')['fp_per_g'].mean()
careers['arch_q'] = careers['archetype'].map(arch_q)
careers['prev_arch'] = careers.groupby('pitcher')['archetype'].shift(1)
careers['prev_arch_q'] = careers.groupby('pitcher')['arch_q'].shift(1)
careers['prev_closer'] = careers.groupby('pitcher')['CLOSER'].shift(1)
careers['dQ'] = careers['arch_q'] - careers['prev_arch_q']

current_year = 2026
shifts = careers[(careers['year']==current_year) & careers['prev_arch'].notna() &
                 (careers['archetype'] != careers['prev_arch'])]
upward = shifts[shifts['dQ'] > 0.5].sort_values('dQ', ascending=False)
downward = shifts[shifts['dQ'] < -0.5].sort_values('dQ')

# Boundary crossings (SOLID -> EDGE = decline risk; EDGE -> SOLID = breakout)
bnd_cross = careers[(careers['year']==current_year)].merge(
    careers[careers['year']==current_year-1][['pitcher','boundary_tier']]
      .rename(columns={'boundary_tier':'prev_bnd'}),
    on='pitcher', how='inner')

# Domain delta scan: ≥10 pt change in S/C/B
prev = careers[careers['year']==current_year-1].set_index('pitcher')[['STUFF','CONTROL','BATTED_BALL']]
cur = careers[careers['year']==current_year].set_index('pitcher')[['STUFF','CONTROL','BATTED_BALL']]
deltas = (cur - prev).rename(columns=lambda c: f'd{c[0]}').dropna()

# Closer flips
lost_closer = careers[(careers['year']==current_year) & (~careers['CLOSER']) &
                       (careers['prev_closer']==True)]
gained_closer = careers[(careers['year']==current_year) & (careers['CLOSER']) &
                         (careers['prev_closer']==False)]

# Closer-by-stuff candidates: non-CLOSER with STUFF + CONTROL both ≥ 65
cbs_cands = careers[(careers['year']==current_year) & (~careers['CLOSER']) &
                     (careers['STUFF']>=65) & (careers['CONTROL']>=65)]
```

Then enrich with roster status from `app.espn_connector` (see `/roster-verify` pattern).

**Output sections:**
1. **Upward archetype shifts on YOUR roster** (validating real RP breakouts you hold)
2. **Upward shifts available as FA** (actionable adds — but cross-check rprs2 first)
3. **Upward shifts rostered elsewhere** (potential trade targets)
4. **Decline on YOUR roster** (sell-high candidates — caveat with rprs2)
5. **Decline as FA** (avoid)
6. **Lost CLOSER tag** (production will lag the skill until role returns — sell-high signal for stuff-elite RPs who lost the job)
7. **Gained CLOSER tag** (handcuff add candidates)
8. **Closer-by-stuff candidates** (non-CLOSER RPs with S+C both ≥ 65 — next-man-up profile)

**Table format requirement:** every row must include columns for `S`, `C`, `B` (current year) and `dS`, `dC`, `dB` (deltas vs prior). Boundary tier as a separate column. Tag columns `CLOSER`/`HIGH_LEV`/`BULK`.

Standard row layout:
```
Player | Status | Prev arch | 2026 arch | S | C | B | dS | dC | dB | bd_tier | CLOSER | dFP/g
```

Sample-size caveat: 2026 ratings based on partial-season TBF — flag any RP with `tbf < 80` as "sample-thin".

### Mode 3 — Find historical comps for an RP: `/rp-archetype comps <name>`

K=5-8 closest historical RP-seasons by Euclidean distance over the **6 sub-domain ratings** (SwM, CS, Velo, WalkAvoid, GB, Bulk), age-matched ±3 years by default.

```python
from scipy.spatial.distance import cdist
import numpy as np

careers = pd.read_parquet(REPO / 'data/research/rp_archetype_career_panel.parquet')
SUB_COLS = ['SWING_MISS','CALLED_STRIKE','VELO','WALK_AVOID','GB_TENDENCY','BULK_IP']

def find_comps(query_vec, query_age=None, exclude_pitcher=None, k=8,
               exclude_inprogress=True, current_year=2026, age_window=3):
    """Default: age-matched ±3 years. Fall back to all-age if pool < k."""
    cands = careers.copy()
    if exclude_inprogress:
        cands = cands[cands['year'] != current_year]
    if exclude_pitcher is not None:
        cands = cands[cands['pitcher'] != exclude_pitcher]
    cands = cands[cands['next_fp'].notna()]

    if query_age is not None:
        age_matched = cands[(cands['age'] >= query_age - age_window) &
                            (cands['age'] <= query_age + age_window)]
        if len(age_matched) >= k:
            cands = age_matched

    qv = np.array([query_vec])
    Xc = cands[SUB_COLS].values
    dists = cdist(Xc, qv, metric='euclidean').flatten()
    return cands.assign(distance=dists).sort_values('distance').head(k)
```

**Output:**
1. **Query profile** on its own line — `Query: Player (S=X C=Y B=Z), 6-sub [SwM=a CS=b V=c WA=d GB=e Bk=f], age N, archetype LABEL [bd_tier], CLOSER=bool`.
2. **Top 5-8 comps** with year, name, age, **all 6 sub-domain ratings of the comp**, fp_per_g in comp year, distance, T+1 fp_per_g, T+1 archetype, T+2 fp_per_g. Layout:
   ```
   Year | Player | Age | SwM | CS | V | WA | GB | Bk | fp/g | dist | T+1 fp/g | T+1 arch
   ```
3. **Aggregate T+1 stats** — mean T+1 fp_per_g, % broke out (T+1 ≥ 4.0), % declined (drop ≥1), % sustained
4. **Quality flag** — if mean comp distance > 7.0, note "wide distance — query profile is unusual, comp set may not be highly representative".
5. **CAVEAT footer** — repeat the R²=0.25 directional warning.

---

## Step-by-Step Execution

### Step 0: Verify data freshness
Check `data/research/rp_ratings_master.csv` mtime. If stale (>24h), suggest running `python scripts/xfp/build_rp_archetypes.py`.

### Step 1: Disambiguate RP (Mode 1 / Mode 3)
- `str.contains(case=False)` against `player_name`
- For collisions: consult `plv_clone/utils/name_match.py` (KNOWN_COLLISIONS) — same rule as SP/hitter.

### Step 2: Pull all years for that RP
- Show every season they had ≥ 80 TBF (or all seasons if RP career is short)
- Most recent year is focus; prior years for trajectory context

### Step 3: For Mode 3, ALWAYS exclude the query RP's own seasons from comp candidates

### Step 4: Format output with markdown tables, year-sorted, S/C/B always visible

---

## Anti-patterns to avoid

0. **Reporting an archetype label without S/C/B (and the 6 sub-domains in profile mode) alongside.** Same rule as SP. Two RPs labeled PURE_STUFF_RP with S=60 vs S=79 are fundamentally different bets.

1. **Recommending an RP add solely on archetype label without checking current rprs2 projection.** This skill answers "who is this pitcher" — not "is this a good fantasy add". Always cross-reference `data/outputs/xfp_rprs2_projections.csv` before any add rec.

2. **Trusting the CLOSER tag for next year.** Persistence is 57.8% YoY. Verify current role via ESPN connector or recent box scores (saves in last 7 days). The tag is a snapshot, not a forecast.

3. **Recommending an RP based on STUFF/CONTROL improvement when CLOSER status is gone.** Production will lag the skill until role changes back. A `PURE_STUFF_RP` who lost the closer job is fantasy-irrelevant in points leagues regardless of how good the stuff is.

4. **Comparing an SP-context to an RP** (or vice versa). Cross-role comps are meaningless — different feature distributions, different TBF baselines, different scoring formulas. Use `/sp-archetype` for SPs.

5. **Treating T+1 / T+2 projections as forecasts.** R²=0.25 means they explain a quarter of the variance. They're directional priors; do not anchor on the point estimate.

6. **Using BATTED_BALL rating to argue fantasy value.** GB_TENDENCY is a stable identity axis but has ~zero empirical fp_per_g weight. A SOLID-BATTED_BALL sinkerballer doesn't outproduce a same-STUFF/CONTROL non-sinkerballer just because of the rating.

7. **Acting on EDGE-tier archetype labels as durable.** 27.2% retention. Many year-to-year "transitions" are boundary wobble (one rating point flipping a label without real skill change). SOLID labels deserve ~1.6× more weight than EDGE labels.

8. **Inferring damage suppression from rating data.** DAMAGE_SUPP is intentionally not a rated subdomain (xwOBACON YoY r=0.12). Report display columns (gb_pct, barrel_pct, hard_hit_pct, xwobacon) with the noise caveat.

9. **Acting on 2026 in-progress ratings with <80 TBF.** Sample-thin — flag in output.

10. **Recommending an add without `/roster-verify` and `get_all_teams()` ownership check.** Same rule as SP.

---

## When NOT to use

- Volume / FP forecasting → use `data/outputs/xfp_rprs2_projections.csv` (rprs2 model)
- Single-game leverage / save-chance decisions → use `live_monitor`
- SP profiling → use `/sp-archetype`
- Hitter profiling → use `/hitter-archetype`

---

## Integration with other skills

| Skill | Relationship |
|---|---|
| `/fa-monitor` | Upstream — surfaces RP role-change / closer-opportunity signals; this skill profiles them by archetype + comps. |
| `/fa-replacement-pool` | Companion — pool scan ranks by rprs2; this skill adds the process lens to the top candidates. |
| `/fa-pickup-deep-dive` | Companion — adds 20-80 ratings + comp lens to a single-RP pickup decision. |
| `/league-deep-audit` | Upstream — full league audit; archetype label can be a column for RP rows. |
| `/sp-archetype` | Sibling — same methodology for SPs. Do NOT cross-reference comps across roles. |
| `/roster-verify` | Pre-condition — verify ownership before any add recommendation. |

---

## Example session

User: "Profile Mason Miller — is the closer job at risk?"

```
Mode: /rp-archetype Mason Miller

Output:

Mason Miller 2026 (age 27, PEAK) — role: closer
  S=72 C=54 B=46 (velo=78)
  Sub-domains: SwM=74 CS=57 Velo=78 | WalkAvoid=54 | GB=44 Bulk=48
  Components: K%=37.2, BB%=10.1, SwStr%=18.4, CSW%=33.1, velo=100.8 mph
              GB%=39.5, Barrel%=8.2, HardHit%=38.1, xwOBAcon=.340, IP/app=1.02

  Label: PURE_STUFF_RP / WHIFF_LED / POWER / PEAK / EDGE
  Tags: CLOSER=True, HIGH_LEVERAGE=True, MULTI_INNING_BULK=False (12 SV, 1 HLD YTD)
  Boundary: distance=2 → EDGE; CONTROL=54 is 6 points from flipping (NEAR_EDGE)
            STUFF=72 is well inside PLUS

  Age-conditioned stickiness: PURE_STUFF_RP PEAK retention 35% (n=43 hist)
  T+1 / T+2 projection: 4.18 / 4.05 fp/g (model R²=0.25 — directional only)

  Career arc:
    2024 (age 25) PURE_STUFF_RP [S=78 C=46 B=48] NEAR_EDGE, CLOSER=True, fp/g=4.95
    2025 (age 26) PURE_STUFF_RP [S=75 C=50 B=47] NEAR_EDGE, CLOSER=True, fp/g=4.41
    2026 (age 27) PURE_STUFF_RP [S=72 C=54 B=46] EDGE,      CLOSER=True, fp/g=4.18

  Verdict: Stuff backbone (S=72, SwStr=18.4%) is the durable signal — three years
  of PURE_STUFF_RP labels with S in [72, 78]. CONTROL trending UP year-over-year
  (46→50→54) is the breakout angle but archetype is still EDGE (label could
  upgrade to LATE_INNING_STUFF_CTRL if C hits 60). CLOSER tag held all 3 years —
  durable role-fit. NOT a sell-high on process; rprs2 governs the fantasy call.
```

---

## Note on data coverage

- **20-80 ratings + archetype + role tags + comps**: 2018-2026 (no 2020 — COVID year excluded)
- **2026 is in-progress** — RPs with TBF < 80 will have noisy ratings; flag in output
- **Stickiness JSON `by_age_tier` may be sparse** for rare archetypes (e.g., ELITE_CLOSER_STUFF n=8 total). Fall back to overall retention when a tier sample is < 5.
- **gmLI / leverage_tier**: 2018-2026 ex-2020 at 99.95% join coverage. Sourced from FanGraphs relief leaderboard via `pull_fg_rp_leverage.py` → `data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv`. The scrape is browser-driven (undetected-chromedriver) and must be refreshed manually — it is NOT wired into the daily `refresh_dashboards.py` chain. Re-run when usage patterns shift (e.g. mid-season closer changes).

## v2 unlocks (what's still missing)

The audit (RP_DATA_AUDIT.md) called out four FG signals that would expand the RP archetype kit. Status:

| Signal | v1 status | Notes |
|---|---|---|
| **gmLI** | ✅ **shipped 2026-05-29** | Drives `leverage_tier`. |
| **pLI / exLI / inLI** | ✅ display columns shipped | Per-PA, exit, and inherited leverage indices. |
| **WPA / WPA-LI / RE24 / REW** | ✅ display columns shipped | Cumulative leverage-weighted outcome — useful but season-counting, not per-outing. |
| **Shutdowns / Meltdowns** | ✅ display columns shipped | High-leverage outing outcome tally. |
| **IR / IR-S% (inherited stranded)** | ❌ **NOT available** | FG's combined-stats JSON endpoint (`type=8`) does NOT expose these. Exhaustive key dump 2026-05-29: 544 keys checked, no IR or strand-rate columns. Would need a different FG endpoint (splits tool?) or Baseball-Reference scrape to fire the FIREMAN archetype tag. Stub column exists (`FIREMAN=False`) for forward compatibility. |
