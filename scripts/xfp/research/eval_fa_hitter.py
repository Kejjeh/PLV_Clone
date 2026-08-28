"""Shared per-candidate FA-hitter eval engine — identical lens stack for every
candidate so the workflow agents compare apples to apples. Usage:
    python scripts/xfp/research/eval_fa_hitter.py "<name>" [mlbam]
Lenses: rh3 (ROS/per-g/rep-delta/signal) · baseline xFP+tier · xwOBA-L21d vs 2025
(required hitter pre-check) · xwOBACON YoY 2024/25/26 · physical-trend (3-axis) ·
recent-15g actuals (boom/bust BrownU FP). Display/context; rh3/Blended is headline.
"""
import sys, json, requests
from datetime import date, timedelta
from pathlib import Path
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
import numpy as np, pandas as pd

C = Path('data/research/xfp_cache')
RH3 = pd.read_csv('data/outputs/xfp_rh3_projections.csv')
HM = pd.read_csv(C / 'hitters_multiyr_2015_2026.csv')
from plv_clone.utils.name_match import resolve_batter_id

name = sys.argv[1]
mlbam = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
if mlbam is None:
    mlbam = resolve_batter_id(name, multiyr=HM)
out = {'name': name, 'mlbam': mlbam}

# --- rh3 ---
r = RH3[RH3['batter'] == mlbam]
if not r.empty:
    rr = r.iloc[0]
    out['rh3'] = {'per_g': round(float(rr['xfp_rh3_per_game']), 2),
                  'ros': round(float(rr['expected_total_fp_remaining'])),
                  'rep_delta': round(float(rr['replacement_delta'])),
                  'signal': str(rr.get('signal', '')), 'pos': str(rr.get('primary_position', '')),
                  'rank': int(rr['rank']),
                  'slump_bounce_pct': (round(float(rr['slump_bounce_pct']), 2) if pd.notna(rr.get('slump_bounce_pct')) else None)}
else:
    out['rh3'] = {'note': 'OUTSIDE rh3 top-240 (projects below the surfaced FA set)'}

# --- Baseline xFP ---
try:
    from scripts.xfp.lib.blend_score import compute_blended_xfp
    b = compute_blended_xfp(player_name=name, player_type='H', mlbam_id=mlbam)
    out['blended'] = {'xfp': b.get('blended_xfp'), 'tier': b.get('confidence_tier'),
                      'value_tier': b.get('value_tier'), 'live_marginal': b.get('live_marginal')}
except Exception as e:
    out['blended'] = {'err': str(e)[:80]}

# --- statcast xwOBA L21d vs 2025 + xwOBACON YoY ---
def szn(y):
    p = C / f'statcast_{y}.parquet'
    if not p.exists(): return None
    df = pd.read_parquet(p, columns=['batter', 'game_date', 'type', 'woba_value', 'woba_denom',
                                     'estimated_woba_using_speedangle'])
    return df[df['batter'] == mlbam]
def woba_xwobacon(df, since=None):
    if df is None or df.empty: return None, None, 0
    if since is not None:
        df = df.assign(d=pd.to_datetime(df['game_date'])); df = df[df['d'] >= since]
    pa = df.dropna(subset=['woba_denom']); wd = pa['woba_denom'].sum()
    woba = (pa['woba_value'].fillna(0).sum() / wd) if wd > 0 else None
    bip = df[df['type'] == 'X']
    xc = bip['estimated_woba_using_speedangle'].mean() if len(bip) else None
    return (round(woba, 3) if woba else None), (round(xc, 3) if xc and not np.isnan(xc) else None), int(wd)
d26, d25, d24 = szn(2026), szn(2025), szn(2024)
l21_since = pd.Timestamp(date(2026, 6, 16) - timedelta(days=21))
w_l21, xc_l21, pa_l21 = woba_xwobacon(d26, since=l21_since)
w_26, xc_26, pa_26 = woba_xwobacon(d26)
w_25, xc_25, pa_25 = woba_xwobacon(d25)
w_24, xc_24, pa_24 = woba_xwobacon(d24)
out['xwoba'] = {'L21d_woba': w_l21, 'L21d_xwobacon': xc_l21, 'L21d_pa': pa_l21,
                '2026_woba': w_26, '2026_xwobacon': xc_26, '2026_pa': pa_26,
                '2025_woba': w_25, '2025_xwobacon': xc_25,
                'xwobacon_yoy': {'2024': xc_24, '2025': xc_25, '2026': xc_26}}
# diagnostic: L21d vs 2025 baseline
if w_l21 and w_25:
    out['xwoba']['L21d_vs_2025_woba_delta'] = round(w_l21 - w_25, 3)

# --- physical trend (3-axis) ---
try:
    from scripts.xfp.lib.trend_signal import trend_for_mlbam
    tag, _ = trend_for_mlbam(mlbam, 'H')
    out['physical_trend'] = tag or 'no qualifying 2026 sample'
except Exception as e:
    out['physical_trend'] = f'err: {str(e)[:60]}'

# --- recent 15g actuals (BrownU hitter FP = R+TB+RBI+BB+HBP+SB-K) ---
try:
    u = f"https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?stats=gameLog&group=hitting&season=2026"
    g = requests.get(u, timeout=15).json()['stats'][0]['splits'][-15:]
    fps = []
    for s in g:
        st = s['stat']
        tb = int(st.get('totalBases', 0))
        fp = (int(st.get('runs', 0)) + tb + int(st.get('rbi', 0)) + int(st.get('baseOnBalls', 0))
              + int(st.get('hitByPitch', 0)) + int(st.get('stolenBases', 0)) - int(st.get('strikeOuts', 0)))
        fps.append(fp)
    if fps:
        arr = np.array(fps)
        out['recent15'] = {'n': len(fps), 'avg': round(arr.mean(), 2), 'l5_avg': round(arr[-5:].mean(), 2),
                           'boom_pct': round((arr >= 5).mean(), 2), 'bust_pct': round((arr < 2).mean(), 2)}
except Exception as e:
    out['recent15'] = {'err': str(e)[:60]}

print(json.dumps(out, indent=2, default=str))
