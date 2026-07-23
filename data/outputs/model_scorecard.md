# Model scorecard — 2026-07-20

**Data health:** 20 PASS / 1 WARN / 0 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2813 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=30832) |
| il_join_match_rate | 2026 | 0.171 | PASS | ratio 0.61 vs prior-year same-split-day comparator 0.279 (n=2245); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/175 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/175 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/175 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 1 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 3 | PASS | newest IL event 2026-07-17 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1336 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2245) |
| ros_cache_split_day_lag | vs_rolling_grid | 0 | PASS | rolling 2026 max split_day=116; ros max split_day=116, season day=116 |
| ros_cache_split_day_lag | vs_calendar | 0 | PASS | ros max split_day=116, season day=116 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-07-19 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-07-19 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-07-19 |
| fg_2026_snapshot_age_days | fg_pit_2026_current.csv | 6 | WARN | mtime-based |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none (window truncated to inception 2026-07-09: 12d observed) |
| fg_proj_cache_systems_latest | 2026-07-20 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0086 | PASS | 463 rows @ 2026-07-13 -> 467 rows @ 2026-07-20 |
| proj_rowcount_delta_7d | rp3 | 0.0057 | PASS | 351 rows @ 2026-07-13 -> 353 rows @ 2026-07-20 |
| proj_rowcount_delta_7d | rprs2 | 0.024 | PASS | 333 rows @ 2026-07-13 -> 341 rows @ 2026-07-20 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 467/467 rows @ 2026-07-20 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7535 | PASS | 266/353 rows @ 2026-07-20 (tail-rank players legitimately lack a volume row) |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.0 | PASS | freshest triangulate_nightly_2026-07-20.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-07-20_cards.json present |
| publish_freshness | index | 0.1 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 19.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-07-20 vs file date 2026-07-20 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-07-13 fwd_days=7 |
| rh3_spearman_rate_7d | all | -0.1768 | INSUFFICIENT | anchor=2026-07-13 fwd_days=7 n=19 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | -0.1784 | INFO | n=19 rate-model vs fwd TOTAL fp |
| rh3_spearman_rate_7d | C |  | INSUFFICIENT | n=2 (position backfilled from latest snapshot) |
| rh3_spearman_rate_7d | non_C | -0.1105 | INFO | n=16 (position backfilled from latest snapshot) |
| rp3_spearman_rate_7d | all |  | INSUFFICIENT | anchor=2026-07-13 fwd_days=7 n=0 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all |  | INFO | n=0 rate-model vs fwd TOTAL fp |
| rprs2_spearman_total_7d | all |  | INSUFFICIENT | anchor=2026-07-13 fwd_days=7 n=0 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all |  | INFO | n=0 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-07-06 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.1285 | INFO | anchor=2026-07-06 fwd_days=14 n=284 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.2782 | INFO | n=284 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0415 | INFO | n=284 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.0352 | INFO | n=95 MAE=0.237 |
| rh3_bias_14d | T2_mid | -0.0128 | INFO | n=94 MAE=0.260 |
| rh3_bias_14d | T3_high | 0.069 | INFO | n=95 MAE=0.210 |
| rh3_spearman_rate_14d | C | 0.2355 | INFO | n=34 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.0671 | INFO | n=232 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.3718 | INFO | anchor=2026-07-06 fwd_days=14 n=95 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.3871 | INFO | n=95 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.1208 | INFO | n=95 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | 0.8864 | INFO | n=32 MAE=4.974 |
| rp3_bias_14d | T2_mid | -2.2223 | INFO | n=31 MAE=5.811 |
| rp3_bias_14d | T3_high | -1.3177 | INFO | n=32 MAE=5.331 |
| rp3_spearman_rate_14d | data_driven | 0.3759 | INFO | n=94 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=1 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_14d | all | 0.2414 | INFO | anchor=2026-07-06 fwd_days=14 n=164 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2337 | INFO | n=164 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-06-29 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.1568 | INFO | anchor=2026-06-29 fwd_days=21 n=291 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.3733 | INFO | n=291 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0488 | INFO | n=291 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0462 | INFO | n=97 MAE=0.193 |
| rh3_bias_21d | T2_mid | -0.0436 | INFO | n=97 MAE=0.175 |
| rh3_bias_21d | T3_high | 0.0329 | INFO | n=97 MAE=0.179 |
| rh3_spearman_rate_21d | C | 0.1253 | INFO | n=38 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.1255 | INFO | n=240 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.3153 | INFO | anchor=2026-06-29 fwd_days=21 n=31 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.3153 | INFO | n=31 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.3383 | INFO | n=31 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -2.2142 | INFO | n=11 MAE=4.766 |
| rp3_bias_21d | T2_mid | 0.5939 | INFO | n=10 MAE=2.836 |
| rp3_bias_21d | T3_high | -2.4303 | INFO | n=10 MAE=4.879 |
| rp3_spearman_rate_21d | data_driven | 0.3153 | INFO | n=31 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_21d | all | 0.3269 | INFO | anchor=2026-06-29 fwd_days=21 n=162 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.3233 | INFO | n=162 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-06-22 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.2113 | INFO | anchor=2026-06-22 fwd_days=28 n=219 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4172 | INFO | n=219 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0623 | INFO | n=219 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0259 | INFO | n=73 MAE=0.161 |
| rh3_bias_28d | T2_mid | -0.0463 | INFO | n=73 MAE=0.142 |
| rh3_bias_28d | T3_high | 0.0622 | INFO | n=73 MAE=0.148 |
| rh3_spearman_rate_28d | C | 0.4006 | INFO | n=22 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.156 | INFO | n=187 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.2431 | INFO | anchor=2026-06-22 fwd_days=28 n=102 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.2223 | INFO | n=102 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.0079 | INFO | n=102 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -2.5126 | INFO | n=34 MAE=4.524 |
| rp3_bias_28d | T2_mid | -1.0225 | INFO | n=34 MAE=4.011 |
| rp3_bias_28d | T3_high | -0.4463 | INFO | n=34 MAE=3.503 |
| rp3_spearman_rate_28d | data_driven | 0.256 | INFO | n=100 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=2 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.2548 | INFO | anchor=2026-06-22 fwd_days=28 n=155 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.2531 | INFO | n=155 vs fwd fp/appearance |
| vol_h_spearman_volD10 | model | 0.8326 | INFO | anchor=2026-07-10 fwd_days=10 n=356; naive(backward PA pace)=0.718 |
| vol_h_spearman_volD10 | naive | 0.718 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD10 | all | 0.1146 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD10 | model | 0.5463 | INFO | anchor=2026-07-10 fwd_days=10 n=173 |
| vol_sp_spearman_volD10 | naive | 0.4615 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD10 | all | 0.0848 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
