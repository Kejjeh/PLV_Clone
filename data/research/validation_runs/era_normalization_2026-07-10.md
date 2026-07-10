# Pre-registration: era normalization (league-environment drift) — 4 cells, Bonferroni 4

---
signal: era_normalization (E1 league_fp_env_to / E2 league_sp_fp_env_to / E3 prior_env_gap / E4 prior_env_gap_sp)
formula: see per-cell definitions below (exact, locked before any eval ran)
outcome: rh3 `ros_full_fp_per_pa` (E1/E3), rp3 `ros_fp_per_start` (E2/E4)
expected_sign: E1 +, E2 +, E3 −, E4 −
theory: league-environment drift across ball/rule eras (2019 juiced ball, 2021 dead ball,
  2023 rules package) mis-centers pooled priors/population means; the to-date league FP
  environment of the CURRENT year, and the environment SHIFT since the Marcel prior was
  earned, carry recoverable level signal for the RoS FP target (which is a LEVEL, not
  year-relative).
production_target: rh3 (E1, E3), rp3 (E2, E4)
framing: in-season → RoS (as-of split_day; env computed strictly to-date)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_era_normalization.py
date: 2026-07-10
verdict: E1 MARGINAL | E2 REJECTED | E3 REJECTED | E4 REJECTED (no promotion)
purpose: test the era-normalization hypothesis against the frozen production rate models;
  REJECTED is a fine outcome. Run alongside (but independent of) the concurrent regime
  DIAGNOSTIC and regime INTERACTION agents — this file owns exactly these 4 cells.
---

## Data provenance (verified during Step 2.5 coverage pre-check, before any eval)

- Hitter rolling substrate `rolling_hitters_2018_2026.csv`: `fp_total_to / pa_to ≡
  core_fp_per_pa_to` (max abs dev 9.7e-17) — the to-date FP columns are **CORE** FP
  (TB+BB+HBP+SB−K; no R/RBI). The rh3 target `ros_full_fp_per_pa` is FULL FP. The env
  feature is therefore denominated in core FP/PA; core and full league envs are near-
  proportional (see env table in results) and the Ridge standardizes, so the units gap is
  a level/scale issue only. Documented, accepted, not revisited after results.
- Pitcher rolling substrate has `fp_per_start_to` (full SP formula), same units as target.
- `hitters_multiyr_2015_2026.csv` has `core_fp_total`, `pa` for every year 2015–2026
  (2017 and 2020 both present → T−1 source exists for every TRAIN_YEAR).
- `sp_multiyr_2015_2025.csv` (despite filename) has years 2015–2026 with `fp_total`, `gs`.
- Coverage: env features are derived from the substrate itself → **100% row coverage,
  7/7 TRAIN_YEARS**, no join risk. Step 2.5 sample-coverage gate passes by construction.

## Cell definitions (exact)

Let a "cell" be one (candidate feature, production model) pair. All four candidates are
added ONE AT A TIME to the FULL production baseline (Rule 9): rh3 = all 21 `RH3_FEATS`,
rp3 = all 24 `RP3_FEATS`, via the production-parity harnesses
(`_validate_rh3_v3_helper.load_and_prep_rh3_inputs`, `_rp3_validation_harness.prep_rolling`)
and the models' own `cross_year_eval` LOO procedures.

### E1 (rh3) `league_fp_env_to`
For each rolling row i at (year, split_day): eligible set S = rows at the same
(year, split_day) with `pa_to ≥ 50` (the rh3 EVAL_PA_MIN). Feature =
leave-self-out PA-weighted league mean core FP/PA to-date:

    env_i = (Σ_{j∈S} fp_total_to_j − [i∈S]·fp_total_to_i) / (Σ_{j∈S} pa_to_j − [i∈S]·pa_to_i)

Strictly to-date (uses only data through the split cutoff) + leave-self-out → no leakage,
including no self-leakage. Expected sign **+**: a hot league year raises everyone's RoS
FP level, and the target is a level.

### E2 (rp3) `league_sp_fp_env_to`
Same construction on the pitcher substrate: S = rows at (year, split_day) with
`gs_to ≥ 2` (rp3 EVAL_GS_MIN); feature = leave-self-out GS-weighted mean of
`fp_per_start_to`:

    env_i = (Σ_{j∈S} fp_ps_to_j·gs_to_j − [i∈S]·own) / (Σ_{j∈S} gs_to_j − [i∈S]·gs_to_i)

Expected sign, reasoned and declared BEFORE running: the hypothesis "higher league
offense env → lower SP FP/start" is true, but this feature is denominated **in SP
FP/start units**, not offense units — a high-offense year shows up as a LOW value of
`league_sp_fp_env_to`. So the declared expectation is coefficient **+** (higher to-date
SP-FP environment → higher RoS SP FP/start). The offense-hurts-pitchers mechanism and
the + sign on this feature are the same statement.

### E3 (rh3) `prior_env_gap`
Environment shift since the Marcel prior was earned:

    prior_env_gap_i = env_year_H(T−1) − league_fp_env_to_i(T, split_day)

where env_year_H(Y) = Σ core_fp_total / Σ pa over ALL batter rows of hitters_multiyr in
year Y (PA-weighted, core units — same units and weighting as E1). Expected sign **−**:
a prior earned in a juiced year overstates talent in a deader year, so conditional on
`prior_fp_per_pa` (in the baseline), a positive gap should push the projection down.

Pre-acknowledged mis-measurements (locked now, not revisited after results):
- 2021 rows use T−1 = 2020 (60-game season) as the prior environment, per the literal
  T−1 definition — even though build_prior_table skips 2020, so the 2021 Marcel prior
  was mostly earned in 2019/2018. This makes E3 a NOISY measure for 2021 specifically.
- The Marcel prior is a 3-year blend; T−1 is a sharp but simplified proxy for "the
  environment the prior was earned in". We test the simple version only.

### E4 (rp3) `prior_env_gap_sp`
Same construction for SP: env_year_SP(T−1) − league_sp_fp_env_to(T, split_day), with
env_year_SP(Y) = Σ fp_total / Σ gs over sp_multiyr rows with gs ≥ 1 in year Y.
Expected sign **−**: a prior earned in a pitcher-friendlier (higher SP-FP) year
overstates the arm's RoS FP/start in a lower-SP-FP current environment.

## Gates (per cell; Bonferroni 4 — per house convention the Δr criterion is effect-size
based and unchanged under multiplicity; the 4-cell family is declared here so no cell
can be reported in isolation)

1. cross_year_r lift ≥ **+0.005** vs the FULL production baseline (Rule 9 hard bar).
2. Per-year sign consistency ≥ **5/7** TRAIN_YEARS positive.
3. Holdout **2024 AND 2025** lift positive (rh3 convention: both years; rp3 harness
   reports the 2024–25 average — we additionally require each year individually ≥ 0
   … declared now: BOTH years must be > 0 for a PASS in every cell).
4. Final-pipeline coefficient sign matches the declared expected sign.
5. Step 2.5 convergence across split_day bands (see identification note below):
   the per-band POOLED cross-year Δr must be same-sign (non-negative) in at least
   3 of 4 bands. Bands: split_day ≤ 60 / 61–105 / 106–150 / >150.

ALL five must hold for PASS; any structural failure → REJECTED; near-miss on gate 1
only, with 2–5 clean → MARGINAL.

## IMPORTANT DESIGN NOTE (identification under LOO — pre-registered honesty)

The env features are constant within a (year, split_day) cell (up to the leave-self-out
epsilon). Consequences, stated BEFORE running:

- Within a fixed (year, split_day) cell, Pearson r is invariant to adding a constant to
  all predictions — so the feature CANNOT improve within-cell ordering. Its
  identification comes from (a) **cross-year level differences** and (b) the
  **within-year split_day trajectory** of the to-date env.
- LOO holds out entire years, so (a) is exactly what the eval tests: the model learns
  the env→target level mapping on 6 years and must transfer it to the held-out year's
  env measured TO-DATE in that year. That is precisely the production use case — at
  projection time we know this year's env so far — so a positive pooled lift is honest,
  leakage-free evidence of era-normalization value; a null says the pooled prior is
  already adequately centered (or Ridge shrinkage eats a 7-point-effective-sample
  year-level signal).
- The per-year r rows in the harness output will understate the effect (within one
  held-out year the feature varies only through split_day drift); the POOLED overall r
  is the headline. Per-year signs (gate 2) remain required as pre-registered — if the
  candidate helps only via a year-level shift and per-year signs are ~coin-flip, that
  is a real (pre-acknowledged) way to fail: it would mean the lift doesn't survive the
  metric family we've committed to for every other candidate, and we do NOT swap
  metrics after seeing results.
- Rule 5 honesty: the cross-year level component has effectively **n = 7 year-level
  observations**. Small-n is intrinsic to any era feature; the sign-consistency and
  band-convergence gates are the honest checks, and a REJECTED verdict here does not
  preclude re-testing with more seasons of data.

## What was computed before this file was locked

Only Step 2.5 coverage facts: column inventories, the fp_total_to≡core identity, year
coverage of the multiyr caches, substrate row counts / split_day grids, and the
league-env-by-year table (a descriptive input to the feature, not an eval result).
NO cross_year_eval, correlation-vs-target, or lift number was computed before locking.

## Results (2026-07-10, script runs logged to .cache/test-logs/20260710T230800Z.log
and 20260710T230939Z.log)

### League env by year (derived, PA-/GS-weighted)

| year | hitter core FP/PA | SP FP/start |
|---|---|---|
| 2015 | 0.2592 | 11.320 |
| 2016 | 0.2672 | 10.700 |
| 2017 | 0.2723 | 10.228 |
| 2018 | 0.2514 | 11.060 |
| 2019 | 0.2666 | 10.521 |
| 2020 | 0.2533 | 10.562 |
| 2021 | 0.2444 | 10.707 |
| 2022 | 0.2365 | 11.074 |
| 2023 | 0.2586 | 10.416 |
| 2024 | 0.2446 | 11.019 |
| 2025 | 0.2521 | 10.657 |
| 2026 | 0.2543 (to-date) | 10.076 (to-date) |

Real era drift exists (hitter env swings ~12% peak-to-trough, 2019 juiced 0.2666 vs 2022
dead 0.2365; SP env anti-correlates as expected). Step 2.5: 0 NaN rows in all 4
candidate columns, 7/7 TRAIN_YEARS covered.

### Per-cell outcomes (candidate added to FULL production baseline, LOO cross_year_eval)

| cell | baseline r | +cand r | lift | signs | holdout 24 / 25 | coef (exp) | bands (sd 0-60/61-105/106-150/151+) | verdict |
|---|---|---|---|---|---|---|---|---|
| E1 rh3 league_fp_env_to | 0.6338 (n=36,571) | 0.6364 | **+0.0026** | 5/7 | +0.0008 / +0.0023 | +0.0078 (+) OK | +0.0015 / +0.0025 / +0.0024 / **−0.0101** | **MARGINAL** |
| E2 rp3 league_sp_fp_env_to | 0.5614 (n=19,111) | 0.5631 | +0.0017 | 4/7 | +0.0007 / +0.0002 | **−0.1430 (+) WRONG SIGN** | +0.0020 / +0.0029 / −0.0020 / −0.0011 | REJECTED |
| E3 rh3 prior_env_gap | 0.6338 | 0.6337 | −0.0001 | 3/7 | −0.0004 / +0.0014 | −0.0053 (−) OK | −0.0004 / −0.0012 / +0.0009 / −0.0022 | REJECTED |
| E4 rp3 prior_env_gap_sp | 0.5614 | 0.5610 | −0.0004 | 4/7 | +0.0003 / +0.0003 | **+0.0845 (−) WRONG SIGN** | +0.0011 / +0.0011 / −0.0011 / −0.0014 | REJECTED |

### Interpretation

- **E1 is the only live signal and it is sub-gate**: +0.0026 vs the +0.005 bar, with
  clean signs (5/7), clean holdout (2/2), correct + coef, and positive convergence in
  3/4 bands — but a decisive late-season reversal (sd>150: −0.0101), consistent with
  the to-date env being least informative for the small residual RoS window. Under the
  pre-registered Bonferroni-4 family, a sub-gate lift does not promote. NOT added to
  RH3_FEATS.
- **E2's coefficient came out NEGATIVE** (higher to-date SP-FP environment → LOWER RoS
  FP/start conditional on the full baseline) — the opposite of the level-transfer
  hypothesis and the pre-declared sign. This is a mean-reversion signature: whatever
  small env information exists, the baseline's own fp_per_start_to / priors already
  carry the level, and the residual env term flips to a regression-to-mean correction.
  Wrong-sign + 4/7 + sub-gate = decisive rejection, not a near-miss.
- **E3/E4 (the sharpest "different balls" test — env shift since the prior was earned)
  are nulls**: lifts −0.0001 / −0.0004, sign consistency at coin-flip, E4 coef
  wrong-sign. The Marcel prior's own league_mean_by_year centering (build_prior_table
  regresses toward the TARGET year's league mean, not the pooled mean) apparently
  already handles most prior-era mis-centering — the hypothesized recoverable signal
  is not there at the model's noise floor.
- **Conclusion for the era-normalization hypothesis**: pooled priors/population means
  are NOT measurably mis-centered by era drift as far as the LOO cross-year target can
  detect. The one residual thread (E1's current-year hitter env, early/mid-season) is
  real-looking but ~half the gate; a future re-test with more seasons (n>7 year-level
  observations) is the only plausible path, and it would need the late-season reversal
  to resolve. No integration recipe applies — nothing passed.
