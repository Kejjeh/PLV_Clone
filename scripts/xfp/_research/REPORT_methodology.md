# Methodology tests report

Date: 2026-05-28. Scope: empirical evaluation of 5 candidate methodology upgrades vs the current linear sub-domain-rating model. Pure research — no production scripts changed.

**Holdout convention**: year-based holdouts on FULL-tier players.
- Tests D, E, G(current+T+1), H: train years ≤ 2023, test year = 2024 (T+1 → 2025).
- Test F: train ≤ 2022, test = 2023 (so T+1/T+2/T+3 all observable).

**Baselines reproduced on this holdout split**:

| Set | Current-year R² | T+1 R² |
|---|---|---|
| Hitters (12 subs + age) | 0.84-0.89 | **0.285** |
| SPs (6 subs + velo + age) | n/a | **0.358** |

## Test D — XGBoost T+1

| Group | n train / test | Linear R² | XGBoost R² | ΔR² |
|---|---|---|---|---|
| Hitters | 1,915 / 284 | 0.285 | 0.264 | **−0.021** |
| SPs | 660 / 92 | 0.358 | 0.338 | **−0.020** |

XGBoost config: 500 trees, lr=0.03, max_depth=4, subsample=0.8, early stopping on 15% internal val split.

**XGBoost top features (gain importance):**
- Hitters: RAW_POWER, K_AVOIDANCE, O_CONTACT, age, DAMAGE_PROD
- SPs: SWING_MISS, age, WALK_AVOID, DAMAGE_SUPP

Same as the linear top coefficients — XGBoost doesn't find a non-linearity worth the variance hit.

**Verdict: DO NOT SHIP.** Spec required ΔR² > +0.04; got −0.02 both sets. Linear on already-normalized 20-80 ratings is near-optimal for available signal; tree boosting adds noise.

## Test E — Interaction terms

OLS p-values via numpy (X'X)⁻¹ for SE → t-distribution.
Ship rule: p < 0.05 AND test-set ΔR² > +0.005.

### Hitters

| Interaction | Train p | β (train) | Test ΔR² | Survives? |
|---|---|---|---|---|
| DAMAGE_PROD × Z_CONTACT | 0.0001 | +1.08e-4 | **−0.019** | No (overfit) |
| K_AVOIDANCE × CONTACT_QUALITY | 0.005 | +7.96e-5 | **−0.005** | No |
| RAW_POWER × PATIENCE | 0.494 | +1.98e-5 | +0.002 | No (insignificant) |
| DAMAGE_PROD × age | 0.976 | −2.27e-6 | −0.000 | No |

Z_CONTACT × DAMAGE_PROD highly significant in-sample (p=0.0001) but **fails to generalize** — classic overfit.

### SPs

| Interaction | Train p | β | Test ΔR² | Survives? |
|---|---|---|---|---|
| **SWING_MISS × WALK_AVOID** | **0.018** | +0.00289 | **+0.0103** | **Yes** |
| SWING_MISS × age | 0.018 | +0.00743 | −0.012 | No |

**Verdict: SHIP only SWING_MISS × WALK_AVOID for SPs** (T+1 R² 0.358 → 0.368, ~+1pp). The "elite stuff with control" interaction is real and generalizes. Recommend running `/validate-feature` with full Rule 9 baseline before promoting.

## Test F — T+2 / T+3 horizons

Train ≤ 2022, test = 2023. Features standardized within train.

### Hitters

| Horizon | n train / test | R² | MAE | Top-3 by |β| |
|---|---|---|---|---|
| T+1 | 1,630 / 285 | **0.255** | 0.0934 | RAW_POWER (+0.064), K_AVOIDANCE (+0.048), O_CONTACT (+0.030) |
| T+2 | 1,137 / 241 | **0.146** | 0.0986 | K_AVOIDANCE (+0.054), RAW_POWER (+0.046), age (−0.027) |
| T+3 | 748 / 156 | **−0.477** | 0.1336 | RAW_POWER (+0.059), K_AVOIDANCE (+0.042), age (−0.028) |

**T+3 hitter R² is negative — model predicts worse than mean.** Three years out, attrition (injury, role change, demotion) dominates skill.

### SPs

| Horizon | n train / test | R² | MAE | Top features |
|---|---|---|---|---|
| T+1 | 573 / 87 | **0.224** | 2.21 | SWING_MISS (+1.83), DAMAGE_SUPP (+0.40), WALK_AVOID (+0.33) |
| T+2 | 352 / 69 | **0.268** | 2.06 | SWING_MISS (+1.95), age (−0.44), WALK_AVOID (+0.28) |
| T+3 | 206 / 37 | **0.036** | 3.31 | SWING_MISS (+1.78), age (−0.56), CALLED_STRIKE (−0.40) |

SP T+2 slightly more predictable than T+1 on this split (small-n noise). SWING_MISS stays dominant. **Age coefficient grows in magnitude with horizon** (T+1 −0.24 → T+2 −0.44 → T+3 −0.56) — confirms age-dominates-long-horizon hypothesis.

**Verdict**: Don't ship T+3 for either set. Publish SP T+2 as supplemental for keeper/dynasty contexts.

## Test G — Park-factor adjustment

`r_HRrate_parkadj = within-year(20-80) of (hr_per_pa / pf_HR)`. Park data covers 2018+.

| Target | Raw R² | Park-adj R² | ΔR² |
|---|---|---|---|
| Current-year FP | 0.891 | 0.880 | **−0.011** |
| T+1 FP | 0.305 | 0.313 | **+0.009** |
| T+1 (movers only, n=54) | 0.173 | 0.185 | **+0.012** |

**Rockies spot-check** (largest raw → parkadj drops):

| Player | Year | pf_HR | Raw | Parkadj | Δ |
|---|---|---|---|---|---|
| C.J. Cron | 2022 | 1.42 | 62 | 53.5 | −8.5 |
| Nolan Arenado | 2019 | 1.28 | 65 | 57.0 | −8.0 |
| Charlie Blackmon | 2019 | 1.28 | 59 | 52.7 | −6.3 |
| Trevor Story | 2019 | 1.28 | 60 | 54.0 | −6.0 |

**Verdict**: Marginal. T+1 +0.009 (movers +0.012) — both below +0.02 ship threshold but in right direction with correct physical interpretation. Current-year drops because raw HR rate has real park-driven points the in-sample model exploits.

Recommend: **don't ship as a model change**, but **display `r_HRrate_parkadj` as a flag column** alongside `r_HRrate` to surface park-inflated ratings.

## Test H — Bayesian shrinkage for PARTIAL tier

PARTIAL rows shrunk toward 50 (prior_var=100, sample_var = prior_var / (pa/250)).

| Target | Raw PARTIAL R² | Shrunk PARTIAL R² | ΔR² | FULL-only ref R² |
|---|---|---|---|---|
| Current-year FP | 0.738 | 0.363 | **−0.376** | 0.853 |
| T+1 FP | 0.239 | 0.200 | **−0.039** | 0.285 |

**Shrinkage strongly hurts**, especially current-year (n_test=130 CY, 78 T+1).

**Interpretation**: PARTIAL sub-domain ratings produced by the pipeline are already conservative — within-year ranking of a 100-249 PA sample naturally regresses extremes because they don't accumulate enough to land at the tails. Stacking another shrinkage on top is double-counting.

**Verdict: DO NOT SHIP.**

## Overall recommendation — methodology

| Test | Ship? | ΔR² T+1 |
|---|---|---|
| D (XGBoost) | **No** | −0.021 hitters / −0.020 SPs |
| E (Interactions) | **Partial — SWING_MISS×WALK_AVOID only** | +0.010 SPs |
| F (T+2/T+3) | **No (T+3 hitter R²<0); publish SP T+2 supplemental** | — |
| G (Park factors) | **No model change; display r_HRrate_parkadj flag** | +0.009 |
| H (Shrinkage) | **No (significantly hurts)** | −0.039 PARTIAL |

**Top finding**: The current linear sub-domain rating model is **closer to optimal than expected**. Signal in the 20-80 sub-domain ratings is mostly **linear and additive** — non-linear methods and explicit shrinkage offer no consistent improvement.

**Single shippable item** (with `/validate-feature` confirmation): add `SWING_MISS × WALK_AVOID` interaction to SP T+1 model. Predicted lift ≈ +0.01 R². Run `/validate-feature` with full Rule 9 baseline before promoting.

**Non-model deliverables to consider**:
- Expose `r_HRrate_parkadj` next to `r_HRrate` in dashboards and FA deep-dives
- Treat T+1 as the only reliable hitter horizon; SP T+2 publishable for dynasty/keeper contexts
