# Model scorecard — 2026-08-10

**Data health:** 26 PASS / 0 WARN / 0 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2824 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=31520) |
| il_join_match_rate | 2026 | 0.2087 | PASS | ratio 0.69 vs prior-year same-split-day comparator 0.302 (n=2933); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/178 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/178 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/178 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 2 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 3 | PASS | newest IL event 2026-08-07 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1214 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2933) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=137; ros max split_day=135, season day=137 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=135, season day=137 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-08-09 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-08-09 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-08-09 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 0 | PASS | mtime-based; daily step (0.8) |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none |
| fg_proj_cache_systems_latest | 2026-08-10 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0063 | PASS | 480 rows @ 2026-08-03 -> 483 rows @ 2026-08-10 |
| proj_rowcount_delta_7d | rp3 | 0.0084 | PASS | 358 rows @ 2026-08-03 -> 361 rows @ 2026-08-10 |
| proj_rowcount_delta_7d | rprs2 | 0.0315 | PASS | 349 rows @ 2026-08-03 -> 360 rows @ 2026-08-10 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 483/483 rows @ 2026-08-10 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7645 | PASS | 276/361 rows @ 2026-08-10 (tail-rank players legitimately lack a volume row) |
| collision_team_reachability | all | 1.0 | PASS | 41/41 collision team hints reachable from 30 live ESPN codes |
| collision_smoke | all | 1.0 | PASS | 12/12 canonical resolver cases |
| fa_join_coverage | H | 1.0 | PASS | 216/216 FA H rows join xfp_rh3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |
| fa_join_coverage | SP | 1.0 | PASS | 213/213 FA SP rows join xfp_rp3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |
| fa_join_coverage | RP | 1.0 | PASS | 292/292 FA RP rows join xfp_rprs2_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.1 | PASS | freshest triangulate_nightly_2026-08-10.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-08-10_cards.json present |
| publish_freshness | index | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 24.4 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 36.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-08-10 vs file date 2026-08-10 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-08-03 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.202 | INFO | anchor=2026-08-03 fwd_days=7 n=255 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.292 | INFO | n=255 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0835 | INFO | n=255 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.0059 | INFO | n=85 MAE=0.268 |
| rh3_bias_7d | T2_mid | 0.0337 | INFO | n=85 MAE=0.247 |
| rh3_bias_7d | T3_high | 0.0018 | INFO | n=85 MAE=0.258 |
| rh3_spearman_rate_7d | C | 0.1941 | INFO | n=29 |
| rh3_spearman_rate_7d | non_C | 0.2006 | INFO | n=226 |
| rp3_spearman_rate_7d | all | 0.2338 | INFO | anchor=2026-08-03 fwd_days=7 n=30 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.2338 | INFO | n=30 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_7d | all | 0.0113 | INFO | n=30 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_7d | T1_low | -1.1448 | INFO | n=10 MAE=4.725 |
| rp3_bias_7d | T2_mid | 0.2622 | INFO | n=10 MAE=7.273 |
| rp3_bias_7d | T3_high | -1.434 | INFO | n=10 MAE=6.932 |
| rp3_spearman_rate_7d | data_driven | 0.235 | INFO | n=29 |
| rp3_spearman_rate_7d | marcel_il |  | INSUFFICIENT | n=1 |
| rprs2_spearman_total_7d | all | 0.179 | INFO | anchor=2026-08-03 fwd_days=7 n=100 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.1806 | INFO | n=100 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-07-27 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.252 | INFO | anchor=2026-07-27 fwd_days=14 n=312 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.4564 | INFO | n=312 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0749 | INFO | n=312 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | 0.0033 | INFO | n=104 MAE=0.207 |
| rh3_bias_14d | T2_mid | 0.0465 | INFO | n=104 MAE=0.181 |
| rh3_bias_14d | T3_high | 0.0413 | INFO | n=104 MAE=0.170 |
| rh3_spearman_rate_14d | C | 0.2 | INFO | n=42 |
| rh3_spearman_rate_14d | non_C | 0.2525 | INFO | n=270 |
| rp3_spearman_rate_14d | all | 0.2951 | INFO | anchor=2026-07-27 fwd_days=14 n=140 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.2514 | INFO | n=140 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.1261 | INFO | n=140 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | -1.0319 | INFO | n=47 MAE=4.995 |
| rp3_bias_14d | T2_mid | -0.8513 | INFO | n=46 MAE=5.422 |
| rp3_bias_14d | T3_high | -0.4259 | INFO | n=47 MAE=5.036 |
| rp3_spearman_rate_14d | data_driven | 0.3057 | INFO | n=134 |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=6 |
| rprs2_spearman_total_14d | all | 0.3286 | INFO | anchor=2026-07-27 fwd_days=14 n=181 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2959 | INFO | n=181 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-07-20 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.2498 | INFO | anchor=2026-07-20 fwd_days=21 n=316 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.4842 | INFO | n=316 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0583 | INFO | n=316 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0048 | INFO | n=106 MAE=0.190 |
| rh3_bias_21d | T2_mid | 0.037 | INFO | n=105 MAE=0.143 |
| rh3_bias_21d | T3_high | 0.0493 | INFO | n=105 MAE=0.141 |
| rh3_spearman_rate_21d | C | 0.0384 | INFO | n=43 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.2757 | INFO | n=273 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.2958 | INFO | anchor=2026-07-20 fwd_days=21 n=73 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.2958 | INFO | n=73 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.1459 | INFO | n=73 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -1.9801 | INFO | n=25 MAE=3.958 |
| rp3_bias_21d | T2_mid | -0.8332 | INFO | n=24 MAE=3.712 |
| rp3_bias_21d | T3_high | -1.2205 | INFO | n=24 MAE=5.677 |
| rp3_spearman_rate_21d | data_driven | 0.3201 | INFO | n=70 |
| rp3_spearman_rate_21d | marcel_il |  | INSUFFICIENT | n=3 |
| rprs2_spearman_total_21d | all | 0.3068 | INFO | anchor=2026-07-20 fwd_days=21 n=169 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.3125 | INFO | n=169 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-07-13 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.2338 | INFO | anchor=2026-07-13 fwd_days=28 n=295 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4635 | INFO | n=295 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0084 | INFO | n=295 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0161 | INFO | n=99 MAE=0.174 |
| rh3_bias_28d | T2_mid | 0.0155 | INFO | n=98 MAE=0.133 |
| rh3_bias_28d | T3_high | 0.0564 | INFO | n=98 MAE=0.137 |
| rh3_spearman_rate_28d | C | 0.0811 | INFO | n=37 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.2451 | INFO | n=258 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3669 | INFO | anchor=2026-07-13 fwd_days=28 n=112 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.3426 | INFO | n=112 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.1854 | INFO | n=112 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -1.3219 | INFO | n=38 MAE=3.666 |
| rp3_bias_28d | T2_mid | -1.6779 | INFO | n=37 MAE=4.120 |
| rp3_bias_28d | T3_high | -1.1492 | INFO | n=37 MAE=4.743 |
| rp3_spearman_rate_28d | data_driven | 0.3911 | INFO | n=106 |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=6 |
| rprs2_spearman_total_28d | all | 0.3365 | INFO | anchor=2026-07-13 fwd_days=28 n=150 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.3433 | INFO | n=150 vs fwd fp/appearance |
| vol_h_spearman_volD31 | model | 0.7704 | INFO | anchor=2026-07-10 fwd_days=31 n=396; naive(backward PA pace)=0.668 |
| vol_h_spearman_volD31 | naive | 0.6677 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD31 | all | 0.1027 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD31 | model | 0.6257 | INFO | anchor=2026-07-10 fwd_days=31 n=210 |
| vol_sp_spearman_volD31 | naive | 0.543 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD31 | all | 0.0827 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
