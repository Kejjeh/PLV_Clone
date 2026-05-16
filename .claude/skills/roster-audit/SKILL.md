---
name: roster-audit
description: Generate a structured audit of the user's BrownU fantasy roster — slot occupancy, IL/return timeline, SP cap math, drop candidates, FA add candidates, and forward-looking roster moves. Use weekly, after any IL transaction, or when planning lineup/drop decisions. Encodes feedback rules about IL-slot vs IL-status, FA-only "best available", and cap/role/eligibility awareness.
---

# roster-audit

You are producing a structured weekly snapshot of the user's roster
state so they (and future-you in another session) can make consistent
drop/add and lineup decisions. The skill exists because the same audit
got done manually multiple times with subtle inconsistencies (counting
injured-on-bench as if it were IL-slotted, ranking RPs with rp3 instead
of rprs2, ignoring SP cap constraints).

The user's job is to ask. Your job is to pull live data, do the math
the same way every time, and surface the next 1-2 actionable moves.

---

## Inputs (all optional — sensible defaults apply)

If the user gave you these, use them. Otherwise default:

1. **Focus area** — `full`, `pitching`, `hitting`, or `il-only`.
   Default `full`.
2. **Matchup week** — ISO date of the week start (Mon). Default: this
   week (today's Monday).
3. **Drop-add depth** — how many drop/FA candidates to surface per
   position. Default 3.

---

## Step 1 — Pull live roster + injury data

Use the connector helper. From repo root:

```python
from app.espn_connector import get_my_roster_with_injuries
df = get_my_roster_with_injuries()
```

This returns one row per rostered player with at least:
`player_name, player_id, position, pro_team, eligible_slots,
lineup_slot, injured, injury_status, on_team_name` plus, for any
`injured=True` player: `injury_type, injury_detail, injury_side,
return_date, days_until_return, status_code, short_comment`.

If the call fails (ESPN auth, network), surface the error verbatim
and stop — do not proceed with stale data. Stale roster reads have
caused at least one bad recommendation already (the Erceg/Giolito
mix-up).

---

## Step 2 — Slot occupancy table (the IL slot ≠ IL status gate)

This is the most-violated rule in the codebase. Compute occupancy from
`lineup_slot`, NEVER from `injured`. Examples:
- Player A is on the 15-day IL and assigned to an IL slot → IL slot used
- Player B is on the 15-day IL but kept in his OF slot (returning soon)
  → IL slot NOT used; OF slot occupied
- Player C is on the 15-day IL but stashed on BE because IL slots are
  full → IL slot NOT used; BE slot occupied

Output a one-line summary:

```
IL slots: X / 3 used   |   Bench: Y / 4 used   |   Active starters: Z / 22 used
Players injured but NOT in IL slot: <list with their actual lineup_slot>
```

The "injured but not in IL slot" list is the *cleanup opportunity* —
those players may eat slots that could be freed by an IL-slot swap.

Reference: `memory/feedback_il_slot_vs_il_status.md`.

---

## Step 3 — IL return timeline

Build a table sorted by `days_until_return` ascending:

| Player | In slot | IL type | Injury | Return | Days | In IL slot? |
|---|---|---|---|---|---|---|
| ... | ... | IL15 / IL60 / DTD | Forearm Strain (R) | 2026-05-22 | 7 | Yes/No |

Annotate each row with the slot transition that happens on return:
- "Activates → P slot" (returning SP)
- "Activates → OF slot, no slot freed" (was in OF while IL'd)
- "Activates → would need a corresponding drop because all P slots full"

Then summarize:
- Total returns next 7 days
- Total returns next 30 days
- IL slots that will free up in next 30 days (the relevant supply
  for any future IL stash)

---

## Step 4 — SP cap math

Hard-coded league constants (BrownU, per
`memory/reference_league_rules.md`):
- 10-SP-start-per-week cap (only first 10 count)
- ~1.19 SP starts per active SP per week (empirical)

Compute:
```
healthy_sp = count(roster[pos=='SP' AND lineup_slot != 'IL' AND NOT injured])
projected_starts = healthy_sp * 1.19
gap_to_cap = 10 - projected_starts
```

Report:
- "X healthy SPs → ~Y starts/week vs 10 cap → Z starts short / over"
- If under cap by ≥ 0.5 starts: streaming needed N times this week.
  Suggest checking `xfp_rp3_projections.csv` for FA streamers (next step).
- If over cap: no streaming, suggest the lowest-projection SP to bench
  or drop next IL return.

Add a forward-looking note: "Once <returning player> activates on
<date>, healthy_sp becomes <new count> → <projected_starts new>."
Highlight the date that pushes you over the cap if applicable — that's
the forced-drop date.

---

## Step 5 — Pull projections for ranking

Load the three model outputs:
```python
import pandas as pd
rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
```

Pre-flight check — verify build dates. If any file's mtime is > 2 days
old, warn the user before proceeding:
> "rh3 projections last built <date>; recommend running
> refresh_dashboards.py before relying on these for decisions."

Use rh3 for HITTERS, rp3 for SPs, **rprs2 for RPs** (NOT rp3 — common
mistake; reference `memory/feedback_team_value_reads_must_be_cap_role_elig_aware.md`).

Merge to roster by fuzzy name match (use
`app.espn_connector.fuzzy_match_name` or the merge helper). Surface
any unmatched roster players explicitly — these are usually rookies or
name-format mismatches and need manual lookup.

---

## Step 6 — Drop candidates (sorted by RoS projection, ascending)

For each position bucket (hitter, SP, RP) on the roster, sort by the
appropriate projection column:
- Hitters: `xfp_rh3_per_pa` (or per-game if available)
- SPs: `xfp_rp3_per_start`
- RPs: `xfp_rprs2_per_g` (or analogous)

Surface the bottom 3 per bucket as drop candidates, with a one-line
"why this might NOT be a drop" note for each — positional flex,
returning from IL, closer-of-record context, etc. This prevents the
"PE the lowest number" mistake.

Especially flag:
- Players with multi-position eligibility (positional value not in raw
  projection)
- Players in unsettled bullpen roles (use save_handcuffs context per
  `memory/feedback_save_handcuffs_needs_closer_context.md`)
- Players with shorter return windows than 15-day baseline

---

## Step 7 — FA add candidates (filter to FREE AGENTS ONLY)

Critical rule (`memory/feedback_best_available_means_FA_only.md`):
**"best available" means FREE AGENTS only**, not players on other teams'
rosters.

```python
from app.espn_connector import get_free_agents, merge_with_model
fa_pit = get_free_agents(position='SP', size=200)
fa_hit = get_free_agents(size=300)  # all hitters
```

Filter out anything `percent_owned > 95` if you're being conservative
(those usually get scooped before you can claim them in 8-team).

Merge each FA pool with the relevant projection, sort top-N per
position bucket. For each candidate, surface:
- Projection (xfp number)
- Pollack tier if data available (cross-reference his Top-150 hitters
  or SP Roundup if recent PDF/scrape is in scope)
- Slot fit: which of your roster's eligible_slots does this candidate
  fill (use ESPN eligibleSlots)
- Injury status (don't recommend an FA in 15-day-IL unless the user is
  IL-stashing)

If the user has IL slots open OR a returning player who frees one,
mention IL-eligible FA stashes (deferred-value pickups) separately.

---

## Step 8 — Forward-looking moves (next 2 weeks)

Combine Steps 3 + 4 + 6 + 7 into a sequence of recommended actions:

```
This week:
  - Drop X, add Y (cap-driven / matchup-driven reason)
  - Move Z from BE to IL slot (Helsley-style cleanup)

Within 7 days:
  - Player A returns → activates to <slot>; if all slots full, drop
    <lowest projected> on activation day.

Within 30 days:
  - Player B returns → IL slot frees; opportunity for IL stash candidate <C>
  - Date X: SP count crosses 10/wk cap → forced drop, pre-identify
    candidate from Step 6
```

Keep this to ≤ 5 actions. The user can act on 5; they can't act on 20.

---

## Step 9 — Output structure

Final report uses this layout (markdown for readability):

```markdown
# Roster audit — <date>

## Slot occupancy
<one-line summary from Step 2>
<injured-but-not-IL-slotted list>

## IL return timeline
<table from Step 3>
<summary>

## SP cap math
<X SPs → Y starts vs 10 cap → Z gap>
<forward-looking dates>

## Drop candidates (bottom-3 per bucket)
<table per bucket, with "do-not-drop" caveats>

## FA add candidates (FA only)
<table per bucket, with slot fit + injury status>

## Recommended moves (next 2 weeks)
<≤ 5 action items, sequenced>
```

If `focus area = il-only` or `pitching` or `hitting`, suppress the
irrelevant sections rather than emit empty ones.

---

## Anti-patterns this skill exists to prevent

If at any point you find yourself:
- Computing IL slot count from `injured` instead of `lineup_slot=='IL'`
  → re-read `memory/feedback_il_slot_vs_il_status.md`, restart Step 2
- Ranking RPs using xfp_rp3 instead of xfp_rprs2 → re-read
  `memory/feedback_team_value_reads_must_be_cap_role_elig_aware.md`
- Surfacing a player on another team's roster as a "pickup" → re-read
  `memory/feedback_best_available_means_FA_only.md` — those must come
  from `get_free_agents()` only
- Recommending more than ~5 moves at once → trim to the most leveraged 5;
  longer lists never get acted on
- Quoting save totals out of context (e.g., recommending a temp-closer
  pickup over the actual closer-of-record) → re-read
  `memory/feedback_save_handcuffs_needs_closer_context.md`
- Using projections > 2 days stale without warning the user → check
  mtimes in Step 5 and surface the warning

---

## When to run this skill

- Weekly at the start of a matchup (default scheduled cadence)
- After any IL transaction notification
- Before any drop/add decision the user is hesitating on
- When the user asks "who should I drop" / "what's my situation" /
  "do I have room for X"

Each run is independent — no state to carry forward. The output IS the
artifact.
