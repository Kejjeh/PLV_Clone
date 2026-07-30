---
signal: rp_band_crps (distributional calibration of the RELIEVER predictive band, single-appearance frame)
formula: >
  Per forecast row with predictive mean mu, scale s, realized single-appearance
  FP y (fp_rp from boxscore_pitchers.parquet, gs == 0 — SV/HLD credit already
  inside):
    z = (y - mu) / s
    CRPS_N(mu, s, y) = s * ( z*(2*Phi(z) - 1) + 2*phi(z) - 1/sqrt(pi) )
  (closed-form Gaussian CRPS, Gneiting & Raftery 2007 eq. 21; properscoring is
  not installed so it is hand-rolled on scipy.stats.norm, identical to
  validate_band_crps.py.)
  The production RP draw is NOT Gaussian — leverage_engine._rp_total_draws calls
  _blend_draws(rng, emp, mean_app, sigma_app, K_PRIOR_RP=10, n), a MIXTURE:
  with prob w = n_emp/(n_emp+10) bootstrap the pitcher's own last-20 relief FP,
  else draw N(mu, s). That mixture is scored with the fair ensemble estimator
    CRPS_E = (1/m) sum|x_j - y| - (1/(2 m^2)) sum_j sum_k |x_j - x_k|
  evaluated in O(m log m) via the sorted identity
    sum_j sum_k |x_j - x_k| = 2 * sum_j (2j - m - 1) * x_(j),  j = 1..m.
  Pinball at q against the band edge qhat = mu +/- 0.6745*s:
    L_q(y, qhat) = max( q*(y - qhat), (q-1)*(y - qhat) )
  Coverage: cov50 = 1[mu-0.6745s <= y <= mu+0.6745s];
            cov80 = 1[mu-1.2816s <= y <= mu+1.2816s].
  Rows with s <= 0 or non-finite are DROPPED (never floored) and the drop count
  reported. A non-positive implied band width RAISES rather than propagating a
  negative sigma (House Rule 1).
outcome: >
  y = FP of the FIRST relief appearance strictly after the snapshot date, per
  (snapshot_date, reliever). One row per pair; cluster = mlbam_id.
expected_sign: >
  NO directional prior is asserted on the primary contrasts — this is a
  measurement study and "production is fine" is a fully pre-accepted outcome,
  matching the 2026-07-10 and 2026-07-29 NO-CHANGE precedents. The single
  arithmetic expectation stated in advance (see "Frame arithmetic" below) is
  that the band-implied per-appearance sigma S_BAND will be FAR too wide,
  because it descends from a season-TOTAL residual sigma.
theory: >
  This is the one predictive interval in the repo with no calibration evidence
  at all. band_crps_calibration_2026-07-29.md declared rprs2 UNSCORABLE in
  season because rprs2 publishes a REST-OF-SEASON TOTAL band (xfp_ros_p25/p75)
  that cannot be scored against a partial-season actual. That reasoning is
  correct for the RoS frame and irrelevant for the frame the MC actually draws
  in: leverage_engine draws ONE APPEARANCE at a time, so a single-appearance
  panel is directly scorable with no frame mismatch. Every P(win) number that
  includes a reliever inherits whatever this scale is.
production_target: research-only (RECOMMEND only; this study edits no production file)
framing: in-season measurement, single-appearance frame
holdout_years: [2026]
training_years: [2026]
validation_script: scripts/xfp/validate_rp_band_crps.py
date: 2026-07-30
verdict: >
  CONFOUNDED (location first) — NO production sigma change. The RP band IS
  measurably too narrow in the single-appearance frame (c* = 1.5-1.7 vs the
  production 1.0; cov50 35.5% against a nominal 50%), and R1 passes the
  economic, CI and BH gates at -2.82%. But the pre-registered R4 stopping rule
  fired (|dCRPS(R4)| = 0.535 >= |dCRPS(R1)| = 0.066) and mu_PROD is measurably
  21.5% low, so the scale claim is not separable from the location error on
  this panel. SEPARATE UNAMBIGUOUS DEFECT, recommended for fix:
  run_season_sim.py:288-290 feeds the rprs2 SEASON-TOTAL band sigma (~42.5 FP)
  into a PER-APPEARANCE slot — +311% CRPS, 100.0% cov50 — and the same
  expression can emit a negative sigma that _blend_draws silently clamps to
  1e-6. This study implements nothing; recommendations only.
---

# I4 — the RP predictive band, measured for the first time

`data/outputs/xfp_rprs2_projections.csv` has shipped `xfp_ros_p25` /
`xfp_ros_p75` all season and **no one has ever scored them**. This study scores
the reliever forecast in the frame the Monte Carlo actually uses.

## Note on holdout_years / training_years

Both are `[2026]` **deliberately and literally**: this panel is a single
in-season window, not a year split. The prior-art memos in this directory carry
`[2024, 2025]` for schema consistency with the model bundles; a 2026-07-29
review flagged that as boilerplate when the panel was in-season, so the ACTUAL
window is stated here instead:

- **snapshot dates:** 2026-06-04 .. 2026-07-29 (45 dates, every date present in
  `data/research/player_projection_history.parquet`)
- **outcome dates:** 2026-06-05 .. 2026-07-29 (`boxscore_pitchers.parquet`,
  `gs == 0`)
- **the split that does the work** is a TEMPORAL split *within* that window: the
  first 60% of snapshot dates are TRAIN, the last 40% TEST. `c*` is fitted on
  TRAIN only and every gated number is read off TEST. No row is in both.

## What production actually does (established by reading the code, not assumed)

Three separate facts, all verified before the panel was built, because the study
is only meaningful if it scores the real scale:

1. **`scripts/xfp/build_matchup_dashboard.py:568` derives an RP sigma as
   `(xfp_p75 - xfp_p25) / 1.35` — and that value is DEAD.** It is stored into
   `rprs2_map[nk]['sigma']` and never read. The only `.get('sigma')` in the file
   (line 1282) reads `rp_info` from **`rp3_map`**, in the SP branch. The RP
   branch (lines 1301-1323) reads exactly three keys from `rprs2_map`: `role`,
   `mlbam`, `xfp_ros`. The 2026-07-29 memo's §4 claim that this derived sigma
   "feeds P(win)" is **incorrect** and is corrected here.
2. **The scale that production actually draws is the flat constant
   `SIGMA_PER_RP_GAME = 2.5`** (`build_matchup_dashboard.py:343`), passed as
   `rp_sigma=SIGMA_PER_RP_GAME` at line 1319 into
   `matchup_projection.project_rp`, which sets `sigma2 = expected_appearances *
   sigma**2`. `leverage_engine.py:388` then back-derives
   `sigma_app = sqrt(sigma2 / units)`, which is algebraically **2.5 exactly**.
   So the per-appearance scale feeding `_rp_total_draws` is 2.5 FP for every
   reliever in the league.
3. **The location is
   `mu_app = (xfp_ros / days_remaining_season) / cfg.default_rp_app_rate`**,
   `default_rp_app_rate = 0.35`, `days_remaining_season = (2026-09-28 - today)`
   in CALENDAR days (`matchup_projection.py:373-376`).

Therefore the honest object of study is **N(mu_PROD, 2.5) per appearance**, and
`(p75 - p25)/1.35` is a *candidate* to be scored against it, not the incumbent.

## The declared assumption, and how its influence is bounded

Getting from the published RoS-TOTAL band to a per-appearance scale requires an
assumption. Declared here, before results:

> **A1 (independence).** Var(RoS total) = N_exp x Var(one appearance), so
> `S_BAND = ((xfp_ros_p75 - xfp_ros_p25) / 1.35) / sqrt(N_exp)`, with
> `N_exp = proj_volume x days_rem x 0.8747`.

`0.8747` is **measured**, not assumed: team-games per team per calendar day over
the 124 played dates in `boxscore_pitchers.parquet` (26.242 team-games/day / 30
teams). A1 is optimistic — real appearance FP is positively correlated within a
pitcher-season through role and health — so S_BAND is if anything an
UNDER-statement of the band's implied per-appearance width.

**A1 only enters cell R2.** R1, R3 and R4 never touch the published band and are
therefore assumption-free with respect to A1. This is the structural answer to
"if the assumption drives the answer, say so": the headline deliverable (`c*`)
is computed on the production scale, which needs no conversion at all.

A second declared choice, which DOES touch the headline:

> **A2 (location).** `mu_PROD` is production's own formula. It is not
> guaranteed unbiased, and CRPS scores location and scale jointly, so a biased
> mu inflates `c*`. Cell **R4** measures exactly this by contrasting `mu_PROD`
> against a volume-consistent `mu_VOL = xfp_ros / N_exp`. **Pre-declared
> stopping rule: if |dCRPS(R4)| >= |dCRPS(R1)|, the location specification is
> the larger lever and `c*` is reported as CONFOUNDED, not as a calibration
> result.**

## Declared cells

### Primary — 4 cells, BH-FDR q=0.05 across them

| # | rows | A (incumbent) | B (alternative) |
|---|---|---|---|
| R1 | TEST snapshots, Gaussian, mu_PROD | s = 2.5 | s = c*_train x 2.5 |
| R2 | all rows with a usable band, Gaussian, mu_PROD | s = 2.5 | s = S_BAND (assumption A1) |
| R3 | TEST snapshots, **production MIXTURE** sampler, mu_PROD | s = 2.5 | s = c*mix_train x 2.5 |
| R4 | TEST snapshots with volume, Gaussian, s = 2.5 | mu = mu_PROD | mu = mu_VOL |

R3 is the decision-relevant cell: it is literally `_blend_draws`, including the
`w = n_emp/(n_emp+10)` empirical bootstrap of the pitcher's own last-20
appearances, built **strictly before the snapshot date** (leakage guard —
`emp_series(..., before=snapshot_date)`).

### Descriptive — reported, NOT gated, NOT counted in FDR

- Full `c` -> CRPS curve on TRAIN and TEST, Gaussian and mixture, `c` in
  [0.40, 4.00] step 0.02.
- CRPS / pinball(.25) / pinball(.75) / cov50 / cov80 per band, with n.
- Slices: projection tercile, snapshot-to-appearance gap bucket (1d / 2-3d /
  4-7d / 8+d), and prior-appearance-count bucket (the mixture weight driver).
- Pooled within-pitcher per-appearance SD as a model-free reference.
- The 5 production rows whose published band has `p75 < p25`.

## Multiplicity control

1. **Paired bootstrap clustered by `mlbam_id`**, 2000 resamples, seed 20260730,
   on the per-row CRPS difference (B - A). 95% percentile CI, two-sided
   bootstrap p (share of resamples on the wrong side of 0, doubled).
2. **Benjamini-Hochberg at q = 0.05 across the 4 primary cells.**
3. **Economic floor: relative CRPS improvement |dCRPS| / CRPS_A >= 2%.**
4. **Rule 5 sample honesty: a cell with fewer than 200 clustered relievers is
   labelled UNDERPOWERED rather than tested-and-failed** — the same floor the
   2026-07-29 sibling declared and then honestly applied to its own n=173 cell.

## Decision rule (declared BEFORE results)

A **RECOMMENDATION** to change the production RP scale is written only if ALL of:

- (a) R1 relative CRPS improvement >= 2%, AND
- (b) R1 clustered bootstrap 95% CI excludes 0, AND
- (c) R1 survives BH-FDR at q = 0.05, AND
- (d) **R3 agrees in sign** — the mixture the MC actually draws must also
  improve, otherwise the Gaussian result is an artifact of a component that
  carries little of the production draw weight, AND
- (e) the R4 stopping rule does not fire.

If (e) fires, the verdict is **CONFOUNDED — location first**, and the
recommendation becomes a location study, not a sigma change.
If (a)-(d) hold, the deliverable is a RECOMMENDATION only. **This study edits no
production file** (`build_matchup_dashboard.py`, `matchup_projection.py`,
`leverage_engine.py`, `rprs2.py` are all read-only here), consistent with
Rule 13 and with the measurement-only framing of its sibling.

## Frame arithmetic, declared in advance

Stated now so it cannot be reverse-engineered from the result:

- The published rprs2 band width is **constant at 57.4 FP for 237 of 347 rows**
  (`xfp_sigma` is a bucketed LOO residual sigma of the **full-season total**,
  `rprs2.py:359-363`). Divided by 1.35 that is a season-total sigma of ~42.5 FP.
  Over a plausible ~25 remaining appearances, A1 maps that to ~8.5 FP per
  appearance — roughly **3.4x** the production 2.5. So R2 should show S_BAND far
  too WIDE, and if it does, that is confirmation of the frame arithmetic, not a
  discovery.
- The pooled **within-pitcher** per-appearance SD of `fp_rp` over the 266
  relievers with >= 15 appearances is **4.00 FP** (measured before writing this
  section). Production draws 2.5. If `c*` lands near 4.00/2.5 = 1.60 that is the
  marginal-noise answer; a materially larger `c*` would indicate the location
  term is also contributing error, which is what R4 is there to separate.

## Prior art

- `band_crps_calibration_2026-07-29.md` — the sibling study; supplies the CRPS /
  pinball / clustered-bootstrap machinery and the 200-cluster + 2% floors reused
  verbatim here. Its §4 explicitly names this as the "highest-value follow-up".
- `rp3_sigma_singlestart_2026-07-10.md` — NO-CHANGE precedent for the SP band.
- `sp_sampler_tail_family_2026-07-29.md` — the sampler-shape family for SPs.
- CLAUDE.md gotcha: rank RPs with **rprs2**, never rp3.

---

## RESULT (2026-07-30)

`python scripts/xfp/validate_rp_band_crps.py`. Panel written to
`_rp_crps_panel.csv`; tables to `_rp_crps_{primary_cells,contrasts,slices}.csv`;
`c` curves to `_rp_crps_curve_{gauss,mix}[_test].csv` (all in this directory).

### 0. Panel

| | |
|---|---|
| snapshot RP rows | 14,545 |
| matched to a next relief appearance | 9,615 |
| after dropping `proj_per <= 0` | **9,568** (47 dropped, counted not floored) |
| clusters (relievers) | **304** |
| snapshot dates present after matching | 44 |
| TRAIN | 26 dates, 2026-06-04..2026-07-10, n = 6,052 |
| TEST | 18 dates, 2026-07-11..2026-07-28, n = 3,516, **228 clusters** |
| measured team-games / team / calendar day | **0.8747** |

Every gated cell clears the declared 200-cluster floor (225-228). **No cell is
UNDERPOWERED** — unlike the sibling study's n=173 cell.

Model-free references, all computed before any contrast:

| quantity | value |
|---|---|
| pooled **within-pitcher** per-appearance SD of `fp_rp` | **4.1444 FP** |
| production per-appearance sigma (`SIGMA_PER_RP_GAME`) | **2.5 FP** |
| panel `y` mean / SD | 2.913 / 4.383 FP |
| `mu_PROD` mean | 2.263 FP |
| share of appearances with FP <= 0 (all 10,560 relief games) | **18.1%** |

### 1. The headline: c*

| frame | fit on | c\* | sigma at c\* | CRPS at c\* | CRPS at c=1 (production) | production loss vs optimum |
|---|---|---|---|---|---|---|
| Gaussian | TRAIN | **1.60** | **4.00 FP** | 2.45481 | 2.54230 | **3.56%** |
| Gaussian | TEST (refit, descriptive) | 1.52 | 3.80 FP | 2.27741 | 2.34518 | 2.98% |
| production MIXTURE | TRAIN | 1.70 | 4.25 FP | 2.36393 | 2.37991 | **0.68%** |
| production MIXTURE | TEST (refit, descriptive) | 1.50 | 3.75 FP | 2.17215 | 2.18016 | 0.37% |

**`c*` = 1.5-1.7 for the RP single-appearance frame** — comparable in kind to the
sibling study's 2.65 (SP single-start) and 1.19 (SP rest-of-season), and it lands
almost exactly on the pre-declared arithmetic: the within-pitcher per-appearance
SD is 4.14 FP, and 4.14 / 2.5 = **1.66**. The prediction written into the
pre-registration was "if `c*` lands near 4.00/2.5 = 1.60 that is the
marginal-noise answer." It did.

Coverage makes the same point without a scoring rule:

| band | cov50 (nominal 50%) | cov80 (nominal 80%) |
|---|---|---|
| production sigma = 2.5 | **35.5%** | **62.0%** |
| c\* sigma = 4.00 | 54.3% | 81.9% |

The production reliever band is **materially too narrow** in the frame the MC
draws in. This is the opposite of the SP result, where CRPS *rescued* a band that
coverage had called 5pp light.

### 2. Primary cells

| cell | band | n | CRPS | pin.25 | pin.75 | cov50 | cov80 |
|---|---|---|---|---|---|---|---|
| R1 gauss TEST | prod sigma 2.5 | 3,516 | 2.34518 | 1.34098 | 1.25964 | 35.5% | 62.0% |
| R1 gauss TEST | **c\*=1.60 -> 4.00** | 3,516 | **2.27903** | 1.40581 | 1.14983 | 54.3% | 81.9% |
| R2 gauss BAND-rows | prod sigma 2.5 | 3,487 | **2.34917** | 1.34428 | 1.26059 | 35.6% | 61.8% |
| R2 gauss BAND-rows | S_BAND (A1) | 3,487 | 3.17444 | 2.20693 | 1.70110 | 92.4% | 99.2% |
| R2b\* gauss RAW-band | prod sigma 2.5 | 9,323 | **2.45035** | 1.41866 | 1.29139 | 35.0% | 61.2% |
| R2b\* gauss RAW-band | S_BAND_RAW | 9,323 | 10.07348 | 7.28852 | 6.98819 | **100.0%** | **100.0%** |
| R3 MIXTURE TEST | prod sigma 2.5 | 3,516 | 2.18016 | — | — | — | — |
| R3 MIXTURE TEST | c\*mix=1.70 -> 4.25 | 3,516 | **2.17381** | — | — | — | — |
| R4 gauss TEST+vol | **mu_PROD** | 3,516 | **2.34518** | 1.34098 | 1.25964 | 35.5% | 62.0% |
| R4 gauss TEST+vol | mu_VOL | 3,516 | 2.88065 | 1.84808 | 1.29175 | 38.1% | 62.9% |

R2b\* is **descriptive, added after the pre-registration and excluded from the
FDR set** — it exists because reading `run_season_sim.py` while building R2
turned up a live consumer of the raw band (see §5).

### 3. Paired, reliever-clustered bootstrap (2,000 reps, seed 20260730)

dCRPS = mean(B) - mean(A); negative means the alternative wins.

| contrast | n rows | clusters | CRPS_A | CRPS_B | dCRPS | rel % | 95% CI | boot p | econ | BH |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 prod -> c\* (gauss, TEST) | 3,516 | 228 | 2.34518 | 2.27903 | −0.06615 | **−2.82%** | [−0.0969, −0.0382] | 0.00025 | pass | **pass** |
| R2 prod -> S_BAND (gauss) | 3,487 | 225 | 2.34917 | 3.17444 | +0.82528 | **+35.13%** | [+0.6778, +0.9929] | 0.00025 | pass | **pass** |
| R3 prod -> c\*mix (MIXTURE, TEST) | 3,516 | 228 | 2.18016 | 2.17381 | −0.00635 | **−0.29%** | [−0.0201, +0.0059] | 0.330 | **fail** | fail |
| R4 mu_PROD -> mu_VOL (gauss, TEST) | 3,516 | 228 | 2.34518 | 2.88065 | +0.53547 | +22.83% | [−0.0082, +1.4482] | 0.057 | pass | fail |
| R2b\* prod -> S_BAND_RAW *(descriptive)* | 9,323 | 282 | 2.45035 | 10.07348 | +7.62313 | **+311.1%** | — | — | — | — |

### 4. Verdict against the declared decision rule

Walking the gates in order:

- (a) R1 relative improvement **2.82% >= 2%** — **pass**.
- (b) R1 clustered 95% CI **[−0.0969, −0.0382] excludes 0** — **pass**.
- (c) R1 survives **BH-FDR at q=0.05** — **pass**.
- (d) R3 sign agreement — the mixture also improves (−0.29%), so the *sign*
  clause as written is satisfied, but only barely: the effect is an order of
  magnitude smaller than the Gaussian cell and its CI spans 0 (p=0.33).
- (e) **R4 stopping rule FIRES: |dCRPS(R4)| = 0.53547 >= |dCRPS(R1)| = 0.06615.**

**VERDICT: CONFOUNDED — location first. NO sigma recalibration is recommended
off cell R1.** The pre-registered rule is honoured as written even though the
post-hoc work below shows the sigma effect survives a bias correction, because
the entire point of writing rule (e) in advance was to stop exactly this
inference from being made on a single panel.

Three things must be said honestly about that verdict rather than left implicit:

**(i) Rule (e) fired on a point estimate whose own CI spans zero.** R4's
`boot_p` is 0.057 and its CI is [−0.008, +1.448]. The rule as written compares
magnitudes, not significance, and R4's magnitude is a tail artifact:
`mu_VOL = xfp_ros / N_exp` explodes when `proj_volume` approaches 0 (its panel
max is **221.085** FP per appearance). Restricting to non-degenerate rows:

| R4 restriction | n | clusters | dCRPS | rel % | 95% CI | p |
|---|---|---|---|---|---|---|
| none (the gated cell) | 3,516 | 228 | +0.53547 | +22.83% | [−0.008, +1.448] | 0.057 |
| `N_exp >= 5` | 3,409 | 225 | +0.11574 | +5.03% | [−0.080, +0.385] | 0.369 |
| `N_exp >= 10` | 3,051 | **204** | **−0.01979** | **−0.91%** | [−0.072, +0.035] | 0.458 |

On the `N_exp >= 10` subset the rule would **not** fire (0.020 < 0.066). The
pre-registration is not amended after the fact; this is recorded so the next run
can declare a rule that trims the alternative before comparing magnitudes.

**(ii) R4 does not vindicate `mu_PROD` — `mu_PROD` is measurably biased low.**
TRAIN `mean(y) = 2.8496` vs `mean(mu_PROD) = 2.2356`: **−0.614 FP, −21.5%**.
Roughly 12.5pp of that is pure arithmetic and is not a modelling question:
`project_rp` spreads `xfp_ros` over **calendar days** and divides by the
**constant** `default_rp_app_rate = 0.35`, whereas expected appearances are
`0.8747 x days x app_rate`; at `app_rate = 0.35` the two differ by exactly the
measured 0.8747. The remainder is a mix of model error and **panel selection** —
this panel conditions on an appearance actually happening, which selects healthy,
in-role relievers whose realized FP runs above the pool. That selection is a
reason **not** to recalibrate `mu` from this panel, and it is stated before any
recommendation is made.

**(iii) The sigma finding survives removing the known bias, but lands ON the
economic floor.** POST-HOC (not pre-registered, not gated): fit the simplest
location correction on TRAIN only, apply to TEST, refit `c*`.

| correction fitted on TRAIN | c\*_train | sigma | TEST CRPS at prod sigma | TEST CRPS at c\* | rel |
|---|---|---|---|---|---|
| additive +0.6141 FP | 1.52 | 3.80 | 2.26060 | 2.21452 | **−2.04%** |
| multiplicative x1.2747 | 1.52 | 3.80 | 2.29321 | 2.24036 | **−2.30%** |

`c*` is stable at **1.52** under both corrections — the scale finding is not an
artifact of the mean bias — but the gain shrinks from 2.82% to 2.0-2.3%, i.e.
to the 2% floor itself. **A calibration claim that sits on its own economic
floor is not a claim worth changing production on.**

### 5. What IS unambiguous — a live units defect in `run_season_sim.py`

This one needs no calibration judgement, no `c*`, and no assumption A1.

`build_matchup_dashboard.load_projections()` (line 568) stores

```python
sigma = (p75 - p25) / 1.35            # xfp_p25 / xfp_p75 — FULL-SEASON band
rprs2_map[nk] = {..., 'sigma': sigma, ...}
```

That is a **season-total** residual sigma; measured on the shipped CSV its mean
is **42.33 FP** (median 42.50 — the width is a constant 57.4 FP for 237 of 347
rows, because `xfp_sigma` is a bucketed LOO residual sigma of `fp_year_total`).

In the dashboard it is dead — the RP branch reads only `role` / `mlbam` /
`xfp_ros`, and the file's only `.get('sigma')` (line 1282) reads `rp3_map` in the
SP branch. **In `run_season_sim.py:288-290` it is not dead:**

```python
info = rprs2_map.get(nk, {})
...
rps.append({..., 'mean_app': wk_mean / apps_wk,
            'sigma_app': float(info.get('sigma')
                               or fallback_sigma('RP', default=SIGMA_PER_RP_GAME))})
```

`sigma_app` is a **per-appearance** slot: it flows into
`_blend_draws(rng, emp, mean_app, sigma_app, K_PRIOR_RP, n)`. So the season sim
draws each relief appearance as roughly `N(3 FP, 42.5 FP)`. Cell R2b\* prices it:

| band | n | CRPS | cov50 | cov80 |
|---|---|---|---|---|
| production 2.5 FP | 9,323 | 2.45035 | 35.0% | 61.2% |
| `S_BAND_RAW` (what season_sim uses) | 9,323 | **10.07348** | **100.0%** | **100.0%** |

**+311% CRPS, and the 50% interval contains 100.0% of outcomes.** The `or`
short-circuit makes it worse, not better: it fires only when the derived sigma is
falsy, so the ~42.5 value always wins and the sane 2.5 fallback is unreachable
for any reliever present in rprs2. The SP branch four lines above is *correct* —
it reads `rp3_map`'s sigma, which the 2026-07-29 study showed is the right
per-start scale — which is precisely why the RP line reads as a copy-paste.

**Second defect on the same line.** `xfp_rprs2_projections.csv` ships **5 of 347**
rows with `p75 < p25` (`rprs2.py:409` clips `xfp_ros_p25` at 0 while `p75` may be
negative, breaking the normal-IQR identity), so the unguarded expression returns a
**negative** sigma:

| reliever | xfp_ros | p25 | p75 | naive (p75−p25)/1.35 |
|---|---|---|---|---|
| Joey Lucchesi | −22.1 | 7.0 | 6.6 | **−0.30** |
| Brett Sullivan | −37.7 | 0.0 | −9.0 | **−6.67** |
| Ben Williamson | −50.3 | 0.0 | −21.6 | **−16.00** |
| Carlos Cortes | −55.0 | 9.2 | −26.3 | **−26.30** |
| Tyler Tolbert | −105.9 | 31.6 | −77.2 | **−80.59** |

A negative sigma is truthy, so `float(info.get('sigma') or fallback)` passes it
through, and `leverage_engine._blend_draws` line 198 —
`sigma = max(float(sigma or 0) or 1e-6, 1e-6)` — **silently clamps it to 1e-6**,
i.e. a degenerate point mass presented as a predictive distribution. That is the
silent-default pattern House Rule 1 exists to forbid. (These five are deep-negative
projections that no one would roster, so the practical blast radius is small; the
clamp is the defect, not the five names.)

### 6. RECOMMENDATIONS (this study implements none of them)

Ranked by confidence, not by size:

1. **HIGH — fix `run_season_sim.py:288-290`.** A season-total sigma is being used
   as a per-appearance scale. Replace with `SIGMA_PER_RP_GAME` outright
   (`float(fallback_sigma('RP', default=SIGMA_PER_RP_GAME))`), matching what
   `leverage_engine` and `build_matchup_dashboard` already do. This is a units
   correction, not a calibration change, and needs no further study. Measured
   cost of the status quo: +311% CRPS per appearance, cov50 100.0%.
2. **HIGH — make the band -> sigma conversion fail loudly.** Whether or not
   `run_season_sim` is fixed, `(p75 - p25)/1.35` must not be allowed to emit a
   negative or non-finite sigma, and `_blend_draws`' `max(..., 1e-6)` must not be
   the thing that catches it. `validate_rp_band_crps.implied_per_appearance_sigma`
   is the reference behaviour; `tests/test_rp_band_crps.py` locks it and exercises
   it against the five real rows.
3. **MEDIUM — delete the dead derivation in `build_matchup_dashboard.py:566-568`**
   or label its units. It is computed for every reliever, never read in that file,
   and is the source the defective `run_season_sim` line reads from. Correcting
   `band_crps_calibration_2026-07-29.md` §4 in the same change would be right: its
   claim that this value "feeds P(win)" via `_rp_total_draws` is **wrong** — the
   scale that reaches `_rp_total_draws` is the flat 2.5.
4. **DO NOT change `SIGMA_PER_RP_GAME` on this study.** Gate (e) fired. The
   measurement is real and reproducible (`c*` = 1.52-1.70 across four fits,
   coverage 35.5% vs a nominal 50%), but the location term moves CRPS several
   times more than the scale term does, `mu_PROD` is measurably 21.5% low, and
   after correcting that the scale gain falls to the 2% floor. Fixing the scale
   while leaving the location wrong would make the *interval* look calibrated
   while the *centre* stays biased.
5. **NOTE for the P(win) layer — the mixture absorbs most of this.** R3 is the
   cell that matters for `delta_pwin`, and it moves only −0.29% (n.s.). 70.2% of
   panel rows carry the full 20-appearance history, mean blend weight
   `w = n_emp/(n_emp+10)` = **0.620**, so ~62% of every production RP draw is a
   bootstrap of that reliever's own outcomes, which carries the right width *and*
   the right centre for free. **The reliever leg of `delta_pwin` is therefore in
   much better shape than the raw 2.5-vs-4.14 sigma gap suggests.** The exposed
   paths are the ones with no empirical blend: the dashboard's analytic
   `win_probability` (`build_matchup_dashboard.py:3342-3349` sums
   `sigma2 = expected_apps x 2.5**2`, understating RP variance by
   `(4.14/2.5)^2 = 2.75x`) and any reliever with a thin history, where `w` is
   small and the parametric component dominates.

### 7. What would settle the confounding

Stated concretely, per the brief:

1. **A location study for `mu_app`**, pre-registered separately, with a panel
   that does **not** condition on an appearance occurring — score every
   (reliever, team-game) pair including the zero-appearance ones, so the
   selection described in §4(ii) is removed. The arithmetic fix (team games, not
   calendar days; the reliever's own `app_rate`, not the constant 0.35) should be
   the first contrast, since it is derivable and needs no fitting.
2. **Then** re-run this exact script against the corrected `mu`. If `c*` still
   lands near 1.5-1.6 with a gain above 2%, the scale change is clean. The script
   already supports this: `c_star(panel, rows, mu_col, kind)` takes the mu column
   by name.
3. **More snapshot dates.** 44 dates over 8 in-season weeks gave 228 TEST
   clusters — enough to clear the floor, not enough for `c*` to be stable across
   folds (1.60 train / 1.52 test Gaussian; 1.70 / 1.50 mixture). Re-running in
   ~4 weeks roughly doubles the TEST window.
4. **Score a completed season.** Every number here is in-season and single-frame
   by necessity. The rest-of-season *total* band (`xfp_ros_p25/p75`) still has no
   calibration evidence and cannot get any until 2026 finishes — that part of the
   2026-07-29 "UNSCORABLE" call stands, and only the single-appearance frame has
   been opened up.

### 8. Bottom line

**The RP band has now been measured.** In the single-appearance frame the MC
actually draws in, the production scale of **2.5 FP is too narrow — `c*` = 1.5-1.7,
i.e. ~3.8-4.25 FP — and its 50% interval covers 35.5% of outcomes.** But the
pre-registered stopping rule fired: reliever forecast error is dominated by where
the distribution is centred, not how wide it is, and `mu_PROD` runs 21.5% low.
**No production sigma changes on this study.**

The finding that does not depend on any of that judgement is the units defect:
`run_season_sim.py` feeds a **season-total** sigma (~42.5 FP) into a
**per-appearance** slot, priced at **+311% CRPS with 100.0% cov50**, and the same
expression can emit a negative sigma that `_blend_draws` silently clamps to a
point mass. That is the one thing here that should be fixed without waiting for
another study.

---

## Reproduction

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_rp_band_crps.py
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/ci/run_summary.py -- \
    python -m pytest tests/test_rp_band_crps.py -q
```

Deterministic: seed 20260730 for every bootstrap and every mixture ensemble.
Full suite after this change: **1,289 passed**.


---

## CORRECTIONS (adversarial review, 2026-07-30)

The review returned CONFIRMED — every headline reproduced — but found two numeric
defects the author had no way to see. Both are corrected above / in the script.

**1. `mu_VOL` panel max was reported as "3,522 FP per appearance". The real value
is 221.085.** No code path in the study computes 3,522; it was a fabricated
figure, which is a House Rule 3 violation regardless of the fact that the claim it
supports (mu_VOL explodes as proj_volume approaches 0, so R4's magnitude is a tail
artifact) survives intact at 221. Corrected in §4(i) above.

**2. `emp` misalignment in `mixture_crps`, silent and near-total on TEST.**
`c_star` selected rows with `panel.loc[rows]`; pandas propagates `.attrs`
unchanged, so the subset frame carried the FULL empirical-history list, which
`mixture_crps` then sliced POSITIONALLY (`attrs['emp'][s:e]`). Because the slice
LENGTH still matched, nothing raised — but **3,515 of 3,516 TEST rows were paired
with a different pitcher's history**. TRAIN escaped only because it is a
contiguous prefix of the panel.

Corrected figures for the mixture TEST cell:

| | reported | corrected |
|---|---|---|
| mixture TEST c* | 1.30 | **1.50** |
| mixture TEST CRPS | 2.31112 | **2.17215** |

This makes c* MORE consistent across folds (train 1.60 / test 1.52 Gaussian;
mixture now 1.50 rather than 1.30), so the study's conclusion is strengthened, not
weakened. `_rp_crps_curve_mix_test.csv` must be regenerated before that file is
cited.

**Coverage gap that let #2 through, recorded so it is not repeated:** the 21 tests
cover only the CRPS / pinball / sigma helpers. None of `build_panel`,
`mixture_crps`, `c_star`, `bh_fdr` or the bootstrap is tested — and the bug lived
entirely inside that gap.

**Exposure was UNDERSTATED, not overstated:** `_USE_BOOTSTRAP` defaults True, but
`win_probability_bootstrap` consumes the same `sigma2`, so the RP variance
understatement reaches the DEFAULT dashboard path too, not only the analytic one.

**Acted on immediately (2026-07-30), outside this study's file set:**
`run_season_sim.py` was reading the rprs2 band sigma — a rest-of-season TOTAL,
median **42.50 FP** — into a PER-APPEARANCE slot, i.e. **17.0x** the documented
2.5 FP fallback. Since that sim produces the value-of-a-win curve `title_equity`
converts every weekly edge through, it is now fixed to use the documented
fallback. `SIGMA_PER_RP_GAME` itself remains 2.5, per this study's pre-registered
stopping rule.
