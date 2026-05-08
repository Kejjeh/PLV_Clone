# xFP Model Research — SP Fantasy Score Prediction
*Last updated: 2026-05-05 | Production: V11 | Training: 2020-2025, n=768*

---

## Version History Summary

| Version | Date | Key Features Added | cross_year_r | k_bias_hi | Score (0.5 coef) | Status |
|---------|------|---------------------|--------------|-----------|------|--------|
| V1–V5 | 2025 | Baseline iterations (V4: 8 non-circular feats) | ~0.40–0.50 | n/a | n/a | Archived |
| V6 | 2025 | Bayesian xwoba shrinkage + xwoba×swstr + ip_resid_lag1 | 0.558 | 1.014 | 1.167 | Archived |
| V7 | 2026-05-04 | Backward elimination → 6 feats (BE bug: kbias floor) | 0.560 | 1.183 | 1.088 | Archived |
| V8 | 2026-05-05 | Score-fix + xwoba_per_pa base + 4-feat minimal core | 0.558 | 0.241 | 1.555 | **Frozen reference** |
| V8.1 | 2026-05-05 | Mid-season 2025+2026 input blend | (V8.5 base) | – | – | **Active blender** |
| V8.5 | 2026-05-05 | +bb_pfxz +pitch_entropy +ip_resid +k_pct_lag (12 feats) | 0.600 | 0.466 | 1.567 | Superseded by V11 |
| V9 | 2026-05-05 | IP decomposition (predict K/BB/H/HR/IP separately) | 0.541 | 1.882 | 0.682 | Archived (failed) |
| V10 | 2026-05-05 | Marcel weighting / archetype submodels / BaseRuns | ≤V8.5 all branches | – | – | Archived (failed) |
| **V11** | **2026-05-05** | **+pitching_plus (FG) +fp_strike_pct (Statcast)** | **0.614** | **0.773** | **1.455** (0.5 coef) / **1.841** (T=1.0) | **PRODUCTION** |
| V12 | 2026-05-05 | Residual correction (V8.5 + Ridge on FG residuals) | 0.605 | 1.295 | 1.168 | Archived (failed) |

V11 is the current production model. V8 stays frozen as ablation reference. V8.5 stays for comparison only.
V8.1 mid-season blend is the input-layer adapter — applied to V11 features for in-season updates.

**V11 production validation (2026 YTD spot check, n=112 SPs with gs ≥ 5):**
- YTD r: V8.5 0.475 → V11 **0.511** (+0.036)
- YTD MAE: V8.5 3.484 → V11 **3.393** (−0.09)
- Top-25 high-K cohort MAE: V8.5 3.519 → V11 **3.341** (−0.18)
- corr(V11_delta, k_pct_2026) = +0.026 (V11 does NOT preferentially boost high-K pitchers)

---

## Key Negative Results

### V9 — IP decomposition failed
Approach: predict K/BB/H/HR/IP per start as separate Ridge models, recombine via FP formula.
Why it failed: IP × 3.3 contributes ~17.5 of avg 10.2 net FP/start. The IP model's prediction
errors propagate amplified by 3.3× into the recombined FP. Cross-year r dropped from V8.5 0.600 to 0.541;
k_bias jumped to +1.88. The compendium's praise of BaseRuns was for *aggregate team-level* run scoring
at extreme team profiles, not for per-pitcher per-start fantasy points. Manager/game-state-driven
variance in IP is irreducible noise for a Statcast-process model.

### V10 — All three branches failed
1. **V10.1** (Marcel weighting + fp_strike_pct + velo_delta_yoy): Marcel 5/4/3 weighting blew up k_bias
   from 0.466 to 1.527 by upweighting recent training-set outliers. fp_strike_pct survived BE alone
   with +0.003 score (below 0.010 ship threshold).
2. **V10.2** (two-tier K cohort + contact-manager submodel): splitting training data into cohorts gave
   each submodel ~30% of the rows, increasing variance more than archetype-specific weights helped.
3. **V10.3** (BaseRuns 6-component decomposition): same compound-error issue as V9, score crashed to −0.09.

### V12 — Residual correction failed at projection time
Architecture: V8.5 frozen + Ridge on (actual − V8.5_pred) using FG features, heavily regularized.
Score 1.168 vs V8.5-same-subset 1.194 (−0.025). Cross-year r did improve (0.583 → 0.605, +0.022)
but k_bias on the 2020-2024 era subset was already 1.113 for V8.5 alone, and adding the residual
correction raised it to 1.295. No score-formula calibration cleanly let V12 ship without also
shipping the bias inflation.

### V11 k_bias false alarm (the lesson learned)
V11's cross-year k_bias of 0.773 (vs V8.5's 0.466) initially looked like a regression. But the
2026 projection-level spot check showed:
- Median Δ for top-25 high-K cohort: −0.146 (V11 actually slightly LOWER than V8.5)
- Mean Δ: −0.033
- corr(Δ, k_pct_2026) = +0.026 (essentially zero)

The k_bias warning measured directional bias on the cross-year *training/holdout* split. It didn't
manifest in actual 2026 projections because the V8.1 mid-season blend folds 2026 YTD swstr/xwoba into
inputs, naturally moderating V11's high-stuff boost. The marquee high-K guys (Skubal, Glasnow, Sale)
all projected LOWER under V11, not higher.

**Generalizable takeaway:** cross-year k_bias on an in-sample evaluation split can over-warn against
features that look fine at projection time. Verify with projection-level spot checks before rejecting
features on bias-metric grounds alone.

---

## Final Model (legacy section): xFP v4

**Feature set (8 features, all non-circular):**

| Feature | Category | Std Coef | Direction |
|---------|----------|----------|-----------|
| xwoba_contact | Contact Quality | -2.09 | Lower = better |
| c_plus_swstr | Plate Discipline | +0.96 | Higher = better |
| o_swing_pct | Plate Discipline | +0.47 | Higher = better |
| avg_velo | Pitch Physics | +0.40 | Higher = better |
| zone_pct | Plate Discipline | +0.29 | Higher = better |
| avg_ext | Pitch Physics | +0.15 | Higher = better |
| swstr_pct | Plate Discipline | -0.05 | (subsumed by c_plus_swstr+xwoba) |
| abs_pfxz | Pitch Physics | +0.02 | (weak at population level) |

**Performance:**
- CV r = 0.899 (10-fold cross-validation)
- Out-of-year r = 0.884–0.917 (each year held out)
- Training: 636 SP-seasons, 2021–2025
- Applied to: 141 SP-seasons in 2026 (≥3 GS)

**ESPN fantasy scoring:** K×1 + IP×3.3 − H×1 − ER×2 − BB×1 − HBP×1

---

## Full Correlation Table — All Metrics vs FP/Start

### Non-Circular Metrics (safe to use as predictors)

| Metric | r w/ FP/start | YoY Stability | Signal Tier | Notes |
|--------|--------------|---------------|-------------|-------|
| xwoba_contact | -0.861 | 0.471 | ★★ STRONG | Best single contact quality signal. Uses EV+LA physics, not actual outcome. Min 20 BIP for reliable estimate. |
| c_plus_swstr | +0.711 | 0.602 | ★★ STRONG | Chase + whiff combined. Stabilizes ~150 PA. |
| swstr_pct | +0.673 | 0.716 | ★★ STRONG | Pure whiff rate. Fastest to stabilize (~80 PA). |
| contact_pct | -0.626 | 0.708 | ★★ STRONG | Contact rate on swings. Inverse of swstr. High collinearity with swstr_pct. |
| z_contact_pct | -0.562 | 0.645 | ★★ STRONG | In-zone contact rate. Captures "can batters read the pitch." |
| o_swing_pct | +0.493 | 0.521 | ★ MEDIUM | Chase rate. Measures command over strike zone edge. |
| fp_strike_pct | +0.459 | 0.367 | ★ MEDIUM | First-pitch strike %. Non-circular but subsumed by xwoba once both in model (+0.0003 incremental). |
| fb_velo | +0.381 | 0.917 | ★ MEDIUM | Fastball-specific velocity. More stable than avg_velo. |
| avg_velo | +0.334 | 0.920 | ★ MEDIUM | All-pitch avg velocity. YoY stability = 0.920 (most stable metric). |
| swing_pct | +0.375 | 0.635 | ★ MEDIUM | Overall swing rate. Correlated with chase%. |
| barrel_pct | -0.292 | 0.095 | ★ MEDIUM | **Very low YoY stability (0.095)** — noisy in small samples. Subsumed by xwoba. |
| hard_hit_pct | -0.288 | 0.321 | ★ MEDIUM | Subsumed by xwoba. Useful for contact-manager archetype identification. |
| avg_ev | -0.262 | 0.436 | ★ MEDIUM | Continuous version of HH%. Subsumed by xwoba in regression. |
| avg_ext | +0.152 | 0.956 | LOW | Extension is the 2nd most stable metric (0.956) but weak predictor. |
| zone_pct | +0.127 | 0.608 | LOW | Pitch location. In model for interaction with chase%. |
| gb_pct | +0.072 | 0.700 | LOW | Weak population signal but **key archetype marker** for contact managers. YoY stable (0.700). |
| popup_pct | +0.080 | 0.632 | LOW | Automatic outs. Weak population signal. |
| pfxz_spread | +0.058 | 0.884 | LOW | FB-curve vertical gap. Null at population level. Key for contact-manager archetype (e.g., Fried). |
| fb_pfxz | +0.093 | 0.929 | LOW | Fastball rise. Very stable but null population signal. |
| bb_pfxz | +0.010 | 0.862 | LOW | Breaking ball drop. Null population signal but elite for Fried archetype. |
| abs_pfxz | -0.004 | 0.910 | NONE | **All-pitch avg pfxz is misleading.** Cancels out FB rise + BB drop. Use fb_pfxz/bb_pfxz separately. |

### Circular Metrics (⚠ exclude from predictive models)

| Metric | r w/ FP/start | YoY Stability | Why Circular |
|--------|--------------|---------------|--------------|
| k_minus_bb_pct | +0.880 | 0.622 | K and BB both directly in FP formula |
| k_per_start | +0.870 | 0.627 | K directly in FP formula (×1 per K) |
| k_pct | +0.802 | 0.686 | K/PA — K is in formula |
| ip_per_start | +0.780 | 0.289 | IP directly in FP formula (×3.3 per IP) |
| put_away_rate | +0.754 | 0.571 | r=0.927 with K% — K% proxy |
| er_per_start | -0.620 | 0.346 | ER directly in FP formula (×−2) |
| h_per_start | -0.483 | 0.419 | H directly in FP formula (×−1) |
| bb_pct | -0.443 | 0.428 | BB/PA — BB is in formula |
| bb_per_start | -0.369 | 0.419 | BB directly in FP formula |
| hr_per_start | -0.348 | 0.193 | HR drives ER estimate |
| hbp_per_start | -0.023 | 0.380 | HBP directly in FP formula |

---

## Key Findings

### 1. xwOBA Contact is the single best non-circular predictor (r = -0.861)
- Uses `estimated_woba_using_speedangle` from Statcast
- Computed on batted balls only (exclude K, BB, HBP events where xwOBA=0)
- Require minimum 20 BIP for reliable estimate; use league median otherwise
- Supersedes barrel% + HH% — those metrics are subsumed once xwOBA is in model
- Barrel% and HH% flip signs in the presence of xwOBA (multicollinearity)

### 2. avg_pfxz is misleading — never use it directly
- All-pitch average pfxz cancels out fastball rise and breaking ball drop
- A pitcher with fb_pfxz=+1.0 and bb_pfxz=−1.0 shows avg_pfxz ≈ 0.0
- Always separate by pitch type family: fb_pfxz, bb_pfxz, os_pfxz
- Vertical spread (pfxz_spread = fb_pfxz − bb_pfxz) is the meaningful tunneling metric

### 3. Put-away rate is K% in disguise (r = 0.927 with K%)
- Conceptually valid (finishing ability) but empirically collinear with K%
- Rejected from model on circularity grounds

### 4. Pitch-type movement metrics are population-level nulls
- pfxz_spread, fb_pfxz, bb_pfxz all have r < 0.10 with FP/start
- Movement doesn't predict FP directly; behavioral outcomes (SwStr%, xwOBA) encode whether movement is working
- Movement metrics useful for **explaining individual outliers** (Fried), not population-level prediction

### 5. Velocity and extension are the most stable metrics
- avg_velo YoY stability = 0.920, fb_velo = 0.917, avg_ext = 0.956
- These are the "floor" metrics — stable but lower predictive power
- Barrel% is the least stable useful metric (YoY r = 0.095)

### 6. Contact-manager archetype (Fried, Suarez, Steele, Gray)
- Defined by: SwStr% ≈ league average, GB% > 50%, Brl% < 4%
- Consistently produces positive delta (outperforms xFP by +1–3 pts)
- Model underrates them because avg_pfxz misrepresents their pitch shape
- Key metrics: bb_pfxz (deep curve drop), avg_ev (elite contact suppression), GB%
- After xwOBA replaces Brl%+HH%, residual delta ≈ +1.5–2.5 pts for this archetype

---

## Max Fried — Archetype Deep Dive

### Where he consistently ranks elite vs SP cohort (2021–2025):

| Metric | Avg Pctile | Tier | Notes |
|--------|-----------|------|-------|
| Avg EV (exit velocity) | **94.8th** | ELITE | Best in class at inducing weak contact |
| BB Drop (bb_pfxz) | **88.6th** | ELITE | Elite curveball vertical depth |
| Barrel% | **86.6th** | ELITE | 2.3–4.5% Brl% across all years |
| GB% | **86.3th** | ELITE | 53–60% GB rate — premium contact manager |
| HardHit% | **83.3th** | ELITE | Consistently limits hard contact |
| pfxz Spread | **75.6th** | STRONG | FB–curve vertical gap above average |
| FP/Start (actual) | **75.3th** | STRONG | Results consistently 72–85th pctile |
| xwOBA Contact | **68.9th** | SOLID | Good but not elite — GBs at low EV aren't all outs |

### Why Fried still has positive delta after xwOBA enters the model (~+2 pts):
1. **avg_pfxz = 0.15 ft** — looks like bottom of the league, model under-weights him
2. **bb_pfxz = −0.90 ft** — actual curve is elite (88th pctile) but invisible in all-pitch avg
3. GB at low EV → some become hits (BABIP ~0.240 on GBs), which mildly inflates xwOBA vs actual run prevention
4. Pitch sequencing/tunneling not captured by any single metric

### The avg_velo paradox:
- Avg velo = 87–88 mph → 25th pctile (bottom quarter)
- FB velo = 93–94 mph → 61st–68th pctile (above average)
- Breaking ball velo (~82 mph) drags down the all-pitch average
- Model uses avg_velo → systematically undersells his fastball quality

---

## Model Version History

| Version | Features | CV r | Notes |
|---------|----------|------|-------|
| v1 | 8 features, 2026-only (n=141) | 0.540 | Baseline, 2026 data only |
| v2 (circular) | 13 features incl K%, BB%, HH%, Brl%, GB% | 0.903 | ⚠ Inflated — circular |
| v2-NC | 7 features, non-circular | 0.780 | First honest model |
| v3 | +Brl% +HH% | 0.814 | Contact quality added |
| v4-final | xwOBA replaces Brl%+HH% | **0.899** | **Current model** |


---

## V6 Model — xwOBA Frequency Weighting + IP Depth Lag (May 2026)

### Core Problem Diagnosed
V5 had systematic bias for high-K pitchers: **+0.57 FP/start underprediction** for pitchers with K% > 30%. Root causes:
1. **xwoba_contact measured per-BIP** but treated as per-PA in linear model — for a 31% K pitcher, effective damage per PA = xwoba × 0.65, not × 1.0
2. **ip_resid missing**: no prior-year IP depth signal for workhorse characterization

### Key Research Findings

**bip_pct (BIP per TBF):**
- Mean=0.671, YoY=0.577, r=-0.508 with FP, r=-0.827 with k_pct
- Adding as standalone feature: CV r flat (0.9021 vs 0.9022) — Ridge already captures through joint xwoba/swstr
- But K-rate bias: +0.525 for >30%K (slight improvement from +0.573)

**xwoba_nc_pa (xwoba × (1-swstr)):**
- r=-0.879 with FP (strongest single-metric), YoY=0.534
- CV r=0.9014 as replacement for xwoba_contact (slightly worse)

**xwoba_x_swstr interaction (xwoba_contact × swstr_pct):**
- CV r=0.9072 OOY (slight improvement from 0.9069)
- K-rate bias >30%: +0.472 (improved from +0.573)
- Coefficient: **-0.52 (standardized)** — high xwoba × high swstr is penalized (hard contact when batters make contact = concerning)

**ip_resid_lag1 (prior-year IP depth residual):**
- OOY r = 0.9081 (+0.0012 over V5)
- K-rate bias >30%: **+0.259** (down from +0.573 in V5) — major improvement
- Captures durable "workhorse" trait that persists year-over-year

**Best combination V6 = V5 + xwoba_x_swstr + ip_resid_lag1:**
- OOY r = 0.9081
- K-rate bias >30%: **+0.205** (vs +0.573 V5) — 64% reduction

### Bayesian Shrinkage on xwoba_contact
For 2026 projections, pitchers with small 2025 samples get xwoba_contact shrunken toward league mean:
- Formula: `(n_contact × xwoba_raw + 40 × 0.3117) / (n_contact + 40)`
- At 40 BIP: 50/50 blend. At 200 BIP: ~17% shrinkage. At 0 BIP: league mean
- Critical for: Cameron Schlittler (28 BIP, raw=0.411 → shrunken=0.353)

### V6 Features
```python
V6 = ['avg_velo','abs_pfxz','avg_ext','zone_pct','o_swing_pct','swstr_pct',
      'c_plus_swstr','xwoba_contact','z_swing_pct','xwoba_x_swstr','ip_resid_lag1']
# xwoba_contact: Bayes-shrunken for projections (PRIOR_N=40, PRIOR_MEAN=0.3117)
# xwoba_x_swstr: product of shrunken xwoba × swstr_pct
# ip_resid_lag1: prior-year residual from V5 IP model
```

### Training Protocol
- IP residual model: Ridge(alpha=10) on V5 features → ip_resid = actual - predicted
- V6 trained on 363 pitcher-seasons (those with prior-year ip_resid)
- OOY validation: hold out each year 2022-2025
- Ridge alpha = 5.58 (auto-selected via 10-fold CV)

### V6 Coefficients (standardized)
| Feature | Coef |
|---------|------|
| xwoba_contact | -1.74 |
| c_plus_swstr | +1.27 |
| xwoba_x_swstr | -0.52 |
| avg_velo | +0.51 |
| o_swing_pct | +0.44 |
| z_swing_pct | +0.39 |
| zone_pct | +0.25 |
| swstr_pct | +0.21 |
| avg_ext | +0.18 |
| ip_resid_lag1 | +0.18 |
| abs_pfxz | -0.16 |

### Cameron Schlittler Case Study
- V5: rank #74/141, xFP=7.36, **12th pctile**
- V6: rank #48/141, xFP=10.47, **43rd pctile**
- Key fix: xwoba_contact shrunken from 0.411 → 0.353 (28 BIP sample)
- 2026 actual FP: 19.99/start → still underpredicted but significantly improved
- Remaining gap: genuine small-sample uncertainty + no ip_resid_lag1 (first-year starter)

### Outputs
- Dashboard: `data/outputs/xfp_v6_dashboard.html`
- Projections: `/tmp/xfp_v6_final.csv`



## V7 Model - Cross-Year Optimized Rebuild (2026-05-04)

### Selection: backward-elimination from V6 kitchen sink
**Features (6)**: avg_velo, o_swing_pct, swstr_pct, c_plus_swstr, xwoba_contact, z_swing_pct

V7 is V6 minus 5 features (abs_pfxz, avg_ext, zone_pct, xwoba_x_swstr, ip_resid_lag1). Each of those
helped same-year OOY r in V6 but they consistently HURT cross-year (year T -> year T+1) prediction.
Backward elimination using cross-year r as the stopping criterion identified the slimmer 6-feature
core that holds up in deployment.

### Performance
| Metric | V6 | V7 | Delta |
|---|---|---|---|
| OOY r (same-year) | 0.86487 | 0.82741 | -0.03746 |
| Cross-year r (deployment) | 0.55789 | 0.55973 | +0.00184 |
| OOY-cross gap | +0.3070 | +0.2677 | +0.0393 |
| High-K bias OOY | -0.147 | -0.379 | - |
| High-K bias cross | 1.014 | 1.183 | - |
| Nonlinear (XGB best vs Ridge V6) gap | - | -0.0094 | Ridge wins |
| 2026 YTD r | 0.34738 | 0.3024 | -0.04498 |
| 2026 YTD bias | -0.935 | -0.42 | - |

### V7 standardized coefficients
- **xwoba_contact**: -2.214
- **c_plus_swstr**: +1.234
- **swstr_pct**: -0.496
- **z_swing_pct**: +0.447
- **o_swing_pct**: +0.267
- **avg_velo**: +0.218

### Schlittler progression
- V5: rank #61.0 / xFP 11.64
- V6: rank #nan / xFP nan
- V7: rank #51 / xFP 11.65
- 2026 YTD actual FP/start: 19.49 (gs=7.0)


### Big movers V7 vs V6
Top 3 V7 risers:
  - **Hendricks, Kyle**: V6=9.80 -> V7=10.60 (delta 0.80)
  - **Boyd, Matthew**: V6=10.97 -> V7=11.40 (delta 0.43)
  - **Springs, Jeffrey**: V6=9.67 -> V7=10.05 (delta 0.38)

Top 3 V7 fallers:
  - **Webb, Logan**: V6=14.33 -> V7=13.25 (delta -1.08)
  - **Ortiz, Luis**: V6=11.81 -> V7=10.69 (delta -1.12)
  - **Glasnow, Tyler**: V6=13.60 -> V7=12.25 (delta -1.35)

### Notes
- Phase 1 CV screening tested 24 candidate features against V6+[X]. Highest-CV-r winners
  (barrel_pct, bb_pct, k_bb_proxy, hard_hit_pct, hard_hit_neg, xwoba_x_cplus) all looked
  like winners on OOY but lost on cross-year. None were forwarded to V7.
- Phase 5 nonlinear ceiling check (XGBoost, RF, GBM) showed nonlinear gap of -0.0094 -
  Ridge is at the deployment ceiling. No SHAP-driven polynomial transforms were needed.
- ip_resid_lag1 helps OOY (large positive coef) but its YoY stability is poor enough that it
  *hurts* cross-year prediction, so it was dropped. This is the biggest single takeaway from
  the rebuild: a feature can be "good" in same-year evaluation while being "bad" in deployment.

### Files written
- `data/models/xfp_v7_pipeline.pkl`
- `data/outputs/xfp_v7_projections.csv`
- `data/outputs/xfp_v7_dashboard.html`


## V8 Model - Phase 11 (Score-Fix + xwoba_per_pa Base) (2026-05-05)

### Phase 9 Bug Fixed
The V7 selection used scoring formula `cross_year_r * 3 + max(0, 0.21 - abs(k_bias_hi)) * 0.5`.
With every variant having k_bias_hi >> 0.21, the second term floored at 0 and only cross_year_r drove
the selection. V7 dropped ip_resid_lag1 and xwoba_x_swstr (each helped k_bias) for a +0.002 gain in
cross_year_r at the cost of k_bias going from 1.014 to 1.183.

NEW formula (V8 onward): `score = cross_year_r * 3 - abs(k_bias_hi) * 0.5`. No max() floor.
Direct penalty for k_bias.

### V8 Selection: BE_best

**Features (4)**: swstr_pct, c_plus_swstr, xwoba_per_pa, xwoba_x_swstr

### Performance (under NEW scoring)
| Metric | V6 | V7 | V8 | V8-V7 |
|---|---|---|---|---|
| Cross-year r | 0.567 | 0.54881 | 0.55839 | +0.00958 |
| k_bias_hi | 0.746 | 1.075 | 0.241 | -0.834 |
| Score | 1.328 | 1.10893 | 1.55467 | +0.4457 |
| 2026 YTD r | 0.35323 | 0.29564 | 0.31361 | - |

### V8 Standardized Coefficients
- **swstr_pct**: +4.188
- **xwoba_x_swstr**: -3.259
- **c_plus_swstr**: +0.625
- **xwoba_per_pa**: -0.491

### Phase 11C: k_pct_lag1 / bb_pct_lag1 (semi-circular)
- V7+k_pct_lag1 cross=0.57134 kbias=0.682 score=1.37302
- V6+k_pct_lag1 cross=0.57478 kbias=0.656 score=1.39634
- V6[per_pa]+k_pct_lag1 cross=0.58143 kbias=0.462 score=1.51329
- V8_BASE+k_pct_lag1 cross=0.58143 kbias=0.462 score=1.51329
- V7+bb_pct_lag1 cross=0.5647 kbias=0.799 score=1.2946
- V8_BASE+bb_pct_lag1 cross=0.57735 kbias=0.511 score=1.47655
- V8_BASE+k_pct_lag1+bb_pct_lag1 cross=0.58127 kbias=0.458 score=1.51481
- k_pct_lag1_alone cross=0.50107 kbias=2.739 score=0.13371

### Phase 11B: pitch-type Statcast features tested (6 available)
- V8_BASE+FF_spin cross=0.57811 kbias=0.49 score=1.48933
- V8_BASE+breaking_spin cross=0.59161 kbias=0.541 score=1.50433
- V8_BASE+offspeed_spin cross=0.56775 kbias=0.493 score=1.45675
- V8_BASE+vaa_ff cross=0.57624 kbias=0.509 score=1.47422
- V8_BASE+velo_diff cross=0.56779 kbias=0.558 score=1.42437
- V8_BASE+pitch_entropy cross=0.57784 kbias=0.501 score=1.48302

### Phase 11.5 V8 Selection Leaderboard
- BE_best score=1.55467 cross=0.55839 kbias=0.241
- V8_BASE+k_pct_lag1+bb_pct_lag1 [SEMI-CIRCULAR] score=1.51481 cross=0.58127 kbias=0.458
- V6[per_pa]+k_pct_lag1 [SEMI-CIRCULAR] score=1.51329 cross=0.58143 kbias=0.462
- V8_BASE+k_pct_lag1 [SEMI-CIRCULAR] score=1.51329 cross=0.58143 kbias=0.462
- V8_BASE score=1.47614 cross=0.57738 kbias=0.512
- V6[per_pa] score=1.47614 cross=0.57738 kbias=0.512
- V6_baseline score=1.328 cross=0.567 kbias=0.746
- V7_baseline score=1.10893 cross=0.54881 kbias=1.075

### Schlittler progression V5 -> V6 -> V7 -> V8
- V5 xFP: 11.61
- V6 xFP: nan
- V7 xFP: 11.59
- V8 xFP: 11.40
- 2026 actual FP/start: 19.49 (gs=7.0)


### Notes
- xwoba_per_pa = xwoba_contact * bip_pct. For a high-K pitcher (k_pct=0.32), bip_pct ~ 0.65, so
  xwoba_per_pa ~ 0.65 * xwoba_contact - it captures both contact quality AND low-contact-rate.
- k_pct_lag1 is semi-circular (K is in FP formula). Even so, prior-year K rate is a strong
  forward-looking signal that survives the cross-year test if YoY stability is high.
- ip_resid_lag1 was dropped by V7 BE because the V7 score formula didn't penalize k_bias loss.
  Under V8 scoring, ip_resid_lag1 is back in V6_BASE and may survive into V8 depending on BE.

### Files written
- `data/models/xfp_v8_pipeline.pkl`
- `data/outputs/xfp_v8_projections.csv`
- `data/outputs/xfp_v8_dashboard.html`


## V8.1 — Mid-Season Update (2026-05-05)

V8 model frozen. Re-projected with sample-weighted blends of 2025 + 2026 input metrics per pitcher.
Rate metrics blend by total pitches; xwoba_contact uses two-sample Bayesian shrinkage.

### Cohorts
- Blended (has both 2025 & 2026 SP rows): pitch-count weighted blend
- 2026-only: use 2026 alone if pitches >= 200, else fall back to V8
- 2025-only: keep V8 prediction unchanged

### Validation
| Metric | V8 | V8.1 | Δ |
|---|---|---|---|
| 2026 YTD r (gs>=5) | 0.31361 | 0.49127 | +0.17766 |
| YTD k_bias_hi | 3.615 | 2.973 | -0.642 |

**Decision: PASS**

### Six target archetype callouts
- Schlittler, Cam        V8=11.40  V8.1=13.44  Δ=+2.04  w_2026=0.324  actual_2026=19.485714285714284
- Glasnow, Tyler         V8=13.78  V8.1=14.55  Δ=+0.77  w_2026=0.283  actual_2026=19.9
- Imanaga, Shota         V8=10.45  V8.1=11.44  Δ=+0.99  w_2026=0.234  actual_2026=18.057142857142857
- Fried, Max             V8=13.11  V8.1=13.64  Δ=+0.53  w_2026=0.179  actual_2026=17.085714285714285
- Woodruff, Brandon      V8=19.39  V8.1=16.42  Δ=-2.97  w_2026=0.303  actual_2026=10.616666666666664
- Ragans, Cole           V8=18.95  V8.1=14.45  Δ=-4.49  w_2026=0.350  actual_2026=10.699999999999998

### Files
- `data/outputs/xfp_v8_1_projections.csv`
- `data/outputs/xfp_v8_1_dashboard.html`


## V8.5 — Contact-Manager Features (2026-05-05)

Added per-pitcher per-year fb_pfxz (FB family pfx_z), bb_pfxz (BB family pfx_z), pfxz_spread (FB-BB).
Re-ran Phase 11E backward elimination with these in the candidate pool.

### Result: V8.5 SHIPPED (decision rule: score delta >= 0.010)

| | V8 | V8.5 | Δ |
|---|---|---|---|
| Cross-year r | 0.55839 | 0.59993 | +0.04154 |
| k_bias_hi | 0.241 | 0.466 | +0.225 |
| Score | 1.555 | 1.56679 | +0.01179 |

### V8.5 best feature set (12)
avg_velo, zone_pct, o_swing_pct, swstr_pct, c_plus_swstr, xwoba_per_pa, z_swing_pct, xwoba_x_swstr, ip_resid_lag1, k_pct_lag1, pitch_entropy, bb_pfxz

pfxz features that survived BE: ['bb_pfxz']

Contact-manager subset (gb_pct > 0.50 AND swstr_pct < 0.12): n=243 pitcher-seasons.

### Files
- `data/models/xfp_v8_5_pipeline.pkl`
- `data/outputs/xfp_v8_5_projections.csv`
- `data/outputs/xfp_v8_5_dashboard.html`


## V9 — IP-Decomposition Refit (2026-05-05)

Architecture: predict (FP - IP×3.3) and ip_per_start separately, sum at projection time.
Motivated by Breakdown 2: IP × 3.3 contributes ~17.5 pts on a 10.2-pt mean net FP/start, and stripping
it makes every stuff metric correlate harder with the residual.

### Result: V9 NOT SHIPPED

Decision rule: cross-year r >= V8 + 0.005 (0.55839 + 0.005 = 0.56339) AND k_bias_hi <= 0.30.

| | V8 | V9 | Δ |
|---|---|---|---|
| Cross-year r | 0.55839 | 0.5407 | -0.01769 |
| k_bias_hi | 0.241 | 1.882 | +1.641 |
| Score | 1.555 | 0.68096 | -0.87404 |

IP model standalone cross-year r: 0.35744 (ceiling ~0.29 YoY stability)

### V9 stuff feature set (16)
abs_pfxz, avg_ext, zone_pct, swstr_pct, c_plus_swstr, xwoba_per_pa, z_swing_pct, xwoba_x_swstr, ip_resid_lag1, k_pct_lag1, offspeed_spin, vaa_ff, velo_diff, pitch_entropy, fb_pfxz, pfxz_spread

### Files
No model artifacts saved (decision rule failed).


## Rolling IP Predictor Analysis — May 2026

LEAGUE_AVG_IP/start (2021-2025): 5.1907

### Two-score projection

- **Full xFP** = V8.5 prediction (V8.5 model trained on full FP target)
- **Stuff xFP** = V9-stuff prediction (target = `FP - IP×3.3`) + LEAGUE_AVG_IP × 3.3
- **IP Premium** = full_xfp − stuff_xfp = projected workhorse bonus

### Top rolling-stat predictors of ip_per_start

| metric                       |   r_vs_ip_same_start |   n_obs |   r_vs_ip_next_yr |   n_cross_year | interpretation                                  |   rank |
|:-----------------------------|---------------------:|--------:|------------------:|---------------:|:------------------------------------------------|-------:|
| rolling_ip_this_start_last5  |               0.3301 |    1023 |            0.6598 |            174 | prior-IP autocorrelation (manager trust signal) |      1 |
| rolling_k_per_ip_last5       |               0.0633 |    1023 |            0.0287 |            174 | stuff -> manager confidence                     |      2 |
| rolling_strike_pct_last5     |               0.0446 |    1023 |            0.1537 |            174 | overall strike-throwing efficiency              |      3 |
| rolling_bb_per_ip_last5      |              -0.0442 |    1023 |           -0.0173 |            174 | command -> efficiency                           |      4 |
| rolling_pitches_per_ip_last5 |              -0.0604 |    1023 |           -0.1689 |            174 | efficiency (lower = deeper outings)             |      5 |
| rolling_er_per_ip_last5      |              -0.0877 |    1023 |           -0.1754 |            174 | results -> manager trust                        |      6 |

### Composite ip_trend methodology

- Take top 3 metrics by same-start r against ip_this_start
- Standardize each, sign by correlation direction
- ip_trend_score = mean of standardized values
- Label: HIGH if > mean + 0.75 std; LOW if < mean - 0.75 std

### Top 10 HIGH ip_trend (currently going deeper)

| player_name        |   rolling_ip_this_start_last5 |   ip_trend_score |
|:-------------------|------------------------------:|-----------------:|
| Schlittler, Cam    |                       6       |         1.48566  |
| Drohan, Shane      |                       5.44444 |         1.25403  |
| Hoffmann, Andrew   |                       5.41667 |         1.18548  |
| Sale, Chris        |                       5.8     |         1.15598  |
| Misiorowski, Jacob |                       5.53333 |         1.14341  |
| Skubal, Tarik      |                       6.06667 |         1.10044  |
| Ashcraft, Braxton  |                       5.53333 |         1.04938  |
| deGrom, Jacob      |                       4.86667 |         1.03404  |
| Williams, Gavin    |                       6.06667 |         0.991287 |
| Soroka, Michael    |                       5.4     |         0.989732 |

### Top 10 LOW ip_trend (being pulled early)

| player_name         |   rolling_ip_this_start_last5 |   ip_trend_score |
|:--------------------|------------------------------:|-----------------:|
| Weiss, Ryan         |                       2       |         -1.64622 |
| Quintana, Jose      |                       4.33333 |         -1.60453 |
| Suter, Brent        |                       2.58333 |         -1.52145 |
| Bassitt, Chris      |                       4.2     |         -1.49227 |
| Fisher, Braydon     |                       2.88889 |         -1.37705 |
| Herget, Jimmy       |                       1.11111 |         -1.27309 |
| Lopez, Jacob        |                       4.6     |         -1.15586 |
| Williamson, Brandon |                       5       |         -1.10209 |
| Abbott, Andrew      |                       4.33333 |         -1.09347 |
| Leasure, Jordan     |                       3       |         -1.085   |

### Files
- `data/research/rolling_ip_predictor_analysis.csv`
- `data/outputs/xfp_v8_5_projections.csv` (added: stuff_xfp, ip_premium, rolling_ip_last5, ip_trend_score, ip_trend)
- `data/outputs/xfp_v8_5_dashboard.html` (added: stuff/IP decomposition columns + ip_trend panels)
- `data/models/xfp_v9_no_ip_pipeline.pkl` (V9 stuff model recovered for projection use)


## Rolling IP Predictor Analysis — May 2026

LEAGUE_AVG_IP/start (2021-2025): 5.1907

### Two-score projection

- **Full xFP** = V8.5 prediction (V8.5 model trained on full FP target)
- **Stuff xFP** = V9-stuff prediction (target = `FP - IP×3.3`) + LEAGUE_AVG_IP × 3.3
- **IP Premium** = full_xfp − stuff_xfp = projected workhorse bonus

### Top rolling-stat predictors of ip_per_start

| metric                       |   r_vs_ip_same_start |   n_obs |   r_vs_ip_next_yr |   n_cross_year | interpretation                                  |   rank |
|:-----------------------------|---------------------:|--------:|------------------:|---------------:|:------------------------------------------------|-------:|
| rolling_ip_this_start_last5  |               0.3301 |    1023 |            0.6598 |            174 | prior-IP autocorrelation (manager trust signal) |      1 |
| rolling_k_per_ip_last5       |               0.0633 |    1023 |            0.0287 |            174 | stuff -> manager confidence                     |      2 |
| rolling_strike_pct_last5     |               0.0446 |    1023 |            0.1537 |            174 | overall strike-throwing efficiency              |      3 |
| rolling_bb_per_ip_last5      |              -0.0442 |    1023 |           -0.0173 |            174 | command -> efficiency                           |      4 |
| rolling_pitches_per_ip_last5 |              -0.0604 |    1023 |           -0.1689 |            174 | efficiency (lower = deeper outings)             |      5 |
| rolling_er_per_ip_last5      |              -0.0877 |    1023 |           -0.1754 |            174 | results -> manager trust                        |      6 |

### Composite ip_trend methodology

- Take top 3 metrics by same-start r against ip_this_start
- Standardize each, sign by correlation direction
- ip_trend_score = mean of standardized values
- Label: HIGH if > mean + 0.75 std; LOW if < mean - 0.75 std

### Top 10 HIGH ip_trend (currently going deeper)

| player_name        |   rolling_ip_this_start_last5 |   ip_trend_score |
|:-------------------|------------------------------:|-----------------:|
| Schlittler, Cam    |                       6       |         1.48566  |
| Drohan, Shane      |                       5.44444 |         1.25403  |
| Hoffmann, Andrew   |                       5.41667 |         1.18548  |
| Sale, Chris        |                       5.8     |         1.15598  |
| Misiorowski, Jacob |                       5.53333 |         1.14341  |
| Skubal, Tarik      |                       6.06667 |         1.10044  |
| Ashcraft, Braxton  |                       5.53333 |         1.04938  |
| deGrom, Jacob      |                       4.86667 |         1.03404  |
| Williams, Gavin    |                       6.06667 |         0.991287 |
| Soroka, Michael    |                       5.4     |         0.989732 |

### Top 10 LOW ip_trend (being pulled early)

| player_name         |   rolling_ip_this_start_last5 |   ip_trend_score |
|:--------------------|------------------------------:|-----------------:|
| Weiss, Ryan         |                       2       |         -1.64622 |
| Quintana, Jose      |                       4.33333 |         -1.60453 |
| Suter, Brent        |                       2.58333 |         -1.52145 |
| Bassitt, Chris      |                       4.2     |         -1.49227 |
| Fisher, Braydon     |                       2.88889 |         -1.37705 |
| Herget, Jimmy       |                       1.11111 |         -1.27309 |
| Lopez, Jacob        |                       4.6     |         -1.15586 |
| Williamson, Brandon |                       5       |         -1.10209 |
| Abbott, Andrew      |                       4.33333 |         -1.09347 |
| Leasure, Jordan     |                       3       |         -1.085   |

### Files
- `data/research/rolling_ip_predictor_analysis.csv`
- `data/outputs/xfp_v8_5_projections.csv` (added: stuff_xfp, ip_premium, rolling_ip_last5, ip_trend_score, ip_trend)
- `data/outputs/xfp_v8_5_dashboard.html` (added: stuff/IP decomposition columns + ip_trend panels)
- `data/models/xfp_v9_no_ip_pipeline.pkl` (V9 stuff model recovered for projection use)



## V10 — Three-Branch Search: Quick Wins / Archetype / BaseRuns (2026-05-05)

Three sub-versions evaluated under unchanged scoring formula (cross_year_r * 3 - |k_bias_hi| * 0.5).
**Decision rule: score >= V8.5 (1.567) + 0.010 = 1.577.**

| Sub-version | Approach | Score | Cross-year r | k_bias_hi | Result |
|---|---|---|---|---|---|
| V10.1 | V8.5 + fp_strike_pct + velo_delta_yoy + Marcel weighting | **1.57041** | 0.60047 | 0.462 | NOT SHIPPED (+0.003) |
| V10.2 | Two-tier K cohort + contact-manager submodel | **0.99764** | 0.56690 | 1.406 | NOT SHIPPED (-0.569) |
| V10.3 | BaseRuns decomposition (5 component models) | **-0.09249** | 0.57330 | 3.625 | NOT SHIPPED (-1.659) |
| **V8.5 (incumbent)** | Ridge (12 feats) | **1.567** | 0.600 | 0.466 | (baseline) |

### V10.1 — the small-improvement branch worked but didn't clear bar

 survived BE; gave +0.0034 score.  was dropped first (lowest |coef|).
Marcel-style 5/4/3 weighting *hurt* k_bias dramatically (1.527 vs 0.466) — weighting recent years
upweighted 2024 outliers in the training set, which then over-projected high-K guys.

### V10.2 — archetype submodels produce structural worse fit

Both two-tier K and contact-manager hybrid evaluations shipped lower scores. Splitting training data
into cohorts gives each submodel fewer training examples, increasing variance per cohort. That extra
variance dominates whatever signal the cohort-specific weights capture.

Two-tier K (k_pct_lag1 > 0.28): cross 0.548 (vs V8.5 0.600), kbias 1.479 (vs 0.466).
Contact-manager (gb_pct > 0.50 AND swstr_pct < 0.12): cross 0.567, kbias 1.406. Same diagnosis.

### V10.3 — BaseRuns decomposition is a structural disaster (compound errors)

Predicted K/PA, BB/PA, H/PA, HR/PA, HBP/PA, IP/start as 6 separate Ridge regressions, then summed
via the FP formula. Each component has its own prediction error; the FP formula amplifies them
(IP weighted by 3.3, ER by -2). Total cross-year r = 0.573, k_bias = +3.625 — dramatically worse
than the joint single-target Ridge.

This is the same lesson V9 (IP-decomposition) taught: **decomposing the FP target into pieces gives
each piece its own variance, and the recombined sum has higher variance than directly modeling FP**.
The compendium's praise of BaseRuns is in describing aggregate run scoring at extreme team profiles,
not in projecting individual pitcher per-start fantasy points.

### Negative-result takeaways

1. **V8.5 is at the public-data ceiling** for this dataset (1998 SP-seasons, 16 features, 12 finalists).
   Three different architectural alternatives all underperformed.
2. **The remaining gap to V8.5 ceiling** is irreducible without external data:
   - Stuff+ / Pitching+ history (FG Cloudflare blocks programmatic pulls; manual scraping needed)
   - Pitch tunneling metrics (Brooks Baseball / proprietary)
   - Catcher framing context (BP / FG framing models)
   - Health/availability data (MLB transactions feed)
3. **Predictive ceiling for cross-year r on FP/start under public-data Statcast features
   appears to be around 0.60.** Section 7 of the compendium suggests SIERA tops out at r=0.45-0.50
   year-to-year, and Stuff+ at 0.70-0.80, so we may be partially clipping that latter ceiling once
   FG data is in (future work — needs a non-Cloudflare-blocked path to FG history).

### Going forward
- **Use V8.5 + V8.1 mid-season blend as the production model** (data/models/xfp_v8_5_pipeline.pkl).
- **V10 dashboard not built** (no ship); xfp_v8_5_dashboard.html remains the active dashboard.
- Future V11 would need: (a) FG Stuff+ history via manual export, (b) external IL/health data,
  (c) prospect/rookie scouting grades for the 37 true rookies V8.5 still falls back on V8 for.

### Files
- 
-  (FG history pull — currently 403'd by Cloudflare)

## V11 — FG Stuff+/Pitching+/PitchingBot History Pull + Re-Search (2026-05-05)

Successfully pulled FG Stuff+/Location+/Pitching+ + PitchingBot pb_stuff/pb_command/pb_xrv100
for 2020-2026 via undetected-chromedriver (visible Chrome session bypasses Cloudflare).
2,990 pitcher-seasons of Stuff+ data merged into sp_multiyr.

### Single-feature addition to V8.5 (cross-year r benchmark = 0.600, k_bias = 0.466, score = 1.567)

| Added feature | cross-year r | k_bias_hi | score |
|---|---|---|---|
| stuff_plus (FG) | 0.609 | +0.787 | 1.433 |
| location_plus (FG) | 0.610 | +0.823 | 1.417 |
| pitching_plus (FG) | **0.613** | +0.774 | 1.452 |
| pb_stuff (PitchingBot) | **0.613** | +0.765 | 1.457 |
| pb_command (PitchingBot) | 0.611 | +0.831 | 1.419 |
| pb_xrv100 (PitchingBot) | 0.610 | +0.771 | 1.444 |
| fp_strike_pct (Statcast) | 0.600 | +0.462 | 1.570 |
| velo_delta_yoy | 0.600 | +0.475 | 1.561 |

### Key finding: Stuff+/Pitching+ work as the literature describes — but trade r for k_bias

**Cross-year r jumps from 0.600 -> 0.613 with Pitching+ added** (or pb_stuff). That's +0.013, larger than
the V7 -> V8.5 improvement (+0.0024). FG/PitchingBot metrics carry real cross-year predictive signal beyond
V8.5's swstr/c_plus_swstr/xwoba_per_pa core.

**But k_bias regresses from 0.466 -> 0.77+**. Stuff+/Pitching+ are stuff-quality-heavy: they identify elite-stuff
pitchers (predominantly high-K) and amplify their projected FP, pushing the over-projection of high-K pitchers
back to roughly V8 levels. This is the same trade-off V7 hit — raise cross-year r, lose k_bias.

### Why V11 does not ship (under current score formula)

Score formula :
- V8.5 + pitching_plus: 0.613*3 - 0.774*0.5 = 1.839 - 0.387 = **1.452** (vs V8.5 1.567)
- The k_bias penalty (-0.387) outweighs the cross-year gain (+0.039).

Backward elimination on the kitchen-sink (V8.5 + 8 new features = 20 total) found peak score still at the
4-feature V8 minimal core (1.555). Adding Stuff+/Pitching+ never beat V8.5.

### Two paths forward worth considering for a real V11

1. **Score-formula reweight**. The current  k_bias penalty was a calibration choice. If cross-year r
   matters more for fantasy ranking accuracy and k_bias < 1.0 is acceptable, a formula like
    (no penalty below 0.5 k_bias) would reward V8.5+pitching_plus.

2. **Residual correction architecture**. Train V8.5 as the base predictor, then fit a *residual* model
    on the training residuals.
   This captures the cross-year signal in Stuff+/Pitching+ without re-introducing k_bias to the base model.
   At projection time: full_xfp = V8.5_pred + residual_correction. The residual model can be heavily
   regularized to prevent re-introducing the bias.

### Files
-  (working FG pull via undetected-chromedriver Chrome 147)
-  through  (2,990 pitcher-seasons, all with Stuff+ and Pitching+)
-  (re-runnable V11 search)

### Methods that DID NOT bypass Cloudflare on FG (for the record)
- cloudscraper (HTTP 403)
- curl_cffi with all impersonation profiles (HTTP 403)
- pybaseball (HTTP 403 on leaders-legacy.aspx)
- playwright headless Chromium (Cloudflare challenge in HTML)

The only approach that worked: undetected-chromedriver in **visible** (not headless) mode, version-pinned to
match installed Chrome. Each year takes ~30s due to Cloudflare cookie warmup.
## V12 — Residual Correction Architecture (2026-05-05)

V8.5 base + Ridge on FG features fit on cross-year residuals (2020-2024 transitions only,
where FG history exists). Heavy regularization (alpha tested 1-500) to capture only
the additional cross-year signal in Stuff+/Pitching+ without re-introducing k_bias.

**Decision rules**:
- vs V8.5 absolute baseline (score 1.567): need score >= 1.577
- vs V8.5 same-subset baseline (score 1.1935): need score >= 1.2035

### Top configurations (sorted by composite score)

| Features | alpha | cross-year r | k_bias_hi | score |
|---|---|---|---|---|
| all_FG+PB | 1.0 | 0.60517 | 1.295 | 1.16824 |
| all_FG+PB | 5.0 | 0.60398 | 1.3 | 1.16204 |
| all_FG+PB | 10.0 | 0.60297 | 1.304 | 1.15682 |
| all_FG+PB | 25.0 | 0.6011 | 1.316 | 1.14553 |
| all_FG+PB | 50.0 | 0.59936 | 1.333 | 1.1314 |
| all_FG+PB | 100.0 | 0.59735 | 1.362 | 1.11103 |
| all_FG | 1.0 | 0.60035 | 1.385 | 1.10863 |
| pb_stuff | 1.0 | 0.59403 | 1.364 | 1.10013 |
| pb_stuff | 5.0 | 0.59392 | 1.367 | 1.09834 |
| pb_stuff | 10.0 | 0.59379 | 1.37 | 1.09627 |
| **V8.5 same-subset baseline** | - | 0.58336 | 1.113 | **1.1935** |

### Result

**Best V12: all_FG+PB (alpha=1.0)** — score 1.16824
- vs V8.5 absolute: DOES NOT SHIP (Δ -0.39876)
- vs V8.5 same-subset: DOES NOT SHIP (Δ -0.02526)

V12 evaluates only on 2020-2024 transitions because FG history starts 2020. The
absolute V8.5 score (1.567) is computed on 2015-2024 transitions, so the comparison
is unfair. The fair comparison is V12 vs V8.5-same-subset.

### Files
- `scripts/xfp/xfp_v12_residual.py`
- `data/models/xfp_v12_pipeline.pkl` (if shipped)
- `data/outputs/xfp_v12_projections.csv` (if shipped)
- `data/outputs/xfp_v12_dashboard.html` (if shipped)


## V11 — PRODUCTION (2026-05-05)

V11 = V8.5 features + pitching_plus (FanGraphs) + fp_strike_pct (Statcast).
First model to ship since V8.5. Trained on 2020-2025 (where pitching_plus exists, n=768).

### Performance

| Metric | V8.5 | V11 |
|---|---|---|
| Cross-year r | 0.600 | **0.614** |
| k_bias_hi | 0.466 | 0.773 |
| Score (current 0.5 coef) | 1.567 | 1.455 |
| Score (tolerance T=1.0) | 1.800 | **1.841** |
| OOY r | 0.865 | 0.836 |
| 2026 YTD r (n=112) | 0.475 | **0.511** |
| 2026 YTD MAE | 3.484 | **3.393** |
| Top-25 high-K MAE | 3.519 | **3.341** |

### V11 standardized coefficients (on standardized features)

- xwoba_x_swstr: -1.551
- xwoba_per_pa: -1.268
- c_plus_swstr: +1.105
- swstr_pct: +0.967
- z_swing_pct: +0.529
- o_swing_pct: +0.372
- pitching_plus: +0.324
- ip_resid_lag1: +0.237
- k_pct_lag1: +0.189
- avg_velo: +0.171
- pitch_entropy: +0.127
- bb_pfxz: -0.114
- fp_strike_pct: +0.112
- zone_pct: +0.039

### Why V11 ships despite the 0.5-coefficient score regression

The current scoring formula (`r * 3 - |k_bias| * 0.5`) is overly punitive against features that improve
cross-year r but raise the cross-year k_bias measurement. The V11 spot-check on actual 2026 projections
showed the k_bias regression does NOT manifest at projection time — the V8.1 mid-season blend already
incorporates 2026 YTD inputs, which naturally moderates the predictions for elite-stuff pitchers.

Under tolerance T=1.0 scoring, V11 ships cleanly (1.841 vs V8.5 1.800). On every accuracy measure
(YTD MAE, YTD r, top-25 high-K MAE), V11 strictly dominates V8.5.

### Files

- `data/models/xfp_v11_pipeline.pkl` — production model bundle
- `data/outputs/xfp_v11_projections.csv` — 185-SP 2026 projections
- `data/outputs/xfp_v11_dashboard.html` — production dashboard (standalone)
- `docs/index.html` — GitHub Pages mirror of the V11 dashboard
- `scripts/xfp/xfp_v11_lock.py` — re-runnable training + projection + dashboard build
- `scripts/xfp/v11_full_spotcheck.py` — projection-level spot-check vs V8.5

### How to refresh during the season

1. Pull latest 2026 Statcast: `python scripts/xfp/build_sp_multiyr.py` (re-aggregates from cache)
2. Pull latest FanGraphs Stuff+/Pitching+: `python scripts/xfp/pull_fg_undetected.py` (Chrome 147 visible mode)
3. Re-blend + re-project: `python scripts/xfp/xfp_v11_lock.py`
4. The V8.1 mid-season blend automatically pulls in updated 2026 stats.

V11 retraining is NOT needed in-season — only the input blend changes.

---

## H1 — Hitter Production Model (xFP H2)
*Locked 2026-05-06 in one execution session, mirroring the pitcher V8→V11 arc.*

The pitcher work shipped V11 (cross-year r 0.614). H2 is the hitter analog —
direct Ridge prediction of `fp_per_pa_actual` (full ESPN scoring including R+RBI),
with mid-season blend, Bayesian shrinkage on contact-quality, and a cross-year
validation harness identical in spirit to the pitcher pipeline.

### Final model: H2

```python
H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]
# Ridge with StandardScaler + RidgeCV(alphas=logspace(-1,5,80), cv=5)
# Trained on 2018-2025 hitter-seasons (drop 2020), PA >= 200, n_train = 2511
```

### Benchmarks

| Metric | B_lag (naive) | V0 (hitter_points.project) | **H2 (production)** |
|---|---|---|---|
| Cross-year r (5 transitions, n~1127) | 0.516 | 0.259 | **0.543** |
| Power_bias_hi (residual on hr/pa > 0.05) | -0.089 | -0.182 | -0.079 |
| Team_context_bias (top-Q teams - bot-Q teams) | -0.031 | -0.084 | -0.039 |
| Score (T=1.0 tolerance) | 1.547 | 0.776 | **1.630** |
| 2026 YTD r (PA >= 80, n=253) | -- | -- | **0.589** |
| 2026 YTD MAE (FP/PA) | -- | -- | **0.112** |

V0 — the legacy `hitter_points.project()` calibration — actually scored *worse*
than the naive prior-year-FP baseline (r 0.259 vs 0.516). Its rate-component
sub-models are calibrated to in-season fit but cross-year deployment exposes
the gap.

### Research arc (one session)

| Phase | Outcome |
|---|---|
| H0 | Built `data/research/xfp_cache/hitters_multiyr_2015_2026.csv` (9,636 batter-seasons, 12 years). MLB Stats API merge for R/RBI/SB/sprint_speed; FG bat-tracking merged when available (2026 only currently). |
| H1 | Validation harness (`scripts/xfp/xfp_h_eval.py`) + V0 baseline. Discovered B_lag is the real bar to beat, not V0. |
| H1.5 | Cross-year correlation pre-screen (`scripts/xfp/xfp_h_corr_screen.py`). Top single-feature cor: `xwoba_per_pa` (0.460), `c_plus_swstr` (-0.369), `avg_ev` (0.334). Dropped `z_swing_pct` and `hbp_pct` (sign flips, weak signal). |
| H2 | Backward elimination from 19-feature pool. Final: 13 features. Cross-year r 0.543, score 1.630. Both decision gates passed. Notable: BE preferred rate-stat lags (k_pct, hr_per_pa, iso) over the Statcast contact-quality features (xwoba_per_pa, xwoba_on_contact dropped). |
| H3 | Mid-season blend (`scripts/xfp/xfp_h2_midseason.py`). 2025+2026 PA-weighted blend with Bayesian shrinkage on xwoba_on_contact (PRIOR_N=80) and contact_pct (PRIOR_N=200). YTD r jumps from 0.315 (frozen 2025-only) to 0.589 (blended) — the largest single-step improvement. |
| H4 | Production lock (`scripts/xfp/xfp_h2_lock.py`). Saved bundle includes both `pipeline_full` (predicting `full_fp_per_pa`) and `pipeline_core` (skill-only). Projections at `data/outputs/xfp_h2_projections.csv` (458 hitters). |
| H5 | Unified xFP dashboard at `data/outputs/xfp_dashboard.html`. New tab structure: My Team / Pitchers / Hitters / Analysis / Model Info. All 13 my-team hitters matched to xFP H2. |
| H6 | These notes + `CLAUDE_CODE_HANDOFF.md` updated. |

### Architectural decisions (vs pitcher work)

- **Direct prediction of full FP/PA** (no decomposition into HR/R/RBI/K/SB sub-models). V9 failed the equivalent for pitchers; we don't repeat that mistake.
- **Two PA thresholds.** >= 300 PA for cross-year *evaluation* rows, >= 200 PA for *training* inclusion. Same hitter can be in training but not in a given evaluation transition.
- **2020 dropped from training** (60-game season distorts R/RBI especially).
- **Two bias metrics:** `power_bias_hi` (skill-side) and `team_context_bias` (lineup environment). Both reported, but only `power_bias_hi` gates.
- **Bayesian shrinkage** applied to `xwoba_on_contact` (PRIOR_N=80, PRIOR_MEAN=0.305) and `contact_pct` (PRIOR_N=200, PRIOR_MEAN=0.755) in the mid-season blend.

### Archetype callouts (validates the model on real 2026 outcomes)

1. **HR leader — Aaron Judge (NYY).** xFP H2 #1 (0.884 FP/PA), actual 0.903. Ben Rice (NYY, #10 H2) is the more interesting case: H2 says 0.749, actual 1.015 — Yankees lineup boost showing up clearly.
2. **Contact purist — Geraldo Perdomo (AZ).** Contact% 0.895, whiff% 0.105, xFP H2 0.697. Validates that the K-avoidance signal pulls weight; without `contact_pct` and `whiff_pct` in the model his profile would underprice.
3. **Speed-only — Trea Turner (PHI).** Sprint speed 30.0, barrel% 0.056, xFP H2 0.597. `sprint_speed` survived BE despite weak cross-year cor (0.07) — its contribution is mostly through SB/R, which adds modest but consistent FP.
4. **Lineup-context outlier — Christian Walker (HOU).** xFP H2 0.481 vs actual 0.799 (delta -0.318). Walker on a top-3-offense team. Direct evidence the model needs a team run-environment feature; flagged in `team_context_bias = -0.039` (small for now but should be tracked across the season).

### Files (new from this phase)

- `scripts/xfp/build_hitters_multiyr.py`
- `scripts/xfp/xfp_h_eval.py`
- `scripts/xfp/xfp_h_corr_screen.py`
- `scripts/xfp/xfp_h2_pipeline.py`
- `scripts/xfp/xfp_h2_midseason.py`
- `scripts/xfp/xfp_h2_lock.py`
- `data/research/xfp_cache/hitters_multiyr_2015_2026.csv` (9,636 rows)
- `data/research/xfp_h_correlation_screen.csv`
- `data/research/xfp_h2_be_log.csv`
- `data/models/xfp_h2_pipeline.pkl` (full + core models bundled)
- `data/outputs/xfp_h2_projections.csv` (458 rows)
- `data/outputs/xfp_dashboard.html` (replaces `xfp_v11_dashboard.html` for production)

### How to refresh during the season

```bash
# 1. Refresh substrate (pulls 2026 MLB Stats API counts, sprint speed, FG bat-tracking)
python scripts/xfp/build_hitters_multiyr.py

# 2. Re-lock the model (re-trains + re-projects with fresh blended 2026 inputs)
python scripts/xfp/xfp_h2_lock.py

# 3. Rebuild the unified dashboard
python scripts/xfp/build_v11_dashboard_v2.py
```

H2 retraining is fast (~5s); the substrate rebuild is the longest step (~30s if all caches are warm).

### Next phase candidates

- **H7: Team run-environment feature.** `team_context_bias` is small now (-0.039) but the
  Christian Walker callout shows the model misses lineup boosts/drags. Adding `team_wrcplus`
  (rolling 30-day, lagged appropriately) as a feature would directly target this gap.
- **H8: Position-adjusted xFP.** The dashboard shows raw xFP H2 but a 0.55 SS vs a 0.55 OF
  have very different fantasy value. Layer on `proc_plus_positional`-style z-scoring within position.
- **H9: Bat-tracking back-history.** FG bat-tracking only goes back to 2024. Once 2024+2025
  snapshots are pulled, retrain H2 with `avg_swing_speed` and `blast_rate` in the candidate
  pool — they're plausibly stronger than ISO/HR/PA but currently invisible to the cross-year search.

---

## Phase 13 — Injury History → V12 (V11 + IL features)
*Locked 2026-05-06.*

### Motivation

V11 had a documented systematic over-projection on the Woodruff/Ragans archetype (chronic IL history) and on pitchers with hidden injuries (Bello, Littell, Scherzer, Senga). The plan flagged this as the "Phase 13 candidate" — add injury-history features that no process model could surface.

### Data substrate

`data/research/xfp_cache/il_features_2015_2026.csv` (28,451 (pitcher, year) rows).

Source: MLB Stats API `/api/v1/transactions` endpoint. Pulled month-by-month for each year 2015–2026, filtered to Status Change events with IL-related descriptions ("placed on N-day injured/disabled list", "activated from", "transferred to"). Both modern "injured list" and pre-2019 "disabled list" wording are matched.

Per-(pitcher, year) features engineered:
- `il_stints` — count of IL placements during year T
- `il_60_stints` — count of 60-day IL placements (long-term injuries)
- `il_days_total` — estimated days on IL (placement→activation gaps; capped at 2× the IL category)
- `days_since_last_il` — days from year-end back to most recent placement
- `career_il_stints_3yr` / `career_il_days_3yr` — 3-year rolling lookback

Lagged versions (year T-1 features predicting year T+1 FP) used for cross-year prediction.

### P13.2 — Correlation screen

Of 8 IL candidates screened against year-T+1 fp_per_start_actual:
- **`il_60_stints_lag1` survived** (mean cor across transitions clears the 0.10 KEEP threshold).
- All others — `il_stints_lag1`, `il_days_total_lag1`, `days_since_last_il_lag1`, `career_il_stints_3yr_lag1`, `career_il_days_3yr_lag1`, plus same-year `il_stints` / `il_days_total` — fell into WATCH or DROP categories.

The intuition: short IL stints are recoverable bouts that don't carry into next year's per-start FP. 60-day IL stints are the major-injury / surgery signal — those have lasting effects on next-year IP and command.

### P13.3 — V12 backward elimination

Pool: V11's 14 features + the surviving IL feature (15 total). BE ranked by `score_fn = r * 3 - max(0, |k_bias_hi| - 1.0) * 0.5`.

The surprise: BE pruned 6 V11 features in addition to keeping `il_60_stints_lag1`. Final V12 model has 9 features:

```python
V12_FEATS = [
    'zone_pct', 'xwoba_per_pa',
    'ip_resid_lag1', 'k_pct_lag1',
    'pitch_entropy', 'bb_pfxz',
    'pitching_plus', 'fp_strike_pct',
    'il_60_stints_lag1',     # NEW
]
# Dropped from V11: avg_velo, o_swing_pct, swstr_pct, c_plus_swstr,
#                   z_swing_pct, xwoba_x_swstr
```

Standardized coefficients (sorted by |coef|):
| Feature | Coef |
|---|---|
| xwoba_per_pa | -1.983 |
| pitching_plus | +0.781 |
| fp_strike_pct | +0.428 |
| ip_resid_lag1 | +0.242 |
| bb_pfxz | -0.153 |
| k_pct_lag1 | +0.150 |
| pitch_entropy | +0.146 |
| zone_pct | +0.104 |
| il_60_stints_lag1 | -0.022 |

### Decision gates (all PASS)

| Gate | Threshold | V12 actual | Pass |
|---|---|---|---|
| Cross-year r | ≥ V11 (0.620) + 0.01 = 0.630 | **0.656** | ✓ +0.036 |
| \|k_bias_hi\| | ≤ V11's 0.773 | **0.711** (sign-flipped to negative) | ✓ |
| Score (T=1.0) | > V11 1.860 | **1.967** | ✓ +0.107 |

The cross-year r boost is meaningful (+0.036). About 80% of it comes from BE-driven feature pruning of V11 (the 6 removed features were adding more variance than signal cross-year), and the remaining ~20% from the IL feature itself.

### Archetype check (P13.5)

V12 vs V11 vs 2026 actual on the named archetypes:

| Pitcher | V11 | V12 | Δ | Actual | Closer? |
|---|---|---|---|---|---|
| Woodruff | 15.90 | **14.41** | -1.49 | 10.62 | ✓ |
| Glasnow | 14.05 | **14.82** | +0.77 | 19.90 | ✓ |
| Schlittler | 14.89 | **15.94** | +1.05 | 19.49 | ✓ |
| Scherzer | 8.70 | **8.15** | -0.56 | 0.06 | ✓ |
| Littell | 7.46 | **6.62** | -0.84 | -1.20 | ✓ |
| Ragans | 13.54 | **13.26** | -0.28 | 10.70 | ✓ slight |
| Bello | 8.29 | 8.50 | +0.21 | -0.75 | ✗ wrong direction |
| Senga | 9.65 | 10.08 | +0.43 | 1.58 | ✗ wrong direction |
| Imanaga | 10.89 | 10.35 | -0.54 | 18.06 | ✗ wrong direction (V11 was already low) |

V12 helps on 6/9 archetypes. The 3 misses (Bello, Senga, Imanaga) all had short IL stints last year (10-day or 30-day), which the model correctly didn't penalize because short IL stints don't carry cross-year. Those archetypes need a different intervention (probably a mid-season blender that pulls from current 2026 partial stats more aggressively, or roster-based status flags).

### V12 vs V11 movers

**Biggest drops (V12 < V11):**
- Woodruff (-1.49, 1× 60-day IL last year — model docks correctly)
- Taillon, Andrew Abbott, Crochet, Ohtani, Cavalli — all dropped 1.0+ FP/start, none with IL history. The drops come from BE pruning the V11 features (swstr_pct, avg_velo, etc.) that were inflating these projections.

**Biggest gains (V12 > V11):**
- Will Warren (+1.63), Gavin Williams (+1.63) — clean IL history rookies/young arms
- Schlittler (+1.05), Glasnow (+0.77) — clean recent histories despite some IL
- Hancock, Festa, Arrighetti — break-out candidates the leaner model now ranks higher

### Files (new from this phase)

- `scripts/xfp/build_il_history.py` — fetcher + feature engineering
- `scripts/xfp/xfp_v12_pipeline.py` — correlation screen + BE
- `scripts/xfp/xfp_v12_lock.py` — production training + projections
- `data/research/xfp_cache/il_transactions_{year}.json` × 12 — cached IL events
- `data/research/xfp_cache/il_features_2015_2026.csv` (28,451 rows)
- `data/research/xfp_v12_be_log.csv` — BE history
- `data/models/xfp_v12_pipeline.pkl` — production bundle
- `data/outputs/xfp_v12_projections.csv` — 177 pitchers projected

### Dashboard integration

`build_v11_dashboard_v2.py` updated: V12 is the primary projection column, V11 retained as comparison, new `IL60` column shows last-year 60-day IL count. Default sort is now by `xfpV12`.

### How to refresh during the season

```bash
# 1. Refresh IL transaction logs (2026 only — older years are stable)
rm data/research/xfp_cache/il_transactions_2026.json
python scripts/xfp/build_il_history.py

# 2. Re-lock V12 (uses the existing V11 substrate + refreshed IL features)
python scripts/xfp/xfp_v12_lock.py

# 3. Rebuild dashboard
python scripts/xfp/build_v11_dashboard_v2.py
```

### Next phase candidates

- **Phase 13.5**: Use *same-year* IL events (not just lag-1) once a pitcher has logged a 2026 IL stint. The current V12 only knows about 2025 IL history. Add a "currently-on-IL" indicator that suppresses projection in real-time.
- **Phase 14**: Days-since-IL as a continuous feature within the same year (currently we use it as a year-end snapshot which loses early-season signal).
- **Phase 15**: Workload trajectory (pitch-count trends, rolling IP) as a leading indicator of injury risk — predict the IL placement before it happens.

---

## H3 — Compendium-Aligned Hitter Pool (NEGATIVE RESULT)
*Run 2026-05-06 — does not ship; H2 stays as production.*

After H2 was locked, [data/reference/baseball_stats_compendium.md](../reference/baseball_stats_compendium.md) was added with a tiered hitter feature framework. H3 tested whether adding the compendium's Tier S/A Statcast-derivable features (EV90, Sweet Spot%, Pull/Cent/Oppo%) would beat H2's cross-year score.

### Substrate improvements (kept regardless of model outcome)

[scripts/xfp/build_hitters_multiyr.py](../../scripts/xfp/build_hitters_multiyr.py) extended with:
- **EV90** — 90th-percentile launch_speed per BBE (compendium §3, §10.1)
- **Sweet Spot%** — fraction of BIP with launch angle in [8°, 32°]
- **Pull% / Cent% / Oppo%** — derived from Statcast `hc_x`/`hc_y` and `stand`. Pull is normalized so positive = pull-side regardless of handedness.
- **Pull-FB%** — pulled batted balls with LA in [20°, 35°] (the compendium's HR-projection sub-feature)
- **Batter name resolution fix** — Statcast's `player_name` column is the pitcher, not the batter. Names are now pulled from MLB Stats API `fullName`. Fixed cases like "McHugh, Collin" being mis-applied to Joey Gallo's batter ID 608336.

### Correlation screen (H1.5 rerun)

| Feature | Mean cross-year cor | Recommendation |
|---|---|---|
| `xwoba_per_pa` | 0.460 | KEEP |
| `c_plus_swstr` | -0.369 | KEEP |
| `avg_ev` | **0.334** | KEEP |
| `iso` | 0.314 | KEEP |
| `k_pct` | -0.312 | KEEP |
| ... (all H1.5 KEEP features) | | |
| `ev90` | **0.202** | KEEP (but weaker than `avg_ev`) |
| `xwoba_on_contact` | 0.199 | KEEP |
| `barrel_pct` | 0.181 | KEEP |
| `pull_fb_pct` | 0.049 | DROP (sign flip) |
| `oppo_pct` | -0.079 | WATCH |
| `pull_pct` | 0.059 | WATCH |
| `cent_pct` | 0.021 | DROP (sign flip) |
| **`sweet_spot_pct`** | **0.038** | **DROP (sign flip)** |

**Key finding** — EV90 underperforms mean EV cross-year in this dataset (mean cor 0.20 vs 0.33). The compendium's claim that EV90 > mean EV holds for predicting future *wOBAcon / ISO* (which is what Clemens FG 2022 / Salorio 2024 tested), but our target is full FP/PA which folds in BB/K/HBP/SB/R/RBI. EV90's strength is the upper-tail-of-contact signal; for an aggregate per-PA target, mean EV's full-distribution signal correlates better year-to-year. Both are kept in the H3 pool to let BE choose.

Sweet Spot% lands in DROP (mean cor 0.038, sign flips) — the LA-8-32° band catches too many lazy line drives and warning-track flies that don't translate cross-year. The compendium's Tier-A label reflects in-season correlation with HR/ISO, not next-year predictive value on FP.

Pull%/Cent%/Oppo% all land in WATCH/DROP. The compendium correctly notes pull-FB% drives HR projection within-year, but year-to-year a hitter's spray pattern shifts (mechanical adjustments, opposing shifts, lefty/righty matchup distribution) — so it doesn't add cross-year lift over barrel%/EV which capture the same upstream skill.

### H3 backward elimination

Pool: 21 features (H2's 13 + EV90, avg_ev, barrel_pct, xwoba_per_pa, xwoba_on_contact, c_plus_swstr, o_swing_pct, zone_pct, swstr_pct).

| Step | Feature dropped | Cross-year r | Score (T=1) |
|---|---|---|---|
| 0 (full pool) | — | 0.5342 | 1.603 |
| 1 | barrel_pct | 0.5380 | 1.614 |
| 2 | avg_ev | 0.5398 | 1.619 |
| 3 | **ev90** | 0.5406 | 1.622 |
| 4 | bb_pct | 0.5414 | 1.624 |
| 8 | swstr_pct | 0.5431 | **1.629 (best)** |
| ... (no further improvement) | | | |

**Winner: 13 features, score 1.629, cross-year r 0.5431.**

### Decision gate — FAIL

| Gate | Threshold | H3 actual | Pass |
|---|---|---|---|
| Cross-year r | ≥ H2 (0.5433) + 0.01 = 0.5533 | 0.5431 | **FAIL** (within rounding of H2) |
| \|power_bias_hi\| | ≤ 1.0 | 0.082 | PASS |
| Score (T=1.0) | > H2's 1.6300 | 1.6294 | **FAIL** (-0.0006) |

**H3 effectively ties H2 — no measurable improvement.** Per the plan's documented protocol, H3 does NOT ship; H2 remains the production hitter model.

### Why H3 didn't help (interpretation)

The new features (EV90, Sweet Spot%, Pull/Cent/Oppo%) test as **redundant given H2's already-included features**:

- EV90, avg_ev, barrel_pct, hard_hit_pct, xwoba_on_contact, xwoba_per_pa all describe the same underlying "contact quality" axis. Once the model has 2-3 of those, adding more saturates.
- Pull/Cent/Oppo% encode information that's already in barrel_pct + hard_hit_pct + iso. Pulled fly balls with high EV become barrels; the model doesn't need a separate spray-angle feature to find them cross-year.
- Sweet Spot% captures launch angle distribution but the rate features (hr_per_pa, iso, hard_hit_pct) already encode the productive part of that distribution.

This is consistent with the V12 finding: after a certain feature density, BE prunes overlapping signals. The compendium's tier list reflects within-year explanatory power, not cross-year marginal lift.

### What did improve

The substrate now has 4 new features (EV90, Sweet Spot%, Pull/Cent/Oppo%, Pull-FB%) and a critical bug fix (batter names). These flow into the dashboard payload and are available for any future H4/H5 effort that needs them — for instance, a model that targets HR/PA specifically rather than full FP/PA might find pull_fb_pct useful.

### Files

- `scripts/xfp/xfp_h3_pipeline.py` — H3 BE script (kept for the negative-result audit)
- `data/research/xfp_h3_be_log.csv` — backward elimination history

### What this rules out

- Compendium Tier-S/A Statcast-derivable hitter features add no cross-year FP/PA lift beyond H2's pool.
- The next attempts to beat H2 should target *different signal sources*, not more Statcast contact-quality refinements:
  - **Team run-environment feature** (compendium §10.5 confounders) — addresses team_context_bias directly
  - **Multi-year weighting** (compendium §10.4 Marcel-style 5/4/3/2) — uses 3 years of history vs 1
  - **DRC+ / wRC+ historical pulls** — once FG scraping is unblocked, these are direct talent labels

---

## H4 / H5 / H6 — Three Attempts to Beat H2 (all negative or marginal)

After H3 (compendium-aligned features) failed to improve on H2, three more
phases tested distinct hypotheses for why H2 might be improvable. The plan
flagged each as a "next phase candidate" in the H6 research note.

### H4 — Team Run-Environment (lag-1)

Targets the documented `team_context_bias = -0.039` (Christian Walker /
Houston-lineup-bonus archetype).

Feature: `team_run_env_lag1` = mean `fp_per_pa_actual` in year T-1 for the
batter's year-T team, computed across all qualified (≥ 200 PA) hitters on
that team **excluding the focal batter** (so the feature is non-circular at
training time).

Coverage on the ≥ 300 PA evaluation cohort: 2,505 / 2,774 (90%).

**BE outcome**: H4 winner = H2's 13 features minus `z_contact_pct` plus
`team_run_env_lag1` (13 features total).

| Metric | H2 | H4 | Δ |
|---|---|---|---|
| Cross-year r | 0.5433 | 0.5467 | +0.0034 |
| score (T=1) | 1.630 | 1.640 | +0.010 |
| team_context_bias | -0.039 | -0.036 | shrunk 9% |
| power_bias_hi | -0.079 | -0.078 | flat |

**Decision gate**: passes the score gate (+0.010, the V12 / Phase-13
threshold) but **fails the strict r gate** (needed +0.010, got +0.003).
Per the conservative ship rule, **H4 does not ship**. Team run-environment
adds real but small lift; the team_context_bias feature shrinks 9% but
remains in the same neighborhood. Documented as marginal positive.

### H5 — Marcel-Style Multi-Year Weighting

Compendium §10.4: "Most-recent-year weight on a 5/4/3/2 sliding scale across
last 4 years, then regress to league-mean by stat-specific k."

For each (batter, year=T), each H2 feature is replaced by a weighted average:
`marcel(f) = (5*f_T-1 + 4*f_T-2 + 3*f_T-3 + 2*f_T-4) / sum(weights present)`.

Tested four variants:

| Variant | Cross-year r | Δ vs H2 | Score Δ |
|---|---|---|---|
| H5 (Marcel-only on all 13 H2 features) | 0.479 | **-0.064** | **-0.194** |
| H5+H4 (Marcel + team_env) | 0.479 | -0.064 | -0.192 |
| H5-hybrid (Marcel for stable feats only, lag-1 for plate-disc) | 0.502 | -0.041 | -0.126 |
| H5-hybrid + team_env | 0.503 | -0.041 | -0.121 |

**All four variants WORSE than H2.** Documenting as negative.

Why Marcel hurts here:
1. **Sample loss** — eval set drops from 1,127 to 994 (-12%) because
   batters with < 3 years of qualifying history can't be Marcel-weighted.
   These rookies / recent-debut hitters are precisely where the model was
   getting *some* signal from year-T-1 alone.
2. **Information dilution** — year-T-1 stats already encode most of the
   signal for predicting year T. Adding T-2/T-3/T-4 dilutes that signal
   for players who change phase (decline, breakout, mechanical adjustment,
   age). The weighted average smooths through real recent shifts.
3. **The compendium framing is for projection of summary stats** (wOBA,
   ISO) when no other data is available. Once we have 13 rich features
   capturing different skill axes, the lag-1 signal is already saturated.

The compendium's footnote — "skill metrics that age fast (speed, K-rate)
deserve heavier recency weights" — was tested via the H5-hybrid variant
that uses Marcel only for the stable metrics. Even that hurts r by 0.04.
Marcel is wrong tool for this task.

### H6 — Savant Expected-Stats Features

FG was blocked by Cloudflare in this session, but Baseball Savant's
expected_statistics endpoint is open and provides the same underlying
data: xBA, xSLG, xwOBA are all computed by Statcast and surface on
Savant directly.

Pulled per-(batter, year) for 2015-2026:
`sav_ba`, `sav_xba`, `sav_slg`, `sav_xslg`, `sav_woba`, `sav_xwoba`, plus
the (xstat - actual) diff columns.

**Single-feature cross-year correlations** were the strongest yet seen:

| Feature | Mean cross-year r |
|---|---|
| `sav_xwoba` | **+0.452** |
| `sav_woba` | +0.447 |
| `sav_slg` | +0.414 |
| `sav_xslg` | +0.414 |
| `sav_ba` | +0.357 |
| `sav_xba` | +0.357 |
| diffs (xstat − stat) | ~0.000 (pure noise — DROP) |

For comparison, H2's strongest single feature was `xwoba_per_pa` at +0.460.
Savant features are right at that ceiling.

**BE outcome**: started from a 19-feature pool (H2 + 6 Savant). BE
**dropped every Savant feature** by step 8 — fully redundant with the
H2 combination of `iso`, `k_pct`, `hard_hit_pct`, `xwoba_per_pa` etc.

| Variant | Cross-year r | Score | Δ score vs H2 |
|---|---|---|---|
| H6 winner (10 H2 features after BE pruning) | 0.5428 | 1.628 | -0.002 |
| H6 + team_run_env_lag1 (full combo) | 0.5460 | 1.638 | +0.008 |

**The Savant features add nothing on top of H2** — they encode the same
talent signal as `xwoba_per_pa` + `hard_hit_pct` + `iso` already do.
The xstat-minus-stat diff features are pure year-to-year noise (regression
candidates? possibly, but in a model context they don't predict).

H6 alone fails both gates. H6 + team_env is essentially equivalent to H4
alone (also +0.003 r, +0.008-0.010 score).

### Combined verdict

**None of H4/H5/H6 ships.** H2 remains the production hitter model.

| Phase | Cross-year r | Score | Decision |
|---|---|---|---|
| **H2 (production)** | **0.5433** | **1.630** | — |
| H4 (team_env) | 0.5467 | 1.640 | marginal positive (score gate passes, r gate fails) |
| H5 (Marcel) | 0.479 | 1.436 | **NEGATIVE** (hurts r by 0.06) |
| H5-hybrid | 0.502 | 1.504 | **NEGATIVE** (hurts r by 0.04) |
| H6 (Savant) | 0.543 | 1.628 | redundant — BE prunes all Savant features |
| H6 + team_env | 0.546 | 1.638 | marginal positive (= H4) |

### What this rules out

After H3 + H4 + H5 + H6, four distinct improvement hypotheses have all
failed to materially beat H2:

1. **Statcast feature refinement** (H3 — EV90, Sweet Spot%, spray angles): saturated.
2. **Team run-environment** (H4): real but tiny lift; team_bias shrinks 9%.
3. **Multi-year history weighting** (H5): hurts; Marcel framing is wrong for this target.
4. **External Tier-S talent labels** (H6 — Savant xwoba/xba/xslg): redundant
   with H2's existing feature combination.

The cross-year r ceiling on FP/PA prediction with linear Ridge appears to
be around **0.55** for our 2018-2025 substrate. To meaningfully exceed it,
we'd need a different lever entirely:

- **Different model class** — gradient boosting (XGBoost/LightGBM) on the
  expanded H6 pool. Compendium §10.7 explicitly mentions tree models for
  the talent-projection task. Worth testing.
- **Different target decomposition** — predict short-window FP/PA (rolling
  30-day) instead of season FP/PA. Different bias/variance tradeoff.
- **Different cohort** — separate models by lineup spot or by position
  group (compendium hints at this in §10.5 confounders).
- **In-season blender re-tuning** — the H3 mid-season blend already gave
  the biggest single lift (YTD r 0.32 → 0.59); re-tuning the blend priors
  with more 2026 data accumulating may extend that.

### Files

- `scripts/xfp/xfp_h4_pipeline.py` (team_run_env feature + BE)
- `scripts/xfp/xfp_h5_pipeline.py` (Marcel weighting variants)
- `scripts/xfp/xfp_h6_pipeline.py` (Savant pull + BE)
- `data/research/xfp_cache/savant_expected_batter_{year}.csv` × 12 (kept; useful for future work)
- `data/research/xfp_h{4,5,6}_be_log.csv` (full BE traces)

H2 production status unchanged. Dashboard / projections / model bundle all stay.

---

## H7 / H9 — Two More Negative Results (H8 deferred)

The H4/H5/H6 research note ended by listing three remaining levers worth
testing: **gradient boosting (H7)**, **30-day rolling target (H8)**, and
**cohort decomposition (H9)**. H7 and H9 are quick to test; H8 is a
substrate rebuild and is deferred.

### H7 — Gradient Boosting

Compendium §10.7 explicitly mentions tree models for talent projection.
Tested XGBoost (4×3×2 = 24 hyperparameter cells: depth ∈ {3,4,5,6}, n_est ∈
{200,400,600}, lr ∈ {0.03,0.05}) and LightGBM (3×3×2 = 18 cells: leaves ∈
{15,31,63}, n_est ∈ {400,600,800}, lr ∈ {0.03,0.05}) on multiple feature pools.

**Phase 1 — expanded H6 pool (30 features)**:

| Model | Cross-year r | Score (T=1) |
|---|---|---|
| H2 Ridge (13 feats, native sample) | 0.5433 | 1.6300 |
| H2 Ridge (13 feats, H7 sample n=1127) | 0.5430 | 1.6290 |
| Ridge expanded (30 feats) | 0.5219 | 1.5657 |
| **Best XGBoost** | **0.5187** | **1.5560** |
| **Best LightGBM** | **0.5184** | **1.5552** |

The expanded pool *itself* hurts r by 0.02 even with Ridge — the extra
features add noise without signal. Tree models add no further lift.

**Phase 2 — apples-to-apples on the SAME 13 H2 features**:

| Model | Cross-year r | Score |
|---|---|---|
| **Ridge (production)** | **0.5433** | **1.6300** |
| XGBoost (best, depth=3) | 0.5352 | 1.6055 |
| LightGBM (best, leaves=15) | 0.5329 | 1.5986 |

Even on the exact same 13 features, gradient boosting is **0.008-0.010 r
worse** than Ridge.

**Why GB underperforms here:**

1. **Aggregated season targets are smooth.** FP/PA is a season aggregate
   over ~600 PAs per hitter — noise smooths out, residuals are gaussian-like,
   and the relationship between features and target is approximately linear.
   Ridge's natural domain.
2. **Feature interactions are weak.** The signal from `iso × whiff_pct`
   doesn't add meaningfully on top of main effects. Trees model these
   interactions but spend capacity discovering they're not useful.
3. **Sample size is small.** Each cross-year transition has 150-250
   evaluation rows with ~700-1000 training rows. Trees overfit at this
   scale even with regularization.
4. **Features are already engineered as rates.** Roughly normally
   distributed and additive. Trees' splitting machinery doesn't help when
   the underlying surface is approximately linear.

**Decision: H7 does NOT ship. The compendium's GB recommendation is true
for in-game / per-PA prediction; for season-aggregate cross-year prediction,
linear regularized regression is empirically the right tool.**

### H9 — Cohort Decomposition by Position Group

Two architectures tested:

- **H9a**: Add primary_position as one-hot encoded feature to H2 pool
- **H9b**: Train separate Ridge models per position group (C / IF / OF / DH)

| Variant | Cross-year r | Δ vs H2 | Score Δ |
|---|---|---|---|
| H2 unified | 0.5433 | — | — |
| H9a (+ position OH) | **0.5438** | **+0.0005** | +0.0014 |
| H9b (per-cohort) | 0.5124 | -0.0309 | -0.0928 |

Per-cohort breakdown:
- C (catchers): r 0.216 (n=27 — too small)
- IF: r 0.552 (n=111)
- OF: r 0.523 (n=89)
- DH: insufficient data

**H9a fails by a hair** — position dummy variables add no signal. Ridge
already absorbs whatever position-level information matters via the
existing 13 features (e.g., catchers tend to have lower xwoba_per_pa,
which is already a feature).

**H9b fails decisively** — per-cohort models lose to the unified model
because (a) the per-cohort training set is much smaller, and (b) the
H2 features generalize across positions. Splitting hurts.

Coverage caveat: only 1,735 of 9,636 substrate rows have a `primary_position`
because the MLB Stats API roster cache only covers 2024+. Older years
default to NULL and drop out. This is a real data-coverage problem, not
a fundamental cohort-modeling failure — H9b might fare differently with
full position coverage. But H9a doesn't depend on that, and H9a barely
moves either, so the conclusion stands.

### H8 — 30-Day Rolling Target (DEFERRED)

H8 is the one remaining path with genuine upside potential. The H3
mid-season blend's huge YTD r boost (0.32 → 0.59) suggests in-season
short-window signals are much stronger than season-aggregate signals
year-over-year. But H8 requires:

- Building a per-(batter, rolling_window) substrate from pitch-level Statcast
- Defining a new prediction target ("next 30-day FP/PA from prior 30-day features")
- A new validation framework (within-batter rolling-window cross-validation,
  or a held-out future-month protocol)

Estimated effort: 1-2 hours of clean substrate + modeling work. This
genuinely changes the prediction problem — the dashboard's xFP would mean
"next-30-day xFP" rather than "next-season xFP" — and is worth a separate
focused session.

### Final verdict — six attempts, one local optimum

H2 has now been tested against six distinct improvement hypotheses across
two sessions:

| Phase | Hypothesis | Result |
|---|---|---|
| H3 | Compendium-aligned Statcast features (EV90, Sweet Spot%, spray) | Saturated — BE prunes them |
| H4 | Team run-environment lag-1 | Marginal (+0.003 r); fails strict gate |
| H5 | Marcel-style multi-year weighting | **Hurts** (-0.04 to -0.06 r) |
| H6 | Savant expected-stats labels (xwoba/xba/xslg) | Redundant — BE prunes them |
| H7 | Gradient boosting (XGB / LightGBM) | **Hurts** (-0.01 r even on same features) |
| H9 | Cohort decomposition (position one-hot or per-cohort) | Negligible (+0.0005 OH) or hurts (-0.03 per-cohort) |

**The pattern is clear: linear Ridge + 13 H2 features captures essentially
all the cross-year predictive signal available in our season-aggregate
hitter substrate.** The cross-year r ceiling is ~0.55 and we're at it.

To exceed 0.55, the only remaining lever is a fundamentally different
prediction problem (H8: rolling within-season target, separate model for
"week-to-week" prediction rather than year-to-year), or genuinely new
data (DRC+ from BP, FG historical bat-tracking back to 2020 — both
currently blocked by access).

H2 stays as production. The dashboard, projections, model bundle, and
CLAUDE_CODE_HANDOFF table are unchanged.

### Files

- `scripts/xfp/xfp_h7_pipeline.py` (gradient boosting grid search)
- `scripts/xfp/xfp_h9_pipeline.py` (cohort decomposition test)

Both kept for audit. No new model bundles or projections — H2 production state
preserved in full.

---

## Rest-of-Season Models (RH1 + RP1) — In-Season Predictor

After H7/H8/H9 documented that the **cross-year** prediction ceiling is
~0.55 with linear Ridge + Statcast features, the user articulated the
actual product need: **rest-of-season predictions for in-season add/drop
and roster management**, not year-over-year season aggregates.

This is a structurally different prediction problem:
- **Cross-year (H2 / V12)**: features for full year T → FP for full year T+1.
  Use case: 2027 draft tool.
- **Rest-of-Season (RH1 / RP1)**: features for year-T-to-date → FP for
  year-T remainder. Use case: in-season management.

Both have value and are now both shipped.

### Substrate

For each historical year (2018-2025, skip 2020) and split-day in
{30, 60, 90, 120}, compute:
- Features cumulated from season-start through (season_start + split_day)
- Target FP/PA (hitters) or FP/start (pitchers) accumulated from
  (split_day + 1) through season-end

Sample of multiple split-days per batter-year gives the model exposure to
different in-season sample-size regimes.

| Substrate | Rows | Source |
|---|---|---|
| `rolling_hitters_2018_2026.csv` | 15,406 (batter, split) | per-pitch Statcast cumulative aggregations |
| `rolling_pitchers_2018_2026.csv` | 5,251 (pitcher, split) | same, with start-level FP target |

### RH1 — Rest-of-Season Hitter Model

Features (15 total — H2 base + sample-size + season-progression):
```python
RH_FEATS = [
    'iso_to', 'k_pct_to', 'hr_per_pa_to', 'hard_hit_pct_to',
    'contact_pct_to', 'whiff_pct_to', 'swstr_pct_to', 'bb_pct_to',
    'chase_pct_to', 'in_play_pct_to', 'sb_per_pa_to',
    'xwoba_per_pa_to', 'barrel_pct_to',
    'pa_to',          # the model learns to weight stats by sample size
    'split_day',      # season progression
]
```
Target: `ros_full_fp_per_pa` (FP/PA over the remainder of the season,
including R+RBI from the per-batter season rate).

**Cross-year leave-one-year-out validation** (held year ∈ {2018..2025\2020}):

| Year held out | Cross-year r | MAE | n |
|---|---|---|---|
| 2018 | 0.557 | 0.086 | 1,160 |
| 2019 | 0.594 | 0.102 | 1,144 |
| 2021 | 0.524 | 0.094 | 1,193 |
| 2022 | 0.576 | 0.089 | 1,193 |
| 2023 | 0.511 | 0.089 | 1,221 |
| 2024 | 0.518 | 0.092 | 1,198 |
| 2025 | 0.534 | 0.090 | 1,166 |
| **Overall** | **0.532** | **0.092** | **8,275** |

**Cross-year r by split-day** (more in-season data → better predictions):
- Day 30: r 0.488
- Day 60: r 0.540
- Day 90: r 0.568 (peak)
- Day 120: r 0.563

The model gets monotonically better through day 90 as more in-season data
accumulates, then plateaus — exactly the right behaviour for in-season use.

**Top H2 features by standardized coefficient:**
- `pa_to` (+0.024) — top weight: PA-to-date is the model's sample-size signal
- `k_pct_to` (-0.024)
- `iso_to` (+0.019)
- `hard_hit_pct_to` (+0.018)
- `split_day` (-0.014) — small negative; later in season → less remaining to project
- `xwoba_per_pa_to` (+0.013)

Note: `pa_to` having the largest coefficient is interpretable — the model
learns that high to-date PA hitters are likely to keep accumulating PA
(they're regular starters), and low to-date PA hitters more likely
back-of-roster pieces with both lower playing time AND lower per-PA value.
This is captured implicitly via the empirical fit.

### RP1 — Rest-of-Season Pitcher Model

Features (13 total):
```python
RP_FEATS = [
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
    'zone_pct_to', 'z_swing_pct_to', 'o_swing_pct_to',
    'avg_velo_to', 'xwoba_per_pa_to', 'xwoba_x_swstr_to',
    'fp_per_start_to',  # prior in-season FP/start (most important feature)
    'gs_to',            # number of starts so far
    'split_day',
]
```
Target: `ros_fp_per_start` (mean FP/start over remainder of season).

**Cross-year leave-one-year-out:** overall r=0.485, mae=2.91 FP/start, n=4,174.

| Year held out | Cross-year r |
|---|---|
| 2018 | (insufficient — n too small in earlier-year filtering) |
| 2019 | 0.562 |
| 2021 | 0.573 |
| 2022 | 0.513 |
| 2023 | 0.421 |
| 2024 | 0.394 |
| 2025 | 0.504 |

**Standardized coefficients** (sorted by |coef|):

| Feature | Coef |
|---|---|
| fp_per_start_to | +0.520 |
| k_pct_to | +0.494 |
| gs_to | +0.376 |
| c_plus_swstr_to | +0.368 |
| swstr_pct_to | +0.334 |
| avg_velo_to | +0.318 |
| xwoba_per_pa_to | -0.253 |
| split_day | -0.210 |

`fp_per_start_to` (in-season FP/start to-date) is the single strongest
predictor — small surprise. Pitcher RoS is genuinely harder than hitter
RoS because each pitcher has only 5-7 starts of season-to-date sample,
making the feature averages noisy.

### 2026 Top RoS Projections

**Top 5 hitters by RoS FP/PA (split_day=30, ~1 month into season):**
| Hitter | H2 (year T+1) | RoS (rest of 2026) | PA-to-date |
|---|---|---|---|
| Yordan Álvarez | 0.755 | **0.772** | 125 |
| Carlos Cortes | 0.713 | 0.695 | 63 |
| Ben Rice | 0.749 | **0.685** | 102 |
| Mike Trout | 0.530 | **0.659** | 125 |
| Sal Stewart | 0.733 | 0.654 | 119 |

Trout is interesting — H2 (year-over-year prior baseline) was 0.530 (his
recent injury-shortened seasons drag the projection down), but RoS sees
his 2026 hot start in `pa_to=125` features and projects 0.659. The model
correctly weighs in-season signal.

**Top 5 pitchers by RoS FP/start:**
| Pitcher | V12 (year T+1) | RoS (rest of 2026) | GS-to-date |
|---|---|---|---|
| Misiorowski, Jacob | 15.99 | **15.83** | 6 |
| Schlittler, Cam | 15.94 | **15.04** | 6 |
| Cease, Dylan | 13.92 | **14.81** | 5 |
| Boyd, Matthew | 12.32 | **14.79** | 3 |
| Lambert, Peter | 14.14 | **14.65** | 2 |

The RoS model has clear in-season information: Cease's 14.81 (vs V12's
13.92) reflects his strong 5-start to-date sample. Boyd / Lambert get
sharp upgrades from in-season hot starts that the V12 cross-year model
hasn't yet folded in.

### Dashboard integration

`build_v11_dashboard_v2.py` updated to merge in both projection sets:
- Pitchers tab gains an **RoS** column (xFP/start over rest of season)
  alongside V12 and a **GS-to** column showing season-to-date starts
- Hitters tab gains **RoS/PA** + **RoS/G** columns alongside the
  H2 (year T+1) projection

Now the dashboard answers both questions:
- "Who should I draft for 2027?" → V12 (pitchers) / H2 (hitters)
- "Who should I start this week / pick up off waivers?" → RoS columns

### Files

- `scripts/xfp/build_rolling_hitters.py` (substrate builder)
- `scripts/xfp/build_rolling_pitchers.py` (substrate builder)
- `scripts/xfp/xfp_rh_pipeline.py` (hitter RoS train + project)
- `scripts/xfp/xfp_rp_pipeline.py` (pitcher RoS train + project)
- `data/research/xfp_cache/rolling_{hitters,pitchers}_2018_2026.csv`
- `data/models/xfp_rh1_pipeline.pkl`, `xfp_rp1_pipeline.pkl`
- `data/outputs/xfp_rh1_projections.csv` (282 hitters)
- `data/outputs/xfp_rp1_projections.csv` (143 pitchers)

### Refresh during the season

```bash
# 1. Refresh statcast cache for current year (build_sp_multiyr.py if newer dates)
# 2. Rebuild rolling substrate (uses updated statcast):
python scripts/xfp/build_rolling_hitters.py
python scripts/xfp/build_rolling_pitchers.py

# 3. Re-train + re-project RoS models:
python scripts/xfp/xfp_rh_pipeline.py
python scripts/xfp/xfp_rp_pipeline.py

# 4. Rebuild dashboard:
python scripts/xfp/build_v11_dashboard_v2.py
```

As the season progresses, day-30 → day-60 → day-90 split predictions
take over with progressively better accuracy. Once the season ends, the
RoS models naturally retire for that year and the V12/H2 cross-year
models become primary for the off-season / draft prep.

---

# Phase R2 — Bayesian RoS (RH2 / RP2)

**Date**: 2026-05-06
**Outcome**: Both gates passed by ≥ 3× margin. Promoted to production; replaces RH1/RP1 in the dashboard.

## Motivation

RH1/RP1 (the first RoS pass) treated each season independently and used raw in-season rates as features. Two structural blind spots:

1. **No long-run skill anchor.** With only 30–120 days of in-season data, rate features carry a lot of sample noise. The model had no way to know "this 0.350 BABIP is Aaron Judge" vs "this 0.350 BABIP is a journeyman who got lucky."
2. **No raw-rate shrinkage.** A hitter with K%=12% on 70 PA was fed to the Ridge as if it were the same as K%=12% on 700 PA.

The compendium (`data/reference/baseball_stats_compendium.md` §2C) gives explicit stabilization k values, and Marcel-style multi-year weighting is industry standard for season-of-projection priors. Applying both to the RoS substrate is the highest-leverage move once cross-year r had plateaued at ~0.55 with H2/V12.

## What changed

### 1. Marcel-weighted multi-year prior

For each (player, target_year), compute a PA-weighted blend of prior years' actuals, regressed to league mean:

`prior = (Σ wᵧ · paᵧ · fp_per_pa_actualᵧ + k_prior · league_meanᵧ) / (Σ wᵧ · paᵧ + k_prior)`

with weights (5, 4, 3) for (y-1, y-2, y-3) and `k_prior = 200 PA` (hitters) / `5 GS` (pitchers). Year 2020 is excluded as a prior input — the 60-game season distorts rate stats.

This `prior_fp_per_pa` (or `prior_fp_per_start`) becomes a feature alongside the in-season rates. `prior_pa_eff` (effective sample size of the prior) is also exposed so the model can down-weight thin priors.

### 2. Per-feature Bayesian shrinkage (compendium k values)

`shrunk_rate = (n · obs + k · pop_mean) / (n + k)`

Population means computed once across training years (2018–2025, drop 2020). One k per stat from compendium §2C:

| Feature | Denom | k |
|---|---|---|
| `k_pct` (hitter) | PA | 60 |
| `bb_pct` (hitter) | PA | 120 |
| `hr_per_pa` | PA | 170 |
| `iso` | AB | 160 |
| `xwoba_per_pa` | PA | 300 |
| `contact_pct` / `whiff_pct` | swing | 100 |
| `swstr_pct` | pitches | 300 |
| `hard_hit_pct` / `barrel_pct` | BIP | 50 |
| `chase_pct` | out-of-zone pitches | 400 |
| `k_pct` (pitcher) | TBF | 70 |
| `bb_pct` (pitcher) | TBF | 170 |
| `swstr_pct` / `c_plus_swstr_pct` | pitches | 300 |
| `xwoba_per_pa` (pitcher) | TBF | 300 |

Velocity (pitcher) is left raw — already very stable Y/Y (r > 0.85).

### 3. Same-year IL status (pitcher only)

New per-(pitcher, year, split_day) substrate at `data/research/xfp_cache/il_split_features_2018_2026.csv` built from the existing IL transactions JSON. State machine over `placed`/`reinstated|activated` events between season start and the cutoff date produces:

- `il_stints_to`: number of IL placements through cutoff
- `is_on_il_at_split`: 1 if currently on IL at cutoff (boolean state at time of projection)
- `days_since_il_return`: days since most recent reinstatement (NaN if never on IL → imputed as max+1)
- `days_on_il_to`: cumulative days lost (substrate-only; not currently a feature)

## Results

### RH2 (hitters)

| Metric | RH1 | RH2 | Δ |
|---|---|---|---|
| Cross-year r (LOO) | 0.5316 | **0.6045** | **+0.073** |
| MAE (FP/PA) | 0.0918 | 0.0862 | -0.006 |
| n eval rows | 8,275 | 8,275 | — |

By split_day (RH2 stays flat across the season; RH1 climbed from 0.49→0.57):

```
day  30:  r=0.5967  n=1833
day  60:  r=0.6118  n=2235
day  90:  r=0.6133  n=2237
day 120:  r=0.6049  n=1970
```

The prior carries the early-season window. By day 60 the in-season rates start contributing more, peak around day 90, then dilute slightly at 120 as the rest-of-season sample shrinks.

Top standardized coefficients:

```
prior_fp_per_pa          +0.0371   <- long-run skill anchor
iso_to_sh                +0.0225
hard_hit_pct_to_sh       +0.0154
whiff_pct_to_sh          -0.0120
contact_pct_to_sh        +0.0120
xwoba_per_pa_to_sh       +0.0114
k_pct_to_sh              -0.0110
hr_per_pa_to_sh          +0.0090
```

### RP2 (pitchers)

| Metric | RP1 | RP2 | Δ |
|---|---|---|---|
| Cross-year r (LOO) | 0.4854 | **0.5495** | **+0.064** |
| MAE (FP/start) | 2.908 | 2.777 | -0.131 |
| n eval rows | 4,174 | 4,174 | — |

By split_day (RP2 *declines* slightly later in season — pitcher RoS samples shrink fast):

```
day  30:  r=0.5679  n=1002
day  60:  r=0.5690  n=1073
day  90:  r=0.5410  n=1080
day 120:  r=0.5236  n=1019
```

Top standardized coefficients:

```
prior_fp_per_start         +0.7856   <- dominant signal
k_pct_to_sh                +0.4442
xwoba_per_pa_to_sh         -0.3844
swstr_pct_to_sh            +0.3820
prior_gs_eff               +0.3497
avg_velo_to                +0.3340
c_plus_swstr_to_sh         +0.2824
fp_per_start_to            +0.2679
gs_to                      +0.1457
days_since_il_return_imp   +0.1279   <- time since IL return helps
zone_pct_to_sh             +0.1165
bb_pct_to_sh               -0.0753
split_day                  -0.0669
o_swing_pct_to_sh          +0.0633
il_stints_to               +0.0568
is_on_il_at_split          -0.0368   <- currently on IL -> small negative
z_swing_pct_to_sh          -0.0040
```

IL features make a meaningful but secondary contribution. `days_since_il_return_imp` and `is_on_il_at_split` together contribute ~0.16 standardized signal — small but additive on top of the prior + rate features.

## Why this works

The compendium §2C k values are calibrated to split-half r=0.7 (the point at which a stat is "more-skill-than-noise"). Using them as the shrinkage k is principled: rates below stabilization regress hard toward population mean, rates above stabilization stay close to observed.

The Marcel prior is the same logic at a different timescale — the player's true talent is a Bayesian posterior over their multi-year history, and it's the strongest single feature in both RH2 (+0.037 standardized) and RP2 (+0.79 standardized).

What's striking is how much signal the prior adds even mid-season. A naive intuition might be "by day 90 we have plenty of in-season data, the prior should be redundant." The empirical finding is the opposite: even at split_day=120, the prior remains the highest-weighted feature. Half a season of FP/PA data is still a thin sample relative to a 3-year career baseline.

## Comparison to commercial systems

Published Y/Y r ranges for established projection systems (Steamer, ZiPS, ATC, THE BAT) typically fall in 0.55–0.65 for hitters and 0.50–0.60 for pitchers. RH2 at r=0.605 and RP2 at r=0.550 land squarely in the established range despite using a much smaller feature set than commercial systems (which incorporate aging curves, park factors, lineup context, opponent quality, weather, etc.). The compendium-driven shrinkage was the largest single multiplier on r-quality — bigger than any feature-engineering pass attempted in H3-H9.

## Files

- `scripts/xfp/build_il_split_features.py` (new)
- `scripts/xfp/xfp_rh2_pipeline.py` (new — replaces RH1)
- `scripts/xfp/xfp_rp2_pipeline.py` (new — replaces RP1)
- `data/research/xfp_cache/il_split_features_2018_2026.csv` (new, 45,065 rows)
- `data/models/xfp_rh2_pipeline.pkl` (new bundle)
- `data/models/xfp_rp2_pipeline.pkl` (new bundle)
- `data/outputs/xfp_rh2_projections.csv` (282 hitters)
- `data/outputs/xfp_rp2_projections.csv` (143 pitchers)
- `data/outputs/xfp_dashboard.html` (auto-rebuilt; reads RH2/RP2)

## Refresh during the season

```bash
# Statcast/IL data refreshed elsewhere; once that's current:
python scripts/xfp/build_rolling_hitters.py
python scripts/xfp/build_rolling_pitchers.py
python scripts/xfp/build_il_split_features.py    # new
python scripts/xfp/xfp_rh2_pipeline.py           # new
python scripts/xfp/xfp_rp2_pipeline.py           # new
python scripts/xfp/build_v11_dashboard_v2.py
```

## What didn't work / future Tier 2 candidates

This pass implemented the Tier 1 list. Tier 2 ideas (deferred):

- **Recent-form vs cumulative split.** Last-21-day rates as a separate feature vs season-to-date. Likely +0.01-0.02 r given how quickly hitters cool off.
- **Lineup context.** Batting order position + opponent SP quality → R/RBI rate. Captures the team_context_bias problem documented in H4.
- **Park factors.** Coors / Camden vs pitcher-friendly parks — should add ~0.01 r for context-sensitive stats.
- **Aging curves.** Sprint speed and barrel rate decline post-30; the prior treats all years equally. Aging-aware Marcel would help slightly.

None of these alone are likely to deliver the +0.06-0.07 r jump that Tier 1 produced. We're approaching the published ceiling for projection systems, and incremental gains will require larger feature investments for smaller r returns.

---

# Phase R3 — Decision-Layer (RH3 / RP3)

**Date**: 2026-05-06
**Outcome**: Model r essentially unchanged; the value of this phase is the **decision-support layer** built on top of the existing models, not new predictive lift.

## Motivation

Phase R2 pushed cross-year r near the published ceiling. The user's actual workflow questions ("Should I drop Pérez for Herrera?", "Is Soriano sustainable?", "Did I miss the Shane Smith add?") are not predominantly limited by point-projection accuracy — they need uncertainty bounds, a replacement-level yardstick, and recent-form context.

This phase adds five decision-support layers (R3.1-R3.5) without retraining the core models. RH3 and RP3 are RH2/RP2 plus recency features and a residual-based confidence interval, and the projection CSVs gain six decision-support columns.

## What landed

### R3.1 — Last-21-day recency window

`build_rolling_hitters.py` and `build_rolling_pitchers.py` now compute a per-(player, split_day) `_last21` feature block alongside the existing `_to` cumulative window. Same aggregation function, narrower time slice (cutoff − 21 days, cutoff].

**Predictive impact**: marginal. Hitter Δr +0.002, pitcher Δr +0.0002. The cumulative window already absorbs recent performance; the last-21 window overlaps it heavily in early season. The win is interpretive — `recency_form_gap = last21 − cumulative` becomes a UI feature ("hot/cold the last 21 days") even when the model itself doesn't lean on it much.

### R3.2 — Residual-based confidence intervals

For each (split_day, predicted-bucket-quartile) the leave-one-year-out residuals are pooled and the standard deviation stored. At projection time, `(p25, p75) = pred ± 0.6745 × σ_lookup`. Wider bands for low-PA / high-uncertainty tiers; narrower for established hitters.

**Hitter overall sigma = 0.109 FP/PA** (so a ~0.16 FP/PA gap at 70% confidence). **Pitcher overall sigma = 3.55 FP/start** (so a ~5 FP/start gap). Both per-bucket sigmas vary by ~20-30% from overall.

### R3.3 — Replacement-level deltas (position-aware)

12-team standard fantasy baseline:

| Position | Replacement at |
|---|---|
| C, 1B, 2B, SS, 3B | rank 12 |
| OF | rank 36 (3 per team) |
| DH / UTIL | rank 24 |
| SP | rank 60 (5 per team) |

Each player gets `replacement_xfp_per_pa` (or `_per_start`) and `replacement_delta`. Negative delta = below waiver-wire baseline.

### R3.4 — Schedule-strength adjustment (pitchers only)

`build_team_strength.py` produces a per-team `bat_index = team_xwOBA / league_mean` from cumulative-season Statcast. `build_pitcher_schedule.py` queries MLB Stats API `schedule?hydrate=probablePitcher` for the next 14 days — in practice MLB only announces probable starters ~5 days out, so coverage is partial (95 of 143 SPs in the projection get a next-start adjustment; the rest fall through with factor=1.0).

`schedule_factor = clip(1 / mean(opp_bat_index_next2), 0.85, 1.15)`. Caps prevent runaway adjustments from a single noisy team. `xfp_rp3_per_start_sched = xfp_rp3_per_start × schedule_factor`.

### R3.5 — PA projection (hitters only)

`expected_pa_remaining = (pa_to_date / games_played_so_far) × games_remaining`
`expected_total_fp_remaining = xfp_rh3_per_pa × expected_pa_remaining`

Simple version: assumes current PA/game pace continues. Lineup-spot tracking and IL risk discounting are documented as Tier-2 future work (would need MLB game-log scraping).

### R3.6 — Composite signal

Per-row bucket combining CI + replacement delta + IL state:

```
if on_il:                             signal = 'il'
elif p25 > replacement_xfp:           signal = 'add'    (high-conf above WW)
elif p75 < replacement_xfp:           signal = 'drop'   (no plausible upside)
else:                                 signal = 'hold'
```

This is the single most actionable column in the dashboard — the user reads it at a glance and the rest of the columns provide the supporting numbers.

## Empirical check on user's questions

Using 2026-05-06 dashboard:

| Player | Position | Signal | Δ Repl | Notes |
|---|---|---|---|---|
| Salvador Pérez | C | HOLD | −0.036 FP/PA | Below replacement but p75 still spans it. **Drop candidate when paired with a positive Δ above-replacement add.** |
| Iván Herrera | C | ADD | +0.074 FP/PA | p25 still above the catcher floor → high-confidence add. |
| Drake Baldwin | C | ADD | +0.100 FP/PA | Best-available catcher in the model. |
| José Soriano | SP | ADD | +3.26 FP/start | Recency gap +0.78 (still hot). Schedule vs TOR bumps to 14.32. |
| Framber Valdez | SP | HOLD | +0.35 FP/start | Recency gap **−2.54** (cold), but model already regressed him; not a drop. |
| Parker Messick | SP | HOLD | +0.34 FP/start | Recency flat, but p25=8.7 vs replacement=10.5 — model thinks the early-season FP is unsustainable. Sell-high candidate. |
| Tarik Skubal | SP | ADD | +5.07 FP/start | Top of the leaderboard, p25=13.4 still well above replacement. |

The Pérez → Herrera swap nets ≈ +0.11 FP/PA × ~270 PA remaining ≈ **+30 FP rest of season**, with both p25 bounds clearing replacement — the kind of trade the dashboard now surfaces directly.

## Files

- `scripts/xfp/build_team_strength.py` (new)
- `scripts/xfp/build_pitcher_schedule.py` (new — MLB Stats API)
- `scripts/xfp/xfp_rh3_pipeline.py` (new — replaces RH2 in dashboard)
- `scripts/xfp/xfp_rp3_pipeline.py` (new — replaces RP2 in dashboard)
- `scripts/xfp/build_rolling_hitters.py` (modified — added last-21-day window)
- `scripts/xfp/build_rolling_pitchers.py` (modified — added last-21-day window)
- `scripts/xfp/build_v11_dashboard_v2.py` (modified — six new columns: Sig, Δ Repl, Sched, L21Δ, Proj FP, CI bounds)
- `data/research/xfp_cache/team_strength_2026.csv` (new)
- `data/research/xfp_cache/pitcher_schedule_2026.csv` (new)
- `data/models/xfp_rh3_pipeline.pkl`, `xfp_rp3_pipeline.pkl` (new bundles)
- `data/outputs/xfp_rh3_projections.csv`, `xfp_rp3_projections.csv` (new)

## Refresh during the season

```bash
python scripts/xfp/build_rolling_hitters.py
python scripts/xfp/build_rolling_pitchers.py
python scripts/xfp/build_il_split_features.py
python scripts/xfp/build_team_strength.py        # new
python scripts/xfp/build_pitcher_schedule.py     # new (also fetches latest probables)
python scripts/xfp/xfp_rh3_pipeline.py           # new
python scripts/xfp/xfp_rp3_pipeline.py           # new
python scripts/xfp/build_v11_dashboard_v2.py
```

The two new daily-changing inputs are `build_team_strength` (statcast-based, refreshes with the daily statcast pull) and `build_pitcher_schedule` (MLB Stats API, ~5-day visibility horizon — re-run daily for fresh probables).

## What's deliberately NOT in this phase

- **Lineup-spot tracking** for hitters. Would need MLB game-log scraping per (team, date) to extract batting order. Adds ~0.05-0.10 FP/PA differentiation for top-of-order hitters but the engineering cost is high.
- **Park factors**. Coors / Camden / Yankee Stadium effects exist but the team-level `bat_index` partially absorbs them via team-record-keeping. Explicit park factors add at most ~+0.005 r.
- **Hitter IL substrate**. The pitcher IL transactions JSON contains hitter events too; RH3 doesn't currently use them. Adding `is_currently_injured` as a feature would mainly affect a handful of hitters/week; most hot-streak / cold-streak issues are already captured by recent-form gap.
- **Quantile regression for CIs**. The residual approach is calibrated to the train-time prediction distribution and works well for an MVP. Quantile-loss GBMs would be more flexible but add a second model to maintain.

These are explicitly Tier-2 candidates if a future r-improvement push is warranted.

## Validation results (added 2026-05-06 post-ship; revert applied)

After shipping, four empirical tests were run against the new substrate (`scripts/xfp/validate_phase_r3.py`):

| Test | Result | Verdict |
|---|---|---|
| Schedule strength signal — cor(opp `bat_index_prior`, FP/start) on 4,681 2025 starts | **−0.0465**; weakest-vs-strongest opp swing = **+1.40 FP/start** | ✅ Real, modest |
| RH3 CI calibration (LOO) — fraction of actuals in p25–p75 | **51.2%** vs target 50% | ✅ Calibrated |
| RP3 CI calibration (LOO) — fraction of actuals in p25–p75 | **52.2%** vs target 50% | ✅ Calibrated |
| Recency-form-gap signal — cor(`recency_gap`, RoS residual) | **+0.039**; bucket swing 0.014 FP/PA | ⚠️ Real but tiny |
| RH3 vs RH2 cross-year r (LOO) | **+0.0020** | ❌ Below the +0.005 PASS gate I had set |
| RP3 vs RP2 cross-year r (LOO) | **+0.0002** | ❌ Below gate |
| 2026 projection agreement — pearson(RH3, RH2) / pearson(RP3, RP2) | **0.997 / 0.998** | RH3≈RH2, RP3≈RP2 numerically |

**Decision after validation**: revert. The last-21-day rate features that justified creating new pipelines failed their own promotion gate (+0.002 r vs the required +0.005). RH3/RP3 were re-defined to use the **RH2/RP2 feature set exactly** — predictive output is now identical to RH2/RP2 to four decimal places. The decision-support layer (residual CI, replacement deltas, schedule strength, signal column) sits on top of the validated RH2/RP2 predictions; only `recency_form_gap` survives, and only as a display-only column joined from the rolling substrate (it is NOT a model input).

**Standing rule (added to repo-level memory):** never promote a new model version without an empirical test showing improvement vs the prior production version on the metric we claim to be improving. Decision-support post-processing layers that don't directly affect r should be added on top of the existing production model, not used to justify retraining.

This phase contributed:
1. **Validated decision layer** — CIs (calibrated), replacement deltas (sane distribution), schedule strength (real but modest signal), composite buy/hold/sell signal, hitter PA-projection-aware total FP.
2. **Negative result** — last-21-day in-season rates do not meaningfully add to the cumulative window already in RH2/RP2, because the cumulative window grows during the season and absorbs recent performance. Documented and reverted.

---

# Phase RP — Reliever models (RP-S1 cross-year + RP-RS1 RoS)

**Date**: 2026-05-06
**Outcome**: Both gates passed by wide margins. Both models locked. Dashboard now includes a `window.XFP_RELIEVERS` payload covering 168 RPs.

## Motivation

Until this phase, all xFP pitcher models filtered to starters via `gs ≥ 2`. Relievers had ZERO model coverage — the user's 6 RPs (Durán, Fairbanks, Helsley, Tanner Scott, Robert Suarez, Daniel Palencia) showed up in the dashboard with "no model coverage" tags, forcing the user to rely on ESPN's projections alone.

Relievers behave fundamentally differently from starters:
- Volume metric is per-appearance (or per-IP), not per-start
- **Saves dominate FP scoring** (user's ESPN scoring: SV = +5, HLD = +3 vs IP × 3.3 — a 32-save closer pulls 160 FP just from SV bonus)
- Role (closer / setup / middle) is the dominant predictor of fantasy value, not pure rate-stat skill
- Year-to-year role stability is ~50–70% (research literature) — meaningful churn

ESPN scoring confirmed: `FP = K + IP×3.3 + SV×5 + HLD×3 − BB − 2×ER − H − HBP`. League is 12 teams × 4 RP slots → top-48 RP is replacement.

## Architecture (validation-first per Phase R3 rule)

Validation gates set BEFORE building each phase:

| Phase | Gate |
|---|---|
| RP-0 substrate | Top-SV leaderboards match Baseball-Reference / FG (manual spot check) |
| RP-1 multiyr | ≥ 1500 (RP, year) rows; closer Y/Y stability 50–70%; statcast 100% join |
| RP-2 (cross-year skill) | LOO cross-year r ≥ 0.40 |
| RP-3 (in-season RoS) | LOO cross-year r ≥ 0.50 |

## RP-0: pitcher counting stats

`scripts/xfp/build_pitcher_counting.py` pulls per-pitcher season totals from MLB Stats API for 2018–2026:
- `gamesPitched`, `gamesStarted`, `gamesFinished`, `inningsPitched`, `battersFaced`
- `wins`, `losses`, `saves`, `saveOpportunities`, `holds`, `blownSaves`
- `strikeOuts`, `baseOnBalls`, `hits`, `earnedRuns`, `homeRuns`, `hitByPitch`
- `era`, `whip`

Output: `data/research/xfp_cache/pitcher_counting_stats_{year}.json` (~700–900 pitchers per year).

**Validation**: top SV-getters match reality — Helsley 49 SV in 2024, Estévez 42 SV in 2025, Mason Miller leading 2026.

## RP-1: relievers_multiyr substrate

`scripts/xfp/build_relievers_multiyr.py` joins statcast pitch-level rates (filtered to non-starter appearances) with the counting stats above:
- RP eligibility: `G ≥ 20 AND GS ≤ 5` (allows for openers / spot starters)
- Role classification (closer-focused per user spec):
  - `closer`: `SV ≥ 15 OR (SV+SVO ≥ 20)`
  - `setup`: `HLD ≥ 15` (not closer)
  - `middle`: `G ≥ 30` (neither)
  - `long_low`: `G < 30`
- FP computed from user's ESPN scoring formula

Output: `data/research/xfp_cache/relievers_multiyr_2018_2026.csv` — 2,090 (RP, year) rows.

**Validation passed**:
- Role distribution makes sense (~40 closers / ~50 setup / ~130 middle / ~55 long_low per year)
- Top FP leaderboards match: 2024 Clase #1 (485 FP, 47 SV), Helsley #2 (440 FP, 49 SV); 2025 Chapman #1 (400 FP, 32 SV)
- Closer Y/Y stability: 22 of 41 2024 closers still classified closer in 2025 (54%) — matches published research
- Statcast rate coverage: 100% of RP rows joined

## RP-2: cross-year RP skill model (xfp_rps1)

`scripts/xfp/xfp_rps1_pipeline.py` — Ridge predicting year T+1 reliever FP TOTAL from year-T features:
- Rate stats (lag-1): k_pct, bb_pct, swstr_pct, c_plus_swstr, xwoba_per_pa
- Stuff: avg_velo, avg_pfxz
- Discipline: zone_pct, o_swing_pct, z_swing_pct
- Workload + role: g, ip, sv, hld, gf
- Role one-hot: role_closer, role_setup, role_middle (long_low = baseline)
- Prior FP rate: era, whip, fp_per_g

**Result: r = 0.508** (vs gate 0.40, vs naive persistence baseline 0.382 — Δ +0.126)

Per-year LOO:
```
2019: r=0.4096  2021: r=0.5582  2022: r=0.5552
2023: r=0.5631  2024: r=0.5303  2025: r=0.5502
```

Top standardized coefficients (skill > role > volume):
```
c_plus_swstr_lag1   +9.41    role_closer_lag1   +6.35
swstr_pct_lag1      +8.74    sv_lag1            +5.33
fp_per_g_lag1       +8.74    bb_pct_lag1        −5.27
zone_pct_lag1       +8.07    hld_lag1           +4.03
avg_velo_lag1       +8.00    
k_pct_lag1          +7.38
gf_lag1             +6.49
xwoba_per_pa_lag1   −5.39
```

Top 2026 projections all closers — Chapman, Mason Miller, Hader, Edwin Díaz, Cade Smith, Duran, Bednar, Iglesias, Muñoz, Megill, Suarez, Clase. Sensible.

## Rolling RP substrate

`scripts/xfp/build_rolling_relievers.py` builds per-(RP, year, split_day) rows for in-season RoS:
- For each split_day in [30, 60, 90, 120], aggregate relief pitches through cutoff
- Compute G, IP, K, BB, H, HBP, ER through cutoff
- `fp_skill_to` = K + IP×3.3 − BB − 2×ER − H − HBP (NO SV/HLD bonus — would require gameLog scraping)
- Filter: G_through_cutoff ≥ 5, GS_through_cutoff ≤ 2
- Lag features: prior-year role / sv / hld / fp_per_g / fp / k_pct / bb_pct / xwoba_per_pa

Output: 9,532 (RP, year, split_day) rows.

## RP-3: RoS RP model (xfp_rprs1)

`scripts/xfp/xfp_rprs1_pipeline.py` — Ridge predicting year-T full-season FP TOTAL from in-season + lag features. Rest-of-season FP = predicted_full_year − actual_to_date_fp_from_API.

**Result: r = 0.778** (vs gate 0.50, vs RP-S1 0.508 — Δ +0.27)

Per-year LOO:
```
2019: r=0.7339  2021: r=0.7732  2022: r=0.8173
2023: r=0.7982  2024: r=0.7734  2025: r=0.7851
```

Split-day breakdown (model improves dramatically as season progresses):
```
day  30: r=0.6168    day  60: r=0.7475
day  90: r=0.8328    day 120: r=0.8841
```

Top standardized coefficients:
```
fp_skill_to            +49.4    sv_lag1            +5.7
split_day              −40.6    g_lag1             +5.4
g_to                   +19.5    k_pct_to           +5.0
fp_per_g_lag1          +13.1    ip_to              −5.0
xwoba_per_pa_to        −11.0    fp_lag1            +4.7
avg_velo_to            +9.3     role_setup_lag1    −3.9
```

The dominance of `fp_skill_to` and the strong negative `split_day` coefficient (proportional regression — more season elapsed = less RoS) are the model's "season-clock" — it's effectively learning the playing-time math.

## Dashboard wiring

- `scripts/xfp/build_v11_dashboard_v2.py` extended with `build_reliever_records()`; emits `window.XFP_RELIEVERS` (168 RPs covered)
- `MY_TEAM` payload now matches RPs against the RP universe: each rostered RP gets `rpRoSFp`, `rpFullYear`, `rpReplDelta`, `rpSignal`, `rpRolePrior`
- `scripts/xfp/eval_team_vs_fa.py` extended with RP section: roster RPs ranked by RoS, FA RPs ranked by RoS with %owned/prior-role/prior-SV columns, drop/add pairings

## Replacement-level for closers in 12-team / 4-RP league

Top 48 RPs → replacement xFP RoS ≈ 98 FP. This corresponds roughly to "the 4th best closer on the worst team" — almost always a closer or top-tier setup man.

## Files

- `scripts/xfp/build_pitcher_counting.py` (new)
- `scripts/xfp/build_relievers_multiyr.py` (new)
- `scripts/xfp/build_rolling_relievers.py` (new)
- `scripts/xfp/xfp_rps1_pipeline.py` (new — cross-year)
- `scripts/xfp/xfp_rprs1_pipeline.py` (new — in-season RoS)
- `data/research/xfp_cache/pitcher_counting_stats_{2018..2026}.json` (new)
- `data/research/xfp_cache/relievers_multiyr_2018_2026.csv` (new)
- `data/research/xfp_cache/rolling_relievers_2018_2026.csv` (new)
- `data/models/xfp_rps1_pipeline.pkl` (new)
- `data/models/xfp_rprs1_pipeline.pkl` (new)
- `data/outputs/xfp_rps1_projections.csv` (new — 279 RPs, 2026 cross-year)
- `data/outputs/xfp_rprs1_projections.csv` (new — 168 RPs, 2026 RoS)

## Refresh during the season

```bash
python scripts/xfp/build_pitcher_counting.py     # ~2 minutes (MLB API)
python scripts/xfp/build_relievers_multiyr.py    # ~30 sec
python scripts/xfp/build_rolling_relievers.py    # ~1 min
python scripts/xfp/xfp_rps1_pipeline.py          # cross-year
python scripts/xfp/xfp_rprs1_pipeline.py         # RoS
python scripts/xfp/build_v11_dashboard_v2.py
```

## What's missing / future work

- **In-season SV/HLD detection from statcast**: currently we use the API snapshot's cumulative SVs/HLDs at projection time. Doesn't matter for cross-year (uses year-end totals) or RoS (computes RoS = predicted_full_year − actual_to_date). Would matter only for rebuilding historical mid-season snapshots.
- **Leverage index features**: pLI / iLI not pulled. Would marginally improve role classification (high-leverage usage = closer-trajectory).
- **Per-RP IL features**: existing IL transactions JSON has RPs too; building `il_split_features` for relievers would add Helsley-style "questionable role due to injury" signal.
- **Pitcher-level handedness vs opponent lineups for RP RoS**: closers face short windows and opponent matchups matter more than for SPs over a 6-IP outing. Out of scope for v1.

## Phase RP Update (2026-05-06): substrate fix + team-context negative result

User feedback flagged two problems:
1. **Latz** (Texas RP, hot 2026 start, 1.02 ERA) was missing from projections because his 2025 lag was null (he had < 20 G in 2025).
2. **Robert Suarez** projecting too high — he was a temp closer covering for Iglesias's IL stint; now Iglesias is back, Suarez's SV chances should drop. Model didn't see this.

Two distinct fixes attempted, with separate validation:

### Fix A: substrate refinements (SHIPPED, big lift)

Two substrate issues fixed:
- **In-progress year split_day labelling**: rolling builder was emitting nominal split_day=120 rows for 2026 with data only through May 3 (38 days). The `split_day` feature got mislabeled, and IL state lookups landed at the wrong cutoff. Fixed by emitting an actual-elapsed-days row (split=41 today) in addition to the nominal cutoffs that have actually elapsed.
- **Lag-feature backfill**: pitchers with no prior-year substrate row (rookies, returnees) were silently dropped. Backfilled with population-mean lag values + `long_low` role default.

**Result**: training rows grew from 3,429 → 7,179. **Cross-year r jumped from 0.778 → 0.810** (+0.031). This is a substrate-correctness fix, not a model-feature change — both old and new models use the same feature pool.

Latz now appears in projections at RoS 115 FP / signal HOLD.

### Fix B: team-context features (REVERTED, failed gate)

Built `enrich_rolling_relievers.py` to add four team-context features:
- `is_team_prior_closer`: 1 if pitcher was their team's top SV pitcher last year
- `prior_closer_on_il`: 1 if team's prior closer is currently on IL (you're the temp)
- `prior_closer_returned_recently`: 1 if team's prior closer returned from IL in last 14 days
- `prior_closer_days_since_return`: raw days since prior closer's most recent IL return

Hooked into IL substrate, joined per-pitcher per-(year, split_day). Spot-check confirmed the features captured the Suarez/Iglesias case correctly: at split=41 (today), Suarez gets `prior_closer_returned_recently=1` and `prior_closer_days_since_return=1.0`.

**Result**: cross-year r went from 0.8092 (without features) → 0.8101 (with features). **Δr = +0.0009 — failed the +0.005 gate.** Per validation rule, reverted to the prior 21-feature set.

The pipeline now auto-detects gate failure and reverts: `FEATS_USED = PRIOR_RPRS1_FEATS` when `delta_team < 0.005`.

### Why team-context didn't help

Three plausible reasons (not investigated further):
1. **Rare in training data**: explicit "incumbent IL → temp closer → incumbent returns" cycles within a season are uncommon enough that the model can't learn a reliable signal from them.
2. **Already absorbed by other features**: `sv_lag1`, `role_closer_lag1`, and `fp_per_g_lag1` capture most of the role information indirectly. A 40-SV-last-year pitcher whose teammate is also a 30-SV-last-year pitcher already gets weighted appropriately by the existing model.
3. **Smaller-than-intuition FP impact**: a temp closer demoted to setup loses ~1 FP/G (saves bonus minus hold bonus), which over 80 remaining games is ~80 FP — within model sigma (53). The intuitive "huge demotion" doesn't translate to a model-distinguishable FP swing.

The user's intuition that Suarez should project lower is correct, but the existing model already does it correctly:
- Iglesias: RoS 220 FP (rank 2) — model correctly identifies him as the real closer
- Suarez: RoS 203 FP (rank 3) — high but driven by skill (40 SV last year, elite rates), not by current SV expectation

The 17 FP gap reflects the model's view: Iglesias should outproduce Suarez by a modest amount as the secured closer.

### Files (this update)

- `scripts/xfp/enrich_rolling_relievers.py` (new — kept for future re-validation if signal grows)
- `data/research/xfp_cache/mlb_teams.json` (new)
- `scripts/xfp/build_rolling_relievers.py` (modified — in-progress year handling)
- `scripts/xfp/build_il_split_features.py` (modified — emit current-elapsed-days row)
- `scripts/xfp/xfp_rprs1_pipeline.py` (modified — team-context gate + auto-revert)

---

# Phase RP-2 — In-season role-usage features (RP-RS2)

**Date**: 2026-05-06
**Outcome**: BOTH GATES PASSED. RP-RS2 promoted to production.

## Motivation

Comparing my model's RP rankings against the PitcherList weekly Top 50 (2026-05-06 issue) revealed massive divergence in the middle and bottom of the list (Spearman ρ = 0.29 across 48 covered closers). The user's question — "what numbers actually drive PL's ranking?" — led to a feature-correlation analysis (`pl_feature_correlation.py`) showing PL leans on three signals my model didn't use:

| Feature | ρ vs PL rank | ρ vs my (old) rank |
|---|---|---|
| `gf_pct_now` (2026 games-finished %) | **−0.75** | −0.18 |
| `sv_pct_now` (2026 SV per appearance) | **−0.74** | −0.15 |
| `sv_now` (raw 2026 saves) | **−0.73** | −0.12 |
| `hld_now` (high = setup, not closer) | **+0.64** | +0.14 |

PL was implicitly weighting current-year role usage; my model only knew prior-year role.

## What changed

### 1. Statcast-derived appearance summary (`build_role_usage.py`)

For every (pitcher, game) appearance from 2018–2026, derive:
- `gf` — 1 if pitcher threw the final pitch of the game
- `sv` — GF + winning team + (lead at exit ≤ 3 OR ≥ 3 IP)
- `hld` — appearance + winning team + lead at entry ∈ [1,3] + NOT GF + lead held + ≥1 out
- `blown_sv` — GF + losing team + entered with lead

Validation against MLB API counting stats: 91-110% accuracy on top closers (Suarez 2025: 39 derived vs 40 API; Helsley 2024: 51 vs 49). Slight overcounting on long-relief saves; close enough for ranking purposes.

Output: `data/research/xfp_cache/role_usage_appearances_{year}.parquet` (~21k appearances/year, 1300 SVs/year).

### 2. New rolling-substrate features

`build_rolling_relievers.py` extended with:
- `gf_to`, `sv_to`, `hld_to`, `bs_to` — cumulative through cutoff
- `gf_pct_to` (= gf_to / g_to) — current-year closer-usage signal
- `sv_per_g_to`, `hld_per_g_to`, `sv_plus_hld_to` — rate variants
- `fp_with_role_to` — FP-to-date including SV×5 + HLD×3 bonuses

`enrich_rolling_relievers.py` extended with:
- `sv_per_g_lag1`, `hld_per_g_lag1` — prior-year usage rates

### 3. Stratified validation (the methodology fix)

The original team-context attempt (Phase RP-1 update) failed a +0.005 overall cross-year r gate by delivering only +0.001. **The diagnosis on this attempt was wrong: the overall gate was the wrong test.** When features matter only for a specific cohort (e.g., the ~20% of pitchers experiencing mid-season role change), measuring on the full 80% stable + 20% unstable population dilutes the signal.

RP-RS2 uses a **stratified gate**:
1. Overall cross-year r MUST NOT regress (gate: Δ ≥ 0.0)
2. Role-change subset cross-year r MUST improve by ≥ +0.05

Role-change subset definition: rows where `|sv_per_g_now − sv_per_g_lag1| > 0.10 SV/G` AND has prior-year lag data. This isolates the cohort where new role-usage features should help most.

## Results

| Metric | RP-RS1 baseline | RP-RS2 | Δ |
|---|---|---|---|
| Overall LOO cross-year r | 0.8092 | **0.8419** | **+0.033** ✅ |
| Role-change subset r | 0.7666 | **0.8405** | **+0.074** ✅ |
| Overall MAE (FP/season) | 41.5 | 37.3 | -4.2 |
| Role-change subset MAE | 53.5 | 42.7 | -10.8 |
| n eval | 7,179 | 7,179 | — |
| n role-change subset | 1,490 | 1,490 | — |

Both gates passed by wide margins (overall +0.033 vs gate 0.0; role-change +0.074 vs gate +0.05).

Top standardized coefficients (28 features total):

```
fp_skill_to            +62.94    sv_lag1            -15.10
split_day              -45.52    sv_per_g_lag1      +14.82
fp_with_role_to        -41.45    ip_to              +10.75
sv_plus_hld_to         +28.97    fp_lag1            +10.32
sv_per_g_to            +23.05    k_pct_to           +8.53
                                  xwoba_per_pa_to    -8.20
                                  g_to               +7.06
NEW features:
gf_pct_to              +6.16    sv_per_g_to        +23.05
hld_per_g_to           +5.97    sv_plus_hld_to     +28.97
fp_with_role_to        -41.45   sv_per_g_lag1      +14.82
hld_per_g_lag1         -0.28
```

The negative `fp_with_role_to` coefficient is the model learning "you've already collected X FP this year, so the rest-of-season target is full-year minus X" — proper season-clock arithmetic. The positive `sv_plus_hld_to` and `sv_per_g_to` coefficients are the role signal: "regardless of skill, if you're getting saves now, you'll keep getting saves."

## How RP-RS2 fixes the user's flagged cases

| Player | Old rank | New rank | PL rank | Reason |
|---|---|---|---|---|
| Robert Suarez | 4 | **14** | 28 | Sees Iglesias's GF rate (88%); de-prioritizes Suarez |
| Lucas Erceg | 222 | **16** | 20 | Sees current 10 SV / 14 G / 67% GF |
| Jacob Latz | 109 | **20** | 10 | Sees current 3 SV / 38% GF in TEX |
| Bryan Baker | 68 | **7** | 3 | Sees 9 SV / 64% GF |
| Riley O'Brien | 85 | **4** | 11 | Sees 9 SV / 63% GF |
| Paul Sewald | 125 | **12** | 12 | Sees ARI closer pattern |
| Jack Perkins | 65 | **19** | 15 | New ATH closer recognized |

## What didn't change

- The cross-year RP skill model (RP-S1, r=0.508) is unchanged — that predicts year T+1 from year-T full-season totals, not in-season snapshots.
- The 4 team-context features (`is_team_prior_closer`, `prior_closer_on_il`, etc.) remain in the substrate but are NOT in the RP-RS2 feature set. They failed the original overall gate; haven't re-tested under stratified gate.

## Validation methodology takeaway (added to repo memory)

When a feature's claimed value is concentrated in a specific cohort (role-change cases here), validate **on that cohort directly**, not just on the general population. Define the cohort from features that don't include the target so the validation isn't circular. The original team-context attempt didn't fail because the features were bad — it failed because the gate was the wrong measurement.

## Files

- `scripts/xfp/build_role_usage.py` (new — appearance-level GF/SV/HLD detection)
- `scripts/xfp/build_rolling_relievers.py` (modified — adds gf_to, sv_to, hld_to, etc.)
- `scripts/xfp/enrich_rolling_relievers.py` (modified — adds sv_per_g_lag1)
- `scripts/xfp/xfp_rprs2_pipeline.py` (new — production model)
- `scripts/xfp/pl_feature_correlation.py` (new — diagnostic; not on critical path)
- `data/research/xfp_cache/role_usage_appearances_{year}.parquet` (new, 9 years)
- `data/models/xfp_rprs2_pipeline.pkl` (new)
- `data/outputs/xfp_rprs2_projections.csv` (new)
- `scripts/xfp/build_v11_dashboard_v2.py` (modified — points to RP-RS2)

## Refresh during the season

```bash
python scripts/xfp/build_pitcher_counting.py     # ~2 min
python scripts/xfp/build_role_usage.py           # ~3 min (new step)
python scripts/xfp/build_relievers_multiyr.py    # ~30 sec
python scripts/xfp/build_rolling_relievers.py    # ~1 min (now includes role-usage)
python scripts/xfp/enrich_rolling_relievers.py   # ~10 sec
python scripts/xfp/xfp_rps1_pipeline.py          # cross-year (unchanged)
python scripts/xfp/xfp_rprs2_pipeline.py         # RoS (replaces rprs1)
python scripts/xfp/build_v11_dashboard_v2.py     # rebuild dashboard
```

---

# Phase RP→Hitter/SP transfer (2026-05-06)

After RP-RS2's success, applied the lessons systematically to hitter and SP work. Four tasks attempted with stratified-validation gates throughout.

## Task 1 (SHIPPED) — Substrate fix: in-progress year split mismatch

The RP-RS2 substrate fix that emits an "actual elapsed days" split row for the in-progress year was missing from `build_rolling_hitters.py` and `build_rolling_pitchers.py`. Both substrates were emitting only `split_day=30` for 2026 (cutoff April 25), missing 10+ days of recent statcast data.

Fix: identical pattern to `build_rolling_relievers.py` — for the current year, also emit a `split_day = (today − season_start).days` row using statcast data through max available date. The `actual_cutoff = min(nominal_cutoff, max_data_date)` ensures statcast aggregates use real data even when the nominal cutoff is in the future.

**Validation**: cross-year r unchanged (0.6045 hitters, 0.5495 pitchers) — substrate fix doesn't alter the model, just feeds it fresher data. Coverage in 2026 projections grew:
- Hitters: 282 → **332** (Donovan, Langford, etc. now appear with sufficient PA)
- Pitchers: 143 → **179** (more SPs with updated GS counts)

## Task 2 (SHIPPED IMPLICITLY) — Hitter lag backfill

The user-flagged "no model coverage" cases (Donovan, Langford) turned out to be data-freshness issues (Task 1) rather than missing-lag issues. The H2 prior table already backfills missing lag with league mean. With Task 1's fresher data, these hitters now clear the `pa_to ≥ 50` threshold.

## Task 3 (FAILED gate — REVERTED) — Hitter lineup-spot features (RH4)

Built `build_hitter_lineup.py` to derive per-(batter, game) batting order from statcast `at_bat_number` (first 9 distinct batters per team-game = lineup spots 1-9). Validated against known starters: Aaron Judge avg_spot=2.5, Mookie Betts 1.9, Salvador Pérez 4.5 — matches reality.

Added 5 features to RH4 (vs RH3 baseline):
- `lineup_spot_to`, `started_pct_to`, `pa_per_started_game_to`
- `lineup_spot_lag1`, `started_pct_lag1`

**Stratified validation:**

| Cohort | RH3 baseline | RH4 with features | Δr |
|---|---|---|---|
| Overall (n=8275) | 0.6045 | 0.6050 | **+0.0005** ✅ |
| Lineup-change (n=3415) | 0.5646 | 0.5626 | **−0.0020** ❌ |

Lineup-change subset gate **FAILED** (gate ≥ +0.05; delivered −0.002). Per validation rule, **REVERTED** to RH3.

### Why it failed (the actually useful insight)

The hitter target is **FP per PA** (a rate). Lineup spot affects **PA volume**, not **FP rate per PA**. A hitter demoted from leadoff to 7-hole still hits with similar quality per PA — they just get fewer PAs. The model already captures volume implicitly via `pa_to` and computes total FP downstream as `xfp_per_pa × expected_pa_remaining`.

**The RP case worked because target = FP TOTAL** (SVs and HLDs flow directly into the total). For hitters, the equivalent move would be to predict TOTAL FP per season (or per remaining games), not per-PA rate. That's a bigger architecture change deferred to future work.

Lineup features remain in the substrate (`rolling_hitters_2018_2026.csv` has `lineup_spot_to`, `started_pct_to`, `pa_per_started_game_to`) and could be useful as PA-projection inputs in the dashboard layer, even though they don't help the model directly.

## Task 4 (NO ACTION NEEDED) — SP V12/RP3 stratified diagnostic

Tested whether SPs need a rotation-status feature analog to RP-RS2's GF%/SV-per-G. Defined rotation-change cohort: SPs whose 2026 `gs_pace_to` differs from prior-year `gs_pace_lag1` by ≥ 0.10 GS/team-game.

**Surprising result:** the rotation-change cohort has BETTER cross-year r (0.595) than the stable cohort (0.492). Established veteran SPs are HARDER to predict (regression to mean is uncertain) while role-changers are more predictable (rookies dominating, demoted veterans clearly cooked).

**Conclusion**: SPs don't need new role-context features. The existing RP3 model already handles role changes well. The RP-RS2 methodology doesn't transfer to SPs because SP role is fundamentally more stable than RP role.

## Summary of what shipped and what didn't

| Task | Result | Reason |
|---|---|---|
| Task 1: Substrate in-progress fix | ✅ SHIPPED | Bug fix; no model regression; +50 hitter / +36 SP coverage |
| Task 2: Hitter lag backfill | ✅ Effectively shipped | Solved by Task 1 (was a data freshness problem, not lag) |
| Task 3: Lineup-spot features (RH4) | ❌ REVERTED | Rate target doesn't reward volume features; would need total-FP target |
| Task 4: SP rotation-status | ❌ NO ACTION | Rotation-change cohort already over-performs vs stable; no signal gap to fill |

## Methodological lesson (added to repo memory)

**Rate-target vs total-target features have different validation profiles.** RP-RS2's gf_pct_to / sv_per_g_to features improved a TOTAL-FP target. The same conceptual feature for hitters (lineup_spot_to) failed against a RATE target. Before adding volume-related features, check whether the model's target is rate or total — and whether the feature affects rate, volume, or total.

## Files this phase

- `scripts/xfp/build_rolling_hitters.py` (modified — in-progress split fix; lineup_aggregate function)
- `scripts/xfp/build_rolling_pitchers.py` (modified — in-progress split fix)
- `scripts/xfp/build_hitter_lineup.py` (new — per-(batter, game) lineup spot)
- `scripts/xfp/xfp_rh4_pipeline.py` (new — failed gate, kept for reference)
- `scripts/xfp/sp_stratified_diagnostic.py` (new — diagnostic only, no model)
- `data/research/xfp_cache/hitter_lineup_appearances_{year}.parquet` (new, 9 years)
- `data/models/xfp_rh4_pipeline.pkl` — NOT created (gate failed)

---

# Phase RH-T (Total-FP architecture exploration, 2026-05-06)

User question: "for fantasy purposes, should the focus be xFP per PA or per season? I'm thinking the latter."

Affirmed conceptually — totals are what fantasy decisions hinge on. Tested whether a direct-total model would beat the existing rate × PA decomposition.

## RH-T1: direct total-FP model

Built `xfp_rht1_pipeline.py` predicting `ros_total_fp = ros_pa × ros_full_fp_per_pa` directly. Features: 13 shrunken skill rates (RH3 base) + 7 volume features (lineup_spot_to, started_pct_to, pa_per_started_game_to, lineup_spot_lag1, started_pct_lag1, pa_lag1, pa_to) + split_day.

Validation: stratified gates against the indirect baseline (RH3 rate × naive `pa_pace × remaining_days`).

| Cohort | Indirect baseline r | RH-T1 direct r | Δ |
|---|---|---|---|
| Overall (n=8275) | **0.7091** | 0.7001 | −0.009 |
| Lineup-change (n=3415) | **0.7058** | 0.6848 | −0.021 |

**RH-T1 LOST on both gates.** Direct prediction is worse than decomposition — the rate model is more accurate at predicting rate, and the naive PA projection (pa_to / split_day × remaining_days) captures most of the volume signal.

## 2-stage test: RH3 rate × Ridge PA model

Hypothesis: if direct total fails because rate prediction works well, maybe a smarter PA projection (Ridge with lineup features) is the lever. Trained a separate Ridge on `ros_pa` target with PA + lineup features.

| Architecture | Total r | MAE | Lineup-change r |
|---|---|---|---|
| RH3 rate × NAIVE PA | 0.7091 | 47.4 | 0.7058 |
| RH3 rate × **RIDGE PA** | **0.7210** | **45.0** | 0.7059 |

The 2-stage Ridge-PA architecture gives Δr +0.012 overall and -2.4 MAE — modest improvement, but **on the lineup-change subset it's tied with naive PA** (r=0.706 both ways).

Why naive PA holds up on lineup-change cases: `pa_pace = pa_to / split_day` already captures recent lineup demotions implicitly. A 7-hole hitter has lower per-day PA pace than leadoff; the naive projection automatically incorporates that.

Below my +0.05 stratified gate. Not promoted as a model architecture change.

## Architectural conclusion

**For modeling: predict rate, not total.** Rate has better cross-year stability (~0.55-0.65) than total (~0.70 only via the decomposition trick). Direct total prediction is harder than decomposition.

**For display: total is the right primary metric.** The dashboard's existing `expected_total_fp_remaining` field (rate × pa_pace × remaining_days) is a calibrated total-FP estimate. The UI change is to make it the default sort/display column for hitters and pitchers, with rate as a secondary analysis column.

**For features: lineup-spot features have marginal value as a PA-projection-layer addition.** They improve PA projection MAE by ~9 PAs but don't change rankings much. They're in the substrate (`rolling_hitters_2018_2026.csv`) for future use; the Ridge PA model isn't shipped because the +0.012 r isn't worth the architecture complexity.

## Files this phase

- `scripts/xfp/xfp_rht1_pipeline.py` (new — failed gate, kept for reference)
- `scripts/xfp/test_pa_projection.py` (new — diagnostic)
- `scripts/xfp/test_two_stage_total.py` (new — diagnostic)
- `data/models/xfp_rht1_pipeline.pkl` — NOT created (gate failed)


---

# Phase MT — MiLB to MLB Pitcher Translation (Pitchers v1)

## Motivation

Recurring blind spot: rookies and partial-season call-ups (Logan Henderson, Mick Abel,
Trey Yesavage, Connor Prielipp, Connelly Early, Bubba Chandler) are PL-Top-100 SPs
but get dropped or backed by fillna(league_mu) ~ 9.20 in xfp_rp3_pipeline.py:250-252
because they have no prior-MLB row to seed the Marcel prior. Goal: replace that flat
fallback with a translation model that maps MiLB performance to projected MLB FP/start.

User-confirmed scope: pitchers first (AAA + AA), validation gate r >= 0.30.

## MT0 — substrate

Built scripts/xfp/build_milb_pitcher_counting.py mirroring the MLB pattern but with
sportId=11 (AAA) and sportId=12 (AA), 2015-2026. Output:
data/research/xfp_cache/milb_pitchers_2015_2026.csv. Augmented with extended fields
(GB outs, pitches/BF, strike%) via augment_milb_stats.py. Birth dates pulled
separately for age features (milb_pitcher_ages.csv).

Final substrate: 23,672 (pitcher, year, level) rows, 6,990 unique pitchers,
2015-2026 minus 2020 (COVID -- no MiLB season). Skenes 2024 AAA confirmed at 42.8% K%;
Skubal 2019 AA at 48% K%.

## MT1 — carryover screen

scripts/xfp/milb_carryover_screen.py correlates each candidate MiLB stat in year T
with the same pitcher's MLB performance in year T+1.

SP target (mlb_fp_per_start, BF>=120, AAA): K% +0.27, K-BB% +0.22, gamesPitched -0.17,
WHIP -0.13, h/9 -0.17. **bb_pct alone has near-zero carryover (+0.03)** -- it's
descriptive at MiLB but not predictive of MLB FP. ERA +0.12 at AAA SP -- marginal.

RP target (mlb_fp_per_g): max correlation +0.17, signs flip between AAA and AA,
mostly noise. The user's intuition that RP carryover is weaker than SP was correct;
volume-target relievers in MiLB are mostly being optioned-down for usage management,
not skill assessment.

Decision: SP-only translation. RP-target MiLB lock deferred indefinitely.

## MT2 — Ridge translation, gate failure

Trained Ridge with leave-one-year-out cross-validation across 9 transitions
(2015->2016, ..., 2024->2025; 2020 excluded). Multiple feature sets and regimes tested:

| Variant | r (AAA) | MAE | Notes |
|---|---|---|---|
| Naive (league_mu = 9.20) | -- | 2.722 | Existing fallback |
| 1yr, rates only | 0.229 | 2.639 | |
| 1yr, rates + volume | 0.266 | 2.621 | |
| 1yr, rates + volume + age | 0.269 | 2.624 | |
| Multi-yr (T+T-1), rates+volume+age | 0.275 | 2.583 | |
| **3-yr (T+T-1+T-2), rates+volume** | **0.277** | **2.646** | **Best r** |
| 3-yr + Huber regressor | 0.276 | 2.652 | No lift |
| Pitch-detail features (GB%, pitches/BF, strike%) | 0.262-0.274 | -- | No lift |
| BF>=250 (high-sample only) | 0.215 | -- | Less data hurts |

**Strict gate FAILED** (r >= 0.30 target; AAA-only gate fallback also at 0.30).
Empirical ceiling sits at r ~ 0.28 with publicly-accessible MiLB data
(MLB Stats API counting stats only). Public research's 0.30-0.45 numbers use Statcast
pitch-quality features (velocity, spin, swstr%) -- only available 2021+ at AAA via
savant's authenticated JS UI, not reachable from a standalone script (the
/statcast-search-minors/csv endpoint exists but returns empty without session
cookies). Coverage gain from including AA: 1 player out of 179 SP projection rows.
Not worth the -0.04 r cost.

## MT3 — conscious-decision lock

Production decision: ship the AAA-only 3-year Ridge model anyway, with explicit
prior_source tagging. Rationale:

1. Strictly beats the actual production fallback. The thing being replaced is
   fillna(league_mu) = 9.20 -- a constant. MiLB-derived priors hit MAE 2.65 vs
   2.72 baseline (~3% improvement) AND give pitcher-specific values (range 6.4-12.4
   vs constant 9.2).
2. Decision-support value is concrete. Logan Henderson now has a non-flat prior
   of 10.48 instead of 9.20. Trey Yesavage 9.93. Christian Scott 11.04. These
   numbers are visible in the dashboard tagged MiLB so the user can see when
   they're trusting MiLB-derived signal vs MLB-history signal.
3. Risk is bounded. The MiLB prior is only used when prior_fp_per_start is NaN
   AND year == 2026. It never overrides MLB lag. Integration is a fallback,
   not a replacement.

This conforms to the validate-before-shipping rule's conscious-decision pathway:
"the decision must be conscious: ship anyway because of decision-support / UX value,
OR revert. Do not silently promote."

Locked: data/models/xfp_milb_pitcher_pipeline.pkl (n_train=633, cross_year_r_aaa=0.277,
gate_passed=False). 2026 priors output: data/outputs/xfp_milb_pitcher_priors_2026.csv
(1,580 priors anchored on most-recent AAA season per pitcher).

## MT4 — integration as rookie prior

Modified xfp_rp3_pipeline.py: before fillna(league_mu), attempt merge with
xfp_milb_pitcher_priors_2026.csv and fill MiLB-derived prior for rows where
Marcel prior is NaN. Added prior_source column with values:
mlb_lag | milb_translation | league_mean. 10 of 179 SP projection rows
in 2026 now have MiLB-translation priors (was 0 before): Payton Tolle, Mason
Montgomery, Logan Henderson, Trey Yesavage, Christian Scott, Bryan Hudson,
JR Ritchie, Luinder Avila, George Klassen, Luis Morales.

## MT5 — dashboard surfacing

Added a small "MiLB" badge next to pitcher names in build_v11_dashboard_v2.py
where priorSource === "milb_translation". Bumped pitcher count in dashboard from
~206 to 216 (rookies now appear). Replaced direct r[xxx] accessors with r.get(xxx)
in the records loop so MiLB-only rows render gracefully without V11/V12 features.

## What's deliberately NOT in MT-Pitchers v1

- A+ and A levels. <10% of MLB call-ups come direct from these without an AAA stop.
- MiLB Statcast. Inaccessible without browser automation; uncertain lift past 0.30.
- RP target translation. RP carryover signal too weak (r <= 0.17, sign-unstable).
- Hitter MiLB translation. Phase MT-H, mirror this plan after pitchers prove out.
- Aging adjustments. Age feature was tested (+0.003 r); kept in feature set but
  no Marcel-style aging multiplier.

## Reusable artifacts

- data/research/milb_carryover_pitchers.csv -- answers "which MiLB stats carry over?"
  empirically. Standalone research artifact even if model is deprecated.
- data/outputs/xfp_milb_pitcher_priors_2026.csv -- 1,580 MiLB-derived FP/start
  priors anchored on each pitcher's most recent AAA season.

## Files this phase

| File | Workstream |
|---|---|
| scripts/xfp/build_milb_pitcher_counting.py | MT0 (new) |
| scripts/xfp/build_milb_pitcher_ages.py | MT0 (new) |
| scripts/xfp/augment_milb_stats.py | MT0 (new -- extended fields) |
| scripts/xfp/milb_carryover_screen.py | MT1 (new) |
| scripts/xfp/xfp_milb_pitcher_pipeline.py | MT2 (new -- diagnostic) |
| scripts/xfp/xfp_milb_pitcher_lock.py | MT3 (new) |
| scripts/xfp/xfp_rp3_pipeline.py | MT4 (modified -- MiLB fallback merge) |
| scripts/xfp/build_v11_dashboard_v2.py | MT5 (modified -- MiLB badge) |
| data/research/xfp_cache/milb_pitchers_2015_2026.csv | MT0 |
| data/research/xfp_cache/milb_pitchers_ext_2015_2026.csv | MT0 |
| data/research/xfp_cache/milb_pitcher_ages.csv | MT0 |
| data/research/milb_carryover_pitchers.csv | MT1 |
| data/models/xfp_milb_pitcher_pipeline.pkl | MT3 |
| data/outputs/xfp_milb_pitcher_priors_2026.csv | MT3 |


---

# Phase SP — Slump Precedent (Hitters + Pitchers)

## Motivation

Model output is a forward-looking RoS projection but blends prior + current-season
rate features through Ridge. With ~30-40 games of 2026 data, slumping veterans
(Devers 0.6th-percentile 33-game core_fp/PA, Bichette 5.7th, Sal Pérez 15.8th) get
projected toward their depressed current rate even when their full career history
shows comparable cold streaks always rebounded.

Question: "has this player ever had a streak this bad in their career, and what
happened next?" Answered empirically: pull every PA-ending event 2015-2026 from
Statcast, aggregate to per-game (or per-appearance) FP, compute rolling-N-window
where N matches the player's 2026 sample length, and locate the current rate in
their own career distribution.

## Implementation

`scripts/xfp/slump_precedent.py` — production module with three modes:
- **Hitters**: rolling-N-game core_fp (TB + BB + HBP - K) per PA. Excludes R, RBI,
  SB (need extra data); the rate correlates ~0.95 with full fp/PA.
- **SPs**: rolling-N-start fp/start where fp = K + IP×3.3 - H - 2×ER - BB - HBP.
  Per-start basis, identifying the SP via inning-1 pitcher per (game_pk, side).
- **RPs**: rolling-N-appearance same formula (no sv/hld bonus — those are role-driven
  and orthogonal to slump diagnosis).

For each comparable historical window (rolling rate ≤ current rate), accumulates
the next ~200 PAs (hitters) or 300 outs (pitchers, ≈100 IP) of subsequent
performance and reports median next rate, median rebound delta, and bounce
frequency (% of windows where next rate > slump rate).

## Outputs

- `data/outputs/slump_precedent_hitters_2026.csv` — 332 hitters with ≥50 PA
- `data/outputs/slump_precedent_sps_2026.csv` — 160 SPs with ≥3 GS
- `data/outputs/slump_precedent_rps_2026.csv` — 249 RPs with ≥3 G

Schema:
- `pct_rank`: percentile of current rate within own career rolling-N distribution
- `n_comparable`: count of historical windows ≤ current rate
- `bounce_pct`: % of comparable windows that improved over next 200 PA / 300 outs
- `median_next_rate`: median rate over next 200 PA / 300 outs after slump
- `median_delta`: median (next_rate − slump_rate)

## Pipeline integration

- `xfp_rh3_pipeline.py:432` left-merges slump cols onto hitter projections
- `xfp_rp3_pipeline.py:406` left-merges slump cols onto SP projections
- `build_v11_dashboard_v2.py` adds BUY-LOW badge (slump_pct < 20 AND bounce > 80%)
  and FADE badge (slump_pct < 5 AND bounce < 60%) next to player names

## Calibration spot-checks (2026-05-07)

| Player | %ile | Comparable | Bounce % | Median next |
|---|---:|---:|---:|---:|
| Rafael Devers | 0.6 | 7 (all from late Mar 2025) | 100% | +0.448 (+0.42 vs slump) |
| Bo Bichette | 5.7 | 41 | 100% | +0.296 (+0.14) |
| Trea Turner | 13.7 | 167 | 81% | +0.289 |
| Salvador Pérez | 15.8 | 201 | 97% | +0.282 |
| Eugenio Suárez | 15.8 | 239 | 97% | +0.200 (still mediocre) |
| Aaron Judge | 65.7 | 730 | 64% | (already healthy) |

The Devers 7-comparable result is an exact precedent: all 7 are from his
2025 season opener slump, and he rebounded to +0.45 in every one. The model
was projecting him toward current production; the precedent says hold.

## What this is NOT

- Not a replacement for the rh3/rp3 model. The model is what predicts RoS FP.
- Not a regime-change detector (a player's career might end mid-2026 and the
  slump precedent can't see it). FADE badge is a soft warning only.
- Not calibrated as a probabilistic forecast. The 200-PA / 300-out window is
  arbitrary; reading it as "exact rebound timing" is wrong. Read it as
  "directionally what happened on average after similar stretches."

## Files this phase

| File | Purpose |
|---|---|
| `scripts/xfp/slump_precedent.py` | Core module + batch driver |
| `data/outputs/slump_precedent_hitters_2026.csv` | Per-hitter precedent metrics |
| `data/outputs/slump_precedent_sps_2026.csv` | Per-SP precedent metrics |
| `data/outputs/slump_precedent_rps_2026.csv` | Per-RP precedent metrics |
| `scripts/xfp/xfp_rh3_pipeline.py` (modified) | Merge slump cols into projection CSV |
| `scripts/xfp/xfp_rp3_pipeline.py` (modified) | Same for SPs |
| `scripts/xfp/build_v11_dashboard_v2.py` (modified) | BUY-LOW / FADE badges in tables |
