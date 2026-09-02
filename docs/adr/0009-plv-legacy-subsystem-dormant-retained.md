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

## Addendum 2026-09-01 — edge severed; scripts-side drivers archived

Corrections to the text above, which had gone stale:

- Four of the seven listed drivers (`gen_leaderboards.py`,
  `run_plv_review.py`, `run_process_review.py`, `validate_pl_plv.py`) were
  already archived to `scripts/_attic/` on 2026-07-04.
- "a chain entirely separate from refresh_dashboards.py, which contains
  zero plv-cli calls" was false from 2026-07-20 (commit e21f10c7): step
  1.98 ran `plv update` WEEKLY, so master_hitter_2026.csv was ≤7 days
  stale — not frozen at 2026-05-16 — and the ACTIVE layer depended on the
  DORMANT chain executing.
- The edge had six readers, not one: rh3.py, rh3_april.py, xfp_h2_lock.py
  (nightly, gating), xfp_volume_pipeline.py (dead constant),
  xfp_h_eval.py (historical 2023/2024 vintages), generate_report.py.

What changed today:

- **Edge severed.** Positions come from
  `plv_clone.data.player_positions.load_position_frame()` over a nightly
  cache (`data/reference/player_positions_{year}.json`) built by the new
  `build_player_positions.py` refresh_all stage — same `build_position_map`
  the chain used, so semantics are identical. A ratchet test
  (`tests/test_position_source.py`) keeps the consumers severed.
- **Step 1.98 retired**; the weekly `plv update` no longer runs. PLV
  boards, masters, and fantasy exports are frozen at their last build;
  `python -X utf8 -m plv_clone.cli update` rebuilds by hand if ever needed.
- **Archived** (batch 2 in `scripts/_attic/README.md`): `refresh.ps1`,
  `fetch_fangraphs.py`, `generate_report.py`; `build-report.yml` moved to
  `docs/archive/workflows/` (it cron'd every 4h year-round).

Still retained deliberately:

- The PACKAGE (`src/plv_clone/models/plv_model.py`, `pipelines/`, the
  `plv` CLI) stays dormant-retained: `refresh_pitch_features.py` (nightly
  step 2.55) imports `pipelines.build_pitch_dataset`, the test suite pins
  the PLV/Process+ math, and the CLI is the only documented rebuild path.
- `scripts/validate_outputs.py` — pinned by
  `tests/test_export_integrity.py` (sys.path `import validate_outputs`).
- `tests/test_contract_schemas.py`'s master-file contracts SKIP when the
  files are absent; the frozen masters keep them active. If the masters
  are ever deleted, those contracts deactivate silently — retire them in
  the same change.
