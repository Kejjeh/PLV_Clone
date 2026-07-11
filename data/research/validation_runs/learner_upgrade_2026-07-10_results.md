# RESULTS: LEARNER UPGRADE test (Ridge → gradient boosting) — 2026-07-10

**Pre-registration:** `learner_upgrade_2026-07-10.md` (written before any run;
no grid change, no weight change, no filter change after results were seen).
**Engine:** `scripts/xfp/validate_learner_upgrade.py`
**Per-cell JSON:** `learner_upgrade_2026-07-10_rh3_results.json`,
`learner_upgrade_2026-07-10_rp3_results.json`

## Verdict: ALL FOUR CELLS REJECTED

| Cell | Learner | Pooled r | Lift vs Ridge | Signs | Holdout 24/25 | Verdict |
|------|---------|----------|---------------|-------|----------------|---------|
| — | rh3 Ridge (baseline of record) | **0.6275** (n=36,571, MAE 0.0861) | — | — | — | — |
| L1 | rh3 HistGB | 0.5738 (MAE 0.0915) | **−0.0537** | 1/7 | +0.0023 / −0.0753 | REJECTED |
| L3 | rh3 blend 0.5/0.5 | 0.6257 (MAE 0.0863) | **−0.0018** | 3/7 | +0.0314 / −0.0118 | REJECTED |
| — | rp3 Ridge (baseline of record) | **0.5614** (n=19,111, MAE 2.8403) | — | — | — | — |
| L2 | rp3 HistGB | 0.4742 (MAE 3.0870) | **−0.0872** | 0/7 | −0.0236 / −0.1002 | REJECTED |
| L4 | rp3 blend 0.5/0.5 | 0.5409 (MAE 2.8918) | **−0.0206** | 1/7 | +0.0140 / −0.0282 | REJECTED |

Measured Ridge baselines matched expectation exactly (0.6275 / 0.5614), so the
comparison ran on the intended data (frame frozen to a pickle before fold 1;
rh3 n filtered 38,083 → 36,571 pooled across the 7 LOO test years).

## Per-year r

rh3: GBM lost 6/7 years (only 2024 +0.0023); worst −0.0753 (2025).
rp3: GBM lost 7/7 years; worst −0.1123 (2019).
Blend recovered most of the damage but never cleared the Ridge baseline
pooled (best single years: rh3 2024 +0.0314, rp3 2024 +0.0140 — isolated).

## Pre-registered honesty checks

- **(a) Overfit:** mean in-sample-minus-held-out r gap: Ridge +0.006 (rh3) /
  +0.009 (rp3) vs GBM **+0.386 (rh3) / +0.494 (rp3)**. The GBM memorizes
  year idiosyncrasies (in-sample r ≈ 0.96 both models) that do not transfer
  across seasons.
- **(b) Tails:** GBM materially distorts both tails. rp3 decile-1 bias
  −1.80 FP/start (Ridge −0.18), decile-10 +0.92 (Ridge −0.28); rh3 decile-1
  −0.032 FP/PA (Ridge −0.005), decile-10 +0.026 (Ridge −0.008). GBM is
  over-confident exactly where the league is played.
- **(c) Stability:** seed spread 0.0000 both models (deterministic given
  config; not a variance issue — the failure is bias/transfer, not seed noise).

## Notes

- Inner 3-fold CV (shuffled, train-years only, per protocol) selected the MOST
  flexible grid corner in all 14 folds (`lr=0.1, max_iter=500, leaves=31,
  min_samples_leaf=50`). The conservative corners were available and rejected:
  within-mixed-year CV rewards flexibility that does not survive the
  year-to-year distribution shift — the same signature as the overfit gap.
  This is an observation, not a protocol deviation.
- Runtime: ~6-13 s per fold for the full 16-config grid; no grid cut invoked.

## Interpretation (per pre-declared ladder)

**REJECTED — linear is enough on these features.** On the current 21/24
engineered, shrunken, already-nonlinearly-transformed features, gradient
boosting finds no exploitable nonlinearity that generalizes across seasons;
even the diversity-ensemble blend is slightly negative. This is itself the
valuable result: future cross-year r gains for rh3/rp3 must come from
**FEATURES / DATA, not learner upgrades**. Do not re-attempt tree learners /
GBM / "just try XGBoost" on the same feature set — this is the documented
dead end (registry family: `learner_upgrade`).

No integration recipe (no cell passed). No production code touched.
