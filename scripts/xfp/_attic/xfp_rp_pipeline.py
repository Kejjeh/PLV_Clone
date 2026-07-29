"""
xfp_rp_pipeline.py — Rest-of-Season pitcher model (RoS-P1).

Pitcher mirror of xfp_rh_pipeline.py. Predicts FP/start over the remainder
of the season from V11/V12-style features cumulated season-to-date.

Outputs:
  data/models/xfp_rp1_pipeline.pkl
  data/outputs/xfp_rp1_projections.csv
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings('ignore')

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_pitchers_2018_2026.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rp1_pipeline.pkl'
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_rp1_projections.csv'

# Pitcher RoS feature pool — V12-style features from the season-to-date window.
RP_FEATS = [
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
    'zone_pct_to', 'z_swing_pct_to', 'o_swing_pct_to',
    'avg_velo_to', 'xwoba_per_pa_to', 'xwoba_x_swstr_to',
    'fp_per_start_to',  # crucial: prior FP/start within the same season
    'gs_to',            # number of starts so far — sample-size sensitivity
    'split_day',
]
TARGET = 'ros_fp_per_start'
EVAL_GS_MIN = 2     # min starts in to-date window
ROS_GS_MIN  = 5     # min remaining starts so target is meaningful


def cross_year_eval(df, feats):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    df = df.dropna(subset=feats + [TARGET])
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN) & (df['year'] != 2020)]

    train_years = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
    per_year = {}
    preds_all, acts_all = [], []
    for held in train_years:
        train = df[df['year'] != held]
        test  = df[df['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        rmse = float(np.sqrt(np.mean((preds - test[TARGET].values) ** 2)))
        mae  = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'rmse': round(rmse, 4),
                          'mae': round(mae, 4), 'n': len(test)}
        preds_all.extend(preds.tolist())
        acts_all.extend(test[TARGET].tolist())
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4), 'n': len(preds_all)}


def split_day_breakdown(df, feats):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    df = df.dropna(subset=feats + [TARGET])
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN) & (df['year'] != 2020)]
    by_split: dict = {}
    train_years = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
    for split in sorted(df['split_day'].unique()):
        sub = df[df['split_day'] == split]
        preds_all, acts_all = [], []
        for held in train_years:
            train = sub[sub['year'] != held]
            test  = sub[sub['year'] == held]
            if len(train) < 30 or len(test) < 10:
                continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            preds_all.extend(pipe.predict(test[feats].values).tolist())
            acts_all.extend(test[TARGET].tolist())
        if preds_all:
            r = float(np.corrcoef(preds_all, acts_all)[0, 1])
            mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
            by_split[int(split)] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(preds_all)}
    return by_split


def main():
    df = pd.read_csv(ROLLING_CSV)
    print(f'=== xfp_rp_pipeline — substrate {len(df)} rows ===')

    df_clean = df.dropna(subset=RP_FEATS + [TARGET])
    qual = df_clean[(df_clean['gs_to'] >= EVAL_GS_MIN) & (df_clean['ros_gs'] >= ROS_GS_MIN) & (df_clean['year'] != 2020)]
    print(f'After dropna + GS filters: {len(qual)} rows  (2026 partial: '
          f'{(qual["year"] == 2026).sum()})\n')

    per_year, overall = cross_year_eval(df, RP_FEATS)
    print('--- Leave-one-year-out cross-year eval ---')
    for y, r in sorted(per_year.items()):
        print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}\n')

    print('--- Cross-year r by split_day ---')
    by_split = split_day_breakdown(df, RP_FEATS)
    for split, r in sorted(by_split.items()):
        print(f'  day {split:>4}:  r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print()

    # Train final
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=RP_FEATS + [TARGET])
    train = train[(train['gs_to'] >= EVAL_GS_MIN) & (train['ros_gs'] >= ROS_GS_MIN)
                  & (train['year'].isin([2018, 2019, 2021, 2022, 2023, 2024, 2025]))]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[RP_FEATS].values, train[TARGET].values)
    print(f'--- Final RP1 pipeline trained on {len(train)} rows ---')
    print(f'  alpha = {pipe.named_steps["r"].alpha_:.3f}')
    coefs = pipe.named_steps['r'].coef_
    print(f'  Standardized coefficients:')
    for f, c in sorted(zip(RP_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<22s} {c:+.4f}')

    bundle = {
        'pipeline': pipe,
        'features': RP_FEATS,
        'target': TARGET,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'per_year_r': per_year,
        'by_split_r': by_split,
        'trained_date': str(date.today()),
        'n_train': len(train),
        'training_years': [2018, 2019, 2021, 2022, 2023, 2024, 2025],
        'min_gs_to': EVAL_GS_MIN,
        'min_ros_gs': ROS_GS_MIN,
        'split_days': sorted(df['split_day'].unique().tolist()),
        'version': 'rp1',
        'note': 'Rest-of-Season pitcher model. Predicts FP/start for remainder of season from V12-style features cumulated season-to-date.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Project 2026
    df_26 = df[df['year'] == 2026].copy()
    if not df_26.empty:
        latest_split = df_26['split_day'].max()
        df_26 = df_26[df_26['split_day'] == latest_split]
        df_26 = df_26[df_26['gs_to'] >= EVAL_GS_MIN]
        valid = df_26.dropna(subset=RP_FEATS).copy()
        valid['xfp_rp1_per_start'] = pipe.predict(valid[RP_FEATS].values)
        # Names from sp_multiyr
        try:
            sp = pd.read_csv(ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv')
            sp_26 = sp[sp['year'] == 2026][['pitcher', 'player_name']].drop_duplicates('pitcher')
            valid = valid.drop_duplicates('pitcher').merge(sp_26, on='pitcher', how='left')
        except Exception:
            valid['player_name'] = '?'
        valid = valid.sort_values('xfp_rp1_per_start', ascending=False).reset_index(drop=True)
        valid['rank'] = valid.index + 1
        keep = ['rank', 'pitcher', 'player_name', 'gs_to', 'fp_per_start_to', 'xfp_rp1_per_start']
        keep = [c for c in keep if c in valid.columns]
        valid[keep + RP_FEATS].to_csv(PROJ_CSV, index=False)
        print(f'\nWrote {PROJ_CSV}: {len(valid)} pitchers (split_day = {int(latest_split)})')
        print(f'Top 10:')
        for _, row in valid.head(10).iterrows():
            name = str(row.get('player_name') or '—')
            print(f'  {int(row["rank"]):>3} {name:<25s} gs={int(row["gs_to"]):>2} '
                  f'fp/start_to={float(row["fp_per_start_to"]):>5.2f}  '
                  f'xfp_rp1/start={float(row["xfp_rp1_per_start"]):>5.2f}')


if __name__ == '__main__':
    main()
