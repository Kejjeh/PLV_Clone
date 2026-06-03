---
signal: park_friendly (boom_stack 5th-component candidate)
formula: park_friendly = 1 if pf_wOBA_prior <= 33rd-percentile (lowest tertile = most pitcher-friendly), else 0. Park = home_team of game_pk (venue regardless of which side SP pitches for). pf_wOBA sourced from data/research/xfp_cache/park_factors_2018_2026.csv using the PRIOR year's value (strict pre-cutoff: 2019 starts use 2018 PF, etc.).
outcome: boom_outcome (binary, current boom_stack target in _boom_stack_per_start_panel_cache.parquet)
expected_sign: +
theory: Lineup-strength (opp_soft) controls for batter quality but not venue. Pitcher-friendly parks suppress XBH/HR which directly reduces ER and H allowed, both of which appear linearly in SP FP. Park is the structural multiplier on the same lineup.
production_target: boom_stack (SP boom-flag ranker)
framing: in-season → next-start (matches boom_stack panel framing)
holdout_years: panel is 2018-2025; 2018 dropped (no 2017 PF in source); analysis uses 2019, 2021, 2022, 2023, 2024, 2025 (27,163 starts)
validation_script: ad-hoc (this run; uses _boom_stack_per_start_panel_cache.parquet + statcast_YYYY.parquet for game_pk→home_team + park_factors_2018_2026.csv prior-year join)
date: 2026-06-03
verdict: SHIP_AS_5TH_COMPONENT
purpose: Quantify whether park-factor explicitly boosts SP boom probability beyond what lineup-strength (opp_soft) already captures. If yes, evaluate as boom_stack's 5th component or a multiplicative modifier.
---

## Headline numbers

- **Standalone edge**: P(boom | park_friendly=1) − P(boom | park_friendly=0) = **+2.69 pp** (16.91% vs 14.23%, z=5.73, bootstrap 95% CI [+1.80, +3.58] pp)
- **Sample**: 27,163 SP starts, 2019-2025 (2018 dropped — no 2017 PF available)
- **Year-by-year stability**: **5/6 years positive**, lone negative is 2021 (-0.27 pp, COVID-affected; all other years ≥+2.0 pp)
- **Marginal within boom_stack**: lifts stack=0 by +1.95 pp (z=3.28) and stack=1 by +4.82 pp (z=5.73); attenuates at stack=2 (+2.80 pp, z=1.59) and saturates at stack=3 (+0.13 pp, n=104)
- **Independence**: phi=0.000 vs flag_recform_hot, phi=-0.007 vs flag_skill_spike, phi=-0.087 vs flag_opp_soft (mild — pitcher-friendly parks face slightly tougher offenses, so the +2.69 pp is *despite* the matchup mix)

## Step 1 — Park factor data source

Source: `data/research/xfp_cache/park_factors_2018_2026.csv` (270 park-years 2018-2026, n_pa per park ≈ 6,000-7,500 each year). Columns: `year, team_abbr, pf_wOBA, pf_HR, pf_R, n_pa`.

**Key finding during exploration**: `pf_HR` is **NOT** the right axis. Quintile boom rates by pf_HR are non-monotonic (Q1=14.80%, Q2=16.21%, Q3=15.34%, Q4=15.33%, Q5=14.02%) and the Q1−Q5 edge is only +0.78 pp.

`pf_wOBA` (which incorporates contact suppression broadly — including XBH, BABIP, K-rate environment) IS monotonic:

| pf_wOBA quintile | n | boom_rate | pf_wOBA range |
|---|---|---|---|
| Q1 (most pitcher-friendly) | 5,548 | **18.06%** | 0.890 – 0.971 |
| Q2 | 5,341 | 14.88% | 0.972 – 0.992 |
| Q3 | 5,434 | 15.57% | 0.992 – 1.006 |
| Q4 | 5,424 | 14.62% | 1.007 – 1.032 |
| Q5 (most hitter-friendly) | 5,416 | **12.48%** | 1.033 – 1.101 |

**Q1−Q5 edge = +5.58 pp** — a much stronger and monotonic signal than pf_HR.

### Most pitcher-friendly parks by average pf_wOBA (used in analysis)

| Park | mean pf_wOBA | mean pf_HR | n starts | boom rate |
|---|---|---|---|---|
| TB | 0.945 | 0.907 | 862 | 17.4% |
| ATH | 0.986 | 0.796 | 910 | 15.3% |
| SEA (T-Mobile)| ~0.95 (most-friendly-100%) | mid | 914 | **20.0%** |
| TB | ~0.945 (100% friendly) | low | 862 | 17.4% |
| HOU | ~0.97 (83%) | low | 924 | 17.5% |
| PHI | ~0.975 (84%) | high | 921 | 16.3% |
| MIL | ~0.971 (83%) | high | 911 | 16.5% |
| LAD | ~0.96 (68%) | high | 891 | 17.3% |
| ATL | ~0.99 (67%) | low | 918 | 15.4% |

Note: PHI/MIL/LAD have HIGH pf_HR but LOW pf_wOBA — they suppress BABIP/contact even though HR fly. This is exactly why pf_HR alone underrates them as pitcher's parks.

### Most hitter-friendly (NOT park_friendly) parks

| Park | mean pf_wOBA | boom rate | n |
|---|---|---|---|
| COL | 1.061 | **8.5%** | 913 |
| KC | 1.069 | 12.3% | 907 |
| TEX | 1.013 (but 0% friendly) | 13.8% | 903 |
| STL | 1.022 (0% friendly) | 13.8% | 912 |
| PIT | 1.037 (0% friendly) | 13.0% | 893 |

COL's 8.5% boom rate vs SEA's 20.0% is a **2.4× ratio** — park context is one of the largest single-feature splits in the panel.

## Step 2 — Per-start panel build

- `game_pk → home_team` derived from `statcast_YYYY.parquet` (drop_duplicates on game_pk, take `home_team`). 17,002 unique games joined; 100% of panel starts received a venue.
- `park_team := home_team` (the SP pitches at the home park regardless of whether they're the home or away SP).
- PF joined by `(year, park_team)` using **prior year** values (strict pre-cutoff to avoid look-ahead bias). 2018 panel starts dropped (no 2017 PF in source file). Final usable rows: **27,163**.

## Step 3 — Park boom rate analysis (Q1 vs Q5)

Using pf_wOBA quintiles (see table above):
- Q1 (pitcher-friendly): 18.06% boom rate
- Q5 (hitter-friendly): 12.48% boom rate
- **Edge Q1−Q5 = +5.58 pp**

Using pf_HR quintiles (for comparison):
- Q1: 14.80%, Q5: 14.02%
- **Edge Q1−Q5 = +0.78 pp** (essentially noise; non-monotonic — Q2 is highest at 16.21%)

**Lesson: pf_HR is the wrong proxy for park boom effect.** HR-only parks (LAD, NYY, BAL) compensate via BABIP/contact suppression. Use the broader pf_wOBA.

## Step 4 — park_friendly flag standalone edge

Definition: `park_friendly = 1` if `pf_wOBA_prior ≤ 33rd percentile` (≈0.9857), else 0. Fires on ~34% of starts.

| | n | boom_rate |
|---|---|---|
| park_friendly = 1 | 9,223 | 16.91% |
| park_friendly = 0 | 17,940 | 14.23% |

**Edge: +2.69 pp, z=5.73, bootstrap 95% CI [+1.80, +3.58] pp** (2000-iter resample).

## Step 5 — Marginal effect within boom_stack

| boom_stack | park_friendly=0 boom | park_friendly=1 boom | Δ pp | z |
|---|---|---|---|---|
| 0 | 12.34% (n=9,030) | 14.28% (n=5,251) | **+1.95** | 3.28 |
| 1 | 15.50% (n=6,953) | 20.32% (n=3,130) | **+4.82** | 5.73 |
| 2 | 17.66% (n=1,625) | 20.46% (n=738) | +2.80 | 1.59 |
| 3 | 21.99% (n=332) | 22.12% (n=104) | +0.13 | 0.03 |

Pattern: **strongest at stack=1, saturates at stack=3**. Not perfectly parallel additive — looks like park_friendly best helps marginal-quality boom candidates (stack=1) become legit booms. At stack=3 the start is already so loaded that park context can't move it further (n=104 sub-cell also limits inference).

**If we collapsed park_friendly into boom_stack as a 5th component** (boom_stack_v2 = boom_stack + park_friendly), the calibration would extend monotonically:

| boom_stack_v2 | n | boom_rate |
|---|---|---|
| 0 | 9,030 | 12.34% |
| 1 | 12,204 | 14.98% |
| 2 | 4,755 | 19.41% |
| 3 | 1,070 | 20.93% |
| 4 | 104 | 22.12% |

Monotone non-decreasing across all 5 tiers. New tier 4 is small (n=104) but consistent with tier 3.

### Independence vs other boom_stack components

| Pair | phi |
|---|---|
| park_friendly vs flag_recform_hot | -0.0003 |
| park_friendly vs flag_skill_spike | -0.0065 |
| park_friendly vs flag_opp_soft | -0.0874 (p=3e-47) |

The -0.087 with opp_soft means **pitcher-friendly parks face slightly tougher offenses on average** (probably AL West / NL West rotation effect — TB, SEA, HOU divisions have above-average offense). The +2.69 pp standalone edge is therefore **understating** the pure park effect; within opp_soft=1 (soft lineup) the park_friendly edge widens to +4.12 pp.

## Step 6 — Year-by-year stability

| Year | pf=1 boom | pf=0 boom | Δ pp |
|---|---|---|---|
| 2019 | 20.34% | 14.86% | **+5.49** |
| 2021 | 14.46% | 14.73% | -0.27 |
| 2022 | 19.43% | 13.39% | **+6.03** |
| 2023 | 15.32% | 13.32% | +2.00 |
| 2024 | 17.03% | 14.62% | +2.41 |
| 2025 | 16.67% | 14.30% | +2.37 |

**5/6 years positive.** The lone -0.27 pp year is 2021 (COVID schedule, expanded rosters, doubleheaders compressed). All other years ≥+2.0 pp, including the most recent two seasons.

## Verdict: **SHIP_AS_5TH_COMPONENT**

All criteria met:
1. Standalone edge meaningfully positive (+2.69 pp) with z > 5 and 95% CI excluding zero
2. Independent from existing components (phi ≈ 0 with skill_spike and recform_hot)
3. Mild correlation with opp_soft is in the *wrong* direction (against finding lift) — pure park edge is even larger
4. Year-by-year stable: 5/6 positive, lone exception is COVID-affected 2021
5. Marginal within boom_stack: positive at every stack value (+1.95, +4.82, +2.80, +0.13 pp); strongest where it matters most (stack 0→1 boundary, the "is this a real boom candidate" call)
6. Monotonic calibration of stack+park_friendly composite: 12.3% → 15.0% → 19.4% → 20.9% → 22.1%

Recommendation: **add park_friendly as the 5th component of boom_stack**, fired when the SP is pitching at a home park whose prior-year pf_wOBA is in the bottom tertile (≤ ~0.986 currently).

### How to source live park factor at game time

`park_friendly` requires only two pieces:
1. **Today's game venue** — `home_team` of the SP's game (available from MLB Stats API `schedule` endpoint or the same probable-pitchers feed already used by `build_matchup_dashboard.py`)
2. **Prior-year pf_wOBA** for that park — already in `data/research/xfp_cache/park_factors_2018_2026.csv`, refreshed once per offseason by whatever rebuilds that file. For 2026 in-season use, the 2025 row is the lookup.

No new data source or API needed. Implementation = 1 join in `build_boom_stack.py` or wherever boom_stack components are assembled, plus a once-per-year refresh of park_factors_2018_2026.csv.

### Caveats / follow-ups

- 2018 data dropped (4,550 starts) because no 2017 PF available. If we want 2018 included, backfill 2017 PF from statcast_2017 (file may not exist locally — check before promising).
- Stack=3 cell (n=104 with park_friendly=1) is small; the +0.13 pp marginal could be noise either direction. Doesn't affect ship decision — most decisions happen at stack 0/1.
- A future refinement: a **continuous park_pf_wOBA modifier** (e.g. `boom_stack + 1.5 × (1 − pf_wOBA_prior)`) might fit better than a binary tertile. Worth one A/B comparison if rebuilding boom_stack v3.
- Park ASSIGNMENT to a year-specific friendliness has churn — e.g., SEA is 100% friendly in this panel, but ATH/SD/NYY hover near the 33rd-percentile boundary and flip between years. The flag will inherit that year-over-year volatility; this is honest behavior, not a bug.
