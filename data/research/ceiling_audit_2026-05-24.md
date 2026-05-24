# xFP model accuracy-ceiling audit — 2026-05-24

Per-model empirical ceiling audit using the `plv_clone.models.xfp.ceiling` toolkit (added 2026-05-23). Three ceilings per model:

1. **NONLINEAR** — Ridge vs XGB vs RF on the same FEATS/target/cross-year split. Verdict thresholds: max(xgb_gap, rf_gap) < 0.003 → AT_CEILING; 0.003–0.010 → MILD_NONLINEARITY; > 0.010 → SIGNIFICANT_NONLINEARITY.
2. **LINEAR** — Ridge alpha sensitivity across a 13-point log-spaced grid (`logspace(-1, 5, 13)`). r_std measured over the "reasonable zone" (alphas within 0.05 of peak r). r_std < 0.005 → STABLE.
3. **FEATURE** — LassoCV over (baseline + candidates). Candidates = all numeric substrate cols not already in baseline, excluding circular ones (ros_*, *_after, fp_total_*, core_fp_per_pa, fp_per_start_*, etc.) and candidates with > 40% NaN in training. Up to 50 candidates retained.

## rh3

- substrate rows: **8322** | baseline feats: **20** | candidates considered: **50**

### Nonlinear ceiling

- ridge_r: `+0.6167`
- xgb_r:   `+0.6167` (gap `+0.0000`)
- rf_r:    `+0.5830` (gap `-0.0337`)
- **verdict:** `AT_CEILING`

### Linear ceiling (alpha sensitivity)

- alpha_chosen: `316.2278`
- r_at_chosen:  `+0.6167`
- r_std (reasonable zone): `0.0083`
- **verdict:** `ALPHA_SENSITIVE`

### Feature ceiling (LassoCV)

- baseline_r: `+0.6167`
- extended_r: `+0.6223` (delta `+0.0056`)
- baseline feats zeroed: **16** / 20
  - zeroed baseline feats: barrel_pct_to_sh, bb_pct_to_sh, career_stage, chase_pct_to_sh, contact_pct_to_sh, hard_hit_pct_to_sh, hr_per_pa_to_sh, in_play_pct_to_sh, k_pct_to_sh, pa_to, prior_pa_eff, sb_per_pa_to_sh, split_day, swstr_pct_to_sh, whiff_pct_to_sh, xwoba_per_pa_to_sh
- new candidates kept: **7**
  - kept: bip_to, contact_last21, contact_to, hard_hit_n_last21, hr_to, in_zone_last21, in_zone_to
- **verdict:** `REPLACE_BASELINE`

## rp3

- substrate rows: **4240** | baseline feats: **23** | candidates considered: **50**

### Nonlinear ceiling

- ridge_r: `+0.5509`
- xgb_r:   `+0.5347` (gap `-0.0162`)
- rf_r:    `+0.5339` (gap `-0.0170`)
- **verdict:** `AT_CEILING`

### Linear ceiling (alpha sensitivity)

- alpha_chosen: `1000.0000`
- r_at_chosen:  `+0.5516`
- r_std (reasonable zone): `0.0093`
- **verdict:** `ALPHA_SENSITIVE`

### Feature ceiling (LassoCV)

- baseline_r: `+0.5509`
- extended_r: `+0.5624` (delta `+0.0115`)
- baseline feats zeroed: **8** / 23
  - zeroed baseline feats: avg_velo_to, c_plus_swstr_to_sh, days_since_il_return_imp, delta_bb_pct, il_stints_to, is_on_il_at_split, o_swing_pct_to_sh, split_day
- new candidates kept: **11**
  - kept: avg_pfxz_to, avg_velo_last21, bb_pct_last21, bb_to, c_plus_swstr_last21, contact_last21, contact_to, gs_last21, hbp_to, hr_to, swing_last21
- **verdict:** `REPLACE_BASELINE`

## rprs2

- substrate rows: **9871** | baseline feats: **28** | candidates considered: **31**

### Nonlinear ceiling

- ridge_r: `+0.8419`
- xgb_r:   `+0.8346` (gap `-0.0073`)
- rf_r:    `+0.8134` (gap `-0.0285`)
- **verdict:** `AT_CEILING`

### Linear ceiling (alpha sensitivity)

- alpha_chosen: `3.1623`
- r_at_chosen:  `+0.8419`
- r_std (reasonable zone): `0.0144`
- **verdict:** `ALPHA_SENSITIVE`

### Feature ceiling (LassoCV)

- baseline_r: `+0.8419`
- extended_r: `+0.8424` (delta `+0.0005`)
- baseline feats zeroed: **12** / 28
  - zeroed baseline feats: bb_pct_to, c_plus_swstr_to, fp_per_g_lag1, g_lag1, hld_per_g_lag1, ip_lag1, ip_to, o_swing_pct_to, role_closer_lag1, role_middle_lag1, sv_plus_hld_to, swstr_pct_to
- new candidates kept: **7**
  - kept: bip_to, swstr_to, h_to, er_to, hld_to, ip_in_app_total, is_team_prior_closer
- **verdict:** `BASELINE_OPTIMAL`

## Headline summary

| model | ridge_r | xgb_gap | rf_gap | alpha r_std | feat delta | nonlinear | linear | feature |
|---|---|---|---|---|---|---|---|---|
| rh3 | +0.6167 | +0.0000 | -0.0337 | 0.0083 | +0.0056 | AT_CEILING | ALPHA_SENSITIVE | REPLACE_BASELINE |
| rp3 | +0.5509 | -0.0162 | -0.0170 | 0.0093 | +0.0115 | AT_CEILING | ALPHA_SENSITIVE | REPLACE_BASELINE |
| rprs2 | +0.8419 | -0.0073 | -0.0285 | 0.0144 | +0.0005 | AT_CEILING | ALPHA_SENSITIVE | BASELINE_OPTIMAL |

