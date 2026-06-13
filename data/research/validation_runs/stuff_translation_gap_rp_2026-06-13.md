---
signal: stuff_translation_gap_rp
formula: Among HIGH-Stuff RELIEF pitchers (top-quartile stuff-proxy within each as-of (year, split_day) cell), build a "Stuff Translation Gap" (within-cell residual of CSW%/swstr%/K-BB% on the stuff measure) AND test five RP "avoid buckets" for predicting LOW forward RP fantasy value: (a) walk-volatility, (b) HR-volatility, (c) low-leverage-trust (good stuff but no save/hold path), (d) one-pitch-fragility (proxy), (e) recent decline (proxy). Each bucket = a pre-week, as-of, within-cell z-feature (POSITIVE = hypothesized worse forward FP), OOS-tested for INCREMENTAL value OVER the stuff-proxy alone.
outcome: forward BrownU RP FP per game = (season_fp - fp_to)/(season_g - g_to) over strictly-post-cutoff appearances. BrownU RP scoring K + IP*3.3 - H - 2ER - BB - HBP + 5SV + 2HLD, derived from the strictly-cumulative count columns (k_to,bb_to,h_to,er_to,outs_to,hbp_to,sv_to,hld_to); last split per (pitcher,year) = season totals. Leakage-safe: all features *_to cumulative-to-cutoff or *_lag1 prior-year; target strictly post-cutoff.
expected_sign: avoid features negatively predict forward FP among high-Stuff relievers
theory: RP fantasy value is ROLE/SAVE-driven (validated ranker = rprs2, NOT rp3). Saves worth 5, holds 2. So unlike SP (where skill-translation dominates), the strongest RP avoid bucket should be LOW-LEVERAGE-TRUST: elite stuff with no save/hold path is the biggest avoid because the dominant point source is structurally absent. Skill-translation (whiff/K, contact damage) should matter SECONDARILY (it gates the ratio side + earns the leverage role), while command/high-BB% should remain ratio-league noise for points (per fg_pitch_modeling_inseason_2026-06-06).
production_target: research-only (CONFLICT/CONVICTION lens on top of rprs2 / leverage_tier; NOT an additive point term per lens_value_add_2026-06-11)
framing: in-season -> ros
holdout_years: expanding-window OOS (train years < test year), test 2019,2021-2025
training_years: 2018,2019,2021,2022,2023,2024,2025 (2026 partial excluded from target)
validation_script: scripts/_oneoff/stuff_translation_gap_rp_study.py
date: 2026-06-13
verdict: PASS (low-leverage-trust / no-save-path DOMINATES and VALIDATES; K-BB translation + walk-vol + recent-decline VALIDATE secondarily; HR-vol + one-pitch-fragility + swstr-translation REJECTED/NOISE)
purpose: RP companion to stuff_translation_gap_sp_2026-06-13. Identify which RP avoid buckets are real for a POINTS+SV/HLD league, and confirm the role/leverage path dominates skill-translation for relievers (the structural reason rprs2 beats rp3 for RP).
---

## Setup

Substrate: `data/research/xfp_cache/rolling_relievers_2018_2026.csv` — per-(pitcher,
split_day) leakage-safe panel; `*_to` cumulative-to-cutoff, `*_lag1` prior-year.

- **Forward target (derived).** The panel has no `ros_fp_per_start` for relievers and
  `fp_with_role_to` is a ROLLING (non-cumulative) value, so it is NOT usable as a
  cumulative anchor. Instead I derived BrownU RP FP from the strictly-cumulative count
  columns (verified monotone: k_to/bb_to/h_to/er_to/outs_to/hbp_to/sv_to/hld_to all
  monotone frac 1.00). Season totals = last split per (pitcher,year). **forward FP/game
  = (season_fp − fp_to)/(season_g − g_to)** over strictly-post-cutoff appearances.
- **RP cohort gate:** `gs_to<=3` (true relievers), `g_to>=10`, `fwd_g>=8`. Historical
  years only (2026 partial excluded from target). Panel RP-weeks: **25,542**.
- **Stuff measure (cohort selector):** Statcast stuff-proxy = within-cell mean z of
  `avg_velo_to` + `swstr_pct_to` (the documented velo+swstr fallback; RP movement col
  is noisier). Computed WITHIN each (year, split_day) cell — pure cross-sectional as-of
  grade, no leakage. **FG cross-check (2023 pre, n=269): RP proxy vs real FG Stuff+ rho
  +0.318**; and **FG Stuff+ vs forward RP FP/g rho +0.341** (n=220) — the stuff floor is
  real for RP too, consistent with the SP study.
- HIGH-Stuff cohort = top-quartile stuff-proxy within each as-of cell: **6,482 RP-weeks**
  (6,475 usable). Forward FP/g mean **3.43** vs full-panel **2.68** (+0.75) — the
  high-Stuff edge is real, which is why we need to know which high-Stuff RP to AVOID.

## Rigor

- **Expanding-window OOS** (train years strictly before test year). Incremental value =
  **OOS ΔR² over stuff-proxy alone** (per `lens_value_add_2026-06-11`: a bucket is only
  "real" if it adds OOS value over the base grade). Base OOS R² (stuff alone) = **+0.122**,
  n_oos = 5,512.
- **Leakage verification.** Role/leverage features (`role_*_lag1`, `sv_per_g_lag1`,
  `hld_per_g_lag1`) confirmed PRIOR-YEAR lagged — nunique per (pitcher,year) = 1 (constant
  within a season). No current-year/future-role feature touches the buckets. The "no-save-
  path" mechanism is partly structural (a no-leverage RP cannot earn saves) — but that is
  exactly the fantasy reality, captured leakage-safely via the lag.
- **Convergence-curve leakage check** (per `feedback_convergence_curve_leakage_detector`):
  per-split Spearman(bucket, forward FP), early (≤79) vs late (≥135). A real as-of signal
  decays as the RoS window shrinks; identical-across-splits would be a leakage smoking gun.

## Per-bucket OOS verdict

OOS incremental ΔR² over stuff-proxy alone (base +0.122), high-Stuff RP cohort, n_oos~5,512:

| bucket | definition (as-of) | ΔR² OOS | spearman | verdict |
|---|---|---|---|---|
| **(c) no-save-path** | `−z(sv/g_lag1 + 0.5·hld/g_lag1)` | **+0.066** | −0.343 | **VALIDATES (strongest)** |
| **(c) low-leverage-trust** | `role_middle_lag1 − z(sv_path)` | **+0.061** | −0.332 | **VALIDATES** |
| **(b') no-K K-BB translation** | `−resid(K%−BB% on stuff)` | **+0.031** | −0.307 | **VALIDATES** |
| (e) recent-decline (proxy) | `−z(g_to)` (workload/established) | +0.024 | −0.144 | VALIDATES (modest; proxy only) |
| (a) walk-volatility | `z(bb%) − z(zone%)` | +0.014 | −0.202 | VALIDATES (modest) |
| (b'') damage-prone | `z(barrel)+z(hardhit)+z(xwOBAcon)` | +0.014 | −0.123 | VALIDATES (weak) |
| no-whiff CSW translation | `−resid(CSW% on stuff)` | +0.007 | −0.204 | weak / borderline |
| (b) HR-volatility | `z(barrel)+z(hardhit)−z(gb)` | +0.004 | −0.059 | **REJECTED (noise)** |
| no-whiff swstr translation | `−resid(swstr% on stuff)` | −0.001 | −0.077 | **REJECTED (collinear w/ proxy)** |
| (d) one-pitch-fragility (proxy) | `−z(o_swing%)` | −0.005 | −0.126 | **NOISE (not derivable; proxy fails)** |

## KEY RP TEST — role-path vs skill-translation (head-to-head)

| model | ΔR² OOS over stuff |
|---|---|
| stuff + **role-path** (`b_lowlev`) | **+0.061** |
| stuff + skill-path (`K-BB` + `CSW` + `damage`) | +0.035 |
| stuff + both | +0.094 |
| stuff + sv_path (positive leverage signal) | **+0.066** |

**The role/leverage path DOMINATES the entire skill-translation set for RP fantasy value
(+0.061 vs +0.035), and the no-save-path bucket alone is the single strongest avoid
signal (ΔR² +0.066, spearman −0.343).** This is the expected RP-specific result and the
structural reason the validated RP ranker is **rprs2** (role/save-driven), not rp3:
saves/holds (5/2 pts) are the dominant point source, so an elite-stuff RP with no
leverage role is the biggest avoid — the skill is real but the point pathway is absent.
The two paths are largely complementary (both together +0.094 ≈ sum), i.e. skill
translation still earns its keep secondarily (it gates the ratio side and is how an arm
EARNS the leverage role), but it is not the headline avoid for relievers.

## Convergence-curve leakage check (clean)

Per-split Spearman(bucket, forward FP), early (≤79) vs late (≥135):

| bucket | mean | early | late |
|---|---|---|---|
| no-save-path | −0.343 | −0.382 | −0.318 |
| low-leverage-trust | −0.332 | −0.375 | −0.274 |
| no-K K-BB | −0.307 | −0.275 | −0.328 |
| walk-vol | −0.202 | −0.169 | −0.223 |
| HR-vol | −0.059 | −0.049 | −0.048 |

The dominant role-path buckets show **early ≥ late** (signal decays as the RoS window
shrinks) — the expected as-of pattern, NOT a flat identical-across-splits leakage
signature. (no-K K-BB is roughly flat/slightly stronger late, which is mild but consistent
with K-rate stabilizing; it is not the headline and not the leakage concern.) HR-vol
hovers near zero at both ends — confirming noise, not leakage.

## "RP Avoid Risk" composite (validating buckets)

`AvoidRisk = mean[ low-leverage-trust , no-K(K-BB) , damage-prone ]` (all within-cell z).
HR-volatility, one-pitch-fragility, and swstr-translation deliberately EXCLUDED (rejected/noise).

| composite | ΔR² OOS | Q1 fwd FP/g → Q5 (Q5 = highest AvoidRisk) |
|---|---|---|
| low-leverage only | +0.061 | 4.78 → 2.96 (Q5−Q1 −1.82) |
| low-leverage + damage | +0.078 | 4.60 → 2.87 (Q5−Q1 −1.73) |
| **low-leverage + K-BB + damage** | **+0.123** | **4.76 → 2.60 (Q5−Q1 −2.16)** |

The three-bucket composite roughly DOUBLES the OOS R² over stuff alone (+0.122 → +0.245)
and sorts forward RP FP/g monotonically. **Q5−Q1 = −2.16 FP/g.** Honesty caveat: even Q5
(worst high-Stuff RP) sits near the full-panel mean (2.68), so "avoid" means **"don't
chase the elite-stuff middle-reliever breakout / don't pay leverage prices for a
non-leverage arm,"** NOT "replacement-level dud." The stuff floor still buys league-average
RP innings.

## Practical fantasy rule

When an elite-Stuff reliever tempts you (high velo + whiff), DOWNGRADE conviction if:

1. **No save/hold path** (the #1 RP avoid). Lagged `sv_per_g`/`hld_per_g` ≈ 0 and prior
   role = middle relief. Elite stuff with no leverage = capped fantasy ceiling in a
   SV/HLD league — the 5/2-point pathway is structurally absent. Cross-check
   `leverage_tier` / CLOSER-FIREMAN tags + the prior-closer-on-IL / team-prior-closer
   context columns before paying up (those flag the arms with a PATH to leverage).
2. **K not following the stuff** (K%−BB% translation residual materially negative) — the
   skill side that gates both the ratio floor and the path to a leverage role. Secondary
   to role but real.
3. **Contact damage** (high barrel%/hard-hit%/xwOBA-on-contact) — weak but additive.

Do NOT downgrade for: high HR-rate / flyball profile in isolation (HR-vol REJECTED as
noise here), "one-pitch" reliever framing (not derivable — proxy is NOISE), or a small
recent-form/workload dip alone (proxy, modest). High BB% is only a mild secondary signal
(walk-vol +0.014) — consistent with the SP finding that command is ratio-league intuition
that under-translates to points; for RP the K side of K-BB carries the weight.

**Headline RP rank stays rprs2 (role/save-driven); RP-AvoidRisk is the conviction/conflict
layer that flags elite-stuff arms whose point pathway is missing.**

## Scope / honesty notes
- production_target = research-only. Per `lens_value_add_2026-06-11`, this is a
  CONFLICT-surfacing / conviction lens surfaced alongside the rprs2 / leverage_tier rank,
  NOT folded into the point forecast as an additive term.
- The role-path buckets are partly MECHANICAL (a non-leverage RP cannot earn saves), which
  is by design the dominant fantasy structure — captured leakage-safely via prior-year lag.
  The honest read: this validates the rprs2-over-rp3 architecture for RP rather than
  discovering a hidden new signal. The genuinely NEW finding is that among high-Stuff arms,
  **K-translation (not HR-vol, not command, not "one-pitch")** is the secondary skill avoid.
- (d) one-pitch-fragility and (e) recent-decline are PROXIES — the RP panel has no per-pitch
  arsenal split and no last-21 velo column (g_to workload is the only decline handle).
  (d) is NOISE; (e) validates modestly but is proxy-grade — treat as tertiary.
- Stuff-proxy (not real FG Stuff+) is the cohort selector so the full 24-split rolling
  design + convergence check are possible; the FG join confirms the proxy tracks the real
  grade (RP rho +0.318) and that FG Stuff+ predicts forward RP FP (rho +0.341).
- Small-n honesty: cohort is 6,475 high-Stuff RP-weeks across 7 seasons; per-test-year
  OOS folds are 800-1,000 each — adequate but not huge. Directions are stable across the
  convergence-curve splits and the FG cross-check, which is the main robustness evidence.
