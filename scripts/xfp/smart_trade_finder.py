"""smart_trade_finder.py — search the league for 1-for-1 trades the model favors.

For each Ligers player × each opponent player pair, considers:
  1. Fairness: are the two players within ~30% on perceived season-long value?
     ("Perceived" = how the opponent's GM is likely to value the swap — uses
     YTD totals + talent baseline, NOT our model's RoS projection.)
  2. Net RoS gain: would the post-trade Ligers roster project more total
     RoS FP than current? Uses the same slot-fill logic as the lineup
     overlap analyzer, so eligibility and flex-slot fit are handled.
  3. Position fit: post-trade lineup must still fill all slots.

Outputs the top trade ideas globally + grouped by opponent.

Output:
  data/outputs/smart_trade_finder.csv (long list)
  data/outputs/smart_trade_finder.json (top ideas per opponent for dashboard)

Usage:
    python scripts/xfp/smart_trade_finder.py
    python scripts/xfp/smart_trade_finder.py --top 20 --fairness 0.35
"""
from __future__ import annotations
import argparse
import json
import sys
import unicodedata
import re
from pathlib import Path
from collections import defaultdict
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))

# Re-use slot config + projection-loading from overlap analyzer
from scripts.xfp.opponent_lineup_overlap import (
    SLOT_FILL_ORDER, SLOT_DISPLAY_GROUP, DISPLAY_ORDER,
    SP_REMAINING_STARTS, _norm, load_projections, fill_slots,
)

OUT = ROOT / 'data' / 'outputs'
MY_TEAM_NAME = 'New York Ligers'


def build_team_players(league_team, h_lookup, p_lookup, ytd_lookup):
    """Per-player {name, eligible, value (RoS proj), is_pitcher, ytd_proxy}."""
    out = []
    for p in league_team.roster:
        elig = set(getattr(p, 'eligibleSlots', None) or [p.position])
        nk = _norm(p.name)
        is_pitcher = bool(elig & {'SP', 'RP', 'P'})
        info = (p_lookup if is_pitcher else h_lookup).get(nk)
        value = info['ros_fp'] if info else 0.0
        ytd = ytd_lookup.get(nk, 0.0)
        out.append({
            'name': p.name, 'eligible': elig, 'value': value,
            'is_pitcher': is_pitcher, 'ytd_proxy': ytd,
        })
    return out


def total_starter_value(slot_assignment: dict) -> float:
    return sum(s['value'] for s in slot_assignment.values() if s['name'])


def build_ytd_lookup() -> dict:
    """Per-player season-to-date FP proxy from substrate (perceived value)."""
    lookup = {}
    # Hitters: 2026 fp_per_pa_actual × pa
    try:
        h = pd.read_csv(ROOT / 'data' / 'research' / 'xfp_cache' /
                          'hitters_multiyr_2015_2026.csv')
        h = h[h['year'] == 2026].copy()
        h['nk'] = h['player_name'].map(_norm)
        h['fp_ytd'] = h['fp_per_pa_actual'] * h['pa']
        for _, r in h.iterrows():
            lookup[r['nk']] = float(r['fp_ytd'] or 0)
    except Exception:
        pass
    # Pitchers: 2026 rolling fp from rolling_pitchers cache
    try:
        rp = pd.read_csv(ROOT / 'data' / 'research' / 'xfp_cache' /
                          'rolling_pitchers_2018_2026.csv')
        rp = rp[rp['year'] == 2026].sort_values(['pitcher', 'split_day'])
        rp = rp.drop_duplicates('pitcher', keep='last')
        # If `fp_per_start_to × gs_to` is available, that's YTD
        if {'fp_per_start_to', 'gs_to'}.issubset(rp.columns):
            rp['fp_ytd'] = rp['fp_per_start_to'].fillna(0) * rp['gs_to'].fillna(0)
        else:
            rp['fp_ytd'] = 0
        # Need mlb_id -> name; use rh3/rp3 lookup
        rp_proj = pd.read_csv(OUT / 'xfp_rp3_projections.csv')[['pitcher', 'player_name']]
        rp_proj['nk'] = rp_proj['player_name'].map(_norm)
        m = rp.merge(rp_proj, on='pitcher', how='left')
        for _, r in m.iterrows():
            if pd.notna(r.get('nk')):
                lookup[r['nk']] = float(r.get('fp_ytd') or 0)
    except Exception:
        pass
    return lookup


def is_fair(my_val: float, opp_val: float, threshold: float = 0.30) -> tuple[bool, float]:
    """True if max/min of perceived values within (1 + threshold).
    Both values ≤ 5 → automatically fair (deep-roster pieces)."""
    if my_val <= 5 and opp_val <= 5:
        return True, 0.0
    if my_val <= 5 or opp_val <= 5:
        return False, 999.0
    hi, lo = max(my_val, opp_val), min(my_val, opp_val)
    ratio = (hi / lo) - 1
    return ratio <= threshold, round(ratio, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=15,
                    help='Top trades per opponent (default 15)')
    ap.add_argument('--fairness', type=float, default=0.30,
                    help='Max perceived-value ratio gap (default 0.30 = 30%%)')
    ap.add_argument('--min-gain', type=float, default=5.0,
                    help='Minimum RoS FP gain to surface (default +5.0)')
    args = ap.parse_args()

    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    h_lookup, p_lookup = load_projections()
    ytd_lookup = build_ytd_lookup()
    league = ls._get_league()

    team_players = {}
    team_standing = {}
    for t in league.teams:
        team_players[t.team_name] = build_team_players(t, h_lookup, p_lookup, ytd_lookup)
        team_standing[t.team_name] = {'wins': t.wins, 'losses': t.losses, 'standing': t.standing}

    if MY_TEAM_NAME not in team_players:
        print(f'ERROR: {MY_TEAM_NAME} not in league'); return

    my_players = team_players[MY_TEAM_NAME]
    base_assignment, _ = fill_slots(my_players)
    base_value = total_starter_value(base_assignment)
    print(f'\nBase Ligers starting-lineup value: {base_value:.1f} FP RoS')

    all_trades = []
    for opp_name, opp_players in team_players.items():
        if opp_name == MY_TEAM_NAME:
            continue
        opp_base, _ = fill_slots(opp_players)
        opp_base_val = total_starter_value(opp_base)
        for my_p in my_players:
            for opp_p in opp_players:
                # Don't trade same player to themselves
                if my_p['name'] == opp_p['name']:
                    continue
                # Don't propose pure pitcher-for-hitter (less commonly accepted unless huge gap)
                # Allow it but require larger gain
                xpos_swap = my_p['is_pitcher'] != opp_p['is_pitcher']

                fair, ratio = is_fair(my_p['ytd_proxy'], opp_p['ytd_proxy'], args.fairness)
                if not fair:
                    continue

                # Simulate post-trade
                new_roster = [p for p in my_players if p['name'] != my_p['name']] + [opp_p]
                new_assign, _ = fill_slots(new_roster)
                new_value = total_starter_value(new_assign)
                gain = new_value - base_value
                if gain < args.min_gain:
                    continue
                # Bonus filter: require larger gain for cross-position swaps
                if xpos_swap and gain < args.min_gain + 10:
                    continue

                all_trades.append({
                    'opp_name': opp_name,
                    'give': my_p['name'],
                    'give_value_ros': round(my_p['value'], 1),
                    'give_ytd': round(my_p['ytd_proxy'], 1),
                    'get': opp_p['name'],
                    'get_value_ros': round(opp_p['value'], 1),
                    'get_ytd': round(opp_p['ytd_proxy'], 1),
                    'fair_ratio': ratio,
                    'edge_gain_ros': round(gain, 1),
                    'xpos_swap': xpos_swap,
                    'new_lineup_value': round(new_value, 1),
                })

    df = pd.DataFrame(all_trades).sort_values('edge_gain_ros', ascending=False)
    df.to_csv(OUT / 'smart_trade_finder.csv', index=False)
    print(f'\nFound {len(df)} fair trades with ≥ {args.min_gain} FP gain')
    print(f'wrote {OUT / "smart_trade_finder.csv"}')

    # Per-opponent top-N for dashboard JSON
    payload = {
        'my_team': MY_TEAM_NAME, 'base_value': round(base_value, 1),
        'fairness_threshold': args.fairness, 'min_gain': args.min_gain,
        'by_opponent': {},
        'global_top': df.head(args.top).to_dict(orient='records'),
    }
    for opp in sorted(df['opp_name'].unique()):
        sub = df[df['opp_name'] == opp].head(args.top)
        payload['by_opponent'][opp] = sub.to_dict(orient='records')
    with open(OUT / 'smart_trade_finder.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote {OUT / "smart_trade_finder.json"}')

    print(f'\n=== TOP 15 TRADES ACROSS ALL OPPONENTS (sorted by RoS gain) ===')
    cols = ['opp_name', 'give', 'give_ytd', 'get', 'get_ytd', 'fair_ratio', 'edge_gain_ros']
    print(df.head(15)[cols].to_string(index=False))

    print('\n=== TOP-3 PER OPPONENT ===')
    for opp, sub in df.groupby('opp_name', sort=False):
        sub = sub.head(3)
        print(f'\n  vs {opp}:')
        for _, r in sub.iterrows():
            print(f'    give {r["give"]} (ytd {r["give_ytd"]:.0f}) → get '
                  f'{r["get"]} (ytd {r["get_ytd"]:.0f})  fair={r["fair_ratio"]:.2f}  '
                  f'gain={r["edge_gain_ros"]:+.1f}')


if __name__ == '__main__':
    main()
