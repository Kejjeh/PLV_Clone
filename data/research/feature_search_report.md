# xFP V7 Feature Search — 2026-05-04T23:28:46.747383

## Phase 0: Baseline (V6)

- V6 OOY r:        0.86487
- V6 cross-year r: 0.55789
- OOY-cross gap:   0.3070
- High-K bias:     OOY=-0.147  cross=1.014
- 2026 YTD r:      0.34738 (n=91)

## Phase 1: CV screening

- barrel_pct: CV r=0.86691 Δ=+0.00363
- bb_pct: CV r=0.86634 Δ=+0.00306
- k_bb_proxy: CV r=0.86629 Δ=+0.00301
- hard_hit_pct: CV r=0.86418 Δ=+0.00090
- hard_hit_neg: CV r=0.86418 Δ=+0.00090
- xwoba_x_cplus: CV r=0.86402 Δ=+0.00074
- swstr_sq: CV r=0.86373 Δ=+0.00045
- avg_ev: CV r=0.86357 Δ=+0.00029
- swing_pct: CV r=0.86353 Δ=+0.00025
- abs_pfxz_x_velo: CV r=0.86338 Δ=+0.00010
- xwoba_nc_pa: CV r=0.86327 Δ=-0.00001
- cplus_sq: CV r=0.86326 Δ=-0.00002
- velo_x_swstr: CV r=0.86325 Δ=-0.00003
- o_swing_x_swstr: CV r=0.86324 Δ=-0.00004
- velo_x_cplus: CV r=0.86318 Δ=-0.00010
- log_swstr: CV r=0.86316 Δ=-0.00012
- log_cplus: CV r=0.86316 Δ=-0.00012
- zone_x_oswing: CV r=0.86315 Δ=-0.00013
- contact_pct: CV r=0.86303 Δ=-0.00025
- z_contact_pct: CV r=0.86285 Δ=-0.00043
- avg_pfxx: CV r=0.86281 Δ=-0.00047
- gb_pct: CV r=0.86281 Δ=-0.00047
- xwoba_per_pa: CV r=0.86240 Δ=-0.00088
- bip_pct: CV r=0.86231 Δ=-0.00097

**Winners forwarded:** ['barrel_pct', 'bb_pct', 'k_bb_proxy', 'hard_hit_pct', 'hard_hit_neg', 'xwoba_x_cplus']

## Phase 2: Dual validation

- xwoba_x_cplus: OOY=0.86598 cross=0.5577 gap=0.3083
- hard_hit_pct: OOY=0.86589 cross=0.55607 gap=0.3098
- hard_hit_neg: OOY=0.86589 cross=0.55607 gap=0.3098
- barrel_pct: OOY=0.86792 cross=0.55443 gap=0.3135
- bb_pct: OOY=0.86643 cross=0.5506 gap=0.3158
- k_bb_proxy: OOY=0.8666 cross=0.55012 gap=0.3165

**Winners forwarded:** []

## Phase 3: Replacements

- xwoba→xwoba_nc_pa: OOY=0.86497 cross=0.55765
- xwoba→xwoba_per_pa: OOY=0.85769 cross=0.5639
- xwoba→xwoba_x_cplus: OOY=0.86164 cross=0.55343

## Phase 4: Backward elimination

- n=11 cross=0.55789 dropped=zone_pct
- n=10 cross=0.55224 dropped=abs_pfxz
- n=9 cross=0.55216 dropped=avg_ext
- n=8 cross=0.54232 dropped=ip_resid_lag1
- n=7 cross=0.55969 dropped=xwoba_x_swstr
- n=6 cross=0.55973 dropped=avg_velo
- n=5 cross=0.55274 dropped=o_swing_pct

**Best:** ['avg_velo', 'o_swing_pct', 'swstr_pct', 'c_plus_swstr', 'xwoba_contact', 'z_swing_pct'] (cross=0.55973)

## Phase 5: Nonlinear ceiling

- xgb on V6: OOY=0.84530 cross=0.52434
- xgb on best_set: OOY=0.81396 cross=0.54847
- rf on V6: OOY=0.84523 cross=0.54622
- rf on best_set: OOY=0.81356 cross=0.55919
- gbm on V6: OOY=0.83877 cross=0.52433
- gbm on best_set: OOY=0.80623 cross=0.54529

**Gap:** -0.0094
**Decision:** Ridge optimal — proceed with Ridge V7

## Phase 6: Follow-on (SHAP / poly / stacking)

- nonlin_gap = -0.0094
- poly_winners tested: []
- best_cross now: 0.55973
- best_set now: ['avg_velo', 'o_swing_pct', 'swstr_pct', 'c_plus_swstr', 'xwoba_contact', 'z_swing_pct']

## Phase 7: Fresh statcast

- Not needed: nonlinear gap < 0.005

## Phase 8: Tenure features

- n_seasons [CLEAN] OOY=0.86271 cross=0.55972
- ip_resid_career [CLEAN] OOY=0.86461 cross=0.55711
- fp_career_mean_lag [SEMI-CIRCULAR] OOY=0.86551 cross=0.56243
- fp_lag1 [SEMI-CIRCULAR] OOY=0.86554 cross=0.56287
- pitcher_career_rank [SEMI-CIRCULAR] OOY=0.87591 cross=0.54514

## Phase 9: V7 lock

- selection: best_set
- features (6): ['avg_velo', 'o_swing_pct', 'swstr_pct', 'c_plus_swstr', 'xwoba_contact', 'z_swing_pct']
- cross-year r: 0.55973
- high-K bias: 1.183
- coefs:
  - xwoba_contact: -2.214
  - c_plus_swstr: +1.234
  - swstr_pct: -0.496
  - z_swing_pct: +0.447
  - o_swing_pct: +0.267
  - avg_velo: +0.218

## Phase 11.0: Baselines (NEW scoring)

- V6:                cross=0.55789 kbias=1.014 **score=1.16667**
- V7:                cross=0.55973 kbias=1.183 **score=1.08769**
- V6[xwoba_per_pa]:  cross=0.5639 kbias=0.89 **score=1.2467**
- V8_BASE (V6 ints + xwoba_per_pa): cross=0.5639 kbias=0.89 **score=1.2467**

## Phase 11E: Backward elimination

- n=19 cross=0.57731 kbias=0.91 score=1.27693 dropped=breaking_spin
- n=18 cross=0.56126 kbias=0.791 score=1.28828 dropped=FF_spin
- n=17 cross=0.56092 kbias=0.795 score=1.28526 dropped=offspeed_spin
- n=16 cross=0.55849 kbias=0.789 score=1.28097 dropped=velo_diff
- n=15 cross=0.57398 kbias=0.728 score=1.35794 dropped=bb_pct_lag1
- n=14 cross=0.57525 kbias=0.766 score=1.34275 dropped=abs_pfxz
- n=13 cross=0.57677 kbias=0.777 score=1.34181 dropped=pitch_entropy
- n=12 cross=0.57357 kbias=0.812 score=1.31471 dropped=ip_resid_lag1
- n=11 cross=0.57342 kbias=0.813 score=1.31376 dropped=zone_pct
- n=10 cross=0.56246 kbias=0.847 score=1.26388 dropped=vaa_ff
- n=9 cross=0.56291 kbias=0.924 score=1.22673 dropped=k_pct_lag1
- n=8 cross=0.57181 kbias=0.957 score=1.23693 dropped=avg_ext
- n=7 cross=0.57111 kbias=1.002 score=1.21233 dropped=avg_velo
- n=6 cross=0.56641 kbias=1.018 score=1.19023 dropped=o_swing_pct
- n=5 cross=0.56871 kbias=0.91 score=1.25113 dropped=z_swing_pct
- n=4 cross=0.57235 kbias=0.765 score=1.33455 dropped=xwoba_per_pa

**Best BE set:** ['avg_velo', 'abs_pfxz', 'avg_ext', 'zone_pct', 'o_swing_pct', 'swstr_pct', 'c_plus_swstr', 'xwoba_per_pa', 'z_swing_pct', 'xwoba_x_swstr', 'ip_resid_lag1', 'k_pct_lag1', 'bb_pct_lag1', 'vaa_ff', 'pitch_entropy'] score=1.35794

## Phase 11.5: V8 lock

- selection: BE_best
- features (15): ['avg_velo', 'abs_pfxz', 'avg_ext', 'zone_pct', 'o_swing_pct', 'swstr_pct', 'c_plus_swstr', 'xwoba_per_pa', 'z_swing_pct', 'xwoba_x_swstr', 'ip_resid_lag1', 'k_pct_lag1', 'bb_pct_lag1', 'vaa_ff', 'pitch_entropy']
- score: 1.35794
- cross-year r: 0.57398
- k_bias_hi: 0.728
- coefs:
  - xwoba_per_pa: -1.521
  - c_plus_swstr: +1.288
  - xwoba_x_swstr: -1.275
  - o_swing_pct: +0.611
  - z_swing_pct: +0.552
  - swstr_pct: +0.455
  - avg_velo: +0.341
  - k_pct_lag1: +0.263
  - avg_ext: +0.218
  - vaa_ff: -0.215
  - zone_pct: +0.204
  - ip_resid_lag1: +0.161
  - pitch_entropy: +0.137
  - abs_pfxz: +0.061
  - bb_pct_lag1: -0.025

## Phase 11.0: Baselines (NEW scoring)

- V6:                cross=0.567 kbias=0.746 **score=1.328**
- V7:                cross=0.54881 kbias=1.075 **score=1.10893**
- V6[xwoba_per_pa]:  cross=0.57738 kbias=0.512 **score=1.47614**
- V8_BASE (V6 ints + xwoba_per_pa): cross=0.57738 kbias=0.512 **score=1.47614**

## Phase 11E: Backward elimination

- n=19 cross=0.58737 kbias=0.483 score=1.52061 dropped=FF_spin
- n=18 cross=0.58754 kbias=0.486 score=1.51962 dropped=bb_pct_lag1
- n=17 cross=0.58763 kbias=0.491 score=1.51739 dropped=avg_ext
- n=16 cross=0.58735 kbias=0.494 score=1.51505 dropped=offspeed_spin
- n=15 cross=0.58733 kbias=0.509 score=1.50749 dropped=breaking_spin
- n=14 cross=0.57452 kbias=0.477 score=1.48506 dropped=velo_diff
- n=13 cross=0.58115 kbias=0.455 score=1.51595 dropped=abs_pfxz
- n=12 cross=0.58163 kbias=0.447 score=1.52139 dropped=vaa_ff
- n=11 cross=0.58257 kbias=0.455 score=1.52021 dropped=pitch_entropy
- n=10 cross=0.58146 kbias=0.47 score=1.50938 dropped=avg_velo
- n=9 cross=0.57964 kbias=0.462 score=1.50792 dropped=k_pct_lag1
- n=8 cross=0.57507 kbias=0.519 score=1.46571 dropped=zone_pct
- n=7 cross=0.57211 kbias=0.524 score=1.45433 dropped=ip_resid_lag1
- n=6 cross=0.55384 kbias=0.603 score=1.36002 dropped=z_swing_pct
- n=5 cross=0.55676 kbias=0.479 score=1.43078 dropped=o_swing_pct
- n=4 cross=0.55839 kbias=0.241 score=1.55467 dropped=xwoba_per_pa

**Best BE set:** ['swstr_pct', 'c_plus_swstr', 'xwoba_per_pa', 'xwoba_x_swstr'] score=1.55467

## Phase 11.5: V8 lock

- selection: BE_best
- features (4): ['swstr_pct', 'c_plus_swstr', 'xwoba_per_pa', 'xwoba_x_swstr']
- score: 1.55467
- cross-year r: 0.55839
- k_bias_hi: 0.241
- coefs:
  - swstr_pct: +4.188
  - xwoba_x_swstr: -3.259
  - c_plus_swstr: +0.625
  - xwoba_per_pa: -0.491
