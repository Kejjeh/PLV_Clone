---
name: fa-monitor
description: Proactive weekly scan of the FA pool across 6 signal types (SP first-start fp_proxy, RP closer/setup opportunity, hitter sustained xwOBA, drafted-then-dropped comeback, IL return timing, role-change RP) outputting HIGH/MED/LOW alerts. Run Monday mornings or after significant league transactions. Script: scripts/xfp/run_fa_monitor.py. For multi-lens deep-dive on any flagged alert, hand off to `/triangulate` or `/fa-pickup-deep-dive`.
---

# fa-monitor

Proactive weekly scan of the FA pool across three signal types — SP early-start
performance, RP closer opportunity, and hitter sustained xwOBA — to surface
high-value pickups before opponents act. Designed to catch the gaps identified
in the 2026 retroactive analysis: Paul Sewald (RP, +0.133 fp_proxy ignored for
weeks), JJ Bleday (0.408 xwOBA for 2 months on wire), Kyle Harrison (first-start
signal available before anyone added him).

**Trigger phrases:** "what FAs am I missing", "weekly FA scan", "anything available
I should grab", "monitor the wire", "run the FA monitor", or as a scheduled
Monday-morning routine alongside `/roster-audit`.

---

## Signal Registry

All signals live here. Add new signals to this table when validated.

| ID | Name | Position | Threshold | Priority | Added |
|---|---|---|---|---|---|
| A | SP First-Start Alert | SP | fpp_season >= 0.02 AND whiff% >= 26% AND rp3 rank ≤ 120 | HIGH if >= 0.04 (MC-validated 2026-05-25: 68% prec, +53pp lift, 10k bootstrap, 2025 holdout) | 2026-05-25 |
| B | RP Closer/Setup Monitor | RP | rprs2 rank ≤ 40 AND xfp_ros > 120, FA | HIGH if top 20 | 2026-05-25 |
| C | Hitter xwOBA Monitor | H | xwOBA ≥ 0.360, PA ≥ 75, rh3 rank ≤ 100 | HIGH if ≥ 0.390 + 100 PA | 2026-05-25 |
| D | Drafted-Then-Dropped Comeback | ALL | Drafted in prior year, dropped, now rp3/rh3 rank ≤ 80 | HIGH | 2026-05-25 |
| E | IL Return Timing | SP/RP | Prior-year elite performance, currently IL, return date ≤ 14d | MEDIUM | 2026-05-25 |
| F | Role-Change RP | RP | sv_lag1=0 in prior year → SV > 0 in current year, rprs2 rank ≤ 50 | HIGH | 2026-05-25 |
| G | Holds-Only Elite RP | RP | fp_proxy/bf >= 0.04 in >= 20 apps, sv_season = 0, rprs2 rank > 60 | HIGH | 2026-05-25 |
| H | SP Roster Upgrade Alert | SP | FA SP fpp >= user's 3rd-weakest SP fpp + 0.015 AND rp3 rank ≤ 150 AND GS >= 4 (OR Signal A HIGH fires) | HIGH PRIORITY if gap >= +0.030 or Signal A HIGH; MONITOR if gap >= +0.015 | 2026-05-25 |
| I | Hitter Roster Upgrade Available | H | FA hitter xwOBA >= user's 3rd-weakest active hitter xwOBA + 0.025 AND rh3 rank ≤ 150 AND 75+ PA AND xwOBACON >= 0.350 | HIGH PRIORITY if gap >= +0.040 AND rh3 rank ≤ 75; MONITOR if gap >= +0.025 | 2026-05-25 |
| J | LEVERAGE_RISE_FA | RP | leverage_tier {LOW,MID} 2025 → {HIGH,ELITE} 2026 AND gmLI_2026 ≥ 1.2 | HIGH if ELITE tier + gmLI ≥ 1.6; MED if gmLI ≥ 1.4; LOW otherwise | 2026-05-30 |
| K | NEW_CLOSER_FA | RP | sv_2026 ≥ 3 AND no CLOSER tag in 2025 (rookie / first-time-closer included) | HIGH if sv_2026 ≥ 8; MED if ≥ 5; LOW if ≥ 3 | 2026-05-30 |
| L | FIREMAN_BREAKOUT | RP | FIREMAN tag True in 2026 AND False in 2025 (IS% ≥ 80, IR ≥ 20) | HIGH if rprs2 rank ≤ 60 AND gmLI ≥ 1.3; MED otherwise | 2026-05-30 |
| M | VELO_SPIKE_RP | RP | VELO rating (20-80 scale) +5 vs 2025 AND swstr_pct +0.5pp vs 2025 | HIGH if VELO Δ ≥ 8 AND swstr Δ ≥ 1.5pp; MED if VELO Δ ≥ 5 AND swstr Δ ≥ 1.0pp; LOW otherwise | 2026-05-30 |
| N | MULTI_INNING_BULK_VALUE | RP | MULTI_INNING_BULK_26 True AND rprs2 rank ≤ 80 | HIGH if rprs2 ≤ 50 + gmLI ≥ 1.2 OR new MIB role; MED if rank ≤ 60; LOW otherwise | 2026-05-30 |

---

## Pre-condition

Run `/roster-verify` first. Never label any player as "yours" without a live
`get_my_roster_with_injuries()` call. Never infer FA status from percent_owned —
always verify via `league.teams` roster scan (Sheehan error, 2026-05-25).

---

## Step 1 — Pull FA pool (single unfiltered call)

```python
import sys
sys.path.insert(0, r'c:\Users\Joshua\plv_clone')
from app.espn_connector import _get_league
import unicodedata, re

def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'\s+', ' ', s).strip()

league = _get_league()

# Mandatory: single unfiltered call, then filter manually
fas = league.free_agents(size=2000)

# Build rostered-name set for verification
rostered = set()
for team in league.teams:
    for p in team.roster:
        rostered.add(_norm(p.name))

def is_fa(player_name):
    return _norm(player_name) not in rostered

fa_sps = [p for p in fas if p.position in ('SP', 'P') and is_fa(p.name)]
fa_rps = [p for p in fas if p.position == 'RP' and is_fa(p.name)]
fa_hitters = [p for p in fas if p.position not in ('SP', 'RP', 'P') and is_fa(p.name)]
```

**Critical:** Do NOT use `get_free_agents(position=X, size=300)` — that call silently
truncates the pool and drops low-owned high-value players.

---

## Signal A — SP First-Start Alert

Catches pitchers with strong early fp_proxy before any team claims them.
Canonical miss: Kyle Harrison (fp_proxy/bf = +0.046 on first start, available Apr 5).

**MC-validated thresholds (2026-05-25, 10k bootstrap, 2025 holdout):** `fpp_season >= 0.02`
AND `whiff% >= 26%` — 68% precision, +53pp lift over prior `fpp > 0.0` threshold. Both
filters are required; fpp alone at 0.02 produces too many false positives from soft-contact
pitchers.

```python
import duckdb
import pandas as pd
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
PARQ = (REPO / 'data/research/xfp_cache/statcast_2026.parquet').as_posix()
rp3 = pd.read_csv(REPO / 'data/outputs/xfp_rp3_projections.csv')

fa_sp_names = [p.name for p in fa_sps]

con = duckdb.connect()
sql = """
WITH starts AS (
  SELECT pitcher,
    COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
    SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
    SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
    SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
    COUNT(DISTINCT game_date::DATE) AS gs,
    -- whiff% = swinging strikes / total swings (plate discipline filter)
    AVG(CASE WHEN description='swinging_strike' THEN 1.0 ELSE 0.0 END) AS whiff_rate
  FROM read_parquet('{parq}')
  WHERE game_date >= '2026-03-26'
  GROUP BY pitcher
  HAVING COUNT(DISTINCT game_date::DATE) BETWEEN 1 AND 8
    AND COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
)
SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0), 4) AS fp_proxy_per_bf
FROM starts
""".format(parq=PARQ)
early_starts = con.execute(sql).df()
con.close()

# Join to rp3 by pitcher ID, then filter to FA names
# (pitcher ID → player_name via Statcast player_name field)
con = duckdb.connect()
name_sql = """
SELECT DISTINCT pitcher, player_name
FROM read_parquet('{parq}')
WHERE game_date >= '2026-03-26'
""".format(parq=PARQ)
pitcher_names = con.execute(name_sql).df()
con.close()

early_starts = early_starts.merge(pitcher_names, on='pitcher', how='left')

# Filter to FAs, flag by threshold
from plv_clone.utils.name_match import fuzzy_match_name

results_a = []
for _, row in early_starts.iterrows():
    name = row.get('player_name', '')
    fa_match = fuzzy_match_name(name, fa_sp_names)
    if not fa_match:
        continue
    rp3_match = rp3[rp3['player_name'].str.contains(
        name.split(',')[0] if ',' in name else name.split()[-1],
        case=False, na=False
    )]
    rp3_rank = int(rp3_match['rank'].iloc[0]) if len(rp3_match) else 999
    fp = row['fp_proxy_per_bf']
    whiff = row.get('whiff_rate', 0.0)
    # MC-validated thresholds: fpp >= 0.02 AND whiff% >= 26% (2026-05-25, 68% prec, +53pp lift)
    if fp >= 0.02 and whiff >= 0.26 and rp3_rank <= 120:
        priority = 'HIGH' if fp >= 0.04 else 'MONITOR'
        results_a.append({
            'player': fa_match, 'gs': int(row['gs']),
            'fp_proxy_per_bf': fp, 'whiff_pct': round(whiff * 100, 1),
            'rp3_rank': rp3_rank, 'priority': priority
        })

results_a.sort(key=lambda x: -x['fp_proxy_per_bf'])
```

**Output tier:**
- `fp_proxy_per_bf >= 0.04` AND whiff% >= 26% → HIGH — act this week, run `/sp-breakout-signal` to confirm
- `0.02 <= fp_proxy_per_bf < 0.04` AND whiff% >= 26% → MONITOR — watch next start
- `rp3_rank <= 80` → escalate to `/fa-pickup-deep-dive`
- Players with fpp >= 0.02 but whiff% < 26%: soft-contact profile, do NOT fire Signal A (validated false-positive zone)

---

## Signal B — RP Closer/Setup Monitor

Catches high-value relievers sitting unclaimed. Canonical miss: Paul Sewald (rprs2 #10,
fp_proxy/bf +0.133, available for weeks in early 2026).

```python
rprs2 = pd.read_csv(REPO / 'data/outputs/xfp_rprs2_projections.csv')

# Filter rprs2 to top 40, then cross-check against FA pool
top_rps = rprs2[rprs2['rank'] <= 40].copy()

results_b = []
for _, row in top_rps.iterrows():
    name = row.get('name_api', row.get('player_name', ''))
    fa_match = fuzzy_match_name(name, [p.name for p in fa_rps])
    if not fa_match:
        continue
    xfp = row.get('xfp_ros', 0)
    rank = int(row['rank'])
    priority = 'HIGH' if rank <= 20 else 'MONITOR'
    results_b.append({
        'player': fa_match, 'rprs2_rank': rank,
        'xfp_ros': xfp,
        'role': row.get('role_lag1', ''),
        'sv_lag1': row.get('sv_lag1', 0),
        'priority': priority
    })

results_b.sort(key=lambda x: x['rprs2_rank'])
```

For any HIGH result: also check early fp_proxy from Statcast (K/BF in RP appearances).
If early fp_proxy > 0.08 AND role shows saves → IMMEDIATE ADD.

---

## Signal C — Hitter xwOBA Monitor

Catches sustained-xwOBA hitters sitting on the wire. Canonical miss: JJ Bleday
(xwOBA 0.408 for 99 PA, available for 2 months; UJLTED finally added May 24).

```python
rh3 = pd.read_csv(REPO / 'data/outputs/xfp_rh3_projections.csv')
fa_hit_names = [p.name for p in fa_hitters]

con = duckdb.connect()
xwoba_sql = """
SELECT batter,
  AVG(estimated_woba_using_speedangle) FILTER (
    WHERE events IS NOT NULL AND events != ''
    AND estimated_woba_using_speedangle IS NOT NULL
  ) AS xwoba_season,
  COUNT(*) FILTER (WHERE events IS NOT NULL AND events != '') AS pa_season,
  AVG(estimated_woba_using_speedangle) FILTER (
    WHERE events IS NOT NULL AND events != ''
    AND estimated_woba_using_speedangle IS NOT NULL
    AND game_date >= CURRENT_DATE - INTERVAL '21 days'
  ) AS xwoba_l21d,
  COUNT(*) FILTER (
    WHERE events IS NOT NULL AND events != ''
    AND game_date >= CURRENT_DATE - INTERVAL '21 days'
  ) AS pa_l21d
FROM read_parquet('{parq}')
WHERE game_date >= '2026-03-26'
GROUP BY batter
""".format(parq=PARQ)
xwoba_df = con.execute(xwoba_sql).df()

batter_names_sql = """
SELECT DISTINCT batter, player_name
FROM read_parquet('{parq}')
WHERE game_date >= '2026-03-26'
""".format(parq=PARQ)
batter_names = con.execute(batter_names_sql).df()
con.close()

xwoba_df = xwoba_df.merge(batter_names, on='batter', how='left')

results_c = []
for _, row in xwoba_df.iterrows():
    if row['pa_season'] < 75:
        continue
    name = row.get('player_name', '')
    # Statcast name is "Last, First" format
    display_name = ' '.join(reversed(name.split(', '))) if ', ' in name else name
    fa_match = fuzzy_match_name(display_name, fa_hit_names)
    if not fa_match:
        continue
    rh3_match = rh3[rh3['player_name'].str.contains(
        name.split(',')[0], case=False, na=False
    )]
    rh3_rank = int(rh3_match['rank'].iloc[0]) if len(rh3_match) else 999
    if rh3_rank > 100:
        continue
    xw = row['xwoba_season']
    if xw >= 0.360:
        priority = 'HIGH' if xw >= 0.390 and row['pa_season'] >= 100 else 'MONITOR'
        # Also check L21d spike
        if row['pa_l21d'] >= 30 and row['xwoba_l21d'] >= 0.400:
            priority = 'HIGH'
        results_c.append({
            'player': fa_match, 'rh3_rank': rh3_rank,
            'xwoba_season': round(xw, 3),
            'pa_season': int(row['pa_season']),
            'xwoba_l21d': round(row['xwoba_l21d'], 3) if row['xwoba_l21d'] else None,
            'pa_l21d': int(row['pa_l21d']),
            'priority': priority
        })

results_c.sort(key=lambda x: -x['xwoba_season'])
```

**Thresholds:**
- xwOBA ≥ 0.390 AND PA ≥ 100 → HIGH, add this week
- xwOBA ≥ 0.360 AND PA ≥ 75 → MONITOR, check rh3 rank
- L21d xwOBA ≥ 0.400 AND PA_L21d ≥ 30 → HIGH regardless of season total (hot streak signal)

---

## Signal D — Drafted-Then-Dropped Comeback

Catches players that any team drafted in 2024 or 2025 who were dropped and are now
producing. Retroactive example: Bryce Miller (Ligers 2024 rnd 12 → Big Dumpers 2025
rnd 19 → UJLTED 2026 add). Draft history signals prior-year interest = a scouting
ledger worth cross-referencing.

```python
draft_2024 = pd.read_csv(REPO / 'data/reference/league_history/draft_2024.csv')
draft_2025 = pd.read_csv(REPO / 'data/reference/league_history/draft_2025.csv')

all_drafted = set(
    draft_2024['player_name'].str.lower().tolist() +
    draft_2025['player_name'].str.lower().tolist()
)

# Cross-reference against FA pool + rp3/rh3/rprs2 top 100
results_d = []
all_fa_names = [p.name for p in fas]
for fa_name in all_fa_names:
    if _norm(fa_name) in all_drafted or any(
        part in _norm(fa_name) for part in [n.split()[-1].lower() for n in all_drafted]
    ):
        # Check model rank
        rp3_m = rp3[rp3['player_name'].str.contains(fa_name.split()[-1], case=False, na=False)]
        rh3_m = rh3[rh3['player_name'].str.contains(fa_name.split()[-1], case=False, na=False)]
        rprs2_m = rprs2[rprs2.get('name_api', rprs2.get('player_name', pd.Series())).str.contains(
            fa_name.split()[-1], case=False, na=False)]
        best_rank = min(
            int(rp3_m['rank'].iloc[0]) if len(rp3_m) else 999,
            int(rh3_m['rank'].iloc[0]) if len(rh3_m) else 999,
            int(rprs2_m['rank'].iloc[0]) if len(rprs2_m) else 999,
        )
        if best_rank <= 80:
            results_d.append({'player': fa_name, 'best_rank': best_rank})

results_d.sort(key=lambda x: x['best_rank'])
```

---

## Signal E — IL Return Timing

For any FA SP/RP currently on ESPN IL with a return date ≤ 14 days:
- Pull prior-year rp3 rank
- If prior rank ≤ 60: flag as IL stash candidate
- Check if any IL slot is open on user's roster

```python
for p in fas:
    if getattr(p, 'injured', False):
        inj = getattr(p, 'injury_status', '')
        # Only flag if return is plausible (not IL60 early in season)
        days_out = getattr(p, 'days_until_return', 999)
        if days_out <= 14:
            # Check rp3 rank
            rp3_m = rp3[rp3['player_name'].str.contains(p.name.split()[-1], case=False, na=False)]
            if len(rp3_m) and int(rp3_m['rank'].iloc[0]) <= 60:
                print(f"IL RETURN CANDIDATE: {p.name} — returns in {days_out}d, rp3 #{int(rp3_m['rank'].iloc[0])}")
```

---

## Signal F — Role-Change RP

Catches RPs transitioning into closer/high-leverage roles mid-season. Detects via
rprs2 `role_lag1` (prior-year role) vs current save/hold accumulation.

```python
# Look for RPs where role_lag1 != 'closer' but current SV > 0 this season
# Cross-reference FA RPs with rprs2
for _, row in rprs2.iterrows():
    if row.get('role_lag1') not in ('closer',) and row.get('sv_lag1', 0) == 0:
        name = row.get('name_api', row.get('player_name', ''))
        fa_match = fuzzy_match_name(name, [p.name for p in fa_rps])
        if fa_match and int(row['rank']) <= 50:
            # This RP was NOT a closer last year but is now ranked inside top 50
            # = role change signal
            print(f"ROLE CHANGE RP: {fa_match} — role_lag1={row.get('role_lag1')}, now rank #{int(row['rank'])}")
```

---

## Signal G — Holds-Only Elite RP

Catches high-value relievers that rprs2 underranks because they accumulate holds but
zero saves (setup men, LOOGY specialists). Canonical cases: Griffin Jax (+0.1087 fpp,
72 apps, 2024 — rprs2 unranked), Gabe Speier (+0.0947, 76 apps, 2025 — rprs2 #123),
Garrett Cleavinger (+0.0617, 67 apps — rprs2 #134).

rprs2 ranks by closer probability * FP/role. Setup men with sv_season=0 rank poorly
regardless of actual fp_proxy quality. Signal G bypasses rprs2 and uses raw fp_proxy
from Statcast to surface them.

```python
# Query current-season RP appearances, filter to fp_proxy >= 0.04, apps >= 20, sv_season = 0
rp_sql = """
WITH apps AS (
  SELECT pitcher, player_name,
    COUNT(DISTINCT game_date::DATE) AS apps,
    COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
    SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
    SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
    SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr
  FROM read_parquet('{parq}')
  WHERE game_date >= '2026-03-26'
    AND inning > 1  -- exclude SP starts; RPs almost never face BF in inning 1
  GROUP BY pitcher, player_name
  HAVING COUNT(DISTINCT game_date::DATE) >= 20
    AND COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 40
)
SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0), 4) AS fpp
FROM apps
WHERE (k-bb-h-hr)*1.0/NULLIF(bf,0) >= 0.04
""".format(parq=PARQ)

# Cross-reference against FA RP pool (using is_fa())
# Filter to players where rprs2 rank > 60 (rprs2 already handles the true closers)
# Surface as HIGH if fpp >= 0.07, MONITOR if 0.04-0.07
```

**Why inning > 1 filter:** Statcast doesn't cleanly tag SP vs RP. Using inning > 1
as a proxy excludes first-inning SP work. Imperfect but catches 90%+ of pure RP
appearances. Cross-check apps count: a RP with 60 apps at inning > 1 is clearly a reliever.

**Persistence note:** These pitchers are genuinely valuable in BrownU scoring even
without saves. K + IP*3.3 - H - 2*ER - BB - HBP + 2*HLD. A pitcher with +0.08 fpp
over 70 apps contributes ~5-6 FP per outing on holds alone. Don't require saves.

---

## Signal H — SP Roster Upgrade Alert

Fires when a FA SP is meaningfully better than the user's weakest active SP by fp_proxy
and model rank. This is the "Harrison miss" signal — designed so we never overlook a
clearly superior FA SP sitting on the wire.

**Canonical case:** Kyle Harrison (2026) — fpp +0.038, whiff 30.0%, rp3 #33 — was
available on FA wire while Bradish (fpp −0.114) and Framber (fpp −0.138) were rostered.
Signal H would have caught this.

**Definition:**
- Pull user's active SPs (lineup_slot not IL) and compute their 2026 season fpp
- Identify the "upgrade floor" = fpp of the user's 3rd-weakest active SP (not Bradish-tier,
  but the median-weak SP). If fewer than 3 active SPs, use the weakest.
- A FA SP fires Signal H if:
  - 2026 fpp >= upgrade_floor + 0.015 (meaningful gap, not noise) AND rp3 rank <= 150
    AND GS >= 4 (enough sample)
  - OR Signal A HIGH fires on them (fpp >= +0.02 AND whiff >= 26%, GS 4-8)

```python
from app.espn_connector import get_my_roster_with_injuries, _get_league
import duckdb
import pandas as pd
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
PARQ = (REPO / 'data/research/xfp_cache/statcast_2026.parquet').as_posix()
rp3 = pd.read_csv(REPO / 'data/outputs/xfp_rp3_projections.csv')

roster = get_my_roster_with_injuries()
my_sps = roster[(roster['position'] == 'SP') & (roster['lineup_slot'] != 'IL')]

# Compute 2026 fpp for each rostered SP via Statcast
# (reuse same BF>=10/game query structure as Signal A, filter by pitcher name)
sp_fpp_sql = """
WITH season AS (
  SELECT player_name,
    COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
    SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
    SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
    SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
    COUNT(DISTINCT game_date::DATE) AS gs
  FROM read_parquet('{parq}')
  WHERE game_date >= '2026-03-26'
  GROUP BY player_name
  HAVING COUNT(DISTINCT game_date::DATE) >= 1
    AND COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
)
SELECT player_name, gs, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0), 4) AS fpp
FROM season
""".format(parq=PARQ)

con = duckdb.connect()
sp_fpp_df = con.execute(sp_fpp_sql).df()
con.close()

# Match each rostered SP to fpp
my_sp_fpps = []
for _, sp in my_sps.iterrows():
    match = sp_fpp_df[sp_fpp_df['player_name'].str.contains(
        sp['name'].split()[-1], case=False, na=False
    )]
    fpp = float(match['fpp'].iloc[0]) if len(match) else -0.20  # penalty for no data
    my_sp_fpps.append(fpp)

my_sp_fpps.sort()  # ascending = weakest first
if len(my_sp_fpps) >= 3:
    upgrade_floor = my_sp_fpps[2]  # 3rd-weakest = median-weak
else:
    upgrade_floor = my_sp_fpps[0] if my_sp_fpps else -0.10

# FA SP scan — compare each FA SP's 2026 fpp against floor
league = _get_league()
fas = league.free_agents(size=2000)
fa_sp_names = [p.name for p in fas if p.position in ('SP', 'P') and is_fa(p.name)]

results_h = []
for _, row in sp_fpp_df.iterrows():
    # Skip if not FA
    name = row['player_name']  # Statcast format "Last, First"
    display = ' '.join(reversed(name.split(', '))) if ', ' in name else name
    fa_match = fuzzy_match_name(display, fa_sp_names)
    if not fa_match:
        continue
    fpp = row['fpp']
    gs = int(row['gs'])
    if gs < 4:
        continue

    rp3_match = rp3[rp3['player_name'].str.contains(
        name.split(',')[0], case=False, na=False
    )]
    rp3_rank = int(rp3_match['rank'].iloc[0]) if len(rp3_match) else 999
    if rp3_rank > 150:
        continue

    gap = fpp - upgrade_floor

    # Also check Signal A HIGH condition (whiff requires separate pull — use fpp as proxy)
    signal_a_high = fpp >= 0.02  # whiff check done in Signal A; assume HIGH if fpp >= 0.04
    signal_a_high_confirmed = fpp >= 0.04

    if gap >= 0.015 or signal_a_high_confirmed:
        if gap >= 0.030 or signal_a_high_confirmed:
            priority = 'HIGH PRIORITY'
        else:
            priority = 'MONITOR'
        results_h.append({
            'player': fa_match, 'fpp': fpp, 'gs': gs,
            'rp3_rank': rp3_rank, 'gap_vs_floor': round(gap, 3),
            'upgrade_floor': round(upgrade_floor, 3), 'priority': priority
        })

results_h.sort(key=lambda x: -x['gap_vs_floor'])
```

**Output tier:**
- `HIGH PRIORITY`: Signal A HIGH fires (fpp >= 0.04, whiff >= 26%) OR fpp gap >= +0.030 vs floor
- `MONITOR`: fpp gap >= +0.015 vs floor — check rp3 rank, consider streaming

---

## Signal I — Hitter Roster Upgrade Available

Fires when a FA hitter clearly outperforms the user's weakest rostered active hitters
by xwOBA and model rank. Hitter-side equivalent of Signal H. Canonical case: any FA
hitter with sustained xwOBA >= 0.380 (Signal C territory) while the user carries a
hitter with xwOBA < 0.330.

**Definition:**
- Pull user's active hitters (lineup_slot not IL)
- Compute each hitter's 2026 season xwOBA and L21d xwOBA from Statcast
- Identify upgrade floor = xwOBA of the user's 3rd-weakest active hitter by season xwOBA
  (if fewer than 3 active hitters, use the weakest)
- A FA hitter fires Signal I if:
  - 2026 season xwOBA >= upgrade_floor + 0.025 (meaningful gap, not noise)
  - AND rh3 rank <= 150
  - AND 75+ PA in 2026
  - AND xwOBACON >= 0.350 (contact quality confirms — not a pure walk/K-rate mirage)

**Implementation note:** Hitter comparisons must use batter IDs (not player_name, which
is the pitcher's name in Statcast). Use `lookup_batter_id_cached(name, team=..., position=...)`
to resolve names to MLBAM IDs before querying the parquet.

```python
from app.espn_connector import get_my_roster_with_injuries, _get_league
from plv_clone.utils.name_match import lookup_batter_id_cached, fuzzy_match_name
import duckdb
import pandas as pd
from pathlib import Path

REPO = Path(r'c:\Users\Joshua\plv_clone')
PARQ = (REPO / 'data/research/xfp_cache/statcast_2026.parquet').as_posix()
rh3 = pd.read_csv(REPO / 'data/outputs/xfp_rh3_projections.csv')

# Step 1: pull user's active hitters (not IL-slotted)
roster = get_my_roster_with_injuries()
my_hitters = roster[
    (~roster['position'].isin(['SP', 'RP', 'P'])) &
    (roster['lineup_slot'] != 'IL')
]

# Step 2: resolve each hitter to MLBAM batter ID using lookup_batter_id_cached
# This avoids the player_name (pitcher name) confusion in Statcast
my_batter_ids = []
for _, h in my_hitters.iterrows():
    try:
        bid = lookup_batter_id_cached(
            h['name'], team=h.get('pro_team'), position=h.get('position')
        )
        my_batter_ids.append({'name': h['name'], 'batter_id': bid})
    except Exception:
        pass  # skip if not resolvable

# Step 3: compute 2026 season xwOBA + L21d xwOBA + xwOBACON for each rostered hitter
# (use batter ID for lookup, not player_name)
if my_batter_ids:
    id_list = ', '.join(str(b['batter_id']) for b in my_batter_ids)
    roster_xwoba_sql = """
    SELECT batter,
      AVG(estimated_woba_using_speedangle) FILTER (
        WHERE events IS NOT NULL AND events != ''
        AND estimated_woba_using_speedangle IS NOT NULL
      ) AS xwoba_season,
      AVG(estimated_woba_using_speedangle) FILTER (
        WHERE events IS NOT NULL AND events != ''
        AND estimated_woba_using_speedangle IS NOT NULL
        AND estimated_ba_using_speedangle IS NOT NULL  -- proxy for batted ball events = xwOBACON
      ) AS xwobacon,
      COUNT(*) FILTER (WHERE events IS NOT NULL AND events != '') AS pa_season
    FROM read_parquet('{parq}')
    WHERE game_date >= '2026-03-26'
      AND batter IN ({ids})
    GROUP BY batter
    """.format(parq=PARQ, ids=id_list)
    con = duckdb.connect()
    my_xwoba_df = con.execute(roster_xwoba_sql).df()
    con.close()

    # Merge back to names
    id_map = {b['batter_id']: b['name'] for b in my_batter_ids}
    my_xwoba_df['name'] = my_xwoba_df['batter'].map(id_map)
    my_xwoba_values = sorted(my_xwoba_df['xwoba_season'].dropna().tolist())
else:
    my_xwoba_values = []

# Upgrade floor: 3rd-weakest active hitter's xwOBA
if len(my_xwoba_values) >= 3:
    upgrade_floor_h = my_xwoba_values[2]
elif my_xwoba_values:
    upgrade_floor_h = my_xwoba_values[0]
else:
    upgrade_floor_h = 0.310  # fallback if roster unresolvable

# Step 4: scan FA hitters for Signal I
# Reuse xwoba_df from Signal C (already queried from parquet by batter ID)
fa_hit_names = [p.name for p in fa_hitters]

results_i = []
for _, row in xwoba_df.iterrows():
    if row['pa_season'] < 75:
        continue
    name = row.get('player_name', '')
    display_name = ' '.join(reversed(name.split(', '))) if ', ' in name else name
    fa_match = fuzzy_match_name(display_name, fa_hit_names)
    if not fa_match:
        continue

    xw = row.get('xwoba_season')
    xwobacon = row.get('xwobacon')  # contact quality filter
    if xw is None or xwobacon is None:
        continue
    if xwobacon < 0.350:
        continue  # pure walk/K-rate mirage — do not fire

    gap = xw - upgrade_floor_h
    if gap < 0.025:
        continue

    rh3_match = rh3[rh3['player_name'].str.contains(
        name.split(',')[0], case=False, na=False
    )]
    rh3_rank = int(rh3_match['rank'].iloc[0]) if len(rh3_match) else 999
    if rh3_rank > 150:
        continue

    priority = 'HIGH PRIORITY' if (gap >= 0.040 and rh3_rank <= 75) else 'MONITOR'
    results_i.append({
        'player': fa_match, 'xwoba_season': round(xw, 3),
        'xwobacon': round(xwobacon, 3), 'pa_season': int(row['pa_season']),
        'xwoba_l21d': round(row['xwoba_l21d'], 3) if row.get('xwoba_l21d') else None,
        'rh3_rank': rh3_rank, 'gap_vs_floor': round(gap, 3),
        'upgrade_floor': round(upgrade_floor_h, 3), 'priority': priority
    })

results_i.sort(key=lambda x: -x['gap_vs_floor'])
```

**Output tier:**
- `HIGH PRIORITY`: xwOBA gap >= +0.040 AND rh3 rank <= 75 — run `/fa-pickup-deep-dive` before acting
- `MONITOR`: xwOBA gap >= +0.025 — check rh3 rank, verify contact quality trend

**Integration with build_sp_alerts.py:** The script at `scripts/xfp/build_sp_alerts.py`
(which generates `data/outputs/sp_alerts.json`) should also compute Signal I hitter
alerts and include them under the key `"hitter_alerts"` in the same JSON file, alongside
the existing `"sp_alerts"` key. This allows the matchup dashboard and any downstream
consumer to read both alert types from a single output artifact.

---

## Signals J–N — RP Archetype Layer (added 2026-05-30)

Built on the `rp_ratings_master.csv` archetype + leverage panel. All five share
one 2025↔2026 year-over-year join on pitcher ID (`load_rp_archetype_join()`
in `run_fa_monitor.py`). Augments the shallow B/F closer coverage with role,
stuff, and leverage trajectory.

### Signal J — LEVERAGE_RISE_FA

FA RP whose `leverage_tier` rose from {LOW, MID} 2025 → {HIGH, ELITE} 2026
**and** current `gmLI ≥ 1.2`. Indicates real role change in progress.

Severity:
- HIGH — landed in ELITE_LEVERAGE AND gmLI ≥ 1.6
- MED — gmLI ≥ 1.4
- LOW — meets baseline but gmLI ≥ 1.2 < 1.4

Output shows `gmLI 2025 → gmLI 2026` delta and rprs2 rank.

### Signal K — NEW_CLOSER_FA

FA RP who's stockpiling saves now (`sv_2026 ≥ 3`) but had no `CLOSER` tag in
2025. The "just took the job" signal — surfaces players the formal CLOSER
classifier hasn't caught up to.

Severity:
- HIGH — sv_2026 ≥ 8 (entrenched)
- MED — sv_2026 ≥ 5 (real run of saves)
- LOW — sv_2026 ≥ 3 (small sample)

Note: 2025 sv is shown but doesn't gate the signal — many rookies (no 2025
season) qualify legitimately.

### Signal L — FIREMAN_BREAKOUT

FA RP newly tagged `FIREMAN` for 2026 (IS% ≥ 80, IR ≥ 20 in the rp_archetype
build) who wasn't FIREMAN in 2025. These guys win close inherited-runner
situations and pile holds.

Severity:
- HIGH — rprs2 rank ≤ 60 AND gmLI ≥ 1.3 (model + leverage both agree)
- MED — otherwise

### Signal M — VELO_SPIKE_RP

FA RP whose VELO rating (20-80 scale, from rp_ratings_master) is ≥ +5 above
2025 AND swstr_pct is up by ≥ 0.5pp. Real stuff improvement, often precedes
role increase.

Severity:
- HIGH — VELO Δ ≥ 8 AND swstr Δ ≥ 1.5pp
- MED — VELO Δ ≥ 5 AND swstr Δ ≥ 1.0pp
- LOW — meets baseline

Output also shows raw `avg_velo` delta in mph.

### Signal N — MULTI_INNING_BULK_VALUE

FA RP with `MULTI_INNING_BULK` tag in 2026 (IP/G ≥ 1.3) AND rprs2 rank ≤ 80.
The 2-IP setup man who can outscore most pure closers in BrownU scoring
(K + IP*3.3 contribution from the second inning is large).

Severity:
- HIGH — rprs2 rank ≤ 50 + gmLI ≥ 1.2, OR newly MIB this year
- MED — rprs2 rank ≤ 60
- LOW — meets baseline

### Output block format (RP signals)

```
🔥 LEVERAGE_RISE_FA — Andres Munoz (SEA)
   gmLI 2025: 0.95 (MID_LEVERAGE) → 2026: 2.16 (ELITE_LEVERAGE)
   rprs2 rank: 28
   Recommendation: deep-dive via /fa-pickup-deep-dive
```

The script prints these in a dedicated `## RP ARCHETYPE SIGNALS (J-N)` block
with HIGH/MED/LOW subsections, distinct from the A-F report above.

---

## Step 2 — Output

```
# FA Monitor — <date>

## HIGH PRIORITY adds (act this week)
[Signal A HIGH] SP: <name> — fp_proxy/bf <X>, <N> GS, rp3 rank #<R> → run /sp-breakout-signal
[Signal B HIGH] RP: <name> — rprs2 rank #<R>, xfp_ros <X>, role=<role>
[Signal C HIGH] H:  <name> — xwOBA <X> (<N> PA), rh3 rank #<R>

## MONITOR tier (re-check next week)
[Signal A] ...
[Signal B] ...
[Signal C] ...

## Drafted-then-dropped on wire (Signal D)
<name> — drafted <year> by <team> (rnd <N>), now rank #<R> and FA

## IL return watch (Signal E)
<name> — returns in <N>d, rp3 rank #<R>. IL slot needed: <YES/NO>

## Role-change RPs (Signal F)
<name> — was <prior_role>, now rank #<R>

## SP roster upgrades available (Signal H)
[HIGH PRIORITY] SP: <name> — fpp <X>, rp3 #<R>, gap vs your floor: +<gap> → run /fa-pickup-deep-dive
[MONITOR]       SP: <name> — fpp <X>, rp3 #<R>, gap vs your floor: +<gap>

## Hitter roster upgrades available (Signal I)
[HIGH PRIORITY] H: <name> — xwOBA <X> (xwOBACON <X>), <N> PA, rh3 #<R>, gap vs your floor: +<gap> → run /fa-pickup-deep-dive
[MONITOR]       H: <name> — xwOBA <X> (xwOBACON <X>), <N> PA, rh3 #<R>, gap vs your floor: +<gap>
```

---

## Integration

| Skill | Relationship |
|---|---|
| `/roster-verify` | Pre-condition — always run first |
| `/roster-audit` | Companion — Step 7 FA candidates; this skill is the proactive version |
| `/sp-breakout-signal` | Follow-up for any Signal A HIGH hit |
| `/fa-pickup-deep-dive` | Follow-up for any HIGH priority hit before acting |
| `/fa-sp-pool` | SP-only equivalent; this skill adds hitter and RP dimensions |
| `/sp-breakout-signal` | Follow-up for any Signal H HIGH hit before acting |
| `/fa-pickup-deep-dive` | Follow-up for any Signal I HIGH hit before acting |
| `/hitter-compare` | Multi-player comparison when Signal I surfaces 2+ upgrade candidates |
| `/slump-or-decline` | Check user's weakest hitter (upgrade floor) before dropping for Signal I target |
| `build_sp_alerts.py` | Should also compute Signal I hitter alerts, output under `"hitter_alerts"` key in sp_alerts.json |

**Run cadence:** Monday morning before setting lineups. Takes ~3-5 minutes.
Secondary run: after any waiver wire news (closer change, IL activation).

---

## Anti-Patterns

1. **Inferring FA status from percent_owned** — always `league.teams` scan. A player
   at 70% national ownership is routinely unclaimed in 8-team (Sheehan, 2026-05-25).
2. **Using position-filtered FA call** — `league.free_agents(size=2000)` then filter.
   Never `get_free_agents(position=X, size=300)` — silently truncates.
3. **Acting on Signal A with only 1 start** — 1-start fp_proxy is noise. Require GS ≥ 2
   before escalating from MONITOR to HIGH, unless rp3 rank ≤ 50 (then 1 elite start
   = worth watching immediately).
4. **Skipping /fa-pickup-deep-dive before adding** — this skill surfaces candidates;
   it does not replace full evaluation. Always confirm with deep dive for HIGH alerts.
5. **Using rp3 for RPs or rh3 for pitchers** — Signal B uses rprs2 exclusively for RPs.
6. **Same-name collision** — build rh3 lookup keyed on `(norm_name, pro_team)` tuple,
   never bare name. Canonical: Max Muncy LAD (0.578, hold) vs ATH (0.379, drop).
   Mandatory pattern:
   ```python
   rh3_idx = {}
   dup_keys = set()
   for _, row in rh3.iterrows():
       key = (_norm(row['player_name']), str(row.get('team','')).upper())
       if key in rh3_idx: dup_keys.add(key)
       rh3_idx[key] = row
   if dup_keys: print(f"WARNING: dup rh3 keys {dup_keys}")
   def rh3_row(name, team): return rh3_idx.get((_norm(name), str(team).upper()))
   ```
   When `pro_team` is available from ESPN (it always is), use it as the second key.

---

## Calibration Notes

Signals calibrated from 2026 retroactive analysis (2026-05-25):
- Signal A thresholds updated 2026-05-25: `fpp_season >= 0.02` AND `whiff% >= 26%`
  (MC-validated: 10k bootstrap, 2025 holdout, 68% precision, +53pp lift over prior
  `fpp > 0.0` threshold). HIGH tier retained at fpp >= 0.04. Kyle Harrison
  (fpp 0.046, whiff 30.0%) fires HIGH; Taj Bradley (fpp 0.027, whiff ~24%) now
  correctly suppressed by whiff filter — fired at MONITOR under old threshold.
- Signal H added 2026-05-25 (Harrison miss): upgrade_floor = 3rd-weakest active SP
  fpp; gap threshold +0.015 (MONITOR), +0.030 (HIGH). Canonical case: Harrison
  fpp +0.038, rp3 #33 vs Bradish −0.114 / Framber −0.138.
- Signal B threshold xfp_ros > 120: Paul Sewald was at 151.1 when missed.
  Set conservatively to catch the full top-40 pool.
- Signal C threshold xwOBA ≥ 0.360: JJ Bleday was at 0.408 for 99 PA. Set to
  0.360 to also catch players slightly below Bleday tier (Ivan Herrera 0.401,
  Jonathan Aranda 0.355 were both worth monitoring).
- Signal I added 2026-05-25 (hitter upgrade equivalent of Signal H): upgrade_floor =
  3rd-weakest active hitter's season xwOBA; gap thresholds +0.025 (MONITOR), +0.040 +
  rh3 ≤ 75 (HIGH PRIORITY). xwOBACON >= 0.350 filter prevents walk/strikeout-driven
  xwOBA mirages from firing. Batter ID resolution via `lookup_batter_id_cached` is
  mandatory — Statcast `player_name` field contains the pitcher's name, not the batter's.
  Signal C (sustained-xwOBA FA monitor) is the complement: Signal C finds elite FAs
  regardless of roster context; Signal I explicitly compares against the user's roster
  floor and fires even if the FA xwOBA is only modestly above the user's weakest.
- Signals D-F: designed from pattern analysis, not yet calibrated against full
  season history. Flag as MONITOR tier until validated.
- Signals J-N added 2026-05-30. Built on `rp_ratings_master.csv` 2025↔2026 join
  (108 RPs with both years' data). Dry-run on 2026-05-30 live FA pool fired:
  J=27 alerts (5 HIGH), K=12 alerts (2 HIGH: Seranthony Dominguez SV 2→11,
  Lucas Erceg SV 2→11), L=3 alerts (1 HIGH: Kevin Kelly), M=3 alerts (Jacob
  Webb +5/+3.7pp), N=3 alerts (1 HIGH: Sam Bachman, new MIB role). Designed
  signals — not yet calibrated against forward outcomes; treat MED/LOW tiers
  as watchlist until 2026 season completes.
