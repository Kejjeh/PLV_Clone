"""boom_stack — live-prediction computation for SP triangulate cards.

Validated via `scripts/xfp/validate_streamer_boom_stack.py` — Mode B PASS
(SHIP_AS_TAG). See `data/research/validation_runs/streamer_boom_stack_v1_2026-06-03.md`.

Three components per SP at "now":
  1. skill_spike: last-3-starts K% - season K% >= +3pp AND last-3-starts
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

# Expected boom rate / mean FP by bucket (legacy, streamer-pool calibration
# from `streamer_boom_stack_v1_2026-06-03.md`). Kept for backwards-compat with
# any caller still reading the flat keys; new code should use the per-tier
# tables below.
BOOM_RATE_BY_STACK = {0: 0.0970, 1: 0.1208, 2: 0.1362, 3: 0.1741}
MEAN_FP_BY_STACK = {0: 8.44, 1: 9.62, 2: 9.92, 3: 10.14}

# Per-tier historical boom% / bust% / mean FP by stack bucket.
# Source: `data/research/validation_runs/boom_stack_by_tier.md` (n=31,713 SP
# starts, 2018-2025). boom% = P(FP >= 20). bust% = P(FP < 0).
BOOM_RATE_BY_TIER_STACK: dict[str, dict[int, float]] = {
    'ace':      {0: 0.419, 1: 0.446, 2: 0.487, 3: 0.567},
    'sp2_sp3':  {0: 0.270, 1: 0.334, 2: 0.280, 3: 0.312},
    'backend':  {0: 0.203, 1: 0.251, 2: 0.207, 3: 0.215},
    'streamer': {0: 0.094, 1: 0.122, 2: 0.132, 3: 0.174},
}
BUST_RATE_BY_TIER_STACK: dict[str, dict[int, float]] = {
    'ace':      {0: 0.050, 1: 0.037, 2: 0.047, 3: 0.000},
    'sp2_sp3':  {0: 0.060, 1: 0.047, 2: 0.053, 3: 0.043},
    'backend':  {0: 0.096, 1: 0.078, 2: 0.106, 3: 0.046},
    'streamer': {0: 0.185, 1: 0.156, 2: 0.152, 3: 0.152},
}
MEAN_FP_BY_TIER_STACK: dict[str, dict[int, float]] = {
    'ace':      {0: 17.33, 1: 17.93, 2: 18.91, 3: 20.93},
    'sp2_sp3':  {0: 14.51, 1: 15.69, 2: 15.16, 3: 15.89},
    'backend':  {0: 12.59, 1: 13.65, 2: 12.91, 3: 13.63},
    'streamer': {0:  8.36, 1:  9.64, 2:  9.75, 3: 10.60},
}

# Tiers where flag_skill_spike has NEGATIVE per-tier lift (recent K%-spike +
# BB%-drop is regression-predictive, not continuation-predictive).
SKILL_SPIKE_ANTIPREDICTIVE_TIERS = frozenset({'sp2_sp3', 'backend'})

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
def _component_skill_spike(pitcher_id: int) -> tuple[int, dict]:
    """Component 1: last-3-starts K% - season K% >= +3pp AND
    last-3-starts BB% - season BB% <= -1pp. <3 starts => 0."""
    starts = _load_starts_2026()
    my = starts[starts['pitcher'] == int(pitcher_id)]
    detail = {'n_starts_2026': int(len(my)), 'reason': None}
    if len(my) < 3:
        detail['reason'] = 'insufficient_starts'
        return 0, detail
    season_pa = int(my['pa'].sum())
    season_k_pct = float(my['k'].sum() / max(season_pa, 1))
    season_bb_pct = float(my['bb'].sum() / max(season_pa, 1))
    last3 = my.tail(3)
    l3_pa = int(last3['pa'].sum())
    l3_k_pct = float(last3['k'].sum() / max(l3_pa, 1))
    l3_bb_pct = float(last3['bb'].sum() / max(l3_pa, 1))
    dK_pp = (l3_k_pct - season_k_pct) * 100.0
    dBB_pp = (l3_bb_pct - season_bb_pct) * 100.0
    detail.update({
        'season_k_pct': season_k_pct, 'season_bb_pct': season_bb_pct,
        'last3_k_pct': l3_k_pct, 'last3_bb_pct': l3_bb_pct,
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
    total = int(c1 + c2 + c3)

    if rp3_rank is None:
        tier = 'streamer'
    else:
        tier = tier_for_rank(int(rp3_rank))

    boom_rate = BOOM_RATE_BY_TIER_STACK[tier][total]
    bust_rate = BUST_RATE_BY_TIER_STACK[tier][total]
    mean_fp = MEAN_FP_BY_TIER_STACK[tier][total]

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
        },
        'detail': {
            'skill_spike': d1,
            'recform_hot': d2,
            'opp_soft': d3,
        },
        'tier': tier,
        'boom_rate_expected': boom_rate,
        'bust_rate_expected': bust_rate,
        'mean_fp_expected': mean_fp,
        'skill_spike_anti_predictive': anti_pred,
    }
