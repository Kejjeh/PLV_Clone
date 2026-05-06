"""
build_il_history.py — pulls MLB Stats API transaction logs and engineers
injury-list features per (pitcher, year).

P13.0 + P13.1 of the plan: address V11's documented systematic over-projection
of pitchers who are returning from IL, hidden injuries, or rehabbing
(Bello, Littell, Scherzer, Senga archetype).

Outputs:
  data/research/xfp_cache/il_transactions_{year}.json   — raw transaction logs
  data/research/xfp_cache/il_features_2015_2026.csv     — per-pitcher per-year features

Features engineered (all keyed by pitcher and year):
  il_stints       — count of IL placements during year T
  il_days_total   — total days on IL during year T (sum of placement→activation gaps)
  il_60_stints    — count of 60-day IL placements (long-term injuries)
  career_il_stints_3yr — IL placements in last 3 years (years T-2, T-1, T)
  career_il_days_3yr   — IL days in last 3 years
  returning_from_il_60 — placed on 60-day IL within year T-1, may be lingering

For cross-year prediction we use *lagged* versions (year T-1 features → year T target).
"""
from __future__ import annotations
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
CACHE.mkdir(parents=True, exist_ok=True)
SP_MULTI = CACHE / 'sp_multiyr_2015_2025.csv'
OUT_FEATS = CACHE / 'il_features_2015_2026.csv'

YEARS = list(range(2015, 2027))

# Description-pattern matchers — handle both "injured list" (2019+) and
# "disabled list" (2015–2018, before MLB rebranded the terminology).
RE_PLACED   = re.compile(r'placed.*?on the (\d+)-day (?:injured|disabled) list', re.IGNORECASE)
RE_ACTIVATED= re.compile(r'(?:activated|reinstated).*?from the (\d+)-day (?:injured|disabled) list', re.IGNORECASE)
RE_TRANSFER = re.compile(r'transferred.*?to the (\d+)-day (?:injured|disabled) list', re.IGNORECASE)

# Roughly: chunk fetching by month to keep each response < 10k events
def month_windows(year: int) -> list[tuple[str, str]]:
    """Generate (start, end) date pairs covering the calendar year, monthly."""
    out = []
    for m in range(1, 13):
        start = date(year, m, 1)
        end_month = m + 1 if m < 12 else 12
        end_year  = year if m < 12 else year
        end = (date(end_year, end_month, 1) if m < 12 else date(year, 12, 31)) - timedelta(days=0)
        if m < 12:
            end = end - timedelta(days=1)
        out.append((start.isoformat(), end.isoformat()))
    return out


def fetch_year_transactions(year: int) -> list[dict]:
    """Fetch all transactions for a year, cache as JSON."""
    cache = CACHE / f'il_transactions_{year}.json'
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            print(f'  [{year}] cached: {len(data)} transactions', flush=True)
            return data
        except Exception:
            pass

    all_txs: list[dict] = []
    for start, end in month_windows(year):
        url = f'https://statsapi.mlb.com/api/v1/transactions?startDate={start}&endDate={end}'
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            chunk = r.json().get('transactions', []) or []
        except Exception as exc:
            print(f'  [{year}] {start}→{end} fetch failed: {exc}', flush=True)
            continue
        all_txs.extend(chunk)
        time.sleep(0.15)  # be polite

    # Trim each tx to only the fields we need (huge size reduction)
    trimmed = []
    for t in all_txs:
        person = t.get('person') or {}
        pid = person.get('id')
        if not pid:
            continue
        type_code = t.get('typeCode', '')
        desc = (t.get('description') or '').lower()
        # Only keep IL-related events to massively shrink the cache.
        # Handle both modern "injured list" wording and 2015-2018 "disabled list".
        if type_code != 'SC':
            continue
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
    print(f'  [{year}] fetched + trimmed: {len(trimmed)} IL events (from {len(all_txs)} total tx)', flush=True)
    return trimmed


def parse_event(t: dict) -> dict | None:
    """Classify a Status Change event as placement/activation/transfer + IL length."""
    desc = (t.get('desc') or '').lower()
    placed = RE_PLACED.search(desc)
    if placed:
        return {'kind': 'place', 'days': int(placed.group(1))}
    activated = RE_ACTIVATED.search(desc)
    if activated:
        return {'kind': 'activate', 'days': int(activated.group(1))}
    transfer = RE_TRANSFER.search(desc)
    if transfer:
        return {'kind': 'transfer', 'days': int(transfer.group(1))}
    return None


def build_features(years: Iterable[int]) -> pd.DataFrame:
    """Engineer per-(pitcher, year) IL features.

    Aggregates events into per-year stint counts + estimated days on IL.
    Days are estimated as: for each `place` event without matching `activate`,
    count the days from placement to year-end (assumes still on IL); for
    matched pairs, count placement→activation interval.
    """
    rows: list[dict] = []
    # Build {pid, year} → list of parsed events
    event_log: dict[tuple[int,int], list[dict]] = {}
    for yr in years:
        txs = fetch_year_transactions(yr)
        for t in txs:
            ev = parse_event(t)
            if not ev:
                continue
            try:
                d = datetime.strptime(t['date'], '%Y-%m-%d').date()
            except Exception:
                continue
            ev['date'] = d
            ev['pid'] = int(t['pid'])
            ev['name'] = t.get('name')
            event_log.setdefault((ev['pid'], yr), []).append(ev)

    for (pid, yr), events in event_log.items():
        events.sort(key=lambda e: e['date'])
        placements = [e for e in events if e['kind'] == 'place']
        activations = [e for e in events if e['kind'] == 'activate']
        transfers   = [e for e in events if e['kind'] == 'transfer']

        # Pair placements with activations chronologically (greedy match)
        days_total = 0
        unmatched_places = 0
        a_idx = 0
        for p in placements:
            # Find first activation after this placement
            while a_idx < len(activations) and activations[a_idx]['date'] < p['date']:
                a_idx += 1
            if a_idx < len(activations):
                d = (activations[a_idx]['date'] - p['date']).days
                if d > 0:
                    days_total += min(d, p['days'] * 2)  # cap at 2× the IL category to avoid wild outliers
                a_idx += 1
            else:
                # No matching activation — assume still on IL through year-end
                year_end = date(yr, 12, 31)
                d = (year_end - p['date']).days
                if d > 0:
                    days_total += min(d, p['days'] * 2)
                unmatched_places += 1

        # Days since last placement (computed as of season end)
        if placements:
            last_placement = max(p['date'] for p in placements)
            days_since_last_il = (date(yr, 12, 31) - last_placement).days
        else:
            days_since_last_il = None

        rows.append({
            'pitcher': pid,
            'name': events[0].get('name'),
            'year': yr,
            'il_stints': len(placements),
            'il_60_stints': sum(1 for p in placements if p['days'] >= 60),
            'il_days_total': days_total,
            'il_unmatched_places': unmatched_places,
            'il_transfers': len(transfers),
            'days_since_last_il': days_since_last_il,
        })

    df = pd.DataFrame(rows)
    return df


def main():
    print('=== build_il_history ===', flush=True)
    print(f'Fetching/caching transaction logs for {YEARS}...', flush=True)
    df = build_features(YEARS)
    if df.empty:
        print('No IL events parsed — aborting.', flush=True)
        return
    df = df.sort_values(['year', 'pitcher']).reset_index(drop=True)

    # Augment with a 3-yr lookback per pitcher
    df['career_il_stints_3yr'] = (
        df.sort_values(['pitcher', 'year'])
          .groupby('pitcher')['il_stints']
          .rolling(3, min_periods=1)
          .sum()
          .reset_index(level=0, drop=True)
    )
    df['career_il_days_3yr'] = (
        df.sort_values(['pitcher', 'year'])
          .groupby('pitcher')['il_days_total']
          .rolling(3, min_periods=1)
          .sum()
          .reset_index(level=0, drop=True)
    )

    df.to_csv(OUT_FEATS, index=False)
    print(f'\nWrote {OUT_FEATS}: {len(df)} (pitcher, year) rows', flush=True)
    print(f'  spans years: {sorted(df["year"].unique())}')
    print(f'  IL stint distribution:')
    print(df['il_stints'].describe().to_string())
    print()
    print(f'  pitchers with ≥1 IL stint: {(df["il_stints"]>=1).sum()}')
    print(f'  pitchers with ≥1 60-day IL: {(df["il_60_stints"]>=1).sum()}')


if __name__ == '__main__':
    main()
