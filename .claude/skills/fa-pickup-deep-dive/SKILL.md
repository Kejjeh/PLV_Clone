---
name: fa-pickup-deep-dive
description: Structured FA pickup analysis for a single player — pulls model projection (xfp_rh3/rp3/rprs2), recent Statcast pitch-shape or bat-tracking, ESPN injury status with return date, ownership %, an archetype layer (label + sub-types + T+1/T+2 + top-5 historical comps with comp-density and trajectory adjustments; for RPs, leverage_tier + CLOSER + FIREMAN role tags), and produces a PASS / CONSIDER / SKIP recommendation. Use whenever the user asks "should I pick up X", "deep dive on X", "what does the model say about X", or shows a screenshot of a single player.
---

# fa-pickup-deep-dive

You are producing a single-player pickup writeup using the same
structured format every time. The skill exists because we did this
manually 4-5 times in one session (Henderson, Webb, Bleday, Sheehan)
and the format was always the same: model says X, recent shape says
Y, injury context Z, ownership W, recommendation.

The user's job is to name the player. Your job is to fetch all four
data streams and produce the writeup.

---

## Inputs

1. **Player name** (required) — fuzzy-match against the relevant
   projection file
2. **Position bucket** (optional) — `H` / `SP` / `RP`. If not given,
   infer from `position` field in ESPN roster/FA pool.
3. **Owner context** (optional) — "for my roster" (compares to your
   weakest at that bucket) vs "in general" (no comparison)

---

## Step 1 — Identify the player

Try in order:
1. `app.espn_connector.get_free_agents()` and check ownership
2. `app.espn_connector.get_all_teams()` to see if rostered
3. Projection files (`xfp_*_projections.csv`) for fuzzy match

If multiple matches (e.g., two players with same surname), surface
all candidates and ask user to pick.

**Same-name collision guard (mandatory):** Build the rh3 lookup keyed
on `(norm_name, pro_team)` tuple, never bare name. Canonical failure:
Max Muncy LAD (3B, 571970, rh3=0.578 — hold) vs Max Muncy ATH (C,
691777, rh3=0.379 — drop candidate) — identical `_norm()` keys, opposite
verdicts. A 2026-05-25 roster audit assigned the wrong projection.

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rh3_idx = {}
dup_keys = set()
for _, row in rh3.iterrows():
    key = (_norm(row['player_name']), str(row.get('team', '')).upper())
    if key in rh3_idx:
        dup_keys.add(key)
    rh3_idx[key] = row
if dup_keys:
    print(f"WARNING: duplicate rh3 keys {dup_keys} — resolve by team")
def rh3_row(name, team): return rh3_idx.get((_norm(name), str(team).upper()))
```

Use `pro_team` from the ESPN row. If absent, call `resolve_batter_id()`
from `plv_clone.utils.name_match`. See `/player-id-resolve`.

If no match anywhere: tell user, suggest a search alternative
(MLB Stats API athlete search).

Determine position bucket from:
- ESPN `position` field if rostered
- Player position from projection file
- Default fallback: if name has any pitching column populated, treat
  as P; else H

---

## Step 2 — Pull model projection

| Bucket | File | Projection col | Key context cols |
|---|---|---|---|
| Hitter | `data/outputs/xfp_rh3_projections.csv` | `xfp_rh3_per_pa` | `prior_fp_per_pa`, `pa_to`, `recency_form_gap`, `signal`, `rank` |
| SP | `data/outputs/xfp_rp3_projections.csv` | `xfp_rp3_per_start` | `prior_fp_per_start`, `gs_to`, `gs_last21`, `fp_per_start_last21`, `recency_form_gap`, `signal`, `rank` |
| RP | `data/outputs/xfp_rprs2_projections.csv` | `xfp_ros` | `role_lag1`, `sv_lag1`, `hld_lag1`, `gf_pct_to`, `replacement_delta`, `signal`, `rank` |

Surface BOTH the recent rolling projection AND the prior/historical
projection. The gap between them is the story:
- Recent ≪ prior → injury or temporary slump; possible buy
- Recent ≈ prior → stable performer
- Recent ≫ prior → hot start; likely regression candidate (sell-high?)

Apply Rule: don't quote any feature whose validation lift has
degraded (see `reference_validated_signals_registry.md`). For example,
`xwoba_gap_to` should not be cited as a buy signal — its marginal
lift is now ~0.

---

## Step 3 — Pull recent Statcast (last 3-5 outings)

For SP / RP — query last 3-5 starts/appearances:
```python
import duckdb
con = duckdb.connect()
df = con.execute(\"\"\"
SELECT game_date, pitch_type, release_speed, release_spin_rate,
       pfx_x, pfx_z, release_extension, description, events
FROM read_parquet('data/research/xfp_cache/statcast_2026.parquet')
WHERE player_name = '<Last, First>' AND game_date >= <date>
\"\"\").df()
```

Surface per-game:
- Pitch count, SwStr%, CSW%
- Velocity trend (last 3-5 starts)
- Whiff/swing per pitch type
- Note any meaningful velo drop (>1 mph from career) or shape change

For HITTER — query last 5-10 games:
- xwOBA per PA recent vs season
- HR/PA, barrel%, EV90 recent vs season
- Bat tracking metrics if available (bat_speed, swing_length,
  attack_angle) — but apply Rule 5 (sample-size honesty), only
  surface if N ≥ 30 swings recent
- **xwOBACON year-over-year trajectory** (mandatory for any FA pickup
  or drop target where the user is weighing recent performance against
  historical norms):

```python
for yr in [2022, 2023, 2024, 2025, 2026]:
    con.execute(f"""
    SELECT COUNT(*) bb, AVG(estimated_woba_using_speedangle) xwobacon
    FROM read_parquet('data/research/xfp_cache/statcast_{yr}.parquet')
    WHERE batter=? AND events IS NOT NULL AND events != ''
      AND launch_speed IS NOT NULL
    """, [batter_id]).df()
```

Display as a one-line table: `xwOBACON: 2022: 0.XXX | 2023: 0.XXX | 2024: 0.XXX | 2025: 0.XXX | 2026: 0.XXX → RISING/STABLE/DECLINING`

This answers: **is the model's history-weighted projection anchored on a rising, stable, or falling contact quality platform?** A declining trajectory means the model may be over-projecting based on prior seasons that are no longer representative. A rising trajectory means the model may be under-projecting.

---

## Step 4 — ESPN injury status

For any player with `injured: True`, fetch structured details:
```python
from app.espn_connector import get_injury_details
inj = get_injury_details([player_id])
```

Surface: injury_type, injury_detail, injury_side, return_date,
days_until_return, short_comment. If return_date is > 30 days,
explicitly flag that an IL stash is multi-week and may compete
with other IL slot uses.

---

## Step 5 — Ownership context

**Always pull from a single unfiltered call. Do NOT use the per-position
`get_free_agents(position=X, size=300)` pattern — it silently truncates
the pool and will miss the player you're looking for.** See
`feedback_fa_pool_size_cap.md` for the canonical fix.

```python
from app.espn_connector import _get_league
league = _get_league()
fas = league.free_agents(size=2000)   # one unfiltered call
# Then find your target by name (normalize accents — see Step 1)
```

Find the player's `percent_owned`. **NEVER conclude a player is rostered
from percent_owned alone — always verify via `get_all_teams()`.** In an
8-team league, a player at 60-70% nationally owned is routinely
unclaimed. This was confirmed 2026-05-25: Emmett Sheehan showed 60.7%
owned and the analysis incorrectly concluded "almost certainly rostered"
without calling `get_all_teams()` — he was a FA.

```python
# MANDATORY: always verify actual roster status
league = _get_league()
for team in league.teams:
    for player in team.roster:
        if _norm(player.name) == _norm(target_name):
            print(f"ROSTERED on {team.team_name} — cannot pick up")
            break
else:
    print("Confirmed FA — available to add")
```

Ownership % as a **rough prior only** (not a conclusion):
- < 30%: almost certainly FA in 8-team
- 30-70%: unknown — must verify via `get_all_teams()`
- 70%+: likely rostered but still verify — do not assume

If they're on another team's roster, surface that — picking up isn't
possible without a trade.

If you're scanning the whole FA pool above a threshold (not just one
player), use `/fa-replacement-pool` instead — that's the right skill
for "show me all FAs above N FP." This skill (`/fa-pickup-deep-dive`)
is for a single named player.

---

## Step 6 — Compare to user's roster (if "for my roster" context)

Pull `get_my_roster()` and find the user's weakest at the same bucket
(lowest xfp projection). Drop-add math:
- New player's projection − weakest current player's projection
  = expected weekly FP gain
- If gain > 5 FP/week → meaningful upgrade
- If gain < 2 FP/week → cosmetic; not worth the transaction
- Also surface: positional flex of the candidate vs the drop target
  (the rh3 projection misses positional flex value)

---

## Step 7 — Pitcher List cross-check (cached PDF OR WebFetch)

Try in order:

1. **Cached PDF** — if a recent Pitcher List PDF is in scope (user
   pasted in this session or recently saved to
   `data/reference/pitcher_list/`), use it.

2. **WebFetch fallback** — if no PDF, delegate to `/pl-cross-reference`
   OR run a single WebFetch on the current week's Top 150 hitters /
   Top 100 starting pitchers article. The PL URL pattern is:
   - Hitters: `https://pitcherlist.com/top-150-hitters-for-fantasy-baseball-2026-week-<N>/`
   - SPs: `https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-<MM-DD>-week-<N>-rankings/`
   - Per-player profile: `https://pitcherlist.com/player/<slug>/`

   WebSearch first (allowed_domains=`['pitcherlist.com']`) to find the
   latest week number. Don't guess.

Use as a sanity check on the model verdict, NOT as a tie-breaker — PL
is rate-stat-driven (12-team mindset) while our model is BrownU-points-
driven (8-team). Common divergence patterns and how to interpret them
are documented in `/pl-cross-reference`.

If the WebFetch dance feels heavy for a single player, just call out
the PL rank if you happen to know it from recent context — don't burn
multiple tool calls on a single-player deep-dive when the model
verdict is already clear.

---

## Step 7.5 — Archetype layer (supplementary)

The model (rh3/rp3/rprs2) is still the **primary** verdict driver. The
archetype layer adds character/comp/forward-trajectory color. It is
process-based, complementary to rh3/rp3/rprs2 (outcome-based).

Read the relevant current-year row from the master CSV:

| Bucket | File | Key cols |
|---|---|---|
| Hitter | `data/research/hitter_ratings_master.csv` | `archetype`, `contact_subtype`, `power_subtype`, `discipline_subtype`, `sb_tier`, `CONTACT`, `POWER`, `DISCIPLINE`, `SB`, `age_tier`, `boundary_tier`, `t1_fp_projection`, `fp_per_pa` |
| SP | `data/research/sp_ratings_master.csv` | `archetype`, `stuff_subtype`, `velo_tier`, `pitch_archetype`, `primary_group`, `STUFF`, `MOVEMENT`, `CONTROL`, `velo_rating`, `SWING_MISS`, `CALLED_STRIKE`, `DAMAGE_SUPP`, `GB_TENDENCY`, `WALK_AVOID`, `age_tier`, `boundary_tier`, `t1_fp_projection`, `t2_fp_projection`, `fp_per_start` |
| RP | `data/research/rp_ratings_master.csv` | `archetype`, `stuff_subtype`, `STUFF`, `CONTROL`, `BATTED_BALL`, `VELO` (rating), `SWING_MISS`, `CALLED_STRIKE`, `WALK_AVOID`, `GB_TENDENCY`, `BULK_IP`, `age_tier`, `boundary_tier`, `CLOSER`, `leverage_tier`, `HIGH_LEVERAGE`, `MULTI_INNING_BULK`, `FIREMAN` (may be absent — gracefully handle), `gmli`, `t1_fp_projection`, `t2_fp_projection`, `fp_per_g` |

If the player has no current-year row in the master (rookie, low PA/IP),
note that and skip this section.

### Top 3-5 historical comps

Filter the master CSV to age within ±3 of the target's `age`, then take
the 3-5 nearest neighbors by Euclidean distance in the rating space:

- **Hitter**: distance over `(CONTACT, POWER, DISCIPLINE)` — SB rated and shown but **excluded from distance** (matches `/hitter-archetype`).
- **SP**: distance over `(SWING_MISS, CALLED_STRIKE, DAMAGE_SUPP, GB_TENDENCY, WALK_AVOID, velo_rating)`.
- **RP**: distance over `(SWING_MISS, CALLED_STRIKE, WALK_AVOID, VELO, GB_TENDENCY, BULK_IP)`.

For each comp, pull the next-year row (`year+1`) keyed on the comp's
`batter`/`pitcher` ID to surface the T+1 actual outcome (and T+2 for
SP/RP). Report:

- Hitter: `<year> <name> — archetype@T → archetype@T+1` plus `fp_per_pa T → fp_per_pa T+1`
- SP / RP: `<year> <name> — archetype@T → @T+1 → @T+2` plus `fp_per_start T → T+1 → T+2` (or `fp_per_g` for RP)

If a comp has no T+1 row (career ended / injury year), mark as `NO_T+1`.

### Output block

```markdown
## Archetype layer
- **Archetype:** <LABEL> (Contact <C>, Power <P>, Discipline <D>[, SB <S>])
- **Sub-types:** <contact_subtype>, <power_subtype>, <discipline_subtype>[, <sb_tier>]
- **Boundary tier:** <SOLID | NEAR_EDGE | EDGE> (clearly inside / borderline)
- **Age tier:** <PRE_PEAK | PEAK | POST_PEAK> (<age>)
- **T+1 projection:** <X.XXX> <FP/PA or FP/start> (vs current <Y.YYY>)
- **T+2 projection (SP/RP only):** <Z.ZZZ>
- **RP-only tags:** CLOSER=<bool>, leverage_tier=<ELITE/HIGH/MID/LOW/GARBAGE>, HIGH_LEVERAGE=<bool>, MULTI_INNING_BULK=<bool>, FIREMAN=<bool|n/a>, gmLI=<X.XX>
- **Closest 5 historical comps** (age ±3, Euclidean over rating sub-domains):
  1. <year> <name> — <arch@T> → <arch@T+1> [→ <arch@T+2>] | <fp@T> → <fp@T+1> [→ <fp@T+2>]
  2. ...
- **Comp verdict:** <K>/<N> sustained-or-improved at T+1 → SUPPORTS_<CONSIDER|SKIP|NEUTRAL>
- **Archetype trajectory:** <UPGRADE | STABLE | DOWNGRADE> vs prior year
```

> Caveat for RPs: rprs2 R² ≈ 0.246 and `t1_fp_projection` from the RP
> master is **directional only**, not a precise forecast. Use it for
> sign, not magnitude.

If the player's archetype looks edge-case (`boundary_tier == NEAR_EDGE`
or `EDGE`) OR the comp distribution is wide, suggest the user run
`/hitter-archetype profile <name>` or `/sp-archetype profile <name>` or
`/rp-archetype profile <name>` for the full archetype deep-dive.

---

## Step 8 — Produce the writeup

Format:

```markdown
## <Player Name> deep dive (as of <date>)

### Model says (<bucket>):
- Recent rolling proj: **<X.XX> <FP/PA or FP/start>** (rank #<N>)
- Historical/prior:    <Y.YY>  (recency_form_gap: <±Z>)
- Signal: <hold / strong add / pass>
- Read: <one sentence interpretation of the gap>

### Recent shape (Statcast, last <N> outings):
- <key metric trend>: <values>
- <notable velo/whiff/bat-tracking observation>

### Injury status: <ACTIVE | IL10/IL15/IL60 with return date>
- <short_comment if injured>

### Availability:
- Owned <X.X>% (8-team translation: <FA-friendly | borderline | rostered>)
- If rostered: which team

### Vs your roster (if applicable):
- Weakest current <bucket>: <player> (<proj>)
- Net weekly FP gain if swap: <±N>
- Positional flex: <note>

### Archetype layer:
- Archetype: <LABEL> (<C/P/D or S/M/C ratings>), boundary <tier>, age tier <tier>
- T+1: <X.XXX> (and T+2 if SP/RP)
- RP-only: CLOSER/leverage_tier/FIREMAN tags
- Comps (3-5): <one-line summary of T+1 outcome distribution>
- Comp verdict: SUPPORTS_<CONSIDER|SKIP|NEUTRAL>

### Verdict: **PASS / CONSIDER / SKIP** (with one-sentence reason)
- Primary driver: <rh3/rp3/rprs2 signal>
- Archetype adjustment: <bumped toward X because Y, or "no adjustment">
```

### Verdict adjustment rules (archetype layer)

The model verdict is the anchor. Apply at most one archetype bump
(don't double-count):

1. **Comp-density rule.** Define "meaningfully" as ≥ 10% relative change
   in fp_per_pa (hitter), fp_per_start (SP), or fp_per_g (RP).
   - If ≥ 4 of 5 comps had T+1 outcomes meaningfully BELOW their T-year
     level → bump verdict one step toward SKIP.
   - If ≥ 4 of 5 comps had T+1 outcomes meaningfully ABOVE T-year level
     → bump verdict one step toward CONSIDER, even if rh3/rp3 is
     lukewarm.
   - Otherwise neutral.

2. **Archetype-trajectory rule.** Compare current-year archetype to the
   prior-year row (same player) if present:
   - DOWNGRADE (e.g. ELITE → POWER_EYE, or SP STUFF tier drop): bump
     toward SKIP **unless** rh3/rp3 is strongly positive (recency_form_gap
     ≥ +1.0 FP/start or +0.020 FP/PA).
   - UPGRADE (e.g. POWER → ELITE): bump toward CONSIDER.
   - STABLE: no adjustment.

3. **RP role overlay** (RPs only; applies BEFORE generic rules):
   - `leverage_tier in {MID, LOW, GARBAGE}` → cap verdict at SKIP
     regardless of rprs2. They are not seeing save/hold opportunities,
     and rprs2 can't fix that.
   - `CLOSER == True AND leverage_tier in {ELITE_LEVERAGE, HIGH_LEVERAGE,
     ELITE, HIGH}` → real add; bump toward CONSIDER if model is even
     neutral.
   - `FIREMAN == True` (when column present) → flag as "wins in tight
     games" — informational, no automatic bump.

If the archetype layer would flip PASS → SKIP or SKIP → CONSIDER, say
so explicitly in the verdict line ("Model said CONSIDER, archetype
downgraded to SKIP because 4/5 comps declined at T+1").

---

## Anti-patterns this skill exists to prevent

- Quoting projection numbers without their prior/recent gap context
  (the gap IS the story for FAs)
- Citing xwoba_gap_to as a buy signal — degraded to no-op
  (see registry 2026-05-16 re-audit)
- Recommending an IL'd player without surfacing return_date
- Recommending someone who's actually on another team's roster
- **Inferring roster status from percent_owned** — "60% owned = probably rostered in 8-team"
  is WRONG. Always call `get_all_teams()` and check `team.roster` explicitly. The
  Sheehan error (2026-05-25): 60.7% owned → concluded "almost certainly rostered" →
  he was a FA. percent_owned is national ESPN data across all league sizes; it is
  not a reliable proxy for 8-team roster status.
- Forgetting to compare to user's drop target — "is X good" is less
  useful than "is X better than what I'd drop for him"
- Using rh3 to rank an RP (use rprs2)
- Resolving a named player to the wrong rh3/rp3 row because of a
  same-name collision. Always check for duplicate `_norm()` keys when
  Step 1 matches a player. See `/player-id-resolve`.

---

## When NOT to use this skill

- User wants to compare 2+ players head-to-head (use a different
  pattern: build a side-by-side comparison instead)
- User wants league-wide FA scan (use `/roster-audit` Step 7 instead)
- User wants a historical analog analysis (this is a different
  skill candidate: `/historical-analog` not yet built)
