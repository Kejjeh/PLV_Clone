---
name: sp-rp-stuff-windows
description: Trailing-pitch/swing-window stuff leaderboard for SP and RP — velo, whiff%, and swstr% each computed over the empirically validated stabilization minimum (L150 pitches velo, L150 swings whiff, L175 SP/L200 RP pitches swstr) instead of a calendar window. Scopes to FA pool, my roster, or league. Use when the user asks for a "velo leaderboard", "whiff leaderboard", "swstr leaderboard", "stuff window", "L150 velo", "who's throwing hardest lately", or wants a stabilized in-season stuff read for SP/RP rather than a calendar L7/L21 cut. Rule 13 — context/awareness only, never moves rp3/rprs2.
---

# sp-rp-stuff-windows

Rank SP/RP by **velo, whiff%, and swstr%** over a trailing PITCH/SWING window
sized to each metric's own validated stabilization minimum — the pitcher-side
analog of `/xwoba-l225`.

Engine: `python -X utf8 scripts/xfp/build_sp_rp_stuff_windows.py --scope {all|fa|roster|league}`
Outputs: `data/outputs/sp_rp_stuff_windows.csv` (latest) + `sp_rp_stuff_windows_<date>.csv`.

## Why a pitch/swing window, not a calendar window

`plv_clone.stabilization.SP_MINS` / `RP_MINS` (measured 2026-07-29,
`pitcher_cutoff_stabilization_2026-07-29.md`, 26,958 SP + 42,978 RP snapshots):

| Metric | SP minimum | RP minimum |
|---|---|---|
| velo | 150 pitches (r≈.90 at the first bucket — the king metric) | 150 pitches |
| whiff% | 150 **swings** | 150 swings |
| swstr% | 175 pitches | 200 pitches |

These three are the ONLY pitcher-side metrics that reliably stabilize
in-window. Do not extend this skill to chase%, BB%, hard-hit/barrel, or
HR-rate against — all four are in `NEVER_STABILIZES` for both SP and RP
(CLAUDE.md gotcha #12); there is no sample size at which a window read on
them is valid. xwOBA-against needs **525 TBF** (`woba_agn`, SP_MINS) — roughly
a full season — so it is deliberately NOT part of this leaderboard; ask for
it separately and expect almost every in-season row to be "not yet enough."

A calendar window (L7/L21) does not carry a fixed denominator across
players — one arm's "last 2 weeks" might be 300 pitches, another's 90. This
engine instead walks each pitcher's own pitch/swing log backward until it
hits the metric's minimum, so every row in a column is the same exposure and
the ranking is actually comparable. Thin-sample arms (e.g. a recent callup)
get walked into the prior season the same way `/xwoba-l225` does for
hitters, flagged via `window_crosses_prior_season`.

## The whiff-window gotcha (fixed 2026-08-10, don't reintroduce)

Whiff%'s minimum is in **swings**, not pitches. `d.tail(150 pitches)` only
contains ~65-75 swings at a typical ~45-50% swing rate — silently underfilling
the window. The engine walks back through the SWING-only rows
(`d[d["is_swing"]].tail(whiff_n)`), not the raw pitch log. If you ever see a
whiff% column moving when nothing else does, check this first.

## Role assignment for FA (the CLAUDE.md gotcha #8 adaptation)

Free-agent objects don't carry MLB Stats API `gamesStarted`, but ESPN's own
`free_agents()` pull already has `GS`/`GP` in `p.stats[0]['breakdown']` — no
extra API call needed. Role logic, cheapest-check-first:

1. `eligibleSlots` has SP but not RP → **SP**
2. `eligibleSlots` has RP but not SP → **RP**
3. Both (a genuinely dual-role arm) → `GS/GP >= 0.4` → **SP**, else **RP**

Never trust the raw `position` tag alone on a dual-eligible arm — it
mislabels current relievers who still carry SP eligibility (and vice versa).
Roster-scope rows use the existing `detect_pitcher_role` owner instead (it
has a real MLB Stats API gamesStarted fallback).

## Reading the output

| Column | Meaning |
|---|---|
| `velo_window` / `whiff_window` / `swstr_window` | the three ranking columns |
| `*_window_full` | True only if that pitcher's own log actually reached the minimum |
| `window_full` | AND of all three — **filter to this before ranking** |
| `n_pitches_avail` | total pitches in the pull (both seasons) |
| `window_crosses_prior_season` | the window reached back into last year — a staler read than its position implies |
| `days_since_last_pitch` | recency vs `asof_date` — a large gap (IL, demoted) means the window is a "last healthy" snapshot, not current form |

The console table already filters to `window_full == True` and reports how
many rows were excluded as thin — never present a `window_full == False` row
in a ranked list without saying so explicitly (same rule as `/xwoba-l225`).

## Hard rules

1. **Rule 13 — context/awareness only.** This never moves rp3/rprs2 or a
   projection. It's a stuff-level read; rp3/rprs2 already integrate this kind
   of signal into the projection where it's earned its keep.
2. **A velo/whiff/swstr spike is a LEVEL read, not automatically a decline
   or breakout call.** Pair with `/sp-decline` (whiff/K LEVEL trend) or
   `/pitcher-sustainability` before headlining "his stuff just jumped."
3. **Live FA verification** — the pool comes from one `free_agents(size=2000)`
   pull minus a live `get_all_teams()` scan (gotcha #6/#4), never per-position
   caps or memory.
4. **Owner modules — call, never re-derive:**

| Fact | Owner |
|---|---|
| stabilization minimums | `plv_clone.stabilization.minimum(<metric>, side)` |
| name → join key | `plv_clone.utils.name_match.join_key` |
| roster pitcher role | `scripts.xfp.lib.pitcher_role.detect_pitcher_role` |
| live roster / FA truth | `app.espn_connector` |

## Routes to

`/triangulate` for the full three-lens card on anyone surfaced here ·
`/sp-decline` / `/pitcher-sustainability` before calling a velo/whiff move a
trend · `/sp-board` / `/fa-rp-pool` / `/fa-sp-pool` for the fantasy-points
decision layer · `/fa-pickup-deep-dive` to turn a stuff spike into an
add/pass verdict.
