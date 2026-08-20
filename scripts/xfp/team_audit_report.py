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
from plv_clone.projections import PROJECTIONS

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

from plv_clone.league_config import MY_TEAM_NAME


# Name join key — OWNER: plv_clone.utils.name_match.join_key (order-independent,
# so "Fried, Max" == "Max Fried"). NEVER re-derive locally: 127 local copies
# drifted apart and mis-keyed Ryan O'Hearn's curly apostrophe (2026-07-28).
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


def collect_player_info():
    """Build {name_key: {dict of every signal we have}}."""
    info = {}
    rh = PROJECTIONS.rh3()
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

    rp = PROJECTIONS.rp3()
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
        rh_names = PROJECTIONS.rh3()[['batter', 'player_name']]
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
        rh_names = PROJECTIONS.rh3()[['batter', 'player_name']]
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
    from plv_clone.league_state import LeagueState
    from scripts.xfp.opponent_lineup_overlap import (
        SLOT_FILL_ORDER, SLOT_DISPLAY_GROUP, DISPLAY_ORDER,
        SP_REMAINING_STARTS, HEALTHY_SP_STARTS_PER_WEEK,
        load_projections, fill_slots, build_team_players)

    h_lookup, p_lookup = load_projections()
    info_lookup = collect_player_info()

    ls = LeagueState()
    league = ls._get_league()
    my_team = next(t for t in league.teams if t.team_name == MY_TEAM_NAME)

    # Capture per-player IL/active status from live ESPN
    espn_status = {}
    for p in my_team.roster:
        espn_status[_norm(p.name)] = {
            'name': p.name,
            'injury_status': getattr(p, 'injuryStatus', 'ACTIVE'),
            'injured': bool(getattr(p, 'injured', False)),
            'lineup_slot': getattr(p, 'lineupSlot', '?'),
            'position': getattr(p, 'position', '?'),
            'eligible_slots': list(getattr(p, 'eligibleSlots', []) or []),
        }

    print(f'\nLIGERS AUDIT — {date.today()}')
    print('=' * 78)
    print(f'Record: {my_team.wins}-{my_team.losses}  Standing: #{my_team.standing}')
    print(f'Roster size: {len(my_team.roster)}')
    print()

    # Slot fill — exclude IL'd players from the optimal starting lineup
    team_players = build_team_players(my_team, h_lookup, p_lookup)
    # Tag IL status from ESPN
    for tp in team_players:
        nk = _norm(tp['name'])
        st = espn_status.get(nk, {})
        tp['injured'] = st.get('injured', False)
        tp['injury_status'] = st.get('injury_status', 'ACTIVE')
        tp['lineup_slot'] = st.get('lineup_slot', '?')
    active_team_players = [p for p in team_players if not p['injured']]
    slot_assignment, bench = fill_slots(active_team_players)
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

    # Bench (active, not IL'd)
    print('\nACTIVE BENCH (would-be starters but model has higher-value alternatives):')
    if bench:
        for p in bench:
            nk = _norm(p['name'])
            ino = info_lookup.get(nk, {})
            print(f'  {p["name"]:<28s}  RoS={p["value"]:.1f}  signal={ino.get("signal", "—")}')
    else:
        print('  (none — full starter usage)')

    # IL — separated out
    il_players = [p for p in team_players if p['injured']]
    print('\nIL / INJURED (do not drop — coming back):')
    if il_players:
        for p in il_players:
            nk = _norm(p['name'])
            ino = info_lookup.get(nk, {})
            inj_label = {'SEVEN_DAY_DL': '7-day IL',
                         'FIFTEEN_DAY_DL': '15-day IL',
                         'SIXTY_DAY_DL': '60-day IL',
                         'DAY_TO_DAY': 'day-to-day',
                         'OUT': 'out'}.get(p['injury_status'], p['injury_status'])
            print(f'  {p["name"]:<28s}  status={inj_label:<12s}  '
                  f'projection (if healthy)={ino.get("ros_fp", p["value"]):.1f}  '
                  f'src={ino.get("signal", "—")}')
    else:
        print('  (none)')

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

    # Drop candidates: low projection bench players, ACTIVE only (no IL)
    print('\nDROP CANDIDATES (ACTIVE bench players ranked by lowest model value — IL excluded):')
    drop_candidates = []
    for p in bench:
        nk = _norm(p['name'])
        ino = info_lookup.get(nk, {})
        drop_candidates.append({
            'name': p['name'],
            'role': 'pitcher' if p['is_pitcher'] else 'hitter',
            'ros_value': p['value'],
            'signal': ino.get('signal', '—'),
            'repl_delta': ino.get('replacement_delta', 0),
        })
    drop_candidates.sort(key=lambda x: x['ros_value'])
    for d in drop_candidates[:5]:
        print(f'  {d["name"]:<28s}  role={d["role"]:<8s}  RoS={d["ros_value"]:>6.1f}  '
              f'signal={d["signal"]}  repl_delta={d["repl_delta"]:+.3f}')

    # Pull ESPN free-agent roster-% — key by (norm_name, team) to disambiguate
    # name collisions (e.g., Max Muncy LAD vs Max Muncy OAK).
    def _team_norm(t):
        t = str(t or '').upper().strip()
        # Athletics moved from Oakland — ESPN uses 'Oak'/'OAK', our rh3 uses 'ATH'
        if t in ('OAK',): return 'ATH'
        return t
    fa_pct_owned = {}
    try:
        fa_lst = league.free_agents(size=2000)  # item 11: was size=500 (Sheehan-bug truncation)
        for fa in fa_lst:
            key = (_norm(fa.name), _team_norm(getattr(fa, 'proTeam', '')))
            fa_pct_owned[key] = float(getattr(fa, 'percent_owned', 0) or 0)
    except Exception as exc:
        print(f'  (could not fetch ESPN FA pool for roster%: {exc})')

    # Top FREE-AGENT pickups available (true FAs only, ranked by RoS value)
    print('\nTOP AVAILABLE HITTER FAs (model RoS, ranked):')
    print(f'{"PLAYER":<25s} {"POS":<5s} {"TEAM":<5s} {"%OWN":>6s} {"RoS":>7s} {"fp/PA":>7s} {"SIG":>5s}')
    rh = PROJECTIONS.rh3()
    # Build owned set across whole league
    owned = set()
    for t in league.teams:
        for p in t.roster:
            owned.add(_norm(p.name))
    rh['nk'] = rh['player_name'].map(_norm)
    fa_hitters = rh[~rh['nk'].isin(owned)].copy()
    fa_hitters = fa_hitters.dropna(subset=['expected_total_fp_remaining'])
    fa_hitters = fa_hitters.sort_values('expected_total_fp_remaining', ascending=False)
    for _, r in fa_hitters.head(15).iterrows():
        key = (r['nk'], _team_norm(r.get('team', '')))
        pct = fa_pct_owned.get(key)
        pct_s = f'{pct:.0f}%' if isinstance(pct, (int, float)) else '?'
        print(f'  {r["player_name"]:<25s} {r.get("primary_position", "?"):<5s} '
              f'{r.get("team", "?"):<5s} {pct_s:>6s} '
              f'{r.get("expected_total_fp_remaining", 0):>7.1f} '
              f'{r.get("xfp_rh3_per_pa", 0):>7.3f}  '
              f'{r.get("signal", "—")}')

    # Top FA pitchers too — in case any are sneaky
    print('\nTOP AVAILABLE PITCHER FAs (model RoS, ranked):')
    print(f'{"PLAYER":<25s} {"%OWN":>6s} {"fp/start":>8s} {"RoS":>7s} {"SRC":<12s} {"SIG":>5s}')
    rp = PROJECTIONS.rp3()
    rp['nk'] = rp['player_name'].map(_norm)
    fa_pit = rp[~rp['nk'].isin(owned)].copy()
    fa_pit['ros_proxy'] = fa_pit['xfp_rp3_per_start'].fillna(0) * SP_REMAINING_STARTS
    fa_pit = fa_pit.sort_values('ros_proxy', ascending=False)
    for _, r in fa_pit.head(10).iterrows():
        # Pitcher's rp3 might not have a team col; lookup just by name
        # (pitcher name collisions much rarer than hitters)
        candidates = [v for k, v in fa_pct_owned.items() if k[0] == r['nk']]
        pct = candidates[0] if candidates else None
        pct_s = f'{pct:.0f}%' if isinstance(pct, (int, float)) else '?'
        src = r.get('prior_source', 'rp3_model')
        print(f'  {r["player_name"]:<25s} {pct_s:>6s} '
              f'{r.get("xfp_rp3_per_start", 0):>8.2f}  '
              f'{r["ros_proxy"]:>7.1f} {src:<12s} '
              f'{r.get("signal", "—")}')

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
