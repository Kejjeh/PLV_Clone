"""
xfp_rh2_pipeline.py — Bayesian Rest-of-Season hitter model (RoS-H2).

Improves on RH1 by adding:

  1. Marcel-weighted multi-year prior FP/PA, regressed toward league mean.
     Captures the long-run skill prior the in-season window cannot fully see.

  2. Per-feature Bayesian shrinkage of in-season rates with stabilization-
     based k values from the baseball compendium (Carleton split-half r=0.7):
       k_pct=60 PA, bb_pct=120 PA, hr_per_pa=170 PA, iso=160 AB, ...

  Shrinkage formula:  shrunk_rate = (n*obs + k*pop_mean) / (n + k)
  Mean computed from training years pooled.

Outputs:
  data/models/xfp_rh2_pipeline.pkl
  data/outputs/xfp_rh2_projections.csv

Decision gate (R2 plan): cross-year r >= RH1 + 0.02.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
MODEL_PKL   = ROOT / 'data' / 'models' / 'xfp_rh2_pipeline.pkl'
PROJ_CSV    = ROOT / 'data' / 'outputs' / 'xfp_rh2_projections.csv'

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN = 50
ROS_PA_MIN = 100
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_PA = 200          # regression-to-mean for the multi-year prior
MARCEL_WEIGHTS = (5, 4, 3)  # weights for y-1, y-2, y-3

# Per-feature shrinkage spec: column name -> (denom_col, k)
# k = stabilization PA from compendium §2C. denom_col tells us the sample size
# of that rate.  For rates expressed against AB or BIP we approximate with PA
# where exact column is unavailable.
SHRINK_SPEC = {
    'k_pct_to':         ('pa_to',     60),
    'bb_pct_to':        ('pa_to',    120),
    'hr_per_pa_to':     ('pa_to',    170),
    'iso_to':           ('ab_to',    160),
    'sb_per_pa_to':     ('pa_to',    300),
    'xwoba_per_pa_to':  ('pa_to',    300),
    'contact_pct_to':   ('swing_to', 100),
    'whiff_pct_to':     ('swing_to', 100),
    'swstr_pct_to':     ('pitches_to', 300),
    'hard_hit_pct_to':  ('bip_to',    50),
    'barrel_pct_to':    ('bip_to',    50),
    'chase_pct_to':     ('out_zone_to', 400),
    'in_play_pct_to':   ('pitches_to', 300),
}

# Final RH2 feature pool — the shrunken rates plus prior + sample-size cues.
RH2_FEATS = [
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    'prior_fp_per_pa', 'prior_pa_eff',  # multi-year prior + how strong it is
    'pa_to', 'split_day',
]


# ---------------------------------------------------------------------------
# Multi-year prior
# ---------------------------------------------------------------------------

def build_prior_table(multiyr: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """For each (batter, target_year), compute Marcel-weighted prior FP/PA from
    the previous 3 years (excluding 2020 since 60-game season distorts rates),
    regressed toward each target_year's league mean with k = PRIOR_K_PA."""
    rows = []
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('batter') for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['pa'] >= 200]
                           .groupby('year')['fp_per_pa_actual'].mean().to_dict())
    weights = MARCEL_WEIGHTS

    all_batters = set()
    for df in by_yr.values():
        all_batters.update(df.index)

    for tgt in years:
        offsets = [1, 2, 3]
        # Skip 2020 — never use it as a prior input
        offsets_use = []
        for off, w in zip(offsets, weights):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for b in all_batters:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                df_y = by_yr[y]
                if b in df_y.index:
                    row = df_y.loc[b]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    pa = float(row.get('pa', 0) or 0)
                    fp = float(row.get('fp_per_pa_actual', np.nan))
                    if pa >= 50 and not np.isnan(fp):
                        num += w * pa * fp
                        denom += w * pa
            prior = (num + PRIOR_K_PA * league_mu) / (denom + PRIOR_K_PA)
            rows.append({'batter': b, 'year': tgt,
                         'prior_fp_per_pa': prior,
                         'prior_pa_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------

def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'ab_to' not in out.columns:
        out = out.assign(ab_to=out['pa_to'] - out['bb_to'] - out.get('hbp_to', 0))
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    return out


def compute_population_means(df: pd.DataFrame, train_years: list[int]) -> dict:
    """Pooled-mean per rate, computed on training years only (drop 2020).
    Use sample-weighted mean = total numerator / total denominator equivalent
    by treating raw rate as obs and weighting by the rate's denominator."""
    means = {}
    sub = _ensure_derived_denoms(df[df['year'].isin(train_years) & (df['year'] != 2020)].copy())
    for rate_col, (denom_col, _k) in SHRINK_SPEC.items():
        d = sub[[rate_col, denom_col]].dropna()
        d = d[d[denom_col] > 0]
        if d.empty:
            means[rate_col] = float(sub[rate_col].mean(skipna=True))
        else:
            # weighted mean by denominator
            means[rate_col] = float((d[rate_col] * d[denom_col]).sum() / d[denom_col].sum())
    return means


def apply_shrinkage(df: pd.DataFrame, pop_means: dict) -> pd.DataFrame:
    """Return df with new *_sh columns produced by Bayesian shrinkage."""
    out = _ensure_derived_denoms(df.copy())
    for rate_col, (denom_col, k) in SHRINK_SPEC.items():
        n = out[denom_col].astype(float)
        obs = out[rate_col].astype(float)
        mean = pop_means.get(rate_col, float(np.nanmean(obs)))
        # Where obs is NaN but n>0, fall back to mean (treat as zero observation)
        obs_filled = obs.fillna(mean)
        n_eff = n.fillna(0.0)
        out[rate_col + '_sh'] = (n_eff * obs_filled + k * mean) / (n_eff + k)
    return out


# ---------------------------------------------------------------------------
# Validation + final training
# ---------------------------------------------------------------------------

def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN)
            & (df['year'] != 2020)]
    per_year = {}
    preds_all, acts_all = [], []
    for held in TRAIN_YEARS:
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
        preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}


def split_day_breakdown(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN)
            & (df['year'] != 2020)]
    by_split = {}
    for split in sorted(df['split_day'].unique()):
        sub = df[df['split_day'] == split]
        preds, acts = [], []
        for held in TRAIN_YEARS:
            train = sub[sub['year'] != held]
            test  = sub[sub['year'] == held]
            if len(train) < 50 or len(test) < 20:
                continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            p = pipe.predict(test[feats].values)
            preds.extend(p.tolist()); acts.extend(test[TARGET].tolist())
        if preds:
            r = float(np.corrcoef(preds, acts)[0, 1])
            mae = float(np.mean(np.abs(np.array(preds) - np.array(acts))))
            by_split[int(split)] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(preds)}
    return by_split


def train_final(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    train = df.dropna(subset=feats + [TARGET])
    train = train[(train['pa_to'] >= EVAL_PA_MIN) & (train['ros_pa'] >= ROS_PA_MIN)
                  & (train['year'].isin(TRAIN_YEARS))]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def main():
    print('=== xfp_rh2_pipeline (Bayesian RoS hitters) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    # Multi-year prior
    print('\nBuilding Marcel-weighted multi-year prior...')
    years_needed = sorted(rolling['year'].unique())
    prior = build_prior_table(multiyr, years_needed)
    print(f'  prior table: {len(prior)} (batter, year) rows')
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    # backfill league-mean prior for batters missing prior history
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    # Bayesian shrinkage
    print('\nApplying Bayesian shrinkage with compendium k values...')
    pop_means = compute_population_means(rolling, TRAIN_YEARS)
    for rc, mu in pop_means.items():
        print(f'  pop_mean[{rc:<22s}] = {mu:.4f}')
    rolling = apply_shrinkage(rolling, pop_means)

    # Cross-year eval
    print('\n--- Leave-one-year-out (RH2) ---')
    per_year, overall = cross_year_eval(rolling, RH2_FEATS)
    for y, r in sorted(per_year.items()):
        print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    # Compare against RH1 baseline (same routine, RH1 features)
    rh1_feats = [
        'iso_to', 'k_pct_to', 'hr_per_pa_to', 'hard_hit_pct_to',
        'contact_pct_to', 'whiff_pct_to', 'swstr_pct_to', 'bb_pct_to',
        'chase_pct_to', 'in_play_pct_to', 'sb_per_pa_to',
        'xwoba_per_pa_to', 'barrel_pct_to', 'pa_to', 'split_day',
    ]
    print('\n--- Leave-one-year-out (RH1 baseline) ---')
    _per_y_b, baseline = cross_year_eval(rolling, rh1_feats)
    print(f'  Overall: r={baseline["r"]}  mae={baseline["mae"]}  n={baseline["n"]}')
    delta = overall['r'] - baseline['r']
    print(f'\n  Δr (RH2 − RH1) = {delta:+.4f}  '
          f'{"PASS" if delta >= 0.02 else "MISS"}  (gate: ≥ +0.02)')

    print('\n--- RH2 cross-year r by split_day ---')
    by_split = split_day_breakdown(rolling, RH2_FEATS)
    for split, r in sorted(by_split.items()):
        print(f'  day {split:>4}:  r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')

    # Train final
    print('\n--- Training final RH2 ---')
    pipe, n_train = train_final(rolling, RH2_FEATS)
    coefs = pipe.named_steps['r'].coef_
    print(f'  n_train = {n_train}, alpha = {pipe.named_steps["r"].alpha_:.3f}')
    print('  Standardized coefficients:')
    for f, c in sorted(zip(RH2_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<24s} {c:+.4f}')

    # Bundle
    bundle = {
        'pipeline': pipe,
        'features': RH2_FEATS,
        'target': TARGET,
        'pop_means': pop_means,
        'shrink_spec': SHRINK_SPEC,
        'prior_k_pa': PRIOR_K_PA,
        'marcel_weights': MARCEL_WEIGHTS,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rh1_r': baseline['r'],
        'delta_r_vs_rh1': round(delta, 4),
        'per_year_r': per_year,
        'by_split_r': by_split,
        'training_years': TRAIN_YEARS,
        'min_pa_to': EVAL_PA_MIN,
        'min_ros_pa': ROS_PA_MIN,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rh2',
        'note': 'Bayesian RoS hitter Ridge: Marcel multi-year prior + per-rate '
                'shrinkage with compendium k values. R2/Phase R2 implementation.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        print('No 2026 rows for projection.')
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['pa_to'] >= EVAL_PA_MIN)]
    valid = df_26.dropna(subset=RH2_FEATS).copy()
    valid['xfp_rh2_per_pa'] = pipe.predict(valid[RH2_FEATS].values)

    # Names
    names = multiyr[multiyr['year'] == 2026][['batter', 'player_name', 'team']] \
        .drop_duplicates('batter')
    valid = valid.drop_duplicates('batter').merge(names, on='batter', how='left')
    valid = valid.sort_values('xfp_rh2_per_pa', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1
    keep = ['rank', 'batter', 'player_name', 'team', 'pa_to', 'split_day',
            'prior_fp_per_pa', 'xfp_rh2_per_pa']
    keep = [c for c in keep if c in valid.columns]
    valid[keep + RH2_FEATS].to_csv(PROJ_CSV, index=False)
    print(f'\nWrote {PROJ_CSV}: {len(valid)} hitters (split_day = {latest_split})')
    print('Top 10:')
    for _, row in valid.head(10).iterrows():
        nm = str(row.get('player_name') or '—')
        tm = str(row.get('team') or '—')
        print(f'  {int(row["rank"]):>3} {nm:<25s} ({tm:<3s}) pa={int(row["pa_to"]):>4}  '
              f'prior={row["prior_fp_per_pa"]:.3f}  xfp_rh2={row["xfp_rh2_per_pa"]:.4f}')


if __name__ == '__main__':
    main()
