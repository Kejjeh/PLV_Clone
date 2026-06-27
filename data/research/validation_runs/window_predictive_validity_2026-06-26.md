# Rolling-window predictive validity for hitter FP — validation record

**Date:** 2026-06-26
**Status:** VALIDATED (leakage-safe, robustness-confirmed). Display/decision guidance only —
does NOT change any projection model (Rule 13).
**Trigger:** "Should we look at L7/L14/L21/Lmonth?" → "validate the stabilization cutoffs on our
own data rather than the textbook ones."
**Engine:** `scripts/_oneoff/validate_windows.py` (gitignored one-off). Panel → `.cache/window_panel.csv`.

## Question

For 2026 hitters, (A) which trailing rolling window best predicts a hitter's FORWARD 14-day
BrownU FP/g, (B/D) does recent form add signal beyond the established level, and (C/E) which
trailing METRIC is the best — and the best INCREMENTAL — leading indicator of forward FP.

## Data + leakage controls

- Per-game BrownU FP from `boxscore_hitters.parquet` (full 2026, Mar 25–Jun 25); per-PA/BBE
  metrics from `statcast_2026.parquet`.
- **Forward target** = next 14 calendar days STRICTLY after anchor `t` (games in `(t, t+14]`,
  ≥4 games). Trailing windows end at `t` inclusive. A game on `t` lands in trailing only → no
  temporal overlap (independently audited: PASS).
- Anchors sampled ≥7 days apart per player; require ≥15 season games. CIs = **player-cluster
  bootstrap** (resample players, B=1000).
- **Robustness:** re-run with anchors ≥**14** days apart so forward windows are fully
  non-overlapping (kills the pseudo-replication that narrows CIs). All conclusions held.

## Results (point r; [2.5, 97.5] cluster-bootstrap CI)

### A) Trailing FP/g window → forward 14d FP/g (marginal)
| Window | overlapping (n=2993) | independent (n=1634) |
|---|---|---|
| L7 | +0.176 [.136,.212] | +0.150 [.097,.196] |
| L14 | +0.238 | +0.227 |
| L21 | +0.272 | +0.254 |
| L30 | +0.285 | +0.270 |
| **Season-to-date** | **+0.331 [.283,.375]** | **+0.317 [.266,.363]** |

Monotonic — longer window predicts better; full season-to-date is the single best predictor.
Note this is **partly measurement-error attenuation** (L7 means are ~2× noisier than season
means; a noisier proxy of the same talent must correlate less). Read it as "longer windows
estimate the predictive LEVEL more precisely," NOT "older games matter more."

### B vs D) Does recent form add INCREMENTAL signal? (the key reconciliation)
- **B — short window | FULL season-to-date** (control CONTAINS the window): partial r ≈ **0.00**
  for L7/L14/L21/L30 (all CIs span 0). Conservative-by-construction (collinear) — flagged in audit.
- **D — short window | season EXCLUDING that window** (clean, no collinearity):
  L7 **+0.115**, L14 +0.162, L21 +0.185, L30 +0.202 — all CIs exclude 0 (independent run:
  +0.098 → +0.181, also all exclude 0).

**Reconciliation:** recent FP is NOT noise — it updates the forward estimate vs an OLDER
baseline. But it adds ~nothing beyond the FULL running season average, because the season
average already incorporates the recent games. **Recency earns its weight by being folded into
the running level; there is NO extra "hot-streak momentum" term on top of that.** → Keep the
season line current; do not double-count a streak. (Consistent with Rule 13: form is context,
not additive point-forecast lift.)

### C/E) Process metrics as leading indicators (trailing L21d → forward FP)
| Metric | C) marginal r | E) partial r \| season FP (incremental over level) |
|---|---|---|
| L21 FP/g (level) | +0.272 | — |
| **bat speed** | +0.136 | **+0.076 [.024,.132] ✓ adds beyond level** |
| K% | −0.141 (strongest abs.) | −0.026 (redundant) |
| xwOBACON | +0.115 | −0.007 (redundant) |
| HardHit% | +0.107 | +0.025 (redundant) |
| BB% | +0.060 | +0.004 (redundant) |

**Bat speed is the ONLY process metric carrying forward signal the FP level does not already
contain** (incremental r excludes 0 in BOTH the overlapping and independent runs). K%/xwOBACON/
HardHit%/BB% are confirmatory, not additive. Empirical confirmation of the "fast-stabilizing
early read" thesis underpinning `/trending`.

## Practical guidance (tuned to OUR numbers)

1. **Anchor on the season-to-date level** — best forward predictor (this is effectively what rh3 does).
2. **L21d is the recent-form sweet spot** — captures real incremental recency (+0.18) without the
   L7 noise penalty. Keep L21d-vs-baseline as the contact-quality diagnostic (CLAUDE.md #8).
3. **L7 is trustworthy ONLY for bat speed** — the one signal that both stabilizes that fast and
   adds forward signal. Everything else at L7 is noise.
4. **No separate momentum term** in a projection — recency is already in the level (Rule 13).

## Caveats (kept honest)
- CIs under overlapping anchors run ~25–40% narrow (pseudo-replication); the gap=14 re-run is the
  honest read and confirms all signs/ranks/significance.
- Population = **established everyday regulars** (≥4 fwd games, ≥15 season games). Platoon/callup/
  injury cases excluded — exactly where a "streak" might encode a real role/health change. Do not
  extend to those without re-test.
- Effect sizes are modest (best single-window r ~0.32; bat-speed increment ~0.08). These are tilts,
  not strong predictors — per-2-week hitter FP is mostly irreducible.

## Level-formula bake-off (which "level" metric to rank by)

Follow-up to settle "should the indicator be a weighted formula?" Same panel/leakage
controls; candidates are per-game RATE estimators of the level computed from games ≤ t,
scored on forward-14d FP/g; paired cluster-bootstrap vs `raw_season`.
Engine: `scripts/_oneoff/validate_level_formula.py`. League game-mean POP = 1.80.

| Candidate | forward-FP r | Δr vs raw season (paired) |
|---|---|---|
| raw **total** FP (volume) | +0.289 | **−0.041 [−.076,−.006] WORSE** |
| **raw season FP/g (rate)** | +0.331 | — (baseline) |
| EWMA half-life 10 (heavy recency) | +0.305 | **−0.026 [−.041,−.007] WORSE** |
| EWMA half-life 40 (light) | +0.329 | −0.001 (tie) |
| **shrunk K10 → league mean** | **+0.337** | **+0.006 [+.001,+.011] better** |
| shrunk K25 | +0.338 | +0.007 (tie) |
| blend 0.7·season + 0.3·L30 | +0.323 | −0.008 [−.015,−.001] WORSE |

**Conclusions:** (1) rank by the **RATE, not the total** (total is the worst — rewards
playing time + early overproduction); (2) **recency-weighting hurts** (heavy EWMA / L30
blend strictly worse; confirms the no-momentum finding); (3) the **only** weighting that
helps is a **light shrink toward the league mean** (~+0.006 r, thin-sample insurance) —
which is exactly what **rh3 already encodes**. So the validated best simple indicator =
**lightly-shrunk season-to-date FP/g** ≈ rh3.

## Implications shipped
- `/trending` SKILL.md + `/breakout-sustainability` SKILL.md: cite these numbers; bat speed = the
  validated incremental early read; L7 trust-list = bat speed only.
- CLAUDE.md fast-path #12: recency adds no momentum beyond the running level; rank level by the
  shrunk RATE not the total; bat speed is the one process metric with incremental forward signal.
- **NEW skill `/level-board`** (`scripts/xfp/run_level_board.py`): ranks roster+FA hitters by the
  validated Level FP/g (shrunk season-to-date rate, K=20) and flags the **LEVEL-vs-rh3 divergence**
  (🔥RIDING-HOT producing-above-model / 💎PEDIGREE model-sees-more / aligned). Context-only (Rule 13);
  rh3 stays the headline. Canonical: TJ Rumfield #1 by total FP but RIDING-HOT (rh3 #82, regression
  risk) vs Luis García Jr. aligned (Δ+0.19, a real model-backed everyday bat).
