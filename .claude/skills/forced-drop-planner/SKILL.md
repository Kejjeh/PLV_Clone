---
name: forced-drop-planner
description: Given the current roster's IL return timeline, computes the exact date the period SP-start cap (10 standard week / 16 ASG block / 20 playoff 2-week) will be breached, pre-identifies the cut candidate from rp3 rankings, and optionally surfaces FA replacement options. Use when multiple IL starters are returning in close succession (Glasnow/Fried pattern) and you need to plan cuts in advance.
---

# forced-drop-planner

Fills the gap between "player returning from IL" and "roster is suddenly over
the SP cap with no plan." Computes the forced-drop deadline and pre-identifies
the cut so there's no surprise on activation day.

**Trigger phrases:** "forced drop", "when do I have to cut", "cap breach date",
"Glasnow/Fried plan", "IL cascade", "who do I drop when X returns".

---

## Canonical case — New York Ligers 2026-05-31 (Glasnow + Fried + Greene)

The classic pattern this skill exists to handle:

| Player | IL type | Return date | IL slot freed |
|---|---|---|---|
| Tyler Glasnow (SP) | IL15 | 2026-06-15 | +1 |
| Max Fried (SP) | IL15 | 2026-06-16 | +1 |
| Hunter Greene (SP) | IL60 (elbow SURGERY) | 2026-07-03 | +1 |

**On 6/15 the cascade begins.** Glasnow activates → 1 IL slot freed AND 1 active
SP slot must be cleared. The next day Fried does the same. **Two forced drops
needed in 24 hours** unless planning starts ~10 days ahead.

**Pre-computed cut candidates** (lowest active SP rp3 ranks on the roster as of
2026-05-30): Will Warren (#175, BUY archetype breakout — preserve if possible),
Parker Messick (rookie, no rp3 yet — cleanest drop).

**Then on 7/3, Greene's IL60 expires** — a third forced drop unless another
SP is meanwhile dropped voluntarily. Plan all three cuts together, not three
separate scrambles.

The Greene case also illustrates why **forced-drop-planner should propagate
the running active-SP count across cascading returns** — Step 2 below currently
recomputes the gap independently per return; a single drop "absorbs" one
return but the next return resets the counter. Fix in TODO list.

---

## Inputs

1. **Current roster** — pulled live via `get_my_roster_with_injuries()`
2. **FA replacement needed?** (optional) — if yes, also surfaces top FA SPs
   by rp3 rank to consider as same-day replacements

---

## Step 1 — Current cap state

```python
from app.espn_connector import get_my_roster_with_injuries
from scripts.xfp.lib.pitcher_role import detect_pitcher_role
import pandas as pd

roster = get_my_roster_with_injuries()
# Bucket by ACTUAL role, NOT the raw ESPN position tag: a dual-eligible starter
# (Detmers 2026 — position='RP' but eligible 'SP' and actually starting) must
# count as an SP against the period SP-start cap. detect_pitcher_role self-resolves
# the mlbam and decides on real gamesStarted (gotcha #8), never the stale tag.
pitchers = roster[roster['eligible_slots'].apply(
    lambda s: any(p in str(s) for p in ('SP', 'RP')))].copy()
pitchers['role'] = pitchers.apply(detect_pitcher_role, axis=1)
sps = pitchers[pitchers['role'] == 'SP']

sps_healthy = sps[(sps['lineup_slot'] != 'IL') & (~sps['injured'])]
from plv_clone.cap_math import SP_CAP, projected_starts, gap_to_cap
n_healthy = len(sps_healthy)
proj_starts = projected_starts(n_healthy)   # OWNER — never re-type 1.19

print(f"Current: {n_healthy} healthy SPs → {proj_starts:.2f} starts/wk vs {SP_CAP} cap")
print(f"Gap: {gap_to_cap(n_healthy):+.2f}")
```

`SP_CAP` is 10 only for a standard scoring week. For the LIVE period cap
(ASG block = 16, playoff 2-week = 20) resolve
`resolve_current_period_meta(league)['sp_cap']` (from
`scripts.xfp.lib.period_meta`) and compare projected starts against that
value in Step 2's over-cap test, not a hardcoded 10.

---

## Step 2 — Simulate each IL return

For each injured SP with a return date, compute what happens when they activate:

```python
il_sps = sps[sps['injured'] == True].sort_values('days_until_return')

cumulative_healthy = n_healthy
events = []

for _, r in il_sps.iterrows():
    cumulative_healthy += 1
    proj = projected_starts(cumulative_healthy)
    over = proj >= SP_CAP
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

### sp-decline cut tiebreaker (prefer cutting the eroding arm)

rp3 rank picks the weakest staff SPs. When the bottom 2-3 candidates are
**within ~1-1.5 FP/start of each other**, break the tie with the validated
`/sp-decline` lens: prefer cutting the **DECLINE-RISK** arm — its FP is propped
above its whiff/K stuff LEVEL and is regressing DOWN rest-of-season, so it has
the least forward value of the cluster. Conversely, **preserve a RISING** arm
(whiff/K level ahead of FP = buy-low-safe) even if its current rp3 rank is a hair
lower.

```python
import sys; sys.path.insert(0, 'scripts/xfp')
from sp_decline_model import build as build_decline
dec, _ = build_decline()            # DataFrame keyed on mlb_id (MLBAM)
dec_by_mlbam = dec.set_index('mlb_id')['tier'].to_dict()
# Annotate each cut candidate with its tier (resolve name -> mlbam first), then
# among near-tied rp3 ranks, cut DECLINE-RISK before STABLE before RISING.
```

**Validated 2026-06-13** (`sp_decline_stuff_decay_2026-06-13.md`, partial-r ~0.235
whiff/K LEVEL). **Context/risk flag ONLY — never moves the rp3 headline** (CLAUDE.md
#13). It breaks ties within the bottom cluster; rp3 rank still selects the cluster.
For the decomposition behind a flag, run `/sp-decline --players "X"`.

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
- **Any RP in a SAVE_PROMOTION_WINDOW or SETUP_CONSOLIDATION_WINDOW** (see RP-leverage cross-check below)
- **Any near-tied SP flagged sp-decline RISING** — whiff/K level ahead of FP = buy-low-safe; cut the DECLINE-RISK arm in the cluster instead (see sp-decline cut tiebreaker above)

### FA SPs available as same-day replacements (if requested)
(from /fa-sp-pool filtered to rp3 rank ≤ 80, not IL'd)
```

---

## RP-leverage cross-check (PR 7, Gate 0c)

Before finalizing the cut list, run each candidate RP through
`scripts/xfp/lib/rp_leverage_window.py::classify_rp_leverage_window` to
detect role-transition signals that would make a drop catastrophic:

- **SAVE_PROMOTION_WINDOW** — closer-transition signal. Recent 14d save
  count ≥ 2 AND prior 14d had 0 saves. Dropping this RP gives away an
  ~5 FP/g role swing. **NEVER cut a SAVE_PROMOTION_WINDOW player to
  resolve an SP cap** unless they are clearly the worst RP and no
  forced choice exists.
- **SETUP_CONSOLIDATION_WINDOW** — recent 14d holds ≥ 4 with ≤ 1 save.
  More tolerable to cut than SAVE_PROMOTION but still worth a flag —
  preserve if any equivalent SP cut exists.

The two windows are distinct on purpose (plan v11 Decision 7) — earlier
heuristics conflated "high HLD" with "closer transition," masking the
actual SV-event signal. The function priority is SAVE_PROMOTION wins
ties, matching the BrownU value impact.

---

## Anti-patterns this skill exists to prevent

- Waiting until the day of activation to identify the cut — by then it's
  reactive and usually means dropping someone on a gut feel
- Cutting the wrong Muncy (or any same-name player) — use team-keyed rp3 lookup
- Bucketing pitchers by the raw ESPN `position` tag — a dual-eligible starter
  (Detmers 2026: position='RP' but eligible 'SP' and starting) gets silently
  dropped from the SP pool, undercounting the cap. Use `detect_pitcher_role()`
  (gotcha #8), never `position == 'SP'`.
- Counting IL'd SPs as healthy — `sps_healthy` must use `lineup_slot != 'IL'`
  not `injured == False` (see `feedback_il_slot_vs_il_status.md`)
- Forgetting that IL-slotted returning SPs free an IL slot (which may allow
  Helsley or another injured player to move off bench)

## When NOT to use

- Only one return pending and currently under cap → sp-week-plan handles it
- User asking about hitter drops → use roster-audit Step 6 directly
