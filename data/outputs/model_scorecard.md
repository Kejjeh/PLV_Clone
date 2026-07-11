# Model scorecard — 2026-07-11

**Data health:** 21 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2812 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=30663) |
| il_join_match_rate | 2026 | 0.1609 | PASS | ratio 0.60 vs prior-year same-split-day comparator 0.270 (n=2076); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/173 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/173 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/173 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 1 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 2 | PASS | newest IL event 2026-07-09 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1411 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2076) |
| ros_cache_split_day_lag | vs_rolling_grid | 0 | PASS | rolling 2026 max split_day=107; ros max split_day=107, season day=107 |
| ros_cache_split_day_lag | vs_calendar | 0 | PASS | ros max split_day=107, season day=107 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-07-10 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-07-10 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-07-10 |
| fg_2026_snapshot_age_days | fg_pit_2026_current.csv | 1 | PASS | mtime-based |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none (window truncated to inception 2026-07-09: 3d observed) |
| fg_proj_cache_systems_latest | 2026-07-11 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0176 | PASS | 455 rows @ 2026-07-04 -> 463 rows @ 2026-07-11 |
| proj_rowcount_delta_7d | rp3 | 0.0234 | PASS | 342 rows @ 2026-07-04 -> 350 rows @ 2026-07-11 |
| proj_rowcount_delta_7d | rprs2 | 0.0184 | PASS | 326 rows @ 2026-07-04 -> 332 rows @ 2026-07-11 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 463/463 rows @ 2026-07-11 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7486 | PASS | 262/350 rows @ 2026-07-11 (tail-rank players legitimately lack a volume row) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-07-04 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.119 | INFO | anchor=2026-07-04 fwd_days=7 n=244 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.2213 | INFO | n=244 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0497 | INFO | n=244 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.046 | INFO | n=82 MAE=0.278 |
| rh3_bias_7d | T2_mid | -0.01 | INFO | n=81 MAE=0.288 |
| rh3_bias_7d | T3_high | 0.0329 | INFO | n=81 MAE=0.263 |
| rh3_spearman_rate_7d | C | 0.1002 | INFO | n=26 (position backfilled from latest snapshot) |
| rh3_spearman_rate_7d | non_C | 0.1098 | INFO | n=205 (position backfilled from latest snapshot) |
| rp3_spearman_rate_7d | all | 0.0342 | INSUFFICIENT | anchor=2026-07-04 fwd_days=7 n=27 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.0342 | INFO | n=27 rate-model vs fwd TOTAL fp |
| rp3_spearman_rate_7d | data_driven | 0.0342 | INFO | n=27 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_7d | all | 0.2443 | INFO | anchor=2026-07-04 fwd_days=7 n=96 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.2342 | INFO | n=96 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-06-27 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.186 | INFO | anchor=2026-06-27 fwd_days=14 n=312 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.4031 | INFO | n=312 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0495 | INFO | n=312 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.0336 | INFO | n=104 MAE=0.245 |
| rh3_bias_14d | T2_mid | -0.017 | INFO | n=104 MAE=0.207 |
| rh3_bias_14d | T3_high | 0.0122 | INFO | n=104 MAE=0.210 |
| rh3_spearman_rate_14d | C | 0.0649 | INFO | n=43 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.1803 | INFO | n=253 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.3165 | INFO | anchor=2026-06-27 fwd_days=14 n=140 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.2658 | INFO | n=140 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | 0.0483 | INFO | n=140 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | 0.0029 | INFO | n=47 MAE=4.800 |
| rp3_bias_14d | T2_mid | -0.5456 | INFO | n=46 MAE=6.015 |
| rp3_bias_14d | T3_high | -0.6012 | INFO | n=47 MAE=4.799 |
| rp3_spearman_rate_14d | data_driven | 0.312 | INFO | n=135 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=5 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_14d | all | 0.1987 | INFO | anchor=2026-06-27 fwd_days=14 n=185 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2033 | INFO | n=185 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-06-20 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.1903 | INFO | anchor=2026-06-20 fwd_days=21 n=307 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.4071 | INFO | n=307 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.0547 | INFO | n=307 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.0318 | INFO | n=103 MAE=0.200 |
| rh3_bias_21d | T2_mid | -0.0098 | INFO | n=102 MAE=0.170 |
| rh3_bias_21d | T3_high | 0.0257 | INFO | n=102 MAE=0.158 |
| rh3_spearman_rate_21d | C | -0.0132 | INFO | n=41 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.2018 | INFO | n=255 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.1733 | INFO | anchor=2026-06-20 fwd_days=21 n=69 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.1733 | INFO | n=69 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.0175 | INFO | n=69 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -0.8982 | INFO | n=23 MAE=4.235 |
| rp3_bias_21d | T2_mid | -3.0641 | INFO | n=23 MAE=5.199 |
| rp3_bias_21d | T3_high | 0.4815 | INFO | n=23 MAE=4.560 |
| rp3_spearman_rate_21d | data_driven | 0.1733 | INFO | n=69 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_21d | all | 0.2667 | INFO | anchor=2026-06-20 fwd_days=21 n=174 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2732 | INFO | n=174 vs fwd fp/appearance |
| window_28d | all | 26 | INFO | anchor=2026-06-15 fwd_days=26 |
| rh3_spearman_rate_28d | all | 0.1715 | INFO | anchor=2026-06-15 fwd_days=26 n=304 pa_floor=31 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4003 | INFO | n=304 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.0431 | INFO | n=304 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0679 | INFO | n=102 MAE=0.186 |
| rh3_bias_28d | T2_mid | -0.0475 | INFO | n=101 MAE=0.172 |
| rh3_bias_28d | T3_high | 0.0372 | INFO | n=101 MAE=0.142 |
| rh3_spearman_rate_28d | C | -0.0219 | INFO | n=37 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.1802 | INFO | n=258 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3205 | INFO | anchor=2026-06-15 fwd_days=26 n=114 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.294 | INFO | n=114 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.0831 | INFO | n=114 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -1.1113 | INFO | n=38 MAE=4.760 |
| rp3_bias_28d | T2_mid | -1.6227 | INFO | n=38 MAE=4.195 |
| rp3_bias_28d | T3_high | -0.2597 | INFO | n=38 MAE=3.996 |
| rp3_spearman_rate_28d | data_driven | 0.3073 | INFO | n=112 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=2 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.2786 | INFO | anchor=2026-06-15 fwd_days=26 n=170 app_floor=6 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.3022 | INFO | n=170 vs fwd fp/appearance |
| volume_skill | all |  | INSUFFICIENT | earliest proj_volume snapshot is 2026-07-10; no forward games realized yet (boxscore frontier 2026-07-10). First meaningful read ~5+ days after — keep running weekly. |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
