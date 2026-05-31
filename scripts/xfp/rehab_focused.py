"""Focused rehab tracker for 5 specific pitchers. Pulls 2026 MiLB Statcast,
compares to most-recent prior MLB baseline, emits AHEAD/ON-TRACK/BEHIND verdict."""
import sys, io, urllib.request
import pandas as pd
from datetime import date

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PLAYERS = [
    # (display_name, mlbam, prior_velo, prior_k_pct, prior_bb_pct, prior_swstr_pct, baseline_yr)
    ('Hunter Greene',         668881, 94.8, 0.312, 0.062, 0.168, 2025),
    ('Blake Snell',           605483, 88.9, 0.281, 0.098, 0.167, 2025),
    ('Spencer Schwellenbach', 680885, 91.2, 0.246, 0.039, 0.146, 2025),
    ('Max Fried',             608331, 88.0, 0.219, 0.079, 0.111, 2026),
    ('Tyler Glasnow',         607192, 90.3, 0.326, 0.083, 0.132, 2026),
]

def fetch_milb(mlbam):
    today = date.today().isoformat()
    url = (
        "https://baseballsavant.mlb.com/statcast_search/csv?"
        "all=true&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
        "&hfGT=R%7CPO%7CS%7C&hfC=&hfSea=2026%7C&hfSit="
        "&player_type=pitcher&hfOuts=&opponent=&pitcher_throws="
        "&batter_stands=&hfSA=&game_date_gt=2026-03-01&game_date_lt=" + today +
        "&hfInfield=&team=&position=&hfOutfield=&hfRO=&home_road=&hfFlag="
        "&hfPull=&metric_1=&hfInn=&min_pitches=0&min_results=0&group_by=name"
        "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
        f"&min_pas=0&pitchers_lookup%5B%5D={mlbam}&minors=true&type=details"
    )
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return pd.read_csv(io.BytesIO(data))
    except Exception as e:
        print(f"  ERROR fetching {mlbam}: {e}")
        return pd.DataFrame()

def fb_velo(df):
    if 'pitch_type' not in df.columns: return None
    fb = df[df['pitch_type'].isin(['FF','FT','SI'])]
    if fb.empty: return None
    v = fb['release_speed'].mean()
    return float(v) if pd.notna(v) else None

def k_pct(df):
    pa = df[df['events'].notna() & (df['events'] != '')]
    if pa.empty: return None
    return (pa['events']=='strikeout').mean()

def bb_pct(df):
    pa = df[df['events'].notna() & (df['events'] != '')]
    if pa.empty: return None
    return ((pa['events']=='walk') | (pa['events']=='hit_by_pitch')).mean()

def swstr_pct(df):
    if df.empty: return None
    return df['description'].isin(['swinging_strike','swinging_strike_blocked','foul_tip']).mean()

def verdict(velo_d, swstr_d, k_d, n_pitches):
    if n_pitches < 30:
        return 'WORKLOAD-ONLY'
    if velo_d is None:
        return 'NO DATA'
    if velo_d >= 1.0 and (swstr_d or 0) >= 0.01 and (k_d or 0) >= 0:
        return 'AHEAD'
    if abs(velo_d) <= 1.0 and abs(swstr_d or 0) <= 0.015:
        return 'ON TRACK'
    if velo_d < -1.0 or (swstr_d or 0) < -0.02:
        return 'BEHIND'
    return 'MIXED'

print(f"{'Player':25s} {'Outings':>7s} {'Pit':>5s} {'LastMiLB':>11s} {'FBvelo':>7s} {'Δvelo':>7s} {'K%':>5s} {'BB%':>5s} {'SwStr%':>7s} {'Verdict':12s}")
print('-'*120)

rows = []
for name, mlbam, p_velo, p_k, p_bb, p_swstr, base_yr in PLAYERS:
    df = fetch_milb(mlbam)
    if df.empty:
        rows.append((name, 0, 0, '—', None, None, None, None, None, 'NO DATA'))
        print(f"{name:25s} {'0':>7s} {'0':>5s} {'—':>11s} {'—':>7s} {'—':>7s} {'—':>5s} {'—':>5s} {'—':>7s} {'NO DATA':12s}")
        continue
    n_pit = len(df)
    n_outings = df['game_date'].nunique() if 'game_date' in df.columns else 0
    last_date = df['game_date'].max() if 'game_date' in df.columns else '—'
    v = fb_velo(df); s = swstr_pct(df); k = k_pct(df); b = bb_pct(df)
    velo_d = (v - p_velo) if v is not None else None
    swstr_d = (s - p_swstr) if s is not None else None
    k_d = (k - p_k) if k is not None else None
    bb_d = (b - p_bb) if b is not None else None
    vd = verdict(velo_d, swstr_d, k_d, n_pit)
    rows.append((name, n_outings, n_pit, last_date, v, velo_d, k, bb_d, swstr_d, vd))
    print(f"{name:25s} {n_outings:>7d} {n_pit:>5d} {str(last_date):>11s} "
          f"{f'{v:.1f}' if v else '—':>7s} {f'{velo_d:+.1f}' if velo_d is not None else '—':>7s} "
          f"{f'{k*100:.1f}' if k is not None else '—':>5s} {f'{b*100:.1f}' if b is not None else '—':>5s} "
          f"{f'{s*100:.1f}' if s is not None else '—':>7s} {vd:12s}")

# Workload curve per pitcher
print()
print('=== Workload curve per pitcher ===')
for name, mlbam, *_ in PLAYERS:
    df = fetch_milb(mlbam)
    if df.empty or 'game_date' not in df.columns:
        continue
    per_game = df.groupby('game_date').size().sort_index()
    if per_game.empty: continue
    print(f'\n{name}:')
    for d, n in per_game.items():
        print(f'  {d}: {n} pitches')
