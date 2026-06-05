---
name: sp-stash-finder
description: Find IL-stash SP candidates from the full Pitcher List universe (Top 100 + injury list), filter to those whose ESPN return date arrives before playoffs end, and rank by playoff xFP and IL-slot cost. Use when planning for playoff weeks 21-23, when the user asks "any IL stashes worth grabbing", "playoff sleeper SP", "Snell-class FAs", or when scanning for arms that opponents have under-decoded.
---

# sp-stash-finder

You are finding IL'd SPs available in the BrownU FA pool whose return dates
fit the playoff window, ranked by playoff xFP impact. The discovery that
prompted this skill: Blake Snell (PL injury list #9, mdl 14, per_start 13.02,
return 2026-07-17) was sitting in the FA pool at 0.1% league ownership while
projecting as the user's #2 SP all the way through playoffs.

## Why this skill exists

The previous workflow for FA SP scans (`/fa-sp-pool`, `/fa-replacement-pool`)
filters to ACTIVE pitchers with recent starts. That deliberately excludes
60-day IL stashes that don't have a current rp3 projection or that signal as
`il`. But the highest-value FA pickups for playoff-bound teams ARE the IL
stashes nobody else is watching:

- Blake Snell — IL60 elbow, returns 7/17, per_start 13.02, 0.1% owned
- Nick Pivetta — IL60 elbow, returns 7/10, per_start 11.97
- Eury Pérez — IL15 gracilis, returns 7/24, per_start 11.24
- Matthew Boyd — IL15 knee, returns 6/12 (8 days)
- Logan Henderson — IL back, returns 7/1, shadow-scout AVG_PROCESS

Plus the PL injury table (39 names as of Week 11 6/1) isn't in our current
`pl_sps_top100.json` cache — those PL ranks were missing from triangulate.
This skill explicitly merges both layers.

## Workflow

### Step 1 — Pull the latest PL Top 100 + IL table

Use `WebFetch` on the latest weekly URL pattern:
`https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-<MM-DD>-week-<N>-rankings/`

Extract BOTH the main Top 100 AND the separate "Injured Pitchers" tiered list
that follows it. The Week 11 (6/1) article is the canonical example.

### Step 2 — Cross-reference with ESPN + our model

For each name in both lists:

1. **Owner lookup** via `league.teams` roster scan + verified FA filter
   (see `feedback_free_agents_leaks_rostered.md`). Skip rostered names.
2. **ESPN injury status** + return date via `app.espn_connector.get_injury_details([player_ids])`.
3. **Model projection** from `data/outputs/xfp_rp3_projections.csv` (rp3 per_start, rank, recform).
4. **Archetype** from `data/research/sp_ratings_master.csv` (OVERALL, traj).
5. **Shadow-scout** (if rp3 + archetype both blank) — see `/shadow-scout`.

### Step 3 — Filter for playoff viability

Playoff weeks 21-23 are roughly **mid-Aug through early Sept**. Compute each
stash's:

- `days_until_return` (from ESPN injury detail)
- `weeks_active_pre_playoffs` = (playoff_start_date - return_date) / 7
- `playoff_xfp` = per_start × 3.6 (assume 3.6 starts in 3 playoff weeks)
- `thru_playoffs_xfp` = per_start × (weeks_active_pre_playoffs × 1.19 + 3.6)

A stash is viable if `return_date < playoff_start_date - 7 days` (need at least
1 week of ramp). Stashes that return DURING playoffs (e.g., Clay Holmes 8/25)
are border-case — flag with WARNING.

### Step 4 — Rank by playoff value relative to IL slot cost

```
playoff_value_per_il_day = thru_playoffs_xfp / days_on_user_IL
```

Higher = better. Stashes with short IL holds (Boyd 8 days, Pivetta 36 days)
score very highly per day. Snell at 43 days is still worth it given his
13.02 per_start.

### Step 5 — Format and surface

Tiered output:

```
ELITE PLAYOFF STASHES (return before playoffs, premium per_start):
  Snell (rp3 #14, per_start 13.02, return 7/17, +90 FP vs Kelly thru playoffs)
  Pivetta (rp3 #32, per_start 11.97, return 7/10, +73 FP)
  ...

NEAR-TERM RETURNS (no playoff cost, immediate ramp):
  Boyd (return 6/12, +30 FP vs Kelly thru playoffs)
  ...

SHADOW STASHES (PL IL list + shadow-scout PLUS_PROCESS):
  Logan Henderson (PL IL #16, shadow=AVG_PROCESS-58, return 7/1)
  ...

SKIP (returns post-playoffs or 2027):
  Burnes, Pepiot, Eflin, Horton, Smith-Shawver, ...
```

## When to invoke

- "Find me playoff stash SPs"
- "Any IL pitchers worth grabbing"
- "Snell-class FAs"
- "What about [rookie name]" combined with a return-date question
- Monday-morning planning when the user has IL slot capacity
- When `/forced-drop-planner` flags the user's IL pipe will fill up — gives stash candidates with later returns

## Anti-patterns

- **Don't recommend Burnes / TJ-recovery stashes.** Tommy John return is 12-18
  months. Even though their `per_start` projections look elite, they won't pitch.
  Always check the return date.
- **Don't trust rp3 projections for IL'd players blindly.** The model uses
  prior production; it can't know they're hurt. Cross-check with ESPN return
  date + injury type.
- **Don't grab IL stashes the user can't roster.** Check their IL slot count
  (BrownU has 3 IL slots). A stash that costs 6 weeks of IL is fine if a slot
  is open; if the user is already using all 3 IL slots, the stash forces a
  drop of another IL'd player first.
- **Don't ignore the shadow lens for rookies.** If a PL-ranked rookie has 200+
  MLB pitches in 2026, run `/shadow-scout` before passing. Henderson and Brown
  were both flagged correctly by the shadow lens that the engine missed.
- **Don't use stale PL cache.** Refresh the Top 100 article weekly; the IL
  table changes faster than weekly (Eury Pérez moved from main list to IL
  between weeks 10 and 11).

## Limitations

1. **PL IL cache.** The current `pl_sps_top100.json` only stores the main Top
   100 — the injury table is not cached. Until that's fixed, refresh manually
   via WebFetch each Monday.
2. **Playoff start date assumption.** Hardcoded to "mid-Aug 2026" for week 21.
   Confirm via `league.settings.matchup_periods` if uncertain.
3. **IL slot tracking.** ESPN's `lineup_slot=='IL'` is the source of truth for
   user IL slot capacity. The user has 3 IL slots in BrownU.

## Related

- `/shadow-scout` — for rookies the lens can't read otherwise (Henderson, Brown)
- `/triangulate` — for a deeper read on any specific stash candidate
- `/forced-drop-planner` — figures out when the IL pipe will fill up
- `/fa-sp-pool` — sibling skill for ACTIVE FA SPs (not IL stashes)
- `feedback_free_agents_leaks_rostered.md` — required filter pattern
