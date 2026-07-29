"""validate_platoon.py — does platoon_factor correlate with FP/start residuals?"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
ROOT = Path('c:/Users/Joshua/plv_clone')

splits = pd.read_csv(ROOT/'data/research/xfp_cache/pitcher_splits.csv')
team_h = pd.read_csv(ROOT/'data/research/xfp_cache/team_handedness.csv')

recent = splits[splits['year'].isin([2022,2023,2024])].copy()
for c in ['tbf_vs_L','tbf_vs_R','xwoba_vs_L','xwoba_vs_R']:
    recent[c] = pd.to_numeric(recent[c], errors='coerce').fillna(0)
recent['wv_L'] = recent['xwoba_vs_L'] * recent['tbf_vs_L']
recent['wv_R'] = recent['xwoba_vs_R'] * recent['tbf_vs_R']
agg = recent.groupby(['pitcher','p_throws']).agg(
    tbf_L=('tbf_vs_L','sum'), tbf_R=('tbf_vs_R','sum'),
    wv_L=('wv_L','sum'), wv_R=('wv_R','sum')
).reset_index()
agg['xwoba_vs_L'] = agg['wv_L']/agg['tbf_L'].replace(0,np.nan)
agg['xwoba_vs_R'] = agg['wv_R']/agg['tbf_R'].replace(0,np.nan)
agg = agg[(agg['tbf_L']+agg['tbf_R'])>=200]  # need solid sample
agg['expected_avg'] = 0.30*agg['xwoba_vs_L'] + 0.70*agg['xwoba_vs_R']

sc = pd.read_parquet(ROOT/'data/research/xfp_cache/statcast_2025.parquet',
                     columns=['game_pk','pitcher','inning','inning_topbot','events',
                              'home_team','away_team','bat_score','fld_score',
                              'post_bat_score','post_fld_score','at_bat_number','pitch_number'])
sc['inning'] = pd.to_numeric(sc['inning'], errors='coerce')
starts = sc[sc['inning']==1].groupby(['game_pk','inning_topbot'])['pitcher'].first().reset_index().rename(columns={'pitcher':'starter_id'})
sp = sc.merge(starts, on=['game_pk','inning_topbot'], how='left')
sp = sp[sp['pitcher']==sp['starter_id']].copy()
ev = sp['events'].fillna('')
sp['is_k'] = ev=='strikeout'
sp['is_bb'] = ev=='walk'
sp['is_hbp'] = ev=='hit_by_pitch'
sp['is_h'] = ev.isin({'single','double','triple','home_run'})
sp['is_pa_end'] = ev != ''
out_ev = {'strikeout','field_out','grounded_into_double_play','sac_fly','sac_bunt','force_out',
          'double_play','triple_play','fielders_choice_out','caught_stealing_2b',
          'caught_stealing_3b','caught_stealing_home','other_out'}
sp['outs'] = ev.isin(out_ev).astype(int)
sp.loc[ev.isin(['grounded_into_double_play','double_play']),'outs']=2
runs = (pd.to_numeric(sp['post_bat_score'],errors='coerce')-pd.to_numeric(sp['bat_score'],errors='coerce')).clip(lower=0)
sp['runs_play'] = runs.where(sp['is_pa_end'], 0)
sp['bat_team'] = np.where(sp['inning_topbot']=='Top', sp['away_team'], sp['home_team'])
per_start = sp.groupby(['game_pk','pitcher','bat_team']).agg(
    k=('is_k','sum'), bb=('is_bb','sum'), hbp=('is_hbp','sum'), h=('is_h','sum'),
    outs=('outs','sum'), er=('runs_play','sum')
).reset_index()
per_start['ip'] = per_start['outs']/3
per_start['fp'] = per_start['k'] + per_start['ip']*3.3 - per_start['h'] - 2*per_start['er'] - per_start['bb'] - per_start['hbp']

team25 = team_h[team_h['year']==2025][['team_abbr','pct_lhb','pct_rhb']]
m = per_start.merge(agg[['pitcher','xwoba_vs_L','xwoba_vs_R','expected_avg']], on='pitcher', how='inner')
m = m.merge(team25.rename(columns={'team_abbr':'bat_team'}), on='bat_team', how='left')
m = m.dropna(subset=['xwoba_vs_L','xwoba_vs_R','pct_lhb'])
m['expected_vs_team'] = m['pct_lhb']*m['xwoba_vs_L'] + m['pct_rhb']*m['xwoba_vs_R']
m['platoon_factor'] = m['expected_vs_team'] / m['expected_avg']
m = m[m['fp'].notna() & (m['outs']>=12)]
print(f'2025 SP starts evaluated: {len(m)}')

pitcher_avg = m.groupby('pitcher')['fp'].mean().rename('pitcher_avg_fp').reset_index()
m = m.merge(pitcher_avg, on='pitcher')
m['residual'] = m['fp'] - m['pitcher_avg_fp']
r = m['platoon_factor'].corr(m['residual'])
print(f'cor(platoon_factor, residual_vs_pitcher_avg): {r:+.4f}')
print('  (negative = harder platoon → lower FP, expected)')

m['pf_bucket'] = pd.qcut(m['platoon_factor'], q=4, duplicates='drop',
                          labels=['Easy','Medium-','Medium+','Hard'])
print('Mean residual by platoon bucket:')
print(m.groupby('pf_bucket', observed=True)['residual'].agg(['mean','std','count']).round(2).to_string())

# More direct: gap between Easy and Hard
easy_mean = m[m['pf_bucket']=='Easy']['residual'].mean()
hard_mean = m[m['pf_bucket']=='Hard']['residual'].mean()
print(f'\nEasy vs Hard platoon: mean FP residual gap = {easy_mean - hard_mean:+.2f} FP/start')
