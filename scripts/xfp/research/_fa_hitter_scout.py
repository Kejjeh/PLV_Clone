"""Scout for the Fairbanks->hitter swap: (1) confirm real injury status of the
DAY_TO_DAY stars, (2) full FA hitter pool (size=2000) joined to rh3, availability-
verified, (3) my current hitter bar + RP staff (Fairbanks drop context).
Saves the FA hitter shortlist for the deep-eval workflow."""
import json, requests
from datetime import date
from pathlib import Path
import sys; sys.path.insert(0, '.')
import pandas as pd
from app.espn_connector import get_my_roster_with_injuries, get_all_teams, get_free_agents
from plv_clone.utils.name_match import resolve_batter_id, _normalize

ROOT = Path('.')
RH3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
HITMULTI = pd.read_csv('data/research/xfp_cache/hitters_multiyr_2015_2026.csv')
try:
    RPRS2 = pd.read_csv('data/outputs/xfp_rprs2_projections.csv')
except Exception:
    RPRS2 = None

def mlb_lastplayed(pid):
    try:
        u = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog&group=hitting&season=2026"
        d = requests.get(u, timeout=15).json()
        splits = d['stats'][0]['splits']
        if not splits: return None, 0
        last = splits[-1]
        return last['date'], len(splits)
    except Exception as e:
        return f"err:{e}", 0

# ---------- (1) INJURY CONFIRMATION ----------
ros = get_my_roster_with_injuries()
print("="*70, "\n(1) INJURY STATUS CONFIRMATION\n", "="*70)
for nm in ['Aaron Judge', 'Elly De La Cruz', 'Trea Turner']:
    row = ros[ros['player_name'] == nm]
    if row.empty:
        print(f"  {nm}: not on roster?"); continue
    r = row.iloc[0]
    inj = r.get('injury_status', '?'); slot = r.get('lineup_slot', '?')
    bid = resolve_batter_id(nm, team=str(r.get('pro_team') or ''), position=str(r.get('position') or ''), multiyr=HITMULTI)
    last, ngames = mlb_lastplayed(bid) if bid else ('no-id', 0)
    print(f"  {nm:<18} ESPN status={inj!r} slot={slot!r} | mlbam={bid} last_game={last} (2026 games={ngames})")

# ---------- my roster context ----------
def is_hitter(pos): return str(pos).upper() not in {'SP','RP','P'}
my_h = ros[ros['position'].apply(is_hitter)].copy()
my_rp = ros[ros['position'].astype(str).str.upper().isin(['RP'])].copy()

def rh3_join_name(nm, team, pos):
    bid = resolve_batter_id(nm, team=str(team or ''), position=str(pos or ''), multiyr=HITMULTI)
    if bid is None: return None
    m = RH3[RH3['batter'] == bid]
    if m.empty: return {'mlbam': bid}
    r = m.iloc[0]
    return {'mlbam': int(bid), 'ros': float(r['expected_total_fp_remaining']),
            'per_g': float(r['xfp_rh3_per_game']), 'rep_delta': float(r['replacement_delta']),
            'signal': str(r.get('signal','')), 'pos': str(r.get('primary_position',''))}

print("\n", "="*70, "\n(2) MY CURRENT HITTERS (the bar a FA must beat) — by rh3 per-game\n", "="*70)
myrows = []
for _, r in my_h.iterrows():
    j = rh3_join_name(r['player_name'], r.get('pro_team'), r.get('position'))
    myrows.append({'name': r['player_name'], 'pos': r.get('position'), 'slot': r.get('lineup_slot'),
                   'inj': r.get('injury_status'), **(j or {})})
mydf = pd.DataFrame(myrows).sort_values('per_g', na_position='last')
for _, r in mydf.iterrows():
    print(f"  {r['name']:<22} {str(r['pos']):<4} per_g={r.get('per_g','—')} ros={r.get('ros','—')} "
          f"slot={r['slot']} inj={r['inj']}")
weak = mydf.dropna(subset=['per_g']).head(4)
print(f"\n  WEAKEST active hitters (FA must beat these to start): "
      f"{', '.join(f'{r['name']} ({r['per_g']:.2f}/g)' for _,r in weak.iterrows())}")

print("\n", "="*70, "\n(3) MY RP STAFF (Fairbanks drop context)\n", "="*70)
_rp_name_col = next((c for c in (RPRS2.columns if RPRS2 is not None else []) if 'name' in c.lower()), None)
if RPRS2 is not None:
    print(f"  (rprs2 cols: {list(RPRS2.columns)[:14]})")
for _, r in my_rp.iterrows():
    nm = r['player_name']; extra = ''
    try:
        if RPRS2 is not None and _rp_name_col:
            rr = RPRS2[RPRS2[_rp_name_col].apply(lambda x: _normalize(str(x)) == _normalize(nm))]
            if not rr.empty:
                rrow = rr.iloc[0]
                cols = {c: rrow[c] for c in rr.columns if c.lower() in
                        ('per_g','xfp_rprs2_per_game','xfp_rprs2_per_g','expected_total_fp_remaining',
                         'ros','leverage_tier','role','sv','closer','rank')}
                extra = ' '.join(f'{k}={v}' for k, v in cols.items())
    except Exception as e:
        extra = f'(rprs2 lookup err: {e})'
    print(f"  {nm:<20} slot={r.get('lineup_slot')} inj={r.get('injury_status')}  {extra}")

# ---------- (2) FA HITTER POOL ----------
print("\n", "="*70, "\n(4) FA HITTER POOL (size=2000, availability-verified) — top by rh3 ROS\n", "="*70)
fa = get_free_agents(size=2000)
allteams = get_all_teams()
rostered = {_normalize(n) for n in allteams['player_name']}
fa_h = fa[fa['position'].apply(is_hitter)].copy()
cands = []
for _, r in fa_h.iterrows():
    nm = r['player_name']
    if _normalize(nm) in rostered:   # Connelly-Early belt-and-suspenders
        continue
    j = rh3_join_name(nm, r.get('pro_team'), r.get('position'))
    if not j or 'ros' not in j:
        continue
    cands.append({'name': nm, 'team': r.get('pro_team'), 'pos': r.get('position'),
                  'pct_owned': float(r.get('percent_owned') or 0), **j})
cdf = pd.DataFrame(cands).sort_values('ros', ascending=False)
TOPN = 22
top = cdf.head(TOPN)
for _, r in top.iterrows():
    print(f"  {r['name']:<22} {str(r['pos']):<4} {str(r['team']):<4} per_g={r['per_g']:.2f} ros={r['ros']:.0f} "
          f"repΔ={r['rep_delta']:+.0f} own={r['pct_owned']:.0f}% sig={r['signal']}")

# ensure Spencer Steer present
steer = cdf[cdf['name'].apply(lambda x: 'steer' in _normalize(x))]
if not steer.empty and steer.iloc[0]['name'] not in set(top['name']):
    print(f"\n  + Spencer Steer (user-named): {steer.iloc[0].to_dict()}")

# save shortlist for workflow
out = top.to_dict('records')
for s in steer.to_dict('records'):
    if s['name'] not in [o['name'] for o in out]:
        out.append(s)
Path('data/research/decisions').mkdir(parents=True, exist_ok=True)
Path('data/research/decisions/fa_hitter_candidates_2026-06-16.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(f"\nsaved {len(out)} candidates -> data/research/decisions/fa_hitter_candidates_2026-06-16.json")
