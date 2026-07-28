---
name: hitter-board
description: Unified hitter decision board with `--mode {slate|level|replace}`. `--mode slate` (DEFAULT) = full multi-lens FA-hitter decision board joining all 14 hitter model layers, positional grid, FA highlighted, sustainability+boom-aware synthesis — the old /hitter-slate-grid. `--mode level` = rank hitters by the validated lightly-shrunk season-to-date FP/g LEVEL with the LEVEL-vs-rh3 divergence flags (RIDING-HOT / PEDIGREE / aligned) — the old /level-board. `--mode replace` = ranked FA replacement pool for a named drop target with Δ vs drop, positional-flex match, roster-vs-FA sweep — the old /fa-replacement-pool. Use for "rundown on all FA hitters", "best hitter pickups", "show me the FA hitter board", "use all hitting models", "FA pickup deep scan for hitters", "hitter slate grid", "FA hitter decision board", "compare FA hitters across all lenses", "who has the highest season-to-date level", "rank hitters by their level", "who's producing the most", "level board", "who's riding hot vs their model", "I'm dropping X, who do I pick up?", "find me a replacement for Y", "show all FAs above N FP". Merges /hitter-slate-grid + /level-board + /fa-replacement-pool (2026-07-20).
maturity: unified-hitter-board
---

# hitter-board — unified hitter decision board (`--mode {slate|level|replace}`)

Merges the three overlapping hitter boards into one entry point. All three modes
share the same owner seams — live ESPN roster/FA pulls, `resolve_batter_id`
collision-safe id resolution, `plv_clone.positions` grouping — and all join on
**MLBAM batter_id**, never name (Max Muncy LAD 3B 571970 vs ATH C 691777).

## Pick the mode by the question

| Ask | Mode | Complete recipe lives in | Engine |
|---|---|---|---|
| "rundown on all FA hitters", "best hitter pickups", "use all hitting models", "FA hitter decision board" | **`slate`** | `/hitter-slate-grid` SKILL.md | inline 14-layer join (rh3 + blend + archetype + boom_stack + PL150 + on-demand deep-dive) |
| "who's producing the most", "rank hitters by their level", "riding hot vs the model", "level board" | **`level`** | `/level-board` SKILL.md | `scripts/xfp/run_level_board.py` |
| "I'm dropping X, who do I pick up?", "replacement for Y", "all FAs above N FP", "roster vs FA sweep" | **`replace`** | `/fa-replacement-pool` SKILL.md | inline `league.free_agents(size=2000)` scan + model join + `filter_eligible_fa` |

**Default when unspecified: `slate`** (the full multi-lens decision surface).
Use `level` when the ask is about season-to-date production or the LEVEL-vs-model
gap; use `replace` when a specific drop target (or a whole-roster-vs-FA sweep) is
named.

## Mode summaries

- **`slate`** — every above-threshold FA hitter (plus your roster for the
  drop-target comparison) with baseline xFP + CI, rh3, live_marginal/value_tier,
  Triangulate, Sustainability bucket (BUY-LOW REJECTED caveat, 705defc),
  xwOBA L21d vs 2025, xwOBACON YoY, archetype + T+1 + comps, hitter boom_stack,
  process panel, PL Top 150, lineup/park/splits. Positional grid + the mandatory
  confidence-weighted synthesis block with Tier B hard veto.
- **`level`** — the validated best *simple* forward indicator (shrunk
  season-to-date FP/g, K=20; total FP and recency weighting both validated
  WORSE, 2026-06-26) plus Δ vs rh3: 🔥 RIDING-HOT (regression risk) /
  💎 PEDIGREE (buy-low) / aligned. Display/context only — rh3 stays the headline.
- **`replace`** — drop-target baseline → single `size=2000` FA pull →
  MLBAM-joined model rows → Δ-tiered table + positional-flex annotation +
  mandatory true-FA verification. Also carries the full roster-comparison mode
  (Step 3b) and the IL-stash carve-out.

## Shared preconditions (all modes)

1. **Live roster truth** — `/roster-verify` semantics: MINE/FA tags come from a
   live `get_my_roster_with_injuries()` / `league.teams` call, never session
   memory (Weathers/Rasmussen 2026-05-25).
2. **Id resolution** — every name-keyed lookup goes through
   `plv_clone.utils.name_match.resolve_batter_id(name, team=…, position=…)` with
   the KNOWN_COLLISIONS gate. Never `dict[_norm(name)]`, never last-name
   `contains`.
3. **FA pool** — single `league.free_agents(size=2000)` + manual filter
   (don't-do #6); Connelly-Early availability verification for any
   externally-sourced name (don't-do #7).
4. **Rule 12** — compute and SHOW the full lens stack; headline verdict must be
   stable and lens-order-independent.
5. **Rule 13** — lenses are conviction/context, not additive lift. The headline
   number stays rh3 / baseline xFP in every mode (`level` and the divergence
   flags never re-rank the model).
6. **Drop gates** — no drop/add recommendation without the xwOBA L21d vs 2025 +
   xwOBACON YoY pre-check (don't-do #8) and the drop-target rule (rank your full
   hitter roster by baseline xFP before naming a drop).

## Relationship to the other hitter skills

- **`/xfp-board` is deliberately NOT absorbed** — it is the cross-position
  merged roster+FA board (hitters AND SPs on one scale); folding it here would
  misroute its SP half. Cross-link: use `/xfp-board` when you want your whole
  roster ranked against the FA pool across both position universes.
- **`/hitter-compare` stays standalone** — 2-6 player head-to-head deep dive.
- `/fa-pickup-deep-dive` (single player), `/triangulate` (3-lens card),
  `/breakout-sustainability` and `/slump-or-decline` (single-player form
  deep-dives) remain the focused follow-ons after this board shortlists names.
- `/hitter-form` — the form/sustainability sweep family (roster/fa/league
  scopes + career lens); run it when the question is "is the form real", not
  "who do I add".

**Deprecation note:** `/hitter-slate-grid`, `/level-board`, and
`/fa-replacement-pool` remain as aliases holding the complete recipes; new
invocations should use `/hitter-board --mode {slate|level|replace}`.
