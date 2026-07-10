---
signal: ros_park_factor_weighted
formula: For each (batter, year, split_day) — batter's primary-team RoS games (game_date > cutoff_date from rolling_hitters), equal-weight mean over RoS games of the VENUE's (home team's park) lagged Savant park factor. Park factor = Savant statcast-park-factors index_wOBA / 100, 3-yr-rolling window ENDING year T-1 (key_year = T-1), single-year T-1 fallback for new-park teams (ATL 2017-18, TEX 2020-21, TOR 2020, ATH/TB 2025), neutral 1.00 if absent. Built in scripts/xfp/build_ros_park_factor.py from scripts/xfp/build_park_factors_savant.py cache.
outcome: rh3 cross_year_eval Δr on RoS FP/PA target (matches rh3 production)
expected_sign: +
theory: A hitter whose remaining schedule runs through hitter-friendly venues (Coors, GABP...) will average more FP/PA than an identical-skill hitter facing a pitcher-park-heavy slate. RH3_FEATS carries own-skill + one schedule lens (ros_opp_sp_xwoba_weighted = opposing PITCHER quality) but no venue/park exposure. Prior art: home-park-only pf_wOBA came back MARGINAL for rh3 (park_pf_wOBA_ros_2026-05-24); this is the done-right RoS-schedule-weighted version with official Savant factors and strict T-1 lagging.
production_target: rh3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_ros_park_factor.py
date: 2026-07-09
verdict: REJECTED
purpose: Quantify whether explicit RoS venue/park exposure adds independent lift on rh3 beyond own-skill + opposing-SP-quality features.
---

# Pre-registration: `ros_park_factor_weighted` (rh3 v3 candidate)

**Date:** 2026-07-09
**Production target:** `rh3`
**Baseline:** full `RH3_FEATS` (21 features, incl. ros_opp_sp_xwoba_weighted).
Rule 9 satisfied — baseline is the current production feature set.
**Gate:** Δr ≥ +0.005 over baseline AND per-year sign-consistency ≥ 5/7 AND
expected coef sign AND holdout (2024-2025) positive.
**Multiple testing:** this signal is tested against 2 model targets (rh3 +
rp3) in the same run → Bonferroni family size 2. Per repo convention the
gate is effect-size based (Δr ≥ +0.005), not p-value based; the 2-cell
family is disclosed and both results are reported regardless of outcome.
**Expected sign:** **+** (higher RoS park factor → hitter-friendlier
remaining venues → more FP/PA → positive coef).

## Hypothesis

Venue exposure varies across hitters at the same skill level: a hitter
with 40% of remaining games at COL/CIN/BOS-class parks should out-produce
his skill-implied FP/PA, and vice versa for SEA/SD-heavy slates. rh3 has
no park input; ros_opp_sp_xwoba_weighted (PASS +0.0137) proved the
schedule-mix channel carries signal for hitters.

## Construction (leakage safety — Rule 8)

Per (batter, year=T, split_day):
1. Primary team = max-PA team that year (`hitters_multiyr_2015_2026.csv`).
2. Team game log from `statcast_{T}.parquet`; venue = home_team.
3. RoS games = game_date > cutoff_date.
4. Venue park factor = Savant `index_wOBA` (statcast-park-factors
   leaderboard), **3-yr rolling window ending T-1** (e.g. outcome 2024
   uses 2021-2023 factors), single-year T-1 fallback for teams whose
   current park lacks a full window. **No data from year T enters the
   feature.** Scale /100 (1.00 = neutral).
5. Equal-weight mean across RoS games.

Cache: `data/research/xfp_cache/ros_park_factor_per_hitter.csv`
(90,226 rows, all 25 rolling split_days, years 2018-2026 ex 2020;
99.3% non-null pre-fill; mean 0.9996, std 0.0219, range [0.91, 1.15]).
NaN rows (end-of-year no-RoS-games) filled with neutral 1.00 in the
validation attach().

## Step 2.5 data-coverage pre-check (run 2026-07-09, PASS)

Savant park factors verified available for all needed key_years 2017-2025
(rolling-3 + rolling-1 union = 30/30 teams, 0 NaN index_wOBA each year —
see build_park_factors_savant.py output). With T-1 lagging, all outcome
years 2018-2026 are covered. Known window gaps handled by single-year
fallback: ATL 2017-18, TEX 2020-21, TOR 2020, ATH/TB 2025 (7 team-year
fallbacks total in the lagged table).

## v1 simplifications (pre-acknowledged)

- Venue keyed by home-team abbr, not venue_id — alternate-site games
  (TOR 2021 Buffalo/Dunedin) inherit the team's factor.
- Equal-weight per game, not per-PA (lineup-spot PA effects already in
  `lineup_spot_to`).
- League-average park factor (batSide=All), no handedness split.
- 2020 rolling-3 windows (used for outcome 2021) include the 60-game
  season; Savant PA-weights across the window.

## Prior art (disclosed)

- `park_pf_wOBA_ros` (rh3, home-park only, same-year statcast-derived
  pf): MARGINAL 2026-05-24.
- `ros_park_pf_HR_weighted` (rp3, RoS-weighted pf_HR, same-year): MARGINAL.
- This variant differs: official Savant index_wOBA, strict T-1 lag,
  RoS-schedule-weighted, tested on rh3.

## Decision rule

PASS if Δr ≥ +0.005 AND positives ≥ 5/7 AND coef > 0 AND holdout > 0.
MARGINAL if 0.0 < Δr < +0.005 OR sign/positives/holdout fail.
REJECTED if Δr ≤ 0.
A REJECTED verdict is a legitimate outcome — no re-specification after
seeing results.

## RESULTS (run 2026-07-09, scripts/xfp/validate_ros_park_factor.py rh3)

| Metric | Value | Gate | Result |
|---|---|---|---|
| Baseline r (21 RH3_FEATS) | 0.6338 (n=36,571) | — | — |
| Candidate r (+ ros_park_factor_weighted) | 0.6338 | — | — |
| Δr (lift) | **+0.0000** | ≥ +0.005 | FAIL |
| Per-year positives | 4/7 (2018 +0.0013, 2019 +0.0004, 2021 +0.0019, 2022 −0.0011, 2023 +0.0013, 2024 −0.0016, 2025 −0.0036) | ≥ 5/7 | FAIL |
| Holdout 2024-2025 | 0/2 positive (−0.0016, −0.0036) | 2/2 | FAIL |
| Coef sign | +0.0025 | + | OK |

Convergence curve: tiny positive Δ at early split_days (30-72,
+0.0001..+0.0016) fading to consistently negative from sd 79 onward —
the pattern of a feature the season-level baseline absorbs as the year
progresses, not a real independent signal.

**VERDICT: REJECTED.** RoS venue mix adds nothing beyond the full
21-feature rh3 baseline (which already carries the schedule-mix channel
via ros_opp_sp_xwoba_weighted and the level channel via own-skill rates).
Consistent with prior art: park_pf_wOBA_ros (home-park) was MARGINAL;
the done-right schedule-weighted, T-1-lagged, official-Savant version
is flatly zero. Park exposure for hitters should remain a display/context
lens only (Rule 13), not an rh3 feature. Bonferroni family = 2 (rh3+rp3),
both reported; companion rp3 run: MARGINAL (+0.0013).
