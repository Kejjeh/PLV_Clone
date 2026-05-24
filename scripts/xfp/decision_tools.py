"""decision_tools.py — fantasy decision support tools.

Subcommands:
  roster        — Roster projection: total RoS FP for your starters + bench
  swap          — Trade/swap analyzer: net FP swing for hypothetical drop+add
  spqueue       — SP queue: rank SPs by next 2 starts xFP
  startsit      — Start/sit recommendations for the upcoming week

All read from the dashboard payload (XFP_HITTERS, XFP_RELIEVERS,
XFP_PROJECTIONS, XFP_MY_TEAM) plus league_config.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from league_config import (HITTER_REPLACEMENT_RANK, SP_REPLACEMENT_RANK,
                            RP_REPLACEMENT_RANK, LEAGUE_SIZE)


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


def parse_dashboard():
    html = (ROOT / 'data/outputs/xfp_dashboard.html').read_text(encoding='utf-8')
    pitchers  = json.loads(re.search(r'window\.XFP_PROJECTIONS\s*=\s*(\[.*?\]);', html, re.S).group(1))
    hitters   = json.loads(re.search(r'window\.XFP_HITTERS\s*=\s*(\[.*?\]);', html, re.S).group(1))
    rel_match = re.search(r'window\.XFP_RELIEVERS\s*=\s*(\[.*?\]);', html, re.S)
    relievers = json.loads(rel_match.group(1)) if rel_match else []
    team      = json.loads(re.search(r'window\.XFP_MY_TEAM\s*=\s*(\{.*?\});', html, re.S).group(1))
    return pitchers, hitters, relievers, team


def get_free_agents_with_model(pitchers, hitters, relievers):
    """Pull ESPN FAs and join to model records by name."""
    from plv_clone.league_state import LeagueState
    fa = LeagueState().available_fa()
    p_by = {name_key(p['name']): p for p in pitchers}
    h_by = {name_key(h['name']): h for h in hitters}
    r_by = {name_key(r['name']): r for r in relievers}
    fa_p, fa_h, fa_r = [], [], []
    for _, row in fa.iterrows():
        is_p = row['position'] in ('SP','RP','P')
        if is_p:
            sp_rec = lookup(row['player_name'], p_by)
            rp_rec = lookup(row['player_name'], r_by)
            if sp_rec and sp_rec.get('rosTotalFp') is not None:
                fa_p.append({**sp_rec, 'percent_owned': row['percent_owned'], 'fa_position': row['position']})
            if rp_rec and rp_rec.get('rpRoSFp') is not None:
                fa_r.append({**rp_rec, 'percent_owned': row['percent_owned'], 'fa_position': row['position']})
        else:
            h_rec = lookup(row['player_name'], h_by)
            if h_rec and h_rec.get('expTotalFp') is not None:
                fa_h.append({**h_rec, 'percent_owned': row['percent_owned'], 'fa_position': row['position']})
    return fa_p, fa_h, fa_r


def canon_pos(p):
    if not p: return 'UTIL'
    p = p.upper()
    if any(x in p for x in ['LF','CF','RF','OF']): return 'OF'
    for x in ['C','1B','2B','SS','3B','DH']:
        if x in p: return x
    return 'UTIL'


# ─── Roster projection ──────────────────────────────────────────────────────

def cmd_roster(args):
    """Sum your starters' total projected FP."""
    pitchers, hitters, relievers, team = parse_dashboard()
    print(f'═══ ROSTER PROJECTION — {team["teamName"]} ═══\n')

    # Hitters
    mine_h = sorted([h for h in hitters if h.get('roster')=='mine'],
                    key=lambda x: -(x.get('expTotalFp') or 0))
    h_total = sum((h.get('expTotalFp') or 0) for h in mine_h)
    h_repl_total = 0
    for h in mine_h:
        pos = canon_pos(h.get('pos'))
        h_repl_total += (h.get('replTotal') or 0)
    print('--- HITTERS (proj total FP rest of season) ---')
    print(f'{"Name":<24} {"Pos":<5} {"ProjFP":<8} {"vs Repl":<8}')
    print('-'*55)
    for h in mine_h:
        print(f'{h["name"]:<24} {(h.get("pos") or "—"):<5} '
              f'{(str(h.get("expTotalFp") or "—")):<8} '
              f'{(("+" if (h.get("replDeltaTotal") or 0) >= 0 else "") + str(h.get("replDeltaTotal") or "—")):<8}')
    print(f'{"TOTAL":<30} {h_total:<8.0f} {h_total - h_repl_total:+.0f} above replacement')

    # Pitchers (SPs + RPs combined)
    mine_p = [p for p in team['pitchers']]
    sp_recs = [p for p in pitchers if p.get('roster')=='mine']
    rp_recs_lookup = {r['mlbId']: r for r in relievers}
    p_total = 0; p_repl = 0
    print('\n--- PITCHERS (SPs + RPs) ---')
    print(f'{"Name":<24} {"Role":<6} {"ProjFP":<8} {"vs Repl":<8}')
    print('-'*55)
    sp_recs_sorted = sorted(sp_recs, key=lambda x: -(x.get('rosTotalFp') or 0))
    for p in sp_recs_sorted:
        proj = p.get('rosTotalFp') or 0
        vs_repl = p.get('rosReplDeltaTotal') or 0
        p_total += proj
        p_repl += proj - vs_repl
        print(f'{p["name"]:<24} {"SP":<6} {(str(p.get("rosTotalFp") or "—")):<8} '
              f'{(("+" if vs_repl >= 0 else "") + str(vs_repl)):<8}')
    for raw in mine_p:
        if raw['role'] != 'RP': continue
        rec = rp_recs_lookup.get(raw.get('mlbId'))
        if rec is None:
            print(f'{raw["name"]:<24} {"RP":<6} {"—":<8} {"(no model)":<8}')
            continue
        proj = rec.get('rpRoSFp') or 0
        vs_repl = rec.get('rpReplDelta') or 0
        p_total += proj; p_repl += proj - vs_repl
        print(f'{raw["name"]:<24} {"RP":<6} {proj:<8.0f} {(("+" if vs_repl >= 0 else "") + str(vs_repl)):<8}')
    print(f'{"TOTAL":<30} {p_total:<8.0f} {p_total - p_repl:+.0f} above replacement')

    print(f'\n═══ GRAND TOTAL: {h_total + p_total:.0f} FP rest of season ═══')
    print(f'    Above replacement: {h_total + p_total - h_repl_total - p_repl:+.0f} FP')


# ─── Swap analyzer ───────────────────────────────────────────────────────────

def cmd_swap(args):
    """Analyze a drop X / add Y swap — net FP swing rest of season."""
    pitchers, hitters, relievers, team = parse_dashboard()
    drop_name = args.drop
    add_name = args.add

    def find(name):
        # Search all three pools
        for pool, kind, key in [(hitters, 'hitter', 'expTotalFp'),
                                (pitchers, 'SP', 'rosTotalFp'),
                                (relievers, 'RP', 'rpRoSFp')]:
            by = {name_key(p['name']): p for p in pool}
            r = lookup(name, by)
            if r is not None and r.get(key) is not None:
                return r, kind, key
        return None, None, None

    drop_rec, drop_kind, drop_key = find(drop_name)
    add_rec, add_kind, add_key = find(add_name)
    if drop_rec is None:
        print(f'❌ Could not find DROP candidate: {drop_name}')
        return
    if add_rec is None:
        print(f'❌ Could not find ADD candidate: {add_name}')
        return

    print(f'═══ SWAP ANALYZER ═══\n')
    drop_proj = drop_rec.get(drop_key) or 0
    add_proj = add_rec.get(add_key) or 0
    swing = add_proj - drop_proj
    tag = 'STRONG' if abs(swing) > 50 else 'modest' if abs(swing) > 20 else 'marginal'
    print(f'  DROP {drop_rec["name"]:<24s} ({drop_kind})  — proj {drop_proj:.0f} FP rest of season')
    print(f'  ADD  {add_rec["name"]:<24s} ({add_kind})  — proj {add_proj:.0f} FP rest of season')
    print(f'  NET  {swing:+.0f} FP swing  [{tag}]')
    if drop_kind != add_kind:
        print(f'\n  ⚠️  Position mismatch: {drop_kind} vs {add_kind}.')
        print(f'      Make sure your roster construction allows this swap.')
    if drop_kind == 'hitter' and add_kind == 'hitter':
        drop_pos = canon_pos(drop_rec.get('pos'))
        add_pos = canon_pos(add_rec.get('pos'))
        if drop_pos != add_pos:
            print(f'\n  Position note: dropping a {drop_pos}, adding a {add_pos}.')
            print(f'      Replacement at {drop_pos} is rank {HITTER_REPLACEMENT_RANK.get(drop_pos)}; '
                  f'at {add_pos} is rank {HITTER_REPLACEMENT_RANK.get(add_pos)}.')


# ─── SP queue ────────────────────────────────────────────────────────────────

def cmd_spqueue(args):
    """Rank all SPs (yours + FAs) by next 2 starts xFP, schedule-adjusted."""
    pitchers, hitters, relievers, team = parse_dashboard()
    fa_p, _, _ = get_free_agents_with_model(pitchers, hitters, relievers)
    mine_sp = [p for p in pitchers if p.get('roster')=='mine']
    by_id_mine = {p['mlbId']: p for p in mine_sp}

    # Combine: my SPs + FA SPs, score by xfpRoSSched (or xfpRoS as fallback)
    all_sp = []
    for p in mine_sp:
        all_sp.append({**p, 'source': 'mine'})
    for p in fa_p:
        if p['mlbId'] in by_id_mine: continue
        all_sp.append({**p, 'source': 'FA'})

    # Score: xfpRoSSched gives you per-start projection accounting for next opponent.
    # Multiply by 2 starts (typical week) for a "next-2-starts" comparison.
    for p in all_sp:
        per = p.get('xfpRoSSched') or p.get('xfpRoS') or 0
        p['_score'] = per * 2

    all_sp.sort(key=lambda x: -x['_score'])
    print(f'═══ SP QUEUE — ranked by next 2 starts (schedule-adjusted) ═══\n')
    print(f'{"Rk":<3} {"Pitcher":<24} {"Src":<5} {"%Own":<6} {"Next2":<7} {"NextOpp":<6} {"L21Δ":<6} {"Sig":<5}')
    print('-'*70)
    for i, p in enumerate(all_sp[:30], 1):
        own = p.get('percent_owned')
        own_str = f'{own:.0f}%' if own is not None else '—'
        next_opp = p.get('nextOpp') or '—'
        gap = p.get('recencyGap')
        gap_str = f'{gap:+.1f}' if gap is not None else '—'
        sig = (p.get('signal') or 'hold').upper()
        src_tag = '★' if p['source'] == 'mine' else 'FA'
        print(f'{i:<3} {p["name"]:<24} {src_tag:<5} {own_str:<6} '
              f'{p["_score"]:<7.1f} {next_opp:<6} {gap_str:<6} {sig:<5}')


# ─── Start/sit calc ──────────────────────────────────────────────────────────

def cmd_startsit(args):
    """For the upcoming week, optimal starting hitters lineup from your roster."""
    pitchers, hitters, relievers, team = parse_dashboard()
    mine_h = [h for h in hitters if h.get('roster')=='mine']
    if not mine_h:
        print('No hitters on roster found.'); return

    # Score each hitter by per-game RoS xFP (rate × 3.5 PA/game)
    for h in mine_h:
        ros_pa = h.get('xfpRoSPerPa') or 0
        h['_per_game'] = ros_pa * 3.5

    # 8-team starting lineup slots: C, 1B, 2B, 3B, SS, MI, CI, UTIL, OF×5
    SLOTS = [
        ('C',    {'C'}),
        ('1B',   {'1B'}),
        ('2B',   {'2B'}),
        ('3B',   {'3B'}),
        ('SS',   {'SS'}),
        ('MI',   {'2B','SS'}),
        ('CI',   {'1B','3B'}),
        ('OF1',  {'OF'}),
        ('OF2',  {'OF'}),
        ('OF3',  {'OF'}),
        ('OF4',  {'OF'}),
        ('OF5',  {'OF'}),
        ('UTIL', {'C','1B','2B','3B','SS','OF','DH'}),
    ]

    # Greedy assignment: sort by per-game FP desc, fill slot if eligible & unfilled
    by_id = {h['mlbId']: h for h in mine_h}
    assigned = {}  # slot_label -> mlbId
    used = set()
    sorted_h = sorted(mine_h, key=lambda x: -x['_per_game'])
    for h in sorted_h:
        if h['mlbId'] in used: continue
        h_pos = canon_pos(h.get('pos'))
        h_fpos = set()
        if h.get('fpos'):
            for fp in h['fpos'].split(','):
                h_fpos.add(canon_pos(fp.strip()))
        h_fpos.add(h_pos)
        # Find first compatible empty slot
        for slot_label, eligible in SLOTS:
            if slot_label in assigned: continue
            if h_fpos & eligible:
                assigned[slot_label] = h['mlbId']
                used.add(h['mlbId'])
                break

    print(f'═══ START/SIT — optimal starting hitter lineup ═══\n')
    print(f'  (sorted by RoS xFP/game; greedy assignment to match league slots)\n')
    print(f'{"Slot":<6} {"Hitter":<24} {"Pos":<6} {"FP/G":<8} {"L21Δ":<7}')
    print('-'*55)
    total_fpg = 0
    for slot_label, eligible in SLOTS:
        mid = assigned.get(slot_label)
        if mid is None:
            print(f'{slot_label:<6} {"(empty)":<24} {"—":<6} {"—":<8} {"—":<7}')
            continue
        h = by_id[mid]
        fpg = h['_per_game']
        total_fpg += fpg
        gap = h.get('recencyGap')
        gap_str = f'{gap:+.3f}' if gap is not None else '—'
        print(f'{slot_label:<6} {h["name"]:<24} {(h.get("pos") or "—"):<6} '
              f'{fpg:<8.2f} {gap_str:<7}')
    bench = [h for h in mine_h if h['mlbId'] not in used]
    print(f'\n--- Bench (lowest FP/G) ---')
    for h in sorted(bench, key=lambda x: -x['_per_game']):
        print(f'{"BE":<6} {h["name"]:<24} {(h.get("pos") or "—"):<6} {h["_per_game"]:<8.2f}')
    print(f'\n  TOTAL projected FP/game from starters: {total_fpg:.1f}')


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Fantasy decision tools')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_roster = sub.add_parser('roster', help='Roster total projection')
    p_roster.set_defaults(func=cmd_roster)

    p_swap = sub.add_parser('swap', help='Drop/Add net FP swing')
    p_swap.add_argument('--drop', required=True, help='Player to drop')
    p_swap.add_argument('--add',  required=True, help='Player to add')
    p_swap.set_defaults(func=cmd_swap)

    p_q = sub.add_parser('spqueue', help='SP queue (next 2 starts)')
    p_q.set_defaults(func=cmd_spqueue)

    p_ss = sub.add_parser('startsit', help='Start/sit lineup optimizer')
    p_ss.set_defaults(func=cmd_startsit)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
