---
name: fa-replacement-pool
description: Build a ranked FA replacement pool for a player being dropped. Pulls all hitters or pitchers above a season-FP threshold from ESPN, joins with our model (rh3/rp3/rprs2), computes Δ vs drop target, flags positional-flex match. Use whenever the user says "I'm dropping X, who do I pick up?", "find me a replacement for Y", or "show all FAs above N FP". Different from /fa-pickup-deep-dive (single-player deep-dive) — this is the BROAD scan.
---

# fa-replacement-pool

You are building a ranked replacement pool when the user has decided to
drop a specific player and wants to see all qualifying FA candidates
side-by-side with model context.

The skill exists because the obvious approach (`get_free_agents(position=X,
size=300)` per position) silently truncates — we missed Sheets, then
Cortes/Steer/Horwitz/García/Busch in one session before realizing the
per-position cap was the culprit. See
`feedback_fa_pool_size_cap.md` for the canonical fix.

---

## Inputs

If the user hasn't provided these, infer or ask:

1. **Drop target name** (required) — used as baseline for Δ comparison
   and positional-flex matching
2. **Bucket** (required) — `H` (hitters) / `SP` / `RP`. Infer from the
   drop target's primary position if not stated.
3. **Threshold** — minimum season FP to qualify. Default = 80 for
   hitters, 60 for SPs, 50 for RPs. The user often starts at 100 and
   asks to expand; default lower to surface adequate candidates first
   pass.
4. **Roster context** — "for my BrownU roster" (apply 8-team translation
   to ownership %) vs "in general"

---

## Step 1 — Establish the drop-target baseline

Pull the drop target's row from the relevant projection file:

| Bucket | File | Key cols |
|---|---|---|
| H | `data/outputs/xfp_rh3_projections.csv` | `xfp_rh3_per_game`, `expected_total_fp_remaining`, `signal`, `replacement_delta` |
| SP | `data/outputs/xfp_rp3_projections.csv` | `xfp_rp3_per_start`, `expected_total_fp_remaining`, `signal` |
| RP | `data/outputs/xfp_rprs2_projections.csv` | `xfp_ros`, `replacement_delta`, `signal` |

Also pull drop target's `eligible_slots` from
`get_my_roster_with_injuries()` — needed for positional-flex matching.

Surface drop-target baseline at top of output so the user can see what
"Δ vs Donovan" means.

---

## Step 2 — Pull the FA pool (CRITICAL: avoid the size cap trap)

**Always use a single unfiltered call:**

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)   # one call, then filter
```

**NEVER** use per-position calls like `get_free_agents(position='H',
size=300)` for "find all hitters above threshold" — the per-position
size cap silently drops candidates. The user explicitly flagged this
("you're missing hitters") in the session that prompted this skill.

Then filter to the bucket:

```python
hitter_positions = {'C','1B','2B','3B','SS','OF','LF','CF','RF','DH'}
sp_positions     = {'SP'}
rp_positions     = {'RP'}
```

For each FA in the bucket, capture:
- `player_name`, `player_id`, `position`, `eligibleSlots`
- `pro_team`, `total_points` (season), `projected_total_points`
- `percent_owned`, `injuryStatus`
- For hitters: `stats[0]['breakdown']` AB/R/HR/RBI/BB/K/SB/AVG

Filter by season FP ≥ threshold.

---

## Step 3 — Join with model projections

Name-normalize for joining (Iván Herrera, Luis García Jr., José Soriano —
accents WILL bite):

```python
import unicodedata
def norm(s):
    if not isinstance(s, str): return ''
    return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower().strip()
```

Disambiguate same-name players (two Max Muncys, two Will Smiths, etc.)
by `team` match first, then by `pa_to` max (the regular).

For hitters surface these joined cols:
- `rh3_rank`, `xfp_rh3_per_game`, `expected_total_fp_remaining`,
  `recency_form_gap`, `pa_last21`, `signal`, `replacement_delta`

Some FAs won't have a row in rh3 (insufficient PA). Don't drop them —
surface as "(insufficient PA in model)" with their ESPN season stats only.
These are often the recent callups (Angel Martínez was a great example
— PL had a glowing recap but rh3 didn't even have him in the file at
first; later he appeared at rank #121).

---

## Step 4 — Compute Δ vs drop target

For each candidate:
- `rh3_ros_delta = candidate_ros - drop_target_ros`
- `rh3_fpg_delta = candidate_fpg - drop_target_fpg`

Tier the table:
- **Meaningful upgrade:** rh3_ros_delta > +30 FP AND rh3_fpg_delta > 0
- **≈ baseline:** Δ within ±20 FP
- **Below baseline (skip):** Δ < −20 FP

---

## Step 5 — Position-flex match annotation

For each candidate, check what fraction of the drop target's eligible
slots they also cover. Direct positional matches matter — e.g., if
the drop target was a 2B/SS/IF guy and the candidate is also SS/2B/IF,
they slot in cleanly. If the candidate is OF-only, slot mismatch.

Annotate with one of:
- ✓ direct match (covers all drop target's IF/OF slots)
- ~ partial match (covers some)
- × mismatch (no overlap on drop target's slots — would need to bench
  someone else)

---

## Step 6 — Verify candidates are TRUE FAs (mandatory, not optional)

**This step is mandatory before recommending ANY candidate, regardless
of ownership %.** The Connelly Early bug (2026-05-18) showed why:

- PL Top 100 ranked Early at #42 T6 with a "discount Max Fried" comp
- I recommended him as a stash candidate from a PL article cross-reference
- He was actually rostered on team "Frendy's Fantastic Team" in the user's
  league — entirely unavailable as a FA
- The user had to flag the error

The lesson: **PL rank ≠ available in your league.** Same goes for "MC
top-N candidate" or any list pulled from external rankings — always
verify against `get_all_teams()` for the user's specific ESPN league.

```python
from app.espn_connector import get_all_teams
teams = get_all_teams()

# For any specifically-named candidate from outside (PL, user mention,
# trending article), explicitly check:
for name in named_candidates:
    on_roster = teams[teams['player_name'].str.contains(name, case=False, na=False)]
    if len(on_roster):
        rostering_team = on_roster.iloc[0]['team_name']
        print(f"⚠ {name} is on '{rostering_team}' — NOT AVAILABLE (trade only)")
```

For the bulk FA pool returned by `league.free_agents()`, ESPN's
classification is usually correct (these are genuinely available).
But for high-owned candidates (>50%) AND for any name imported from
external rankings, always cross-check rosters.

If a recommended candidate is actually on another roster, surface it
prominently:
> "**X is on [Team Y] — not available as FA, would require a trade**"

Then either suggest an alternative or pivot to discussing trade
possibility.

---

## Step 7 — Sort and present

Sort by `xfp_rh3_per_game` descending (or `xfp_rp3_per_start` /
`xfp_ros` for pitchers).

Output format:

```markdown
## FAs ≥<threshold> season FP — replacement candidates for <DropTarget>

(<DropTarget> baseline: <fpg> FP/g, <ros> RoS, signal=<signal>)

### Tier 1 — meaningful upgrade
| # | Player | Pos | Eligible | Sn FP | rh3 FP/g | RoS | Δ vs DropTarget | Recency | PA L21 | Owned | Signal | Flex |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Tier 2 — ≈ baseline
... same columns ...

### Tier 3 — skip
brief list only
```

Surface `pct_owned` honestly but DO NOT auto-exclude high-owned FAs —
the user has explicitly asked "ownership is not a concern" before,
and ESPN's "%owned" can be misleading in 8-team. Mention claim-risk
as commentary, not a filter.

---

## Step 8 — Auto-offer the natural next step

End the output with: "Want a deep-dive on the top N? (uses
`/fa-pickup-deep-dive` or `/hitter-compare`)"

The replacement-pool is the BROAD scan; the deep-dive is the FOCUSED
follow-on. Don't try to do both in one shot — the output gets
unreadable past ~10 candidates with full deep-dive details.

---

## Anti-patterns this skill exists to prevent

- **Per-position `size=300` truncation.** This is the central lesson.
  Single `size=2000` call, manual position filter. Always.
- Auto-excluding candidates because ownership > 50% — user often
  cares more about absolute upside than claim risk.
- Forgetting accent-normalization on name joins — Iván Herrera,
  José Soriano, Luis García Jr. will all fail naive string match.
- Same-name collisions (Max Muncy LAD vs Max Muncy ATH) — always
  disambiguate by team or by `pa_to` max.
- Treating "no rh3 row" as "skip" — recent callups are often the
  most interesting names (Angel Martínez, Logan Henderson, etc.).
  Surface them with ESPN stats only and a note.
- Recommending a "FA" who's actually on another roster. **Always run
  `get_all_teams()` check before recommending ANY externally-sourced
  candidate (PL article, podcast mention, trending name) — not just
  high-owned ones.** The Connelly Early bug (2026-05-18) was a low-owned
  player who happened to be rostered in the user's specific 8-team
  league. PL/MC rankings don't reflect your league's roster state.
- Doing full Statcast deep-dive on each candidate in this skill —
  that's `/fa-pickup-deep-dive` or `/hitter-compare`. Stay broad here.

---

## When NOT to use this skill

- User named a specific 1-3 players they're already considering →
  use `/fa-pickup-deep-dive` (single player) or `/hitter-compare`
  (multi-player head-to-head) instead.
- User wants a full league-wide audit → `/roster-audit` covers
  drop/add candidates as part of a broader sweep.
- User wants prospect / minor-league scouting → out of scope; this
  is FA-pool-only.
