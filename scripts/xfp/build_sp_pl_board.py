"""build_sp_pl_board — the master SP decision board (engine for the /sp-pl-board skill).

Cross-references the FULL Pitcher List Top 100 (The List) against my roster + the FA pool,
and for every PL-ranked pitcher who is MINE or FA emits one row with EVERY column:
  identity      : new_pl, old_pl, move, owner(MINE/FA), player
  our models    : rp3 (validated rank), verdict (triangulate), xFP (blended)
  recent form   : L1/L3/L5/L8/season FP per start  (OUR calc from MLB box scores, = ESPN scoring)
  reliability   : boom% (>=17) / bust% (<5) / net   (the reliable-boomer lens)
  HR profile    : HR/9 2026 vs CAREER               (running-hot vs structural)
  driver        : K%
  context       : velo/decline flags
  Nick          : sentiment — chronologically distilled from The List + Streamer + Roundup blurbs

FP PROVENANCE (verified): per-start FP is computed BY US from MLB Stats API box lines via the
BrownU formula K + IP*3.3 - H - 2*ER - BB - HBP (refresh_boxscores.py). It is NOT pulled from
ESPN (ESPN's API doesn't expose applied totals); it equals ESPN scoring by construction and
recomputes to the stored value with max |diff| 0.0000 across all starts.

Inputs (skill regenerates these each run):
  data/research/pl_cache/pl_top100_<date>.json                  — {"ranks": {Name: rank}}
  data/research/triangulate_universe/nick_sentiment_<date>.json — {"sentiment": {norm_name: str}}
  data/research/triangulate_universe/results_<date>.csv         — triangulate batch (rp3/verdict/old PL)
Usage: python scripts/xfp/build_sp_pl_board.py --date 2026-06-30
"""
import sys, os, json, argparse, unicodedata
sys.path.insert(0, '.'); sys.path.insert(0, 'src')
import pandas as pd
import numpy as np
from pathlib import Path
from plv_clone.league_state import default_state


def get_all_teams():  # league_state migration 2026-07-04 (schema superset)
    return default_state().all_teams()
from lib.boom_bust import SP_BOOM, SP_BUST  # OWNER: boom/bust cutoffs (never re-type 17/5)

MY = 'New York Ligers'
C = Path('data/research/xfp_cache')
PA = {'single','double','triple','home_run','strikeout','strikeout_double_play','walk','intent_walk',
      'hit_by_pitch','field_out','force_out','grounded_into_double_play','double_play','triple_play',
      'fielders_choice','fielders_choice_out','field_error','sac_fly','sac_fly_double_play','sac_bunt','catcher_interf'}


def _nm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    return ' '.join(s.lower().replace('.', '').replace(',', '').split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default='2026-06-30')
    a = ap.parse_args()
    d = a.date
    UNI = 'data/research/triangulate_universe'
    top = json.load(open(f'data/research/pl_cache/pl_top100_{d}.json', encoding='utf-8'))['ranks']
    NEWPL = {_nm(k): v for k, v in top.items()}
    sent = json.load(open(f'{UNI}/nick_sentiment_{d}.json', encoding='utf-8'))['sentiment']
    _res_cands = [Path(UNI) / f'results_{d}.csv', Path(UNI) / f'triangulate_nightly_{d}.csv']
    _res_path = next((p for p in _res_cands if p.exists()), _res_cands[-1])
    res = pd.read_csv(_res_path)
    res['k'] = res['player_name'].apply(_nm)
    R = {r['k']: r for _, r in res[res['bucket'] == 'SP'].iterrows()}

    teams = get_all_teams()
    owner = {_nm(n): t for n, t in zip(teams['player_name'], teams['team_name'])}
    inj = {_nm(n): str(s) for n, s in zip(teams['player_name'], teams['injury_status'])}

    bp = pd.read_parquet(C / 'boxscore_pitchers.parquet')
    sp = bp[bp['gs'] == 1].copy(); sp['game_date'] = pd.to_datetime(sp['game_date'])
    name2id = {_nm(n): i for n, i in zip(sp['player_name'], sp['mlbam_id'])}
    career = {}; cur = {}; kk = {}
    for y in range(2015, 2027):
        f = C / f'statcast_{y}.parquet'
        if not f.exists():
            continue
        dd = pd.read_parquet(f, columns=['pitcher', 'events']); dd = dd[dd['events'].isin(PA)]
        g = dd.groupby('pitcher').agg(bf=('events', 'size'), hr=('events', lambda s: (s == 'home_run').sum()),
                                      k=('events', lambda s: s.isin(['strikeout', 'strikeout_double_play']).sum()))
        for pid, r in g.iterrows():
            c = career.setdefault(pid, [0, 0]); c[0] += r['hr']; c[1] += r['bf']
            if y == 2026:
                cur[pid] = [r['hr'], r['bf']]; kk[pid] = round(r['k'] / r['bf'] * 100) if r['bf'] else None

    def hr9(dd, pid):
        v = dd.get(pid); return round(v[0] / v[1] * 38, 2) if (v and v[1] >= 100) else None

    def actuals(pid):
        g = sp[sp['mlbam_id'] == pid].sort_values('game_date'); f = g['fp_sp'].tolist()
        if not f:
            return {}
        m = lambda n: round(np.mean(f[-n:]), 1)
        # K-composition (rating_reimagine memo): the K-fed part of SP FP repeats
        # (r=.59) while the IP-fed part fades (r=-.14). k_share = K / (K + 3.3*IP)
        # is the fraction of the positive FP base that comes from strikeouts.
        # K-FED (high k_share) = stickier production; IP-FED = more likely to fade.
        # Display/context ONLY (Rule 13) — never moves the rp3 headline.
        k_tot = float(g['so'].sum()); ip_tot = float(g['ip'].sum())
        base = k_tot + 3.3 * ip_tot
        k_share = round(k_tot / base, 2) if base > 0 else None
        k_per_st = round(k_tot / len(g), 1) if len(g) else None
        k_src = None if k_share is None else ('K-FED' if k_share >= 0.30 else 'IP-FED')
        return dict(L1=round(f[-1], 1), L3=m(3), L5=m(5), L8=m(8), season=round(np.mean(f), 1), n=len(f),
                    boom_pct=round(100 * np.mean([x >= SP_BOOM for x in f])), bust_pct=round(100 * np.mean([x < SP_BUST for x in f])),
                    k_per_st=k_per_st, k_share=k_share, k_src=k_src)

    rows = []
    for k, npl in NEWPL.items():
        o = owner.get(k)
        who = 'MINE' if o == MY else ('FA' if o is None else None)
        if who is None:
            continue
        rr = R.get(k); pid = name2id.get(k); ac = actuals(pid) if pid else {}
        get = (lambda c: rr[c] if (rr is not None and pd.notna(rr.get(c))) else None) if rr is not None else (lambda c: None)
        opl = get('pl_rank'); fl = []
        for cc in ('velo_severity', 'decline_tier'):
            v = get(cc)
            if v is not None and str(v) not in ('STABLE', ''):
                fl.append(str(v))
        rows.append(dict(
            new_pl=npl, old_pl=int(opl) if opl is not None else None,
            move=(int(npl - opl) if opl is not None else None), owner=who,
            player=next((kk2 for kk2 in top if _nm(kk2) == k), k.title()),
            rp3=int(get('model_rank')) if get('model_rank') is not None else None,
            verdict=get('verdict_top') or get('verdict'),
            xfp=round(float(get('headline_proj')), 1) if get('headline_proj') is not None else None,
            **ac, net_boom=(ac.get('boom_pct', 0) - ac.get('bust_pct', 0)) if ac else None,
            hr9_2026=hr9(cur, pid), hr9_career=hr9(career, pid), k_pct=kk.get(pid),
            flags=' '.join(fl), il=(inj.get(k, 'ACTIVE') not in ('ACTIVE', 'nan', '')),
            nick_sentiment=sent.get(k, '—')))
    df = pd.DataFrame(rows).sort_values('new_pl')
    out = f'{UNI}/sp_pl_board_{d}.csv'
    df.to_csv(out, index=False)
    print(f"sp_pl_board: {len(df)} PL-ranked SPs that are MINE/FA "
          f"({(df.owner=='MINE').sum()} mine, {(df.owner=='FA').sum()} FA) -> {out}")

    # COMBINED display: fewer columns, ALL the data folded in (preferred format 2026-06-30).
    # The raw 21-col data is in the CSV; this view groups related fields into compact cells.
    def g(v, nd=2):
        return '—' if (v is None or (isinstance(v, float) and pd.isna(v))) else (
            str(int(v)) if (isinstance(v, (int, float)) and float(v).is_integer()) else f"{v:.{nd}f}")

    def pl_cell(r):
        npl = int(r['new_pl'])
        if pd.isna(r['old_pl']):
            return f"{npl} new"
        mv = int(r['move']); arr = '▲' if mv < 0 else ('▼' if mv > 0 else '·')
        return f"{npl} {arr}{abs(mv) if mv else ''} ({int(r['old_pl'])})"

    disp_rows = []
    for _, r in df.iterrows():
        if pd.isna(r.get('boom_pct')):
            bb = '—'
        else:
            net = f"{int(r['net_boom']):+d}" if not pd.isna(r['net_boom']) else '—'
            bb = f"{g(r['boom_pct'])}%/{g(r['bust_pct'])}% ({net})"
        disp_rows.append({
            'PL ▲▼ (old)': pl_cell(r),
            'Own': '⭐' if r['owner'] == 'MINE' else 'FA',
            'Pitcher': r['player'],
            'rp3·verdict·xFP': ('—' if pd.isna(r['rp3']) else
                                f"#{int(r['rp3'])} {r['verdict'] if (isinstance(r['verdict'], str)) else '—'} {g(r['xfp'], 1)}"),
            'L1/L3/L5/L8/Sea': '/'.join(g(r[c], 1) for c in ('L1', 'L3', 'L5', 'L8', 'season')),
            'boom%/bust%(net)': bb,
            'HR 26/car': f"{g(r['hr9_2026'])}/{g(r['hr9_career'])}",
            'K%': g(r['k_pct']),
            # K-composition: K/start + K-FED/IP-FED source (K-fed FP repeats
            # r=.59, IP-fed fades -.14 — rating_reimagine memo; context only).
            'K/st (src)': ('—' if pd.isna(r.get('k_per_st')) else
                           f"{g(r['k_per_st'], 1)} {r['k_src']}" if isinstance(r.get('k_src'), str)
                           else g(r['k_per_st'], 1)),
            'flags': r['flags'] or '',
            'Nick sentiment': r['nick_sentiment'],
        })
    disp = pd.DataFrame(disp_rows)
    with pd.option_context('display.max_rows', None, 'display.width', 400, 'display.max_colwidth', 90):
        print(disp.to_string(index=False))
    cols = list(disp.columns)
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    for _, r in disp.iterrows():
        lines.append('| ' + ' | '.join(str(r[c]) for c in cols) + ' |')
    open(f'{UNI}/sp_pl_board_{d}.md', 'w', encoding='utf-8').write('\n'.join(lines))
    print(f"\ncombined-column markdown -> {UNI}/sp_pl_board_{d}.md "
          f"({len(cols)} columns, ALL data folded in; raw 21-col data in the .csv)")


if __name__ == '__main__':
    main()
