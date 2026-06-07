---
name: sp-floor
description: SP FLOOR / bust-risk board — ranks starting pitchers by their probability of a dud start (<5 FP), the "avoid bad days" lens that complements Stuff+ (mean) and boom-bust-history (measured variance). Use for bench-against-the-10-start-cap decisions — which start is most likely to crater. Triggers: "which SP do I bench", "bust risk", "floor on my SPs", "who's most likely to blow up", "safest start this week", "avoid bad days".
---

# sp-floor

You are rendering the **floor / bust-risk** lens. Stuff+ predicts a pitcher's
*mean* FP/start; this predicts his *downside* — P(this start busts, <5 FP).

Engine: `python scripts/xfp/sp_floor_model.py` (validation + `--staff` board).

## Why this exists (and its honest ceiling)

We proved Stuff+ shifts the mean but **not the variance** (std flat ~8.9 across
all Stuff+ tiers). So "avoid bad days" is a *separate* problem from "win the
season," and needs its own model. Built + validated 2026-06-06
(`data/research/validation_runs/sp_floor_model_2026-06-06.md`):

- **Per-start bust is mostly irreducible noise.** TEST AUC = 0.601 (2018-22 train
  → 2023-25 test, n=24k starts). It CANNOT predict which single start blows up.
- **But it ranks risk and is well-calibrated.** Riskiest quintile busts **38%**
  vs safest **18% (2.1× separation)**; predicted ≈ actual at every quintile.
- **Drivers (what makes a bust-prone arm):** `prior_k_pct` dominates (strikeouts
  are the floor — they end innings without balls in play to snowball), opponent
  offense (`lineup_xfp`) second, BB% minor. Validated season-level too: K% −6.3 pp
  bust/SD, BB% +2.5, barrel% +1.5; **GB% and raw Stuff+ barely matter once K% is
  in.** The floor is **K−BB%**, not stuff.
- **Command-only ≈ full model** (AUC 0.595 vs 0.603), so the staff board needs no
  live matchup data; opponent shifts a given start ~±5 pp.

**Use it as a bench-priority TILT, never a game predictor.** It tells you which
starts to sit *over the cap on average*, not which one will implode tonight.

## What it outputs

`--staff` board: each rostered SP with K% / BB% / **bust_prob** / tier:
- **SAFE** (<20%) — highest floor, never the bench candidate
- **MODERATE** (20-30%)
- **RISKY** (≥30%) — bench-first when you're over the 10-start cap

## How to read it against the other lenses

| lens | question | tool |
|---|---|---|
| MEAN | who scores most RoS? | `/sp-stuff-board` (Stuff+) |
| FLOOR | who's least likely to crater? | **this** |
| MEASURED variance | who HAS been booming/busting? | `/boom-bust-history` |

Decision pattern: when over the cap, **bench the RISKY-tier arm against a strong
offense**, not the high-mean/high-Stuff+ arm. The canonical case: Stuff+ flags
Messick as a sell-high (low stuff), but his elite K−BB% makes him a high-floor
MODERATE — don't bench him to avoid bad days. Bench Valdez (RISKY, K 18.6%).

## Guardrails

- **Honest about precision.** AUC 0.60 — relative ranking only. If asked "will X
  bust tonight," the answer is "can't say; here's his risk tier vs the staff."
- **Cross-check the outliers.** When measured bust (from `/boom-bust-history`)
  >> predicted bust, the gap is shape/contact the command model can't see (e.g.,
  Soriano: predicted 22%, measured 38% — flat-ride sinker). Run
  `/pitcher-sustainability` on those.
- **Single-axis.** Doesn't see role, injury, or the 10-start cap math — feed it
  into `/sp-week-plan` for the actual bench decision.
