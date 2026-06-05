# rprs2 `ros_xfp` — Phase 0 Pre-Promotion Audit

**Date:** 2026-06-05  
**Auditor:** read-only Phase 0 pass  
**Subject:** `xfp_rprs2_projections.csv` column `xfp_ros` (note: file column is `xfp_ros`, not `ros_xfp`) for promotion as the RP headline number in `/triangulate`.

---

## 1. Leakage verdict — CLEAN (with one caveat)

Source: `src/plv_clone/models/xfp/rprs2.py` lines 57–72 (`FEATS_RPRS2`), training in `cross_year_eval` (lines 82–117), final fit in `train_final` (lines 153–162). All features fall into one of two safe categories:

- `_lag1` family (`role_*_lag1`, `sv_lag1`, `hld_lag1`, `g_lag1`, `ip_lag1`, `fp_per_g_lag1`, `fp_lag1`, `sv_per_g_lag1`, `hld_per_g_lag1`) — by construction, these come from the prior completed season. Substrate is built in `scripts/xfp/build_rolling_relievers.py` from `relievers_multiyr` rows. Safe.
- `_to` family (`k_pct_to`, `bb_pct_to`, `swstr_pct_to`, `c_plus_swstr_to`, `xwoba_per_pa_to`, `avg_velo_to`, `zone_pct_to`, `o_swing_pct_to`, `g_to`, `ip_to`, `fp_skill_to`, `gf_pct_to`, `sv_per_g_to`, `hld_per_g_to`, `sv_plus_hld_to`, `fp_with_role_to`) — season-to-date through `split_day`. Safe IF rolling substrate enforces `split_day` correctly; the substrate builder bundles a `split_day` column per row and the LOO eval splits by `year` (line 91), so test-year rows never appear in train.

Target: `fp_year_total` (line 52), joined from `multiyr` totals (build_rolling_relievers.py line 313). Target is the full-season outcome — that is by design for a RoS model; the model predicts season total, then ROS is computed at projection time as `xfp_full_year − fp_actual_2026` (line 273). This is NOT leakage; the model never sees `fp_year_total` of the test year during fit.

**Caveat (not leakage, but worth flagging):** LOO is *across years*, not temporally walk-forward within a year. A 2024 test row at `split_day=120` is predicted by a model trained on 2025 rows that include `split_day` values >120. This is the standard convention for our entire xfp family (rh3/rp3 use the same scheme) — flag for awareness, not a blocker.

No `ros_*` or `future_*` predictor names found. **Verdict: CLEAN.**

## 2. Scoring verdict — DIVERGES (HLD weight)

BrownU formula (CLAUDE.md, reference_league_rules.md):
```
RP FP = K + IP*3.3 − H − 2*ER − BB − HBP + 5*SV + 2*HLD
```

rprs2 substrate `fp` (build_relievers_multiyr.py line 46, line 193) and rprs2 final 2026-actual computation (`rprs2.py` lines 264–268):
```
fp = K + IP*3.3 + SV*5 + HLD*3 − BB − 2*ER − H − HBP
```

**HLD weight is 3, not 2.** This propagates to:
- The training target `fp_year_total` (build_rolling_relievers.py line 313 ← build_relievers_multiyr.py line 193).
- The current-season actual `fp_actual_2026` (rprs2.py line 267).
- The same divergence exists in `xfp_rprs1_pipeline.py` (lines 273–274), `monitor_drift.py` (175–176), `live_monitor.py` (line 261), `bullpen_quality.py` (line 33).

Implication: every FP number the rprs2 pipeline produces is biased UP for high-hold RPs by `1 × HLD`. For a setup man with 25 HLD, total-season FP is overstated by ~25 FP; ROS is overstated by the share of remaining HLDs × 1. For Morejón (proj 10 holds remaining), ~10 FP overstatement on `xfp_ros = 130.0`. For pure closers (Helsley, Duran), the bias is near zero.

**Verdict: DIVERGES.** The bias is uniform across train and projection, so r/MAE shape is preserved, but the headline absolute number is systematically high for hold-heavy RPs and rprs2's `replacement_delta` overstates the value of setup men relative to closers (whose value comes from saves@5, correctly weighted).

## 3. Downstream consumer impact

Consumers of `xfp_ros` / `replacement_delta` from `xfp_rprs2_projections.csv`:

| File | Use | Impact if promoted to /triangulate |
|---|---|---|
| `build_matchup_dashboard.py` (lines 318, 941–945, 1310) | Computes per-team-game RP contribution as `xfp_ros / days_remaining` | Already surfaces `xfp_ros`; promotion changes only display label, not value. |
| `build_live_blend_xfp.py` (line 86) | Anchor projection for live blend | Already uses `xfp_ros`; no change. |
| `build_v11_dashboard_v2.py` (lines 471–475) | Surfaces `rpRoSFp`, `rpRoSFpP25/P75`, `rpReplDelta` | No change. |
| `closer_rank.py`, `compare_to_pitcherlist.py`, `compare_pl_top50.py` | Rank RPs by `xfp_ros` | No change. |
| `league_wide_full_audit.py` (line 631), `league_wide_synthesis.py` (line 90) | RP ranking via `xfp_ros` | No change. |
| `lib/triangulate_core.py` (lines 327–328) | **Already sets `proj_label='xfp_ros'`, `proj=r['xfp_ros']` for RPs.** | No code change needed — display layer already wired. |
| `lib/blend_score.py` | Per-G blend currently used elsewhere | Phase 1 must reconcile: blend produces per-G, triangulate already uses xfp_ros. No conflict; just inconsistency between surfaces. |

**Surprising finding:** `triangulate_core.py` line 327 already uses `xfp_ros` as the RP headline. The "promote to RP headline" is, effectively, *already done in code*. Phase 1 may be only a labeling / display-polish task plus reconciling the per-G blend in `blend_score.py` to read the same source. Confirm with owner.

## 4. Empirical accuracy

**Cannot retroactively run rprs2 on hold-out.** `data/research/historical_panel/master_panel.parquet` has 2024 RP `fp_total` (year-end actual), but reconstructing the rprs2 input feature vector at a 2024 mid-season split_day requires the rolling-relievers substrate snapshotted at that date — that substrate is built rolling-forward and the historical mid-year snapshots are not preserved.

What CAN be cited from the model bundle: `cross_year_r` and per-year LOO r are recorded in `MODEL_PKL` at training time (lines 304, 311). Recommend Phase 3 forward-validation:
- Freeze current `xfp_ros` projections snapshot for top-60 rostered RPs.
- At season end, compute actual ROS FP from `pitcher_counting_stats` using **the BrownU formula** (HLD×2, not HLD×3).
- Report MAE / R² / role-bias (closer vs setup vs middle).

Sample sanity (top closers, current snapshot):

| Player | role | sv_to | g_to | xfp_full_year | fp_actual_2026 | xfp_ros |
|---|---|---|---|---|---|---|
| Helsley | closer | 7 | 12 | 246.1 | 65.2 | 180.9 |
| Duran | closer | 12 | 18 | 313.6 | 142.9 | 170.7 |
| T. Scott | closer | 5 | 26 | 267.5 | 128.7 | 138.8 |
| Morejón | setup | 1 | 26 | 243.0 | 113.0 | 130.0 |
| Palencia | closer | 2 | 13 | 160.4 | 51.1 | 109.3 |

Values are directionally sane (closer RoS > setup RoS at parity volume; closer ramping up after IL gap shows higher RoS as expected). Morejón sits suspiciously high — consistent with the HLD×3 inflation flagged in §2.

## 5. Recommendation — PROCEED_WITH_CAVEAT

`xfp_ros` is leakage-clean and **already wired as the RP headline in `triangulate_core.py`**. Promoting it formally is mostly a documentation / label / blend-reconciliation task. However:

1. **HLD scoring divergence (HLD×3 in rprs2 vs HLD×2 in BrownU).** Recommend NOT silently re-fitting (that's Phase 2+ work); instead, in Phase 1 surface a footnote: *"xfp_ros uses HLD×3 internal weighting; setup-man values are biased high by ~1 FP per remaining HLD vs BrownU scoring. Closer values unaffected."* Open a follow-up ticket to retrain rprs2 with HLD×2 and compare delta.
2. **Per-G blend in `lib/blend_score.py`** should be reconciled with `xfp_ros` so the matchup dashboard and triangulate present consistent units (display per-G as `xfp_ros / games_remaining` rather than from the independent blend).
3. **Phase 3 forward validation as outlined above** — freeze the snapshot now.

No HALT condition. The leakage audit is clean; the scoring divergence is uniform and documentable. Proceed to Phase 1 with the caveat footnote and a tracked follow-up to align HLD weight.

---

## Section headers + final verdict (verification print)

1. Leakage verdict — CLEAN (with one caveat)  
2. Scoring verdict — DIVERGES (HLD weight)  
3. Downstream consumer impact  
4. Empirical accuracy  
5. Recommendation — **PROCEED_WITH_CAVEAT**
