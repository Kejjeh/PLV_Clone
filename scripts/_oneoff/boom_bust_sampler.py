"""Pull 2025 game logs from MLB Stats API for top-N SPs / hitters / RPs,
compute BrownU FP per game, output distributions to C:/tmp."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd

SEASON = 2025
TOP_N_SP = 250
TOP_N_H = 250
TOP_N_RP = 250
TIMEOUT = 20

def parse_ip(ip):
    if ip is None or ip == '':
        return 0.0
    s = str(ip)
    try:
        whole, frac = s.split('.')
        return int(whole) + int(frac) / 3.0
    except Exception:
        try:
            return float(s)
        except Exception:
            return 0.0

def fp_pitcher(row, is_rp):
    ip = parse_ip(row.get('inningsPitched', 0))
    k = int(row.get('strikeOuts', 0) or 0)
    h = int(row.get('hits', 0) or 0)
    er = int(row.get('earnedRuns', 0) or 0)
    bb = int(row.get('baseOnBalls', 0) or 0)
    hbp = int(row.get('hitByPitch', 0) or 0)
    base = k + ip * 3.3 - h - 2 * er - bb - hbp
    if is_rp:
        sv = int(row.get('saves', 0) or 0)
        hld = int(row.get('holds', 0) or 0)
        base += 5 * sv + 2 * hld
    return base

def fp_hitter(row):
    r = int(row.get('runs', 0) or 0)
    tb = row.get('totalBases')
    if tb is None or tb == '':
        h = int(row.get('hits', 0) or 0)
        d = int(row.get('doubles', 0) or 0)
        t = int(row.get('triples', 0) or 0)
        hr = int(row.get('homeRuns', 0) or 0)
        singles = h - d - t - hr
        tb = singles + 2*d + 3*t + 4*hr
    tb = int(tb or 0)
    rbi = int(row.get('rbi', 0) or 0)
    bb = int(row.get('baseOnBalls', 0) or 0)
    hbp = int(row.get('hitByPitch', 0) or 0)
    sb = int(row.get('stolenBases', 0) or 0)
    k = int(row.get('strikeOuts', 0) or 0)
    return r + tb + rbi + bb + hbp + sb - k

def fetch_gamelog(player_id, group):
    url = (f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
           f"?stats=gameLog&season={SEASON}&group={group}")
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        j = r.json()
        st = j.get('stats', [])
        if not st:
            return []
        return [s.get('stat', {}) for s in st[0].get('splits', [])]
    except Exception:
        return []

def collect(ids, group, label):
    results = []
    print(f"[{label}] fetching {len(ids)} players...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_gamelog, pid, group): pid for pid in ids}
        done = 0
        for f in as_completed(futs):
            try:
                stats = f.result()
            except Exception:
                stats = []
            results.append(stats)
            done += 1
            if done % 50 == 0:
                print(f"  [{label}] {done}/{len(ids)}", file=sys.stderr)
    return results

def main():
    sp = pd.read_csv('c:/Users/Joshua/plv_clone/data/outputs/xfp_rp3_projections.csv')
    hi = pd.read_csv('c:/Users/Joshua/plv_clone/data/outputs/xfp_rh3_projections.csv')
    rp = pd.read_csv('c:/Users/Joshua/plv_clone/data/outputs/xfp_rprs2_projections.csv')

    sp_ids = sp.sort_values('rank').head(TOP_N_SP)['pitcher'].astype(int).tolist()
    h_ids  = hi.sort_values('rank').head(TOP_N_H)['batter'].astype(int).tolist()
    rp_ids = rp.sort_values('rank').head(TOP_N_RP)['pitcher'].astype(int).tolist()

    sp_fps = []
    for stats in collect(sp_ids, 'pitching', 'SP'):
        for s in stats:
            gs = int(s.get('gamesStarted', 0) or 0)
            if gs >= 1:
                sp_fps.append(fp_pitcher(s, is_rp=False))

    rp_fps = []
    for stats in collect(rp_ids, 'pitching', 'RP'):
        for s in stats:
            gs = int(s.get('gamesStarted', 0) or 0)
            gp = int(s.get('gamesPlayed', 0) or 0)
            if gs == 0 and gp >= 1:
                rp_fps.append(fp_pitcher(s, is_rp=True))

    h_fps = []
    for stats in collect(h_ids, 'hitting', 'H'):
        for s in stats:
            pa = int(s.get('plateAppearances', 0) or 0)
            if pa >= 1:
                h_fps.append(fp_hitter(s))

    out = {'sp_fps': sp_fps, 'hitter_fps': h_fps, 'rp_fps': rp_fps}
    with open('C:/tmp/boom_bust_fps.json', 'w') as f:
        json.dump(out, f)
    print(f"SP n={len(sp_fps)}  H n={len(h_fps)}  RP n={len(rp_fps)}")

if __name__ == '__main__':
    main()
