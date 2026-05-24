"""opponent_lineup_overlap.py — per-opponent per-position edge analyzer.

For each of the 7 opponents, computes Ligers' projected RoS FP at each
STARTING SLOT vs theirs, edge, and trade-target framing.

BrownU starting lineup (confirmed 2026-05-10 from ESPN screenshot):
  Hitters (13 slots): C, 1B, 2B, 3B, SS, MI (2B/SS), CI (1B/3B), OF×5, UTIL
  Pitchers (8 slots): SP×5, RP×3
  Bench + IL beyond starters.

Slot-fill logic per team:
  1) Greedily fill primary positional slots from best-projected eligible
     player. Uses ESPN `eligibleSlots` so multi-position players (Vladdy
     1B/3B, Donovan 2B/3B/OF, etc.) get placed optimally.
  2) After primary slots, fill MI from best-leftover 2B/SS eligibility.
  3) Then CI from best-leftover 1B/3B eligibility.
  4) Then UTIL from best-leftover hitter.
  5) Edge = (my slot value) − (their slot value), summed gives total edge.

Output:
  data/outputs/opponent_lineup_overlap.csv (long: team × slot)
  data/outputs/opponent_lineup_overlap.json (per-opp summary for dashboard)
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

# Slot fill order matters: fill restrictive slots first, then flex.
SLOT_FILL_ORDER = [
    ('C',    {'C'}),
    ('1B',   {'1B'}),
    ('2B',   {'2B'}),
    ('3B',   {'3B'}),
    ('SS',   {'SS'}),
    ('OF1',  {'OF', 'LF', 'CF', 'RF'}),
    ('OF2',  {'OF', 'LF', 'CF', 'RF'}),
    ('OF3',  {'OF', 'LF', 'CF', 'RF'}),
    ('OF4',  {'OF', 'LF', 'CF', 'RF'}),
    ('OF5',  {'OF', 'LF', 'CF', 'RF'}),
    ('MI',   {'2B', 'SS', '2B/SS'}),
    ('CI',   {'1B', '3B', '1B/3B'}),
    ('UTIL', {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH', 'UTIL'}),
    # Note: BrownU has NO per-day SP slot count — any team can roll 10 SPs in
    # a week (only first 10 starts count for scoring). We keep SP1-SP10 here
    # as placeholders for greedy assignment ranked by value, then the
    # cap-aware aggregation post-fill applies the 10-starts/week ceiling
    # (which works out to 200 starts per team RoS at this date).
    ('SP1',  {'SP'}), ('SP2',  {'SP'}), ('SP3',  {'SP'}), ('SP4',  {'SP'}),
    ('SP5',  {'SP'}), ('SP6',  {'SP'}), ('SP7',  {'SP'}), ('SP8',  {'SP'}),
    ('SP9',  {'SP'}), ('SP10', {'SP'}),
    # RP cap is real — 4 RP slots in BrownU
    ('RP1',  {'RP'}), ('RP2',  {'RP'}), ('RP3',  {'RP'}), ('RP4',  {'RP'}),
]

# Aggregate slot grouping for display (collapse OF1-5 into single "OF" row)
SLOT_DISPLAY_GROUP = {
    'C': 'C', '1B': '1B', '2B': '2B', '3B': '3B', 'SS': 'SS',
    'OF1': 'OF', 'OF2': 'OF', 'OF3': 'OF', 'OF4': 'OF', 'OF5': 'OF',
    'MI': 'MI (2B/SS)', 'CI': 'CI (1B/3B)', 'UTIL': 'UTIL',
    'SP1':'SP','SP2':'SP','SP3':'SP','SP4':'SP','SP5':'SP',
    'SP6':'SP','SP7':'SP','SP8':'SP','SP9':'SP','SP10':'SP',
    'RP1':'RP','RP2':'RP','RP3':'RP','RP4':'RP',
}
DISPLAY_ORDER = ['C', '1B', '2B', '3B', 'SS', 'MI (2B/SS)', 'CI (1B/3B)',
                  'OF', 'UTIL', 'SP', 'RP']

# Empirical 2024-2025 finding: league-average SP makes 1.19 starts per active
# week (NOT 2). 82.2% of SP-weeks have 1 start, only 17.8% have 2.
# So SP_REMAINING_STARTS scales dynamically with weeks left in season.
HEALTHY_SP_STARTS_PER_WEEK = 1.19  # empirical, from starts_per_week_analysis.py
SEASON_END_DATE = '2026-09-28'  # approximate MLB regular season end


def _compute_sp_remaining_starts() -> int:
    """Today-relative remaining starts for a healthy full-time SP."""
    from datetime import date as _date
    days = (pd.Timestamp(SEASON_END_DATE).date() - _date.today()).days
    weeks = max(days, 0) / 7
    return max(int(round(weeks * HEALTHY_SP_STARTS_PER_WEEK)), 8)


SP_REMAINING_STARTS = _compute_sp_remaining_starts()


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'[,]+', ' ', s)
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def load_projections():
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    rh = rh.drop_duplicates('nk', keep='first')
    h_lookup = {}
    for _, r in rh.iterrows():
        h_lookup[r['nk']] = {
            'name': r['player_name'],
            'ros_fp': float(r.get('expected_total_fp_remaining') or 0),
        }

    # SP projections from rp3 (per-start × estimated remaining starts)
    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rp['nk'] = rp['player_name'].map(_norm)
    rp = rp.drop_duplicates('nk', keep='first')
    p_lookup = {}
    for _, r in rp.iterrows():
        per_start = float(r.get('xfp_rp3_per_start') or 0)
        p_lookup[r['nk']] = {
            'name': r['player_name'],
            'ros_fp': per_start * SP_REMAINING_STARTS,
            'src': 'rp3',
        }

    # RP projections from rprs2 (closer/setup roles, has xfp_ros directly)
    rprs2_path = OUT / 'xfp_rprs2_projections.csv'
    if rprs2_path.exists():
        rprs2 = pd.read_csv(rprs2_path)
        if 'name_api' in rprs2.columns:
            rprs2['nk'] = rprs2['name_api'].map(_norm)
            rprs2 = rprs2.drop_duplicates('nk', keep='first')
            for _, r in rprs2.iterrows():
                nk = r['nk']
                ros = float(r.get('xfp_ros') or 0)
                # Prefer RP-specific value if it's higher (real RPs would have low
                # rp3 value since they don't start; for converted SPs we keep rp3)
                existing = p_lookup.get(nk)
                if not existing or existing['ros_fp'] < ros:
                    p_lookup[nk] = {
                        'name': r['name_api'],
                        'ros_fp': ros,
                        'src': 'rprs2',
                    }
    return h_lookup, p_lookup


def build_team_players(league_team, h_lookup, p_lookup):
    """Return list of {name, eligible: set, value, is_pitcher}."""
    out = []
    for p in league_team.roster:
        elig = set(getattr(p, 'eligibleSlots', None) or [p.position])
        nk = _norm(p.name)
        is_pitcher = bool(elig & {'SP', 'RP', 'P'})
        info = (p_lookup if is_pitcher else h_lookup).get(nk)
        if info is None:
            value = 0.0
        else:
            value = info['ros_fp']
        out.append({
            'name': p.name, 'eligible': elig, 'value': value, 'is_pitcher': is_pitcher,
        })
    return out


def fill_slots(players: list[dict]) -> tuple[dict, list]:
    """Greedy assignment of players to slots in SLOT_FILL_ORDER.

    Returns ({slot: {name, value}}, [bench_players_unused]).

    For SPs, applies the BrownU 10-starts/week team cap by scaling each
    SP's RoS value by the cap-binding fraction. SPs ranked above the cap
    boundary get full value; SPs below contribute only their partial
    starts under the cap. RoS starts cap = 10 × weeks_remaining ≈ 200
    when called early-to-mid season.
    """
    from datetime import date as _date
    days_remaining = max((pd.Timestamp(SEASON_END_DATE).date() - _date.today()).days, 0)
    weeks_remaining = days_remaining / 7
    TEAM_SP_STARTS_CAP = int(round(weeks_remaining * 10))  # 10 SP starts/week

    available = sorted(players, key=lambda x: -x['value'])
    assigned = {}
    used = set()  # player names already placed
    sp_starts_assigned = 0  # cumulative SP starts charged against cap
    PER_SP_ROS_STARTS = SP_REMAINING_STARTS  # ~24 currently

    for slot, allowed in SLOT_FILL_ORDER:
        is_pitch_slot = slot.startswith(('SP', 'RP'))
        is_sp_slot = slot.startswith('SP')
        for p in available:
            if p['name'] in used:
                continue
            if p['is_pitcher'] != is_pitch_slot:
                continue
            if not (p['eligible'] & allowed):
                continue
            value = p['value']
            if is_sp_slot:
                # Apply cumulative SP-starts cap: marginal SPs past the cap
                # get reduced credit proportional to how many of their
                # 24 RoS starts fit under the remaining team cap budget.
                remaining_starts = max(TEAM_SP_STARTS_CAP - sp_starts_assigned, 0)
                if remaining_starts <= 0:
                    value = 0.0
                else:
                    starts_used = min(PER_SP_ROS_STARTS, remaining_starts)
                    if PER_SP_ROS_STARTS > 0:
                        value = value * (starts_used / PER_SP_ROS_STARTS)
                    sp_starts_assigned += starts_used
            assigned[slot] = {'name': p['name'], 'value': round(value, 2)}
            used.add(p['name'])
            break
        else:
            assigned[slot] = {'name': None, 'value': 0.0}
    bench = [p for p in available if p['name'] not in used]
    return assigned, bench


def collapse_to_groups(slot_assignment: dict) -> dict:
    """Sum slot values into display groups (OF1-5 → OF, SP1-5 → SP, etc.)."""
    grouped = defaultdict(lambda: {'value': 0.0, 'starters': []})
    for slot, info in slot_assignment.items():
        group = SLOT_DISPLAY_GROUP.get(slot, slot)
        grouped[group]['value'] += info['value']
        if info['name']:
            grouped[group]['starters'].append(info['name'])
    return dict(grouped)


def main():
    from plv_clone.league_state import LeagueState
    h_lookup, p_lookup = load_projections()
    ls = LeagueState()
    league = ls._get_league()

    # Build per-team player lists from league teams (use eligibleSlots)
    team_data = {}
    team_standing = {}
    for t in league.teams:
        team_data[t.team_name] = build_team_players(t, h_lookup, p_lookup)
        team_standing[t.team_name] = {'wins': t.wins, 'losses': t.losses,
                                        'standing': t.standing}

    if MY_TEAM_NAME not in team_data:
        print(f'ERROR: {MY_TEAM_NAME} not in league'); return

    my_slot_assignment, my_bench = fill_slots(team_data[MY_TEAM_NAME])
    my_groups = collapse_to_groups(my_slot_assignment)
    print(f'\nLigers starting lineup ({sum(1 for s in my_slot_assignment if my_slot_assignment[s]["name"])} slots filled):')
    for slot, info in my_slot_assignment.items():
        print(f'  {slot:<6s} {info["name"] or "(empty)":<30s}  {info["value"]:.1f} FP')

    # Head-to-head history if available
    h2h = {}
    h2h_path = OUT / 'opponent_matchup_history.json'
    if h2h_path.exists():
        try:
            h2h = json.loads(h2h_path.read_text(encoding='utf-8')).get('summary', {})
        except Exception:
            pass

    opps = []
    long_rows = []
    for tname, players in team_data.items():
        if tname == MY_TEAM_NAME:
            continue
        opp_assignment, opp_bench = fill_slots(players)
        opp_groups = collapse_to_groups(opp_assignment)

        per_group = {}
        total_edge = 0.0
        for g in DISPLAY_ORDER:
            mv = my_groups.get(g, {'value': 0, 'starters': []})
            ov = opp_groups.get(g, {'value': 0, 'starters': []})
            edge = mv['value'] - ov['value']
            per_group[g] = {
                'my_value': round(mv['value'], 1),
                'my_starters': mv['starters'],
                'opp_value': round(ov['value'], 1),
                'opp_starters': ov['starters'],
                'edge': round(edge, 1),
            }
            total_edge += edge
            long_rows.append({
                'opp_name': tname, 'slot_group': g,
                'my_value': round(mv['value'], 1),
                'opp_value': round(ov['value'], 1),
                'edge': round(edge, 1),
            })

        sorted_groups = sorted(per_group.items(), key=lambda x: -x[1]['edge'])
        biggest_adv = sorted_groups[0]
        biggest_wk = sorted_groups[-1]

        # Trade targets: positions where they have surplus (high bench at slot)
        # AND we're behind (edge < -10)
        trade_targets = []
        opp_bench_values_by_slot = defaultdict(float)
        opp_bench_names_by_slot = defaultdict(list)
        for p in opp_bench:
            for slot, allowed in SLOT_FILL_ORDER:
                if slot.startswith(('SP', 'RP')) != p['is_pitcher']:
                    continue
                if p['eligible'] & allowed:
                    group = SLOT_DISPLAY_GROUP.get(slot, slot)
                    opp_bench_values_by_slot[group] += p['value']
                    opp_bench_names_by_slot[group].append(p['name'])
                    break
        for g in DISPLAY_ORDER:
            if per_group[g]['edge'] < -15 and opp_bench_values_by_slot[g] > 0:
                trade_targets.append({
                    'position': g,
                    'my_edge': per_group[g]['edge'],
                    'their_bench_value': round(opp_bench_values_by_slot[g], 1),
                    'their_bench_names': opp_bench_names_by_slot[g][:3],
                })
        trade_targets.sort(key=lambda t: t['my_edge'])

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
            'biggest_advantage': biggest_adv[0],
            'biggest_advantage_edge': biggest_adv[1]['edge'],
            'biggest_weakness': biggest_wk[0],
            'biggest_weakness_edge': biggest_wk[1]['edge'],
            'per_position': per_group,
            'trade_targets': trade_targets,
        })

    opps.sort(key=lambda o: -o['total_edge'])

    long_df = pd.DataFrame(long_rows)
    long_df.to_csv(OUT / 'opponent_lineup_overlap.csv', index=False)

    my_position_values = {g: {'value': round(my_groups.get(g, {'value': 0})['value'], 1),
                                'starters': my_groups.get(g, {'starters': []})['starters']}
                            for g in DISPLAY_ORDER}

    payload = {
        'my_team': MY_TEAM_NAME,
        'my_position_values': my_position_values,
        'my_slot_assignment': {s: my_slot_assignment[s] for s in my_slot_assignment},
        'opponents': opps,
    }
    with open(OUT / 'opponent_lineup_overlap.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)

    print(f'\nwrote {OUT / "opponent_lineup_overlap.csv"}')
    print(f'wrote {OUT / "opponent_lineup_overlap.json"}')

    print('\n=== Per-opponent total edge (sorted desc) ===')
    print(f'{"Opponent":<28s} {"H2H":<7s} {"Edge":>8s}  {"Strongest":<15s}  {"Weakest":<15s}')
    for o in opps:
        print(f'  {o["opp_name"]:<28s} {o["h2h_record"]:<7s} {o["total_edge"]:>+8.1f}  '
              f'{o["biggest_advantage"]}({o["biggest_advantage_edge"]:+.0f}){"":<5s}  '
              f'{o["biggest_weakness"]}({o["biggest_weakness_edge"]:+.0f})')


if __name__ == '__main__':
    main()
