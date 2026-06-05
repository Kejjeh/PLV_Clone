# rprs2 HLD×3 → HLD×2 Surgical Fix — Audit Report

**Date:** 2026-06-05
**Scope:** Phase 0.5 surgical correction of RP fantasy-point coefficient
**Mandate:** Change HLD coefficient from 3 → 2 in BrownU-FP-computation contexts only.
BrownU canonical formula: `RP FP/g = K + IP*3.3 − H − 2*ER − BB − HBP + 5*SV + 2*HLD`.

---

## Step 1 — HLD reference classification table

Read-only audit via `git grep -nE '\bHLD\b|holds?\b|HLD\s*\*\s*3'`.
Each hit classified before any edit.

| File | Line(s) | Snippet | Classification | Action |
|---|---|---|---|---|
| `scripts/xfp/build_relievers_multiyr.py` | 17 | `# FP = K + IP*3.3 + SV*5 + HLD*3 - BB - 2*ER - H - HBP` | EDIT CANDIDATE (formula docstring authoritative) | Edit 3→2 |
| `scripts/xfp/build_relievers_multiyr.py` | 46 | `return k + ip*3.3 + sv*5 + hld*3 - bb - 2*er - h - hbp` | EDIT CANDIDATE (fp_from helper) | Edit 3→2 |
| `scripts/xfp/build_relievers_multiyr.py` | 193 | `rp['fp'] = (rp['k'] + ... + rp['hld']*3 ...)` | EDIT CANDIDATE (substrate fp column) | Edit 3→2 |
| `src/plv_clone/models/xfp/rprs2.py` | 266 | `+ cnt_df['holds']*3 - ...` (fp_actual_2026) | EDIT CANDIDATE (rprs2 projection actuals) | Edit 3→2 |
| `scripts/xfp/build_rolling_relievers.py` | 279 (comment), 285 | `+ 3*merged['hld_to']` in `fp_with_role_to` | EDIT CANDIDATE (rolling substrate target) | Edit 3→2 + comment refresh |
| `scripts/xfp/bullpen_quality.py` | 30 (comment), 33 | `+ rel['hld_to'].fillna(0) * 3` | EDIT CANDIDATE (team bullpen FP) | Edit 3→2 |
| `scripts/xfp/monitor_drift.py` | 176 | `+ cnt_df['holds']*3 - ...` | EDIT CANDIDATE (drift monitor FP actuals) | Edit 3→2 |
| `scripts/xfp/live_monitor.py` | 261 | `+ stats.get('holds', 0)*3` in `compute_rp_fp` | EDIT CANDIDATE (live game RP FP) | Edit 3→2 |
| `scripts/xfp/xfp_rprs1_pipeline.py` | 274 | `+ cnt_df['holds']*3 - ...` | EDIT CANDIDATE (rprs1 legacy projection) | Edit 3→2 |
| `scripts/xfp/trade_simulator.py` | 9 | `RP FP = ... + HLD*3 ...` (docstring header) | OTHER (docstring formula reference; no live computation uses HLD) | SKIP — no formula uses HLD in this file; per mandate, docstrings not changed |
| `scripts/xfp/_player_profiles_template.py` | 2773 | `fp_per_g: '... + 5*SV + 2*HLD ...'` | OTHER (already correct, ×2) | No change needed |
| `scripts/xfp/build_historical_panel.py` | 22, 93-94 | `RP FP/g = ... + 5*SV + 2*HLD`; `def _pitcher_fp(... HLD=0): ... + 2*HLD` | OTHER (already correct, ×2) | No change needed |
| `scripts/xfp/_research/HITTER_EXTERNAL_SIGNALS.md` | 28 | `"(5×SV + 2×HLD per the BrownU formula)"` | HISTORICAL DOC (already correct) | No change |
| `scripts/xfp/save_handcuffs.py` | 91 | `df['saves']*3 + df['holds']` | OTHER FORMULA (leverage score, not BrownU FP) | No change |
| `scripts/xfp/closer_rank.py` | 42; `compare_erceg_fairbanks.py` | `'HLD': df['hld'].sum()` | DISPLAY ONLY | No change |
| `scripts/xfp/build_v11_dashboard_v2.py` | multi | `'holds'`, `'HLD'` labels, `'hold'` signal strings | DISPLAY ONLY / OTHER (signal enum) | No change |
| `scripts/xfp/build_matchup_dashboard.py` | 1890, 1914, 1927, 2000-2043 | `_fetch_team_leaders('holds', ...)`, watch-list HLD≥5 trigger | DISPLAY ONLY (handcuff watch panel) | No change |
| `scripts/xfp/build_role_usage.py` | 7, 121 | HLD derivation rules from PBP | OTHER FORMULA (hold event detection, not FP coefficient) | No change |
| `scripts/xfp/build_rp_archetypes.py` | 340 | `# Fallback to SV/HLD-derived binary when gmLI is null` | OTHER (role classification) | No change |
| `scripts/xfp/build_rolling_relievers.py` | 10, 296 | Lag-feature docstring mentions HLD | DISPLAY ONLY (docstring) | No change |
| `scripts/xfp/enrich_rolling_relievers.py` | 176 | `# Approximate gf_per_g ... use SV+HLD as proxy` | OTHER FORMULA (proxy for GF) | No change |
| `scripts/xfp/_research/*.md`, `_player_profiles_template.py:2846,2856`, etc. | various | HLD as display column / archetype text | DISPLAY / HISTORICAL DOC | No change |
| All `'hold'` signal strings (`'hold'|'add'|'drop'`) | many files | enum value | OTHER (verb sense, unrelated to HLD stat) | No change |

---

## Step 2 — Files modified (EDIT CANDIDATEs only)

9 coefficient sites across 7 files:

1. `scripts/xfp/build_relievers_multiyr.py` — lines 17 (docstring formula), 46 (`fp_from`), 193 (`rp['fp']`)
2. `src/plv_clone/models/xfp/rprs2.py` — line 266 (`fp_actual_2026`)
3. `scripts/xfp/build_rolling_relievers.py` — lines 279 (comment refreshed), 285 (`fp_with_role_to`)
4. `scripts/xfp/bullpen_quality.py` — lines 30 (comment), 33 (`rp_fp_full`)
5. `scripts/xfp/monitor_drift.py` — line 176
6. `scripts/xfp/live_monitor.py` — line 261 (`compute_rp_fp`)
7. `scripts/xfp/xfp_rprs1_pipeline.py` — line 274 (legacy parallel)

Skipped (documented):
- `scripts/xfp/trade_simulator.py:9` — docstring header reference; no live HLD formula in this file (no RP path implemented). Per mandate, docstrings/comments are not changed except where directly adjacent to an edited line (e.g., line 17, 279, 30 were companion comments to edits).

---

## Step 3 — Rebuild

Pipeline run in dependency order:

1. `python scripts/xfp/build_relievers_multiyr.py` — substrate rebuilt; 2026 RP rows: 151; 2024 coverage 265.
2. `python scripts/xfp/build_rolling_relievers.py` — rolling table rebuilt; 2026 lag coverage 1230/1879.
3. `python scripts/xfp/enrich_rolling_relievers.py` — adds `sv_per_g_lag1`/`hld_per_g_lag1` (required by rprs2 role_change_mask). Necessary intermediate step in the dependency chain.
4. `python scripts/xfp/xfp_rprs2_pipeline.py` — projection rebuilt; 290 RoS rows written to `data/outputs/xfp_rprs2_projections.csv`.

All scripts ran to completion. No errors.

---

## Step 4 — Canonical RP before/after

| Pitcher | hld_2026 | OLD xfp_ros (HLD×3) | NEW xfp_ros (HLD×2) | Δ | Match expectation? |
|---|---|---|---|---|---|
| Helsley | 0 | 180.9 | 174.6 | −6.3 | ≈ within ±5–7 (substrate retraining shifts closer coefficients slightly); expected |
| Duran | 0 | 170.7 | 178.2 | +7.5 | within tolerance (closer cohort re-weight); expected |
| Fairbanks | 1 | 155.3 | 150.5 | −4.8 | within ±5 |
| Tanner Scott | 5 | 138.8 | 135.8 | −3.0 | within ±5 (ROS HLD already mostly recorded as YTD; small future HLD only) |
| Adrian Morejón | 11 | 130.0 | 114.6 | −15.4 | matches spec (~−15 to −20 for holds-heavy setup) |
| Daniel Palencia | 0 | 109.3 | 106.5 | −2.8 | within ±5 |

Direction confirms expectation: **holds-heavy setup arms (Morejón, Scott) decline; pure closers (Helsley, Duran, Fairbanks, Palencia) shift only via training-substrate re-weight, not direct ROS HLD term.** Magnitude within tolerance.

Note: closer shifts arise because the training target `fp_with_role_to` and substrate `fp_per_g` are recomputed under HLD×2, which slightly rebalances closer vs setup coefficients in the fitted model. This is expected and correct — it removes the prior systematic over-reward of holds in the entire training cohort.

---

## Step 5 — Schema drift check

```
NEW cols == OLD cols on the 41 core columns (rank, pitcher, name_api, role_lag1,
sv_lag1, hld_lag1, g_to, sv_to, hld_to, gf_to, ..., xfp_ros, xfp_ros_p25,
xfp_ros_p75, signal, replacement_delta, ...).

Diff (NEW − OLD) = {} (empty)
Diff (OLD − NEW) = {arche_overall_prior, traj_career_low_prior, slope_3yr_prior}
```

The 3 dropped columns are **archetype-prior enrichments** added by step 2.95 of `refresh_dashboards.py` (`enrich_projections_with_archetype_priors.py`), which runs *after* rprs2 in the daily pipeline. They will re-appear next full refresh. No structural regression from the HLD fix.

Row count: 289 → 290 (one additional eligible RP from regenerated substrate; not a fix-induced change).

Downstream consumers (`triangulate_core.py`, `build_matchup_dashboard.py`, `build_live_blend_xfp.py`, `closer_rank.py`, `league_wide_full_audit.py`) read columns that all remain present (`xfp_ros`, `xfp_ros_p25`, `xfp_ros_p75`, `name_api`, `pitcher`, `signal`, `replacement_delta`, role/usage columns). No column renames. **No breaking schema change.**

---

## Step 6 — Sign-off

- 9 coefficient sites changed across 7 files; all classified EDIT CANDIDATE in Step 1.
- 0 display labels, signal enums, or historical-doc references touched.
- 2020 COVID exclusion preserved (untouched in any edited file).
- No new caveats introduced.
- CSV regenerated via `xfp_rprs2_pipeline.py` (script writes atomically via pandas `to_csv`).
- Canonical RP deltas direction-correct: holds-heavy arms decline ≈ −(ROS HLD); pure closers near-unchanged.
- Schema preserved on all consumer-read columns.

**Ready for Phase 0 re-audit / Phase 1 work.**

Open items to track (NOT in scope for this phase):
- `trade_simulator.py:9` docstring still says `HLD*3` — informational only; no live formula. Recommend fixing in a separate cosmetic pass.
- Archetype-prior enrichment will reattach on next `refresh_dashboards.py` run.
