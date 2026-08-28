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
from plv_clone.projections import PROJECTIONS

_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))

from plv_clone.paths import ROOT
OUT = ROOT / 'data' / 'outputs'

# Roster positional needs (BrownU 8-team H2H — confirmed 2026-05-10/11)
# 13 hitter slots: C, 1B, 2B, 3B, SS, MI (2B/SS), CI (1B/3B), OF×5, UTIL
# 9 pitcher slots: SP×5, RP×4
ROSTER_SLOTS = {'C': 1, '1B': 1, '2B': 1, '3B': 1, 'SS': 1,
                'OF': 5, 'MI': 1, 'CI': 1, 'UTIL': 1,
                'SP': 5, 'RP': 4}

# Cap-aware aggregation for SP value. BrownU has NO per-day SP slot count —
# the only constraint is the SP_CAP (10) starts/week scoring cap. So total
# team SP-starts can go up to SP_CAP × ~20 RoS weeks. Each SP averages
# STARTS_PER_SP_PER_WEEK (~1.19, cap_math owner) × weeks_remaining ≈ 24 RoS
# starts. Optimal SP count ≈ team starts / per-SP starts ≈ 8.4 (8-9 SPs).
# Above that, marginal SPs lose value as their starts get capped.
from plv_clone.cap_math import SP_CAP, STARTS_PER_SP_PER_WEEK
_ROS_WEEKS = 20
CAP_AWARE_TEAM_SP_STARTS = SP_CAP * _ROS_WEEKS                       # 200
CAP_AWARE_PER_SP_STARTS = round(STARTS_PER_SP_PER_WEEK * _ROS_WEEKS)  # ~24
CAP_AWARE_RP_STARTERS = 4
CAP_AWARE_RP_RoS_GAMES = 25
# 13 hitter slots in BrownU; deeper bench doesn't add weekly score
CAP_AWARE_HITTER_STARTERS = 13


# Name join key — OWNER: plv_clone.utils.name_match.join_key (order-independent,
# so "Fried, Max" == "Max Fried"). NEVER re-derive locally: 127 local copies
# drifted apart and mis-keyed Ryan O'Hearn's curly apostrophe (2026-07-28).
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


def main():
    from plv_clone.league_state import LeagueState
    from scripts.xfp.opponent_lineup_overlap import load_projections
    ls = LeagueState()
    league = ls._get_league()

    # Load projections — hitters and pitchers
    rh = PROJECTIONS.rh3()
    rh['nk'] = rh['player_name'].map(_norm)
    rh = rh.drop_duplicates('nk')
    rh_lookup = rh.set_index('nk')['xfp_rh3_per_pa'].to_dict()
    rh_pa = rh.set_index('nk')['expected_pa_remaining'].to_dict() if 'expected_pa_remaining' in rh.columns else {}

    # Use role-aware projection loader (rp3 for SPs, rprs2 for closers/setup).
    # p_lookup_full[nk] = {'name', 'ros_fp', 'src'}. For SPs ros_fp = per_start*18;
    # for RPs ros_fp = rprs2.xfp_ros (full RoS already).
    _, p_lookup_full = load_projections()
    rp_lookup = {k: v['ros_fp'] for k, v in p_lookup_full.items()}
    rp_src    = {k: v.get('src') for k, v in p_lookup_full.items()}

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
                # ros_fp here is total RoS value (rp3 per_start × 18 for SPs,
                # rprs2 full RoS for closers/setup). Treat all on same scale.
                ros_value = rp_lookup.get(nk, 0) or 0
                roster_pits.append({
                    'name': p.name, 'pos': pos, 'nk': nk,
                    'ros_fp': ros_value,
                    'src': rp_src.get(nk, 'none'),
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

        # Aggregate — cap-aware: only top 13 hitters (starting slots) count
        hit_pool = sorted([(h['projected_ros_fp'] or 0) for h in roster_hits], reverse=True)
        hit_total_fp = sum(hit_pool[:CAP_AWARE_HITTER_STARTERS])
        # SP: cap-aware. Use ALL SPs but cap cumulative starts at the 10/week
        # ceiling (200 RoS total). Per-SP value is per_start × min(remaining_cap, 24).
        # ros_fp here = per_start × 24 already (set by load_projections).
        sp_pool = sorted(
            [p['ros_fp'] for p in roster_pits if p['pos'] == 'SP'],
            reverse=True)
        sp_total = 0.0
        starts_remaining = CAP_AWARE_TEAM_SP_STARTS
        for ros in sp_pool:
            if starts_remaining <= 0: break
            this_starts = min(CAP_AWARE_PER_SP_STARTS, starts_remaining)
            if CAP_AWARE_PER_SP_STARTS > 0:
                sp_total += ros * (this_starts / CAP_AWARE_PER_SP_STARTS)
            starts_remaining -= this_starts
        # RP: top 4 RPs (real 4 RP slots). rprs2 gives full RoS directly.
        rp_pool = sorted(
            [p['ros_fp'] for p in roster_pits if p['pos'] == 'RP'],
            reverse=True)
        rp_total = sum(rp_pool[:CAP_AWARE_RP_STARTERS])

        # Position imbalances vs standard slots
        pos_counts = {}
        for p in roster_hits + roster_pits:
            pos_counts[p['pos']] = pos_counts.get(p['pos'], 0) + 1

        # Trade-chip candidates: rostered with high projected RoS who might be expendable
        top_hits = sorted([h for h in roster_hits if h['projected_ros_fp']],
                          key=lambda x: -x['projected_ros_fp'])
        top_pits = sorted([p for p in roster_pits if p['ros_fp']],
                          key=lambda x: -x['ros_fp'])

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
