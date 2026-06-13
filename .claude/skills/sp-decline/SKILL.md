---
name: sp-decline
description: SP rest-of-season FP DECLINE-RISK board — flags starting pitchers whose results are propped above their whiff/K stuff LEVEL and are likely to regress DOWN, the "catch a Framber before the crater" lens. Complements Stuff+ (mean) and sp-floor (per-start bust). Triggers: "is X declining", "who on my staff is fading", "decline risk", "catch a Framber early", "which of my SPs will regress", "sell-high SP", "is X's good results sustainable".
---

# sp-decline

You are rendering the **rest-of-season DECLINE-RISK** lens. It answers: *which
SPs are likely to see their FP/start regress DOWN over the rest of the season* —
the early-warning board built to catch a Framber Valdez BEFORE his results fully
crater.

Engine: `python scripts/xfp/sp_decline_model.py`
(`--players "A,B"` for a focus list).

## The validated basis (read this — it's why the skill ignores the obvious signal)

Backtest: `data/research/validation_runs/sp_decline_stuff_decay_2026-06-13.md`
(n=23,598 split-day rows, 37.5% material-decline base rate, player-clustered
GroupKFold, partial-r controlling for the to-date FP base — Rule 9).

**The reliable forward-decline predictor is the CURRENT-SEASON whiff/K LEVEL,
NOT the in-season change/decay.**

- `swstr_z_pop` (SwStr% LEVEL) — partial-r **+0.235** over the to-date FP base
- `k_z_pop` (K% LEVEL) — partial-r **+0.234**, full-model AUC **~0.72**
- `velo_recent` (FB velo LEVEL) — partial-r **+0.16** (light third lens)

**REJECTED as noise — do NOT use** (this is the seductive-but-wrong version):
- Within-season recency **deltas** of whiff/K/velo (L21 − to-date): all
  partial-r < 0.05, ΔAUC ≈ 0. "His swing-and-miss is falling off this month"
  does **not** survive controlling for the base rate.
- Contact-quality / xwOBAcon, archetype, and age signals all **failed** too.
- YoY whiff/velo deltas have only ~39% coverage and `d_k_yoy` even flips sign.

Mechanism: a pitcher whose **results to date outrun his whiff/K stuff** is the
one who regresses. The *level* of stuff is exactly what the to-date FP fails to
encode — so it predicts RoS FP **beyond** what current FP shows.

## The read: the level-vs-FP GAP

For every 2026 SP (≥5 GS), the engine computes percentiles **within the 2026 SP
pool**:

- `stuff_level_pctl` — combined whiff/K level (SwStr% 0.40 + K% 0.40 + velo 0.20,
  velo light per the backtest; velo drops out where missing)
- `curfp_pctl` — current BrownU FP/start percentile
- `decline_gap = curfp_pctl − stuff_level_pctl` — **large positive = FP propped
  above the whiff/K stuff = decline coming.**

**Tiers** (explicit, defensible):

- **DECLINE-RISK** — `stuff_level_pctl ≤ 45` (below-average whiff/K LEVEL — the
  validated primary gate) **AND** `decline_gap ≥ −10` (FP hasn't already fallen
  *below* the level). Sorted by gap so the most-propped ("hasn't fallen yet")
  arms surface at the top.
- **RISING** — `decline_gap ≤ −20` (whiff/K level well ahead of FP =
  sustainable / buy-low-safe).
- **STABLE** — everything else, including strong-stuff arms whose level supports
  their FP (aces never flag).

Why low-LEVEL is the primary gate, not the gap alone: the *level* is the
validated predictor (partial-r 0.235). A 27th-pctl whiff/K arm is a decline
candidate whether his FP has started falling or not — the gap is the *severity*
dial (still-propped = highest risk), not the on/off switch.

## The Framber 2026 canonical case

Framber Valdez 2026: K% **18.6%** / SwStr% **9.1%** → `stuff_level_pctl ≈ 27`
(below-average LEVEL), while his FP percentile (~39) hadn't fully caught down →
`gap ≈ +12`. He flags **DECLINE-RISK**. Aces stay clean: Skenes (lvl 86), Sale
(79), Skubal (88), Crochet (RISING). This is the exact arm the
`/sp-stuff-board` Stuff+ buy-low would have mis-read as a buy (Stuff+ 103) —
the whiff/K *level* says fade. (See CLAUDE.md "Don't do these" #14.)

## What it outputs

`scripts/xfp/sp_decline_model.py` (default, league-wide):
1. **DECLINE-RISK board** — all flagged SPs, gap-sorted, with ownership tags.
2. **YOUR SP STAFF** — your 9 SPs ranked by decline risk, with a **FADE WATCH**
   line naming any of yours in DECLINE-RISK.
3. **FA DECLINE-RISK** — propped FAs to NOT stream (results won't hold).
4. **RISING** — whiff/K level ahead of FP = sustainable / buy-low-safe.

`--players "A,B"` renders just those, gap-sorted.

## How to read it against the other lenses

| lens | question | tool |
|---|---|---|
| MEAN level | who scores most RoS? | `/sp-stuff-board` (Stuff+) |
| per-START floor | who's least likely to crater tonight? | `/sp-floor` |
| RoS DECLINE | whose results will regress DOWN? | **this** |
| MEASURED variance | who HAS been booming/busting? | `/boom-bust-history` |

This **operationalizes the §2 DECLINE CROSS-CHECK** that `/sp-stuff-board` now
requires before headlining a Stuff+ "buy-low" on a veteran: when Stuff+ says buy
but this board says DECLINE-RISK, the whiff/K level wins → headline
**"DECLINING — back-end, defensible drop, not a buy."**

## Guardrails

- **Single-lens risk board.** It does not headline a point projection — the
  number is rh3/rp3/`/sp-stuff-board` projFP. Feed any flagged name into
  `/triangulate` for the full stack before a drop/hold verdict.
- **`marcel_il` gotcha respected.** This reads live FG SwStr%/K% (and rolling
  velo), NOT the suppressed `marcel_il` rp3 per_start — so IL'd / FA-tier arms
  with a Marcel-prior rp3 still get a real whiff/K read here. Rank by this
  board's level, not rp3, for those.
- **Ownership two-pass.** MINE/opp/FA tags come from a LIVE ESPN call using the
  same full-norm → (last, first-initial) match as `/sp-stuff-board` (never
  last-only — the Cam/Cameron + Logan/Gunnar Henderson gotcha). Tags are omitted
  cleanly when ESPN is offline.
- **Direction, not magnitude.** AUC ~0.72 is good for this target but it ranks
  *risk*, it doesn't quantify the FP drop. "How much will X fall" → not this; it
  says X is in the cohort that regresses.
- **Velo is the light lens.** Per the backtest it's weighted 0.20 and drops out
  where the rolling cache has no 2026 velo — whiff/K carry the signal.
