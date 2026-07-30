---
signal: sp_bootstrap_opp_factor (how the matchup adjustment enters the EMPIRICAL-BOOTSTRAP leg of the sp_bench_mc per-start sampler)
formula: >
  For one SP start, the empirical leg of `sp_bench_mc.build_sp_sampler` holds a
  pool E = {x_1 .. x_m} of that pitcher's real trailing per-start BrownU FP
  (production: last 30 started games across 2024-2026, MLB Stats API gameLog),
  and the matchup enters through `opp_factor`
      f = clip(1 / bat_index_recent(opp), 0.80, 1.20).
  Write m_emp = mean(E) and mu_rp3 = xfp_rp3_per_start_sched (falling back to
  xfp_rp3_per_start) — the same mu the parametric leg uses.

  FIVE treatments, all resampling the SAME pool E, differing only in how f enters:

    (a) MULTIPLY  [INCUMBENT — sp_bench_mc.py line ~190]
          X = x * f,           x ~ Uniform(E)
        Predictive law: the empirical law of E scaled by f.

    (b) SHIFT-SELF  (task option (a): "shift by the same location delta the
        parametric leg uses (target - ev)", with the empirical leg's OWN centre
        as ev — the literal leverage_engine `base + (target - ev)` analogue,
        target = m_emp * f, ev = m_emp)
          X = x + m_emp * (f - 1)
        Same mean as MULTIPLY by construction; shape and SD preserved exactly.

    (b2) SHIFT-RP3  (the same delta, but anchored on the PARAMETRIC leg's mean
         so both legs of `blend` are tilted by the identical number of FP)
          X = x + mu_rp3 * (f - 1)

    (c) UNADJUSTED  (task option (c) — pre-accepted null)
          X = x
        The empirical leg carries NO matchup tilt; in `blend` the week's matchup
        sensitivity is then attenuated by the empirical weight w = m/(m + 20).

    (d) OPP-CONDITIONED POOL  (task option (b))
          X = x,  x ~ Uniform(E_band),
          E_band = { starts in E whose own opponent's 2026 bat_index_recent puts
                     them in the same opp_factor band as the upcoming start }
        Bands DECLARED BEFORE RUNNING as f-tertiles of the fixed grid
        [0.80, 0.95), [0.95, 1.05), [1.05, 1.20]. Falls back to the full pool
        when |E_band| < MIN_BAND (declared 8) — the fallback RATE and the pool
        thinness are themselves a reported outcome, per the task's "quantify how
        thin before recommending it".
outcome: >
  y = realized BrownU FP of the NEXT start after the rp3 snapshot
  (boxscore_pitchers.parquet, gs == 1, fp_sp), on the IDENTICAL panel
  validate_band_crps.panel_b() / validate_sp_sampler_tail.py built:
  merge_asof(backward, tolerance 10d, allow_exact_matches=False), marcel_il
  excluded. The panel is hard-asserted row-for-row identical to the persisted
  _crps_panelB_starters.csv (1037 starts, 202 pitchers) before any scoring; a
  mismatch RAISES.

  The empirical pool E for each row is rebuilt AS OF the snapshot date from the
  MLB Stats API gameLog (2024/2025/2026, same call the production
  fetch_pitcher_starts_multi_year makes), keeping only starts strictly BEFORE
  the snapshot date — so the pool never contains the outcome or anything after
  the decision moment. Rows with |E| < MIN_POOL (declared 10) are dropped from
  the contrast and the drop count is reported.
expected_sign: >
  Lower CRPS is better. NO directional prior is asserted on CRPS. MULTIPLY and
  SHIFT-SELF have IDENTICAL predictive means by construction (E[fX] = f*m_emp =
  E[X + m_emp(f-1)]), so they can differ only in shape: MULTIPLY additionally
  scales the SD by f and mirrors the sign asymmetry, SHIFT does neither. The
  CRPS gap is therefore expected to be SMALL, and "CRPS cannot separate them"
  is an anticipated and pre-handled outcome (see the selection rule).

  What IS asserted, and is provable rather than measured: under MULTIPLY,
  P(X <= 0) = P(x <= 0) for every f > 0, because multiplying by a positive
  scalar cannot change a sign. The incumbent's blow-up probability is EXACTLY
  invariant to the opponent. The script verifies this numerically rather than
  assuming it.
theory: >
  BrownU SP FP = K + IP*3.3 - H - 2*ER - BB - HBP has no floor; 170 of these
  1037 real starts (16.39%) finished at FP <= 0, minimum -23.5. The F2 study
  (sp_sampler_tail_family_2026-07-29.md) fixed the PARAMETRIC leg — it had zero
  mass below 0 — and shipped a Gaussian with LOCATION scaling on opp_factor,
  explicitly declaring the EMPIRICAL-BOOTSTRAP leg out of scope. That leg still
  multiplies a bootstrapped REAL start by f, which carries the same asymmetry
  the parametric fix removed: a -15 FP disaster against a top offense (f = 0.83)
  is rescaled to -12.5, i.e. the tough matchup makes the blow-up LESS bad, and
  the probability of a blow-up does not move at all. `blend` is the CLI default
  and routes w = m/(m+20) of its mass through this leg (60% at the production
  30-start pool), so the leg is not a corner case — it is the majority of the
  default sampler.

  A bootstrap has no mean parameter to shift, so the repair is not mechanical:
  either the resampled values are translated (preserving the real shape but
  asserting the matchup is a pure location effect), or the POOL itself is
  conditioned on opponent quality (more principled, far thinner), or the leg
  simply carries no tilt and the parametric leg does all the matchup work.
  This study picks between those, on the panel, by CRPS.
production_target: scripts/xfp/sp_bench_mc.py — build_sp_sampler's EMPIRICAL leg (`prior='empirical'`, and the empirical half of `prior='blend'`). The parametric leg is NOT re-litigated; it keeps the F2 Gaussian + location scaling verbatim. Rule 13: nothing here touches rh3/rp3/rprs2 or baseline xFP.
framing: in-season measurement, single pre-declared 5-way contrast (4 candidates vs the incumbent), BH-FDR over the 4
holdout_years: []
training_years: []
data_window: "rp3 snapshots 2026-06-03 .. 2026-07-09; scored starts 2026-06-04 .. 2026-07-19 — ONE 2026 in-season span, not a multi-year holdout. Empirical pools reach back into 2024-2025 game logs but only as PREDICTOR history, never as scored rows."
validation_script: scripts/xfp/validate_sp_bootstrap_opp_factor.py
date: 2026-07-30
---

# I1 — the empirical-bootstrap leg's matchup adjustment

## The defect (inherited, declared open by F2)

`sp_bench_mc.build_sp_sampler`, empirical leg:

```python
return rng.choice(emp_arr, size=n, replace=True) * opp_factor
```

Two consequences, both structural:

1. **Sign asymmetry.** `opp_factor < 1` means a TOUGHER opponent. Applied to a
   negative bootstrapped start it moves the value *up*, toward zero. The tougher
   the offense, the milder the modeled disaster.
2. **Tail invariance.** `P(X <= 0) = P(x <= 0)` for every `f > 0`. The number a
   bench/start call is *for* — the probability this start blows up — does not
   respond to the opponent at all.

Measured on the sibling P(win) engine at this panel's median (`mu = 9.86`,
`sigma = 8.73`), multiplicative gives `P(FP<=0) = 10.75%` at **every** `f` in
[0.83, 1.20] (spread 0.00pp) while location scaling gives 11.44% -> 4.48%,
monotone, spread 6.97pp.

## Note on holdout_years / training_years

Deliberately **empty**, not the boilerplate `[2024, 2025]`. Nothing is fitted
and no feature is selected here: `m_emp` is an average of observed history,
`mu_rp3`/`sigma` come from the shipped rp3 bundle, `f` comes from
`team_strength_2026.csv`, and the band edges and MIN_POOL/MIN_BAND thresholds
are written in this file before the script ran. The panel is a single 2026
in-season span (see `data_window`); calling it a multi-year holdout would be
false.

## Known limitation, declared before running

`bat_index_recent` in `team_strength_2026.csv` is a **single current-season
snapshot** of each offense, not an as-of-date value. Two places it bites:

- the upcoming start's `f` uses end-of-window offense strength (this is exactly
  what production reads, so the contrast is faithful to the tool);
- treatment (d) bands 2024/2025 historical starts by their opponent's **2026**
  offense, which is an anachronism.

It is applied **identically to all five treatments**, so it cannot favour one —
but it is a real reason to discount (d) specifically, and is reported as such.

## Declared decision metric (written BEFORE running)

**PRIMARY — CRPS, all rows, pure empirical leg (`prior='empirical'`).** The
predictive law is discrete and equally weighted over the transformed pool, so
CRPS is available in *exact closed form* (no MC noise at all):

    CRPS = (1/m) * sum_i |x_i - y|  -  (1/(2 m^2)) * sum_i sum_j |x_i - x_j|

evaluated via the sorted O(m log m) identity. Contrast = paired
**pitcher-clustered** bootstrap of `mean CRPS(candidate) - mean CRPS(MULTIPLY)`,
2000 resamples, seed 20260729 (same helper `validate_band_crps.paired_cluster_bootstrap`),
**BH-FDR at q = 0.05 over the 4 comparisons**, plus the same **2% relative
economic floor** B3 and F2 declared.

**SECONDARY — left-tail calibration and matchup responsiveness** (reported for
all five; used as the declared tie-break):

1. `P(FP <= 0)` averaged over rows, vs the realized **16.39%**.
2. `q10` (the p10 the skill prints) — mean, and share of realized `y` below it.
3. **MONOTONICITY**: `P(FP <= 0)` re-evaluated on a fixed grid
   `f in {0.83, 0.90, 1.00, 1.10, 1.20}` at each row's own pool. A treatment
   passes if `P(FP<=0)` is non-increasing in `f` AND the spread across the grid
   is >= **2.0pp**. MULTIPLY and UNADJUSTED are expected to score exactly 0.00pp.

**SELECTION RULE.**

1. If any candidate beats MULTIPLY by >= 2% relative CRPS and passes BH-FDR,
   ship the lowest-CRPS such candidate. Done.
2. Otherwise CRPS has not separated the treatments. Then apply the **do-no-harm
   + responsiveness** rule: among candidates whose dCRPS 95% CI does **not**
   place them worse than the incumbent by more than the 2% floor (i.e. not
   materially worse), keep only those that PASS the monotonicity criterion, and
   pick the one with the smallest `|mean P(FP<=0) - 16.39%|`. The justification
   is declared here and not after the fact: a bench/start sampler whose blow-up
   probability is provably invariant to the opponent cannot do the job the tool
   exists for, so when CRPS is indifferent, responsiveness decides.
3. If no candidate survives (2), the verdict is **NO-CHANGE / document the
   attenuation** — treatment (c) UNADJUSTED with an explicit note that `blend`'s
   matchup sensitivity is scaled by `(1 - w)`, `w = m/(m+20)`.

**Pre-accepted nulls.** Both "(c) leave the bootstrap alone" and "keep MULTIPLY"
are legitimate outcomes and will be recorded as such if the numbers say so.
(d) is pre-committed to be **rejected on thinness alone** if its median banded
pool size is < 8 or its fallback-to-full-pool rate exceeds 40%, regardless of
CRPS — a treatment that silently degenerates to another treatment most of the
time is not a treatment.

## Scope limits (declared)

- The **parametric leg is untouched**: F2's Gaussian + location scaling stands,
  and `sigma` is not re-tuned (that would be an undeclared second test).
- `_non_sp_total`'s lognormal for hitter/RP weekly TOTALS is unchanged, as in F2.
- No FEATS list, no rh3/rp3/rprs2 value moves (Rule 13).

---

## RESULT

`python scripts/xfp/validate_sp_bootstrap_opp_factor.py`, 2026-07-30.

### Panel

Reconstructed with `validate_sp_sampler_tail.build_rp3_single_start_panel` and
**hard-asserted identical** to `_crps_panelB_starters.csv` — same 1037 rows, same
`(pitcher, game_pk)` keys, same `mu`/`sigma`/`actual` to 1e-9. `marcel_il`
excluded (3414 rows). Realized **P(FP<=0) = 170/1037 = 16.39%**, minimum
**-23.5 FP**.

**Window: snapshots 2026-06-03 .. 2026-07-09, scored starts 2026-06-04 ..
2026-07-19.** One 2026 in-season span. Empirical pools reach back into
2024/2025 game logs, but only as predictor history.

| quantity | value |
|---|---|
| game-log store fetched | 8,410 started games, 202 pitchers (2024-2026) |
| pool size (<=30, strictly pre-snapshot) | median **30**, mean 24.5 |
| rows dropped by the declared `MIN_POOL = 10` | 108 / 1037 (**10.4%**) |
| **scored panel** | **929 starts, 170 pitchers** |
| opp_factor on the panel | mean 1.0256, **range [0.935, 1.149]** |
| (d) banded sub-pool | median **18**, mean 16.2; fallback-to-full **19.3%** |

Two things worth flagging before the numbers are read:

- **The panel's `opp_factor` range is [0.935, 1.149], much narrower than the
  [0.80, 1.20] clip.** 2026 `bat_index_recent` simply does not spread the 30
  offenses as far as the clip allows. So every effect measured here is measured
  under a *modest* real tilt; the declared monotonicity grid deliberately
  exercises the full clip instead.
- **(d) survived the thinness pre-commitment** (median band pool 18 >= 8,
  fallback 19.3% <= 40%). It is therefore judged on the numbers, not dismissed.

### Closed-form verification

`crps_sample` is exact for a finite equally-weighted sample, so it is checked
against a brute-force numerical integral of `(F - H)^2` on a 400,001-point grid
over 20 random (pool, y) pairs: **max relative error 3.57e-05**. There is no
Monte Carlo anywhere in the scoring.

Construction checks the pre-registration asserted:

- `max |mean(multiply) - mean(shift_self)| = 8.88e-15` — the two treatments
  share a mean exactly, so any CRPS difference is **shape only**.
- `SD(multiply) / SD(pool)` equals `f` to **4.44e-16** — the incumbent rescales
  spread by the matchup factor; the translation does not.

### PRIMARY — exact CRPS + declared left-tail calibration

| treatment | n | CRPS | CRPS y>0 | CRPS y<=0 | pred P(FP<=0) | \|err\| vs 16.39% | mean q10 | below q10 |
|---|---|---|---|---|---|---|---|---|
| **multiply (INCUMBENT)** | 929 | 5.5864 | 4.4259 | 11.5185 | 14.52% | **1.87pp** | -1.066 | 13.78% |
| **shift_self** | 929 | **5.5841** | 4.4117 | 11.5770 | 13.98% | 2.41pp | -0.768 | 13.99% |
| shift_rp3 | 929 | **5.5766** | 4.4059 | 11.5611 | 13.95% | 2.44pp | -0.778 | 13.99% |
| unadjusted | 929 | 5.5842 | 4.4542 | 11.3603 | 14.52% | 1.87pp | -1.044 | 13.56% |
| opp_conditioned | 929 | 5.6816 | 4.5345 | 11.5453 | 14.41% | 1.98pp | -0.504 | 15.07% |

### Paired pitcher-clustered contrasts vs the incumbent

2000 resamples, seed 20260729, BH-FDR q = 0.05 over 4, 2% economic floor:

| candidate | n | pitchers | dCRPS | rel % | ci95 | boot_p | CI excl 0 | econ | BH-FDR |
|---|---|---|---|---|---|---|---|---|---|
| shift_self | 929 | 170 | -0.0023 | **-0.04%** | [-0.0104, +0.0061] | 0.579 | no | **fail** | no |
| shift_rp3 | 929 | 170 | -0.0098 | -0.17% | [-0.0179, -0.0015] | 0.022 | yes | **fail** | yes |
| unadjusted | 929 | 170 | -0.0022 | -0.04% | [-0.0284, +0.0255] | 0.844 | no | **fail** | no |
| opp_conditioned | 929 | 170 | **+0.0952** | **+1.70%** | [+0.0377, +0.1568] | 0.00025 | yes | fail | yes |

**CRPS does not separate the four sane treatments.** Every candidate sits within
0.2% relative of the incumbent — two orders of magnitude inside the declared 2%
floor. `shift_rp3` is statistically distinguishable (CI excludes 0) but the
effect is 0.17%, i.e. real and irrelevant. This was the anticipated outcome and
is exactly why the selection rule has a step 2.

**(d) opp_conditioned is the one clear finding on CRPS: it is WORSE**, +1.70%
relative, CI [+0.0377, +0.1568], p = 0.00025. Cutting a 30-start pool down to
an 18-start band throws away more estimation precision than the opponent
conditioning buys back, on a panel whose real `f` spread is only [0.935, 1.149].
It is also **anachronistic by construction** (2024/2025 starts banded by their
opponent's *2026* offense) and degenerates to the full pool 19.3% of the time.
**Recommendation: do not pursue the opponent-conditioned pool.** It is more
principled in theory and measurably worse here, and the thinness is the reason.

### SECONDARY — P(FP<=0) across the DECLARED opp_factor grid

| treatment | f=0.83 | f=0.90 | f=1.00 | f=1.10 | f=1.20 | spread | non-incr. | **pass** |
|---|---|---|---|---|---|---|---|---|
| multiply (INCUMBENT) | 14.52% | 14.52% | 14.52% | 14.52% | 14.52% | **0.00pp** | yes | **NO** |
| **shift_self** | 17.90% | 16.33% | 14.52% | 12.39% | 10.96% | **6.94pp** | yes | **YES** |
| shift_rp3 | 17.78% | 16.37% | 14.52% | 12.31% | 11.04% | 6.74pp | yes | YES |
| unadjusted | 14.52% | 14.52% | 14.52% | 14.52% | 14.52% | **0.00pp** | yes | **NO** |
| opp_conditioned | 14.52% | 14.52% | 14.57% | 14.13% | 14.13% | 0.43pp | **no** | **NO** |

The incumbent's 0.00pp is not a small effect — it is an **identity**. Multiplying
by a positive scalar cannot move a sign, so `P(X <= 0) = P(x <= 0)` for every
`f`. The measurement confirms the algebra rather than discovering it.

Note also that (d)'s response is **non-monotone and 0.43pp** — conditioning the
pool on opponent quality did not even produce a matchup response, because the
band membership is dominated by which starts happen to be in the pool.

### Declared selection rule, executed

1. Step 1 does **not** fire: no candidate clears 2% relative CRPS.
2. Step 2 — do-no-harm survivors (adverse CI end < +2% rel):
   `shift_self, shift_rp3, unadjusted`. `opp_conditioned` is excluded, its
   adverse end being +2.8% relative. Monotonicity survivors:
   `shift_self, shift_rp3`. Intersection: **`shift_self`, `shift_rp3`**.
   Tie-break on `|P(FP<=0) - 16.39%|`: `shift_self` **2.41pp** vs `shift_rp3`
   **2.44pp**.

**WINNER = `shift_self`** — `X = bootstrap(E) + mean(E) * (opp_factor - 1)`.

The tie-break margin (0.03pp) is negligible, so the choice between the two shift
variants is effectively arbitrary on this metric. `shift_self` is the one to
prefer on grounds the rule did not have to invoke: it keeps the empirical leg
anchored on its **own** centre, so a pitcher whose real history disagrees with
rp3 does not have rp3's level smuggled into his bootstrap through the tilt.

### The honest complication, and a POST-HOC check for it

**The incumbent scores a BETTER pooled `|P(FP<=0) - 16.39%|` than the winner
(1.87pp vs 2.41pp).** That must be said plainly rather than buried, and it needs
an answer, because on its face it looks like the fix made calibration worse.

The answer is that a pooled average cannot distinguish a well-calibrated
conditional predictor from an unresponsive constant. `multiply`'s predicted
P(FP<=0) is per-row invariant to `f` by identity, so it is *forced* to sit near
the unconditional realized rate — that is what unresponsiveness does, not what
skill does. The question the pooled number cannot ask is whether the realized
blow-up rate **actually moves** with `opp_factor`.

**POST-HOC (not pre-registered, reported as such):** split the 929 rows at the
median `opp_factor` (1.0263) and compare predicted vs realized within each half.

| half | n | mean f | **realized P(FP<=0)** | multiply | **shift_self** | shift_rp3 | unadjusted | opp_cond |
|---|---|---|---|---|---|---|---|---|
| TOUGHER (f <= median) | 492 | 0.9874 | **17.28%** | 14.41% | **14.68%** | 14.66% | 14.41% | 14.40% |
| EASIER (f > median) | 437 | 1.0689 | **15.33%** | 14.65% | **13.20%** | 13.15% | 14.65% | 14.42% |
| **delta (tough - easy)** | | | **+1.95pp** | **-0.24pp** | **+1.48pp** | +1.51pp | -0.24pp | -0.02pp |

Real starts against the tougher half blow up **+1.95pp more often**. Only the
shift treatments predict that at all (+1.48pp / +1.51pp); the incumbent and the
unadjusted leg predict **-0.24pp — the wrong sign**, and that -0.24pp is purely
a composition artifact of which rows landed in which half, since their per-row
prediction cannot depend on `f`. So the responsiveness the tie-break bought is
pointed at a real effect, of roughly the right size, and it is the pooled
calibration number that is misleading — not the fix.

This is a diagnostic, not a decision metric, and it was not pre-declared. n=492 /
437 with ~150 negatives total, so the +1.95pp realized delta is not itself
tightly estimated. It supports the declared verdict; it did not produce it.

### Behaviour change — what a bench/start call actually surfaces

Panel-wide means, 929 starts:

| treatment | mean p10 (FP) | mean P(FP<=0) | CRPS |
|---|---|---|---|
| multiply (before) | -1.066 | 14.52% | 5.5864 |
| **shift_self (after)** | **-0.768** | **13.98%** | 5.5841 |

Those pooled means move little **because the panel's `f` averages 1.0256** — the
change is a re-pointing, not a level shift. The per-start effect at real inputs
(real 30-start pools, real rp3 mu/sigma from the 2026-07-09 snapshot, real
`bat_index_recent`, 400k draws) is where it shows, and it goes **both ways**:

| pitcher | f | leg | p10 before | p10 after | P(FP<=0) before | P(FP<=0) after |
|---|---|---|---|---|---|---|
| Skenes, Paul | 0.955 (tough) | empirical | +0.48 | **-0.18** | 6.68% | **13.43%** |
| Meyer, Max | 0.955 (tough) | empirical | +0.19 | **-0.37** | 6.73% | **10.05%** |
| Weathers, Ryan | 0.935 (tough) | empirical | -0.75 | **-1.48** | 16.75% | **20.05%** |
| Warren, Will | 0.935 (tough) | blend | -2.65 | **-3.49** | 18.03% | 18.03% |
| Márquez, Germán | 1.149 (weak) | empirical | -11.61 | **-9.57** | 39.91% | **36.51%** |
| Matthews, Zebby | 1.083 (weak) | empirical | -2.67 | **-1.73** | 26.76% | **16.78%** |
| Kremer, Dean | 1.047 (weak) | empirical | -0.18 | **+0.38** | 13.34% | **6.65%** |

Skenes against a top-decile offense goes from a **6.68% to a 13.43%** modeled
blow-up — the number doubles, and the old value could not have moved no matter
who he faced. Márquez against a weak offense goes the other way. Mean per start
is preserved to **<= 0.004 FP** everywhere (verified on all 111 pitchers in the
final snapshot).

**A real 6-start week through the CLI-default `blend`** (real pools, real rp3,
real opponents, 400k trials):

| | mean | p10 | p05 | p01 |
|---|---|---|---|---|
| before | 72.37 | 40.66 | 31.44 | **13.89** |
| after | 72.36 | 41.77 | 32.80 | **16.03** |

And on the bench decision itself — the thing the skill outputs:

| bench candidate | f | dEV before | dEV after | d(p10) before | d(p10) after | d(p01) before | d(p01) after |
|---|---|---|---|---|---|---|---|
| Warren, Will | 0.935 | -9.18 | -9.18 | -7.45 | -7.23 | -6.15 | -5.93 |
| **Márquez, Germán** | 1.149 | -5.42 | -5.41 | -1.38 | **-2.10** | **+2.06** | **+0.54** |

The EV of a bench is unchanged, as it must be. What changes is the *downside*
case for benching: under the old multiply, sitting Márquez looked like it bought
**+2.06 FP of p01 protection**; that was largely an artifact of his spread being
inflated by `f = 1.149`, and the real figure is **+0.54**. A tail-protection
argument for a bench against a *weak* offense was roughly 4x overstated.

### Silent-default removals

- The empirical pool is now checked for non-finite values in `build_sp_sampler`
  (naming the pitcher) instead of producing silent NaN draws.
- `_bootstrap_draws` raises on an empty pool, a non-finite pool mean, and a
  non-finite `opp_factor`. The old expression returned NaNs or an empty array.

### Tests

`tests/test_sp_bootstrap_opp_factor_2026_07_30.py`, 15 tests.
**Verified to FAIL against the old behaviour: 11 of 15 fail** when the leg is
reverted to `rng.choice(...) * opp_factor` and the new guards are removed
(5 fail from the one-line sign revert alone). The load-bearing ones:

- `P(FP<=0)` non-increasing in `opp_factor` with a > 5pp spread across the clip
  — the direct mirror of F2's
  `test_opp_factor_scales_location_not_the_finished_draw`, and impossible to
  satisfy under any multiply.
- the worst modeled start must be **worse** against a tough offense than a weak
  one, and must reach below the worst REAL start in the pool.
- SD must equal the pool's SD at every `opp_factor` (a multiply scales it by f).
- the same monotonicity through the CLI-default `blend` at w = 30/50.
- the draws are still a bootstrap of the real starts, shifted — and specifically
  **not** the old rescaled pool (direct anti-revert guard).
- the mean still equals `m_emp * f` (the shape-only invariant that licenses
  shipping on a tie-break).
- every new failure path raises.

Full suite: **1246 passed, 0 failed** (baseline 1210 + 15 here + concurrent
agents' additions).

### Open items (NOT done here)

1. **`_non_sp_total` still draws lognormal** for hitter/RP weekly totals —
   unchanged, as in F2.
2. **The opponent-conditioned pool is measured and rejected**, not shelved. If
   it is ever revisited it needs an as-of-date team-strength series (so
   historical starts are banded by contemporaneous offense) and a panel with a
   wider real `f` spread; neither exists today.
3. The `f` clip is [0.80, 1.20] but 2026 `bat_index_recent` only reaches
   [0.935, 1.149]. Whether the clip is doing anything at all is a separate
   question and was not tested here.

---

verdict: >
  SHIP shift_self — the empirical-bootstrap leg now TRANSLATES resampled real
  starts by `mean(E) * (opp_factor - 1)` instead of multiplying by `opp_factor`.
  CRPS was INDIFFERENT (5.5841 vs 5.5864, -0.04% rel, ci95 [-0.0104, +0.0061],
  p = 0.579 — nowhere near the 2% economic floor), so step 1 of the declared
  rule did not fire and this shipped on the pre-declared **step-2 responsiveness
  tie-break**: the incumbent's P(FP<=0) is 0.00pp responsive to the opponent as
  an algebraic identity, while the winner moves 17.90% -> 10.96% monotonically
  across the clip. Do-no-harm was verified (adverse CI end -0.04%, far inside
  the floor) and the mean is preserved exactly (8.88e-15). A POST-HOC
  conditional check, reported as post-hoc, confirms the direction: realized
  P(FP<=0) is +1.95pp higher against the tougher half of matchups and only the
  shift treatments predict it (+1.48pp vs the incumbent's -0.24pp, wrong sign).
  Option (b) OPP-CONDITIONED POOL is **measured and REJECTED**: significantly
  WORSE CRPS (+1.70% rel, ci95 [+0.0377, +0.1568], p = 0.00025), a non-monotone
  0.43pp matchup response, a banded pool of median 18 vs the full 30, and a
  19.3% degenerate-fallback rate. Option (c) UNADJUSTED was eligible on
  do-no-harm but fails the responsiveness criterion for the same identity
  reason as the incumbent. Rule 13 respected — no rh3/rp3/rprs2 or baseline xFP
  value moves.
