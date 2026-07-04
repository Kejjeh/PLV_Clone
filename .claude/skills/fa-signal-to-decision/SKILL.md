---
name: fa-signal-to-decision
description: Meta-skill that chains fa-monitor (HIGH alerts only) → fa-pickup-deep-dive (per alert) → ranked add recommendation. Replaces the manual loop of "fa-monitor fires X, now should I deep-dive it?" Use when you want to go from signal to final add/pass decision in one pass, scoped to ≤3 HIGH alerts.
---

# fa-signal-to-decision

Chains two skills that are almost always used sequentially:

1. **fa-monitor** → pull HIGH-priority alerts across all 12 signals
2. **fa-pickup-deep-dive** → run full deep-dive on each HIGH hit (cap at 3)
3. **Rank and recommend** → final add/pass decision with comparative context

The skill exists because the manual pattern "fa-monitor fires HIGH on X, let me
now run a deep-dive on X" happened every week and involved re-pulling ESPN data.

---

## Inputs

1. **Signal filter** (optional) — `all` (default), `SP`, `H`, `RP`. Focus the
   fa-monitor step on a specific signal type.
2. **Your weakest at each bucket** — pulled automatically from roster.
3. **Max deep-dives** — default 3 (cap; more than 3 alerts in one session is
   cognitive overload and likely means the wrong threshold).

---

## Step 1 — fa-monitor (HIGH only)

Run `/fa-monitor` and extract only HIGH-priority alerts. Suppress MONITOR tier
from the main output — these appear in a collapsed appendix only.

```python
# Run fa-monitor script or inline signal logic
# Key: rp3 rank <= 150 for Signal A, rh3 rank <= 150 for Signal I
# HIGH = both gates cleared (fpp >= 0.02 AND whiff >= 26% for Signal A)
high_alerts = [a for a in alerts if a['priority'] == 'HIGH']
```

If zero HIGH alerts: report "No HIGH alerts this run — MONITOR alerts in appendix."
Stop here. Do NOT run deep-dives on MONITOR alerts.

If > 3 HIGH alerts: surface all in a summary table, then deep-dive only the
top 3 by signal strength (fpp gap for A, xwOBA gap for I, role certainty for RP).

**Signal O (rating-arc) tiebreak:** when two alerts are otherwise close, break
the tie with the **rating-arc Δ** — the in-season trajectory of the validated
pillar (SP STUFF / hitter CONTACT) from `scripts/xfp/lib/rating_arc.py`. A
steeper positive arc Δ (rating climbing) wins the last deep-dive slot over a
flat one. **Rule 13:** rating-arc is CONTEXT only — it breaks ties between
alerts, it does NOT create an alert or move a model rank.

```python
from lib.rating_arc import rating_arcs  # OWNER of arc computation (context lens)
arcs = rating_arcs('sp')            # or 'hitter' — DataFrame per mlbam
# each row: arc in {RISER, FLAT, FALLER} + dk (the pillar delta over lookback).
# tiebreak when |score_a - score_b| is within noise: prefer the larger `dk`
# (RISER > FLAT > FALLER).
```

---

## Step 2 — fa-pickup-deep-dive (per HIGH alert, ≤3)

For each HIGH alert player, run `/fa-pickup-deep-dive` using the shared ESPN
`fa_all` DataFrame (do not re-fetch). Key outputs per player:

- Model projection vs prior (the gap is the story)
- Recent Statcast (last 3-5 outings or 5-10 games for hitters)
- Injury status and return date if applicable
- Ownership % and ESPN team verification
- Net weekly FP gain vs your weakest at that bucket

---

## Step 3 — Comparative rank and recommendation

After deep-diving all HIGH alerts, rank them by:

```
score = model_rank_pct + recency_form_gap_normalized + slot_fit_bonus
```

Where:
- `model_rank_pct` = (total_players - rank) / total_players
- `recency_form_gap_normalized` = gap / 3.0 (cap at 1.0)
- `slot_fit_bonus` = 0.1 if player fills an open eligible slot, else 0

Output: ranked add recommendation with the drop target for each.

---

## Output format

```markdown
# FA Signal → Decision — <date>

## HIGH alerts summary (N total)
| Signal | Player | Priority reason | Own% |
|---|---|---|---|
| A | ... | fpp=X, whiff=Y% | Z% |
| I | ... | xwOBA gap +0.035, OBACON 0.370 | Z% |

## Deep dives (top 3)

### 1. <Player> [Signal A / I / H]
<fa-pickup-deep-dive condensed output>
**Add verdict: YES / BORDERLINE / PASS** — <one sentence>
**Drop to make room:** <player> (<model projection>)

### 2. <Player>
...

## Final recommendation
**Add #1: <Player>** (drop <X>) — net +N FP/wk
**Add #2: <Player>** (drop <Y>) — net +N FP/wk (if multiple slots available)
**Pass on: <Player>** — <one reason>

## MONITOR alerts (appendix — do not act yet)
<collapsed list>
```

---

## Anti-patterns this meta-skill exists to prevent

- Deep-diving MONITOR-tier alerts — they haven't cleared both gates; they're
  watch candidates, not action candidates
- Running deep-dives on > 3 players — decision fatigue produces worse picks
  than a clear top-3 comparison
- Forgetting to verify FA status — fa-monitor fires on the model; the player
  may have been picked up between the signal and the deep-dive. Always check
  `get_all_teams()` before recommending the add.
- Recommending an add without naming the drop — "add X" without "drop Y" is
  not actionable in a full-roster scenario

## When NOT to use

- Just want the signal scan without committing to a decision → `/fa-monitor` alone
- Single known player → `/fa-pickup-deep-dive` directly (skip the monitor step)
- SP-specific FA scan → `/fa-sp-pool` (broader; not alert-driven)
