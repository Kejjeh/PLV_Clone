"""Runner for /level-board — hitter season-to-date LEVEL board.

Ranks hitters by the EMPIRICALLY-VALIDATED best *simple* forward-FP indicator:
a lightly-shrunk season-to-date FP/g.

WHY this metric (validated 2026-06-26, leakage-safe, player-cluster bootstrap):
  - window_predictive_validity_2026-06-26.md: season-to-date level is the single
    best forward predictor of next-14d FP/g (r ~0.33); recent windows add nothing
    beyond it (no momentum term).
  - level-formula bake-off: recency-weighting (EWMA/L30-blend) is WORSE than the
    flat mean; ranking by TOTAL FP is the worst (rewards playing time); the ONLY
    weighting that helps is a LIGHT shrink toward the league mean (~+0.006 r),
    which is exactly what rh3 already encodes.

So Level FP/g = (n*raw + K*POP)/(n+K), K=20 toward the league game-mean. The board's
real value-add is the LEVEL-vs-rh3 DIVERGENCE: where in-season production sits above
or below the career-anchored model.
  - RIDING-HOT  = Level >> rh3  -> producing above the model's forward rate
                  (regression risk; the TJ Rumfield / hot-but-no-pedigree trap).
  - PEDIGREE    = rh3 >> Level  -> career model sees more than the in-season line
                  (buy-low-ish / bounce candidate).
  - ALIGNED     = the two agree (steadiest reads; e.g. Luis Garcia Jr.).

Display/context only — rh3 stays the headline projection (CLAUDE.md Rule 13). This
board does NOT introduce a competing projection; it foregrounds the validated level
and its gap to the model.

  python scripts/xfp/run_level_board.py                 # my roster + top FA by level
  python scripts/xfp/run_level_board.py --fa-top 30
  python scripts/xfp/run_level_board.py --names "Luis Garcia Jr., Michael Busch"
"""
import sys, argparse, unicodedata
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path
from plv_clone.utils.name_match import resolve_batter_id

C = Path('data/research/xfp_cache')
K_SHRINK = 20                     # validated light shrink (K10-K25 optimal)
MIN_GAMES = 15                    # need a real season-to-date sample

HIT = pd.read_csv(C / 'hitters_multiyr_2015_2026.csv')


def _norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    return ' '.join(s.lower().replace('.', '').replace(',', '').split())


def _bucket(pos):
    p = str(pos).upper()
    if p in ('C',):
        return 'C'
    if p in ('1B', '2B', '3B', 'SS', 'IF', '1B/3B', '2B/SS'):
        return 'IF'
    if p in ('LF', 'CF', 'RF', 'OF'):
        return 'OF'
    if p in ('DH',):
        return 'DH'
    return '?'


def resolve(name, team, pos, nmap):
    """resolve_batter_id first (collision-safe); fall back to rh3's disambiguated
    name->mlbam map (catches the Luis Garcia Jr. case resolve_batter_id refuses).
    The fallback is position-bucket guarded so a same-name star can't be grabbed for
    a different-position FA (the Julio Rodriguez C-vs-OF / Max Muncy collision)."""
    try:
        bid = resolve_batter_id(name, team=team, position=pos, multiyr=HIT)
    except Exception:
        bid = None
    if bid is None:
        cand = nmap.get(_norm(name))   # (bid, primary_position) or None
        if cand is not None:
            cb, cpos = cand
            b_in, b_rh = _bucket(pos), _bucket(cpos)
            if b_in == '?' or b_rh == '?' or b_in == b_rh:
                bid = cb
    return bid


def level_table():
    """mlbam -> n_games, raw_pg, level_pg (shrunk), total_fp."""
    bx = pd.read_parquet(C / 'boxscore_hitters.parquet')[['mlbam_id', 'fp_h']].dropna()
    pop = bx.fp_h.mean()
    g = bx.groupby('mlbam_id').agg(n_games=('fp_h', 'size'), raw_pg=('fp_h', 'mean'),
                                   total=('fp_h', 'sum'))
    g['level_pg'] = (g.n_games * g.raw_pg + K_SHRINK * pop) / (g.n_games + K_SHRINK)
    return g[g.n_games >= MIN_GAMES], pop


def rh3_table():
    r = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
    return r.set_index('batter')[['rank', 'xfp_rh3_per_game', 'player_name', 'primary_position']]


def divergence_flag(level_pg, rh3_pg):
    if pd.isna(rh3_pg):
        return '?', float('nan')
    d = level_pg - rh3_pg
    if d >= 0.40:
        return 'RIDING-HOT', d           # producing above model -> regression risk
    if d <= -0.40:
        return 'PEDIGREE', d             # model sees more than in-season line
    return 'ALIGNED', d


def build(LT, RH, pop):
    rows = []
    for pid, r in LT.iterrows():
        rr = RH.loc[pid] if pid in RH.index else None
        rh3_pg = rr['xfp_rh3_per_game'] if rr is not None else float('nan')
        rh3_rank = int(rr['rank']) if rr is not None else None
        flag, d = divergence_flag(r.level_pg, rh3_pg)
        rows.append(dict(mlbam=pid, n=int(r.n_games), raw_pg=r.raw_pg, level_pg=r.level_pg,
                         total=r.total, rh3_rank=rh3_rank, rh3_pg=rh3_pg, flag=flag, gap=d))
    return pd.DataFrame(rows)


def fmt(r, name):
    rk = f"rh3#{int(r['rh3_rank'])}" if pd.notna(r['rh3_rank']) else "rh3 NA"
    flagstr = {'RIDING-HOT': '🔥RIDING-HOT', 'PEDIGREE': '💎PEDIGREE',
               'ALIGNED': '· aligned', '?': '· (no rh3)'}[r['flag']]
    dv = f"{r['gap']:+.2f}" if pd.notna(r['gap']) else "  na"
    rh3pg = f"{r['rh3_pg']:4.2f}" if pd.notna(r['rh3_pg']) else " na "
    return (f"  {name:<22} Level {r['level_pg']:4.2f} fp/g  (raw {r['raw_pg']:4.2f}, {int(r['n'])}G, "
            f"tot {r['total']:3.0f})  {rk} {rh3pg}  d{dv}  {flagstr}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', default=None)
    ap.add_argument('--fa-top', type=int, default=25)
    ap.add_argument('--min-games', type=int, default=MIN_GAMES)
    args = ap.parse_args()

    LT, pop = level_table()
    RH = rh3_table()
    B = build(LT, RH, pop).set_index('mlbam')
    NMAP = {_norm(nm): (bid, RH.loc[bid, 'primary_position'])
            for bid, nm in RH['player_name'].items()}
    print(f"Level FP/g = shrunk season-to-date rate (K={K_SHRINK} -> league {pop:.2f}); "
          f"validated best simple forward indicator. rh3 = career-anchored model (headline).")

    if args.names:
        from plv_clone.league_state import default_state
        allp = default_state().all_teams()
        print("\n=== LEVEL CARDS ===")
        for nm in [x.strip() for x in args.names.split(',') if x.strip()]:
            hit = allp[allp['player_name'] == nm]
            team = hit.iloc[0].get('pro_team') if not hit.empty else None
            pos = hit.iloc[0].get('position') if not hit.empty else None
            bid = resolve(nm, team, pos, NMAP)
            if bid in B.index:
                print(fmt(B.loc[bid], nm))
            else:
                print(f"  {nm:<22} — no qualifying 2026 sample (<{args.min_games}G / unresolved)")
        return

    from app.espn_connector import get_my_roster
    from plv_clone.league_state import default_state  # item 11: FA pool owner
    mine = get_my_roster()
    mine_ids = set()
    print("\n=== MY HITTERS — by season-to-date LEVEL (validated best forward FP indicator) ===")
    mrows = []
    for _, r in mine.iterrows():
        if str(r['position']).upper() in {'SP', 'RP', 'P'}:
            continue
        bid = resolve(r['player_name'], r.get('pro_team'), r['position'], NMAP)
        if bid in B.index:
            mine_ids.add(bid); mrows.append((r['player_name'], B.loc[bid]))
    for n, row in sorted(mrows, key=lambda x: -x[1]['level_pg']):
        print(fmt(row, n))

    fa = default_state().available_fa()  # item 11: cross-team-verified FA pool
    farows = []
    for _, r in fa.iterrows():
        if str(r['position']).upper() in {'SP', 'RP', 'P'}:
            continue
        bid = resolve(r['player_name'], r.get('pro_team'), r['position'], NMAP)
        if bid in B.index and bid not in mine_ids:
            farows.append((r['player_name'], B.loc[bid]))
    seen = set()
    print(f"\n=== TOP {args.fa_top} FA HITTERS — by season-to-date LEVEL ===")
    for n, row in sorted(farows, key=lambda x: -x[1]['level_pg']):
        if row.name in seen:
            continue
        seen.add(row.name)
        print(fmt(row, n))
        if len(seen) >= args.fa_top:
            break
    print("\nFlags: 🔥RIDING-HOT = producing above the model (regression risk) · "
          "💎PEDIGREE = model sees more than the line (buy-low) · aligned = steadiest.")


if __name__ == '__main__':
    main()
