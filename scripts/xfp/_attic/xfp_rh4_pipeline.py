"""xfp_rh4_pipeline.py — RoS hitter model with lineup-spot features.

Adds (vs RH3):
  - lineup_spot_to        (statcast-derived avg batting order, current year through cutoff)
  - started_pct_to        (fraction of team apps where they were in starting lineup)
  - pa_per_started_game_to (avg PAs per started game — captures lineup-position-driven volume)
  - lineup_spot_lag1      (prior-year avg batting order)
  - started_pct_lag1      (prior-year started %)

Stratified validation gates (mirrors RP-RS2 methodology):
  1. OVERALL LOO cross-year r MUST NOT regress vs RH3 baseline.
  2. LINEUP-CHANGE subset r MUST improve by >= +0.05.
     Subset: rows where |lineup_spot_to − lineup_spot_lag1| >= 1.5 AND has lag.

Promotes if both gates pass; reverts otherwise.
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
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
MASTER_HITTER = ROOT / 'data' / 'outputs' / 'master_hitter_2026.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rh4_pipeline.pkl'
PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rh4_projections.csv'

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN = 50
ROS_PA_MIN = 100
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_PA = 200
MARCEL_WEIGHTS = (5, 4, 3)
PA_PER_GAME_LEAGUE = 3.5
SEASON_GAMES = 162
REPLACEMENT_RANK = {'C': 12, '1B': 12, '2B': 12, 'SS': 12, '3B': 12,
                    'OF': 36, 'DH': 24, 'UTIL': 24}

SHRINK_SPEC_TO = {
    'k_pct_to':         ('pa_to', 60), 'bb_pct_to':        ('pa_to', 120),
    'hr_per_pa_to':     ('pa_to', 170), 'iso_to':           ('ab_to', 160),
    'sb_per_pa_to':     ('pa_to', 300), 'xwoba_per_pa_to':  ('pa_to', 300),
    'contact_pct_to':   ('swing_to', 100), 'whiff_pct_to':  ('swing_to', 100),
    'swstr_pct_to':     ('pitches_to', 300), 'hard_hit_pct_to': ('bip_to', 50),
    'barrel_pct_to':    ('bip_to', 50),
    'chase_pct_to':     ('out_zone_to', 400), 'in_play_pct_to': ('pitches_to', 300),
}

# Baseline RH3 features (no lineup)
BASE_FEATS = [
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    'prior_fp_per_pa', 'prior_pa_eff', 'pa_to', 'split_day',
]

# New features in RH4
NEW_FEATS = [
    'lineup_spot_to', 'started_pct_to', 'pa_per_started_game_to',
    'lineup_spot_lag1', 'started_pct_lag1',
]

FEATS_RH4 = BASE_FEATS + NEW_FEATS


def _ensure_derived(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'ab_to' not in out.columns:
        out = out.assign(ab_to=out['pa_to'] - out['bb_to'] - out.get('hbp_to', 0))
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    return out


def build_prior_table(multiyr: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    rows = []
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('batter') for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['pa'] >= 200]
                           .groupby('year')['fp_per_pa_actual'].mean().to_dict())
    all_batters = set()
    for df in by_yr.values():
        all_batters.update(df.index)
    for tgt in years:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL_WEIGHTS):
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


def build_lineup_lag(rolling: pd.DataFrame) -> pd.DataFrame:
    """Per (batter, year) prior-year lineup_spot avg from full-year cutoff (split=120)
    or whichever was the latest split for that year."""
    last_split_per_year = rolling.groupby('year')['split_day'].max().to_dict()
    rows = []
    for yr, max_split in last_split_per_year.items():
        sub = rolling[(rolling['year'] == yr) & (rolling['split_day'] == max_split)]
        for _, r in sub.iterrows():
            rows.append({
                'batter': int(r['batter']),
                'year_target': int(yr) + 1,
                'lineup_spot_lag1': float(r['lineup_spot_to']) if pd.notna(r['lineup_spot_to']) else np.nan,
                'started_pct_lag1': float(r['started_pct_to']) if pd.notna(r['started_pct_to']) else np.nan,
            })
    return pd.DataFrame(rows)


def compute_population_means(df, train_years, spec):
    means: dict[str, float] = {}
    sub = _ensure_derived(df[df['year'].isin(train_years) & (df['year'] != 2020)].copy())
    for rate_col, (denom_col, _k) in spec.items():
        if rate_col not in sub.columns or denom_col not in sub.columns:
            means[rate_col] = float(sub.get(rate_col, pd.Series([0])).mean(skipna=True) or 0.0)
            continue
        d = sub[[rate_col, denom_col]].dropna()
        d = d[d[denom_col] > 0]
        if d.empty:
            means[rate_col] = float(sub[rate_col].mean(skipna=True) or 0.0)
        else:
            means[rate_col] = float((d[rate_col] * d[denom_col]).sum() / d[denom_col].sum())
    return means


def apply_shrinkage(df, pop_means, spec):
    out = _ensure_derived(df.copy())
    for rate_col, (denom_col, k) in spec.items():
        if rate_col not in out.columns or denom_col not in out.columns:
            mu = pop_means.get(rate_col, 0.0)
            out[rate_col + '_sh'] = mu
            continue
        n = out[denom_col].astype(float)
        obs = out[rate_col].astype(float)
        mean = pop_means.get(rate_col, float(np.nanmean(obs) or 0.0))
        obs_filled = obs.fillna(mean)
        n_eff = n.fillna(0.0)
        out[rate_col + '_sh'] = (n_eff * obs_filled + k * mean) / (n_eff + k)
    return out


def cross_year_eval(df, feats, subset_mask=None):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    per_year, preds_all, acts_all, test_indices = {}, [], [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(test)}
        preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
        test_indices.extend(test.index.tolist())
    if subset_mask is not None:
        preds_arr = np.array(preds_all); acts_arr = np.array(acts_all)
        idx_arr = np.array(test_indices)
        keep = subset_mask.reindex(idx_arr).fillna(False).values
        preds_arr = preds_arr[keep]; acts_arr = acts_arr[keep]
        if len(preds_arr) < 30:
            return per_year, {'r': np.nan, 'mae': np.nan, 'n': len(preds_arr)}
        r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
        mae = float(np.mean(np.abs(preds_arr - acts_arr)))
        return per_year, {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(preds_arr)}
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}


def lineup_change_mask(df: pd.DataFrame) -> pd.Series:
    """Rows where current lineup spot differs from prior-year lineup spot by >= 1.5
    AND has lag data."""
    has_lag = df['lineup_spot_lag1'].notna()
    gap = (df['lineup_spot_to'] - df['lineup_spot_lag1']).abs()
    return has_lag & (gap >= 1.5)


def train_final(df, feats):
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
    print('=== xfp_rh4_pipeline (RoS hitter + lineup-spot features) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    # Marcel prior
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    # Lineup lag from prior-year final-cutoff rolling row
    lineup_lag = build_lineup_lag(rolling)
    rolling = rolling.merge(lineup_lag, left_on=['batter','year'],
                             right_on=['batter','year_target'], how='left').drop(columns=['year_target'], errors='ignore')
    # Backfill missing lag with population mean (rookies/returnees -> default = 5.5 = mid-order)
    pop_lineup_spot = float(rolling['lineup_spot_to'].mean())
    rolling['lineup_spot_lag1'] = rolling['lineup_spot_lag1'].fillna(pop_lineup_spot)
    rolling['started_pct_lag1'] = rolling['started_pct_lag1'].fillna(0.0)
    # Backfill current-year lineup features (NaN if rookie hasn't appeared in lineup yet)
    rolling['lineup_spot_to'] = rolling['lineup_spot_to'].fillna(pop_lineup_spot)
    rolling['started_pct_to'] = rolling['started_pct_to'].fillna(0.0)
    rolling['pa_per_started_game_to'] = rolling['pa_per_started_game_to'].fillna(rolling['pa_per_started_game_to'].mean())

    # Shrinkage on cumulative features (RH3 carry-over)
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)

    # Identify lineup-change subset
    lc_mask = lineup_change_mask(rolling)
    print(f'\nLineup-change subset (|lineup_spot_to − lineup_spot_lag1| >= 1.5 AND has lag): {lc_mask.sum()} rows')

    # Baseline RH3
    print('\n--- BASELINE RH3 (BASE_FEATS only) ---')
    _per, baseline_overall = cross_year_eval(rolling, BASE_FEATS)
    _per, baseline_lc = cross_year_eval(rolling, BASE_FEATS, subset_mask=lc_mask)
    print(f'  Overall:        r={baseline_overall["r"]}  mae={baseline_overall["mae"]}  n={baseline_overall["n"]}')
    print(f'  Lineup-change:  r={baseline_lc["r"]}       mae={baseline_lc["mae"]}      n={baseline_lc["n"]}')

    # RH4
    print('\n--- RH4 (BASE + lineup features) ---')
    per_year, overall = cross_year_eval(rolling, FEATS_RH4)
    _per, overall_lc = cross_year_eval(rolling, FEATS_RH4, subset_mask=lc_mask)
    for y, m in sorted(per_year.items()):
        print(f'  {y}: r={m["r"]:.4f}  mae={m["mae"]:.4f}  n={m["n"]}')
    print(f'  Overall:        r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')
    print(f'  Lineup-change:  r={overall_lc["r"]}       mae={overall_lc["mae"]}      n={overall_lc["n"]}')

    delta_overall = overall['r'] - baseline_overall['r']
    delta_lc      = overall_lc['r'] - baseline_lc['r']
    print(f'\n--- GATE EVALUATION ---')
    print(f'  Δr overall (gate ≥ 0.0):       {delta_overall:+.4f}  '
          f'{"PASS" if delta_overall >= 0.0 else "FAIL"}')
    print(f'  Δr lineup-change (gate ≥ +0.05): {delta_lc:+.4f}  '
          f'{"PASS" if delta_lc >= 0.05 else "FAIL"}')

    if delta_overall < 0.0:
        print('\nOVERALL r REGRESSED — rejecting RH4 (would degrade general accuracy).')
        return
    if delta_lc < 0.05:
        print('\nLINEUP-CHANGE subset DID NOT IMPROVE — features have no signal where it matters.')
        print('Documenting negative result; not promoting.')
        return

    print('\n[BOTH GATES PASSED] Promoting RH4 to production.')

    # Train final
    pipe, n_train = train_final(rolling, FEATS_RH4)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RH4 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}, '
          f'{len(FEATS_RH4)} features) ---')
    print('  Top 12 coefficients:')
    for f, c in sorted(zip(FEATS_RH4, coefs), key=lambda x: -abs(x[1]))[:12]:
        print(f'    {f:<26s} {c:+.4f}')
    print('  NEW feature coefficients:')
    for f, c in zip(FEATS_RH4, coefs):
        if f in NEW_FEATS:
            print(f'    {f:<26s} {c:+.4f}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['pa_to'] >= EVAL_PA_MIN)]
    valid = df_26.dropna(subset=FEATS_RH4).copy()
    valid['xfp_rh4_per_pa'] = pipe.predict(valid[FEATS_RH4].values)

    # Names + position
    names = multiyr[multiyr['year'] == 2026][['batter', 'player_name', 'team']].drop_duplicates('batter')
    valid = valid.drop_duplicates('batter').merge(names, on='batter', how='left')
    if MASTER_HITTER.exists():
        mh = pd.read_csv(MASTER_HITTER)
        keep = [c for c in ['batter', 'primary_position', 'fantasy_positions',
                            'fantasy_positions_display']
                if c in mh.columns]
        valid = valid.merge(mh[keep], on='batter', how='left')
    if 'primary_position' not in valid.columns:
        valid['primary_position'] = None

    games_played_so_far = max(latest_split, 1)
    games_remaining = max(SEASON_GAMES - games_played_so_far, 0)
    pa_pace = valid['pa_to'] / games_played_so_far
    valid['expected_pa_remaining'] = (pa_pace * games_remaining).round(0)
    valid['expected_total_fp_remaining'] = (
        valid['xfp_rh4_per_pa'] * valid['expected_pa_remaining']
    ).round(1)

    # Replacement-level
    def _norm_pos(p):
        if not isinstance(p, str): return 'UTIL'
        p = p.upper().strip()
        if p in ('LF','CF','RF','OF'): return 'OF'
        if p in ('C','1B','2B','SS','3B','DH'): return p
        return 'UTIL'
    valid['_pos'] = valid['primary_position'].map(_norm_pos)
    repl = {}
    for pos, n in REPLACEMENT_RANK.items():
        sub = valid[valid['_pos'] == pos].sort_values('xfp_rh4_per_pa', ascending=False)
        if len(sub) >= n:
            repl[pos] = float(sub['xfp_rh4_per_pa'].iloc[n - 1])
        elif not sub.empty:
            repl[pos] = float(sub['xfp_rh4_per_pa'].iloc[-1])
        else:
            repl[pos] = float(valid['xfp_rh4_per_pa'].median())
    valid['replacement_xfp_per_pa'] = valid['_pos'].map(repl)
    valid['replacement_delta'] = (valid['xfp_rh4_per_pa'] - valid['replacement_xfp_per_pa']).round(4)
    valid = valid.drop(columns=['_pos'])

    valid = valid.sort_values('xfp_rh4_per_pa', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': FEATS_RH4,
        'features_baseline': BASE_FEATS,
        'features_new': NEW_FEATS,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rh3_r': baseline_overall['r'],
        'lineup_change_r': overall_lc['r'],
        'lineup_change_baseline_r': baseline_lc['r'],
        'delta_overall': round(delta_overall, 4),
        'delta_lineup_change': round(delta_lc, 4),
        'per_year_r': per_year,
        'training_years': TRAIN_YEARS,
        'replacement_rank': REPLACEMENT_RANK,
        'gate_overall': 0.0,
        'gate_lineup_change': 0.05,
        'pa_per_game_league': PA_PER_GAME_LEAGUE,
        'season_games': SEASON_GAMES,
        'pop_means_to': pop_to,
        'shrink_spec_to': SHRINK_SPEC_TO,
        'pop_lineup_spot': pop_lineup_spot,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rh4',
        'note': 'RoS hitter Ridge + statcast-derived lineup-spot features. '
                'Stratified-validated.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    out_cols = ['rank','batter','player_name','team','primary_position',
                'pa_to','lineup_spot_to','started_pct_to','lineup_spot_lag1',
                'prior_fp_per_pa','xfp_rh4_per_pa',
                'expected_pa_remaining','expected_total_fp_remaining',
                'replacement_xfp_per_pa','replacement_delta']
    out_cols = [c for c in out_cols if c in valid.columns]
    valid[out_cols].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} hitters')

    print('\nTop 15 by RoS xFP/PA:')
    print(valid.head(15)[['rank','player_name','primary_position','team','pa_to',
                          'lineup_spot_to','xfp_rh4_per_pa','replacement_delta']].to_string(index=False))


if __name__ == '__main__':
    main()
