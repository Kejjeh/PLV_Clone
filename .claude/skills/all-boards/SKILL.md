---
name: all-boards
description: Master meta-skill for the BOARDS domain — one command that renders the complete browse surface across every pool. Chains sp-board --scope slate (every scheduled SP start, FA highlighted) → streamer-precision-board (today's precision streamer table + boom>=2 shortlist) → hitter-board (slate mode FA decision board) → fa-pitcher-pool --role sp AND --role rp (availability-verified pitcher pools) → fa-monitor HIGH alerts. Use when the user asks "show me all the boards", "full market scan", "everything available", "what's out there across the board", or wants the whole FA landscape in one pass instead of five invocations. Surfacing only — adds route to /player-verdict then /moves.
---

# all-boards

The browse-domain master: every board, one pass, one FA pool pull.

1. **sp-board --scope slate** — every scheduled SP start in the window,
   MINE/FA tagged, model + boom + PL-streamer layers.
2. **streamer-precision-board** — today's FADJ + boom_stack precision table;
   include its `--filter boom>=2` shortlist.
3. **hitter-board** (mode=slate, the default) — the layered hitter FA
   decision board.
4. **fa-pitcher-pool --role sp** and **--role rp** — availability-verified
   pools (rp for the RP-for-RP-upgrade-only lane; 4-RP floor context).
5. **fa-monitor** — HIGH-priority alerts only (MONITOR tier collapsed).

## Pull-once contract (best-effort — QA'd 2026-07-20)

ONE `league.free_agents(size=2000)` + ONE `get_all_teams()` for every
INLINE join (gotcha 6: never per-position pulls; Connelly-Early/Sheehan
availability rules — roster scan, never percent_owned). The standalone
engines (`run_streamer_board.py`, `run_fa_monitor.py`) re-pull internally
(no injection seam yet — registry backlog); accept it, don't monkeypatch.

Meta-pass scope: carry each board's TABLE layers only — skip the per-player
deep layers (triangulate/sustainability/live-marginal/PL WebFetch refresh)
that the alias recipes describe for standalone runs. fa-monitor: the engine
takes `--signals` (default A-F + J-O; G/H/I are compute-heavy opt-ins);
there is no `--priority` flag — apply the HIGH filter in the report.
marcel_il SPs with NO FG Stuff+ row: tag NO-STUFF-DATA (never rp3-rank
them). Roster-side tables bucket via `detect_pitcher_role`, never ESPN
position (Detmers).

## Output format

Five sections in chain order, each board's own table format preserved,
prefixed by a 5-line **"Top of every board"** digest (best FA SP start, best
streamer, best FA hitter, best FA RP, loudest HIGH alert) so the answer is
readable without scrolling.

## Hard rules

1. FAs only in add columns (never another team's player as "available").
2. marcel_il SPs rank by Stuff+ in any board row that surfaces them.
3. Rule 13: boards surface; they do not execute or auto-recommend drops —
   route to `/player-verdict` (pick) then `/moves` (execute).

## When NOT to use

- You know the position already → the specific board alone is faster
  (`/sp-board`, `/hitter-board`, `/fa-pitcher-pool`).
- Game-day morning routine → `/daily-rhythm` (leg 2 already carries the
  streamer board).
- Cross-position roster-vs-FA value on one scale → `/xfp-board` (standalone,
  deliberately not absorbed here).
