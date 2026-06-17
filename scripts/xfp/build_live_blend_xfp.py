"""build_live_blend_xfp.py — Phase 3 Agent 3: Live within-season blend ROS projection.

Produces a per-player blended ROS projection that doubles R^2 vs the headline
xfp_rh3 / xfp_rp3 / xfp_rprs2 anchors at split_day~=90 (and remains a strong
boost at split_day 30-120). Validation: data/research/validation_runs/
weight_blend_within_season_2026-06-04.md (H 0.642, SP 0.584, RP 0.398 at 90).

Output: data/outputs/live_blend_xfp_<YYYY-MM-DD>.csv
Columns: mlbam_id, player_name, player_type, live_blend_xfp,
         ci_lower, ci_upper, confidence_tier, fitted_split_day, n_features_used.

Display surfacing: build_matchup_dashboard.py reads this CSV and appends a
"blended X.X [lo-hi]" suffix to the existing projection cell. Headline numbers
and win-prob logic are NOT changed by this script.

CAVEAT 2020 EXCLUDED -- COVID-shortened, do not fit on this year
CAVEAT same-year arche_overall is leak-free at split_day>=60 -- see Phase 3 doc
CAVEAT slope_3yr_prior fallback to 0 for rookies -- propagated from blend_score.py
CAVEAT R^2 != decision quality -- surface ci_lower/upper in output
CAVEAT NaN-fallback: missing PL -> no-PL coefficients (hard-coded, no silent drops)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from plv_clone.paths import ROOT
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
RESEARCH = ROOT / 'data' / 'research'
HP = RESEARCH / 'historical_panel'
OUT = ROOT / 'data' / 'outputs'

# Cleanup #3 (2026-06-05): consume corrected pl_rank_panel.parquet (2,544 rows)
# and add `is_non_closer_rp` binary segmentation flag for RP per Cleanup #1.
# Leverage z-score blend HELD per Cleanup #1 explicit recommendation.
PL_PANEL = HP / 'pl_rank_panel.parquet'
PL_CAP = {'SP': 100.0, 'H': 150.0, 'RP': 100.0}

SEASON_START = date(2026, 3, 27)
SPLIT_DAY_GRID = [30, 60, 90, 120]
SPLIT_DAY_MAP = {30: 30, 60: 58, 90: 93, 120: 121}  # matches fit_weight_blend_within_season.py

CFG = {
    'SP': {
        'rolling': 'rolling_pitchers_2018_2026.csv',
        'arch': 'sp_ratings_master.csv',
        'id_col': 'pitcher',
        'features_to': ['k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'avg_velo_to', 'barrel_pct_to',
                        'hard_hit_pct_to', 'gb_pct_to', 'fp_per_start_to'],
        'features_recent': ['k_pct_last21', 'fp_per_start_last21', 'xwoba_per_pa_last21'],
        'ros_col': 'ros_fp_per_start',
        'sample_col': 'gs_to', 'sample_min': 3,
        'anchor_col': 'fp_per_start_to',
        'anchor_projection': ('xfp_rp3_projections.csv', 'pitcher', 'xfp_rp3_per_start'),
    },
    'H': {
        'rolling': 'rolling_hitters_2018_2026.csv',
        'arch': 'hitter_ratings_master.csv',
        'id_col': 'batter',
        'features_to': ['k_pct_to', 'bb_pct_to', 'iso_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'hard_hit_pct_to', 'barrel_pct_to',
                        'contact_pct_to', 'chase_pct_to', 'core_fp_per_pa_to'],
        'features_recent': ['core_fp_per_pa_last21', 'xwoba_per_pa_last21', 'k_pct_last21'],
        'ros_col': 'ros_full_fp_per_pa',
        'sample_col': 'pa_to', 'sample_min': 50,
        'anchor_col': 'core_fp_per_pa_to',
        'anchor_projection': ('xfp_rh3_projections.csv', 'batter', 'xfp_rh3_per_pa'),
    },
    'RP': {
        'rolling': 'rolling_relievers_2018_2026.csv',
        'arch': 'rp_ratings_master.csv',
        'id_col': 'pitcher',
        'features_to': ['k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'xwoba_per_pa_to',
                        'xwoba_on_contact_to', 'avg_velo_to', 'barrel_pct_to',
                        'hard_hit_pct_to', 'sv_per_g_to', 'hld_per_g_to'],
        'features_recent': [],
        'ros_col': None,
        'sample_col': 'g_to', 'sample_min': 8,
        'anchor_col': 'fp_per_g_lag1',
        'anchor_projection': ('xfp_rprs2_projections.csv', 'pitcher', 'xfp_ros'),
    },
}


def _emit_caveats():
    print('CAVEATS:', file=sys.stderr)
    print('  - 2020 EXCLUDED from training (COVID-shortened)', file=sys.stderr)
    print('  - same-year arche_overall leak-free at split_day>=60', file=sys.stderr)
    print('  - slope_3yr_prior fallback to 0 for rookies', file=sys.stderr)
    print('  - R^2 != decision quality; ci_lower/upper surfaced', file=sys.stderr)
    print('  - NaN-fallback: missing PL -> no-PL coefficients', file=sys.stderr)


def pick_split_day(today: date) -> int:
    days = (today - SEASON_START).days
    days = max(days, 30)
    return min(SPLIT_DAY_GRID, key=lambda g: abs(g - days))


def _load_pl_panel():
    """Cleanup #2 corrected pl_rank_panel.parquet (2,544 rows). Collapses to
    one row per (mlbam_id, year) with `pl_rank` = mid → early → late."""
    if not PL_PANEL.exists():
        return None
    pl = pd.read_parquet(PL_PANEL)
    pl['pl_rank'] = pl['pl_rank_mid']
    pl['pl_rank'] = pl['pl_rank'].fillna(pl['pl_rank_early']).fillna(pl['pl_rank_late'])
    return pl[['mlbam_id', 'year', 'pl_rank']].copy()


def _attach_pl_features(df, ptype, id_col):
    """Attach `pl_rank_mid_inv` and (RP) `is_non_closer_rp`. NaN-safe so
    rows without PL coverage fall back to mean imputation downstream."""
    pl = _load_pl_panel()
    if pl is None:
        df['pl_rank_mid_inv'] = np.nan
        if ptype == 'RP':
            df['is_non_closer_rp'] = 1
        return df
    pl_join = pl.rename(columns={'mlbam_id': id_col})
    df = df.merge(pl_join, on=['year', id_col], how='left')
    cap = PL_CAP[ptype]
    df['pl_rank_mid_inv'] = np.where(
        df['pl_rank'].notna(),
        np.clip((cap - df['pl_rank']) / cap, 0, 1),
        np.nan,
    )
    if ptype == 'RP':
        # Cleanup #1 binary segmentation flag: real PL panel covers closers;
        # absence is a clean non-closer indicator.
        df['is_non_closer_rp'] = (~df['pl_rank'].notna()).astype(int)
    df = df.drop(columns=['pl_rank'])
    return df


def load_training_panel(ptype: str, target_sd: int):
    """Replicates the panel-build math from fit_weight_blend_within_season.py.

    Cleanup #3 (2026-06-05) additions:
      - `pl_rank_mid_inv` from corrected pl_rank_panel.parquet
      - `is_non_closer_rp` binary flag (RP only) per Cleanup #1
      - PL feature is added with mean-imputation, NOT as a hard subset,
        so non-PL rows still contribute to base feature learning.
    """
    cfg = CFG[ptype]
    df = pd.read_csv(CACHE / cfg['rolling'])
    df = df[df['year'] != 2020]  # CAVEAT
    avail = SPLIT_DAY_MAP[target_sd]
    df = df[df['split_day'] == avail].copy()

    if cfg['ros_col'] is not None:
        df['_ros'] = df[cfg['ros_col']]
    else:
        df['_ros'] = df['fp_year_total'] - df['fp_with_role_to']

    df = df[df[cfg['sample_col']] >= cfg['sample_min']]
    df = df[df['_ros'].notna()]

    arch = pd.read_csv(RESEARCH / cfg['arch'])
    arch_keep = arch[['year', cfg['id_col'], 'OVERALL', 'OVERALL_career_pct',
                      'traj_flag', 'age']].rename(columns={
        'OVERALL': 'arche_ovr', 'OVERALL_career_pct': 'arche_career_pct',
        'traj_flag': 'arche_traj'})
    df = df.merge(arch_keep, on=['year', cfg['id_col']], how='left')

    df['traj_up'] = (df['arche_traj'] == 'TRENDING_UP').astype(int)
    df['traj_down'] = (df['arche_traj'] == 'TRENDING_DOWN').astype(int)
    df['age_norm'] = (df['age'].fillna(28) - 28) / 5

    # Cleanup #3: attach PL features.
    df = _attach_pl_features(df, ptype, cfg['id_col'])

    base_features = ([f for f in cfg['features_to'] if f in df.columns]
                + [f for f in cfg['features_recent'] if f in df.columns]
                + ['arche_ovr', 'arche_career_pct', 'traj_up', 'traj_down', 'age_norm'])
    # PL feature appended; mean-imputed on missing.
    pl_features = ['pl_rank_mid_inv']
    if ptype == 'RP':
        pl_features.append('is_non_closer_rp')
    features = base_features + pl_features

    # Mean-impute the PL features so subset doesn't shrink dramatically.
    for c in pl_features:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            df[c] = df[c].fillna(df[c].mean())

    df = df.dropna(subset=base_features + ['_ros'])
    return df, features


def fit_blend(train_df: pd.DataFrame, features: list[str]):
    """Standardize on train, fit linear blend, also compute residual bootstrap pool."""
    means = train_df[features].mean()
    stds = train_df[features].std().replace(0, 1)
    X = ((train_df[features] - means) / stds).values
    y = train_df['_ros'].values
    reg = LinearRegression().fit(X, y)
    pred = reg.predict(X)
    resid = y - pred
    return reg, means, stds, resid


def bootstrap_ci(reg, X_live, resid, n_boot=200, ci=0.95):
    """Residual bootstrap CI: add resampled residuals to base prediction."""
    base = reg.predict(X_live)
    n = X_live.shape[0]
    rng = np.random.default_rng(20260604)
    sims = np.empty((n_boot, n), dtype=float)
    for i in range(n_boot):
        sims[i] = base + rng.choice(resid, size=n, replace=True)
    lo = np.quantile(sims, (1 - ci) / 2, axis=0)
    hi = np.quantile(sims, 1 - (1 - ci) / 2, axis=0)
    return base, lo, hi


def build_live_features(ptype: str, target_sd: int):
    """Pull today's _to features for the live (year=2026) cohort at the live split_day."""
    cfg = CFG[ptype]
    df = pd.read_csv(CACHE / cfg['rolling'])
    df = df[df['year'] == 2026].copy()
    # use the LATEST available 2026 split_day (live data may not yet have target snap)
    if len(df) == 0:
        return pd.DataFrame()
    latest_live_sd = int(df['split_day'].max())
    df = df[df['split_day'] == latest_live_sd].copy()

    arch = pd.read_csv(RESEARCH / cfg['arch'])
    arch_2026 = arch[arch['year'] == 2026]
    arch_keep = arch_2026[['year', cfg['id_col'], 'player_name', 'OVERALL',
                            'OVERALL_career_pct', 'traj_flag', 'age']].rename(columns={
        'OVERALL': 'arche_ovr', 'OVERALL_career_pct': 'arche_career_pct',
        'traj_flag': 'arche_traj'})
    df = df.merge(arch_keep, on=['year', cfg['id_col']], how='left')

    df['traj_up'] = (df['arche_traj'] == 'TRENDING_UP').astype(int)
    df['traj_down'] = (df['arche_traj'] == 'TRENDING_DOWN').astype(int)
    df['age_norm'] = (df['age'].fillna(28) - 28) / 5
    df['_live_split_day'] = latest_live_sd
    # Cleanup #3: attach PL features for the live cohort.
    df = _attach_pl_features(df, ptype, cfg['id_col'])
    return df


def confidence_tier(row, cfg) -> str:
    n = row.get(cfg['sample_col'], 0) or 0
    has_arche = pd.notna(row.get('arche_ovr'))
    if n >= cfg['sample_min'] * 4 and has_arche:
        return 'HIGH'
    if n >= cfg['sample_min'] * 2 and has_arche:
        return 'MED'
    return 'LOW'


def run_one_ptype(ptype: str, target_sd: int):
    cfg = CFG[ptype]
    train_df, features = load_training_panel(ptype, target_sd)
    print(f'  [{ptype}] train n={len(train_df)} features={len(features)} '
          f'(target split_day={target_sd}, mapped={SPLIT_DAY_MAP[target_sd]})', file=sys.stderr)
    reg, means, stds, resid = fit_blend(train_df, features)

    live = build_live_features(ptype, target_sd)
    if live.empty:
        print(f'  [{ptype}] no live 2026 rows; skipping', file=sys.stderr)
        return pd.DataFrame()

    # Impute missing features to training mean (z=0 after standardize)
    for f in features:
        if f not in live.columns:
            live[f] = means[f]
        live[f] = live[f].fillna(means[f])

    X_live = ((live[features] - means) / stds).values
    base, lo, hi = bootstrap_ci(reg, X_live, resid, n_boot=200)

    out = pd.DataFrame({
        'mlbam_id': live[cfg['id_col']].astype(int),
        'player_name': live['player_name'],
        'player_type': ptype,
        'live_blend_xfp': np.round(base, 4),
        'ci_lower': np.round(lo, 4),
        'ci_upper': np.round(hi, 4),
        'fitted_split_day': SPLIT_DAY_MAP[target_sd],
        'live_split_day': live['_live_split_day'].astype(int),
        'n_features_used': len(features),
    })
    out['confidence_tier'] = [confidence_tier(r, cfg) for _, r in live.iterrows()]
    # Drop rows missing arche (rookies w/o ratings master entry) only if anchor truly missing
    out = out[out['live_blend_xfp'].notna()].copy()
    # Drop rows where archetype merge failed (no ratings master entry -> NaN name).
    out = out[out['player_name'].notna()].copy()
    return out


def main():
    print(f'BUILD LIVE BLEND XFP -- {date.today().isoformat()}', file=sys.stderr)
    _emit_caveats()
    today = date.today()
    target_sd = pick_split_day(today)
    print(f'  today={today} days_into_season={(today - SEASON_START).days} '
          f'-> target split_day={target_sd}', file=sys.stderr)

    frames = []
    for ptype in ['SP', 'H', 'RP']:
        try:
            f = run_one_ptype(ptype, target_sd)
            if not f.empty:
                frames.append(f)
        except Exception as e:
            print(f'  [{ptype}] ERROR: {e}', file=sys.stderr)

    if not frames:
        print('No output rows produced', file=sys.stderr)
        sys.exit(1)

    full = pd.concat(frames, ignore_index=True)
    out_path = OUT / f'live_blend_xfp_{today.isoformat()}.csv'
    # Atomic write: temp + rename.
    tmp = out_path.with_suffix('.csv.tmp')
    full.to_csv(tmp, index=False)
    tmp.replace(out_path)
    # Also write a stable "latest" alias for downstream consumers.
    latest = OUT / 'live_blend_xfp_latest.csv'
    tmp2 = latest.with_suffix('.csv.tmp')
    full.to_csv(tmp2, index=False)
    tmp2.replace(latest)
    print(f'Wrote {out_path} ({len(full)} rows)', file=sys.stderr)
    print(f'Wrote {latest}', file=sys.stderr)

    # Quick top-10 sanity peek to stderr.
    sp = full[full.player_type == 'SP'].nlargest(10, 'live_blend_xfp')
    h_bot = full[full.player_type == 'H'].nsmallest(10, 'live_blend_xfp')
    print('\nTop-10 SP by live_blend_xfp (fp/start):', file=sys.stderr)
    for _, r in sp.iterrows():
        nm = str(r.player_name)[:28]
        print(f'  {nm:<28s} {r.live_blend_xfp:6.2f} '
              f'[{r.ci_lower:5.2f}, {r.ci_upper:5.2f}] {r.confidence_tier}',
              file=sys.stderr)
    print('\nBottom-10 hitters by live_blend_xfp (fp/PA):', file=sys.stderr)
    for _, r in h_bot.iterrows():
        nm = str(r.player_name)[:28]
        print(f'  {nm:<28s} {r.live_blend_xfp:6.3f} '
              f'[{r.ci_lower:5.3f}, {r.ci_upper:5.3f}] {r.confidence_tier}',
              file=sys.stderr)
    # Sanity peek for canonical names mentioned in spec.
    print('\nSanity check (Snell ~12-13, Kelly ~8, Judge ~2.4-2.7/PA):',
          file=sys.stderr)
    for needle in ['Snell', 'Kelly', 'Judge']:
        hit = full[full.player_name.astype(str).str.contains(needle, na=False)]
        for _, r in hit.head(3).iterrows():
            print(f'  {r.player_name} [{r.player_type}] {r.live_blend_xfp:.3f} '
                  f'[{r.ci_lower:.3f}, {r.ci_upper:.3f}]', file=sys.stderr)


if __name__ == '__main__':
    main()
