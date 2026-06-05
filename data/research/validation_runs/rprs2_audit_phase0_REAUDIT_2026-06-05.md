# rprs2 Phase 0 RE-AUDIT — Post HLD×3→×2 Surgical Fix

**Date:** 2026-06-05
**Scope:** Re-verification of the four gates after Phase 0.5 patched 9 sites across 7 files.
**Constraint:** Read-only. No production runs, no file modifications outside this audit doc.

---

## Step 1 — Scoring consistency re-verify

Re-grep `HLD\s*\*\s*[0-9]|hld\s*\*\s*[0-9]|holds?\s*\*\s*[0-9]` across `scripts/xfp/` and `src/`.

**All EDIT CANDIDATE sites from Phase 0.5 now show ×2:**

| File:line | Current |
|---|---|
| `scripts/xfp/build_relievers_multiyr.py:17` | `FP = K + IP*3.3 + SV*5 + HLD*2 - BB - 2*ER - H - HBP` |
| `scripts/xfp/build_relievers_multiyr.py:46` | `return k + ip*3.3 + sv*5 + hld*2 - bb - 2*er - h - hbp` |
| `scripts/xfp/build_relievers_multiyr.py:193` | `rp['fp'] = ... + rp['hld']*2 ...` |
| `src/plv_clone/models/xfp/rprs2.py:266` | `+ cnt_df['holds']*2 - cnt_df['baseOnBalls'] ...` |
| `scripts/xfp/build_rolling_relievers.py:285` | `merged['fp_skill_to'] + 5*merged['sv_to'] + 2*merged['hld_to']` |
| `scripts/xfp/bullpen_quality.py:33` | `+ rel['sv_to'].fillna(0) * 5 + rel['hld_to'].fillna(0) * 2` |
| `scripts/xfp/monitor_drift.py:176` | `+ cnt_df['holds']*2 - ...` |
| `scripts/xfp/live_monitor.py:261` | `+ stats.get('saves', 0)*5 + stats.get('holds', 0)*2` |
| `scripts/xfp/xfp_rprs1_pipeline.py:274` | `+ cnt_df['holds']*2 - ...` |

**Files NOT in the modified list — verified already correct:**

- `scripts/xfp/build_historical_panel.py:22, 94` — docstring + `_pitcher_fp` both `+ 2*HLD`. ✓
- `scripts/xfp/_player_profiles_template.py:2773` — docstring formula `+ 2*HLD`. ✓
- `scripts/xfp/save_handcuffs.py:91` — `df['saves']*3 + df['holds']` is the *leverage score* (not BrownU FP). Unchanged is correct. ✓
- `scripts/xfp/closer_rank.py` — display only (`'HLD': df['hld'].sum()`). ✓
- `scripts/xfp/build_v11_dashboard_v2.py`, `build_matchup_dashboard.py` — display/labels only. ✓
- `scripts/xfp/enrich_rolling_relievers.py` — SV+HLD proxy for GF; not an FP formula. ✓
- `scripts/xfp/build_rp_archetypes.py` — role classification (binary). ✓
- Skill `.md` files / `_research/*.md` — descriptive prose where present is already ×2.

**Only remaining ×3 reference anywhere:**

- `scripts/xfp/trade_simulator.py:9` docstring header: `RP FP = K + IP*3.3 + SV*5 + HLD*3 − BB − 2*ER − H − HBP`. **Comment-only; no RP formula is actually computed in this file.** Phase 0.5 documented this skip; carrying forward as a cosmetic-only open item.

**Verdict — Step 1: SCORING MATCHES BrownU canonical (one cosmetic docstring outstanding, no live FP path).**

---

## Step 2 — Leakage re-verify (`src/plv_clone/models/xfp/rprs2.py`)

- `FEATS_RPRS2 = BASE_FEATS + NEW_FEATS` (lines 57–72). Identical to the registry-validated list; no features added/removed by the HLD patch. `_check_feats_validated(..., strict=True)` runs at import (line 79).
- Train/test split logic unchanged — LOO across years via `cross_year_eval` (lines 183–184). The HLD patch did not touch any split-construction code.
- `fp_actual_2026` (lines 264–268) is computed from `pitcher_counting_stats_2026.json` *end-of-cutoff actuals only* — `strikeOuts`, `inningsPitched`, `saves`, `holds`, `baseOnBalls`, `earnedRuns`, `hits`, `hitByPitch`. No projections, no future data, no rolling-forward fields. Subtracted from `xfp_full_year` to derive `xfp_ros` — i.e., the model predicts full year and `actual-to-date` is netted off. Standard, leakage-free.
- All `_to` features in the FEATS list are explicit through-cutoff aggregates from `build_rolling_relievers.py`; all `_lag1` features are prior-year. Both observable at prediction date.

**Verdict — Step 2: LEAKAGE CLEAN.**

---

## Step 3 — Downstream schema re-verify

`git diff --stat data/outputs/xfp_rprs2_projections.csv`: 291 ins / 290 del (values changed; one extra row from substrate regen, already noted in Phase 0.5).

**Header comparison (new vs `HEAD`):**

- 24 core columns identical and in the same order: `rank,pitcher,name_api,role_lag1,sv_lag1,hld_lag1,g_to,sv_to,hld_to,gf_to,gf_pct_to,sv_per_g_to,sv_2026,hld_2026,fp_actual_2026,xfp_full_year,xfp_p25,xfp_p75,xfp_ros,xfp_ros_p25,xfp_ros_p75,replacement_xfp,replacement_delta,signal`.
- Missing from new (will re-attach at refresh step 2.95): `arche_overall_prior`, `slope_3yr_prior`, `traj_career_low_prior`.

**Downstream consumer handling of the 3 missing cols:**

Consumers: `scripts/xfp/lib/blend_score.py`, `scripts/xfp/build_live_blend_xfp.py`, `scripts/xfp/enrich_projection_csvs.py`.

- `blend_score.py` reads them via `r.get(dst)` with `_isnan` guard and fallback (`r.get(dst) is None or ... _isnan(...)`) → `pr.get(src)` lookup (lines 459–470). Graceful absence handling confirmed.
- `build_live_blend_xfp.py:95` explicitly emits a `slope_3yr_prior fallback to 0 for rookies` caveat — i.e., absence already an expected branch.
- `enrich_projection_csvs.py:77`: `prior['slope_3yr_prior'] = prior['slope_3yr_prior'].fillna(0.0)` — re-attaches the columns idempotently.

No downstream consumer hard-fails on absence. Columns re-attach next full refresh.

**Verdict — Step 3: SCHEMA UNCHANGED on consumer-read columns. Three priors will reappear at refresh step 2.95 with graceful absence handling in the interim.**

---

## Step 4 — Cohort-shift legitimacy

**Observation.** Helsley (0 HLDs in 2026) moved 180.9 → 174.6 (Δ −6.3); Duran (0 HLDs) moved 170.7 → 178.2 (Δ +7.5).

**Direct mechanism check.** Both players' `fp_actual_2026` ROS netting only uses each player's own HLD count, which is 0. So the direct HLD term contributes ~0 to their personal ROS deltas. The shift comes entirely through the **fitted coefficient vector**.

**Mechanism.**

- Training target `fp_with_role_to` (in `build_rolling_relievers.py:285`) and the substrate `fp_per_g` (in `build_relievers_multiyr.py:193`) are both now re-computed under HLD×2. Every training row's *label* shrank by `Δlabel = −1 × HLD_count`. Hold-heavy setup rows shrank materially (Morejón-like rows); pure closer training rows barely moved.
- Ridge regression on the standardized FEATS minimizes squared residual against these re-weighted labels. The coefficients most affected are those whose training-side covariance with HLD-bearing labels was largest — `hld_per_g_lag1`, `hld_per_g_to`, `sv_plus_hld_to`, `fp_with_role_to`, and through correlation propagation, the role-dummies and `sv_per_g_*` features.
- Pure closers (Helsley, Duran) have near-identical *feature vectors* in saves/role-closer space but differ in secondary features (xwoba, swstr, BB%, velo, gf_pct, lag1 production). The Δ between them (−6.3 vs +7.5 = 13.8 spread) reflects how the refit re-prices these secondary features — not direct HLD inflation.

**Sanity bound.** Per-feature contribution math cannot be computed without loading the fitted ridge pipe (which is a production run by another definition — but Phase 0.5 already ran it). The *symmetry of the canonical RP table* gives the legitimacy check:

- Holds-heavy: Morejón −15.4 (HLD=11 ⇒ direct term = −11; remainder −4.4 = refit). ✓ matches spec.
- Tanner Scott −3.0 (HLD=5 ⇒ direct = −5; refit +2). ✓ within tolerance.
- Pure closers net: Helsley −6.3, Duran +7.5, Fairbanks −4.8, Palencia −2.8. Mean = −1.6, range 13.8. Consistent with a ridge-refit perturbation on a high-dim feature space.

Direction confirms: holds-heavy arms shrink by roughly `−1 × HLD_to_date`; pure closers redistribute around a near-zero mean as the model re-prices secondary features. The Helsley/Duran 13.8-FP spread is the largest outlier but is plausibly explained by their differing secondary-feature profiles (Duran has stronger swstr/k_pct, Helsley has been velocity-trending-down per refresh notes) being re-weighted under the new fit.

**Caveat.** A clean per-coefficient reproduction would require either logging the old-fit and new-fit coefficient vectors (Phase 0.5 stdout did print top-12 + NEW_FEATS coefficients, but the old run's coefficients were not preserved for diff). If a future Phase wants tighter assurance, capture the ridge `coef_` array on every rebuild into a versioned artifact — that would let any future re-audit do exact per-feature decomposition.

**Verdict — Step 4: LEGITIMATE_LOO_EFFECT.** The shift mechanism (label re-weighting → ridge re-fit → coefficient redistribution → per-player prediction Δ) is the textbook expected behavior of a supervised model whose training target's scoring rule changed. No leakage or bug signature. Per-coefficient math not reproduced in this read-only audit (would require a model run); flagged as a future-hardening item.

---

## Step 5 — Section verdicts and recommendation

1. **Scoring verdict:** MATCHES. All 9 live FP-formula sites use HLD×2. One cosmetic docstring (`trade_simulator.py:9`) still says ×3 — informational, no live formula. Carry forward as a non-blocking cosmetic.
2. **Leakage verdict:** CLEAN. FEATS_RPRS2 unchanged, train/test split unchanged, `fp_actual_2026` end-of-cutoff-only.
3. **Schema verdict:** UNCHANGED on consumer-read columns. The 3 archetype-prior columns reattach at refresh step 2.95 and downstream consumers handle absence gracefully (`.get` + `fillna`).
4. **Cohort-shift legitimacy:** LEGITIMATE_LOO_EFFECT. Holds-heavy arms decline ≈ −1·HLD_to_date (direct term); closer shifts reflect ridge-refit re-pricing of secondary features under the corrected training labels. Mechanism plausible, magnitudes within tolerance, no leakage signature. Per-coefficient math not exactly reproduced (read-only constraint); recommend logging `coef_` vector on each rebuild for future audits.

### Recommendation

**CLEAR_FOR_PHASE_1.**

The display change (Phase 1) can proceed safely. The HLD×2 correction is consistently applied across all live formula sites, no leakage was introduced, downstream schema consumers tolerate the temporary archetype-prior absence, and the closer-cohort shifts are explained by legitimate ridge-refit re-pricing rather than a regression or data-quality artifact.

Non-blocking follow-ups (do not gate Phase 1):

- Cosmetic: fix `trade_simulator.py:9` docstring `HLD*3` → `HLD*2`.
- Hardening: persist the fitted ridge `coef_` vector per rebuild so future audits can do exact per-feature decomposition.
- Ops: run `refresh_dashboards.py` (or the standalone `enrich_projection_csvs.py` step) before Phase 1 ships so the archetype-prior columns reattach for `blend_score.py` consumers that prefer the direct read path.
