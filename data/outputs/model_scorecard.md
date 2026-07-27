# Model scorecard — 2026-07-27

**Data health:** 19 PASS / 1 WARN / 1 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2813 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=31079) |
| il_join_match_rate | 2026 | 0.183 | PASS | ratio 0.64 vs prior-year same-split-day comparator 0.287 (n=2492); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/176 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/176 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/176 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 2 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 3 | PASS | newest IL event 2026-07-24 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1392 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2492) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=123; ros max split_day=121, season day=123 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=121, season day=123 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-07-26 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-07-26 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-07-26 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 13 | FAIL | mtime-based; daily step (0.8) — FG scrape appears to be SILENTLY FAILING (13d since last successful update; it exits 0 on chromedriver crash). Run scripts/_oneoff/fg_2026_current.py in an interactive shell with a working Chrome. |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none |
| fg_proj_cache_systems_latest | 2026-07-27 | 7 | WARN | 7/8 systems; absent: steamerr_bat |
| proj_rowcount_delta_7d | rh3 | 0.0107 | PASS | 467 rows @ 2026-07-20 -> 472 rows @ 2026-07-27 |
| proj_rowcount_delta_7d | rp3 | 0.0113 | PASS | 353 rows @ 2026-07-20 -> 357 rows @ 2026-07-27 |
| proj_rowcount_delta_7d | rprs2 | 0.0147 | PASS | 341 rows @ 2026-07-20 -> 346 rows @ 2026-07-27 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 472/472 rows @ 2026-07-27 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7591 | PASS | 271/357 rows @ 2026-07-27 (tail-rank players legitimately lack a volume row) |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.1 | PASS | freshest triangulate_nightly_2026-07-27.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-07-27_cards.json present |
| publish_freshness | index | 0.1 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 23.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-07-27 vs file date 2026-07-27 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-07-20 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.1247 | INFO | anchor=2026-07-20 fwd_days=7 n=249 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.2348 | INFO | n=249 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0253 | INFO | n=249 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.0402 | INFO | n=83 MAE=0.273 |
| rh3_bias_7d | T2_mid | 0.0025 | INFO | n=83 MAE=0.254 |
| rh3_bias_7d | T3_high | 0.0696 | INFO | n=83 MAE=0.219 |
| rh3_spearman_rate_7d | C | 0.0766 | INFO | n=26 (position backfilled from latest snapshot) |
| rh3_spearman_rate_7d | non_C | 0.1239 | INFO | n=223 (position backfilled from latest snapshot) |
| rp3_spearman_rate_7d | all | 0.1947 | INFO | anchor=2026-07-20 fwd_days=7 n=32 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.1947 | INFO | n=32 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_7d | all | 0.2455 | INFO | n=32 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_7d | T1_low | 1.8785 | INFO | n=11 MAE=6.318 |
| rp3_bias_7d | T2_mid | -0.8581 | INFO | n=10 MAE=4.572 |
| rp3_bias_7d | T3_high | 3.1344 | INFO | n=11 MAE=7.401 |
| rp3_spearman_rate_7d | data_driven | 0.2011 | INFO | n=30 |
| rp3_spearman_rate_7d | marcel_il |  | INSUFFICIENT | n=2 |
| rprs2_spearman_total_7d | all | 0.2095 | INFO | anchor=2026-07-20 fwd_days=7 n=98 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.1986 | INFO | n=98 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-07-13 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.1607 | INFO | anchor=2026-07-13 fwd_days=14 n=282 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.2859 | INFO | n=282 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | -0.0123 | INFO | n=282 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | 0.0073 | INFO | n=94 MAE=0.231 |
| rh3_bias_14d | T2_mid | 0.0192 | INFO | n=94 MAE=0.253 |
| rh3_bias_14d | T3_high | 0.0665 | INFO | n=94 MAE=0.217 |
| rh3_spearman_rate_14d | C | 0.2962 | INFO | n=32 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.1285 | INFO | n=250 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.3585 | INFO | anchor=2026-07-13 fwd_days=14 n=106 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.3585 | INFO | n=106 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.2492 | INFO | n=106 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | 0.4734 | INFO | n=36 MAE=6.193 |
| rp3_bias_14d | T2_mid | -1.4607 | INFO | n=35 MAE=4.590 |
| rp3_bias_14d | T3_high | -0.8333 | INFO | n=35 MAE=6.326 |
| rp3_spearman_rate_14d | data_driven | 0.363 | INFO | n=101 |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=5 |
| rprs2_spearman_total_14d | all | 0.2294 | INFO | anchor=2026-07-13 fwd_days=14 n=168 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2544 | INFO | n=168 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-07-06 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.1514 | INFO | anchor=2026-07-06 fwd_days=21 n=302 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.3487 | INFO | n=302 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0465 | INFO | n=302 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0196 | INFO | n=101 MAE=0.184 |
| rh3_bias_21d | T2_mid | 0.0015 | INFO | n=100 MAE=0.201 |
| rh3_bias_21d | T3_high | 0.0643 | INFO | n=101 MAE=0.175 |
| rh3_spearman_rate_21d | C | 0.1808 | INFO | n=37 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.1365 | INFO | n=265 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.3962 | INSUFFICIENT | anchor=2026-07-06 fwd_days=21 n=23 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.3962 | INFO | n=23 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_21d | data_driven | 0.3962 | INFO | n=23 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_21d | all | 0.2822 | INFO | anchor=2026-07-06 fwd_days=21 n=162 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2952 | INFO | n=162 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-06-29 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.1713 | INFO | anchor=2026-06-29 fwd_days=28 n=297 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.3915 | INFO | n=297 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0496 | INFO | n=297 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0392 | INFO | n=99 MAE=0.180 |
| rh3_bias_28d | T2_mid | -0.0261 | INFO | n=99 MAE=0.152 |
| rh3_bias_28d | T3_high | 0.0444 | INFO | n=99 MAE=0.157 |
| rh3_spearman_rate_28d | C | 0.0725 | INFO | n=37 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.1788 | INFO | n=260 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3056 | INFO | anchor=2026-06-29 fwd_days=28 n=107 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.3105 | INFO | n=107 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.0918 | INFO | n=107 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -1.2775 | INFO | n=36 MAE=4.119 |
| rp3_bias_28d | T2_mid | -0.8019 | INFO | n=35 MAE=3.956 |
| rp3_bias_28d | T3_high | -0.229 | INFO | n=36 MAE=4.376 |
| rp3_spearman_rate_28d | data_driven | 0.3014 | INFO | n=104 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=3 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.3164 | INFO | anchor=2026-06-29 fwd_days=28 n=162 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.3256 | INFO | n=162 vs fwd fp/appearance |
| vol_h_spearman_volD17 | model | 0.8079 | INFO | anchor=2026-07-10 fwd_days=17 n=374; naive(backward PA pace)=0.691 |
| vol_h_spearman_volD17 | naive | 0.6913 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD17 | all | 0.1166 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD17 | model | 0.5775 | INFO | anchor=2026-07-10 fwd_days=17 n=201 |
| vol_sp_spearman_volD17 | naive | 0.5057 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD17 | all | 0.0718 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
