# Wiring note — RP forward-volume model (step 4.09c), 2026-07-10

Status: model VALIDATED (PASS — pooled LOO Spearman **+0.127** vs naive
persistence, 6/6 years, holdout 2024/2025 both positive, MAE −17.2%;
prereg + results: `data/research/validation_runs/rp_volume_model_2026-07-10.md`).
The snapshot logger (`build_player_projection_history.py`) already has the
`'RP'` entry in `_VOLUME_SOURCES` (verified live 2026-07-10: 331/331 RP rows
filled). The ONLY remaining wiring is the daily refresh step below —
`refresh_dashboards.py` was deliberately NOT edited in the validation run.

## Snippet for refresh_dashboards.py

Insert directly after the 4.09b block (SP volume, currently ends
`print('  ⚠ SP volume projections failed — proj_volume stays NaN today (non-gating)')`)
and before step 4.10 (the snapshot logger MUST run after this so
`proj_volume` fills for RPs):

```python
    # 4.09c. RP forward-appearance volume (validated 2026-07-10, PASS: pooled
    # Spearman +0.127 vs naive g-pace, 6/6 years, holdout 2/2 —
    # rp_volume_model_2026-07-10.md). Completes the volume layer (H/SP/RP).
    # Fail-soft.
    ok_rpvol = run(
        '4.09c. Build RP volume projections',
        'python -X utf8 scripts/xfp/xfp_rp_volume_pipeline.py',
        timeout=600,
    )
    if not ok_rpvol:
        print('  ⚠ RP volume projections failed — proj_volume stays NaN today (non-gating)')
```

## Notes

- Runtime: ~1 min (single statcast pass per year for schedule + relief
  appearance dates; no model pickle — refit daily like the H/SP legs).
- Output: `data/outputs/xfp_rp_volume_projections.csv` (334 relievers on
  2026-07-10). Key column `proj_ros_g_per_teamgame`; `proj_ros_g` is the
  implied RoS appearance count via (162 − team_games_to).
- Units reminder for consumers: RoS RP totals = rprs2 rate skill ×
  proj_ros_g_per_teamgame × team games remaining. Do NOT hand-multiply by a
  flat appearances-per-week heuristic when a volume row exists (same rule
  as the H/SP legs, CLAUDE.md "RoS TOTALS = rate × volume").
- Ordering constraint: must run AFTER the rprs2 pipeline (its output CSV is
  the mlbam-keyed name fallback for arms missing from relievers_multiyr —
  fail-soft if absent) and BEFORE step 4.10.
- Integration into any ranker (e.g. xfp_board RP totals) remains a
  separate, separately-validated step — this note wires the DATA layer only.
