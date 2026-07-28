---
name: level-board
description: ALIAS → /hitter-board --mode level. Recipe lives below; routing/triggers live on the canonical.
---

> **⚠ MERGED (2026-07-20) → `/hitter-board --mode level`.** This SKILL holds the
> complete level-board recipe and stays live as the delegate; new invocations
> should prefer `/hitter-board --mode level` (routing + trigger phrases live on
> the canonical).

# level-board — season-to-date hitter LEVEL board

## What this is

A ranking of hitters by their **season-to-date production LEVEL**, which is the
single best *simple* predictor of forward fantasy FP — validated on our own data,
not assumed. The board's real value is the **LEVEL-vs-rh3 divergence**: where a
hitter's in-season production sits above or below the career-anchored model.

Engine: [scripts/xfp/run_level_board.py](../../scripts/xfp/run_level_board.py).

## Why this metric (validated 2026-06-26 — don't re-derive)

Two leakage-safe, player-cluster-bootstrap studies on the 2026 panel
(`data/research/validation_runs/window_predictive_validity_2026-06-26.md`):

1. **Window study.** Of trailing windows (L7/L14/L21/L30/season), the **full
   season-to-date level is the best forward predictor** of next-14d FP/g (r ~0.33);
   shorter windows predict worse and add **no incremental signal beyond the running
   level** (no momentum term — Rule 13). Bat speed is the only *process* metric that
   adds beyond the level (that's `/trending`'s job, not this board's).
2. **Level-formula bake-off.** Head-to-head on forward FP:
   - Ranking by **TOTAL FP is the worst** (−0.041 vs the rate) — it rewards playing
     time + early overproduction (the TJ Rumfield trap: #1 by total, rh3 #82).
   - **Recency-weighting (EWMA / L30-blend) is WORSE** than the flat season mean.
   - The **only** weighting that helps is a **light shrink toward the league game-mean**
     (~1.80 FP/g), +0.006 r — and only for thin samples. That is exactly what rh3
     already encodes.

So the board ranks by **Level FP/g = (n·raw_pg + K·POP)/(n + K)**, K=20, POP = league
game-mean — a lightly-shrunk season-to-date *rate* (NOT total, NOT recency-weighted).

## The divergence flag (the actionable output)

`Δ = Level − rh3_per_game` (both are fp/game). rh3 is the career-anchored model.

| Flag | Condition | Read |
|---|---|---|
| 🔥 **RIDING-HOT** | Δ ≥ +0.40 | In-season production sits above the model's forward rate → **regression risk**. The FA pool is full of these (a hot bat the model doesn't believe). |
| 💎 **PEDIGREE** | Δ ≤ −0.40 | Career model sees MORE than the current line → **buy-low / bounce** candidate. |
| · **aligned** | \|Δ\| < 0.40 | Level and model agree → the **steadiest** reads (canonical: Luis García Jr. Δ+0.19 — a real, model-backed everyday bat). |

**This does NOT introduce a competing projection.** rh3 remains the headline forward
number (CLAUDE.md Rule 13). The board foregrounds the validated level and its gap to
the model so you can tell a *real* high level (aligned) from a *hot* one (RIDING-HOT).

## How to run

```bash
python scripts/xfp/run_level_board.py                 # my roster + top-25 FA by Level
python scripts/xfp/run_level_board.py --fa-top 40     # deeper FA board
python scripts/xfp/run_level_board.py --names "Luis Garcia Jr., Michael Busch"
```

- Tags MINE (live `get_my_roster`) vs FA (`get_free_agents` size=2000). Hitters only.
- Name resolution: `resolve_batter_id` (collision-safe) with an rh3 disambiguated
  name→mlbam fallback (catches the **Luis García Jr.** case `resolve_batter_id`
  refuses without a clean team key). All joins by MLBAM.
- `MIN_GAMES = 15` floor so the level is a real sample.

## Reading it

- **Sort is Level FP/g** — the validated best simple forward indicator.
- A **high Level + aligned** = the safest add (real production the model backs).
- A **high Level + 🔥RIDING-HOT** = fool's gold risk — the model is projecting
  regression; cross-check why (small sample? early-season cluster? unsustainable
  K/BB?). Hand to `/breakout-sustainability` or `/slump-or-decline` if it matters.
- A **💎PEDIGREE** with a depressed line is a buy-low — hand to `/slump-or-decline`.

## When to use a different skill

- **Forward projection / ranking by the model:** `/xfp-board` or `/triangulate`
  (rh3 IS the validated weighted level — this board is the *raw in-season* level and
  the gap to it, a transparency/divergence tool, not a replacement ranker).
- **Is a hot level real (process)?** `/breakout-sustainability` (skill change) or
  `/trending` (bat speed — the one early signal that adds beyond the level).
- **Is a low level a slump or decline?** `/slump-or-decline`.

## Hard rules

1. **Display/context ONLY** — never moves rh3/baseline xFP (Rule 13). Headline stays the model.
2. **Rank by the RATE, never the total** — total FP rewards playing time (validated worst).
3. **No recency weighting** — validated worse than the flat mean; recency is already in the level.
4. **All joins by MLBAM** via `resolve_batter_id` + rh3 fallback — never name-only.
5. **Roster truth is live** — MINE/FA from a live ESPN call, never session memory.
