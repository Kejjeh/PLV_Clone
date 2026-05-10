"""team_audit_report.py — produce a fresh Ligers audit from LIVE ESPN data.

For each player on the current roster, pull:
  - Position + eligibility
  - RoS projection (rh3/rp3)
  - Recent rolling form (last 21 days) where available
  - Signal (add/hold/drop)
  - Slump precedent if applicable
  - YTD totals from substrate
  - Career xwoba_residual (luck signal)
  - Age + career year

Plus team-level summary:
  - Greedy starting-lineup assignment using eligibleSlots
  - Total RoS value vs league average
  - Per-position assessment
  - Drop candidates (low signal, low projection)
  - Trade priority recommendations from overlap analyzer

Outputs:
  data/research/ligers_audit_{date}.md (markdown report)
  prints to console

Usage:
    python scripts/xfp/team_audit_report.py
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import sys
import unicodedata
import re
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

MY_TEAM_NAME = 'New York Ligers'


def _norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'[,]+', ' ', s)
    parts = re.findall(r'[a-z]+', s)
    return ''.join(sorted(parts))


def collect_player_info():
    """Build {name_key: {dict of every signal we have}}."""
    info = {}
    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    rh['nk'] = rh['player_name'].map(_norm)
    rh = rh.drop_duplicates('nk', keep='first').set_index('nk')
    for nk, r in rh.iterrows():
        info[nk] = {
            'name': r['player_name'], 'role': 'hitter',
            'pa_to': int(r.get('pa_to') or 0),
            'xfp_per_pa': float(r.get('xfp_rh3_per_pa') or 0),
            'xfp_per_game': float(r.get('xfp_rh3_per_game') or 0),
            'ros_fp': float(r.get('expected_total_fp_remaining') or 0),
            'signal': r.get('signal'),
            'replacement_delta': float(r.get('replacement_delta') or 0),
            'recency_form_gap': float(r.get('recency_form_gap') or 0)
                if 'recency_form_gap' in rh.columns else 0,
            'slump_pct_rank': r.get('slump_pct_rank'),
            'slump_bounce_pct': r.get('slump_bounce_pct'),
            'slump_next_rate': r.get('slump_next_rate'),
            'rank': int(r['rank']) if pd.notna(r.get('rank')) else None,
        }

    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv')
    rp['nk'] = rp['player_name'].map(_norm)
    rp = rp.drop_duplicates('nk', keep='first').set_index('nk')
    for nk, r in rp.iterrows():
        info[nk] = {
            'name': r['player_name'], 'role': 'pitcher',
            'gs_to': int(r.get('gs_to') or 0),
            'xfp_per_start': float(r.get('xfp_rp3_per_start') or 0),
            'ros_fp': float(r.get('xfp_rp3_per_start') or 0) * 18,
            'signal': r.get('signal'),
            'replacement_delta': float(r.get('replacement_delta') or 0),
            'recency_form_gap': float(r.get('recency_form_gap') or 0)
                if 'recency_form_gap' in rp.columns else 0,
            'next_opp_team': r.get('next_opp_team'),
            'is_on_il_at_split': int(r.get('is_on_il_at_split') or 0),
            'rank': int(r['rank']) if pd.notna(r.get('rank')) else None,
        }

    # Add xwoba residual + age
    try:
        xw = pd.read_csv(OUT / 'hitter_xwoba_residual.csv')
        rh_names = pd.read_csv(OUT / 'xfp_rh3_projections.csv')[['batter', 'player_name']]
        xw = xw.merge(rh_names, on='batter', how='left')
        for _, r in xw.iterrows():
            nk = _norm(r['player_name'])
            if nk in info:
                info[nk]['xwoba_residual_career'] = float(r.get('xwoba_residual_career') or 0)
                info[nk]['ev90_career'] = float(r.get('ev90_career') or 0)
    except Exception:
        pass

    try:
        age = pd.read_csv(OUT / 'hitter_age_career.csv')
        age = age[age['year'] == 2026]
        rh_names = pd.read_csv(OUT / 'xfp_rh3_projections.csv')[['batter', 'player_name']]
        age = age.merge(rh_names, on='batter', how='left')
        for _, r in age.iterrows():
            nk = _norm(r['player_name'])
            if nk in info:
                info[nk]['age'] = int(r['age'])
                info[nk]['career_year'] = int(r['career_year'])
    except Exception:
        pass

    return info


def main():
    from app import espn_connector as ec
    from scripts.xfp.opponent_lineup_overlap import (
        SLOT_FILL_ORDER, SLOT_DISPLAY_GROUP, DISPLAY_ORDER,
        SP_REMAINING_STARTS, load_projections, fill_slots, build_team_players)

    h_lookup, p_lookup = load_projections()
    info_lookup = collect_player_info()

    league = ec._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)

    print(f'\nLIGERS AUDIT — {date.today()}')
    print('=' * 78)
    print(f'Record: {my_team.wins}-{my_team.losses}  Standing: #{my_team.standing}')
    print(f'Roster size: {len(my_team.roster)}')
    print()

    # Slot fill
    team_players = build_team_players(my_team, h_lookup, p_lookup)
    slot_assignment, bench = fill_slots(team_players)
    total_value = sum(s['value'] for s in slot_assignment.values() if s['name'])

    print('STARTING LINEUP (greedy-optimal via eligibleSlots):')
    print(f'{"SLOT":<6s} {"PLAYER":<28s} {"RoS FP":>8s} {"YTD":>6s} {"SIG":>5s} {"RANK":>5s} {"NOTES"}')
    for slot, sa in slot_assignment.items():
        if not sa['name']:
            print(f'{slot:<6s} (empty)')
            continue
        nk = _norm(sa['name'])
        ino = info_lookup.get(nk, {})
        rank = ino.get('rank', '—')
        signal = ino.get('signal', '—') or '—'
        recency = ino.get('recency_form_gap', 0)
        notes = []
        if abs(recency) >= 0.10:
            notes.append(f'recency {recency:+.2f}')
        if ino.get('slump_pct_rank') is not None and ino.get('slump_pct_rank', 100) <= 25:
            notes.append(f'SLUMP pct={ino["slump_pct_rank"]:.0f}')
        if ino.get('is_on_il_at_split'):
            notes.append('IL')
        notes_s = ', '.join(notes) if notes else ''
        ytd = ino.get('pa_to', ino.get('gs_to', 0))
        print(f'{slot:<6s} {sa["name"]:<28s} {sa["value"]:>8.1f} {ytd:>6} {str(signal)[:4]:>5s} {str(rank):>5s} {notes_s}')

    print(f'\nTotal starting-lineup RoS FP value: {total_value:.1f}')

    # Bench
    print('\nBENCH (not in starting lineup):')
    if bench:
        for p in bench:
            nk = _norm(p['name'])
            ino = info_lookup.get(nk, {})
            print(f'  {p["name"]:<28s}  value={p["value"]:.1f}  signal={ino.get("signal", "—")}')
    else:
        print('  (none — full starter usage)')

    # Position-by-position assessment vs opponent_lineup_overlap.json
    overlap_path = OUT / 'opponent_lineup_overlap.json'
    if overlap_path.exists():
        import json
        ov = json.loads(overlap_path.read_text(encoding='utf-8'))
        # Aggregate edges by display group
        edge_by_group = {g: 0.0 for g in DISPLAY_ORDER}
        for opp in ov.get('opponents', []):
            for g, pp in opp.get('per_position', {}).items():
                edge_by_group[g] = edge_by_group.get(g, 0) + pp.get('edge', 0)
        avg_edge = {g: v / max(len(ov['opponents']), 1) for g, v in edge_by_group.items()}
        print('\nPOSITIONAL STRENGTH MAP (avg edge vs each opponent at this slot group):')
        print(f'{"GROUP":<14s} {"MY VALUE":>10s} {"AVG EDGE":>10s} {"READ"}')
        for g in DISPLAY_ORDER:
            mv = ov['my_position_values'].get(g, {})
            edge = avg_edge.get(g, 0)
            read = 'STRENGTH' if edge > 30 else ('WEAKNESS' if edge < -30 else 'avg')
            print(f'{g:<14s} {mv.get("value", 0):>10.1f} {edge:>+10.1f}  {read}')

    # Drop candidates: low signal + low projection
    print('\nDROP CANDIDATES (signal=drop OR low replacement_delta):')
    drops = []
    for p in my_team.roster:
        nk = _norm(p.name)
        ino = info_lookup.get(nk, {})
        sig = ino.get('signal')
        rd = ino.get('replacement_delta', 0)
        if sig == 'drop' or rd <= -0.02:
            drops.append((p.name, sig, rd))
    drops.sort(key=lambda x: x[2])
    for nm, sig, rd in drops[:5]:
        print(f'  {nm:<28s}  signal={sig}  repl_delta={rd:+.3f}')

    # Trade priorities from smart_trade_finder
    finder_path = OUT / 'smart_trade_finder.json'
    if finder_path.exists():
        import json
        ftf = json.loads(finder_path.read_text(encoding='utf-8'))
        top = ftf.get('global_top', [])[:8]
        print('\nTOP TRADE IDEAS (from smart_trade_finder):')
        for t in top:
            print(f'  vs {t["opp_name"]:<25s}: give {t["give"]:<25s} → get {t["get"]:<25s}  '
                  f'+{t["edge_gain_ros"]:.1f} RoS FP  (fair gap {t["fair_ratio"]*100:.0f}%)')

    # Save markdown
    md_lines = [f'# Ligers Audit — {date.today()}', '',
                f'Record: {my_team.wins}-{my_team.losses} (Standing #{my_team.standing})',
                f'Roster: {len(my_team.roster)} players',
                f'Total starting-lineup RoS value: **{total_value:.1f} FP**', '',
                '## Starting lineup', '',
                '| Slot | Player | RoS FP | Signal | Notes |',
                '|------|--------|--------|--------|-------|']
    for slot, sa in slot_assignment.items():
        if not sa['name']:
            md_lines.append(f'| {slot} | (empty) | — | — | — |')
            continue
        nk = _norm(sa['name'])
        ino = info_lookup.get(nk, {})
        notes = []
        if abs(ino.get('recency_form_gap', 0)) >= 0.10:
            notes.append(f'recent form {ino["recency_form_gap"]:+.2f}')
        if ino.get('slump_pct_rank', 100) <= 25:
            notes.append(f'SLUMP pct={int(ino["slump_pct_rank"])}')
        if ino.get('is_on_il_at_split'):
            notes.append('IL')
        md_lines.append(f'| {slot} | {sa["name"]} | {sa["value"]:.1f} | {ino.get("signal", "—") or "—"} | {", ".join(notes) or "—"} |')

    if bench:
        md_lines.append('\n## Bench\n')
        for p in bench:
            nk = _norm(p['name'])
            ino = info_lookup.get(nk, {})
            md_lines.append(f'- {p["name"]} — value {p["value"]:.1f}, signal={ino.get("signal", "—") or "—"}')

    md_path = RES / f'ligers_audit_{date.today()}.md'
    md_path.write_text('\n'.join(md_lines), encoding='utf-8')
    print(f'\nwrote {md_path}')


if __name__ == '__main__':
    main()
