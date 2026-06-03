# Within-team residual correlation test — σ² scaling diagnostic

Generated 2026-06-03. Panel: `data/outputs/predictions_history.csv` (141
backfilled matchups + a few live 2026 rows). Implementation:
`scripts/xfp/within_team_corr_test.py`.

## Question

The current matchup dashboard's win-probability distribution is
compressed to ~0.30–0.77 — clearly lopsided matchups never reach 85%+
confidence. Hypothesis: team σ² is being **over-counted** because we sum
per-player σ² and ignore within-team residual correlation. If true team
σ² is smaller, win-prob extremes should widen.

## Method

1. From each backfill row back out implied total σ from
   `win_probability = Φ((my_proj − opp_proj) / σ_total)`.
2. Split σ_total between teams proportionally to projected totals
   (constant-CV approximation): σ_team ∝ proj_team. Verified algebra
   recovers σ_my² + σ_opp² = σ_total².
3. Normalize each team's residual: `z = (actual − projected) / σ_team`.
4. Under a well-calibrated σ², `std(z) ≈ 1`. Smaller → σ² inflated.
5. Required scaling: `s = std(z)²`. Implied within-team correlation:
   `ρ̄ = (s − 1) / (n − 1)`, with n ≈ 22 active scoring slots.
6. Cross-validate by year and by re-running win-prob with `σ²_new = s·σ²_old`.

## Results

### Normalized residuals

| Slice | n | mean(z) | std(z) | s = std(z)² | ρ̄ (n=22) |
|---|---:|---:|---:|---:|---:|
| **Pooled** | **278** | **+0.28** | **0.773** | **0.597** | **−0.0192** |
| 2024 synth | 158 | +0.16 | 0.476 | 0.226 | −0.0369 |
| 2025 synth | 112 | +0.38 | 1.012 | 1.025 | +0.0012 |
| 2026 live | 8 | +1.38 | 0.644 | 0.415 | −0.0279 |

**Directional:** std(z) < 1 pooled → σ² is inflated; ρ̄ negative & small
(consistent with the prior — long SP outings cannibalize relief work,
boom-stack covariance not fully captured, etc.).

**The 2024 vs 2025 split is the headline caveat.** s ranges 0.23 → 1.03
across years. They do **not** agree. 2025 alone says the variance
aggregation is already well-calibrated; only 2024 plus the small 2026
slice pull the pooled estimate below 1.

### Win-prob redistribution at s = 0.597

| Bucket | OLD (current σ²) | NEW (σ² × 0.597) |
|---|---:|---:|
| ≥85% | 2 | 2 |
| ≥75% | 4 | 4 |
| ≥65% | 6 | 11 |
| 35–65% | 128 | 120 |
| ≤25% | 0 | 0 |
| ≤15% | 0 | 0 |
| min / max | 0.303 / 0.964 | 0.252 / 0.990 |

The compression breaks open only modestly. Confidence ≥65% goes 6→11,
range widens 0.30–0.96 → 0.25–0.99. Few new ≥85% or ≤15% predictions
appear because the projected-total **gaps** in the panel are themselves
small — sharper σ pushes them out a little, not dramatically.

### Per-bucket calibration

OLD (current σ²):

```
25–35:  n= 6  pred 0.32  actual 0.17
35–45:  n=26  pred 0.42  actual 0.31
45–55:  n=68  pred 0.50  actual 0.43
55–65:  n=34  pred 0.59  actual 0.59
65–75:  n= 2  pred 0.68  actual 0.50
75–85:  n= 2  pred 0.76  actual 1.00
85+:    n= 2  pred 0.95  actual 1.00
```

NEW (σ² scaled by 0.597):

```
25–35:  n= 9  pred 0.29  actual 0.11
35–45:  n=25  pred 0.41  actual 0.36
45–55:  n=60  pred 0.50  actual 0.42
55–65:  n=35  pred 0.60  actual 0.57
65–75:  n= 7  pred 0.69  actual 0.57
75–85:  n= 2  pred 0.82  actual 1.00
85+:    n= 2  pred 0.98  actual 1.00
```

Aggregate skill:

| Metric | OLD | NEW |
|---|---:|---:|
| LogLoss | 0.6559 | 0.6520 |
| Brier | 0.2329 | 0.2314 |

NEW is **marginally** better on log-loss and Brier (~0.4% relative
improvement). Middle buckets (35–65, 91 of 145 unique matchups) stay
well-calibrated. Mid-confidence buckets (55–75) drift slightly farther
from the diagonal under scaling, but n is tiny.

## Stationarity / panel caveats

1. **Synthetic backfill used Bayesian-shrunk season averages, NOT the
   live boom_stack-aware projection.** That biases the synthetic
   projection toward the mean. Under-projection of variance in the
   *projection itself* could either inflate or deflate observed σ-residual
   ratios depending on direction. We expect σ to look inflated (residuals
   tighter than σ predicts) precisely because shrunk projections track
   mean realizations.
2. **2024 vs 2025 disagreement (s = 0.23 vs 1.03).** Two cleanly
   different generative regimes inside the synthetic panel. Either
   the 2024 synthetic projection was *especially* conservative (likely
   — fewer in-season data points to anchor on), or true ρ̄ shifted, or
   the noise floor of n=158 for a variance estimate is just wide.
3. **Mean(z) = +0.28 pooled.** A small but non-zero positive bias —
   actual totals run higher than synthetic projections on average. This
   leaks into std(z) slightly (uncentered second moment). Centering
   first changes std(z) negligibly (≤2%), so finding survives.
4. **Implied-σ backout depends on the OLD win-prob being a sufficient
   statistic for σ²_total.** It is (the formula is invertible), but any
   future schema change that stores σ directly would let us skip this
   step.
5. **141-row panel is enough for directional, not tight.** 95% CI on
   pooled std(z) is roughly ±0.07 → s ∈ [0.51, 0.71], ρ̄ ∈ [−0.023, −0.014].
   2024-vs-2025 separation is wider than that — so the regime question is
   real, not a sample-size artifact alone.

## Verdict

**NEEDS_MORE_DATA** — directionally consistent with σ² inflation
(pooled s ≈ 0.60, ρ̄ ≈ −0.019) but **not stable enough to ship a global
multiplier**:

- 2024 (s = 0.23) and 2025 (s = 1.03) disagree by ~4×. A single global
  `s` baked into `build_matchup_dashboard.py` would be wrong for at
  least one of those regimes.
- The win-prob redistribution at s = 0.60 is small — buckets ≥65%
  only move from 6 → 11 of 145. Log-loss improves only 0.6%.
  The compressed-band problem is dominated by **projection gaps being
  small**, not by σ being too big.
- The synthetic-projection conservatism caveat is unresolved. A live
  boom_stack-aware projection would shrink synthetic-vs-actual
  residuals, which *moves std(z) upward* (away from "σ² inflated") on
  the rebuilt panel. We risk shipping a scaling factor fit to an
  artifact of the backfill methodology.

## Recommended next steps (in priority order)

1. **Re-derive the panel with the live boom_stack-aware projection** for
   the 2025 matchups we still have full inputs for. If pooled std(z)
   then climbs to 0.9+, the σ² inflation we measured is mostly a
   backfill artifact and the answer is "don't ship anything."
2. **Wait for 8-12 more 2026 live matchups** (4-6 weeks of data) and
   re-fit on live-only. The 2026 slice (n=8, s=0.41) is too small now
   but is the only regime that matches production.
3. **Tag any future ship as `panel-dependent`** — store `s` in
   `data/research/validation_runs/sigma_calibration.json` under a new
   key (e.g. `team_correlation_s`, version `v1_2026-06-03`) so re-fits
   re-derive instead of stacking.
4. **If a scaling ship becomes warranted later:** multiplicative on
   each team's aggregated σ² inside
   `build_matchup_dashboard.py::compute_team_sigma`, applied uniformly
   to my_team and opp_team. Spec is one constant — no per-position or
   per-roster-size branching is justified by 141 rows.

## DO NOT do

- Ship `s = 0.60` blindly. The 2024-vs-2025 split makes this an
  unstable estimate.
- Use a per-year `s`. The synthetic 2024 panel is the most suspect
  slice; fitting to it would be fitting to the artifact.
- Treat compressed win-prob band as solely a σ² problem — the
  projection-gap distribution is the bigger contributor at the
  current snapshot.

## Files

- Analysis: `scripts/xfp/within_team_corr_test.py`
- This report: `data/research/validation_runs/within_team_correlation_test.md`
- Panel: `data/outputs/predictions_history.csv` (141 backfilled rows)
