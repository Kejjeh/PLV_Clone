"""build_hitter_pl_board — the PL-spine HITTER board (engine for /hitter-board --mode pl).

The hitter mirror of `build_sp_pl_board.py`: one row per Pitcher-List Top-150
hitter that is MINE or FA, sorted by PL rank, with ▲▼ movement vs the prior
edition. Everything else on the row is our own model + actuals + splits.

WHY THIS EXISTS. `/hitter-board --mode slate|level|replace` are all MODEL-spined
(sorted by baseline xFP / shrunk level / Δ-vs-drop-target) and treat PL as one
of 14 columns — the slate recipe is explicit that "PL Top 150 alone is NEVER" a
ranker. That is correct for a pickup board but leaves no surface answering "what
does PL think of my guys and the wire, one row each, and what moved". This is
that surface, and only that.

DELIBERATE ASYMMETRIES vs the SP board (do not treat as gaps to fill):
  - NO Nick-sentiment equivalent at parity. SP Roundup recaps essentially every
    starter each day; PL's Hitter Recap features ~5-8 noteworthy performances out
    of ~250 hitters who played. Coverage runs ~16% of rows and the column is
    sparse BY SOURCE DESIGN. Authors differ too: Top 150 is Scott Chu, recaps
    rotate (Amore / Stanzel / O'Brien / Clark / Havelock / Solow) — so the column
    is "PL sentiment [author]", never "Nick".
  - NO HR/9 structural lens (SP-specific). Replaced by the platoon xwOBA split,
    which is the hitter analogue of a structural-vs-luck read.

Inputs:
  data/research/pl_cache/pl_hitters_top150*.json               — {"ranks": {Name: rank}}
  data/research/triangulate_universe/pl_hitter_sentiment_*.json — {"sentiment": {norm: str}}
  data/research/triangulate_universe/triangulate_nightly_*.csv  — model/verdict/archetype
  data/research/xfp_cache/boxscore_hitters.parquet              — per-game FP actuals
  data/research/xfp_cache/statcast_2026.parquet                 — platoon xwOBA
Usage:
  python scripts/xfp/build_hitter_pl_board.py --date 2026-07-28 \
      --old-pl-json data/research/pl_cache/pl_hitters_top150_2026-07-15.json
"""
import sys, os, json, argparse, unicodedata
sys.path.insert(0, '.')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
from pathlib import Path
from plv_clone.league_state import default_state
from plv_clone.league_config import MY_TEAM_NAME
from plv_clone.utils.name_match import safe_name_key   # OWNER: never re-derive
from lib.boom_bust import H_BOOM            # OWNER: never re-type the 5/0 cutoffs
from lib.expected_stats import _xwoba_woba  # OWNER: never re-derive xwOBA

H_BUST = 0.0
C = Path('data/research/xfp_cache')
UNI = Path('data/research/triangulate_universe')


def _nm(s):
    """Join key. Flips "Last, First" (rp3/volume CSV convention) then delegates
    to the OWNER normalizer.

    Do NOT hand-roll this. A local copy here silently dropped Ryan O'Hearn on
    the first run: the PL cache writes a curly apostrophe (U+2019) and the rh3
    file a straight one (U+0027), so the two normalized differently and his row
    came back with zero games. `safe_name_key` already collapses both, plus
    "C.J." / "CJ" and hyphens. This is fix-backlog item #4 (73 files re-defining
    the normalizer) biting in real time — route to the owner instead of adding
    a 74th variant.
    """
    s = str(s)
    if ',' in s:
        last, _, first = s.partition(',')
        s = f'{first.strip()} {last.strip()}'
    return safe_name_key(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default='2026-07-28')
    ap.add_argument('--pl-json', default='data/research/pl_cache/pl_hitters_top150.json')
    ap.add_argument('--old-pl-json', default=None,
                    help='prior-edition hitter Top-150 json for the ▲▼ move column')
    ap.add_argument('--asb', default='2026-07-16', help='first post-All-Star-break game date')
    a = ap.parse_args()
    d = a.date

    NEW = {_nm(k): v for k, v in json.load(open(a.pl_json, encoding='utf-8'))['ranks'].items()}
    disp_of = {_nm(k): k for k in json.load(open(a.pl_json, encoding='utf-8'))['ranks']}
    OLD = ({_nm(k): v for k, v in json.load(open(a.old_pl_json, encoding='utf-8'))['ranks'].items()}
           if a.old_pl_json else None)
    sent_p = UNI / f'pl_hitter_sentiment_{d}.json'
    sent = json.load(open(sent_p, encoding='utf-8'))['sentiment'] if sent_p.exists() else {}

    st = default_state()
    teams = st.all_teams()
    owner = {_nm(n): t for n, t in zip(teams['player_name'], teams['team_name'])}
    inj = {_nm(n): str(s) for n, s in zip(teams['player_name'], teams['injury_status'])}
    fa = st.available_fa()
    fa_inj = {_nm(r.player_name): str(r.injury_status) for _, r in fa.iterrows()}

    tri = pd.read_csv(UNI / f'triangulate_nightly_{d}.csv')
    tri = tri[tri.bucket == 'H'].copy()
    tri['k'] = tri.player_name.map(_nm)
    T = tri.drop_duplicates('k').set_index('k')

    rh = pd.read_csv('data/outputs/xfp_rh3_projections.csv'); rh['k'] = rh.player_name.map(_nm)
    RH = rh.drop_duplicates('k').set_index('k')
    id_of = {r.k: int(r.batter) for _, r in rh.iterrows() if pd.notna(r.batter)}
    vol = pd.read_csv('data/outputs/xfp_volume_projections.csv'); vol['k'] = vol.player_name.map(_nm)
    V = vol.drop_duplicates('k').set_index('k')
    bs = pd.read_csv('data/research/bat_speed_trending_2026.csv'); bs['k'] = bs.name.map(_nm)
    BS = bs.drop_duplicates('k').set_index('k')

    box = pd.read_parquet(C / 'boxscore_hitters.parquet')
    box['game_date'] = pd.to_datetime(box.game_date)
    sc = pd.read_parquet(C / 'statcast_2026.parquet',
                         columns=['batter', 'events', 'woba_value', 'woba_denom',
                                  'estimated_woba_using_speedangle', 'p_throws'])
    sc = sc[sc['events'].notna() & (sc['events'] != '')]

    g = lambda s, c: (s[c] if (s is not None and c in s.index and pd.notna(s[c])) else None)
    rows = []
    for k, npl in NEW.items():
        o = owner.get(k)
        who = 'MINE' if o == MY_TEAM_NAME else ('FA' if o is None else None)
        if who is None:
            continue                      # opponent-rostered: excluded, same as the SP board
        t = T.loc[k] if k in T.index else None
        r = RH.loc[k] if k in RH.index else None
        v = V.loc[k] if k in V.index else None
        z = BS.loc[k] if k in BS.index else None
        bid = id_of.get(k)

        gl = box[box.mlbam_id == bid].sort_values('game_date') if bid else box.iloc[0:0]
        l7, l21 = gl.tail(7), gl.tail(21)
        pab = sc[sc.batter == bid] if bid else sc.iloc[0:0]
        xr, _, nr = _xwoba_woba(pab[pab.p_throws == 'R'])
        xl, _, nl = _xwoba_woba(pab[pab.p_throws == 'L'])

        opl = OLD.get(k) if OLD is not None else g(t, 'pl_rank')
        pa_pg = g(v, 'proj_ros_pa_per_teamgame'); naive = g(v, 'naive_pace')
        flags = []
        if g(t, 'xstat_regression') in ('UNDERPERFORMING', 'OVERPERFORMING'):
            flags.append(g(t, 'xstat_regression')[:5])
        if z is not None and pd.notna(z.get('z')):
            if float(z['z']) >= 1.0: flags.append('BAT-SPD+')
            elif float(z['z']) <= -1.0: flags.append('BAT-SPD-')
        st_ = fa_inj.get(k, inj.get(k, 'ACTIVE'))
        if st_ not in ('ACTIVE', 'nan', ''):
            flags.append(st_)

        rows.append(dict(
            new_pl=int(npl), old_pl=int(opl) if opl is not None else None,
            move=(int(npl - opl) if opl is not None else None), owner=who,
            player=disp_of.get(k, k.title()),
            rh3=int(g(r, 'rank')) if g(r, 'rank') is not None else None,
            verdict=g(t, 'verdict_top'), baseline=g(t, 'headline_proj'),
            l7=round(l7.fp_h.mean(), 2) if len(l7) else None,
            l21=round(l21.fp_h.mean(), 2) if len(l21) else None,
            season=round(gl.fp_h.mean(), 2) if len(gl) else None, n_g=len(gl),
            boom=round(100 * np.mean(l21.fp_h >= H_BOOM)) if len(l21) else None,
            bust=round(100 * np.mean(l21.fp_h < H_BUST)) if len(l21) else None,
            xwoba_R=round(xr, 3) if (xr is not None and nr >= 100) else None, pa_R=nr,
            xwoba_L=round(xl, 3) if (xl is not None and nl >= 40) else None, pa_L=nl,
            pa_pg=round(float(pa_pg), 2) if pa_pg is not None else None,
            vol_gap=round(float(pa_pg) - float(naive), 2) if (pa_pg and naive) else None,
            arche=g(t, 'arche_overall'), traj=g(t, 'arche_traj'),
            bs_z=round(float(z['z']), 2) if (z is not None and pd.notna(z.get('z'))) else None,
            flags=' '.join(flags), pl_sentiment=sent.get(k, '—')))

    df = pd.DataFrame(rows).sort_values('new_pl')
    out = UNI / f'hitter_pl_board_{d}.csv'
    df.to_csv(out, index=False)
    n_sent = int((df.pl_sentiment != '—').sum())
    print(f"hitter_pl_board: {len(df)} PL-ranked hitters that are MINE/FA "
          f"({(df.owner=='MINE').sum()} mine, {(df.owner=='FA').sum()} FA) -> {out}")
    print(f"PL sentiment populated on {n_sent}/{len(df)} rows "
          f"({100*n_sent/max(len(df),1):.0f}% — sparse by source design, see module docstring)")

    def fmt(v, nd=2):
        return '—' if (v is None or (isinstance(v, float) and pd.isna(v))) else (
            str(int(v)) if (isinstance(v, (int, float)) and float(v).is_integer()) else f"{v:.{nd}f}")

    def pl_cell(r):
        n = int(r['new_pl'])
        if pd.isna(r['old_pl']):
            return f"{n} new"
        mv = int(r['move']); arr = '▲' if mv < 0 else ('▼' if mv > 0 else '·')
        return f"{n} {arr}{abs(mv) if mv else ''} ({int(r['old_pl'])})"

    disp_rows = []
    for _, r in df.iterrows():
        nb = (f"{fmt(r['boom'],0)}%/{fmt(r['bust'],0)}% ({int(r['boom']-r['bust']):+d})"
              if pd.notna(r['boom']) else '—')
        disp_rows.append({
            'PL ▲▼ (old)': pl_cell(r),
            'Own': '⭐' if r['owner'] == 'MINE' else 'FA',
            'Hitter': r['player'],
            'rh3·verdict·baseline': ('—' if pd.isna(r['rh3']) else
                                     f"#{int(r['rh3'])} {r['verdict'] if isinstance(r['verdict'], str) else '—'} "
                                     f"{fmt(r['baseline'],2)}"),
            'L7/L21/Sea (G)': f"{fmt(r['l7'])}/{fmt(r['l21'])}/{fmt(r['season'])} ({r['n_g']})",
            'boom/bust(net)': nb,
            'xwOBA R/L': f"{fmt(r['xwoba_R'],3)}/{fmt(r['xwoba_L'],3)}",
            'PA/tg (vs pace)': f"{fmt(r['pa_pg'])} ({fmt(r['vol_gap'])})",
            'arche/traj': f"{fmt(r['arche'],0)} {r['traj'] if isinstance(r['traj'], str) else '—'}",
            'bat spd z': fmt(r['bs_z']),
            'flags': r['flags'],
            'PL sentiment': r['pl_sentiment'],
        })
    disp = pd.DataFrame(disp_rows)
    with pd.option_context('display.max_rows', None, 'display.width', 420, 'display.max_colwidth', 60):
        print(disp.to_string(index=False))
    cols = list(disp.columns)
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    for _, r in disp.iterrows():
        lines.append('| ' + ' | '.join(str(r[c]) for c in cols) + ' |')
    md = UNI / f'hitter_pl_board_{d}.md'
    md.write_text('\n'.join(lines), encoding='utf-8')
    print(f"\ncombined-column markdown -> {md}")


if __name__ == '__main__':
    main()
