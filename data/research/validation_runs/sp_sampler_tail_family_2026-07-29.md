---
signal: sp_sampler_tail_family (per-start FP distribution family for the sp_bench_mc parametric leg)
formula: >
  For one SP start with rp3 predictive mean mu (= xfp_rp3_per_start_sched, falling
  back to xfp_rp3_per_start) and band sigma s (= xfp_rp3_sigma, the DISPLAY band,
  alpha_global = 2.41 — this is literally what sp_bench_mc reads today via
  build_matchup_dashboard.load_projections), three candidate families, each
  moment-matched to (mean = mu, SD = s):

    (1) LOGNORMAL  [INCUMBENT — sp_bench_mc._lognormal_draws]
          s2  = ln(1 + s^2/mu^2);  lmu = ln(mu) - s2/2
          X   = LogNormal(lmu, sqrt(s2))          support (0, inf)

    (2) GAUSSIAN
          X   = Normal(mu, s)                     support (-inf, inf)

    (3) SHIFTED LOGNORMAL, shift c = 30.0 FP (DECLARED BEFORE RUNNING; the
        observed single-start minimum in the panel is -23.5 FP, so support
        starts strictly below every observed outcome; c is NOT fitted)
          Z   = LogNormal moment-matched to (mean = mu + c, SD = s)
          X   = Z - c                             support (-c, inf)

  CRPS is scored in closed form for all three, on ALL rows including y <= 0,
  using the energy identity CRPS = E|X - y| - 0.5*E|X - X'| (Gneiting & Raftery
  2007). For a lognormal and y <= 0 this collapses to
          CRPS = mu*(2 - 2*Phi(sigma_log/sqrt(2))) - y
  so the incumbent is scored on the 170 negative starts rather than having them
  dropped — the drop is what hid the defect. Shifted-lognormal CRPS uses
  translation invariance: CRPS_{Z-c}(y) = CRPS_Z(y + c). Every closed form is
  verified against a 200k-draw empirical CRPS on random rows and the max
  relative error is reported; a mismatch above 1e-3 raises.

  Left-tail quantities per family (predicted vs realized):
          P(FP <= 0)   analytic per row, averaged over rows
          q10          analytic 10th percentile per row
          pinball at q = 0.10 against that q10
outcome: >
  y = realized BrownU FP of the NEXT start after the snapshot
  (boxscore_pitchers.parquet, gs == 1, fp_sp), paired to the rp3 snapshot by
  merge_asof(backward, tolerance 10d, allow_exact_matches=False) — the identical
  panel construction validate_band_crps.panel_b() uses. n = 1037 starts,
  202 pitchers, marcel_il rows excluded.
expected_sign: >
  Lower CRPS is better. Directional prior IS asserted here (unlike the B3
  measurement study): the incumbent lognormal assigns exactly zero density to
  FP <= 0 while 16.4% of real starts land there, so it must lose. What is NOT
  pre-judged is WHICH replacement wins — Gaussian and shifted-lognormal are
  both pre-accepted, and "shifted lognormal beats Gaussian" is a live outcome.
theory: >
  BrownU SP scoring is K + IP*3.3 - H - 2*ER - BB - HBP with no floor. A
  3-inning 7-run start is deeply negative (panel min -23.5 FP). The single most
  decision-relevant event for a bench/start call is the blow-up, and a
  distribution on (0, inf) prices it at probability zero: the modeled p10 and
  P(FP <= 0) that Josh reads off sp_bench_mc are therefore not conservative
  estimates, they are structurally unreachable. A support-correct family is a
  prerequisite for the downside half of the tool meaning anything.
production_target: scripts/xfp/sp_bench_mc.py — build_sp_sampler parametric leg ('rp3' mode) and the parametric half of 'blend'. The empirical-bootstrap leg is NOT touched (it already resamples real negatives).
framing: in-season measurement, single pre-declared 3-way contrast (2 comparisons vs incumbent)
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_sp_sampler_tail.py
date: 2026-07-29
verdict: >
  SHIP GAUSSIAN. CRPS 5.3982 vs incumbent lognormal 5.8298 (dCRPS -0.4317,
  -7.40% relative, pitcher-clustered bootstrap ci95 [-0.4990, -0.3640],
  boot_p = 0.00025, BH-FDR pass, economic floor pass). Shifted lognormal also
  beat the incumbent (5.4551, -6.43%) but lost the declared tie-break on
  left-tail calibration. Swapped into sp_bench_mc.build_sp_sampler's parametric
  leg; empirical bootstrap leg untouched.
---

# F2 — the SP bench/start sampler cannot produce a disaster start

## The defect

`sp_bench_mc.build_sp_sampler` has three modes. `'empirical'` bootstraps real
per-start FP from the MLB gameLog and reproduces negatives correctly.
`'rp3'` and `'blend'` (**`blend` is the CLI default**) route through
`_lognormal_draws`, a moment-matched lognormal. A lognormal has support
`(0, inf)`. Therefore:

    P(modeled FP <= 0) == 0, exactly, for every pitcher, every start.

Measured on the single-start panel the CRPS study already built
(`_crps_panelB_starters.csv`, n = 1037): **170 of 1037 real starts (16.39%)
finished at FP <= 0.** The blow-up — the entire reason a bench/start MC exists
— is modeled as impossible.

Secondary evidence already in hand from B3's descriptive side-cell: on the 867
rows where a lognormal is scorable at all, its CRPS was **4.7744 vs the
Gaussian's 4.3449** at the same x2.41 band, i.e. the incumbent is 9.9% worse
*even after* the rows it cannot represent are removed from its own scoring.

## Note on holdout_years

As in B3, the frontmatter train/holdout years are the *model bundles'* years,
carried for directory schema consistency. There is no screen here: no feature is
selected and **no parameter is fitted** — `mu` and `s` come from the shipped rp3
bundle, and the shift `c = 30.0` is declared in this file before the script was
run, not tuned. All rows are 2026, out-of-sample by year for every production
`.pkl` (TRAIN_YEARS end 2025).

## Declared decision rule (written BEFORE running)

**Primary metric — CRPS, all 1037 rows.** Paired pitcher-clustered bootstrap
(2000 resamples, seed 20260729) of `mean CRPS(candidate) - mean CRPS(lognormal)`,
BH-FDR at q = 0.05 across the 2 comparisons, plus the same **2% relative
economic floor** B3 declared.

**Secondary metric — left-tail calibration** (reported for all three, used only
as the tie-break and as the behavior-change quantification):

1. `P(FP <= 0)` averaged over rows, vs the realized **16.39%**.
2. Bottom-decile coverage: share of realized y below each family's analytic
   per-row `q10`. Target 10%.
3. Pinball loss at q = 0.10.

**Selection rule.** Swap in the candidate with the lowest CRPS *provided* it
beats the incumbent by >= 2% relative AND passes BH-FDR. If the two candidates
are within 2% of each other on CRPS, break the tie by absolute error of
`P(FP <= 0)` against 16.39%. If NEITHER candidate clears the floor vs the
incumbent, the verdict is NO-CHANGE and the lognormal stays — the zero-mass
argument alone does not license a swap.

**Pre-accepted null.** "Lognormal is fine, do not touch sp_bench_mc" is a
legitimate outcome of this run and will be recorded as such if the numbers say
so.

## Scope limits (declared)

- The **empirical bootstrap leg is untouched.** It already reproduces negatives.
- `_non_sp_total` (hitters + RPs, weekly TOTALS) also calls `_lognormal_draws`.
  A weekly *total* is a sum over many events and is far less structurally
  wrong on `(0, inf)`. It is **NOT in this contrast** and is NOT changed.
- `sigma` is NOT re-tuned. B3 already located the CRPS-optimal multiplier for
  this frame; re-litigating alpha here would be a second, undeclared test. The
  band in use (x2.41) is held fixed so the contrast is purely the family.

## RESULT

`python scripts/xfp/validate_sp_sampler_tail.py`, 2026-07-29.

### Panel

n = **1037** single starts, **202** pitchers, `marcel_il` excluded (3414 rows).
The script reconstructs the panel with `validate_band_crps`'s own snapshot
loader and merge and then **hard-asserts** it is row-for-row identical to that
study's persisted `_crps_panelB_starters.csv` (same 1037 rows, same
`(pitcher, game_pk)` keys, same `mu`/`sigma`/`actual` to 1e-9). A mismatch, or a
missing reference panel, raises — there is no fallback panel.

Realized share of starts at **FP <= 0: 170/1037 = 16.39%**, minimum **-23.5 FP**.
`mu` mean 10.054, `sigma` mean 8.642 (`xfp_rp3_sigma`, the x2.41 display band —
which is exactly what `sp_bench_mc` reads).

### Closed-form verification

Two independent checks, both must pass or the run aborts:

- **Branch continuity (analytic, MC-free).** The newly-derived `y <= 0` lognormal
  CRPS branch must agree with the published `y > 0` form in the limit `y -> 0`.
  Max relative gap **4.75e-08**.
- **Closed form vs 1,000,000-draw empirical CRPS**, on 15 negative-`y` and 15
  positive-`y` rows. The Gaussian form is *exact*, so its discrepancy is pure MC
  noise and is used as the self-calibrating tolerance (no hand-picked threshold):
  noise floor **3.46e-03**; lognormal **1.83e-03**, shifted lognormal
  **2.18e-03**; both inside 3x the floor.

### Primary + declared secondary

| family | n | CRPS | CRPS y>0 | CRPS y<=0 | pred P(FP<=0) | \|err\| vs 16.39% | share below q10 | mean q10 | pinball q10 |
|---|---|---|---|---|---|---|---|---|---|
| lognormal (INCUMBENT) | 1037 | **5.8298** | 4.7744 | 11.2124 | **0.00%** | 16.39pp | 23.53% | **+3.078** | 2.1627 |
| **gaussian** | 1037 | **5.3982** | 4.3449 | 10.7695 | **12.99%** | **3.40pp** | **12.92%** | **-1.022** | **1.8365** |
| shifted lognormal (c=30) | 1037 | 5.4551 | 4.4522 | 10.5701 | 11.78% | 4.61pp | 14.18% | -0.205 | 1.8649 |

The `CRPS y>0` column reproduces the B3 side-cell exactly (4.7744 vs 4.3449 on
the 867 scorable rows) — this study's contribution is the `y <= 0` column, which
B3 had to drop and which is where the incumbent is charged for the region it
prices at zero.

### Paired contrasts vs the incumbent

2000 pitcher-clustered resamples, seed 20260729:

| candidate | n | pitchers | dCRPS | rel % | ci95 | boot_p | CI excl 0 | econ | BH-FDR |
|---|---|---|---|---|---|---|---|---|---|
| gaussian | 1037 | 202 | -0.4317 | **-7.40%** | [-0.4990, -0.3640] | 0.00025 | yes | pass | pass |
| shifted lognormal | 1037 | 202 | -0.3747 | -6.43% | [-0.4247, -0.3261] | 0.00025 | yes | pass | pass |

Head-to-head `shifted - gaussian`: **+0.0570 (+1.06% rel)**, ci95
[+0.0363, +0.0778], p = 0.0003. Statistically separated but **inside the declared
2% economic floor**, so the pre-declared tie-break fires: `|P(FP<=0) - 16.39%|`
is 3.40pp for the Gaussian vs 4.61pp for the shifted lognormal.

**WINNER = GAUSSIAN.** Both candidates satisfied the selection rule; the Gaussian
won on CRPS *and* on the tie-break, so the choice is not knife-edge.

Note the Gaussian at 12.99% still **under**-states P(FP<=0) vs the realized
16.39% (real per-start FP is left-skewed, which is also why the bottom-decile
coverage is 12.92% rather than 10%). That residual is honest and is NOT patched
here — patching it would mean re-tuning sigma or adding skew, neither declared.

### Behavior change — what the bench/start consumer actually reads

Panel-wide means of the two numbers Josh reads off a bench/start call:

| | mean p10 (FP) | mean P(FP <= 0) |
|---|---|---|
| lognormal (before) | **+3.078** | **0.00%** |
| gaussian (after) | **-1.022** | **12.99%** |

The "10th percentile of a start" was a **positive score**. It is now negative.

A concrete week, **fully real inputs** (rp3 `mu`/`sigma` from the panel's latest
snapshot 2026-07-09, `bat_index_recent` from `team_strength_2026.csv`,
`--prior rp3` so no synthetic history enters), 400k trials:

| pitcher | mu | opp | opp_factor | p10 before | P(FP<=0) before | p10 after | P(FP<=0) after |
|---|---|---|---|---|---|---|---|
| Skubal, Tarik | 16.54 | NYY | 1.122 | +8.71 | 0.00% | +7.39 | 1.68% |
| Brown, Hunter | 11.36 | BOS | 0.985 | +3.71 | 0.00% | +0.02 | 9.95% |
| Soriano, José | 12.01 | SEA | 1.029 | +4.34 | 0.00% | +1.19 | 7.79% |
| Warren, Will | 9.69 | ATL | 1.049 | +2.82 | 0.00% | -1.00 | 12.19% |
| Bieber, Shane | 7.40 | COL | 1.039 | +1.51 | 0.00% | -3.47 | 18.82% |
| **Márquez, Germán** | 6.41 | LAD | 0.965 | **+0.99** | **0.00%** | **-4.98** | **23.86%** |

The marginal bench candidate's p10 moves **+0.99 -> -4.98 FP (-5.97)** and his
blow-up probability goes from **0% to 23.86%**. Through `run_mc`'s 6-start week
total: mean is unchanged (66.13 -> 66.14, as it must be — the family is
moment-matched), but the disaster tail widens materially:

| | mean | p10 | p05 | p01 |
|---|---|---|---|---|
| before | 66.13 | 42.22 | 37.86 | **30.83** |
| after | 66.14 | 38.71 | 30.94 | **16.34** |

**p01 of the SP week widens by 14.5 FP.** The EV of benching Márquez is
identical either way (**-6.20 FP** both), so this does not flip a
maximize-EV bench call — what it changes is every *downside* number attached to
that call, and therefore the P(win) tail that `--cap-rule` decisions and the
"is this start worth the cap slot" question lean on. Nothing about the headline
EV ranking moves.

For the CLI-default `blend` mode the parametric leg carries `(1 - w)`,
`w = n_emp/(n_emp+20)`, so the shift is diluted but never erased — e.g. at
`n_emp = 30` (`w = 0.60`) the blended P(FP<=0) goes 9.84% -> 15.03%, and at
`n_emp = 2` (Rodon-post-IL) 1.49% -> 13.30%.

### Post-hoc correctness fix: opp_factor direction

**Not pre-registered** — found while implementing, reported as post-hoc, with
its own measurement. It is a sign repair, not a fitted model choice.

`run_mc` applied the matchup adjustment as `draw * opp_factor` *after* sampling.
With support on `(0, inf)` that is monotone and harmless. Once negatives exist it
is wrong in two ways, measured at the panel median (`mu = 9.86`, `sigma = 8.73`):

| opp_factor | multiply: P(FP<=0) | multiply: p10 | location-scale: P(FP<=0) | location-scale: p10 |
|---|---|---|---|---|
| 0.83 (toughest offense) | 12.94% | -1.10 | **17.43%** | -3.01 |
| 1.00 | 12.94% | -1.33 | 12.94% | -1.33 |
| 1.20 (weakest offense) | 12.94% | -1.60 | **8.77%** | +0.64 |

A post-hoc multiply is scale-only: it leaves `P(FP<=0)` **completely invariant to
the opponent**, and it shrinks a blow-up *toward zero* against the best offenses.
`opp_factor` now goes **into** the sampler and scales the parametric leg's
LOCATION (`N(mu * opp_factor, sigma)`; sigma deliberately not scaled, per the
declared scope). The empirical leg still multiplies its bootstrapped FP exactly
as before — untouched by declared scope, and it carries the same asymmetry on
its own negative draws. **Open item, needs its own study** (see below).

### Silent-default removals (2026-07-28 ROOT-bug pattern)

Found while implementing, no measurement needed — these are failure modes, not
model choices:

- A pitcher absent from `rp3_map` arrived at the sampler as `rp3_mean = 0`
  (`.get('per_start_sched') or .get('per_start') or 0`) and the old
  `_lognormal_draws` `mu <= 0` branch quietly turned that into
  `N(0, sigma)` — a **0-FP starter, confidently simulated**. `build_sp_sampler`
  now **raises** (naming the pitcher) whenever the parametric leg is required and
  `rp3_mean` is missing / non-finite / non-positive. `_gaussian_draws` raises on a
  non-finite `mu` or a non-positive `sigma` instead of the old
  `max(sigma, 1e-6)` floor.
- The MC-not-earning-its-complexity fallback ranking imputed `adj_EV = 0.00` for a
  pitcher with no rp3 row, which would masquerade as the **worst** start and
  drive a bench recommendation. It now prints `n/a` and sorts last.

`SIGMA_PER_SP_START` remains a documented fallback for a missing **sigma** only
(the mean has no defensible default; a spread does).

### Consistency note

`run_matchup_leverage._blend_draws` was **already Gaussian** (`rng.normal`). This
fix brings `sp_bench_mc` in line with its sibling engine rather than inventing a
new convention.

### Tests

`tests/test_sp_sampler_tail_2026_07_29.py`, 36 tests. Verified to FAIL against
the pre-fix sampler: 8 of 9 key assertions fail when the old lognormal
`build_sp_sampler` is restored (the 9th is a source-inspection guard on
`run_mc`, which that harness did not revert). The load-bearing ones:

- `P(FP <= 0) > 0` for both `rp3` and `blend` — old value was exactly 0.
- `P(FP <= 0)` within 6pp of the realized 16.39% at the panel-average inputs.
- the sampler can reach the worst real start (-23.5 FP).
- p10 at panel-average inputs is negative.
- a direct anti-revert guard: the parametric leg must not be strictly positive.
- `opp_factor` monotonicity: `P(FP<=0)` strictly decreasing in `opp_factor`, with
  a >5pp spread across [0.83, 1.20] — this fails under a scale-only multiply.
- moments preserved (mean/SD unchanged to 0.10).
- the empirical leg is still a bootstrap over the real FPs, blend weight math
  unchanged, blend mixes both legs at the declared weight.
- every silent-default path raises, with the pitcher named.

Full suite: **1005 passed, 0 failed** (baseline 931 + 36 here + a concurrent
agent's additions).

### Open items (NOT done here — out of file set / undeclared)

1. **`run_matchup_leverage.py` rescales draws multiplicatively** to hit a target
   EV (`base * (target/ev)`, lines ~492-505) and its SP draws are Gaussian, so
   negatives get the same sign-inverted matchup treatment this fix removed from
   `sp_bench_mc`. Same defect, different engine.
2. **The empirical bootstrap leg's `* opp_factor`** carries the same asymmetry.
   Declared out of scope here; needs its own pre-registration.
3. **`_non_sp_total` still draws lognormal** for hitter and RP *weekly totals*.
   Much less structurally wrong (a sum over many events), explicitly excluded
   from this contrast, unchanged.
4. **The Gaussian still under-states the left tail** (12.99% modeled vs 16.39%
   realized; bottom-decile coverage 12.92% vs 10% target). Closing that gap means
   a skewed family or a re-tuned sigma — both undeclared here, both would need a
   fresh pre-registration. Note the direction: the tool is still mildly
   *optimistic* about blow-ups, just no longer infinitely so.


---

## SIBLING ENGINE: the same defect in the P(win) engine (2026-07-29, same day)

`run_matchup_leverage.py` carried the identical sign defect at its per-start EV
retarget (old lines 492-505). The code moved to
`scripts/xfp/lib/leverage_engine.py` during the C1 extraction and was fixed
there in the same change: `base = base * (target / ev)` became
`base = base + (target - ev)`. `_blend_draws` never multiplied anything itself —
it draws `rng.normal` and bootstrap-replaces a fraction — so its empirical leg
only INHERITED the distortion from that call site, and the location shift
therefore repairs both legs at once.

### Measured, at this study's own panel median (mu=9.86, sigma=8.73, 30-start log)

| opp_factor | multiply P(FP<=0) | shift P(FP<=0) |
|---|---|---|
| 0.83 | 10.75% | **11.44%** |
| 0.90 | 10.75% | 10.91% |
| 1.00 | 10.75% | 10.24% |
| 1.10 | 10.75% | 4.97% |
| 1.20 | 10.75% | **4.48%** |

Multiplicative spread **0.00pp — completely invariant to the matchup**, exactly as
this study found for `sp_bench_mc`. Location scaling: 6.97pp and monotone.
Sigma at factor 1.20: base 7.583, multiply **9.886** (inflated), shift 7.583 (held).

### Weekly total, 6 starts — the consumer-facing number

| factor | treatment | p05 | p10 | mean |
|---|---|---|---|---|
| 0.83 | multiply | 21.57 | 27.77 | 49.10 |
| 0.83 | **shift** | **18.48** | **25.37** | 49.10 |
| 1.20 | multiply | 31.19 | 40.16 | 70.99 |
| 1.20 | **shift** | **40.37** | **47.26** | 70.99 |

Means agree by construction; the tails do not. The multiply is **optimistic about
the floor in a bad matchup (+3.1 FP at p05) and pessimistic in a good one
(-9.2 FP)** — wrong in both directions.

### Live P(win) impact: small, and worth saying so plainly

Rebuilding the real period-17 state (WTD 91.1 vs 120.7) under both treatments,
20k sims, seed 7:

| treatment | P(win) | regime | my p05 | my p10 | my mean |
|---|---|---|---|---|---|
| multiply | 28.78% | TRAILING | 312.8 | 327.2 | 380.3 |
| shift | **29.07%** | TRAILING | 312.8 | 327.0 | 380.3 |

**+0.30pp**, and the team-total percentiles barely move. The defect is
structurally real and correctly fixed, but its live effect here is modest for two
reasons worth recording so nobody over-claims it later: (a) `model_fp` sits close
to the empirical mean for most current events, so `target/ev` is near 1 and the
two treatments nearly coincide; (b) the SP leg is 7 starts inside a full-roster
total, so any per-start distortion is diluted. It matters most where the retarget
factor is far from 1 — strong matchup tilts, `marcel_il` arms leaning parametric,
and thin-history streamers.

Guards: `tests/test_leverage_engine.py::test_matchup_factor_scales_location_not_the_finished_draw`
(mirrors this study's `test_opp_factor_scales_location_not_the_finished_draw`),
plus `test_matchup_factor_holds_sigma_fixed` and
`test_weekly_total_downside_responds_to_the_matchup`.

### Still open (declared out of scope here, unchanged)

`sp_bench_mc.build_sp_sampler`'s **empirical-bootstrap leg** still multiplies
bootstrapped REAL FP by `opp_factor` and carries the same asymmetry: a negative
real start scaled by a factor < 1 becomes LESS bad. Distinct from the parametric
leg this study fixed, and it needs its own contrast (a bootstrap has no mean
parameter to shift, so the fix is not simply "shift instead" — options are
resampling from an opponent-conditioned pool, or shifting the bootstrapped values
by the same location delta).
