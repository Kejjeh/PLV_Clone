"""Robust venue-weighted ROS hitter board — 2026-08-28 session method, frozen.

Recency-laddered level (season 0.55 / L225-PA 0.30 / L21d 0.15) + venue deltas
from season AND L225 windows, each shrunk n/(n+60) per side, x remaining
home/road schedule through the fantasy end (9/27). Data: MLB gameLog API
(live — includes tonight's finals immediately). Display layer only (Rule 13).
Population: data/outputs/hitter_actuals_horizons_2026-08-28.csv (MINE + FA).
"""
import pandas as pd, numpy as np, requests, re, unicodedata, concurrent.futures as cf

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z ]', '', s.lower()).strip()

hz = pd.read_csv('data/outputs/hitter_actuals_horizons_2026-08-28.csv')
bh = pd.read_parquet('data/research/xfp_cache/boxscore_hitters.parquet')
bh['nk'] = bh.player_name.map(norm)
# ID-SAFE resolution (2026-08-29). The old path took `.iloc[0]` on a NAME
# match, which is don't-do #10: two Max Muncys exist (LAD 571970, 123 g,
# 2.29 FP/g and ATH 691777, 67 g, 1.21), so adding "Max Muncy" by name alone
# silently picks whichever row sorts first. The population now carries an
# `mlbam` column; it wins wherever present, and an ambiguous name with no id
# is SKIPPED LOUDLY instead of guessed.
ids, teams = {}, {}
_ambiguous = []
for _, r in hz.iterrows():
    pid = r.get('mlbam') if 'mlbam' in hz.columns else None
    if pid == pid and pid:                      # not NaN, not 0
        m = bh[bh.mlbam_id == int(pid)]
        if len(m):
            ids[r['name']] = int(pid); teams[r['name']] = m.team_id.iloc[-1]
            continue
    m = bh[bh.nk == norm(r['name'])]
    uniq = m.mlbam_id.unique()
    if len(uniq) > 1:
        _ambiguous.append((r['name'], list(uniq)))
        continue
    if len(m):
        ids[r['name']] = int(uniq[0]); teams[r['name']] = m.team_id.iloc[-1]
if _ambiguous:
    print('  ! SKIPPED ambiguous names (add an mlbam to the population to include them):')
    for n, u in _ambiguous:
        print(f'      {n}: {u}')

sched = requests.get('https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-08-29&endDate=2026-09-27', timeout=30).json()
mix = {}
for d in sched.get('dates', []):
    for g in d.get('games', []):
        if g.get('gameType') != 'R':
            continue
        h, a = g['teams']['home']['team']['id'], g['teams']['away']['team']['id']
        mix.setdefault(h, [0, 0]); mix[h][0] += 1
        mix.setdefault(a, [0, 0]); mix[a][1] += 1

def gamelog(nm):
    pid = ids.get(nm)
    try:
        r = requests.get(f'https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog&season=2026&group=hitting', timeout=12).json()
        rows = []
        for s in r['stats'][0]['splits']:
            st = s['stat']
            fp = (st.get('runs', 0) + int(st.get('totalBases', 0)) + st.get('rbi', 0)
                  + st.get('baseOnBalls', 0) + st.get('hitByPitch', 0)
                  + st.get('stolenBases', 0) - st.get('strikeOuts', 0))
            rows.append((s['date'], bool(s.get('isHome')), fp, int(st.get('plateAppearances', 0))))
        return nm, pd.DataFrame(rows, columns=['date', 'home', 'fp', 'pa'])
    except Exception:
        return nm, None

K_SPLIT = 60.0
L21_CUT = (pd.Timestamp.now() - pd.Timedelta(days=21)).strftime('%Y-%m-%d')
out = []
with cf.ThreadPoolExecutor(8) as ex:
    for nm, g in ex.map(gamelog, list(ids)):
        if g is None or len(g) < 30:
            continue
        g['date'] = pd.to_datetime(g.date); g = g.sort_values('date')
        season = g.fp.mean()
        gr = g.iloc[::-1]; cum = gr.pa.cumsum()
        l225 = gr[cum <= 225] if (cum <= 225).any() else gr.iloc[:1]
        l21 = g[g.date >= L21_CUT]
        level = 0.55 * season + 0.30 * l225.fp.mean() + 0.15 * (l21.fp.mean() if len(l21) else season)
        def vdelta(frame, base):
            dh = frame[frame.home].fp.mean() - base if frame.home.any() else 0
            da = frame[~frame.home].fp.mean() - base if (~frame.home).any() else 0
            nh, na = frame.home.sum(), (~frame.home).sum()
            return dh * nh / (nh + K_SPLIT), da * na / (na + K_SPLIT)
        dh_s, da_s = vdelta(g, season)
        dh_2, da_2 = vdelta(l225, l225.fp.mean())
        dh, da = 0.7 * dh_s + 0.3 * dh_2, 0.7 * da_s + 0.3 * da_2
        gh, ga = mix.get(teams[nm], [0, 0])
        ros = gh * (level + dh) + ga * (level + da)
        tag = hz[hz.name == nm].tag.iloc[0]
        out.append(dict(ros=round(ros, 1), name=nm, tag=tag, level=round(level, 2),
                        gh=gh, ga=ga, d_home=round(dh, 2), d_road=round(da, 2),
                        l225=round(l225.fp.mean(), 2),
                        l21=round(l21.fp.mean(), 2) if len(l21) else None,
                        last_game=str(g.date.max().date()), last_fp=int(g.fp.iloc[-1])))
df = pd.DataFrame(out).sort_values('ros', ascending=False)
df.to_csv('data/outputs/robust_ros_hitter_board_latest.csv', index=False)
print(df.to_string(index=False))
