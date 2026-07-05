---
name: sp-board
description: Unified SP decision board with `--scope {slate|roster}`. `--scope slate` = full-slate scan over a date window (every scheduled SP start, FA highlighted, joins all model + boom + PL-streamer layers, decision-deadline header) — the old /sp-slate-grid. `--scope roster` = one row per Pitcher-List-ranked starter that is MINE or FA, integrating rp3/triangulate/blended xFP + recent-form L1/L3/L5/L8/season + the HR/9 structural lens + boom%/bust%/net + K/st (K-FED/IP-FED) + velo/decline flags + the full Pitcher List stack distilled into Nick Pollack's chronological sentiment — the old /sp-pl-board. Use for "SP board", "which streamer/start today", "what does Nick say about my SPs+FA", "every SP start tomorrow", "restate the SP board", "integrate the PL list". Merges /sp-slate-grid + /sp-pl-board (item 15, 2026-07-04).
maturity: unified-sp-board
---

# sp-board — unified SP decision board (`--scope {slate|roster}`)

Merges the two overlapping SP boards into one entry point (item 15). Both scopes
share the same owner modules (`detect_pitcher_role`, `pl_cache`, `lib/boom_bust`,
`lib/extra_lenses` floor/park/opp/next_start) and all join on **MLBAM pitcher_id**
— never name (ESPN playerId ≠ MLBAM; same-name collisions like Logan Allen).

## Pick the scope by the question

| Ask | Scope | Delegates to |
|---|---|---|
| "every SP start tomorrow", "full slate", "who's starting DATE1+DATE2", "streamer to pick today" | **`slate`** | the `/sp-slate-grid` flow |
| "my SP board", "what does Nick say", "integrate the PL Top 100", "restate the board", "pick a drop/add from my staff+FA" | **`roster`** | `scripts/xfp/build_sp_pl_board.py` |

Default when unspecified: **`roster`** (the one-look MINE+FA board). Use `slate`
whenever the user names a date window or asks about "every"/"all" starts.

---

## `--scope slate` — full-slate scan

Run the full `/sp-slate-grid` protocol (that SKILL.md holds the complete recipe):
probables from MLB Stats API over the date window (default today+tomorrow), join
ALL model layers (Blended xFP + CI, rp3 + per_start band + opp_bat_index, live_marginal
+ value_tier, Triangulate verdict, Sustainability, SP archetype OVERALL/traj/T+1,
shadow_scout for no-rp3 rookies, boom_stack 0-4 + boom%/bust%/E[FP] + secondary tags,
process panel, PL Top 100, PL daily streamers with auto-fresh WebFetch), tag ownership
MINE/opp/FA, render a time-sorted grid with FA highlighted + a decision-deadline header,
then synthesize a boom-layer-aware pick that can DOWNGRADE a high-rp3 name when live
boom disagrees (canonical Sheehan 6/7/26 rp3 #55 but boom 9/18 = skip).

Also carry the **Floor + Conv context columns** (item 1) — `floor_flag`
(FLOOR-RISK/SAFE-FLOOR) + conviction-scan divergence (PROCESS>MODEL / MODEL>PROCESS),
display-only (Rule 13).

## `--scope roster` — MINE + FA PL-ranked board

Run the `/sp-pl-board` engine — `python scripts/xfp/build_sp_pl_board.py --date <today>`.
One row per PL-ranked starter that is MINE or FA, folding in: rp3 rank + triangulate
verdict + blended xFP; recent-form L1/L3/L5/L8/season FP-per-start; the **HR/9 structural
lens** (2026 vs career); the reliable-boomer lens (boom%/bust%/net); K% and **K/st (src)**
= K-FED/IP-FED (item 4, `k_share=K/(K+3.3·IP)`); velo/decline flags; and the full Pitcher
List stack distilled into **Nick Pollack's chronological sentiment** per pitcher. Emits
the combined-column markdown board (`sp_pl_board_<date>.md`) + the 21-col CSV.

**Both lenses PRESERVED in the merge:** Nick-sentiment column (roster scope) and the
HR/9 structural lens (roster scope) are load-bearing and must never be dropped.

---

## Relationship to the other SP skills

- `/stream-the-stack` stays thin (boom-tier FA streamers, shares probables + FA-pool helpers).
- `/sp-stuff-board` (Stuff+) and `/sp-floor` (K-BB floor) stay standalone single-lens; feed their picks into this board.
- `/fa-pitcher-pool --role sp` = FA-only flat availability list (Connelly-Early verified); `/sp-week-plan` = my-roster cap math. This board is the joined decision surface.

**Deprecation note:** `/sp-slate-grid` and `/sp-pl-board` remain as aliases pointing here;
new invocations should use `/sp-board --scope {slate|roster}`.
