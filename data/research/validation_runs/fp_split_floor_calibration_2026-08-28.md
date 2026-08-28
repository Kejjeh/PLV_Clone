# FP/start split noise floor — calibration (2026-08-28)

**Why:** the decision layer now screens RESULTS gaps in FP-per-start terms
everywhere (forward distribution cards, the new-leaf boards, the new-leaf
calibration's Gate 1), and every such screen improvised a NAIVE Welch z with
no dispersion calibration. The canonical owner (`lib/split_floor.py`) only
covered K/BB rate metrics. This study measures the FP-side over-dispersion
and installs `split_floor_fp` as the single owner.

## Method

- Panel: `sp_event_panel_2017_2026.csv` per-start rows, years 2018-2026,
  pitcher-seasons with >=12 GS → **1,175 seasons** (same eligibility as the
  new-leaf calibration).
- Every within-season split with >=4 starts per side → **21,242 splits**;
  |Welch z| on FP/start per split.
- Null: per-season start-order shuffle (seed 20260828) with IDENTICAL split
  geometry — destroys temporal structure, keeps each pitcher's true FP
  marginal distribution and every (n1, n2). Small-sample t-inflation cancels
  in the ratio because both arms share the same window sizes.
- Script: `scripts/_oneoff/fp_split_floor_calibration.py` (re-runnable).

## Results

| quantity | value |
|---|---|
| var(z_obs) / var(z_shuffle), overall | **1.180** (SD multiplier 1.086) |
| by min-side n: 4-5 / 6-9 / 10+ | **1.121 / 1.165 / 1.259** |
| z_obs p50 / p90 / p99 | 0.74 / 1.91 / 3.32 |
| z_shuffle p50 / p90 / p99 | 0.68 / 1.80 / 3.02 |
| per-season MAX z (searched view) p50 / p90 | **1.86 / 3.17** |

Findings:

1. **FP/start splits are over-dispersed ×1.18 vs iid — and it GROWS with
   window size** (1.12 → 1.26). Real temporal structure (schedule/park/streak
   autocorrelation) accumulates, so a naive Welch z is most too-lenient
   exactly when the windows look most trustworthy. Mirrors the K-BB floor's
   1.114 in magnitude.
2. **Searched-split honesty, FP edition:** the MEDIAN pitcher-season's best
   split reaches naive z = 1.86 by construction — the given bar (1.83) can
   never serve a searched split. Searched bar set at the per-season-max p90
   in calibrated units: 3.17 / 1.086 ≈ **Z_SEARCHED_FP = 2.92**.
3. **Re-screen impact on the new-leaf calibration:** 24 of its 227 clearing
   rows (10.6%) demote to noise under the calibrated floor (227 → 203) — all
   rows that cleared only via the naive FP Welch z in the 1.83-1.99 band.
   Directionally this strengthens, not weakens, that study's null (fewer
   real breaks).
4. Canonicals (given splits): Lopez z_cal = **3.78** (still clears,
   decisively); Cameron 1.10, Soriano 0.20, Imanaga 0.28 (all within noise —
   consistent with every verdict shipped on the 2026-08-28 boards).

## Shipped

- `lib/split_floor.py`: `split_floor_fp(pre_fps, post_fps)` — same contract
  as `split_floor`, Welch SE inflated by the window-size-bucketed dispersion;
  <4 starts per side returns UNMEASURABLE. Constants `DISPERSION_FP_SP`,
  `DISPERSION_FP_SP_OVERALL`, `Z_SEARCHED_FP`.
- `tests/test_split_floor.py` — first dedicated pins for the floor module:
  constants, monotone dispersion, stricter-than-naive, contract parity,
  symmetry, small-side refusal.

Scope notes: SP only (RP FP/appearance and hitter FP/g floors remain naive —
same follow-up shape if needed). Rule 13: screen-layer only, nothing touches
rp3/rprs2.
