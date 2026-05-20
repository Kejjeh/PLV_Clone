"""Win-prob calibration: of predictions in each probability bucket,
what % actually won? A well-calibrated model has actual_win_rate ≈ predicted.

Reads predictions_history.csv, requires actual_my_final / actual_opp_final
populated (run fetch_closed_matchup_actuals.py first).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / 'data' / 'outputs' / 'predictions_history.csv'

BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]


def main():
    df = pd.read_csv(HISTORY)
    if 'actual_my_final' not in df.columns:
        print('No actual_my_final column. Run fetch_closed_matchup_actuals.py first.'); return
    df = df[df['actual_my_final'].notna()].copy()
    if len(df) == 0:
        print('No periods with actuals yet. Run fetch_closed_matchup_actuals.py.'); return

    # Keep first snapshot per (period, model_version) for fair comparison
    df['date'] = pd.to_datetime(df['date'])
    df['mv'] = df.get('model_version', 'baseline').fillna('baseline')
    df = df.sort_values('date').drop_duplicates(['period', 'mv'], keep='first')
    df['actual_outcome'] = (df['actual_my_final'] > df['actual_opp_final']).astype(int)

    print('=== Win-probability calibration ===')
    print(f'n observations: {len(df)} (across {df["period"].nunique()} period(s) × {df["mv"].nunique()} model_version(s))')
    print()

    for mv in sorted(df['mv'].unique()):
        sub = df[df['mv'] == mv]
        if len(sub) == 0: continue
        print(f'--- model_version = {mv} (n={len(sub)}) ---')
        print(f'{"Bucket":<12} {"n":>4} {"pred_avg":>9} {"act_win%":>9} {"calib_gap":>10}')
        rows = []
        for lo, hi in BUCKETS:
            mask = (sub['win_probability'] >= lo) & (sub['win_probability'] < hi)
            n = int(mask.sum())
            if n == 0: continue
            pred_avg = float(sub.loc[mask, 'win_probability'].mean())
            actual = float(sub.loc[mask, 'actual_outcome'].mean())
            gap = actual - pred_avg
            print(f'[{lo:.1f},{hi:.1f})   {n:>4} {pred_avg:>9.3f} {actual:>9.3f} {gap:>+10.3f}')
            rows.append((lo, hi, n, pred_avg, actual, gap))
        # Brier score per model_version
        brier = float(((sub['win_probability'] - sub['actual_outcome']) ** 2).mean())
        print(f'Brier score: {brier:.4f} (lower=better; 0.25 = random, 0.0 = perfect)')
        print()

    # Side-by-side if both versions present
    if df['mv'].nunique() == 2 and df['period'].nunique() >= 1:
        print('--- Direct comparison on overlapping periods ---')
        pivot = df.pivot(index='period', columns='mv', values=['win_probability', 'actual_outcome'])
        print(pivot)


if __name__ == '__main__':
    main()
