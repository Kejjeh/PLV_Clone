---
name: monday-morning
description: Meta-skill that chains roster-verify → roster-audit (full) → roster-health → sp-week-plan → fa-monitor → conviction-scan into a single Monday workflow. Replaces 4-6 separate invocations with one unified report. Use every Monday before lineups lock or after any significant IL transaction.
---

# monday-morning

Runs the full Monday decision workflow in one pass:

1. **roster-verify** — confirm live roster membership before anything else
2. **roster-audit** — slot occupancy, IL returns, SP cap math, drop candidates, FA adds
3. **roster-health** — signal-driven alerts (TRENDING_DOWN, ARCHETYPE_DOWNGRADE, COLD_BABIP, etc.) layered on top of the slot/cap view from step 2
4. **sp-week-plan** — project this week's starts against the 10-cap, rank, bench recommendation
5. **fa-monitor** — pull HIGH-priority alerts from all signals
6. **conviction-scan** — league-wide model-vs-process divergence watch (buy-low / sell-high conviction; Rule 13 context only)

For any specific player flagged in steps 2-5, optionally run `/triangulate <name>` to get the full 3-lens verdict + confidence + watch-list before making the move.

The skill exists because these four are always run together on Mondays but
were previously 4 separate invocations with manual data handoff between them
(e.g., re-pulling the roster between roster-audit and sp-week-plan).

---

## Shared data (pull ONCE, pass through all steps)

```python
from app.espn_connector import get_my_roster_with_injuries, get_free_agents
import pandas as pd

# Pull once — reused by all steps
roster = get_my_roster_with_injuries()
fa_all = get_free_agents(size=2000)

# Projection files — check mtime; warn if > 2 days old
rh3   = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rp3   = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rprs2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
```

Collision-safe rh3 lookup (always use this pattern):

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

rh3_idx = {}
dup_keys = set()
for _, row in rh3.iterrows():
    key = (_norm(row['player_name']), str(row.get('team', '')).upper())
    if key in rh3_idx: dup_keys.add(key)
    rh3_idx[key] = row
if dup_keys: print(f"WARNING: duplicate rh3 keys {dup_keys}")
def rh3_row(name, team): return rh3_idx.get((_norm(name), str(team).upper()))
```

---

## Step 1 — roster-verify

Before anything: verify live roster membership. DO NOT use session context
for "which players are yours." See `/roster-verify` for full protocol.

```python
my_names = set(_norm(r['player_name']) for _, r in roster.iterrows())
def my_tag(name): return '✓' if _norm(name) in my_names else ''
```

---

## Step 2 — roster-audit (condensed)

Run the full `/roster-audit` protocol using the shared `roster` object.
Key outputs to extract and carry forward:

```python
# IL slot occupancy (from lineup_slot, NOT injured flag)
il_used  = (roster['lineup_slot'] == 'IL').sum()
be_used  = (roster['lineup_slot'] == 'BE').sum()

# Injured not in IL slot — cleanup opportunities
injured_not_il = roster[(roster['injured']==True) & (roster['lineup_slot']!='IL')]

# SP cap math — role + cap from the OWNERS (gotcha #8 + audit 2026-07-04):
# raw position=='SP' misses dual-eligible starters (Detmers), and hand-typed
# 1.19/10 forked the cap math.
from scripts.xfp.lib.pitcher_role import detect_pitcher_role
from plv_clone.cap_math import SP_CAP, projected_starts, gap_to_cap as cap_gap
pitchers = roster[roster['eligible_slots'].apply(
    lambda sl: any(p in str(sl) for p in ('SP', 'RP', 'P')))].copy()
pitchers['role'] = pitchers.apply(detect_pitcher_role, axis=1)
sps = pitchers[pitchers['role'] == 'SP']
sps_healthy = sps[(sps['lineup_slot'] != 'IL') & (~sps['injured'].fillna(False))]
n_healthy_sp = len(sps_healthy)
proj_starts  = projected_starts(n_healthy_sp)
gap_to_cap   = cap_gap(n_healthy_sp)

# IL returns sorted by days
il_returns = roster[roster['injured']==True].sort_values('days_until_return')
```

Pass `n_healthy_sp`, `proj_starts`, `il_returns` to Steps 3 and 4.

---

## Step 3 — sp-week-plan (condensed)

Using `sps_healthy` from Step 2, run the start projection:

- Pull confirmed probables from MLB Stats API for current week
- For each SP not confirmed: infer from rotation gap (see `/sp-week-plan` Step 3)
- Rank starts by matchup + recent form
- Flag bench candidate (weakest 1-start)

**Forward-looking forced-drop date** (carry from roster-audit):

```python
il_sps = il_returns[il_returns.apply(detect_pitcher_role, axis=1) == 'SP']
for _, r in il_sps.iterrows():
    projected = projected_starts(n_healthy_sp + 1)
    if projected >= SP_CAP:
        print(f"FORCED DROP DEADLINE: {r['return_date']} — {r['player_name']} activates → {n_healthy_sp+1} SPs → {projected:.1f}/wk")
        break
```

---

## Step 4 — fa-monitor (condensed)

Using `fa_all` and `rh3_idx` from shared data, run all 6 signals.
**Surface only HIGH-priority alerts.** MONITOR-tier alerts go in a collapsed
section at the bottom. See `/fa-monitor` for full signal definitions.

Key signals:
- **Signal A** (SP breakout): fpp >= 0.02 AND whiff >= 26%, GS 4-8, rp3_rank <= 150 → HIGH
- **Signal H** (SP upgrade): FA SP fpp >= 3rd-weakest active SP + 0.030 → HIGH
- **Signal I** (hitter upgrade): xwOBA_L21d >= floor + 0.025 AND xwOBACON >= 0.350 AND rh3_rank <= 150 AND PA >= 50 → HIGH

---

## Step 5 — conviction-scan (Conviction watch)

Run the league-wide model-vs-process divergence board once, then surface the
top disagreements as a watch list. Buy-low = the rating (validated pillar: SP
STUFF / hitter CONTACT) is well above the model; sell-high = the reverse.

```python
# Engine: scripts/xfp/run_conviction_scan.py — prints MINE/FA/opp tagged board
python scripts/xfp/run_conviction_scan.py --top 8
```

**Rule 13:** divergence NEVER moves rh3/rp3 and never re-ranks — it sets
conviction and routes to `/triangulate`. Hitter buy-low was REJECTED as an
additive signal (−0.069 FP/PA) — treat the hitter flavor as CONTEXT ONLY.

---

## Output format

```markdown
# Monday Morning — <date>

## Slot occupancy
IL: X/3  |  Bench: Y/4  |  Active: Z/22
Cleanup: <injured-not-IL list>

## SP cap
N healthy SPs → P starts/wk vs 10 cap (G gap)
⚠ Forced drop deadline: <date> (<player> activates → over cap)
Pre-identified cut: <weakest SP by rp3>

## This week's starts
<projected starts table, bench call>

## IL returns
<return timeline table — next 30 days>

## Drop candidates
<bottom-3 hitter / SP / RP by model>

## FA alerts (HIGH only)
### Signal A (SP breakout)
<table>
### Signal H (SP upgrade)
<table>
### Signal I (hitter upgrade)
<table>

## Conviction watch (context only — buy-low / sell-high)
### PROCESS>MODEL (patience / buy-low WATCH)
<table — SP flavor validated; hitter flavor CONTEXT ONLY>
### MODEL>PROCESS (distrust / sell-high WATCH)
<table>

## Recommended moves (≤5, sequenced)
1. ...
2. ...
```

---

## Anti-patterns this meta-skill exists to prevent

- Re-pulling roster between steps — pull once, share the DataFrame
- Running fa-monitor before roster-audit — need cap math first to compute upgrade floor
- Labeling a player "yours" from session context — always verify via Step 1
- Reporting forced-drop date without pre-identifying the cut candidate — useless as a warning without the name

## When NOT to use

- Mid-week single-player question → use `/fa-pickup-deep-dive` or `/slump-or-decline`
- Just need the SP week plan → `/sp-week-plan` alone
- IL transaction just happened → run immediately regardless of day; don't wait for Monday
