---
signal: sp_floor_bust_model
formula: per-start P(bust, fp<5) from pre-start features — cumulative season-to-date prior_k_pct + prior_bb_pct (expanding, shifted, no leak), opponent lineup_xfp, days_rest, n_prior_starts. Logistic regression.
outcome: per-start bust (BrownU SP FP < 5)
expected_sign: prior_k_pct − ; prior_bb_pct + ; lineup_xfp +
theory: Stuff+ shifts the MEAN but not variance (std flat across Stuff+ tiers); the floor is a separate axis driven by command (K−BB%) — strikeouts end innings without balls in play that snowball into duds.
production_target: research-only
framing: per-start, in-season
holdout_years: [2023, 2024, 2025]
training_years: [2018, 2019, 2021, 2022]
validation_script: scripts/xfp/sp_floor_model.py
date: 2026-06-06
verdict: PASS-AS-RANKING-TILT
purpose: Build the "avoid bad days" floor lens that Stuff+ cannot be. Ship /sp-floor skill if it ranks risk out-of-sample.
---

# SP floor / bust-probability model

## Motivation
Stuff+ validated as a MEAN predictor (`fg_pitch_modeling_inseason`), driven by
velocity. But std FP is flat (~8.9) across every Stuff+ tier — high stuff makes
duds *rarer* (bust% 31.6%→14.7% from <95 to 110+) without making a pitcher less
volatile. So the floor needs its own model.

## Two layers of evidence

**Season-level (n=770 pitcher-seasons, R²=0.46):** what makes a bust-prone arm,
standardized coefs (pp bust per +1 SD): **K% −6.3 (dominant), BB% +2.5, barrel%
+1.5, hard-hit% +0.9, stuff_plus −0.4, GB% −0.6.** Floor = K−BB%; raw stuff and
grounders barely matter once K% is controlled. Staff check: corr(K−BB%, measured
bust%) = −0.43.

**Per-start (n train 13,682 / test 10,435):** logistic P(bust). **TEST AUC 0.601.**
Per-start bust is mostly irreducible (matches std-flat), so this is a RANKING TILT
not a game predictor. But well-calibrated with real separation:

| predicted-bust quintile (test) | pred% | actual% | n |
|---|---|---|---|
| Q1 safest | 16 | 18 | 2087 |
| Q3 | 25 | 26 | 2087 |
| Q5 riskiest | 36 | 38 | 2087 |

Riskiest quintile busts 2.1× the safest. Standardized coefs: prior_k_pct −0.39
(dominant), lineup_xfp +0.17, prior_bb_pct +0.07, n_prior −0.05, days_rest −0.01.
Ablation AUC: command-only 0.595 → +opponent 0.603 → full 0.601 (~85% command,
~15% opponent; rest/sample negligible). **Command-only is enough → staff board
needs no live matchup data.**

## Verdict — PASS as a ranking tilt (not a per-game predictor)
Shipped as `/sp-floor` (engine `sp_floor_model.py`, `staff_board()`), tiers
SAFE <20% / MODERATE 20-30% / RISKY ≥30%. Honest ceiling stated in the skill.
Outlier cross-check: when measured bust >> predicted (Soriano 38% vs pred 22%),
the gap is shape/contact (flat-ride sinker) the command model can't see — route
to `/pitcher-sustainability`. NOT integrated into rp3 (standalone decision aid).
