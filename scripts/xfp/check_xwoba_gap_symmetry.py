"""check_xwoba_gap_symmetry.py — does negative gap (overperformer, due
to regress DOWN) work as well as positive gap (underperformer, due UP)?
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'

TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
TEST_YEARS = [2024, 2025]


def main():
    panel = pd.read_csv(RES / 'drift_panel_v5_hitters.csv')

    # Rebuild xwoba_gap (drop NaN)
    p = panel.dropna(subset=['xwoba_gap', 'baseline_fp_pa', 'post_fp_pa']).copy()
    if 'xwoba_gap' not in p.columns:
        print('panel missing xwoba_gap — re-run validate_drift_v5_fixes first')
        return

    # Hmm, the saved drift_panel_v5_hitters.csv may not have xwoba_gap yet.
    # Try to reload from the corrected sample.
    # Easier: re-merge here.
    rh3 = None
    from scripts.xfp.validate_drift_v5_fixes import load_year_full
    CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
    print('Computing xwoba_gap inline...')
    feats = []
    for y in TRAIN_YEARS + TEST_YEARS:
        df = load_year_full(y)
        if df.empty: continue
        season_start = df['game_date'].min()
        cutoff = season_start + pd.Timedelta(weeks=6)
        pre = df[df['game_date'] < cutoff]
        pre_pa = pre[pre['is_pa']==1].groupby('batter').size()
        qual = pre_pa[pre_pa>=50].index
        for bid in qual:
            pb = pre[pre['batter'] == bid]
            if 'estimated_woba_using_speedangle' not in pb.columns: continue
            bbe = pb[pb['estimated_woba_using_speedangle'].notna()]
            act = pb[pb['woba_denom'] > 0]
            if len(bbe) >= 30 and len(act) >= 30:
                xw = float(bbe['estimated_woba_using_speedangle'].mean())
                aw = float(act['woba_value'].sum() / act['woba_denom'].sum())
                feats.append({'year': y, 'batter': bid, 'xwoba_gap': xw - aw})
    fd = pd.DataFrame(feats)
    merged = panel.merge(fd, on=['year','batter'], how='left', suffixes=('_old','_new'))
    if 'xwoba_gap_new' in merged.columns:
        merged['xwoba_gap'] = merged['xwoba_gap_new']
    p = merged.dropna(subset=['xwoba_gap', 'baseline_fp_pa', 'post_fp_pa']).copy()
    print(f'Sample: {len(p)} hitter-years (with xwoba_gap)')
    print(f'  xwoba_gap range: {p["xwoba_gap"].min():.4f} to {p["xwoba_gap"].max():.4f}')
    print(f'  xwoba_gap median: {p["xwoba_gap"].median():.4f}')

    # Bucket the xwoba gap and check post_fp_pa - baseline_fp_pa per bucket
    p['gap_bucket'] = pd.qcut(p['xwoba_gap'], q=5, labels=['Q1_overperf', 'Q2', 'Q3_neutral', 'Q4', 'Q5_underperf'])
    p['delta_fp'] = p['post_fp_pa'] - p['baseline_fp_pa']

    print('\n=== Post-cutoff regression by xwoba_gap quintile ===')
    print(f'{"BUCKET":<14s} {"N":>5s} {"mean_gap":>9s} {"baseline":>9s} {"post":>9s} {"delta":>9s}')
    for b, sub in p.groupby('gap_bucket', observed=True):
        if pd.isna(b): continue
        print(f'  {str(b):<14s} {len(sub):>5d} {sub["xwoba_gap"].mean():>+9.4f} '
              f'{sub["baseline_fp_pa"].mean():>9.4f} {sub["post_fp_pa"].mean():>9.4f} '
              f'{sub["delta_fp"].mean():>+9.4f}')

    # Symmetric fit: fit on positive-only sample, then negative-only
    print('\n=== Positive vs Negative gap separately ===')
    p_pos = p[p['xwoba_gap'] > 0].copy()
    p_neg = p[p['xwoba_gap'] < 0].copy()
    print(f'  Positive (n={len(p_pos)}): mean gap = +{p_pos["xwoba_gap"].mean():.4f}, mean delta_fp = {p_pos["delta_fp"].mean():+.4f}')
    print(f'  Negative (n={len(p_neg)}): mean gap = {p_neg["xwoba_gap"].mean():.4f}, mean delta_fp = {p_neg["delta_fp"].mean():+.4f}')

    # Fit on full sample, get coefficient
    train_full = p[p['year'].isin(TRAIN_YEARS)].dropna(subset=['xwoba_gap', 'baseline_fp_pa', 'post_fp_pa'])
    X = np.column_stack([np.ones(len(train_full)),
                          train_full['baseline_fp_pa'].values,
                          train_full['xwoba_gap'].values])
    y = train_full['post_fp_pa'].values
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    print(f'\nOLS fit (full train sample, both positive and negative gaps):')
    print(f'  α: {coefs[0]:+.4f}')
    print(f'  β_baseline: {coefs[1]:+.4f}')
    print(f'  β_xwoba_gap: {coefs[2]:+.4f}  (per unit of gap)')

    # Fit on positive-only and negative-only — see if coefficients are similar
    for sign_name, sub in [('positive', train_full[train_full['xwoba_gap'] > 0]),
                              ('negative', train_full[train_full['xwoba_gap'] < 0])]:
        if len(sub) < 50: continue
        Xs = np.column_stack([np.ones(len(sub)), sub['baseline_fp_pa'].values, sub['xwoba_gap'].values])
        cs, *_ = np.linalg.lstsq(Xs, sub['post_fp_pa'].values, rcond=None)
        print(f'  Fit on {sign_name}-only (n={len(sub)}): β_xwoba_gap = {cs[2]:+.4f}')

    # Per-bucket symmetry: does each bucket's delta_fp scale linearly with gap?
    bucket_summary = p.groupby('gap_bucket', observed=True).agg(
        mean_gap=('xwoba_gap', 'mean'),
        mean_delta_fp=('delta_fp', 'mean'),
        n=('xwoba_gap', 'size'),
    ).reset_index()
    print('\n  Linear fit through bucket means:')
    slope, intercept = np.polyfit(bucket_summary['mean_gap'], bucket_summary['mean_delta_fp'], 1)
    print(f'    delta_fp = {slope:+.4f} * gap + {intercept:+.4f}')
    print(f'    R² = {np.corrcoef(bucket_summary["mean_gap"], bucket_summary["mean_delta_fp"])[0,1]**2:.4f}')


if __name__ == '__main__':
    main()
