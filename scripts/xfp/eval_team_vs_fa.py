"""eval_team_vs_fa.py — your roster vs actual ESPN free agents in your league.

Pulls live free agents from the ESPN API (via app/espn_connector.py),
joins to RH3/RP3 projections, and prints:
  - your roster ranked by RoS xFP at each position
  - top FAs at each position with model coverage
  - drop/add pairings (your weakest at a position vs best FA at that position)
"""
from __future__ import annotations
import os, re, json, sys
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')

sys.path.insert(0, str(ROOT / 'app'))
from espn_connector import get_free_agents  # noqa


# ── Name matching (mirrors scripts/xfp/build_v11_dashboard_v2.py) ────────────
import unicodedata

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s)
                   if not unicodedata.combining(c))

def _norm(s: str) -> str:
    return re.sub(r'[^a-z]+', '', _strip_accents(s or '').lower())

def name_key(name: str) -> tuple[str, str]:
    """Normalize 'Last, First' or 'First Last' to (last, first)."""
    if ',' in name:
        last, first = name.split(',', 1)
    else:
        parts = name.strip().split()
        if len(parts) < 2:
            return (_norm(name), '')
        last, first = parts[-1], ' '.join(parts[:-1])
    return (_norm(last), _norm(first))

def lookup(plv_name: str, by_key: dict):
    last, first = name_key(plv_name)
    rec = by_key.get((last, first))
    if rec is not None:
        return rec
    # Fallback: unique last-name match with 3-char first-name prefix
    candidates = [(k, v) for k, v in by_key.items() if k[0] == last]
    if len(candidates) == 1:
        if first[:3] == candidates[0][0][1][:3]:
            return candidates[0][1]
    return None


def canon_pos(p: str | None) -> str:
    if not p: return 'UTIL'
    p = p.upper()
    if any(x in p for x in ['LF','CF','RF','OF']): return 'OF'
    for x in ['C','1B','2B','SS','3B','DH']:
        if x in p: return x
    return 'UTIL'


def parse_dashboard():
    html = (ROOT / 'data/outputs/xfp_dashboard.html').read_text(encoding='utf-8')
    pitchers = json.loads(re.search(r'window\.XFP_PROJECTIONS\s*=\s*(\[.*?\]);', html, re.S).group(1))
    hitters  = json.loads(re.search(r'window\.XFP_HITTERS\s*=\s*(\[.*?\]);', html, re.S).group(1))
    relievers_match = re.search(r'window\.XFP_RELIEVERS\s*=\s*(\[.*?\]);', html, re.S)
    relievers = json.loads(relievers_match.group(1)) if relievers_match else []
    team     = json.loads(re.search(r'window\.XFP_MY_TEAM\s*=\s*(\{.*?\});', html, re.S).group(1))
    return pitchers, hitters, relievers, team


def fmt(v, dp=2):
    return f'{v:.{dp}f}' if v is not None else '—'

def fmt_signed(v, dp=2):
    if v is None: return '—'
    return f'{v:+.{dp}f}'


def main():
    pitchers, hitters, relievers, team = parse_dashboard()
    print(f'═══ TEAM EVAL — {team["teamName"]} vs ESPN free agents ═══\n')

    # Pull free agents from ESPN
    print('Fetching ESPN free agents (size=2000)...')
    fa = get_free_agents(size=2000)
    print(f'  got {len(fa)} free agents\n')
    fa_pitchers = fa[fa['position'].isin(['SP','RP','P'])]
    fa_hitters = fa[~fa['position'].isin(['SP','RP','P'])]

    # Build name-keyed lookup for projections
    p_by_key = {name_key(p['name']): p for p in pitchers}
    h_by_key = {name_key(h['name']): h for h in hitters}

    # ─── PITCHERS ────────────────────────────────────────────────────────────
    mine_p = sorted([p for p in pitchers if p.get('roster')=='mine'],
                    key=lambda x: -(x.get('xfpRoS') or 0))
    print('─── MY PITCHERS ───────────────────────────────────────────────────────')
    print(f'{"Pos":<5} {"Name":<22} {"RoS":<7} {"P25-75":<11} {"Sched":<7} {"L21Δ":<6} {"Sig":<5} {"ΔRepl":<7}')
    print('─' * 78)
    for p in mine_p:
        pos = (p.get('espnPos') or '—')[:4]
        ros = p.get('xfpRoS')
        p25 = p.get('xfpRoSp25'); p75 = p.get('xfpRoSp75')
        ci = f'{p25:.1f}-{p75:.1f}' if p25 is not None else '—'
        print(f'{pos:<5} {p["name"]:<22} {fmt(ros):<7} {ci:<11} '
              f'{fmt(p.get("xfpRoSSched")):<7} {fmt_signed(p.get("recencyGap"),1):<6} '
              f'{(p.get("signal") or "hold").upper():<5} {fmt_signed(p.get("replDelta")):<7}')
    matched_ids = {p.get('mlbId') for p in mine_p}
    no_cov = [p for p in team['pitchers'] if p.get('mlbId') not in matched_ids]
    if no_cov:
        print(f'\n  No model coverage (RPs / partial-season SPs):')
        for p in no_cov:
            print(f'    {p["name"]:<22s} {p.get("espnPos","—"):<5s} ESPN proj/G={p.get("fpPerGame")}')

    # FA pitchers with model coverage
    fa_p_matched = []
    for _, row in fa_pitchers.iterrows():
        rec = lookup(row['player_name'], p_by_key)
        if rec and rec.get('xfpRoS') is not None:
            fa_p_matched.append({**rec, 'fa_position': row['position'],
                                 'percent_owned': row['percent_owned']})
    fa_p_matched.sort(key=lambda x: -x['xfpRoS'])

    print(f'\n─── TOP FREE-AGENT SPs ({len(fa_p_matched)} matched of {len(fa_pitchers)} ESPN FAs) ───')
    print(f'{"Name":<22} {"%Own":<5} {"RoS":<7} {"P25-75":<11} {"Sched":<7} {"L21Δ":<6} {"Sig":<5} {"ΔRepl":<7}')
    print('─' * 80)
    for p in fa_p_matched[:15]:
        p25 = p.get('xfpRoSp25'); p75 = p.get('xfpRoSp75')
        ci = f'{p25:.1f}-{p75:.1f}' if p25 is not None else '—'
        print(f'{p["name"]:<22} {p["percent_owned"]:<5.1f} {fmt(p.get("xfpRoS")):<7} {ci:<11} '
              f'{fmt(p.get("xfpRoSSched")):<7} {fmt_signed(p.get("recencyGap"),1):<6} '
              f'{(p.get("signal") or "hold").upper():<5} {fmt_signed(p.get("replDelta")):<7}')

    # Pitcher drop/add pairings.
    # Same logic as hitters: total FP > rate. Approximate remaining starts as
    # gs_to / weeks_played × weeks_remaining. Use 5 weeks played, 21 weeks
    # remaining (162-game season ≈ 26 weeks; today is 2026-05-06).
    WEEKS_PLAYED = 5; WEEKS_REMAIN = 21
    def proj_total_fp(p):
        gs_to = p.get('gsToDate')
        ros = p.get('xfpRoS')
        if gs_to is None or ros is None:
            return None
        starts_remaining = (gs_to / WEEKS_PLAYED) * WEEKS_REMAIN
        return ros * starts_remaining

    for p in mine_p:
        p['_projTotal'] = proj_total_fp(p)
    for p in fa_p_matched:
        p['_projTotal'] = proj_total_fp(p)

    print(f'\n─── PITCHER DROP/ADD PAIRINGS (optimized on TOTAL projected FP) ───')
    print(f'  Total FP = xfpRoS × projected starts remaining (= gs_to/{WEEKS_PLAYED}wk × {WEEKS_REMAIN}wk)')
    weakest = sorted([p for p in mine_p if p.get('_projTotal') is not None],
                     key=lambda x: x['_projTotal'])[:5]
    fa_sorted_total = sorted([p for p in fa_p_matched if p.get('_projTotal') is not None],
                             key=lambda x: -x['_projTotal'])
    p_moves = []
    for w in weakest:
        for a in fa_sorted_total:
            swing = a['_projTotal'] - w['_projTotal']
            if swing > 0:
                p_moves.append({'worst': w, 'best': a, 'swing': swing})
                break
    p_moves.sort(key=lambda x: -x['swing'])
    for m in p_moves[:5]:
        w, a = m['worst'], m['best']
        tag = 'STRONG' if m['swing'] > 30 else 'modest' if m['swing'] > 10 else 'marginal'
        print(f'  DROP {w["name"]:<22s} (proj {int(w["_projTotal"])} FP from {w["gsToDate"]} GS so far, {w["xfpRoS"]:.2f}/start)')
        print(f'  ADD  {a["name"]:<22s} (proj {int(a["_projTotal"])} FP from {a["gsToDate"]} GS so far, {a["xfpRoS"]:.2f}/start)')
        print(f'  NET  +{int(m["swing"])} FP rest of season  [{tag}]')
        print()

    # ─── RELIEVERS ───────────────────────────────────────────────────────────
    print('\n\n─── MY RELIEVERS ──────────────────────────────────────────────────────')
    print(f'{"Name":<22} {"PriorRole":<10} {"G":<4} {"SV":<4} {"HLD":<4} {"FP-now":<7} {"RoS":<7} {"P25-75":<13} {"Sig":<5} {"ΔRepl":<7}')
    print('─' * 90)
    rp_lookup = {r['mlbId']: r for r in relievers}
    my_rps = [p for p in team['pitchers'] if p['role']=='RP']
    my_covered_rps = []
    for rp in my_rps:
        rec = rp_lookup.get(rp.get('mlbId'))
        if rec is None:
            print(f'{rp["name"]:<22} {"—":<10} (no model coverage)')
            continue
        rec['_my_team_name'] = rp['name']
        my_covered_rps.append(rec)
        ci = f'{rec["rpRoSFpP25"]:.0f}-{rec["rpRoSFpP75"]:.0f}' if rec.get('rpRoSFpP25') is not None else '—'
        print(f'{rp["name"]:<22} {(rec.get("rpRolePrior") or "—"):<10} '
              f'{rec.get("gToDate","—"):<4} {rec.get("sv2026","—"):<4} {rec.get("hld2026","—"):<4} '
              f'{rec.get("fpActual","—"):<7} {rec.get("rpRoSFp","—"):<7} {ci:<13} '
              f'{(rec.get("rpSignal") or "hold").upper():<5} {fmt_signed(rec.get("rpReplDelta"),1):<7}')

    # FA relievers — match by name, since ESPN API returns FAs by name
    fa_rps = fa[fa['position'].isin(['RP','P'])].copy()
    rp_by_key = {name_key(r['name']): r for r in relievers}
    fa_rp_matched = []
    for _, row in fa_rps.iterrows():
        rec = lookup(row['player_name'], rp_by_key)
        if rec and rec.get('rpRoSFp') is not None:
            fa_rp_matched.append({**rec, 'percent_owned': row['percent_owned']})
    fa_rp_matched.sort(key=lambda x: -x['rpRoSFp'])

    print(f'\n─── TOP FREE-AGENT RELIEVERS ({len(fa_rp_matched)} matched of {len(fa_rps)} ESPN FAs) ───')
    print('  Closer-focused: prior-year role + SV count visible')
    print(f'  {"Name":<22} {"%Own":<5} {"PriorRole":<10} {"prSV":<5} {"FP-now":<7} {"RoS":<7} {"P25-75":<13} {"Sig":<5} {"ΔRepl":<7}')
    for rec in fa_rp_matched[:15]:
        ci = f'{rec["rpRoSFpP25"]:.0f}-{rec["rpRoSFpP75"]:.0f}' if rec.get('rpRoSFpP25') is not None else '—'
        print(f'  {rec["name"]:<22} {rec["percent_owned"]:<5.1f} '
              f'{(rec.get("rpRolePrior") or "—"):<10} '
              f'{rec.get("svPriorYr","—"):<5} {rec.get("fpActual","—"):<7} '
              f'{rec.get("rpRoSFp","—"):<7} {ci:<13} '
              f'{(rec.get("rpSignal") or "hold").upper():<5} '
              f'{fmt_signed(rec.get("rpReplDelta"),1):<7}')

    # RP drop/add pairings
    print(f'\n─── RP DROP/ADD PAIRINGS (your weakest covered RP vs best FA RP) ───')
    if my_covered_rps and fa_rp_matched:
        weakest = sorted([r for r in my_covered_rps if r.get('rpRoSFp') is not None],
                         key=lambda x: x['rpRoSFp'])[:3]
        rp_moves = []
        for w in weakest:
            for a in fa_rp_matched:
                # don't pair with someone already on the team
                if a['mlbId'] == w['mlbId']:
                    continue
                swing = a['rpRoSFp'] - w['rpRoSFp']
                if swing > 0:
                    rp_moves.append({'worst': w, 'best': a, 'swing': swing})
                    break
        rp_moves.sort(key=lambda x: -x['swing'])
        for m in rp_moves[:5]:
            w, a = m['worst'], m['best']
            tag = 'STRONG' if m['swing'] > 30 else 'modest' if m['swing'] > 10 else 'marginal'
            wname = w.get('_my_team_name') or w['name']
            print(f'  DROP {wname:<22s} (RoS {w["rpRoSFp"]:.0f} FP, {(w.get("rpRolePrior") or "—")})')
            print(f'  ADD  {a["name"]:<22s} (RoS {a["rpRoSFp"]:.0f} FP, {(a.get("rpRolePrior") or "—")}, {a["percent_owned"]:.0f}% owned)')
            print(f'  NET  +{int(m["swing"])} FP rest of season  [{tag}]')
            print()

    # ─── HITTERS ────────────────────────────────────────────────────────────
    mine_h = sorted([h for h in hitters if h.get('roster')=='mine'],
                    key=lambda x: -(x.get('xfpRoSPerPa') or 0))

    def pos_set(rec):
        f = rec.get('fpos') or rec.get('pos') or ''
        return {canon_pos(p) for p in f.split(',') if p}

    print('\n\n─── MY HITTERS ────────────────────────────────────────────────────────')
    print(f'{"Pos":<7} {"Name":<22} {"RoS/PA":<8} {"P25-75":<13} {"L21Δ":<8} {"Sig":<5} {"ΔRepl":<8} {"ProjFP":<6}')
    print('─' * 88)
    for h in mine_h:
        pos = (h.get('espnPos') or h.get('pos') or '—')[:6]
        ros = h.get('xfpRoSPerPa')
        p25 = h.get('xfpRoSp25'); p75 = h.get('xfpRoSp75')
        ci = f'{p25:.2f}-{p75:.2f}' if p25 is not None else '—'
        proj = h.get('expTotalFp')
        print(f'{pos:<7} {h["name"]:<22} {fmt(ros,3):<8} {ci:<13} '
              f'{fmt_signed(h.get("recencyGap"),3):<8} '
              f'{(h.get("signal") or "hold").upper():<5} '
              f'{fmt_signed(h.get("replDelta"),3):<8} '
              f'{(str(int(proj)) if proj is not None else "—"):<6}')

    # FA hitters with model coverage
    fa_h_matched = []
    for _, row in fa_hitters.iterrows():
        rec = lookup(row['player_name'], h_by_key)
        if rec and rec.get('xfpRoSPerPa') is not None:
            fa_h_matched.append({**rec, 'fa_position': row['position'],
                                 'percent_owned': row['percent_owned']})
    fa_h_matched.sort(key=lambda x: -x['xfpRoSPerPa'])
    print(f'\n─── TOP FREE-AGENT HITTERS ({len(fa_h_matched)} matched of {len(fa_hitters)} ESPN FAs) — top 5 per pos ───')

    by_pos = defaultdict(list)
    for h in fa_h_matched:
        for p in pos_set(h):
            by_pos[p].append(h)

    for pos in ['C','1B','2B','SS','3B','OF','DH']:
        cands = by_pos.get(pos, [])
        if not cands:
            continue
        print(f'\n  {pos}:')
        print(f'  {"Name":<22} {"%Own":<5} {"RoS/PA":<8} {"L21Δ":<8} {"Sig":<5} {"ΔRepl":<8} {"ProjFP":<6}')
        for h in cands[:5]:
            print(f'  {h["name"]:<22} {h["percent_owned"]:<5.1f} {fmt(h.get("xfpRoSPerPa"),3):<8} '
                  f'{fmt_signed(h.get("recencyGap"),3):<8} '
                  f'{(h.get("signal") or "hold").upper():<5} '
                  f'{fmt_signed(h.get("replDelta"),3):<8} '
                  f'{(str(int(h.get("expTotalFp"))) if h.get("expTotalFp") is not None else "—"):<6}')

    # Hitter drop/add pairings — optimize on TOTAL projected FP, not rate.
    # An add/drop doesn't swap playing time: you LOSE your player's full-season FP
    # contribution and GAIN the new player's. So Ballesteros' great rate is moot
    # if he only gets 285 PA at STL while Herrera plays 525 PA.
    print(f'\n─── HITTER DROP/ADD PAIRINGS (optimized on TOTAL projected FP, not rate) ───')
    print('  For each position: your weakest by total FP vs best non-roster total FP')
    moves = []
    for pos in ['C','1B','2B','SS','3B','OF','DH']:
        my_at_pos = sorted([h for h in mine_h if pos in pos_set(h)
                            and h.get('expTotalFp') is not None],
                           key=lambda x: x['expTotalFp'])
        fa_at_pos = sorted([h for h in by_pos.get(pos, [])
                            if h.get('expTotalFp') is not None],
                           key=lambda x: -x['expTotalFp'])
        if not my_at_pos or not fa_at_pos:
            continue
        worst = my_at_pos[0]
        best = fa_at_pos[0]
        swing_total = best['expTotalFp'] - worst['expTotalFp']
        swing_pa = best['xfpRoSPerPa'] - worst['xfpRoSPerPa']
        if swing_total <= 0:
            continue  # negative swap = your player is already better than top FA
        moves.append({
            'pos': pos, 'worst': worst, 'best': best,
            'swing_total': swing_total, 'swing_pa': swing_pa,
        })

    moves.sort(key=lambda x: -x['swing_total'])
    for m in moves:
        worst, best = m['worst'], m['best']
        tag = 'STRONG' if m['swing_total'] > 50 else 'modest' if m['swing_total'] > 20 else 'marginal'
        print(f'  {m["pos"]:<3}  DROP {worst["name"]:<22s} (proj {int(worst["expTotalFp"])} FP, {worst["xfpRoSPerPa"]:.3f}/PA)')
        print(f'       ADD  {best["name"]:<22s} (proj {int(best["expTotalFp"])} FP, {best["xfpRoSPerPa"]:.3f}/PA)')
        print(f'       NET  +{int(m["swing_total"])} FP rest of season  [{tag}]')

    # Top 5 highest-impact roster moves overall (across all positions)
    print(f'\n─── TOP 5 HIGHEST-IMPACT MOVES (sorted by total-FP swing) ───')
    for i, m in enumerate(moves[:5], 1):
        print(f'  {i}. [{m["pos"]}] {m["worst"]["name"]} → {m["best"]["name"]}: '
              f'+{int(m["swing_total"])} FP rest of season')


if __name__ == '__main__':
    main()
