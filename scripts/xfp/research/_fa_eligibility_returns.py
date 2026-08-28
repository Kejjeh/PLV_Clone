"""Correction: pull real eligible_slots for the FA candidates + Steer (don't bucket
by .position alone), and Judge/Elly IL return timeline (Judge out longest -> OF
is the priority hole)."""
import sys; _REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
from app.espn_connector import _get_league
try:
    from app.espn_connector import get_injury_details
except Exception:
    get_injury_details = None

CAND = ['Spencer Steer','Michael Busch','Spencer Horwitz','Colson Montgomery','Marcus Semien',
        'Willy Adames','Alec Bohm','Jake Burger','Jakob Marsee','TJ Rumfield','Bryson Stott',
        'Gavin Sheets','Carlos Cortes','Matt McLain','Jo Adell']

lg = _get_league()
fas = lg.free_agents(size=2000)
byname = {}
for p in fas:
    byname[p.name] = p

OF_SLOTS = {'OF','LF','CF','RF'}
print("=== FA candidate eligibility (OF-eligible = can fill the Judge hole) ===")
print(f"  {'player':<20}{'ESPN pos':<9}{'OF?':<5}{'SS?':<5}{'eligible_slots'}")
for nm in CAND:
    p = byname.get(nm)
    if p is None:
        print(f"  {nm:<20} NOT IN FA POOL (rostered?)"); continue
    elig = [str(s) for s in (getattr(p, 'eligibleSlots', []) or [])]
    of = 'YES' if any(s in OF_SLOTS for s in elig) else '-'
    ss = 'YES' if 'SS' in elig else '-'
    print(f"  {nm:<20}{str(getattr(p,'position','?')):<9}{of:<5}{ss:<5}{elig}")

# Judge / Elly return timeline
print("\n=== IL return timeline (Judge OF vs Elly SS) ===")
ids = {'Aaron Judge':592450, 'Elly De La Cruz':682829, 'Trea Turner':607208}
if get_injury_details:
    try:
        inj = get_injury_details(list(ids.values()))
        print(inj.to_string() if hasattr(inj,'to_string') else inj)
    except Exception as e:
        print('get_injury_details err:', e)
# also raw from roster
from app.espn_connector import get_my_roster_with_injuries
ros = get_my_roster_with_injuries()
cols = [c for c in ros.columns if c.lower() in ('player_name','injury_status','lineup_slot','position') or 'return' in c.lower() or 'date' in c.lower() or 'detail' in c.lower()]
for nm in ids:
    r = ros[ros['player_name']==nm]
    if not r.empty:
        print(f"  {nm}: {r[cols].to_dict('records')}")
