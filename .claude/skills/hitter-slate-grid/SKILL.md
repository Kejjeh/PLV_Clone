---
name: hitter-slate-grid
description: Multi-day hitter FA-pickup decision board joining ALL 14 hitter model layers — Blended xFP (Phase 1 production scorer with 95% bootstrap CI), rh3 rank + per_pa/per_game + expected_total_fp_remaining, live_marginal + value_tier (Phase 2.5 same-position FA-pool-relative delta C/1B/2B/3B/SS/OF/DH with bucket-scaled tier cuts), Triangulate verdict + reason_tag + confidence (BUY/HOLD/CAUTION/FADE/MIXED for hitters), Sustainability bucket (LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS) with BUY-LOW/SELL-HIGH divergence flag (CAVEAT — hitter BUY-LOW REJECTED in PR 8 backtest 705defc at pooled −0.069 FP/PA with 95% CI [−0.114, −0.023]; divergence shown for diagnosis only, NOT as additive signal), xwOBA L21d vs 2025 baseline diagnostic (gap ±0.020 = skill holding, < −0.060 = real decline), xwOBACON year-over-year trajectory (RISING/STABLE/DECLINING distinguishes valid recovery templates from structural decline), Hitter archetype master (Contact/Power/Discipline + SB overlay, 27-cell C/P/D matrix, age_tier PRE_PEAK/PEAK/POST_PEAK, boundary_tier SOLID/EDGE), archetype T+1 projection + 5 historical comps with comp-density flag, Hitter boom_stack 0-4 score (skill_spike_hitter + recform_hot_hitter + opp_soft_hitter + lineup_amp_hitter components) + boom%/bust%/E[FP] from validated tier-aware lookup, Process panel composite (PR 8 L30/STD/PriorYr 9-marker decomposition with direction-adjusted z-score and level_pct), PL Top 150, lineup spot + confirmation status from MLB Stats API, park factor + vs LHP/RHP splits, positional eligibility for roster fit. Tags ownership (MINE / opp team name / FA) via league.teams roster walk. Includes mandatory KNOWN_COLLISIONS check for same-name players (canonical Max Muncy LAD 3B vs ATH C). Renders a positional grid with FA highlighted, then synthesizes a sustainability-aware boom-aware top-FA recommendation. Use when the user asks "rundown on all FA hitters", "best hitter pickups", "show me the FA hitter board", "use all hitting models", "FA pickup deep scan for hitters", or wants the multi-lens hitter decision surface across positions. Engine pattern — ESPN free_agents(size=2000) + Connelly-Early verification via league.teams + rh3/blend/hitter_master/process_panel/boom_stack JSON joins on MLBAM batter_id (NOT name — Max Muncy LAD vs ATH bug 2026-05-25 silently broke a career percentile lookup) + on-demand Sustainability/Triangulate/xwOBA-L21d/xwOBACON-YoY for shortlisted FAs.
---

# hitter-slate-grid

You are rendering the **full hitter FA-pickup decision board** — every
above-threshold available hitter across positions, joined with all 14
hitter model lenses, with ownership tagged and the model+sustainability+
boom-aware synthesis applied. This is the parallel of `/sp-slate-grid`
for hitters.

## What's different from SPs

Hitters play **daily**, so the single-game vs RoS framework distinction
is less sharp than for SPs (Cameron-style case from 6/7/26 doesn't quite
map — you start hitters every game, not once a week). The relevant
question for hitters is **"who's the best ADD given my position needs
and the FA pool depth"**, not "who fills my cap." Specific differences:

| Concern | SP | Hitter |
|---|---|---|
| Decision horizon | Single start (cap fill) | RoS hold (~30+ games) |
| Daily lineup risk | Always starts | Bench / OFF / pinch-hit risk |
| Same-name collision | Rare (Logan Allen) | **Frequent** (Max Muncy LAD/ATH, Luis García Jr. WSH/HOU/PHI, Aaron Judge…) |
| Positional fit | Boolean (SP/RP) | Multi-dim (C/1B/2B/3B/SS/OF/UTIL eligibility) |
| Park factor | Single game, weakly weighted | Daily for next ~7 games, materially impacts xwOBA |
| Triangulate verdict source | rp3 + archetype + PL | rh3 + archetype + PL |

## Trigger phrases

"rundown on all FA hitters", "best hitter pickups", "FA hitter board",
"use all hitting models", "show me FA hitters across the slate",
"pickup deep scan for hitters", "hitter slate grid",
"FA hitter decision board", "compare FA hitters across all lenses".

## What this skill produces (14 layers, ranked by empirical importance below)

For each above-threshold FA hitter (plus your roster's hitters for the
drop-target comparison):

| Layer | What it adds | Source | Cost |
|---|---|---|---|
| **MLB API lineup** | Confirmed / projected starter, batting order spot, vs LHP/RHP | `https://statsapi.mlb.com/api/v1/schedule?date=DATE&hydrate=lineups,team` | net |
| **Ownership** | MINE / `<opp team name>` / FA | `league.teams` roster walk + KNOWN_COLLISIONS guard | API |
| **Blended xFP (H)** | Production headline FP/PA + bootstrap CI + confidence_tier | `data/outputs/live_blend_xfp_latest.csv` filter `player_type='H'`, keyed on `mlbam_id` | file |
| **rh3** | Rank, per_pa, per_game, expected_total_fp_remaining, replacement_delta, signal, slump_pct_rank | `data/outputs/xfp_rh3_projections.csv` keyed on `batter` (MLBAM) | file |
| **live_marginal + value_tier (H)** | Phase 2.5 same-position FA-pool-relative delta (C/1B/2B/3B/SS/OF/DH bucket). Tier cuts H-bucket-scaled: ±100/±40 (vs SP's ±40/±15). Tiers: OWN_THE_ROLE / COMFORTABLE_HOLD / REPLACEABLE / DOWNGRADE / ACTIVE_LOSS | `scripts/xfp/lib/blend_score.py::_compute_live_marginal_h` (Phase 2.5). Snapshot: `data/research/fa_snapshots/fa_pool_H_latest.parquet` | compute |
| **Triangulate verdict (H)** | Synthesized BUY/HOLD/CAUTION/FADE/MIXED + reason_tag + confidence (4-lens vote: PL150 + rh3 + archetype + traj/T+1) | `scripts/xfp/lib/triangulate_core.py::triangulate_player(name)` auto-detects bucket='H'. **Compute only for shortlisted top-15 FAs** by Blended xFP | compute |
| **Sustainability bucket (H)** | LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS confidence layer on rh3 + BUY-LOW/SELL-HIGH divergence flag (>0.4 FP/g gap). **CRITICAL CAVEAT**: hitter BUY-LOW REJECTED in PR 8 backtest (commit 705defc, pooled mean residual −0.069 FP/PA, 95% CI [−0.114, −0.023] fully below zero, both 2024 and 2025 negative). Display the divergence flag for diagnosis only, do NOT treat as actionable signal | `scripts/xfp/hitter_sustainability.py::classify(rows)` | compute |
| **xwOBA L21d vs 2025 diagnostic** | Single most useful luck-vs-skill diagnostic per memory `reference_xwoba_l21d_vs_2025_diagnostic.md`. Gap of ±0.020 = skill holding; gap of < −0.060 = real decline; intermediate = mixed | Compute directly from `data/research/xfp_cache/statcast_2025.parquet` and `statcast_2026.parquet` over a [as_of−21d, as_of] window for L21d | compute |
| **xwOBACON YoY trajectory** | RISING / STABLE / DECLINING across 2022→2026. Distinguishes "valid prior-trough recovery template" (xwOBACON stable across years) from "structural decline where recovery ceiling is lower" (declining each year) | Aggregate per-year xwOBACON from `statcast_{yr}.parquet` for years in {2022, 2023, 2024, 2025, 2026}; compute the per-year delta and label | compute |
| **Hitter archetype** | 20-80 ratings on Contact / Power / Discipline + SB overlay; archetype label (27-cell C/P/D matrix); age_tier (PRE_PEAK ≤25 / PEAK 26-30 / POST_PEAK 31+); boundary_tier (SOLID / NEAR_EDGE / EDGE) | `data/research/hitter_ratings_master.csv` keyed on `batter` (MLBAM), latest year row | file |
| **Archetype T+1 + 5 historical comps** | T+1 fp_per_pa + 5 nearest-neighbor historical comps (age ±3 yrs, Euclidean over CONTACT/POWER/DISCIPLINE) with T+1 outcomes. Comp verdict: SUPPORTS_CONSIDER / SUPPORTS_SKIP / NEUTRAL | Same `hitter_ratings_master.csv` for the panel; T+1 comp matching is computed on demand | compute |
| **Hitter boom_stack (4 components)** | Live score 0-4: skill_spike_hitter / recform_hot_hitter / opp_soft_hitter / lineup_amp_hitter. Plus boom%/bust%/E[FP] from validated tier-aware lookup. Per-stack boom% climbs 23.9% → 30.6% across stack 0-3 (n=245k starter-games 2018-2025, year-stable) | `data/outputs/hitter_boom_stack_<DATE>.json` keyed on `batter_id` | file |
| **Process panel composite (PR 8)** | L30/STD/PriorYr decomposition of 9 markers (avg_ev / ev90 / hard_hit_pct / barrel_pct / xwoba_on_contact / k_pct / bb_pct / chase_pct / sweet_spot_pct) with direction-adjusted z and level_pct | `data/outputs/hitter_process_panel.csv` keyed on `batter` (MLBAM) | file |
| **PL Top 150** | Pitcher List weekly hitter rank | `data/research/pl_cache/pl_hitters_top150.json` | file |
| **Lineup spot + park + vs LHP/RHP** | Today's batting-order spot (if confirmed) + park factor (run wOBA) + opposing-SP handedness with the batter's career split | MLB API hydrate + cached park factors + Statcast splits | net |
| **Same-name collision check** | KNOWN_COLLISIONS gate via `plv_clone.utils.name_match.resolve_batter_id(name, team=…, position=…)` — REQUIRED before any dict-keyed lookup | `src/plv_clone/utils/name_match.py::KNOWN_COLLISIONS` (Max Muncy LAD 3B vs ATH C; Luis García Jr. WSH/HOU/PHI; Logan Allen LHP-twins for pitchers) | file |

**Performance budget:** ~9 file joins (cheap, <2s for ~500 FAs). On-demand
compute layers (Triangulate / Sustainability / xwOBA-L21d / xwOBACON-YoY)
only for **top-15 FAs by Blended xFP**. Total runtime ~30-90s depending
on Statcast parquet size.

---

## Step 1 — Pull all FA hitters + verify Connelly-Early style

```python
from app.espn_connector import _get_league
league = _get_league()

all_fas = league.free_agents(size=2000)  # MANDATORY — per-position cap silently truncates
h_fas = [p for p in all_fas if 'UTIL' in (p.eligibleSlots or [])
         or any(s in (p.eligibleSlots or []) for s in ['C','1B','2B','3B','SS','OF','DH'])]

# Connelly-Early verification: subtract anyone rostered on another team
rostered = {pl.name.lower() for t in league.teams for pl in t.roster}
h_fas = [p for p in h_fas if p.name.lower() not in rostered]
```

**Anti-pattern guard:** NEVER use `get_all_teams()` for the ownership
check — it returns strings, not Team objects with `.roster`. The
ownership map MUST come from `league.teams[*].roster`.

## Step 2 — Resolve MLBAM with KNOWN_COLLISIONS

```python
from plv_clone.utils.name_match import resolve_batter_id, KNOWN_COLLISIONS

def safe_mlbam(name, team=None, pos=None):
    """ALWAYS use this. NEVER do _norm(name) -> dict[mlbam_id]."""
    if name in KNOWN_COLLISIONS:
        # Forces caller to disambiguate via team or position
        return resolve_batter_id(name, team=team, position=pos)
    return resolve_batter_id(name)
```

Canonical bug (2026-05-25): a career-percentile analysis built a
`dict[_norm(name)] = batter_id` map. Max Muncy LAD (571970, 3B) and
ATH (691777, C) collided on the normalized key — half the lookups
silently returned the wrong player's data. Skill body MUST use
`resolve_batter_id` for every name-keyed lookup.

## Step 3 — Join all 14 model layers on MLBAM batter_id

```python
import pandas as pd, json, glob

# Layer 1: rh3 — keyed on `batter` = MLBAM
rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rh3_lookup = rh3.set_index('batter')[[
    'rank','xfp_rh3_per_pa','xfp_rh3_per_game','expected_total_fp_remaining',
    'replacement_delta','signal','pa_to','pa_last21','recency_form_gap',
    'slump_pct_rank','slump_bounce_pct','slump_next_rate','slump_delta',
    'arche_overall_prior','slope_3yr_prior','traj_career_low_prior',
]].to_dict('index')

# Layer 2: Blended xFP (H rows only)
blend = pd.read_csv('data/outputs/live_blend_xfp_latest.csv')
blend = blend[blend['player_type']=='H']
blend_lookup = blend.set_index('mlbam_id')[[
    'live_blend_xfp','ci_lower','ci_upper','confidence_tier'
]].to_dict('index')

# Layer 3: Hitter archetype master
arch = pd.read_csv('data/research/hitter_ratings_master.csv')
arch = arch[arch['year']==arch['year'].max()].drop_duplicates('batter', keep='first')
arch_lookup = arch.set_index('batter')[[
    'archetype','CONTACT','POWER','DISCIPLINE','SB',
    'age','age_tier','boundary_tier','t1_fp_projection','fp_per_pa',
    'contact_subtype','power_subtype','discipline_subtype','sb_tier',
]].to_dict('index')

# Layer 4: Process panel composite (PR 8)
proc = pd.read_csv('data/outputs/hitter_process_panel.csv')
proc_lookup = proc.set_index('batter')[[
    'composite','TREND_z','BASE_z','level_pct'
]].to_dict('index')

# Layer 5: Hitter boom_stack (today's JSON)
bs_files = sorted(glob.glob('data/outputs/hitter_boom_stack_*.json'))
with open(bs_files[-1]) as f:
    bs_data = json.load(f)
bs_lookup = {c['batter_id']: c for c in bs_data['candidates']}

# Layer 6: PL Top 150 — keyed on name (resolve to MLBAM via name_match)
with open('data/research/pl_cache/pl_hitters_top150.json') as f:
    pl_top = json.load(f).get('ranks', {})
```

## Step 4 — Compute on-demand layers for top-15 FAs by Blended xFP

```python
from scripts.xfp.lib.blend_score import _compute_live_marginal_h
from scripts.xfp.lib.triangulate_core import triangulate_player
from scripts.xfp.hitter_sustainability import classify as sustain_classify_h
import duckdb
from datetime import date, timedelta

def deep_dive_h(mlbam_id, name, team, position, target_ros):
    # live_marginal — same-position H bucket comparison
    live_marg = _compute_live_marginal_h(mlbam_id, position, target_ros)

    # Triangulate
    tri = triangulate_player(name)

    # Sustainability bucket + divergence (note BUY-LOW caveat)
    sust = sustain_classify_h(_load_sustain_rows_h(mlbam_id))

    # xwOBA L21d vs 2025 baseline (the diagnostic from memory)
    as_of = date.today()
    L21_start = (as_of - timedelta(days=21)).isoformat()
    L21_xwoba = duckdb.query(f"""
        SELECT AVG(estimated_woba_using_speedangle)
        FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
        WHERE batter = {mlbam_id}
          AND game_date >= '{L21_start}'
          AND events IS NOT NULL AND events != ''
    """).fetchone()[0]
    baseline_xwoba = duckdb.query(f"""
        SELECT AVG(estimated_woba_using_speedangle)
        FROM read_parquet('data/research/xfp_cache/statcast_2025.parquet')
        WHERE batter = {mlbam_id} AND events IS NOT NULL AND events != ''
    """).fetchone()[0]
    gap = (L21_xwoba or 0) - (baseline_xwoba or 0)
    xwoba_verdict = (
        'SKILL_HOLDING' if abs(gap) <= 0.020
        else 'REAL_DECLINE' if gap < -0.060
        else 'MIXED'
    )

    # xwOBACON YoY trajectory (2022 -> 2026)
    yoy = []
    for yr in (2022, 2023, 2024, 2025, 2026):
        if yr == 2020: continue  # COVID exclusion
        q = duckdb.query(f"""
            SELECT AVG(estimated_woba_using_speedangle), COUNT(*)
            FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
            WHERE batter = {mlbam_id}
              AND events IS NOT NULL AND events != ''
              AND launch_speed IS NOT NULL
        """).fetchone()
        if q[1] >= 30:  # min sample
            yoy.append((yr, q[0]))
    # Classify as RISING/STABLE/DECLINING per memory
    # `reference_xwoba_l21d_vs_2025_diagnostic` rule
    if len(yoy) >= 3:
        deltas = [yoy[i+1][1] - yoy[i][1] for i in range(len(yoy)-1)]
        avg_delta = sum(deltas) / len(deltas)
        trajectory = 'RISING' if avg_delta > 0.010 else 'DECLINING' if avg_delta < -0.010 else 'STABLE'
    else:
        trajectory = 'INSUFFICIENT'

    return {
        'live_marginal': live_marg.get('live_marginal'),
        'live_value_tier': live_marg.get('live_value_tier'),
        'verdict': tri.get('verdict'),
        'verdict_top': tri.get('verdict_top'),
        'reason_tag': tri.get('reason_tag'),
        'confidence': tri.get('confidence'),
        'sustain_bucket': sust.get('bucket'),
        'sustain_divergence_diagnostic_only': sust.get('divergence_tag'),
        'L21_xwoba': L21_xwoba,
        'baseline_xwoba_2025': baseline_xwoba,
        'L21_vs_2025_gap': gap,
        'xwoba_verdict': xwoba_verdict,
        'xwobacon_yoy_trajectory': trajectory,
    }
```

## Step 5 — Pull confirmed lineup status

```python
import requests
def lineup_card(date_str):
    """Returns {team_abbr: {batter_name: {order, status}}} for the date."""
    url = (f'https://statsapi.mlb.com/api/v1/schedule'
           f'?sportId=1&date={date_str}&hydrate=lineups,team')
    r = requests.get(url, timeout=20).json()
    out = {}
    for d in r.get('dates', []):
        for g in d.get('games', []):
            for side in ('home', 'away'):
                team = g['teams'][side]['team']['abbreviation']
                # Lineup may be in g['lineups']['homePlayers'] or game['teams'][side]
                # Confirmed status: gameStatus is "Live"/"Scheduled" + lineupPosted=True
                ...  # parse per actual API shape
    return out
```

If lineup is NOT confirmed (status=TBD), render the cell as `?` rather
than blank, so the user knows the player MIGHT not start.

## Step 6 — Render the positional grid

Group by position bucket (C / 1B / 2B / 3B / SS / OF / DH-UTIL) so the
user can scan for the position they want to fill. Within each group,
sort by Blended xFP descending.

Primary grid columns (cheap layers, every row):

`Pos | Player | Team | Own | xFP [CI] | conf | rh3 # | per_pa / per_game | Arche (C/P/D/SB) | OVERALL | ProcZ | level_pct | BoomStk | Boom%/Bust% | E[FP] | PL | Lineup`

FA shortlist deep-dive table (top 15 FAs by Blended xFP):

`Player | Verdict (conf) | Reason | live_marginal | value_tier | Sust bucket | xwOBA L21d-vs-2025 | xwOBACON YoY traj`

For FA rows, **bold** the name with `🟢 FA`; user's rows: `🟦 MINE`;
opp rows: opp team name.

---

## Empirical importance ranking (read this when synthesizing)

Below is the ranked importance of each layer for the specific decision
problem of **picking up the right FA hitter for RoS hold**. Where
empirical citations exist they're listed; where they don't, `[qual]`.

### Tier 1 — Headline projection (~50% weight)

1. **Blended xFP for hitters (H bucket)** — Production headline number.
   Phase 1 RP-card analog for hitters; per_pa + bootstrap CI +
   confidence_tier. Same caveat as SP version: refit cadence quarterly,
   5 NaN-fallback cases (pl_unavailable, slope_3yr_missing,
   archetype_missing, rookie/no-anchor, hard 2020 exclusion). When
   confidence_tier is HIGH and CI doesn't span zero, trust the point
   estimate.

2. **rh3 per_pa / per_game** — Validated single-model RoS projection.
   Hetero σ rescaled in `xfp_rh3_per_pa`. `expected_total_fp_remaining`
   is the season-long total accounting for `expected_pa_remaining`. IS a
   component of Blended xFP — use rh3 standalone only when blend is null.

### Tier 2 — FA-pickup decision modifiers (~20%)

3. **live_marginal + value_tier (H)** — Phase 2.5 same-position FA-pool
   delta with bucket-scaled tier cuts (H: ±100/±40 vs SP's ±40/±15).
   Compares your target vs the best FA at the SAME position bucket
   (C/1B/2B/3B/SS/OF/DH). Built on Blended xFP so it inherits headline
   accuracy. **The cleanest "is this FA better than my current player
   at this position" answer.**

4. **Hitter boom_stack + boom%/bust%/E[FP]** — Validated tier-aware boom
   prediction. Per-stack boom% climbs **23.9% → 30.6%** across stack
   0-3 (n=245k starter-games 2018-2025, year-stable, ECE good). Stack=4
   extrapolated to ~34% from heatmap + team-day anchors.
   Components: skill_spike_hitter / recform_hot_hitter / opp_soft_hitter
   / lineup_amp_hitter (the 4th component shipped 2026-06-03, +2.1 pp
   within-stratum, +14.2 pp team-level, 7/7 years positive). Stack=3
   still busts 37.5% — distribution shift, not floor.

### Tier 3 — Sustainability / inflection (~5-15% each, compounds with Tier 2)

5. **xwOBA L21d vs 2025 baseline gap** — Per memory
   `reference_xwoba_l21d_vs_2025_diagnostic.md`, this is the **single
   most useful luck-vs-skill diagnostic for hitters**. Required
   pre-check before any drop/add recommendation:
   - Gap of `±0.020` → skill holding (recent = expected)
   - Gap of `< −0.060` → real decline (not luck — actual skill drop)
   - Intermediate → mixed; demand confirmation from another lens
   Cited rule in the project memory; do NOT ship a drop/add
   recommendation without surfacing this gap.

6. **xwOBACON year-over-year trajectory** — RISING / STABLE / DECLINING
   across 2022→2026 (skip 2020). Distinguishes:
   - RISING → breakout is continuation of multi-year skill trajectory;
     **highest sustainability**
   - STABLE → recent gain is real but new; watch for regression to
     stable baseline (moderate sustainability)
   - DECLINING → contact-quality platform is falling; any xwOBA
     "breakout" is almost certainly outcomes (BABIP hot, HR landing).
     **Low sustainability — even valid prior-trough recoveries hit a
     lower ceiling**
   Per memory `reference_xwoba_l21d_vs_2025_diagnostic.md`: the YoY
   trajectory determines whether prior slump/recovery patterns are
   valid templates (canonical: Trea Turner pattern = declining =
   recovery ceiling is lower than prior troughs).

7. **Sustainability bucket (LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS)** —
   Confidence layer on rh3 from the 9-marker Statcast skill decomp.
   **⚠️ CRITICAL CAVEAT**: the **BUY-LOW divergence flag (the
   actionable output of the sustainability bucket) was REJECTED** in
   the PR 8 backtest (commit `705defc`, 2026-06-06):
   - Pooled n=71 BUY-LOW candidates, **mean residual −0.069 FP/PA**
   - 95% CI [−0.114, −0.023] **fully below zero**
   - **Both 2024 and 2025 negative** — no sign flip, signal fires the
     OPPOSITE direction. High-process + low-model hitters
     **underperform** rh3 over the next 30-60d by ~0.07 FP/PA.
   - Production CSV ships **WITHOUT** `buylow_flag` per plan v11
     Decision 12 (the `_assert_no_buylow` regression guard enforces this)
   **What you DO use the bucket for**: diagnosis ("why is this player's
   per_pa moving"). What you DO NOT use it for: as additive lift over
   Blended xFP. When the sustainability bucket says BUY-LOW, the
   correct response is **skepticism** — the rh3 ranker is probably
   correctly de-rating these candidates and BUY-LOW is the trap.

### Tier 4 — Process / archetype (~5-10% each)

8. **Hitter archetype (Contact / Power / Discipline + SB overlay)** —
   3,485 batter-years 2015-2026, PA floor 250 (80 in-progress), age tiers
   PRE_PEAK ≤25 / PEAK 26-30 / POST_PEAK 31+ (hitters peak earlier than
   SPs). Boundary tier retention validated: **EDGE 28.5%** vs **SOLID
   56.1%** (~2× spread). For FA decisions, prefer SOLID over EDGE
   archetype rows — the model holds up better.

9. **Process panel composite (PR 8 L30/STD/PriorYr)** — Direction-
   adjusted z-score on the 9 canonical hitter markers (avg_ev, ev90,
   hard_hit_pct, barrel_pct, xwoba_on_contact, k_pct, bb_pct,
   chase_pct, sweet_spot_pct). Useful as a **secondary confirmation** of
   the boom_stack `skill_spike_hitter` component. Not backtested as a
   standalone driver. **Note**: SP version of process panel composite is
   in the same architecture but the BUY-LOW rejection is hitter-
   specific; the process panel composite itself was NOT what got
   rejected (the BUY-LOW joint flag was).

10. **Archetype T+1 + 5 historical comps** — Age-matched (±3yr)
    Euclidean over (CONTACT, POWER, DISCIPLINE). Comp verdict
    SUPPORTS_CONSIDER / SUPPORTS_SKIP / NEUTRAL via comp-density rule
    (≥4 of 5 meaningfully above/below at T+1). **Standalone lift not
    published**; use as agreement check, not as primary signal.

### Tier 5 — Synthesis / triangulate (~5%)

11. **Triangulate verdict (BUY / HOLD / CAUTION / FADE / MIXED)** —
    Synthesis of PL150 + rh3 + archetype + 4th-lens overrides.
    Calibrated against canonical case set
    (`docs/triangulate_calibration_2026.md`). Confidence = fraction of
    4 independent signals voting in agreement. Useful as a 10-second
    scan headline; not new information beyond the underlying lenses.

### Tier 6 — External benchmarks (agreement/disagreement only)

12. **PL Top 150 rank** — External benchmark with documented bias (PL
    is rate-stat / 12-team mindset; ours is BrownU points / 8-team).
    The DIVERGENCE between PL and our model is what's actionable, NOT
    the absolute PL rank. `archetype_breakout` and `model_anchored`
    rules in triangulate are gap-driven. **PL Top 150 alone is NEVER
    reason to add.**

### Tier 7 — Context / required-but-not-predictive

13. **Lineup spot + confirmation status** — Top-of-order vs 9th is a
    materially different per-PA expectation. If lineup is NOT confirmed
    (status TBD), the row is speculative; don't synthesize without
    flagging that the player might not start.

14. **Park factor + vs LHP/RHP** — Daily park (Coors lifts ~+10%,
    petCo suppresses) and the batter's career split vs the opposing SP's
    handedness. Material for a single-game pickup decision; matters
    less for a RoS hold but still informs the next 7 days.

15. **Positional eligibility** — Roster fit. A 1B-only FA is less
    valuable than a 2B/SS/IF multi-position guy because the latter can
    cover injury or bench rotation. Per memory
    `feedback_team_value_reads_must_be_cap_role_elig_aware.md`, ALWAYS
    cap-aware + role-aware + eligibility-aware.

16. **Same-name collision check (KNOWN_COLLISIONS)** — Required gate
    via `resolve_batter_id(name, team=…, position=…)`. Canonical bug:
    Max Muncy LAD 3B (571970, rh3=0.578 hold) vs ATH C (691777, rh3=0.379
    drop candidate) — identical `_norm()` keys, opposite verdicts. A
    2026-05-25 roster audit assigned the wrong projection.

### Synthesis rules

- When **Tier 1 and Tier 2 disagree** → trust Blended xFP unless boom
  layer shows a SHARP boom%/bust% sign-flip; then weight boom_stack.
- **xwOBA L21d vs 2025 gap is the gate** for any drop/add — surface it
  always before naming a swap; never ship without this check.
- **xwOBACON YoY trajectory** determines whether prior recovery
  templates apply — DECLINING trajectory means recovery ceiling lower
  than prior troughs.
- **Sustainability BUY-LOW is REJECTED** — display the flag for
  diagnosis but treat as skepticism signal, NOT additive lift. The
  divergence is more likely a Tier-1 de-rating that's correct than
  a missed-upside opportunity.
- **Tier 5 (Triangulate) is the synthesis label** — read it as the
  headline, then verify against the underlying lenses.
- **Tier 6 (PL) is the 4th-lens agreement check** — PL alone never
  drives an add.

---

## Drop-target rule (mirrors `/sp-slate-grid` v3)

**When recommending an FA pickup that requires a drop**, you MUST first
rank the user's full hitter roster by Blended xFP before naming a
drop target. The 2026-06-06 Messick failure on the SP side applies
verbatim here.

```python
# 1. Pull user's roster
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
my_hitters = roster[roster['position'].isin(['C','1B','2B','3B','SS','OF','DH'])]

# 2. Join rh3 + blend by MLBAM (resolve_batter_id, not name)
# ... build {mlbam: blended_xfp} for each hitter ...

# 3. Show side-by-side: drop.blend_xFP vs add.blend_xFP
# If drop's xFP > add's xFP, STOP and reconsider
```

Synthesis output requirement:

```
| What you give up (drop) | Blended xFP | What you gain (add) | Blended xFP |
```

---

## Anti-patterns this skill exists to prevent

- **Calling a rostered hitter "no data" because they're not in the
  daily lineup.** A hitter benched today is still fully present in
  rh3 + blend + hitter_master + process_panel + boom_stack JSON.
  Always query by MLBAM directly. (Same root cause as the Messick SP
  failure.)
- **Building `dict[_norm(name)] = batter_id` maps.** Max Muncy LAD vs
  ATH; Luis García Jr. WSH vs HOU vs PHI. ALWAYS use
  `resolve_batter_id(name, team=…, position=…)`.
- **Treating BUY-LOW divergence as an additive signal.** The PR 8
  backtest REJECTED it at the hitter level (pooled −0.069 FP/PA).
  Display the flag for diagnosis but do not treat as lift.
- **Skipping the xwOBA L21d vs 2025 check before any drop/add.** Per
  memory `reference_xwoba_l21d_vs_2025_diagnostic.md` — this is the
  required pre-check.
- **Trusting a stale PL Top 150 cache** without checking `fetched`.
  Refresh if >7d old.
- **Using `get_all_teams()` for ownership** — returns strings, not
  Team objects. Use `league.teams`.
- **Rendering tags without verifying boom_stack JSON booleans** (same
  rule as SP version — read `is_*` flags, never infer from heuristics).
- **Recommending against a "BUY-LOW" hitter purely because BUY-LOW was
  rejected.** The rejection is about ADDING based on BUY-LOW divergence
  alone; it doesn't mean BUY-LOW-flagged hitters are universally bad
  picks. Use Blended xFP + boom_stack + xwOBA L21d + xwOBACON YoY in
  combination; the BUY-LOW flag is one negative-weighted input, not a
  veto.
- **Ignoring lineup confirmation status.** A "starts every day" hitter
  who's TBD for tonight may be a manager's day-off; mark `?` and don't
  blindly project for that single game.
- **Filtering to FA only before the synthesis pass.** Opp-rostered
  hitters tell you who to fade in trade scenarios (same as the SP
  "fade my opponent's pitcher" lens).

## When NOT to use this skill

- User asked for a single named player → `/fa-pickup-deep-dive` or
  `/triangulate`.
- User wants to compare 2-6 specific hitters head-to-head →
  `/hitter-compare`.
- User wants the full league audit across all 8 teams →
  `/league-deep-audit`.
- User wants the archetype panel for one hitter →
  `/hitter-archetype profile <name>`.
- User wants peak-vs-slump career percentile → `/career-form-rank`.
- User wants the sustainability deep-dive for one hot/cold hitter →
  `/breakout-sustainability` or `/slump-or-decline`.
- User wants the FA-replacement flat ranked list with no synthesis →
  `/fa-replacement-pool`.

## Output canonical reference

When run, save the joined CSV to `C:/tmp/hitter_slate_<window>.csv` for
ad-hoc sort/filter. Save the rendered markdown to
`data/outputs/hitter_slate_grid_<date>.md` so the user can re-read
without rebuilding.

## Related

- `/sp-slate-grid` — full SP slate parallel (this skill's structural twin)
- `/fa-replacement-pool` — flat FA ranked list (no grid, no synthesis)
- `/fa-pickup-deep-dive` — single-hitter deep dive
- `/hitter-compare` — multi-hitter head-to-head
- `/hitter-archetype` — single-hitter archetype profile
- `/hitter-sustainability` — sustainability bucket on rh3 (the underlying
  layer this skill aggregates)
- `/breakout-sustainability` — sustainability deep dive
- `/career-form-rank` — career-percentile distribution
- `/slump-or-decline` — slump diagnostic
- `/league-deep-audit` — full 8-team statistical audit
- `/triangulate` — 3-lens verdict per player
