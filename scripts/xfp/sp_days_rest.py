"""sp_days_rest.py — per-SP career fp/start by days rest before the start.

For each SP, identify their starts and compute days between consecutive
starts. Bucket: 4-day (short rest), 5-day (typical), 6+ day (extra rest).
Per-pitcher fp/start by bucket reveals who benefits from extra rest vs
who can pitch effectively on short rest.

Useful for: weekly SP slot decisions, especially streamers picking
between two arms based on whose schedule has more 6-day rest gaps.

Output: data/outputs/sp_days_rest.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from plv_clone.projections import PROJECTIONS
import numpy as np

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

OUT_EVENTS = {
    'strikeout', 'strikeout_double_play', 'field_out', 'grounded_into_double_play',
    'sac_fly', 'sac_bunt', 'force_out', 'double_play', 'triple_play',
    'fielders_choice_out', 'other_out',
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
}
TWO_OUT_EVENTS = {'grounded_into_double_play', 'double_play'}
PA_EVENTS = {
    'single', 'double', 'triple', 'home_run', 'walk', 'intent_walk',
    'hit_by_pitch', 'strikeout', 'strikeout_double_play',
    'field_out', 'force_out', 'grounded_into_double_play', 'sac_fly', 'sac_bunt',
    'fielders_choice', 'fielders_choice_out', 'double_play', 'triple_play',
    'field_error', 'catcher_interf',
}


def _starters(year):
    p = CACHE / f'statcast_{year}.parquet'
    if not p.exists(): return pd.DataFrame()
    df = pd.read_parquet(p, columns=['game_pk','inning','inning_topbot','pitcher','at_bat_number'])
    df = df[df['inning'] == 1].sort_values(['game_pk','inning_topbot','at_bat_number'])
    s = df.groupby(['game_pk','inning_topbot'])['pitcher'].first().reset_index()
    s.columns = ['game_pk','inning_topbot','starter_id']
    return s


def sp_starts_with_fp(years=range(2018, 2026)) -> pd.DataFrame:
    frames = []
    for year in years:
        if year == 2020: continue
        path = CACHE / f'statcast_{year}.parquet'
        if not path.exists(): continue
        df = pd.read_parquet(path, columns=['game_pk','game_date','pitcher','inning','inning_topbot',
                                              'events','bat_score','post_bat_score','at_bat_number'])
        s = _starters(year)
        if s.empty: continue
        df = df.merge(s, on=['game_pk','inning_topbot'], how='left')
        df = df[df['pitcher'] == df['starter_id']].copy()
        if df.empty: continue
        ev = df['events'].fillna('')
        df['k'] = ev.isin({'strikeout','strikeout_double_play'}).astype(int)
        df['bb'] = ev.isin({'walk','intent_walk'}).astype(int)
        df['hbp'] = (ev == 'hit_by_pitch').astype(int)
        df['h'] = ev.isin({'single','double','triple','home_run'}).astype(int)
        df['outs'] = ev.isin(OUT_EVENTS).astype(int)
        df.loc[ev.isin(TWO_OUT_EVENTS),'outs'] = 2
        df['is_pa_end'] = (ev != '') & ev.isin(PA_EVENTS)
        runs = (pd.to_numeric(df['post_bat_score'],errors='coerce')
                - pd.to_numeric(df['bat_score'],errors='coerce')).clip(lower=0)
        df['er'] = runs.where(df['is_pa_end'], 0)
        per = df.groupby(['game_pk','game_date','pitcher'], as_index=False).agg(
            k=('k','sum'), bb=('bb','sum'), hbp=('hbp','sum'),
            h=('h','sum'), outs=('outs','sum'), er=('er','sum'))
        per['ip'] = per['outs']/3
        per['fp'] = per['k'] + per['ip']*3.3 - per['h'] - 2*per['er'] - per['bb'] - per['hbp']
        per['game_date'] = pd.to_datetime(per['game_date'])
        per = per.sort_values(['pitcher','game_date'])
        per['days_rest'] = per.groupby('pitcher')['game_date'].diff().dt.days
        frames.append(per)
    if not frames: return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def aggregate(starts: pd.DataFrame) -> pd.DataFrame:
    starts = starts.dropna(subset=['days_rest']).copy()
    def bucket(d):
        if d <= 4: return 'short(<=4)'
        if d == 5: return '5-day'
        if d == 6: return '6-day'
        return '7+ day'
    starts['rest_bucket'] = starts['days_rest'].apply(bucket)
    g = starts.groupby(['pitcher','rest_bucket'], as_index=False).agg(
        gs=('game_pk','count'), fp_total=('fp','sum'))
    g['fp_per_start'] = g['fp_total']/g['gs']
    pivot = g.pivot_table(index='pitcher', columns='rest_bucket',
                          values=['gs','fp_per_start']).reset_index()
    pivot.columns = [f'{m}_{b}' if b else m for m, b in pivot.columns]
    overall = starts.groupby('pitcher', as_index=False).agg(
        total_gs=('game_pk','count'), total_fp=('fp','sum'))
    overall['annual_rate'] = overall['total_fp']/overall['total_gs']
    overall = overall[overall['total_gs'] >= 30]
    out = pivot.merge(overall[['pitcher','annual_rate','total_gs']], on='pitcher', how='inner')
    # Add lift columns
    for b in ['short(<=4)','5-day','6-day','7+ day']:
        col = f'fp_per_start_{b}'
        if col in out.columns:
            out[f'lift_{b}_pct'] = ((out[col] - out['annual_rate'])/out['annual_rate'].replace(0,np.nan)*100).round(1)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    starts = sp_starts_with_fp()
    if starts.empty:
        print('  no data'); return
    agg = aggregate(starts)
    rp = PROJECTIONS.rp3()
    agg = agg.merge(rp[['pitcher','player_name','rank']], on='pitcher', how='left')
    out = OUT / 'sp_days_rest.csv'
    agg.to_csv(out, index=False)
    print(f'  wrote {out} ({len(agg)} SPs)')


if __name__ == '__main__':
    main()
