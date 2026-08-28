"""OF-priority re-rank: ALL FA hitters eligible at OF (can fill the durable Judge
hole, out ~38d), ranked by rh3 then baseline xFP. Catches OF-eligible bats my
rh3-ROS-sorted scan missed (e.g. Steer, outside rh3 top-240)."""
import sys; _REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
from app.espn_connector import _get_league, get_all_teams
from plv_clone.utils.name_match import resolve_batter_id, _normalize
RH3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
HM = pd.read_csv('data/research/xfp_cache/hitters_multiyr_2015_2026.csv')
from scripts.xfp.lib.blend_score import compute_blended_xfp

OF = {'OF','LF','CF','RF'}
lg = _get_league()
rostered = {_normalize(n) for n in get_all_teams()['player_name']}
rows = []
for p in lg.free_agents(size=2000):
    elig = [str(s) for s in (getattr(p, 'eligibleSlots', []) or [])]
    if not (set(elig) & OF):
        continue
    if _normalize(p.name) in rostered:
        continue
    bid = resolve_batter_id(p.name, team=str(getattr(p,'proTeam','') or ''), position=str(getattr(p,'position','') or ''), multiyr=HM)
    r = RH3[RH3['batter'] == bid] if bid is not None else RH3.iloc[0:0]
    per_g = float(r.iloc[0]['xfp_rh3_per_game']) if not r.empty else None
    ros = float(r.iloc[0]['expected_total_fp_remaining']) if not r.empty else None
    rows.append({'name': p.name, 'pos': getattr(p,'position','?'), 'mlbam': bid,
                 'own': float(getattr(p,'percent_owned',0) or 0),
                 'rh3_per_g': per_g, 'rh3_ros': ros,
                 'rh3_top240': not r.empty})
df = pd.DataFrame(rows)
# rank: top-240 rh3 first (by per_g), then the rest
df = df.sort_values(['rh3_top240','rh3_per_g'], ascending=[False, False])
print(f"OF-eligible FA hitters: {len(df)} (showing top 16 by rh3 + any with own>20%)\n")
print(f"  {'player':<20}{'pos':<5}{'rh3/g':<7}{'rh3_ros':<8}{'own%':<6}{'top240'}")
show = df.head(16)
for _, r in show.iterrows():
    pg = f"{r['rh3_per_g']:.2f}" if r['rh3_per_g'] else '—'
    ro = f"{r['rh3_ros']:.0f}" if r['rh3_ros'] else '—'
    print(f"  {r['name'][:19]:<20}{str(r['pos']):<5}{pg:<7}{ro:<8}{r['own']:<6.0f}{r['rh3_top240']}")

# Baseline xFP for the top OF-eligible + Steer (the real production read)
print("\n=== baseline xFP (production read) for top OF-eligible candidates ===")
focus = list(show['name'][:8]) + ['Spencer Steer','Carlos Cortes','Jo Adell','Gavin Sheets','Jakob Marsee']
seen = set()
for nm in focus:
    if nm in seen: continue
    seen.add(nm)
    rr = df[df['name'] == nm]
    if rr.empty: continue
    bid = rr.iloc[0]['mlbam']
    try:
        b = compute_blended_xfp(player_name=nm, player_type='H', mlbam_id=int(bid))
        print(f"  {nm[:20]:<22} baseline xFP={b.get('blended_xfp'):.2f} tier={b.get('confidence_tier')} "
              f"rh3/g={rr.iloc[0]['rh3_per_g']}")
    except Exception as e:
        print(f"  {nm[:20]:<22} blend err: {str(e)[:50]}")
