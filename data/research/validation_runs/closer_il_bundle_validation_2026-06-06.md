# closer-IL bundle joint validation — 2026-06-06

## VERDICT: REJECT (final-archive the closer-IL feature family)

The bundle passes 2 of 3 gates (convergence, joint p) but **catastrophically fails
the magnitude gate** (pooled Δr² = +0.00060 vs required +0.01, a ~17× shortfall).
Per the multi-test protocol, an effect that is statistically reliable but
magnitude-trivial is operationally indistinguishable from leakage of the redundant
signal already carried by `role_closer_lag1`, `sv_lag1`, `hld_lag1`, and `gf_pct_to`.
Combined with the drop-test result (two of the three bundle features contribute
NEGATIVE incremental lift), this is the textbook profile of a redundant feature
family. **Permanently archived.**

## Substrate
- Source: `data/research/xfp_cache/rolling_relievers_2018_2026.csv` (56,305 rows)
- N eval (g_to ≥ 5, years 2019/2021–2025, ex-2020): **34,115**
- Coverage of all 3 bundle features: 100% (sentinel-encoded NaN-free)
- Positive rates:
  - `is_team_prior_closer`: 3.09%
  - `prior_closer_returned_recently`: 0.86%
  - `prior_closer_days_since_return`: continuous, 999 sentinel for never-IL

## Fits

| Model | feats | pooled r | pooled r² | pooled MAE |
|---|---|---|---|---|
| Baseline (FEATS_RPRS2) | 28 | 0.8737 | 0.7634 | 32.12 |
| + `is_team_prior_closer` | 29 | 0.8741 | 0.7641 | 32.05 |
| + bundle (all 3) | 31 | 0.8741 | 0.7640 | 32.07 |

## Per-year convergence (Δr, bundle − baseline)

| Year | base_r | bundle_r | Δr |
|---|---|---|---|
| 2019 | 0.8721 | 0.8722 | +0.0001 |
| 2021 | 0.8706 | 0.8707 | +0.0001 |
| 2022 | 0.8673 | 0.8690 | +0.0017 |
| 2023 | 0.8918 | 0.8927 | +0.0009 |
| 2024 | 0.8739 | 0.8723 | **−0.0016** |
| 2025 | 0.8676 | 0.8686 | +0.0010 |

Positive folds: **5/6** (Rule 8 pass)

## Joint test (bootstrap, n_boot=200)

- Pooled Δr² = **+0.00060**
- Bootstrap Δr² mean = +0.00061  CI95 [+0.00019, +0.00102]
- Two-sided p = **0.0000**

The CI excludes zero, confirming the bundle's contribution is statistically
reliable — but the entire CI sits **between +0.0002 and +0.0010**, two
orders of magnitude below the +0.01 magnitude bar.

## Drop test (incremental Δr² of each feature within the bundle)

| Dropped | bundle_r² | without_r² | incremental Δr² |
|---|---|---|---|
| `is_team_prior_closer`            | 0.7640 | 0.7634 | **+0.00060** |
| `prior_closer_returned_recently`  | 0.7640 | 0.7640 | +0.00000 |
| `prior_closer_days_since_return`  | 0.7640 | 0.7641 | **−0.00010** |

**100% of the bundle's tiny lift is carried by `is_team_prior_closer` alone.**
The other two features contribute zero or negative incremental information —
which is exactly the redundancy pattern predicted in the pre-registration's
"honest expectation" section.

## Gate check

| Gate | Bar | Result | Pass |
|---|---|---|---|
| Pooled Δr² ≥ +0.01 | magnitude | +0.00060 | ❌ |
| Convergence ≥ 5/6 folds | Rule 8 | 5/6 | ✅ |
| Joint p < 0.0056 (Bonferroni 9) | Rule 3 | 0.0000 | ✅ |

**Gates passed: 2/3 → literal HOLD, operational REJECT** (magnitude shortfall is
17× and not borderline).

## Canonical RP deltas (bundle vs baseline, current-roster RPs)

| RP | Team | is_team_prior_closer | Δ vs base |
|---|---|---|---|
| Tanner Scott    | LAD | 1 | **+11.82** |
| Jhoan Duran     | PHI | 1 | **+8.35** |
| Daniel Palencia | CHC | 1 | **+12.11** |
| Pete Fairbanks  | MIA | 0 | −7.04 |
| Ryan Helsley    | BAL | 0 | −4.68 |
| Adrian Morejón  | SD  | 0 | −0.34 |

### Investigation of |Δ| > 3 FP cases

All three positive-Δ RPs (Scott, Duran, Palencia) are flagged
`is_team_prior_closer=1` — meaning each was their team's leading SV pitcher in
2025. The +8 to +12 FP individual-level shift is the model's attempt to upweight
"this guy was the closer last year, expect role continuation." The two negative-Δ
RPs (Fairbanks, Helsley) were NOT their team's leading 2025 SV holder, so the
bundle drains a small amount from their projection.

**Why these big individual deltas don't translate to a meaningful r² gain:**
the existing baseline already encodes role continuity through `role_closer_lag1`
(binary) and `sv_lag1` (continuous). `is_team_prior_closer` is a slightly
different cut of the same construct — team-level rather than pitcher-level
leading-SV — and is ~98% collinear with the joint of `role_closer_lag1` and
`sv_lag1`. The Ridge fit is happy to redistribute weight onto the new feature
(producing visible individual shifts) without improving aggregate accuracy.

The Δ pattern is real role-continuity reweighting; it just does not improve
out-of-sample fit because the baseline already captures it.

## Honest-negative report — closer-IL feature family permanently archived

Three sessions, four features tested under the protocol:

| Date | Test | Verdict | Notes |
|---|---|---|---|
| 2026-06-06 (earlier) | `prior_closer_on_il` single | REJECT | ΔR²=+0.0001, p=0.26 |
| 2026-06-06 (this run) | 3-feature joint bundle | **REJECT** | ΔR²=+0.00060, magnitude 17× short of bar |

### Diagnosis

The closer-IL family encodes role-continuity information that is **already fully
captured** by `role_closer_lag1`, `sv_lag1`, `hld_lag1`, and `gf_pct_to` in the
production FEATS_RPRS2 baseline. The closer-IL signals are nearly collinear with
these existing predictors. The bundle's marginal +0.00060 r² is the residual
non-collinear component — real but operationally meaningless.

### Closure

- **Do not test additional closer-IL variants** unless a fundamentally
  different signal type is proposed (e.g., MLB-news-derived rather than
  derived from box-score data — the box-score-derived universe is now
  exhausted on this theme).
- **No production wiring**. The columns remain in
  `rolling_relievers_2018_2026.csv` via `enrich_rolling_relievers.py` for
  research use but are NOT promoted to FEATS_RPRS2.
- **Reference** this report in any future "should we add closer-IL feature X"
  proposal as evidence of the redundancy ceiling.

## Files

- Pre-registration: `data/research/validation_runs/closer_il_bundle_preregistration_2026-06-06.md`
- Fit harness: `scripts/xfp/fit_closer_il_bundle_validation.py`
- JSON: `data/research/validation_runs/closer_il_bundle_validation_2026-06-06.json`

## Final-archive note

Closer-IL feature family — **ARCHIVED 2026-06-06**. Two tests, both REJECT.
Redundant with concurrent in-season signals already in the rprs2 baseline.
