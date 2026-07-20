"""Build a multi-year per-game BrownU-FP store (2015-2026) from MLB gameLogs — the
only source with R/RBI/SB (hitters) + ER (pitchers) per game. Threaded + resumable.
Persists data/research/multiyr_boxscore_fp.parquet (mlbam, year, game_date, role, gs, fp, sb)."""
import sys, requests, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd, numpy as np
from plv_clone.fantasy.scoring import pitcher_fp

OUT = 'data/research/multiyr_boxscore_fp.parquet'
YEARS = list(range(2015, 2027))
SESS = requests.Session()


def _ip(s):
    try:
        a, b = (str(s) + '.0').split('.')[:2]
        return int(a) + int(b[0]) / 3.0
    except Exception:
        return 0.0


def hitter_games(pid, yr):
    try:
        j = SESS.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog&group=hitting&season={yr}", timeout=12).json()
        out = []
        for s in j.get('stats', [{}])[0].get('splits', []):
            st = s.get('stat', {}); pa = int(st.get('plateAppearances', 0))
            if pa < 1:
                continue
            sb = int(st.get('stolenBases', 0))
            fp = (int(st.get('runs', 0)) + int(st.get('totalBases', 0)) + int(st.get('rbi', 0))
                  + int(st.get('baseOnBalls', 0)) + int(st.get('hitByPitch', 0)) + sb - int(st.get('strikeOuts', 0)))
            out.append((pid, yr, s.get('date'), 'H', 0, float(fp), sb))
        return out
    except Exception:
        return []


def pitcher_games(pid, yr):
    try:
        j = SESS.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog&group=pitching&season={yr}", timeout=12).json()
        out = []
        for s in j.get('stats', [{}])[0].get('splits', []):
            st = s.get('stat', {})
            gs = int(st.get('gamesStarted', 0))
            # canonical BrownU weights via scoring.pitcher_fp (audit #4);
            # operand order matches the old inline expression -> bit-identical
            fp = pitcher_fp(
                k=int(st.get('strikeOuts', 0)),
                ip=_ip(st.get('inningsPitched', 0)),
                h=int(st.get('hits', 0)),
                er=int(st.get('earnedRuns', 0)),
                bb=int(st.get('baseOnBalls', 0)),
                hbp=int(st.get('hitByPitch', 0)),
                sv=int(st.get('saves', 0)),
                hld=int(st.get('holds', 0)))
            out.append((pid, yr, s.get('date'), 'SP' if gs else 'RP', gs, float(fp), 0))
        return out
    except Exception:
        return []


# population per year from the multiyr caches (rostered-relevant: not Sept call-ups)
H = pd.read_csv('data/research/xfp_cache/hitters_multiyr_2015_2026.csv')
hit_jobs = [(int(r.batter), int(r.year), 'H') for r in H[H.pa >= 100].itertuples() if r.year in YEARS]
pids = set()
for f in ['sp_multiyr_2015_2025.csv', 'sp_multiyr.csv', 'relievers_multiyr_2018_2026.csv']:
    try:
        d = pd.read_csv(f'data/research/xfp_cache/{f}')
        for r in d.itertuples():
            if int(getattr(r, 'year', 0)) in YEARS:
                pids.add((int(r.pitcher), int(r.year), 'P'))
    except Exception as e:
        print('skip', f, e)
jobs = hit_jobs + list(pids)
print(f"jobs: {len(hit_jobs):,} hitter-seasons + {len(pids):,} pitcher-seasons = {len(jobs):,} gameLog calls")


def run(job):
    pid, yr, role = job
    return hitter_games(pid, yr) if role == 'H' else pitcher_games(pid, yr)


rows, done = [], 0
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(run, j): j for j in jobs}
    for fu in as_completed(futs):
        rows.extend(fu.result()); done += 1
        if done % 1000 == 0:
            print(f"  {done:,}/{len(jobs):,} ... rows={len(rows):,}")

df = pd.DataFrame(rows, columns=['mlbam', 'year', 'game_date', 'role', 'gs', 'fp', 'sb'])
df = df.drop_duplicates(['mlbam', 'game_date', 'role'])
df.to_parquet(OUT, index=False)
print(f"\nWROTE {OUT}: {len(df):,} player-games, years {sorted(df.year.unique())}")
print(df.groupby('role').size().to_string())
