---
signal: pwin_mean_bias
formula: >
  gap = mean(outcome) - mean(win_probability), computed on the LIVE
  predictions_history panel after (a) excluding synthetic backfill rows and
  legacy NULL-model_version rows, (b) dropping snapshots logged outside their
  own ESPN period window, (c) dropping periods ESPN still calls UNDECIDED, and
  (d) replacing the stored actual_my_final / actual_opp_final with ESPN's
  authoritative matchup totalPoints.  Companion statistics:
  resid = (true_my - true_opp) - (proj_my - proj_opp)  [margin bias, FP]
  frac_side = (true_side - side_wtd) / (proj_side - side_wtd) - 1  [per-side]
outcome: >
  Did my team out-score the opponent in that scoring period (ESPN winner).
expected_sign: >
  The review reported gap ~= -0.070 (predictions optimistic).  Pre-registered
  direction of the test: gap < 0.  A per-side explanation would additionally
  require frac_my < 0 (H1) or frac_opp > 0 (H3).
theory: >
  P(win) is produced by a normal/bootstrap comparison of two projected team
  totals.  A mean bias in P(win) must come from a mean bias in the projected
  MARGIN, which in turn must come from a mean bias in one or both projected
  team totals.  Candidate mechanisms: survivorship (projections assume rostered
  players keep playing), frozen opponent rosters (opponents add mid-period),
  the 0.80 unconfirmed-rotation-gap start probability, and chronological SP-cap
  enforcement.
production_target: >
  NONE.  This is a measurement/diagnosis run.  Rule 13 holds throughout:
  nothing here touches rh3 / rp3 / rprs2 / baseline xFP.  The only production
  edit is to the actuals-backfill script that labels the calibration panel.
framing: >
  Rule 8 - one pre-registered primary question ("is the reported ~7pp mean
  bias distinguishable from zero?") plus five named secondary hypotheses,
  ranked by evidence.  The per-side / per-arm interval table in section 5 is
  18 intervals and is treated as exploratory, not as 18 independent tests.
holdout_years: []
training_years: []
data_window: >
  Live 2026 in-season only.  predictions_history.csv snapshots from 2026-05-13
  to 2026-07-29 covering ESPN matchup periods 7-17; after exclusions the panel
  is 8 completed periods (8, 9, 10, 12, 13, 14, 15, 16) x 2 model arms =
  16 first-snapshot observations (284 snapshots if every in-window row is kept).
  NO prior-season data is used; there is no holdout because nothing is fit.
validation_script: scripts/xfp/diagnose_pwin_mean_bias.py
date: 2026-07-30
---

# I5 — is the P(win) mean bias real?

## TL;DR

**No. At this n the ~7pp mean bias is not distinguishable from zero — and the
number it was measured from was computed against corrupted labels.**

1. **A P0 data defect dominates everything else.** `fetch_closed_matchup_actuals.py`
   wrote *in-progress single-day* scores into **5 of the 11** live periods as if
   they were finals. Period 13 is stored as `25.7-64.5`; the real final is
   `322.1-331.3`. One of the five (period 15) has the **wrong recorded winner**.
   A sixth period (17) is still open and was graded anyway.
2. **On corrected labels the margin is essentially unbiased.**
   mean residual `(true_my - true_opp) - (proj_my - proj_opp)` =
   **-5.4 FP, 95% CI [-35.0, +27.6]** (period-clustered bootstrap, 16 obs /
   8 periods). Against a realized spread SD of ~47 FP that is noise.
3. **The win-rate gap on corrected labels is -0.099**, period-level
   Poisson-binomial **z = -0.76, p = 0.45**, bootstrap CI on the gap
   **[-0.339, +0.140]**. E[wins] = 3.79, observed 3, SD 1.04. Losing 0.8 more
   matchups than expected across 8 tries is a completely ordinary outcome.
4. **Neither side is separately mis-projected.** `frac_opp - frac_my` =
   **-0.004 [-0.128, +0.111]**. H1 and H3 both fail to show anything.
5. Two *real but symmetric* projection-window defects were found (the ASG
   two-week block projected as one week; stale post-period snapshots). They
   move each side's total by up to +230 FP but nearly cancel in the margin,
   so they do not explain a P(win) mean bias either.
6. **The same corrupted labels drove yesterday's VARIANCE verdict too**
   (section 4b). On ESPN finals the realized spread SD is **39.64 FP, not
   56.41**, the pre-F1 model's dispersion was already **0.940 [0.720, 1.140]**
   rather than 1.379, and the post-F1 widened model is **under-confident at
   0.712 [0.546, 0.863]**. That needs a re-run of the F1 harness, not a new
   sigma tune.

---

## 1. What the panel actually is (loud exclusions)

`data/outputs/predictions_history.csv` = 464 rows, three populations:

| population | rows | why excluded |
|---|---|---|
| `backfill_2024_*` / `backfill_2025_*` synthetic | **141** | implied spread sigma 100-400 FP vs 29-56 FP live; pooling them inverts every dispersion statistic |
| NULL `model_version` (periods 7, 8) | **25** | a third, pre-shadow-logging projection version. The prior harness `fillna('baseline')`'d these, silently pooling it into the baseline arm |
| live `baseline` / `MA_v1` | **298** | kept |

Of the 298 live rows: 8 belong to still-open period 17 (dropped), and 6 are
logged outside their own period window (dropped: 4 rows dated 2026-06-15 under
period 11, 2 rows dated 2026-07-20 under period 15), leaving **284 snapshots
over 8 completed periods**, or **16 first-snapshot observations** (8 periods x
2 arms).

Periods 7 and 11 leave the panel entirely — 7 because all its rows are the
legacy NULL arm, 11 because all four of its snapshot rows are dated
2026-06-15, the day *after* period 11 closed (2026-06-08..14).

## 2. The P0: the calibration labels were wrong

ESPN's authoritative `mMatchupScore` totals vs what was stored:

| period | stored as "final" | ESPN final | stored W | true W |
|---|---|---|---|---|
| 12 | 124.4 - 145.5 | 294.6 - 385.0 | L | L |
| 13 | 25.7 - 64.5 | 322.1 - 331.3 | L | L |
| 14 | 46.1 - 50.9 | 306.5 - 363.3 | L | L |
| 15 | 22.7 - 15.0 | **552.1 - 581.4** | **W** | **L** |
| 16 | 43.8 - 31.2 | 362.3 - 246.7 | W | W |

Periods 7-11 were stored correctly; the defect starts at period 12.

**Mechanism (two independent bugs compounding).**

* `_period_closed()` derived the period window from the **ISO week of the first
  snapshot**. The 2026 All-Star block (period 15) runs **Jul 6-19**, so the
  ISO rule declared it closed on **Jul 13**, six days early, and fetched it live.
* `_fetch_period_finals()` called `league.box_scores(matchup_period=N)`.
  `espn_api` only overrides `scoring_period` when the caller passes it
  **explicitly**, so `scoringPeriodId` stayed at *today*; ESPN then returns a
  payload carrying `totalPointsLive`, and `H2HPointsBoxScore` **prefers
  `totalPointsLive` over `totalPoints`**. `totalPointsLive` is the current
  DAY's points. A single BrownU team-day is ~25-50 FP — exactly the magnitudes
  stored. `tests/test_matchup_actuals_backfill.py::test_espn_api_boxscore_prefers_live_points`
  pins that old behaviour on the same payload.
* The backfill was documented "never overwrites", so once a partial score
  landed it was permanent.

**Fix shipped** (surgical, `scripts/xfp/fetch_closed_matchup_actuals.py`): read
the raw `mMatchupScore` schedule, take `totalPoints`, and **raise
`PeriodNotFinal` if ESPN reports `winner == UNDECIDED`** rather than writing a
partial. `MatchupNotFound` / `KeyError` on a missing team or missing
`totalPoints` — no silent zero anywhere. A new `--repair` flag overwrites
stored actuals that disagree with ESPN.

`predictions_history.csv` itself was **left untouched** (other agents are
reading it this session). To rewrite it:
`python scripts/xfp/fetch_closed_matchup_actuals.py --repair`.
The diagnostic applies the correction in memory, so it is already correct.

## 3. Attribution ladder — where the reported -7pp came from

| step | n | periods | mean pred | actual | gap | Brier |
|---|---|---|---|---|---|---|
| prior harness, as reviewed | 21 | 11 | 0.516 | 0.429 | **-0.087** | 0.2467 |
| - drop legacy NULL `model_version` | 19 | 10 | 0.483 | 0.368 | -0.115 | 0.2675 |
| - drop periods ESPN calls UNDECIDED | 17 | 9 | 0.448 | 0.412 | -0.036 | 0.2263 |
| - drop out-of-window snapshots | 15 | 8 | 0.472 | 0.467 | -0.005 | 0.2463 |
| - use ESPN finals, not stored actuals | 15 | 8 | 0.472 | 0.333 | -0.138 | 0.1253 |

The gap does not decay monotonically to zero — it moves around between -0.005
and -0.138 as ~2 observations enter or leave. **That instability, on 8-11
observations, is the finding.**

A separate reproducibility note: the prior harness's row selection was
`sort_values('date').drop_duplicates(..., keep='first')` with pandas' default
**unstable** quicksort, over a frame with **55 same-day tie groups (max 16 rows
in one day)**. Re-running with `kind='mergesort'` moves the headline from
`mean_pred = 0.5009 / Brier 0.2603` to `0.5160 / 0.2467`. **~1.5pp of the
reported 7pp is sort-algorithm artifact.** The diagnostic sorts by
`['date','timestamp']` with `kind='mergesort'`.

## 4. Primary result — is the bias distinguishable from zero?

Period is the experimental unit (all snapshots in a period resolve to the same
win/loss). Poisson-binomial on period-level mean predicted probability:

| panel | arm | periods | mean pred | actual | gap [95% CI] | E[wins] | obs | z | p |
|---|---|---|---|---|---|---|---|---|---|
| first snapshot, **as-logged** actuals | ALL | 8 | 0.474 | 0.500 | +0.026 [-0.297,+0.385] | 3.79 | 4 | +0.20 | 0.84 |
| first snapshot, **ESPN-corrected** | ALL | 8 | 0.474 | 0.375 | **-0.099 [-0.339,+0.140]** | 3.79 | 3 | **-0.76** | **0.45** |
| first snapshot, ESPN-corrected | baseline | 8 | 0.490 | 0.375 | -0.115 [-0.356,+0.122] | 3.92 | 3 | -0.87 | 0.39 |
| first snapshot, ESPN-corrected | MA_v1 | 8 | 0.458 | 0.375 | -0.083 [-0.321,+0.161] | 3.66 | 3 | -0.65 | 0.51 |
| all in-window snapshots, corrected | ALL | 8 | 0.428 | 0.375 | -0.053 [-0.219,+0.109] | 3.43 | 3 | -0.42 | 0.68 |

**Verdict: not distinguishable from zero.** The largest |z| anywhere is 0.87.
The 95% CI on the gap spans roughly -0.34 to +0.14 — it comfortably contains
both 0 and the reported -0.07.

**A trap worth recording:** running the Poisson-binomial over all 284 snapshots
as if they were independent trials gives `z = -4.33, p < 0.001` for the ALL arm
and `z = -3.21` for baseline. That is entirely an artifact of counting one
period's outcome up to 37 times. `tests/test_pwin_mean_bias.py::test_naive_snapshot_level_test_overstates_significance`
locks the correct treatment in.

**Power.** With 8 periods and a typical p near 0.45, SD(wins) ~ 1.04. Detecting
a true 7pp bias at alpha=0.05 two-sided with 80% power needs
`n = (1.96+0.84)^2 * p(1-p) / 0.07^2` = **~396 matchup observations** (a 10pp
bias needs ~194; 5pp needs ~777). At 8 of my own matchups per season that is
**~49 seasons**. **The mean of this layer is not measurable from my own
matchups alone on any useful timescale.** Section 7 says what would be.

## 4b. Downstream: the corrupted labels also drove yesterday's VARIANCE verdict

This is the most consequential consequence of the P0 and it needs its own
follow-up. The F1 track (`hitter_sigma_scale_2026-07-29.md`) concluded the
win-prob model was **over-confident** — `SD(resid/sigma)` 1.379 -> 1.045 after
widening hitter sigma ~9.7x — and reported a realized spread SD of 56.41 FP.
`resid` there is `(actual_my - actual_opp) - (proj_my - proj_opp)`, computed
from the same corrupted `actual_*` columns.

Recomputed on the same panel construction (F1's `_load_live_history`, first
snapshot per period x arm), restricted to ESPN-decided periods, n = 19
snapshots / 10 periods, period-clustered bootstrap:

| | realized spread SD | SD(resid/sigma) | 95% CI |
|---|---|---|---|
| pre-F1 model, **as-logged** labels | 55.40 FP | **1.351** | [1.001, 1.640] |
| pre-F1 model, **ESPN finals** | **39.64 FP** | **0.940** | [0.720, 1.140] |
| post-F1 model, **ESPN finals** | 39.64 FP | **0.712** | [0.546, 0.863] |

(The post-F1 row applies the team-sigma ratio 39.65/30.03 = 1.320 that the F1
memo itself reports; their harness uses a hitter-share-weighted multiplier that
nets to the same team sigma.)

**Read carefully.** On correct labels the *pre-fix* model was already close to
calibrated (0.940, CI containing 1.00), and the widened *post-fix* model is
**under-confident — bands too wide** (0.712, CI excludes 1.00). The corrupted
periods were exactly the ones whose fabricated 25-FP "finals" produced ~300 FP
residuals, which is where the 1.379 came from.

**This does NOT automatically mean the F1 fix was wrong.** Its core measurement
— hitter per-game FP SD = 3.2502 on 26,199 started games / 377 batters — is a
direct, independent, high-n measurement, and the unit bug it fixed (PA/game
entering variance linearly, and a per-game-rate residual RMS read as per-PA) was
real. What is now unsupported is the *panel evidence* that was used to confirm
the resulting team sigma. Two candidate reconciliations, both testable:

* the period-15 window defect (section 5) inflates the corrected residual too
  (+31.7 FP on that period alone), so 39.64 FP may itself be an over-estimate
  of the true spread SD — which would make the post-fix under-confidence worse,
  not better; ex-P15 in-window the realized SD is 40.80 FP and post-F1
  dispersion 0.727;
* the team-level sigma may be double-counting correlated components (a shared
  team-day, a shared opponent-pitcher) or the SP/RP legs may be too wide,
  which per-player hitter sigma cannot detect.

**Recommended next action for whoever owns the variance track: re-run
`validate_hitter_sigma_scale.py` section 7b after
`fetch_closed_matchup_actuals.py --repair`, before any further sigma tuning.**
Nothing was changed here — this track does not own that file.

## 5. Ranked hypotheses

| # | hypothesis | evidence | verdict |
|---|---|---|---|
| **0** | *(added)* the actuals themselves are wrong | 5/11 periods stored with single-day partials; 1 outcome flip; period 17 graded while open; 2 out-of-window snapshots; unstable sort moves the headline 1.5pp | **CONFIRMED — this is the real defect.** Fixed. |
| **1** | my side systematically over-projected | `frac_my` = +0.058 [-0.085,+0.249] (ALL, all periods); ex-period-15 -0.025 [-0.109,+0.066]. Sign flips between arms | **No support.** Interval straddles 0 in every cut. |
| **3** | opponent under-projected (mid-period roster churn) | `frac_opp` = +0.054 [-0.088,+0.200]; paired `frac_gap = frac_opp - frac_my` = **-0.004 [-0.128,+0.111]** (ex-P15: +0.028 [-0.097,+0.135]) | **No support.** The paired statistic — the one that would actually move P(win) — is centred on zero. Weak positive lean ex-P15, far inside noise. |
| **2** | survivorship / attrition propagates from rh3's +bias | Would show as `frac_my < 0`. The only interval excluding zero in the whole table is MA_v1 `frac_my` = -0.086 [-0.159,-0.008] ex-P15 — but MA_v1's `frac_opp` is -0.065 the same direction, so it is a **level** property of the MA_v1 adjuster chain (it projects ~7-9% high for *both* teams), not a my-side asymmetry. It cancels in the margin: MA_v1 mean resid = **-2.05 FP**. 1 of the 18 exploratory intervals in section 5 landing outside zero at 95% is the expected false-positive count | **Not separable at this n; the one flagged interval is symmetric across sides and so cannot bias P(win).** |
| **5** | chronological SP-cap enforcement differs sim-vs-reality | Would be a one-sided effect (my cap is modelled in detail, the opponent's is not). Margin residual is -5.4 [-35.0,+27.6] FP and `frac_gap` ~ 0, so any such effect is < ~30 FP | **No support; not separately identified.** |
| **4** | `UNCONFIRMED_START_P` / `_UNCONFIRMED_START_CONF` = 0.80 too high | **Not testable from any existing store.** Nothing logs which starts were predicted-but-unconfirmed at snapshot time, so the realised occurrence rate cannot be reconstructed. `dpwin_history.parquet` records candidate moves, not per-start confirmation flags | **UNTESTED — see section 7.** |

### Two real (but symmetric) projection-window defects found in passing

* **Multi-week periods are projected as one week.** Period 15 (ASG block,
  Jul 6-19): the 07-06 snapshot projected 322.2 / 383.2 against finals of
  552.1 / 581.4 — errors of **+230 / +198 FP**. The projected total only jumps
  (322 -> 523) on 07-13, when the horizon rolls into the second week.
  `resolve_period_meta()` already returns the correct Jul 6-19 window, so the
  dashboard's projection horizon is not using it. Because both sides are
  under-projected together the margin error is only **+31.7 FP**, so this does
  not bias P(win) much — but it makes every period-15 total projection and the
  P(win) *variance* (a one-week variance on a two-week window) wrong.
  **Not fixed here** — it lives in `build_matchup_dashboard.py`, which this
  track was told not to edit, and the fix needs its own measurement.
* **Stale post-period snapshots.** Period 11's only four snapshot rows (2 per
  arm) are dated 2026-06-15 (period closed 06-14) and project another 221 FP onto a finished
  matchup; period 15 has a 2026-07-20 row projecting 930.8. These are logged
  under a period label that has already rolled over.

## 6. Per-period detail (first snapshot, baseline arm, ESPN-corrected)

| period | date | my proj | my true | e_my | opp proj | opp true | e_opp | resid | P(win) | W |
|---|---|---|---|---|---|---|---|---|---|---|
| 8  | 05-20 | 342.95 | 364.2 | +21.3 | 341.74 | 289.8 | -51.9 | +73.2 | 0.511 | 1 |
| 9  | 05-27 | 348.81 | 312.1 | -36.7 | 299.67 | 292.1 |  -7.6 | -29.1 | 0.855 | 1 |
| 10 | 06-02 | 272.14 | 262.6 |  -9.5 | 284.71 | 343.4 | +58.7 | -68.2 | 0.396 | 0 |
| 12 | 06-15 | 222.46 | 294.6 | +72.1 | 287.85 | 385.0 | +97.2 | -25.0 | 0.025 | 0 |
| 13 | 06-22 | 303.33 | 322.1 | +18.8 | 277.70 | 331.3 | +53.6 | -34.8 | 0.739 | 0 |
| 14 | 06-29 | 317.52 | 306.5 | -11.0 | 335.14 | 363.3 | +28.2 | -39.2 | 0.333 | 0 |
| 15 | 07-06 | 322.15 | 552.1 | **+230.0** | 383.16 | 581.4 | **+198.2** | +31.7 | 0.073 | 0 |
| 16 | 07-20 | 369.03 | 362.3 |  -6.7 | 275.17 | 246.7 | -28.5 | +21.7 | 0.991 | 1 |

Residual SD 46.5 FP on 8 periods; realized spread SD from the F1 memo was
56.4 FP on its (partly corrupted) panel. The three highest-confidence calls
(P12 0.025 L, P16 0.991 W, P15 0.073 L) were all **correct**; the misses are
mid-range (P13 0.739 L, P9 0.855 W, P14 0.333 L).

## 7. What would settle each open question

* **The mean bias itself.** 8 of my own matchups per season will never resolve
  7pp. The fix is to widen the panel, not to wait: **log a projection snapshot
  for all four BrownU matchups each period, not just mine** (4x the n
  immediately, and it removes the "my team happens to be worse than projected"
  confound entirely, because the league-wide win rate is 0.500 by construction).
  Build it into `log_prediction`. At 4 matchups x ~20 periods that is ~80
  observations/season, so the ~396 needed for 80% power at 7pp arrives in
  ~5 seasons — still slow, but a 10pp bias (~194) lands in ~2.5.
* **H4 (unconfirmed-start probability 0.80).** Add a per-snapshot start ledger:
  `(snapshot_date, period, team, mlbam, predicted_start_date, confirmed_flag)`
  written alongside `predictions_history.csv`, then join realised starts from
  the MLB Stats API. The realised occurrence rate of `confirmed=False`
  predictions is a direct read of whether 0.80 is right, needs ~100 flagged
  starts (about 3 weeks of logging), and is a one-parameter fix if wrong.
  **Until that ledger exists this hypothesis cannot be evaluated at all.**
* **H3 (opponent churn).** `matchup_rosters_history.parquet` already snapshots
  all 8 rosters daily. Recomputing each opponent's projected total under the
  *end-of-period* roster and differencing against the frozen build-time roster
  gives the churn effect directly, without needing the win/loss outcome. That
  is a real study and is the highest-value follow-up.
* **The F1 variance verdict (highest priority).** Run
  `python scripts/xfp/fetch_closed_matchup_actuals.py --repair`, then re-run
  `scripts/xfp/validate_hitter_sigma_scale.py` section 7b. If the post-fix
  dispersion stays near 0.71 the team-sigma assembly is too wide and the fix
  overshot at the TEAM level even though the per-hitter measurement was right.
* **The multi-week projection-window defect.** Re-run the period-15 build with
  the horizon taken from `resolve_period_meta()['week_end']` and check the
  07-06 projected total lands near 552/581 rather than 322/383.

## 8. Files

* `scripts/xfp/diagnose_pwin_mean_bias.py` — the diagnostic (this memo's numbers)
* `scripts/xfp/fetch_closed_matchup_actuals.py` — the P0 fix (+ `--repair`)
* `tests/test_matchup_actuals_backfill.py` — 7 tests; all 7 fail on the old file
* `tests/test_pwin_mean_bias.py` — 15 tests on the statistical helpers
* `data/research/espn_matchup_finals_2026.json` — cached ESPN truth
* `data/research/pwin_mean_bias_2026-07-30.json` — machine-readable results

---

verdict: **NEGATIVE on the stated hypothesis, POSITIVE on a P0 data defect
that also invalidates the panel evidence behind yesterday's variance fix.**
The reported ~7pp optimistic mean bias in P(win) is **not statistically
distinguishable from zero** at n=8 completed periods (period-level
Poisson-binomial z = -0.76, p = 0.45; gap 95% CI [-0.339, +0.140]; margin
residual -5.4 FP, 95% CI [-35.0, +27.6] against a 47 FP residual SD). No fix
to the projection mean is warranted and none was made. What *was* real is that
the number was computed against corrupted labels: five of eleven live periods
had in-progress single-day scores stored as finals (one with the wrong winner),
a still-open period was graded, two snapshots were logged after their period
closed, and an unstable sort moved the headline by 1.5pp. That backfill defect
is fixed and locked by tests. Secondary but larger in impact: those same labels
produced the F1 track's dispersion evidence, and on ESPN finals the realized
spread SD is 39.64 FP (not 56.41), the pre-fix model scored 0.940 [0.720,1.140]
(not 1.379), and the post-fix widened model scores 0.712 [0.546,0.863] — i.e.
under-confident. The F1 hitter-level measurement stands; its team-level
confirmation must be re-run on repaired labels before any further sigma tuning.
Rule 13 respected — no rh3/rp3/rprs2/baseline xFP value was touched.
