---
signal: xwoba_contact_to
formula: AVG(estimated_woba_using_speedangle) WHERE launch_speed IS NOT NULL AND game_date <= cutoff_date, per (pitcher, year, split_day)
outcome: ros_fp_per_start (rp3 production target, cross-year r)
expected_sign: negative (lower xwOBA on contact → better pitcher → more FP/start RoS)
theory: xwoba_contact_to isolates contact quality from K%/BB% (which xwoba_per_pa_to_sh already captures). A pitcher who suppresses hard contact generates persistently good outcomes independent of strikeout rate. The to_sh version of xwOBA per PA is in RP3_FEATS but it penalizes K-heavy pitchers less on contact — xwoba_contact separates the two channels cleanly.
production_target: rp3
framing: in-season → ros (season-to-date xwOBA-on-contact at each split_day cutoff → rest-of-season fp_per_start)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_xwoba_contact_to.py
date: 2026-05-25
verdict: REJECTED
purpose: Emergent from stuff_contact_composite validation (2026-05-25) — continuous xwoba_contact showed +0.1012 lift vs full RP3_FEATS (7/7 years, holdout +0.1380) but with full-season data leakage. This run computes xwoba_contact_to properly at each split_day cutoff_date. If it clears the +0.005 gate cleanly, xwoba_contact_to would be the largest validated lift in the rp3 history. Rule 9 baseline = full RP3_FEATS (24 feats, r≈0.5654).
---

## Step 2.5 data-coverage pre-check

- Source: `statcast_{year}.parquet` files, 2018-2025 (all available)
- `estimated_woba_using_speedangle` + `launch_speed`: present in Statcast since 2015
- BIP coverage: ~20-30 batted balls per start × 5+ starts by split_day 30 = ~100-150 BIP
  per pitcher at the earliest cutoff. xwOBACON is semi-stable at 50+ BIP.
- Pitchers with < 15 BIP at cutoff: NaN → filled with per-year mean (not imputed to 0)
- 2020 COVID year included (shorter season; pitchers will have fewer BIP at each cutoff
  but split_day 30 ≈ 2020-08-25, covering about 3-4 starts)
- Training years available: 2018, 2019, 2021, 2022, 2023 = 5 years (clears Rule 2b bar of ≥5)
- Holdout: 2024-2025 (declared off-limits per standard rp3 protocol)

## Decision rule

- PASS: lift ≥ +0.005 AND sign consistent ≥ 5/7 training years AND holdout lift > 0
- MARGINAL: lift in (0, +0.005] OR fails one secondary gate while clearing headline
- REJECTED: lift ≤ 0 OR wrong sign on holdout

## Bonferroni context

Single hypothesis — no sweep. Full α=0.05 (no adjustment needed).

## If PASS: production integration plan

1. Add `xwoba_contact_to` computation to `scripts/xfp/build_batter_rolling_features.py`
   (or a new `build_sp_contact_features.py`) — one DuckDB query per (year, cutoff_date)
2. Join output to rolling_pitchers CSV on (pitcher, year, split_day)
3. Shrinkage: apply with k≈50 BIP (xwOBACON stabilizes faster than xwOBA/PA)
4. Add `xwoba_contact_to_sh` to RP3_FEATS in `src/plv_clone/models/xfp/rp3.py`
5. Run full-pipeline backtest: cross_year_r must improve ≥ +0.005 in integrated form
6. Version bump: rp3 v4

## Formal result (2026-05-25)

Script: `scripts/xfp/validate_xwoba_contact_to.py`
Rule 9 baseline: r=0.5654 (24 features)

| Gate | Value | Pass? |
|---|---|---|
| (a) Lift ≥ +0.005 | **−0.0001** | FAIL |
| (b) Sign ≥ 5/7 years | 4/7 | FAIL |
| (c) Holdout > 0 | +0.0002 | marginal |
| Ridge coef | −0.0461 | correct sign |

Per-year: 2018 +0.0001, 2019 −0.0001, 2021 +0.0000, 2022 +0.0005, 2023 −0.0006, 2024 +0.0002, 2025 +0.0002

Convergence curve: split_day 30 +0.0004, 60 −0.0004, 90 −0.0004, 120 −0.0003 (flat, no improvement at any cutoff)

**Root cause:** `xwoba_per_pa_to_sh` + `k_pct_to_sh` + `bb_pct_to_sh` already in RP3_FEATS
allow the model to reconstruct xwOBA-on-contact algebraically. Adding it explicitly adds zero
marginal information. The +0.1012 from the stuff_contact_composite run was circular — full-season
xwOBA-on-contact predicting full-season FP (same season, not RoS).

**PA splits:** Would not change this verdict. The redundancy is structural (components already
in model), not a sample-size problem. Switching to PA-based cutoffs would equalize sample
sizes but cannot add signal that the model's existing features already reconstruct.

**Do not promote to RP3_FEATS.**

## Note on sign convention

`expected_sign: negative` — lower xwOBA-on-contact = better pitcher. The Ridge model
will learn a negative coefficient. When reporting lift, a negative coefficient with
consistent negative correlation between xwoba_contact_to and ros_fp_per_start is "working
as expected." The cross_year_r metric is unsigned correlation — lift is always positive
if the feature helps.
