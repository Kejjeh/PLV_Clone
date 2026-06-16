"""Playing-time + platoon check for the Adell-vs-Steer OF-hole decision.
Everyday vs part-time (PA/team-game), recent start cadence, and vs-LHP/RHP skew."""
import requests, json
PLAYERS = {'Jo Adell': 666176, 'Spencer Steer': 668715}

def fetch(pid):
    out = {}
    # game log (start cadence + total PA)
    g = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog&group=hitting&season=2026", timeout=15).json()
    sp = g['stats'][0]['splits']
    pas = [int(s['stat'].get('plateAppearances', 0)) for s in sp]
    out['games'] = len(sp); out['total_pa'] = sum(pas)
    out['pa_per_game'] = round(sum(pas)/len(sp), 2) if sp else 0
    last10 = pas[-10:]
    out['last10_started'] = sum(1 for x in last10 if x >= 2)  # >=2 PA ~= started
    out['last10_pa'] = last10
    out['bats'] = None
    # handedness
    try:
        p = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}", timeout=10).json()
        out['bats'] = p['people'][0].get('batSide', {}).get('code')
    except Exception: pass
    # platoon splits vs L / vs R
    s = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=statSplits&group=hitting&season=2026&sitCodes=vl,vr", timeout=15).json()
    splits = {}
    for sp2 in s['stats'][0]['splits']:
        code = sp2.get('split', {}).get('code')
        st = sp2['stat']
        splits[code] = {'PA': st.get('plateAppearances'), 'OPS': st.get('ops'), 'AVG': st.get('avg'),
                        'HR': st.get('homeRuns'), 'K%': (round(int(st.get('strikeOuts',0))/max(int(st.get('plateAppearances',1)),1),3))}
    out['vsL'] = splits.get('vl'); out['vsR'] = splits.get('vr')
    return out

for nm, pid in PLAYERS.items():
    d = fetch(pid)
    print(f"\n=== {nm} (bats {d['bats']}) ===")
    print(f"  2026: {d['games']} games, {d['total_pa']} PA, {d['pa_per_game']} PA/game "
          f"-> {'EVERYDAY' if d['pa_per_game']>=3.3 else 'PART-TIME/PLATOON'}")
    print(f"  last 10 games started (>=2 PA): {d['last10_started']}/10   PA pattern: {d['last10_pa']}")
    print(f"  vs LHP: {d['vsL']}")
    print(f"  vs RHP: {d['vsR']}")
