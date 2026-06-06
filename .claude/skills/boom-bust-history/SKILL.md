---
name: boom-bust-history
description: Historical actuals analysis with boom/bust/variance decomposition for any list of players (default — user's full roster including IL'd returners with cross-year fallback). Pulls last-N game logs from MLB Stats API (SP — L8 starts, hitter — L21 games, RP — L15 appearances; window configurable), computes BrownU FP per game using the canonical scoring formulas (SP/RP — `K + IP*3.3 − H − 2*ER − BB − HBP`, plus `5*SV + 2*HLD` for RP; hitter — `R + TB + RBI + BB + HBP + SB − K`), then surfaces position-aware boom%/bust% (SP — boom ≥20 / bust <5; hitter — boom ≥10 / bust <2; RP — boom ≥5 / bust <0) alongside L8/L5/L3 averages, std (variance), min/max range, and trend direction (L3 vs L5 vs L8). Auto-fallback to prior year for any player with insufficient current-year games (IL60+ stashes like Hunter Greene 2025 surface automatically). Tags ownership (MINE / opp / FA), injury status (ACT / BE / IL15 / IL60 + return date), and trend arrows. Renders a position-grouped table sorted by recent form, plus optional per-game detail blocks. Designed to surface the variance side of the projection picture that model layers (rh3/rp3/rprs2, Blended xFP, archetype) cannot — actuals show whether a SP is a 37% boom hot streak (Bradish) or 0% boom 25% bust cap-fodder (Valdez) regardless of what the model says. Use when the user asks "boom bust", "how consistent has X been", "who's been booming/busting", "show me actuals not just projections", "variance check on my roster", "last 8 starts breakdown", "is X really hot or just lucky", "rank my SPs by boom rate", "roster variance audit", or wants to verify a model's projection with hard recent-actuals evidence. Engine pattern — `name_to_mlbam` via name flip + norm + KNOWN_COLLISIONS guard, MLB Stats API gameLog per player, position bucket auto-detect from rh3/rp3/rprs2 join, boom/bust threshold lookup by bucket, cross-year fallback when current-year n < 5 (Hunter Greene case), output sorted by L5 avg desc within position group, with model-projection cross-reference column (Blended xFP / rp3 per_start / rh3 per_game) showing where actuals disagree.
---

# boom-bust-history

You are rendering the **variance-aware historical-actuals view** of a
player set. This is the lens that complements `/sp-slate-grid`,
`/hitter-slate-grid`, and `/triangulate` — those skills show what the
model projects; this skill shows what's actually been happening.

The skill exists because the model layers (Blended xFP, rp3, rh3,
archetype) anchor on career-long signal. Recent actuals can diverge
sharply — Bradish's blend says 5.98 (streamer tier) but his actual L5
is 17.88 FP/start with 37% boom rate. Without the actuals, the user
makes drop decisions on stale model verdicts.

## Trigger phrases

"boom bust", "how consistent has X been", "who's been booming/busting",
"variance check", "actuals not just projections", "last 8 starts
breakdown", "last 21 games breakdown", "is X really hot",
"rank my SPs by boom rate", "rank my hitters by boom rate",
"roster variance audit", "show me consistency",
"L5 vs L3 trend on X", "boom percent on Y", "bust risk on Z".

## What this skill produces

For each player in scope:

| Field | Description |
|---|---|
| **Status** | ACT (active P/H slot) / BE (bench healthy) / IL15 / IL60 (with return date) |
| **Source year** | Year(s) the data came from. Annotated when fallback fired |
| **N starts/games** | Sample size pulled |
| **L8 avg** (SP) or **L21 avg** (H) or **L15 avg** (RP) | Long-window average FP/game |
| **L5 avg** | Mid-window average FP/game (5 most recent) |
| **L3 avg** | Short-window average FP/game (3 most recent) — recency snapshot |
| **Trend** | UP ↑ / FLAT → / DOWN ↓ based on L3 vs L5 vs L8 deltas |
| **Std** | Standard deviation (variance) |
| **Min / Max** | Single-game extremes within the window |
| **Boom%** | % of games meeting position-specific boom threshold |
| **Bust%** | % of games meeting position-specific bust threshold |
| **Model cross-ref** | Blended xFP per_pa/per_start + confidence_tier — shows where actuals disagree with model |
| **Status note** | Optional flag: HOT STREAK / CAP FODDER / DECLINING / RAMP / VOLATILE |

## Position-aware thresholds (the calibration that makes this skill work)

| Position | Window | **Boom threshold** | **Bust threshold** | Rationale |
|---|---|---|---|---|
| SP | L8 starts | **≥20 FP** | **<5 FP** | BrownU SP scoring: ~14 FP avg per start league-wide. 20+ = top-quintile start. <5 = bottom-quintile / disaster |
| Hitter | L21 games | **≥10 FP** | **<2 FP** | Hitter scoring: ~5 FP avg per game. 10+ = top quintile (HR + multi-hit). <2 = 0-for-4 dud |
| RP | L15 appearances | **≥5 FP** (incl. SV/HLD) | **<0 FP** | RP scoring: ~1.5 FP avg per appearance. 5+ = clean inning with K + save/hold. <0 = blown opp |

**Thresholds are display-fixed.** Don't let the user override them per
invocation — calibration matters more than personalization here. If a
user needs custom thresholds for a specific decision, surface that as
a one-time "you can compute X% above N from the detail table" rather
than re-running with new cutoffs.

## Cross-year fallback (the Hunter Greene case)

If a player has fewer than 5 starts/games in the current year, pull
prior-year data and annotate. Use cases:
- **IL60 stashes** (Greene — out since March 2026 elbow surgery; use 2025)
- **Promotions** where the rookie has a partial 2026 line but a full 2025 MiLB or alternate-league line — skip MiLB; only MLB counts
- **Trades or position changes** mid-season — use full prior-year if needed

Annotate which year(s) the data came from in the source year column.
NEVER mix years silently — the table must say `2025` or `2025+2026`
explicitly.

```python
def pull_last_n(pid, n, current_year, fallback_year):
    """Pull last N games. If current year has <5, augment with prior year."""
    starts = []
    for yr in [current_year, fallback_year]:
        if yr is None: continue
        r = requests.get(
            f'https://statsapi.mlb.com/api/v1/people/{pid}/stats'
            f'?stats=gameLog&group={GROUP_FOR_POSITION}&season={yr}',
            timeout=20
        ).json()
        splits = [s for s in r['stats'][0]['splits'] if FILTER_FOR_POSITION(s)]
        splits.sort(key=lambda s: s['date'], reverse=True)
        for s in splits:
            starts.append({'date': s['date'], 'year': yr, ...})
            if len(starts) >= n: break
        if len(starts) >= n: break
    return starts[:n]
```

## Inputs

1. **Default: user's full roster** (active + BE + IL slots). Auto-splits
   into SP / H / RP buckets. Cross-year fallback fires per player.

2. **Optional `--names "A,B,C"`**: comma-separated list of any
   players. Skip the roster pull, just analyze these.

3. **Optional `--position SP|H|RP`**: force the position bucket if
   auto-detection might collide (e.g., a 2-way player).

4. **Optional `--window N`**: override the default window (8 for SP,
   21 for H, 15 for RP). Useful for "last 30 starts trend" or "last
   60 PA bat-tracking check."

5. **Optional `--show-detail`**: per-game breakdown rendered below the
   summary table.

## Step 1 — Resolve names to MLBAM with KNOWN_COLLISIONS gate

```python
from plv_clone.utils.name_match import resolve_batter_id, KNOWN_COLLISIONS
import pandas as pd, unicodedata
def _norm(s): return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()
def _flip(n):
    if isinstance(n,str) and ',' in n:
        a,b = n.split(',',1); return f'{b.strip()} {a.strip()}'
    return n

# Pitcher MLBAM (Last, First → First Last)
rp3 = pd.read_csv('data/outputs/xfp_rp3_projections.csv')
rp3['_key'] = rp3['player_name'].apply(_flip).apply(_norm)
rp3 = rp3.drop_duplicates('_key', keep='first')
p_lookup = dict(zip(rp3['_key'], rp3['pitcher']))

# Batter MLBAM (already First Last)
rh3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
rh3['_key'] = rh3['player_name'].apply(_norm)
rh3 = rh3.drop_duplicates('_key', keep='first')
h_lookup = dict(zip(rh3['_key'], rh3['batter']))
```

**Same-name collision check is mandatory.** Max Muncy LAD vs ATH;
Luis García Jr. WSH/HOU/PHI; Logan Allen pitcher-twins. Always pass
team + position to `resolve_batter_id` when the name is in
`KNOWN_COLLISIONS`.

## Step 2 — Determine position bucket per player

```python
def position_bucket(name, p_lookup, h_lookup, force=None):
    if force: return force
    k = _norm(name)
    if k in p_lookup:
        # Distinguish SP from RP via rp3 vs rprs2 row
        ...
    if k in h_lookup:
        return 'H'
    return None  # unknown — fallback to ESPN roster lookup or error
```

## Step 3 — Pull last-N game logs from MLB Stats API

| Position | API group | gameLog filter |
|---|---|---|
| SP | `pitching` | `gamesStarted >= 1` |
| RP | `pitching` | `gamesStarted == 0 AND (saves > 0 OR holds > 0 OR appearances > 0)` |
| H | `hitting` | `plateAppearances > 0` (also filter days off / pinch-hit only as separate annotations) |

Compute BrownU FP per game:

```python
# Canonical BrownU scoring formulas (see CLAUDE.md league rules section)
def fp_sp_or_rp(st, is_rp=False):
    ip_str = st.get('inningsPitched','0.0')
    ipp, ipf = ip_str.split('.'); ip = int(ipp) + int(ipf)/3
    K = int(st.get('strikeOuts',0))
    H = int(st.get('hits',0))
    ER = int(st.get('earnedRuns',0))
    BB = int(st.get('baseOnBalls',0))
    HBP = int(st.get('hitByPitch',0))
    base = K + ip*3.3 - H - 2*ER - BB - HBP
    if is_rp:
        SV = int(st.get('saves',0))
        HLD = int(st.get('holds',0))
        return base + 5*SV + 2*HLD
    return base

def fp_hitter(st):
    R = int(st.get('runs',0))
    TB = int(st.get('totalBases',0))
    RBI = int(st.get('rbi',0))
    BB = int(st.get('baseOnBalls',0))
    HBP = int(st.get('hitByPitch',0))
    SB = int(st.get('stolenBases',0))
    K = int(st.get('strikeOuts',0))
    return R + TB + RBI + BB + HBP + SB - K
```

**HLD coefficient confirmed BrownU=2 per Gate 0a sweep (plan v11);
NEVER use HLD=3.** See `data/models/league_scoring.json` for the
authoritative scoring config.

## Step 4 — Compute boom/bust + variance + trend

```python
def analyze(fps, boom_t, bust_t):
    n = len(fps)
    if n == 0: return None
    last5 = fps[:5]
    last3 = fps[:3]
    booms = sum(1 for f in fps if f >= boom_t)
    busts = sum(1 for f in fps if f < bust_t)
    l8_avg = statistics.mean(fps)
    l5_avg = statistics.mean(last5) if last5 else 0
    l3_avg = statistics.mean(last3) if last3 else 0
    # Trend: compare L3 to L5 to L8
    short_delta = l3_avg - l5_avg
    long_delta = l5_avg - l8_avg
    if short_delta >= 2 and long_delta >= 0: trend = 'UP'
    elif short_delta <= -2 and long_delta <= 0: trend = 'DOWN'
    else: trend = 'FLAT'
    return {
        'n': n, 'L8_avg': l8_avg, 'L5_avg': l5_avg, 'L3_avg': l3_avg,
        'std': statistics.stdev(fps) if n > 1 else 0,
        'min': min(fps), 'max': max(fps),
        'boom_pct': booms / n, 'bust_pct': busts / n,
        'trend': trend,
    }
```

## Step 5 — Join model cross-reference

For each player, attach the model's verdict so the user can see WHERE
actuals diverge:

| Bucket | Model col | File |
|---|---|---|
| SP | `xfp_rp3_per_start` + Blended xFP + confidence_tier | `xfp_rp3_projections.csv` + `live_blend_xfp_latest.csv` |
| H | `xfp_rh3_per_game` + Blended xFP + confidence_tier | `xfp_rh3_projections.csv` + `live_blend_xfp_latest.csv` |
| RP | `xfp_ros` + leverage_tier | `xfp_rprs2_projections.csv` |

Highlight rows where:
- **Actuals (L5) > Model + 3 FP** → "model lagging" (Bradish pattern)
- **Actuals (L5) < Model − 3 FP** → "outcome cold but model says hold" (Soriano pattern)

## Step 6 — Status note labels

Auto-tag each player based on the boom/bust + trend pattern:

| Tag | Condition |
|---|---|
| **HOT STREAK** | boom% ≥ 30% AND trend = UP |
| **CAP FODDER** | boom% = 0% AND bust% ≥ 25% |
| **DECLINING** | trend = DOWN AND bust% ≥ 25% |
| **RAMP** | trend = UP AND L3 ≥ L8 + 4 |
| **VOLATILE** | std > 9 (SP) or std > 5 (H) — high variance |
| **FLOOR** | std < 5 (SP) or std < 3 (H) AND bust% ≤ 10% |
| **STASH** | IL60+ with strong prior-year actuals (boom% ≥ 30% in fallback year) |

Multi-tag is allowed (a player can be both VOLATILE and HOT STREAK).

## Step 7 — Render the table

Group by position, sort by L5 avg descending within group.

For SPs:

```
| Rk | SP | Status | Yr | N | L8 avg | L5 avg | L3 avg | Trend | Std | Min | Max | Boom% | Bust% | Blended xFP | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
```

For Hitters:

```
| Rk | Hitter | Status | Yr | N | L21 avg | L7 avg | L3 avg | Trend | Std | Min | Max | Boom% | Bust% | Blended xFP | Note |
```

For RPs:

```
| Rk | RP | Status | Yr | N | L15 avg | L7 avg | L3 avg | Trend | Std | Min | Max | Boom% | Bust% | leverage_tier | Note |
```

Sort by **L5 avg desc** (or L7 for hitters) — recent form matters more
than long-window for variance-aware decisions.

## Step 8 — Optional per-game detail block

If `--show-detail` is set, render below each player's row:

```
<Player>:
  2026-06-05 vs OPP: 6.0 IP  FP=15.80
  2026-05-29 vs OPP: 4.2 IP  FP= 3.40 BUST
  ...
```

For hitters, include lineup spot if available (1st, 2nd, ... 9th).

## Anti-patterns this skill exists to prevent

- **Trusting model projections (Blended xFP, rp3) without checking
  recent actuals.** Bradish blend 5.98 vs actuals L5 17.88 = the
  model is 12 FP behind reality.
- **Comparing players across different windows.** L8 SP vs L21 hitter
  vs L15 RP. The position-aware window is part of the calibration —
  don't compute SP L21 unless asked explicitly.
- **Mixing prior-year and current-year actuals silently.** Hunter
  Greene's "L8" might be 2025 entirely; the table MUST surface that
  fact in the Source Year column.
- **Using HLD=3 instead of HLD=2.** Per BrownU Gate 0a sweep,
  canonical is HLD=2. Check `data/models/league_scoring.json`.
- **Looking up batter IDs by name alone.** Max Muncy LAD vs ATH —
  always go through `resolve_batter_id(name, team=…, position=…)`.
- **Computing FP from `applied_total` or ESPN's `points` field.**
  Both return 0 across the API for most players. Always recompute
  from raw counting stats via the canonical formulas.
- **Treating Std as the primary metric.** Std measures variance; users
  care about boom AND bust separately because they're not symmetric.
  A 0% boom 25% bust SP (Valdez) is worse than a 25% boom 25% bust SP
  (Roki) even at the same std.
- **Hiding small samples.** If N < 5, surface "small sample (N=3)"
  warning. Don't render boom%/bust% as if they're stable.
- **Forgetting position-specific thresholds.** Hitter boom is ≥10 FP
  per GAME (not 20). RP boom is ≥5 FP per appearance. Using SP
  thresholds across positions produces nonsense.

## When NOT to use this skill

- User wants model projections only → use `/triangulate` or the
  slate-grids.
- User wants Statcast process metrics (xwOBA, bat speed, swstr%) →
  use `/hitter-sustainability` or `/pitcher-sustainability`.
- User wants matchup-specific projections (today's opp, park, weather)
  → use `/sp-slate-grid` / `/hitter-slate-grid`.
- User wants future projections — this skill is purely retrospective.
- User wants comparison of 2-6 players head-to-head with full
  decomposition → use `/hitter-compare` or `/sp-archetype comps`.

## See-also references (called from other skills)

This skill should be referenced from:

- `/sp-slate-grid` — at the synthesis step, after model layers
  diverge from each other, suggest "for variance check, run
  `/boom-bust-history` on the SP".
- `/hitter-slate-grid` — same pattern for FA hitter picks where the
  model is uncertain (MED confidence).
- `/triangulate` — when verdict is MIXED or when actuals seem to
  contradict the headline, mention `/boom-bust-history` as the next
  step.
- `/sp-week-plan` — at the bench-decision step, surface boom%/bust%
  alongside the matchup quality.
- `/forced-drop-planner` — when computing drop priority, use boom%
  as the tiebreaker between two similar-projection SPs.

## Canonical output example (from the conversation that birthed this skill)

User asked: "do all of the SPs, including the ones that are injured,
for green, bring in his starts from last year if those are his last
eight, and add rookie."

Output (with sample data):

```
| Rk | SP | Status | Yr | N | L8 avg | L5 avg | L3 avg | Trend | Std | Min | Max | Boom% | Bust% | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Hunter Greene | IL60 | 2025 | 8 | 18.05 | 19.04 | 15.07 | FLAT | 13.80 | -7.3 | 36.7 | 50% | 12% | STASH + HOT STREAK |
| 2 | Roki Sasaki | BE | 2026 | 8 | 13.31 | 18.16 | 19.40 | UP | 9.93 | 1.4 | 29.1 | 25% | 25% | RAMP + VOLATILE |
| 3 | Kyle Bradish | BE | 2026 | 8 | 12.71 | 17.88 | 15.50 | FLAT | 8.57 | -2.8 | 22.8 | 37% | 12% | HOT STREAK |
| 4 | Tyler Glasnow | IL15 | 2026 | 8 | 16.47 | 17.46 | 16.80 | FLAT | 9.45 | 2.3 | 33.4 | 25% | 12% | STASH |
| 5 | Parker Messick | ACT | 2026 | 8 | 14.29 | 13.88 | 13.30 | FLAT | 4.32 | 8.5 | 20.7 | 12% | 0% | FLOOR |
| 6 | Max Fried | IL15 | 2026 | 8 | 12.56 | 12.70 | 4.77 | DOWN | 10.03 | -0.1 | 30.4 | 25% | 25% | DECLINING + VOLATILE |
| 7 | Carlos Rodón | ACT | 2026 | 8 | 14.15 | 12.50 | 16.70 | UP | 6.20 | 4.3 | 24.1 | 12% | 12% | RAMP |
| 8 | Framber Valdez | BE | 2026 | 8 | 8.60 | 11.96 | 13.43 | UP | 10.50 | -13.1 | 18.8 | 0% | 25% | CAP FODDER + VOLATILE |
| 9 | José Soriano | ACT | 2026 | 8 | 9.25 | 11.16 | 9.30 | DOWN | 8.80 | -2.8 | 24.3 | 12% | 37% | DECLINING |
| 10 | Freddy Peralta | ACT | 2026 | 8 | 11.95 | 10.92 | 11.10 | FLAT | 4.70 | 3.4 | 16.8 | 0% | 12% | FLOOR |
| 11 | Will Warren | ACT | 2026 | 8 | 13.97 | 9.80 | 11.70 | DOWN | 8.74 | -1.8 | 25.1 | 25% | 12% | DECLINING |
```

Notice:
- Sorted by L5 desc within position group
- Cross-year flagged (`Yr` column = 2025 for Greene)
- Tags surface the actionable read (CAP FODDER for Valdez, HOT STREAK
  for Bradish, RAMP for Roki, etc.)
- Min/Max range gives the user the floor/ceiling at a glance
