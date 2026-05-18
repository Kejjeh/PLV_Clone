---
name: fa-pickup-deep-dive
description: Structured FA pickup analysis for a single player — pulls model projection (xfp_rh3/rp3/rprs2), recent Statcast pitch-shape or bat-tracking, ESPN injury status with return date, ownership %, and produces a PASS / CONSIDER / SKIP recommendation. Use whenever the user asks "should I pick up X", "deep dive on X", "what does the model say about X", or shows a screenshot of a single player.
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

Find the player's `percent_owned`. Translation to 8-team BrownU:
- < 50%: clearly available
- 50-80%: marginal — may already be rostered in 8-team
- 80%+: probably rostered; check `get_all_teams()` to confirm

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

### Verdict: **PASS / CONSIDER / SKIP** (with one-sentence reason)
```

---

## Anti-patterns this skill exists to prevent

- Quoting projection numbers without their prior/recent gap context
  (the gap IS the story for FAs)
- Citing xwoba_gap_to as a buy signal — degraded to no-op
  (see registry 2026-05-16 re-audit)
- Recommending an IL'd player without surfacing return_date
- Recommending someone who's actually on another team's roster
- Forgetting to compare to user's drop target — "is X good" is less
  useful than "is X better than what I'd drop for him"
- Using rh3 to rank an RP (use rprs2)

---

## When NOT to use this skill

- User wants to compare 2+ players head-to-head (use a different
  pattern: build a side-by-side comparison instead)
- User wants league-wide FA scan (use `/roster-audit` Step 7 instead)
- User wants a historical analog analysis (this is a different
  skill candidate: `/historical-analog` not yet built)
