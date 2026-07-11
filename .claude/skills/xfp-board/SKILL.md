---
name: xfp-board
description: Merged dual-ranked xFP boards — your full roster PLUS every available FA, ranked together by projected rest-of-season AND fantasy-playoff xFP, for SPs and for all five hitter position buckets (C, 1B/3B, 2B/SS, OF, UTIL). One board per universe so a swap decision is visible at a glance (your guy vs the best FA at his slot, on the same scale, in the same window). SP per_start sourced Stuff+ proj > rp3 data-driven > rp3 Marcel; hitter per_game from rh3 (MLBAM-id-joined, collision-safe). Players the in-season model can't score (IL stashes like Judge / Greene / Snell) fall back to a calibrated talent-prior estimate, clearly flagged LOW-CONF. Live IL return dates fold into availability scaling. Renders a self-contained HTML dashboard (data/outputs/xfp_board.html + GitHub Pages). Use when the user asks "show me the xFP board", "rank my roster against the FA pool", "merged board", "who should I add/drop by rest-of-season value", "best available at each position", "playoff-value board", or wants their staff and the FA pool ranked on one scale.
---

# xfp-board

You are generating the **merged xFP boards** — the user's full roster and the
entire available FA pool, ranked together on a single scale, dual-ranked by
rest-of-season (RoS) xFP and fantasy-playoff xFP. There is one board for SPs
and one for hitters (sliced into 5 position buckets). The point is the swap
decision: the user's own player and the best FA replacement appear on the same
board, in the same window, so an add/drop is obvious instead of requiring two
separate lookups.

Engine: `scripts/xfp/build_xfp_boards.py`
Dashboard: `scripts/xfp/build_xfp_board_dashboard.py` → `data/outputs/xfp_board.html`
(+ `xfp-model/docs/xfp_board.html`, linked in the GH Pages nav as "xFP Board").

## When to use

- "Show me the xFP board" / "merged board" / "rank my roster vs the FA pool"
- "Best available SP/hitter by rest-of-season value"
- "Playoff-value board" (the Aug 17 → Sep 20 window)
- Any add/drop where the user wants their player and the FA alternative ranked
  side-by-side on one scale.

NOT for: single-player deep dives (`/fa-pickup-deep-dive`, `/triangulate`),
the daily SP slate with live boom_stack (`/sp-slate-grid`), or a flat FA-only
list (`/fa-replacement-pool`, `/fa-sp-pool`). This is the **two-window,
roster+FA, dual-ranked landscape**.

## How to run

```bash
# Rebuild both CSVs + the HTML page (mirrors to xfp-model/docs):
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/build_xfp_board_dashboard.py

# Or just the CSVs + a console summary (no HTML):
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/build_xfp_boards.py
```

To present the boards in-conversation, import the engine directly and read the
DataFrames (don't re-implement the join):

```python
import sys; sys.path.insert(0, 'scripts/xfp')
import build_xfp_boards as B
sp  = B.build_sp_board()       # MINE + every FA SP, ranked (per_start rows)
hit = B.build_hitter_board()   # MINE + every FA hitter; `buckets` set per row
have = hit[hit['per_game'].notna()]
for bkey, label in B.HITTER_BUCKETS:
    sub = have[have['buckets'].apply(lambda s: bkey in s)]
    # render top-N by xfp_ros and xfp_po, MINE highlighted
```

The boards are written to dated CSVs:
`data/research/sp_merged_xfp_rank_<date>.csv` and
`data/research/hitter_merged_xfp_rank_<date>.csv`.

## Window math (date-parameterized — works any day)

Module constants at the top of `build_xfp_boards.py`: `TODAY = date.today()`,
`SEASON_END = 2026-09-20`, `PLAYOFF_START = 2026-08-17`. There are no hardcoded
build dates — re-running on a later day re-scopes both windows automatically.

- **xFP RoS** = per_start/per_game × the now→`SEASON_END` window
  (SP ≈ per_start × 1.19 starts/wk; hitter ≈ per_game × 6.3 g/wk),
  scaled by availability (an IL'd player's window starts at their return date).
- **xFP Playoffs** = the `PLAYOFF_START`→`SEASON_END` window only
  (SP × 3.6 full-availability starts; hitter × 18 games), availability-scaled.

## Source tiers (the `src` column — honest provenance)

| `src` | Meaning | Confidence |
|---|---|---|
| `Stuff+` | SP: validated Stuff+ proj_ros_fp | high |
| `rp3_dd` | SP: rp3 `data_driven_*` per_start | high |
| `id` | Hitter: rh3 joined by MLBAM batter id | high |
| `name` | Hitter: rh3 joined by exact-norm name (id resolution missed) | ok |
| `talent_prior` | **LOW-CONF** calibrated Marcel fallback | low — flagged |

## talent-prior LOW-CONF caveat (READ THIS BEFORE PRESENTING)

`talent_prior` rows are an **if-healthy** Marcel estimate for elites the
in-season form models can't score — IL stashes like **Aaron Judge, Hunter
Greene, Blake Snell**. They are NOT a real in-season read. They exist so those
players can still be *ranked* rather than vanishing from the board, and the
dashboard flags them with a `LOW-CONF*` badge + legend. Per CLAUDE.md gotcha
#13, treat them as a **conviction sorter, not an additive point forecast** —
never headline a talent-prior number as if it were a model projection. The
calibrated hitter prior has a sample-size guard (≥250 total PA, ≥200 in one
season) so fringe players don't get a noisy prior.

## Gotchas this engine already handles (don't re-derive)

- **`marcel_il` → Stuff+ (CLAUDE.md gotcha #1).** SP per_start prefers the
  validated Stuff+ proj over rp3; the rp3 Marcel value (the suppressed
  `marcel_il` prior) is used only as the LOW-CONF `talent_prior` tier, never as
  a real read.
- **rp3 "Last, First" name flip.** rp3 stores `Snell, Blake`; the engine flips
  to `Blake Snell` (via `talent_prior.flip_name`) before matching the FA pool /
  roster, or marcel-only arms silently fall into NO_DATA.
- **Collision safety (CLAUDE.md gotcha #10).** Hitters join rh3 by MLBAM id via
  `resolve_batter_id(name, team=, position=)` with an ESPN→collision-list team
  alias (OAK→ATH). Exact-norm name fallback REFUSES to guess when the name is
  ambiguous in rh3 (Max Muncy LAD/ATH). `main()` prints a Max Muncy smoke test.
- **FA pool size.** Pulls `free_agents(size=1500)` per position (not the
  per-position `size=300` trap), so low-owned high-FP candidates aren't dropped.
- **IL return / Corbin-Burnes caveat.** Return dates come from
  `LeagueState.injury_details()` where available; otherwise a coarse status
  heuristic. **Surgery / season-ending cases are over-estimated** by the
  heuristic (a FIFTEEN_DAY_DL guess of 21 days for a player who is actually done
  for the year) — treat any long-IL talent_prior row as a ranking aid, not a
  guarantee. The dashboard methodology note says this too.
- **Console encoding (CLAUDE.md gotcha #2).** Always prefix inline python with
  `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`.

## Presentation

The HTML page (and any in-conversation rendering) must:
- Highlight MINE rows and always surface the user's own players even when they
  rank below the display cut (an IL'd talent-prior stash like Judge should never
  silently drop off — `_topn_plus_mine` pins MINE rows).
- Show both `xFP RoS` and `xFP PO` columns plus `per_start`/`per_game`, owner,
  team, own%, src, and the return date for IL'd players.
- Flag `talent_prior` rows LOW-CONF with the legend.
- Lead with the swap framing: for each of the user's weaker rostered players,
  name the best FA above them at the same slot (with the Δ in xFP) — but if the
  upgrade rests on a `talent_prior` row, state the LOW-CONF caveat explicitly.

## Daily refresh

Wired into `refresh_dashboards.py` as fail-soft step **4.55** (rebuilds both
CSVs + `xfp_board.html`, mirrored to GH Pages). Non-gating — an ESPN/MLB hiccup
won't abort the pipeline.

## Related

- `/fa-replacement-pool` / `/fa-sp-pool` — flat FA-only ranked lists
- `/sp-slate-grid` — daily SP slate with live boom_stack + all model lenses
- `/sp-week-plan` — my-roster period SP-cap math (10 std / 16 ASG / 20 playoff)
- `/triangulate` — single/few-player three-lens deep dive
- `/sp-stash-finder` — IL'd FA SPs with playoff-return timing
