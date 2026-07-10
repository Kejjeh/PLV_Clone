"""fetch_il_transactions.py — MLB IL/transaction history ingestion (2015..today).

Pulls ALL transactions from the free MLB Stats API in monthly chunks:
  https://statsapi.mlb.com/api/v1/transactions?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD

Filters to IL-relevant status changes at the MLB level:
  - typeCode == 'SC' (Status Change) whose description mentions
    "injured list" (2019+) or "disabled list" (pre-2019 naming),
  - toTeam is one of the 30 MLB clubs (drops the huge minor-league /
    DSL volume that shares the endpoint).

Outputs
-------
data/research/xfp_cache/il_transactions_2015_2026.parquet
    columns: date, mlbam_id, player_name, type_code, type_desc,
             description, team_id (+ tx_id for dedup, il_action tag)

data/research/xfp_cache/injury_proneness_by_year.csv
    per (mlbam_id, year), AS-OF-JAN-1 leakage-safe features:
      il_stints_prior3yr     — stints STARTING in [Jan1(Y-3), Jan1(Y))
      il_days_prior3yr       — stint-day overlap with that 3-yr window
      career_il_days_to_jan1 — stint-day overlap with (-inf, Jan1(Y))

Stint construction (placement -> activation pairing)
----------------------------------------------------
Rows are classified per description:
  PLACE    = "placed ... on the N-day injured/disabled list"
  ACTIVATE = "activated/reinstated ... from the ... injured/disabled list"
  TRANSFER = "transferred ..." (10->60 day etc.) — extends an open stint,
             never opens or closes one.
Per player, sorted by date (ACTIVATE ordered before PLACE on the same
date so a same-day activate+re-place closes the old stint first):
  - PLACE opens a stint.
  - The first subsequent ACTIVATE closes it.
Unpaired-edge handling (documented invariants):
  - PLACE with no later ACTIVATE (season-ending IL, or data edge):
    stint end is capped at min(next PLACE date for the same player,
    Nov 30 of the stint's start year, today). Nov 30 approximates
    "reinstated after the season" — offseason days are not counted.
  - ACTIVATE with no open stint (placement predates the 2015-01-01
    window, or a paternity->IL edge case) is dropped from pairing.
  - Open stints as of today are censored at today (still counted as a
    stint; days accrue only to today).

Idempotency / resume
--------------------
Each month is cached to data/research/xfp_cache/il_tx_chunks/
il_tx_YYYY-MM.parquet. Re-runs skip completed past months and only
refetch the current (still-accumulating) month. Delete a chunk file to
force a refetch. Final writes are atomic (tmp -> replace).

Usage:
    python scripts/xfp/fetch_il_transactions.py            # full pull + derive
    python scripts/xfp/fetch_il_transactions.py --derive-only
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from plv_clone.paths import ROOT  # noqa: E402

CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
CHUNK_DIR = CACHE / 'il_tx_chunks'
OUT_TX = CACHE / 'il_transactions_2015_2026.parquet'
OUT_PRONE = CACHE / 'injury_proneness_by_year.csv'

MLB_API = 'https://statsapi.mlb.com/api/v1'
SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'plv_clone/il-transactions'

START_YEAR = 2015
TODAY = date.today()

IL_RE = re.compile(r'\b(injured|disabled)\s+list\b', re.I)
PLACE_RE = re.compile(r'\bplaced\b', re.I)
ACTIVATE_RE = re.compile(r'\b(activated|reinstated)\b', re.I)
TRANSFER_RE = re.compile(r'\btransferred\b', re.I)

# Unpaired-placement caps
SEASON_END_MONTH, SEASON_END_DAY = 11, 30  # Nov 30 of stint start year


def _get(path: str, params: dict | None = None, retries: int = 4) -> dict:
    url = f'{MLB_API}{path}'
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
    return {}


def _mlb_team_ids() -> set[int]:
    data = _get('/teams', {'sportId': 1})
    ids = {t['id'] for t in data.get('teams', [])}
    if len(ids) < 28:  # sanity — expect the 30 MLB clubs
        raise RuntimeError(f'only {len(ids)} MLB team ids returned')
    return ids


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    return start, min(end, TODAY)


def _classify(desc: str) -> str:
    if TRANSFER_RE.search(desc):
        return 'TRANSFER'
    if ACTIVATE_RE.search(desc):
        return 'ACTIVATE'
    if PLACE_RE.search(desc):
        return 'PLACE'
    return 'OTHER'


def fetch_month(year: int, month: int, mlb_ids: set[int]) -> pd.DataFrame:
    start, end = _month_bounds(year, month)
    data = _get('/transactions', {'startDate': start.isoformat(), 'endDate': end.isoformat()})
    rows = []
    for t in data.get('transactions', []):
        if t.get('typeCode') != 'SC':
            continue
        desc = t.get('description') or ''
        if not IL_RE.search(desc):
            continue
        team = t.get('toTeam') or t.get('fromTeam') or {}
        if team.get('id') not in mlb_ids:
            continue
        person = t.get('person') or {}
        if not person.get('id'):
            continue
        rows.append({
            'tx_id': t.get('id'),
            'date': t.get('date') or t.get('effectiveDate') or t.get('resolutionDate'),
            'mlbam_id': person['id'],
            'player_name': person.get('fullName'),
            'type_code': t.get('typeCode'),
            'type_desc': t.get('typeDesc'),
            'description': desc,
            'team_id': team.get('id'),
        })
    return pd.DataFrame(rows)


def pull_all() -> pd.DataFrame:
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    mlb_ids = _mlb_team_ids()
    cur_month_key = f'{TODAY.year}-{TODAY.month:02d}'

    months = []
    y, m = START_YEAR, 1
    while (y, m) <= (TODAY.year, TODAY.month):
        months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1

    fetched = skipped = 0
    for y, m in months:
        key = f'{y}-{m:02d}'
        chunk = CHUNK_DIR / f'il_tx_{key}.parquet'
        if chunk.exists() and key != cur_month_key:
            skipped += 1
            continue
        try:
            df = fetch_month(y, m, mlb_ids)
        except Exception as e:
            print(f'  ! {key}: fetch failed ({e}) — skipping (resume by rerunning)')
            continue
        df.to_parquet(chunk, index=False)
        fetched += 1
        if fetched % 12 == 0:
            print(f'  ... {key}: {len(df)} IL rows (fetched {fetched} months so far)')
        time.sleep(1.0)  # be polite: ~1 req/sec

    print(f'  chunks: fetched {fetched}, reused {skipped}')
    parts = [pd.read_parquet(p) for p in sorted(CHUNK_DIR.glob('il_tx_*.parquet'))]
    parts = [p for p in parts if not p.empty]
    if not parts:
        raise RuntimeError('no IL transaction chunks found')
    tx = pd.concat(parts, ignore_index=True)
    tx = tx.drop_duplicates(subset=['tx_id']).sort_values(['date', 'tx_id']).reset_index(drop=True)
    tx['il_action'] = tx['description'].map(_classify)

    tmp = OUT_TX.with_suffix('.parquet.tmp')
    tx.to_parquet(tmp, index=False)
    tmp.replace(OUT_TX)
    print(f'  wrote {OUT_TX.name}: {len(tx)} rows')
    return tx


def build_stints(tx: pd.DataFrame) -> pd.DataFrame:
    """Pair PLACE -> ACTIVATE per player into IL stints (see module docstring)."""
    df = tx[tx['il_action'].isin(['PLACE', 'ACTIVATE'])].copy()
    df['d'] = pd.to_datetime(df['date']).dt.date
    # ACTIVATE before PLACE on the same date
    df['ord'] = (df['il_action'] == 'PLACE').astype(int)
    df = df.sort_values(['mlbam_id', 'd', 'ord'])

    stints = []
    for pid, grp in df.groupby('mlbam_id', sort=False):
        open_start = None
        name = grp['player_name'].iloc[-1]
        for _, row in grp.iterrows():
            if row['il_action'] == 'PLACE':
                if open_start is not None:
                    # consecutive PLACE: close prior at min(new place, season end)
                    season_end = date(open_start.year, SEASON_END_MONTH, SEASON_END_DAY)
                    end = min(row['d'], season_end, TODAY) if row['d'] > open_start else open_start
                    stints.append((pid, name, open_start, max(end, open_start), 'unpaired_replaced'))
                open_start = row['d']
            else:  # ACTIVATE
                if open_start is not None:
                    stints.append((pid, name, open_start, max(row['d'], open_start), 'paired'))
                    open_start = None
                # else: unpaired activation — dropped
        if open_start is not None:
            season_end = date(open_start.year, SEASON_END_MONTH, SEASON_END_DAY)
            end = min(max(season_end, open_start), TODAY)
            tag = 'open_censored' if open_start.year == TODAY.year else 'unpaired_capped'
            stints.append((pid, name, open_start, end, tag))

    out = pd.DataFrame(stints, columns=['mlbam_id', 'player_name', 'start', 'end', 'pairing'])
    out['days'] = [(e - s).days for s, e in zip(out['start'], out['end'])]
    out['days'] = out['days'].clip(lower=1)  # a stint is at least 1 day
    return out


def derive_proneness(stints: pd.DataFrame) -> pd.DataFrame:
    """As-of-Jan-1 features per (mlbam_id, year). Leakage-safe: only stint
    days strictly BEFORE Jan 1 of `year` are counted."""
    rows = []
    names = stints.groupby('mlbam_id')['player_name'].last()
    starts = pd.to_datetime(stints['start'])
    ends = pd.to_datetime(stints['end'])
    pids = stints['mlbam_id'].to_numpy()

    for year in range(START_YEAR + 1, TODAY.year + 2):
        jan1 = pd.Timestamp(year, 1, 1)
        win_lo = pd.Timestamp(year - 3, 1, 1)
        # overlap of [start, end) with (-inf, jan1)
        career_days = (ends.clip(upper=jan1) - starts).dt.days.clip(lower=0)
        # override: stint entirely after jan1 contributes 0 (clip handles via start>jan1 -> negative -> 0)
        prior3_days = (ends.clip(upper=jan1) - starts.clip(lower=win_lo)).dt.days.clip(lower=0)
        started_in_win = ((starts >= win_lo) & (starts < jan1)).astype(int)

        per = pd.DataFrame({
            'mlbam_id': pids,
            'career_il_days_to_jan1': career_days,
            'il_days_prior3yr': prior3_days,
            'il_stints_prior3yr': started_in_win,
        }).groupby('mlbam_id', as_index=False).sum()
        per = per[per['career_il_days_to_jan1'] > 0]
        per.insert(1, 'year', year)
        rows.append(per)

    out = pd.concat(rows, ignore_index=True)
    out['player_name'] = out['mlbam_id'].map(names)
    return out[['mlbam_id', 'player_name', 'year',
                'il_stints_prior3yr', 'il_days_prior3yr', 'career_il_days_to_jan1']]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--derive-only', action='store_true',
                    help='skip the API pull; rebuild stints/proneness from cached parquet')
    args = ap.parse_args()

    print('=== IL transaction ingestion (2015..today) ===')
    if args.derive_only and OUT_TX.exists():
        tx = pd.read_parquet(OUT_TX)
        print(f'  loaded cached {OUT_TX.name}: {len(tx)} rows')
    else:
        tx = pull_all()

    yr = pd.to_datetime(tx['date']).dt.year
    print('  IL transaction rows per year:')
    for y, n in yr.value_counts().sort_index().items():
        print(f'    {y}: {n}')

    stints = build_stints(tx)
    print(f'  stints built: {len(stints)} '
          f'(paired={int((stints.pairing=="paired").sum())}, '
          f'unpaired_capped={int((stints.pairing=="unpaired_capped").sum())}, '
          f'unpaired_replaced={int((stints.pairing=="unpaired_replaced").sum())}, '
          f'open_censored={int((stints.pairing=="open_censored").sum())})')

    prone = derive_proneness(stints)
    tmp = OUT_PRONE.with_suffix('.csv.tmp')
    prone.to_csv(tmp, index=False)
    tmp.replace(OUT_PRONE)
    print(f'  wrote {OUT_PRONE.name}: {len(prone)} (mlbam_id, year) rows, '
          f'years {prone.year.min()}..{prone.year.max()}')
    print('  proneness rows per year:')
    for y, n in prone['year'].value_counts().sort_index().items():
        print(f'    {y}: {n}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
