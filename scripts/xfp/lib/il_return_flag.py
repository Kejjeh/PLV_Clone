"""il_return_flag — standalone display tag for SP triangulate cards.

Salvaged from the otherwise-rejected bust_stack_v2_context research program.
See `data/research/validation_runs/bust_stack_v2_context_validation.md`.

The component `flag_first_back_long_IL` (pitcher's previous MLB start was
>= 30 calendar days before the next scheduled start — proxy for "first
start back from a 30+ day IL stint") was the ONLY one of 5 context
components with an independently-significant bust signal:

  - Fire rate: 2.02% (n=640 SP-starts, 2018-2025 ex-2020)
  - bust@flag=1: 17.50%   bust@flag=0: 14.57%
  - Lift: +2.93 pp (chi²=4.07, p=0.044)
  - Independent of all 3 boom_stack components (|r| < 0.03)

It did NOT clear the Bonferroni-adjusted gate inside a stack, so it is
NOT a bust_stack component. The salvage path is a standalone display tag
on triangulate SP cards — same pattern as HIGH-K ARM and catcher framing
(layer on top of boom_stack, never override the verdict).

This module derives, on the fly:

  1. Pitcher's most recent 2026 MLB start date from `statcast_2026.parquet`
     (any appearance with >= 5 PA on a given date counts as a start).
  2. Pitcher's next scheduled start date from `pitcher_schedule_2026.csv`
     (the MLB-Stats-API probables feed). Falls back to today() when no
     scheduled start is in the feed (IL'd / non-active pitchers).
  3. Gap in days. Flag fires when gap >= IL_RETURN_DAYS_THRESHOLD (30).

Public API: `compute_il_return_flag(pitcher_id: int) -> dict`.

Schema additive only. Defensive: any error / missing data => flag False.
"""
from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from typing import Optional

import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_STATCAST_2026 = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'statcast_2026.parquet')
_PITCHER_SCHEDULE = os.path.join(_REPO_ROOT, 'data', 'research', 'xfp_cache', 'pitcher_schedule_2026.csv')

# Validated threshold from bust_stack_v2_context_validation.md.
IL_RETURN_DAYS_THRESHOLD = 30
# Lift on bust@flag=1 vs flag=0, from validation (n=640, p=0.044).
IL_RETURN_BUST_LIFT_PP = 2.93


@lru_cache(maxsize=1)
def _load_last_start_per_pitcher_2026() -> dict[int, pd.Timestamp]:
    """pitcher (mlbam, int) -> last 2026 MLB start date (Timestamp).

    A "start" here is any (pitcher, game_date) where the pitcher faced
    >= 5 PA — matches the per_start panel filter used throughout the
    repo. We derive it from statcast_2026.parquet so the module has no
    external dependency at import-time."""
    if not os.path.exists(_STATCAST_2026):
        return {}
    try:
        sc = pd.read_parquet(
            _STATCAST_2026,
            columns=['pitcher', 'game_date', 'events'],
        )
    except Exception:
        return {}
    if sc.empty:
        return {}
    sc = sc.dropna(subset=['pitcher', 'game_date']).copy()
    sc['game_date'] = pd.to_datetime(sc['game_date'])
    # PA count per (pitcher, date) via non-null events.
    pa = (sc.assign(_is_pa=sc['events'].notna().astype(int))
            .groupby(['pitcher', 'game_date'])['_is_pa'].sum()
            .reset_index())
    pa = pa[pa['_is_pa'] >= 5]
    if pa.empty:
        return {}
    last = pa.groupby('pitcher')['game_date'].max().reset_index()
    return {int(p): pd.Timestamp(d) for p, d in zip(last['pitcher'], last['game_date'])}


@lru_cache(maxsize=1)
def _load_next_scheduled_start() -> dict[int, pd.Timestamp]:
    """pitcher (mlbam) -> earliest scheduled 2026 start_date >= today.

    Pulled from pitcher_schedule_2026.csv (MLB-Stats-API probables feed).
    Pitchers not in the feed (IL'd, undeclared) get no entry — the caller
    will then fall back to date.today() for the gap calculation."""
    if not os.path.exists(_PITCHER_SCHEDULE):
        return {}
    try:
        df = pd.read_csv(_PITCHER_SCHEDULE)
    except Exception:
        return {}
    if 'pitcher' not in df.columns or 'game_date' not in df.columns:
        return {}
    df = df.dropna(subset=['pitcher', 'game_date']).copy()
    df['game_date'] = pd.to_datetime(df['game_date'], errors='coerce')
    df = df.dropna(subset=['game_date'])
    today = pd.Timestamp(date.today())
    df = df[df['game_date'] >= today]
    if df.empty:
        return {}
    nxt = df.groupby('pitcher')['game_date'].min().reset_index()
    return {int(p): pd.Timestamp(d) for p, d in zip(nxt['pitcher'], nxt['game_date'])}


def compute_il_return_flag(pitcher_id: int) -> dict:
    """Compute the IL_RETURN standalone display tag for one SP.

    Args:
        pitcher_id: MLBAM pitcher id (int).

    Returns:
        {
          'is_first_back_long_il': bool,
          'days_since_last_start': int | None,
          'last_start_date':       str | None,   # 'YYYY-MM-DD'
          'reference_date':        str | None,   # next scheduled start, or today()
          'reference_source':      str,          # 'next_scheduled' | 'today' | 'none'
          'threshold_days':        int,          # 30
          'baseline_bust_pp':      float,        # +2.93 from validation
          'reason':                str | None,
        }
    """
    out = {
        'is_first_back_long_il': False,
        'days_since_last_start': None,
        'last_start_date': None,
        'reference_date': None,
        'reference_source': 'none',
        'threshold_days': IL_RETURN_DAYS_THRESHOLD,
        'baseline_bust_pp': IL_RETURN_BUST_LIFT_PP,
        'reason': None,
    }
    try:
        pid = int(pitcher_id)
    except (TypeError, ValueError):
        out['reason'] = 'bad_pitcher_id'
        return out
    try:
        last_map = _load_last_start_per_pitcher_2026()
    except Exception:
        out['reason'] = 'last_start_load_failed'
        return out
    last = last_map.get(pid)
    if last is None:
        out['reason'] = 'no_2026_start'
        return out
    try:
        sched_map = _load_next_scheduled_start()
    except Exception:
        sched_map = {}
    nxt = sched_map.get(pid)
    if nxt is not None:
        ref = nxt
        out['reference_source'] = 'next_scheduled'
    else:
        ref = pd.Timestamp(date.today())
        out['reference_source'] = 'today'
    gap = int((ref - last).days)
    out['days_since_last_start'] = gap
    out['last_start_date'] = last.strftime('%Y-%m-%d')
    out['reference_date'] = ref.strftime('%Y-%m-%d')
    if gap >= IL_RETURN_DAYS_THRESHOLD:
        out['is_first_back_long_il'] = True
    else:
        out['reason'] = f'gap_{gap}d_below_threshold'
    return out
