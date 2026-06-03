"""boom_stack — live-prediction computation for SP triangulate cards.

Validated via `scripts/xfp/validate_streamer_boom_stack.py` — Mode B PASS
(SHIP_AS_TAG). See `data/research/validation_runs/streamer_boom_stack_v1_2026-06-03.md`.

Three components per SP at "now":
  1. skill_spike: last-5-starts K% - season K% >= +3pp AND last-5-starts
     BB% - season BB% <= -1pp. Requires >=3 prior starts; else 0.
  2. recform_hot: recency_form_gap >= +3.0 from the rp3 projection row.
  3. opp_soft: today's next_opp_team has bat_index_recent in the soft (bottom)
     tertile across 30 MLB teams. 33rd percentile cached once per script
     invocation.

boom_stack = c1 + c2 + c3, range [0, 3].

This is a DISPLAY TAG ONLY. Not a verdict override, not a feature in RP3_FEATS.

# Tier-aware rollout (2026-06-03)

Per-tier amplification analysis (`data/research/validation_runs/boom_stack_by_tier.md`)
revealed boom_stack is informative at ALL tiers, not just streamers. The rank
floor was DROPPED — the tag fires for any SP with an rp3 row.

Per-tier historical boom% at stack=3 (n=31,713 SP starts 2018-2025):
  ace      (rank 1-10):  56.7%  (+14.8 pp vs stack=0)
  sp2_sp3  (rank 11-30): 31.2%  (+4.2 pp)
  backend  (rank 31-50): 21.5%  (+1.3 pp)
  streamer (rank 51+):   17.4%  (+8.0 pp)

# Anti-predictive flag (skill_spike at SP2/3 + Backend tiers)

flag_skill_spike has NEGATIVE lift at SP2/3 and Backend tiers:
  SP2/3:   -3.4 pp  (recent K% spike + BB% drop = regression incoming)
  Backend: -4.1 pp
  Streamer: +2.7 pp (continuation more likely than regression)
  Ace:      +3.1 pp

When tier in {sp2_sp3, backend} AND skill_spike==1 AND boom_stack>=1, the
engine flags `skill_spike_anti_predictive=True` as a regression-risk hint.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_STATCAST_2026 = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'statcast_2026.parquet')
_TEAM_STRENGTH = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'team_strength_2026.csv')
_PITCHER_SCHEDULE = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'pitcher_schedule_2026.csv')
_PARK_FACTORS = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'park_factors_2018_2026.csv')

# park_friendly uses PRIOR-year park factor (strict pre-cutoff per validation
# spec: 2026 in-season starts use 2025 pf_wOBA). See
# data/research/validation_runs/park_factor_boom_modifier.md.
_PARK_PF_YEAR = 2025

# Expected boom rate / mean FP by bucket (legacy, streamer-pool calibration
# from `streamer_boom_stack_v1_2026-06-03.md`). Kept for backwards-compat with
# any caller still reading the flat keys; new code should use the per-tier
# tables below.
BOOM_RATE_BY_STACK = {0: 0.0970, 1: 0.1208, 2: 0.1362, 3: 0.1741}
MEAN_FP_BY_STACK = {0: 8.44, 1: 9.62, 2: 9.92, 3: 10.14}

# Per-tier historical boom% / bust% / mean FP by stack bucket.
# Source: `data/research/validation_runs/boom_stack_by_tier.md` (n=31,713 SP
# starts, 2018-2025). boom% = P(FP >= 20). bust% = P(FP < 0).
# NOTE on stack=4 (park_friendly 5th-component rollout, 2026-06-03):
# The validation report (park_factor_boom_modifier.md) reports a COMPOSITE
# stack=4 boom rate of 22.1% (n=104) across all tiers — per-tier stack=4
# numbers were NOT derived because the cell is too thin. The values below
# at stack=4 are an EXTRAPOLATION: each tier's stack=3 value scaled by the
# composite uplift ratio stack=3→stack=4 (≈ 22.1/20.9 = 1.057×) for boom
# rate, and the stack=3 value held flat for bust/mean (no signal to update).
# Mark as extrapolated; revisit when per-tier-stack=4 numbers exist.
BOOM_RATE_BY_TIER_STACK: dict[str, dict[int, float]] = {
    'ace':      {0: 0.419, 1: 0.446, 2: 0.487, 3: 0.567, 4: 0.599},  # 4: extrapolated (0.567×1.057)
    'sp2_sp3':  {0: 0.270, 1: 0.334, 2: 0.280, 3: 0.312, 4: 0.330},  # 4: extrapolated
    'backend':  {0: 0.203, 1: 0.251, 2: 0.207, 3: 0.215, 4: 0.227},  # 4: extrapolated
    'streamer': {0: 0.094, 1: 0.122, 2: 0.132, 3: 0.174, 4: 0.184},  # 4: extrapolated
}
BUST_RATE_BY_TIER_STACK: dict[str, dict[int, float]] = {
    'ace':      {0: 0.050, 1: 0.037, 2: 0.047, 3: 0.000, 4: 0.000},  # 4: held = stack=3
    'sp2_sp3':  {0: 0.060, 1: 0.047, 2: 0.053, 3: 0.043, 4: 0.043},  # 4: held
    'backend':  {0: 0.096, 1: 0.078, 2: 0.106, 3: 0.046, 4: 0.046},  # 4: held
    'streamer': {0: 0.185, 1: 0.156, 2: 0.152, 3: 0.152, 4: 0.152},  # 4: held
}
MEAN_FP_BY_TIER_STACK: dict[str, dict[int, float]] = {
    'ace':      {0: 17.33, 1: 17.93, 2: 18.91, 3: 20.93, 4: 20.93},  # 4: held
    'sp2_sp3':  {0: 14.51, 1: 15.69, 2: 15.16, 3: 15.89, 4: 15.89},  # 4: held
    'backend':  {0: 12.59, 1: 13.65, 2: 12.91, 3: 13.63, 4: 13.63},  # 4: held
    'streamer': {0:  8.36, 1:  9.64, 2:  9.75, 3: 10.60, 4: 10.60},  # 4: held
}

# Composite stack→boom rate (all tiers pooled) from park_factor_boom_modifier.md
# Used as a reference / fallback. n at stack=4 = 104.
COMPOSITE_BOOM_RATE_BY_STACK_V2 = {0: 0.1234, 1: 0.1498, 2: 0.1941, 3: 0.2093, 4: 0.2212}

# Week-boom rate (>= 30 FP combined across both starts) for 2-start week SPs.
# Keyed by tier and boom_stack at start_1. From
# `data/research/validation_runs/2start_week_amplification.md` (n=4,905
# 2-start weeks 2018-2025, 4,650 with tier assignment).
#
# Per-tier amplification at stack_s1>=2 vs stack_s1=0:
#   ace      +5.1 pp  (n=36 at stack_s1=2)
#   sp2_sp3  +10.7 pp (n=63 at stack_s1=2)  — biggest week-level amp
#   backend  +0.4 pp  (n=62 at stack_s1=2)  — NO actionable edge
#   streamer -0.7 pp  (n=290 at stack_s1=2) — NO actionable edge
#
# Operational note: backend + streamer rows are included for completeness
# but the per-start signal does NOT compound to a week-boom edge there.
# Display should be GATED to ace + sp2_sp3 tiers only (see
# `lookup_week_boom_rate` / sp-week-plan Step 5.5).
WEEK_BOOM_RATE_BY_TIER_STACK_S1: dict[str, dict[int, float]] = {
    'ace':      {0: 67.1, 1: 69.4, 2: 72.2, 3: 83.3},
    'sp2_sp3':  {0: 44.9, 1: 52.6, 2: 55.6, 3: 53.3},
    'backend':  {0: 41.5, 1: 42.9, 2: 41.9, 3: 50.0},
    'streamer': {0: 20.0, 1: 20.4, 2: 19.3, 3: 23.1},
}

# Tiers where the week-boom callout is actionable (validated +ve edge at
# stack_s1>=2). Backend / streamer are excluded — no week-level amp.
WEEK_BOOM_LOCK_TIERS = frozenset({'ace', 'sp2_sp3'})

# Component sticky rates — P(flag_s2=1 | flag_s1=1) pooled across tiers.
# Source: 2start_week_amplification.md section 2.
COMPONENT_STICKY_RATE: dict[str, float] = {
    'flag_skill_spike': 0.443,  # 5.2x base; recent K%+BB% reflects real arm state
    'flag_recform_hot': 0.586,  # 2.9x base; L3 window overlaps across starts
    'flag_opp_soft':    0.344,  # ~base (0.998x); independent across starts
}


def lookup_week_boom_rate(tier: str, stack_s1: int) -> float:
    """Historical week-boom rate (%) for a 2-start week SP given tier
    and stack at start 1.

    Args:
        tier:      One of 'ace' / 'sp2_sp3' / 'backend' / 'streamer'.
        stack_s1:  boom_stack value at start 1, integer in [0, 3].
                   Values >=3 are clamped to 3; values <0 to 0.

    Returns 0.0 when tier is unrecognized (defensive; do not silently
    substitute a wrong tier's rate).
    """
    table = WEEK_BOOM_RATE_BY_TIER_STACK_S1.get(tier)
    if table is None:
        return 0.0
    try:
        s = int(stack_s1)
    except (TypeError, ValueError):
        return 0.0
    s = max(0, min(3, s))
    return float(table.get(s, 0.0))

# Tiers where flag_skill_spike has NEGATIVE per-tier lift (recent K%-spike +
# BB%-drop is regression-predictive, not continuation-predictive).
SKILL_SPIKE_ANTIPREDICTIVE_TIERS = frozenset({'sp2_sp3', 'backend'})

# ---------------------------------------------------------------------------
# HIGH-K ARM tag (validated 2026-06-03, PASS_AS_DISPLAY_TAG)
# ---------------------------------------------------------------------------
# Standalone TYPE signal — pitcher's cumulative season K% z-scored within
# (year, month) cohort >= +0.5 fires the flag. NOT a 4th component of
# boom_stack (the boom_stack_v2 stack=4 cell was n=12 and failed Bonferroni-
# adjusted chi²). Instead it's an INDEPENDENT signal that compounds with
# whatever boom_stack value is present.
#
# Validation: data/research/validation_runs/boom_stack_v2_validation.md
#   - Standalone boom edge: +6.84 pp (p=2.6e-11, n=1,039)
#   - 7/7 years positive (+1.24 to +16.86 pp)
#   - Pooled max |corr| with v1 components: 0.018 (fully orthogonal)
#   - Tier amplification: +6.51 / +6.18 / +9.48 / +16.82 pp at v1 stack=0/1/2/3
HIGH_K_Z_THRESHOLD = 0.5
HIGH_K_MIN_PRIOR_STARTS = 3
HIGH_K_STANDALONE_LIFT_PP = 6.84  # Standalone boom-edge pp from validation.
HIGH_K_TIER_AMP_LIFT_PP = {
    0: 6.51,
    1: 6.18,
    2: 9.48,
    3: 16.82,
}

# Streamer-class threshold (rp3 rank floor). DEPRECATED 2026-06-03 — kept as an
# importable constant for backwards-compat (legacy callers + memory docs) but
# the engine no longer gates on it. The tag now fires for any SP with rp3 row.
STREAMER_RANK_FLOOR = 50


def tier_for_rank(rp3_rank: int) -> str:
    """Map an rp3 rank to the tier label used for boom_stack annotations.

    rank 1-10  -> 'ace'
    rank 11-30 -> 'sp2_sp3'
    rank 31-50 -> 'backend'
    rank 51+   -> 'streamer'
    """
    r = int(rp3_rank)
    if r <= 10:
        return 'ace'
    if r <= 30:
        return 'sp2_sp3'
    if r <= 50:
        return 'backend'
    return 'streamer'


# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_starts_2026() -> pd.DataFrame:
    """Per-start panel for 2026 SPs: (pitcher, game_pk, game_date, pa, k, bb).

    PA filter >= 5 to exclude reliever stints mislabeled as starts.
    """
    cols = ['game_pk', 'game_date', 'pitcher', 'events']
    sc = pd.read_parquet(_STATCAST_2026, columns=cols)
    g = (
        sc.groupby(['pitcher', 'game_pk', 'game_date'])
          .agg(
              pa=('events', lambda s: s.notna().sum()),
              k=('events', lambda s: s.isin(['strikeout', 'strikeout_double_play']).sum()),
              bb=('events', lambda s: s.isin(['walk']).sum()),
          )
          .reset_index()
    )
    g = g[g['pa'] >= 5].copy()
    g['pitcher'] = g['pitcher'].astype('int64')
    g = g.sort_values(['pitcher', 'game_date']).reset_index(drop=True)
    return g


@lru_cache(maxsize=1)
def _load_soft_tertile() -> tuple[float, pd.DataFrame]:
    """Return (33rd-percentile bat_index_recent, team_strength_df).

    Soft offense = LOW bat_index_recent. The bottom tertile is the soft slate.
    """
    ts = pd.read_csv(_TEAM_STRENGTH)
    bri = ts['bat_index_recent'].dropna()
    p33 = float(np.percentile(bri.values, 100.0 / 3.0))
    return p33, ts


# ---------------------------------------------------------------------------
# Component computations
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_park_friendly_set() -> tuple[frozenset, float, int]:
    """Return (set of pitcher-friendly park_team codes, p33 threshold, ref_year).

    "Pitcher-friendly" = pf_wOBA in bottom (lowest) tertile of MLB parks in the
    PRIOR year (_PARK_PF_YEAR). Matches the validation framing exactly.
    """
    pf = pd.read_csv(_PARK_FACTORS)
    pf = pf[pf['year'] == _PARK_PF_YEAR].copy()
    if pf.empty:
        return frozenset(), float('nan'), _PARK_PF_YEAR
    p33 = float(np.percentile(pf['pf_wOBA'].values, 100.0 / 3.0))
    friendly = frozenset(pf.loc[pf['pf_wOBA'] <= p33, 'team_abbr'].astype(str).tolist())
    return friendly, p33, _PARK_PF_YEAR


@lru_cache(maxsize=1)
def _load_pitcher_schedule() -> Optional[pd.DataFrame]:
    """Load the MLB Stats API probable-pitchers schedule (built by
    build_pitcher_schedule.py). Returns None if the file is missing.

    Cols of interest: pitcher (mlb_id, int), park_team, start_idx.
    """
    if not os.path.exists(_PITCHER_SCHEDULE):
        return None
    df = pd.read_csv(_PITCHER_SCHEDULE)
    if 'pitcher' not in df.columns or 'park_team' not in df.columns:
        return None
    df['pitcher'] = df['pitcher'].astype('int64', errors='ignore')
    return df


def _component_park_friendly(pitcher_id: int) -> tuple[int, dict]:
    """Component 4 (NEW 2026-06-03): SP pitching at a park whose PRIOR-year
    pf_wOBA is in the bottom (most-pitcher-friendly) tertile of MLB parks.

    Looked up via pitcher_schedule_2026.csv (the probable-pitchers feed with
    is_home + park_team already resolved). When the pitcher has no confirmed
    next start in the schedule, the flag is 0 (we do NOT fabricate a venue).

    Validation: data/research/validation_runs/park_factor_boom_modifier.md
      - Standalone edge +2.69 pp (z=5.73, 95% CI [+1.80, +3.58])
      - Composite stack 0→4 boom rate: 12.3/15.0/19.4/20.9/22.1%
      - 5/6 years positive; lone -0.27 pp in 2021 (COVID)
    """
    sched = _load_pitcher_schedule()
    detail: dict = {'park_team': None, 'pf_wOBA': None,
                    'pf_year': _PARK_PF_YEAR, 'reason': None}
    if sched is None or sched.empty:
        detail['reason'] = 'no_schedule_file'
        return 0, detail
    try:
        pid = int(pitcher_id)
    except (TypeError, ValueError):
        detail['reason'] = 'bad_pitcher_id'
        return 0, detail
    my = sched[sched['pitcher'] == pid]
    if 'start_idx' in my.columns:
        my = my[my['start_idx'] == 1]
    if my.empty:
        detail['reason'] = 'no_scheduled_start'
        return 0, detail
    park_team = my.iloc[0].get('park_team')
    if park_team is None or (isinstance(park_team, float) and pd.isna(park_team)):
        detail['reason'] = 'no_park_team'
        return 0, detail
    park_team = str(park_team)
    friendly, p33, ref_year = _load_park_friendly_set()
    detail['park_team'] = park_team
    detail['p33_threshold'] = p33
    detail['pf_year'] = ref_year
    # Pull this park's actual pf_wOBA for transparency.
    pf = pd.read_csv(_PARK_FACTORS)
    row = pf[(pf['year'] == ref_year) & (pf['team_abbr'] == park_team)]
    if not row.empty:
        detail['pf_wOBA'] = float(row.iloc[0]['pf_wOBA'])
    fired = int(park_team in friendly)
    if not fired:
        detail['reason'] = 'park_not_in_friendly_tertile'
    return fired, detail


def _component_skill_spike(pitcher_id: int) -> tuple[int, dict]:
    """Component 1: last-5-starts K% - season K% >= +3pp AND
    last-5-starts BB% - season BB% <= -1pp. <5 starts => 0.

    Window switched 3g -> 5g 2026-06-03 after dual-agent validation
    (skill_spike_5g_validation.md + skill_spike_tier_aware_validation.md):
    flat_5g cleans up anti-predictive sign at backend/SP2/3 tiers AND
    is non-inferior at streamer tier; pooled weighted boom edge +2.68 pp
    vs +1.16 pp for 3g; cross-year 7/7 vs 6/7; stack=3 boom rate 26.1% vs 22.8%.
    """
    starts = _load_starts_2026()
    my = starts[starts['pitcher'] == int(pitcher_id)]
    detail = {'n_starts_2026': int(len(my)), 'reason': None}
    if len(my) < 5:
        detail['reason'] = 'insufficient_starts'
        return 0, detail
    season_pa = int(my['pa'].sum())
    season_k_pct = float(my['k'].sum() / max(season_pa, 1))
    season_bb_pct = float(my['bb'].sum() / max(season_pa, 1))
    last5 = my.tail(5)
    l5_pa = int(last5['pa'].sum())
    l5_k_pct = float(last5['k'].sum() / max(l5_pa, 1))
    l5_bb_pct = float(last5['bb'].sum() / max(l5_pa, 1))
    dK_pp = (l5_k_pct - season_k_pct) * 100.0
    dBB_pp = (l5_bb_pct - season_bb_pct) * 100.0
    detail.update({
        'season_k_pct': season_k_pct, 'season_bb_pct': season_bb_pct,
        'last5_k_pct': l5_k_pct, 'last5_bb_pct': l5_bb_pct,
        'delta_k_pp': dK_pp, 'delta_bb_pp': dBB_pp,
    })
    fired = int((dK_pp >= 3.0) and (dBB_pp <= -1.0))
    return fired, detail


def _component_recform_hot(recency_form_gap: Optional[float]) -> tuple[int, dict]:
    """Component 2: recency_form_gap >= +3 from rp3 row."""
    if recency_form_gap is None or pd.isna(recency_form_gap):
        return 0, {'recency_form_gap': None}
    rfg = float(recency_form_gap)
    return int(rfg >= 3.0), {'recency_form_gap': rfg}


def _component_opp_soft(next_opp_team: Optional[str]) -> tuple[int, dict]:
    """Component 3: today's opponent bat_index_recent in soft (bottom) tertile."""
    detail = {'next_opp_team': next_opp_team}
    if not next_opp_team or (isinstance(next_opp_team, float) and pd.isna(next_opp_team)):
        detail['reason'] = 'no_next_opp'
        return 0, detail
    p33, ts = _load_soft_tertile()
    detail['soft_p33_threshold'] = p33
    row = ts[ts['team'] == next_opp_team]
    if row.empty:
        detail['reason'] = 'team_not_in_strength_csv'
        return 0, detail
    bri = float(row.iloc[0]['bat_index_recent'])
    detail['opp_bat_index_recent'] = bri
    fired = int(bri <= p33)
    return fired, detail


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_boom_stack(
    pitcher_id: int,
    recency_form_gap: Optional[float],
    next_opp_team: Optional[str],
    rp3_rank: Optional[int] = None,
) -> dict:
    """Compute boom_stack for a single SP at "now".

    Args:
        pitcher_id:        MLBAM pitcher id (int).
        recency_form_gap:  `recency_form_gap` from the rp3 projection row.
        next_opp_team:     Today's next-opponent team code (3-letter MLB).
        rp3_rank:          SP's current rp3 rank. Used to derive the tier
                           ('ace' / 'sp2_sp3' / 'backend' / 'streamer') and
                           the tier-specific boom% / bust% / mean-FP rates.
                           When None, tier defaults to 'streamer' (the legacy
                           bucket) for back-compat with old callers.

    Returns:
        {
          'boom_stack': int 0-3,
          'components': {'skill_spike','recform_hot','opp_soft'} -> int 0|1,
          'detail': {...per-component diagnostics...},
          'tier': str,                  # 'ace'/'sp2_sp3'/'backend'/'streamer'
          'boom_rate_expected': float,  # tier-specific
          'bust_rate_expected': float,  # tier-specific
          'mean_fp_expected':   float,  # tier-specific
          'skill_spike_anti_predictive': bool,
              # True when tier in {sp2_sp3, backend} AND skill_spike==1 AND
              # boom_stack>=1 — a regression-risk hint, not a boom signal.
        }
    """
    c1, d1 = _component_skill_spike(pitcher_id)
    c2, d2 = _component_recform_hot(recency_form_gap)
    c3, d3 = _component_opp_soft(next_opp_team)
    c4, d4 = _component_park_friendly(pitcher_id)
    total = int(c1 + c2 + c3 + c4)

    if rp3_rank is None:
        tier = 'streamer'
    else:
        tier = tier_for_rank(int(rp3_rank))

    # Tier table goes 0..4 since park_friendly addition; clamp defensively.
    total_clamped = max(0, min(4, total))
    boom_rate = BOOM_RATE_BY_TIER_STACK[tier][total_clamped]
    bust_rate = BUST_RATE_BY_TIER_STACK[tier][total_clamped]
    mean_fp = MEAN_FP_BY_TIER_STACK[tier][total_clamped]

    anti_pred = bool(
        tier in SKILL_SPIKE_ANTIPREDICTIVE_TIERS
        and c1 == 1
        and total >= 1
    )

    return {
        'boom_stack': total,
        'components': {
            'skill_spike': c1,
            'recform_hot': c2,
            'opp_soft': c3,
            'park_friendly': c4,
        },
        'detail': {
            'skill_spike': d1,
            'recform_hot': d2,
            'opp_soft': d3,
            'park_friendly': d4,
        },
        'tier': tier,
        'boom_rate_expected': boom_rate,
        'bust_rate_expected': bust_rate,
        'mean_fp_expected': mean_fp,
        'skill_spike_anti_predictive': anti_pred,
    }


# ---------------------------------------------------------------------------
# HIGH-K ARM compute (standalone display tag — INDEPENDENT of boom_stack)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_high_k_baseline() -> tuple[float, float, dict, str]:
    """Compute the (year, current-month) cohort mean + std of season K%.

    Returns (mean_k_pct, std_k_pct, k_pct_by_pitcher, cohort_label).

    - Pools every SP with >= HIGH_K_MIN_PRIOR_STARTS 2026 starts in the
      latest game-month seen in the statcast_2026 cache.
    - season K% = cumulative-season K / cumulative-season PA, computed as of
      that pitcher's MOST RECENT start in the cohort month. This matches
      the validation framing (cumulative-prior season K% per pitcher).
    - Latest game date in the cache defines the "current month" cohort.
    """
    starts = _load_starts_2026()
    if starts.empty:
        return (float('nan'), float('nan'), {}, '')
    starts = starts.copy()
    starts['game_date'] = pd.to_datetime(starts['game_date'])
    latest = starts['game_date'].max()
    cohort_label = latest.strftime('%Y-%m')
    # Per-pitcher season K% YTD (full season through latest start).
    agg = (
        starts.groupby('pitcher')
              .agg(pa=('pa', 'sum'), k=('k', 'sum'),
                   n_starts=('game_pk', 'count'))
              .reset_index()
    )
    # Cohort restricted to pitchers with >= MIN_PRIOR_STARTS season starts so
    # the baseline isn't polluted by spot-start small samples.
    agg = agg[agg['n_starts'] >= HIGH_K_MIN_PRIOR_STARTS].copy()
    agg['k_pct'] = agg['k'] / agg['pa'].replace(0, np.nan)
    agg = agg.dropna(subset=['k_pct'])
    if agg.empty:
        return (float('nan'), float('nan'), {}, cohort_label)
    mn = float(agg['k_pct'].mean())
    sd = float(agg['k_pct'].std(ddof=0))
    k_by = dict(zip(agg['pitcher'].astype(int), agg['k_pct'].astype(float)))
    n_by = dict(zip(agg['pitcher'].astype(int), agg['n_starts'].astype(int)))
    # Return n_starts alongside k_pct in a single dict for downstream use.
    by_pitcher = {pid: {'k_pct': k_by[pid], 'n_starts': n_by[pid]} for pid in k_by}
    return (mn, sd, by_pitcher, cohort_label)


def compute_high_k_pitcher(pitcher_id: int) -> dict:
    """Compute the HIGH-K ARM standalone display tag for one SP.

    The z-score baseline is the (year, current-month) cohort of all SPs with
    >= HIGH_K_MIN_PRIOR_STARTS 2026 starts. Flag fires when this pitcher's
    season K% z-score >= +HIGH_K_Z_THRESHOLD AND he himself has
    >= HIGH_K_MIN_PRIOR_STARTS starts.

    Returns:
        {
          'is_high_k': bool,
          'k_pct': float | None,      # season K% YTD for this pitcher
          'z_score': float | None,    # z within (year, month) cohort
          'cohort_mean': float,       # cohort mean K%
          'cohort_std': float,        # cohort std K%
          'cohort_label': str,        # 'YYYY-MM' for the cohort month
          'n_starts': int | None,
          'standalone_lift_pp': float,           # +6.84 from validation
          'tier_amp_lift_pp_by_v1_stack': dict,  # per-tier amp lifts
          'reason': str | None,       # populated when is_high_k=False
        }
    """
    mn, sd, by_pitcher, cohort_label = _load_high_k_baseline()
    out: dict = {
        'is_high_k': False,
        'k_pct': None,
        'z_score': None,
        'cohort_mean': mn,
        'cohort_std': sd,
        'cohort_label': cohort_label,
        'n_starts': None,
        'standalone_lift_pp': HIGH_K_STANDALONE_LIFT_PP,
        'tier_amp_lift_pp_by_v1_stack': dict(HIGH_K_TIER_AMP_LIFT_PP),
        'reason': None,
    }
    if not np.isfinite(mn) or not np.isfinite(sd) or sd == 0:
        out['reason'] = 'no_cohort_baseline'
        return out
    rec = by_pitcher.get(int(pitcher_id))
    if rec is None:
        out['reason'] = 'pitcher_below_min_starts_or_missing'
        return out
    k = float(rec['k_pct'])
    n_starts = int(rec['n_starts'])
    z = (k - mn) / sd
    out['k_pct'] = k
    out['z_score'] = float(z)
    out['n_starts'] = n_starts
    if n_starts < HIGH_K_MIN_PRIOR_STARTS:
        out['reason'] = 'insufficient_starts'
        return out
    out['is_high_k'] = bool(z >= HIGH_K_Z_THRESHOLD)
    if not out['is_high_k']:
        out['reason'] = f'z={z:.2f}_below_threshold'
    return out
