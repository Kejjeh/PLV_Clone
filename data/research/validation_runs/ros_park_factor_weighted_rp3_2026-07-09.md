---
signal: ros_park_factor_weighted
formula: For each (pitcher, year, split_day) — pitcher's primary-team RoS games (game_date > cutoff_date from rolling_pitchers), equal-weight mean over RoS games of the VENUE's (home team's park) lagged Savant park factor. Park factor = Savant statcast-park-factors index_wOBA / 100, 3-yr-rolling window ENDING year T-1 (key_year = T-1), single-year T-1 fallback for new-park teams, neutral 1.00 if absent. Built in scripts/xfp/build_ros_park_factor.py from scripts/xfp/build_park_factors_savant.py cache.
outcome: rp3 cross_year_eval Δr on RoS FP/start target (matches rp3 production)
expected_sign: -
theory: An SP whose remaining schedule runs through hitter-friendly venues concedes more H/ER/HR per start, so FP/start falls as the RoS park factor rises — negative coefficient expected. RP3_FEATS carries opponent-quality schedule mix (ros_opp_xwoba_weighted, PASS +0.0145) but no venue exposure. Prior art: same-year statcast-derived ros_park_pf_HR_weighted came back MARGINAL (2026-05-24); this variant uses official Savant index_wOBA with strict T-1 lagging.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_ros_park_factor.py
date: 2026-07-09
verdict: MARGINAL
purpose: Quantify whether explicit RoS venue/park exposure adds independent lift on rp3 beyond stuff/command/drift/prior/IL + opponent-quality schedule features.
---

# Pre-registration: `ros_park_factor_weighted` (rp3 v3 candidate)

**Date:** 2026-07-09
**Production target:** `rp3`
**Baseline:** full `RP3_FEATS` (25 features, incl. ros_opp_xwoba_weighted).
Rule 9 satisfied — baseline is the current production feature set.
**Gate:** Δr ≥ +0.005 over baseline AND per-year sign-consistency ≥ 5/7 AND
expected coef sign AND holdout (2024-2025) positive.
**Multiple testing:** tested against 2 model targets (rh3 + rp3) in the
same run → Bonferroni family size 2, disclosed; effect-size gate per repo
convention; both results reported regardless of outcome.
**Expected sign:** **−** (higher RoS park factor → hitter-friendlier
remaining venues → fewer FP/start → negative coef).

## Hypothesis

Identical to the rh3 pre-registration mirrored to the pitcher side: venue
mix over the remaining schedule shifts run environment. A COL/CIN-heavy
remaining slate should depress FP/start below the stuff-implied level;
a SEA/SD-heavy slate should inflate it.

## Construction (leakage safety — Rule 8)

Per (pitcher, year=T, split_day):
1. Primary team from `pitcher_primary_team_2018_2026.csv`.
2. Team game log from `statcast_{T}.parquet`; venue = home_team.
3. RoS games = game_date > cutoff_date.
4. Venue park factor = Savant `index_wOBA`, **3-yr rolling window ending
   T-1**, single-year T-1 fallback for new-park teams. **No data from
   year T enters the feature.** Scale /100.
5. Equal-weight mean across RoS games.

Cache: `data/research/xfp_cache/ros_park_factor_per_pitcher.csv`
(30,595 rows, all 25 rolling split_days, years 2018-2026 ex 2020;
99.1% non-null pre-fill; mean 0.9995, std 0.0209, range [0.91, 1.15]).
NaN filled with neutral 1.00 in validation attach().

## Step 2.5 data-coverage pre-check (run 2026-07-09, PASS)

Same as rh3 pre-registration: Savant factors verified for all key_years
2017-2025, 30/30 team coverage per year with rolling-1 fallback, so all
outcome years 2018-2026 are covered under T-1 lagging.

## v1 simplifications (pre-acknowledged)

- Venue keyed by home-team abbr, not venue_id.
- Equal-weight per team game — approximates the SP's actual start venues
  by the team's venue mix (an SP starts ~1 of 5 team games; his personal
  start-venue draw is noisier than the team mix this feature measures).
- League-average factor (batSide=All), no platoon split.

## Prior art (disclosed)

- `park_pf_HR_ros` (home-park only, pf_HR): MARGINAL (+0.0017, holdout
  fail) 2026-05-24.
- `ros_park_pf_HR_weighted` (RoS-weighted pf_HR, same-year
  statcast-derived): MARGINAL 2026-05-24.
- This variant differs: official Savant index_wOBA (wOBA-based, not HR),
  strict T-1 lag (prior versions used same-year factors — mild
  look-ahead), same RoS weighting.

## Decision rule

PASS if Δr ≥ +0.005 AND positives ≥ 5/7 AND coef < 0 AND holdout > 0.
MARGINAL if 0.0 < Δr < +0.005 OR sign/positives/holdout fail.
REJECTED if Δr ≤ 0.
A REJECTED verdict is a legitimate outcome — no re-specification after
seeing results.

## RESULTS (run 2026-07-09, scripts/xfp/validate_ros_park_factor.py rp3)

| Metric | Value | Gate | Result |
|---|---|---|---|
| Baseline r (24-feat RP3_FEATS incl. ros_opp_xwoba_weighted) | 0.5615 (n=19,111) | — | — |
| Candidate r (+ ros_park_factor_weighted) | 0.5628 | — | — |
| Δr (lift) | **+0.0013** | ≥ +0.005 | FAIL (below gate) |
| Per-year lift | 2018 −0.0027, 2019 +0.0047, 2021 +0.0028, 2022 −0.0024, 2023 +0.0045, 2024 +0.0024, 2025 +0.0007 | ≥ 5/7 positive | PASS (5/7) |
| Holdout 2024-2025 avg lift | +0.0016 | > 0 | PASS |
| Coef sign | −0.1864 | − | OK |

**VERDICT: MARGINAL.** Direction is right everywhere it can be (correct
negative coef, 5/7 years positive, holdout positive) but the effect is
~4× too small for the +0.005 production gate. Third consecutive MARGINAL
for an SP park feature (park_pf_HR_ros home-only +0.0017; ros_park_pf_HR_weighted
same-year statcast pf; now Savant index_wOBA T-1-lagged +0.0013) — the
park channel for rp3 is real but tiny, mostly absorbed by
ros_opp_xwoba_weighted + own-skill levels. Do NOT add to RP3_FEATS.
Keep park as a per-start context lens (boom_stack park_friendly component,
which IS validated for the boom framing). Bonferroni family = 2 (rh3+rp3),
both reported; companion rh3 run: REJECTED (+0.0000).
