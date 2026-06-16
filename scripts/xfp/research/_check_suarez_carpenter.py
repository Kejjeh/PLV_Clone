"""Availability + eligibility + platoon for Eugenio Suarez + Kerry Carpenter
before slotting into the FA-OF board."""
import sys, requests; sys.path.insert(0, '.')
from app.espn_connector import _get_league, get_all_teams
from plv_clone.utils.name_match import resolve_batter_id, _normalize
import pandas as pd
HM = pd.read_csv('data/research/xfp_cache/hitters_multiyr_2015_2026.csv')

TARGETS = {'Eugenio Suarez': ('CIN','3B'), 'Kerry Carpenter': ('DET','RF')}
lg = _get_league()
at = get_all_teams()
fas = {p.name: p for p in lg.free_agents(size=2000)}
OF = {'OF','LF','CF','RF'}

for nm, (team, pos) in TARGETS.items():
    bid = resolve_batter_id(nm, team=team, position=pos, multiyr=HM)
    # availability
    rost = at[at['player_name'].apply(lambda x: _normalize(x)==_normalize(nm))]
    on_roster = None if rost.empty else rost.iloc[0]['team_name']
    fa = None
    for fn, p in fas.items():
        if _normalize(fn) == _normalize(nm):
            fa = p; break
    elig = [str(s) for s in (getattr(fa,'eligibleSlots',[]) or [])] if fa else []
    own = float(getattr(fa,'percent_owned',0) or 0) if fa else None
    print(f"\n=== {nm} (mlbam {bid}) ===")
    print(f"  rostered by: {on_roster or 'NO — appears available'}")
    print(f"  in FA pool: {'YES' if fa else 'NO'}  own={own}  OF-eligible={'YES' if set(elig)&OF else 'NO'}")
    print(f"  eligible_slots: {elig}")
    # platoon
    if bid:
        try:
            s = requests.get(f"https://statsapi.mlb.com/api/v1/people/{bid}/stats?stats=statSplits&group=hitting&season=2026&sitCodes=vl,vr", timeout=15).json()
            for sp in s['stats'][0]['splits']:
                code = sp['split']['code']; st = sp['stat']
                print(f"  vs {code.upper()}: PA={st.get('plateAppearances')} OPS={st.get('ops')} HR={st.get('homeRuns')} AVG={st.get('avg')}")
            g = requests.get(f"https://statsapi.mlb.com/api/v1/people/{bid}/stats?stats=gameLog&group=hitting&season=2026", timeout=15).json()['stats'][0]['splits']
            pas=[int(x['stat'].get('plateAppearances',0)) for x in g]
            print(f"  2026: {len(g)} games, {sum(pas)} PA ({round(sum(pas)/max(len(g),1),2)}/g), last10 started={sum(1 for x in pas[-10:] if x>=2)}/10")
        except Exception as e:
            print(f"  splits err: {e}")
