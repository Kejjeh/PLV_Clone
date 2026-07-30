---
signal: hitter_per_game_sigma_scale (units + scale of the hitter per-game outcome sigma in the matchup win-probability path)
formula: >
  Per-game hitter FP is a RATE times a COUNT:
      FP_game = (FP / PA) * PA_game
  so, treating PA_game as approximately fixed for a given batter,
      sigma(FP_game) = sigma(FP/PA) * PA_game
  and therefore per-game VARIANCE is quadratic in PA/game:
      var(FP_game) = sigma_rate^2 * PA_game^2

  SHIPPED (pre-fix), src/plv_clone/matchup_projection.py:258:
      sigma_pa = global_sigma_pa_fp * sigma_factor          # 0.517 * factor
      sigma2   = n_games * sigma_pa^2 * pa_per_g            # PA/game LINEAR
  This is the per-PA reading: it assumes 0.517 is a per-PA sigma so that PA/game
  enters the variance once (independent-PA sum). Two errors:
    (E1) EXPONENT. global_sigma_pa_fp is NOT per-PA. build_hitter_sigma_
         calibration.py:77-83 computes it as the PA-weighted RMS of the per-GAME
         residual of fp_proxy/PA -- a per-GAME RATE, one observation per game.
         PA/game must therefore enter the variance SQUARED.
    (E2) SCALE. It is measured off fp_proxy = TB + BB + HBP - K
         (analyze_hitter_boom_bust.py:96), which OMITS R, RBI and SB. The
         canonical BrownU hitter formula is R + TB + RBI + BB + HBP + SB - K, so
         the constant is also in the wrong FP units.

  FIXED, matchup_projection.hitter_sigma_per_game():
      sigma_game = global_sigma_pa_fp * FP_PROXY_TO_FULL_FP_SIGMA
                   * sigma_factor * pa_per_g
      sigma2     = n_games * sigma_game^2
  with FP_PROXY_TO_FULL_FP_SIGMA = 1.517531
     = 1.4742 (measured canonical/proxy per-game-RATE sigma ratio)
     x 1.0295 (through-origin recalibration of the per-batter slope),
  giving an effective slope 0.517 * 1.517531 = 0.784563 FP per PA-of-a-game.
outcome: >
  PRIMARY: within-batter pooled SD of canonical per-game hitter FP (fp_h from
  data/research/xfp_cache/boxscore_hitters.parquet), 2026, STARTED games only --
  the population the projection covers.
  SECONDARY (acceptance test): team-level win-probability dispersion on
  data/outputs/predictions_history.csv -- SD(spread residual / model sigma),
  which is 1.00 when calibrated, and Brier score.
expected_sign: >
  Pre-registered before the team-level acceptance test was run: if the
  diagnosis (per-game hitter sigma understated ~3.4x, hitters ~9% of team
  sigma^2) is correct, then the logged win probabilities must be
  OVER-CONFIDENT -- SD(resid/sigma) > 1 -- and the fix, which can only
  INCREASE sigma, must move SD(resid/sigma) DOWN TOWARD 1.00 and lower Brier.
  If SD(resid/sigma) had come in at or below 1.00 before the fix, the
  diagnosis would have been incomplete and the fix would have been WRONG to
  ship; that outcome was pre-accepted as a stop condition.
theory: >
  The mislabelling is a units error, not a modelling choice. "sigma per PA" and
  "sigma of a per-PA rate observed once per game" are different objects that
  differ by a factor of sqrt(PA) in the per-game aggregate; at PA/g ~ 4 that is
  a factor of 2, and the proxy-formula gap contributes another 1.47x, for a
  combined ~3.1-3.4x in sigma / ~9.7-11.3x in variance. Because the shipped
  hitter sigma was ~3x too small AND hitters are only ~9% of a BrownU team's
  projected variance (the SP side, at a correctly-calibrated 8.73 FP/start, has
  ~761 of ~902 FP^2), the team-level symptom is a modest but systematic
  over-confidence in P(win) rather than an obviously broken number -- which is
  why it survived. The per-batter sigma_factor is unaffected: it is
  pred_sigma/global_sigma re-centred to mean 1.0, and ridge is scale-equivariant
  in y, so the factor is dimensionless and invariant to any global rescale of
  the fitted target.
production_target: >
  src/plv_clone/matchup_projection.py :: project_hitter_games / the new
  hitter_sigma_per_game kernel. Consumed by
  scripts/xfp/build_matchup_dashboard.py (per-player sigma2 -> team sigma2 ->
  win_probability / win_probability_bootstrap -> matchup.html and
  data/outputs/predictions_history.csv), and downstream by /matchup-leverage
  and (partially, blended against an empirical bootstrap) /matchup-leverage.
  NOT consumed by /season-sim, which sources its hitter sigma from the boxscore
  series instead -- verified at run_season_sim.py:303-305.
framing: >
  Bug repair with a measured recalibration, not a new feature. No new predictor
  is introduced; no projection MEAN changes anywhere. Rule 9 baseline-inclusion
  does not apply (nothing is added to rh3/rp3/rprs2). Multiple-testing exposure
  is one pre-registered directional acceptance test (SD(resid/sigma) -> 1) plus
  reporting of Brier; no threshold was tuned to pass, and the constant is fixed
  by measurement on the outcome data, not selected against the acceptance test.
holdout_years: >
  2026 (in-season) for the canonical-FP measurement, because 2026 is the only
  season with a canonical per-game FP store (boxscore_hitters.parquet carries
  fp_h). Cross-checked against 2018-2025 for the units question, where only the
  proxy exists: the panel's proxy sigma rescaled by the canonical/proxy ratio
  measured on the 2026 rows reproduces the direct 2026 estimate to +0.11%,
  i.e. the two eras agree.
training_years: >
  None -- nothing is fitted to an outcome here. The one number estimated from
  data (the through-origin slope 0.784563) is estimated on the same 2026 window
  it is reported against, and is reported alongside the two independent
  estimates that bracket it (0.762996 direct rate sigma, 0.762139 panel-scaled).
validation_script: scripts/xfp/validate_hitter_sigma_scale.py
date: 2026-07-29
revised: 2026-07-30 (section 5 re-scored on repaired matchup labels — see addendum; conclusion of the acceptance test REVERSES)
---

# Hitter per-game sigma: the matchup win-prob path was 3.1x under-dispersed on the hitter side

Reproduce everything below with:

```
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/validate_hitter_sigma_scale.py
```

---

## 1. fp_proxy audit — done FIRST, because it changes the answer

The task's candidate ground truth was `fp_proxy`'s SD of 2.3072 on the
245,712-row boom-bust panel. Its mean of 1.1775 FP/game is indeed implausibly
low for a BrownU hitter game, and the reason is that **`fp_proxy` is not the
scoring formula**:

```
canonical BrownU   FP/game = R + TB + RBI + BB + HBP + SB - K
panel fp_proxy             =     TB       + BB + HBP      - K     # omits R, RBI, SB
                                                                  # analyze_hitter_boom_bust.py:96
```

`data/research/xfp_cache/boxscore_hitters.parquet` carries **both** the
canonical `fp_h` and every `fp_proxy` component, so the two can be compared on
identical rows. `fp_h` reproduces `R+TB+RBI+BB+HBP+SB-K` with `max|dev| = 0.0`
over 32,808 rows — it *is* the canonical formula.

| quantity | value |
|---|---|
| panel `fp_proxy` mean / SD (all rows) | 1.1775 / 2.3072 |
| 2026 boxscore `fp_h` mean / SD (all rows) | 1.8071 / 3.1735 |
| 2026 boxscore `proxy` mean / SD (all rows) | 0.8788 / 2.1137 |
| omitted terms (R + RBI + SB), mean | **0.9283 FP/game** |

**So `fp_proxy`'s 2.3072 must NOT be adopted as ground truth.** It is a proxy
undercount of both the level and the spread. Everything below uses `fp_h`.

## 2. `global_sigma_pa_fp = 0.517` is a per-GAME RATE sigma, not a per-PA sigma

Reproducing `build_hitter_sigma_calibration.py:77-83` exactly:

| estimator of the same `fp_proxy/PA` residual | value |
|---|---|
| PA-weighted within-batter RMS (the shipped 0.517) | **0.516968** |
| UNWEIGHTED within-batter SD | 0.518566 |
| plain unweighted SD across all rows | 0.523869 |

PA-weighting moves the number by **+0.31%**. Weighting a *rate* by PA weights
games; it does not convert the rate into a per-PA quantity. The unit is
"FP per PA, observed once per game" — a per-game rate.

Dimensional test on that same panel (mean PA/g 4.3483; measured within-batter
per-game SD of `fp_proxy` = **2.2816**):

| reading | prediction | error vs measured |
|---|---|---|
| per-PA: `0.517 * sqrt(4.3483)` | 1.0780 | **−52.8%** |
| per-game-rate: `0.517 * 4.3483` | 2.2479 | **−1.5%** |

Confirmed independently on **per-batter PA/g variation** (377 batters,
26,199 started 2026 games, pa_per_g range 2.98–4.72), fitting through the
origin, games-weighted:

| model | constant | weighted R² vs batter SDs | RMSE |
|---|---|---|---|
| `sigma = C * ppg` | **0.784563** | **+0.2142** | 0.4923 |
| `sigma = C * sqrt(ppg)` | 1.589189 | +0.1654 | 0.5074 |

The exponent is settled: **PA/game is linear in sigma, quadratic in variance.**

## 3. The empirical per-game hitter FP sigma (production population)

Joining `boxscore_hitters` to `hitter_lineup_appearances_2026` (32,808 of 32,808
rows joined) gives canonical FP *and* PA *and* the started-game flag. Production
projects games a hitter is expected to start, so **started games** is the right
population.

| | ALL appearances | **STARTED games** |
|---|---|---|
| n games / batters (≥30 g) | 30,335 / 415 | **26,199 / 377** |
| mean PA/game | 3.7856 | **4.0810** |
| mean canonical `fp_h` | 1.8845 | **2.0448** |
| within-batter per-GAME SD of `fp_h` | 3.1496 | **3.2502 ← truth** |
| within-batter per-GAME SD of proxy | 2.0952 | 2.1671 |
| within-batter RATE sigma, canonical | 0.793074 | **0.762996** |
| within-batter RATE sigma, proxy | 0.537614 | 0.517549 |
| canonical/proxy RATE-sigma ratio | 1.4752 | **1.4742** |
| `rate_sigma * PA/g` vs per-game SD | −4.7% | −4.2% |
| `rate_sigma * sqrt(PA/g)` vs per-game SD | −51.0% | −52.6% |

Note the proxy rate sigma on 2026 started games (0.517549) lands on the panel's
0.516968 to within 0.11% — the populations are comparable, which validates
transporting the ratio across eras.

**Two independent estimates of the canonical per-game-rate sigma:**

| estimate | value |
|---|---|
| (i) direct 2026 measurement, canonical FP, started games | 0.762996 |
| (ii) 2018-25 panel proxy sigma × canonical/proxy ratio (1.4742) | 0.762139 |
| agreement | **+0.11%** |

The **shipped constant is the through-origin slope 0.784563** (+2.9% above these
two), because that is the quantity calibrated against the exact production
formula `sigma_game = C × pa_per_g` on the production population. It centres the
per-batter ratio realised/model at **mean 0.9961** (SD 0.1583).

**Magnitude of the bug**, at the measured mean pa_per_g 4.0810:

| variant | sigma FP/game | understatement vs truth (3.2502) | in variance |
|---|---|---|---|
| SHIPPED, `0.517*sqrt(3.5)` (missing-`pa_per_g` default) | 0.9672 | **3.360x** | 11.29x |
| SHIPPED, `0.517*sqrt(4.081)` (real per-batter path) | 1.0444 | **3.112x** | 9.68x |
| exponent fix only, `0.517*4.081` | 2.1099 | 1.540x | 2.37x |
| **FIXED, `0.784563*4.081`** | **3.1138** | **1.044x** | 1.09x |
| legacy `SIGMA_PER_HITTER_GAME = 3.5` | 3.5000 | 0.929x (7.7% too big) | 0.86x |

This confirms the task's framing: the legacy 3.5 constant it replaced was
**~2.5-3x closer to truth and conservative in direction**. The "improvement"
that shipped was a regression.

## 4. The sigma_factor refit question — resolved: NO refit needed, proven

`batter_sigma_factor` is `pred_sigma / global_sigma`, re-centred to mean 1.0
(`hitter_sigma_hetero.compute_batter_sigma_factors`). Ridge minimises
`||y - Xb||² + a||b||²`, which is **scale-equivariant in y**: substituting
`y -> cy, b -> cb` scales the objective by `c²` and leaves the minimiser
unchanged, so `pred_sigma` scales by `c`, `global_sigma` scales by `c`, and the
ratio — hence the re-centred factor — is untouched. Verified numerically by
refitting the actual calibration on `sigma_emp`, `2*sigma_emp` and
`10*sigma_emp`:

```
max |factor(y) - factor(2y)|  = 0.000e+00
max |factor(y) - factor(10y)| = 1.998e-15
```

Confirmed live: the shipped `batter_sigma_factor` in
`xfp_rh3_projections.csv` has mean exactly **1.000000** (n=473, SD 0.0844,
range 0.701–1.248) — a pure dimensionless multiplier.

**It also TRANSFERS to canonical FP**, which is the non-trivial part (it was fit
on *proxy*-rate sigma over 2018-2025). Against realised 2026 canonical
quantities, 377 batters:

| correlation | value |
|---|---|
| `corr(batter_sigma_factor, realised sigma / model sigma)` | **+0.5757** |
| `corr(batter_sigma_factor, realised canonical per-game-RATE sigma)` | **+0.6239** |

So the factor keeps doing real work after the rescale, and the constant/exponent
correction neither double-counts nor mis-scales it.

## 5. ACCEPTANCE TEST — team-level win-prob calibration, BEFORE vs AFTER

**Audit trail, stated so the pre-registration can be judged.** The constant
0.784563 was fixed by the measurements in sections 3-4 — canonical per-game FP SD
and the through-origin slope — *before* any team-level number was computed, and
it was never adjusted afterwards. One correction was made to the acceptance test
itself after first running it: the first pass pooled the 141 synthetic
`backfill_2024_*` / `backfill_2025_*` rows with the live ones and reported
SD(resid/sigma) 0.956 -> 0.724, i.e. "the fix makes calibration worse." That
result was an artifact — those rows carry an implied spread sigma of 100-400 FP
against the live model's 29-50 FP, so they dominate and invert the statistic.
The exclusion is justified independently of the outcome (they are a different
code path, flagged `is_synthetic` / `backfill_year`, and the live-only implied
sigma is corroborated to +5.0% by the section-5a reconstruction — +4.6% after
the 2026-07-30 input refresh), not because it flipped the sign. The filter is in the script as
`LIVE_MODEL_VERSIONS = ("baseline", "MA_v1")` and it prints the excluded count.

### 5a. Hitter share of team sigma², reconstructed from production inputs

*(numbers refreshed 2026-07-30 with one more day of boxscores — games/week
5.870 → 5.748, share 0.0905 → 0.0889; an input drift, unrelated to the label
repair, and immaterial: at the old 0.0905 the section-5b sweep row differs by
< 0.005 in SD(z).)*

Real inputs: 5.748 games per MLB team per scoring week (from 2026 boxscores);
mean pa_per_g 4.0016 over 377 regulars; per-SP-start sigma **8.7261** (the
`xfp_rp3_sigma` production actually uses); BrownU 13 active hitters, 10 SP starts
under the period cap, 4 true RPs at 0.40 app rate, RP sigma 2.5.

| component | sigma² BEFORE | sigma² AFTER |
|---|---|---|
| hitters (74.7 hitter-games) | 79.9 | 736.6 |
| SP (10 starts @ 8.7261) | 761.5 | 761.5 |
| RP (9.2 apps @ 2.5) | 57.5 | 57.5 |
| **team sigma** | **29.98 FP** | **39.44 FP** |

**Hitter share of team sigma² before the fix = 0.0889.** Hitter variance
multiplier from the fix = **9.215x**.

**Independent cross-check that this reconstruction is right:** it implies a
*spread* sigma of `29.98 * sqrt(2) = 42.40 FP`. Inverting the actually-logged
win probabilities gives a mean implied spread sigma of **40.52 FP**
(median 40.92) — **+4.6% agreement**, from a completely separate data path. The
0.0889 share is therefore trustworthy.

*(Data hygiene, and the reason a first pass got this backwards:
`predictions_history.csv` also holds 141 `backfill_2024_*` / `backfill_2025_*`
synthetic rows whose implied spread sigma is 100–400 FP, 3-10x the live model's.
Including them inverts the sign of the dispersion test. Only
`model_version in {baseline, MA_v1}` is live and only those are used.)*

### 5b. The result — RE-SCORED 2026-07-30 on repaired labels; the acceptance test now FAILS

*(The 2026-07-29 version of this section graded against corrupted labels — 5 of
the 11 labelled periods held single-day partials, not matchup finals — and
reported PASS: 1.379 → 1.045, Brier 0.2603 → 0.2469. Those numbers are
label artifacts; the originals are preserved in the addendum table. What
follows is the honest re-score.)*

19 live snapshots over 10 **closed** periods (9 of them `MA_v1`, the live
version). Residual = `(actual_my - actual_opp) - (proj_my - proj_opp)`. The
original run's "11 completed periods" was wrong: period 17 was still OPEN and
its labels were running partials; the script now excludes still-open periods
via the open-period guard in `_load_live_history`.

| metric | BEFORE (as logged) | AFTER (fixed) | target |
|---|---|---|---|
| realised spread-error SD | 39.41 FP | 39.41 FP | — |
| model spread sigma | 40.52 FP | **53.30 FP** | 39.41 |
| **SD(resid / sigma)** | **0.927** | **0.704** | **1.000** |
| \|error from 1.00\| | 0.073 | **0.296** | 0 |
| Brier | 0.1203 | **0.1269** | lower |
| window-normalised `k = sigma/sqrt(remaining FP)` | 1.6813 | **2.2117** | 1.6323 |

`MA_v1` only (n=9, the live production version):

| metric | BEFORE | AFTER |
|---|---|---|
| realised spread-error SD | 45.08 FP | 45.08 FP |
| model spread sigma | 39.74 FP | 52.28 FP |
| **SD(resid / sigma)** | **1.080** | **0.821** |
| Brier | 0.1203 | **0.1235** |

**On honest labels the pre-registered stop condition has occurred.** The
front-matter pre-registration reads: *"If SD(resid/sigma) had come in at or
below 1.00 before the fix, the diagnosis would have been incomplete and the fix
would have been WRONG to ship; that outcome was pre-accepted as a stop
condition."* The all-live BEFORE is **0.927** — at/below 1.00 — and the fix
moves dispersion AWAY from 1 on both panels (0.927 → 0.704; MA_v1 1.080 →
0.821) and worsens Brier slightly (0.1203 → 0.1269; MA_v1 0.1203 → 0.1235).
The realised spread-error SD (39.41 FP) matches the OLD model sigma (40.52 FP)
almost exactly; the widened sigma (53.30 FP) over-disperses at team level.
Confident-bucket read: BEFORE `[0.65,1.00) n=7 pred 0.83 / act 0.71`; AFTER
`n=6 pred 0.80 / act 0.67` — the logged probabilities were not the
mis-calibrated object; the labels were.

Sampling context, stated both ways: at n=19 the 1-SE band on an SD estimate is
roughly ±0.16, so BEFORE's 0.927 is within 1 SE of perfect while AFTER's 0.704
is ~1.8 SE below it; at n=9 (MA_v1) the band is ~±0.25 and neither 1.080 nor
0.821 is decisive alone. The test no longer supports the fix in the
pre-registered direction on either panel; it does not by itself *prove* the
fix over-disperses.

Sensitivity to the one reconstructed quantity (hitter share), all-live:

| share | sigma scale | SD(z) |
|---|---|---|
| 0.0500 | 1.188 | 0.780 |
| 0.0750 | 1.271 | 0.729 |
| **0.0905 (≈ reconstructed 0.0889)** | **1.320** | **0.702** |
| 0.1000 | 1.350 | 0.687 |
| 0.1500 | 1.494 | 0.620 |
| 0.2000 | 1.626 | 0.570 |

The reversal holds across the whole plausible range: every share from 0.05 to
0.20 moves SD(z) further below the BEFORE's 0.927 — there is no share at which
the widened sigma improves team-level dispersion on honest labels.

The mean/bias question (mean pred 0.467 before / 0.471 after vs actual win
rate 0.368, all-live on honest labels) remains out of scope: nothing in this change touches a
projection mean, and the I5 study (`pwin_mean_bias_2026-07-30.md`) found the
apparent mean bias indistinguishable from zero at this n once the same label
corruption was removed.

## 6. Recommendation on `MATCHUP_LEGACY_SIGMA` — keep the default at `0` (off)

*(SD(z) columns re-scored 2026-07-30 on repaired labels; the team-level ranking
INVERTS — see addendum.)*

`MATCHUP_LEGACY_SIGMA=1` swaps in fixed per-position sigmas: hitter 3.5,
**SP 5.5**, RP 2.5. Scaling the honest-label dispersion by each variant's
reconstructed team sigma:

| variant | sigma_hit FP/g | team sigma | scale | SD(z) | \|SD(z)−1\| |
|---|---|---|---|---|---|
| SHIPPED buggy (real ppg) | 1.0342 | 29.98 | 1.000 | 0.927 | 0.073 |
| SHIPPED buggy (3.5 fallback) | 0.9672 | 29.81 | 0.994 | 0.932 | 0.068 |
| exponent fix only | 2.0688 | 33.75 | 1.126 | 0.823 | 0.177 |
| **FIXED (shipped now)** | **3.1395** | **39.44** | **1.315** | **0.704** | **0.296** |
| FIXED, worst-case 3.5 ppg fallback | 2.7460 | 37.18 | 1.240 | 0.747 | 0.253 |
| `MATCHUP_LEGACY_SIGMA=1` | 3.5000 | 35.71 | 1.191 | 0.778 | 0.222 |

**The original verdict's empirical basis is withdrawn.** On corrupted labels
this table read 1.379 / 1.223 / 1.045 / 1.151 top to bottom and the FIXED path
"won outright" (0.045 vs legacy's 0.151). On honest labels every variant sits
BELOW 1 and the ranking inverts: the buggy path is now numerically closest to
1 (0.073) and the FIXED path farthest (0.296). At n=19 (±0.16 1-SE) this does
not license flipping any default — it licenses saying the team-level evidence
no longer discriminates in the fix's favour. The default stays `0` for now
because no variant is *demonstrably* better at this n and the hetero path
keeps the per-batter heteroskedasticity (section 4's r = +0.58/+0.62, which is
label-independent and stands); the team-level question is OPEN pending the
follow-up in the addendum (SP-side sigma / cross-player correlation).

Two follow-ups this memo does NOT ship (both outside this change's file set):

1. `scripts/xfp/build_matchup_dashboard.py:361` still passes
   `LEAGUE_PA_PER_GAME = 3.5` into `_MCFG`, overriding the newly measured
   `MatchupConfig.league_pa_per_game = 4.0016`. This only fires for batters with
   no lineup-map entry (fewer than 3 started games in the trailing 21 days), so
   the real-world effect is small; the worst case, if it fired for *every*
   hitter, is the "3.5 fallback" row above vs the FIXED row (0.747 vs 0.704 on
   repaired labels). One-line follow-up: pass 4.0016, or
   drop the argument and inherit the measured default.
2. The comment block at `build_matchup_dashboard.py:363-370` states the wrong
   identity ("Per-game variance ~ PA_per_game * sigma_pa^2 ... ~ 0.94 FP^2,
   sigma ~ 0.97 FP/g"). That is the root of the reasoning error and should be
   rewritten to the correct `(sigma_rate * PA_per_game)^2` form.

## 7. Prior outputs this INVALIDATES

Everything that consumed per-player hitter `sigma2` between the hetero-sigma
ship (2026-06-03, per `CLAUDE.md` "Recent shipping") and 2026-07-29:

- **`data/outputs/predictions_history.csv` — the corrupted thing was the
  LABELS, not the probabilities.** *(Rewritten 2026-07-30; the original bullet
  claimed "every `baseline` / `MA_v1` `win_probability` in that window is
  over-confident" with spread sigma "40.46 FP where 53.43 FP was warranted" —
  that claim was measured against the corrupt labels and is WITHDRAWN.)*
  5 of 11 labelled periods stored single-day partials as finals (period 13:
  25.7-64.5 vs real 322.1-331.3); repaired 2026-07-30 (commit `dda7639`,
  `fetch_closed_matchup_actuals --repair`, 182 rows, periods 12-16). On honest
  labels the logged win probabilities score Brier 0.1203 and SD(resid/sigma)
  0.927 all-live / 1.080 MA_v1 — near-calibrated. Systematic over-confidence
  is no longer demonstrated at team level. The 141 synthetic `backfill_*` rows
  are a *separate* problem (their sigma is 3-10x the live model's) and should
  not be pooled with live rows for any calibration read; nor should any
  still-open period's labels (they are partials until the nightly `--repair`
  closes them — the open-period guard in the script enforces this).
- **`matchup.html` win probability and its CI bands** (`render_ci_bands` reads
  the same `my_sigma2` / `opp_sigma2`) for every build in that window — the
  per-player hitter bands were too narrow (sections 1-4, label-independent),
  but the TEAM-level "bands were too narrow" consequence is no longer
  demonstrable on honest labels (SD(z) before = 0.927 ≈ calibrated;
  corrected 2026-07-30).
- **`/matchup-leverage` P(win) regimes — PARTIALLY affected.** `run_matchup_leverage.py:407`
  derives its per-game hitter sigma as `sqrt(proj['sigma2'] / n_games)`, i.e.
  directly from the buggy value. But `_blend_draws` mixes an empirical boxscore
  bootstrap with the parametric normal at weight `w = n_emp/(n_emp + K_PRIOR_H)`
  with `K_PRIOR_H = 8`, so for a hitter with ~25 games of history 76% of draws
  come from his real game log and only 24% from the too-narrow normal. The
  regime cut-points are thresholds on that P(win), so historical regime labels
  are biased toward the confident regimes, but by materially less than the
  matchup dashboard's own number. Thin-history hitters (few boxscore games) are
  the ones that were badly under-dispersed. Re-derive before quoting a
  historical regime call; do not assume the label was wrong.

**Checked and NOT invalidated (stated explicitly, because it was on the suspect
list):**

- **`/season-sim` title odds and its "+10% sigma" variance-helps/hurts
  conclusion are NOT affected by this bug.** `run_season_sim.py:303-305` does not
  read `proj['sigma2']` at all — it sets the per-game hitter sigma from the
  player's own boxscore series (`np.std(emp, ddof=1)` when `len(emp) >= 8`) and
  otherwise from `fallback_sigma('H', default=3.2)`. Both are independent of
  `matchup_projection`, and both are close to the 3.2502 truth established here.
  The season-sim variance conclusion stands on its own merits; this fix neither
  rescues nor voids it.

Not affected: every projection MEAN (`fp`), all rank orders, `rh3`/`rp3`/`rprs2`
outputs, `xfp_rh3_p25`/`p75` bands (a different, per-PA rate-CI sigma), the SP
and RP variance paths, and `batter_sigma_factor` itself.

---

## verdict:

**SHIP — units bug confirmed and repaired; recalibration measured, not assumed.**
**(REVISED 2026-07-30: items 1-4 stand unchanged; items 5-6 are re-scored on
repaired labels and the acceptance test now lands in its own pre-registered
stop-condition region — see the addendum. The per-player measurement basis for
the ship is intact; the team-level acceptance support is withdrawn.)**

1. `global_sigma_pa_fp = 0.517` is a per-GAME-RATE sigma, not a per-PA sigma
   (PA-weighted 0.516968 vs unweighted 0.518566; the per-PA reading misses the
   measured per-game SD by −52.8%, the rate reading by −1.5%). Exponent on
   PA/game corrected from 1 to 2 in the variance.
2. `fp_proxy` is NOT the BrownU formula — it omits R, RBI and SB (0.9283 FP/game
   of level) — so its SD of 2.3072 was correctly REJECTED as ground truth. The
   canonical per-game hitter FP SD, measured on `fp_h` over 26,199 started 2026
   games, is **3.2502 FP**.
3. Scale corrected by the measured factor **1.517531**, giving an effective slope
   0.784563 and a per-game sigma of 3.1138 FP at mean PA/g — within **4.2%** of
   the 3.2502 truth, against **3.11x too small** before.
4. The per-batter `sigma_factor` needed **no refit** — proven, not assumed: it is
   a re-centred ratio, ridge is scale-equivariant in y, and rescaling the target
   2x / 10x reproduces the factors to `max|Δ| = 2e-15`. It also transfers to
   canonical FP (r = +0.58 / +0.62).
5. *(Re-scored 2026-07-30 on repaired labels — REVERSED.)* The acceptance test
   **no longer passes**: on honest labels SD(resid/sigma) goes 0.927 -> **0.704**
   all-live (target 1.00; the fix moves it AWAY) and 1.080 -> **0.821** MA_v1;
   Brier worsens slightly, 0.1203 -> **0.1269** (MA_v1 0.1203 -> 0.1235). The
   original PASS (1.379 -> 1.045, Brier 0.2603 -> 0.2469) was an artifact of
   grading against corrupted labels. The all-live BEFORE of 0.927 is the
   pre-registered stop condition ("at or below 1.00 before the fix ... the fix
   would have been WRONG to ship"). The reversal holds across the full
   0.05-0.20 hitter-share sensitivity range.
6. *(Re-scored 2026-07-30 — the cited numbers inverted.)* `MATCHUP_LEGACY_SIGMA`
   default stays `0`, but no longer on the original grounds (legacy 0.151 vs
   fixed 0.045 was label-artifact). On honest labels the fixed path is
   *farthest* from 1 (0.296 vs legacy 0.222 vs buggy 0.073); at n=19 nothing is
   demonstrably best, so the default is kept for the per-batter
   heteroskedasticity, not for team-level calibration.

Caveats stated plainly: the team-level acceptance test rests on **10 closed
periods / 19 snapshots** (the original "11 completed periods" wrongly counted
the still-open period 17) — far too small to settle the per-player vs
team-level tension the re-score exposed. The hitter share 0.0889 is a
reconstruction, though one that agrees with the logged-implied sigma to +4.6%.
The canonical-FP measurement is 2026-only because no earlier season has a
canonical per-game FP store; the 2018-2025 panel agrees on the units question
and on the proxy sigma to 0.11%.

---

## ADDENDUM 2026-07-30 — section 5 re-scored on repaired matchup labels; the acceptance-test conclusion REVERSES

### What changed, and why

The 2026-07-29 run of section 5b graded against
`data/outputs/predictions_history.csv` labels that were CORRUPTED: the pre-fix
`fetch_closed_matchup_actuals.py` wrote in-progress single-day scores into
**5 of the 11** labelled live periods as if they were matchup finals (period 13
stored as 25.7-64.5, real final 322.1-331.3; period 15 stored as 22.7-15.0,
real final 552.1-581.4 — with the WRONG winner). Commit `dda7639` (2026-07-30,
track I5) repaired 182 live rows across periods 12-16 from ESPN's authoritative
`totalPoints`, and the nightly now runs `--repair` so future closures
self-heal. This addendum re-runs section 5 (script section 7b) against the
repaired labels. Two accompanying changes:

1. **Open-period guard added to the script** (`_load_live_history`). A non-null
   `actual_*_final` is not necessarily a final: the repair tool refuses
   still-open periods (`PeriodNotFinal`), so period 17 — open Jul 27-Aug 2,
   labelled 3.3-23.3 / 81.1-68.5 by the pre-fix labeller — still carries
   partials. The original run's "11 completed periods" silently included it.
   The guard drops any period whose live labels vary across snapshots (a
   decided, repaired period's labels are one constant pair) and prints the
   exclusion; period 17 re-enters on its own once ESPN closes it.
2. **One day of boxscore drift** (not label-related): `boxscore_hitters.parquet`
   gained Jul 29 games, moving section 7a's games/week 5.870 → 5.748 and the
   reconstructed hitter share 0.0905 → 0.0889 (sigma scale 1.320 → 1.315).
   Sections 1-6 of the script reproduce the 2026-07-29 memo **digit-for-digit**
   (e.g. 0.516968, 3.250239, 0.784563, factor max|Δ| 0.000e+00) — they never
   touch the labels.

### Old vs new (script section 7b; old = corrupt labels, new = repaired labels + open-period guard)

| metric | panel | OLD (2026-07-29, corrupt) | NEW (2026-07-30, repaired) |
|---|---|---|---|
| n snapshots / periods | all-live | 21 / 11 (incl. open p17) | 19 / 10 (closed only) |
| realised spread-error SD | all-live | 56.41 FP | **39.41 FP** |
| model spread sigma BEFORE | all-live | 40.46 FP | 40.52 FP |
| model spread sigma AFTER | all-live | 53.43 FP | 53.30 FP |
| SD(resid/sigma) BEFORE fix | all-live | 1.379 | **0.927** |
| SD(resid/sigma) AFTER fix | all-live | 1.045 | **0.704** |
| Brier BEFORE fix | all-live | 0.2603 | **0.1203** |
| Brier AFTER fix | all-live | 0.2469 | **0.1269** |
| realised spread-error SD | MA_v1 | 61.33 FP | 45.08 FP |
| SD(resid/sigma) BEFORE fix | MA_v1 | 1.503 | **1.080** |
| SD(resid/sigma) AFTER fix | MA_v1 | 1.138 | **0.821** |
| Brier BEFORE fix | MA_v1 | 0.2766 | **0.1203** |
| Brier AFTER fix | MA_v1 | 0.2609 | **0.1235** |
| §6 \|SD(z)−1\|: buggy / legacy / FIXED | all-live | 0.379 / 0.151 / **0.045** | 0.073 / 0.222 / **0.296** |

Robustness: the reversal is NOT an artifact of the new guard. Re-scoring on
repaired labels with period 17's partials still included (the script exactly
as it ran on 2026-07-29) gives SD(z) before/after **0.988 / 0.751** all-live
and **1.136 / 0.864** MA_v1, Brier 0.1738 → 0.1702 / 0.1804 → 0.1727 — same
direction on dispersion; only the tiny Brier edge flips sign with the guard.
Nor is it the share drift: at the old 0.0905 share the sweep row reads 0.702
vs 0.704.

Independent corroboration: the I5 study (`pwin_mean_bias_2026-07-30.md` §4b)
re-computed the same quantities through its own harness (ESPN finals pulled
live, same n = 19 / 10 closed periods, period-clustered bootstrap) BEFORE this
re-run: realized spread SD **39.64 FP** (vs 39.41 here — repaired CSV rounds
finals to 0.1), pre-fix dispersion **0.940 [0.720, 1.140]** (vs 0.927), post-fix
**0.712 [0.546, 0.863]** (vs 0.704). Two harnesses agree; note the I5 bootstrap
CI for the post-fix model EXCLUDES 1.00, i.e. under its interval construction
the widened model's team-level under-confidence is resolvable at 95%, which is
stronger than the ±1-SE framing used above. I5's stated follow-up — "its
team-level confirmation must be re-run on repaired labels" — is what this
addendum executes.

### Did conclusions change? Yes — stated plainly

- **Section 5b: PASS → FAIL.** The pre-registered acceptance test read
  "over-confident before (SD > 1), fix moves SD toward 1". On honest labels
  the BEFORE is 0.927 all-live — inside the memo's own pre-accepted stop
  condition ("at or below 1.00 before the fix ... the fix would have been
  WRONG to ship") — and the fix moves dispersion away from 1 on both panels
  while slightly worsening Brier. The 8.4x dispersion-error shrink and the
  0.0134 Brier gain were label artifacts.
- **Section 6: empirical basis inverted.** "After the fix the hetero path wins
  outright (0.045 vs 0.151)" is withdrawn; on honest labels FIXED is farthest
  from 1 (0.296) and the buggy path closest (0.073). The default stays 0, now
  justified only by the (label-independent) per-batter heteroskedasticity.
- **Section 7, first bullet: withdrawn.** The logged win probabilities were
  not systematically over-confident; the labels were corrupt. On honest labels
  they score Brier 0.1203, SD(z) 0.927 — consistent with the I5 memo's verdict
  ("the defect was the labels, not the model").
- **Sections 1-4 and the units/scale repair itself: UNCHANGED.** The shipped
  per-game hitter sigma was, and remains, measurably ~3.1x below each batter's
  own realised per-game SD (3.2502 FP truth vs ~1.04 shipped); the exponent,
  the 1.517531 scale factor, and the sigma_factor scale-freeness are all
  label-independent measurements.

### The open tension this exposes (not resolved here; n = 19 cannot resolve it)

Per-player, the hitter sigma was provably ~3x too small; yet the team-level
realised spread dispersion (39.41 FP) matches the OLD, narrower team sigma
(40.52 FP) almost exactly, and widening the hitter component over-disperses
(0.704). Both cannot be fully right unless some OTHER component of the
reconstructed team sigma is overstated — the prime suspects being the SP side
(10 starts at the calibrated 8.7261 FP/start is 761.5 of ~902 FP², dwarfing the
hitter share) and the independence assumption across players/games — or the
n=19 panel is simply too small (±0.16 1-SE on SD). **Follow-up registered:**
(a) re-score section 7b as closed periods accrue (the nightly `--repair` keeps
labels honest from here on; ~8-10 more periods remain in 2026); (b) audit the
team-level aggregation — SP per-start sigma realised-vs-model on the same
matchup panel, and cross-player residual correlation — before any decision to
revert or re-scale the shipped hitter fix. Until then the fix stays shipped on
its per-player measurement basis, with the team-level acceptance claim
explicitly retracted.

Reproduce: `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python
scripts/xfp/validate_hitter_sigma_scale.py` (deterministic; no seeds).
