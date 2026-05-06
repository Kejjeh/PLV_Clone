"""
xfp_rh_pipeline.py — Rest-of-Season hitter model (RoS-H1).

Predicts each batter's FP/PA over the REMAINDER of the season from features
accumulated season-to-date.

Training data: rolling_hitters_2018_2026.csv (per-(batter, split_day) pairs).
Validation: leave-one-year-out on 2018-2025 (skip 2020).
Compares to H2 (cross-year season FP/PA) — different prediction problem,
but H2's projection is the natural baseline for "what would I have used
mid-season before this model existed?"

Decision: ship if cross-year-eval r on RoS targets > 0.30 (rough floor;
RoS is genuinely harder than YoY because the remaining sample is small).
"""
from __future__ import annotations
import sys
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rh1_pipeline.pkl'
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_rh1_projections.csv'

# RoS feature pool — H2 base + sample-size + season-progression awareness.
# Note: features come with the `_to` suffix from build_rolling_hitters.
RH_FEATS = [
    'iso_to', 'k_pct_to', 'hr_per_pa_to', 'hard_hit_pct_to',
    'contact_pct_to', 'whiff_pct_to', 'swstr_pct_to', 'bb_pct_to',
    'chase_pct_to', 'in_play_pct_to', 'sb_per_pa_to',
    'xwoba_per_pa_to', 'barrel_pct_to',
    'pa_to',          # sample size — the model learns to weight stats by sample
    'split_day',      # season progression
]
# sprint_speed isn't in the rolling substrate yet (it's per-year not per-window).
# Could add by joining from the season-level substrate; skip for v1.

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN = 50    # minimum to-date PA to be in training/eval
ROS_PA_MIN = 100    # minimum remaining PA so the target is meaningful


def load_rolling() -> pd.DataFrame:
    df = pd.read_csv(ROLLING_CSV)
    return df


def cross_year_eval_ros(df: pd.DataFrame, feats: list[str]):
    """For each held-out year, train on the other years' (batter, split_day)
    pairs and predict the held-out year's pairs. Aggregate r across years."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]

    train_years = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
    per_year = {}
    preds_all, acts_all = [], []
    for held in train_years:
        train = df[df['year'] != held]
        test  = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
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


def split_day_breakdown(df: pd.DataFrame, feats: list[str]):
    """How does cross-year r vary with how far into the season we predict from?"""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    by_split: dict[int, dict] = {}
    train_years = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
    for split in sorted(df['split_day'].unique()):
        sub = df[df['split_day'] == split]
        preds_all, acts_all = [], []
        for held in train_years:
            train = sub[sub['year'] != held]
            test  = sub[sub['year'] == held]
            if len(train) < 50 or len(test) < 20:
                continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            p = pipe.predict(test[feats].values)
            preds_all.extend(p.tolist())
            acts_all.extend(test[TARGET].tolist())
        if preds_all:
            r = float(np.corrcoef(preds_all, acts_all)[0, 1])
            mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
            by_split[int(split)] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(preds_all)}
    return by_split


def train_final(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [TARGET])
    train = train[(train['pa_to'] >= EVAL_PA_MIN) & (train['ros_pa'] >= ROS_PA_MIN)
                  & (train['year'].isin([2018, 2019, 2021, 2022, 2023, 2024, 2025]))]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def project_2026(df: pd.DataFrame, feats: list[str], pipe, min_pa_to: int = EVAL_PA_MIN) -> pd.DataFrame:
    """For 2026, project RoS using the latest available split_day per batter.
    Filters to hitters with ≥ min_pa_to PA so far — micro-samples (1-5 PA)
    produce wild projections from the model and aren't actionable."""
    df_26 = df[(df['year'] == 2026)].copy()
    if df_26.empty:
        return pd.DataFrame()
    latest_split = df_26['split_day'].max()
    df_26 = df_26[df_26['split_day'] == latest_split]
    df_26 = df_26[df_26['pa_to'] >= min_pa_to]
    valid = df_26.dropna(subset=feats).copy()
    if valid.empty:
        return valid
    valid['xfp_rh1_per_pa'] = pipe.predict(valid[feats].values)
    # `pa_to` and `split_day` are both metadata AND in `feats`. Drop duplicates
    # by selecting unique columns explicitly (preserve the meta versions).
    keep = ['batter', 'xfp_rh1_per_pa'] + list(feats)
    out = valid[keep].copy()
    out = out.loc[:, ~out.columns.duplicated()]
    return out


def main():
    df = load_rolling()
    print(f'=== xfp_rh_pipeline — substrate {len(df)} rows ===')

    # Coverage
    df_clean = df.dropna(subset=RH_FEATS + [TARGET])
    qual = df_clean[(df_clean['pa_to'] >= EVAL_PA_MIN) & (df_clean['ros_pa'] >= ROS_PA_MIN) & (df_clean['year'] != 2020)]
    print(f'After dropna + PA/RoS filters: {len(qual)} rows')
    print(f'  pa_to ≥ {EVAL_PA_MIN}: {(df["pa_to"] >= EVAL_PA_MIN).sum()}')
    print(f'  ros_pa ≥ {ROS_PA_MIN}: {(df["ros_pa"] >= ROS_PA_MIN).sum()}')
    print(f'  year != 2020: {(df["year"] != 2020).sum()}')
    print(f'  Years in eval: {sorted(qual["year"].unique())}\n')

    # Leave-one-year-out cross-year eval
    print('--- Leave-one-year-out cross-year eval ---')
    per_year, overall = cross_year_eval_ros(df, RH_FEATS)
    print(f'  Per-year r (and n):')
    for y, r in sorted(per_year.items()):
        print(f'    {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall (concatenated): r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}\n')

    # Split-day breakdown — does the model do better when we have more in-season data?
    print('--- Cross-year r by split_day (does more in-season data help?) ---')
    by_split = split_day_breakdown(df, RH_FEATS)
    for split, r in sorted(by_split.items()):
        print(f'  day {split:>4}:  r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print()

    # Train final
    print('--- Training final RH1 pipeline on all years 2018-2025 (drop 2020) ---')
    pipe, n_train = train_final(df, RH_FEATS)
    print(f'  n_train = {n_train}')
    coefs = pipe.named_steps['r'].coef_
    print(f'  alpha = {pipe.named_steps["r"].alpha_:.3f}')
    print(f'  Standardized coefficients:')
    for f, c in sorted(zip(RH_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<22s} {c:+.4f}')

    # Verify reload
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        'pipeline': pipe,
        'features': RH_FEATS,
        'target': TARGET,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'per_year_r': per_year,
        'by_split_r': by_split,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'training_years': [2018, 2019, 2021, 2022, 2023, 2024, 2025],
        'min_pa_to': EVAL_PA_MIN,
        'min_ros_pa': ROS_PA_MIN,
        'split_days': sorted(df['split_day'].unique().tolist()),
        'version': 'rh1',
        'note': 'Rest-of-Season hitter model. Predicts FP/PA for the remainder of the season from features cumulated season-to-date.',
    }
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote bundle: {MODEL_PKL}')

    # Project 2026 latest
    print('\n--- Project 2026 RoS ---')
    proj = project_2026(df, RH_FEATS, pipe)
    if proj.empty:
        print('  No 2026 data to project on.')
    else:
        # Merge in player names from substrate
        names = pd.read_csv(ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv')
        names = names[names['year'] == 2026][['batter', 'player_name', 'team']].drop_duplicates('batter')
        proj = proj.drop_duplicates('batter').merge(names, on='batter', how='left')
        proj = proj.sort_values('xfp_rh1_per_pa', ascending=False).reset_index(drop=True)
        proj['rank'] = proj.index + 1
        latest_split_val = int(proj['split_day'].dropna().iloc[0])
        proj.to_csv(PROJ_CSV, index=False)
        print(f'  Wrote {PROJ_CSV}: {len(proj)} hitters (split_day = {latest_split_val})')
        print(f'  Top 10:')
        for _, row in proj.head(10).iterrows():
            name = str(row.get('player_name') or '—')
            team = str(row.get('team') or '—')
            print(f'    {int(row["rank"]):>3} {name:<25s} team={team:<4s} '
                  f'pa_to={int(row["pa_to"]):>4} xfp_rh1/PA={row["xfp_rh1_per_pa"]:.4f}')


if __name__ == '__main__':
    main()
