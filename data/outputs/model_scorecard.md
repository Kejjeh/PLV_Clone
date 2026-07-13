# Model scorecard — 2026-07-13

**Data health:** 21 PASS / 0 WARN / 0 FAIL / 0 SKIP

## Data-health tripwires

| check | segment | value | status | note |
|---|---|---|---|---|
| il_join_match_rate | all_years | 0.2815 | PASS | healthy ~0.27-0.32; the 2026-07-09 dead-join bug read 0.0045 (n=30708) |
| il_join_match_rate | 2026 | 0.1678 | PASS | ratio 0.62 vs prior-year same-split-day comparator 0.270 (n=2121); collapse (<0.25x) = dead join |
| il_grid_coverage | rolling_pitchers | 0 | PASS | 0/174 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_hitters | 0 | PASS | 0/174 substrate grid cells absent from IL cache |
| il_grid_coverage | rolling_relievers | 0 | PASS | 0/174 substrate grid cells absent from IL cache |
| il_tx_json_freshness | file_mtime | 0 | PASS | proves the STALE_AFTER_DAYS self-refresh is running (in-season natural cycle ~4d) |
| il_tx_json_freshness | newest_event | 0 | PASS | newest IL event 2026-07-13 (WARN-only: ASG break / transaction lulls are legitimate) |
| ros_opp_xwoba_nan_rate | 2026 | 0.1443 | PASS | fraction of 2026 rolling rows with no schedule-strength value pre-fill (n=2121) |
| ros_cache_split_day_lag | vs_rolling_grid | 2 | PASS | rolling 2026 max split_day=109; ros max split_day=107, season day=109 |
| ros_cache_split_day_lag | vs_calendar | 2 | PASS | ros max split_day=107, season day=109 (weekly grid: some lag is normal) |
| statcast_max_date_lag_days | all | 1 | PASS | max date 2026-07-12 (gf bridge should keep this at ~1 day) |
| boxscore_hitters_lag_days | all | 1 | PASS | max date 2026-07-12 |
| boxscore_pitchers_lag_days | all | 1 | PASS | max date 2026-07-12 |
| fg_2026_snapshot_age_days | fg_pit_2026_current.csv | 1 | PASS | mtime-based |
| fg_proj_cache_missing_days_14d | all | 0 | PASS | missing: none (window truncated to inception 2026-07-09: 5d observed) |
| fg_proj_cache_systems_latest | 2026-07-13 | 8 | PASS | 8/8 systems; absent: none |
| proj_rowcount_delta_7d | rh3 | 0.0109 | PASS | 458 rows @ 2026-07-06 -> 463 rows @ 2026-07-13 |
| proj_rowcount_delta_7d | rp3 | 0.0233 | PASS | 343 rows @ 2026-07-06 -> 351 rows @ 2026-07-13 |
| proj_rowcount_delta_7d | rprs2 | 0.0246 | PASS | 325 rows @ 2026-07-06 -> 333 rows @ 2026-07-13 |
| proj_volume_fill_rate | hitter | 1.0 | PASS | 463/463 rows @ 2026-07-13 (tail-rank players legitimately lack a volume row) |
| proj_volume_fill_rate | sp | 0.7493 | PASS | 263/351 rows @ 2026-07-13 (tail-rank players legitimately lack a volume row) |

## Forward accuracy

Honest baseline (2026-06-26 forward retro): rh3 ~0.35 / rp3 ~0.40 forward Spearman over 2-3 weeks. All metrics conditional on forward-volume floors (survivorship).

| metric | segment | value | status | note |
|---|---|---|---|---|
| window_7d | all | 7 | INFO | anchor=2026-07-06 fwd_days=7 |
| rh3_spearman_rate_7d | all | 0.0809 | INFO | anchor=2026-07-06 fwd_days=7 n=212 pa_floor=15 (survivorship: conditional on volume) |
| rh3_spearman_total_7d | all | 0.1476 | INFO | n=212 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_7d | all | 0.0838 | INFO | n=212 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_7d | T1_low | -0.0969 | INFO | n=71 MAE=0.315 |
| rh3_bias_7d | T2_mid | -0.0973 | INFO | n=70 MAE=0.321 |
| rh3_bias_7d | T3_high | -0.0436 | INFO | n=71 MAE=0.307 |
| rh3_spearman_rate_7d | C | -0.0556 | INFO | n=20 (position backfilled from latest snapshot) |
| rh3_spearman_rate_7d | non_C | 0.0631 | INFO | n=181 (position backfilled from latest snapshot) |
| rp3_spearman_rate_7d | all | 0.4695 | INFO | anchor=2026-07-06 fwd_days=7 n=33 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_7d | all | 0.4695 | INFO | n=33 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_7d | all | 0.1205 | INFO | n=33 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_7d | T1_low | 3.1359 | INFO | n=11 MAE=4.991 |
| rp3_bias_7d | T2_mid | -0.4419 | INFO | n=11 MAE=3.592 |
| rp3_bias_7d | T3_high | -0.4561 | INFO | n=11 MAE=6.514 |
| rp3_spearman_rate_7d | data_driven | 0.4695 | INFO | n=33 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_7d | all | 0.1815 | INFO | anchor=2026-07-06 fwd_days=7 n=101 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_7d | all | 0.1983 | INFO | n=101 vs fwd fp/appearance |
| window_14d | all | 14 | INFO | anchor=2026-06-29 fwd_days=14 |
| rh3_spearman_rate_14d | all | 0.1198 | INFO | anchor=2026-06-29 fwd_days=14 n=308 pa_floor=17 (survivorship: conditional on volume) |
| rh3_spearman_total_14d | all | 0.3692 | INFO | n=308 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_14d | all | 0.0585 | INFO | n=308 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_14d | T1_low | -0.1005 | INFO | n=103 MAE=0.269 |
| rh3_bias_14d | T2_mid | -0.0439 | INFO | n=102 MAE=0.236 |
| rh3_bias_14d | T3_high | -0.0241 | INFO | n=103 MAE=0.207 |
| rh3_spearman_rate_14d | C | -0.1535 | INFO | n=40 (position backfilled from latest snapshot) |
| rh3_spearman_rate_14d | non_C | 0.141 | INFO | n=252 (position backfilled from latest snapshot) |
| rp3_spearman_rate_14d | all | 0.2895 | INFO | anchor=2026-06-29 fwd_days=14 n=135 start_floor=2 (survivorship: conditional on volume) |
| rp3_spearman_total_14d | all | 0.2886 | INFO | n=135 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_14d | all | -0.0102 | INFO | n=135 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_14d | T1_low | 0.3864 | INFO | n=45 MAE=5.063 |
| rp3_bias_14d | T2_mid | -0.3283 | INFO | n=45 MAE=5.361 |
| rp3_bias_14d | T3_high | -0.0649 | INFO | n=45 MAE=5.296 |
| rp3_spearman_rate_14d | data_driven | 0.2981 | INFO | n=129 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_14d | marcel_il |  | INSUFFICIENT | n=6 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_14d | all | 0.2406 | INFO | anchor=2026-06-29 fwd_days=14 n=189 app_floor=3 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_14d | all | 0.2351 | INFO | n=189 vs fwd fp/appearance |
| window_21d | all | 21 | INFO | anchor=2026-06-22 fwd_days=21 |
| rh3_spearman_rate_21d | all | 0.1933 | INFO | anchor=2026-06-22 fwd_days=21 n=224 pa_floor=25 (survivorship: conditional on volume) |
| rh3_spearman_total_21d | all | 0.3791 | INFO | n=224 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_21d | all | 0.106 | INFO | n=224 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_21d | T1_low | -0.051 | INFO | n=75 MAE=0.192 |
| rh3_bias_21d | T2_mid | -0.0679 | INFO | n=74 MAE=0.172 |
| rh3_bias_21d | T3_high | 0.0306 | INFO | n=75 MAE=0.173 |
| rh3_spearman_rate_21d | C | 0.0474 | INFO | n=23 (position backfilled from latest snapshot) |
| rh3_spearman_rate_21d | non_C | 0.1703 | INFO | n=191 (position backfilled from latest snapshot) |
| rp3_spearman_rate_21d | all | 0.1911 | INFO | anchor=2026-06-22 fwd_days=21 n=76 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_21d | all | 0.1837 | INFO | n=76 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_21d | all | 0.0587 | INFO | n=76 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_21d | T1_low | -2.6245 | INFO | n=26 MAE=4.458 |
| rp3_bias_21d | T2_mid | -1.0201 | INFO | n=25 MAE=4.208 |
| rp3_bias_21d | T3_high | -0.3032 | INFO | n=25 MAE=4.198 |
| rp3_spearman_rate_21d | data_driven | 0.1983 | INFO | n=75 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_21d | marcel_il |  | INSUFFICIENT | n=1 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_21d | all | 0.2633 | INFO | anchor=2026-06-22 fwd_days=21 n=171 app_floor=5 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_21d | all | 0.2603 | INFO | n=171 vs fwd fp/appearance |
| window_28d | all | 28 | INFO | anchor=2026-06-15 fwd_days=28 |
| rh3_spearman_rate_28d | all | 0.1775 | INFO | anchor=2026-06-15 fwd_days=28 n=297 pa_floor=34 (survivorship: conditional on volume) |
| rh3_spearman_total_28d | all | 0.4042 | INFO | n=297 rate-model vs fwd TOTAL fp |
| rh3_vs_prior_delta_28d | all | 0.05 | INFO | n=297 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rh3_bias_28d | T1_low | -0.0813 | INFO | n=99 MAE=0.185 |
| rh3_bias_28d | T2_mid | -0.0732 | INFO | n=99 MAE=0.171 |
| rh3_bias_28d | T3_high | 0.0143 | INFO | n=99 MAE=0.139 |
| rh3_spearman_rate_28d | C | -0.0013 | INFO | n=36 (position backfilled from latest snapshot) |
| rh3_spearman_rate_28d | non_C | 0.1816 | INFO | n=252 (position backfilled from latest snapshot) |
| rp3_spearman_rate_28d | all | 0.3597 | INFO | anchor=2026-06-15 fwd_days=28 n=124 start_floor=4 (survivorship: conditional on volume) |
| rp3_spearman_total_28d | all | 0.3489 | INFO | n=124 rate-model vs fwd TOTAL fp |
| rp3_vs_prior_delta_28d | all | 0.0834 | INFO | n=124 spearman(model)-spearman(prior); >0 = in-season layer earning |
| rp3_bias_28d | T1_low | -0.853 | INFO | n=42 MAE=4.298 |
| rp3_bias_28d | T2_mid | -1.8744 | INFO | n=41 MAE=3.795 |
| rp3_bias_28d | T3_high | -0.209 | INFO | n=41 MAE=3.467 |
| rp3_spearman_rate_28d | data_driven | 0.3354 | INFO | n=119 (tag backfilled from latest snapshot — approx for old anchors) |
| rp3_spearman_rate_28d | marcel_il |  | INSUFFICIENT | n=5 (tag backfilled from latest snapshot — approx for old anchors) |
| rprs2_spearman_total_28d | all | 0.2724 | INFO | anchor=2026-06-15 fwd_days=28 n=166 app_floor=7 proj=RoS-total (rank-only; incl sv/hld) |
| rprs2_spearman_rate_28d | all | 0.2983 | INFO | n=166 vs fwd fp/appearance |
| vol_h_spearman_volD3 | model | 0.6094 | INSUFFICIENT | anchor=2026-07-10 fwd_days=3 n=319; naive(backward PA pace)=0.532 |
| vol_h_spearman_volD3 | naive | 0.532 | INSUFFICIENT | backward season PA-pace comparator |
| vol_h_edge_vs_naive_volD3 | all | 0.0774 | INSUFFICIENT | validated 2026-07-09 at +0.074 — watch for decay |
| vol_sp_spearman_volD3 | model | 0.6961 | INSUFFICIENT | anchor=2026-07-10 fwd_days=3 n=128 |
| vol_sp_spearman_volD3 | naive | 0.6369 | INSUFFICIENT | backward season GS-pace comparator |
| vol_sp_edge_vs_naive_volD3 | all | 0.0592 | INSUFFICIENT | validated 2026-07-09 at +0.100 — watch for decay |

_Generated by scripts/xfp/build_model_scorecard.py. History accumulates in data/research/model_scorecard_history.csv._
