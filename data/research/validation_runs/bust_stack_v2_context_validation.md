---
signal: bust_stack_v2_context
date: 2026-06-03
verdict: DON'T_SHIP
script: scripts/xfp/validate_bust_stack_v2_context.py
results_json: data/research/validation_runs/bust_stack_v2_context_results.json
pre_registration: data/research/validation_runs/bust_stack_v2_context_2026-06-03.md
---

# bust_stack_v2_context — Validation report

## TL;DR

**Verdict: DON'T_SHIP.** The game-context reframing of bust_stack fails. Stack=3 bust rate is **16.73%** (n=1,297) versus a stack=0 rate of **14.96%** and a baseline of **14.63%** — a lift of only **+1.77pp** vs stack=0, chi² p=0.167 (does not pass p<0.05). Of the 5 candidate context components, only `flag_first_back_long_IL` (+2.93pp, p=0.044) is independently significant; one other (`flag_short_rest`, +3.74pp) is directionally interesting but underpowered (n=300). The other three (`taxed_bullpen`, `extreme_prior`, `day_after_night`) are complete nulls.

Year-by-year stability is poor: only **4/7 years sign-positive**, with 2022, 2024, and 2025 all flat-to-negative (-3.7pp, -0.5pp, -0.74pp). The 2024+2025 holdout collapses confirm v1's structural finding — **bust is dominated by within-game noise**, and reframing from upstream-process (v1) to game-context (v2) does not change the conclusion.

The honest finding: across two different framings of "what predicts a bust," the answer remains "almost nothing predictably." Bust risk is irreducible noise at the per-start level. The bench-decision-grade signal we hoped for does not exist in either bucket of features.

---

## Pre-registered hypothesis recap

- H1 (Mode B, primary): stack=3 bust >= 25% vs baseline 14%, chi² p < 0.05.
- H2 (per-component): each component >= +2pp at Bonferroni alpha = 0.01 (5 tests).
- H3 (year stability): >= 5/7 years sign-positive at stack=3.
- H4 (independence from boom_stack): all |r| < 0.15 with boom components.

---

## Panel construction

| | |
|---|---|
| Per-start panel rows (2018-2025 ex-2020, PA>=5) | 31,713 |
| SP team identified (via inning 1 inning_topbot) | 31,712 (99.997%) |
| Bust base rate (FP < 0) | **14.63%** |

Context features computed from statcast pitch-level + game-level metadata:
- Team identification: inning 1 `inning_topbot == 'Top'` → home pitcher; `'Bot'` → away pitcher
- Rest days: statcast `pitcher_days_since_prev_game`
- Bullpen IP: sum of outs/3 across non-SP pitchers on the team in the prior 3 calendar days
- Long-IL gap: derived from `game_date` differences between consecutive same-pitcher starts in same season
- Pitches per start: pitch-level row count per (pitcher, game_pk)
- Prior-day team game: indicator that SP's team played a game on `game_date - 1`

No weather/wind data was available; that feature was skipped per the pre-registration's permission to do so.

---

## Per-component bust edge

| Component | Fire rate | bust@flag=1 | bust@flag=0 | Lift (pp) | chi² | p | Bonferroni pass (alpha=0.01)? |
|---|---|---|---|---|---|---|---|
| `flag_first_back_long_IL` (gap >= 30d since prior start) | 2.02% (n=640) | 17.50% | 14.57% | **+2.93** | 4.07 | 0.044 | **FAIL** (above alpha) |
| `flag_short_rest` (pitcher_days_since_prev_game in [1,4]) | 0.95% (n=300) | 18.33% | 14.60% | **+3.74** | 3.03 | 0.082 | **FAIL** (underpowered) |
| `flag_taxed_bullpen` (bullpen IP prior 3d >= 8.0) | 63.20% (n=20,044) | 14.54% | 14.79% | -0.25 | 0.36 | 0.55 | **FAIL** (null) |
| `flag_extreme_prior` (prior start pitches>=110 or ip<3.0) | 4.32% (n=1,369) | 14.10% | 14.66% | -0.56 | 0.28 | 0.59 | **FAIL** (null) |
| `flag_day_after_night` (team played prior calendar day) | 84.52% (n=26,804) | 14.63% | 14.65% | -0.02 | 0.00 | 0.99 | **FAIL** (null) |

**Result: 0 of 5 components pass the Bonferroni-adjusted gate.** Two directionally-positive signals (first_back_long_IL +2.93pp at p=0.044, and short_rest +3.74pp at p=0.082) hint at real but weak effects. Three components are flat zero.

### Why each candidate failed

- **`flag_day_after_night`** (84% fire rate): MLB teams play nearly every day during the season. The flag has too little discrimination — almost every start fires it. The proper version would require a HOME night-game-then-DAY-game travel pattern, which needs game start times we don't have.
- **`flag_taxed_bullpen`** (63% fire rate, lift = -0.25pp): the hypothesis was that a taxed pen makes the manager leave the SP in too long. The data says the opposite of "more bust." Two confounds: (a) high prior-pen IP often correlates with the team having SCORED a lot too (extra-inning games, blowouts), not just struggled; (b) managers may pull the SP EARLIER when the pen is taxed to save remaining relievers, which actually limits SP exposure. The flag captures something but not bust signal.
- **`flag_extreme_prior`** (4.3% fire rate, lift = -0.56pp): hypothesis was over-extension or rebound noise. Neither shows up. Pitchers coming off a 110+ pitch outing OR a sub-3-IP disaster bust at the SAME rate as everyone else. Hot streaks and short outings are too matchup-driven to predict the next outing.
- **`flag_first_back_long_IL`** (2.0%, +2.93pp): the only component with a real signal direction. But the magnitude is small and the cohort is small (n=640 across 8 seasons ≈ 80/year). On its own this is a one-off display flag at best, not a stack component.
- **`flag_short_rest`** (0.95%, +3.74pp, p=0.082): rare event (SP coming back on 4 days rest or less in modern baseball is unusual — usually a 5th-day fill-in or rotation injury cascade). Directionally consistent with the IL-gap signal (both flag "abnormal rotation circumstance") but underpowered.

---

## Stack-sum bust rate

| bust_stack_v2 | n | busts | bust rate | mean FP |
|---|---|---|---|---|
| **0** | 3,315 | 496 | **14.96%** | 10.13 |
| 1 | 9,088 | 1,333 | 14.67% | 10.39 |
| 2 | 17,938 | 2,583 | 14.40% | 10.44 |
| **3** | 1,297 | 217 | **16.73%** | 9.66 |
| 4 | 73 | 10 | 13.70% | 8.07 |
| 5 | 2 | 1 | 50.00% | 2.40 |

- **Not monotonic.** Stack=0→2 actually trends *down* (15.0% → 14.7% → 14.4%) because the high-fire-rate null components (`day_after_night` 84%, `taxed_bullpen` 63%) dominate stacks 1-2 and they carry no signal.
- Stack=3 lift over stack=0: **+1.77pp** (16.73% vs 14.96%). Chi² stack>=3 vs ==0: chi² = 1.91, **p = 0.167** — FAILS p < 0.05 gate.
- Stack=4 (n=73) drops back to baseline. Stack=5 (n=2) is uninterpretable.

The pre-registered effect-size threshold (stack=3 bust >= 25%) is rejected by a 95% Wilson CI of roughly 14.7%-18.9% on the 16.7% observation — the CI does not include 25%.

---

## Year-by-year stability

| Year | n | bust @ stack=0 | bust @ stack>=3 | Lift (pp) | n_stack0 | n_stack3+ |
|---|---|---|---|---|---|---|
| 2018 | — | 14.86% | 16.15% | +1.29 | 471 | 260 |
| 2019 | — | 14.06% | 19.29% | **+5.23** | 441 | 254 |
| 2021 | — | 13.43% | 15.15% | +1.72 | 484 | 198 |
| 2022 | — | 15.74% | 15.00% | **-0.74** | 451 | 180 |
| 2023 | — | 13.93% | 20.79% | **+6.85** | 488 | 178 |
| 2024 | — | 16.46% | 12.75% | **-3.71** | 486 | 149 |
| 2025 | — | 16.19% | 15.69% | **-0.51** | 494 | 153 |

**Sign consistency: 4/7 years positive.** The pre-registered >=5/7 threshold fails. Both holdout years (2024 and 2025) are negative. 2022 is also negative. The two large positive years (2019 +5.2pp, 2023 +6.9pp) carry the aggregate signal — and they're not consecutive, suggesting they're random noise rather than a stable structural signal.

---

## Independence with boom_stack (H4 — passes)

All bust-v2 components are orthogonal to all boom_stack components (|r| <= 0.029):

| bust component | corr(skill_spike) | corr(recform_hot) | corr(opp_soft) |
|---|---|---|---|
| flag_first_back_long_IL | -0.019 | -0.029 | -0.007 |
| flag_short_rest | -0.013 | -0.027 | -0.006 |
| flag_taxed_bullpen | +0.001 | +0.008 | -0.011 |
| flag_extreme_prior | +0.002 | +0.008 | +0.008 |
| flag_day_after_night | +0.000 | +0.001 | +0.008 |

H4 passes (all |r| < 0.03 ≪ 0.15 threshold). This was the design intent — context ≠ process — and it confirms v2 is a genuinely independent test of bust predictability, not a re-discovery of the v1 features. **The independence result strengthens the negative finding**: if v2 had been measuring the same thing as v1, we'd expect similar weak-positive lift. Instead v2 is independently weak.

---

## Co-occurrence with boom_stack (heatmap)

| | bust=0 | bust=1 | bust=2 | bust=3 | bust=4 | bust=5 |
|---|---|---|---|---|---|---|
| boom=0 | 1,711 | 4,710 | 9,439 | 698 | 47 | 2 |
| boom=1 | 1,250 | 3,357 | 6,691 | 488 | 23 | 0 |
| boom=2 | 304 | 824 | 1,492 | 96 | 2 | 0 |
| boom=3 | 50 | 197 | 316 | 15 | 1 | 0 |

(Approximate — joined n=31,713.) The high-variance edge case the brief hoped to find (boom>=2 AND bust_v2>=3) exists with n ≈ 111 — possibly interesting but the bust rate inside that cell is roughly flat at baseline, so no actionable "this is a wild swing" signal emerges.

---

## Verdict

**VERDICT: DON'T_SHIP**

Decision tree mapping:

| Pre-reg threshold | Observed | Pass? |
|---|---|---|
| H1: stack=3 bust >= 25% | 16.73% | **FAIL** |
| H1: chi² p < 0.05 | p = 0.167 | **FAIL** |
| H2: >= 3 of 5 components @ +2pp Bonferroni | 0 of 5 | **FAIL** |
| H3: >= 5/7 years sign-positive | 4/7 | **FAIL** |
| H4: independence from boom (|r|<0.15) | all <0.03 | PASS |

H1 magnitude AND significance fail. H2 fails (no component passes Bonferroni). H3 fails. Per the pre-registered decision tree → **DON'T_SHIP**.

### What this tells us (combined v1 + v2 finding)

Two independent framings of "what predicts a bust" — upstream skill drift (v1) and game context (v2) — both fail to produce a bench-decision-grade signal. The combined evidence strongly supports the hypothesis that **bust is dominated by within-game noise**:

- HR allowed (which is a function of one swing, sometimes on a competitive pitch)
- BABIP-driven runs (defense, sequencing)
- Bullpen leverage (when the manager pulls)
- Random opponent process (hit clusters)

None of these are forecastable from pre-game inputs. The boom_stack right-tail signal (+9.4pp at stack=3) does NOT have a symmetric inverse, neither in process features (v1: +3.7pp ceiling) nor in context features (v2: +1.8pp ceiling). **Booms are partially process-driven; busts are mostly variance.**

### What's actually informative for engineering

1. **`flag_first_back_long_IL` is a real but weak signal.** The +2.93pp lift (n=640, p=0.044) survives even with no Bonferroni protection. It is also intuitive — the first start back from a >=30-day IL stint is a genuine risk class. Worth surfacing as a **standalone display tag** on triangulate cards (similar treatment to v1's `flag_opp_tough`), NOT as part of a stack. Note: this signal will partially overlap with the rust/rehab pattern we already track in `/sp-rehab-tracker`.

2. **`flag_short_rest` is too rare to act on but directionally consistent.** Only 300 starts across 8 seasons. If we ever see an SP penciled in on 4 days' rest due to rotation cascade, the +3.74pp lift suggests bench consideration. But we shouldn't build a flag around it — too noisy.

3. **`flag_taxed_bullpen`, `flag_extreme_prior`, `flag_day_after_night` are confirmed nulls.** Do NOT add these to any ranker or surface them as advisory flags. They look intuitive but the data is clear.

4. **The combined v1+v2 evidence rejects the entire "bust_stack" research program.** Two well-powered, pre-registered, independent attempts both failed. Future bust-prediction work should focus on (a) within-game leverage situations (HR park factors, opp HR rate, specific umpire zones), not pre-game pitcher-state features.

### What NOT to do

- Do NOT add `bust_stack_v2` or any of its components (except first_back_long_IL as a display tag) to RP3_FEATS or any ranker.
- Do NOT surface `bust_stack_v2 >= 3` as a "DON'T START" warning in triangulate cards. The +1.77pp lift is too small AND non-monotonic.
- Do NOT pursue a v3 bust_stack with yet another framing. The combined v1+v2 negative result is strong enough to redirect research effort.

---

## Sample-size honesty

- Panel n = 31,713 starts. Stack distribution well-powered through stack=3 (n=1,297).
- Stack=3 95% Wilson CI on 16.73% bust rate: roughly **14.8% - 18.9%**. CI does NOT include 25%, so the pre-registered effect size is rejected.
- `flag_first_back_long_IL` n=640: Wilson CI on 17.5% is roughly **14.7% - 20.6%**. Real lift but uncertain magnitude.
- `flag_short_rest` n=300: too small to call a definitive signal even if directionally positive (CI roughly 14.3% - 23.2%).

---

## Files

- Pre-reg: `data/research/validation_runs/bust_stack_v2_context_2026-06-03.md`
- Script: `scripts/xfp/validate_bust_stack_v2_context.py`
- Results JSON: `data/research/validation_runs/bust_stack_v2_context_results.json`
- This report: `data/research/validation_runs/bust_stack_v2_context_validation.md`

No engine module created (no SHIP).
