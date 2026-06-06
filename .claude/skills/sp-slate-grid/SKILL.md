---
name: sp-slate-grid
description: Full-slate SP scan over a date window (default today + tomorrow) joining ALL 14 model layers — Blended xFP (Phase 3 production scorer with 95% bootstrap CI), rp3 rank + per_start band + opp_bat_index + recency_form_gap, live_marginal + value_tier (Phase 2.5 FA-pool-relative delta with SP floor), Triangulate verdict + reason_tag + confidence (synthesized BUY/HOLD/CAUTION/FADE/MIXED), Sustainability bucket (LEGIT/IMPROVING/STABLE/MIXED/NOISE/BAD_LUCK/REGRESS on rp3 with BUY-LOW/SELL-HIGH divergence flags), SP archetype master OVERALL + traj_flag + T+1, shadow_scout grade (20-80 ratings + PLUS_PROCESS/AVG_PROCESS/BELOW_AVG/NO_MLB_DATA for rookies/spot starts with no rp3 row), boom_stack 0-4 score + boom%/bust%/E[FP] from the validated tier-aware lookup + per-component breakdown (skill_spike / recform_hot / opp_soft / park_friendly), secondary boom tags (🔥 HIGH-K ARM standalone +6.84pp lift, 🧊 ELITE FRAMER / ⚠ FRAMING TAX within-pitcher paired p=0.017, 🚩 IL_RETURN salvage tag +2.93pp bust lift, ⚠ skill_spike_anti_predictive regression warning at SP2/3+Backend tiers), Process panel composite (PR 8 L30/STD/PriorYr SP marker decomposition with direction-adjusted z-score and level_pct), PL Top 100, PL daily streamer ranks with auto-fresh WebFetch when cache is stale and paywall fallback to nearest cached date. Tags ownership (MINE / opponent team name / FA) via league.teams roster walk. Renders a time-sorted multi-day grid with FA highlighted, decision-deadline header (first pitch ET), then synthesizes a boom-layer-aware top-FA recommendation that can DOWNGRADE high-rp3 picks when the live boom signal disagrees (canonical Emmet Sheehan 6/7/26 — rp3 #55 but boom 9/18 said skip; Cameron rp3 #85 with boom_stack 3/4 was the actual best play). Use when the user asks "rundown on all SP starts", "show me every SP start tomorrow", "what SPs are available across the slate", "all SP starts on DATE1 + DATE2 with FA highlighted", "use all models, every starter" or wants the full multi-day pitcher board not just their own roster. Engine pattern: probables from MLB Stats API + fa_sp_master.csv + sp_boom_stack_full_pool JSON + live_blend_xfp_latest.csv + sp_process_panel.csv + sp_ratings_master.csv + xfp_rp3_projections.csv + PL caches + on-demand shadow_scout and triangulate calls for shortlisted FAs — ALL joined on MLBAM pitcher_id (NOT name — same-name collisions like Logan Allen would silently break a name join, and ESPN's playerId is NOT MLBAM, canonical bug Castillo ESPN=33748 vs MLBAM=622491).
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

## What this skill produces (all 14 layers, ranked by empirical importance below)

For each scheduled SP start in the window:

| Layer | What it adds | Source | Cost |
|---|---|---|---|
| **MLB API probable** | Pitcher, MLBAM id, matchup, ET first pitch | `https://statsapi.mlb.com/api/v1/schedule` with `hydrate=probablePitcher,team` | net |
| **Ownership** | MINE / `<opp team name>` / FA | `league.teams` roster walk (NOT `get_all_teams()` — that returns strings) | API |
| **Blended xFP + 95% CI** | Production headline per-start projection (blends rp3 + archetype + PL + slope_3yr + HIGH-K + shadow features per validated weights) + bootstrap CI + confidence_tier | `data/outputs/live_blend_xfp_latest.csv` keyed on `mlbam_id` | file |
| **rp3** | Rank, per_start with p25/p75 band, opp_bat_index, recency_form_gap, data_quality_tag | `data/outputs/xfp_rp3_projections.csv` keyed on `pitcher` (MLBAM) | file |
| **live_marginal + value_tier** | FA-pool-relative delta (`target.ros − best_FA_at_role.ros`) + SP floor (`sp_floor_ros` bottom-25%) + tier (OWN_THE_ROLE / COMFORTABLE_HOLD / REPLACEABLE / DOWNGRADE / ACTIVE_LOSS) | `scripts/xfp/lib/blend_score.py::_compute_live_marginal_sp` (Phase 2.5 + PR 6 floor). Snapshot: `data/research/fa_snapshots/fa_pool_SP_latest.parquet` | compute |
| **Triangulate verdict** | Synthesized BUY / HOLD / CAUTION / FADE / MIXED + reason_tag + confidence (4 independent signals voting) | `scripts/xfp/lib/triangulate_core.py::triangulate_player(name)` — expensive at slate scale; **call only for shortlisted FAs (top 10 by Blended xFP)** | compute |
| **Sustainability bucket** | LEGIT / IMPROVING / STABLE / MIXED / NOISE / BAD_LUCK / REGRESS confidence layer on rp3 + BUY-LOW/SELL-HIGH divergence flag when sustainability disagrees by >1.5 FP/start | `scripts/xfp/pitcher_sustainability.py::classify(rows)` — compute on demand from rolling cache | compute |
| **SP archetype** | OVERALL, archetype label, traj_flag (UP/DOWN/STABLE/CAREER_LOW), T+1, slope_3yr | `data/research/sp_ratings_master.csv` keyed on `pitcher` (MLBAM), latest year | file |
| **shadow_scout** | 20-80 grades on FB velo / K% / BB% / whiff% / CSW% from 2026 Statcast percentiled vs live ~432-SP population. Verdict: PLUS_PROCESS / AVG_PROCESS / BELOW_AVG / NO_MLB_DATA. **Critical for rookies / spot starts with no rp3 row** | `scripts/xfp/lib/shadow_scout.py::shadow_card(mlbam_id)` — fallback ONLY when rp3 row is missing | compute |
| **Boom stack headline** | Live score 0-4 (`***.` style), per-component breakdown (skill_spike / recform_hot / opp_soft / park_friendly), **boom% / bust% / E[FP]** from validated tier-aware lookup | `data/outputs/sp_boom_stack_full_pool_<DATE>.json` `candidates` array, keyed on `pitcher_id` | file |
| **Boom secondary tags** | 🔥 HIGH-K ARM (standalone +6.84 pp boom edge); 🧊 ELITE FRAMER / ⚠ FRAMING TAX (catcher CSAA quintile, within-pitcher paired p=0.017); 🚩 IL_RETURN salvage tag (days since last MLB start ≥ 30, +2.93 pp bust lift); ⚠ skill_spike_anti_predictive (regression warning at SP2/3 + Backend tiers when K-spike + BB-drop fires, -3.4 to -4.1 pp at those tiers) | Same `sp_boom_stack_full_pool_<DATE>.json` under `season_only_tags` and `boom_components` — parse but render as compact emoji tags inline with boom_stack score | file |
| **Process panel composite** | PR 8 L30/STD/PriorYr SP marker decomposition (swstr / c_plus_swstr / o_swing / k_pct / bb_pct / hard_hit / barrel / xwoba_contact) with direction-adjusted z-score + level_pct | `data/outputs/sp_process_panel.csv` keyed on `pitcher` (MLBAM). Show as one composite score; full breakdown deferred to deep-dive | file |
| **PL Top 100** | Pitcher List weekly SP rank | `data/research/pl_cache/pl_sps_top100.json` | file |
| **PL streamer** | Daily streamer rank + tier (Auto / Probably / Questionable / DNS) + opp | `data/research/pl_cache/pl_sp_streamers_<DATE>.json` — **auto-refetch via WebSearch + WebFetch when cache is >2d stale**, with paywall-fallback to nearest cached date | file or WebFetch |

**Performance budget**: ~10 file joins (cheap, <1s) + triangulate calls capped at top-10 FAs by Blended xFP + shadow_scout only for rows with no rp3. Total skill runtime ~30-60s.

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

## Step 3 — Join all 14 model layers **on MLBAM pitcher_id**

**Critical:** ESPN's `playerId` is NOT the MLBAM id (canonical bug:
Castillo ESPN=33748 vs MLBAM=622491). The MLB Stats API probable hydrate
returns MLBAM directly. Join everything against THAT id.

```python
import pandas as pd, json, glob

# ── Layer 1: rp3 — keyed on `pitcher` column = MLBAM ────────────────────
rp3 = (pd.read_csv('data/outputs/xfp_rp3_projections.csv')
       .sort_values('rank').drop_duplicates('pitcher', keep='first'))
rp3_lookup = rp3.set_index('pitcher')[[
    'rank','xfp_rp3_per_start','xfp_rp3_p25','xfp_rp3_p75',
    'recency_form_gap','next_opp_bat_index','data_quality_tag'
]].to_dict('index')

# ── Layer 2: Blended xFP + 95% CI — production headline number ─────────
blend = pd.read_csv('data/outputs/live_blend_xfp_latest.csv')
blend_lookup = blend.set_index('mlbam_id')[[
    'live_blend_xfp','ci_lower','ci_upper','confidence_tier'
]].to_dict('index')

# ── Layer 3: SP archetype master — `pitcher` = MLBAM, latest year ──────
sp = pd.read_csv('data/research/sp_ratings_master.csv')
sp = sp[sp['year']==sp['year'].max()].drop_duplicates('pitcher', keep='first')
arch_lookup = sp.set_index('pitcher')[[
    'archetype','OVERALL','traj_flag','t1_fp_projection','OVERALL_slope_3yr'
]].to_dict('index')

# ── Layer 4: Boom stack JSON (incl. secondary tags) — keyed on pitcher_id
bs_files = sorted(glob.glob('data/outputs/sp_boom_stack_full_pool_*.json'))
with open(bs_files[-1]) as f:
    bs_data = json.load(f)
bs_lookup = {c['pitcher_id']: c for c in bs_data['candidates']}
# Each candidate dict carries: boom_stack score, boom_components,
# boom_rate_expected, boom_bust_rate_expected, boom_mean_fp_expected,
# tier, skill_spike_anti_predictive, season_only_tags{high_k_pitcher,
# catcher_framing, il_return}. Parse all of it — surface inline tags
# in render: 🔥 HIGH-K, 🧊 ELITE FRAMER / ⚠ FRAMING TAX, 🚩 IL_RETURN,
# ⚠ ANTI-PRED.

# ── Layer 5: Process panel composite (PR 8) ────────────────────────────
proc = pd.read_csv('data/outputs/sp_process_panel.csv')
proc_lookup = proc.set_index('pitcher')[[
    'composite','TREND_z','BASE_z','level_pct'
]].to_dict('index')

# ── Layer 6: PL Top 100 — keyed on name ────────────────────────────────
with open('data/research/pl_cache/pl_sps_top100.json') as f:
    pl_top = json.load(f).get('ranks', {})

# ── Layer 7: PL daily streamer ranks — see Step 4 for freshness gating ─
# (auto-fetch if cache >2d stale; paywall fallback to nearest cached date)

# ── Layers 8-10: live_marginal, Triangulate verdict, Sustainability ────
# These are COMPUTE-time (not file joins). Run ONLY for shortlisted FAs
# (top 10 by Blended xFP) to keep slate runtime under 60s.
from scripts.xfp.lib.blend_score import _compute_live_marginal_sp
from scripts.xfp.lib.triangulate_core import triangulate_player
from scripts.xfp.pitcher_sustainability import classify as sustain_classify

def deep_dive_fa(mlbam_id, name, target_ros):
    live_marg = _compute_live_marginal_sp(mlbam_id, target_ros)
    tri = triangulate_player(name)  # full 3-lens output
    sust = sustain_classify(_load_sustain_rows(mlbam_id))  # confidence layer
    return {
        'live_marginal': live_marg.get('live_marginal'),
        'live_value_tier': live_marg.get('live_value_tier'),
        'sp_floor_ros': live_marg.get('sp_floor_ros'),
        'sp_floor_marginal': live_marg.get('sp_floor_marginal'),
        'verdict': tri.get('verdict'),
        'verdict_top': tri.get('verdict_top'),
        'reason_tag': tri.get('reason_tag'),
        'confidence': tri.get('confidence'),
        'sustain_bucket': sust.get('bucket'),
        'sustain_divergence': sust.get('divergence_tag'),  # BUY-LOW/SELL-HIGH
    }

# ── Layer 11: shadow_scout — fallback for rows with NO rp3 row ─────────
from scripts.xfp.lib.shadow_scout import shadow_card

def shadow_for_rookie(mlbam_id):
    """Return PLUS_PROCESS / AVG_PROCESS / BELOW_AVG / NO_MLB_DATA verdict
    + 20-80 grades. Call ONLY when rp3_lookup.get(pid) is missing."""
    return shadow_card(mlbam_id)  # {'verdict','fb_velo_grade','k_grade',
                                  #  'bb_grade','whiff_grade','csw_grade'}
```

If `sp_boom_stack_full_pool_<today>.json` isn't present, the daily refresh
hasn't run; fall back to the newest file but warn (boom_stack rolls daily
because opp_soft + park_friendly are date-dependent).

**Compute budget contract:**
- File joins: cheap (<1s total).
- shadow_scout: only rows where `rp3_lookup.get(pid)` is missing AND the
  row is FA (don't waste compute on opp-rostered rookies).
- triangulate + live_marginal + sustainability: only for **top 10 FAs by
  Blended xFP**. Total: ~30-60s budget.

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

**Primary grid** (cheap layers, every start) — 14 columns:

`Time(ET) | Pitcher | Match | Own | xFP [CI] | rp3 #/per_start [p25-p75] | OppBat | RecForm | Arche/Traj | T+1 | BoomStk + Tags | Boom%/Bust% | E[FP] | ProcZ | PL | Streamer`

Where `BoomStk + Tags` packs the score `***.` with inline emoji for
secondary tags: `***. 🔥` = boom_stack 3/4 + HIGH-K; `**.. 🧊` = boom 2/4 +
elite framer; `**.. ⚠` = boom 2/4 + framing tax; `*... 🚩` = boom 1/4 +
IL_RETURN; `*... ⚠AP` = boom 1/4 + anti-predictive K-spike warning.

**FA shortlist deep-dive table** (compute layers, top 10 FAs by Blended xFP):

`Pitcher | Verdict (conf) | Reason | live_marginal | value_tier | floor_marg | Sust bucket | Divergence`

For rows with **no rp3** (rookies / spot starts), instead show
shadow_scout fallback grades:

`Pitcher | shadow_verdict | FB velo | K% | BB% | Whiff% | CSW%`

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

## Empirical importance ranking (read this when synthesizing the recommendation)

Below is the ranked importance of each layer for the **specific decision
problem of optimizing SP starts** — picking the right pitcher to add and
start when. Where empirical citations exist they are listed; where they
don't, the rank is honest qualitative judgment, marked `[qual]`.

This ranking informs which signal to weight when lenses disagree (the
Sheehan 6/7/26 case: rp3 #55 said BUY; boom_stack 0/4 said skip; boom
won because Tier 3 evidence is strong and tier-aware).

### Tier 1 — Headline projection (the actual point estimate; weight ~50%)

1. **Blended xFP + 95% CI** — *Production headline number.* Built by
   stacking rp3 + archetype + PL + slope_3yr + HIGH-K + shadow features
   with validated weights (`data/research/validation_runs/weight_blend_
   cleanup3_refit_2026-06-05.{md,json}`). Latest weight-refit deflated
   the per-start R² gain over rp3-only at ~0.02-0.03 incremental r — small
   but consistent and *the only signal that explicitly trades off all
   the others*. When this disagrees with rp3, trust the blend.

2. **rp3 per_start [p25-p75]** — *Validated single-model RoS projection.*
   The project's primary SP model with documented validation history
   (re-fit each daily refresh; LOO over 2019-2025 sans 2020). The p25-p75
   band carries hetero σ rescaled to historical calibration. rp3 IS one
   of the components of Blended xFP — when reading a row, ignore rp3 if
   Blended xFP is available; only use rp3 when blend is null
   (`pl_unavailable` / `rookie_or_no_prior_year` fallback).

### Tier 2 — FA-pickup decision modifiers (weight ~20% on top of headline)

3. **live_marginal + value_tier** — *Direct answer to "is this FA actually
   better than the best alternative?"* Built on Blended xFP so it inherits
   the headline accuracy AND adds the FA-pool-relative delta. Tiers
   (OWN_THE_ROLE / COMFORTABLE_HOLD / REPLACEABLE / DOWNGRADE / ACTIVE_LOSS)
   are calibrated against ros-delta cuts. The SP floor (`sp_floor_ros`,
   shipped PR 6 99d61ca) prevents the "above the best FA but below
   replacement-level" trap. Use when comparing 2+ FA candidates side-by-
   side.

4. **boom_stack score + boom%/bust%/E[FP]** — *Tier-aware live-state
   modifier.* Validated Mode B PASS at SHIP_AS_TAG (`data/research/
   validation_runs/boom_bust_deep_dive.md` and the tier-aware extension
   `boom_stack_by_tier.md` 2026-06-03). At ace tier stack=3, +14.8 pp
   boom-rate vs stack=0. At streamer tier stack=3, +8.0 pp. **Most
   powerful single-day "is the live state different from the season
   average?" signal we have.** Can override headline xFP when boom%/bust%
   sign-flip (Sheehan 9/18 case).

### Tier 3 — Independent tag layer (weight ~5-10% each, compounding)

5. **🔥 HIGH-K ARM** — Standalone +6.84 pp boom edge, p=2.6e-11, n=1,039,
   7/7 years positive (`data/research/validation_runs/boom_stack_v2_
   validation.md`, shipped 2026-06-03). Independent of boom_stack —
   *compounds* on top. Tier amplification +6.5 → +16.8 pp across v1
   stack=0→3.

6. **🧊 ELITE FRAMER / ⚠ FRAMING TAX** — Catcher CSAA quintile lookup;
   within-pitcher paired test n=208, t=2.40, p=0.017, +3.06 pp boom-rate
   gap (`data/research/validation_runs/catcher_framing_boom_modifier.md`).
   Fires only on Q5/Q1 tails. Canonical case Soriano-O'Hoppe (LAA, CSAA
   −0.85, WORST framer in MLB → automatic ⚠ TAX).

7. **🚩 IL_RETURN salvage tag** — Days since last MLB start ≥ 30 → +2.93 pp
   bust lift (n=640, p=0.044). Salvaged from rejected bust_stack_v2_context
   program; documented as standalone tag (`data/research/validation_runs/
   days_since_il_return_imp_grandfather.md`). Cross-reference with
   `/sp-rehab-tracker` for MiLB rehab outing quality.

8. **⚠ skill_spike_anti_predictive** — *Regression risk warning, NOT a
   boost.* At SP2/3 tier −3.4 pp, Backend tier −4.1 pp (`data/research/
   validation_runs/skill_spike_anti_predictive_diagnosis.md`,
   `skill_spike_tier_aware_validation.md`). Fires when K%-spike +
   BB%-drop combine at a sub-ace tier — the pattern that LOOKS like a
   breakout is actually mean-reversion ahead. Critical for FAs in the
   streamer / sp2_sp3 tiers.

### Tier 4 — Process / context layers (weight ~5%)

9. **Sustainability bucket (LEGIT / IMPROVING / STABLE / MIXED / NOISE /
   BAD_LUCK / REGRESS)** — *Confidence layer on rp3.* The most valuable
   output is the DIVERGENCE flag (>1.5 FP gap between sustainability
   decomp and rp3 → BUY-LOW / SELL-HIGH). The bucket itself is
   diagnostic — it explains WHY a per_start is moving but isn't a
   strong predictor by itself. `[qual]` — no published lift number on
   the sustainability bucket as a standalone signal; the divergence
   FLAG is what's been useful in practice. **Important caveat:** the
   analogous *hitter* BUY-LOW signal was REJECTED in the PR 8 backtest
   (pooled −0.069 FP/PA, 95% CI [−0.114, −0.023], commit 705defc). The
   SP version has NOT been re-validated against the same backtest — treat
   any "BUY-LOW SP" divergence flag with skepticism until re-run.

10. **shadow_scout grade (PLUS_PROCESS / AVG_PROCESS / BELOW_AVG /
    NO_MLB_DATA)** — *The only signal that gives you ANYTHING for rows
    where rp3 + archetype are both null.* High value at the rookie/spot-
    start margin; less impactful for established SPs (Blended xFP already
    incorporates shadow features via `shadow_velo_pct_prior` etc. for
    those that have rp3). Use as fallback verdict ONLY when the other
    layers return null. No standalone lift number published — this is
    a "fills the gap" layer, not a "lifts the projection" layer.

11. **Triangulate verdict (BUY / HOLD / CAUTION / FADE / MIXED + reason_tag
    + confidence)** — *Synthesis of PL + model + archetype + 4th-lens
    overrides.* Calibrated against the canonical case set (`docs/
    triangulate_calibration_2026.md`). Confidence = fraction of 4
    independent signals voting in agreement. Useful as a 10-second-scan
    headline but DON'T treat as additive lift — it's a *labeling* of the
    underlying lenses, not new information.

12. **SP archetype OVERALL + traj_flag + T+1** — *Process-based projection.*
    Less validated as a standalone predictor than rp3. The
    `archetype_breakout` triangulate rule (Rule #1) leans on traj_flag —
    when traj=TRENDING_UP AND archetype_breakout fires, it's a buy
    signal in the 4-lens vote. T+1 is forward-looking (rest-of-season)
    and is INCLUDED in Blended xFP via `arche_overall_prior`. Standalone
    use: only as the trajectory column for the scan.

13. **Process panel composite (PR 8 L30/STD/PriorYr)** — *Direction-
    adjusted z-score on the 9 canonical SP markers.* Shipped this session
    (`scripts/xfp/build_process_panel.py`); BUY-LOW *hitter* validation
    was REJECTED at the production level, but the SP composite hasn't
    been backtested as a signal directly. Useful as a *secondary
    confirmation* of boom_stack's `skill_spike` component, not a
    standalone driver.

### Tier 5 — External benchmarks (weight as agreement/disagreement signal only)

14. **PL Top 100 rank** — *External benchmark with documented bias.*
    PL is rate-stat / 12-team-mindset; our model is BrownU points / 8-team.
    The DIVERGENCE between PL and rp3 is what's actionable
    (`archetype_breakout`, `model_anchored`, `FADE — PL chasing outcomes`
    are all *gap*-driven rules), NOT the absolute PL rank. Treat as
    a *4th lens* in the triangulate synthesis but not as an independent
    projection.

15. **PL daily streamer rank + tier** — Same bias caveats. Useful for
    *streamer-tier confirmation* when boom_stack agrees (Cameron 6/7/26:
    boom_stack 3/4 + streamer #14 + rp3 #85 = three-lens agreement on a
    cheap-ownership pickup). Auto-fetch via WebFetch when cache is stale;
    paywall-fallback when only the first day is non-pro.

### Tier 6 — Data sources (required but not predictive)

16. **MLB API probables + ET first-pitch times** — Required for the
    decision-deadline framing but it's a data source, not a model.
17. **Ownership tags (MINE / opp / FA)** — Categorical filter, not
    predictive. Use for decision space (FA highlight) and the secondary
    "fade my opponent's pitcher" lens (their pitcher's xFP indirectly
    informs my matchup projection).

### How to use the ranking in synthesis

When all six "weighted ≥ 5%" lenses agree → strong signal, recommend.
When Tier 1 and Tier 2 disagree → trust Blended xFP unless boom_stack
boom%/bust% sign-flip is sharp; then weight boom_stack.
When Tier 3 tags compound (`***. 🔥 🧊`) → upgrade the recommendation.
When Tier 3 anti-predictive fires (`⚠ AP` on a SP2/3 with K-spike) →
downgrade despite hot recent line.
Tier 5 (PL ranks) alone is NEVER reason to add. PL agreement amplifies
a model BUY; PL disagreement alone doesn't beat the model.

### CRITICAL — Decision-horizon-aware reweighting (added 2026-06-06 after Cameron mis-call)

**The above weights are calibrated for ROS / multi-start decisions.** For
a one-shot single-start streamer pickup, the framework shifts:

- **Blended xFP loses weight** when its conservatism is anchored on
  `shadow_*_prior` or `traj_career_low_prior` (i.e. prior-season process
  tail risk that compounds across many starts but doesn't bind a single
  game). Check `marcel_baseline` vs `data_driven_estimate` — if they
  disagree by >2 FP, the blend may be over-penalizing.
- **boom_mean_fp_expected (from boom_stack JSON) becomes the central
  tendency for THIS start**, not the RoS-anchored Blended xFP. Use this
  when comparing FAs for a single-start pickup; use Blended xFP when
  comparing for a hold-the-roster-spot decision.
- **rp3_per_start_sched** (schedule-adjusted rp3) is the most direct
  single-start estimate when boom_stack is unavailable.
- **Recent inflection check**: pull last 4-6 MLB game logs via
  `https://statsapi.mlb.com/api/v1/people/<MLBAM>/stats?stats=gameLog&group=pitching&season=2026`
  and compute BrownU FP per start (`K + IP*3.3 - H - 2*ER - BB - HBP`).
  If the L4 average is materially above season per_start, the boom
  layer's `recform_hot` signal is corroborated and the prior-process
  drag in Blended xFP should be down-weighted for the one-start
  decision.

### Single-start vs RoS framework — concrete rule

| Decision type | Primary headline | Secondary | Tertiary |
|---|---|---|---|
| **Add for the roster (RoS)** | Blended xFP (Tier 1, 50%) | live_marginal value_tier | rp3 RoS |
| **One-shot streamer (single start)** | rp3_per_start_sched OR boom_mean_fp_expected (whichever is more recent / corroborated) | boom_stack tier-amp lift | recent 4-start actual FP/start |

Canonical case (Cameron 6/7/26): Blended xFP 6.89 (Tier 1) said skip
because prior-season velo 10th-pct + traj_career_low_prior dragged the
blend; boom_mean_fp_expected 10.6 + rp3 schedule-adj 10.51 + L4 actual
18.55 said legitimate single-start play. For a one-shot streamer pickup
the correct call was BUY despite the low Blended xFP.

### CRITICAL — Tag verification rule (added 2026-06-06 after Cameron mis-call)

**NEVER render an emoji tag without verifying the boolean in the
boom_stack JSON.** I shipped a slate with `🔥 HIGH-K` on Cameron when
his z-score was +0.28 (below the +0.5 threshold). The validated tags
fire only on the documented thresholds:

```python
def boom_tags(candidate: dict) -> str:
    """Build the tag string from the boom_stack JSON candidate.

    Reads BOOLEAN fields, not heuristics. Never emit an emoji unless
    the corresponding is_* flag is True.
    """
    sot = candidate.get('season_only_tags', {})
    parts = []
    if sot.get('high_k_pitcher', {}).get('is_high_k'):     # z >= +0.5
        parts.append('🔥')
    if sot.get('catcher_framing', {}).get('is_elite_framer'):  # Q5
        parts.append('🧊')
    if sot.get('catcher_framing', {}).get('is_framing_tax'):   # Q1
        parts.append('⚠F')
    if sot.get('il_return', {}).get('is_first_back_long_il'):  # >=30d
        parts.append('🚩')
    if candidate.get('skill_spike_anti_predictive'):  # SP2/3 + Backend only
        parts.append('⚠AP')
    return ''.join(parts)
```

**Reason check**: every JSON section has a `reason` field explaining
why a tag does/doesn't fire (`z=0.28_below_threshold`,
`gap_5d_below_threshold`, etc.). Surface the reason in the deep-dive
table when the user pushes back on a recommendation.

### CRITICAL — skill_spike anti-predictive is TIER-DEPENDENT

The skill_spike + BB-drop pattern is NOT universally bearish:

| Tier | skill_spike lift | Interpretation |
|---|---|---|
| ace (rank 1-10) | **+3.1 pp** | K-spike confirms ace stuff |
| sp2_sp3 (11-30) | **−3.4 pp** | Regression incoming — the K-spike is a peak the pitcher will lose |
| backend (31-50) | **−4.1 pp** | Same — anti-predictive |
| **streamer (51+)** | **+2.7 pp** | Continuation more likely than regression |

**`skill_spike_anti_predictive` only fires True when tier IN {sp2_sp3,
backend}.** At streamer or ace tier, the K-spike is a legit positive
signal. When walking through a Cameron-style "streamer with K-spike",
do NOT treat the skill_spike as a warning.

---

## Drop-target rule (added 2026-06-06 after Messick mis-call)

**When recommending an FA pickup that requires a drop**, you MUST first
rank the user's full SP staff by Blended xFP before naming a drop target.

The canonical failure (2026-06-06): I recommended dropping Parker Messick
to add Roki Sasaki, calling Messick "no rp3 row, rookie callup, no
validated signal." Messick actually had:

- rp3 **#63** per_start 10.68
- Blended xFP **14.68 [8.49-19.74] HIGH confidence** — the HIGHEST on the
  user's roster
- Archetype PURE_MOVEMENT OVERALL **65**, K% **28.2%**, BB% 6.4%
- HIGH-K verified (z=0.93)
- 13 MLB starts (data_driven_full)

The error: he wasn't on the 6/6-6/7 slate (last start 6/5), so my
slate-grid query never joined his row. I extrapolated "not in this
window" → "no data" without checking the underlying files directly.

### Rule

Before naming ANY drop target:

```python
# 1. Pull user's roster
from app.espn_connector import get_my_roster_with_injuries
roster = get_my_roster_with_injuries()
my_sps = roster[roster['position']=='SP']

# 2. Join rp3 + blend by MLBAM via Last,First flip on name
rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
blend = pd.read_csv('data/outputs/live_blend_xfp_latest.csv')
# ... build {name: blended_xfp} for each rostered SP ...

# 3. Rank staff descending. Drop candidates start at the BOTTOM.
# Never name a drop target without showing the proposed drop's
# Blended xFP next to the FA add's Blended xFP.
```

### Synthesis output requirement

Any drop/add recommendation table MUST include:

```
| What you give up (drop) | Blended xFP | What you gain (add) | Blended xFP |
```

When the drop's Blended xFP > add's Blended xFP, STOP and re-evaluate
before recommending the swap. Either pick a different drop or
acknowledge the trade is RoS-negative (and explain WHY anyway — e.g.,
"streamer rental for this week's 10th cap start").

## Anti-patterns this skill exists to prevent

- **Calling a rostered player "no data" because they're not on the
  slate's date window.** Slate-grid only joins data for pitchers IN the
  target probables. A rostered SP not pitching that day is invisible to
  the slate join but is FULLY PRESENT in rp3 + blend + sp_master +
  process_panel + boom_stack JSON. Always query by MLBAM directly.
- **Recommending a drop without ranking the user's full SP staff by
  Blended xFP first.** Canonical Messick failure 2026-06-06.
- **Pattern-matching "rookie callup" → "no validated signal".** Rookies
  with 10+ MLB starts have data_driven_full rp3 rows. Always check.
- **Rendering an emoji tag without verifying the boolean field in the
  JSON.** Canonical bug 2026-06-06: I tagged Cameron `🔥 HIGH-K` while
  his `is_high_k: false, reason: "z=0.28_below_threshold"`. Always read
  the boolean, never infer the tag from per_start or recent K count.
- **Applying the RoS-calibrated Tier 1 weighting to a single-start
  decision.** Blended xFP's conservatism comes from `shadow_*_prior` +
  `traj_career_low_prior` tail risk that compounds across N starts.
  For one start, use `boom_mean_fp_expected` or `rp3_per_start_sched`
  as the central tendency.
- **Treating skill_spike as a universal regression warning.** It's
  bearish ONLY at sp2_sp3 + backend tiers. At streamer + ace tiers it
  CONFIRMS a real K-rate development.
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

- `/boom-bust-history` — **variance lens companion**. When the model
  layer (rp3 + Blended xFP + archetype) gives a verdict but you want
  hard evidence of recent form, invoke `/boom-bust-history --names
  "X,Y"` for the L8-starts decomposition (boom% ≥20 FP, bust% <5 FP,
  std, trend arrow). Canonical case: Bradish blend 5.98 vs L5 actuals
  17.88 — boom-bust history reveals the model is 12 FP behind reality.
  Especially useful before drop/keep decisions and when surveying
  IL'd returners (auto-fallback to prior year — Hunter Greene 2025).
- `/fa-sp-pool` — flat FA-only ranked list (no grid, no synthesis)
- `/sp-week-plan` — my-roster weekly cap math
- `/stream-the-stack` — my-eligible-pool filtered by boom tier
- `/triangulate` — single/few player 3-lens deep dive
- `/boom-stack-explain` — decompose one pitcher's current boom_stack
- `/sp-stash-finder` — IL stash candidates with playoff timing
