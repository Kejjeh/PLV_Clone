# Live-tag retroactive R² lift on SP weight blend — 2026-06-04

Mandate: retroactively reconstruct boom_stack / recform_hot / shadow-scout /
HIGH-K-ARM at historical timestamps using only data available at decision
time, then test whether they add R² lift on top of the Phase-2 SP blend
(prior_year_fp_per_start + arche_overall_prior + arche_career_pct_prior +
3 trajectory flags + age_normalized).

Phase-2 SP baseline: anchor R² = 0.206 → blend R² = 0.295 (lift +0.089,
9/9 fold convergence).

## 1. What was reconstructed

| Tag | Status | Reason |
|---|---|---|
| HIGH-K-ARM | FULL (2018-2025) | Season K% z-scored within (year) cohort, n_bf ≥ 100 floor. Year-end aggregate from statcast. Zero leakage when used as prior-year feature. |
| shadow-scout | FULL (2018-2025) | Year-end per-(pitcher, year) percentile rank within ≥200-pitch population for FB velo / K% / BB% / Whiff% / CSW%. Aggregates only, no within-season slicing. |
| recform_hot | DEFERRED | Requires within-season actuals split by split_day for ROS test; master_panel only has season totals. Designable on rolling_*.csv substrate but not feasible same-session without a split-day actuals build-out. |
| boom_stack | DEFERRED (proof-of-concept only) | 4 components (skill_spike, recform_hot, opp_soft, park_friendly) each need decision-time decomposition. Park table is easy; opp_soft requires per-start opponent xwOBA at decision time; skill_spike needs 5-game rolling stuff vs season baseline; recform shares blocker with Step 3. Recommend single-year (2024) proof-of-concept as a follow-up. |

Builder: `scripts/xfp/build_live_tags_retroactive.py` →
`data/research/historical_panel/sp_live_tags_retroactive.parquet` (6,736
pitcher-year rows). Tags joined to the SP panel as **prior-year** features
so the year-T prediction sees only year-(T−1) data.

Fitter: `scripts/xfp/fit_weight_blend_live_tags.py` →
`data/research/validation_runs/weight_blend_live_tags_2026-06-04.json`.

## 2. R² lift — apples-to-apples (matched n)

The high_k and shadow joins drop sample size because the statcast cache
starts at 2018, so the right baseline is the Phase-2 blend re-fit on the
same subset, not the full-panel 0.295.

| Spec | n | anchor R² | blend R² | lift vs anchor | convergence |
|---|---|---|---|---|---|
| Phase-2 baseline (full) | 1,178 | 0.206 | 0.295 | +0.089 | 9/9 |
| Phase-2 baseline (HK subset) | 754 | 0.195 | 0.305 | +0.110 | 6/6 |
| Phase-2 + HIGH-K-ARM | 754 | 0.195 | **0.344** | **+0.150** (Δ +0.040) | 6/6 |
| Phase-2 baseline (shadow subset) | 735 | 0.195 | 0.307 | +0.112 | 6/6 |
| Phase-2 + shadow (5 pct features) | 735 | 0.195 | **0.353** | **+0.158** (Δ +0.046) | 6/6 |
| Phase-2 + HIGH-K + shadow combined | 735 | 0.195 | **0.362** | **+0.167** (Δ +0.055) | 6/6 |

Both individual tags clear the +0.01 R² ship threshold by 4-5× and pass
Rule 8 convergence (every held-out year shows positive lift).

## 3. Per-feature drop-test contribution

In the combined-features model (full-sample partial R²):

| Feature | ΔR² if dropped |
|---|---|
| arche_overall_prior | +0.0238 |
| **high_k_z_year_prior** | **+0.0098** |
| **shadow_velo_pct_prior** | **+0.0083** |
| traj_down_prior | +0.0043 |
| **shadow_bb_pct_prior** | **+0.0039** |
| age_normalized | +0.0016 |
| shadow_k_pct_prior | +0.0010 (correlated with high_k_z) |
| shadow_csw_pct_prior | +0.0004 |
| shadow_whiff_pct_prior | ~0 (collinear with CSW + K%) |
| prior_year_fp_per_start | ~0 (washed by arche + high_k) |

High_k and shadow_velo carry most of the new signal. Shadow_k_pct and
shadow_whiff_pct collapse into noise once HIGH-K-ARM is in the model
(expected — they measure the same underlying skill). The cleanest set is
**high_k + shadow_velo + shadow_bb** plus the existing blend.

## 4. Rookie / small-sample subgroup (prior n_pitches ∈ [200, 2000))

This is the bucket where rp3 is thin and shadow-scout was theorized to
add the most.

| Spec | n | anchor R² | blend R² | lift |
|---|---|---|---|---|
| Baseline | 341 | 0.144 | 0.263 | +0.120 |
| + shadow | 341 | 0.144 | 0.306 | +0.162 (Δ +0.042) |
| + HIGH-K | 341 | 0.144 | **0.332** | **+0.189 (Δ +0.069)** |

HIGH-K wins decisively in the rookie band — exactly the band the
shadow-scout skill was built for. The hypothesis that shadow is most
valuable on thin samples partially holds, but HIGH-K alone delivers more
lift than shadow's 5-feature panel here. (5/6 fold convergence — 2023
holdout is negative, driven by the post-pitch-clock K% shift.)

## 5. Honest assessment

- HIGH-K-ARM: trivial to recompute (one season aggregate per pitcher),
  +0.040 R² as a standalone add. **Ship.**
- shadow-scout: requires per-year percentile fit on a ≥200-pitch
  population, +0.046 R² as a set but most of it concentrates in velo +
  BB%; the K/whiff/CSW trio is collinear with HIGH-K-ARM. **Ship trimmed
  (velo + bb + csw) — not the full 5-feature panel.**
- recform_hot: needs split-day actuals work before a real test.
  **Defer.**
- boom_stack: requires decision-time park + opp + 5-game rolling stuff
  reconstruction. The infrastructure cost is real and same-session
  reconstruction would risk leakage. **Defer; build a 2024-only POC next
  pass.**

## 6. Recommended production set

Add to the SP rp3 blend (or its successor):

1. `high_k_z_year_prior` — single new feature, biggest individual lift.
2. `shadow_velo_pct_prior` — orthogonal to K-based metrics, picks up
   stuff-only signal.
3. `shadow_bb_pct_prior` — orthogonal control component.

Skip for now: `shadow_k_pct_prior`, `shadow_whiff_pct_prior`,
`shadow_csw_pct_prior` (all collinear with high_k_z once high_k_z is in).

Expected combined lift vs current Phase-2 baseline on matched n: roughly
**+0.05 R²** (blend rises from 0.31 to 0.36). Rule 8 satisfied (6/6 folds
positive on both individual specs; 6/6 on combined).

Phase 2 status update: SP anchor 0.206 → blend 0.295 → **blend+live-tags
0.36 on the 2018+ subset**.

## Files

- Builder: `scripts/xfp/build_live_tags_retroactive.py`
- Feature table: `data/research/historical_panel/sp_live_tags_retroactive.parquet`
- Fitter: `scripts/xfp/fit_weight_blend_live_tags.py`
- JSON result dump: `data/research/validation_runs/weight_blend_live_tags_2026-06-04.json`
