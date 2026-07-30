---
signal: band_crps_calibration (distributional calibration of rh3/rp3 predictive bands)
formula: >
  Per forecast row with predictive mean mu, band sigma s, realized y:
    z = (y - mu) / s
    CRPS(mu, s, y) = s * ( z*(2*Phi(z) - 1) + 2*phi(z) - 1/sqrt(pi) )
  (closed-form Gaussian CRPS, Gneiting & Raftery 2007 eq. 21; properscoring
  is NOT installed so it is hand-rolled on scipy.stats.norm. Rows with
  s <= 0 or non-finite are DROPPED, not floored, and the drop count reported.)
  Pinball loss at quantile q against the PUBLISHED band edge qhat:
    L_q(y, qhat) = max( q*(y - qhat), (q-1)*(y - qhat) )
  q = 0.25 -> qhat = published p25 (clip-at-zero INCLUDED, because that is the
  number the add/drop trigger and the dashboard actually read)
  q = 0.75 -> qhat = published p75
  CRPS uses the UNCLIPPED N(mu, s) because that is literally what the MC
  consumers draw: run_matchup_leverage._blend_draws -> rng.normal(mean, sigma)
  and run_season_sim likewise. Coverage reported alongside:
    cov50 = 1[p25 <= y <= p75];  cov80 = 1[mu-1.2816s <= y <= mu+1.2816s]
outcome: >
  PANEL A (rest-of-season average frame): H -> ros_full_fp_per_pa;
  SP -> ros_fp_per_start. PANEL B (single-event frame): SP -> next-start fp_sp
  from boxscore_pitchers.parquet; H -> next-game fp_h / pa_game (per-PA rate,
  matching the per-PA band units).
expected_sign: >
  Lower CRPS is better. NO directional prior is asserted for either contrast —
  this is a measurement study and both "current is fine" and "the alternative
  wins" are pre-accepted outcomes. The 2026-07-10 NO-CHANGE precedent is the
  explicit null.
theory: >
  Interval COVERAGE is a single-threshold summary that is blind to how badly
  the tails are wrong; a proper scoring rule (CRPS) integrates over every
  quantile at once. Because three MC consumers (run_matchup_leverage P(win),
  sp_bench_mc, run_season_sim) draw from these bands, a band that passes a
  coverage gate but loses on CRPS is silently corrupting every MC-derived
  number. Two frames are scored because the bands are consumed in both, and a
  sigma tuned for one frame is arithmetically wrong for the other.
production_target: research-only
framing: in-season measurement
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023]
validation_script: scripts/xfp/validate_band_crps.py
date: 2026-07-29
verdict: NO-CHANGE (research-only) — see RESULT
---

# B3 — distributional calibration of the projection bands (CRPS / pinball)

Measurement only. **Nothing in this study may change production sigma**; the
sole thing that could come out of it is a *proposal*, and only if the declared
decision rule below fires.

## Note on holdout_years

The frontmatter `holdout_years` / `training_years` are the *model bundles'*
years, carried for schema consistency with the rest of this directory. They are
not a screen/holdout split for this study, because **there is no screen**: no
feature is selected, no threshold is fit. Both panels are evaluated on 2026
rows only, which every production `.pkl` here is out-of-sample by year
(TRAIN_YEARS end 2025). Panel B additionally has an internal
first-80%-of-snapshot-dates / last-20% split, reported descriptively.

## Declared cells (Rule 3 — counted BEFORE any result is seen)

### Primary contrasts — 4 cells, gated

| # | panel | bucket | contrast | band A | band B |
|---|---|---|---|---|---|
| A1 | RoS-average | H | global vs hetero sigma | `xfp_rh3_sigma_raw` (global, current backtest) | `raw * batter_sigma_factor` (hetero_v1, current PRODUCTION) |
| A2 | RoS-average | SP | display vs decision band | `sigma_raw * alpha` (alpha=2.41) | `sigma_raw` |
| B1 | single-event | H | global vs hetero sigma | `xfp_rh3_sigma_global` | `xfp_rh3_sigma_hetero` |
| B2 | single-event | SP | display vs decision band | `xfp_rh3`->`xfp_rp3_sigma` (x2.41) | `xfp_rp3_sigma_raw` |

Both members of a contrast are scored on the **identical row set** so the
comparison is exactly paired.

### Descriptive cells — reported, NOT gated, NOT counted in FDR

- CRPS / pinball(.25) / pinball(.75) / cov50 / cov80 per bucket x band, with n.
- The same, sliced by projection tercile (T1_high / T2_mid / T3_low), and for
  Panel B by snapshot-to-event gap bucket (1-2d / 3-5d / 6-10d).
- Panel B rp3 sliced by `data_quality_tag` (the `marcel_il` rows are EXCLUDED
  from every primary number, per gotcha #1 — a suppressed Marcel prior is not
  a real read and would contaminate a calibration measurement).
- **Lognormal side-cell (declared now so it is not a post-hoc addition):**
  `sp_bench_mc.build_sp_sampler` draws *lognormal* matched to (mean, sigma),
  not Gaussian. CRPS for that lognormal is computed by Monte-Carlo sample
  (200k draws, seed 20260729) on the Panel-B SP rows for both sigma variants.
  Descriptive only; cannot promote anything.

### Declared UNSCORABLE up front

**rprs2 / RP gets no CRPS number.** `verdict_backtest.run_relievers` compares a
full-SEASON-total projection against an in-progress `fp_year_total` that is
season-to-date as of the pull. The host already flags this (its own comment:
units mismatch, ranking lens only). A CRPS computed across that mismatch would
be a real number attached to a meaningless quantity, so it is not computed. The
RP band's calibration requires a completed-season panel and is **out of scope**.

## Multiplicity control

1. **Paired bootstrap, clustered by player id**, 2000 resamples, seed 20260729,
   on the per-row CRPS difference (B - A). 95% percentile CI. Clustering by
   player is required because the same pitcher/batter contributes many rows
   (Panel A: multiple split_days; Panel B: multiple starts) and treating them
   as independent inflates precision — this is the same autocorrelation error
   that inflated the 2026-07-28 delta-grid holdout from ~0 to +0.090.
2. **Benjamini-Hochberg FDR at q = 0.05 across all 4 primary cells**, using the
   bootstrap two-sided p (share of resamples on the wrong side of 0, doubled).
3. **Economic floor:** relative CRPS improvement `|dCRPS| / CRPS_A >= 2%`. A
   statistically clean 0.3% improvement does not advance.
4. **Rule 5 sample honesty:** n reported for every cell. A cell with fewer than
   200 clustered units (players) is marked UNDERPOWERED rather than
   tested-and-failed.

## Decision rule (declared BEFORE results)

A production-change PROPOSAL is written only if, for a given contrast, ALL of:

- (a) relative CRPS improvement >= 2%, AND
- (b) the player-clustered paired bootstrap 95% CI for dCRPS excludes 0, AND
- (c) it survives BH-FDR at q=0.05 across the 4 primary cells, AND
- (d) **the sign agrees on BOTH panels** (single-event and RoS-average).

If (d) fails while (a)-(c) pass, the correct conclusion is explicitly
**"the two frames disagree, so the band is frame-specific, not wrong"** — a
routing statement for consumers, not a sigma change.

Otherwise: **NO CHANGE**, matching the 2026-07-10 precedent.

## Frame interpretation, declared in advance

The two panels are NOT interchangeable and I am committing to this reading
before seeing numbers, so it cannot be reverse-engineered from the result:

- `alpha = 2.41` was derived on a **per-start** panel (sigma_calibration.json:
  "3,229 starts"). Arithmetically it should therefore look good on Panel B and
  **too wide on Panel A**, because a rest-of-season *average* over k starts has
  roughly `1/sqrt(k)` the SD of a single start.
- Conversely `sigma_raw` is the LOO residual sigma of the RoS target itself, so
  it should look good on Panel A and **too narrow on Panel B**.
- If that is what the numbers show, the finding is a **consumer-routing**
  finding (which band for which horizon), NOT evidence that either band is
  miscalibrated. Only a contrast that loses on BOTH panels is a real defect.

## Prior art

- `rp3_sigma_singlestart_2026-07-10.md` — coverage 44.9% [p25,p75] / 74.0%
  [p10,p90] on 868 pairs; verdict NO CHANGE, alpha=2.41 kept. Panel B here
  re-builds that exact pair construction and must reproduce those coverage
  numbers as a **sanity check** before any CRPS number is trusted.
- `sigma_recalibration.md` (2026-06-03) — origin of alpha=2.41.
- `hitter_sigma_heteroskedastic_search.md` (2026-06-03) — origin of hetero_v1,
  CV r2 0.574 on 639 batters, factor clipped [0.7, 1.5], re-centered to mean 1.
- `rp3.py` lines 492-505 — the decision band exists because the x2.41 display
  band made the add/drop signal emit `hold` on 100% of rows.
- CLAUDE.md #13 — forward calibration is good; the p25/p75 "band check" in the
  2026-06-26 study was a units bug (rh3 bands are per-PA, not per-game). This
  study keeps rh3 in per-PA units throughout, on both panels.

## RESULT (2026-07-29, same day)

`python scripts/xfp/validate_band_crps.py`. Panels written to
`data/research/validation_runs/_crps_panel{A,B}_{hitters,starters}.csv`,
tables to `_crps_{primary_cells,slices,contrasts}.csv`.

### 0. Sanity check FIRST (gate on trusting anything below)

Panel B reproduces the 2026-07-10 single-start coverage read:

| | 2026-07-10 | this run |
|---|---|---|
| n (pitcher, start) pairs | 868 | **1,037** |
| display band [p25,p75] cov | 44.9% | **46.3%** |
| display band [p10,p90] cov | 74.0% | **75.3%** |

n is larger because the snapshot cache has grown from 24 to 30 dates
(2026-06-03..2026-07-09). Coverage moves 1.4pp / 1.3pp. **Reproduced.**
3,414 `marcel_il` snapshot rows excluded (gotcha #1).

### 1. Primary cells

| cell | band | n | CRPS | pin.25 | pin.75 | cov50 | cov80 |
|---|---|---|---|---|---|---|---|
| A1 rh3 RoS-avg (FP/PA) | global | 2,187 | 0.06414 | 0.03564 | 0.03636 | 46.9% | 77.3% |
| A1 rh3 RoS-avg (FP/PA) | **hetero** | 2,187 | **0.06395** | 0.03547 | 0.03635 | 46.1% | 77.6% |
| A2 rp3 RoS-avg (FP/start) | display x2.41 | 1,215 | 2.61269 | 1.58715 | 1.41589 | 83.0% | 99.8% |
| A2 rp3 RoS-avg (FP/start) | **decision raw** | 1,215 | **2.24087** | 1.28562 | 1.24350 | 41.2% | 71.0% |
| B1 rh3 next-game (FP/PA) | global | 7,616 | 0.60733 | 0.31044 | 0.31822 | 7.7% | 13.5% |
| B1 rh3 next-game (FP/PA) | **hetero** | 7,616 | **0.60728** | 0.31031 | 0.31832 | 7.5% | 13.3% |
| B2 rp3 next-start (FP/start) | **display x2.41** | 1,037 | **5.39816** | 3.19403 | 2.86367 | 46.3% | 75.3% |
| B2 rp3 next-start (FP/start) | decision raw | 1,037 | 6.11518 | 3.41105 | 3.24958 | 19.5% | 34.7% |

Panel A: H 322 batters / 10 splits, mean forward PA 188.3; SP 173 pitchers /
11 splits, mean forward GS 9.24. Panel B: 421 batters, 202 pitchers.

### 2. Paired, player-clustered bootstrap (2000 reps, seed 20260729)

dCRPS = mean(B) − mean(A); negative means the *second* band wins.

| cell | n rows | n clusters | CRPS_A | CRPS_B | dCRPS | rel % | 95% CI | boot p | BH pass | econ pass |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 global→hetero | 2,187 | 322 | 0.06414 | 0.06395 | −0.000189 | **−0.29%** | [−0.000381, −0.000000] | 0.050 | no | **no** |
| A2 display→decision | 1,215 | 173 | 2.61269 | 2.24087 | −0.37182 | **−14.23%** | [−0.4653, −0.2650] | 0.00025 | yes | yes |
| B1 global→hetero | 7,616 | 421 | 0.60733 | 0.60728 | −0.000055 | **−0.01%** | [−0.000484, +0.000374] | 0.804 | no | **no** |
| B2 display→decision | 1,037 | 202 | 5.39816 | 6.11518 | +0.71702 | **+13.28%** | [+0.6347, +0.8042] | 0.00025 | yes | yes |

**Rule 5:** A2 has **173 clusters, below the declared 200 minimum → flagged
UNDERPOWERED per the pre-registration.** In this case the flag does not change
the reading (the effect is 14% with a CI nowhere near 0 — it is not a power
problem), but the declared label is applied as written rather than waived.

### 3. Verdict against the declared decision rule

**A1 / B1 — rh3 global vs hetero: NO CHANGE.** Hetero is better on both panels,
so sign agreement (d) holds, but the effect is **−0.29% and −0.01%** — an order
of magnitude below the declared 2% economic floor, and B1's CI spans 0
(p=0.804). Gate (a) fails, gate (c) fails. Two consequences:
- `hetero_v1` is **CRPS-neutral in aggregate**. It reallocates band width
  between batters (factor range 0.700–1.245, mean 1.000) without changing pooled
  sharpness. That is what a *re-centered* factor is supposed to do, so this is
  a confirmation, not an indictment — but the hetero path cannot be justified
  on CRPS, only on the per-batter argument in its own 2026-06-03 memo.
- **`verdict_backtest.py` line ~203 omitting the hetero factor is immaterial**
  (0.29% CRPS). The comment there ("hetero factor ~1.0 mean; omitted") is
  correct and does not need changing.

**A2 / B2 — rp3 display vs decision: NO CHANGE, and gate (d) FAILS by design.**
Both contrasts pass (a), (b), (c) with large effects, but in **opposite
directions**. Per the pre-registered clause, the correct conclusion is
explicitly *"the two frames disagree, so the band is frame-specific, not
wrong"* — a consumer-routing finding, not a sigma change. The pre-registered
frame arithmetic is confirmed almost exactly:

- mean forward GS per RoS row = 9.24, `sqrt(9.24) = 3.04`. A k-start average has
  ~1/sqrt(k) the SD of one start. `alpha = 2.41` sits inside that gap, so one
  alpha provably cannot serve both frames.
- **Post-hoc diagnostic** (NOT pre-registered, NOT gated, added after seeing the
  above): the CRPS-minimizing multiplier `c*` on the raw LOO sigma is

  | frame | n | c\* | CRPS at c\* | band in use | CRPS in use | loss vs optimum |
  |---|---|---|---|---|---|---|
  | rp3 RoS-average | 1,215 | 1.19 | 2.22461 | 1.00 (raw) | 2.24087 | **0.73%** |
  | rp3 single-start | 1,037 | 2.65 | 5.38646 | 2.41 (display) | 5.39816 | **0.22%** |

  **Both rp3 bands are within 0.7% of the CRPS optimum for their own frame.**
  Coverage alone said the display band was 5pp light (46.3 vs 50) and the RoS
  band 9pp light (41.2 vs 50); the proper scoring rule says both are
  essentially optimal and the residual coverage gap is skew, not width. This is
  the substantive upgrade CRPS buys over coverage, and it **strengthens** the
  2026-07-10 NO-CHANGE decision rather than overturning it.

### 4. Which band MC consumers should draw from

- **SP: `xfp_rp3_sigma` (the x2.41 display band). This is already what they do
  and it is correct.** `run_matchup_leverage.py:724` and
  `build_matchup_dashboard.py:526` both read `xfp_rp3_sigma`, and every SP draw
  is **per start** (`_blend_draws` → `rng.normal(per_start, sigma)`). Panel B
  says that is the CRPS-best of the two bands for that frame, 0.22% off optimum.
  **`xfp_rp3_decision_p25/p75` must never be fed to an MC** — it is 13% worse
  per-start (cov50 19.5%) and exists only for the add/drop trigger, which is a
  rest-of-season judgement where it is in turn the better band.
- **Rule of thumb:** raw sigma for rest-of-season *average* questions
  (add/hold/drop, ranking), x2.41 for *single-event* questions (MC, streamer
  bench/start, P(win)). Using either in the other frame costs ~13-14% CRPS.
- **rprs2 / RP: no number produced** — declared unscorable in-season as planned.
  Note `build_matchup_dashboard.py:544` derives the RP sigma as
  `(p75 - p25) / 1.35`, i.e. it inverts the band back to a sigma. That is the
  correct normal-IQR identity, but it inherits whatever the rprs2 band's
  calibration is, which **remains unmeasured**. Highest-value follow-up.

### 5. Descriptive slices

Direction is uniform — no slice reverses a primary result.

- rp3 single-start: display wins in every tercile (T3 4.82 vs 5.30, T2 5.61 vs
  6.45, T1 5.53 vs 6.27), every gap bucket (1-2d n=810, 3-5d n=127, 6-10d
  n=100), and both `data_quality_tag` values (`data_driven_full` n=803,
  `data_driven_thin` n=234). Coverage degrades with staleness as expected
  (6-10d: 38.0% vs 46.9% at 1-2d).
- rp3 RoS-average: decision-raw wins in every tercile; the display band's cov80
  is **99.8-100.0%** — near-total containment, the signature of a band ~2.4x
  too wide for the frame, and exactly why it emitted `hold` on 100% of rows.
- rh3: differences are in the 4th decimal everywhere.

### 6. Lognormal side-cell (declared descriptive)

`sp_bench_mc.build_sp_sampler` draws a moment-matched **lognormal**, not a
Gaussian. **Declared deviation:** the pre-registration specified a 200k-draw MC
estimator; I used the exact closed form (Baran & Lerch) for the same functional
instead — a strict improvement, verified against a 200k-draw MC on 50 rows to
**max relative error 7.6e-03, mean 2.0e-03**. On the 867 Panel-B rows a
lognormal can score:

| sampler | lognormal CRPS | Gaussian CRPS (same rows) |
|---|---|---|
| display x2.41 | 4.7744 | **4.3449** |
| decision raw | 4.8424 | 4.7456 |

**The lognormal is worse than the Gaussian it replaced (+9.9% CRPS), and it
cannot score 170 / 1,037 rows (16.4%) at all** — those are starts with FP <= 0,
to which a lognormal assigns exactly zero probability. A blow-up start is the
single most decision-relevant SP outcome and `sp_bench_mc`'s sampler treats it
as impossible. Descriptive only, cannot promote anything, but it is a concrete
follow-up: `sp_bench_mc` should use the Gaussian (or a shifted lognormal).

### 7. BUG FOUND IN EXISTING CODE (2 of them)

**BUG 1 — `verdict_backtest.py` was dead for hitters. FIXED here.**
`build_hitter_panel()` never merged `bx_prior_h`, promoted into `RH3_FEATS` on
2026-07-10. Every hitter run raised `KeyError: ['bx_prior_h']` at
`sub.dropna(subset=feats)`. Every other consumer of RH3_FEATS was updated at
promotion time (`validate_bx_ensemble`, `validate_xwoba_l150pa`,
`_validate_rh3_v3_helper`, `validate_inseason_discipline`,
`validate_rh3_breakout_signals`) — this one host was missed, so
`/verdict-scorecard`'s hitter retro has been silently unrunnable for ~3 weeks.
Fixed by mirroring `rh3.main()` lines 373-397 exactly (mlbam join on
(batter, year), per-year-mean fill, global-mean fill). 931/931 tests still pass.

**BUG 2 — hitter per-game variance in the matchup MC is ~5.7x too small.
REPORTED ONLY, NOT FIXED** (this study is measurement-only and this is
production sigma).

`src/plv_clone/matchup_projection.py:258`:
```python
sigma_pa = cfg.global_sigma_pa_fp * float(sigma_factor)   # 0.517 * factor
sigma2   = n * (sigma_pa ** 2) * ppg                       # ppg, NOT ppg**2
```
`global_sigma_pa_fp = 0.517` is **not a per-PA sigma**. In
`build_hitter_sigma_calibration.py:82-83` it is the PA-weighted RMS of the
*per-game rate* residual (`fp_proxy / PA`). Proof that the PA-weighting does not
convert it to a per-PA quantity, on the same 245,712-batter-game panel:

| quantity | value |
|---|---|
| PA-weighted RMS of per-game-RATE residual (the stored 0.517) | **0.5170** |
| UNweighted SD of the per-game RATE | **0.5239** |

They are the same number. A genuine per-PA sigma would be ~1.11
(`2.307 / sqrt(4.348)`). Consequences, mean PA/game = 4.348, empirical per-game
hitter FP SD = **2.3072**:

| parameterization | sigma_g | vs truth |
|---|---|---|
| current code `0.517*sqrt(3.5)` | 0.9672 | variance **5.69x too SMALL** |
| `ppg**2` scaling `0.517*3.5` | 1.8095 | closer |
| `ppg**2` at true ppg `0.517*4.348` | **2.2481** | matches 2.3072 to **2.6%** |
| legacy `SIGMA_PER_HITTER_GAME = 3.5` | 3.5000 | variance 2.30x too BIG |

The `ppg` exponent is the bug: with `ppg**2` and the real PA/game the arithmetic
reproduces the empirical per-game SD to 2.6%, which is conclusive. The
"improved" hetero path that replaced the legacy constant is **further from the
truth than the constant it replaced** — and the code comment at
`build_matchup_dashboard.py:365-369` reasons from the wrong identity
("Per-game variance ≈ PA_per_game * σ_pa²"), which is how it slipped through.

Blast radius: `project_hitter` feeds `sigma2` → `win_probability`
(`build_matchup_dashboard.py:3318-3325`), `render_ci_bands`, and the hitter legs
of `run_matchup_leverage.py` / `run_season_sim.py`. Effect: hitter contribution
to total variance is understated, so **matchup P(win) is pushed toward 0/100 —
systematically overconfident**, and `run_season_sim`'s `+10% weekly sigma`
sensitivity dial is being evaluated at the wrong operating point. Escape hatch:
`MATCHUP_LEGACY_SIGMA=1` restores the (differently wrong, but 2.5x closer)
legacy constant.

This needs its own pre-registered run — the fix is not simply `ppg**2`, because
(a) the per-batter `sigma_factor` was fitted against the mislabeled scale, and
(b) `fp_proxy` should be checked against the canonical BrownU hitter formula
before its SD is adopted as truth.

### 8. Bottom line

**NO-CHANGE on both declared contrasts, consistent with the 2026-07-10
precedent — and now with a proper scoring rule behind it rather than a single
coverage threshold.** Both rp3 bands are within 0.7% of their frame's CRPS
optimum; hetero-vs-global rh3 is a 0.01-0.29% non-effect. Nothing in this study
justifies touching production sigma. The two genuine findings are incidental:
the `bx_prior_h` host rot (fixed) and the `ppg`-exponent variance bug in the
matchup MC (reported, needs its own study). The frame-routing rule in §4 is the
durable deliverable: **x2.41 for single-event MC draws, raw for
rest-of-season judgements, and never the reverse.**


---

## CORRECTIONS (from independent adversarial review, 2026-07-29)

The reviewer re-ran this study; **the NO-CHANGE verdict is CONFIRMED** and the
Panel-B replication claim was UPGRADED. Four corrections to surrounding claims:

**1. RETRACT "BUG 1 is fixed / verdict_backtest.py is now runnable again."**
Repairing `build_hitter_panel`'s missing `bx_prior_h` merge fixed only the FIRST
of TWO rot points. The host is still dead for BOTH buckets:
`run_hitters()` raises at line ~237 and `run_pitchers()` at line ~284 —
`AttributeError: module 'plv_clone.models.xfp.rh3' has no attribute '_signal'`
(and `RP3._signal`). Both symbols were deleted in commit **de9f6e6** when signal
computation moved to a vectorized `np.select` path. This study never hit it
because `panel_a()` imports only the panel builders and never executes `run_*`.
"931/931 tests pass" was NOT evidence of the fix — **no test exercises that
path**, which is the actual defect. Tracked as F3.

**2. Bug-2 magnitude is ~4.6x, not 5.7x, on the production path.** The 5.69x
figure assumes `cfg.league_pa_per_game = 3.5`, but
`build_matchup_dashboard.py:1372` passes the real per-batter `pa_per_g`; at the
empirical mean 4.348 the variance understatement is **4.58x**. 5.69x applies only
where `pa_per_g` is missing and the 3.5 default fires. Both figures are dimensionally
correct — the exponent error stands either way.

**3. The 868 -> 1037 pair growth is NEW OUTCOMES, not cache growth.** Both runs
used the same 30 snapshot dates and 6,266 band-carrying rows; the 169 additional
starts are simply dated after 2026-07-09 and have since landed in
`boxscore_pitchers.parquet`. The §0 sanity narrative should say so.

**4. UPGRADE the replication claim.** Restricting Panel B to
`game_date <= 2026-07-09` reproduces the 2026-07-10 single-start coverage study
**digit-for-digit: n=868, cov50 44.9%, cov80 74.0%.** That is a stronger
statement than the memo made, and it means this study *strengthens* the earlier
NO-CHANGE conclusion rather than merely agreeing with it.

**5. The 2.307 FP/g empirical SD is PROVISIONAL.** It inherits `fp_proxy`'s
definition, whose mean is 1.1775 FP/g — implausibly low for a BrownU hitter game
(R+TB+RBI+BB+HBP+SB-K). The ppg-exponent error is dimensionally correct in any
units so the bug stands regardless, but the 2.6% match must NOT be read as
validating `fp_proxy`. Any sigma recalibration must audit `fp_proxy` against the
canonical formula first (tracked as F1).
