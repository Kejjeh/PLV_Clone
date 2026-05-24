"""Smoke tests for the shared batter_rolling_features cache.

Strategy: the full build is fast (~1s) so we just (re)build once at
session start and inspect the resulting CSV. If the CSV is older than
1 hour we rebuild; otherwise reuse the artifact.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT_CSV = CACHE / 'batter_rolling_features.csv'
BUILDER = ROOT / 'scripts' / 'xfp' / 'build_batter_rolling_features.py'

EXPECTED_COLUMNS = {
    'batter', 'player_name', 'team_recent', 'total_career_pa',
    'current_l150_xwoba',
    'career_l150_median', 'career_l150_min', 'career_l150_max', 'career_l150_mean',
    'career_percentile',
    'avg_ev', 'ev90', 'hard_hit_pct', 'barrel_pct', 'xwoba_on_contact',
    'k_pct', 'bb_pct', 'chase_pct', 'sweet_spot_pct',
    'avg_ev_l21d', 'ev90_l21d', 'hard_hit_pct_l21d', 'barrel_pct_l21d',
    'xwoba_on_contact_l21d', 'k_pct_l21d', 'bb_pct_l21d',
    'chase_pct_l21d', 'sweet_spot_pct_l21d',
    'n_pa_l21d', 'built_at',
}


@pytest.fixture(scope='module')
def cache_df() -> pd.DataFrame:
    statcast_2026 = CACHE / 'statcast_2026.parquet'
    if not statcast_2026.exists():
        pytest.skip('statcast parquet cache missing; cannot run end-to-end builder test')
    # Rebuild if missing or stale (>1h old)
    stale = (not OUT_CSV.exists()) or (time.time() - OUT_CSV.stat().st_mtime > 3600)
    if stale:
        r = subprocess.run(
            [sys.executable, '-X', 'utf8', str(BUILDER)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=600,
        )
        assert r.returncode == 0, f'builder failed: {r.stderr[-500:]}'
    assert OUT_CSV.exists(), 'builder did not produce the expected CSV'
    return pd.read_csv(OUT_CSV)


def test_cache_file_and_columns(cache_df):
    df = cache_df
    assert len(df) >= 500, f'expected >= 500 batters, got {len(df)}'
    missing = EXPECTED_COLUMNS - set(df.columns)
    assert not missing, f'missing columns: {missing}'


def test_known_stable_batters_plausible(cache_df):
    df = cache_df.set_index('player_name')
    # These guys have huge career samples and well-defined contact profiles.
    for name in ('Aaron Judge', 'Pete Alonso'):
        assert name in df.index, f'{name} missing from cache'
        x = float(df.loc[name, 'current_l150_xwoba'])
        assert 0.30 <= x <= 0.50, f'{name} current_l150_xwoba={x:.3f} out of plausible band'


def test_career_percentile_bounds(cache_df):
    pct = cache_df['career_percentile'].dropna()
    assert ((pct >= 0.0) & (pct <= 1.0)).all(), \
        f'career_percentile out of [0,1]: min={pct.min()} max={pct.max()}'
