"""variance_bands — loader for the era-general subseason variance bands.

Source table: data/research/xfp_cache/subseason_variance_bands.csv, built by
scripts/xfp/build_subseason_variance_bands.py from a stratified MLB Stats API
gameLog panel (2010-2025, 5,100 player-seasons; see
data/research/validation_runs/subseason_variance_bands_2026-07-10.md).

Consumers: run_matchup_leverage.py and run_season_sim.py use these as the
FALLBACK sigma source for thin-history players (Rule 13, decision layer only —
the primary per-player empirical bootstrap path is untouched, and rh3/rp3/
rprs2 sigmas still win when present).

Key: (player_type H/SP/RP, horizon game/week/month, tier T1/T2/T3 by season
volume tercile, era). Default lookup = tier T2, era 2021-25 (current run
environment). All lookups degrade gracefully to the caller's `default` if the
CSV is missing or the cell is absent — engines must never crash on a missing
bands file.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BANDS_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'subseason_variance_bands.csv'

_CACHE: dict = {}


def load_bands():
    """-> DataFrame of the bands table, or None if unavailable. Cached."""
    if 'df' not in _CACHE:
        try:
            import pandas as pd
            _CACHE['df'] = pd.read_csv(BANDS_CSV)
        except Exception as e:  # noqa: BLE001 — missing/corrupt file -> None
            _CACHE['df'] = None
            # Degrading to the caller's default is DELIBERATE (engines must never
            # crash on a missing bands file) but it must not be invisible: a
            # P(win) built on caller defaults otherwise looks identical to one
            # built on the measured 2010-2025 table. One line, once per process
            # (the flag lives in _CACHE so it resets with the table).
            if not _CACHE.get('_notified'):
                _CACHE['_notified'] = True
                print(f"  [variance_bands] WARN table unreadable ({BANDS_CSV}): "
                      f"{type(e).__name__} — falling back to caller-supplied sigmas",
                      file=sys.stderr)
    return _CACHE['df']


def band_row(player_type: str, horizon: str = 'game', tier: str = 'T2',
             era: str = '2021-25') -> dict | None:
    """One bands cell as a dict, or None."""
    df = load_bands()
    if df is None:
        return None
    key = (player_type, horizon, tier, era)
    if key not in _CACHE:
        m = df[(df['player_type'] == player_type) & (df['horizon'] == horizon)
               & (df['tier'] == tier) & (df['era'] == era)]
        _CACHE[key] = m.iloc[0].to_dict() if len(m) else None
    return _CACHE[key]


def fallback_sigma(player_type: str, horizon: str = 'game', tier: str = 'T2',
                   era: str = '2021-25', default: float | None = None) -> float | None:
    """Honest per-window total-FP sigma for a thin-history player.

    horizon='game' -> per-game (H) / per-start (SP) / per-appearance (RP) FP SD.
    Falls back to `default` when the bands table or cell is unavailable.
    """
    row = band_row(player_type, horizon, tier, era)
    if row is None:
        return default
    try:
        v = float(row['sd_fp_total_per_horizon'])
        return v if v > 0 else default
    except Exception:  # noqa: BLE001
        return default


def shrink_k(player_type: str, horizon: str = 'game', tier: str = 'T2',
             era: str = '2021-25', default: float | None = None) -> float | None:
    """Empirical shrinkage k (units: PA for H, starts for SP, apps for RP):
    a horizon-window mean deserves weight n/(n+k) against the season mean."""
    row = band_row(player_type, horizon, tier, era)
    if row is None:
        return default
    try:
        v = float(row['shrink_k'])
        return v if v == v and v > 0 else default   # NaN-safe
    except Exception:  # noqa: BLE001
        return default
