# rp3 σ single-start coverage study — PRE-REGISTRATION

Registered 2026-07-10 (BEFORE any coverage number was computed).
Status: PRE-REGISTERED — results section to be appended after the run.

## Why this study

- rp3 ships `xfp_rp3_p25/p75` = per_start ± 0.6745·σ, where σ = LOO residual
  lookup (`fit_residual_ci`/`lookup_sigma`) × `alpha_global = 2.41` from
  `data/research/validation_runs/sigma_calibration.json` (`global_alpha_v1`,
  derived 2026-06-03 on the 3,229-start 2021-2025 backtest panel; pooled
  coverage there 51.7%).
- The 2026-06-26 forward-calibration memo measured 39% band coverage but was
  CONFOUNDED (window-mean actuals read against a single-start band, plus
  point-bias skew) and explicitly prescribed THIS study instead of a
  recalibration: live 2026 snapshots vs true NEXT single-start outcomes.
- The unlock condition (per-start projection history) now exists via
  git-committed daily `data/outputs/xfp_rp3_projections.csv` snapshots
  (dailies since early June 2026; calibrated bands shipped 2026-06-03).

## Hypothesis

The current alpha (2.41) under-covers single starts in live 2026 forward
data — i.e. [p25,p75] empirical coverage < 45% — because the alpha was fit
on a pooled 2021-2025 retrospective panel whose residual dispersion may not
match the live-season, snapshot-conditioned single-start error distribution
(and the 2026-06-26 confounded read hinted at 39%).

## Pre-registered design (all choices fixed before computing coverage)

1. **Snapshots.** Every git commit touching `data/outputs/xfp_rp3_projections.csv`
   with commit date ≥ 2026-06-03 (first date the calibrated bands exist) and
   ≤ 2026-07-09. One snapshot per calendar date: the LATEST commit of that
   date. Cached to `data/research/sigma_study_cache/rp3_<date>.csv`.
2. **Snapshot semantics.** A snapshot committed on date D reflects data
   through D−1. Outcome = the pitcher's NEXT single start STRICTLY AFTER D
   (game_date > D), within ≤ 10 days of D.
3. **Outcomes.** `data/research/xfp_cache/boxscore_pitchers.parquet`,
   rows with `gs == 1`; actual = `fp_sp`. Join on MLBAM id only
   (`pitcher` ↔ `mlbam_id`). Never by name.
4. **Exclusions.** Rows with `data_quality_tag == 'marcel_il'` (bands there
   are scaled priors, not data-driven reads). Rows lacking p25/p75 or
   per_start. Starts of pitchers with no snapshot row.
5. **Dedup.** Each (pitcher, game_pk) outcome pair counts ONCE, attributed
   to the LATEST snapshot date strictly before the start. (This is the
   pre-registered choice; a sensitivity slice by days-between is reported
   but the headline uses latest-snapshot-only pairs.)
6. **Metrics.**
   - Empirical coverage of [xfp_rp3_p25, xfp_rp3_p75] (target 50%).
   - [p10,p90] target 80%: the CSV ships no p10/p90 columns, so a DERIVED
     Gaussian band per_start ± 1.2816·xfp_rp3_sigma is measured and labeled
     "derived, same mechanism".
   - Point bias: mean(actual − per_start) and median(actual − per_start),
     to separate band-POSITION from band-WIDTH failure.
   - Recentered coverage: shift both band edges by the pooled MEDIAN error,
     re-measure coverage. If raw coverage fails but recentered coverage is
     in-gate, the problem is center shift, not width — alpha refit would be
     the WRONG fix and the outcome is reported as such.
   - Slices (report n per slice): per_start terciles (computed per snapshot
     date over band-carrying non-marcel rows); data_quality_tag
     (data_driven_full vs data_driven_thin); days between snapshot and
     start (1-2 / 3-5 / 6-10).
7. **Decision rule.** If pooled [p25,p75] coverage is OUTSIDE 45-55% with
   n ≥ 300 pairs AND the failure is a WIDTH problem (recentered coverage
   also outside 45-55%): refit `alpha_global` on the single-start residuals
   via the SAME mechanism that produced 2.41 —
   `alpha = std(actual − per_start) / mean(xfp_rp3_sigma_raw)`
   (sigma_recalibration.md, 2026-06-03) — fit on the FIRST 80% of snapshot
   dates, verify [p25,p75] coverage lands in 45-55% on the HELD-OUT last
   20% of snapshot dates, then update sigma_calibration.json (via the
   established JSON mechanism, no hand-edit of pipeline code) and rerun the
   rp3 pipeline once. If coverage is within 45-55%: NO CHANGE, question
   closes until September. If n < 300: report UNDERPOWERED with the
   projected date n reaches 300, change nothing.
8. **Secondary (measurement-only, NO recalibration this pass).** rh3 hitter
   bands vs next-game FP. `xfp_rh3_p25/p75` are PER-PA units (known past
   units bug — handled explicitly): a game is covered iff
   fp_h / PA_game ∈ [p25, p75] (algebraically identical to
   fp_h ∈ [p25·PA, p75·PA]). PA per (batter, game) counted from
   `statcast_2026.parquet` distinct `at_bat_number`; games with PA=0 or no
   statcast rows excluded. Same snapshot/dedup/≤10-day rules; outcome =
   next single GAME strictly after D from boxscore_hitters.parquet.

## Runner

`data/research/sigma_study_cache/run_sigma_study.py` (one-off study script;
writes no model artifacts unless the decision rule fires, in which case only
`sigma_calibration.json` changes through the established mechanism).

---

## RESULTS (run 2026-07-10, script `data/research/sigma_study_cache/run_sigma_study.py`)

Snapshots used: 30 dates 2026-06-03 .. 2026-07-09 (latest commit per date);
6,266 band-carrying non-marcel snapshot rows; outcomes from
boxscore_pitchers.parquet through 2026-07-09.

### rp3 primary — n = 868 (pitcher, start) pairs (POWERED, ≥300)

| Band | n | coverage | target |
|---|---:|---:|---:|
| [p25,p75] shipped | 868 | **44.9%** (Wilson95 [41.7, 48.3]) | 50% |
| [p10,p90] derived (±1.2816σ) | 868 | 74.0% | 80% |
| [p25,p75] RECENTERED by median err (+0.96) | 868 | **45.5%** | 50% |

Point bias: mean(actual − per_start) = **+0.04** (centered), median = **+0.96**,
sd(err) = 9.77. Error quantiles q10/q25/q50/q75/q90 =
−12.65 / −6.46 / +0.96 / +6.62 / +12.04 — the known right-skew
(sigma_recalibration.md asymmetry note) reproduces live: the MEAN is
unbiased, the MEDIAN sits ~1 FP above the point estimate.

Slices ([p25,p75]):

| Slice | n | coverage |
|---|---:|---:|
| tier T3_low (per-snapshot per_start terciles) | 197 | 52.8% [45.8, 59.6] |
| tier T2_mid | 300 | 40.3% [34.9, 46.0] |
| tier T1_high | 371 | 44.5% [39.5, 49.6] |
| tag data_driven_full | 665 | 44.7% |
| tag data_driven_thin | 203 | 45.8% |
| gap 1-2 days | 753 | 45.2% |
| gap 3-5 days | 99 | 44.4% |
| gap 6-10 days | 16 | 37.5% |

Implied alpha via the SAME mechanism as 2026-06-03
(std(err)/mean(σ_raw)) = **2.730** on the full pairs panel (live sd(err)
9.77 vs 9.09 on the 2021-2025 backtest). Descriptive only: full-sample
coverage at α=2.730 would be 50.8%.

Refit dry-run (computed for the record, NOT acted on): α fit on first 80%
of snapshot dates = 2.717 → coverage 51.6% in-fit (n=721) but **44.2%
(Wilson95 [36.4, 52.3]) on the held-out last 20% of dates (n=147)** —
point estimate outside the 45-55 gate. (Current-α holdout coverage is
40.8% [33.2, 48.9] — the holdout slice is small either way.)

### Decision-rule outcome: **NO CHANGE**

The pre-registered refit condition does NOT fire, on two independent
grounds:

1. **Not a width failure.** Raw coverage 44.9% sits 0.1pp outside the
   45-55 gate (Wilson CI [41.7, 48.3] spans 45), but the RECENTERED
   coverage (+0.96 median-error shift) is **45.5% — inside the gate**.
   Per pre-registered rule 7, refit requires the recentered coverage to
   ALSO fail; the residual miss is a (small, known-asymmetry) center/skew
   effect plus boundary noise, not a clear width problem, and an alpha
   refit is the wrong instrument for it.
2. **The refit fails held-out verification anyway.** α=2.717 fit on the
   first 80% of dates covers only 44.2% on the held-out last 20% — outside
   45-55 — so even under the simpler outside-the-gate reading the
   pre-registered verification step rejects the update.

`sigma_calibration.json` unchanged (α stays 2.41, `global_alpha_v1`).
No pipeline rerun. Question CLOSES until September.

**Watch-list for the September re-run** (re-use the cached pairs +
`run_sigma_study.py`; pairs accrue ~200/week so n≈2,500 by 2026-09-01):
implied live alpha 2.73 > 2.41 and mid-tier coverage 40.3% [34.9, 46.0]
are consistent hints the band is ~10-13% too tight on live data. If the
September panel shows pooled coverage < 45% with the Wilson CI excluding
45%, refit to the then-implied alpha via the same mechanism with the same
80/20 held-out verification.

### rh3 secondary (measurement ONLY — pre-registered no-recalibration)

n = 7,260 (batter, next-game) pairs; PA per game from statcast_2026
distinct at_bat_number; covered iff fp_h/PA ∈ per-PA [p25,p75].

| Band | n | coverage | target |
|---|---:|---:|---:|
| [p25,p75] per-PA vs next-game realized rate | 7,260 | **7.6%** | 50% |
| recentered by median err (−0.175/PA) | 7,260 | 7.8% | — |
| tiers T3_low / T2_mid / T1_high | 2,481/2,408/2,371 | 6.4 / 8.6 / 7.8% | — |

Reading: the rh3 per-PA band is a **RoS-rate interval, not a game-level
interval** — a single game's realized FP/PA (~4 PA draw) is vastly noisier
than the RoS rate the σ was calibrated for, so game-level coverage is
7.6% by construction, not by bug. Mean per-PA bias −0.011 (≈centered);
median −0.175 (single-game rates are right-skewed — most games land below
the projection, a few boom games balance the mean). **Operational note:
never present xfp_rh3_p25/p75 as a "range for tonight" — it is not one,
in either units or width.** No hitter recalibration this pass, per
pre-registration.

### Files

- `data/research/sigma_study_cache/rp3_<date>.csv`, `rh3_<date>.csv` —
  30+30 git-recovered snapshots (cache for the September re-run)
- `data/research/sigma_study_cache/run_sigma_study.py` — the runner
- `data/research/sigma_study_cache/rp3_pairs.csv`, `rh3_pairs.csv` —
  the joined (snapshot, outcome) panels
- `sigma_calibration.json` — UNCHANGED
- No commits made.
