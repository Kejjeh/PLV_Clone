"""Fetch closed matchup final scores from ESPN and backfill
`actual_my_final` / `actual_opp_final` columns in predictions_history.csv.

For each unique period in predictions_history that has no actuals populated,
checks whether the period is fully closed (today > period_end) and if so,
pulls final scores via `league.box_scores(matchup_period=N)` and writes them
back to ALL rows of that period.

Run periodically (e.g., Mon morning) or on demand.
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta
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
    """Period covers Mon-Sun starting from first-snapshot's ISO week."""
    period_start = period_first_snapshot_date - pd.Timedelta(days=period_first_snapshot_date.weekday())
    period_end = period_start + pd.Timedelta(days=6)
    return today > period_end


def _fetch_period_finals(period: int, ligers_team_id: int | None = None):
    """Return (my_final, opp_final) for the given period, or (None, None)."""
    from app import espn_connector as ec
    league = ec._get_league()
    try:
        box_scores = league.box_scores(matchup_period=period)
    except Exception as e:
        print(f'  Period {period}: box_scores fetch failed: {e}')
        return None, None
    for bs in box_scores:
        if bs.home_team and 'Ligers' in bs.home_team.team_name:
            return float(bs.home_score), float(bs.away_score)
        if bs.away_team and 'Ligers' in bs.away_team.team_name:
            return float(bs.away_score), float(bs.home_score)
    return None, None


def main():
    if not HISTORY.exists():
        print(f'No predictions_history at {HISTORY}'); return
    df = pd.read_csv(HISTORY)
    df = _ensure_actual_cols(df)
    df['date'] = pd.to_datetime(df['date'])
    today = pd.Timestamp.today().normalize()

    updates = 0
    for period, sub in df.groupby('period'):
        sub = sub.sort_values('date')
        first_snap = sub['date'].min()
        already_populated = sub['actual_my_final'].notna().all()
        if already_populated:
            continue
        if not _period_closed(first_snap, today):
            print(f'  Period {int(period)}: not yet closed (first snap {first_snap.date()}, today {today.date()}). Skipping.')
            continue
        my_final, opp_final = _fetch_period_finals(int(period))
        if my_final is None:
            print(f'  Period {int(period)}: ESPN returned no scores')
            continue
        idx = df['period'] == period
        df.loc[idx, 'actual_my_final'] = my_final
        df.loc[idx, 'actual_opp_final'] = opp_final
        updates += int(idx.sum())
        print(f'  Period {int(period)}: backfilled actuals my={my_final:.1f}, opp={opp_final:.1f} ({int(idx.sum())} rows)')

    if updates:
        df.to_csv(HISTORY, index=False)
        print(f'\nWrote {updates} updated rows → {HISTORY}')
    else:
        print('\nNothing to update.')


if __name__ == '__main__':
    main()
