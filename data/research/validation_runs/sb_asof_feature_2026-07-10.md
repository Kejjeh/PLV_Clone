---
signal: sb_per_pa_to_sh LIVE (cell a) + sprint_speed_lag1 complement (cell b)
formula: >
  (a) sb_per_pa_to = TRUE as-of stolen bases through cutoff (MLB Stats API
  gameLog source, batter_sb_asof_2018_2026.csv) / statcast pa_to, shrunk per
  SHRINK_SPEC_TO k=300 -> sb_per_pa_to_sh. (b) prior-year (T-1) Savant season
  sprint speed, missing -> TRAIN_YEARS mean (identical construction to the
  2026-07-09/2026-07-10 runs).
outcome: ros_full_fp_per_pa (rh3 target, SB-corrected per sb_target_fix_2026-07-10)
expected_sign: + (both cells)
theory: >
  BrownU hitter FP includes SB. The target now pays for steals
  (sb_target_fix_2026-07-10) but the production feature sb_per_pa_to_sh has
  been a dead-zero column since RH1 (statcast events never carry SBs; the
  runner-derivation attempt was REJECTED at +24.6% league inflation). The MLB
  Stats API per-player gameLog is a TRUE dated as-of source (verified by the
  subseason horizons probe and source-validated today: 2018-2025 season sums
  match mlb_sb 100% exactly, league diff 0.00%, r=1.0000 per year; 2026
  -0.05%). Demonstrated as-of SB rate should predict RoS SB scoring directly.
  Sprint speed (cell b) is physical speed; the open question it answers is
  whether physique adds anything BEYOND demonstrated as-of SB accrual once
  the SB feature is live.
production_target: rh3
framing: in-season -> ros
holdout_years: [2024, 2025]
training_years: [2018, 2019, 2021, 2022, 2023, 2024, 2025]
validation_script: scripts/xfp/validate_sb_asof_live.py (production-parity via
  _validate_rh3_v3_helper with the _cye 2-tuple shim)
date: 2026-07-10
multiple_look_caveat: >
  Cell (a) is the FIRST real test of sb_per_pa_to_sh — the registry PASS
  record covered a degenerate all-zero column (superseded note in
  sb_target_fix_2026-07-10.md) and the 2026-07-09 "test" was vacuous by
  construction (delta-r identically 0). Standard gates apply. Cell (b) is the
  THIRD look at holdout 2024-25 for sprint_speed_lag1 (2026-07-09 REJECTED on
  the buggy target; 2026-07-10 retest MARGINAL +0.0035). Per the retest
  prereg's own escalation rule, a bare-gate pass is NOT sufficient: cell (b)
  requires the clear-pass bar >= +0.008 with >= 6/7 signs. Bonferroni 2
  across the two cells; gates are effect-size based (unchanged Delta-r
  criteria), alpha framing alpha=0.025/cell where p-values arise.
cells:
  a_sb_per_pa_to_sh_live:
    baseline: >
      full 21-feature RH3_FEATS evaluated on the regenerated (live-SB) rolling
      cache with sb_per_pa_to_sh FORCED TO ZERO — an exact replica of the
      previous production state (dead column), expected to reproduce the
      r=0.6275 anchor from sb_target_fix_2026-07-10.md. The feature is ALREADY
      in RH3_FEATS, so the honest test is FEATS-with-live-sb vs
      FEATS-with-sb-zeroed (adding it as a 22nd column would double-count).
    extended: identical prep, sb_per_pa_to_sh at its live shrunk values.
    gates: Delta-r >= +0.005; per-year sign consistency >= 5/7; holdout 2024
      AND 2025 both positive; final-pipeline coefficient sign +.
  b_sprint_speed_lag1_complement:
    baseline: full RH3_FEATS WITH live sb_per_pa_to_sh (cell a extended).
    extended: baseline + sprint_speed_lag1 (22 features).
    gates: CLEAR-PASS bar Delta-r >= +0.008 with >= 6/7 signs (third holdout
      look); holdout 2024 AND 2025 both positive; coefficient sign +.
      A result in [+0.005, +0.008) is recorded MARGINAL, not promoted.
decision_rules: >
  (a) PASS -> sb_per_pa_to_sh goes live in production. Integration is
  mechanical: the feature is already in RH3_FEATS, so the regenerated rolling
  cache + an rh3 rerun IS the integration. FAIL -> keep the true data in the
  cache (correct data; a zero-lift feature is harmless and the column is no
  longer degenerate), document verdict, feature stays as-is in FEATS only if
  Delta-r >= 0; if Delta-r < -0.005 consider forcing the column back to zero
  in rh3 prep (decision recorded here, not silently).
  (b) PASS (clear bar) -> promote sprint_speed_lag1 into RH3_FEATS +
  validated-signals registry. MARGINAL/FAIL -> bench candidate note updated;
  next look only after TRAIN_YEARS grows (2026 complete).
---

# RESULTS (appended after run, 2026-07-10)

## Source validation (hard gate, build_batter_sb_gamelog.py assemble)

gameLog season sums vs `mlb_sb` (hitter_counting_stats_{year}.json), common
batter sets (5,681 batter-years, 395,977 player-games):

| year | n | mlb_sb | gamelog_sb | diff | r | exact match |
|---|---|---|---|---|---|---|
| 2018 | 830 | 2,473 | 2,473 | +0.00% | 1.0000 | 100.0% |
| 2019 | 837 | 2,279 | 2,279 | +0.00% | 1.0000 | 100.0% |
| 2021 | 887 | 2,209 | 2,209 | +0.00% | 1.0000 | 100.0% |
| 2022 | 644 | 2,479 | 2,479 | +0.00% | 1.0000 | 100.0% |
| 2023 | 626 | 3,495 | 3,495 | +0.00% | 1.0000 | 100.0% |
| 2024 | 628 | 3,610 | 3,610 | +0.00% | 1.0000 | 100.0% |
| 2025 | 635 | 3,427 | 3,427 | +0.00% | 1.0000 | 100.0% |
| 2026 | 594 | 1,899 | 1,898 | −0.05% | 1.0000 | 99.8% |

GATE PASS (bars: ±1% league, r ≥ 0.99). The single 2026 mismatch (Naylor
18 vs 17) is counting-stats snapshot timing, not a source defect. Contrast
with the rejected statcast runner-derivation: +24.6% league inflation.
Acuña 2023 as-of trajectory ends at exactly 73 SB. Cache regen checks:
90,249 rows (unchanged), target `ros_full_fp_per_pa` byte-identical to the
pre-wiring cache (the target uses the season-rate allocation, never sb_to),
all non-SB columns identical, league weighted sb/PA at final split
0.0118–0.0147 (2018-21) rising to 0.0196–0.0213 (2023+) — era-consistent.

## Cell results

| cell | baseline r | +cand r | Δr | signs | holdout 24/25 | coef | verdict |
|---|---|---|---|---|---|---|---|
| (a) sb_per_pa_to_sh LIVE (vs zeroed) | 0.6275 | 0.6343 | **+0.0068** | 6/7 | **2/2** (+0.0127/+0.0083) | +0.0140 (+) | **PASS** |
| (b) sprint_speed_lag1 complement | 0.6343 | 0.6345 | +0.0002 | 5/7 | **0/2** (−0.0032/−0.0013) | +0.0055 (+) | **NOT PROMOTED** (fails clear bar decisively) |

(a) Baseline reproduced the pre-registered 0.6275 anchor exactly (n=36,571).
Only negative year 2019 (−0.0007, noise-level). Convergence curve rises with
sample size (split 30 +0.0026 → split 114 +0.0087 → split 142 +0.0069),
consistent with a real accrual signal that needs PA to stabilize.

(b) With live as-of SB in the model, physical speed adds nothing: Δr +0.0002
with BOTH holdout years negative. The 2026-07-10 retest MARGINAL (+0.0035)
is now explained — sprint speed was proxying the missing SB feature. Bench
status closed: demonstrated as-of SB dominates physique. Next look only if
TRAIN_YEARS grows AND a new mechanism is hypothesized.

## Production integration (cell a PASS)

The feature was already in RH3_FEATS, so integration = regenerated rolling
cache (BUILDER_VERSION 3) + rh3 rerun. `xfp_rh3_pipeline.py` cold LOO:
**overall r 0.6343** (mae 0.0855, n=36,571), internal Rule-9 gate
+0.0135 ≥ +0.005 (PASS), `sb_per_pa_to_sh` coef +0.0140 (8th |coef| of 21).
463 hitters projected. Rank movement vs pre-live projections:
**corr(rank rise, 2026 sb/PA) = +0.81**; top risers Nasim Nuñez +155,
Esteury Ruiz +142, Jazz Chisholm +107, José Caballero +107, Oneil Cruz +90,
Chandler Simpson +60 — burners, as predicted; fallers are 0-SB
catchers/sluggers (Del Castillo −53, Torkelson −43, Chapman −41).

**Registry note:** `sb_per_pa_to_sh` status upgrades from "dead pending
as-of source" (sb_target_fix_2026-07-10.md) to **LIVE / PASS** on this run.
Operational: the 2026 as-of file goes stale as the season progresses —
re-pull with `build_batter_sb_gamelog.py pull --years 2026 --force`
(~5 min) + `assemble` before the daily rolling-cache regen, else the builder
carries the last pulled cutoff forward (leakage-safe, loudly warned).

verdicts: cell (a) PASS — shipped; cell (b) NOT PROMOTED
