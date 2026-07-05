# PLV legacy subsystem: dormant, retained — one load-bearing edge into the live models

The PLV stack is the repo's original namesake: a pitch-grading `PLVModel`
composing five LGBM sub-models (called_strike, contact_whiff, foul_in_play,
batted_ball_value, swing_take), the `pl_plv_model` variant, and the hitter
`ProcessPlusModel`, in `src/plv_clone/models/` with 13 pipelines under
`src/plv_clone/pipelines/` and the 15-command `plv` CLI (`src/plv_clone/cli.py`).
Its daily driver is `scripts/refresh.ps1` wrapping `plv update` — a chain
entirely separate from `scripts/xfp/refresh_dashboards.py`, which contains zero
plv-cli calls. The model files have been frozen since 2026-04-23 (a few touched
2026-05-03/05) while the sibling xfp package moves daily.

**Status decision:** dormant, retained. Not archived, not deleted.

## The one load-bearing edge

`data/outputs/master_hitter_2026.csv` is written by
`src/plv_clone/pipelines/build_exports.py::build_master_hitter` and consumed by
the **wired** `xfp_h2_lock.py` (position map + batter_name enrichment) and by
`rh3`/`rh3_april` (optional position join, gracefully skipped via `exists()`).
Last regenerated **2026-05-16** — the daily xfp pipeline has been consuming a
~4-week-stale position file, so newly called-up hitters get
`primary_position=None` in rh3 output.

Severing this edge (sourcing positions from ESPN `get_all_teams()` or the MLB
Stats API instead) would leave the legacy subsystem with **zero** live
consumers, at which point archiving its `scripts/`-side drivers
(`refresh.ps1`, `gen_leaderboards.py`, `run_plv_review.py`,
`run_process_review.py`, `generate_report.py`, `validate_pl_plv.py`,
`fetch_fangraphs.py`) becomes safe. Until then they stay put.

Other pins: `validate_outputs.py` is held live by
`tests/test_export_integrity.py` (sys.path import); `fantasy/hitter_points.py`
and `pitcher_points.py` consume plv_scores/process_plus outputs.

## Considered and rejected

- **Archive the PLV scripts now.** Rejected: the master_hitter edge is live and
  the staleness is a real defect — archiving the only regeneration path makes
  it permanent.
- **Delete the subsystem.** Rejected for the same reason, plus the `plv` CLI is
  the only documented way to rebuild the historical plv_scores artifacts.

## Follow-up

Replace the rh3/h2 position source with a live one (ESPN or MLB Stats API),
then revisit: the whole legacy chain becomes archive-eligible in one move.
