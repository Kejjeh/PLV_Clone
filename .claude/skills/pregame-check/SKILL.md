---
name: pregame-check
description: Morning-of (before lineup lock) daily decision skill. For each of my SPs starting today, decides whether the start is CAP-WORTHY (counts toward the period SP-start cap — 10 standard week / 16 ASG block / 20 playoff 2-week) vs CAP-BENCH (keep on BE because better starts are coming) based on empirically validated rules. Empirical validation 2026-06-06 (n=13,716 starts 2023-25) showed the v1 "aggressive bench" rules were REJECTED — even flagged starts average 9-11 FP, well above replacement ~5 FP. **Skill v2 is conservative** — default to START every confirmed start UNLESS the period SP-start cap is at risk of overflow OR Blended xFP is at replacement-level AND matchup is brutal. Also pre-scans opponent's confirmed SPs and flags any of my hitters facing high-boom opp pitchers (boom_stack ≥3). Pulls live matchup state + current win prob delta. Use every game-day morning before ~12 PM ET. The missing daily layer between /sp-week-plan (weekly cap math) and /roster-deep-audit (seasonal). Triggers — "pregame check", "should I bench today", "any of my SPs in trouble today", "morning roster check", "pregame", "should I start X today", "what's my matchup look like today".
---

# pregame-check

You are running the **morning-of (before lineup lock) daily decision check**.
For each of the user's SP starts today: decide whether to START (count
toward the period SP-start cap) or CAP-BENCH (keep on BE so the start doesn't count
and the cap slot stays free). Also surface opp confirmed SPs + live
matchup state + projected daily delta.

The skill exists because on 2026-06-06 the merge protocol's Tier B veto
on Bradish (NOISE, K% −12.3pp) was correct at the ROSTER level but
Bradish still started and posted −5.8 FP. A daily check would have
flagged "is this start cap-worthy or should we wait for a better
matchup?"

## Trigger phrases

"pregame check", "should I bench today", "any of my SPs in trouble
today", "morning roster check", "pregame", "should I start X today",
"what's my matchup look like today", "are we set for today",
"pre-lock check".

## Empirical validation calibration (CRITICAL)

The v1 "aggressive bench" rules were **empirically rejected**
(`data/research/validation_runs/bench_rule_validation_2026-06-06.md`):

- Tested n=13,716 SP starts 2023-25
- Rules 2/3/4 (Mid + TOUGH; Tier B FLAGGED; Cap-rental streamers)
  produced **net −9,555 FP** when applied universally
- Even "flagged" starts average **9-11 FP**, well above replacement (5 FP)
- Surviving 68-71% of benched starts were positive-EV → bench rules
  were over-aggressive

**What survives empirical audit:**
- **Rule 1 (Ace, never bench)** — trivially safe; never produces bench
- **Rule 3-soft (Tier B flagged + SOFT opp → START)** — correct (soft
  opps rescue flagged arms; mean FP 11.42)

**What the skill must NOT do (per validation):**
- ❌ Bench Tier B FLAGGED pitchers vs NEUTRAL matchups (they avg ~9.4 FP)
- ❌ Bench Mid-tier pitchers vs TOUGH matchups (they avg ~10 FP)
- ❌ Bench cap-rental streamers by default (they avg ~8.9 FP)

## What this skill produces

Three blocks per invocation:

### Block 1: My SP starts today
For each confirmed SP start the user has today:
- Confirmed probable + opp + first pitch ET
- Blended xFP from `live_blend_xfp_latest.csv`
- Tier B status (from latest pitcher-sustainability or sp_master)
- opp_bat_index_recent from `team_strength_*.csv`
- boom_stack score from today's `sp_boom_stack_full_pool_*.json`
- **Cap-worthy verdict**: START / CAP-BENCH with reasoning

### Block 2: Opp confirmed SPs today
- Opp's confirmed SPs (read opp roster + cross-ref MLB API)
- boom_stack score per opp SP
- Flag any of my hitters facing boom_stack ≥3 opp pitchers
- **Hitter exposure**: which of my hitters face a high-boom opp SP

### Block 3: Live matchup state
- `league.box_scores(matchup_period=current)` for live scores
- Projected day-end delta with/without action
- Current win probability and revised post-action win prob

## V2 START/BENCH rules (empirically conservative)

### START by default
**Every confirmed SP start defaults to START** unless one of these
explicit conditions fires:

### Rare CAP-BENCH conditions
Only consider CAP-BENCH when:

1. **Cap overflow risk**: The user is projected to exceed 10 SP
   starts this week AND this specific start has the LOWEST expected
   FP of all confirmed starts. In this case, bench the lowest-EV start
   to free cap for a higher-EV one later in the week.

2. **Replacement-level AND brutal matchup**: Blended xFP ≤ 7.0
   (genuinely replacement-level) AND opp_bat_index_recent ≥ 1.10
   (truly brutal, top-3 offense). Both conditions required.
   Even then, only bench if there's a known-better start coming THIS
   week to take the cap slot.

3. **Tier B NOISE/REGRESS + opp_bat ≥ 1.10**: ONLY bench if (a) Tier B
   sustainability says NOISE or REGRESS (validated process collapse,
   not just "looks bad") AND (b) opp_bat is top-3 brutal AND (c) the
   user has alternate cap-eligible starts in the week.

### Override: SOFT opp ALWAYS supports START (validated)
Per Agent 1 (Rule 3-soft, n=217, mean FP 11.42): if opp_bat < 0.95,
**ALWAYS START** regardless of any Tier B flag. Soft matchups rescue
flagged arms.

### Override: ONLY confirmed SP today → ALWAYS START
If the user has only one SP starting today and the matchup is critical
(period decider), don't bench. The opportunity cost of benching is
higher than the variance cost of a tough matchup. Canonical: Soriano
vs LAD 2026-06-07 (only Sunday SP for Ligers, Bettsing has zero SPs).

## Inputs

1. **Default: today's date** (current MLB game day)
2. **Optional `--date YYYY-MM-DD`**: force a specific date
3. **Optional `--period N`**: force a matchup period
4. **Optional `--names "A,B,C"`**: limit to specific SPs (default = all
   of user's roster SPs with confirmed starts today)

## Step 1: Pull confirmed probables for today

```python
import requests
from app.espn_connector import get_my_roster_with_injuries

# My roster SPs — bucket by ACTUAL role (detect_pitcher_role), never position=='SP'
# (Detmers 2026: position='RP' but a starter). A BE-slot SP still starts today; only
# lineup_slot=='IL' / injured zeros him (feedback_il_slot_vs_il_status.md, gotcha #8).
from scripts.xfp.lib.pitcher_role import detect_pitcher_role
roster = get_my_roster_with_injuries()
pitchers = roster[roster['eligible_slots'].apply(
    lambda s: any(p in str(s) for p in ('SP','RP','P')))].copy()
pitchers['role'] = pitchers.apply(detect_pitcher_role, axis=1)
my_sps = pitchers[(pitchers['role']=='SP') & (pitchers['lineup_slot'] != 'IL')
                  & (~pitchers['injured'].fillna(False))]
my_sp_ids = set(my_sps['player_id'].dropna().astype(int).tolist())

# Today's probables
today = date.today().isoformat()
url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher,team'
r = requests.get(url, timeout=20).json()
```

**Resolving today's probables to my SPs**: ESPN `player_id` ≠ MLBAM. Join by MLBAM
via `plv_clone.utils.name_match.resolve_pitcher_id(name, team=..., role='SP')` — the
collision-safe owner — **never** a bare name or `str.contains` substring match
(gotcha #10: Will vs Austin Warren).

## Step 1.5: Load boxscore bridge for recent SP actuals

Before computing verdicts, load the last 14 days of actual starts from the
boxscore bridge. This fills the context gap between the blended projection
(model-based) and what the pitcher actually did last time out.

```python
from pathlib import Path
import pandas as pd
from datetime import date, timedelta

BS_P = Path('data/research/xfp_cache/boxscore_pitchers.parquet')

def load_bs_recent(lookback_days: int = 14) -> dict[int, list[dict]]:
    """Return {mlbam_id: [starts sorted newest-first]} for last N days."""
    if not BS_P.exists():
        return {}
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    df = pd.read_parquet(BS_P)
    df = df[df['game_date'] >= cutoff].sort_values('game_date', ascending=False)
    out: dict[int, list[dict]] = {}
    for _, row in df.iterrows():
        mid = int(row['mlbam_id'])
        out.setdefault(mid, []).append({
            'date': str(row['game_date']),
            'ip':   float(row['ip']),
            'so':   int(row['so']),
            'h':    int(row['h_allowed']),
            'er':   int(row['er']),
            'fp':   float(row['fp_sp']),
        })
    return out

bs_recent = load_bs_recent()
```

Use this dict in Step 2 to annotate each SP's verdict card with their
most recent 1-2 actual starts. Do NOT use it to override the blended
projection or change verdict rules — it is context only.

**Interpretation heuristics (display only, not rule triggers):**
- Last start FP ≥ 20 (⚡ elite): reinforces START even if model shows mid-tier
- Last start FP < 0 (💀 disaster): note the rough outing but don't auto-bench;
  check whether it was a genuine implosion (ER ≥ 5) or a short hook (IP < 3)
- 2+ consecutive poor starts (FP < 5 each): worth noting trend, not a rule change
- Recent actuals confirming the model (within ±5 FP of blended xFP): label "MODEL ALIGNED"

## Step 2: Per-SP cap-worthy verdict

For each my-SP confirmed for today:

```python
# Tier A
blend_row = blend[(blend['mlbam_id']==pid) & (blend['player_type']=='SP')].iloc[0]
blended_xfp = blend_row['live_blend_xfp']
conf = blend_row['confidence_tier']

# Tier B (from pitcher-sustainability cache or sp_master)
# If no cached verdict, mark as PASSED (default)
tier_b = pitcher_sustainability_verdict(pid) or 'PASSED'

# Matchup tier
opp_bat = team_strength.loc[team_strength['team']==opp_team, 'bat_index_recent'].iloc[0]
matchup_tier = 'TOUGH' if opp_bat >= 1.05 else ('SOFT' if opp_bat < 0.95 else 'NEUTRAL')

# Boom_stack
boom_data = boom_stack_lookup.get(pid, {})
boom_score = boom_data.get('boom_stack', 0)

# Cap math: how many confirmed starts this week so far?
starts_this_week = count_my_starts_this_week_so_far()

# Apply V2 rules
if matchup_tier == 'SOFT':
    verdict = 'START'  # validated by Agent 1 Rule 3-soft
elif starts_this_week + remaining_confirmed_starts <= 10:
    verdict = 'START'  # under cap, no need to bench anyone
elif blended_xfp <= 7.0 and opp_bat >= 1.10 and tier_b in ('NOISE','REGRESS'):
    verdict = 'CAP-BENCH'  # rare bench case validated by Agent 1
else:
    verdict = 'START'  # default to start
```

## Step 3: Pre-scan opp confirmed SPs

```python
# Find my opponent's team from current matchup
league = _get_league()
my_matchup = league.box_scores()  # find Ligers' opponent
opp_roster_sp_ids = set(opp_team.roster ... filter SPs)

# Cross-ref MLB API probables today
opp_today_sp_starts = []
for game in today_games:
    for side in ('away','home'):
        sp = game['teams'][side].get('probablePitcher',{})
        if sp.get('id') in opp_roster_sp_ids:
            opp_today_sp_starts.append((sp['fullName'], sp['id'], opp_team_abbr))

# For each, pull boom_stack and flag high-boom (≥3)
for name, pid, opp in opp_today_sp_starts:
    bs = boom_stack_lookup.get(pid, {}).get('boom_stack', 0)
    if bs >= 3:
        # WHO of my hitters faces this pitcher? Cross-ref matchup
        my_hitters_facing = [h for h in my_active_hitters if h.team == game_opp_team]
        # Flag as risk
```

## Step 4: Live matchup state + projected delta

```python
bs_current = league.box_scores(matchup_period=current_period)
for m in bs_current:
    if 'Ligers' in m.home_team.team_name or 'Ligers' in m.away_team.team_name:
        my_score = m.home_score if mine_home else m.away_score
        opp_score = m.away_score if mine_home else m.home_score
        gap = my_score - opp_score
        # Project today's expected delta from confirmed starts
        my_today_proj = sum(blended_xfp_for_each_starter)
        opp_today_proj = sum(opp_starter_blends)
        revised_gap = gap + (my_today_proj - opp_today_proj)
```

Compute win probability with daily-std ≈ 25-28 FP:
```python
from scipy.stats import norm
z = revised_gap / 28
wp = norm.cdf(z) if revised_gap > 0 else (1 - norm.cdf(-z))
```

## Step 5: Output card

```
## Pregame Check — <date>

### Live matchup
Ligers vs <opp>  
Current: Ligers <X> vs <opp> <Y>  
Margin: <gap>  
Days remaining: <N>  
Win prob today: ~<WP>%

### My SP starts today
1. <Pitcher> vs <opp> (<time> ET)
   Blended xFP: <X> (<conf>)
   Recent actual: <MM-DD> <IP>IP <K>K → <FP> FP [⚡/💀/MODEL ALIGNED]
   (or last 2 if both within 7 days)
   Tier B: <status>
   Matchup: <tier> (opp_bat <X.XX>)
   boom_stack: <N>/4
   Rule fired: <rule>
   **Verdict: START / CAP-BENCH** — <reasoning>

### Opp Bettsing's confirmed SPs today
- <pitcher> vs <opp> — boom_stack <N>/4 — <FLAG/OK>
- (or: zero confirmed SPs — major edge for me)

### Net action
- <bullet 1>
- <bullet 2>
- <bullet 3>
```

## Anti-patterns this skill exists to prevent

- **Bench-by-default culture.** The empirical validation showed
  v1 rules over-bench; even "flagged" starts average 9-11 FP.
  Default is START. CAP-BENCH only fires for the explicit rare
  conditions in Step 2.
- **Benching when you have only one SP starting today.** The
  opportunity cost is higher than the variance cost. Soriano 2026-06-07
  is the canonical example.
- **Benching for "tough matchup" alone.** Tough matchup is one factor
  among many. Mid-tier + TOUGH still averages 10+ FP per validation.
- **Forgetting the opp scan.** This is the half of the skill that
  doesn't get attention. If Bettsing has Ben Brown with boom_stack 3/4,
  knowing this affects your risk-tolerance on YOUR side too.
- **Running this mid-game.** This is a pre-lock skill. After first
  pitch, decisions are locked.

## When NOT to use this skill

- FA pickup decision → `/fa-pickup-deep-dive`
- Trade decision → `/roster-deep-audit`
- Streamer pick → `/stream-the-stack`
- Full-week SP cap math → `/sp-week-plan`
- Pure roster move (drop/add) without daily context → `/roster-deep-audit`

## Related skills

- `/sp-week-plan` — weekly cap math (this skill is the daily layer)
- `/roster-deep-audit` — seasonal layer (this skill is the daily tactical layer)
- `/boom-bust-history` — variance lens (this skill consumes it)
- `/sp-slate-grid` — full multi-day SP slate (this skill is the single-day filter)
- `/triangulate` — 3-lens player verdicts
- `reference_lens_merge_protocol.md` — the merge protocol this skill applies daily

## Empirical references

- `data/research/validation_runs/bench_rule_validation_2026-06-06.md`
  — full backtest of v1 rules; the source of the v2 conservative rewrite
- `data/research/validation_runs/lens_weight_backtest_2026-06-06.md`
  — boom-bust is strongest lift lens (informs daily decisions)
- `data/research/validation_runs/tier_b_veto_validation_2026-06-06.md`
  — SP veto valid (80% correct); used in Step 2 rule 3

## Future development

- Validate Step 4 (live matchup state) once 2026 season ends with full
  matchup history
- Validate per-week applied skill output via tracked predictions
- Add Step 1.5: pull confirmed Sunday/Monday lineups for opp hitters
  the user is facing (currently only checks opp SPs)
- Extend to RPs: leverage_tier-based daily activation logic
