# Model scorecard — 2026-08-03

**Data health:** 25 PASS / 1 WARN / 0 FAIL / 0 SKIP
**Pipeline staleness:** 10 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2812 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=31282) |
| il_join_match_rate | 2026 | 0.1889 | PASS | ratio 0.64 vs prior-year same-split-day comparator 0.295 (n=2695); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/177 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/177 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/177 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 3 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 3 | PASS | newest IL event 2026-07-31 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1232 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2695) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=130; ros max split_day=128, season day=130 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=128, season day=130 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-08-02 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-08-02 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-08-02 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 0 | PASS | mtime-based; daily step (0.8) |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none |
| fg_proj_cache_systems_latest | 2026-08-03 | 7 | WARN | 7/8 systems; absent: steamerr_pit |
| proj_rowcount_delta_7d | rh3 | 0.0169 | PASS | 472 rows @ 2026-07-27 -> 480 rows @ 2026-08-03 |
| proj_rowcount_delta_7d | rp3 | 0.0028 | PASS | 357 rows @ 2026-07-27 -> 358 rows @ 2026-08-03 |
| proj_rowcount_delta_7d | rprs2 | 0.0087 | PASS | 346 rows @ 2026-07-27 -> 349 rows @ 2026-08-03 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 480/480 rows @ 2026-08-03 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7598 | PASS | 272/358 rows @ 2026-08-03 (tail-rank players legitimately lack a volume row) |
| collision_team_reachability | all | 1.0 | PASS | 29/29 collision team hints reachable from 30 live ESPN codes |
| collision_smoke | all | 1.0 | PASS | 12/12 canonical resolver cases |
| fa_join_coverage | H | 1.0 | PASS | 219/219 FA H rows join xfp_rh3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |
| fa_join_coverage | SP | 1.0 | PASS | 210/210 FA SP rows join xfp_rp3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |
| fa_join_coverage | RP | 1.0 | PASS | 282/282 FA RP rows join xfp_rprs2_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 0.0 | PASS | console_data.json vs newest input xfp_rprs2_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 0.1 | PASS | freshest triangulate_nightly_2026-08-03.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-08-03_cards.json present |
| publish_freshness | index | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 23.0 | PASS | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-08-03 vs file date 2026-08-03 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-07-27 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.1451 | INFO | anchor=2026-07-27 fwd_days=7 n=243 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.243 | INFO | n=243 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0276 | INFO | n=243 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.013 | INFO | n=81 MAE=0.282 |
| rh3_bias_7d | T2_mid | 0.0956 | INFO | n=81 MAE=0.225 |
| rh3_bias_7d | T3_high | 0.0463 | INFO | n=81 MAE=0.230 |
| rh3_spearman_rate_7d | C | -0.0068 | INFO | n=22 |
| rh3_spearman_rate_7d | non_C | 0.1594 | INFO | n=221 |
| rp3_spearman_rate_7d | all | 0.1038 | INFO | anchor=2026-07-27 fwd_days=7 n=33 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.1038 | INFO | n=33 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_7d | all | 0.3109 | INFO | n=33 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_7d | T1_low | -3.2037 | INFO | n=11 MAE=4.281 |
| rp3_bias_7d | T2_mid | 0.259 | INFO | n=11 MAE=5.408 |
| rp3_bias_7d | T3_high | 0.1891 | INFO | n=11 MAE=5.339 |
| rp3_spearman_rate_7d | data_driven | 0.1025 | INFO | n=32 |
| rp3_spearman_rate_7d | marcel_il |  | INSUFFICIENT | n=1 |
| rprs2_spearman_total_7d | all | 0.4597 | INFO | anchor=2026-07-27 fwd_days=7 n=110 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.4503 | INFO | n=110 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-07-20 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.191 | INFO | anchor=2026-07-20 fwd_days=14 n=322 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.3844 | INFO | n=322 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0258 | INFO | n=322 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | 0.0027 | INFO | n=108 MAE=0.246 |
| rh3_bias_14d | T2_mid | 0.0494 | INFO | n=107 MAE=0.196 |
| rh3_bias_14d | T3_high | 0.0722 | INFO | n=107 MAE=0.174 |
| rh3_spearman_rate_14d | C | 0.1649 | INFO | n=44 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.1923 | INFO | n=278 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.3016 | INFO | anchor=2026-07-20 fwd_days=14 n=141 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.2535 | INFO | n=141 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.2699 | INFO | n=141 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | 0.0318 | INFO | n=47 MAE=5.566 |
| rp3_bias_14d | T2_mid | -1.3844 | INFO | n=47 MAE=3.885 |
| rp3_bias_14d | T3_high | 0.2743 | INFO | n=47 MAE=5.774 |
| rp3_spearman_rate_14d | data_driven | 0.3312 | INFO | n=132 |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=9 |
| rprs2_spearman_total_14d | all | 0.3028 | INFO | anchor=2026-07-20 fwd_days=14 n=187 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.3077 | INFO | n=187 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-07-13 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.1954 | INFO | anchor=2026-07-13 fwd_days=21 n=298 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.3815 | INFO | n=298 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | -0.0053 | INFO | n=298 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0143 | INFO | n=100 MAE=0.201 |
| rh3_bias_21d | T2_mid | 0.0301 | INFO | n=99 MAE=0.187 |
| rh3_bias_21d | T3_high | 0.0753 | INFO | n=99 MAE=0.162 |
| rh3_spearman_rate_21d | C | 0.278 | INFO | n=36 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.1777 | INFO | n=262 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.6791 | INSUFFICIENT | anchor=2026-07-13 fwd_days=21 n=14 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.6791 | INFO | n=14 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_21d | data_driven | 0.6791 | INSUFFICIENT | n=14 |
| rprs2_spearman_total_21d | all | 0.3169 | INFO | anchor=2026-07-13 fwd_days=21 n=161 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.3098 | INFO | n=161 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-07-06 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.1772 | INFO | anchor=2026-07-06 fwd_days=28 n=308 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.3973 | INFO | n=308 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0155 | INFO | n=308 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0278 | INFO | n=103 MAE=0.174 |
| rh3_bias_28d | T2_mid | 0.011 | INFO | n=102 MAE=0.176 |
| rh3_bias_28d | T3_high | 0.0716 | INFO | n=103 MAE=0.144 |
| rh3_spearman_rate_28d | C | 0.2727 | INFO | n=37 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.1493 | INFO | n=271 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3946 | INFO | anchor=2026-07-06 fwd_days=28 n=113 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.3702 | INFO | n=113 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.2721 | INFO | n=113 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -0.6074 | INFO | n=38 MAE=3.849 |
| rp3_bias_28d | T2_mid | -2.149 | INFO | n=37 MAE=3.834 |
| rp3_bias_28d | T3_high | -0.6282 | INFO | n=38 MAE=4.560 |
| rp3_spearman_rate_28d | data_driven | 0.3953 | INFO | n=112 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=1 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.3305 | INFO | anchor=2026-07-06 fwd_days=28 n=152 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.3473 | INFO | n=152 vs fwd fp/appearance |
| vol_h_spearman_volD24 | model | 0.7858 | INFO | anchor=2026-07-10 fwd_days=24 n=387; naive(backward PA pace)=0.666 |
| vol_h_spearman_volD24 | naive | 0.6661 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD24 | all | 0.1197 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD24 | model | 0.6126 | INFO | anchor=2026-07-10 fwd_days=24 n=205 |
| vol_sp_spearman_volD24 | naive | 0.5294 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD24 | all | 0.0833 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
