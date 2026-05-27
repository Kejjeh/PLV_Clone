---
signal: pl_untested_signals_sweep
formula: |
  Six PL-roundup-derived SP signals validated as a sweep (singletons + 2 bundles)
  against full 24-feature RP3_FEATS baseline:

  F. fps_pct_to              = season-to-date first-pitch strike rate
                               (reuse data/research/xfp_cache/fp_strike_2015_2026.csv;
                               proxy: full-year fp_strike_pct of current year applied
                               as a stable rate — same approach as ext_delta used)
  P. putaway_pct_to          = (K events) / (PAs that reached 2 strikes), season-to-date,
                               computed from Statcast parquets via DuckDB
  T. ttop_penalty_to         = xwOBA-allowed at 3rd-time-through-order minus 1st-time,
                               per-pitcher season-to-date (game-level TTO assigned by
                               cumulative distinct-batter count within game)
  O. out_pitch_whiff_delta   = whiff% on pitcher's primary breaking ball (SL/CU/ST)
                               in year T minus year T-1 (modal breaking ball per pitcher)
  R. velo_recovery_slope     = OLS slope of avg_velo_last21 vs days_since_il_return
                               for IL returners (NaN for non-returners)
  X. pitch_trim_flag         = 1 if pitcher had a pitch type at ≥10% usage in year T-1
                               that is <5% in year T (inverse of new_pitch_flag)

outcome: ros_fp_per_start
expected_sign: F:+ P:+ T:- O:+ R:+ X:+
theory: |
  Each signal targets a specific PL roundup observation that has shown 1-3 week lead
  time over stat-based models. FPS captures command-axis discipline; putaway% captures
  two-strike skill (distinct from aggregate K%); TTOP penalty captures the structural
  limit on max-effort short-stint pitchers; out-pitch whiff captures per-pitch-type
  novelty (not aggregate); velo recovery slope captures IL-return trajectory (not
  level); pitch_trim_flag tests the symmetric hypothesis to the rejected new_pitch_flag
  (dropping a bad pitch may be just as informative as adding a good one).

production_target: rp3
framing: in-season → ros
holdout_years_A: [2024, 2025]
holdout_years_B: [2025, 2026]
training_years_A: [2018, 2019, 2021, 2022, 2023]
training_years_B: [2018, 2019, 2021, 2022, 2023, 2024]
bonferroni_cells: 28
bonferroni_adjusted_partial_r_bar: 0.21
validation_script: scripts/xfp/validate_pl_signals.py
date: 2026-05-27
verdict: REJECTED
---

## Results summary (v2, split-day-corrected)

V1 (full-year proxy) produced spurious +0.022 to +0.076 lifts due to Rule 8
framing leakage — full-year FPS/putaway applied to predict RoS from mid-season
cutoff. V2 rebuilt fps_pct_to_sd and putaway_pct_to_sd as TRUE split-day-aware
cumulative-to-game-date values; convergence-curve `d30:+0.0020 d42:+0.0020 ...`
confirms proper split-day variation under the hood.

**V2 lifts (all REJECTED):**

| Cell | cv_lift A | cv_lift B | ho_lift A | ho_lift B | n | Verdict |
|---|---|---|---|---|---|---|
| F_sd (fps_pct_to_sd) | +0.0006 | +0.0003 | +0.0004 | −0.0000 | ~3,300 | REJECTED (below +0.005) |
| P_sd (putaway_pct_to_sd) | +0.0008 | +0.0008 | +0.0017 | +0.0014 | ~3,200 | REJECTED (below +0.005) |
| FP_sd bundle | +0.0011 | +0.0009 | +0.0021 | +0.0017 | ~3,200 | REJECTED (below +0.005) |
| T (ttop_penalty) | −0.0003 | −0.0002 | +0.0004 | +0.0014 | ~3,200 | REJECTED (null) |
| O (out_pitch_whiff_delta) | −0.0041 | −0.0013 | flat | flat | ~1,800 | REJECTED |
| R (velo_recovery_slope) | +0.0089 | +0.0017 | mixed | mixed | ~600 | REJECTED (subset null) |
| X (pitch_trim_flag) | +0.0001 | +0.0000 | flat | flat | ~2,000 | REJECTED |

**Sign consistency is PERFECT (5/5, 6/6) on F/P/FP** but lift is well below the +0.005 bar. Confirms a tiny real signal exists, but RP3_FEATS delta layer (delta_swstr, delta_k_pct, c_plus_swstr_to_sh) already captures the lion's share of two-strike/first-pitch information through their downstream consequences on K-rate and swstr.

## Leakage post-mortem

V1 used `data/research/xfp_cache/fp_strike_2015_2026.csv` (keyed pitcher,year)
applied as if it were season-to-date. Putaway% in v1 was computed via DuckDB
on full-year Statcast data (no `game_date <= cutoff_date` filter).

**Smoking gun in v1:** convergence curve identical at split_day 30, 42, 56
— mathematically impossible for a true season-to-date feature, since
mid-April FPS% should differ from mid-May FPS% as the sample grows.

**V2 fix:** built `data/research/xfp_cache/pl_signals_split_day_2018_2026.csv`
via `scripts/xfp/build_pl_signals_split_day.py`. Per-(pitcher, game_date)
cumulative counts of first-pitches/first-pitch-strikes/2-strike-PAs/Ks,
joined to rolling_pitchers via DuckDB ASOF on cutoff_date. Stabilization
gate: ≥50 first-pitches and ≥30 two-strike PAs.

V2 convergence curves are properly distinct across cutoffs (d30 different
from d70), confirming the fix.

## V3 framing: rolling-last-N-PA windows

Tested whether **recent form** (last 100 first-pitch PA / last 50 two-strike PA)
predicts beyond season average. Directly analogous to RP3's `delta_swstr` /
`delta_k_pct` features. Cache: `pl_signals_lastpa_2018_2026.csv` via
`build_pl_signals_lastpa.py`.

9 cells × 2 holdout configs = 18:

| Cell | Best cv_lift | Best ho_lift | Sign | Verdict |
|---|---|---|---|---|
| F_lpa (fps_pct_last100pa) | +0.0006 | +0.0011 | 5/5, 6/6 | MARGINAL → reject |
| F_dlpa (fps_pct_delta_l100) | +0.0001 | +0.0001 | 5/5, 6/6 | MARGINAL → reject |
| P_lpa (putaway_pct_last50pa) | +0.0001 | +0.0024 | 5/5, 6/6 | MARGINAL → reject |
| P_dlpa (putaway_pct_delta_l50) | −0.0002 | +0.0005 | 5/5, 6/6 | REJECTED |
| FP_lpa | +0.0007 | +0.0038 | 5/5, 6/6 | MARGINAL → reject |
| ALL_lpa (4-feat) | +0.0007 | +0.0047 | 5/5, 6/6 | MARGINAL → reject |

**All 18 cells fail the +0.005 cv_lift gate.** Best is ALL_lpa with cv=+0.0007 /
ho=+0.0047 — brushing the bar from below on holdout but nowhere near it on CV.
Sign consistency is perfect across every cell, confirming a tiny real signal
exists but is overwhelmed by what's already in RP3_FEATS.

## Three-framing convergence

| Framing | Best cv_lift | Verdict |
|---|---|---|
| v1 cumulative (leaky) | +0.0972 | Spurious |
| v2 cumulative split-day-aware | +0.0011 | REJECTED |
| v3 rolling-last-N-PA | +0.0007 | REJECTED |

Three independent feature representations converge on lift ≈ +0.001 over the
RP3 baseline. The PL roundup edge on first-pitch command / putaway skill exists
in raw form but is fully absorbed by the existing delta-rate-stat layer.
**Final close: REJECTED for production promotion in any framing.**

## Bonus: production-model leakage audit

Parallel audit of RP3 (24 features), RH3 (17 features), RPRS2 (31 features)
returned **CLEAN across all three models**. Every `_to` feature in production
is correctly computed from `pitches[game_date <= actual_cutoff]`. Every
`prior_*` feature uses strictly prior-year data. RoS schedule-strength features
(`ros_opp_xwoba_weighted`, `ros_opp_sp_xwoba_weighted`) legitimately use
PRIOR-season opponent aggregates against the publicly-known RoS schedule —
not leakage.

No production-model corrections needed.

## Sweep cells (14 × 2 holdout configs = 28 total)

| Cell | Signal set | Type |
|---|---|---|
| F | fps_pct_to | singleton |
| P | putaway_pct_to | singleton |
| T | ttop_penalty_to | singleton |
| O | out_pitch_whiff_delta | singleton |
| R | velo_recovery_slope | singleton |
| X | pitch_trim_flag | singleton |
| FP | fps + putaway (PL "command + stuff" pair) | bundle |
| TOX | ttop + out_pitch + pitch_trim (process-change composite) | bundle |
| FPT | fps + putaway + ttop | bundle |
| FPTO | F+P+T+O | bundle |
| FPTOX | F+P+T+O+X | bundle |
| ALL | F+P+T+O+R+X | full bundle |
| R_int | velo_recovery_slope × is_on_il_at_split | interaction |
| R_il_subset | velo_recovery_slope as singleton on IL-returner subset only | subset test |

## Data-coverage pre-check (Step 2.5)

| Signal | Source | Years available | N expected (gs≥3) | Pre-check |
|---|---|---|---|---|
| F (fps) | xfp_cache/fp_strike_2015_2026.csv | 2015-2026 | ~5,400 | PASS |
| P (putaway) | Statcast parquets, strikes==2 + events | 2018-2025 | ~4,800 | PASS |
| T (ttop) | Statcast parquets, at_bat_number + inning | 2018-2025 | ~3,200 (gs≥5 for stable 3rd-TTO N) | PASS |
| O (out_pitch_whiff) | Statcast, pitch_type + description | 2018-2025 (need T-1) | ~3,500 | PASS |
| R (velo_recovery_slope) | rolling_pitchers + il_split_features | 2018-2025 | ~600 (IL returners only) | **BORDERLINE** — test as interaction primarily |
| X (pitch_trim_flag) | Statcast pitch_type usage | 2018-2025 (need T-1) | ~3,500 | PASS |

Rule 5 sample-size: All singletons except R have N ≥ 3,000 pooled across training years. R will be tested two ways: (1) standalone with sub-population NaN-imputed to median; (2) interaction with is_on_il_at_split (which is the load-bearing axis).

## Rule 9 baseline

Full RP3_FEATS (24 features) as used in xfp_rp3_pipeline.py. Same baseline as
pitch_shape_early_warning_sweep (2026-05-27, REJECTED) — comparing on identical
ground.

## Bonferroni

28 cells × α=0.05 → per-cell α = 0.0018. Conservative bar: partial r ≥ 0.21 for
the headline gate, with the standard +0.005 cv_lift + holdout-positive + sign-consistent
year-over-year gates as the actual PASS criteria.

## Convergence curve

Per Rule 8, re-validate any passing cell at split_day cutoffs 30, 42, 56, 70, 84.
Sign-flip across cutoffs = REJECTED regardless of pooled lift.
