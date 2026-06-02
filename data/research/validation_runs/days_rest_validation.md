---
signal: days_rest
target: rp3
verdict: REJECTED
date: 2026-06-02
pre_registration: data/research/validation_runs/days_rest_2026-06-02.md
validation_script: scripts/xfp/validate_days_rest.py
results_json: data/research/validation_runs/days_rest_results.json
---

# days_rest — Validation report (2026-06-02)

## Pre-registered hypothesis (timestamped before any model run)

> Days between an SP's two most recent prior starts (clamped to [3, 7],
> default 5 for SPs with <2 prior starts) will carry RoS-relevant
> information about rotation usage / health regime beyond what is
> already captured by the IL feature triad. Expected sign:
> ambiguous / weakly negative for extra rest. Production gate:
> cross-year r lift ≥ +0.005, sign-consistent in ≥5 of 7 years,
> holdout 2024-2025 lift > 0, MAE on holdout improves.

Full pre-registration in `days_rest_2026-06-02.md` (written before
the script was run).

## Backtest setup

- **Substrate:** `rolling_pitchers_2018_2026.csv` (29,493 rows) prepped
  through the production `_rp3_validation_harness.prep_rolling()`
  pipeline so the baseline has every derived rp3 feature (Marcel prior,
  shrinkage `_to_sh` features, IL features, all 6 drift deltas,
  `ros_opp_xwoba_weighted`).
- **Baseline:** full 24-feature RP3_FEATS as defined in
  `src/plv_clone/models/xfp/rp3.py` lines 73-96. **No stripping** (Rule 9).
- **Candidate:** `days_rest` computed per (pitcher, year, cutoff_date)
  from `statcast_YYYY.parquet` distinct game_date counts. Most recent
  start date minus second-most-recent, in calendar days, strictly
  before cutoff. Clamped to [3, 7]. Pitchers with < 2 prior starts get
  `days_rest = 5`.
- **Eval:** leave-one-year-out cross-year RidgeCV (production
  `cross_year_eval`), filtered to `gs_to ≥ 2` and `ros_gs ≥ 5`. 2020
  excluded. Pooled eval n = 19,111.
- **Holdout:** 2024 + 2025 carved out as the held-year folds.
- **Convergence:** split_day 30 / 44 / 58 (closest grid match to
  requested 30/42/56).

## Feature distribution

- Pre-merge (panel of all valid pitcher-cutoff pairs, n=141,847):
  - mean: 4.69 days (after clamp), std: 1.36
  - Bucket counts: 3 days: 31.4% / 4 days: 6.1% / 5 days: 37.8% /
    6 days: 11.6% / 7 days: 13.1%. The bimodal 3 / 5 distribution is
    driven by (a) the clamp at 3 (28% of raw values were < 3) and
    (b) the neutral default of 5 (25% of rows have < 2 prior starts).
  - Of rows with ≥ 2 prior starts: 28.25% had raw rest < 3 (clamped up),
    59.19% landed in [3, 7], 12.56% had raw rest > 7 (clamped down).
- Post-merge into rolling (n=29,493): 36.8% of rows are at the neutral
  default of 5 (smaller than the pre-merge fraction because the rolling
  substrate is biased toward established SPs).

## Headline numbers

| Metric | Baseline | Baseline + days_rest | Gain |
|---|---|---|---|
| Pooled cross-year r (LOO-CV, all years) | 0.5548 | 0.5546 | **-0.0002** |
| Holdout 2024-25 avg r lift | — | — | **-0.0013** |
| Holdout 2024-25 MAE (FP/start) | 2.7738 | 2.7755 | **-0.0017 (WORSE)** |
| Partial r vs full baseline (pooled LOO residuals) | — | — | **-0.0007** |

Per-year r gain (full minus baseline):

| Year | r gain |
|---|---|
| 2018 | +0.0007 |
| 2019 | +0.0006 |
| 2021 | +0.0000 |
| 2022 | +0.0006 |
| 2023 | -0.0002 |
| **2024** | **-0.0023** |
| **2025** | **-0.0002** |

**Sign consistency: 3 / 7 years positive** (well below the 5/7 bar).

## Convergence check (split_day 30 / 44 / 58)

| split_day | r baseline | r full | r gain | MAE gain |
|---|---|---|---|---|
| 30 | 0.5766 | 0.5792 | **+0.0026** | +0.0022 |
| 44 | 0.5725 | 0.5731 | **+0.0006** | +0.0050 |
| 58 | 0.5655 | 0.5663 | **+0.0008** | +0.0031 |

When restricted to single-split-day cohorts the gains are weakly positive
(+0.0026 / +0.0006 / +0.0008) but evaporate when pooled across split_days
(-0.0002). This is consistent with the per-split-day gains being noise
that does not aggregate. No leakage smell — gains are LARGER at split_day
30 than 58, the opposite of the canonical leakage signature where later
cutoffs (more season observed) would inflate lift. If anything the
opposite pattern suggests days_rest is a slight in-sample fitting
artifact at small split-day-restricted sample sizes (n ≈ 1000).

## Partial r vs full baseline

Partial r of days_rest vs the full RP3_FEATS baseline: **-0.0007**
(essentially zero, slightly negative). This is the strongest single
signal in the report: after controlling for the existing 24 rp3
features, days_rest carries no additional information about
ros_fp_per_start.

## Honest verdict: **DON'T SHIP** (REJECTED)

days_rest fails all four pre-committed gates:

1. **Lift bar:** -0.0002 < +0.005 production gate.
2. **Year consistency:** 3/7 positive years; bar is ≥5/7.
3. **Holdout sign:** -0.0013 (wrong sign on 2024-2025 average).
4. **MAE on holdout:** baseline + days_rest is **worse** by 0.0017
   FP/start on the held-out 2024-2025 window.

The partial-r of -0.0007 is the cleanest single-number summary: the rp3
baseline already absorbs whatever signal days_rest could carry. The IL
feature triad (`is_on_il_at_split`, `days_since_il_return_imp`,
`il_stints_to`) handles the long-rest tail (post-IL), and the clamp to
[3, 7] deliberately suppresses the most extreme cases that might have
been informative.

## What this tells us

- The hypothesis that inter-start rest carries RoS-relevant signal
  beyond the IL features is **not supported** in 2018-2025 data.
- The convergence test shows no leakage signature — split_day=30 has
  the LARGEST in-sample lift (+0.0026), but it does not generalize when
  pooled.
- 6-man rotation moves, rainouts, and 4-vs-6 day rest variation
  apparently do not move the RoS needle in a way ridge regression can
  pick up. SPs are robust to ±2 day rest perturbations within the
  normal range, exactly the empirical conclusion of the Lichtman /
  Cameron rest research from the 2010s.

## Leakage audit

- `days_rest` at row (pitcher P, year Y, cutoff CD) was computed
  strictly from game_dates with date < CD. Verified in
  `build_days_rest_for_year` (`prior = [d for d in dates_sorted if d < cd]`).
- The most recent and second-most-recent dates are picked from this
  filtered list — no look-ahead to start N+1.
- Pitchers with < 2 prior starts get the neutral default of 5.
- Convergence at split_day 30 / 44 / 58 produced gains of
  +0.0026 / +0.0006 / +0.0008 — gains DECREASE with later cutoff,
  the opposite of the canonical leakage signature. Clean.

## Recommendation

Do NOT add `days_rest` to `RP3_FEATS`. Log this run in the rejected
section of `reference_validated_signals_registry.md`.

Alternative formulations that might be worth a future test (NOT
recommended for promotion today; would each need their own
pre-registration + Rule 9 baseline test):

1. **Interaction with IL features**: `days_rest * is_on_il_at_split` —
   capture the post-IL ramp specifically (the most likely productive
   slice of the rest signal).
2. **Rolling rest distribution** (e.g. coefficient of variation of
   inter-start intervals over the last 5 starts) — captures "irregular
   usage" rather than the most recent gap.
3. **Days-since-last-start** WITHOUT clamping — let extreme values
   speak for themselves, but with appropriate winsorization or a
   non-linear basis (kernel / spline).

## Files

- Validation script: `scripts/xfp/validate_days_rest.py`
- Pre-registration: `data/research/validation_runs/days_rest_2026-06-02.md`
- Raw results JSON: `data/research/validation_runs/days_rest_results.json`
- This report: `data/research/validation_runs/days_rest_validation.md`
