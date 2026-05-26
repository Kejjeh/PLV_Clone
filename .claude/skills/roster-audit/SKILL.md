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

### Name-collision guard (mandatory for hitter projection lookups)

When building any `dict[name] → projection` lookup from the rh3 CSV,
you MUST account for same-name MLB players. The canonical example:

- **Max Muncy LAD** — 3B, batter_id 571970, rh3 ≈ 0.578 → hold
- **Max Muncy ATH** — C, batter_id 691777, rh3 ≈ 0.379 → drop candidate

A naive `_norm("Max Muncy")` key collision caused the wrong projection
to be applied and produced an incorrect drop recommendation. NEVER key
on normalized name alone.

**The fix — use one of these approaches:**

1. Key on `(normalized_name, pro_team)` tuple when iterating the rh3 CSV,
   then match against the ESPN row's `proTeam` field.
2. Use `resolve_batter_id(name, team=..., position=...)` from
   `plv_clone.utils.name_match`, which consults `KNOWN_COLLISIONS` and
   refuses to silently guess.

**Detection:** After building the name→projection dict, check for
duplicate normalized keys. If any exist, log a warning:
```
WARNING: duplicate rh3 key 'max muncy' — rows for LAD (571970) and ATH (691777).
Resolving by pro_team match against ESPN roster row.
```
Then prefer the row whose `pro_team` matches the ESPN roster player's
`proTeam`. If `pro_team` is missing or ambiguous, surface the collision
explicitly in the audit output rather than silently picking one.

Also applies to rp3 and rprs2 CSV lookups — same-name pitchers are rarer
but not impossible.

Reference: `memory/feedback_player_name_collisions.md`.

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

**For each hitter drop candidate: check xwOBACON year-over-year trajectory.**
A player at the bottom of the rh3 rankings may be there because of a variance
slump (xwOBACON stable, outcomes not landing → HOLD for bounce) or genuine
structural decline (xwOBACON declining each year → DROP confirmed). Surface
as a one-liner per candidate:

```python
# Quick YoY xwOBACON check for each hitter drop candidate
for yr in [2023, 2024, 2025, 2026]:
    xwobacon_by_yr[yr] = con.execute(f"""
    SELECT AVG(estimated_woba_using_speedangle)
    FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
    WHERE batter=? AND events IS NOT NULL AND events != '' AND launch_speed IS NOT NULL
    """, [batter_id]).fetchone()[0]
trend = 'DECLINING' if all(xwobacon_by_yr[y]>xwobacon_by_yr[y+1] for y in [2023,2024,2025] if xwobacon_by_yr.get(y) and xwobacon_by_yr.get(y+1)) else 'STABLE/OTHER'
```

Output per hitter candidate: `xwOBACON: 2023: 0.XXX | 2024: 0.XXX | 2025: 0.XXX | 2026: 0.XXX → DECLINING (confirmed drop) / STABLE (check L21d before dropping)`

Do NOT recommend dropping a hitter in confirmed variance-slump (xwOBACON stable, xwOBA down, process intact) when a better FA option exists at the same position. The rh3 model's RoS projection will already start recovering; dropping at the trough locks in the loss.

---

## Step 7 — FA add candidates (filter to FREE AGENTS ONLY)

Critical rule (`memory/feedback_best_available_means_FA_only.md`):
**"best available" means FREE AGENTS only**, not players on other teams'
rosters.

### Pull all three FA buckets from a single unfiltered call

Always use the `size=2000` unfiltered pattern — per-position calls with
`size=300` silently drop low-owned high-FP candidates (see
`memory/feedback_fa_pool_size_cap.md`):

```python
from app.espn_connector import get_free_agents
import unicodedata

fa_all = get_free_agents(size=2000)   # unfiltered; split by position below

fa_hitters = fa_all[fa_all['position'].isin(['C','1B','2B','3B','SS','OF','DH','MI','CI'])]
fa_sp      = fa_all[fa_all['position'] == 'SP']
fa_rp      = fa_all[fa_all['position'] == 'RP']
```

Cross-reference each bucket to the **correct** model:
- Hitters → **rh3** (`xfp_rh3_projections.csv`)
- Starting pitchers → **rp3** (`xfp_rp3_projections.csv`)
- Relief pitchers → **rprs2** (`xfp_rprs2_projections.csv`) — NOT rp3

### Accent normalization for SP name matching

SP names in the rp3 CSV use "Last, First" format with accented characters
(e.g., `"Luzardo, Jesús"`). ESPN roster uses `"Jesus Luzardo"`. Build
**both** key formats AND strip accents so all players resolve:

```python
def _strip_accents(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')

def _norm(s):
    return _strip_accents(s).lower().strip()

# Build lookup from rp3 CSV with both "First Last" and "Last, First" keys
rp3_lookup = {}
for _, row in rp3.iterrows():
    raw = row['player_name']  # may be "Last, First" or "First Last"
    if ',' in raw:
        last, first = [x.strip() for x in raw.split(',', 1)]
        key_a = _norm(f"{first} {last}")
        key_b = _norm(raw)
    else:
        key_a = _norm(raw)
        key_b = key_a
    for k in (key_a, key_b):
        rp3_lookup[k] = row
```

Apply the same accent-stripping when normalizing ESPN FA player names
before the merge. Without this, players like Jesús Luzardo, José Berríos,
and Framber Valdez will fail to match and appear as "unmatched."

### Output three sub-tables

**FA hitters — top 15**

| Player | Pos | %Own | rh3 proj | Slot fit | Injury |
|---|---|---|---|---|---|
| ... | ... | ... | ... | eligible_slots ∩ open_slots | DTD / IL15 / IL60 / — |

**FA starting pitchers — top 10** (flag injured/IL explicitly)

| Player | %Own | rp3 proj | Next start | Injury |
|---|---|---|---|---|
| ... | ... | ... | vs OPP (day) | **IL60** / DTD / — |

Many high-projection FA SPs will be on IL60. Flag their injury status
prominently — a player on IL60 is NOT immediately available and should
only appear in the "IL stash" section if the user has an open IL slot.
Do not present them as normal pickup candidates.

#### Recency outlier alert (model-lagging candidates)

After surfacing the top-10 FA SPs by rp3 projection, run a secondary scan:

```python
# Flag FA SPs where recent form significantly exceeds model projection
# Criteria: gs_to >= 10, recency_form_gap > 2.5, fp_per_start_last21 not null
outliers = rp3_fa[
    (rp3_fa['gs_to'] >= 10) &
    (rp3_fa['recency_form_gap'] > 2.5) &
    (rp3_fa['fp_per_start_last21'].notna())
].sort_values('recency_form_gap', ascending=False)
```

Surface as: `⚠ RECENCY OUTLIER: {name} — rank #{rank}, xfp {xfp:.1f}/start, L21d {l21d:.1f}/start, gap +{gap:.1f}`

**Why 10 GS threshold:** K% stabilizes at ~70 TBF (~5-6 GS); by 10 GS the season carries 67% weight in the prior blend and K% signal is fully credible. Below 10 GS the L21d gap can reflect a single dominant outing, not a skill shift.

**Why this exists:** On 2026-05-25, Max Meyer (rank #65, xfp=10.58) averaged 17.0 FP/start in L21d with a +3.1 gap but was invisible to the main FA scan because he was below the replacement threshold (rank 45). Career form: PEAK/PEAK (k_pct 90th, velo 93.5th percentile). Someone else picked him up. This alert would have surfaced him.

**FA relief pitchers — top 10**

| Player | %Own | rprs2 proj | Role | Injury |
|---|---|---|---|---|
| ... | ... | ... | Closer / Setup / MR | — |

### Additional FA section rules

- Filter out `percent_owned > 95` if you're being conservative (usually
  scooped before claims process in 8-team).
- For each candidate surface: slot fit (which of your open eligible_slots
  this player fills), projection rank, and injury status.
- Pollack tier if data available (cross-reference his Top-150 hitters or
  SP Roundup if recent PDF/scrape is in scope).
- If the user has IL slots open OR a returning player who will free one,
  include a separate **IL stash candidates** sub-table of IL60/IL15 FAs
  with high projections — clearly labeled as deferred-value pickups.

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
- Building a `dict[name] → projection` lookup keyed on normalized name
  alone → same-name players (canonical: Max Muncy LAD 571970 vs ATH
  691777) will silently clobber each other and produce the wrong
  projection for a drop/hold decision. **Mandatory fix — use this exact
  pattern for every rh3 lookup in this skill:**

  ```python
  rh3_idx = {}
  dup_keys = set()
  for _, row in rh3.iterrows():
      key = (_norm(str(row['player_name'])), str(row.get('team', '')).upper())
      if key in rh3_idx:
          dup_keys.add(key)
      rh3_idx[key] = row
  if dup_keys:
      print(f"WARNING: duplicate rh3 keys {dup_keys}")
  def rh3_row(espn_row): return rh3_idx.get((_norm(espn_row['player_name']), str(espn_row.get('pro_team','')).upper()))
  ```

  Reference: `memory/feedback_player_name_collisions.md`
- Failing to strip accents when matching SP names between rp3 CSV and
  ESPN FA pool → players like "Jesús Luzardo" vs "Jesus Luzardo" will
  appear as unmatched and be silently excluded from the SP FA table.
  Always apply `unicodedata.normalize('NFKD', name).encode('ascii',
  'ignore').decode('ascii')` to both sides of the merge, and build both
  "Last, First" and "First Last" key formats for the rp3 lookup
- Ignoring recency_form_gap outliers below the replacement threshold — the model
  intentionally excludes L21d as a feature (failed +0.005r gate); below-replacement
  pitchers with large positive gaps are "model-lagging" candidates that need manual
  review. Run the recency outlier scan every week.
- Dropping a hitter on rh3 rank alone without checking xwOBACON trajectory.
  The Turner pattern (2026-05-25): 0.285 rolling xwOBA looks identical to prior
  troughs that fully recovered — but xwOBACON declining each year (0.415 → 0.330)
  means the recovery ceiling is lower. Without the trajectory check, the drop call
  requires full `/slump-or-decline` to confirm; with it, you can often make the
  call faster in the audit context. Always surface xwOBACON 3-year trend for
  bottom-3 hitters before recommending drop.

---

## When to run this skill

- Weekly at the start of a matchup (default scheduled cadence)
- After any IL transaction notification
- Before any drop/add decision the user is hesitating on
- When the user asks "who should I drop" / "what's my situation" /
  "do I have room for X"

Each run is independent — no state to carry forward. The output IS the
artifact.
