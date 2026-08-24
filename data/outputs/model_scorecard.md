# Model scorecard — 2026-08-24

**Data health:** 25 PASS / 1 WARN / 0 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2841 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=31923) |
| il_join_match_rate | 2026 | 0.2338 | PASS | ratio 0.74 vs prior-year same-split-day comparator 0.316 (n=3336); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/180 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/180 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/180 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 1 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 1 | PASS | newest IL event 2026-08-23 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1217 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=3336) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=151; ros max split_day=149, season day=151 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=149, season day=151 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-08-23 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-08-23 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-08-23 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 0 | PASS | mtime-based; daily step (0.8) |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none |
| fg_proj_cache_systems_latest | 2026-08-24 | 7 | WARN | 7/8 systems; absent: rzips_pit |
| proj_rowcount_delta_7d | rh3 | 0.0244 | PASS | 491 rows @ 2026-08-17 -> 503 rows @ 2026-08-24 |
| proj_rowcount_delta_7d | rp3 | 0.0137 | PASS | 366 rows @ 2026-08-17 -> 371 rows @ 2026-08-24 |
| proj_rowcount_delta_7d | rprs2 | 0.0681 | PASS | 367 rows @ 2026-08-17 -> 392 rows @ 2026-08-24 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 503/503 rows @ 2026-08-24 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7736 | PASS | 287/371 rows @ 2026-08-24 (tail-rank players legitimately lack a volume row) |
| collision_team_reachability | all | 1.0 | PASS | 41/41 collision team hints reachable from 30 live ESPN codes |
| collision_smoke | all | 1.0 | PASS | 12/12 canonical resolver cases |
| fa_join_coverage | H | 1.0 | PASS | 229/229 FA H rows join xfp_rh3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |
| fa_join_coverage | SP | 1.0 | PASS | 220/220 FA SP rows join xfp_rp3_projections.csv by mlbam; +0.000 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |
| fa_join_coverage | RP | 0.9968 | PASS | 316/317 FA RP rows join xfp_rprs2_projections.csv by mlbam; -0.003 vs trailing mean 1.000 (WARN -0.05 / FAIL -0.15) |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.1 | PASS | freshest triangulate_nightly_2026-08-24.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-08-24_cards.json present |
| publish_freshness | index | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 26.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-08-24 vs file date 2026-08-24 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-08-17 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.1233 | INFO | anchor=2026-08-17 fwd_days=7 n=246 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.2132 | INFO | n=246 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | -0.0306 | INFO | n=246 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.0552 | INFO | n=82 MAE=0.279 |
| rh3_bias_7d | T2_mid | 0.0689 | INFO | n=82 MAE=0.268 |
| rh3_bias_7d | T3_high | 0.0128 | INFO | n=82 MAE=0.261 |
| rh3_spearman_rate_7d | C | 0.1206 | INFO | n=25 |
| rh3_spearman_rate_7d | non_C | 0.1234 | INFO | n=221 |
| rp3_spearman_rate_7d | all | 0.2217 | INSUFFICIENT | anchor=2026-08-17 fwd_days=7 n=28 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.2217 | INFO | n=28 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_7d | data_driven | 0.2217 | INFO | n=28 |
| rprs2_spearman_total_7d | all | 0.1644 | INFO | anchor=2026-08-17 fwd_days=7 n=107 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.2247 | INFO | n=107 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-08-10 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.247 | INFO | anchor=2026-08-10 fwd_days=14 n=308 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.4053 | INFO | n=308 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0808 | INFO | n=308 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | 0.003 | INFO | n=103 MAE=0.214 |
| rh3_bias_14d | T2_mid | 0.0232 | INFO | n=102 MAE=0.194 |
| rh3_bias_14d | T3_high | 0.0081 | INFO | n=103 MAE=0.225 |
| rh3_spearman_rate_14d | C | 0.2707 | INFO | n=44 |
| rh3_spearman_rate_14d | non_C | 0.2095 | INFO | n=264 |
| rp3_spearman_rate_14d | all | 0.2481 | INFO | anchor=2026-08-10 fwd_days=14 n=138 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.228 | INFO | n=138 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.113 | INFO | n=138 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | -0.6453 | INFO | n=46 MAE=5.442 |
| rp3_bias_14d | T2_mid | 0.9589 | INFO | n=46 MAE=4.806 |
| rp3_bias_14d | T3_high | 0.8178 | INFO | n=46 MAE=4.854 |
| rp3_spearman_rate_14d | data_driven | 0.2409 | INFO | n=130 |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=8 |
| rprs2_spearman_total_14d | all | 0.1655 | INFO | anchor=2026-08-10 fwd_days=14 n=178 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2504 | INFO | n=178 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-08-03 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.2873 | INFO | anchor=2026-08-03 fwd_days=21 n=314 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.4628 | INFO | n=314 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0976 | INFO | n=314 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0047 | INFO | n=105 MAE=0.172 |
| rh3_bias_21d | T2_mid | 0.0455 | INFO | n=104 MAE=0.170 |
| rh3_bias_21d | T3_high | 0.0217 | INFO | n=105 MAE=0.177 |
| rh3_spearman_rate_21d | C | 0.1661 | INFO | n=42 |
| rh3_spearman_rate_21d | non_C | 0.2792 | INFO | n=272 |
| rp3_spearman_rate_21d | all | 0.1796 | INFO | anchor=2026-08-03 fwd_days=21 n=72 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.1796 | INFO | n=72 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | -0.0388 | INFO | n=72 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -2.997 | INFO | n=24 MAE=3.975 |
| rp3_bias_21d | T2_mid | -1.0719 | INFO | n=24 MAE=3.605 |
| rp3_bias_21d | T3_high | 0.1931 | INFO | n=24 MAE=4.171 |
| rp3_spearman_rate_21d | data_driven | 0.1904 | INFO | n=70 |
| rp3_spearman_rate_21d | marcel_il |  | INSUFFICIENT | n=2 |
| rprs2_spearman_total_21d | all | 0.2154 | INFO | anchor=2026-08-03 fwd_days=21 n=165 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2427 | INFO | n=165 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-07-27 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.3265 | INFO | anchor=2026-07-27 fwd_days=28 n=311 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.5065 | INFO | n=311 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0892 | INFO | n=311 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | 0.0123 | INFO | n=104 MAE=0.146 |
| rh3_bias_28d | T2_mid | 0.0467 | INFO | n=103 MAE=0.129 |
| rh3_bias_28d | T3_high | 0.0412 | INFO | n=104 MAE=0.153 |
| rh3_spearman_rate_28d | C | 0.301 | INFO | n=45 |
| rh3_spearman_rate_28d | non_C | 0.3104 | INFO | n=266 |
| rp3_spearman_rate_28d | all | 0.3066 | INFO | anchor=2026-07-27 fwd_days=28 n=129 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.2523 | INFO | n=129 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.1277 | INFO | n=129 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -1.3081 | INFO | n=43 MAE=3.672 |
| rp3_bias_28d | T2_mid | 0.1818 | INFO | n=43 MAE=3.505 |
| rp3_bias_28d | T3_high | 0.3327 | INFO | n=43 MAE=4.381 |
| rp3_spearman_rate_28d | data_driven | 0.3115 | INFO | n=123 |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=6 |
| rprs2_spearman_total_28d | all | 0.2313 | INFO | anchor=2026-07-27 fwd_days=28 n=161 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.2675 | INFO | n=161 vs fwd fp/appearance |
| vol_h_spearman_volD45 | model | 0.7304 | INFO | anchor=2026-07-10 fwd_days=45 n=410; naive(backward PA pace)=0.648 |
| vol_h_spearman_volD45 | naive | 0.6485 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD45 | all | 0.082 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD45 | model | 0.65 | INFO | anchor=2026-07-10 fwd_days=45 n=219 |
| vol_sp_spearman_volD45 | naive | 0.5548 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD45 | all | 0.0951 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
