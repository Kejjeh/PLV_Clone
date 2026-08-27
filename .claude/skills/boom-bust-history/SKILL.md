---
name: boom-bust-history
description: Historical actuals analysis with boom/bust/variance decomposition for any list of players (default — user's full roster including IL'd returners with cross-year fallback). Pulls last-N game logs from MLB Stats API (SP — L8 starts, hitter — L21 games, RP — L15 appearances; window configurable), computes BrownU FP per game using the canonical scoring formulas (SP/RP — `K + IP*3.3 − H − 2*ER − BB − HBP`, plus `5*SV + 2*HLD` for RP; hitter — `R + TB + RBI + BB + HBP + SB − K`), then surfaces position-aware boom%/bust% (SP — boom ≥17 / bust <5; hitter — boom ≥5 / bust <0; RP — boom ≥6 / bust <0; recalibrated 2026-06-28 to empirical ~p78/p22 quantiles — SP boom lowered 20→17 so a top-quartile 17.7 start counts; hitter was 10/2 = a useless 3%/57%; see boom_bust_cutoff_recalibration_2026-06-28.md) alongside L8/L5/L3 averages, std (variance), min/max range, and trend direction (L3 vs L5 vs L8). Auto-fallback to prior year for any player with insufficient current-year games (IL60+ stashes like Hunter Greene 2025 surface automatically). Tags ownership (MINE / opp / FA), injury status (ACT / BE / IL15 / IL60 + return date), and trend arrows. Renders a position-grouped table sorted by recent form, plus optional per-game detail blocks. Designed to surface the variance side of the projection picture that model layers (rh3/rp3/rprs2, baseline xFP, archetype) cannot — actuals show whether a SP is a 37% boom hot streak (Bradish) or 0% boom 25% bust cap-fodder (Valdez) regardless of what the model says. Use when the user asks "boom bust", "how consistent has X been", "who's been booming/busting", "show me actuals not just projections", "variance check on my roster", "last 8 starts breakdown", "is X really hot or just lucky", "rank my SPs by boom rate", "roster variance audit", or wants to verify a model's projection with hard recent-actuals evidence. Engine pattern — `name_to_mlbam` via name flip + norm + KNOWN_COLLISIONS guard, MLB Stats API gameLog per player, position bucket auto-detect from rh3/rp3/rprs2 join, boom/bust threshold lookup by bucket, cross-year fallback when current-year n < 5 (Hunter Greene case), output sorted by L5 avg desc within position group, with model-projection cross-reference column (baseline xFP / rp3 per_start / rh3 per_game) showing where actuals disagree.
---

# boom-bust-history

You are rendering the **variance-aware historical-actuals view** of a
player set. This is the lens that complements `/sp-slate-grid`,
`/hitter-slate-grid`, and `/triangulate` — those skills show what the
model projects; this skill shows what's actually been happening.

## `--explain <player>` mode (absorbs /boom-stack-explain, item 15)

When invoked with `--explain <player>` (or when the user asks "why is X's
boom_stack N/4", "what's driving this tag", "decompose this boom_stack"), do NOT
render the roster actuals table — instead decompose that ONE player's current
`boom_stack` tag into its component signals:

1. Resolve the player to MLBAM (name flip + norm + KNOWN_COLLISIONS guard).
2. Pull the live boom_stack record (SP: `data/outputs/sp_boom_stack_full_pool_<date>.json`;
   hitter: `data/outputs/hitter_boom_stack_<date>.json`).
3. For each of the 4 components (SP: skill_spike / recform_hot / opp_soft /
   park_friendly; hitter: skill_spike_hitter / recform_hot_hitter /
   opp_soft_hitter / lineup_amp_hitter): show **status (fired/not) · value ·
   threshold · why**.
4. Show the tier outcome lookup (boom%/bust%/E[FP] for this stack value at this
   player's tier) from the validated tier table.
5. **Verdict.** Explanatory ONLY — the headline number stays rp3/rh3, and
   boom_stack is a context lens (Rule 13), never a ranker.

This is the diagnostic companion to the roster-wide actuals view: the table
shows *how variable* a player has been; `--explain` shows *why the model's
boom tag is what it is* for one player.

The skill exists because the model layers (baseline xFP, rp3, rh3,
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
| **Model cross-ref** | baseline xFP per_pa/per_start + confidence_tier — shows where actuals disagree with model |
| **Status note** | Optional flag: HOT STREAK / CAP FODDER / DECLINING / RAMP / VOLATILE |

## Position-aware thresholds (the calibration that makes this skill work)

**Empirically validated against 2025 league-wide distributions** (top-250-by-rank
samples, n=3,765 SP starts / 27,672 hitter games / 9,256 RP appearances). Cuts
target the actual p80 (boom) and p20 (bust) quintiles.

| Position | Window | **Boom threshold** | **Bust threshold** | Empirical anchor |
|---|---|---|---|---|
| SP | L8 starts | **≥17 FP** | **<5 FP** | recalibrated 2026-06-28: ≥17 = top-quartile (23.5%) so a strong 17.7 FP start counts; 12-yr-confirmed ~24-26% boom. (Old ≥20 = p80/top-14%, missed it.) |
| Hitter | L21 games | **≥5 FP** | **<0 FP** | 2025: p80=5.0, p20=0.0. Median hitter game is 1 FP — the old 10/2 cuts marked the median as "bust" |
| RP | L15 appearances | **≥6 FP** (incl. SV/HLD) | **<0 FP** | 2025: p80=6.3, p20=0.4. Old ≥5 cut tagged 1-in-3 outings as "boom" — too loose |

## ⚠ SHRINK THE RATE BEFORE YOU BELIEVE IT (measured 2026-08-27, both sides)

A boom rate from a short window is mostly sampling noise. Regressing the NEXT
window's boom rate on the observed one (`scripts/xfp/validate_boom_window.py`):

| SP window | slope | **noise** | | HITTER window | slope | **noise** |
|---|---|---|---|---|---|---|
| L3 | 0.179 | **82%** | | L7 | 0.105 | **89%** |
| L5 | 0.261 | 74% | | L14 | 0.192 | 81% |
| **L8** (default) | **0.353** | **65%** | | **L21** (default) | **0.267** | **73%** |
| L12 | 0.431 | 57% | | L28 | 0.330 | 67% |
| L20 | 0.575 | 42% | | L60 | 0.520 | 48% |

**The asymmetry is the surprise: hitter L21 is NOISIER than SP L8** — 73% vs
65% — despite resting on 21 observations instead of 8. More data, less signal.

The mechanism is between-player spread, and two windows per side agree on it:
the implied TRUE between-player SD of boom rate is **~12pp for pitchers** and
only **~5pp for hitters**. Hitters are simply more alike in how often they boom,
so even a longer window resolves less of a real difference.

**Corrected displays:**

| | displayed | forward |
|---|---|---|
| SP "0% boom cap-fodder" (0/8) | 0.0% | **19.7%** |
| SP "37% boom hot streak" (3/8) | 37.5% | **33.0%** |
| Hitter 0/21 | 0.0% | **15.2%** |
| Hitter 10/21 | 47.6% | **27.9%** |

A 0-for-the-window player is never a player who *cannot* boom. He is a roughly
one-in-five (SP) or one-in-seven (hitter) player, and the raw display invites
exactly the wrong inference.

**Always report the forward estimate next to the raw rate:**

```python
import sys; sys.path.insert(0, "scripts/xfp/lib")
from boom_bust import forward_rate
forward_rate(3/8, window=8,  side="SP")   # -> 0.330
forward_rate(0.0, window=21, side="H")    # -> 0.152
```

**As a PROBABILITY the window loses to the base rate.** Brier vs a constant:
SP L8 **+0.0091** (boom) / **+0.0147** (bust); hitter L21 **+0.0048** / **+0.0045**.
It keeps real RANKING skill (AUC 0.55-0.60) — use it to sort, never as a number.

**One side-specific caveat.** For SPs a smooth parametric P(FP≥thr) beats both
windows. For hitter BUST it does NOT (Brier +0.0041, worse than season-to-date)
— hitter per-game FP is strongly right-skewed (skew +1.22, kurtosis 5.09) and a
Gaussian misprices the left tail. On the hitter bust line, prefer season-to-date.

**And treat the Trend arrow with suspicion.** SP compares L3/L5/L8 = 82/74/65%
noise; hitters L7/L14/L21 = 89/81/73%. Largely noise against noise, and the
shorter inputs are always the worse ones.

Calibration note: `forward_rate` is a DISPLAY correction (Rule 13). It never
moves rh3/rp3/rprs2 and changes no existing output — callers opt in.



**Threshold history**: original v1 cuts were SP 20/5, Hitter 10/2, RP 5/0,
calibrated by intuition. The 2026-06-06 empirical validation confirmed SP
is correct but hitter and RP were badly miscalibrated:

- **Hitter 10/2** → boom rate only 3.7% (median day tagged "bust" because
  a R + single + RBI day is 4 FP). Recalibrated to **5/0**.
- **RP 5/0** → boom rate 33.3% (any clean inning with a K + save = boom).
  Recalibrated to **6/0**.
- **SP 20/5 → 17/5** (recalibrated 2026-06-28). The original 20 (≈p80, top-14%)
  flagged only "monster" starts; lowered to **17** (top-quartile, ~24-26% in the
  modern run env, **12-year-confirmed on 656k real per-game FP**) so a strong
  17.7 FP start counts as a boom. Bust <5 kept. NOTE: the `boom_stack` FORWARD
  tables keep their P(FP≥20) "monster" rate by design — the display lens (recent
  realized "good starts", ≥17) and the forward expectation table (≥20) are
  separate tools (they already differed on bust, 5 vs 0).

Validation report archived at `C:/tmp/boom_bust_threshold_validation.md`,
sampler at `scripts/_oneoff/boom_bust_sampler.py`.

**Thresholds are display-fixed.** Don't let the user override them per
invocation — calibration matters more than personalization here. If a
user needs custom thresholds for a specific decision, surface that as
a one-time "you can compute X% above N from the detail table" rather
than re-running with new cutoffs.

## Bayesian shrinkage to prior year (when baseline xFP unavailable)

When projecting forward FP for a player whose baseline xFP is missing
(MED conf / no_blend / rookie thin sample), this skill applies Bayesian
shrinkage to combine L21 actuals with prior-year baseline:

```
shrunk_avg = (n_L21 × L21_avg + k × prior_year_avg) / (n_L21 + k)
projected_fp_wk = shrunk_avg × games_per_week
```

**Empirically calibrated k by position** (2026-06-06 backtest, 1,498
hitter snapshots + 550 SP snapshots across 2024-2025; see
`data/research/validation_runs/shrinkage_calibration_2026-06-06.md`):

| Position | Default k | Notes |
|---|---|---|
| **Hitter (pooled)** | **k = 80** | Optimal k=40 only +0.6% MAE better; k=80 defensible |
| **Hitter (top-50 rh3 rank)** | **k = 40** | Elite hitters' L21 form carries more signal; lighter shrink |
| **SP (all strata)** | **k = 20** | MUCH lighter than hitters; L21 form more predictive for SPs. k=80 is ~3× worse MAE than k=20 for SPs. |
| **RP** | k = 30 default (not separately validated) | — |

**Two-year prior is a free upgrade.** Use `prior = 0.6 × Y−1 + 0.4 × Y−2`
whenever both prior seasons exist for the player.

**Season progress doesn't matter.** Early/mid/late as_of dates show
<0.01 MAE difference — no time-of-season adjustment needed.

### When to prefer baseline xFP over manual shrinkage

If a player has a HIGH-confidence baseline xFP row in
`live_blend_xfp_latest.csv`, **prefer the blend over manual shrinkage**.
The Phase 3 blend weights are learned from a multi-feature holdout
backtest and incorporate prior + slope_3yr + archetype + recent rh3 + PL
features simultaneously. Manual k-shrinkage only uses 2 features (L21 +
1-2 prior years) — strictly less informed than the validated blend.

Manual shrinkage is the FALLBACK for: MED-confidence blends, no-blend
rookies, cross-validation when blend looks wrong, IL stashes using
prior-year data.

Canonical failure (2026-06-06): I applied k=80 to Willy Adames and got
15.4 FP/wk. His baseline xFP HIGH said 10.27. The blend was right — it
weighted his multi-year decline; my 2-feature shrinkage just used 2025
baseline + 2026 L21, missing the 2024 trend. **Trust the blend when
available.**

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

## Step 0.5 — Mandatory KNOWN_COLLISIONS stop-check rendering (REQUIRED)

When any input name appears in
`plv_clone.utils.name_match.KNOWN_COLLISIONS` (hitters) or
`KNOWN_PITCHER_COLLISIONS` (pitchers), the output MUST include a
visible "Stop check" block BEFORE the analysis table. Code-side
disambiguation via `resolve_batter_id` is not enough — the user needs
to SEE which MLBAM was selected and why, so silent mis-pulls can be
caught at the point of decision.

Render template:

```
Stop check confirmed - Max Muncy:
   KNOWN_COLLISIONS hit. Two candidates:
     - MLBAM 571970 - LAD, 3B, veteran (active 2015+)
     - MLBAM 691777 - ATH, SS, 2024 callup
   Selected: 571970 (LAD 3B vet) based on team='LAD' from roster.
   NOT pulling MLBAM 691777 (ATH SS young).
```

Required fields per stop-check block:
- Both candidate MLBAM IDs (or all N for >2-way collisions like Luis Garcia)
- Each candidate's team / position / age-or-tenure hint
- The selected MLBAM
- The disambiguator used (team / position / role)
- Explicit "NOT pulling X" line for the rejected candidate(s)

Trigger this block when:
- `name in KNOWN_COLLISIONS` (hitters)
- `name in KNOWN_PITCHER_COLLISIONS` (SP/RP)
- `resolve_batter_id` / `resolve_pitcher_id` returns None on first
  call because no team/position was passed — re-prompt the caller and
  render the block once a team is supplied.

Canonical case (2026-06-06): user asked "stop check, are you pulling
the right Muncy" mid-session. The skill body didn't require a visible
stop-check, so the answer was buried in code rather than rendered.
This step forces the trust signal into the output.

This block is REQUIRED, not optional. Do not skip even when "obvious
from context" — the user explicitly asked for this signal to be
rendered every time a collision name is in scope.

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
| SP | `xfp_rp3_per_start` + baseline xFP + confidence_tier | `xfp_rp3_projections.csv` + `live_blend_xfp_latest.csv` |
| H | `xfp_rh3_per_game` + baseline xFP + confidence_tier | `xfp_rh3_projections.csv` + `live_blend_xfp_latest.csv` |
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

## Step 6.5 — Mandatory Tier 3 process gate (REQUIRED before any drop/add recommendation)

**The rule**: When the analysis output includes a drop/add recommendation
(either explicitly recommending a swap, or implicitly via CAP FODDER /
DECLINING / HOT STREAK tags that the user is acting on), the synthesis
MUST surface the Tier 3 process check for the affected players BEFORE
issuing the recommendation. The boom-bust skill produces variance-aware
**actuals**, but actuals can be luck-driven (BABIP-fuelled hot streaks,
playing-hurt slumps). The process gate is the load-bearing check that
distinguishes signal from noise.

This is mandatory per
`~/.claude/projects/c--Users-Joshua-plv-clone/memory/reference_xwoba_l21d_vs_2025_diagnostic.md`
and feedback memory `feedback_check_il_before_decline_call.md`.

### Per-position gate specification

**Hitters** — pull `xwOBA L21d` from `data/research/xfp_cache/statcast_2026.parquet`
filtered to the last 21 days, compare to `xwOBA 2025` baseline:

| Gap (L21d − 2025) | Verdict | Recommendation reading |
|---|---|---|
| `±0.020` | **SKILL_HOLDING** | recommendation is luck-aligned with skill |
| `< −0.060` | **REAL_DECLINE** | drop recommendation justified by process; add recommendation suspect |
| Intermediate (between −0.060 and −0.020, or between +0.020 and any positive) | **MIXED** | demand secondary confirmation (bat speed, EV90, K%) |

Also pull `xwOBACON YoY trajectory` 2022 → 2023 → 2024 → 2025 → 2026
(RISING / STABLE / DECLINING). DECLINING means recovery ceiling is lower
than prior troughs — prior slump/recovery templates DON'T apply (the
Turner pattern). STABLE means prior recoveries predict this one.

**Pitchers (SP)** — pull recent **velo + SwStr% + CSW%** from
`statcast_2026.parquet` (last 30 days) vs season baseline:

- velo down >1 mph AND SwStr% down >2 pp → **REAL_DECLINE** (process supports drop)
- velo flat/up AND SwStr% flat/up → **PROCESS_HOLDING** (drop suspect; bounce coming)
- mixed → **MIXED**

**RPs** — pull `leverage_tier` from `xfp_rprs2_projections.csv` + recent
usage trend from the last 15 appearances. If demoted from HIGH_LEVERAGE
to MID/LOW or save-share collapsing → **PROCESS_DOWNGRADE** (drop
justified). If leverage_tier intact → drop recommendation is
outcome-driven and should be downgraded to HOLD/CAUTION.

### Output template (mandatory render when recommending drop/add)

```
Tier 3 process gate:
   <Player>: <metric> L21d/L30d = X.XXX vs 2025 baseline Y.YYY → gap +/-Z → SKILL_HOLDING | REAL_DECLINE | MIXED
   xwOBACON YoY: 2022=A → 2023=B → 2024=C → 2025=D → 2026=E → RISING | STABLE | DECLINING
   Recommendation: SUPPORTED | CAUTION | OVERRIDE
```

Where:
- **SUPPORTED** — process agrees with actuals-driven recommendation; ship it
- **CAUTION** — process is mixed or partially disagrees; soften the recommendation (HOLD, monitor 1 week)
- **OVERRIDE** — process directly contradicts the actuals (bounce coming on a "drop" / BABIP-driven hot streak on an "add"); reverse or shelve the recommendation

### Cross-reference

For deeper single-player work on whether a hot streak is sustainable,
hand off to:
- `/breakout-sustainability` — single-player deep dive on bat tracking +
  discipline + contact quality decomposition
- `/hitter-sustainability` — sweep-mode equivalent across roster / FA pool
- `/pitcher-sustainability` — SP analog with 9-marker Statcast decomp
  (velo, swstr, CSW, chase, K%, BB%, HardHit%, Barrel%, xwOBA-contact)
- `/sp-floor` — the PREDICTIVE floor companion to this skill's MEASURED
  variance. boom-bust shows the bust% a SP HAS posted (retrospective);
  `/sp-floor` predicts P(next start busts) from K−BB% (validated 2026-06-06).
  When measured bust (here) ≫ predicted floor, the gap is shape/contact the
  command model can't see (canonical: Soriano measured 38% vs predicted 22% —
  flat-ride sinker). Use both for SP bench/drop calls.

## Synthesis output template (REQUIRED — uses lens merge protocol)

<!-- LENS_MERGE_PROTOCOL_BLOCK_START -->
Every drop/add/hold recommendation issued from this skill MUST be
rendered using the confidence-weighted output block defined in
`~/.claude/projects/c--Users-Joshua-plv-clone/memory/reference_lens_merge_protocol.md`.
The template merges all 8 lenses (model, process gate, variance,
context) into a single block with explicit Tier B veto status and
conflict-rule provenance:

```
RECOMMENDATION: <action> <player>
   Confidence: HIGH | MEDIUM | LOW (per **empirically calibrated** 8-lens count — HIGH ≥5 of 8 NOT ≥6, per 2026-06-06 calibration `confidence_label_calibration_2026-06-06.md`. **Conflict Rule 4** REJECTED at HIGH_CONFIDENCE per `conflict_rule_lift_2026-06-06.md` — triple-signal drops downgrade to MODERATE with bounce-back caveat.)
   Tier A (model): rh3=<v> | baseline xFP=<v>
   Tier B (process gate): xwOBA L21d=<v> | xwOBACON YoY=<v> | sustainability=<v>
   Tier C (variance): boom-bust=<v> | boom_stack=<v>
   Tier D (context): archetype=<v> | PL=<v>
   Tier B veto: PASSED | DOWNGRADED
   Conflict rule applied: #N | none
```

Render the block VERBATIM. Do not collapse, summarize, or drop tiers —
when a lens is unavailable, write `n/a` and proceed; never silently
omit a row. The decision-type → lens priority mapping lives in
`reference_decision_type_lens_registry.md`; consult it when the
recommendation type (SP drop vs hitter add vs RP hold etc.) is in
question.
<!-- LENS_MERGE_PROTOCOL_BLOCK_END -->

## Where boom-bust sits in the merge protocol

<!-- TIER_C_POSITIONING_BLOCK_START -->
Boom-bust-history is a **Tier C (variance check)** lens. It does NOT
override Tier A (primary model — rh3/rp3/rprs2 + baseline xFP) and it
does NOT override Tier B (process gate — xwOBA L21d, xwOBACON YoY,
sustainability decomp, velo/SwStr/CSW for SPs, leverage_tier for RPs).

When boom-bust disagrees with Tier B, apply the conflict resolution
rules from `reference_lens_merge_protocol.md`:

- **Conflict Rule 1** — Model FADE + actuals BUY → check
  sustainability; if Tier B says SUSTAINABLE/IMPROVING the actuals win
  (model lagging); if Tier B says NOISE/HOT_STREAK the model wins.
- **Conflict Rule 2** — CAP_FODDER variance verdict + xwOBA L21d gap
  within ±0.020 → HOLD; Tier B's "skill holding" overrides Tier C's
  "outcome cold."

The CAP_FODDER / HOT_STREAK / DECLINING / RAMP / VOLATILE / FLOOR /
STASH tags this skill emits are **synthesis inputs, not standalone
verdicts**. They feed the merge block above; they do not ship as
recommendations on their own.

Canonical case (2026-06-06): José Soriano's 37% bust rate read as a
DECLINING drop signal in isolation. Tier B sustainability said
IMPROVING (velo intact, SwStr% trending up). Per Conflict Rule 2 the
boom-bust verdict was downgraded to HOLD. Shipping the Tier C verdict
alone would have produced a wrong drop.
<!-- TIER_C_POSITIONING_BLOCK_END -->

## Step 7 — Render the table

Group by position, sort by L5 avg descending within group.

For SPs:

```
| Rk | SP | Status | Yr | N | L8 avg | L5 avg | L3 avg | Trend | Std | Min | Max | Boom% | Bust% | baseline xFP | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
```

For Hitters:

```
| Rk | Hitter | Status | Yr | N | L21 avg | L7 avg | L3 avg | Trend | Std | Min | Max | Boom% | Bust% | baseline xFP | Note |
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

## Marginal FP per slot — SP vs Hitter decision math

When the boom-bust analysis is feeding a **cross-position drop/add
decision** (drop an SP to add a hitter, or vice versa), the right
synthesis lens is **marginal FP per slot per week**, not raw FP/game.

A hitter starts ~6 games per scoring week. An SP starts ~1.19 games
per scoring week (BrownU empirical rate). Per-slot weekly value:

```
hitter_slot_weekly_FP = hitter_FP_per_game * 6
SP_slot_weekly_FP     = SP_FP_per_start   * 1.19
```

For a hitter slot to beat an SP slot:

```
hitter_FP_per_game > SP_FP_per_start * (1.19 / 6)
hitter_FP_per_game > SP_FP_per_start * 0.198
```

Threshold table (use L5 actuals on the SP side — or per_start projection
— and L5 actuals or per_game projection on the hitter side):

| SP tier | SP FP/start | Hitter must clear (FP/game) |
|---|---|---|
| Elite | 18+ | **3.6+** |
| Strong | 14 | **2.8+** |
| Mid | 12 | **2.4+** |
| Below avg | 10-11 | **2.0+** |
| Cap fodder | <10 | **<2.0** — almost any hitter wins |

**When to use this framework:**
- Cross-position drop/add (drop SP -> add hitter, or drop hitter -> add SP)
- Evaluating whether an empty hitter slot is worth more than holding a
  marginal SP on the bench
- Marginal-slot-value questions where the question is "is this player's
  slot earning its weekly cost"

**When NOT to use it (use direct L5 comparison instead):**
- Same-position swaps (drop SP A, add SP B; drop OF X, add OF Y) —
  these are direct head-to-head, no slot-rate conversion needed
- Lineup setting within a confirmed roster (no drop involved)
- Boom/bust variance audits where the question is consistency, not
  marginal slot value

This was the implicit synthesis lens of the 2026-06-06 cross-position
conversation (mid-tier SP at 14 FP/start needed to be beaten by 2.8+
FP/game hitter to justify the swap). Make it explicit whenever the user
is comparing across positions.

## Anti-patterns this skill exists to prevent

- **Trusting model projections (baseline xFP, rp3) without checking
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
- **Forgetting position-specific thresholds.** Hitter boom is ≥5 FP
  per GAME (not 17 — that's the SP cut). RP boom is ≥6 FP per
  appearance. Using SP thresholds across positions produces nonsense.
  Empirically calibrated 2026-06-06 (hitter/RP) + 2026-06-28 (SP 20→17,
  12-year-confirmed) — see "Position-aware thresholds" section above.
- **Using old v1 thresholds (Hitter 10/2, RP 5/0).** Those were
  calibrated by intuition and rejected by 2025 league-wide data. Hitter
  10/2 marked 52% of games "bust" (median game is 1 FP, not 5);
  RP 5/0 marked 33% of outings "boom". Always use the empirical cuts.
- **Slot fungibility error: dropping a same-eligible player to "fill"
  an empty same-position slot.** Lineup slots at the same position are
  FUNGIBLE — dropping a player at position P does NOT fill an empty
  P-slot, it just opens a different P-slot. To fill an empty slot you
  must ADD a player eligible for that slot. Canonical failure
  (2026-06-06): recommended "drop Wyatt Langford OF to fill empty OF5."
  Wrong — dropping Langford opens OF4 (his current slot); OF5 stays
  empty. The fix is to ADD an OF-eligible FA. When applying the
  marginal-FP-per-slot framework above, the comparison is between the
  marginal slot's expected FP (the slot the ADD fills) vs the marginal
  slot's current cost (the DROP's slot, if any) — never conflate them
  with same-position swaps.

- **Shipping drop/add recommendations without the Tier 3 process gate.**
  The boom-bust skill produces variance-aware actuals, but actuals can be
  luck-driven (BABIP-fuelled hot streaks, playing-hurt slumps that mimic
  decline). The Tier 3 gate (xwOBA L21d vs 2025 baseline for hitters;
  velo/SwStr/CSW trend for SPs; usage/leverage for RPs) is mandatory per
  `reference_xwoba_l21d_vs_2025_diagnostic.md` before any drop/add ships.
  Without it, the skill could ship a drop for a player whose underlying
  contact quality is intact (bounce coming) or an add for a hot streak
  that's BABIP-driven. See Step 6.5 for the gate spec and render template.


<!-- TIER_C_ANTIPATTERN_START -->
- **Treating boom-bust verdicts as standalone drop/add signals.**
  They're Tier C inputs that feed the merge protocol. A 37% bust rate
  (Soriano) or 37% boom rate (Bradish) can both be misleading if Tier B
  (sustainability + Tier 3 process gate) says otherwise. Always
  synthesize via `reference_lens_merge_protocol.md`, never ship a
  recommendation from boom-bust alone.
<!-- TIER_C_ANTIPATTERN_END -->

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
