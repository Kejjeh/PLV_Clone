---
signal: stuff_translation_gap_sp
formula: Among HIGH-Stuff STARTING pitchers (top-quartile stuff-proxy within each as-of cell), the "Stuff Translation Gap" = residual of a skill-translation metric (CSW%, swstr%, K-BB%) regressed on the stuff measure WITHIN the as-of (year, split_day) cell. Negative residual => stuff NOT converting to whiffs/Ks. Six SP "avoid buckets" each defined as a pre-week, as-of, within-cell z-feature (sign-oriented so POSITIVE = hypothesized worse forward FP), then OOS-tested for incremental value OVER stuff-proxy alone.
outcome: ros_fp_per_start (BrownU SP scoring K + IP*3.3 - H - 2ER - BB - HBP, per start) over the forward ros_gs starts from each (pitcher, split_day) cutoff. Leakage-safe: all features are *_to cumulative-to-cutoff; target is strictly post-cutoff.
expected_sign: avoid features negatively predict forward FP among high-Stuff arms
theory: Stuff+ answers "are the pitch traits good?" not "does he turn them into outs/Ks/IP/value?". The strongest avoid signal should be DISAGREEMENT between the stuff grade and actual skill-translation. For a POINTS league (rewards K/IP/dominance, under-penalizes walks vs ratio leagues), whiff/K translation and contact damage should be the real avoid signals; command/high-BB% should be ratio-league intuition that does NOT translate.
production_target: research-only (CONFLICT/CONVICTION lens on top of sp_stuff_model Stuff+ rank; NOT an additive point term per lens_value_add_2026-06-11)
framing: in-season -> ros
holdout_years: expanding-window OOS (train years < test year), test 2019,2021-2025
training_years: 2018,2019,2021,2022,2023,2024,2025 (2026 partial excluded from target)
validation_script: scripts/_oneoff/stuff_translation_gap_study.py
date: 2026-06-13
verdict: PASS (whiff-translation + contact-damage VALIDATE; command/high-BB% + declining-velo REJECTED)
purpose: Build a "Stuff Translation Gap" and identify which SP avoid buckets are real for a POINTS league vs ratio-league intuitions that don't translate, extending (not redoing) the VALIDATED Stuff+ engine (sp_stuff_model.py / fg_pitch_modeling_inseason_2026-06-06).
---

## Setup

Substrate: `data/research/xfp_cache/rolling_pitchers_2018_2026.csv` — per-(pitcher,
split_day) leakage-safe panel; all `*_to` cols cumulative-to-cutoff, forward target
`ros_fp_per_start` over `ros_gs` post-cutoff starts.

- SP cohort gate: `gs_to>=5` AND `ros_gs>=3`. Historical years only (2026 partial
  excluded from the forward target). Panel SP-weeks: **19,797**.
- **Stuff measure (cohort selector):** Statcast stuff-proxy = mean within-cell
  z-score of `avg_velo_to` + `avg_pfxz_to` (movement) + `swstr_pct_to`, computed
  WITHIN each (year, split_day) cell so it is a pure cross-sectional as-of grade
  (no leakage). The prompt's documented fallback path; the real FG Stuff+ join is
  used as a cross-check (below). **proxy vs real FG Stuff+ rho = +0.455** (06-06
  cutoff join, n=193) — the proxy tracks the validated grade.
- HIGH-Stuff cohort = top-quartile stuff-proxy within each as-of cell: **5,009 SP-weeks**.
  Forward FP mean **12.62** (sd 4.75) vs full-panel **10.33** — the high-Stuff edge
  is real (+2.29), which is exactly why we need to know which high-Stuff arms to AVOID.
- Translation gaps are RESIDUALS (OLS, within-cell) of the translation metric on
  stuff-proxy: negative residual = stuff not translating to whiffs/Ks.

## Rigor

- **Expanding-window OOS** (train years strictly before the test year); incremental
  value of each bucket measured as **OOS ΔR² over stuff-proxy alone** (per
  `lens_value_add_2026-06-11` — a bucket is only "real" if it adds OOS value over the
  base Stuff+ grade, not in isolation).
- **Convergence-curve leakage check** (per `feedback_convergence_curve_leakage_detector`):
  per-split_day Spearman(bucket, forward FP). A real as-of signal weakens as the RoS
  window shrinks (early > late). Identical lift across all split_days would be a
  leakage smoking gun.

## Per-bucket OOS verdict

OOS incremental over stuff-proxy alone (base OOS R² = +0.026), high-Stuff cohort, n_oos~4,283:

| bucket | definition (as-of) | ΔR² OOS | rho vs base-resid | verdict |
|---|---|---|---|---|
| **(b) no-whiffs K-BB** | `-resid(K-BB% on stuff)` | **+0.073** | −0.251 | **VALIDATES (strongest)** |
| **(b) no-whiffs CSW** | `-resid(CSW% on stuff)` | **+0.053** | −0.204 | **VALIDATES** |
| **(c) damage-prone** | z(barrel)+z(hardhit)+z(xwOBAcon) | **+0.040** | −0.203 | **VALIDATES** |
| (b) no-whiffs swstr | `-resid(swstr% on stuff)` | +0.026 | −0.139 | VALIDATES (weakest of whiff set; collinear w/ proxy) |
| (e) short-outings | `-z(BF/start)` | +0.019 | −0.235 | VALIDATES (modest; proxy only) |
| (a) **no-command** | z(BB%) − z(zone%) | **+0.004** | −0.125 | **REJECTED (ratio-league noise)** |
| (d) incomplete-arsenal | `-z(chase)` proxy | −0.003 | −0.035 | NOISE (not derivable; proxy fails) |
| (f) declining-velo | `-z(velo_last21 − velo_to)` | **−0.012** | +0.030 | **REJECTED (NOISE)** |

### K vs BB attribution (why command is rejected)
Decomposing the K-BB bucket into K-only and BB-only translation residuals (incremental ΔR² over stuff-proxy, high-Stuff cohort):

| component | ΔR² OOS | rho |
|---|---|---|
| low-K translation residual | **+0.062** | −0.225 |
| high-BB translation residual | +0.010 | −0.130 |
| raw BB% | +0.012 | −0.139 |
| raw low-zone% | **−0.005** | −0.050 |

**~85% of the K-BB avoid signal is the K side.** Raw BB% and raw zone% are tiny-to-
negative as incremental terms. This independently reproduces the prior finding
(`fg_pitch_modeling_inseason_2026-06-06`: Location+/command REJECTED for points) and
the floor finding (`sp_floor_model_2026-06-06`: command shows up in DOWNSIDE/bust, not
the mean — here it's near-zero for the forward MEAN among high-Stuff arms). The points-
league mechanism: walks are under-penalized (−1 BB) vs the K/IP upside they trade for.

## Convergence-curve leakage check (clean)

Per-split Spearman(bucket, forward FP), early (split<=79) vs late (>=135):

| bucket | mean rho | early | late |
|---|---|---|---|
| no-whiffs K-BB | −0.329 | −0.327 | −0.320 |
| no-whiffs CSW | −0.283 | −0.290 | −0.244 |
| short-outings | −0.258 | −0.258 | −0.236 |
| damage-prone | −0.235 | −0.250 | −0.227 |
| no-command | −0.165 | −0.188 | −0.163 |
| declining-velo | +0.005 | −0.029 | +0.041 |

Validating buckets show early >= late (signal decays as RoS window shrinks) — the
expected as-of pattern, NOT a flat identical-across-splits leakage signature.
Declining-velo hovers at zero with a sign flip — confirming NOISE, not leakage.

## FG real Stuff+ / Location+ cross-check (06-06 cutoff, n=193)
- real Stuff+ vs forward FP: rho **+0.450** (p 5e-11) — Stuff+ validated, consistent with prior.
- real Location+ vs forward FP: rho **+0.072** (p 0.32) — command does NOT predict forward points (REJECTED, consistent with prior).
- real BB% vs forward FP: rho −0.200 — present but weak, and (above) near-zero INCREMENTAL over the stuff grade.

## "Avoid Risk" composite (validating buckets only)

`AvoidRisk = mean[ no-whiffs(K-BB) , damage-prone , short-outings ]` (all within-cell z).
Command and declining-velo deliberately EXCLUDED (rejected).

- OOS incremental over stuff-proxy: **ΔR² +0.116** (base +0.026 -> full +0.142).
- Monotonic quintile forward FP (high-Stuff cohort, Q5 = highest AvoidRisk):
  Q1 **15.43** -> Q2 13.81 -> Q3 12.34 -> Q4 11.35 -> Q5 **10.58**. **Q5−Q1 = −4.85 FP/start.**
- Honesty caveat: even Q5 (worst high-Stuff arms) sits ~+0.3 above the FULL-PANEL mean
  (10.33). So "avoid" means **"don't pay up / don't chase the breakout"**, NOT
  "replacement-level dud." The stuff floor still buys you league-average. This is a
  CONVICTION/CONFLICT downgrade lens, not a drop trigger.

## Practical fantasy rule

When `sp_stuff_model.py` flags a high-Stuff+ breakout/buy-low candidate, DOWNGRADE
conviction if the arm shows the **Stuff Translation Gap**:
1. **Whiffs not following the stuff** — CSW%/K-BB% materially below what the stuff grade
   predicts (negative translation residual). This is the #1 avoid signal. (Eury-Pérez-
   style high-Stuff/high-BB arms are STILL buys — walks don't matter; it's the *K* gap
   that matters.)
2. **Contact damage** — high barrel% / hard-hit% / xwOBA-on-contact despite good stuff.
3. **Short outings** — low BF/start caps the IP*3.3 and K accumulation (modest, proxy).

Do NOT downgrade for: high BB% / low zone% / "poor command" alone (ratio-league
intuition, REJECTED for points), or a small recent velo dip (declining-velo NOISE at
the forward-mean horizon — note it can still matter for bust/floor per sp_floor_model,
a different question).

Headline rank stays Stuff+ (sp_stuff_model); AvoidRisk is the conviction layer.

## Scope / honesty notes
- production_target = research-only. Per `lens_value_add_2026-06-11`, this is a
  CONFLICT-surfacing / conviction lens, surfaced alongside the Stuff+ rank, NOT folded
  into rp3/the Stuff+ point forecast as an additive term.
- (d) incomplete-arsenal and (e) poor-workload are PROXIES — the panel has no per-pitch
  arsenal / platoon / TTO splits and no innings column (BF/start is the workload handle).
  (d) is NOISE; (e) validates modestly but is proxy-grade, so treat as secondary.
- Stuff-proxy (not real FG Stuff+) is the cohort selector so the full 24-split rolling
  design + convergence check are possible; the FG join confirms the proxy tracks the
  real grade (rho +0.455) and reproduces the Stuff+ / Location+ directions.
