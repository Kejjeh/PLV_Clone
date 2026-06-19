"""waiver_watch.py — who's scooping value, who's dropping it.

Pulls the last 60 days of ESPN league activity (drops + adds). For each
player action, looks up their RoS projection value from rh3/rp3/rprs2.
Surfaces:

  1. VALUABLE PLAYERS RECENTLY DROPPED (model says >150 RoS FP): if I'd
     been watching the wire, these are players I missed. If they're still
     FAs, claim them now.

  2. BIGGEST WAIVER WINS BY TEAM: which manager is most efficient at
     converting wire claims into RoS value. (Team Solomon scoring
     Altuve, etc.)

  3. INACTIVE / INEXPERIENCED MANAGER FLAGS: teams that have dropped
     above-replacement players. Their roster is leakage — monitor
     their next drops.

  4. NET WAIVER EFFECTIVENESS: per-team (adds value − drops value).

Output:
  data/outputs/waiver_watch.csv (long activity log)
  data/outputs/waiver_watch.json (dashboard payload)
  prints to console with top movers

Usage:
    python scripts/xfp/waiver_watch.py
    python scripts/xfp/waiver_watch.py --days 30
"""
from __future__ import annotations
import argparse
import json
import sys
import unicodedata
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import pandas as pd
from plv_clone.projections import PROJECTIONS

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'data' / 'outputs'


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'[,]+', ' ', s)
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def build_player_value_lookup():
    """Returns {nk: {name, ros_fp, role}}"""
    out = {}
    rh = PROJECTIONS.rh3()
    rh['nk'] = rh['player_name'].map(_norm)
    rh = rh.drop_duplicates('nk', keep='first')
    for _, r in rh.iterrows():
        out[r['nk']] = {'name': r['player_name'], 'role': 'hitter',
                         'ros_fp': float(r.get('expected_total_fp_remaining') or 0)}

    rp = PROJECTIONS.rp3()
    rp['nk'] = rp['player_name'].map(_norm)
    rp = rp.drop_duplicates('nk', keep='first')
    from scripts.xfp.opponent_lineup_overlap import SP_REMAINING_STARTS
    for _, r in rp.iterrows():
        per_start = float(r.get('xfp_rp3_per_start') or 0)
        out.setdefault(r['nk'], {})['name'] = r['player_name']
        out[r['nk']]['role'] = 'pitcher'
        out[r['nk']]['ros_fp'] = per_start * SP_REMAINING_STARTS

    rprs2_path = OUT / 'xfp_rprs2_projections.csv'
    if rprs2_path.exists():
        rprs2 = PROJECTIONS.rprs2()
        if 'name_api' in rprs2.columns:
            rprs2['nk'] = rprs2['name_api'].map(_norm)
            rprs2 = rprs2.drop_duplicates('nk', keep='first')
            for _, r in rprs2.iterrows():
                ros = float(r.get('xfp_ros') or 0)
                existing = out.get(r['nk'], {})
                if not existing or existing.get('ros_fp', 0) < ros:
                    out[r['nk']] = {'name': r['name_api'], 'role': 'pitcher',
                                     'ros_fp': ros}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=60, help='Lookback window (default 60)')
    args = ap.parse_args()

    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    league = ls._get_league()
    val_lookup = build_player_value_lookup()

    # Snapshot of CURRENT rosters so we can tell "still held" vs "rented" pickups
    currently_rostered = set()  # (team_name, normalized_player_name)
    for t in league.teams:
        for p in t.roster:
            currently_rostered.add((t.team_name, _norm(p.name)))

    cutoff = datetime.now() - timedelta(days=args.days)
    activity_rows = []
    for msg_type in ['ADDED', 'DROPPED', 'WAIVER ADDED', 'WAIVER DROPPED', 'FA ADDED', 'TRADED']:
        try:
            acts = league.recent_activity(size=400, msg_type=msg_type)
        except Exception:
            continue
        for a in acts or []:
            act_date = datetime.fromtimestamp(a.date / 1000) if a.date else None
            if act_date is None or act_date < cutoff:
                continue
            for action in (a.actions or []):
                if len(action) < 3:
                    continue
                team_obj, action_type, player_name = action[0], action[1], action[2]
                nk = _norm(player_name)
                val = val_lookup.get(nk, {})
                still_held = (team_obj.team_name, nk) in currently_rostered
                activity_rows.append({
                    'date': act_date,
                    'team_id': team_obj.team_id,
                    'team_name': team_obj.team_name,
                    'action': action_type,
                    'player': str(player_name),
                    'role': val.get('role'),
                    'ros_fp': val.get('ros_fp', 0),
                    'still_held': still_held,
                })

    df = pd.DataFrame(activity_rows).drop_duplicates(
        subset=['date', 'team_name', 'action', 'player'])
    if df.empty:
        print('No activity in window'); return
    print(f'Pulled {len(df)} activity rows in last {args.days} days')

    # 1. Valuable drops
    drops = df[df['action'].str.upper().str.contains('DROP')]
    print(f'\n=== 1. VALUABLE PLAYERS DROPPED IN LAST {args.days} DAYS (ros_fp > 100) ===')
    val_drops = drops[drops['ros_fp'] > 100].sort_values('ros_fp', ascending=False)
    if val_drops.empty:
        print('  (none — no significant drops by value in window)')
    else:
        for _, r in val_drops.head(20).iterrows():
            print(f'  {r["date"].strftime("%m-%d %H:%M")}  '
                  f'{r["team_name"]:<28s} dropped {r["player"]:<22s} '
                  f'({r["role"] or "?"}, {r["ros_fp"]:.0f} RoS FP)')

    # 2. Biggest waiver wins (FA/waiver ADDS with high RoS value)
    adds = df[df['action'].str.upper().str.contains('ADD')]
    val_adds = adds[adds['ros_fp'] > 100].sort_values('ros_fp', ascending=False)
    print(f'\n=== 2. BIGGEST WAIVER PICKUPS (ros_fp > 100) ===')
    if val_adds.empty:
        print('  (none)')
    else:
        for _, r in val_adds.head(20).iterrows():
            print(f'  {r["date"].strftime("%m-%d %H:%M")}  '
                  f'{r["team_name"]:<28s} added {r["player"]:<22s} '
                  f'({r["role"] or "?"}, {r["ros_fp"]:.0f} RoS FP)')

    # 3. Inactive / leaky teams: who dropped above-replacement (ros_fp > 80)
    REPLACEMENT_LEVEL = 80
    leaky = drops[drops['ros_fp'] > REPLACEMENT_LEVEL]
    by_team = leaky.groupby('team_name').agg(
        n_drops=('player', 'count'),
        total_value_dropped=('ros_fp', 'sum'),
        worst_drop_value=('ros_fp', 'max')).reset_index()
    by_team = by_team.sort_values('total_value_dropped', ascending=False)
    print(f'\n=== 3. LEAKY-ROSTER TEAMS (dropped players > {REPLACEMENT_LEVEL} RoS FP) ===')
    print(f'{"Team":<28s} {"# Drops":>8s} {"Total FP":>10s} {"Worst":>8s}')
    for _, r in by_team.iterrows():
        print(f'  {r["team_name"]:<28s} {r["n_drops"]:>8} {r["total_value_dropped"]:>10.1f} {r["worst_drop_value"]:>8.1f}')

    # 4. Net waiver effectiveness: count ONLY pickups still held today (not rentals)
    adds_held = adds[adds['still_held']]
    adds_by_team = adds_held.groupby('team_name')['ros_fp'].sum().reset_index().rename(
        columns={'ros_fp': 'value_added_held'})
    # Drops still reflect lost value — count all of them (they're gone either way)
    drops_by_team = drops.groupby('team_name')['ros_fp'].sum().reset_index().rename(
        columns={'ros_fp': 'value_dropped'})
    eff = adds_by_team.merge(drops_by_team, on='team_name', how='outer').fillna(0)
    eff['net'] = eff['value_added_held'] - eff['value_dropped']
    eff = eff.sort_values('net', ascending=False)
    print(f'\n=== 4. NET WAIVER EFFECTIVENESS ({args.days}d, ONLY adds-still-held minus drops) ===')
    print(f'{"Team":<28s} {"Held Adds":>10s} {"Dropped":>10s} {"Net":>10s}')
    for _, r in eff.iterrows():
        marker = '   <-- YOU' if 'Ligers' in r['team_name'] else ''
        print(f'  {r["team_name"]:<28s} {r["value_added_held"]:>10.1f} {r["value_dropped"]:>10.1f} {r["net"]:>+10.1f}{marker}')

    df.to_csv(OUT / 'waiver_watch.csv', index=False)
    print(f'\nwrote {OUT / "waiver_watch.csv"}')

    # JSON for dashboard
    payload = {
        'days': args.days,
        'as_of': datetime.now().isoformat()[:10],
        'valuable_drops': val_drops.head(30)[['date', 'team_name', 'player', 'role', 'ros_fp']].to_dict(orient='records'),
        'biggest_pickups': val_adds.head(30)[['date', 'team_name', 'player', 'role', 'ros_fp']].to_dict(orient='records'),
        'leaky_teams': by_team.to_dict(orient='records'),
        'net_effectiveness': eff.to_dict(orient='records'),
    }
    with open(OUT / 'waiver_watch.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote {OUT / "waiver_watch.json"}')


if __name__ == '__main__':
    main()
