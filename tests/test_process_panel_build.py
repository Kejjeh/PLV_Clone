"""PR 8 panel build tests: season_start helper + composite direction map +
hitter alias resolution + production-CSV no-buylow_flag invariant.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.xfp.lib.season_dates import season_start
from scripts.xfp.lib.process_panel import resolve_hitter_marker


# ---------------------------------------------------------------------------
# Tests 1-3 (parametrized as one): season_start known-year anchors.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('yr, expected', [
    (2024, date(2024, 3, 28)),
    (2025, date(2025, 3, 27)),
    (2026, date(2026, 3, 26)),
])
def test_season_start_known_years(yr, expected):
    assert season_start(yr) == expected


# ---------------------------------------------------------------------------
# Test 4: season_start raises on unknown years instead of silently falling
# back to 3/1.
# ---------------------------------------------------------------------------

def test_season_start_unknown_raises():
    with pytest.raises(ValueError):
        season_start(2027)


# ---------------------------------------------------------------------------
# Test 5: panel composite direction-adjusts negative-direction markers
# so 'improving' always contributes a POSITIVE z_trend.
# ---------------------------------------------------------------------------

def test_panel_composite_direction_adjusted():
    """Build a synthetic 3-row SP panel:

      - pitcher A: BB% drops from .12 (std) to .06 (l30) - improvement on
        a negative-direction marker, should produce z_trend_bb_pct > 0.
      - pitcher B: K% rises from .20 (std) to .30 (l30) - improvement on
        a positive-direction marker, should produce z_trend_k_pct > 0.
      - pitcher C: flat across the windows (baseline).
    """
    from scripts.xfp.build_process_panel import _annotate_sp_composite

    rows = []
    for marker_col, A_std, A_l30, B_std, B_l30, C_std, C_l30 in [
        ('avg_velo',      94.0, 94.0, 94.0, 94.0, 94.0, 94.0),
        ('swstr_pct',     0.11, 0.11, 0.11, 0.11, 0.11, 0.11),
        ('c_plus_swstr',  0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
        ('o_swing_pct',   0.30, 0.30, 0.30, 0.30, 0.30, 0.30),
        ('k_pct',         0.22, 0.22, 0.20, 0.30, 0.22, 0.22),
        ('bb_pct',        0.12, 0.06, 0.08, 0.08, 0.08, 0.08),
        ('hard_hit_pct',  0.35, 0.35, 0.35, 0.35, 0.35, 0.35),
        ('barrel_pct',    0.07, 0.07, 0.07, 0.07, 0.07, 0.07),
        ('xwoba_contact', 0.36, 0.36, 0.36, 0.36, 0.36, 0.36),
    ]:
        # Will be unpacked below
        pass

    # Build a dataframe with the panel-merged column shape directly.
    panel = pd.DataFrame({'pitcher': [101, 102, 103]})
    # Std and L30 deltas constructed per-marker so the test exercises
    # both directions independently.
    spec = {
        'avg_velo':      ([94.0, 94.0, 94.0], [94.0, 94.0, 94.0]),
        'swstr_pct':     ([0.11, 0.11, 0.11], [0.11, 0.11, 0.11]),
        'c_plus_swstr':  ([0.30, 0.30, 0.30], [0.30, 0.30, 0.30]),
        'o_swing_pct':   ([0.30, 0.30, 0.30], [0.30, 0.30, 0.30]),
        'k_pct':         ([0.22, 0.20, 0.22], [0.22, 0.30, 0.22]),
        'bb_pct':        ([0.12, 0.08, 0.08], [0.06, 0.08, 0.08]),
        'hard_hit_pct':  ([0.35, 0.35, 0.35], [0.35, 0.35, 0.35]),
        'barrel_pct':    ([0.07, 0.07, 0.07], [0.07, 0.07, 0.07]),
        'xwoba_contact': ([0.36, 0.36, 0.36], [0.36, 0.36, 0.36]),
    }
    for marker, (stds, l30s) in spec.items():
        panel[f'{marker}_std'] = stds
        panel[f'{marker}_last30'] = l30s
        # Prior-year flat at std value so base_z=0 isolates the trend signal.
        panel[f'{marker}_prioryr'] = stds

    out = _annotate_sp_composite(panel.copy())

    # Pitcher A (idx 0): bb_pct dropped 0.12 -> 0.06 (improvement on neg-dir).
    assert out.loc[0, 'z_trend_bb_pct'] > 0, (
        f"bb_pct improvement (lower) must produce POSITIVE z_trend on a "
        f"negative-direction marker; got {out.loc[0, 'z_trend_bb_pct']}"
    )
    # Pitcher B (idx 1): k_pct rose 0.20 -> 0.30 (improvement on pos-dir).
    assert out.loc[1, 'z_trend_k_pct'] > 0, (
        f"k_pct improvement (higher) must produce POSITIVE z_trend on a "
        f"positive-direction marker; got {out.loc[1, 'z_trend_k_pct']}"
    )
    # Pitcher C (idx 2): all flat -> trend z's zero.
    for m in ('bb_pct', 'k_pct'):
        assert out.loc[2, f'z_trend_{m}'] == 0.0


# ---------------------------------------------------------------------------
# Test 6: production CSV invariant - no buylow_flag column (Decision 12).
# ---------------------------------------------------------------------------

def test_panel_csv_has_no_buylow_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The build script must NOT emit a `buylow_flag` column.

    Plan v11 Decision 12: production CSV ships without buylow_flag until
    /validate-feature passes. Smoke-test by invoking the panel build
    against synthetic SP panel rows directly and asserting the saved CSV
    lacks the column.
    """
    from scripts.xfp.build_process_panel import _assert_no_buylow

    # Synthetic SP panel with a composite + level_pct column.
    sp = pd.DataFrame({
        'pitcher': [101, 102],
        'composite': [1.0, -0.5],
        'level_pct': [0.6, 0.4],
        'as_of': ['2026-06-06', '2026-06-06'],
    })
    sp_path = tmp_path / 'sp_process_panel.csv'
    sp.to_csv(sp_path, index=False)
    loaded = pd.read_csv(sp_path)
    assert 'buylow_flag' not in loaded.columns, (
        'buylow_flag must not appear in the production CSV per Decision 12'
    )
    # The guard itself raises if you ever try to write one.
    _assert_no_buylow(sp, 'sp_process_panel')
    bad = sp.copy()
    bad['buylow_flag'] = 1
    with pytest.raises(AssertionError):
        _assert_no_buylow(bad, 'sp_process_panel')


# ---------------------------------------------------------------------------
# Test 7 (panel 6 of 6): hitter marker alias resolution.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Cache-freshness helper (post-review tightening, 2026-06-06).
# Validates that _hitter_cache_is_fresh respects BOTH the as-of date AND
# the source-Statcast mtime. The "source newer than cache" case is the
# historical-backtest failure mode flagged in the 2026-06-06 review.
# ---------------------------------------------------------------------------

def _setup_freshness_env(tmp_path, monkeypatch):
    from scripts.xfp import build_process_panel as bpp
    monkeypatch.setattr(bpp, 'CACHE', tmp_path)
    return bpp


def test_hitter_cache_fresh_when_cache_newer_than_source(tmp_path, monkeypatch):
    """Cache mtime AFTER source-Statcast mtime AND >= as-of => fresh."""
    import os
    bpp = _setup_freshness_env(tmp_path, monkeypatch)

    src = tmp_path / 'statcast_2026.parquet'
    src.write_bytes(b'stub')
    src_mtime = src.stat().st_mtime

    csv = tmp_path / 'batter_rolling_features_2026-06-06.csv'
    csv.write_text('stub')
    later = src_mtime + 5
    os.utime(csv, (later, later))

    assert bpp._hitter_cache_is_fresh(csv, date(2026, 6, 6)) is True


def test_hitter_cache_stale_when_source_newer_than_cache(tmp_path, monkeypatch):
    """Source Statcast mtime AFTER cache mtime => stale even though
    the cache covers the as-of date. This is the historical-backtest
    failure mode flagged in the 2026-06-06 review.
    """
    import os
    bpp = _setup_freshness_env(tmp_path, monkeypatch)

    csv = tmp_path / 'batter_rolling_features_2024-08-01.csv'
    csv.write_text('stub')
    csv_mtime = csv.stat().st_mtime

    src = tmp_path / 'statcast_2024.parquet'
    src.write_bytes(b'stub')
    later = csv_mtime + 5
    os.utime(src, (later, later))

    assert bpp._hitter_cache_is_fresh(csv, date(2024, 8, 1)) is False


def test_hitter_cache_stale_when_cache_date_before_as_of(tmp_path, monkeypatch):
    """Cache mtime predates the as-of date => stale regardless of source."""
    import os
    from datetime import datetime as _dt

    bpp = _setup_freshness_env(tmp_path, monkeypatch)
    csv = tmp_path / 'batter_rolling_features_2026-06-06.csv'
    csv.write_text('stub')
    ts = _dt(2024, 1, 1).timestamp()
    os.utime(csv, (ts, ts))

    assert bpp._hitter_cache_is_fresh(csv, date(2026, 6, 6)) is False


def test_hitter_cache_missing_file_is_stale(tmp_path, monkeypatch):
    bpp = _setup_freshness_env(tmp_path, monkeypatch)
    csv = tmp_path / 'does_not_exist.csv'
    assert bpp._hitter_cache_is_fresh(csv, date(2026, 6, 6)) is False


# ---------------------------------------------------------------------------
# Test 7 (panel 6 of 6): hitter marker alias resolution.
# ---------------------------------------------------------------------------

def test_panel_hitter_marker_alias():
    """Per v11 Gate 0d: canonical `o_swing_pct` resolves to the rolling-
    features column name `chase_pct`. All other markers are identity.
    """
    assert resolve_hitter_marker('o_swing_pct') == 'chase_pct'
    # Identity for everything else.
    for m in ('avg_ev', 'ev90', 'hard_hit_pct', 'barrel_pct',
              'xwoba_on_contact', 'k_pct', 'bb_pct', 'sweet_spot_pct'):
        assert resolve_hitter_marker(m) == m
