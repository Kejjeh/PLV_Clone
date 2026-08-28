"""monitor_drift.py — production calibration check on 2026 actuals.

For each production model (RH3, RP3, RP-RS2), compare its 2026 projections to
2026 actual fantasy points so far. Outputs:
  - Cohort-level r and MAE on the 2026 partial-season cohort
  - Per-bucket calibration table (predicted vs actual mean by quartile)
  - Drift indicator: is 2026 r within ±0.10 of training cross-year r?

If the drift indicator fires, the production model may need retraining or
substrate refresh. Run weekly during the season.

Output: prints to stdout + writes data/research/xfp_cache/drift_report_<date>.txt
"""
from __future__ import annotations
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from plv_clone.fantasy.scoring import pitcher_fp
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'


# ─── Calibration metric helpers ──────────────────────────────────────────────

def calibration(preds, acts, label):
    if len(preds) < 10:
        return f'  {label}: insufficient data (n={len(preds)})'
    r = float(np.corrcoef(preds, acts)[0, 1]) if np.std(preds) > 0 and np.std(acts) > 0 else np.nan
    mae = float(np.mean(np.abs(preds - acts)))
    bias = float(np.mean(preds - acts))
    df = pd.DataFrame({'pred': preds, 'act': acts})
    df['bucket'] = pd.qcut(df['pred'], q=4, duplicates='drop', labels=['Q1','Q2','Q3','Q4'])
    bucket_means = df.groupby('bucket', observed=False).agg(pred_mean=('pred','mean'),
                                                             act_mean=('act','mean'),
                                                             n=('pred','count'))
    out = []
    out.append(f'  {label} — n={len(preds)} | r={r:.4f} | MAE={mae:.3f} | bias={bias:+.3f} (pred − act)')
    out.append(f'    Calibration by predicted quartile:')
    for q, row in bucket_means.iterrows():
        gap = row['pred_mean'] - row['act_mean']
        out.append(f'      {q}: pred={row["pred_mean"]:.3f}  act={row["act_mean"]:.3f}  gap={gap:+.3f}  n={int(row["n"])}')
    return '\n'.join(out), {'r': r, 'mae': mae, 'bias': bias, 'n': len(preds)}


def check_drift(name, current_r, training_r, current_bias=None,
                bias_threshold=0.10, q4_gap=None, q4_threshold=0.20):
    """Drift heuristic — flag based on:
      - sign of bias (model systematically under/over-predicts)
      - Q4 gap (model mis-calibrated for top players, the cohort that matters)
    Comparing in-season r vs cross-year training r is misleading (in-season is
    naturally higher because partial-season data is more predictive). Use bias
    and bucket-calibration as the drift indicator instead.
    """
    parts = []
    if pd.notna(current_r):
        ref = f'training cross-year r={training_r:.3f}' if training_r is not None else ''
        parts.append(f'  {name} 2026 r={current_r:.3f}  ({ref})')
    flags = []
    if current_bias is not None and not pd.isna(current_bias):
        if abs(current_bias) > bias_threshold:
            flags.append(f'BIAS={current_bias:+.3f} (>{bias_threshold:.2f})')
    if q4_gap is not None and not pd.isna(q4_gap):
        if abs(q4_gap) > q4_threshold:
            flags.append(f'TOP-QUARTILE GAP={q4_gap:+.3f} (>{q4_threshold:.2f})')
    if flags:
        parts.append(f'    DRIFT: {", ".join(flags)}  → investigate substrate / retrain')
    else:
        parts.append(f'    OK — calibration within tolerances')
    return '\n'.join(parts)


# ─── RH3 (hitter RoS) drift ──────────────────────────────────────────────────

def check_rh3(report_lines):
    proj_path = ROOT / 'data/outputs/xfp_rh3_projections.csv'
    multiyr_path = CACHE / 'hitters_multiyr_2015_2026.csv'
    bundle_path = ROOT / 'data/models/xfp_h2_pipeline.pkl'
    if not (proj_path.exists() and multiyr_path.exists()):
        report_lines.append('RH3: missing files; skip')
        return
    proj = pd.read_csv(proj_path)
    multiyr = pd.read_csv(multiyr_path)
    actuals_26 = multiyr[multiyr['year'] == 2026][['batter','fp_per_pa_actual','pa']].rename(
        columns={'fp_per_pa_actual':'actual_per_pa', 'pa':'pa_2026'})
    merged = proj.merge(actuals_26, on='batter', how='inner')
    merged = merged[merged['pa_2026'] >= 80]  # Need decent sample for actual
    if merged.empty:
        report_lines.append('RH3: no merged actuals'); return
    res = calibration(merged['xfp_rh3_per_pa'].values, merged['actual_per_pa'].values, 'RH3 (FP/PA)')
    if isinstance(res, tuple):
        report_lines.append(res[0])
        if bundle_path.exists():
            bundle = joblib.load(bundle_path)
            training_r = bundle.get('cross_year_r')
            # Compute Q4 gap from the calibration data
            df = pd.DataFrame({'pred': merged['xfp_rh3_per_pa'].values,
                                'act': merged['actual_per_pa'].values})
            df['bucket'] = pd.qcut(df['pred'], q=4, duplicates='drop', labels=False)
            q4 = df[df['bucket'] == 3]
            q4_gap = float(q4['pred'].mean() - q4['act'].mean()) if len(q4) > 0 else np.nan
            report_lines.append(check_drift('RH3', res[1]['r'], training_r,
                                             current_bias=res[1]['bias'],
                                             bias_threshold=0.05,
                                             q4_gap=q4_gap, q4_threshold=0.10))
    else:
        report_lines.append(res)


# ─── RP3 (SP RoS) drift ──────────────────────────────────────────────────────

def check_rp3(report_lines):
    proj_path = ROOT / 'data/outputs/xfp_rp3_projections.csv'
    sp_path = CACHE / 'sp_multiyr_2015_2025.csv'
    bundle_path = ROOT / 'data/models/xfp_rp3_pipeline.pkl'
    if not (proj_path.exists() and sp_path.exists()):
        report_lines.append('RP3: missing files'); return
    proj = pd.read_csv(proj_path)
    sp = pd.read_csv(sp_path)
    actuals = sp[sp['year'] == 2026][['pitcher','fp_per_start_actual','gs']]
    merged = proj.merge(actuals, on='pitcher', how='inner')
    merged = merged[merged['gs'] >= 5]
    if merged.empty:
        report_lines.append('RP3: insufficient 2026 data (need GS>=5)')
        return
    res = calibration(merged['xfp_rp3_per_start'].values,
                       merged['fp_per_start_actual'].values, 'RP3 (FP/start)')
    if isinstance(res, tuple):
        report_lines.append(res[0])
        if bundle_path.exists():
            bundle = joblib.load(bundle_path)
            training_r = bundle.get('cross_year_r')
            df = pd.DataFrame({'pred': merged['xfp_rp3_per_start'].values,
                                'act': merged['fp_per_start_actual'].values})
            df['bucket'] = pd.qcut(df['pred'], q=4, duplicates='drop', labels=False)
            q4 = df[df['bucket'] == 3]
            q4_gap = float(q4['pred'].mean() - q4['act'].mean()) if len(q4) > 0 else np.nan
            report_lines.append(check_drift('RP3', res[1]['r'], training_r,
                                             current_bias=res[1]['bias'],
                                             bias_threshold=1.0, q4_gap=q4_gap, q4_threshold=2.0))
    else:
        report_lines.append(res)


# ─── RP-RS2 (RP RoS) drift ───────────────────────────────────────────────────

def check_rprs2(report_lines):
    proj_path = ROOT / 'data/outputs/xfp_rprs2_projections.csv'
    cnt_path = CACHE / 'pitcher_counting_stats_2026.json'
    bundle_path = ROOT / 'data/models/xfp_rprs2_pipeline.pkl'
    if not (proj_path.exists() and cnt_path.exists()):
        report_lines.append('RP-RS2: missing files'); return
    proj = pd.read_csv(proj_path)
    cnt = json.loads(cnt_path.read_text())
    cnt_df = pd.DataFrame(cnt)
    def parse_ip(v):
        # Delegates to the ONE canonical parser (issue #78). NaN (not 0.0) on a
        # miss — this is Series-mapped and a zero would be a real value.
        if v is None or pd.isna(v):
            return np.nan
        return _canon_parse_ip(v, default=np.nan)
    cnt_df['ip'] = cnt_df['inningsPitched'].map(parse_ip)
    cnt_df['fp_actual'] = pitcher_fp(
        k=cnt_df['strikeOuts'], ip=cnt_df['ip'], h=cnt_df['hits'],
        er=cnt_df['earnedRuns'], bb=cnt_df['baseOnBalls'],
        hbp=cnt_df['hitByPitch'], sv=cnt_df['saves'], hld=cnt_df['holds'])
    # We compare projected FULL-YEAR FP vs PROJECTED-OUT actual (linear extrapolation).
    # Today is ~22% into season; simple extrapolation: full = actual / 0.22
    elapsed_frac = max((pd.Timestamp(date.today()) - pd.Timestamp('2026-03-26')).days / 185, 0.05)
    cnt_df['fp_full_extrapolated'] = cnt_df['fp_actual'] / elapsed_frac
    merged = proj.merge(cnt_df[['pitcher','fp_actual','fp_full_extrapolated','ip']],
                        on='pitcher', how='inner')
    merged = merged[merged['ip'] >= 7]
    if merged.empty:
        report_lines.append('RP-RS2: insufficient 2026 data')
        return
    res = calibration(merged['xfp_full_year'].values,
                       merged['fp_full_extrapolated'].values,
                       'RP-RS2 (full-year FP, extrapolated from to-date)')
    if isinstance(res, tuple):
        report_lines.append(res[0])
        if bundle_path.exists():
            bundle = joblib.load(bundle_path)
            training_r = bundle.get('cross_year_r')
            df = pd.DataFrame({'pred': merged['xfp_full_year'].values,
                                'act': merged['fp_full_extrapolated'].values})
            df['bucket'] = pd.qcut(df['pred'], q=4, duplicates='drop', labels=False)
            q4 = df[df['bucket'] == 3]
            q4_gap = float(q4['pred'].mean() - q4['act'].mean()) if len(q4) > 0 else np.nan
            report_lines.append(check_drift('RP-RS2', res[1]['r'], training_r,
                                             current_bias=res[1]['bias'],
                                             bias_threshold=20.0, q4_gap=q4_gap, q4_threshold=40.0))
    else:
        report_lines.append(res)


def main():
    report_lines = []
    report_lines.append('═' * 72)
    report_lines.append(f'PRODUCTION MODEL DRIFT REPORT — {date.today()}')
    report_lines.append('═' * 72)
    report_lines.append('\n--- RH3 (hitter rate × naive PA) ---')
    check_rh3(report_lines)
    report_lines.append('\n--- RP3 (SP per-start RoS) ---')
    check_rp3(report_lines)
    report_lines.append('\n--- RP-RS2 (RP total RoS) ---')
    check_rprs2(report_lines)
    report_lines.append('\n' + '═' * 72)
    report_lines.append('Drift triggers: per-model bias > threshold OR top-quartile gap > threshold.')
    report_lines.append('Note: in-season r is naturally higher than cross-year r (more recent data).')
    report_lines.append('      For RP-RS2 the actual is extrapolated (early-season pace ≠ full year);')
    report_lines.append('      a real bias check requires end-of-season actuals.')
    report_lines.append('═' * 72)

    out = '\n'.join(report_lines)
    print(out)
    out_path = CACHE / f'drift_report_{date.today()}.txt'
    out_path.write_text(out, encoding='utf-8')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
