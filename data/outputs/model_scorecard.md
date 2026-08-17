# Model scorecard — 2026-08-17

**Data health:** 26 PASS / 0 WARN / 0 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2833 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=31732) |
| il_join_match_rate | 2026 | 0.2235 | PASS | ratio 0.72 vs prior-year same-split-day comparator 0.309 (n=3145); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/179 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/179 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/179 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 0 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 1 | PASS | newest IL event 2026-08-16 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1227 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=3145) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=144; ros max split_day=142, season day=144 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=142, season day=144 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-08-16 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-08-16 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-08-16 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 0 | PASS | mtime-based; daily step (0.8) |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none |
| fg_proj_cache_systems_latest | 2026-08-17 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0166 | PASS | 483 rows @ 2026-08-10 -> 491 rows @ 2026-08-17 |
| proj_rowcount_delta_7d | rp3 | 0.0139 | PASS | 361 rows @ 2026-08-10 -> 366 rows @ 2026-08-17 |
| proj_rowcount_delta_7d | rprs2 | 0.0194 | PASS | 360 rows @ 2026-08-10 -> 367 rows @ 2026-08-17 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 491/491 rows @ 2026-08-17 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7705 | PASS | 282/366 rows @ 2026-08-17 (tail-rank players legitimately lack a volume row) |
| collision_team_reachability | all | 1.0 | PASS | 41/41 collision team hints reachable from 30 live ESPN codes |
| collision_smoke | all | 1.0 | PASS | 12/12 canonical resolver cases |
| fa_join_coverage | H | 1.0 | PASS | 222/222 FA H rows join xfp_rh3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |
| fa_join_coverage | SP | 1.0 | PASS | 218/218 FA SP rows join xfp_rp3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |
| fa_join_coverage | RP | 1.0 | PASS | 296/296 FA RP rows join xfp_rprs2_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.1 | PASS | freshest triangulate_nightly_2026-08-17.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-08-17_cards.json present |
| publish_freshness | index | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 26.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-08-17 vs file date 2026-08-17 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-08-10 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.2083 | INFO | anchor=2026-08-10 fwd_days=7 n=241 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.3027 | INFO | n=241 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0867 | INFO | n=241 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | 0.0074 | INFO | n=81 MAE=0.256 |
| rh3_bias_7d | T2_mid | 0.0274 | INFO | n=80 MAE=0.258 |
| rh3_bias_7d | T3_high | 0.0119 | INFO | n=80 MAE=0.279 |
| rh3_spearman_rate_7d | C | 0.1975 | INFO | n=21 |
| rh3_spearman_rate_7d | non_C | 0.2094 | INFO | n=220 |
| rp3_spearman_rate_7d | all | 0.4794 | INFO | anchor=2026-08-10 fwd_days=7 n=30 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.4794 | INFO | n=30 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_7d | all | 0.2136 | INFO | n=30 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_7d | T1_low | -0.2084 | INFO | n=10 MAE=4.546 |
| rp3_bias_7d | T2_mid | 0.2607 | INFO | n=10 MAE=5.341 |
| rp3_bias_7d | T3_high | -2.4936 | INFO | n=10 MAE=4.999 |
| rp3_spearman_rate_7d | data_driven | 0.4664 | INFO | n=27 |
| rp3_spearman_rate_7d | marcel_il |  | INSUFFICIENT | n=3 |
| rprs2_spearman_total_7d | all | 0.1707 | INFO | anchor=2026-08-10 fwd_days=7 n=82 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.1695 | INFO | n=82 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-08-03 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.2625 | INFO | anchor=2026-08-03 fwd_days=14 n=310 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.4687 | INFO | n=310 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0994 | INFO | n=310 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.0162 | INFO | n=104 MAE=0.210 |
| rh3_bias_14d | T2_mid | 0.0389 | INFO | n=103 MAE=0.203 |
| rh3_bias_14d | T3_high | 0.0146 | INFO | n=103 MAE=0.186 |
| rh3_spearman_rate_14d | C | 0.102 | INFO | n=43 |
| rh3_spearman_rate_14d | non_C | 0.2817 | INFO | n=267 |
| rp3_spearman_rate_14d | all | 0.2834 | INFO | anchor=2026-08-03 fwd_days=14 n=139 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.2554 | INFO | n=139 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.1175 | INFO | n=139 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | -0.5842 | INFO | n=47 MAE=4.486 |
| rp3_bias_14d | T2_mid | -0.7308 | INFO | n=46 MAE=5.112 |
| rp3_bias_14d | T3_high | 0.3357 | INFO | n=46 MAE=5.101 |
| rp3_spearman_rate_14d | data_driven | 0.281 | INFO | n=132 |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=7 |
| rprs2_spearman_total_14d | all | 0.1815 | INFO | anchor=2026-08-03 fwd_days=14 n=178 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2306 | INFO | n=178 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-07-27 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.3041 | INFO | anchor=2026-07-27 fwd_days=21 n=313 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.506 | INFO | n=313 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0835 | INFO | n=313 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | 0.0037 | INFO | n=105 MAE=0.178 |
| rh3_bias_21d | T2_mid | 0.0386 | INFO | n=104 MAE=0.160 |
| rh3_bias_21d | T3_high | 0.0346 | INFO | n=104 MAE=0.148 |
| rh3_spearman_rate_21d | C | 0.2637 | INFO | n=46 |
| rh3_spearman_rate_21d | non_C | 0.307 | INFO | n=267 |
| rp3_spearman_rate_21d | all | 0.3709 | INFO | anchor=2026-07-27 fwd_days=21 n=76 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.3709 | INFO | n=76 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.168 | INFO | n=76 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -0.974 | INFO | n=26 MAE=4.649 |
| rp3_bias_21d | T2_mid | -0.5822 | INFO | n=25 MAE=3.923 |
| rp3_bias_21d | T3_high | -1.1988 | INFO | n=25 MAE=4.590 |
| rp3_spearman_rate_21d | data_driven | 0.3717 | INFO | n=73 |
| rp3_spearman_rate_21d | marcel_il |  | INSUFFICIENT | n=3 |
| rprs2_spearman_total_21d | all | 0.2839 | INFO | anchor=2026-07-27 fwd_days=21 n=169 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.3079 | INFO | n=169 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-07-20 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.2653 | INFO | anchor=2026-07-20 fwd_days=28 n=312 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.5121 | INFO | n=312 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0599 | INFO | n=312 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0089 | INFO | n=104 MAE=0.172 |
| rh3_bias_28d | T2_mid | 0.0355 | INFO | n=104 MAE=0.137 |
| rh3_bias_28d | T3_high | 0.048 | INFO | n=104 MAE=0.135 |
| rh3_spearman_rate_28d | C | 0.0861 | INFO | n=44 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.2915 | INFO | n=268 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3023 | INFO | anchor=2026-07-20 fwd_days=28 n=125 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.294 | INFO | n=125 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.1827 | INFO | n=125 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -1.2561 | INFO | n=42 MAE=3.701 |
| rp3_bias_28d | T2_mid | -1.0667 | INFO | n=41 MAE=3.937 |
| rp3_bias_28d | T3_high | -0.5338 | INFO | n=42 MAE=4.396 |
| rp3_spearman_rate_28d | data_driven | 0.3308 | INFO | n=115 |
| rp3_spearman_rate_28d | marcel_il | -0.2242 | INSUFFICIENT | n=10 |
| rprs2_spearman_total_28d | all | 0.3105 | INFO | anchor=2026-07-20 fwd_days=28 n=159 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.3209 | INFO | n=159 vs fwd fp/appearance |
| vol_h_spearman_volD38 | model | 0.7473 | INFO | anchor=2026-07-10 fwd_days=38 n=402; naive(backward PA pace)=0.657 |
| vol_h_spearman_volD38 | naive | 0.6567 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD38 | all | 0.0906 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD38 | model | 0.6534 | INFO | anchor=2026-07-10 fwd_days=38 n=216 |
| vol_sp_spearman_volD38 | naive | 0.5553 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD38 | all | 0.0982 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
