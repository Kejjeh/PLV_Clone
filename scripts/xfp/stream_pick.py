"""stream_pick.py — best FA SP to stream in a date window.

Usage:
  python stream_pick.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
  Defaults to tomorrow → Sunday window.

Logic:
  1. Pull ESPN free agents (SPs)
  2. Match to model projections (must be in xFP universe)
  3. Filter to those with a probable start in the date window
  4. Rank by sched-adjusted FP (now park-adjusted)
  5. Surface top 5 with rationale
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'app'))
from espn_connector import get_free_agents


def _strip(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def name_norm(s):
    return re.sub(r'[^a-z]+', '', _strip((s or '').lower()))

def name_key(name):
    if ',' in name:
        last, first = name.split(',', 1)
    else:
        parts = name.strip().split()
        if len(parts) < 2: return (name_norm(name), '')
        last, first = parts[-1], ' '.join(parts[:-1])
    return (name_norm(last), name_norm(first))

def lookup(name, by_key):
    last, first = name_key(name)
    rec = by_key.get((last, first))
    if rec is not None: return rec
    candidates = [(k, v) for k, v in by_key.items() if k[0] == last]
    if len(candidates) == 1 and first[:3] == candidates[0][0][1][:3]:
        return candidates[0][1]
    return None


def main():
    parser = argparse.ArgumentParser()
    today = date.today()
    default_end = today + timedelta(days=(6 - today.weekday()) % 7 or 7)  # next Sunday
    parser.add_argument('--start', default=(today + timedelta(days=1)).isoformat())
    parser.add_argument('--end',   default=default_end.isoformat())
    args = parser.parse_args()
    start_d = pd.Timestamp(args.start)
    end_d   = pd.Timestamp(args.end)
    print(f'═══ STREAM PICK — best FA SP {start_d.date()} → {end_d.date()} ═══\n')

    # Load model projections + schedule
    html = (ROOT / 'data/outputs/xfp_dashboard.html').read_text(encoding='utf-8')
    pitchers = json.loads(re.search(r'window\.XFP_PROJECTIONS\s*=\s*(\[.*?\]);', html, re.S).group(1))
    p_by = {name_key(p['name']): p for p in pitchers}

    sched = pd.read_csv(ROOT / 'data/research/xfp_cache/pitcher_schedule_2026.csv')
    sched['game_date'] = pd.to_datetime(sched['game_date'])
    sched_window = sched[(sched['game_date'] >= start_d) & (sched['game_date'] <= end_d)]
    print(f'Probable starts in window: {len(sched_window)} from {sched_window["pitcher"].nunique()} pitchers\n')

    # Pull FAs
    fa = get_free_agents(size=400)
    fa_sp = fa[fa['position'].isin(['SP','P'])].copy()

    # Build candidates: FAs with a scheduled start in the window AND a model projection
    cands = []
    for _, row in fa_sp.iterrows():
        rec = lookup(row['player_name'], p_by)
        if rec is None or rec.get('xfpRoS') is None:
            continue
        pid = rec['mlbId']
        starts_in_window = sched_window[sched_window['pitcher'] == pid]
        for _, s in starts_in_window.iterrows():
            cands.append({
                'name': row['player_name'],
                'pct_owned': row['percent_owned'],
                'game_date': s['game_date'],
                'opp': s['opp_team_abbrev'],
                'is_home': bool(s['is_home']),
                'park_factor': s.get('park_factor', 1.0),
                'xfp_per_start': rec.get('xfpRoS'),
                'sched_per_start': rec.get('xfpRoSSched'),
                'l21_gap': rec.get('recencyGap'),
                'sig': rec.get('signal') or 'hold',
                'gs_to': rec.get('gsToDate'),
                'p25': rec.get('xfpRoSp25'),
                'p75': rec.get('xfpRoSp75'),
                'replDelta': rec.get('replDelta'),
            })

    if not cands:
        print('No FA SPs with model projections AND probable starts in the window.')
        print('(MLB only announces probables ~5 days out — may need to wait or check manually.)')
        return

    # Score candidates: prefer the per-start sched (already park+opp adjusted)
    df = pd.DataFrame(cands)

    # If a pitcher has 2 starts in window, sum the sched_per_start (multi-start gives 2x value)
    by_p = df.groupby(['name','pct_owned','xfp_per_start','sched_per_start','l21_gap','sig','gs_to','p25','p75','replDelta']).agg(
        starts_in_window=('game_date', 'count'),
        total_sched_fp=('sched_per_start', 'sum'),
        first_date=('game_date', 'min'),
        first_opp=('opp', 'first'),
        first_park_factor=('park_factor', 'first'),
    ).reset_index().sort_values('total_sched_fp', ascending=False)

    print(f'{"Rank":<5} {"Pitcher":<22} {"%Own":<5} {"Starts":<7} {"TotalFP":<8} {"L21Δ":<6} {"Sig":<5} {"NextOpp":<7} {"P25-P75":<11}')
    print('-'*85)
    for i, (_, r) in enumerate(by_p.head(10).iterrows(), 1):
        l21 = f'{r["l21_gap"]:+.1f}' if r['l21_gap'] is not None and pd.notna(r['l21_gap']) else '—'
        ci = f'{r["p25"]:.0f}-{r["p75"]:.0f}' if pd.notna(r['p25']) else '—'
        opp = f'{"@" if False else ""}{r["first_opp"]}'
        print(f'{i:<5} {r["name"]:<22} {r["pct_owned"]:<5.0f} '
              f'{int(r["starts_in_window"]):<7} {r["total_sched_fp"]:<8.1f} '
              f'{l21:<6} {r["sig"].upper():<5} {opp:<7} {ci:<11}')

    # Top pick analysis
    top = by_p.iloc[0]
    print(f'\n═══ TOP PICK: {top["name"]} ═══')
    print(f'  Sched-adjusted FP for window: {top["total_sched_fp"]:.1f}')
    print(f'  Starts in window: {int(top["starts_in_window"])}')
    print(f'  First start: {top["first_date"].date()} vs {top["first_opp"]} '
          f'(park factor {top["first_park_factor"]:.3f})')
    print(f'  CI per start: {top["p25"]:.1f} – {top["p75"]:.1f} FP')
    print(f'  Recent form (L21Δ vs season): {top["l21_gap"]:+.2f}')
    print(f'  Ownership: {top["pct_owned"]:.0f}% (must be available in your league)')


if __name__ == '__main__':
    main()
