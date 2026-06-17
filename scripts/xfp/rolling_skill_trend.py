"""rolling_skill_trend.py — week-by-week underlying skill trends per hitter.

Catches players whose UNDERLYING physical skills are improving or
declining over the season — the leading-indicator the model itself
doesn't capture (the model uses cumulative-to-date shrunken rates,
so it can't tell "started bad, getting better" from "consistently
average").

For each target hitter:
  - Split 2026 statcast into ISO-week buckets (Mon-Sun)
  - Per week: PA, K%, BB%, EV (avg + p90), hard-hit%, barrel%, bat speed
  - Compute last-2-week vs first-2-week deltas
  - Flag: IMPROVING (last 2 > first 2 by 1σ+), DECLINING, or STABLE

Output:
  data/research/rolling_skill_trend.csv (all rows)
  data/outputs/rolling_skill_trend.json (dashboard payload — Ligers + flagged FAs)
  Console: Ligers roster trends first, then league-wide notable movers

Usage:
    python scripts/xfp/rolling_skill_trend.py
    python scripts/xfp/rolling_skill_trend.py --league   # all hitters
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RES = ROOT / 'data' / 'research'
OUT = ROOT / 'data' / 'outputs'

PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk', 'hit_by_pitch',
    'strikeout', 'strikeout_double_play', 'field_out', 'force_out',
    'grounded_into_double_play', 'sac_fly', 'sac_bunt', 'fielders_choice',
    'fielders_choice_out', 'double_play', 'triple_play', 'field_error', 'catcher_interf',
}
SWINGS = {'foul', 'foul_tip', 'hit_into_play', 'swinging_strike',
          'swinging_strike_blocked', 'missed_bunt'}
WHIFFS = {'swinging_strike', 'swinging_strike_blocked'}


def load_2026_pa(batter_ids: set) -> pd.DataFrame:
    """One row per pitch in 2026 for these batters, with weekly bucket."""
    path = CACHE / 'statcast_2026.parquet'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path, columns=[
        'game_date', 'batter', 'events', 'description', 'pitch_type',
        'launch_speed', 'launch_angle', 'bat_speed'])
    df = df[df['batter'].isin(batter_ids)].copy()
    if df.empty: return df
    df['game_date'] = pd.to_datetime(df['game_date'])
    df['week_start'] = df['game_date'].dt.to_period('W-SUN').apply(lambda x: x.start_time)
    df['is_pa'] = df['events'].isin(PA_EVENTS).astype(int)
    df['is_swing'] = df['description'].isin(SWINGS).astype(int)
    df['is_whiff'] = df['description'].isin(WHIFFS).astype(int)
    df['is_k'] = df['events'].isin({'strikeout', 'strikeout_double_play'}).astype(int)
    df['is_bb'] = df['events'].isin({'walk', 'intent_walk'}).astype(int)
    return df


def weekly_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Per (batter, week_start): aggregate skill metrics."""
    if df.empty: return df
    # Aggregate at PA level for K/BB rates
    pa_agg = df[df['is_pa'] == 1].groupby(['batter', 'week_start']).agg(
        pa=('is_pa', 'sum'),
        k=('is_k', 'sum'),
        bb=('is_bb', 'sum'),
    ).reset_index()
    # Aggregate at pitch level for swstr / whiff
    pitch_agg = df.groupby(['batter', 'week_start']).agg(
        pitches=('is_pa', 'count'),  # all pitches
        swings=('is_swing', 'sum'),
        whiffs=('is_whiff', 'sum'),
    ).reset_index()
    # BBE aggregates (only when launch_speed is populated)
    bbe = df[df['launch_speed'].notna()].groupby(['batter', 'week_start']).agg(
        bbe=('launch_speed', 'count'),
        ev_mean=('launch_speed', 'mean'),
        ev_p90=('launch_speed', lambda x: float(np.percentile(x, 90))),
        hard_hit=('launch_speed', lambda x: (x >= 95).sum()),
    ).reset_index()
    bbe['hard_hit_pct'] = bbe['hard_hit'] / bbe['bbe'] * 100
    # Barrel (simplified)
    bb_only = df[df['launch_speed'].notna() & df['launch_angle'].notna()].copy()
    bb_only['is_barrel'] = ((bb_only['launch_speed'] >= 98)
                             & bb_only['launch_angle'].between(26, 30)).astype(int)
    barrel_agg = bb_only.groupby(['batter', 'week_start']).agg(
        bbe2=('is_barrel', 'count'),
        barrels=('is_barrel', 'sum'),
    ).reset_index()
    barrel_agg['barrel_pct'] = barrel_agg['barrels'] / barrel_agg['bbe2'] * 100
    # Bat speed (2024+ data)
    bs = df[df['bat_speed'].notna()].groupby(['batter', 'week_start'])['bat_speed'].mean().reset_index().rename(
        columns={'bat_speed': 'bat_speed_mean'})

    out = pa_agg.merge(pitch_agg, on=['batter', 'week_start'], how='outer')
    out = out.merge(bbe, on=['batter', 'week_start'], how='left')
    out = out.merge(barrel_agg[['batter', 'week_start', 'barrel_pct']], on=['batter', 'week_start'], how='left')
    out = out.merge(bs, on=['batter', 'week_start'], how='left')
    out['k_pct'] = out['k'] / out['pa'].replace(0, np.nan) * 100
    out['bb_pct'] = out['bb'] / out['pa'].replace(0, np.nan) * 100
    out['whiff_per_swing'] = out['whiffs'] / out['swings'].replace(0, np.nan) * 100
    return out.sort_values(['batter', 'week_start'])


def detect_trend(weekly: pd.DataFrame, batter_id: int) -> dict:
    """Compare last 2 weeks vs first 2 weeks of the season for one batter."""
    sub = weekly[weekly['batter'] == batter_id].dropna(subset=['pa'])
    if len(sub) < 4:
        return {'trend': 'insufficient_data', 'weeks': len(sub)}
    sub = sub.sort_values('week_start')
    first = sub.head(2)
    last = sub.tail(2)
    out = {'weeks': len(sub),
            'first_weeks': [str(w.date()) for w in first['week_start']],
            'last_weeks': [str(w.date()) for w in last['week_start']],
            'first_pa': int(first['pa'].sum()),
            'last_pa': int(last['pa'].sum())}
    metrics_def = [
        ('k_pct',          'lower better'),
        ('bb_pct',         'higher better'),
        ('whiff_per_swing','lower better'),
        ('ev_mean',        'higher better'),
        ('ev_p90',         'higher better'),
        ('hard_hit_pct',   'higher better'),
        ('barrel_pct',     'higher better'),
        ('bat_speed_mean', 'higher better'),
    ]
    flags = []
    for col, direction in metrics_def:
        try:
            f = float(first[col].mean())
            l = float(last[col].mean())
            if np.isnan(f) or np.isnan(l):
                out[col + '_delta'] = None
                continue
            delta = l - f
            out[col + '_first'] = round(f, 2)
            out[col + '_last'] = round(l, 2)
            out[col + '_delta'] = round(delta, 2)
            improving = (delta < 0) if 'lower better' in direction else (delta > 0)
            if abs(delta) >= 0.5 * abs(f) * 0.1 or abs(delta) >= 1.0:
                # heuristic threshold — adjust per metric below
                pass
            if improving and (
                (col == 'ev_mean' and abs(delta) >= 1.0) or
                (col == 'ev_p90' and abs(delta) >= 1.0) or
                (col == 'k_pct' and abs(delta) >= 3.0) or
                (col == 'whiff_per_swing' and abs(delta) >= 2.0) or
                (col == 'bat_speed_mean' and abs(delta) >= 1.0) or
                (col == 'hard_hit_pct' and abs(delta) >= 3.0) or
                (col == 'barrel_pct' and abs(delta) >= 2.0)):
                flags.append(f'+{col}')
            elif not improving and (
                (col == 'ev_mean' and abs(delta) >= 1.0) or
                (col == 'ev_p90' and abs(delta) >= 1.0) or
                (col == 'k_pct' and abs(delta) >= 3.0) or
                (col == 'whiff_per_swing' and abs(delta) >= 2.0) or
                (col == 'bat_speed_mean' and abs(delta) >= 1.0) or
                (col == 'hard_hit_pct' and abs(delta) >= 3.0) or
                (col == 'barrel_pct' and abs(delta) >= 2.0)):
                flags.append(f'-{col}')
        except Exception:
            pass
    out['flags'] = flags
    pos = sum(1 for f in flags if f.startswith('+'))
    neg = sum(1 for f in flags if f.startswith('-'))
    if pos >= 3 and neg == 0:
        out['trend'] = 'IMPROVING'
    elif neg >= 3 and pos == 0:
        out['trend'] = 'DECLINING'
    elif pos > neg:
        out['trend'] = 'slight_up'
    elif neg > pos:
        out['trend'] = 'slight_down'
    else:
        out['trend'] = 'stable'
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--league', action='store_true',
                    help='Run on all 2026 hitters in rh3 (not just Ligers)')
    args = ap.parse_args()

    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    if args.league:
        target_ids = set(rh['batter'].astype(int))
        print(f'Running league-wide on {len(target_ids)} hitters')
    else:
        from plv_clone.league_state import LeagueState
        league = LeagueState()._get_league()
        my_team = next(t for t in league.teams if t.team_name == 'New York Ligers')
        my_names = {p.name for p in my_team.roster}
        ligers_rows = rh[rh['player_name'].isin(my_names)]
        target_ids = set(ligers_rows['batter'].astype(int))
        print(f'Running on Ligers hitters: {len(target_ids)}')

    df = load_2026_pa(target_ids)
    print(f'Loaded {len(df)} 2026 pitch-level rows')
    weekly = weekly_aggregate(df)

    # Get name map
    name_lookup = rh.drop_duplicates('batter').set_index('batter')['player_name'].to_dict()

    results = []
    for bid in target_ids:
        result = detect_trend(weekly, bid)
        result['batter'] = bid
        result['name'] = name_lookup.get(bid, str(bid))
        results.append(result)

    rdf = pd.DataFrame(results)
    rdf.to_csv(RES / 'rolling_skill_trend.csv', index=False)

    # Console — Ligers first
    if not args.league:
        print('\n=== Ligers roster — rolling skill trends ===')
        for r in sorted(results, key=lambda x: x.get('name', '') if isinstance(x.get('name'), str) else ''):
            nm = r['name']
            trend = r['trend']
            wks = r.get('weeks', 0)
            fp = r.get('first_pa', 0)
            lp = r.get('last_pa', 0)
            print(f'\n  {nm:<25s}: TREND={trend} ({wks} weeks, {fp}+{lp} PA first->last 2wks)')
            if r['trend'] == 'insufficient_data': continue
            for label, key in [('EV mean', 'ev_mean'), ('EV p90', 'ev_p90'),
                                ('K%', 'k_pct'), ('Whiff/swing', 'whiff_per_swing'),
                                ('Hard hit %', 'hard_hit_pct'),
                                ('Barrel %', 'barrel_pct'),
                                ('Bat speed', 'bat_speed_mean')]:
                first_v = r.get(key + '_first')
                last_v = r.get(key + '_last')
                if first_v is None or last_v is None: continue
                delta = r.get(key + '_delta', 0)
                print(f'    {label:<14s} first2wk={first_v:>7.2f}  last2wk={last_v:>7.2f}  D={delta:>+7.2f}')
            if r.get('flags'):
                print(f'    flags: {", ".join(r["flags"])}')
    else:
        improving = [r for r in results if r.get('trend') == 'IMPROVING']
        declining = [r for r in results if r.get('trend') == 'DECLINING']
        print(f'\n=== {len(improving)} IMPROVING (3+ skill metrics trending up) ===')
        for r in improving[:30]:
            print(f'  {r["name"]:<25s} flags: {", ".join(r.get("flags", []))}')
        print(f'\n=== {len(declining)} DECLINING (3+ skill metrics trending down) ===')
        for r in declining[:30]:
            print(f'  {r["name"]:<25s} flags: {", ".join(r.get("flags", []))}')

    # Save JSON for dashboard
    with open(OUT / 'rolling_skill_trend.json', 'w', encoding='utf-8') as f:
        json.dump({'as_of': str(pd.Timestamp.today().date()),
                    'results': results}, f, separators=(',', ':'), default=str)
    print(f'\nwrote rolling_skill_trend.csv + .json')


if __name__ == '__main__':
    main()
