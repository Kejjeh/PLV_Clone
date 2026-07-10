---
signal: injury_proneness features (il_days_prior3yr, career_il_days_to_jan1) as ADDITIONS to the three validated forward-VOLUME models
formula: candidate columns appended to each volume pipeline's FEATS list (Ridge+StandardScaler, unchanged); source data/research/xfp_cache/injury_proneness_by_year.csv, as-of Jan 1 of each year (leakage-safe), joined on (mlbam_id, year), zero-filled where no transaction history
outcome: each pipeline's own LOO target (ros_pa_per_teamgame / ros_gs_per_teamgame / ros_g_per_teamgame), evaluated with each pipeline's own cell-Spearman machinery on the IDENTICAL row set (candidates zero-fill, so eligible() drops no extra rows)
expected_sign: NEGATIVE (more career/recent IL history -> less forward volume)
theory: the volume models' naive-pace over-prediction of the top tercile IS forward injury/rest risk, currently learned only via same-season IL state + recent pace; multi-year proneness (career + prior-3yr IL days) should carry incremental attrition signal
production_target: xfp_volume_pipeline.py (H), xfp_sp_volume_pipeline.py (SP), xfp_rp_volume_pipeline.py (RP) — the 1-2-day-old companion models, NOT rh3/rp3/rprs2
framing: in-season -> ros, per (player, year, split_day)
holdout_years: [2024, 2025]
training_years: H/SP [2018, 2019, 2021, 2022, 2023, 2024, 2025]; RP [2019, 2021, 2022, 2023, 2024, 2025] (each pipeline's own convention)
validation_script: scratchpad harness importing each pipeline module and swapping its FEATS list (pipelines NOT edited until a PASS)
date: 2026-07-10
verdict: REJECTED (all 6 cells + all 3 joints)
---

# Pre-registration — injury-proneness features in the volume models (2026-07-10)

## Candidate features

From `injury_proneness_by_year.csv` (per mlbam_id x year, as-of Jan 1;
MLB transaction log 2015-2026; coverage 2016+ so every TRAIN_YEAR has a
fully-backed prior-3yr window):

1. `il_days_prior3yr` — IL days in the 3 calendar years before `year`
2. `career_il_days_to_jan1` — cumulative career IL days as of Jan 1 of `year`

`il_stints_prior3yr` is EXCLUDED a priori: r=0.656 with il_days_prior3yr
(Step 2.5), collinear; days is the richer measure.

## Step 2.5 data-coverage pre-check (run BEFORE this prereg was locked)

Per-year player join rates vs each substrate's activity-filtered universe:
hitters 53-64%, SP 57-71%, RP 44-63% — stable across all TRAIN_YEARS.
Unmatched players have NO transaction-log entries -> **zero-fill**, which is
semantically correct (zero recorded IL days), not a missing-data patch.
No (mlbam_id, year) duplicates, no NaNs in the file.

## Declared cells (Bonferroni m = 6)

2 features x 3 models = 6 single-feature cells. Additionally the JOINT
(both features together) is run per model and REPORTED, but the joint is
descriptive: integration decisions key off the declared cells, and if a
single cell passes the integrated form is whichever configuration
(single or joint) that model's gates support.

| cell | model | feature |
|---|---|---|
| H1 | hitter volume | il_days_prior3yr |
| H2 | hitter volume | career_il_days_to_jan1 |
| S1 | SP volume | il_days_prior3yr |
| S2 | SP volume | career_il_days_to_jan1 |
| R1 | RP volume | il_days_prior3yr |
| R2 | RP volume | career_il_days_to_jan1 |

## Baseline (Rule 9)

The FULL current production feature set of each volume model — every
feature in VOLUME_FEATS / SP_VOLUME_FEATS / RP_VOLUME_FEATS as shipped
2026-07-09/10, including the same-season IL-state features
(il_stints_to, days_on_il_to, is_on_il_at_split, days_since_il_return_imp)
and all pace/priors. Candidate must add lift ON TOP of these.

Row-set identity: candidates are zero-filled before eligible(), so
baseline and candidate evaluate the exact same rows.

## Gates per cell (locked before results)

1. Pooled LOO cell-Spearman lift vs the full-baseline model >= +0.005
2. Per-year lift > 0 in >= 5 of available LOO years (7 for H/SP, 6 for RP)
3. Holdout: 2024 AND 2025 LOO folds both lift > 0
4. Report (non-gating): final-fit coefficient sign — expected NEGATIVE;
   a passing cell with a positive coefficient is flagged for review, not
   auto-shipped.

Joint (both features) reported per model with the same three statistics.

## Integration rule

For any MODEL where at least one cell (or the joint, if it dominates both
singles and both singles' gates pass) PASSES: add the passing feature(s)
to that pipeline's FEATS list + join/zero-fill in prepare(), rerun the
pipeline end-to-end, confirm the output CSV regenerates sanely (row count
within a few % of prior; top/bottom movers reviewed), append the
integration note here. REJECTED everywhere is a legitimate outcome — the
recent-pace + same-season IL features may already absorb health history.

---

# RESULTS (appended after the run — design above was locked first)

Run: 2026-07-10, scratchpad harness importing each pipeline module and
swapping its FEATS list (pipelines untouched). Candidates zero-filled before
eligible(), so every config evaluated the IDENTICAL row set per model
(H n=61,231 / SP n=26,291 / RP n=40,289 LOO rows). Eligible player-years
with nonzero il_days_prior3yr: H 57.5% / SP 60.1% / RP 52.2%.

Lift = pooled LOO cell-Spearman (candidate config) − (FULL baseline config).
Baselines: H rho 0.7410 (naive 0.6663), SP 0.5246 (0.4196), RP 0.6885 (0.5615).

| cell | model | feature | lift | yrs+ | holdout 24/25 | verdict |
|---|---|---|---|---|---|---|
| H1 | hitter | il_days_prior3yr | +0.0002 | 4/7 | NEG | REJECTED |
| H2 | hitter | career_il_days_to_jan1 | +0.0002 | 5/7 | NEG | REJECTED |
| S1 | SP | il_days_prior3yr | +0.0010 | 5/7 | POS | REJECTED (gate 1) |
| S2 | SP | career_il_days_to_jan1 | +0.0034 | 5/7 | POS | REJECTED (gate 1) |
| R1 | RP | il_days_prior3yr | +0.0001 | 3/6 | NEG | REJECTED |
| R2 | RP | career_il_days_to_jan1 | +0.0005 | 4/6 | POS | REJECTED |

Joint (both features, reported): H +0.0002 (4/7, holdout NEG);
SP +0.0016 (4/7, holdout NEG — worse than S2 alone); RP +0.0004 (4/6,
holdout POS). No joint dominates; none would pass the single-cell gates.

Final-fit standardized coefficients (joint config): career_il_days_to_jan1
is NEGATIVE in all three models (H −0.031, SP −0.005, RP −0.007) — the
expected direction — but il_days_prior3yr flips positive in SP (+0.001) and
RP (+0.003), consistent with the same-season IL-state + recent-pace features
already absorbing the prior-3yr window.

**VERDICT: REJECTED in all 6 declared cells and all 3 joints.** No pipeline
edited; no output regenerated. The only near-signal is S2 (SP
career_il_days_to_jan1, +0.0034 pooled, holdout both positive, correct
negative sign) — real but below the +0.005 gate; the SP model's existing
il_stints_to / days_on_il_to / days_since_il_return_imp features appear to
carry most of the health-history information. Do not re-attempt without a
materially different construction (e.g., injury-TYPE severity weighting or
age x IL-history interaction), and note the hitter result is a hard zero.
