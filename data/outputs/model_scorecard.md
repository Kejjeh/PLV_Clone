# Model scorecard — 2026-07-10

**Data health:** 15 PASS / 1 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2812 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=30637) |
| il_join_match_rate | 2026 | 0.16 | PASS | ratio 0.62 vs prior-year same-split-day comparator 0.260 (n=2050); collapse (<0.25x) = dead join |
| ros_opp_xwoba_nan_rate | 2026 | 0.159 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2050) |
| ros_cache_split_day_lag | vs_rolling_grid | 1 | PASS | rolling 2026 max split_day=106; ros max split_day=105, season day=106 |
| ros_cache_split_day_lag | vs_calendar | 1 | PASS | ros max split_day=105, season day=106 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-07-09 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-07-09 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-07-09 |
| fg_2026_snapshot_age_days | fg_pit_2026_current.csv | 0 | PASS | mtime-based |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none (window truncated to inception 2026-07-09: 2d observed) |
| fg_proj_cache_systems_latest | 2026-07-10 | 7 | WARN | 7/8 systems; absent: rzips_pit |
| proj_rowcount_delta_7d | rh3 | 0.0312 | PASS | 449 rows @ 2026-07-03 -> 463 rows @ 2026-07-10 |
| proj_rowcount_delta_7d | rp3 | 0.0324 | PASS | 339 rows @ 2026-07-03 -> 350 rows @ 2026-07-10 |
| proj_rowcount_delta_7d | rprs2 | 0.0376 | PASS | 319 rows @ 2026-07-03 -> 331 rows @ 2026-07-10 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 463/463 rows @ 2026-07-10 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7457 | PASS | 261/350 rows @ 2026-07-10 (tail-rank players legitimately lack a volume row) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-07-03 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.1286 | INFO | anchor=2026-07-03 fwd_days=7 n=236 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.2485 | INFO | n=236 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0464 | INFO | n=236 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.0378 | INFO | n=79 MAE=0.222 |
| rh3_bias_7d | T2_mid | -0.0013 | INFO | n=78 MAE=0.298 |
| rh3_bias_7d | T3_high | 0.0172 | INFO | n=79 MAE=0.259 |
| rh3_spearman_rate_7d | C | 0.1966 | INFO | n=25 (position backfilled from latest snapshot) |
| rh3_spearman_rate_7d | non_C | 0.1207 | INFO | n=197 (position backfilled from latest snapshot) |
| rp3_spearman_rate_7d | all | 0.0845 | INSUFFICIENT | anchor=2026-07-03 fwd_days=7 n=26 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.0845 | INFO | n=26 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_7d | data_driven | 0.0766 | INFO | n=25 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_7d | marcel_il |  | INSUFFICIENT | n=1 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_7d | all | 0.221 | INFO | anchor=2026-07-03 fwd_days=7 n=100 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.2134 | INFO | n=100 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-06-26 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.156 | INFO | anchor=2026-06-26 fwd_days=14 n=311 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.3773 | INFO | n=311 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0167 | INFO | n=311 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.0581 | INFO | n=104 MAE=0.233 |
| rh3_bias_14d | T2_mid | -0.0076 | INFO | n=103 MAE=0.219 |
| rh3_bias_14d | T3_high | 0.0306 | INFO | n=104 MAE=0.212 |
| rh3_spearman_rate_14d | C | -0.007 | INFO | n=43 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.1571 | INFO | n=246 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.3027 | INFO | anchor=2026-06-26 fwd_days=14 n=140 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.2765 | INFO | n=140 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.0191 | INFO | n=140 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | -0.056 | INFO | n=47 MAE=4.383 |
| rp3_bias_14d | T2_mid | -0.5557 | INFO | n=46 MAE=6.792 |
| rp3_bias_14d | T3_high | -0.8318 | INFO | n=47 MAE=5.123 |
| rp3_spearman_rate_14d | data_driven | 0.2969 | INFO | n=135 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=5 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_14d | all | 0.2534 | INFO | anchor=2026-06-26 fwd_days=14 n=183 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2548 | INFO | n=183 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-06-19 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.2073 | INFO | anchor=2026-06-19 fwd_days=21 n=311 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.4026 | INFO | n=311 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0583 | INFO | n=311 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0388 | INFO | n=104 MAE=0.196 |
| rh3_bias_21d | T2_mid | -0.0187 | INFO | n=103 MAE=0.170 |
| rh3_bias_21d | T3_high | 0.0219 | INFO | n=104 MAE=0.155 |
| rh3_spearman_rate_21d | C | 0.0257 | INFO | n=41 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.2299 | INFO | n=254 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.3317 | INFO | anchor=2026-06-19 fwd_days=21 n=68 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.3317 | INFO | n=68 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.0699 | INFO | n=68 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | 0.1432 | INFO | n=23 MAE=4.654 |
| rp3_bias_21d | T2_mid | -1.5513 | INFO | n=22 MAE=3.903 |
| rp3_bias_21d | T3_high | 0.5299 | INFO | n=23 MAE=4.741 |
| rp3_spearman_rate_21d | data_driven | 0.3085 | INFO | n=66 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_21d | marcel_il |  | INSUFFICIENT | n=2 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_21d | all | 0.263 | INFO | anchor=2026-06-19 fwd_days=21 n=176 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2829 | INFO | n=176 vs fwd fp/appearance |
| window_28d | all | 25 | INFO | anchor=2026-06-15 fwd_days=25 |
| rh3_spearman_rate_28d | all | 0.1858 | INFO | anchor=2026-06-15 fwd_days=25 n=305 pa_floor=30 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4119 | INFO | n=305 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0296 | INFO | n=305 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0566 | INFO | n=102 MAE=0.189 |
| rh3_bias_28d | T2_mid | -0.0496 | INFO | n=101 MAE=0.175 |
| rh3_bias_28d | T3_high | 0.0366 | INFO | n=102 MAE=0.147 |
| rh3_spearman_rate_28d | C | 0.0247 | INFO | n=39 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.2019 | INFO | n=254 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3221 | INFO | anchor=2026-06-15 fwd_days=25 n=108 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.3255 | INFO | n=108 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.0677 | INFO | n=108 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -0.7149 | INFO | n=36 MAE=4.884 |
| rp3_bias_28d | T2_mid | -1.9487 | INFO | n=36 MAE=3.972 |
| rp3_bias_28d | T3_high | -0.1582 | INFO | n=36 MAE=4.084 |
| rp3_spearman_rate_28d | data_driven | 0.3082 | INFO | n=106 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=2 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.2746 | INFO | anchor=2026-06-15 fwd_days=25 n=168 app_floor=6 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.2948 | INFO | n=168 vs fwd fp/appearance |
| volume_skill | all |  | INSUFFICIENT | earliest proj_volume snapshot is 2026-07-10; no forward games realized yet (boxscore frontier 2026-07-09). First meaningful read ~5+ days after — keep running weekly. |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
