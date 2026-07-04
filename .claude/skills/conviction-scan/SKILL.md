---
name: conviction-scan
description: League-wide model-vs-process divergence board (the buy-low / sell-high conviction surface). For every 2026 player with both a validated model projection and a current rating, compares the percentile of the VALIDATED key pillar (SP STUFF / hitter CONTACT — the only ratings with forward-FP signal, 2026-07-04 study) vs the model percentile (rp3/rh3). PROCESS>MODEL (≥ +25pp) = patience/buy-low watch; MODEL>PROCESS (≤ −25pp) = distrust/sell-high watch. Tagged MINE / FA / opponent (trade targets). Use when the user asks "who should I buy low on", "sell-high candidates", "where do the model and the stuff disagree", "conviction scan", or "trade bait". Rule 13 — divergence never moves rh3/rp3; it routes to /triangulate. Engine scripts/xfp/run_conviction_scan.py.
---

# conviction-scan

The divergence board: where the validated **process rating** and the validated
**model** disagree, sorted by gap. Agreement = conviction; disagreement = the
insight (lens-merge protocol).

```bash
python scripts/xfp/run_conviction_scan.py               # both roles, MINE+FA+opp
python scripts/xfp/run_conviction_scan.py --role sp --top 12
```

## Reading it
- **PROCESS>MODEL** (rating pct ≥ model pct + 25pp): the underlying skill is
  ahead of results. SP flavor mirrors the validated Stuff+ buy-low family —
  but apply the **mandatory veteran decline cross-check** (CLAUDE.md #14)
  before headlining any BUY. Hitter flavor is **CONTEXT-ONLY** (hitter buy-low
  REJECTED as additive, −0.069 FP/PA).
- **MODEL>PROCESS**: production the process doesn't support — sell-high /
  distrust watch. Canonical 2026-07-04 first run: **Fried −40pp, Freddy −25pp**
  (independently matching the forced-drop cut order), Framber −29pp (the
  known STUFF-DECLINE), Kirby −46pp.
- marcel-suppressed rp3 rows are excluded (a prior isn't a model read).
- Excludes nothing by ownership: **opponent rows are trade-target surface**.

## Rules
1. **Rule 13** — never re-rank on divergence; headline stays rp3/rh3.
2. Route every actionable row through `/triangulate` (full stack) first.
3. Cross-reference `/rating-arc` for direction: PROCESS>MODEL **plus** a
   rising arc is the strongest patience case; MODEL>PROCESS plus a falling
   arc is the strongest sell case.

## Owners consumed
`{sp,hitter}_ratings_master.csv` (pillars) · `xfp_rp3/rh3` (model + marcel
tags) · `get_all_teams` (ownership). Arc companion: `lib/rating_arc.py`.
