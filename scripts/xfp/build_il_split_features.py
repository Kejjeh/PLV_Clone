"""
build_il_split_features.py — split-day-aware IL features for pitcher RoS.

Builds, for each (pitcher, year, split_day), an in-season IL state vector:
  - il_stints_to: number of times placed on IL between season start and cutoff
  - is_on_il_at_split: 1 if currently on IL at the cutoff date
  - days_since_il_return: days since the most recent IL reinstatement
                          (NaN if never on IL this season; 0 = just returned)
  - days_on_il_to: cumulative days on IL between season start and cutoff

Anchor grid (fixed 2026-07-09): the split_day grid is derived per year from
the ACTUAL split_day values present in the rolling substrate CSVs
(rolling_{pitchers,hitters,relievers}_2018_2026.csv), unioned with the legacy
monthly anchors [30, 60, 90, 120] and the current-elapsed-day snapshot. The
rp3 pipeline (and its validation harness) joins this cache with an EXACT
merge on (pitcher, year, split_day); when the rolling builders moved to a
weekly cadence on 2026-05-29 this builder kept emitting only monthly anchors,
so the join silently matched <1% of rows and the three validated IL features
degenerated to their fillna constants. Deriving the grid from the substrate
keeps the exact join correct even if the rolling cadence changes again.

Staleness guard (fixed 2026-07-09): the current-year il_transactions JSON is
a fetch-once cache (build_il_history.fetch_year_transactions returns it
as-is if present), so mid-season it froze at its first fetch date. If the
current year's JSON is older than STALE_AFTER_DAYS, it is refetched from the
MLB Stats API (same endpoint + trim rules as build_il_history) and rewritten.

Output: data/research/xfp_cache/il_split_features_2018_2026.csv
"""
from __future__ import annotations
import json
import time
from datetime import date
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
# Legacy monthly anchors — kept in the emitted grid for back-compat with
# consumers that still read monthly splits (backtest_framework, volume
# pipelines, one-off diagnostics).
SPLIT_DAYS = [30, 60, 90, 120]

# Rolling substrates whose per-year split_day grids the IL cache must cover
# exactly (the rp3/harness join is an exact merge on pitcher/year/split_day).
ROLLING_SUBSTRATES = [
    CACHE / 'rolling_pitchers_2018_2026.csv',
    CACHE / 'rolling_hitters_2018_2026.csv',
    CACHE / 'rolling_relievers_2018_2026.csv',
]

STALE_AFTER_DAYS = 3


def substrate_split_days() -> dict[int, set[int]]:
    """Union of split_day values per year across the rolling substrate CSVs."""
    grid: dict[int, set[int]] = {}
    for p in ROLLING_SUBSTRATES:
        if not p.exists():
            print(f'  (grid) missing substrate {p.name} — skipping')
            continue
        d = pd.read_csv(p, usecols=['year', 'split_day']).drop_duplicates()
        for y, s in d.itertuples(index=False):
            grid.setdefault(int(y), set()).add(int(s))
    return grid


def refresh_current_year_json_if_stale(year: int) -> None:
    """Refetch il_transactions_{year}.json when its newest event is stale.

    Mirrors build_il_history.fetch_year_transactions' trim rules so the
    rewritten cache stays byte-compatible with every other consumer.
    Fail-soft: any fetch error leaves the existing cache in place.
    """
    cache = CACHE / f'il_transactions_{year}.json'
    today = pd.Timestamp(date.today())
    if cache.exists():
        try:
            rows = json.loads(cache.read_text(encoding='utf-8'))
            max_d = max((r.get('date') or '') for r in rows) if rows else ''
            if max_d and (today - pd.Timestamp(max_d)).days <= STALE_AFTER_DAYS:
                return
            print(f'  [{year}] il_transactions JSON stale (max date {max_d}) — refetching')
        except Exception:
            print(f'  [{year}] il_transactions JSON unreadable — refetching')
    try:
        import requests
        all_txs: list[dict] = []
        start = pd.Timestamp(f'{year}-01-01')
        end_of_year = min(pd.Timestamp(f'{year}-12-31'), today)
        cur = start
        while cur <= end_of_year:
            # cur is always the 1st of a month, so MonthEnd(0) rolls forward.
            nxt = min(cur + pd.offsets.MonthEnd(0), end_of_year)
            url = ('https://statsapi.mlb.com/api/v1/transactions'
                   f'?startDate={cur.date().isoformat()}&endDate={nxt.date().isoformat()}')
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            all_txs.extend(r.json().get('transactions', []) or [])
            time.sleep(0.15)
            cur = nxt + pd.Timedelta(days=1)
        trimmed = []
        for t in all_txs:
            person = t.get('person') or {}
            pid = person.get('id')
            if not pid:
                continue
            if t.get('typeCode', '') != 'SC':
                continue
            desc = (t.get('description') or '').lower()
            if ('injured list' not in desc
                    and 'disabled list' not in desc
                    and 'reinstated' not in desc):
                continue
            trimmed.append({
                'date': t.get('date'),
                'pid': int(pid),
                'name': person.get('fullName'),
                'desc': t.get('description'),
            })
        cache.write_text(json.dumps(trimmed))
        print(f'  [{year}] refetched il_transactions JSON: {len(trimmed)} IL events')
    except Exception as exc:
        print(f'  [{year}] IL transactions refetch FAILED ({exc}) — using existing cache')


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


def build_year(year: int, substrate_grid: set[int] | None = None) -> pd.DataFrame:
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
    # Grid = legacy monthly anchors ∪ rolling substrate split_days ∪ elapsed
    # snapshots. The substrate union is what keeps the rp3 exact join alive.
    splits_emit = set(SPLIT_DAYS) | (substrate_grid or set())
    if elapsed_days > 0:
        splits_emit.add(elapsed_days)
    today_elapsed = int((pd.Timestamp(date.today()) - season_start).days)
    if 0 < today_elapsed <= 250:  # in-progress season: cover today's snapshot label
        splits_emit.add(today_elapsed)

    by_pid = {pid: sub for pid, sub in df.groupby('pid')}
    out_rows = []
    for split_day in sorted(splits_emit):
        cutoff = season_start + pd.Timedelta(days=split_day)
        ever_seen = df[df['date'] <= cutoff]['pid'].unique()
        for pid in ever_seen:
            feats = stints_for_pitcher(by_pid[pid], season_start, cutoff)
            out_rows.append({
                'pitcher': int(pid),
                'year': year,
                'split_day': split_day,
                **feats,
            })
    return pd.DataFrame(out_rows)


def main():
    print('=== build_il_split_features ===')
    cur_year = date.today().year
    if cur_year in SEASON_STARTS:
        refresh_current_year_json_if_stale(cur_year)
    grid = substrate_split_days()
    frames = []
    for yr in sorted(SEASON_STARTS.keys()):
        sub = build_year(yr, substrate_grid=grid.get(yr))
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
