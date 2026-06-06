---
name: sp-slate-grid
description: Full-slate SP scan over a date window (default today + tomorrow). Pulls EVERY scheduled SP start from MLB Stats API, joins all six model layers (rp3 rank + per_start band, SP archetype master OVERALL/traj/T+1, live boom_stack score + boom%/bust% + E[FP] expected from the validated tier-aware lookup, PL Top 100, PL daily streamer ranks with auto-fresh WebFetch when cache is stale), tags ownership (MINE / opponent team name / FA), renders a time-sorted grid with FA highlighted and a decision-deadline header, then synthesizes a boom-layer-aware top-FA recommendation that can DOWNGRADE high-rp3 picks when the live boom signal disagrees (canonical case Emmet Sheehan 6/7/26 — rp3 #55 but boom 9/18 said skip). Use when the user asks "rundown on all SP starts", "show me every SP start tomorrow", "what SPs are available across the slate", "all SP starts on DATE1 + DATE2 with FA highlighted", "use all models" or wants the full multi-day pitcher board not just their own roster. Engine pattern: probables.pkl + fa_sp_master.csv + sp_boom_stack_full_pool JSON + PL caches, all joined on MLBAM pitcher_id (NOT name — same-name collisions like Logan Allen would silently break a name join).
---

# sp-slate-grid

You are rendering the **full SP slate** for a date window — every scheduled
starter, not just the user's roster, not just FAs — with all six model
lenses joined and the user's ownership status (MINE / opp team / FA)
tagged on each row. The user needs to see the whole board because their
decision space includes any FA pickup, any opponent's pitcher (for fade
context), and their own roster (for what's already locked).

The skill exists because we built this manually on 2026-06-06 across
multiple sequential queries — first FA-only, then "highlight FA in every
start," then "include archetype + boom_stack + fresh streamer ranks." Doing
it in one pass is materially better.

## What this skill produces (and what each layer adds)

For each scheduled SP start in the window:

| Lens | What it adds | Source |
|---|---|---|
| **MLB API probable** | Pitcher, MLBAM id, matchup, ET first pitch | `https://statsapi.mlb.com/api/v1/schedule` with `hydrate=probablePitcher,team` |
| **Ownership** | MINE / `<opp team name>` / FA | `league.teams` roster walk (NOT `get_all_teams()` — that returns strings) |
| **rp3** | Rank, per_start with p25/p75 band, opp_bat_index, recency_form_gap, data_quality_tag | `data/outputs/xfp_rp3_projections.csv` keyed on `pitcher` (MLBAM) |
| **SP archetype** | OVERALL, archetype label, traj_flag (UP/DOWN/STABLE/CAREER_LOW), T+1 projection | `data/research/sp_ratings_master.csv` keyed on `pitcher` (MLBAM), latest year |
| **Boom stack** | Live score 0-4 (`***.` style), per-component breakdown, **boom% / bust% / E[FP]** from the validated tier-aware lookup | `data/outputs/sp_boom_stack_full_pool_<DATE>.json` `candidates` array, keyed on `pitcher_id` |
| **PL Top 100** | Pitcher List weekly SP rank | `data/research/pl_cache/pl_sps_top100.json` |
| **PL streamer** | Daily streamer rank + tier (Auto / Probably / Questionable / DNS) + opp | `data/research/pl_cache/pl_sp_streamers_<DATE>.json` — **auto-refetch via WebSearch + WebFetch when cache is >2d stale**, with paywall-fallback to nearest cached date |

The output is one markdown table per day, sorted by start time, with a
**decision-deadline header** (first pitch ET) so the user knows their
cutoff for that day's adds. FAs are bolded with 🟢 and the user's pitchers
with 🟦.

## Why a new skill (not `/fa-sp-pool` or `/sp-week-plan`)

- `/fa-sp-pool` returns FA-only and a single ranked list. Doesn't show OPP
  pitchers or rendered as a time-sorted grid.
- `/sp-week-plan` is roster-side weekly cap math. It doesn't enumerate FAs
  or render every league start.
- `/stream-the-stack` filters to my-eligible-pool + boom tier; doesn't show
  the full slate.

This skill is the **decision surface BEFORE picking up** — the grid you
look at to decide between Castillo / Sheehan / Cameron / Drohan / Leiter
with all signals visible at once.

## Trigger phrases

"all SP starts on DATE", "every SP start tomorrow", "rundown on all FA SP",
"show me the full SP slate", "highlight the FA SPs across the next N days",
"use all models, every starter", "SP board for DATE1 and DATE2",
"pitcher slate with boom_stack".

## Inputs

1. **Date window** — default `[today, today+1d]`. Accept `today`,
   `tomorrow`, an ISO date, or a range like `6/6 6/7`. Hard cap window at
   5 days (more than that is `/sp-week-plan` territory).
2. **Include rostered?** — default YES (show everyone, FAs highlighted).
   If the user says "FA only" then filter at render time but still
   compute the full join (so the synthesis section can reference the
   landscape).

---

## Step 1 — Pull all probables for the window

```python
import requests
from datetime import datetime
import pytz

eastern = pytz.timezone('America/New_York')
games = []
for d in window_dates:  # list of ISO date strings
    url = (
        f'https://statsapi.mlb.com/api/v1/schedule'
        f'?sportId=1&date={d}&hydrate=probablePitcher,team'
    )
    r = requests.get(url, timeout=20).json()
    for g in r.get('dates', [{}])[0].get('games', []):
        gd = g.get('gameDate')  # UTC ISO
        et_time = (
            datetime.fromisoformat(gd.replace('Z','+00:00'))
            .astimezone(eastern).strftime('%I:%M %p ET')
            if gd else 'TBD'
        )
        h = g['teams']['home']; a = g['teams']['away']
        for side, opp_side, ha in [(a, h, '@'), (h, a, 'vs')]:
            sp = side.get('probablePitcher', {})
            if sp.get('id'):
                games.append({
                    'date': d, 'time_et': et_time,
                    'sp_name': sp['fullName'], 'sp_id': sp['id'],
                    'team': side['team']['abbreviation'],
                    'opp':  opp_side['team']['abbreviation'],
                    'home_away': ha,
                })
```

Note the **first pitch ET** of the EARLIEST game on day 1 — that's the
decision deadline header for that day. If today is the first day in the
window, the user has until that time to add.

TBD probables: include the row with `sp_name='TBD'` and skip the model
joins. Surface "TBD" in the rendered output — the user may want to know
which games haven't named a starter yet.

---

## Step 2 — Ownership lookup

```python
from app.espn_connector import _get_league
league = _get_league()

# Build {normalized_name: team_name} from league.teams.
# DO NOT use get_all_teams() — that returns strings, not Team objects.
import unicodedata
def _norm(s):
    return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

owner_map = {_norm(p.name): t.team_name for t in league.teams for p in t.roster}
MY_TEAM = 'New York Ligers'  # adjust per user
```

For each game row, compute the ownership tag:

```python
owner = owner_map.get(_norm(sp_name), 'FA')
if owner == MY_TEAM:
    own_tag = 'MINE'
elif owner == 'FA':
    own_tag = 'FA'
else:
    own_tag = owner[:14]  # truncate opp team name for column width
```

---

## Step 3 — Join all six model layers **on MLBAM pitcher_id**

**Critical:** ESPN's `playerId` is NOT the MLBAM id (canonical bug:
Castillo ESPN=33748 vs MLBAM=622491). The MLB Stats API probable hydrate
returns MLBAM directly. Join everything against THAT id.

```python
import pandas as pd, json

# rp3 — keyed on `pitcher` column = MLBAM
rp3 = (pd.read_csv('data/outputs/xfp_rp3_projections.csv')
       .sort_values('rank').drop_duplicates('pitcher', keep='first'))
rp3_lookup = rp3.set_index('pitcher')[[
    'rank','xfp_rp3_per_start','xfp_rp3_p25','xfp_rp3_p75',
    'recency_form_gap','next_opp_bat_index','data_quality_tag'
]].to_dict('index')

# SP archetype master — `pitcher` = MLBAM; filter to latest year
sp = pd.read_csv('data/research/sp_ratings_master.csv')
sp = sp[sp['year']==sp['year'].max()].drop_duplicates('pitcher', keep='first')
arch_lookup = sp.set_index('pitcher')[[
    'archetype','OVERALL','traj_flag','t1_fp_projection'
]].to_dict('index')

# Boom stack — TODAY'S JSON, keyed on pitcher_id
import glob
bs_files = sorted(glob.glob('data/outputs/sp_boom_stack_full_pool_*.json'))
with open(bs_files[-1]) as f:
    bs_data = json.load(f)
bs_lookup = {c['pitcher_id']: c for c in bs_data['candidates']}

# PL Top 100 — keyed on name
with open('data/research/pl_cache/pl_sps_top100.json') as f:
    pl_top = json.load(f).get('ranks', {})
```

If `sp_boom_stack_full_pool_<today>.json` isn't present, the daily refresh
hasn't run; fall back to the newest file but warn (boom_stack rolls daily
because opp_soft + park_friendly are date-dependent).

---

## Step 4 — PL streamer cache freshness + auto-refetch

PL streamer ranks are **the most decision-relevant lens** but the cache
goes stale fast. Schema: `data/research/pl_cache/pl_sp_streamers_<DATE>.json`
with `ranks = {name: {rank, tier, opp}}`. The skill MUST:

1. Try to load a cache file dated `<window_day>`.
2. If it doesn't exist OR `fetched` date is >2 days stale, **WebFetch
   the current article**:
   - WebSearch: `pitcherlist.com SP streamer ranks <month>/<day_n> <month>/<day_n+1> 2026` with `allowed_domains=['pitcherlist.com']`
   - WebFetch the URL with the prompt: "Extract the FULL ranked list of starting pitchers for DATES. For each: date, rank within day, name, team@opponent, tier (Auto-Start / Probably / Questionable / Do Not Start). Plain text format."
3. Parse into the schema and write `data/research/pl_cache/pl_sp_streamers_<TODAY>.json`.
4. Handle paywall: PL pro members get the second/third day; non-pro returns
   "restricted." If a day is paywalled, fall back to the most recent cached
   day available for that date (mark with a `*` in the rendered output) and
   surface the staleness in the table footer.

```python
# Tier coercion when rendering:
TIER_TAG = {'AUTO':'AS','PROBABLY':'PS','QUESTIONABLE':'QS','DO_NOT':'DNS'}
def streamer_cell(name, day_streamers):
    sd = day_streamers.get(name)
    if not sd: return '—'
    rank = sd.get('rank') if isinstance(sd, dict) else sd
    tier = (sd.get('tier') or '') if isinstance(sd, dict) else ''
    return f'#{int(rank)} {TIER_TAG.get(tier,"")}'.strip()
```

---

## Step 5 — Render the time-sorted grid

ASCII-safe formatting (Windows cp1252 chokes on emoji unless you set
`PYTHONIOENCODING=utf-8` AND use `python -X utf8`):

```python
def fmt_per(r):
    if pd.isna(r['per_start']): return '—'
    return f"{r['per_start']:.1f} [{r['p25']:.1f}-{r['p75']:.1f}]"

def fmt_opp_bat(v):
    if pd.isna(v): return '—'
    tag = ' TGH' if v >= 1.05 else (' SFT' if v <= 0.95 else '')
    return f'{v:.2f}{tag}'

def fmt_recform(v):
    if pd.isna(v): return '—'
    tag = ' HOT' if v >= 3 else (' CLD' if v <= -3 else '')
    return f'{v:+.1f}{tag}'

def fmt_arch(r):
    if pd.isna(r['overall']): return '—'
    traj_map = {'TRENDING_UP':'^','TRENDING_DOWN':'v','STABLE':'-',
                'CAREER_LOW':'LO','CAREER_HIGH':'HI'}
    return f"{int(r['overall'])}{traj_map.get(r['traj'],'?')} {(r['archetype'] or '')[:14]}"

def fmt_boom(r):
    if pd.isna(r['boom_stack']): return '—'
    n = int(r['boom_stack'])
    return '*' * n + '.' * (4 - n)   # `***.` for 3/4

def fmt_boomrate(r):
    if pd.isna(r.get('boom_rate')): return '—'
    return f"{r['boom_rate']*100:.0f}/{r['bust_rate']*100:.0f}"
```

Columns to show:
`Time(ET) | Pitcher | Match | Own | rp3 | per_start [p25-p75] | OppBat | RecForm | Arche/Traj | T+1 | BoomStk | Boom%/Bust% | E[FP] | PL | Streamer`

Header per day:

```
## SATURDAY 6/6 — decision deadline 1:10 PM ET first pitch
```

FA rows: pitcher name **bolded**, ownership cell `🟢 FA`. User's rows:
`🟦 MINE`. Opp rows: plain opp-team-name (no emoji, keeps the table
scanable for the "fade my opponent's pitcher" lens).

---

## Step 6 — Synthesis (boom-aware FA ranking)

After the tables, append a `# Recommendation` section with:

1. **Top FA picks where rp3 + recform + boom_stack agree** — the cleanest
   adds. Examples surface like Cameron + Drohan on 6/7/26 (`***.` boom,
   recform HOT, rp3 sub-100).
2. **Boom-layer downgrades** — high-rp3 FAs where boom_stack = 0/4 and
   bust% > boom%. Surface as "demote despite rp3." Canonical case:
   Emmet Sheehan 6/7/26 rp3 #55 but boom 9%/bust 18%.
3. **Best single-day pick if user wants to act today** (Sat 6/6 in the
   canonical run: Jack Leiter).
4. **My-own-roster risk callouts** — when my pitcher has boom_stack=0
   and tough opp + cold recform (Soriano 6/7/26 vs LAD = bust risk).

Synthesis format:

```markdown
| Goal | Pick | Why |
|---|---|---|
| Best <day> FA play (combined signal) | <Pitcher> | <one-line synthesis across all 6 lenses> |
| ... | ... | ... |
| Skip | <Pitcher> | <which lens is downgrading> |
```

End with **one explicit call** ("My call: wait for Sun and grab Cameron")
so the user gets the decision baked, not just data dumped.

---

## Anti-patterns this skill exists to prevent

- **Joining by name** when ESPN's `playerId` is NOT MLBAM. The MLB Stats
  API hydrate returns MLBAM as `probablePitcher.id` — use THAT for all
  model joins. Name joins silently fail for "Last, First" SP master vs
  "First Last" ESPN.
- **Trusting a stale streamer cache** without checking the `fetched` date.
  Auto-refetch when >2d stale; explicitly mark cells from older articles
  with a `*` and surface staleness in a table footnote.
- **Using `get_all_teams()` for ownership lookup** — it returns strings,
  not Team objects. Use `league.teams` (Player objects with `.name`).
- **Ignoring TBD probables** — they're real games with real cap implications;
  show the row with empty model cells rather than dropping it.
- **Rendering with raw pandas in cp1252 shell** — Windows shells choke
  on unicode tier markers. Either ASCII-only (`***.` not `★★★☆`) or set
  `PYTHONIOENCODING=utf-8` AND `python -X utf8`.
- **Recommending the highest-rp3 FA without checking boom_stack.** When
  boom_stack = 0/4 and bust% > boom%, the live state today contradicts
  the season-anchored rp3. Canonical: Sheehan 6/7/26.
- **Forgetting opp bat-index tagging.** A pitcher facing a 1.10 opp_bat
  team needs the TGH tag prominent so the user doesn't miss the matchup.
- **Filtering to FAs only before the synthesis pass.** The opp-rostered
  pitchers tell you who you can FADE this week; that's decision-relevant
  even though you can't add them.

## When NOT to use this skill

- User asked for a single named player → use `/fa-pickup-deep-dive` or `/triangulate`.
- User asked specifically about THEIR own roster → use `/sp-week-plan`.
- User asked just for the boom_stack tag explanation → use `/boom-stack-explain`.
- User asked for IL stash candidates only → use `/sp-stash-finder`.
- User wants the FA list as a flat ranked CSV (no grid, no synthesis) →
  use `/fa-sp-pool` and skip the multi-day enrichment.
- User wants to scan ALL positions, not just SPs → that's a future
  `/slate-grid` parent skill, not yet built.

## Output canonical reference

Saved 2026-06-06 to `data/outputs/sp_slate_grid_2026-06-06_to_2026-06-07.md`
(when this skill is run, persist the output there so the user can re-read
without rebuilding). Save the joined CSV to
`C:/tmp/sp_slate_<window>.csv` for ad-hoc sort/filter.

## Related

- `/fa-sp-pool` — flat FA-only ranked list (no grid, no synthesis)
- `/sp-week-plan` — my-roster weekly cap math
- `/stream-the-stack` — my-eligible-pool filtered by boom tier
- `/triangulate` — single/few player 3-lens deep dive
- `/boom-stack-explain` — decompose one pitcher's current boom_stack
- `/sp-stash-finder` — IL stash candidates with playoff timing
