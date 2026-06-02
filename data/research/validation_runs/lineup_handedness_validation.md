---
signal: lineup_handedness_match
target: rp3
verdict: REJECTED
date: 2026-06-02
pre_registration: data/research/validation_runs/lineup_handedness_2026-06-02.md
validation_script: scripts/xfp/validate_lineup_handedness.py
results_json: data/research/validation_runs/lineup_handedness_results.json
---

# lineup_handedness_match — Validation report (2026-06-02)

## Pre-registered hypothesis (timestamped before any model run)

> Season-to-date fraction of PAs where opposing `batter.stand` matches
> the SP's `p_throws` will carry RoS-relevant information beyond what
> is already captured by `ros_opp_xwoba_weighted` and the existing
> rp3 baseline. Expected sign: positive (more same-handed matchups
> → platoon advantage to pitcher → higher ros_fp_per_start). Production
> gate: cross-year r lift ≥ +0.005, sign-consistent in ≥5 of 7 years,
> holdout 2024-2025 lift > 0, MAE on holdout improves, partial r vs
> full baseline ≥ +0.02.

Full pre-registration in `lineup_handedness_2026-06-02.md` (written
before the script was run).

## Backtest setup

- **Substrate:** `rolling_pitchers_2018_2026.csv` (29,493 rows) prepped
  through `_rp3_validation_harness.prep_rolling()`. Includes the
  previously-validated `ros_opp_xwoba_weighted` in the baseline.
- **Baseline:** full 24-feature RP3_FEATS. **No stripping** (Rule 9).
- **Candidate:** `lineup_handedness_match` computed per (pitcher, year,
  cutoff_date) from `statcast_YYYY.parquet`. Reduced to one row per PA
  via `drop_duplicates(['pitcher', 'game_pk', 'at_bat_number'])`. Same-handed
  flag = `(stand == p_throws)`. Pitchers with < 50 prior PAs at cutoff
  get population-mean default (estimated from training years only:
  **0.4679**).
- **Eval:** leave-one-year-out cross-year RidgeCV. Pooled eval n = 19,111.
- **Holdout:** 2024 + 2025.
- **Convergence:** split_day 30 / 44 / 58.

## Feature distribution

- Pre-merge panel (n=141,847): 42.4% fall at the default (low PA early
  in season), 57.6% are real measurements.
- Real (non-default) distribution: mean 0.485, std 0.132, range
  [0.023, 0.889]. This range reflects that LHP face ~30-45% L-handed
  bats (since most lineups are R-skewed by ~60/40) while RHP face
  ~55-65% R-handed bats. The two pitcher-handedness regimes give a
  bimodal shape, but the overall mean of 0.49 is consistent with mixed
  populations.
- Post-merge into rolling (n=29,493): only 3.4% fall at the default
  (the rolling substrate is biased toward established SPs with plenty
  of pre-cutoff PA).
- Population default of 0.4679 (training-years-only) intentionally does
  NOT use 2024-2025 data — leakage discipline.

## Headline numbers

| Metric | Baseline | Baseline + lineup_handedness | Gain |
|---|---|---|---|
| Pooled cross-year r (LOO-CV, all years) | 0.5548 | 0.5542 | **-0.0006** |
| Holdout 2024-25 avg r lift | — | — | **+0.0010** |
| Holdout 2024-25 MAE (FP/start) | 2.7738 | 2.7710 | **+0.0028 (better)** |
| Partial r vs full baseline (pooled LOO residuals) | — | — | **-0.0131** |

Per-year r gain (full minus baseline):

| Year | r gain |
|---|---|
| 2018 | +0.0005 |
| 2019 | **-0.0039** |
| 2021 | +0.0001 |
| 2022 | -0.0001 |
| 2023 | **-0.0021** |
| **2024** | **+0.0010** |
| **2025** | **+0.0009** |

**Sign consistency: 4 / 7 years positive** (below the 5/7 bar).

## Convergence check (split_day 30 / 44 / 58)

| split_day | r baseline | r full | r gain | MAE gain |
|---|---|---|---|---|
| 30 | 0.5766 | 0.5748 | **-0.0018** | -0.0022 |
| 44 | 0.5725 | 0.5719 | **-0.0006** | -0.0041 |
| 58 | 0.5655 | 0.5636 | **-0.0019** | -0.0045 |

All three split_days produce negative r gains and negative MAE gains.
The lifts are NOT inflated at later split_days (no monotonic increase),
which would have been the canonical leakage signature. **No leakage
smell detected.** The signal is genuinely redundant with the existing
baseline.

## Partial r vs full baseline

Partial r of lineup_handedness_match vs the full RP3_FEATS baseline:
**-0.0131** (small, negative). After controlling for the existing 24
features (especially `ros_opp_xwoba_weighted`, which captures the
strength dimension of the schedule), the handedness mix provides
**slightly negative** added information cross-year. This is the
clearest single-number summary of the pre-stated confound: the rp3
baseline already absorbs the team-strength channel through which
handedness might have shown up.

## Honest verdict: **DON'T SHIP** (REJECTED)

lineup_handedness_match fails three of four pre-committed gates:

1. **Lift bar:** -0.0006 < +0.005 production gate (FAIL).
2. **Year consistency:** 4/7 positive years; bar is ≥5/7 (FAIL).
3. **Holdout sign:** +0.0010 (PASS on this single gate).
4. **MAE on holdout:** Baseline + handedness IS better by 0.0028
   FP/start on 2024-25 (PASS on this single gate).
5. **Partial r ≥ +0.02 (pre-stated bar):** -0.0131 (FAIL — wrong sign).

The convergence-panel result is unambiguous — three negative split-day
gains. The 2024-25 PASS on holdout and MAE is at odds with the
all-year pooled metric, the convergence panel, and the partial-r —
classic noise-pattern (a feature with no real signal can still produce
a small positive holdout reading by chance, especially with only two
held years averaged).

## Confound analysis: re-discovering team strength?

The pre-registration explicitly flagged this concern. Evidence:

- Partial r is **-0.0131**, not positive. If the signal were
  re-encoding team-strength info already in `ros_opp_xwoba_weighted`,
  the partial r would be ≈ 0 (orthogonal residual). The slightly
  negative number suggests it's mildly redundant in a way that hurts
  the ridge fit (correlated noise wastes degrees of freedom).
- 2019 (-0.0039) and 2023 (-0.0021) are the worst years; both are
  high-offense seasons where lineup composition variance is wider.
  This is consistent with the handedness frame adding noise the model
  has to fit against.

So lineup_handedness is not just redundant with team strength — it
appears to add a small amount of noise on top of the baseline.

## What this tells us

- Handedness composition of faced batters does NOT carry independent
  RoS predictive signal once the rp3 baseline (especially the schedule-
  strength `ros_opp_xwoba_weighted` term) is accounted for.
- The hypothesis that "platoon-favorable batter mix → inflated SP
  counting stats → predictive of regression" is **not supported**.
- The empirical story is that pitcher-handedness × batter-handedness
  effects are real (this is well established in the splits literature)
  but already absorbed by the joint xwOBA-by-handedness data that
  flows into per-team opponent xwOBA aggregates.

## Leakage audit

- `lineup_handedness_match` at row (pitcher P, year Y, cutoff CD) used
  only statcast PAs with game_date strictly < CD.
- Reduced to one row per PA via `drop_duplicates(['pitcher', 'game_pk',
  'at_bat_number'])` — no pitch-count double-counting.
- Population-mean default (0.4679) computed from TRAINING YEARS ONLY
  (2018, 2019, 2021, 2022, 2023). 2024 and 2025 were not touched.
- Convergence: -0.0018 / -0.0006 / -0.0019 across split_day 30 / 44 / 58.
  No monotonic inflation. Clean.

## Recommendation

Do NOT add `lineup_handedness_match` to `RP3_FEATS`. Log this run in
the rejected section of `reference_validated_signals_registry.md`.

Alternative formulations that might be worth a future test (NOT
recommended for promotion today):

1. **Forward-looking** RoS handedness match (using already-rostered
   opponents' season-to-date handedness composition, weighted by RoS
   schedule). This is fundamentally different from the season-to-date
   handedness used here — and would be conceptually orthogonal to
   `ros_opp_xwoba_weighted` only if opponent xwOBA is computed against
   league-average pitchers rather than handedness-stratified pitchers.
2. **Per-handedness wOBA-against** for the SP (woba_vR_to / woba_vL_to)
   as features — these are direct platoon-split skill measurements,
   not opponent-composition measurements. Likely to be redundant with
   the existing shrunken xwOBA features but worth checking.
3. **Handedness mismatch with park / weather** (e.g. RHP × Cole Park
   short-porch right field) — interaction features that get at park
   factors stratified by handedness. Niche and difficult to compute
   cleanly.

None of these is recommended for promotion today.

## Files

- Validation script: `scripts/xfp/validate_lineup_handedness.py`
- Pre-registration: `data/research/validation_runs/lineup_handedness_2026-06-02.md`
- Raw results JSON: `data/research/validation_runs/lineup_handedness_results.json`
- This report: `data/research/validation_runs/lineup_handedness_validation.md`
