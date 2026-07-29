---
name: hitter-board
description: Unified hitter decision board with `--mode {slate|level|replace|pl}`. `--mode slate` (DEFAULT) = full multi-lens FA-hitter decision board joining all 14 hitter model layers, positional grid, FA highlighted, sustainability+boom-aware synthesis — the old /hitter-slate-grid. `--mode level` = rank hitters by the validated lightly-shrunk season-to-date FP/g LEVEL with the LEVEL-vs-rh3 divergence flags (RIDING-HOT / PEDIGREE / aligned) — the old /level-board. `--mode replace` = ranked FA replacement pool for a named drop target with Δ vs drop, positional-flex match, roster-vs-FA sweep — the old /fa-replacement-pool. `--mode pl` = the PL-SPINED board: one row per Pitcher-List Top-150 hitter that is MINE or FA, sorted by PL rank with ▲▼ movement vs the prior edition, plus rh3/verdict/baseline, L7/L21/season FP/g, boom/bust, platoon xwOBA, volume, bat speed and PL sentiment — the hitter mirror of /sp-board --scope roster. Use for "rundown on all FA hitters", "best hitter pickups", "show me the FA hitter board", "use all hitting models", "FA pickup deep scan for hitters", "hitter slate grid", "FA hitter decision board", "compare FA hitters across all lenses", "who has the highest season-to-date level", "rank hitters by their level", "who's producing the most", "level board", "who's riding hot vs their model", "I'm dropping X, who do I pick up?", "find me a replacement for Y", "show all FAs above N FP", "what does PL think of my hitters", "PL hitter board", "add the new PL Top 150", "rank all FA hitters and mine by PL". Merges /hitter-slate-grid + /level-board + /fa-replacement-pool (2026-07-20); `pl` mode added 2026-07-28.
maturity: unified-hitter-board
---

# hitter-board — unified hitter decision board (`--mode {slate|level|replace|pl}`)

Merges the overlapping hitter boards into one entry point. All modes share the
same owner seams — live ESPN roster/FA pulls, `resolve_batter_id` collision-safe
id resolution, `safe_name_key` for every join key, `plv_clone.positions`
grouping — and all join on **MLBAM batter_id**, never name (Max Muncy LAD 3B
571970 vs ATH C 691777).

> **Never hand-roll the normalizer in a mode engine.** `pl` mode shipped with a
> local `_nm()` and it silently mis-keyed **Ryan O'Hearn** — the PL cache writes
> a curly apostrophe (U+2019), ESPN/rh3 a straight one (U+0027) — so he matched
> nothing, *including the roster scan*, and the board listed an
> opponent-rostered player as a FREE AGENT (Connelly-Early class, don't-do #7).
> `plv_clone.utils.name_match.safe_name_key` already collapses both apostrophes
> plus `C.J.`/`CJ` and hyphens. Import it; this is fix-backlog item #4 (73
> normalizer copies) and it bit within one run. Fixed 2026-07-28.

## Pick the mode by the question

| Ask | Mode | Complete recipe lives in | Engine |
|---|---|---|---|
| "rundown on all FA hitters", "best hitter pickups", "use all hitting models", "FA hitter decision board" | **`slate`** | `/hitter-slate-grid` SKILL.md | inline 14-layer join (rh3 + blend + archetype + boom_stack + PL150 + on-demand deep-dive) |
| "who's producing the most", "rank hitters by their level", "riding hot vs the model", "level board" | **`level`** | `/level-board` SKILL.md | `scripts/xfp/run_level_board.py` |
| "I'm dropping X, who do I pick up?", "replacement for Y", "all FAs above N FP", "roster vs FA sweep" | **`replace`** | `/fa-replacement-pool` SKILL.md | inline `league.free_agents(size=2000)` scan + model join + `filter_eligible_fa` |
| "what does PL think of my hitters", "PL hitter board", "add the new PL Top 150", "rank all FA hitters and mine by PL", "restate the hitter board" | **`pl`** | this file (§ `--mode pl`) | `scripts/xfp/build_hitter_pl_board.py` |

**Default when unspecified: `slate`** (the full multi-lens decision surface).
Use `level` when the ask is about season-to-date production or the LEVEL-vs-model
gap; use `replace` when a specific drop target (or a whole-roster-vs-FA sweep) is
named; use `pl` when the ask is anchored on **Pitcher List** — its ranks, its
movement, or its take — rather than on our model.

**`slate` vs `pl` is a spine question, not a data question.** `slate` is
MODEL-spined: PL Top 150 is one of 14 columns and the recipe is explicit that
"PL Top 150 alone is NEVER" a ranker, which is right for a pickup board. `pl` is
PL-spined: PL rank IS the sort, unranked players don't appear, and our model
becomes the context column. Ask "who should I add?" → `slate`. Ask "what does PL
say and what moved?" → `pl`.

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
- **`pl`** — one row per PL Top-150 hitter that is MINE or FA, sorted by PL rank,
  ▲▼ vs the prior edition, with rh3·verdict·baseline, L7/L21/season FP/g, boom/
  bust(net), platoon xwOBA (vs R / vs L), PA/team-game vs naive pace, archetype +
  trajectory, bat-speed z, flags, and PL sentiment. Opponent-rostered names are
  excluded, exactly as the SP board does.

---

## `--mode pl` — the PL-spined board

```bash
python scripts/xfp/build_hitter_pl_board.py --date <today> \
    --old-pl-json data/research/pl_cache/pl_hitters_top150_<prior edition>.json
```

Emits `hitter_pl_board_<date>.{csv,md}` to `data/research/triangulate_universe/`.
Typical shape: ~60 rows (≈13 MINE + ≈47 FA) out of the Top 150; the other ~89 are
opponent-rostered.

### Cadence — this is the whole operational rhythm

PL Top 150 **hitters publish ~Wednesday** (SP Top 100 Monday, closers ~Tuesday).
`build_pl_cache.py` picks hitters up Thursday AM. Two consequences:

1. **Always pass `--old-pl-json`.** Once the nightly ingests a new edition, the
   triangulate CSV's `pl_rank` IS the new rank and every move renders `·`. Point
   the flag at the *prior* dated cache to get a real ▲▼. Same fix as the SP
   board's flag (2026-07-27).
2. **Staleness is cadence-aware** (gotcha #10). A Wednesday pull is current until
   the *next* Wednesday, not stale at a flat 7 days. Don't refresh off age alone.

### PL sentiment — sparse BY SOURCE DESIGN, not a build failure

Sources, and who writes them (**attribution differs from the SP board — never
call this column "Nick"**):

| Series | Cadence | Author(s) | Yield |
|---|---|---|---|
| **Top 150 Hitters** (Hitter List) | weekly Wed | **Scott Chu** | selective per-player blurbs |
| **Hitter Recap** | daily | rotating — Amore / Stanzel / O'Brien / Clark / Havelock / Solow | ~5-8 players/day |
| Hitter Matchups · Catchers To Stream | weekly | varies | not yet ingested |

**Expect ~15% row coverage.** SP Roundup recaps essentially every starter, so the
SP board's column is dense. Hitter Recap features ~5-8 noteworthy performances out
of ~250 hitters who played — measured 5 of 61 names across four recaps
(2026-07-28). Rows showing `—` are genuinely unwritten-about. **Do not present
thin coverage as a data gap, and do not fill it by inferring sentiment from the
numbers** — the column's only value is that it is somebody else's independent read.

Write `pl_hitter_sentiment_<date>.json` as `{"sentiment": {safe_name_key: str}}`,
one latest-weighted line per hitter: 🟢/🟡/🔴 + trend arrow + the why in ≤12 words +
`[author]`. Key it with `safe_name_key` — see the normalizer warning above.

### Reading the board

1. **rh3 is still the headline (Rule 13).** PL sets the sort; it does not set the
   verdict. A PL-vs-rh3 gap is the surface this board exists to expose, not an
   error to reconcile — route wide gaps to `/triangulate` or `/conviction-scan`.
   Canonical 2026-07-28: **Ryan Jeffers PL #140 / rh3 #55** (PL undervalues) and
   **Jordan Walker PL #11 / rh3 #98** (PL overvalues, and he's MINE).
2. **PL hitter ranks carry documented bias** — see the `slate` recipe's layer-12
   note. PL alone is never a pickup reason.
3. **Platoon xwOBA replaces the SP board's HR/9 lens** — it is the hitter
   structural-vs-luck read. Floors: 100 PA vs RHP, 40 vs LHP; below that the cell
   is `—` rather than a number that looks real.
4. **Show ALL rows.** If you truncate for readability, say so explicitly — no
   silent caps (same rule as the SP board).

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
- **`/sp-board --scope roster` is `--mode pl`'s twin** — same spine (PL rank),
  same ▲▼ movement, same MINE/FA-only universe, same `--old-pl-json` flag. Two
  columns deliberately do NOT cross over: the SP board's **HR/9 structural lens**
  (pitcher-only; the hitter analogue is platoon xwOBA) and its dense
  **Nick-sentiment** column (no hitter series has comparable coverage — see the
  sentiment table above). Keep the two engines in sync when either gains a lens.

**Deprecation note:** `/hitter-slate-grid`, `/level-board`, and
`/fa-replacement-pool` remain as aliases holding the complete recipes; new
invocations should use `/hitter-board --mode {slate|level|replace|pl}`. `pl` has
no alias — it is new surface (2026-07-28), not a merge.
