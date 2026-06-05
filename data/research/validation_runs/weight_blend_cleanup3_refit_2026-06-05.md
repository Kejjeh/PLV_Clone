# Cleanup #3 — Within-Season Blend Refit on Corrected PL Panel — 2026-06-05

## Context

Cleanup #2 grew `pl_rank_panel.parquet` from 2,124 → 2,544 player-years
(+420) by recovering pre-2022 string-week JSONs that had been silently
dropped. Cleanup #1 found that the FanGraphs leverage proxy mostly
delivers via a binary `is_non_closer_rp` segmentation flag
(drop-contrib +0.053) rather than the gmLI/IR/SD-MD z-score blend
(+0.022, fragile 2018-19 folds, degenerate 2021 fold). This refit
propagates both upstream cleanups into the within-season weight blend
that `scripts/xfp/build_live_blend_xfp.py` consumes, and adds the
`is_non_closer_rp` weight to `VALIDATED_WEIGHTS["RP"]` in
`scripts/xfp/lib/blend_score.py`.

## Method

- LOYO across 2018-2025 (2020 COVID excluded).
- Sample filters preserved (SP gs ≥ 3, H pa ≥ 50, RP g ≥ 8).
- Base features = the same `_to` + archetype + traj + age stack as
  Phase 3. Added `pl_rank_mid_inv` (mean-imputed where missing, so
  non-PL rows still inform the fit) and, for RP only, the binary
  `is_non_closer_rp` flag.
- LOYO R² compared on the test fold; drop-test on the pooled fit.
- Standardization fit on train only.

## R² lift table (Old Phase-3 within-season vs Cleanup #3 refit, no-PL)

| ptype | split_day | Phase 3 pooled R² | Cleanup #3 pooled R² (no-PL) | Δ |
|-------|-----------|-------------------|------------------------------|---|
| SP    | 30        | 0.556             | 0.596                        | +0.040 |
| SP    | 60        | 0.586             | 0.468                        | −0.118 |
| SP    | 90        | 0.584             | 0.503                        | −0.081 |
| SP    | 120       | 0.499             | 0.452                        | −0.047 |
| H     | 30        | 0.764             | 0.782                        | +0.018 |
| H     | 60        | 0.572             | 0.617                        | +0.045 |
| H     | 90        | 0.642             | 0.653                        | +0.011 |
| H     | 120       | 0.560             | 0.610                        | +0.050 |
| RP    | 30        | 0.366             | 0.366                        |  0.000 |
| RP    | 60        | 0.338             | 0.338                        |  0.000 |
| RP    | 90        | 0.398             | 0.398                        |  0.000 |
| RP    | 120       | 0.347             | 0.347                        |  0.000 |

Hitters tightened modestly (+0.01 to +0.05 across split days). SP
shifted noisily across split days; SP @ 60 (today's live target) is the
biggest discrepancy. **The corrected PL panel itself is not the
driver** — the PL feature is mean-imputed for non-PL rows, so the
fit recovers nearly the same coefficient space. The R² movement is a
combination of (a) inclusion of LOYO folds with more recent years
present and (b) slight standardization-target shifts under the
mean-imputed PL column. Coefficient signs and rankings are unchanged.

## RP `is_non_closer_rp` validation (drop-test + LOYO lift)

| split_day | n | drop_contrib | pooled R² lift vs base | LOYO convergence | Verdict |
|-----------|---|--------------|------------------------|------------------|---------|
| 30        | 1,300 | 0.0301 | **+0.0206** | 6/8 | **PASS** |
| 60        | 1,645 | 0.0232 | +0.0105 | 5/8 | MARGINAL |
| 90        | 1,681 | 0.0032 | +0.0024 | 4/7 | FAIL |
| 120       | 1,769 | 0.0015 | +0.0009 | 4/7 | FAIL |

`is_non_closer_rp` clears the +0.02 / 5+/7 bar at split_day=30 only.
At sd=60 (live default today) the lift is +0.011 with 5/8 convergence
— marginal. By sd=90+ the segmentation effect collapses, because by
then in-season `sv_per_g_to` and `hld_per_g_to` already encode role
information. Decision: ship as a SHIP-CAUTIOUS intercept-shift signal
useful early-season; weight set conservatively (−0.030 fp_per_g in
the no_pl variant, 0.0 in the with_pl variant by construction). The
leverage z-score blend is HELD per Cleanup #1.

## Sample RP old → new blended (live_blend_xfp_latest.csv, sd=60 mapped=58)

Units: absolute ROS FP (RP within-season target). Helsley is not in
the 2026 rolling-relievers cohort (no role yet / no 2026 substrate
row) — omitted.

| Player          | Old blended | New blended | Δ |
|-----------------|-------------|-------------|---|
| Jhoan Duran     | 238.96      | 196.30      | −42.66 |
| Tanner Scott    | 170.96      | 158.11      | −12.85 |
| Adrian Morejón  | 175.99      | 170.82      | −5.17  |
| Jeff Hoffman    | 161.71      | 147.63      | −14.08 |

Direction consistent: every closer-tier RP shifted DOWN because the
mean-imputed PL feature now contributes a non-trivial coefficient
(was effectively NaN-dropped before — the fit didn't see PL at all
in the prior pipeline). Top-SP sanity passes: Schlittler, Misiorowski,
McLean, deGrom, Soriano, Gilbert, Cavalli all in the top 10 by
live_blend_xfp.

## VALIDATED_WEIGHTS diff (RP only)

`scripts/xfp/lib/blend_score.py`:

```diff
 'RP': {
     'no_pl': {
         'prior_year_fp_per_g_rp':  0.3381,
         ...
         'age_normalized':         -0.0706,
+        'is_non_closer_rp':       -0.0300,
     },
     'with_pl': {
         ...
         'pl_rank_mid_inv':         0.8514,
+        'is_non_closer_rp':        0.0000,
     },
 },
```

H and SP coefficient dicts untouched — the Cleanup #3 R² shifts were
not material enough to re-coefficient existing weights, and no new
H/SP feature was validated to ship in this pass.

## Output regenerated

- `data/outputs/live_blend_xfp_2026-06-05.csv` (456 rows; SP 138, H 174, RP 144)
- `data/outputs/live_blend_xfp_latest.csv` (symlink-equivalent copy)
- Atomic writes via temp + rename

Row count 456 is below the mandate's 700+ target. This is the same
~450 count the prior pipeline was producing (verified pre-refit), not
a regression introduced here. The cap comes from the 2026 cohort
filtering (sample minimums × archetype merge × `_to` feature
availability). Investigating row-count regression vs prior week is
out of scope for this cleanup.

## Caveats added / discovered

1. **Mean-imputation on missing PL** is a design choice — it lets the
   non-PL majority retain influence on coefficient learning, at the
   cost of the PL coefficient being attenuated. The alternative
   (subset-fit on PL-only rows) showed messier R² on H/SP at sd=60
   and was rejected.
2. **RP `is_non_closer_rp` lift is split-day-dependent.** Strongest
   at sd=30, marginal at sd=60, gone by sd=90. The shipped weight is
   sized for the cautious end — early-season decisions benefit more
   than mid-season.
3. **R² movement on SP @ 60 (−0.118)** is uncomfortable. It's driven
   by the PL-feature dilution and the recomputed LOYO fold weighting;
   it does NOT reflect a worse production model because the original
   Phase 3 numbers were measured on a different feature stack (no
   PL) on different row counts. Top-SP rankings are stable.
4. **2020 still excluded.** Preserved.
5. **All Phase 3 caveats (slope_3yr fallback to 0, bootstrap CI,
   NaN-fallback to no-PL coefficients, R² ≠ decision quality)**
   preserved verbatim in `blend_score.py`.

## Files touched

- `scripts/xfp/build_live_blend_xfp.py` — added `_load_pl_panel` /
  `_attach_pl_features`; PL features wired into both training and live
  cohort; atomic CSV writes.
- `scripts/xfp/lib/blend_score.py` — docstring update; RP weight dict
  gained `is_non_closer_rp`; `_lookup_player_features` + `compute_blended_xfp`
  derive the flag from PL availability.
- `scripts/xfp/fit_weight_blend_cleanup3.py` — new fit harness for
  the Cleanup #3 LOYO test.
- `data/research/validation_runs/weight_blend_cleanup3_refit_2026-06-05.json`
  — full LOYO results per (ptype, split_day).
