"""MA0 — Calibration regression for matchup dashboard projections.

Reads `data/outputs/predictions_history.csv`, identifies completed periods,
treats `max(wtd)` per period as the "actual final" outcome, and fits a
scalar correction factor: scalar = sum(actual) / sum(projected).

Output: `data/models/matchup_calibration.json`

The scalar is consumed by `project_player()` in build_matchup_dashboard.py
as the final MA7 residual multiplier.

Usage:
    python scripts/xfp/calibrate_matchup_projection.py
    python scripts/xfp/calibrate_matchup_projection.py --backtest

Backtest mode prints per-period before/after MAE for inspection.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = ROOT / 'data' / 'outputs' / 'predictions_history.csv'
OUTPUT_PATH = ROOT / 'data' / 'models' / 'matchup_calibration.json'


def load_completed_periods(today_iso: str | None = None) -> pd.DataFrame:
    """For each (period, team), return (projected_total, actual_total).

    Treats a period as 'completed' if its latest snapshot date is at least
    7 days before today (i.e., the matchup period has rolled over).

    For each completed period:
      - projected_total = first-snapshot's projected_total (initial prediction)
      - actual_total = max(wtd) across all snapshots (proxy for final)

    Returns long-format DataFrame: period, team_side ('my'|'opp'),
    projected_total, actual_total.
    """
    if not HISTORY_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_PATH)
    if len(df) == 0:
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'])
    today = pd.to_datetime(today_iso) if today_iso else pd.Timestamp.today().normalize()

    has_actual_cols = 'actual_my_final' in df.columns and 'actual_opp_final' in df.columns
    out_rows = []
    for period, sub in df.groupby('period'):
        sub = sub.sort_values('date')
        first_snap = sub['date'].min()
        period_start = first_snap - pd.Timedelta(days=first_snap.weekday())
        period_end = period_start + pd.Timedelta(days=6)
        if today <= period_end:
            continue  # period still open
        first = sub.iloc[0]
        # Prefer true Sunday-night actuals (from fetch_closed_matchup_actuals.py).
        # Fall back to max(my_wtd) proxy only if actuals not yet backfilled — that
        # proxy systematically under-counts the period's full output.
        if has_actual_cols and pd.notna(sub['actual_my_final'].iloc[0]):
            my_actual = float(sub['actual_my_final'].iloc[0])
            opp_actual = float(sub['actual_opp_final'].iloc[0])
            actual_source = 'espn_box_score'
        else:
            my_actual = float(sub['my_wtd'].max())
            opp_actual = float(sub['opp_wtd'].max())
            actual_source = 'max_wtd_proxy'
        out_rows.append({
            'period': int(period), 'team_side': 'my',
            'projected_total': float(first['my_projected_total']),
            'actual_total': my_actual, 'actual_source': actual_source,
            'n_snapshots': len(sub),
        })
        out_rows.append({
            'period': int(period), 'team_side': 'opp',
            'projected_total': float(first['opp_projected_total']),
            'actual_total': opp_actual, 'actual_source': actual_source,
        })
    return pd.DataFrame(out_rows)


def fit_calibration(completed: pd.DataFrame) -> dict:
    """Fit a single scalar correction. scalar = sum(actual) / sum(projected).

    Pooled across all (period, team_side) observations because n is small.
    A linear (actual ~ a*projected + b) fit isn't useful at n<5.
    """
    if len(completed) == 0:
        return {
            'scalar_correction': 1.0,
            'n_observations': 0,
            'n_periods': 0,
            'mae_before': None,
            'mae_after': None,
            'method': 'NO_DATA',
            'fit_date': datetime.now().isoformat(),
            'note': 'No completed periods yet — scalar=1.0 (identity)',
        }

    sum_actual = completed['actual_total'].sum()
    sum_projected = completed['projected_total'].sum()
    scalar = float(sum_actual / sum_projected) if sum_projected > 0 else 1.0

    # MAE before/after
    before_errors = (completed['actual_total'] - completed['projected_total']).abs()
    after_errors = (completed['actual_total'] - completed['projected_total'] * scalar).abs()
    mae_before = float(before_errors.mean())
    mae_after = float(after_errors.mean())

    return {
        'scalar_correction': round(scalar, 4),
        'n_observations': int(len(completed)),
        'n_periods': int(completed['period'].nunique()),
        'periods_used': sorted(completed['period'].unique().tolist()),
        'mae_before': round(mae_before, 2),
        'mae_after': round(mae_after, 2),
        'mae_improvement_pct': round((mae_before - mae_after) / mae_before * 100, 1) if mae_before > 0 else 0.0,
        'method': 'POOLED_SCALAR',
        'fit_date': datetime.now().isoformat(),
        'note': (f'Scalar={scalar:.3f} → multiply all projections by this. '
                 f'sample is small (n={len(completed)}); refit weekly as more periods close.'),
    }


def print_backtest_detail(completed: pd.DataFrame, scalar: float) -> None:
    print('\n=== Per-(period, team) backtest ===')
    print(f'{"Period":>6} | {"Team":<5} | {"Projected":>10} | {"Actual":>8} | {"Err":>7} | {"Adj proj":>9} | {"Err adj":>8}')
    print('-' * 75)
    for _, r in completed.iterrows():
        adj = r['projected_total'] * scalar
        err = r['actual_total'] - r['projected_total']
        err_adj = r['actual_total'] - adj
        print(f'{int(r["period"]):>6} | {r["team_side"]:<5} | {r["projected_total"]:>10.1f} | '
              f'{r["actual_total"]:>8.1f} | {err:>+7.1f} | {adj:>9.1f} | {err_adj:>+8.1f}')


def main():
    parser = argparse.ArgumentParser(description='Calibrate matchup dashboard projection scalar.')
    parser.add_argument('--backtest', action='store_true',
                        help='Print per-period before/after MAE detail.')
    parser.add_argument('--today', type=str, default=None,
                        help='Override "today" for period-completion check (ISO date).')
    args = parser.parse_args()

    completed = load_completed_periods(today_iso=args.today)
    print(f'Completed (period, team) observations: {len(completed)}')
    if len(completed) > 0:
        print(completed.to_string(index=False))

    calibration = fit_calibration(completed)
    print()
    print('=== Calibration result ===')
    for k, v in calibration.items():
        print(f'  {k}: {v}')

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(calibration, indent=2))
    print(f'\nWrote → {OUTPUT_PATH}')

    if args.backtest and len(completed) > 0:
        print_backtest_detail(completed, calibration['scalar_correction'])


if __name__ == '__main__':
    main()
