"""sp_velocity_trend.py — rolling-5-start fastball velocity trend per SP.

For each SP, compute mean fastball release_speed per start (FF/SI/FT only),
then a rolling-5-start window. Compare last-5-start mean to career mean to
flag declining velocity (early warning for injury / mechanical breakdown).

Output: data/outputs/sp_velocity_trend.csv
  pitcher, player_name, last5_velo, career_velo, velo_drop_mph,
  starts_n, last_start_date, alert
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

FASTBALL = {'FF', 'SI', 'FT', 'FA'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in range(2023, 2027):
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=['game_pk', 'game_date', 'pitcher', 'pitch_type', 'release_speed', 'inning'])
        # SP-only proxy: pitchers who appeared in inning 1
        sp_ids = df[df['inning'] == 1].groupby('pitcher')['game_pk'].nunique()
        sp_ids = sp_ids[sp_ids >= 3].index  # at least 3 inning-1 games => SP
        df = df[df['pitcher'].isin(sp_ids) & df['pitch_type'].isin(FASTBALL) & df['release_speed'].notna()]
        if df.empty:
            continue
        agg = df.groupby(['pitcher', 'game_pk', 'game_date'], as_index=False)['release_speed'].agg(['mean', 'count'])
        agg.columns = ['pitcher', 'game_pk', 'game_date', 'velo', 'fb_pitches']
        agg = agg[agg['fb_pitches'] >= 10]  # exclude opener / cameo
        frames.append(agg)
    if not frames:
        print('  no data'); return
    full = pd.concat(frames, ignore_index=True)
    full['game_date'] = pd.to_datetime(full['game_date'])
    full = full.sort_values(['pitcher', 'game_date'])

    rows = []
    for pid, sub in full.groupby('pitcher'):
        if len(sub) < 8:
            continue
        career_velo = sub['velo'].mean()
        last5 = sub.tail(5)
        last5_velo = last5['velo'].mean()
        drop = last5_velo - career_velo  # negative = declining
        # 2026 starts in particular
        sub_2026 = sub[sub['game_date'].dt.year == 2026]
        last_2026_velo = sub_2026.tail(5)['velo'].mean() if len(sub_2026) >= 1 else np.nan
        rows.append({
            'pitcher': int(pid),
            'starts_n': int(len(sub)),
            'starts_2026': int(len(sub_2026)),
            'career_velo': round(career_velo, 2),
            'last5_velo': round(last5_velo, 2),
            'last5_2026_velo': round(last_2026_velo, 2) if not np.isnan(last_2026_velo) else None,
            'velo_drop_mph': round(drop, 2),
            'last_start_date': sub['game_date'].max().strftime('%Y-%m-%d'),
        })
    out = pd.DataFrame(rows)
    out['alert'] = np.where(out['velo_drop_mph'] <= -1.0, 'DECLINING',
                    np.where(out['velo_drop_mph'] >= 1.0, 'GAINING', 'stable'))
    # Attach names: master id->name map (built from FG projection CSVs)
    name_map_path = CACHE / 'mlb_player_id_name.csv'
    if name_map_path.exists():
        nm = pd.read_csv(name_map_path)
        nm['pitcher'] = pd.to_numeric(nm['mlb_id'], errors='coerce').astype('Int64')
        nm = nm[['pitcher', 'name']].rename(columns={'name': 'player_name'}).dropna()
        out = out.merge(nm, on='pitcher', how='left')
    else:
        out['player_name'] = None
    out = out.sort_values('velo_drop_mph')

    fname = OUT / 'sp_velocity_trend.csv'
    out.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(out)} SPs)')
    print('\n  Top 10 DECLINING velocity (red flags):')
    decl = out[out['alert'] == 'DECLINING'].head(10)
    print(decl[['player_name', 'starts_n', 'career_velo', 'last5_velo', 'velo_drop_mph', 'last_start_date']].to_string(index=False))
    print('\n  Top 5 GAINING velocity (positive signal):')
    gain = out[out['alert'] == 'GAINING'].head(5)
    print(gain[['player_name', 'starts_n', 'career_velo', 'last5_velo', 'velo_drop_mph', 'last_start_date']].to_string(index=False))


if __name__ == '__main__':
    main()
