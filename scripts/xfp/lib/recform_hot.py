"""recform_hot.py — Live trailing-5-start fp_proxy_per_bf z-score for SPs.

Phase 3 Agent C (Phase 3 follow-up). Surfaces a DISPLAY-ONLY tag on
`/triangulate` SP cards so the user can see "this SP has hot/cold recent
form" without it being part of the verdict synthesis.

Per Agent 5 (`build_recform_hot_retroactive.py` + the validation runs):

  - For each SP, compute the trailing-5-start mean fp_proxy_per_bf as of
    `as_of_date`, where fp_proxy = K + 3.3*IP - H - 2*R - BB - HBP and
    "R" approximates ER (small constant per-pitcher bias, harmless under
    z-scoring).
  - Population: all SPs in the same calendar month with >= 3 starts in
    season-to-date who themselves qualify with >= 3 trailing-window
    starts.
  - z = (this pitcher's mean - cohort mean) / cohort std (ddof=0).
  - Tag: HOT if z >= +0.5, COLD if z <= -0.5, TEPID otherwise. Threshold
    matches HIGH-K ARM for consistency.

Why this isn't promoted into the blend: Agent 5 found recform_hot's R²
contribution is absorbed by `fp_per_start_to` (r=+0.69), so it doesn't
add headline predictive value. The per-stack gradient IS real (mean
ROS FP climbs 8.66 -> 11.25 across recform stack buckets), making it a
fine context tag.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST_2026 = _REPO_ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet'

TRAILING_N = 5
MIN_TRAILING_STARTS = 3
SP_START_BF_MIN = 15           # filter relief stints mislabeled as starts
HOT_Z = 0.5
COLD_Z = -0.5


# ---------------------------------------------------------------------------
# Per-start aggregation (cached)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_starts_2026() -> pd.DataFrame:
    """Per-start panel for 2026 SPs with fp_proxy + BF.

    Mirrors `build_recform_hot_retroactive.per_start_fp_proxy` exactly so
    live z-scores are comparable to the retroactive validation.
    """
    cols = ['game_date', 'pitcher', 'game_pk', 'events',
            'post_bat_score', 'bat_score']
    sc = pd.read_parquet(_STATCAST_2026, columns=cols)
    sc = sc.dropna(subset=['game_date', 'pitcher', 'game_pk']).copy()
    sc['game_date'] = pd.to_datetime(sc['game_date'], errors='coerce')
    sc = sc[sc['game_date'].notna()]

    sc['runs_on_play'] = (
        sc['post_bat_score'].fillna(0) - sc['bat_score'].fillna(0)
    ).clip(lower=0)

    OUT1 = {'field_out', 'strikeout', 'force_out', 'sac_fly', 'sac_bunt',
            'fielders_choice_out', 'fielders_choice', 'strikeout_double_play',
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'pickoff_caught_stealing_home', 'other_out', 'sac_fly_double_play'}
    OUT2 = {'grounded_into_double_play', 'double_play'}
    OUT3 = {'triple_play'}

    sc['outs_on_play'] = 0
    sc.loc[sc['events'].isin(OUT1), 'outs_on_play'] = 1
    sc.loc[sc['events'].isin(OUT2), 'outs_on_play'] = 2
    sc.loc[sc['events'].isin(OUT3), 'outs_on_play'] = 3

    PA_END = {'field_out', 'strikeout', 'home_run', 'single', 'double', 'triple',
              'walk', 'hit_by_pitch', 'force_out', 'grounded_into_double_play',
              'sac_fly', 'sac_bunt', 'fielders_choice', 'fielders_choice_out',
              'strikeout_double_play', 'double_play', 'triple_play',
              'sac_fly_double_play', 'field_error', 'catcher_interf', 'other_out'}
    sc['is_pa']  = sc['events'].isin(PA_END).astype(int)
    sc['is_k']   = sc['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    sc['is_bb']  = (sc['events'] == 'walk').astype(int)
    sc['is_hbp'] = (sc['events'] == 'hit_by_pitch').astype(int)
    sc['is_hit'] = sc['events'].isin({'single', 'double', 'triple', 'home_run'}).astype(int)

    g = (
        sc.groupby(['pitcher', 'game_pk', 'game_date'], observed=True)
          .agg(BF=('is_pa', 'sum'),
               K=('is_k', 'sum'),
               BB=('is_bb', 'sum'),
               HBP=('is_hbp', 'sum'),
               H=('is_hit', 'sum'),
               R=('runs_on_play', 'sum'),
               outs=('outs_on_play', 'sum'))
          .reset_index()
    )
    g = g[g['BF'] >= SP_START_BF_MIN].copy()
    g['IP'] = g['outs'] / 3.0
    # NOT the canonical BrownU FP formula — a deliberate Statcast-source PROXY.
    # Pitch-by-pitch Statcast exposes runs_on_play (R), not earned runs (ER), and
    # no SV/HLD, so this uses −2*R as a stand-in for −2*ER. Do NOT route this to
    # fantasy.scoring.pitcher_fp and do NOT "correct" R→ER: the validated good-
    # start threshold (fp_proxy_per_bf ≥ −0.0476) was calibrated on THIS proxy.
    g['fp_proxy'] = g['K'] + 3.3 * g['IP'] - g['H'] - 2 * g['R'] - g['BB'] - g['HBP']
    g['pitcher'] = g['pitcher'].astype('int64')
    g = g.sort_values(['pitcher', 'game_date']).reset_index(drop=True)
    return g


# ---------------------------------------------------------------------------
# Cohort baseline (cached per as_of_date)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _cohort_baseline(as_of_iso: str) -> tuple[float, float, dict, str]:
    """Return (mu, sigma, per_pitcher_recform_fp_per_bf, cohort_label).

    `cohort_label` is the YYYY-MM of as_of_date (matches the
    HIGH-K-ARM cohort framing — same-month population).

    `per_pitcher_recform_fp_per_bf` keys: pitcher_id -> {'fp_per_bf': float,
    'trail_starts': int, 'mean_per_start_fp': float}.
    """
    starts = _load_starts_2026()
    if starts.empty:
        return (float('nan'), float('nan'), {}, '')
    as_of = pd.Timestamp(as_of_iso)
    cohort_label = as_of.strftime('%Y-%m')

    before = starts[starts['game_date'] <= as_of].copy()
    if before.empty:
        return (float('nan'), float('nan'), {}, cohort_label)

    # Trailing N starts per pitcher
    trail = (
        before.groupby('pitcher', observed=True)
              .tail(TRAILING_N)
    )
    rec = (
        trail.groupby('pitcher', observed=True)
             .agg(trail_bf=('BF', 'sum'),
                  trail_fp=('fp_proxy', 'sum'),
                  trail_starts=('game_pk', 'count'))
             .reset_index()
    )
    rec = rec[rec['trail_starts'] >= MIN_TRAILING_STARTS].copy()
    if rec.empty:
        return (float('nan'), float('nan'), {}, cohort_label)
    rec['fp_per_bf'] = rec['trail_fp'] / rec['trail_bf'].replace(0, np.nan)
    rec = rec.dropna(subset=['fp_per_bf'])
    if rec.empty:
        return (float('nan'), float('nan'), {}, cohort_label)
    mu = float(rec['fp_per_bf'].mean())
    sd = float(rec['fp_per_bf'].std(ddof=0))
    rec['mean_per_start_fp'] = rec['trail_fp'] / rec['trail_starts']
    by_p = {
        int(p): {
            'fp_per_bf': float(f),
            'trail_starts': int(ts),
            'mean_per_start_fp': float(mps),
        }
        for p, f, ts, mps in zip(rec['pitcher'], rec['fp_per_bf'],
                                 rec['trail_starts'], rec['mean_per_start_fp'])
    }
    return (mu, sd, by_p, cohort_label)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_recform_z(mlbam_id: int,
                      as_of_date: Optional[str | pd.Timestamp] = None) -> Optional[float]:
    """Return the trailing-5-start fp_proxy_per_bf z-score for `mlbam_id`,
    or None if the pitcher has fewer than MIN_TRAILING_STARTS starts on
    or before `as_of_date` (defaults to today)."""
    if as_of_date is None:
        as_of_iso = pd.Timestamp.now().strftime('%Y-%m-%d')
    else:
        as_of_iso = pd.Timestamp(as_of_date).strftime('%Y-%m-%d')
    mu, sd, by_p, _ = _cohort_baseline(as_of_iso)
    if not np.isfinite(mu) or not np.isfinite(sd) or sd == 0:
        return None
    try:
        pid = int(mlbam_id)
    except (TypeError, ValueError):
        return None
    rec = by_p.get(pid)
    if rec is None:
        return None
    return float((rec['fp_per_bf'] - mu) / sd)


def recform_tag(z: Optional[float]) -> Optional[str]:
    """Return 'HOT' / 'COLD' / 'TEPID' for a z-score, or None when z is None."""
    if z is None:
        return None
    try:
        zf = float(z)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(zf):
        return None
    if zf >= HOT_Z:
        return 'HOT'
    if zf <= COLD_Z:
        return 'COLD'
    return 'TEPID'


def compute_recform(mlbam_id: int,
                    as_of_date: Optional[str | pd.Timestamp] = None) -> dict:
    """Convenience: full structured result for surfacing in triangulate.

    Returns:
        {
          'z': float | None,
          'tag': 'HOT' | 'COLD' | 'TEPID' | None,
          'trail_starts': int | None,
          'mean_per_start_fp': float | None,
          'cohort_label': str,
          'cohort_mean_fp_per_bf': float,
          'cohort_std_fp_per_bf': float,
          'reason': str | None,
        }
    """
    if as_of_date is None:
        as_of_iso = pd.Timestamp.now().strftime('%Y-%m-%d')
    else:
        as_of_iso = pd.Timestamp(as_of_date).strftime('%Y-%m-%d')
    mu, sd, by_p, cohort_label = _cohort_baseline(as_of_iso)
    out: dict = {
        'z': None,
        'tag': None,
        'trail_starts': None,
        'mean_per_start_fp': None,
        'cohort_label': cohort_label,
        'cohort_mean_fp_per_bf': mu if np.isfinite(mu) else None,
        'cohort_std_fp_per_bf': sd if np.isfinite(sd) else None,
        'reason': None,
    }
    if not np.isfinite(mu) or not np.isfinite(sd) or sd == 0:
        out['reason'] = 'no_cohort_baseline'
        return out
    try:
        pid = int(mlbam_id)
    except (TypeError, ValueError):
        out['reason'] = 'bad_pitcher_id'
        return out
    rec = by_p.get(pid)
    if rec is None:
        out['reason'] = 'insufficient_trailing_starts'
        return out
    z = float((rec['fp_per_bf'] - mu) / sd)
    out['z'] = z
    out['tag'] = recform_tag(z)
    out['trail_starts'] = rec['trail_starts']
    out['mean_per_start_fp'] = rec['mean_per_start_fp']
    return out
