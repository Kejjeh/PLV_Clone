"""pl_feature_correlation.py — what features actually drive the PL ranking?

For the PL Top 50 closers we have model coverage on, regress / correlate each
candidate feature with PL rank. This tells us which signals PL is implicitly
weighting — and helps identify features we should consider adding to xFP.

CRITICAL: matching PL is not the goal. Predicting end-of-season FP is. So the
output also reports each feature's correlation with our model's RoS xFP — if
a feature matches PL strongly but doesn't predict our FP target, it's likely
PL noise, not signal.
"""
from __future__ import annotations
import json, re, unicodedata
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from plv_clone.paths import ROOT
PROJ = pd.read_csv(ROOT / 'data/outputs/xfp_rprs1_projections.csv')
PROJ['ros_rank'] = PROJ['xfp_ros'].rank(ascending=False, method='min')

from plv_clone.utils.name_match import safe_name_key as norm  # noqa: E402  OWNER — never re-derive
LOOKUP = {norm(r['name_api']): r for _, r in PROJ.iterrows()}

PL_TOP50 = [
    (1, 'Mason Miller'), (2, 'Jhoan Duran'), (3, 'Bryan Baker'),
    (4, 'Louis Varland'), (5, 'Aroldis Chapman'), (6, 'Daniel Palencia'),
    (7, 'Cade Smith'), (8, 'Andres Munoz'), (9, 'Devin Williams'),
    (10, 'Jacob Latz'), (11, "Riley O'Brien"), (12, 'Paul Sewald'),
    (13, 'David Bednar'), (14, 'Raisel Iglesias'), (15, 'Jack Perkins'),
    (16, 'Abner Uribe'), (17, 'Tanner Scott'), (18, 'Kenley Jansen'),
    (19, 'Seranthony Dominguez'), (20, 'Lucas Erceg'), (21, 'Caleb Kilian'),
    (22, 'Gregory Soto'), (23, 'Ryan Zeferjahn'), (24, 'Gus Varland'),
    (25, 'Rico Garcia'), (26, 'Trevor Megill'), (27, 'Jeff Hoffman'),
    (28, 'Robert Suarez'), (29, 'Graham Ashcraft'), (30, 'Tony Santillan'),
    (31, 'Kyle Finnegan'), (32, 'Keaton Winn'), (33, 'Alex Vesia'),
    (34, 'Tyler Phillips'), (35, 'Bryan King'), (36, 'Sam Bachman'),
    (37, 'Dennis Santana'), (38, 'Anthony Nunez'), (39, 'Blake Treinen'),
    (40, 'Luke Weaver'), (41, 'Camilo Doval'), (42, 'Enyel De Los Santos'),
    (43, 'Daniel Lynch IV'), (44, 'Ryan Walker'), (45, 'Mason Montgomery'),
    (46, 'Grant Taylor'), (47, 'Juan Morillo'), (48, 'Erik Sabrowski'),
    (49, 'Dylan Lee'), (50, 'Kirby Yates'),
]

# Pull current 2026 counting stats for sv_now / hld_now / gf_now
cnt = json.loads((ROOT / 'data/research/xfp_cache/pitcher_counting_stats_2026.json').read_text())
cnt_df = pd.DataFrame(cnt)
def parse_ip(v):
    if v is None or pd.isna(v): return np.nan
    s = str(v)
    if '.' in s:
        whole, frac = s.split('.', 1)
        return float(whole) + (1/3 if frac.startswith('1') else 2/3 if frac.startswith('2') else 0)
    return float(v)
cnt_df['ip'] = cnt_df['inningsPitched'].map(parse_ip)
cnt_df['sv_pct'] = cnt_df['saves'] / cnt_df['gamesPitched'].replace(0, np.nan)
cnt_df['gf_pct'] = cnt_df['gamesFinished'] / cnt_df['gamesPitched'].replace(0, np.nan)
cnt_df['k_pct_2026'] = cnt_df['strikeOuts'] / cnt_df['battersFaced'].replace(0, np.nan)
cnt_df['bb_pct_2026'] = cnt_df['baseOnBalls'] / cnt_df['battersFaced'].replace(0, np.nan)
cnt_df['ip_per_app'] = cnt_df['ip'] / cnt_df['gamesPitched'].replace(0, np.nan)
cnt_df['sv_plus_hld'] = cnt_df['saves'] + cnt_df['holds']
CNT_LOOKUP = {int(r['pitcher']): r for _, r in cnt_df.iterrows()}

# Build feature table
rows = []
for pl_rank, name in PL_TOP50:
    rec = LOOKUP.get(norm(name))
    if rec is None:
        continue
    pid = int(rec['pitcher'])
    cnt_row = CNT_LOOKUP.get(pid)
    rows.append({
        'pl_rank': pl_rank,
        'name': name,
        'model_ros_rank': float(rec['ros_rank']) if pd.notna(rec['ros_rank']) else np.nan,
        'model_ros_fp': float(rec['xfp_ros']) if pd.notna(rec['xfp_ros']) else np.nan,
        # In-season features
        'sv_now': float(cnt_row.get('saves')) if cnt_row is not None else np.nan,
        'hld_now': float(cnt_row.get('holds')) if cnt_row is not None else np.nan,
        'sv_plus_hld_now': float(cnt_row.get('sv_plus_hld')) if cnt_row is not None else np.nan,
        'sv_pct_now': float(cnt_row.get('sv_pct')) if cnt_row is not None else np.nan,
        'gf_pct_now': float(cnt_row.get('gf_pct')) if cnt_row is not None else np.nan,
        'g_now': float(cnt_row.get('gamesPitched')) if cnt_row is not None else np.nan,
        'ip_now': float(cnt_row.get('ip')) if cnt_row is not None else np.nan,
        'ip_per_app_now': float(cnt_row.get('ip_per_app')) if cnt_row is not None else np.nan,
        'k_pct_now': float(cnt_row.get('k_pct_2026')) if cnt_row is not None else np.nan,
        'era_now': float(cnt_row.get('era')) if cnt_row is not None else np.nan,
        'whip_now': float(cnt_row.get('whip')) if cnt_row is not None else np.nan,
        # Statcast skill from rolling
        'swstr_pct_to': float(rec.get('swstr_pct_to', np.nan)) if 'swstr_pct_to' in PROJ.columns else np.nan,
        'avg_velo_to': float(rec.get('avg_velo_to', np.nan)) if 'avg_velo_to' in PROJ.columns else np.nan,
        # Lag features
        'sv_lag1': float(rec.get('sv_lag1', np.nan)),
        'hld_lag1': float(rec.get('hld_lag1', np.nan)),
        'fp_per_g_lag1': float(rec.get('fp_per_g_lag1', np.nan)),
        'role_lag1': rec.get('role_lag1') or '—',
    })

df = pd.DataFrame(rows)
print(f'Coverage: {len(df)} of 50 PL closers in model\n')

# Compute correlations: feature vs PL rank (lower = better) AND feature vs model RoS rank
features = ['sv_now', 'hld_now', 'sv_plus_hld_now', 'sv_pct_now', 'gf_pct_now',
            'g_now', 'ip_now', 'ip_per_app_now', 'k_pct_now', 'era_now', 'whip_now',
            'swstr_pct_to', 'avg_velo_to',
            'sv_lag1', 'hld_lag1', 'fp_per_g_lag1']

print(f'{"Feature":<22} {"r vs PL rank":<14} {"r vs Model rank":<16} {"PL > Model?":<14}')
print('  (negative ρ means feature is HIGHER for higher PL/model ranking — i.e. predictive)')
print('-' * 80)
results = []
for f in features:
    sub = df.dropna(subset=[f])
    if len(sub) < 20:
        continue
    rho_pl, _ = spearmanr(sub['pl_rank'], sub[f])
    rho_mine, _ = spearmanr(sub['model_ros_rank'], sub[f])
    results.append({
        'feature': f, 'rho_pl': rho_pl, 'rho_mine': rho_mine,
        'pl_minus_mine': abs(rho_pl) - abs(rho_mine), 'n': len(sub)
    })
results = sorted(results, key=lambda r: r['rho_pl'])  # most negative first = strongest PL predictor
for r in results:
    diff_str = f'{r["pl_minus_mine"]:+.3f}'
    flag = ' ← PL leans on this' if r['pl_minus_mine'] > 0.1 else ''
    print(f'{r["feature"]:<22} {r["rho_pl"]:+.3f} (n={r["n"]:>2})   {r["rho_mine"]:+.3f}            {diff_str:<10s}{flag}')

# Role distribution: does PL favor specific prior_role?
print('\n--- Average PL rank by prior role ---')
print(df.groupby('role_lag1')['pl_rank'].agg(['mean', 'count']).round(1).to_string())
