---
title: Lens value-add — does synthesis beat base rank?
date: 2026-06-11
author: validation (extends drop_one_lens_ablation + confidence_label_calibration 2026-06-06)
panel: shrinkage_{h,sp}_snap_2026-06-06.parquet (1498 H / 550 SP, leakage-safe as-of)
base_model: pred_k150 (talent-shrunk fwd projection = rh3/rp3 analog; Rule-9 full, not stripped)
cv: player-clustered GroupKFold (k=5); cluster bootstrap B=1000 on the delta
status: research — NOT committed, NOT promoted
---

# Lens value-add: does the multi-lens synthesis earn its complexity?

**Question.** On a leakage-safe as-of panel, does adding the lens layer (boom-bust, sustainability, prior-year, xwOBA-L21, xwOBACON-YoY, archetype-age) to the BASE production projection improve out-of-sample forecasts of realized forward FP/g — measured as OOS ΔR² and Δ rank-correlation — or is it noise?

**What's new vs the 2026-06-06 work.** The earlier `drop_one_lens_ablation` used a *random* 50/50 split on a panel with ~8 snapshots per player, which leaks the same player into train+test, and measured in-sample-ish MAE within an all-lens ensemble. Here the base is the FULL shrinkage projection used directly, folds are **clustered by player (GroupKFold)**, the headline is **OOS incremental R²/Spearman of base vs base+synthesis**, and the bootstrap resamples *players* not rows.

**Leakage notes.** (1) `pred_*` are built only from data ≤ as_of and `target` is strictly forward, so the panel itself is leakage-safe. (2) Lens votes are PROXIES synthesized from the same as_of fields — they are not the live triangulate cards, so this bounds the *information content* of the underlying signals, not the exact UI. (3) L1/L8 rank-decile proxies are EXCLUDED from the synthesis layer because they duplicate the base; including them would fake a lift. (4) SP cells are small (89 players); read SP results as directional.

## Headline verdict

**Does the synthesis beat the base model rank at point-forecasting forward FP? Mostly NO — once leakage is removed, the lens layer adds ~0 to OOS R².**

| | ΔR² (all 6, optimistic) | ΔR² (CLEAN, honest) | significant? |
|---|---|---|---|
| Hitters | +0.0330 (CI [+0.0068, +0.0588]) | **+0.0055** (CI [-0.0112, +0.0180]) | no |
| SPs | +0.0239 (CI [-0.0394, +0.0745]) | **-0.0137** (CI [-0.0687, +0.0216]) | no (negative) |

- The headline +0.033 ΔR² for hitters in the 'all-6' row is **almost entirely a leakage artifact**: lens L7 ('top50 tier') is built from full-season FP rank, which peeks at the forward window. Drop it and the genuine Tier-B/C lenses (boom-bust, sustainability, xwOBA-L21, xwOBACON-YoY) add **+0.0055 R² for hitters (n.s., CI spans 0)** and **−0.014 R² for SPs (they make it WORSE)**.
- **BUT the confidence/agreement DIRECTION still sorts outcomes.** Even on the clean 5-lens stack, hitter signed-Δ rises monotonically LOW +0.15 → MED +0.30 → HIGH +0.47 FP/g, and per-agreement-count climbs cleanly 0→4. So the lens layer's value is as a **directional confidence/conviction sorter**, not as an additive point-forecast term. This refines the 2026-06-06 'FAIL' verdict: the labels ARE ordered; what they're NOT is a free R² boost on top of rank.
- **Lenses that earn their slot (clean, OOS marginal):** L4 prior-year and L3 sustainability for hitters are weakly positive; **L5 xwOBA-L21 actively HURTS hitters** (drop_ΔR² −0.0028) and **boom-bust L2 + sustainability L3 actively HURT SPs**. No Tier-B lens is a clear additive winner for either group.
- **Complexity justified?** As a *ranker add-on*: barely — keep the base model as the headline, exactly as CLAUDE.md already mandates. As a *conviction/confidence display*: yes, the agreement count is a real, monotone outcome sorter. Recommend: stop treating any single Tier-B lens as additive lift (consistent with the existing BUY-LOW-rejected and xwOBA-L21 caveats), and keep the merge protocol's role as conflict-surfacing + conviction, not point-estimate blending.


## HITTERS (n=1498 snaps, 189 players)

### Core: base-only vs base+synthesis (OOS, player-clustered)

| variant | R² base | R² +synth | ΔR² | ΔR² boot 95% CI | p(ΔR²≤0) | Spear base | Spear +synth | ΔSpear | ΔSpear 95% CI | p(Δ≤0) |
|---|---|---|---|---|---|---|---|---|---|---|
| primary (k150, all 6 lenses) | 0.1715 | 0.2045 | +0.0330 | [+0.0068, +0.0588] | 0.006 | 0.3839 | 0.4162 | +0.0323 | [-0.0007, +0.0603] | 0.026 |
| **clean (k150, drop leaky L7)** | 0.1715 | 0.1769 | +0.0055 | [-0.0112, +0.0180] | 0.362 | 0.3839 | 0.3932 | +0.0092 | [-0.0166, +0.0269] | 0.379 |
| robustness (k40 base, all 6) | 0.1854 | 0.2096 | +0.0242 | [+0.0003, +0.0444] | 0.025 | 0.4002 | 0.4206 | +0.0204 | [-0.0071, +0.0435] | 0.089 |

> **L7 leakage flag.** The snapshot `tier` (top50/other) is assigned by full-season FP rank, which peeks at the forward window; it correlates ~0.31 with the target on its own. So the 'all 6 lenses' row is OPTIMISTIC — the **clean** row (L7 dropped) is the honest, leakage-safe estimate of what the genuine lens signals add.

### Per-lens marginal value (OOS ΔR² over the primary base)

`add_ΔR²` = base→base+lens (value the lens adds alone). `drop_ΔR²` = full→full−lens (marginal within the stack; >0 useful, ≤0 redundant/noise).

| Lens | Signal | add ΔR² | drop ΔR² | read |
|---|---|---|---|---|
| L7 | archetype age tier top50 (Tier D) | +0.0380 | +0.0282 | earns slot |
| L4 | prior-year baseline (Tier A/D) | +0.0131 | +0.0021 | earns slot |
| L3 | sustainability -(L21-L42) (Tier B) | +0.0104 | +0.0008 | earns slot |
| L6 | xwOBACON YoY prior-prior2 (Tier B) | +0.0074 | -0.0007 | redundant/noise |
| L2 | boom-bust L21 (Tier C) | +0.0134 | -0.0008 | redundant/noise |
| L5 | xwOBA-L21 vs prior gap (Tier B) | +0.0153 | -0.0028 | ACTIVELY HURTS |

Base R² (k150) = 0.1590; Full (base+6 lenses) R² = 0.2045; full stack ΔR² = +0.0455.

### Confidence-label calibration (refresh)

Label = agreement count among the synthesis lenses pointing the net direction. signed_delta = net_dir × (target − cohort-median): a correct FADE on a poor performer scores positive, so this measures whether the verdict's *direction* sorts realized outcomes.

**All 6 lenses (incl. leaky L7)** (HIGH ≥5/6, MED 3-4, LOW 1-2, NULL 0):

| label | n | signed Δ FP/g | 95% CI | raw target |
|---|---|---|---|---|
| HIGH | 33 | +0.4047 | [+0.1581, +0.6493] | 2.832 |
| MED | 690 | +0.3056 | [+0.2448, +0.3687] | 2.281 |
| LOW | 426 | +0.1048 | [+0.0289, +0.1839] | 2.092 |
| NULL | 349 | +0.0000 | [+0.0000, +0.0000] | 2.064 |

Monotone HIGH≥MED≥LOW≥NULL? **YES**. HIGH vs MED 95% CI: **OVERLAP**.

Per-agreement-count (n≥15):

| agree | n | signed Δ | 95% CI | raw target |
|---|---|---|---|---|
| 0 | 349 | +0.0000 | [+0.0000, +0.0000] | 2.064 |
| 1 | 59 | -0.0146 | [-0.2401, +0.2282] | 2.034 |
| 2 | 367 | +0.1240 | [+0.0468, +0.2033] | 2.101 |
| 3 | 522 | +0.2118 | [+0.1429, +0.2802] | 2.208 |
| 4 | 168 | +0.5973 | [+0.4721, +0.7265] | 2.505 |
| 5 | 29 | +0.4387 | [+0.1873, +0.6743] | 2.844 |

**CLEAN — 5 lenses (L7 dropped)** (HIGH ≥4/5, MED 3-3, LOW 1-2, NULL 0):

| label | n | signed Δ FP/g | 95% CI | raw target |
|---|---|---|---|---|
| HIGH | 131 | +0.4697 | [+0.3372, +0.6074] | 2.156 |
| MED | 504 | +0.2996 | [+0.2298, +0.3719] | 2.270 |
| LOW | 513 | +0.1466 | [+0.0741, +0.2176] | 2.194 |
| NULL | 350 | +0.0000 | [+0.0000, +0.0000] | 2.077 |

Monotone HIGH≥MED≥LOW≥NULL? **YES**. HIGH vs MED 95% CI: **OVERLAP**.

Per-agreement-count (n≥15):

| agree | n | signed Δ | 95% CI | raw target |
|---|---|---|---|---|
| 0 | 350 | +0.0000 | [+0.0000, +0.0000] | 2.077 |
| 1 | 74 | +0.0448 | [-0.1577, +0.2542] | 2.114 |
| 2 | 439 | +0.1637 | [+0.0888, +0.2401] | 2.207 |
| 3 | 504 | +0.2996 | [+0.2289, +0.3683] | 2.270 |
| 4 | 121 | +0.4956 | [+0.3484, +0.6422] | 2.148 |


## STARTING PITCHERS (n=550 snaps, 89 players)

### Core: base-only vs base+synthesis (OOS, player-clustered)

| variant | R² base | R² +synth | ΔR² | ΔR² boot 95% CI | p(ΔR²≤0) | Spear base | Spear +synth | ΔSpear | ΔSpear 95% CI | p(Δ≤0) |
|---|---|---|---|---|---|---|---|---|---|---|
| primary (k150, all 6 lenses) | 0.0298 | 0.0536 | +0.0239 | [-0.0394, +0.0745] | 0.289 | 0.2092 | 0.2653 | +0.0561 | [-0.0416, +0.1781] | 0.154 |
| **clean (k150, drop leaky L7)** | 0.0298 | 0.0161 | -0.0137 | [-0.0687, +0.0216] | 0.838 | 0.2092 | 0.1745 | -0.0347 | [-0.1231, +0.0838] | 0.744 |
| robustness (k40 base, all 6) | 0.0324 | 0.0538 | +0.0214 | [-0.0450, +0.0687] | 0.311 | 0.2223 | 0.2653 | +0.0430 | [-0.0611, +0.1596] | 0.191 |

> **L7 leakage flag.** The snapshot `tier` (top50/other) is assigned by full-season FP rank, which peeks at the forward window; it correlates ~0.24 with the target on its own. So the 'all 6 lenses' row is OPTIMISTIC — the **clean** row (L7 dropped) is the honest, leakage-safe estimate of what the genuine lens signals add.

### Per-lens marginal value (OOS ΔR² over the primary base)

`add_ΔR²` = base→base+lens (value the lens adds alone). `drop_ΔR²` = full→full−lens (marginal within the stack; >0 useful, ≤0 redundant/noise).

| Lens | Signal | add ΔR² | drop ΔR² | read |
|---|---|---|---|---|
| L7 | archetype age tier top50 (Tier D) | +0.0011 | +0.0283 | earns slot |
| L5 | xwOBA-L21 vs prior gap (Tier B) | +0.0132 | +0.0112 | earns slot |
| L4 | prior-year baseline (Tier A/D) | +0.0036 | -0.0087 | ACTIVELY HURTS |
| L6 | xwOBACON YoY prior-prior2 (Tier B) | +0.0026 | -0.0116 | ACTIVELY HURTS |
| L3 | sustainability -(L21-L42) (Tier B) | +0.0007 | -0.0154 | ACTIVELY HURTS |
| L2 | boom-bust L21 (Tier C) | -0.0050 | -0.0251 | ACTIVELY HURTS |

Base R² (k150) = 0.0313; Full (base+6 lenses) R² = 0.0536; full stack ΔR² = +0.0224.

### Confidence-label calibration (refresh)

Label = agreement count among the synthesis lenses pointing the net direction. signed_delta = net_dir × (target − cohort-median): a correct FADE on a poor performer scores positive, so this measures whether the verdict's *direction* sorts realized outcomes.

**All 6 lenses (incl. leaky L7)** (HIGH ≥5/6, MED 3-4, LOW 1-2, NULL 0):

| label | n | signed Δ FP/g | 95% CI | raw target |
|---|---|---|---|---|
| HIGH | 22 | +2.3625 | [+0.7015, +4.0384] | 16.437 |
| MED | 264 | +0.4439 | [-0.1286, +0.9771] | 13.695 |
| LOW | 143 | -0.5731 | [-1.3343, +0.1345] | 12.669 |
| NULL | 121 | +0.0000 | [+0.0000, +0.0000] | 12.316 |

Monotone HIGH≥MED≥LOW≥NULL? **NO**. HIGH vs MED 95% CI: **OVERLAP**.

Per-agreement-count (n≥15):

| agree | n | signed Δ | 95% CI | raw target |
|---|---|---|---|---|
| 0 | 121 | +0.0000 | [+0.0000, +0.0000] | 12.316 |
| 2 | 131 | -0.5884 | [-1.3485, +0.1225] | 12.709 |
| 3 | 192 | +0.4988 | [-0.1983, +1.1578] | 13.427 |
| 4 | 72 | +0.2975 | [-0.6323, +1.2300] | 14.411 |
| 5 | 19 | +1.4882 | [-0.0813, +3.1095] | 15.473 |

**CLEAN — 5 lenses (L7 dropped)** (HIGH ≥4/5, MED 3-3, LOW 1-2, NULL 0):

| label | n | signed Δ FP/g | 95% CI | raw target |
|---|---|---|---|---|
| HIGH | 51 | +1.0215 | [-0.2704, +2.2578] | 14.621 |
| MED | 157 | +1.1087 | [+0.4874, +1.7040] | 13.326 |
| LOW | 196 | +0.3361 | [-0.2611, +0.9522] | 13.405 |
| NULL | 146 | +0.0000 | [+0.0000, +0.0000] | 12.423 |

Monotone HIGH≥MED≥LOW≥NULL? **NO**. HIGH vs MED 95% CI: **OVERLAP**.

Per-agreement-count (n≥15):

| agree | n | signed Δ | 95% CI | raw target |
|---|---|---|---|---|
| 0 | 146 | +0.0000 | [+0.0000, +0.0000] | 12.423 |
| 1 | 36 | -0.0978 | [-1.9895, +1.5343] | 12.099 |
| 2 | 160 | +0.4338 | [-0.2010, +1.0884] | 13.698 |
| 3 | 157 | +1.1087 | [+0.5178, +1.7088] | 13.326 |
| 4 | 45 | +0.6742 | [-0.6217, +1.9725] | 14.427 |

