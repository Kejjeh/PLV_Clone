# Pre-registration: `ros_opp_sp_xwoba_weighted` (rh3 v3 candidate)

**Date:** 2026-05-24
**Production target:** `rh3`
**Baseline:** full `RH3_FEATS` (20 features). Rule 9 satisfied — baseline is the current production feature set.
**Gate:** Δr ≥ +0.005 over baseline AND per-year sign-consistency ≥ 5/7 AND expected coef sign.
**Expected sign:** **+** (higher opp-SP xwOBA-allowed → opposing SPs are worse → hitter benefits → positive coef on hitter FP/PA).

## Hypothesis

Hitters with a remaining-of-season slate of weaker opposing starting
pitchers will outperform their baseline rh3 projection (and vice versa).
The rh3 model currently uses no schedule-strength input — all features
are own-skill (own bat-tracking, own discipline, own xwOBA, lineup spot,
career stage). The rp3 analog `ros_opp_xwoba_weighted` PASSED today
(+0.0145) on the SP side; this is the hitter mirror.

## Construction

Per (batter, year, split_day):
1. Resolve batter's **primary team** that year via max-PA team in
   `hitters_multiyr_2015_2026.csv`.
2. Get team game log (game_pk, date, home, away) from per-year statcast
   parquet.
3. Filter to RoS games (game_date > split_day cutoff).
4. Look up each RoS opp's **team-average SP xwOBA-allowed** that year
   (tbf-weighted across pitchers on opp_team with gs >= 5; from
   `sp_multiyr_2015_2025.csv` joined to `pitcher_primary_team_2018_2026.csv`).
5. Equal-weight mean across RoS games. (Equivalent to 4-PA-per-game
   weighting under the avg-SP-per-team approximation, since each game
   contributes equal PAs.)

Cache: `data/research/xfp_cache/ros_opp_sp_xwoba_per_hitter.csv`
(15,939 rows across 8 years × 4 split_days; 96.8% non-null pre-fill;
NaN rows are end-of-year batters with no remaining games — filled with
year mean during validation `attach()`).

## v1 simplifications

- **No handedness adjustment.** Team-avg SP xwOBA-allowed pools L+R.
  v2 could split by handedness and weight by the batter's batting hand.
- **SP-quality proxy is full-season** (mild look-ahead, same as the rp3
  schedule feature that PASSED). Carries cross-batter variation in
  schedule mix.
- **Equal-weight per game**, not per-PA. Lineup-spot effects on PA count
  are already captured by `lineup_spot_to` in RH3_FEATS.

## Decision rule

PASS if Δr ≥ +0.005 AND positives ≥ 5/7 AND coef > 0.
MARGINAL if 0.0 < Δr < +0.005 OR sign/positives fail.
REJECTED if Δr ≤ 0.
