"""Fetch closed matchup final scores from ESPN and backfill
`actual_my_final` / `actual_opp_final` columns in predictions_history.csv.

For each unique period in predictions_history that has any NaN actuals,
checks whether the period is fully closed (today > period_end) and if so,
pulls final scores via `league.box_scores(matchup_period=N)` and writes them
back ONLY to rows where the actuals are missing.

Idempotent: safe to re-run anytime. Only fills NaN rows; never overwrites.

Emits a one-line summary suitable for log scraping:
  Backfilled M new rows; total backfilled now N/T.

Run periodically (e.g., as part of refresh_dashboards.py) or on demand.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HISTORY = ROOT / 'data' / 'outputs' / 'predictions_history.csv'


def _ensure_actual_cols(df: pd.DataFrame) -> pd.DataFrame:
    for c in ('actual_my_final', 'actual_opp_final', 'model_version'):
        if c not in df.columns:
            df[c] = pd.NA
    return df


def _period_closed(period_first_snapshot_date: pd.Timestamp, today: pd.Timestamp) -> bool:
    """Period covers Mon-Sun starting from first-snapshot's ISO week.

    Thin wrapper around the pure helpers in scripts/xfp/lib/period_math.py.
    Centralized 2026-06-06 (PR 3a) so the math has one home + parametrized tests.
    """
    from scripts.xfp.lib.period_math import compute_period_window, is_period_closed
    _, period_end = compute_period_window(period_first_snapshot_date.date())
    return is_period_closed(period_end, today.date())


def _fetch_period_finals(period: int):
    """Return (my_final, opp_final) for the given period, or (None, None)."""
    try:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        box_scores = league.box_scores(matchup_period=period)
    except Exception as e:
        print(f'  Period {period}: ESPN fetch failed: {e}')
        return None, None
    for bs in box_scores:
        if bs.home_team and 'Ligers' in bs.home_team.team_name:
            return float(bs.home_score), float(bs.away_score)
        if bs.away_team and 'Ligers' in bs.away_team.team_name:
            return float(bs.away_score), float(bs.home_score)
    return None, None


def run_backfill(verbose: bool = True) -> tuple[int, int, int]:
    """Run the incremental backfill.

    Returns (new_rows_filled, total_backfilled_now, total_rows).
    """
    if not HISTORY.exists():
        if verbose:
            print(f'No predictions_history at {HISTORY}')
        return 0, 0, 0
    df = pd.read_csv(HISTORY)
    df = _ensure_actual_cols(df)
    df['date'] = pd.to_datetime(df['date'])
    today = pd.Timestamp.today().normalize()

    new_filled = 0
    for period, sub in df.groupby('period'):
        missing_mask = (df['period'] == period) & df['actual_my_final'].isna()
        n_missing = int(missing_mask.sum())
        if n_missing == 0:
            continue  # fully backfilled; skip
        first_snap = sub['date'].min()
        if not _period_closed(first_snap, today):
            if verbose:
                print(f'  Period {int(period)}: not yet closed (first snap {first_snap.date()}, today {today.date()}). Skipping.')
            continue
        my_final, opp_final = _fetch_period_finals(int(period))
        if my_final is None:
            if verbose:
                print(f'  Period {int(period)}: ESPN returned no scores')
            continue
        # Only fill the missing rows — never overwrite existing actuals.
        df.loc[missing_mask, 'actual_my_final'] = my_final
        df.loc[missing_mask, 'actual_opp_final'] = opp_final
        new_filled += n_missing
        if verbose:
            print(f'  Period {int(period)}: filled {n_missing} missing rows with my={my_final:.1f}, opp={opp_final:.1f}')

    if new_filled:
        df.to_csv(HISTORY, index=False)

    total_backfilled = int(df['actual_my_final'].notna().sum())
    total = int(len(df))
    print(f'Backfilled {new_filled} new rows; total backfilled now {total_backfilled}/{total}.')
    return new_filled, total_backfilled, total


def main():
    run_backfill(verbose=True)


if __name__ == '__main__':
    main()
