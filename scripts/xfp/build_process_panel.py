"""build_process_panel.py — L30 + Season-to-date + Prior-year process panels.

PR 8 sub-action 1 main build script. For a given ``--as-of YYYY-MM-DD`` date,
computes per-SP and per-hitter marker panels in three windows, plus a
direction-adjusted composite z-score and a current-level percentile.

SP markers (9, per ``pitcher_sustainability.py``) are aggregated through the
canonical ``aggregate_sp_markers_statcast`` helper at
``scripts/xfp/lib/process_panel.py``. NO inline SQL anywhere in this file
aggregates SP markers from Statcast directly. NO use of ``*_last21`` fields
from ``rolling_pitchers_2018_2026.csv``. NO hardcoded ``statcast_2026.parquet``
- all parquet paths are parameterized on ``as_of.year``.

Hitter markers (9) come from the ``--as-of`` extension of
``build_batter_rolling_features.py``.

Per plan v11 Decision 12, the production CSVs ship WITHOUT a ``buylow_flag``
column. The flag will be added in a follow-up PR after ``/validate-feature``
passes.

Outputs:
  data/outputs/sp_process_panel.csv
  data/outputs/hitter_process_panel.csv

Usage:
  python -X utf8 scripts/xfp/build_process_panel.py --as-of 2026-06-06
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.xfp.lib.process_panel import (  # noqa: E402
    SP_MARKERS,
    SP_MARKER_DIRS,
    aggregate_sp_markers_statcast,
    resolve_hitter_marker,
)
from scripts.xfp.lib.season_dates import season_start  # noqa: E402

ROOT = _ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

# Hitter canonical marker names + their corresponding rolling-features
# column name (resolved via resolve_hitter_marker for the chase alias).
HITTER_MARKERS = [
    'avg_ev', 'ev90', 'hard_hit_pct', 'barrel_pct', 'xwoba_on_contact',
    'k_pct', 'bb_pct', 'o_swing_pct', 'sweet_spot_pct',
]
HITTER_MARKER_DIRS = {
    'avg_ev':           +1,
    'ev90':             +1,
    'hard_hit_pct':     +1,
    'barrel_pct':       +1,
    'xwoba_on_contact': +1,
    'k_pct':            -1,
    'bb_pct':           +1,
    'o_swing_pct':      -1,  # chase: lower is better
    'sweet_spot_pct':   +1,
}


def _statcast_paths(yr: int) -> Path:
    return CACHE / f'statcast_{yr}.parquet'


def build_sp_panel(as_of: date) -> pd.DataFrame:
    """Build the SP process panel for one as-of date.

    Computes three windows (L30, season-to-date, prior-year) per SP via
    the canonical ``aggregate_sp_markers_statcast`` helper. Cross-year L30
    automatically falls back to LIST input so the helper UNIONs raw rows
    in DuckDB and computes rates from correct per-metric denominators.

    Composite per ``spec-this-out-as-mellow-cerf.md``::

        z_marker_trend = (l30 - std) / sd_pop * dir
        z_marker_base  = (std - prioryr) / sd_pop * dir
        TREND_z        = sum(z_marker_trend)
        BASE_z         = sum(z_marker_base)
        composite      = 0.6 * TREND_z + 0.4 * BASE_z
    """
    yr = as_of.year
    cur_pq = _statcast_paths(yr)
    prev_pq = _statcast_paths(yr - 1)

    if not cur_pq.exists():
        raise FileNotFoundError(f'SP panel: current-year parquet missing: {cur_pq}')

    l30_start = as_of - timedelta(days=30)

    # L30 — cross-year list-form when l30_start falls in the prior year.
    if l30_start.year < yr:
        if not prev_pq.exists():
            raise FileNotFoundError(
                f'SP panel: cross-year L30 requires prior-year parquet but {prev_pq} missing'
            )
        l30 = aggregate_sp_markers_statcast(
            [str(prev_pq), str(cur_pq)],
            date_start=l30_start,
            date_end=as_of,
        )
    else:
        l30 = aggregate_sp_markers_statcast(
            str(cur_pq),
            date_start=l30_start,
            date_end=as_of,
        )

    # Season-to-date using canonical season_start mapping (never hardcoded 3/1).
    std = aggregate_sp_markers_statcast(
        str(cur_pq),
        date_start=season_start(yr),
        date_end=as_of,
    )

    # Prior-year (full season, no date filter).
    pyr = (
        aggregate_sp_markers_statcast(str(prev_pq))
        if prev_pq.exists()
        else pd.DataFrame(columns=['pitcher', 'pitches', 'tbf', 'bip'] + SP_MARKERS)
    )

    panel = _merge_windows_sp(l30, std, pyr)
    panel = _annotate_sp_composite(panel)
    panel = _annotate_sp_level_pct(panel)
    panel = _join_sp_names_and_rp3(panel, cur_pq)
    panel['as_of'] = as_of.isoformat()
    return panel


def _merge_windows_sp(
    l30: pd.DataFrame,
    std: pd.DataFrame,
    pyr: pd.DataFrame,
) -> pd.DataFrame:
    """Outer-join the three SP windows on pitcher with per-window suffixes,
    then filter to the CURRENT-YEAR universe.

    Without the filter, the outer join brings in any pitcher with a
    prior-year row even when they have no current-year activity (retired
    in 2025, called up but not pitched in 2026, etc.). Those rows are
    name-less downstream (Statcast name-map is current-year-only) and
    composite=0.0 from the fillna in _annotate_sp_composite — exactly
    the dashboard-pollution failure mode caught in the 2026-06-06
    review.

    Current-year activity = `pitches_std > 0` OR `pitches_last30 > 0`.
    """
    def _rename(df: pd.DataFrame, sfx: str) -> pd.DataFrame:
        return df.rename(columns={c: f'{c}{sfx}' for c in df.columns if c != 'pitcher'})

    l30r = _rename(l30, '_last30')
    stdr = _rename(std, '_std')
    pyrr = _rename(pyr, '_prioryr')

    out = stdr.merge(l30r, on='pitcher', how='outer').merge(pyrr, on='pitcher', how='outer')

    # Drop prior-year-only rows.
    if 'pitches_std' in out.columns or 'pitches_last30' in out.columns:
        std_active = out.get('pitches_std', pd.Series(0, index=out.index)).fillna(0) > 0
        l30_active = out.get('pitches_last30', pd.Series(0, index=out.index)).fillna(0) > 0
        out = out.loc[std_active | l30_active].copy()
    return out


def _annotate_sp_composite(panel: pd.DataFrame) -> pd.DataFrame:
    """Add per-marker z-scores plus TREND_z / BASE_z / composite columns.

    Direction-adjusted: markers with `dir = -1` get their z multiplied by
    -1 so 'better' is always positive regardless of natural direction.
    """
    for m in SP_MARKERS:
        std_col = f'{m}_std'
        l30_col = f'{m}_last30'
        prior_col = f'{m}_prioryr'
        if std_col not in panel.columns:
            panel[std_col] = np.nan
        if l30_col not in panel.columns:
            panel[l30_col] = np.nan
        if prior_col not in panel.columns:
            panel[prior_col] = np.nan

        # Population SD anchored on season-to-date. ddof=0 -> divides by N,
        # matching the "sd_pop" variable name. Prior `.std()` defaulted to
        # ddof=1 (sample SD) which subtly inflated z-scores when N is small.
        sd_pop = panel[std_col].std(ddof=0)
        if pd.isna(sd_pop) or sd_pop == 0:
            sd_pop = 1.0
        d_trend = panel[l30_col] - panel[std_col]
        d_base = panel[std_col] - panel[prior_col]
        sign = SP_MARKER_DIRS[m]
        panel[f'z_trend_{m}'] = d_trend / sd_pop * sign
        panel[f'z_base_{m}'] = d_base / sd_pop * sign

    # min_count=1 so a row with NO z values across markers stays NaN
    # rather than collapsing to 0.0 (which would silently rank a
    # data-empty pitcher next to a genuine "no change from baseline").
    panel['TREND_z'] = panel[[f'z_trend_{m}' for m in SP_MARKERS]].sum(
        axis=1, skipna=True, min_count=1,
    )
    panel['BASE_z'] = panel[[f'z_base_{m}' for m in SP_MARKERS]].sum(
        axis=1, skipna=True, min_count=1,
    )
    panel['composite'] = 0.6 * panel['TREND_z'] + 0.4 * panel['BASE_z']
    return panel


def _annotate_sp_level_pct(panel: pd.DataFrame) -> pd.DataFrame:
    """Equal-weighted level percentile across markers using L30 values, sign-adjusted."""
    for m in SP_MARKERS:
        col = f'{m}_last30'
        if col not in panel.columns:
            panel[f'pct_last30_{m}'] = np.nan
            continue
        s = panel[col].rank(pct=True)
        if SP_MARKER_DIRS[m] < 0:
            s = 1 - s
        panel[f'pct_last30_{m}'] = s
    panel['level_pct'] = panel[[f'pct_last30_{m}' for m in SP_MARKERS]].mean(axis=1)
    return panel


def _join_sp_names_and_rp3(panel: pd.DataFrame, cur_pq: Path) -> pd.DataFrame:
    """Join player names from Statcast + rp3 rank + per_start from xfp_rp3 projections."""
    import duckdb
    name_df = duckdb.query(
        f"SELECT pitcher, ANY_VALUE(player_name) AS player_name "
        f"FROM read_parquet('{cur_pq.as_posix()}') WHERE pitcher IS NOT NULL "
        f"GROUP BY pitcher"
    ).df()
    name_map = name_df.set_index('pitcher')['player_name'].to_dict()
    panel['player_name'] = panel['pitcher'].map(name_map)

    def _flip(n):
        if isinstance(n, str) and ',' in n:
            a, b = [x.strip() for x in n.split(',', 1)]
            return f'{b} {a}'
        return n

    panel['name'] = panel['player_name'].apply(_flip)

    rp3_path = OUT / 'xfp_rp3_projections.csv'
    if rp3_path.exists():
        rp3 = pd.read_csv(rp3_path)
        idcol = 'mlbam' if 'mlbam' in rp3.columns else ('pitcher' if 'pitcher' in rp3.columns else None)
        if idcol is not None:
            keep = [idcol] + [
                c for c in ('xfp_rp3_per_start', 'xfp_rp3_per_start_sched',
                            'data_quality_tag', 'rank')
                if c in rp3.columns
            ]
            rp3_sub = rp3[keep].rename(columns={idcol: 'pitcher', 'rank': 'rp3_rank'})
            if 'rp3_rank' not in rp3_sub.columns and 'xfp_rp3_per_start' in rp3_sub.columns:
                rp3_sub['rp3_rank'] = (
                    rp3_sub['xfp_rp3_per_start']
                    .rank(ascending=False, method='min')
                    .astype('Int64')
                )
            panel = panel.merge(rp3_sub, on='pitcher', how='left')
    return panel


def _hitter_cache_is_fresh(csv_path: Path, as_of: date) -> bool:
    """The hitter rolling-features cache is fresh when it satisfies BOTH:

      1. cache mtime >= as_of  (the cache covers the requested date), AND
      2. cache mtime >= every relevant source-Statcast parquet's mtime.

    Condition 2 catches the historical-as-of case the 2026-06-06 review
    flagged: if you rebuild a backtest panel for as-of=2024-08-01 and the
    cache was written earlier today (so the date check passes), but the
    underlying 2024 Statcast parquet was refreshed since the cache build,
    the cache is silently stale. Source-mtime forces the rebuild.

    Source parquets considered: statcast_{as_of.year}.parquet and (if it
    exists) statcast_{as_of.year - 1}.parquet for the prior-year backfill.
    """
    if not csv_path.exists():
        return False
    cache_ts = csv_path.stat().st_mtime
    cache_date = datetime.fromtimestamp(cache_ts).date()
    if cache_date < as_of:
        return False
    for yr in (as_of.year, as_of.year - 1):
        src = CACHE / f'statcast_{yr}.parquet'
        if src.exists() and src.stat().st_mtime > cache_ts:
            return False
    return True


def build_hitter_panel(as_of: date, *, force_rebuild: bool = False) -> pd.DataFrame:
    """Build the hitter process panel via build_batter_rolling_features.py --as-of.

    Triggers the batter-features builder in as-of mode (writing a per-date
    CSV with L30/STD/PriorYr suffixes), then composes direction-adjusted
    z-scores + composite + level percentile.

    Args:
        as_of: as-of date for the panel window.
        force_rebuild: if True, ignore the cache and always re-invoke the
            rolling-features builder. Use for historical backtests where
            cache freshness is hard to reason about.
    """
    csv_path = CACHE / f'batter_rolling_features_{as_of.isoformat()}.csv'
    needs_build = force_rebuild or not _hitter_cache_is_fresh(csv_path, as_of)
    if needs_build:
        builder = ROOT / 'scripts' / 'xfp' / 'build_batter_rolling_features.py'
        print(f'[build_process_panel] invoking hitter builder --as-of {as_of}', flush=True)
        r = subprocess.run(
            [sys.executable, '-X', 'utf8', str(builder), '--as-of', as_of.isoformat()],
            cwd=str(ROOT), capture_output=True, text=True, timeout=900,
        )
        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr, file=sys.stderr)
            raise RuntimeError('hitter builder failed in as-of mode')

    panel = pd.read_csv(csv_path)

    # Build canonical -> column-name resolver for marker access.
    for m in HITTER_MARKERS:
        for sfx in ('_last30', '_std', '_prioryr'):
            actual = f'{resolve_hitter_marker(m)}{sfx}'
            canonical = f'{m}{sfx}'
            if actual in panel.columns and canonical != actual:
                panel[canonical] = panel[actual]
            elif canonical not in panel.columns:
                panel[canonical] = np.nan

    for m in HITTER_MARKERS:
        std_col = f'{m}_std'
        l30_col = f'{m}_last30'
        prior_col = f'{m}_prioryr'
        sd_pop = panel[std_col].std(ddof=0)
        if pd.isna(sd_pop) or sd_pop == 0:
            sd_pop = 1.0
        d_trend = panel[l30_col] - panel[std_col]
        d_base = panel[std_col] - panel[prior_col]
        sign = HITTER_MARKER_DIRS[m]
        panel[f'z_trend_{m}'] = d_trend / sd_pop * sign
        panel[f'z_base_{m}'] = d_base / sd_pop * sign

    panel['TREND_z'] = panel[[f'z_trend_{m}' for m in HITTER_MARKERS]].sum(
        axis=1, skipna=True, min_count=1,
    )
    panel['BASE_z'] = panel[[f'z_base_{m}' for m in HITTER_MARKERS]].sum(
        axis=1, skipna=True, min_count=1,
    )
    panel['composite'] = 0.6 * panel['TREND_z'] + 0.4 * panel['BASE_z']

    for m in HITTER_MARKERS:
        col = f'{m}_last30'
        s = panel[col].rank(pct=True)
        if HITTER_MARKER_DIRS[m] < 0:
            s = 1 - s
        panel[f'pct_last30_{m}'] = s
    panel['level_pct'] = panel[[f'pct_last30_{m}' for m in HITTER_MARKERS]].mean(axis=1)

    rh3_path = OUT / 'xfp_rh3_projections.csv'
    if rh3_path.exists():
        rh3 = pd.read_csv(rh3_path)
        idcol = (
            'mlbam' if 'mlbam' in rh3.columns
            else 'batter' if 'batter' in rh3.columns
            else None
        )
        if idcol is not None:
            keep = [idcol] + [
                c for c in ('xfp_rh3_per_game', 'xfp_rh3_per_pa',
                            'expected_total_fp_remaining', 'rank')
                if c in rh3.columns
            ]
            rh3_sub = rh3[keep].rename(columns={idcol: 'batter', 'rank': 'rh3_rank'})
            if 'rh3_rank' not in rh3_sub.columns and 'xfp_rh3_per_game' in rh3_sub.columns:
                rh3_sub['rh3_rank'] = (
                    rh3_sub['xfp_rh3_per_game']
                    .rank(ascending=False, method='min')
                    .astype('Int64')
                )
            panel = panel.merge(rh3_sub, on='batter', how='left')

    panel['as_of'] = as_of.isoformat()
    # Drop the rolling-features build timestamp before writing to the
    # tracked production panel — `built_at` reflects when the cache was
    # built, not the panel's as-of date, and would otherwise produce
    # non-reproducible output across same-day rebuilds.
    if 'built_at' in panel.columns:
        panel = panel.drop(columns=['built_at'])
    return panel


def _assert_no_buylow(df: pd.DataFrame, name: str) -> None:
    if 'buylow_flag' in df.columns:
        raise AssertionError(
            f"{name}: buylow_flag must not be in the production CSV per "
            f"plan v11 Decision 12 (BUY-LOW awaits /validate-feature gate)"
        )


def main(argv=None) -> Tuple[Path, Path]:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        '--as-of',
        type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
        default=date.today(),
        help='As-of date (YYYY-MM-DD). Default: today.',
    )
    p.add_argument('--sp-out', type=Path, default=OUT / 'sp_process_panel.csv')
    p.add_argument('--hitter-out', type=Path, default=OUT / 'hitter_process_panel.csv')
    p.add_argument(
        '--force-rebuild',
        action='store_true',
        help='Ignore the hitter rolling-features cache and always re-invoke '
             'build_batter_rolling_features.py. Use for historical backtests '
             'where cache freshness vs the underlying Statcast parquet is '
             'hard to reason about by mtime alone.',
    )
    args = p.parse_args(argv)

    t0 = time.time()
    print(f'[build_process_panel] as_of={args.as_of} force_rebuild={args.force_rebuild}')

    sp_panel = build_sp_panel(args.as_of)
    _assert_no_buylow(sp_panel, 'sp_process_panel')
    args.sp_out.parent.mkdir(parents=True, exist_ok=True)
    sp_panel.to_csv(args.sp_out, index=False)
    print(f'[build_process_panel] SP panel: {len(sp_panel)} rows -> {args.sp_out}')

    hitter_panel = build_hitter_panel(args.as_of, force_rebuild=args.force_rebuild)
    _assert_no_buylow(hitter_panel, 'hitter_process_panel')
    args.hitter_out.parent.mkdir(parents=True, exist_ok=True)
    hitter_panel.to_csv(args.hitter_out, index=False)
    print(f'[build_process_panel] hitter panel: {len(hitter_panel)} rows -> {args.hitter_out}')

    elapsed = time.time() - t0
    print(f'[build_process_panel] done in {elapsed:.1f}s')
    return args.sp_out, args.hitter_out


if __name__ == '__main__':
    main()
