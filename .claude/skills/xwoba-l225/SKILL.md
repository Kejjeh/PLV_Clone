---
name: xwoba-l225
description: Rolling trailing-225-PA xwOBA leaderboard for hitters — FA pool, my roster, or league-wide. Uses a fixed PLATE-APPEARANCE window (the validated stabilization minimum) instead of a calendar window, walking back into the prior season when the current one is short, so every row carries the same denominator and the ranking is actually comparable. Use when the user asks to "rank by xwOBA", "xwOBA leaderboard", "who has the best bat available", "L225 xwOBA", "xwOBA for my team", or wants contact-quality rank rather than fantasy-point rank. Builds ON DEMAND (~90s) — deliberately not in the nightly refresh. Rule 13 — context/awareness only, never moves rh3/rp3/rprs2.
---

# xwoba-l225

Rank hitters by xwOBA over their **last 225 plate appearances** — the window
in which the metric actually carries signal.

Engine: `python -X utf8 scripts/xfp/build_xwoba_l225.py --scope {all|fa|roster|league}`
Outputs: `data/outputs/xwoba_l225.csv` (latest) + `xwoba_l225_<date>.csv`.

**Build it when asked, not on a schedule.** A nightly step existed for a few
hours on 2026-08-10 and was removed the same day: the forward study (7 disjoint
windows, 2 seasons) measured xwOBA's incremental value beyond the season FP
level at **partial r = +0.069, signs unstable** — real enough to keep as a
context lens, not enough to justify a standing pipeline slot. Check the CSV's
`asof_date`; if it predates the latest statcast pull, rerun (~90s).

## Why a PA window, not L7/L21/L42

`plv_clone.stabilization` puts xwOBA/PA at **225 PA** for forward r ≥ 0.50.
Measured on the 2026 FA pool, the median PA available in each calendar window
was **L7 = 8 · L21 = 28 · L42 = 53**, and **zero** players cleared 225 in any of
them. Short-window xwOBA is therefore noise *by construction* — not "a small
sample worth a caveat", but a number with no forward content. Ranking on a
fixed PA window fixes the denominator across every row.

If the user explicitly asks for calendar windows anyway, produce them, label
the PA count per window, and say plainly that only the season/L225 column is
readable. For genuinely fast-stabilizing short-window reads use bat speed
(50 swings), K% (50 PA), or hard-hit/barrel (50 BIP) instead.

## Reading the output

| Column | Meaning |
|---|---|
| `xwoba_window` | xwOBA over the trailing 225 PA — **the ranking column** |
| `pa_current_in_window` / `pa_prior_in_window` | season split of those 225 PA |
| `window_from` / `window_to` | calendar span the window covers |
| `xwoba_current` / `xwoba_prior` | full-season figures, for direction |
| `window_full` | False = fewer than 225 PA exist even across both seasons |
| `rank_full_window` | rank among full-window players only |

**Discount rows with a large `pa_prior_in_window`.** A window reaching back
months mixes two run environments and is a staler read than its rank implies
(canonical: Giancarlo Stanton ranked #4 on 129-of-225 PA from 2025).

**Never rank on `window_full == False` rows** without saying so — their
denominator is smaller than everyone else's, which is the exact failure the
fixed window exists to prevent.

## Hard rules

1. **Rule 13 — context only.** xwOBA never moves rh3/rp3/rprs2 or a projection.
   It ranks the *bat*; BrownU scores `R + TB + RBI + BB + HBP + SB − K`, which
   also pays for lineup slot, team offense and steals that xwOBA cannot see. A
   player can be top-10 here and a mediocre fantasy add (and vice versa —
   canonical 2026-08-10: Durbin #83 by xwOBA yet the best one-week add by
   ΔP(win) on volume and a 10% bust rate).
2. **xwOBA ≠ xwOBACON.** The numerator is per-PA: xwOBAcon on batted balls,
   else the wOBA linear weight (BB .69 / HBP .72 / K 0), over `woba_denom == 1`
   rows. Using `estimated_woba_using_speedangle` alone silently drops the
   strikeouts and walks that dominate the metric.
3. **Never key statcast on `player_name`** — on pitch-level rows that column is
   the PITCHER (16/972 hitter match rate when tried). Resolve through the
   mlbam-keyed model tables, as the engine does.
4. **Live FA verification.** The pool comes from one `free_agents(size=2000)`
   pull minus a live `get_all_teams()` scan — never per-position caps
   (gotcha #6), never memory (gotcha #4).
5. **Include IL players when the question is about talent**, exclude them when
   it is about this week. `--scope fa` returns both; filter on `inj` at the
   presentation layer and say which you did.

## Owner modules (call, never re-derive)

| Fact | Owner |
|---|---|
| 225-PA stabilization minimum | `plv_clone.stabilization.minimum('xwoba_ppa','H')` |
| name → join key | `plv_clone.utils.name_match.join_key` |
| live roster / FA truth | `app.espn_connector` |

## Routes to

`/triangulate` for a full three-lens card on anyone surfaced here ·
`/hitter-board` for a fantasy-points board · `/prior-year-peg` when a hitter's
window is far off his own baseline · `/player-verdict` to actually choose.
