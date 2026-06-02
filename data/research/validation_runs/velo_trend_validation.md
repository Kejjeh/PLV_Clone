---
signal: velo_trend
target: rp3
verdict: REJECTED
date: 2026-06-02
pre_registration: data/research/validation_runs/velo_trend_2026-06-02.md
validation_script: scripts/xfp/validate_velo_trend.py
results_json: data/research/validation_runs/velo_trend_results.json
---

# velo_trend — Validation report (2026-06-02)

## Pre-registered hypothesis (timestamped before any model run)

> Recent-3-start mean velocity of an SP's primary pitch type, minus that SP's
> season-to-date mean velocity on the same pitch, will positively predict
> rest-of-season FP/start when ADDED to the full RP3_FEATS production baseline,
> because it captures arm-state drift that the existing `delta_velo` (mix-blended,
> 21-day calendar window) dilutes. Expected sign: positive. Production gate:
> partial r ≥ +0.02 / lift ≥ +0.005 / sign-consistent across ≥ 5 of 7 years /
> holdout 2024-2025 lift > 0.

Full pre-registration with theory, framing, leakage discipline, and decision
rules in `velo_trend_2026-06-02.md` (written before the script was run).

## Backtest setup

- **Substrate:** `rolling_pitchers_2018_2026.csv` (29,493 rows), prepped through
  the production `_rp3_validation_harness.prep_rolling()` pipeline so the
  baseline has every derived feature that production `rp3.py` uses
  (Marcel prior, shrinkage `_to_sh` features, IL features, all 6 drift deltas,
  `ros_opp_xwoba_weighted`).
- **Baseline:** full 24-feature RP3_FEATS as defined in
  `src/plv_clone/models/xfp/rp3.py` lines 73-96. **No stripping** (Rule 9).
- **Candidate:** `velo_trend` computed from `statcast_YYYY.parquet` files
  per (pitcher, year, cutoff_date). Primary pitch = most-thrown pitch type
  on pitches strictly before cutoff. Pitchers with < 3 prior starts → 0
  (neutral). Coverage post-merge: 94.1% of rolling rows have non-zero
  velo_trend (rows below threshold are early-season minimum-start cases).
- **Eval:** leave-one-year-out cross-year RidgeCV (the production
  `cross_year_eval` flow, identical to how every other rp3 candidate gets
  scored), filtered to `gs_to ≥ 2` and `ros_gs ≥ 5`. 2020 excluded.
  Pooled eval n = 19,111.
- **Holdout:** 2024 + 2025 carved out as the held-year folds.
- **Convergence check:** the same eval restricted to single split_days
  30 / 44 / 58 (closest grid match to the requested 30/42/56 — the
  rolling cache snaps to a 7-day grid).

## Feature distribution

- mean: +0.058 mph, std: 0.447 mph, range: large but tight tails.
- 66.9% of rows have nonzero velo_trend (pre-merge); after the
  rolling-row join the rate becomes 94.1% because most rolling rows are
  later-season cutoffs where every healthy SP has ≥3 prior starts.
- Sign distribution is roughly balanced — most SPs sit within ±0.5 mph
  of their season norm over a 3-start window, exactly as expected.

## Headline numbers

| Metric | Baseline | Baseline + velo_trend | Gain |
|---|---|---|---|
| Pooled cross-year r (LOO-CV, all years) | 0.5548 | 0.5562 | **+0.0014** |
| Holdout 2024-25 avg r | (see below) | (see below) | **-0.0003** |
| Holdout 2024-25 MAE (FP/start) | 2.7738 | 2.7801 | **-0.0063 (WORSE)** |
| Partial r vs full baseline (pooled LOO residuals) | — | — | **+0.0474** |

Per-year r gain (full minus baseline):

| Year | r gain |
|---|---|
| 2018 | +0.0049 |
| 2019 | +0.0014 |
| 2021 | -0.0002 |
| 2022 | -0.0002 |
| 2023 | +0.0042 |
| **2024** | **+0.0013** |
| **2025** | **-0.0019** |

**Sign consistency: 4 / 7 years positive** (below the 5/7 bar).

## Convergence check (split_day 30 / 44 / 58)

| split_day | r baseline | r full | r gain | MAE gain |
|---|---|---|---|---|
| 30 | 0.5766 | 0.5748 | **-0.0018** | -0.0060 |
| 44 | 0.5725 | 0.5721 | **-0.0004** | -0.0009 |
| 58 | 0.5655 | 0.5651 | **-0.0004** | -0.0030 |

All three split_days produce negative gains. The lifts are NOT inflated at
later split_days — if anything they are slightly worse at the earliest
split_day. **No leakage smell detected.** This is consistent with a real
"the signal is just noise / redundant" verdict rather than a
"leakage was inflating an apparent signal" verdict.

## Partial r ≠ held-out r gain (the key insight)

Partial r of velo_trend vs the full baseline (computed by regressing
out the full baseline from both `y` and `pred_full`, then correlating
the residuals across all LOO-CV held-year predictions): **+0.0474**.

That looks promising in isolation, but it does NOT survive into the
held-out cross-year evaluation: the pooled r gain is only +0.0014 and
the holdout-specific gain is negative. This is a classic case where a
small residual correlation exists but the existing baseline already
contains most of the same information (via `delta_velo`, `avg_velo_to`,
the shrunken whiff/zone metrics, and the recency drift quartet). The
RidgeCV can't extract incremental cross-year predictive value from
that residual because the baseline already eats most of the signal in
training and the marginal piece doesn't generalise.

## Honest verdict: **DON'T SHIP** (REJECTED)

velo_trend fails all four pre-committed gates:

1. **Lift bar:** +0.0014 < +0.005 production gate (and far below the
   +0.02 partial-r bar from the task brief).
2. **Year consistency:** 4/7 positive years; bar is ≥5/7.
3. **Holdout sign:** -0.0003 (wrong sign on 2024-2025 average).
4. **MAE on holdout:** baseline + velo_trend is **worse** by 0.0063
   FP/start on the held-out 2024-2025 window.

The convergence panel additionally shows velo_trend is REJECTED at
every split_day tested, not just on the pooled number.

## What this tells us

The hypothesis (primary-pitch start-window velo drift carries
arm-state information that mix-blended calendar-window `delta_velo`
misses) is **not supported empirically against the full rp3 baseline**.
The existing `delta_velo` + `avg_velo_to` pair, combined with the
shrunken contact/whiff features, already absorb the predictive content
that velo_trend would have added. A non-trivial partial r exists in
in-sample residual space, but it doesn't generalise across years —
exactly the pattern Rule 9 was designed to detect.

This result is consistent with the 2026-05-24 `avg_velo_last21` MARGINAL
verdict (+0.0021 pooled, just-under-gate). Both candidates probe the
same construct (within-season velocity recency) from different angles
and both come up short against the full production baseline. The
takeaway: rp3's velocity sub-model is essentially saturated by
(`avg_velo_to`, `delta_velo`) and adding more velocity recency
encodings is unlikely to move the needle. Future velo-related gains
will need to come from a different mechanism (e.g., pitch-specific
movement deltas, stuff-shape signals) rather than from another framing
of the same recency information.

## Leakage audit

- velo_trend at row (pitcher P, year Y, cutoff_date CD) was computed
  strictly from pitches with game_date < CD. Verified in
  `build_velo_trend_for_year` (`prior = sub[sub['game_date'] < cd]`).
- Primary pitch was determined from pre-cutoff pitches only.
- Pitchers with < 3 prior starts received `velo_trend = 0`, so no
  small-sample tails contaminate the signal.
- Convergence at split_day 30 / 44 / 58 produced gains of
  -0.0018 / -0.0004 / -0.0004 — there is no monotonic increase in
  lift with later cutoff date, which is the signature pattern the
  convergence-curve test was designed to surface (see
  `feedback_convergence_curve_leakage_detector.md`). Clean.

## Recommendation

Do NOT add `velo_trend` to `RP3_FEATS`. Log this run in the rejected
section of `reference_validated_signals_registry.md`.

If the user wants to revisit the within-season velocity-recency
question, the most likely productive variant would test:

1. **Pitch-specific velo delta** *normalised by within-arsenal SD*
   rather than absolute mph (controls for between-pitcher velo
   variance baselines).
2. **A non-linear transform** of recent vs season velo (e.g., the
   absolute drop rather than signed drop — fatigue cuts both ways
   when reading "below own norm" but the cost is asymmetric).
3. **Interaction with start count / fatigue load** — a 1 mph drop
   after 5 starts may mean nothing; a 1 mph drop after 18 starts may
   mean a lot.

None of these is recommended for promotion today; they would each need
their own pre-registration + Rule 9 baseline test.

## Files

- Validation script: `scripts/xfp/validate_velo_trend.py`
- Pre-registration: `data/research/validation_runs/velo_trend_2026-06-02.md`
- Raw results JSON: `data/research/validation_runs/velo_trend_results.json`
- This report: `data/research/validation_runs/velo_trend_validation.md`
