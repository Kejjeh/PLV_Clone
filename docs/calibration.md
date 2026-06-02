# Projection calibration

How we validate that the matchup projections actually match reality, and
the gate that flags when they stop doing so.

## What `predictions_history.csv` tracks

`data/outputs/predictions_history.csv` is an append-only log of every
matchup projection snapshot we've ever shown on `matchup.html`. Schema:

| Column | Meaning |
|---|---|
| `timestamp`, `date`, `period` | When the snapshot was taken; ESPN matchup period |
| `my_team`, `opp_team` | Ligers + opponent for that period |
| `my_wtd`, `my_projected_total` | Week-to-date FP + final projection (mine) |
| `opp_wtd`, `opp_projected_total` | Same, opponent |
| `win_probability` | Modelled P(Ligers win) at snapshot time |
| `actual_my_final`, `actual_opp_final` | Final scores once period closes (NaN until backfilled) |
| `model_version` | Tag identifying which projection model produced the row |

Rows are NEVER overwritten. Backfill only fills the `actual_*` columns
when the period has closed.

## How backfill happens

`scripts/xfp/fetch_closed_matchup_actuals.py` is **idempotent** and
**incremental**:

1. Loads `predictions_history.csv`.
2. For every period with any NaN `actual_my_final`, checks whether the
   period's Mon-Sun window has fully passed.
3. If yes, pulls the period's box score via
   `league.box_scores(matchup_period=N)` and fills the missing rows only.
4. Prints one summary line: `Backfilled M new rows; total backfilled now N/T.`

It's invoked automatically by `scripts/xfp/refresh_dashboards.py` (step
3.5, fail-soft — a backfill failure does not block the dashboard build),
so just running the daily refresh keeps the history file fresh.

You can also run it manually any time: `python scripts/xfp/fetch_closed_matchup_actuals.py`.

## How to read the accuracy report

`data/outputs/projection_accuracy_report.md` is regenerated on every
refresh by `scripts/xfp/report_calibration.py`. It contains:

1. **Periods covered** — which weeks have backfilled actuals and which
   model versions exist in each.
2. **Error metrics — all snapshots** — MAE / RMSE / bias for both
   `my_total` and `opp_total`, per `model_version`. Bias > 0 means the
   model over-projects.
3. **Error metrics — latest snapshot per (period, model)** — the
   "end-of-week dashboard view" — cleanest signal of how the final
   projection compared to the final score.
4. **Win-probability calibration** — buckets `0.00-0.25`, `0.25-0.50`,
   `0.50-0.75`, `0.75-1.00`. For each bucket: N, mean predicted win
   prob, actual win rate. Buckets with N < 5 are flagged INSUFFICIENT.
5. **Verdict** — INSUFFICIENT until at least one bucket reaches N ≥ 5
   for at least one model.

When the verdict clears INSUFFICIENT, `report_calibration.py` also writes
`data/outputs/calibration_summary.json` — a machine-readable mirror of
the per-bucket calibration that downstream gates consume.

## Calibration gate semantics

`scripts/xfp/check_calibration_gate.py` is the automated alarm:

* Exits **0** if the model is well-calibrated, defined as:
  for every bucket with N ≥ 5, |mean predicted win prob − actual win
  rate| ≤ 0.15.
* Exits **0 with an INSUFFICIENT note** if no bucket has reached N ≥ 5
  yet (we can't fail what we can't measure).
* Exits **1** if any sufficient bucket has |gap| > 0.15, printing which
  model + bucket failed.

Run it on demand: `python scripts/xfp/check_calibration_gate.py`.

## When to act on miscalibration warnings

A single warning is not enough to retrain. Treat the gate as a tripwire,
not a final verdict.

| Pattern | Likely cause | Action |
|---|---|---|
| One bucket fails, gap 0.15–0.25 | Small-sample noise (still only ~5–10 weeks) | Wait one more closed week; re-check. |
| Multiple buckets fail simultaneously | Model drifted (lineup-spot weights, RP usage changes mid-season, role swaps) | Inspect recent `model_version` rows, compare to the previous version's metrics block. |
| Gap > 0.25 in any sufficient bucket | Likely a real regression — opponent-projection bug or aggregation error | Run `/matchup-audit` to cross-check matchup.html against MLB Stats API; check `build_matchup_dashboard.py` for the four known SP bugs. |
| Persistent bias > 0 on `opp_total` only | Opponent roster aggregation issue (IL'd players counted, benched-by-mistake players counted) | Audit `build_matchup_dashboard.py` opponent-side aggregation. Standing TODO from the period 8 Team Solomon miss. |

Do **not** swap model versions on the basis of < 5 closed periods of
data. The honest threshold for choosing between baseline and MA_v1 is
5+ matchups with both versions present.
