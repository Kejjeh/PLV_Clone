---
signal: lineup_handedness_match
formula: For each (pitcher, year, split_day) row, the season-to-date (strictly before cutoff_date) fraction of opposing batters faced (in PA-count terms) whose `stand` matches the SP's `p_throws`. E.g. for a RHP, lineup_handedness_match = (PAs against R-handed batters) / (total PAs). Computed from statcast_YYYY.parquet rows where pitcher=P and game_date<cutoff_date. Uses one row per (pitcher, batter, at_bat_number, game_pk) to avoid pitch-double-counting. Switch hitters get whichever side they bat from in that specific PA (statcast's `stand` is already platoon-resolved). Pitchers with fewer than 50 prior PAs at cutoff get lineup_handedness_match = population mean (~0.56 for RHP, ~0.38 for LHP — but in our framing, this is "fraction same-handed as pitcher faces" so the population mean ≈ 0.56 for everyone after platoon-resolution).
outcome: ros_fp_per_start (rp3 production target, the column already in rolling_pitchers_2018_2026.csv)
expected_sign: NEGATIVE for the SP. A higher fraction of same-handed PAs faced is a worse matchup distribution for the SP (more RvR / LvL = better for the pitcher → HIGHER ros_fp_per_start? Or worse for the pitcher → LOWER?). Convention: same-handed matchup ADVANTAGES the pitcher (the platoon split is small but consistently in the pitcher's favor when handedness matches). So higher lineup_handedness_match → better matchup history → potentially HIGHER ros_fp_per_start. Expected sign: POSITIVE. BUT: the SEASON-TO-DATE history of handedness fraction faced is a function of the schedule already played, which may or may not be predictive of REMAINING schedule. If teams cycle through home / away series with mixed-handed lineups, this should be ~0.55 for everyone and the variance is mostly noise. Expected magnitude: SMALL.
theory: RP3_FEATS already encodes ros_opp_xwoba_weighted (the strength of the RoS schedule, weighted across remaining opponents). It does NOT encode the *handedness composition* of opponents already faced or yet to come. The hypothesis: SPs who have faced a same-handedness-skewed lineup distribution so far in the season may have inflated counting stats relative to true talent (RvR / LvL advantages compound), and the rp3 model could regress this if the feature loads negatively. ALTERNATIVELY, the season-to-date handedness fraction may simply re-encode the team strength already captured by opp xwOBA (good lefty-mashing teams are good against RHPs and would show as low handedness_match for RHPs facing them) — in which case partial r vs ros_opp_xwoba_weighted should be small.
production_target: rp3
framing: in-season → ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_lineup_handedness.py
date: 2026-06-02

# Pre-registration body (written BEFORE running any models)

## Why this candidate
- The TASK BRIEF explicitly flags this as a "matchup advantage proxy" candidate. The model currently has `ros_opp_xwoba_weighted` (RoS schedule strength) but no handedness-mix term.
- IF a real signal exists beyond what opp xwOBA captures, it would mean the model can distinguish "easy schedule because of low-quality opponents" from "easy schedule because of platoon-favorable handedness composition" — two different mechanisms.
- The task brief itself flags the most likely confound: "good lefty mashers are good vs RHP" — handedness is partially encoded in team xwOBA already. A real signal would be ORTHOGONAL to that.

## Rule 8 framing
- Production use case is in-season → RoS at split rows of split_day = 30, 37, 44, 51, 58.
- Convergence check: split_day 30, 44, 58.
- All handedness computations use ONLY statcast PAs with game_date strictly less than cutoff_date.

## Rule 9 baseline (the critical one)
- Baseline = full current RP3_FEATS (24 features), including the already-validated `ros_opp_xwoba_weighted`. No stripping.
- Lift = cross_year_r(baseline + lineup_handedness_match) − cross_year_r(baseline).
- The critical comparison: does adding lineup_handedness_match move the needle BEYOND what ros_opp_xwoba_weighted already provides?

## Rule 5 sample-size honesty
- Training years: 2018, 2019, 2021, 2022, 2023 — well above floors.
- Holdout: 2024, 2025.
- Coverage: depends on pitcher having ≥ 50 prior PAs at cutoff. At split_day=30 most SPs have 100+ PAs, so coverage is high (≥ 95%).

## Rule 3 / Bonferroni
- Two candidates this run (days_rest, lineup_handedness_match). Bonferroni alpha_per_test = 0.025. Effect-size gate +0.005 r lift.

## Decision rule (pre-committed)
- **SHIP** (verdict PASS): cross-year r lift ≥ +0.005 AND lifts at split_day 30/44/58 are all same-sign AND holdout 2024-2025 lift > 0 AND MAE reduction on holdout > 0 AND partial r vs full baseline ≥ +0.02.
- **DON'T SHIP** (verdict REJECTED): lift below +0.005 gate OR wrong sign on holdout OR lifts wildly inconsistent across split_days OR partial r is small AND fully redundant with ros_opp_xwoba_weighted.
- **NEEDS MORE DATA** (verdict MARGINAL): partial r in (0, +0.02), or directionally right but below sample-size confidence.

## Confound red flag (pre-stated)
The task brief explicitly warns: "handedness is somewhat encoded in opp team xwOBA already (good lefty mashers are good vs RHP). Be careful interpreting any positive lift — it may just be re-discovering the team-strength signal."

Concrete mitigations in this validation:
1. The baseline INCLUDES ros_opp_xwoba_weighted. The Rule 9 lift is the marginal contribution AFTER that feature.
2. Partial r is reported vs the full baseline INCLUDING ros_opp_xwoba_weighted. If the partial r is high but the lift is small, that confirms re-encoding rather than orthogonal signal.
3. Convergence at 30/44/58: if the lift is larger at split_day 58 than at 30, that's a candidate leakage signature (later cutoff = more season observed = more correlation with full-season counts).

## Leakage discipline pre-commitments
1. Statcast PAs are filtered to game_date < cutoff_date for EACH (pitcher, year, cutoff) row.
2. The handedness fraction is built per (pitcher, year, cutoff) using only those pre-cutoff PAs.
3. Pitchers with < 50 prior PAs get lineup_handedness_match = 0.56 (overall population mean, computed once on training-years data only).
4. Leave-one-year-out: when predicting year Y, train on the other 4 training years (Y excluded).
5. Holdout (2024, 2025) is NEVER touched during training-year tuning.

## Key open question this validation will answer
Does the rp3 model benefit from knowing the handedness composition of an SP's faced batters, after already knowing the strength (xwOBA) of remaining opponents? If yes → SHIP. If no → handedness is fully absorbed by xwOBA-based features and the rp3 model doesn't need it.
