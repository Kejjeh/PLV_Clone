"""
build_il_split_features.py — split-day-aware IL features for pitcher RoS.

Builds, for each (pitcher, year, split_day), an in-season IL state vector:
  - il_stints_to: number of times placed on IL between season start and cutoff
  - is_on_il_at_split: 1 if currently on IL at the cutoff date
  - days_since_il_return: days since the most recent IL reinstatement
                          (NaN if never on IL this season; 0 = just returned)
  - days_on_il_to: cumulative days on IL between season start and cutoff

Output: data/research/xfp_cache/il_split_features_2018_2026.csv
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = CACHE / 'il_split_features_2018_2026.csv'

SEASON_STARTS = {
    2018: '2018-03-29', 2019: '2019-03-20', 2020: '2020-07-23',
    2021: '2021-04-01', 2022: '2022-04-07', 2023: '2023-03-30',
    2024: '2024-03-28', 2025: '2025-03-27', 2026: '2026-03-26',
}
SPLIT_DAYS = [30, 60, 90, 120]


def classify(desc: str) -> str | None:
    """Return 'place' / 'return' / None."""
    if not isinstance(desc, str):
        return None
    s = desc.lower()
    if 'placed' in s and 'injured list' in s:
        return 'place'
    if ('reinstated' in s or 'activated' in s) and 'injured list' in s:
        return 'return'
    return None


def stints_for_pitcher(events: pd.DataFrame, season_start: pd.Timestamp,
                       cutoff: pd.Timestamp) -> dict:
    """Walk a pitcher's events sorted by date and compute IL state at cutoff.

    State machine: out → on_il → out. We pair places with the next return.
    Unpaired place = still on IL at cutoff.
    """
    ev = events[(events['date'] >= season_start) & (events['date'] <= cutoff)] \
        .sort_values('date')
    stints = 0
    days_on_il = 0
    on_il = False
    place_date = None
    last_return = None
    for _, row in ev.iterrows():
        kind = row['kind']
        d = row['date']
        if kind == 'place' and not on_il:
            on_il = True
            place_date = d
            stints += 1
        elif kind == 'return' and on_il:
            days_on_il += (d - place_date).days
            last_return = d
            on_il = False
            place_date = None
    if on_il and place_date is not None:
        days_on_il += (cutoff - place_date).days
    days_since_return = (cutoff - last_return).days if last_return is not None else np.nan
    return {
        'il_stints_to': stints,
        'is_on_il_at_split': int(on_il),
        'days_since_il_return': days_since_return if not on_il else 0,
        'days_on_il_to': days_on_il,
    }


def build_year(year: int) -> pd.DataFrame:
    path = CACHE / f'il_transactions_{year}.json'
    if not path.exists():
        return pd.DataFrame()
    rows = json.loads(path.read_text(encoding='utf-8'))
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()
    df['date'] = pd.to_datetime(df['date'])
    df['kind'] = df['desc'].map(classify)
    df = df.dropna(subset=['kind'])
    season_start = pd.Timestamp(SEASON_STARTS[year])
    # For in-progress year, also emit IL state at "today" (last known IL date)
    # so downstream substrate can join at the actual current elapsed-days split.
    last_il_date = df['date'].max()
    elapsed_days = int((last_il_date - season_start).days) if pd.notna(last_il_date) else 0
    splits_emit = list(SPLIT_DAYS)
    if elapsed_days > 0 and elapsed_days not in splits_emit:
        splits_emit.append(elapsed_days)

    out_rows = []
    for split_day in splits_emit:
        cutoff = season_start + pd.Timedelta(days=split_day)
        ever_seen = df[df['date'] <= cutoff]['pid'].unique()
        for pid in ever_seen:
            sub = df[df['pid'] == pid]
            feats = stints_for_pitcher(sub, season_start, cutoff)
            out_rows.append({
                'pitcher': int(pid),
                'year': year,
                'split_day': split_day,
                **feats,
            })
    return pd.DataFrame(out_rows)


def main():
    print('=== build_il_split_features ===')
    frames = []
    for yr in sorted(SEASON_STARTS.keys()):
        sub = build_year(yr)
        if not sub.empty:
            print(f'  [{yr}] {len(sub)} (pitcher, split_day) IL rows')
            frames.append(sub)
    if not frames:
        print('No IL transaction data found.')
        return
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(OUT, index=False)
    print(f'\nWrote {OUT}: {len(df)} rows')
    print('  by year:')
    print(df.groupby('year').size().to_string())
    print('  IL state at latest split per year (sample):')
    for y in sorted(df['year'].unique()):
        latest = df[df['year'] == y]['split_day'].max()
        sub = df[(df['year'] == y) & (df['split_day'] == latest)]
        on_il = sub['is_on_il_at_split'].sum()
        print(f'    [{y} @ split {latest}d]: {on_il} pitchers on IL  '
              f'({100 * on_il / max(len(sub), 1):.1f}%)')


if __name__ == '__main__':
    main()
