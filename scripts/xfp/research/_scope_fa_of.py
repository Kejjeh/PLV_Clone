"""Scope 'all FA OF' to the decision-relevant set for a triangulate sweep:
OF-eligible free agents that have a real rh3 projection (top-240) OR own>=8% OR
are PL-ranked. Dumps name+mlbam+pos for the workflow."""
import sys, json; _REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
from app.espn_connector import _get_league, get_all_teams
from plv_clone.utils.name_match import resolve_batter_id, _normalize
RH3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
HM = pd.read_csv('data/research/xfp_cache/hitters_multiyr_2015_2026.csv')
OF = {'OF','LF','CF','RF'}
lg = _get_league()
rostered = {_normalize(n) for n in get_all_teams()['player_name']}
rows = []
for p in lg.free_agents(size=2000):
    elig = [str(s) for s in (getattr(p, 'eligibleSlots', []) or [])]
    if not (set(elig) & OF) or _normalize(p.name) in rostered:
        continue
    bid = resolve_batter_id(p.name, team=str(getattr(p,'proTeam','') or ''), position=str(getattr(p,'position','') or ''), multiyr=HM)
    r = RH3[RH3['batter'] == bid] if bid is not None else RH3.iloc[0:0]
    own = float(getattr(p,'percent_owned',0) or 0)
    in240 = not r.empty
    per_g = round(float(r.iloc[0]['xfp_rh3_per_game']),2) if in240 else None
    ros_v = float(r.iloc[0]['expected_total_fp_remaining']) if in240 else 0
    # union: startable rh3 projection (rate + real playing time) OR name-brand/buy-low
    viable = (in240 and per_g >= 1.65 and ros_v >= 85) or own >= 12
    if not viable:
        continue
    rows.append({'name': p.name, 'mlbam': int(bid) if bid else None, 'pos': getattr(p,'position','?'),
                 'own': round(own,0), 'rh3_per_g': per_g,
                 'rh3_ros': round(float(r.iloc[0]['expected_total_fp_remaining'])) if in240 else None,
                 'tier': 'rh3' if (in240 and per_g and per_g>=1.5) else 'name_brand'})
# always include Steer
if not any('steer' in _normalize(x['name']) for x in rows):
    rows.append({'name':'Spencer Steer','mlbam':668715,'pos':'OF-elig','own':25,'rh3_per_g':None,'rh3_ros':None})
df = pd.DataFrame(rows).sort_values(['tier','rh3_per_g','own'], ascending=[True,False,False], na_position='last')
print(f"VIABLE FA OF (OF-eligible; rh3/g>=1.5 OR own>=10%): {len(df)}\n")
for _, r in df.iterrows():
    print(f"  [{r['tier']:<10}] {r['name'][:22]:<24}{str(r['pos']):<6}own={r['own']:<5.0f}rh3/g={r['rh3_per_g'] if r['rh3_per_g'] else '—':<6} ros={r['rh3_ros'] if r['rh3_ros'] else '—'}")
df.to_json('data/research/decisions/fa_of_triangulate_set_2026-06-16.json', orient='records', indent=1)
print(f"\nsaved {len(df)} -> data/research/decisions/fa_of_triangulate_set_2026-06-16.json")
