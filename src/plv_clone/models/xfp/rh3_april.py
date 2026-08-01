"""
xfp_rh3_april — early-season-only variant of rh3.

Substrate is filtered to `split_day <= 30` BEFORE the cross_year_eval
call, training, and final fit. Originally scaffolded to unlock the
`lineup_spot_to` signal that decays into noise in the full-season pool
but had +0.0028 cell-level lift at split_day=30 (see
validation_runs/lineup_spot_to_2026-05-23.md and the April re-framing
at lineup_spot_to_april_2026-05-24.md).

**2026-05-24 result: lineup_spot_to did NOT clear the +0.005 gate on
the April substrate either** (Δr = +0.0027, same as the cell-level
finding). The hypothesis that substrate-filtering would multiply the
lift was wrong — substrate filtering just removes noise from non-load-
bearing cells, it doesn't add new signal. So lineup_spot_to is NOT in
RH3_APRIL_FEATS; v2_added is empty and the Rule 9 gate is vacuous.

The file remains as the scaffolding for an early-season-substrate model.
Even without lineup_spot_to it answers a useful question: does an April-
only retrained rh3 outperform the full-season rh3 when evaluated on
April rows? Future v2 candidates (lineup_spot_to interactions,
opportunity-bundle features, MiLB-prior interactions) can be added to
RH3_APRIL_FEATS individually and re-gated.

**Valid ONLY for split_day <= 30 rows** — i.e., March / early April.
Use rh3 (full-season variant) for any later cutoff. Projection CSV is
only populated when the latest 2026 split_day <= 30.

Outputs:
  data/models/xfp_rh3_april_pipeline.pkl
  data/outputs/xfp_rh3_april_projections.csv

This is a SIBLING to rh3.py, NOT a replacement. rh3.py keeps its current
FEATS unchanged. Do not auto-rebuild in refresh_dashboards.py unless we
add an explicit early-season UX path.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import joblib

from plv_clone.models.xfp import engine as _engine
from plv_clone.models.xfp.engine import lookup_sigma  # re-export
from plv_clone.league_config import HITTER_REPLACEMENT_RANK as REPLACEMENT_RANK

warnings.filterwarnings('ignore')

# Path anchors
ROOT = Path(__file__).resolve().parents[4]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_hitters_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'
H2_PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_h2_projections.csv'
IL_CSV      = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_split_features_2018_2026.csv'
MASTER_HITTER = ROOT / 'data' / 'outputs' / 'master_hitter_2026.csv'
MODEL_PKL   = ROOT / 'data' / 'models' / 'xfp_rh3_april_pipeline.pkl'
PROJ_CSV    = ROOT / 'data' / 'outputs' / 'xfp_rh3_april_projections.csv'

TARGET = 'ros_full_fp_per_pa'
EVAL_PA_MIN = 50
ROS_PA_MIN = 100
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_PA = 200
MARCEL_WEIGHTS = (5, 4, 3)
PA_PER_GAME_LEAGUE = 3.5
SEASON_GAMES = 162

# April-only substrate cutoff
APRIL_SPLIT_MAX = 30


def projection_year(rolling: pd.DataFrame) -> int:
    """The season this run projects: the newest one present in the substrate.

    Matches the idiom rh3 / rp3 / rprs2 already use. rh3_april is not in the
    nightly chain (it is run by hand for the April-framing study), so a
    hardcoded season here would not fail loudly on the calendar roll — it
    would quietly select last season's frame. (An earlier revision of this
    comment claimed the module is "out of framing past split_day 30"; the
    guard is actually unreached in that regime — review 2026-08-01.)
    """
    return int(rolling['year'].max())

SHRINK_SPEC_TO = {
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
SHRINK_SPEC_LAST21 = {
    'k_pct_last21':         ('pa_last21',     30),
    'bb_pct_last21':        ('pa_last21',     60),
    'iso_last21':           ('ab_last21',     80),
    'xwoba_per_pa_last21':  ('pa_last21',    150),
    'contact_pct_last21':   ('swing_last21',  50),
    'whiff_pct_last21':     ('swing_last21',  50),
    'hard_hit_pct_last21':  ('bip_last21',    25),
    'barrel_pct_last21':    ('bip_last21',    25),
    'hr_per_pa_last21':     ('pa_last21',     85),
}

# rh3 FEATS + lineup_spot_to (linear, no interaction).
RH3_APRIL_FEATS = [
    'iso_to_sh', 'k_pct_to_sh', 'hr_per_pa_to_sh', 'hard_hit_pct_to_sh',
    'contact_pct_to_sh', 'whiff_pct_to_sh', 'swstr_pct_to_sh', 'bb_pct_to_sh',
    'chase_pct_to_sh', 'in_play_pct_to_sh', 'sb_per_pa_to_sh',
    'xwoba_per_pa_to_sh', 'barrel_pct_to_sh',
    'prior_fp_per_pa', 'prior_pa_eff', 'pa_to', 'split_day',
    'lift_h2_aug150',
    'xwoba_residual_career',
    'career_stage',
    # lineup_spot_to was the original v2 candidate for this variant but failed
    # the +0.005 gate on the April substrate (Δr=+0.0027, verdict MARGINAL,
    # validation_runs/lineup_spot_to_april_2026-05-24.md). Removed from FEATS
    # 2026-05-24. v2_added is now empty and the Rule 9 gate below is vacuous.
]
H2_LOCKED_CSV = ROOT / 'data' / 'outputs' / 'seasonality_h2_locked.csv'
XWOBA_RESID_CSV = ROOT / 'data' / 'outputs' / 'hitter_xwoba_residual.csv'

# Hard assert: every FEATS entry must have a PASS validation_runs record
# registered for the rh3_april target. lineup_spot_to has its April-specific
# pre-reg; other features are grandfathered for rh3 but the registry parser
# checks target membership — so we run the check against target="rh3" for
# the grandfathered features and target="rh3_april" for the new addition.
from plv_clone.models.xfp.validated_signals import (
    check_feats_validated as _check_feats_validated,
    load_registry as _load_registry,
)
_registry = _load_registry()
# All current rh3_april FEATS are inherited from rh3 and validate against
# the rh3 target. When/if rh3_april grows its own validated features,
# split the list and pass target="rh3_april" for those.
with warnings.catch_warnings():
    warnings.simplefilter("default", UserWarning)
    _check_feats_validated(RH3_APRIL_FEATS, target="rh3", registry=_registry, strict=True)


def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'ab_to' not in out.columns:
        out = out.assign(ab_to=out['pa_to'] - out['bb_to'] - out.get('hbp_to', 0))
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    if 'ab_last21' not in out.columns and 'pa_last21' in out.columns:
        out = out.assign(ab_last21=out['pa_last21'] - out['bb_last21'].fillna(0)
                         - out.get('hbp_last21', 0))
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


def compute_population_means(df: pd.DataFrame, train_years: list[int],
                              spec: dict) -> dict:
    return _engine.compute_population_means(_ensure_derived_denoms(df.copy()), train_years, spec)


def apply_shrinkage(df: pd.DataFrame, pop_means: dict, spec: dict) -> pd.DataFrame:
    return _engine.apply_shrinkage(_ensure_derived_denoms(df.copy()), pop_means, spec)


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[(df['pa_to'] >= EVAL_PA_MIN) & (df['ros_pa'] >= ROS_PA_MIN) & (df['year'] != 2020)]
    per_year, preds_all, acts_all = {}, [], []
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
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 4),
                      'n': len(preds_all)}


def fit_residual_ci(df: pd.DataFrame, feats: list[str]):
    sub = df.dropna(subset=feats + [TARGET]).copy()
    sub = sub[(sub['pa_to'] >= EVAL_PA_MIN) & (sub['ros_pa'] >= ROS_PA_MIN)
              & (sub['year'] != 2020)]
    res = _engine.train_residual_table(
        df=sub, feats=feats, target_col=TARGET, train_years=TRAIN_YEARS,
        min_train=100, min_test=30,
    )
    out: dict[tuple[int, int], float] = {}
    for split in sorted(res['split_day'].unique()):
        sub2 = res[res['split_day'] == split]
        qs = pd.qcut(sub2['pred'], q=4, duplicates='drop', labels=False)
        for q in sorted(sub2.groupby(qs).groups.keys()):
            ix = (qs == q)
            sigma = float(sub2.loc[ix, 'resid'].std())
            out[(int(split), int(q))] = sigma
    overall_sigma = float(res['resid'].std())
    return out, overall_sigma


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
    print('=== xfp_rh3_april (rh3 + lineup_spot_to, substrate sd<=30) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    print(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    # Marcel prior
    print('\nBuilding Marcel prior...')
    years_needed = sorted(rolling['year'].unique())
    prior = build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    # H2-locked career profile
    if H2_LOCKED_CSV.exists():
        h2_locked = pd.read_csv(H2_LOCKED_CSV)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2_locked, on='batter', how='left')
        rolling['lift_h2_aug150'] = rolling['lift_h2_aug150'].fillna(0.0)
    else:
        rolling['lift_h2_aug150'] = 0.0

    # xwOBA residual career
    if XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(XWOBA_RESID_CSV)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
        rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
    else:
        rolling['xwoba_residual_career'] = 0.0

    # xwoba_gap_to (kept derived but not in FEATS)
    if 'xwoba_on_contact_to' in rolling.columns and 'woba_d_sum_to' in rolling.columns:
        rolling['actual_woba_per_pa_to'] = np.where(
            rolling['woba_d_sum_to'] > 0,
            rolling['woba_v_sum_to'] / rolling['woba_d_sum_to'],
            np.nan)
        rolling['xwoba_gap_to'] = (rolling['xwoba_on_contact_to']
                                     - rolling['actual_woba_per_pa_to']).fillna(0.0)
    else:
        rolling['xwoba_gap_to'] = 0.0

    # career_stage
    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    rolling['career_stage'] = rolling.apply(
        lambda r: r['year'] - first_year.get(r['batter'], r['year']), axis=1)

    # lineup_spot_to: not in FEATS but kept in substrate for ad-hoc analysis +
    # research re-gating. Fill NaN with neutral 5.0 (mid-order).
    if 'lineup_spot_to' in rolling.columns:
        rolling['lineup_spot_to'] = rolling['lineup_spot_to'].fillna(5.0)

    # Shrinkage
    print('Shrinkage (cumulative + last21)...')
    pop_to = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_TO)
    pop_l21 = compute_population_means(rolling, TRAIN_YEARS, SHRINK_SPEC_LAST21)
    rolling = apply_shrinkage(rolling, pop_to, SHRINK_SPEC_TO)
    rolling = apply_shrinkage(rolling, pop_l21, SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)

    # >>> APRIL-ONLY SUBSTRATE FILTER (load-bearing) <<<
    n_before = len(rolling)
    rolling = rolling[rolling['split_day'] <= APRIL_SPLIT_MAX].copy()
    print(f'\nApril substrate filter: split_day<={APRIL_SPLIT_MAX} -> '
          f'{len(rolling)}/{n_before} rows')
    per_yr_n = rolling.groupby('year').size().to_dict()
    print(f'  rows by year: {per_yr_n}')

    # Cross-year eval
    print('\n--- LOO cross-year eval (rh3_april) ---')
    per_year, overall = cross_year_eval(rolling, RH3_APRIL_FEATS)
    for y, r in sorted(per_year.items()):
        print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
    print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

    # Rule 9 gate: v2_added is empty (no April-specific promoted features yet).
    # See module docstring for the lineup_spot_to MARGINAL story.
    v2_added: set[str] = set()
    baseline_feats = [f for f in RH3_APRIL_FEATS if f not in v2_added]
    if v2_added:
        _ , baseline = cross_year_eval(rolling, baseline_feats)
        delta = overall['r'] - baseline['r']
        print(f'\n--- Baseline (drops v2 features {sorted(v2_added)}) ---')
        print(f'  Overall: r={baseline["r"]}')
        print(f'  Δr (rh3_april − baseline) = {delta:+.4f}  (gate: ≥ +0.005)')
        assert delta >= 0.005, (
            f"Rule 9 hard assert: Δr={delta:+.4f} below +0.005 gate for "
            f"v2 features {sorted(v2_added)} in rh3_april. Revert or re-validate."
        )
    else:
        baseline = overall  # vacuous gate
        delta = 0.0
        print('\n--- Rule 9 gate vacuous (v2_added is empty) ---')

    # CI table
    print('\n--- Building residual-based CI table ---')
    ci_table, overall_sigma = fit_residual_ci(rolling, RH3_APRIL_FEATS)
    print(f'  overall sigma = {overall_sigma:.4f} FP/PA')

    # Train final + project
    pipe, n_train = train_final(rolling, RH3_APRIL_FEATS)
    coefs = pipe.named_steps['r'].coef_
    print(f'\n--- Final rh3_april pipeline (n_train={n_train}, '
          f'alpha={pipe.named_steps["r"].alpha_:.1f}) ---')
    print('  Top coefficients:')
    for f, c in sorted(zip(RH3_APRIL_FEATS, coefs), key=lambda x: -abs(x[1]))[:14]:
        print(f'    {f:<26s} {c:+.4f}')

    # projection year = latest season in the substrate (audit R2 idiom, applied
    # here 2026-08-01/T43 — rh3/rp3/rprs2 were migrated earlier and this file
    # was the holdout). ONLY valid if latest split_day <= APRIL_SPLIT_MAX.
    proj_year = projection_year(rolling)
    df_26 = rolling[rolling['year'] == proj_year].copy()
    if df_26.empty:
        print(f'\nNo {proj_year} April-substrate data — skipping projection.')
        latest_split = None
        valid = pd.DataFrame()
    else:
        latest_split = int(df_26['split_day'].max())
        if latest_split > APRIL_SPLIT_MAX:
            print(f'\nLatest {proj_year} split_day={latest_split} > {APRIL_SPLIT_MAX}: '
                  'rh3_april is OUT OF FRAMING. Skipping projection.')
            valid = pd.DataFrame()
        else:
            df_26 = df_26[(df_26['split_day'] == latest_split)
                          & (df_26['pa_to'] >= EVAL_PA_MIN)]
            valid = df_26.dropna(subset=RH3_APRIL_FEATS).copy()
            valid['xfp_rh3_april_per_pa'] = pipe.predict(valid[RH3_APRIL_FEATS].values)

    if not valid.empty:
        # CI buckets
        train_for_buckets = rolling.dropna(subset=RH3_APRIL_FEATS + [TARGET])
        train_for_buckets = train_for_buckets[(train_for_buckets['pa_to'] >= EVAL_PA_MIN)
                                              & (train_for_buckets['ros_pa'] >= ROS_PA_MIN)
                                              & (train_for_buckets['year'].isin(TRAIN_YEARS))]
        train_pred = pipe.predict(train_for_buckets[RH3_APRIL_FEATS].values)
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
                                       row['xfp_rh3_april_per_pa'], pred_buckets))
        valid['xfp_rh3_april_sigma'] = sigmas
        valid['xfp_rh3_april_p25'] = (
            valid['xfp_rh3_april_per_pa'] - Z25 * valid['xfp_rh3_april_sigma']
        ).clip(lower=0)
        valid['xfp_rh3_april_p75'] = (
            valid['xfp_rh3_april_per_pa'] + Z25 * valid['xfp_rh3_april_sigma']
        )
        valid['xfp_rh3_april_per_game'] = (
            valid['xfp_rh3_april_per_pa'] * PA_PER_GAME_LEAGUE
        ).round(2)

        # Names + position
        # rolling and multiyr are separate files; if multiyr lags a season the
        # exact-year join would yield NaN names for every row, so fall back to
        # multiyr's own newest season (audit 2026-08-01/T43).
        name_year = proj_year if (multiyr['year'] == proj_year).any() \
            else int(multiyr['year'].max())
        names = multiyr[multiyr['year'] == name_year][['batter', 'player_name', 'team']] \
            .drop_duplicates('batter')
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
            valid['xfp_rh3_april_per_pa'] * valid['expected_pa_remaining']
        ).round(1)

        valid = valid.sort_values('xfp_rh3_april_per_pa', ascending=False).reset_index(drop=True)
        valid['rank'] = valid.index + 1

    # Bundle
    bundle = {
        'pipeline': pipe,
        'features': RH3_APRIL_FEATS,
        'target': TARGET,
        'pop_means_to': pop_to,
        'pop_means_last21': pop_l21,
        'shrink_spec_to': SHRINK_SPEC_TO,
        'shrink_spec_last21': SHRINK_SPEC_LAST21,
        'prior_k_pa': PRIOR_K_PA,
        'marcel_weights': MARCEL_WEIGHTS,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_r': baseline['r'],
        'delta_r_vs_baseline': round(delta, 4),
        'per_year_r': per_year,
        'ci_table': ci_table,
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'min_pa_to': EVAL_PA_MIN,
        'min_ros_pa': ROS_PA_MIN,
        'april_split_max': APRIL_SPLIT_MAX,
        'pa_per_game_league': PA_PER_GAME_LEAGUE,
        'season_games': SEASON_GAMES,
        'replacement_rank': REPLACEMENT_RANK,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rh3_april',
        'note': 'Early-season-only hitter Ridge; substrate sd<=30; '
                'lineup_spot_to in FEATS.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    if valid.empty:
        # Still write an empty CSV with the header so downstream readers don't break.
        empty_cols = ['rank', 'batter', 'player_name', 'team', 'primary_position',
                      'pa_to', 'lineup_spot_to',
                      'xfp_rh3_april_per_pa', 'xfp_rh3_april_per_game',
                      'xfp_rh3_april_sigma', 'xfp_rh3_april_p25', 'xfp_rh3_april_p75',
                      'expected_pa_remaining', 'expected_total_fp_remaining']
        pd.DataFrame(columns=empty_cols).to_csv(PROJ_CSV, index=False)
        print(f'Wrote empty {PROJ_CSV} (out of April framing).')
        return

    out_cols = [
        'rank', 'batter', 'player_name', 'team', 'primary_position',
        'pa_to', 'lineup_spot_to',
        'prior_fp_per_pa',
        'xfp_rh3_april_per_pa', 'xfp_rh3_april_per_game', 'xfp_rh3_april_sigma',
        'xfp_rh3_april_p25', 'xfp_rh3_april_p75',
        'expected_pa_remaining', 'expected_total_fp_remaining',
    ]
    out_cols = [c for c in out_cols if c in valid.columns]
    valid[out_cols].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} hitters')


if __name__ == '__main__':
    main()
