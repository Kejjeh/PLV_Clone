"""opponent_lineup_overlap.py — per-opponent per-position edge analyzer.

For each of the 7 opponents, computes:
  - Starting-lineup projected RoS FP per position (C, 1B, 2B, 3B, SS, OF×3, SP×5, RP×3)
  - Per-position edge (Ligers value − opponent value)
  - Total edge across all positions (sum)
  - Biggest advantage / biggest weakness for trade-target framing
  - Redundancy score (how much of opp's strength is in positions where we ALSO
    have surplus — i.e., they can't trade their strength to fill our gaps because
    we don't have a gap there)

Output:
  data/outputs/opponent_lineup_overlap.csv (long table: team × position rows)
  data/outputs/opponent_lineup_overlap.json (per-opp summary for dashboard)

Usage:
    python scripts/xfp/opponent_lineup_overlap.py
"""
from __future__ import annotations
import json
import sys
import unicodedata
import re
from pathlib import Path
from collections import defaultdict
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'data' / 'outputs'

MY_TEAM_NAME = 'New York Ligers'

# Starting-lineup slot counts (BrownU H2H)
STARTERS = {
    'C': 1, '1B': 1, '2B': 1, '3B': 1, 'SS': 1, 'OF': 3,
    'SP': 5, 'RP': 3,
}
OF_POSITIONS = {'OF', 'CF', 'LF', 'RF'}

# Estimated remaining starts per SP (rough proxy — will refine if we want)
SP_REMAINING_STARTS = 18  # ~20 weeks left of regular season, every 5 days = 4-ish starts/mo


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'[,]+', ' ', s)
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))  # order-independent sorted-words key


def load_projections():
    """Returns (hitter_lookup, pitcher_lookup) keyed by normalized name."""
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    rh = rh.drop_duplicates('nk', keep='first')
    h_lookup = {}
    for _, r in rh.iterrows():
        h_lookup[r['nk']] = {
            'name': r['player_name'],
            'ros_fp': float(r.get('expected_total_fp_remaining') or 0),
            'per_pa': float(r.get('xfp_rh3_per_pa') or 0),
            'pa_remaining': float(r.get('expected_pa_remaining') or 0),
        }

    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rp['nk'] = rp['player_name'].map(_norm)
    rp = rp.drop_duplicates('nk', keep='first')
    p_lookup = {}
    for _, r in rp.iterrows():
        per_start = float(r.get('xfp_rp3_per_start') or 0)
        p_lookup[r['nk']] = {
            'name': r['player_name'],
            'per_start': per_start,
            'ros_fp': per_start * SP_REMAINING_STARTS,  # crude SP-side projection
        }
    return h_lookup, p_lookup


def position_bucket(pos: str) -> str | None:
    """Map raw ESPN position to lineup slot."""
    if pos in OF_POSITIONS:
        return 'OF'
    if pos in STARTERS:
        return pos
    if pos == 'DH':
        # Add DH to OF? No — DH slot doesn't exist in our STARTERS map. Treat as bench.
        return None
    return None


def evaluate_team(roster_df: pd.DataFrame, h_lookup: dict, p_lookup: dict) -> dict:
    """Return per-position bucketed list of {name, value} for one team."""
    buckets = defaultdict(list)
    for _, p in roster_df.iterrows():
        slot = position_bucket(p['position'])
        if slot is None:
            continue
        nk = _norm(p['player_name'])
        if slot in ('SP', 'RP'):
            info = p_lookup.get(nk)
            if not info:
                continue
            buckets[slot].append({'name': p['player_name'], 'value': info['ros_fp']})
        else:
            info = h_lookup.get(nk)
            if not info:
                continue
            buckets[slot].append({'name': p['player_name'], 'value': info['ros_fp']})

    # Sort each bucket by value descending
    for k in buckets:
        buckets[k].sort(key=lambda x: -x['value'])
    return dict(buckets)


def position_value(bucket_list: list[dict], n_starters: int) -> tuple[float, list[str], float]:
    """Return (starter_total_value, starter_names, bench_value_at_position)."""
    starters = bucket_list[:n_starters]
    bench = bucket_list[n_starters:]
    starter_total = sum(p['value'] for p in starters)
    bench_total = sum(p['value'] for p in bench) * 0.25  # bench worth ~25% of starter
    return starter_total, [p['name'] for p in starters], bench_total


def main():
    from app import espn_connector as ec
    teams = ec.get_all_teams()
    print(f'Loaded {len(teams)} player-roster rows across {teams["team_name"].nunique()} teams')

    h_lookup, p_lookup = load_projections()
    print(f'Projections: {len(h_lookup)} hitters, {len(p_lookup)} pitchers')

    # Build per-team buckets
    team_buckets = {}
    for tname, grp in teams.groupby('team_name'):
        team_buckets[tname] = evaluate_team(grp, h_lookup, p_lookup)

    if MY_TEAM_NAME not in team_buckets:
        print(f'ERROR: {MY_TEAM_NAME} not found in roster snapshot')
        return

    # Compute Ligers per-position values once
    my_values = {}
    for slot, n in STARTERS.items():
        val, names, bench = position_value(team_buckets[MY_TEAM_NAME].get(slot, []), n)
        my_values[slot] = {'value': val, 'names': names, 'bench': bench, 'depth': len(team_buckets[MY_TEAM_NAME].get(slot, []))}

    # Try to attach standings + head-to-head if available
    try:
        league = ec._get_league()
        team_standing = {t.team_name: {'wins': t.wins, 'losses': t.losses, 'standing': t.standing}
                          for t in league.teams}
    except Exception:
        team_standing = {}

    h2h_path = OUT / 'opponent_matchup_history.json'
    h2h = {}
    if h2h_path.exists():
        try:
            h2h_data = json.loads(h2h_path.read_text(encoding='utf-8'))
            for opp, s in h2h_data.get('summary', {}).items():
                h2h[opp] = s
        except Exception:
            pass

    # Per-opponent edge analysis
    opps = []
    long_rows = []
    for tname, buckets in team_buckets.items():
        if tname == MY_TEAM_NAME:
            continue
        opp_values = {}
        per_pos = {}
        total_edge = 0.0
        for slot, n in STARTERS.items():
            opp_val, opp_names, opp_bench = position_value(buckets.get(slot, []), n)
            opp_values[slot] = {'value': opp_val, 'names': opp_names, 'bench': opp_bench,
                                 'depth': len(buckets.get(slot, []))}
            edge = my_values[slot]['value'] - opp_val
            per_pos[slot] = {
                'my_value': round(my_values[slot]['value'], 1),
                'my_starters': my_values[slot]['names'],
                'my_bench_val': round(my_values[slot]['bench'], 1),
                'opp_value': round(opp_val, 1),
                'opp_starters': opp_names,
                'opp_bench_val': round(opp_bench, 1),
                'edge': round(edge, 1),
            }
            total_edge += edge
            long_rows.append({
                'opp_name': tname, 'position': slot,
                'my_value': round(my_values[slot]['value'], 1),
                'opp_value': round(opp_val, 1),
                'edge': round(edge, 1),
            })

        # Biggest advantage/weakness
        pos_sorted = sorted(per_pos.items(), key=lambda x: -x[1]['edge'])
        biggest_advantage = pos_sorted[0] if pos_sorted else None
        biggest_weakness = pos_sorted[-1] if pos_sorted else None

        # Trade-target framing: where they're stacked AND we're thin
        trade_targets = []
        for slot in STARTERS:
            if per_pos[slot]['edge'] < -10 and opp_values[slot]['depth'] > STARTERS[slot]:
                # They have surplus AND we're weak — they could trade their depth here for our depth elsewhere
                trade_targets.append({
                    'position': slot,
                    'their_bench_value': per_pos[slot]['opp_bench_val'],
                    'their_starters': per_pos[slot]['opp_starters'],
                    'my_edge': per_pos[slot]['edge'],
                })
        # Sort by biggest deficit
        trade_targets.sort(key=lambda x: x['my_edge'])

        std = team_standing.get(tname, {})
        h2h_rec = h2h.get(tname, {})
        opps.append({
            'opp_name': tname,
            'standing': std.get('standing'),
            'wins': std.get('wins'),
            'losses': std.get('losses'),
            'h2h_record': f"{h2h_rec.get('wins',0)}-{h2h_rec.get('losses',0)}" + (
                f"-{h2h_rec['ties']}" if h2h_rec.get('ties') else ''),
            'h2h_avg_margin': h2h_rec.get('avg_margin'),
            'total_edge': round(total_edge, 1),
            'biggest_advantage': biggest_advantage[0] if biggest_advantage else None,
            'biggest_advantage_edge': biggest_advantage[1]['edge'] if biggest_advantage else None,
            'biggest_weakness': biggest_weakness[0] if biggest_weakness else None,
            'biggest_weakness_edge': biggest_weakness[1]['edge'] if biggest_weakness else None,
            'per_position': per_pos,
            'trade_targets': trade_targets,
        })

    opps.sort(key=lambda o: -(o['total_edge'] or 0))

    # Save
    long_df = pd.DataFrame(long_rows)
    long_df.to_csv(OUT / 'opponent_lineup_overlap.csv', index=False)
    print(f'wrote {OUT / "opponent_lineup_overlap.csv"}')

    payload = {
        'my_team': MY_TEAM_NAME,
        'my_position_values': {k: {'value': round(v['value'], 1),
                                     'starters': v['names'],
                                     'bench_val': round(v['bench'], 1),
                                     'depth': v['depth']}
                                for k, v in my_values.items()},
        'opponents': opps,
    }
    with open(OUT / 'opponent_lineup_overlap.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote {OUT / "opponent_lineup_overlap.json"}')

    # Console summary
    print('\n=== Per-opponent lineup overlap (sorted by my projected edge) ===')
    print(f'{"Opponent":<28s} {"H2H":<7s} {"Edge":>8s}  {"Strongest":<10s}  {"Weakest":<12s}')
    for o in opps:
        adv = f"{o['biggest_advantage']}({o['biggest_advantage_edge']:+.0f})" if o['biggest_advantage'] else '—'
        wk = f"{o['biggest_weakness']}({o['biggest_weakness_edge']:+.0f})" if o['biggest_weakness'] else '—'
        print(f'  {o["opp_name"]:<28s} {o["h2h_record"]:<7s} {o["total_edge"]:>+8.1f}  {adv:<10s}  {wk:<12s}')


if __name__ == '__main__':
    main()
