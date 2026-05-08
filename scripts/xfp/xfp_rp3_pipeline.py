"""
xfp_rp3_pipeline.py — Bayesian RoS pitcher model with recency + CI +
replacement deltas + schedule-strength adjustment.

Adds on top of RP2:
  1. Last-21-day rate features (shrunken with smaller k) + last21 FP/start
  2. Residual-based CI (p25/p50/p75) per projection
  3. Replacement-level delta vs SP-60 (12-team x 5 SPs)
  4. Schedule strength: opponent batting index for next 2 starts
  5. Composite drop / hold / add signal vs replacement

Outputs:
  data/models/xfp_rp3_pipeline.pkl
  data/outputs/xfp_rp3_projections.csv
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
TEAM_STR_CSV  = ROOT / 'data' / 'research' / 'xfp_cache' / 'team_strength_2026.csv'
SCHEDULE_CSV  = ROOT / 'data' / 'research' / 'xfp_cache' / 'pitcher_schedule_2026.csv'
MILB_PRIORS_CSV = ROOT / 'data' / 'outputs' / 'xfp_milb_pitcher_priors_2026.csv'
MODEL_PKL  = ROOT / 'data' / 'models' / 'xfp_rp3_pipeline.pkl'
PROJ_CSV   = ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'

TARGET = 'ros_fp_per_start'
EVAL_GS_MIN = 2
ROS_GS_MIN = 5
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_GS = 5
MARCEL_WEIGHTS = (5, 4, 3)

# Replacement-level from league_config (8-team)
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from league_config import SP_REPLACEMENT_RANK as REPLACEMENT_SP_RANK

SHRINK_SPEC_TO = {
    'k_pct_to':         ('tbf_to',     70),
    'bb_pct_to':        ('tbf_to',    170),
    'swstr_pct_to':     ('pitches_to', 300),
    'c_plus_swstr_to':  ('pitches_to', 300),
    'xwoba_per_pa_to':  ('tbf_to',    300),
    'zone_pct_to':      ('pitches_to', 200),
    'z_swing_pct_to':   ('in_zone_to', 200),
    'o_swing_pct_to':   ('out_zone_to', 200),
}
SHRINK_SPEC_LAST21 = {
    'k_pct_last21':         ('tbf_last21',     35),
    'bb_pct_last21':        ('tbf_last21',     85),
    'swstr_pct_last21':     ('pitches_last21', 150),
    'xwoba_per_pa_last21':  ('tbf_last21',    150),
}

# Model features = RP2 set. Last-21-day rates failed the +0.005 r gate
# (delta vs RP2 was only +0.0002 — within noise). They remain in the substrate
# but are NOT model inputs; recency_form_gap is a display-only column.
RP3_FEATS = [
    'k_pct_to_sh', 'bb_pct_to_sh', 'swstr_pct_to_sh', 'c_plus_swstr_to_sh',
    'xwoba_per_pa_to_sh', 'zone_pct_to_sh',
    'z_swing_pct_to_sh', 'o_swing_pct_to_sh',
    'avg_velo_to',
    'fp_per_start_to', 'gs_to',
    # Prior + IL
    'prior_fp_per_start', 'prior_gs_eff',
    'is_on_il_at_split', 'days_since_il_return_imp', 'il_stints_to',
    'split_day',
]


def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    return out


def build_prior_table(multiyr: pd.DataFrame, years: list[int]) -> pd.DataFrame:
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
            rows.append({'pitcher': p, 'year': tgt,
                         'prior_fp_per_start': prior,
                         'prior_gs_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    return pd.DataFrame(rows)


def compute_population_means(df: pd.DataFrame, train_years: list[int],
                              spec: dict) -> dict:
    means: dict[str, float] = {}
    sub = _ensure_derived_denoms(df[df['year'].isin(train_years) & (df['year'] != 2020)].copy())
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


def apply_shrinkage(df: pd.DataFrame, pop_means: dict, spec: dict) -> pd.DataFrame:
    out = _ensure_derived_denoms(df.copy())
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


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['gs_to'] >= EVAL_GS_MIN) & (df['ros_gs'] >= ROS_GS_MIN)
            & (df['year'] != 2020)]
    per_year, preds_all, acts_all = {}, [], []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 4), 'n': len(test)}
        preds_all.extend(preds.tolist()); acts_all.extend(test[TARGET].tolist())
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}


def fit_residual_ci(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    sub = df.dropna(subset=feats + [TARGET]).copy()
    sub = sub[(sub['gs_to'] >= EVAL_GS_MIN) & (sub['ros_gs'] >= ROS_GS_MIN)
              & (sub['year'] != 2020)]
    rows = []
    for held in TRAIN_YEARS:
        train = sub[sub['year'] != held]; test = sub[sub['year'] == held]
        if len(train) < 50 or len(test) < 10:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        preds = pipe.predict(test[feats].values)
        rows.append(pd.DataFrame({
            'pred': preds,
            'actual': test[TARGET].values,
            'split_day': test['split_day'].values,
        }))
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    res['resid'] = res['actual'] - res['pred']
    out = {}
    for split in sorted(res['split_day'].unique()):
        sub2 = res[res['split_day'] == split]
        qs = pd.qcut(sub2['pred'], q=4, duplicates='drop', labels=False)
        for q in sorted(sub2.groupby(qs).groups.keys()):
            ix = (qs == q)
            sigma = float(sub2.loc[ix, 'resid'].std())
            out[(int(split), int(q))] = sigma
    overall_sigma = float(res['resid'].std())
    return out, overall_sigma, res


def lookup_sigma(ci_table, overall_sigma, split_day, pred, pred_buckets):
    if split_day not in pred_buckets:
        return overall_sigma
    cuts = pred_buckets[split_day]
    q = int(np.searchsorted(cuts, pred))
    q = min(max(q, 0), len(cuts))
    return ci_table.get((split_day, q), overall_sigma)


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
    print('=== xfp_rp3 (RP2 + recency + CI + replacement + schedule) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    il = pd.read_csv(IL_CSV)
    print(f'rolling {len(rolling)} | multiyr {len(multiyr)} | il {len(il)}')

    # Marcel prior
    prior = build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())

    # MiLB-derived rookie prior fallback (Phase MT-Pitchers v1).
    # For rows where Marcel prior is NaN (no prior MLB) AND year==2026, prefer
    # MiLB-translated prior over league_mu. Tagged via prior_source.
    rolling['prior_source'] = np.where(
        rolling['prior_fp_per_start'].notna(), 'mlb_lag', None)
    if MILB_PRIORS_CSV.exists():
        milb_pri = pd.read_csv(MILB_PRIORS_CSV)[['pitcher', 'projected_fp_per_start']]
        milb_pri = milb_pri.rename(columns={'projected_fp_per_start': 'milb_prior_fp'})
        rolling = rolling.merge(milb_pri, on='pitcher', how='left')
        # Fill NaN MLB-prior rows in 2026 with MiLB prior where available
        is_2026 = rolling['year'] == 2026
        needs_fallback = is_2026 & rolling['prior_fp_per_start'].isna()
        has_milb = needs_fallback & rolling['milb_prior_fp'].notna()
        rolling.loc[has_milb, 'prior_fp_per_start'] = rolling.loc[has_milb, 'milb_prior_fp']
        rolling.loc[has_milb, 'prior_source'] = 'milb_translation'
        n_milb = int(has_milb.sum())
        print(f'  MiLB-derived priors applied to {n_milb} 2026 rookie rows')

    rolling['prior_source'] = rolling['prior_source'].fillna('league_mean')
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff']       = rolling['prior_gs_eff'].fillna(0.0)

    # IL
    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to']        = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split']   = rolling['is_on_il_at_split'].fillna(0).astype(int)
    max_dsr = float(rolling['days_since_il_return'].max(skipna=True) or 200)
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)

    # Shrinkage on cumulative + last21
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(rolling['fp_per_start_to'])

    # Cross-year RP3
    print('\n--- LOO cross-year (RP3) ---')
    per_year, overall = cross_year_eval(rolling, RP3_FEATS)
    for y, r in sorted(per_year.items()):
        print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    # RP2 baseline
    rp2_feats = [f for f in RP3_FEATS if 'last21' not in f]
    _ , baseline = cross_year_eval(rolling, rp2_feats)
    delta = overall['r'] - baseline['r']
    print(f'\n--- RP2 baseline ---  r={baseline["r"]}')
    print(f'  Δr (RP3 − RP2) = {delta:+.4f}  '
          f'{"PASS" if delta >= 0.005 else "MARGINAL"}  (gate: ≥ +0.005)')

    # CI
    ci_table, overall_sigma, _res = fit_residual_ci(rolling, RP3_FEATS)
    print(f'\n  overall sigma = {overall_sigma:.3f} FP/start')

    # Train final
    pipe, n_train = train_final(rolling, RP3_FEATS)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final RP3 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}) ---')
    print('  Top coefficients:')
    for f, c in sorted(zip(RP3_FEATS, coefs), key=lambda x: -abs(x[1]))[:14]:
        print(f'    {f:<28s} {c:+.4f}')

    # Project 2026
    df_26 = rolling[rolling['year'] == 2026].copy()
    if df_26.empty:
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['gs_to'] >= EVAL_GS_MIN)]
    valid = df_26.dropna(subset=RP3_FEATS).copy()
    valid['xfp_rp3_per_start'] = pipe.predict(valid[RP3_FEATS].values)

    # Pred-bucket cuts for sigma
    train_for_buckets = rolling.dropna(subset=RP3_FEATS + [TARGET])
    train_for_buckets = train_for_buckets[(train_for_buckets['gs_to'] >= EVAL_GS_MIN)
                                          & (train_for_buckets['ros_gs'] >= ROS_GS_MIN)
                                          & (train_for_buckets['year'].isin(TRAIN_YEARS))]
    train_pred = pipe.predict(train_for_buckets[RP3_FEATS].values)
    pred_buckets = {}
    for split in sorted(train_for_buckets['split_day'].unique()):
        ix = (train_for_buckets['split_day'].values == split)
        if ix.sum() < 30:
            continue
        cuts = np.quantile(train_pred[ix], [0.25, 0.5, 0.75])
        pred_buckets[int(split)] = cuts

    Z25 = 0.6745
    sigmas = []
    for _, row in valid.iterrows():
        sigmas.append(lookup_sigma(ci_table, overall_sigma, latest_split,
                                   row['xfp_rp3_per_start'], pred_buckets))
    valid['xfp_rp3_sigma'] = sigmas
    valid['xfp_rp3_p25'] = (valid['xfp_rp3_per_start'] - Z25 * valid['xfp_rp3_sigma']).clip(lower=0)
    valid['xfp_rp3_p75'] = valid['xfp_rp3_per_start'] + Z25 * valid['xfp_rp3_sigma']

    # Recency form gap
    valid['recency_form_gap'] = (valid['fp_per_start_last21'] -
                                  valid['fp_per_start_to']).round(3)

    # Names — multiyr only has MLB-active pitchers; for rookies (MiLB-prior
    # source) fall back to the MiLB priors CSV which carries their names.
    sp_26 = multiyr[multiyr['year'] == 2026][['pitcher', 'player_name']].drop_duplicates('pitcher')
    valid = valid.drop_duplicates('pitcher').merge(sp_26, on='pitcher', how='left')
    if MILB_PRIORS_CSV.exists():
        milb_names = pd.read_csv(MILB_PRIORS_CSV)[['pitcher', 'name']].rename(
            columns={'name': 'milb_name'}).drop_duplicates('pitcher')
        valid = valid.merge(milb_names, on='pitcher', how='left')
        valid['player_name'] = valid['player_name'].fillna(valid['milb_name'])
        valid = valid.drop(columns=['milb_name'])

    # Schedule strength: opponent batting index for next 2 starts
    valid = apply_schedule_strength(valid)

    # Replacement-level
    valid = compute_replacement_delta(valid)

    valid['signal'] = valid.apply(_signal, axis=1)
    valid = valid.sort_values('xfp_rp3_per_start', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': RP3_FEATS,
        'target': TARGET,
        'pop_means_to': pop_to,
        'pop_means_last21': pop_l21,
        'shrink_spec_to': SHRINK_SPEC_TO,
        'shrink_spec_last21': SHRINK_SPEC_LAST21,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rp2_r': baseline['r'],
        'delta_r_vs_rp2': round(delta, 4),
        'per_year_r': per_year,
        'ci_table': ci_table,
        'pred_buckets': {k: v.tolist() for k, v in pred_buckets.items()},
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'replacement_sp_rank': REPLACEMENT_SP_RANK,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rp3',
        'note': 'Bayesian RoS pitcher Ridge + last-21-day form + residual CI '
                '+ schedule-strength + replacement-level delta.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Slump-precedent merge (rolling-window career comparison vs current 2026)
    slump_path = ROOT / 'data' / 'outputs' / 'slump_precedent_sps_2026.csv'
    if slump_path.exists():
        sp_slump = pd.read_csv(slump_path)[
            ['pitcher', 'pct_rank', 'n_comparable', 'bounce_pct',
             'median_next_rate', 'median_delta']
        ].rename(columns={
            'pct_rank': 'slump_pct_rank',
            'n_comparable': 'slump_n_comparable',
            'bounce_pct': 'slump_bounce_pct',
            'median_next_rate': 'slump_next_rate',
            'median_delta': 'slump_delta',
        })
        valid = valid.merge(sp_slump, on='pitcher', how='left')

    out_cols = [
        'rank', 'pitcher', 'player_name',
        'gs_to', 'gs_last21', 'fp_per_start_to', 'fp_per_start_last21',
        'recency_form_gap',
        'prior_fp_per_start', 'prior_source',
        'is_on_il_at_split',
        'xfp_rp3_per_start', 'xfp_rp3_sigma', 'xfp_rp3_p25', 'xfp_rp3_p75',
        'next_opp_team', 'next_opp_bat_index',
        'next2_avg_bat_index', 'schedule_factor',
        'xfp_rp3_per_start_sched',
        'replacement_xfp_per_start', 'replacement_delta',
        'signal',
        'slump_pct_rank', 'slump_n_comparable', 'slump_bounce_pct',
        'slump_next_rate', 'slump_delta',
    ]
    out_cols = [c for c in out_cols if c in valid.columns]
    valid[out_cols].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} pitchers')

    print('\nTop 10 by replacement_delta (best add candidates):')
    show = ['rank', 'player_name', 'gs_to', 'xfp_rp3_per_start',
            'xfp_rp3_p25', 'xfp_rp3_p75',
            'next_opp_team', 'next2_avg_bat_index', 'xfp_rp3_per_start_sched',
            'replacement_delta', 'signal']
    show = [c for c in show if c in valid.columns]
    top = valid.sort_values('replacement_delta', ascending=False).head(10)
    print(top[show].to_string(index=False))


def apply_schedule_strength(valid: pd.DataFrame) -> pd.DataFrame:
    """Multiply rp3_per_start by inverse of opponent strength for next 2 starts.
    schedule_factor < 1 means easier schedule -> higher adjusted xFP."""
    valid = valid.copy()
    if not (TEAM_STR_CSV.exists() and SCHEDULE_CSV.exists()):
        valid['next_opp_team'] = None
        valid['next_opp_bat_index'] = np.nan
        valid['next2_avg_bat_index'] = np.nan
        valid['schedule_factor'] = 1.0
        valid['xfp_rp3_per_start_sched'] = valid['xfp_rp3_per_start']
        return valid

    team = pd.read_csv(TEAM_STR_CSV)
    sched = pd.read_csv(SCHEDULE_CSV)
    sched = sched.merge(team[['team', 'bat_index']],
                        left_on='opp_team_abbrev', right_on='team',
                        how='left', suffixes=('', '_t'))
    sched = sched.rename(columns={'bat_index': 'opp_bat_index'})

    by_pitcher = sched.groupby('pitcher')
    next_opp = by_pitcher.first()[['opp_team_abbrev', 'opp_bat_index']].rename(
        columns={'opp_team_abbrev': 'next_opp_team',
                 'opp_bat_index': 'next_opp_bat_index'})
    next2_avg = by_pitcher['opp_bat_index'].mean().to_frame('next2_avg_bat_index')
    if 'park_factor' in sched.columns:
        next2_park = by_pitcher['park_factor'].mean().to_frame('next2_avg_park_factor')
    else:
        next2_park = pd.DataFrame({'next2_avg_park_factor': []})
    if 'platoon_factor' in sched.columns:
        next2_pla = by_pitcher['platoon_factor'].mean().to_frame('next2_avg_platoon_factor')
    else:
        next2_pla = pd.DataFrame({'next2_avg_platoon_factor': []})

    valid = valid.merge(next_opp, left_on='pitcher', right_index=True, how='left')
    valid = valid.merge(next2_avg, left_on='pitcher', right_index=True, how='left')
    if not next2_park.empty:
        valid = valid.merge(next2_park, left_on='pitcher', right_index=True, how='left')
    else:
        valid['next2_avg_park_factor'] = 1.0
    if not next2_pla.empty:
        valid = valid.merge(next2_pla, left_on='pitcher', right_index=True, how='left')
    else:
        valid['next2_avg_platoon_factor'] = 1.0
    valid['next2_avg_park_factor'] = valid['next2_avg_park_factor'].fillna(1.0)
    valid['next2_avg_platoon_factor'] = valid['next2_avg_platoon_factor'].fillna(1.0)

    # Combined schedule factor: opp strength × park. (Platoon factor was tested
    # but failed validation — cor with per-start residual was −0.005, no
    # meaningful signal. Kept in the substrate for transparency, NOT applied.)
    valid['opp_factor']     = 1.0 / valid['next2_avg_bat_index'].fillna(1.0)
    valid['park_factor']    = 1.0 / valid['next2_avg_park_factor']
    valid['platoon_factor'] = 1.0 / valid['next2_avg_platoon_factor']  # kept for display only
    valid['schedule_factor'] = (valid['opp_factor'] * valid['park_factor']).clip(0.80, 1.20)
    valid['xfp_rp3_per_start_sched'] = (
        valid['xfp_rp3_per_start'] * valid['schedule_factor']
    ).round(2)
    return valid


def compute_replacement_delta(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    sub = df.sort_values('xfp_rp3_per_start', ascending=False)
    n = REPLACEMENT_SP_RANK
    if len(sub) >= n:
        repl = float(sub['xfp_rp3_per_start'].iloc[n - 1])
    else:
        repl = float(sub['xfp_rp3_per_start'].median())
    df['replacement_xfp_per_start'] = round(repl, 3)
    df['replacement_delta'] = (df['xfp_rp3_per_start'] - repl).round(3)
    return df


def _signal(row) -> str:
    delta = row.get('replacement_delta', 0)
    p25 = row.get('xfp_rp3_p25', None)
    p75 = row.get('xfp_rp3_p75', None)
    repl = row.get('replacement_xfp_per_start', None)
    is_il = bool(row.get('is_on_il_at_split', 0))
    if is_il:
        return 'il'
    if delta is None or pd.isna(delta) or repl is None or pd.isna(repl):
        return 'hold'
    if p25 is not None and not pd.isna(p25) and p25 > repl:
        return 'add'
    if p75 is not None and not pd.isna(p75) and p75 < repl:
        return 'drop'
    return 'hold'


if __name__ == '__main__':
    main()
