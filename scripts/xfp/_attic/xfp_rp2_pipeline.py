"""
xfp_rp2_pipeline.py — Bayesian Rest-of-Season pitcher model (RoS-P2).

Improves on RP1 by adding:

  1. Marcel-weighted multi-year prior FP/start, regressed toward league mean.
     Built from sp_multiyr_2015_2025.csv (per-season SP totals).

  2. Per-feature Bayesian shrinkage on in-season pitcher rates with
     compendium k values: K%≈70 BF, BB%≈170 BF, SwStr%/CSW% pitch-denom,
     xwOBA/PA ~PRIOR_BF.

  3. Same-year IL status from il_split_features (current IL flag, days since
     return, stints to date).  Captures the "missed time → uncertain return"
     signal that sets RoS apart from cross-year prediction.

Outputs:
  data/models/xfp_rp2_pipeline.pkl
  data/outputs/xfp_rp2_projections.csv

Decision gate (R2 plan): cross-year r >= RP1 + 0.02.
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
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_pitchers_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
IL_CSV      = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_split_features_2018_2026.csv'
MODEL_PKL   = ROOT / 'data' / 'models' / 'xfp_rp2_pipeline.pkl'
PROJ_CSV    = ROOT / 'data' / 'outputs' / 'xfp_rp2_projections.csv'

TARGET = 'ros_fp_per_start'
EVAL_GS_MIN = 2
ROS_GS_MIN = 5
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_GS = 5      # regression-to-mean for the multi-year prior
MARCEL_WEIGHTS = (5, 4, 3)

# Shrinkage spec for pitcher rates: column -> (denom_col, k)
SHRINK_SPEC = {
    'k_pct_to':         ('tbf_to',     70),
    'bb_pct_to':        ('tbf_to',    170),
    'swstr_pct_to':     ('pitches_to', 300),
    'c_plus_swstr_to':  ('pitches_to', 300),
    'xwoba_per_pa_to':  ('tbf_to',    300),
    'zone_pct_to':      ('pitches_to', 200),
    'z_swing_pct_to':   ('in_zone_to', 200),
    'o_swing_pct_to':   ('out_zone_to', 200),
}

RP2_FEATS = [
    'k_pct_to_sh', 'bb_pct_to_sh', 'swstr_pct_to_sh', 'c_plus_swstr_to_sh',
    'xwoba_per_pa_to_sh', 'zone_pct_to_sh',
    'z_swing_pct_to_sh', 'o_swing_pct_to_sh',
    'avg_velo_to',  # already very stable; no shrinkage needed
    'fp_per_start_to', 'gs_to',
    'prior_fp_per_start', 'prior_gs_eff',
    'is_on_il_at_split', 'days_since_il_return_imp', 'il_stints_to',
    'split_day',
]


def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    return out


# ---------------------------------------------------------------------------
# Multi-year prior (FP/start)
# ---------------------------------------------------------------------------

def build_prior_table(multiyr: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """For each (pitcher, target_year), Marcel-weighted prior FP/start from
    prior years (excluding 2020), regressed to league mean with k=5 starts."""
    rows = []
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('pitcher')
             for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['gs'] >= 10]
                           .groupby('year')['fp_per_start_actual'].mean().to_dict())

    all_pitchers = set()
    for df in by_yr.values():
        all_pitchers.update(df.index)

    for tgt in years:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL_WEIGHTS):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for p in all_pitchers:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                df_y = by_yr[y]
                if p in df_y.index:
                    row = df_y.loc[p]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    gs = float(row.get('gs', 0) or 0)
                    fp = float(row.get('fp_per_start_actual', np.nan))
                    if gs >= 3 and not np.isnan(fp):
                        num += w * gs * fp
                        denom += w * gs
            prior = (num + PRIOR_K_GS * league_mu) / (denom + PRIOR_K_GS)
            rows.append({
                'pitcher': p, 'year': tgt,
                'prior_fp_per_start': prior,
                'prior_gs_eff': denom / max(sum(w for _, w in offsets_use), 1),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------

def compute_population_means(df: pd.DataFrame, train_years: list[int]) -> dict:
    means = {}
    sub = _ensure_derived_denoms(df[df['year'].isin(train_years) & (df['year'] != 2020)].copy())
    for rate_col, (denom_col, _k) in SHRINK_SPEC.items():
        d = sub[[rate_col, denom_col]].dropna()
        d = d[d[denom_col] > 0]
        if d.empty:
            means[rate_col] = float(sub[rate_col].mean(skipna=True))
        else:
            means[rate_col] = float((d[rate_col] * d[denom_col]).sum() / d[denom_col].sum())
    return means


def apply_shrinkage(df: pd.DataFrame, pop_means: dict) -> pd.DataFrame:
    out = _ensure_derived_denoms(df.copy())
    for rate_col, (denom_col, k) in SHRINK_SPEC.items():
        n = out[denom_col].astype(float)
        obs = out[rate_col].astype(float)
        mean = pop_means.get(rate_col, float(np.nanmean(obs)))
        obs_filled = obs.fillna(mean)
        n_eff = n.fillna(0.0)
        out[rate_col + '_sh'] = (n_eff * obs_filled + k * mean) / (n_eff + k)
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN)
            & (df['year'] != 2020)]
    per_year = {}
    preds_all, acts_all = [], []
    for held in TRAIN_YEARS:
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
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
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
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN)
            & (df['year'] != 2020)]
    by_split = {}
    for split in sorted(df['split_day'].unique()):
        sub = df[df['split_day'] == split]
        preds, acts = [], []
        for held in TRAIN_YEARS:
            train = sub[sub['year'] != held]
            test  = sub[sub['year'] == held]
            if len(train) < 30 or len(test) < 10:
                continue
            pipe = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
            pipe.fit(train[feats].values, train[TARGET].values)
            preds.extend(pipe.predict(test[feats].values).tolist())
            acts.extend(test[TARGET].tolist())
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
    train = train[(train['gs_to'] >= EVAL_GS_MIN) & (train['ros_gs'] >= ROS_GS_MIN)
                  & (train['year'].isin(TRAIN_YEARS))]
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[feats].values, train[TARGET].values)
    return pipe, len(train)


def main():
    print('=== xfp_rp2_pipeline (Bayesian RoS pitchers) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    il = pd.read_csv(IL_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} | il: {len(il)}')

    # Multi-year prior
    print('\nBuilding Marcel prior FP/start...')
    years_needed = sorted(rolling['year'].unique())
    prior = build_prior_table(multiyr, years_needed)
    print(f'  prior table: {len(prior)} (pitcher, year) rows')
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff']       = rolling['prior_gs_eff'].fillna(0.0)

    # IL features
    print('\nMerging IL split features...')
    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to']        = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split']   = rolling['is_on_il_at_split'].fillna(0).astype(int)
    rolling['days_on_il_to']       = rolling['days_on_il_to'].fillna(0).astype(int)
    # days_since_il_return: NaN means "never on IL"; impute as max-observed + 1
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)

    # Diagnostic — IL coverage
    print('  IL flagged this season:')
    iloc = rolling.groupby('year').agg(
        n=('pitcher', 'size'),
        any_il=('il_stints_to', lambda s: (s > 0).sum()),
        on_il=('is_on_il_at_split', 'sum'),
    ).round(2)
    print(iloc.to_string())

    # Shrinkage
    print('\nApplying Bayesian shrinkage...')
    pop_means = compute_population_means(rolling, TRAIN_YEARS)
    for rc, mu in pop_means.items():
        print(f'  pop_mean[{rc:<22s}] = {mu:.4f}')
    rolling = apply_shrinkage(rolling, pop_means)

    # Cross-year (RP2)
    print('\n--- Leave-one-year-out (RP2) ---')
    per_year, overall = cross_year_eval(rolling, RP2_FEATS)
    for y, r in sorted(per_year.items()):
        print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    # RP1 baseline
    rp1_feats = [
        'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
        'zone_pct_to', 'z_swing_pct_to', 'o_swing_pct_to',
        'avg_velo_to', 'xwoba_per_pa_to',
        'fp_per_start_to', 'gs_to', 'split_day',
    ]
    print('\n--- Leave-one-year-out (RP1 baseline) ---')
    _per_b, baseline = cross_year_eval(rolling, rp1_feats)
    print(f'  Overall: r={baseline["r"]}  mae={baseline["mae"]}  n={baseline["n"]}')
    delta = overall['r'] - baseline['r']
    print(f'\n  Δr (RP2 − RP1) = {delta:+.4f}  '
          f'{"PASS" if delta >= 0.02 else "MISS"}  (gate: ≥ +0.02)')

    print('\n--- RP2 cross-year r by split_day ---')
    by_split = split_day_breakdown(rolling, RP2_FEATS)
    for split, r in sorted(by_split.items()):
        print(f'  day {split:>4}:  r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')

    # Train final
    print('\n--- Training final RP2 ---')
    pipe, n_train = train_final(rolling, RP2_FEATS)
    coefs = pipe.named_steps['r'].coef_
    print(f'  n_train = {n_train}, alpha = {pipe.named_steps["r"].alpha_:.3f}')
    print('  Standardized coefficients:')
    for f, c in sorted(zip(RP2_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'    {f:<26s} {c:+.4f}')

    bundle = {
        'pipeline': pipe,
        'features': RP2_FEATS,
        'target': TARGET,
        'pop_means': pop_means,
        'shrink_spec': SHRINK_SPEC,
        'prior_k_gs': PRIOR_K_GS,
        'marcel_weights': MARCEL_WEIGHTS,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rp1_r': baseline['r'],
        'delta_r_vs_rp1': round(delta, 4),
        'per_year_r': per_year,
        'by_split_r': by_split,
        'training_years': TRAIN_YEARS,
        'min_gs_to': EVAL_GS_MIN,
        'min_ros_gs': ROS_GS_MIN,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rp2',
        'note': 'Bayesian RoS pitcher Ridge: Marcel multi-year prior + per-rate '
                'shrinkage + same-year IL state. R2/Phase R2 implementation.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        print('No 2026 rows.'); return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['gs_to'] >= EVAL_GS_MIN)]
    valid = df_26.dropna(subset=RP2_FEATS).copy()
    valid['xfp_rp2_per_start'] = pipe.predict(valid[RP2_FEATS].values)

    sp_26 = multiyr[multiyr['year'] == 2026][['pitcher', 'player_name']].drop_duplicates('pitcher')
    valid = valid.drop_duplicates('pitcher').merge(sp_26, on='pitcher', how='left')
    valid = valid.sort_values('xfp_rp2_per_start', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1
    keep = ['rank', 'pitcher', 'player_name', 'gs_to', 'fp_per_start_to',
            'prior_fp_per_start', 'is_on_il_at_split', 'xfp_rp2_per_start']
    keep = [c for c in keep if c in valid.columns]
    valid[keep + RP2_FEATS].to_csv(PROJ_CSV, index=False)
    print(f'\nWrote {PROJ_CSV}: {len(valid)} pitchers (split_day = {latest_split})')
    print('Top 10:')
    for _, row in valid.head(10).iterrows():
        nm = str(row.get('player_name') or '—')
        on_il = '🤕' if row['is_on_il_at_split'] == 1 else ''
        print(f'  {int(row["rank"]):>3} {nm:<25s} gs={int(row["gs_to"]):>2}  '
              f'prior={row["prior_fp_per_start"]:5.2f}  '
              f'xfp_rp2={row["xfp_rp2_per_start"]:5.2f} {on_il}')


if __name__ == '__main__':
    main()
