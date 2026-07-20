---
signal: pulled_air_rate
formula: per (batter, year, split_day) — share of batted balls (type=='X') hit in the air (launch_angle >= 10) AND to the pull third (handedness-adjusted spray angle from hc_x/hc_y <= -15 deg), over all batted balls with game_date <= season_start + split_day; k=40 BBE shrinkage toward the as-of population rate. Cell 2 = the shrunken rate interacted with I[middle tercile of hard_hit_pct_to_sh within (year, split_day)]
outcome: ros_core_fp_per_pa (rh3 harness target)
expected_sign: "+"
theory: Statcast xwOBA (and therefore the baseline's xwoba_per_pa/barrel/hard-hit stack) is direction-blind by construction; pulled air contact converts to HR/TB at ~2x the wOBA of non-pulled air contact (.733 vs .353, Savant 2022-24) and air-pull tendency is a sticky skill (r^2=0.624 YoY on medium-hit flies)
production_target: rh3
framing: in-season → ros (all split_days)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_pulled_air_rate.py
date: 2026-07-19
verdict: REJECTED
---

## RESULT (2026-07-19 run)

Sanity: league share 0.176 (published 0.175); Paredes #1, Yandy Díaz bottom — spray math verified.
- **1A-1 main:** Δr −0.0001, 2/7 years, holdout 0/2, coef sign WRONG (−). REJECTED.
- **1A-2 mid-power interaction:** Δr +0.0003 (< gate), 4/7, holdout 2/2, coef sign WRONG (−). REJECTED.
- **Interpretation:** direction-blindness is real for xwOBA, but RH3_FEATS carries
  realized ISO/HR rates, which are direction-AWARE outcomes — the pull skill is already
  priced into the power rates it produces. The literature effect lives in the
  wOBA-minus-xwOBA residual, and rh3 never consumes that residual raw.
- Pre-declared benchmark rule fires: Wave 2A (spray-adjusted xwOBAcon) runs.

## Cells (declared in the campaign ledger, registry 2026-07-19)

- **1A-1** `pulled_air_rate_to_sh` main effect.
- **1A-2** `pulled_air_x_midpow` = pulled_air_rate_to_sh × I[hard_hit_pct_to_sh in the
  middle tercile of that (year, split_day)] — pre-declared because the literature says
  the pull benefit concentrates in medium power (Clemens: elite power gains ~nothing;
  the pull-happiest vs oppo-happiest gap is "a handful of points of wOBA" overall).
- Family-wise: 2 cells, α/2. Both reported regardless of outcome.

## Rule 9 baseline

Full RH3_FEATS via `_validate_rh3_v3_helper.run_candidate_eval` (patched-loader merge,
same pattern as ev90_to_sh_2026-07-19).

## Closest graveyard relatives (pre-declared differences)

- **xwOBA-minus-wOBA in-season gap (closed MARGINAL):** that was the realized outcome
  residual — noisy, self-referential. This is the underlying batted-ball DIRECTION
  distribution: a process input with r^2=0.62 stickiness.
- **ev90_to_sh (closed MARGINAL today):** ev90 is another contact-QUALITY tail measure —
  same axis as hard_hit/barrel, which is why it was absorbed. Direction is a different
  AXIS entirely; no baseline feature sees spray.

## Step 2.5 coverage

hc_x/hc_y + launch_angle 2015+; local parquets 2018-2026. Same-year signal, 5 train +
2 holdout years, thousands of batters/year. Clears Rule 5.

## Sanity check (pre-harness, required)

2024 full-season pulled_air_rate must rank known extreme pull-power profiles (Isaac
Paredes-type) at the top and slap/oppo profiles near the bottom; league mean air-pull
share of BBE should be in the vicinity of the published ~17.5% pulled-airball share.

## Honest expectation

Modest. Clemens: "not a huge effect." The additive channel is the TB/HR term of FP
only. Plausible +0.005; interaction cell may carry it if the main effect is diluted
by elite-power hitters where pull adds nothing.
