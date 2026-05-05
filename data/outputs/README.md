# xFP Model Outputs

## Production (current)
- **xfp_v11_projections.csv** — 185 SP projections from V11 model. Columns: `pitcher`, `player_name`,
  `xfp_v8_5`, `xfp_v11`, `v11_has_pitching_plus`, `xfp_v8_1`, `xfp_v8`, `xfp_v7`, `xfp_v6`, `xfp_v5`,
  `gs_2026`, `fp_per_start_actual_2026`, `k_pct_2026`, `stuff_xfp`, `ip_premium`, `rolling_ip_last5`,
  `ip_trend`, `ip_trend_score`, `delta_v11_v85`. Pitchers without pitching_plus history have
  `v11_has_pitching_plus=False` and `xfp_v11` set equal to `xfp_v8_5` as fallback.
- **xfp_v11_dashboard.html** — Production dashboard. Self-contained (no runtime file reads).
  Open in browser, or see GitHub Pages mirror at `docs/index.html`.

## Comparison Baseline (kept for V8.5 vs V11 delta analysis)
- **xfp_v8_5_projections.csv** — V8.5 projections. Superseded by V11. Kept so the V11 dashboard's
  delta column has a stable comparison baseline.

## FanGraphs Pitcher Data (input to V11)
- **fangraphs_pitchers_2020.csv** through `fangraphs_pitchers_2026.csv` — 7 years of FG leaderboard
  data, pulled via `scripts/xfp/pull_fg_undetected.py`. Includes Stuff+, Location+, Pitching+, plus
  PitchingBot pb_stuff/pb_command/pb_xrv100. ~500 pitchers per year.

## Archive (`data/outputs/archive/`)
Superseded dashboards and projections from V3 through V8.1. Kept for historical reference; not used
by any live pipeline.

## Note on PLV outputs
Files like `process_report_2026.html`, `master_pitcher_*.parquet`, `hitter_*.csv`, etc. belong to
the separate PLV pipeline and are unrelated to xFP. Do not modify them through xFP workflows.
