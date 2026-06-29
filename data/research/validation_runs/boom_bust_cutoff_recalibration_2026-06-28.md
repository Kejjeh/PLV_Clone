---
signal: boom_bust_cutoff_recalibration
formula: hitter boom_thr 10->5 / bust_thr 2->0 ; SP boom_thr 20->17 (display only) ; RP unchanged (6/0)
outcome: CALIBRATION (cutoff hits target percentile of the per-game/per-start FP distribution) + STABILITY (percentile stable across sub-periods); NOT a forward-FP prediction
expected_sign: n/a (calibration, not prediction)
theory: the /boom-bust-history display cutoffs are absolute FP bars; the hitter pair (10/2) is badly miscalibrated (boom=97th pctl fires 3%, everyone shows 0% boom; bust=57th pctl, a coin-flip baseline). Recalibrate hitter to ~top-15% / ~bottom-22% and lower SP boom to top-quartile (~17, so a 17.7 FP start counts) so the displayed rates discriminate.
production_target: research-only
framing: full-year (descriptive display lens; CLAUDE.md #13 -> NOT a ranker, never moves a projection)
holdout_years: n/a (calibration, not a trained predictor; stability checked across 2026 sub-periods + cross-year fp_proxy SHAPE)
training_years: 2026 (the only season with real per-game BrownU FP in the boxscore store; fp_proxy 2018-2025 used only for distribution-shape stability)
validation_script: scripts/xfp/calibrate_boom_cutoffs.py
date: 2026-06-28
verdict: RESEARCH-ONLY
purpose: fix miscalibrated hitter boom/bust display cutoffs + lower SP boom to top-quartile; document boom_stack dependency (hitter independent/aligned; SP table stays at validated 20)
---

# RESULT (2026-06-28) — SHIPPED display recalibration

**Final cutoffs (live in `scripts/xfp/lib/boom_bust.py`):**
- Hitter: boom **10→5** (fires 17.0%), bust **2→0** (fires 22.4%)
- SP: boom **20→17** (fires 23.5%; a 17.7 FP start now counts), bust 5 (unchanged)
- RP: **unchanged** (6/0 = 21.8% / 18.1%, already well-calibrated)

**Calibration + stability gates (all PASS):**
1. Calibration — each cutoff lands in its pre-registered target band (H boom top-17%, H bust bottom-22%, SP boom top-quartile 23.5%).
2. Stability — across 2026 months the chosen cutoffs' fire-rates are flat: H boom 16.3–18.4%, H bust 21.6–25.0%, SP boom 21.5–26.3% (all within ±5pp).
3. Cross-year shape — `fp_proxy` p80/85/90 = **2.0/3.0/4.0 identical across 2023/2024/2025** → the per-game distribution does not drift, so a fixed absolute cutoff is justified.
4. boom_stack consistency — hitter boom_stack uses `fp_proxy >= 80th pct` (24.6% boom rate); the new display hitter boom (fp>=5, top-17%) now **shares that top-quintile philosophy** (old fp>=10 was top-3%, a gross mismatch). **No hitter boom_stack re-derivation needed** (independent + now philosophy-aligned).

**boom_stack tables — NOT re-derived (and why):**
- *Hitter:* independent of the display cutoff (own 80th-pct `fp_proxy` definition). Untouched.
- *SP:* the `BOOM_RATE_BY_TIER_STACK` tables are locked at `P(FP>=20)` from 33k starts (2018-2025). The surviving panel (`boom_stack_history_panel.parquet`) was only a 2026 lookup-snapshot at the time of this note. The SP boom_stack forward table therefore keeps its validated `>=20` "monster" definition by design; the display lens (now `>=17`) and the boom_stack forward table are separate tools (they already differed on bust: 5 vs 0). Documented inline in `boom_bust.py`. **UPDATE (same session):** the multi-year per-game FP store WAS then built (see the Multi-year-confirmation block below), so SP-at-17 re-derivation is now feasible (kept as the intentional split); the HITTER SB re-derivation was measured = +1.3pp uniform, edge-preserved.

**Impact verified on the live decisions:** Peralta L8 boom 0%→**12%** (his 17.7 now registers); hitter boom% now *discriminates* (Grisham 29% / Nimmo 24% / Cortes 5% — previously all 0%).

**Multi-year confirmation — FULL STATCAST ERA (2026-06-28, supersedes the Rule-5 honesty note):**
built a persistent multi-year per-game BrownU-FP store from MLB Stats API gameLogs —
`data/research/multiyr_boxscore_fp.parquet`, **656,423 player-games across 2015-2026** (488k
hitter-games, 47k SP starts, 121k RP appearances; `scripts/xfp/build_multiyr_fp_store.py`).
Every recalibrated cutoff is stable across all 12 years of REAL per-game FP:
- Hitter **boom≥5 = 16.8-20.1%** every year (pooled 18.3%); **bust<0 = 20.2-22.8%** (pooled 21.6%).
- SP **boom≥17 = 24-26%** in the modern run env (2023-26; top-quartile as intended — slightly higher
  ~30% in 2015-16's lower-K era, but we calibrate to current); bust<5 ~25-29%.
- RP **boom≥6 = 20-23%**, **bust<0 = 15-19%** (2017+; sparse earlier).
No drift, no regime artifact. The 2026 anchor was correct — more years re-derive the SAME cutoffs.
The store is now REUSABLE INFRASTRUCTURE for every actuals lens (boom/bust, /boom-bust-history
multi-year fallback, future boom_stack re-derivations). SB share of FP held 2.4-2.8% in all years.

**SB RULE-CHANGE REGIME (2023) — accounted for (2026-06-28).** The 2023 rules (bigger bases +
pickoff/disengagement caps + pitch clock) jumped league SB ~+50% (mean sb_per_pa 0.013->0.019;
`scripts/_oneoff/sb_regime_check.py`). The jump is a LEVEL shift that PRESERVES rank order (YoY
rank-corr ~0.74 even across the break), so within-year RELATIVE reads are safe (archetype `r_SB`)
but YoY DELTAS are only valid WITHIN a regime. Audit: boom/bust multi-year check used 2023-25 only
(clean); velo/decline panel has no SB (irrelevant); the new `/trending` SB axis got a regime GUARD
(`SB_RULE_YEAR=2023` in `trend_signal.py` — `z_sb` is suppressed when cur/base straddle 2023; the
in-season `sb_recent` is always same-regime). **A future multi-year boxscore store MUST NOT pool
pre/post-2023 for any SB-inclusive metric** (FP distribution, boom_stack SB tables) — use 2023+ only.

**Status:** SHIPPED as a display/context recalibration (CLAUDE.md #13 — never moves a projection). Logged RESEARCH-ONLY because it is a calibration of a display lens, NOT a predictive ranker signal — it is *not* eligible for any FEATS list. Tests: `tests/test_boom_bust.py` + triangulate suites green (53 passed); core `boom_bust_summary` unchanged (only wrapper defaults).

# Boom/Bust cutoff recalibration — pre-registration

## Why (the miscalibration, measured on 2026)
- **Hitter** boom 10 fires on **3%** of games (97th pctl) -> the column is dead (every non-elite hitter shows 0% boom). bust 2 fires on **57%** (57th pctl) -> uninformative coin-flip baseline.
- **SP** boom 20 fires 14% (86th pctl), bust 5 fires 30% (30th pctl) — roughly OK but boom is a touch stringent; a 17.7 FP start (top-quartile) does not count.
- **RP** boom 6 fires ~20%, bust 0 fires ~18% — well-calibrated; **leave unchanged**.

## Targets (pre-registered, before running exact numbers)
- Hitter BOOM: smallest integer FP cutoff whose tail is ~12-18% of games (top ~quintile-to-sixth).
- Hitter BUST: cutoff whose tail is ~20-25% (bottom ~quartile).
- SP BOOM: top-quartile (~p75), must be <= 17.7 so Peralta's start counts.
- RP: unchanged.

## Calibration + stability criteria (this is the "validation" for a display lens)
1. **Calibration:** chosen cutoff sits within the pre-registered target percentile band on the full 2026 distribution.
2. **Stability:** the chosen cutoff's percentile is stable across 2026 monthly sub-periods (within +-5 pp) — so a FIXED absolute cutoff is defensible vs a drifting run environment.
3. **Cross-year shape:** the fp_proxy distribution shape (statcast-computable 2023-2025) is stable, supporting a fixed cutoff (BrownU FP not available pre-2026, noted as a Rule-5 honesty limit).
4. **boom_stack consistency:** verify hitter boom_stack (80th-pct fp_proxy) ~ the new hitter display cutoff (alignment, not a break); document SP boom_stack stays at validated 20.

## Scope / honesty notes
- This is a **display/context lens (CLAUDE.md #13)** — recalibration changes only what the boom%/bust% NUMBERS mean, never a projection or a drop decision. Logged RESEARCH-ONLY; not eligible for any FEATS list.
- **Rule-5 limit:** real per-game BrownU FP only exists for 2026 in the boxscore store; multi-year is fp_proxy-shape only. Absolute cutoffs anchored on the current (2026) run environment, with stability checks. A full multi-year BrownU-FP re-derivation is a deferred follow-up.
- **SP boom_stack re-derivation: now UNBLOCKED** (the 2015-2026 `multiyr_boxscore_fp.parquet`, with
  gs/role, was built later this session — see the multi-year-confirmation block below). SP display
  lowered to 17; the boom_stack forward table keeps its validated P(FP>=20) "monster" definition **by
  design** (intentional separate-tool split — display = realized "good starts", table = forward
  "monster" rate; they already differed on bust 5-vs-0). Re-deriving the SP table at 17 is now
  feasible if desired but NOT required (the split is intentional + documented). The HITTER boom_stack
  SB-inclusive re-derivation was MEASURED on the 245k panel (`scripts/_oneoff/rederive_hitter_sb.py`):
  the panel reproduces the current tables exactly, and adding SB shifts every stack by a UNIFORM **+1.3pp**
  (stack 0: 23.9→25.2%, stack 3: 30.6→32.1%) that PRESERVES the stack 0→3 edge (+6.7→+6.9pp). Since
  boom_stack discriminates on the EDGE (unchanged) and the shift is uniform + sub-2pp, the tables are
  left as-is with the SB note documented inline; the displayed absolute boom% runs ~1.3pp light for
  speedsters only (a documented, non-discriminating bias, not an error).
