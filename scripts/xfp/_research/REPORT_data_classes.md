# Data-class tests report

Date: 2026-05-28. Scope: empirical evaluation of 4 candidate new data classes (skipping C — multi-year bat tracking, waiting for 2027 data). All tests pure research; no production scripts changed.

## Test A1 — SP put-away pitch

Data: `data/processed/pitch_features/year=2021..2026`. **3,932 pitcher-years** with ≥1 pitch type at ≥30 swings.

`best_putaway_whiff` = max whiff% across pitch types per (pitcher, year), then 20-80 rated.

**YoY stability:** raw whiff r = **0.414** (n=2,377), r_BestPutaway r = **0.430** — moderate, real signal.

**Current-year `fp_per_start` regression (n=995):**

| Spec | R² | ΔR² |
|---|---|---|
| STUFF only | 0.523 | — |
| STUFF + r_BestPutaway | 0.525 | **+0.002** |
| STUFF + MOV + CTRL | 0.671 | — |
| Full + r_BestPutaway | 0.671 | **+0.0001** |
| Full + swstr_pct | 0.671 | — |
| Full + swstr_pct + r_BestPutaway | 0.671 | **+9e-6** |

**T+1 (n=581):** Full baseline + age + prior fp R²=0.284 → +r_BestPutaway = 0.284 (**ΔR²=+0.0001**).

**Verdict: SKIP.** Signal is fully absorbed by existing STUFF/MOVEMENT/CONTROL + swstr_pct. p-value goes from 0.037 (simple baseline) to 0.65 once existing features control for it.

## Test A2 — Hitter per-pitch-type performance

Data: pitch_features in-play rows. **1,091 batter-years** with ≥2 pitch types at ≥50 BIP.

`best_pitch_xwoba`, `pitch_spread = best - worst`, 20-80 rated.

**YoY stability:** best_pitch_xwoba r = **0.664** (likely proxying overall xwOBA-on-contact). pitch_spread r = **0.218** (weak).

**Current-year fp_per_pa regression (n=1,091):**

| Spec | R² | ΔR² |
|---|---|---|
| CONTACT + POWER + DISCIPLINE | 0.747 | — |
| + r_BestPitchXwoba | 0.776 | **+0.029** ✓ |
| + r_PitchSpread | 0.748 | +0.001 |
| **Tough baseline (+ xwoba_on_contact)** | **0.789** | — |
| Tough + r_BestPitchXwoba | 0.791 | **+0.002** |
| Tough + r_PitchSpread | 0.789 | +7e-5 |

**T+1 (n=982):** baseline 0.271 → any per-pitch variant = 0.271 (ΔR² ≤ 1e-5).

**Verdict: SKIP.** The +0.029 lift over CPD-only is a Rule 9 mirage — once `xwoba_on_contact` (already a production field) is in the baseline, lift drops to +0.002. The novel construct (pitch_spread = "holes in swing") has weak YoY and zero lift.

## Test B1 — Hitter platoon splits

Data: `data/research/xfp_cache/statcast_*.parquet`, 2018-2026, end-of-PA rows. Threshold ≥50 PA vs LHP and ≥100 PA vs RHP. **2,333 batter-years**.

`xwoba_abs_split = |xwoba_vs_L - xwoba_vs_R|`; orientation-aware `xwoba_platoon_adv`.

**YoY stability — the headline test:**

| Metric | YoY r | n pairs |
|---|---|---|
| xwoba_abs_split | **0.054** | 1,392 |
| xwoba_platoon_adv | **0.090** | 1,392 |
| r_PlatoonNeutral 20-80 | **0.038** | 1,392 |

Effectively zero. Even more pessimistic than Tango/Lichtman's 0.20-0.40. Apparent platoon splits in a single season are sample noise.

**Current-year fp_per_pa (n=2,100):** baseline 0.751 → +xwoba_abs_split = 0.754 (ΔR²=+0.003).
**T+1 (n=1,448):** baseline 0.267 → +split = 0.269 (ΔR²=+0.001).

Coefficient sign on `xwoba_abs_split` is negative (bigger platoon hole hurts FP) but trivial in magnitude, and the predictor can't propagate forward since YoY r ≈ 0.

**Verdict: SKIP.** YoY r of 0.05-0.09 is the smoking gun.

## Test B2 — RISP / clutch (confirmation)

2,314 batter-years with ≥60 RISP PA and ≥200 total PA. `clutch = xwoba_RISP - xwoba_overall`.

**YoY r = 0.0024** (n=1,253). Mean +0.002, σ ≈ 0.033.

**Verdict: Noise, as expected.**

## Overall recommendation — data classes

| Test | Promote? | Why |
|---|---|---|
| A1 SP put-away | **No** | YoY moderate but ΔR² ≤ 0.002 once STUFF/MOV/CTRL/swstr_pct controlled |
| A2 Hitter per-pitch | **No** | +0.029 lift evaporates to +0.002 after xwoba_on_contact added (classic Rule 9) |
| B1 Hitter platoon | **No** | YoY r=0.05-0.09 — almost pure noise |
| B2 RISP/clutch | **No** | YoY r=0.002 — pure noise |

Best illustration of the validation framework: A2 would have appeared promotion-worthy (+0.029) under a stripped-down baseline. The apples-to-apples Rule 9 check kept it honest. If platoon is ever revisited, the avenue most likely to work is Bayesian-shrunk platoon (weight observed split heavily toward the league handedness baseline); the raw single-season metric tested here is the maximally noisy version.
