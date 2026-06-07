# Drop-one-lens ablation — 2026-06-06

Goal: Identify which of the 8 synthesis lenses carry signal vs which are dead weight, 
by ablating each in turn from an equal-weighted ensemble that predicts forward FP/g.

## Method

- Snapshot frames at `data/research/validation_runs/shrinkage_*_snap_2026-06-06.parquet`.
- 8 lenses synthesized as -1/0/+1 votes (see header of `scripts/_oneoff/test_drop_one_lens.py` for proxies).
- Ensemble: `pred = cohort_mean(target by year×tier) + slope * sum(votes)`. Slope fit via OLS on train half.
- 50/50 train/test split (seed=42) for headline MAE; bootstrap (B=500) for ΔMAE CI.
- ΔMAE > 0 ⇒ lens carries signal (dropping it raises error). ΔMAE ≤ 0 ⇒ dead weight or noise.

## Results

### HITTER sample — n=1498
Baseline MAE (all 8 lenses) = **0.6658** FP/g

| Lens | Description | MAE w/o lens | ΔMAE (point) | ΔMAE bootstrap mean | 95% CI |
|---|---|---|---|---|---|
| L1 | Blended xFP / rh3 rank decile (pred_k150) | 0.6707 | +0.0049 | +0.0041 | [+0.0000, +0.0076] |
| L2 | Boom-bust L21 actuals (l21_avg) | 0.6707 | +0.0049 | +0.0040 | [-0.0013, +0.0098] |
| L4 | Prior-year baseline (prior_avg) | 0.6714 | +0.0055 | +0.0039 | [-0.0002, +0.0080] |
| L8 | Model rank decile (pred_k300) | 0.6700 | +0.0042 | +0.0035 | [+0.0002, +0.0072] |
| L3 | Sustainability bucket proxy (-(L21-L42)) | 0.6664 | +0.0006 | +0.0015 | [-0.0039, +0.0074] |
| L5 | L21 vs prior-year gap | 0.6645 | -0.0013 | +0.0004 | [-0.0064, +0.0071] |
| L6 | xwOBACON YoY (prior - prior2) | 0.6658 | -0.0000 | -0.0002 | [-0.0042, +0.0038] |
| L7 | Archetype age tier (top50 vs other) | 0.6659 | +0.0000 | -0.0027 | [-0.0072, +0.0018] |

- **Critical (CI excludes 0, drop HURTS MAE):** L1, L8
- **Dead weight (CI < 0 or ≈ 0):** L5, L6
- **Ambiguous:** L2, L3, L4, L7

### SP sample — n=550
Baseline MAE (all 8 lenses) = **3.5609** FP/g

| Lens | Description | MAE w/o lens | ΔMAE (point) | ΔMAE bootstrap mean | 95% CI |
|---|---|---|---|---|---|
| L5 | L21 vs prior-year gap | 3.5743 | +0.0134 | +0.0148 | [-0.0277, +0.0547] |
| L2 | Boom-bust L21 actuals (l21_avg) | 3.5766 | +0.0156 | +0.0090 | [-0.0281, +0.0450] |
| L4 | Prior-year baseline (prior_avg) | 3.5709 | +0.0099 | +0.0071 | [-0.0181, +0.0320] |
| L1 | Blended xFP / rh3 rank decile (pred_k150) | 3.5648 | +0.0039 | +0.0050 | [-0.0194, +0.0291] |
| L8 | Model rank decile (pred_k300) | 3.5657 | +0.0048 | +0.0024 | [-0.0267, +0.0245] |
| L3 | Sustainability bucket proxy (-(L21-L42)) | 3.5621 | +0.0012 | +0.0020 | [-0.0350, +0.0393] |
| L7 | Archetype age tier (top50 vs other) | 3.5507 | -0.0103 | +0.0014 | [-0.0380, +0.0420] |
| L6 | xwOBACON YoY (prior - prior2) | 3.5623 | +0.0013 | -0.0048 | [-0.0291, +0.0174] |

- **Critical (CI excludes 0, drop HURTS MAE):** (none)
- **Dead weight (CI < 0 or ≈ 0):** (none)
- **Ambiguous:** L1, L2, L3, L4, L5, L6, L7, L8

## Combined verdict & recommendation

- **Hitters — keep:** L1, L4, L8
- **Hitters — drop:** (none clearly negative)
- **SPs — keep:** (none above threshold)
- **SPs — drop:** (none clearly negative)

Caveats: lens votes are PROXIES synthesized from snapshot fields, not the real triangulate 
merge-protocol cards. Real lens votes come from the live skill stack and are not in the 
snapshot. This analysis is best read as an information-content scan over the underlying 
signal sources, not a final say on the protocol UI. Bootstrap uses sampled-with-replacement 
blocks; sample sizes (H n=1498, SP n=550) are modest so CIs are wide.
