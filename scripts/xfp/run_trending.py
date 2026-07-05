"""Runner for /trending — physical getting-better/worse board.

Default: MY roster + FA risers, role-appropriate signal (hitters=bat speed,
pitchers=FB velo), 2026-to-date vs prior-year baseline, z-scored, with the
contact/results column as confirmation.
  python scripts/xfp/run_trending.py
  python scripts/xfp/run_trending.py --names "Jordan Walker, Dustin May"

Engine + validation: scripts/xfp/lib/trend_signal.py,
data/research/validation_runs/early_season_bat_speed_2026-06-16.md
"""
import sys, argparse
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path
from scripts.xfp.lib.trend_signal import (hitter_trend_table, pitcher_trend_table,
                                          hitter_level_table, level_tag_hitter,
                                          tag_hitter, tag_pitcher)
from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id

C = Path('data/research/xfp_cache')
HIT = pd.read_csv(C / 'hitters_multiyr_2015_2026.csv')
SPM = pd.read_csv(C / 'sp_multiyr_2015_2025.csv')
try:
    RPM = pd.read_csv(C / 'relievers_multiyr_2018_2026.csv')
except Exception:
    RPM = None
NAMES = HIT.query('year>=2025').drop_duplicates('batter').set_index('batter')['player_name'].to_dict()

HT, PT = hitter_trend_table(), pitcher_trend_table()
LT = hitter_level_table()


def is_pitcher(pos):
    return str(pos).upper() in {'SP', 'RP', 'P'}


def rid(name, pos, team):
    try:
        if is_pitcher(pos):
            return resolve_pitcher_id(name, team=team, role=('SP' if str(pos).upper() == 'SP' else 'RP'),
                                      sp_multiyr=SPM, rp_multiyr=RPM)
        return resolve_batter_id(name, team=team, position=pos, multiyr=HIT)
    except Exception:
        return None


def card(name, pos, team):
    pid = rid(name, pos, team)
    if pid is None:
        return f"  {name:<24} — unresolved (collision needs team hint, or no 2026 sample)"
    if is_pitcher(pos):
        if pid in PT.index:
            return f"  {name:<24} {tag_pitcher(PT.loc[pid])}"
    else:
        if pid in HT.index:
            return f"  {name:<24} {tag_hitter(HT.loc[pid])}"
        if pid in LT.index:  # no YoY baseline (rookie / thin '25) — level read fallback
            return f"  {name:<24} {level_tag_hitter(LT.loc[pid])}"
    return f"  {name:<24} — no qualifying 2026 sample (IL / small sample)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', default=None, help='comma-separated player names for ad-hoc cards')
    ap.add_argument('--fa-top', type=int, default=12)
    args = ap.parse_args()

    if args.names:
        print("=== TREND CARDS ===")
        for nm in [x.strip() for x in args.names.split(',') if x.strip()]:
            # try to infer role/team from rostered-players table; else guess hitter then pitcher
            from plv_clone.league_state import default_state
            allp = default_state().all_teams()
            hit_row = allp[allp['player_name'] == nm]
            if not hit_row.empty:
                r = hit_row.iloc[0]
                print(card(nm, r['position'], r.get('pro_team')))
            else:
                # unknown role: print whichever table has the resolved id
                bid = resolve_batter_id(nm, multiyr=HIT)
                if bid in HT.index:
                    print(card(nm, '1B', None))
                else:
                    print(card(nm, 'SP', None))
        return

    # TODO(item 11): get_free_agents -> available_fa() adds cross-team verification; verify before migrating
    from app.espn_connector import get_my_roster, get_free_agents
    mine = get_my_roster()
    rows_h, rows_p, unres = [], [], []
    for _, r in mine.iterrows():
        pid = rid(r['player_name'], r['position'], r.get('pro_team'))
        if pid is None:
            unres.append(r['player_name']); continue
        if is_pitcher(r['position']) and pid in PT.index:
            rows_p.append((r['player_name'], PT.loc[pid]))
        elif (not is_pitcher(r['position'])) and pid in HT.index:
            rows_h.append((r['player_name'], HT.loc[pid]))
        else:
            unres.append(f"{r['player_name']} [no 2026 sample]")

    print("=== MY HITTERS — 3-axis physical trend (bat speed + swing path + intent, 2026 vs '25) ===")
    for n, row in sorted(rows_h, key=lambda x: -x[1]['z_comp']):
        print(f"  {n:<24} {tag_hitter(row)}")
    print("\n=== MY PITCHERS — FB velo trend (2026 vs '25) ===")
    for n, row in sorted(rows_p, key=lambda x: -x[1]['d_velo']):
        print(f"  {n:<24} {tag_pitcher(row)}")
    if unres:
        print(f"\n  (no read: {', '.join(unres)})")

    fa = get_free_agents(size=2000)
    fa_h, fa_p = [], []
    for _, r in fa.iterrows():
        pid = rid(r['player_name'], r['position'], r.get('pro_team'))
        if pid is None:
            continue
        if is_pitcher(r['position']) and pid in PT.index and PT.loc[pid, 'n_fb'] >= 80:
            fa_p.append((r['player_name'], PT.loc[pid]))
        elif (not is_pitcher(r['position'])) and pid in HT.index and HT.loc[pid, 'n_sw'] >= 120:
            fa_h.append((r['player_name'], HT.loc[pid]))
    print("\n=== TOP FA HITTER RISERS (breakout watch, 3-axis composite) ===")
    for n, row in sorted(fa_h, key=lambda x: -x[1]['z_comp'])[:args.fa_top]:
        print(f"  {n:<24} {tag_hitter(row)}")
    print("\n=== TOP FA SP/RP RISERS (stuff-up watch) ===")
    for n, row in sorted(fa_p, key=lambda x: -x[1]['d_velo'])[:args.fa_top]:
        print(f"  {n:<24} {tag_pitcher(row)}")


if __name__ == '__main__':
    main()
