# xFP model accuracy-ceiling audit — 2026-07-29

Models covered by THIS run: **rh3, rp3**. Substrate built through the shared canonical assembly (`plv_clone.models.xfp.frames`) — the same code `rh3.main()` runs.

Per-model empirical ceiling audit using the `plv_clone.models.xfp.ceiling` toolkit (added 2026-05-23). Three ceilings per model:

1. **NONLINEAR** — Ridge vs XGB vs RF on the same FEATS/target/cross-year split. Verdict thresholds: max(xgb_gap, rf_gap) < 0.003 → AT_CEILING; 0.003–0.010 → MILD_NONLINEARITY; > 0.010 → SIGNIFICANT_NONLINEARITY.
2. **LINEAR** — Ridge alpha sensitivity across a 13-point log-spaced grid (`logspace(-1, 5, 13)`). r_std measured over the "reasonable zone" (alphas within 0.05 of peak r). r_std < 0.005 → STABLE.
3. **FEATURE** — LassoCV over (baseline + candidates). Candidates = all numeric substrate cols not already in baseline, excluding circular ones (ros_*, *_after, fp_total_*, core_fp_per_pa, fp_per_start_*, etc.) and candidates with > 40% NaN in training. Up to 50 candidates retained.

## rh3

- substrate rows: **38758** | baseline feats: **22** | candidates considered: **50**

### Nonlinear ceiling

- ridge_r: `+0.6419`
- xgb_r:   `+0.6336` (gap `-0.0084`)
- rf_r:    `+0.5603` (gap `-0.0817`)
- **verdict:** `AT_CEILING`

### Linear ceiling (alpha sensitivity)

- alpha_chosen: `3162.2777`
- r_at_chosen:  `+0.6421`
- r_std (reasonable zone): `0.0056`
- **verdict:** `ALPHA_SENSITIVE`

### Feature ceiling (LassoCV)

- baseline_r: `+0.6419`
- extended_r: `+0.6457` (delta `+0.0038`)
- baseline feats zeroed: **13** / 22
  - zeroed baseline feats: barrel_pct_to_sh, bb_pct_to_sh, career_stage, chase_pct_to_sh, hard_hit_pct_to_sh, hr_per_pa_to_sh, in_play_pct_to_sh, pa_to, prior_fp_per_pa, prior_pa_eff, split_day, swstr_pct_to_sh, whiff_pct_to_sh
- new candidates kept: **1**
  - kept: hr_to
- **verdict:** `BASELINE_OPTIMAL`

## rp3

- substrate rows: **20400** | baseline feats: **24** | candidates considered: **50**

### Nonlinear ceiling

- ridge_r: `+0.5617`
- xgb_r:   `+0.5407` (gap `-0.0210`)
- rf_r:    `+0.5307` (gap `-0.0310`)
- **verdict:** `AT_CEILING`

### Linear ceiling (alpha sensitivity)

- alpha_chosen: `3162.2777`
- r_at_chosen:  `+0.5623`
- r_std (reasonable zone): `0.0027`
- **verdict:** `STABLE`

### Feature ceiling (LassoCV)

- baseline_r: `+0.5617`
- extended_r: `+0.5813` (delta `+0.0196`)
- baseline feats zeroed: **9** / 24
  - zeroed baseline feats: avg_velo_to, delta_bb_pct, delta_chase, delta_k_pct, delta_swstr, delta_velo, is_on_il_at_split, split_day, xwoba_per_pa_to_sh
- new candidates kept: **21**
  - kept: avg_pfxz_last21, avg_pfxz_to, avg_velo_last21, barrel_n_last21, bb_pct_last21, bb_pct_to, bb_to, bip_last21, called_strike_last21, contact_to, gb_n_last21, gs_last21, hard_hit_n_last21, hard_hit_n_to, hr_to, in_zone_last21, in_zone_to, o_swing_last21, o_swing_pct_to, out_zone_to, swing_last21
- **verdict:** `REPLACE_BASELINE`

## Headline summary

| model | ridge_r | xgb_gap | rf_gap | alpha r_std | feat delta | nonlinear | linear | feature |
|---|---|---|---|---|---|---|---|---|
| rh3 | +0.6419 | -0.0084 | -0.0817 | 0.0056 | +0.0038 | AT_CEILING | ALPHA_SENSITIVE | BASELINE_OPTIMAL |
| rp3 | +0.5617 | -0.0210 | -0.0310 | 0.0027 | +0.0196 | AT_CEILING | STABLE | REPLACE_BASELINE |

