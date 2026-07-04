# _attic — quarantined dead xfp scripts

**Date:** 2026-07-04
**Why:** 2026-07-04 whole-repo audit (8-agent sweep; evidence at
`.cache/audit0704b/quarantine.txt` + `result.json`) verified these files have
**zero live references** — nothing in `refresh_all.py` stages,
`refresh_dashboards.py` steps, any of the 59 `.claude/skills/*.md` files,
`tests/`, launchers, or any live import chain (iterated to a transitive
fixed point). They pollute CodeGraph symbol searches with stale
v-something duplicates (the exact v9/v10/v11 problem CLAUDE.md warns about).

**Not deleted:** `git mv` only — everything stays git-tracked and recoverable.
Move a file back out if a future symbol search or memory file proves it live.

## Contents

- **Dead model-pipeline versions** (superseded by rh3 / rp3 / rprs2):
  `xfp_h3/h4/h5/h6/h7/h9_pipeline.py`, `xfp_rh2/rh4/rht1_pipeline.py`,
  `xfp_rp_pipeline.py`, `xfp_rp2_pipeline.py`, `xfp_rprs1_pipeline.py`
- **Dead MiLB lock pipelines:** `xfp_milb_hitter_lock.py`,
  `xfp_milb_pitcher_lock.py`, `xfp_milb_pitcher_pipeline.py`
- **Superseded utilities:** `week_level_substrate.py` (→ live
  `build_weekly_fp_substrate.py`), `snapshot_projections.py` +
  `accuracy_tracker.py` (→ `build_player_projection_history.py`, refresh
  step 4.10), `build_park_factors.py` + `build_park_factors_by_year.py`
  (park factors now served via the cached map in `lib/extra_lenses`)
- **Dead companions moved for consistency** (each itself on the audit's
  verified list; their only refs were to files above): `test_pa_projection.py`,
  `test_two_stage_total.py` (imported xfp_rht1), `week_level_eval.py`
  (read week_level_substrate.csv), `audit_all_models.py` (referenced
  xfp_milb_pitcher_pipeline)

## Explicit exclusions (kept live per the audit)

`build_pl_cache.py` (wired into refresh step 2.85), `run_positional_board.py`,
`check_calibration_gate.py`, `ci_games_live.py`, `_rp3_validation_harness.py`
(2 live importers), and the 4 `validate_*` files touched 2026-07-04
(2-week hold).
