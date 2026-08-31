# Model scorecard — 2026-08-31

**Data health:** 26 PASS / 0 WARN / 0 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2848 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=32151) |
| il_join_match_rate | 2026 | 0.2438 | PASS | ratio 0.76 vs prior-year same-split-day comparator 0.322 (n=3564); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/181 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/181 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/181 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 0 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 1 | PASS | newest IL event 2026-08-30 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1176 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=3564) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=158; ros max split_day=156, season day=158 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=156, season day=158 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-08-30 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-08-30 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-08-30 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 0 | PASS | mtime-based; daily step (0.8) |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none |
| fg_proj_cache_systems_latest | 2026-08-31 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0199 | PASS | 503 rows @ 2026-08-24 -> 513 rows @ 2026-08-31 |
| proj_rowcount_delta_7d | rp3 | 0.0108 | PASS | 371 rows @ 2026-08-24 -> 375 rows @ 2026-08-31 |
| proj_rowcount_delta_7d | rprs2 | 0.0179 | PASS | 392 rows @ 2026-08-24 -> 399 rows @ 2026-08-31 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 513/513 rows @ 2026-08-31 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.776 | PASS | 291/375 rows @ 2026-08-31 (tail-rank players legitimately lack a volume row) |
| collision_team_reachability | all | 1.0 | PASS | 41/41 collision team hints reachable from 30 live ESPN codes |
| collision_smoke | all | 1.0 | PASS | 12/12 canonical resolver cases |
| fa_join_coverage | H | 1.0 | PASS | 238/238 FA H rows join xfp_rh3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |
| fa_join_coverage | SP | 1.0 | PASS | 218/218 FA SP rows join xfp_rp3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |
| fa_join_coverage | RP | 1.0 | PASS | 321/321 FA RP rows join xfp_rprs2_projections.csv by mlbam; +0.001 vs trailing mean 0.999 (WARN -0.05 / FAIL -0.15) |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.1 | PASS | freshest triangulate_nightly_2026-08-31.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-08-31_cards.json present |
| publish_freshness | index | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 27.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-08-31 vs file date 2026-08-31 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-08-24 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.0902 | INFO | anchor=2026-08-24 fwd_days=7 n=252 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.1769 | INFO | n=252 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | -0.008 | INFO | n=252 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.006 | INFO | n=84 MAE=0.235 |
| rh3_bias_7d | T2_mid | -0.0432 | INFO | n=84 MAE=0.297 |
| rh3_bias_7d | T3_high | 0.0939 | INFO | n=84 MAE=0.270 |
| rh3_spearman_rate_7d | C | 0.1202 | INFO | n=28 |
| rh3_spearman_rate_7d | non_C | 0.099 | INFO | n=224 |
| rp3_spearman_rate_7d | all | -0.0227 | INSUFFICIENT | anchor=2026-08-24 fwd_days=7 n=25 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | -0.0227 | INFO | n=25 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_7d | data_driven | -0.0227 | INFO | n=25 |
| rprs2_spearman_total_7d | all | 0.0189 | INFO | anchor=2026-08-24 fwd_days=7 n=101 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.0261 | INFO | n=101 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-08-17 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.1962 | INFO | anchor=2026-08-17 fwd_days=14 n=310 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.359 | INFO | n=310 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0039 | INFO | n=310 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.0126 | INFO | n=104 MAE=0.216 |
| rh3_bias_14d | T2_mid | 0.0552 | INFO | n=103 MAE=0.237 |
| rh3_bias_14d | T3_high | 0.0444 | INFO | n=103 MAE=0.182 |
| rh3_spearman_rate_14d | C | 0.1609 | INFO | n=46 |
| rh3_spearman_rate_14d | non_C | 0.1779 | INFO | n=264 |
| rp3_spearman_rate_14d | all | 0.1949 | INFO | anchor=2026-08-17 fwd_days=14 n=134 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.1557 | INFO | n=134 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.0773 | INFO | n=134 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | -1.1818 | INFO | n=45 MAE=5.146 |
| rp3_bias_14d | T2_mid | 1.5241 | INFO | n=44 MAE=4.421 |
| rp3_bias_14d | T3_high | 1.2207 | INFO | n=45 MAE=5.263 |
| rp3_spearman_rate_14d | data_driven | 0.1949 | INFO | n=134 |
| rprs2_spearman_total_14d | all | 0.2239 | INFO | anchor=2026-08-17 fwd_days=14 n=179 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2066 | INFO | n=179 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-08-10 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.2667 | INFO | anchor=2026-08-10 fwd_days=21 n=307 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.4212 | INFO | n=307 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.058 | INFO | n=307 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | 0.0055 | INFO | n=103 MAE=0.174 |
| rh3_bias_21d | T2_mid | 0.0127 | INFO | n=102 MAE=0.180 |
| rh3_bias_21d | T3_high | 0.0349 | INFO | n=102 MAE=0.170 |
| rh3_spearman_rate_21d | C | 0.329 | INFO | n=47 |
| rh3_spearman_rate_21d | non_C | 0.2331 | INFO | n=260 |
| rp3_spearman_rate_21d | all | 0.3106 | INFO | anchor=2026-08-10 fwd_days=21 n=70 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.3106 | INFO | n=70 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.2687 | INFO | n=70 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -1.458 | INFO | n=24 MAE=4.119 |
| rp3_bias_21d | T2_mid | 0.6902 | INFO | n=23 MAE=4.567 |
| rp3_bias_21d | T3_high | -0.5729 | INFO | n=23 MAE=3.656 |
| rp3_spearman_rate_21d | data_driven | 0.274 | INFO | n=66 |
| rp3_spearman_rate_21d | marcel_il |  | INSUFFICIENT | n=4 |
| rprs2_spearman_total_21d | all | 0.1918 | INFO | anchor=2026-08-10 fwd_days=21 n=163 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2502 | INFO | n=163 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-08-03 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.3169 | INFO | anchor=2026-08-03 fwd_days=28 n=306 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4746 | INFO | n=306 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0825 | INFO | n=306 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0143 | INFO | n=102 MAE=0.152 |
| rh3_bias_28d | T2_mid | 0.0351 | INFO | n=102 MAE=0.149 |
| rh3_bias_28d | T3_high | 0.0275 | INFO | n=102 MAE=0.145 |
| rh3_spearman_rate_28d | C | 0.2447 | INFO | n=44 |
| rh3_spearman_rate_28d | non_C | 0.3101 | INFO | n=262 |
| rp3_spearman_rate_28d | all | 0.2427 | INFO | anchor=2026-08-03 fwd_days=28 n=126 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.2129 | INFO | n=126 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.0712 | INFO | n=126 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -1.6493 | INFO | n=42 MAE=3.836 |
| rp3_bias_28d | T2_mid | -0.1848 | INFO | n=42 MAE=3.354 |
| rp3_bias_28d | T3_high | 0.761 | INFO | n=42 MAE=4.348 |
| rp3_spearman_rate_28d | data_driven | 0.2226 | INFO | n=119 |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=7 |
| rprs2_spearman_total_28d | all | 0.2382 | INFO | anchor=2026-08-03 fwd_days=28 n=155 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.2638 | INFO | n=155 vs fwd fp/appearance |
| vol_h_spearman_volD52 | model | 0.7244 | INFO | anchor=2026-07-10 fwd_days=52 n=418; naive(backward PA pace)=0.654 |
| vol_h_spearman_volD52 | naive | 0.6536 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD52 | all | 0.0708 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD52 | model | 0.6562 | INFO | anchor=2026-07-10 fwd_days=52 n=222 |
| vol_sp_spearman_volD52 | naive | 0.5833 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD52 | all | 0.0729 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
