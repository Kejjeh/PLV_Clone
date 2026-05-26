---
name: forced-drop-planner
description: Given the current roster's IL return timeline, computes the exact date the 10-SP-start cap will be breached, pre-identifies the cut candidate from rp3 rankings, and optionally surfaces FA replacement options. Use when multiple IL starters are returning in close succession (Glasnow/Fried pattern) and you need to plan cuts in advance.
---

# forced-drop-planner

Fills the gap between "player returning from IL" and "roster is suddenly over
the SP cap with no plan." Computes the forced-drop deadline and pre-identifies
the cut so there's no surprise on activation day.

---

## Inputs

1. **Current roster** — pulled live via `get_my_roster_with_injuries()`
2. **FA replacement needed?** (optional) — if yes, also surfaces top FA SPs
   by rp3 rank to consider as same-day replacements

---

## Step 1 — Current cap state

```python
from app.espn_connector import get_my_roster_with_injuries
import pandas as pd

roster = get_my_roster_with_injuries()
sps = roster[roster['position'] == 'SP']

sps_healthy = sps[(sps['lineup_slot'] != 'IL') & (~sps['injured'])]
n_healthy = len(sps_healthy)
proj_starts = n_healthy * 1.19

print(f"Current: {n_healthy} healthy SPs → {proj_starts:.2f} starts/wk vs 10 cap")
print(f"Gap: {10 - proj_starts:+.2f}")
```

---

## Step 2 — Simulate each IL return

For each injured SP with a return date, compute what happens when they activate:

```python
il_sps = sps[sps['injured'] == True].sort_values('days_until_return')

cumulative_healthy = n_healthy
events = []

for _, r in il_sps.iterrows():
    cumulative_healthy += 1
    proj = cumulative_healthy * 1.19
    over = proj >= 10
    events.append({
        'player': r['player_name'],
        'return_date': r['return_date'],
        'days_until': r['days_until_return'],
        'il_type': r['injury_status'],
        'new_healthy_count': cumulative_healthy,
        'new_proj_starts': proj,
        'over_cap': over,
        'forced_drop': over  # need a cut on or before this date
    })

for e in events:
    flag = ' ← FORCED DROP DATE' if e['forced_drop'] and events.index(e) == next(i for i,x in enumerate(events) if x['forced_drop']) else ''
    print(f"{e['return_date']:12s} {e['player']:25s} → {e['new_healthy_count']} SPs → {e['new_proj_starts']:.2f}/wk{flag}")
```

---

## Step 3 — Identify cut candidates

From the healthy SP pool, rank by rp3 projection ascending. The bottom 2-3 are
the pre-identified cuts:

```python
import unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv').dropna(subset=['player_name'])
rp3_lookup = {}
for _, row in rp3.iterrows():
    raw = str(row['player_name'])
    if ',' in raw:
        last, first = [x.strip() for x in raw.split(',', 1)]
        for k in (_norm(f'{first} {last}'), _norm(raw)):
            rp3_lookup[k] = row
    else:
        rp3_lookup[_norm(raw)] = row

cuts = []
for _, r in sps_healthy.iterrows():
    proj = rp3_lookup.get(_norm(r['player_name']))
    xfp = proj['xfp_rp3_per_start'] if proj is not None else None
    rank = int(proj['rank']) if proj is not None else 999
    cuts.append({'name': r['player_name'], 'xfp': xfp, 'rank': rank, 'slot': r['lineup_slot']})

cuts.sort(key=lambda x: x['rank'], reverse=True)  # worst first
print("\nCut candidates (weakest first):")
for c in cuts[:3]:
    print(f"  #{c['rank']:3d}  {c['name']:25s}  {c['xfp']:.2f}/start  slot={c['slot']}")
```

---

## Step 4 — Output report

```markdown
## Forced Drop Plan — <date>

### Current state
N healthy SPs → P starts/wk (X under/over cap)

### IL return cascade
| Return date | Player | New SP count | Projected starts/wk | Action needed |
|---|---|---|---|---|
| Jun 15 | Glasnow | 9 | 10.7 | **FORCED DROP by Jun 15** |
| Jun 16 | Fried | 10 | 11.9 | **SECOND FORCED DROP by Jun 16** |
| Jul 1 | Greene | 11 | 13.1 | IL slot frees (no new healthy SP) |

### Pre-identified cuts
1. **<Worst SP>** — #XXX rp3, X.XX/start → DROP by <date>
2. **<2nd Worst SP>** — #XXX rp3, X.XX/start → DROP by <date> (if needed)

### Do NOT cut
- <any SP in top 8 by rp3> — under cap even with returns
- Any SP with ≤2 weeks to IL return (could be activated after cut is absorbed)

### FA SPs available as same-day replacements (if requested)
(from /fa-sp-pool filtered to rp3 rank ≤ 80, not IL'd)
```

---

## Anti-patterns this skill exists to prevent

- Waiting until the day of activation to identify the cut — by then it's
  reactive and usually means dropping someone on a gut feel
- Cutting the wrong Muncy (or any same-name player) — use team-keyed rp3 lookup
- Counting IL'd SPs as healthy — `sps_healthy` must use `lineup_slot != 'IL'`
  not `injured == False` (see `feedback_il_slot_vs_il_status.md`)
- Forgetting that IL-slotted returning SPs free an IL slot (which may allow
  Helsley or another injured player to move off bench)

## When NOT to use

- Only one return pending and currently under cap → sp-week-plan handles it
- User asking about hitter drops → use roster-audit Step 6 directly
