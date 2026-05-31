---
name: sp-week-plan
description: Plan the upcoming scoring week's SP usage against the 10-start cap. Projects each healthy SP's start count (1 or 2) from confirmed probables + rotation gap, joins opponent offensive strength, ranks starts by expected FP, identifies the weakest start to bench when starts exceed cap, and flags long-IL SPs as drop candidates. Use Monday morning, or whenever the user asks "how many starts do I have this week", "should I bench any SP", "which start is the weakest", or "I have N starts — what do I drop".
---

# sp-week-plan

You are planning the upcoming scoring week's SP usage. The skill
exists because Monday-morning SP-planning is a 5-step workflow that
recurs every week (MLB probables → rotation-gap predictions →
opponent strength → recent form → bench/drop recommendation), and
because the BrownU 10-start cap means a wrong bench costs you 0 FP
on what could have been a 25-FP start.

The 10-SP-start cap is HARD — starts 11+ count as zeros (see
`reference_league_rules.md`). Always confirm projected starts vs cap
even if the user didn't ask explicitly.

---

## Inputs

1. **Scoring window** (default = current Mon–Sun, i.e., today through
   Sunday). If today is mid-week, surface remaining-week starts and
   note that earlier starts are locked.
2. **Cap** (default = 10 SP starts per BrownU rules). Don't change
   without confirmation.
3. **Mode** — `plan` (default, full output) | `bench-only` (just the
   bench recommendation) | `drops-only` (just the drop list).

---

## Step 1 — Pull active pitching roster

```python
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
pitchers = roster[roster['eligible_slots'].apply(
    lambda s: any(p in s for p in ['SP','RP','P']) if isinstance(s,list) else False
)]
sps_healthy = pitchers[(pitchers['position']=='SP') & (pitchers['lineup_slot'] != 'IL') & (~pitchers['injured'])]
sps_injured = pitchers[(pitchers['position']=='SP') & (pitchers['injured'])]
```

Critical: distinguish `position=='SP'` from `lineup_slot=='SP'`. SPs
on bench (`lineup_slot=='BE'`) still pitch their normal rotation; they
just need to be moved to a `P` slot on start day.

Also flag injured SPs sitting on `BE` instead of `IL` (e.g., Helsley
today — counts as a BE-slot drag, not an IL stash).

---

## Step 2 — Pull confirmed probables for the window

```python
import requests
url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={window_start}&endDate={window_end}&hydrate=probablePitcher,team"
data = requests.get(url, timeout=30).json()
```

For each `date` → each `game` → home/away `probablePitcher`, capture
`{date, pitcher_id, pitcher_name, team, opp_abbr, is_home}`.

Filter to my roster's pitcher IDs. The MLB Stats API only publishes
probables 2–5 days ahead — many later-week starts will be
unconfirmed and need rotation-gap prediction.

---

## Step 3 — Predict unconfirmed starts from rotation gap

For each healthy SP NOT in the confirmed probables list (or where the
confirmed list is incomplete for the full window):

```python
url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog&group=pitching&season=2026"
r = requests.get(url, timeout=15).json()
splits = [s for s in r['stats'][0]['splits'] if int(s['stat']['gamesStarted']) > 0]
splits.sort(key=lambda s: s['date'], reverse=True)
```

Compute rotation gap from the most recent two recorded starts:
```python
latest_actual = datetime.strptime(splits[0]['date'], '%Y-%m-%d')
if len(splits) >= 2:
    gap = (latest_actual - datetime.strptime(splits[1]['date'], '%Y-%m-%d')).days
    gap = max(4, min(7, gap))  # clamp to typical rotation range
else:
    gap = 5
```

**CRITICAL — anchor predictions to the LATER of `latest_actual` and
the latest confirmed probable date in this window.** Otherwise the
rotation predictor re-emits a date that's already confirmed (e.g.,
pitcher last logged 5/13, confirmed for today 5/18, gap=7 → predictor
emits 5/20 as "next" — but his actual next start is the confirmed
today's 5/18). This caused a false 13-start count during /sp-week-plan
testing before the fix.

```python
confirmed_dates_in_window = [
    datetime.strptime(c['date'], '%Y-%m-%d')
    for c in confirmed.get(name, [])
]
anchor = max([latest_actual] + confirmed_dates_in_window)
preds = []
nd = anchor
for _ in range(3):
    nd = nd + timedelta(days=gap)
    if WIN_START <= nd <= WIN_END:
        preds.append(nd)
```

**Dedup near-matches:** After predicting, drop any predicted date that
falls within ±1 day of a confirmed date — same start, just labeled
differently.

**2-start week detection:** Final count = `len(confirmed_in_window) +
len(preds_after_dedup)`. Cap at 2 per pitcher per week — rotations
don't produce a 3rd start in 7 days.

---

## Step 4 — Join opponent offensive strength

For each predicted start, look up opponent in
`data/research/xfp_cache/team_strength_2026.csv`:

```python
import pandas as pd
ts = pd.read_csv('data/research/xfp_cache/team_strength_2026.csv')
# bat_index_recent: >1.0 = above-avg offense (bad matchup),
#                   <1.0 = below-avg offense (good matchup)
```

Annotate each start with `bat_index_recent` of opponent. Use
`bat_index_recent` not `bat_index_to` — recent 21d signal is
what matters for streaming decisions.

Translate to plain-English tier:
- ≥ 1.05 → **brutal** (TOP-5 offense)
- 1.00–1.05 → above-avg
- 0.95–1.00 → ≈ avg
- 0.90–0.95 → favorable
- < 0.90 → **streamable** (very weak)

---

## Step 5 — Score each start: model projection × matchup × recent form

For each start, build an EV score (rough heuristic — exact formula
not critical):

1. **Base:** SP's `xfp_rp3_per_start` from
   `data/outputs/xfp_rp3_projections.csv`. Skip the join if the SP isn't
   in rp3 (rookie/recent callup — note "no model row" and use last-3-
   start ERA/K as proxy).
2. **Matchup adjustment:** scale down by opponent `bat_index_recent`
   (1.10 = subtract ~15% from base; 0.90 = add ~10%).
3. **Recent form penalty:** if last 2 starts had IP < 5.0 OR ER > 4,
   apply additional 20-30% penalty (short outings are FP poison
   regardless of K rate).

Don't over-engineer the formula — surface the components honestly
(model, matchup, recent form) and let the user weight. The EV is
just for *ordering* the bench candidates, not a precise projection.

---

## Step 6 — Cap math + bench recommendation

**CRITICAL — count PAST + FUTURE, not just future.** Cap math is
*week-to-date already pitched* + *today's confirmed/predicted* +
*remaining days' confirmed/predicted*. A common bug was the matchup
dashboard's cap counter only summing forward-looking starts, missing
days 1-N already played. On the last day of a scoring week with 5+
prior starts, this caused a massive undercount (reported 2/10 when
actual was 9/10 — 5 prior + 2 Sat + 2 Sun). Fixed 2026-05-31 in
`render_cap_status` via a new `_count_past_sp_starts` helper that hits
MLB Stats API gameLog for each healthy SP in `my_lineup`.

When you build the week's cap math:
1. **Past starts** — for each rostered SP, fetch their MLB gameLog and
   count starts with date in `[week_start, today)`.
2. **Today's starts** — confirmed probables for date == today + predicted
   from rotation gap.
3. **Future starts** — confirmed probables + rotation-gap predictions
   for dates > today within the window.
4. Total = past + today + future. THAT is what hits the 10-cap.

```python
total_starts = past_starts + sum(start_counts)
if total_starts <= cap:
    bench_recommendation = "No bench needed."
elif total_starts > cap:
    over_by = total_starts - cap
    # Find the lowest-EV start(s) to bench
    # RULE: never bench a 2-start pitcher unless catastrophic — 1 good
    #       start almost always beats 1 elite start in cap math
    bench_candidates = [s for s in starts if pitcher_is_1_start(s.pitcher)]
    bench_candidates.sort(key=lambda s: s.ev_score)
    bench = bench_candidates[:over_by]
```

Format the bench recommendation:
```
Bench: <Pitcher> <day vs opp> — reason: <short-outings|brutal matchup|combo>
```

For each bench-candidate, explain WHY it's the weakest — not just
"lowest projection" but the actual driver (e.g., "3.2 IP and 4.1 IP
in his last 2 starts — short outings tank FP regardless of K rate").

---

## Step 6.5 — Cross-check with matchup dashboard (regression detector)

If the matchup dashboard (`xfp-model/docs/matchup.html`) has been built
recently, cross-reference its SP start count against this plan's count:

```python
import re
from pathlib import Path
html = Path('xfp-model/docs/matchup.html').read_text(encoding='utf-8')
m = re.search(r'(?:Only|⚠ SP cap at maximum:?) (\d+) probable starts', html)
dashboard_count = int(m.group(1)) if m else None
```

The two should match (or be within ±1 from race conditions on confirmed
probables between runs). If `/sp-week-plan` says 10 starts and the
dashboard says 6, there's a regression in `build_matchup_dashboard.py`
— run `/matchup-audit` to identify which of the 4 known bug patterns
applies (see `reference_matchup_dashboard_sp_gotchas.md`):
- Bug A: IL'd SPs projected non-zero
- Bug B: SP undercount (only confirmed counted)
- Bug C: mlbam=None false-positives on TBD probables
- Bug D: today's games excluded by `today_s <` strict filter

If counts differ but you can't immediately identify the cause, surface
the discrepancy to the user before recommending any bench decisions —
their dashboard view may not match what `/sp-week-plan` shows, and
bench choices made off the wrong count will misfire.

---

## Step 6.6 — Forward-looking forced-drop date

After cap math for this week, compute when the cap will be breached
by upcoming IL activations:

```python
from datetime import date

il_returns = roster[(roster['injured']==True) & (roster['position']=='SP') & (roster['lineup_slot']=='IL')]
il_returns = il_returns.sort_values('days_until_return')

for _, r in il_returns.iterrows():
    projected_healthy = len(sps_healthy) + 1  # +1 per return
    proj_starts = projected_healthy * 1.19
    if proj_starts >= 10:
        print(f"FORCED DROP DATE: {r['return_date']} — {r['player_name']} activates → {projected_healthy} SPs → {proj_starts:.1f} starts/wk (over cap)")
        print(f"Pre-identify cut NOW from bottom of rp3 rankings: {[s['player_name'] for s in sps_healthy sorted by rp3 asc][:2]}")
        break
```

Report as: "Forced-drop deadline: **Jun 15** (Glasnow activates → 9 SPs → 10.7/wk). Pre-cut: Warren or Bradish."

This prevents the surprise of a returning star creating a cap violation with no pre-planned cut.

---

## Step 7 — Drop candidates for long-term roster optimization

Separate from the weekly bench decision, surface drop candidates:

**Tier 1 (drop if any roster pressure):**
- 60-day IL SPs (>30 day return) — biggest opportunity cost. Recovery
  stigma means even when "back" they need ramp time.
- Healthy SPs not in your top 8 by rp3 projection (with the 10-cap
  binding, you only need ~8 active SPs anyway).

**Tier 2 (hold but monitor):**
- BE-slot injured pitchers (move to IL slot as soon as one frees)
- 15-day IL with return <14 days away (close enough to hold)

**Tier 3 (hold):**
- All healthy rotation-locked SPs in your top 8
- RPs with closer-of-record role (see
  `feedback_save_handcuffs_needs_closer_context.md`)

Show the drop priority list ONLY if (a) user explicitly asked OR
(b) projected starts exceed cap structurally (e.g., 11-12 starts
multiple weeks running suggests too many SPs on roster).

---

## Step 8 — Output format

```markdown
## Projected starts this week (<window>)

| Pitcher | Confirmed | 2nd (inferred) | n | Last 3 form (IP/ER/K) | Opp xwOBA |
|---|---|---|---|---|---|
... rows sorted by start day ...

**TOTAL projected starts: N** (cap = 10)

## Bench recommendation

**Bench: <Pitcher> <date vs opp>** — <reason in 1-2 sentences>

Backup candidate (if you trust <Pitcher>'s K upside): <alt>

Do NOT bench: <list pitchers + brief reason — 2-start, hot form, weak opp>

## Drop candidates (if applicable)

(only show if user asked OR if structural cap pressure)

Tier 1: <60-day IL or below-replacement SP>
Tier 2: <hold but monitor>
Tier 3: <hold>

## TL;DR

- Bench <one line>
- Drop <one line if applicable>
- N starts projected vs 10 cap
```

---

## Anti-patterns this skill exists to prevent

- **Benching a 2-start pitcher.** Two OK starts > one elite start in
  cap math. Bench candidates should come from the 1-start pool
  unless a 2-start matchup is genuinely catastrophic (both opponents
  ≥ 1.05 bat_index_recent AND pitcher in poor form).
- **Counting Glasnow/Greene/Fried-style IL'd SPs in the start total.**
  Always filter to `~injured` SPs at the roster step. They'll appear
  in rotation predictions because the API still tracks their last
  start.
- **Trusting MLB Stats API probables for full-week count.** Probables
  only post 2-5 days ahead. Late-week starts MUST come from rotation-
  gap prediction.
- **Recommending a bench based on matchup alone.** Recent SP form
  (especially IP/start) matters more than opponent xwOBA for the
  weakest start. Carlos Rodón today: TOR was a mid matchup (0.305
  xwOBA), but Rodón's 3.2 + 4.1 IP was the actual problem.
- **Auto-recommending an FA SP pickup to replace dropped pitcher.**
  This skill identifies drop candidates; FA replacement is separate
  (`/fa-replacement-pool` with bucket=SP).
- **Mixing the weekly bench decision with long-term drop decisions.**
  Benching for one week ≠ dropping. Surface as separate sections.

---

## When NOT to use this skill

- User just wants a single SP's projection → use a direct rp3 lookup,
  not this skill
- Mid-game live monitoring → use `scripts/xfp/live_monitor.py --watch`
- RP-only roster decisions (closer rankings, save chasing) → out of
  scope; needs a separate `/rp-week-plan` (not yet built — candidate
  for future)
- Multi-week forward planning (which IL SP to keep through July) →
  use `/roster-audit` for the long-term view

---

## Integration with `/triangulate`

For any borderline bench-or-start call, weight the EV score by the
per-SP triangulate output:

- `/triangulate <SP_name>` returns `verdict_top`, `confidence`, and `arche_t1_fp`.
  Use `arche_t1_fp` as an alternative ceiling estimate when rp3 disagrees with
  archetype (e.g., Bryan Woo's rp3 #17 vs archetype TRENDING_DOWN, or Reid Detmers
  rp3 #185 vs MT_RUSHMORE archetype TRENDING_UP). The triangulate verdict tag
  (BUY / HOLD / CAUTION / FADE) often resolves the rp3-vs-recent-form dissonance.
- For SPs where two start options are within 1pp of each other in EV, hand off
  to `/sp-bench-mc` for the MC simulator with bootstrap CIs.
