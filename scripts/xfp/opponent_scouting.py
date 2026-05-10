"""opponent_scouting.py — per-GM roster profile + transaction tendency tracker.

For each team in the BrownU league, compute:
  - Roster total xFP value (sum of rh3 + rp3 across roster)
  - Position composition (count by pos)
  - Bench-depth proxy: number of high-value hitters/SPs beyond starting needs
  - Roster age profile (mean age via hitter_age_career + sp_age_career)
  - Most-recent transactions (via espn-api recent_activity)
  - Standing context

Auto-pulled signals only. Manual diary observations live in
data/research/opponent_notes.md — keep that as a separate human-edited file.

Outputs:
  data/outputs/opponent_scouting.csv  (one row per team, key metrics)
  data/outputs/opponent_scouting.json (for dashboard)

Usage:
    python scripts/xfp/opponent_scouting.py
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import json
import sys
import unicodedata
import re
import pandas as pd

sys.path.insert(0, '.')

ROOT = Path('c:/Users/Joshua/plv_clone')
OUT = ROOT / 'data' / 'outputs'

# Roster positional needs (BrownU 8-team H2H typical setup)
ROSTER_SLOTS = {'C': 1, '1B': 1, '2B': 1, '3B': 1, 'SS': 1, 'OF': 3, 'DH': 1,
                'SP': 5, 'RP': 3}  # starts; bench beyond


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'[,]+', ' ', s)
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def main():
    from app import espn_connector as ec
    league = ec._get_league()

    # Load projections
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    rp['nk'] = rp['player_name'].map(_norm)
    rh_lookup = rh.drop_duplicates('nk').set_index('nk')['xfp_rh3_per_pa'].to_dict()
    rh_pa = rh.drop_duplicates('nk').set_index('nk')['expected_pa_remaining'].to_dict() if 'expected_pa_remaining' in rh.columns else {}
    rp_lookup = rp.drop_duplicates('nk').set_index('nk')['xfp_rp3_per_start'].to_dict()
    rp_gs = rp.drop_duplicates('nk').set_index('nk').get('gs_to', pd.Series()).to_dict() if 'gs_to' in rp.columns else {}

    # Recent activity (transactions) for context
    try:
        activity = league.recent_activity(size=200, msg_type='TRADED')
    except Exception:
        activity = []
    try:
        adds = league.recent_activity(size=200, msg_type='ADDED')
    except Exception:
        adds = []
    try:
        drops = league.recent_activity(size=200, msg_type='DROPPED')
    except Exception:
        drops = []

    # Per-team transaction counts (last 30 days)
    cutoff = datetime.now() - timedelta(days=30)
    tx_counts = {}  # team_id -> {'trades': N, 'adds': N, 'drops': N}
    for tx_list, key in [(activity, 'trades'), (adds, 'adds'), (drops, 'drops')]:
        for act in tx_list or []:
            try:
                act_date = datetime.fromtimestamp(act.date / 1000) if act.date else None
                if act_date is None or act_date < cutoff:
                    continue
                for action_tuple in act.actions:
                    team = action_tuple[0]
                    tid = team.team_id
                    tx_counts.setdefault(tid, {'trades': 0, 'adds': 0, 'drops': 0})
                    tx_counts[tid][key] += 1
            except Exception:
                continue

    # Per-team profile
    rows = []
    for team in league.teams:
        roster_hits, roster_pits = [], []
        for p in team.roster:
            nk = _norm(p.name)
            pos = getattr(p, 'position', '')
            if pos in {'SP', 'RP', 'P'}:
                fp_per_g = rp_lookup.get(nk)
                roster_pits.append({
                    'name': p.name, 'pos': pos, 'nk': nk,
                    'xfp_per_start': fp_per_g,
                    'gs_to': rp_gs.get(nk) if rp_gs else None,
                })
            else:
                fp_per_pa = rh_lookup.get(nk)
                pa_est = rh_pa.get(nk, 0)
                roster_hits.append({
                    'name': p.name, 'pos': pos, 'nk': nk,
                    'xfp_per_pa': fp_per_pa,
                    'expected_pa_remaining': pa_est,
                    'projected_ros_fp': (fp_per_pa * pa_est) if fp_per_pa and pa_est else None,
                })

        # Aggregate
        hit_total_fp = sum(h['projected_ros_fp'] or 0 for h in roster_hits)
        # Pitchers: estimate per-pitcher with ~16 remaining starts cap (proxy)
        sp_total = sum((p['xfp_per_start'] or 0) * 16 for p in roster_pits if p['pos'] == 'SP')
        rp_total = sum((p['xfp_per_start'] or 0) * 30 for p in roster_pits if p['pos'] == 'RP')

        # Position imbalances vs standard slots
        pos_counts = {}
        for p in roster_hits + roster_pits:
            pos_counts[p['pos']] = pos_counts.get(p['pos'], 0) + 1

        # Trade-chip candidates: rostered with high projected RoS who might be expendable
        top_hits = sorted([h for h in roster_hits if h['projected_ros_fp']],
                          key=lambda x: -x['projected_ros_fp'])
        top_pits = sorted([p for p in roster_pits if p['xfp_per_start']],
                          key=lambda x: -x['xfp_per_start'])

        tx = tx_counts.get(team.team_id, {'trades': 0, 'adds': 0, 'drops': 0})
        rows.append({
            'team_id': team.team_id,
            'team_name': team.team_name,
            'wins': team.wins,
            'losses': team.losses,
            'standing': team.standing,
            'roster_size': len(team.roster),
            'hitter_ros_fp_total': round(hit_total_fp, 1),
            'sp_value_proxy': round(sp_total, 1),
            'rp_value_proxy': round(rp_total, 1),
            'total_value': round(hit_total_fp + sp_total + rp_total, 1),
            'pos_counts': pos_counts,
            'top3_hitters': [h['name'] for h in top_hits[:3]],
            'top3_pitchers': [p['name'] for p in top_pits[:3]],
            'trades_30d': tx['trades'],
            'adds_30d': tx['adds'],
            'drops_30d': tx['drops'],
        })

    df = pd.DataFrame(rows).sort_values('total_value', ascending=False)

    # Save
    df.to_csv(OUT / 'opponent_scouting.csv', index=False)
    print(f'wrote {OUT / "opponent_scouting.csv"}')

    payload = df.to_dict(orient='records')
    with open(OUT / 'opponent_scouting.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), default=str)
    print(f'wrote {OUT / "opponent_scouting.json"}')

    # Console summary
    print('\n=== Opponent Scouting (sorted by total projected value) ===')
    show_cols = ['team_name', 'wins', 'losses', 'standing', 'total_value',
                 'hitter_ros_fp_total', 'sp_value_proxy', 'trades_30d', 'adds_30d', 'drops_30d']
    print(df[show_cols].to_string(index=False))

    # Notes file
    notes = ROOT / 'data' / 'research' / 'opponent_notes.md'
    if not notes.exists():
        with open(notes, 'w', encoding='utf-8') as f:
            f.write('# Opponent Notes — BrownU League\n\n')
            for team in league.teams:
                f.write(f'## {team.team_name} (team_id {team.team_id})\n')
                f.write('- Trading style:\n')
                f.write('- Overvalues:\n')
                f.write('- Undervalues:\n')
                f.write('- Active periods:\n')
                f.write('- Past trade history with Ligers:\n\n')
        print(f'\nSeeded {notes} (manual observations go here)')
    else:
        print(f'\nNotes file already exists at {notes}')


if __name__ == '__main__':
    main()
