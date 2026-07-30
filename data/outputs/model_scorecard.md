# Model scorecard — 2026-07-30

**Data health:** 25 PASS / 0 WARN / 1 FAIL / 0 SKIP
**Pipeline staleness:** 8 PASS / 2 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2814 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=31135) |
| il_join_match_rate | 2026 | 0.1856 | PASS | ratio 0.65 vs prior-year same-split-day comparator 0.287 (n=2548); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/176 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/176 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/176 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 1 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 3 | PASS | newest IL event 2026-07-27 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.137 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2548) |
| ros_cache_split_day_lag | vs_rolling_grid | 1 | PASS | rolling 2026 max split_day=125; ros max split_day=124, season day=126 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=124, season day=126 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 2 | PASS | max date 2026-07-28 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 2 | PASS | max date 2026-07-28 |
| boxscore_pitchers_lag_days | all | 2 | PASS | max date 2026-07-28 |
| fg_scrape_silent_fail | fg_pit_2026_current.csv | 15 | FAIL | mtime-based; daily step (0.8) — FG scrape appears to be SILENTLY FAILING (15d since last successful update; it exits 0 on chromedriver crash). Run scripts/_oneoff/fg_2026_current.py in an interactive shell with a working Chrome. |
| fg_proj_cache_missing_days_14d | all | 1 | PASS | missing: 2026-07-30 |
| fg_proj_cache_systems_latest | 2026-07-29 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0064 | PASS | 470 rows @ 2026-07-22 -> 473 rows @ 2026-07-29 |
| proj_rowcount_delta_7d | rp3 | 0.0085 | PASS | 354 rows @ 2026-07-22 -> 357 rows @ 2026-07-29 |
| proj_rowcount_delta_7d | rprs2 | 0.0146 | PASS | 342 rows @ 2026-07-22 -> 347 rows @ 2026-07-29 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 473/473 rows @ 2026-07-29 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7591 | PASS | 271/357 rows @ 2026-07-29 (tail-rank players legitimately lack a volume row) |
| collision_team_reachability | all | 1.0 | PASS | 29/29 collision team hints reachable from 30 live ESPN codes |
| collision_smoke | all | 1.0 | PASS | 12/12 canonical resolver cases |
| fa_join_coverage | H | 1.0 | PASS | 214/214 FA H rows join xfp_rh3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |
| fa_join_coverage | SP | 1.0 | PASS | 209/209 FA SP rows join xfp_rp3_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |
| fa_join_coverage | RP | 1.0 | PASS | 281/281 FA RP rows join xfp_rprs2_projections.csv by mlbam; no trailing baseline yet (need 3+ prior days) — absolute floors 0.70/0.40 applied |

## Pipeline-staleness tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| console_data_freshness | all | 12.7 | WARN | console_data.json vs newest input xfp_rh3_projections.csv; hours behind (>0 = stale decision console — the 2026-07-18 trap) |
| tri_nightly_freshness | nightly_json | 16.7 | PASS | freshest triangulate_nightly_2026-07-29.json; age hours (>=26h = nightly not running) |
| tri_nightly_freshness | cards_sidecar | 1 | PASS | triangulate_nightly_2026-07-29_cards.json present |
| publish_freshness | index | 0.1 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | matchup | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | triangulate | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| publish_freshness | xfp_board | 0.0 | PASS | hours behind console_data.json (>26h = stuck publish) |
| espn_snapshot_ttl | all | 1020.0 | WARN | oldest free_agents_2000.pkl age minutes vs TTL 240min (WARN >960min = stale snapshot lingering) |
| trajectory_endpoint | all | 0 | PASS | max endpoint 2026-07-29 vs file date 2026-07-29 via traj_last_label MM-DD endpoints (gap >3d = frozen 04-25->06-20 trajectory class) |
| golden_stash_leftover | all | 0 | PASS | no .golden_stash dir (nothing stashed) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 6 | INFO | anchor=2026-07-23 fwd_days=6 |
| rh3_spearman_rate_7d | all | 0.0572 | INFO | anchor=2026-07-23 fwd_days=6 n=206 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.1216 | INFO | n=206 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0035 | INFO | n=206 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.0497 | INFO | n=69 MAE=0.251 |
| rh3_bias_7d | T2_mid | 0.0459 | INFO | n=68 MAE=0.249 |
| rh3_bias_7d | T3_high | 0.1104 | INFO | n=69 MAE=0.245 |
| rh3_spearman_rate_7d | C | 0.3771 | INFO | n=15 |
| rh3_spearman_rate_7d | non_C | 0.0339 | INFO | n=191 |
| rp3_spearman_rate_7d | all | 0.3036 | INFO | anchor=2026-07-23 fwd_days=6 n=139 start_floor=1 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.3017 | INFO | n=139 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_7d | all | 0.2335 | INFO | n=139 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_7d | T1_low | 0.8581 | INFO | n=47 MAE=7.019 |
| rp3_bias_7d | T2_mid | -1.3904 | INFO | n=46 MAE=6.302 |
| rp3_bias_7d | T3_high | 0.2609 | INFO | n=46 MAE=8.400 |
| rp3_spearman_rate_7d | data_driven | 0.3145 | INFO | n=133 |
| rp3_spearman_rate_7d | marcel_il |  | INSUFFICIENT | n=6 |
| rprs2_spearman_total_7d | all | 0.3185 | INFO | anchor=2026-07-23 fwd_days=6 n=62 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.295 | INFO | n=62 vs fwd fp/appearance |
| window_14d | all | 13 | INFO | anchor=2026-07-16 fwd_days=13 |
| rh3_spearman_rate_14d | all | 0.2139 | INFO | anchor=2026-07-16 fwd_days=13 n=309 pa_floor=16 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.4043 | INFO | n=309 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0338 | INFO | n=309 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.0146 | INFO | n=103 MAE=0.229 |
| rh3_bias_14d | T2_mid | 0.0419 | INFO | n=103 MAE=0.213 |
| rh3_bias_14d | T3_high | 0.0459 | INFO | n=103 MAE=0.194 |
| rh3_spearman_rate_14d | C | 0.2555 | INFO | n=41 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.1971 | INFO | n=268 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.3724 | INFO | anchor=2026-07-16 fwd_days=13 n=132 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.3417 | INFO | n=132 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.291 | INFO | n=132 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | 1.2407 | INFO | n=44 MAE=5.992 |
| rp3_bias_14d | T2_mid | -1.7878 | INFO | n=44 MAE=4.248 |
| rp3_bias_14d | T3_high | -0.5114 | INFO | n=44 MAE=5.718 |
| rp3_spearman_rate_14d | data_driven | 0.378 | INFO | n=125 |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=7 |
| rprs2_spearman_total_14d | all | 0.2412 | INFO | anchor=2026-07-16 fwd_days=13 n=176 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2283 | INFO | n=176 vs fwd fp/appearance |
| window_21d | all | 20 | INFO | anchor=2026-07-09 fwd_days=20 |
| rh3_spearman_rate_21d | all | 0.2041 | INFO | anchor=2026-07-09 fwd_days=20 n=303 pa_floor=24 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.3801 | INFO | n=303 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.051 | INFO | n=303 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0105 | INFO | n=101 MAE=0.203 |
| rh3_bias_21d | T2_mid | 0.0021 | INFO | n=101 MAE=0.206 |
| rh3_bias_21d | T3_high | 0.0431 | INFO | n=101 MAE=0.153 |
| rh3_spearman_rate_21d | C | 0.2595 | INFO | n=36 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.1834 | INFO | n=267 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.5071 | INSUFFICIENT | anchor=2026-07-09 fwd_days=20 n=15 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.5071 | INFO | n=15 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_21d | data_driven | 0.5071 | INFO | n=15 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_21d | all | 0.2531 | INFO | anchor=2026-07-09 fwd_days=20 n=153 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2592 | INFO | n=153 vs fwd fp/appearance |
| window_28d | all | 27 | INFO | anchor=2026-07-02 fwd_days=27 |
| rh3_spearman_rate_28d | all | 0.1869 | INFO | anchor=2026-07-02 fwd_days=27 n=304 pa_floor=32 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4022 | INFO | n=304 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0598 | INFO | n=304 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0333 | INFO | n=102 MAE=0.178 |
| rh3_bias_28d | T2_mid | -0.0026 | INFO | n=101 MAE=0.161 |
| rh3_bias_28d | T3_high | 0.0524 | INFO | n=101 MAE=0.143 |
| rh3_spearman_rate_28d | C | 0.0678 | INFO | n=38 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.1955 | INFO | n=266 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3794 | INFO | anchor=2026-07-02 fwd_days=27 n=107 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.3457 | INFO | n=107 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.1283 | INFO | n=107 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -0.5905 | INFO | n=36 MAE=3.851 |
| rp3_bias_28d | T2_mid | -1.4021 | INFO | n=35 MAE=4.095 |
| rp3_bias_28d | T3_high | -0.9248 | INFO | n=36 MAE=4.664 |
| rp3_spearman_rate_28d | data_driven | 0.3763 | INFO | n=105 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=2 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.2987 | INFO | anchor=2026-07-02 fwd_days=27 n=171 app_floor=6 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.3038 | INFO | n=171 vs fwd fp/appearance |
| vol_h_spearman_volD20 | model | 0.8058 | INFO | anchor=2026-07-10 fwd_days=19 n=379; naive(backward PA pace)=0.690 |
| vol_h_spearman_volD20 | naive | 0.6901 | INFO | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD20 | all | 0.1157 | INFO | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD20 | model | 0.5561 | INFO | anchor=2026-07-10 fwd_days=19 n=203 |
| vol_sp_spearman_volD20 | naive | 0.4792 | INFO | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD20 | all | 0.0769 | INFO | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
