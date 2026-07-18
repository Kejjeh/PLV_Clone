---
name: second-half-splits
description: Career pre/post All-Star splits in BrownU FP terms for the full roster + named FAs, grouped by position with role-truth bucketing. Use when the user asks "who performs better in second halves", "2H splits", "post-All-Star history", or is weighing a hold-vs-drop on first-half form (the Peralta-vs-Soriano 2026-07-18 canonical). Rule 13 — a career-tendency lens, never a projection mover.
---

# second-half-splits

## What this is

For every player on the roster (plus `--extra` FA names), pulls CAREER
pre-ASG vs post-ASG splits (MLB Stats API `careerStatSplits`, sitCodes
`preas`/`posas` — one call per half, accent-tolerant `people/search` id
resolution) and expresses both halves in BrownU FP per unit:
hitters FP/g, SP FP/start, RP FP/app. Renders position-grouped tables
(C / CI / MI / OF-DH, then SPs, then RPs) sorted by Δ(2H−1H).

## Run

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_second_half_splits.py \
  --extra "Jake Bennett,Curtis Mead"          # roster + extras
# or --names "A,B" --no-roster for an arbitrary list
```

Output table + `data/outputs/second_half_splits.csv`.

## Reading rules (learned 2026-07-18)

1. **Role truth first (gotcha #8).** Pitchers are bucketed by
   `detect_pitcher_role()` — eligible_slots + gamesStarted — NEVER the ESPN
   `.position` tag. Canonical: Detmers (ESPN "RP", true SP).
2. **Role-converts poison FP/unit.** A recent RP→SP convert (Jax, Seymour)
   carries relief-era FP (incl. SV/HLD) divided by a tiny career GS count →
   absurd FP/start. For converts read ERA / K-BB% columns, not FP/unit.
3. **Report n alongside Δ.** A 2H column built on <20 games/starts is an
   anecdote, not a tendency (Bennett 2H n=1).
4. **Rule 13.** Δ(2H−1H) is context/conviction — it breaks ties on a
   hold-vs-drop (Peralta +1.27 kept over Soriano's chronic walks); it never
   moves rh3/rp3/rprs2 and never overrides current-season role/health.
5. Canonical findings 2026-07-18: Peralta 2H ERA 3.45 / K% rises; Greene
   +3.10 FP/start; Bichette +0.63, Harris +0.80 FP/g; Elly −0.93 FP/g
   (career 2H fade — watch, don't panic-sell).
