---
name: daily-edge
description: Game-day-morning meta-skill (before lineup lock) that chains roster-verify → pregame-check → streamer-precision-board into one report (3-step chain since the P1 streamer merge 2026-07-10 — the boom_stack shortlist is the board's own `--filter boom>=2`, not a separate step), pulling the roster + probables + FA pool ONCE and threading them through every step. Use every game-day morning (~before noon ET) to get the day's start/bench + streamer edge in a single pass. Engineering note: pattern-matches /monday-morning (pull-once contract). NO roster moves are executed — this produces the decision surface only.
---

# daily-edge

Runs the full game-day-morning decision workflow in one pass (SKILL_REGISTRY
section 3, bundle **daily-edge**):

1. **roster-verify** — confirm live roster membership before anything else
2. **pregame-check** — for each of my SPs starting today: START vs CAP-BENCH
   verdict (empirically validated v2 conservative rules) + opponent-SP scan
   flagging my hitters facing high boom_stack opp pitchers
3. **streamer-precision-board** — the precision MINE+FA streamer board for today,
   now carrying the boom_stack column; render the boom-shot shortlist via its
   `--filter boom>=2` view (the old stream-the-stack step, merged P1 2026-07-10)

For any specific player flagged in steps 2-3, optionally run
`/triangulate <name>` for the full 3-lens verdict before deciding.

The bundle exists because these steps are always run together on a game-day
morning but were previously separate invocations that each re-pulled the
roster, the day's probables, and the size=2000 FA pool.

---

## Shared data (pull ONCE, thread through all steps)

```python
from app.espn_connector import get_my_roster_with_injuries, get_free_agents
import pandas as pd

roster = get_my_roster_with_injuries()          # step 1 truth
fa_all = get_free_agents(size=2000)             # step 3 pool (never <2000)

rp3   = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')

# Probables for today+next-3d — pull once from the OWNER (item 9):
from plv_clone.mlb_stats import get_probables
from datetime import date, timedelta
today = date.today()
probables = get_probables(today.isoformat(), (today + timedelta(days=3)).isoformat())
```

Collision-safe lookups: resolve to MLBAM via
`plv_clone.utils.name_match.resolve_pitcher_id(name, team=..., role=...)` —
never a name-only `str.contains` (gotcha #10).

---

## Step 1 — roster-verify

Verify live roster membership. DO NOT use session context for "which players
are yours." See `/roster-verify`.

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()
my_names = set(_norm(r['player_name']) for _, r in roster.iterrows())
def my_tag(name): return '✓' if _norm(name) in my_names else ''
```

## Step 2 — pregame-check (condensed)

Run the `/pregame-check` protocol over `roster` + `probables`. Default START
every confirmed start UNLESS the period SP-start cap is at overflow risk AND the start
is the lowest-EV one, OR blend ≤7 + opp_bat ≥1.10 + Tier B NOISE/REGRESS.
Always START on SOFT opp_bat (<0.95). Also scan the opponent's confirmed SPs
and flag my hitters facing boom_stack ≥3 opp pitchers.

## Step 3 — streamer-precision-board (condensed)

Run `/streamer-precision-board` over the same `fa_all` + `probables`. Do NOT
re-pull the FA pool. The board's `stk` column carries boom_stack 0-4; present
the boom-shot shortlist from its `--filter boom>=2` view (this replaced the
separate stream-the-stack step in the P1 merge 2026-07-10 — same
confirmed-probables ∩ FA universe, Connelly-Early-verified, ⚠spike-anti and
DECLINE-RISK guards intact).

---

## Output format

```markdown
# Daily Edge — <date>

## My SPs today (START / CAP-BENCH)
<table: SP · opp · opp_bat · blend · verdict>

## My hitters facing tough opp SPs
<any hitter vs boom_stack ≥3 opp pitcher>

## Streamer edge (FA SPs, boom-tier filtered)
<time-sorted board, FA highlighted, decision-deadline header>

## Recommended (≤3, sequenced) — DECISION SURFACE ONLY
1. ...
```

---

## Anti-patterns this bundle exists to prevent

- Re-pulling roster / probables / FA pool between steps — pull once, thread through
- Running the streamer board before roster-verify — need my_tag first
- Benching a confirmed start on soft matchup (v1 aggressive-bench rules were REJECTED, n=13,716)
- Labeling a player "yours" from session context — always verify via Step 1

## When NOT to use

- Weekly cap planning → `/sp-week-plan` or `/monday-morning`
- Single-player deep dive → `/fa-pickup-deep-dive` or `/triangulate`
