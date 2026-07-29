"""xfp_milb_pitcher_pipeline.py — MiLB -> MLB SP fp_per_start translation.

Trains a Ridge model on (pitcher, year, level) MiLB rows where the same
pitcher logged >= 5 GS in the next MLB season. Validates with leave-one-year-out
across 2018->2019, 2021->2022, 2022->2023, 2023->2024, 2024->2025.

Decision gate (from plan):
  - overall LOO cross-year r >= 0.30, AND
  - AAA-subset r >= 0.30 AND AA-subset r >= 0.20

Run as a script: prints metrics, does NOT save artifacts (that's MT3 lock).
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV, HuberRegressor

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

EXT_PATH = CACHE / 'milb_pitchers_ext_2015_2026.csv'
MILB = pd.read_csv(EXT_PATH if EXT_PATH.exists() else CACHE / 'milb_pitchers_2015_2026.csv')
SP = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv').rename(columns={'year': 'season'})
AGES = pd.read_csv(CACHE / 'milb_pitcher_ages.csv')
AGES['birthDate'] = pd.to_datetime(AGES['birthDate'], errors='coerce')

# Features pulled from MT1 carryover screen (|cor| >= 0.10 in any reasonable cell)
RATE_FEATURES = [
    'k_pct', 'bb_pct', 'k_minus_bb_pct',
    'h_per_9', 'er_per_9', 'whip',
]
VOLUME_FEATURES = [
    'inningsPitched', 'gamesPitched', 'gamesStarted', 'ip_per_g',
]
LEVEL_FEATURES = ['is_aaa']  # AA is reference
AGE_FEATURES = ['age', 'age_relative']  # age and age vs level mean
PITCH_FEATURES = ['gb_pct_outs', 'pitches_per_bf', 'strike_pct']

# Bayesian shrinkage compendium (BF for K%/BB%, IP for rate-of-events).
SHRINK_K = {
    'k_pct': 70,
    'bb_pct': 170,
    'k_minus_bb_pct': 100,
    'h_per_9': 60,
    'er_per_9': 60,
    'whip': 50,
}

LEAGUE_AVGS_BY_LEVEL: dict[tuple[str, str], float] = {}


def consolidate_milb(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (pitcher, season, level) with summed counts and recomputed rates."""
    df = df.copy()
    sum_fields = ['battersFaced', 'strikeOuts', 'baseOnBalls', 'homeRuns',
                  'hits', 'earnedRuns', 'gamesPitched', 'gamesStarted', 'ip']
    has_ext = 'groundOuts' in df.columns
    if has_ext:
        sum_fields += ['groundOuts', 'airOuts', 'numberOfPitches', 'strikes']
    for c in sum_fields:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    agg_map = {f: (f, 'sum') for f in sum_fields}
    agg_map['name'] = ('name', 'first')
    grp = df.groupby(['pitcher', 'season', 'level'], as_index=False).agg(**agg_map)
    bf = grp['battersFaced'].replace(0, np.nan)
    ip = grp['ip'].replace(0, np.nan)
    g = grp['gamesPitched'].replace(0, np.nan)
    grp['k_pct'] = grp['strikeOuts'] / bf
    grp['bb_pct'] = grp['baseOnBalls'] / bf
    grp['k_minus_bb_pct'] = grp['k_pct'] - grp['bb_pct']
    grp['hr_per_9'] = grp['homeRuns'] * 9 / ip
    grp['h_per_9'] = grp['hits'] * 9 / ip
    grp['er_per_9'] = grp['earnedRuns'] * 9 / ip
    grp['ip_per_g'] = grp['ip'] / g
    grp['whip'] = (grp['baseOnBalls'] + grp['hits']) / ip
    grp['inningsPitched'] = grp['ip']
    grp['is_aaa'] = (grp['level'] == 'AAA').astype(int)
    if has_ext:
        out_total = (grp['groundOuts'] + grp['airOuts']).replace(0, np.nan)
        np_total = grp['numberOfPitches'].replace(0, np.nan)
        grp['gb_pct_outs'] = grp['groundOuts'] / out_total
        grp['pitches_per_bf'] = grp['numberOfPitches'] / bf
        grp['strike_pct'] = grp['strikes'] / np_total
    else:
        grp['gb_pct_outs'] = np.nan
        grp['pitches_per_bf'] = np.nan
        grp['strike_pct'] = np.nan
    return grp


def populate_league_avgs(milb: pd.DataFrame):
    """Per-(season, level) league averages for each rate feature, used as
    the prior mean in Bayesian shrinkage."""
    for (season, level), sub in milb.groupby(['season', 'level']):
        for feat, k in SHRINK_K.items():
            denom = sub['battersFaced'] if feat in ('k_pct', 'bb_pct', 'k_minus_bb_pct') else sub['ip']
            x = pd.to_numeric(sub[feat], errors='coerce')
            w = pd.to_numeric(denom, errors='coerce')
            m = x.notna() & w.notna() & (w > 0)
            if m.sum() < 20:
                LEAGUE_AVGS_BY_LEVEL[(season, level, feat)] = float(x[m].mean()) if m.any() else 0.0
            else:
                LEAGUE_AVGS_BY_LEVEL[(season, level, feat)] = float((x[m] * w[m]).sum() / w[m].sum())


def shrink_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for feat, k in SHRINK_K.items():
        denom = df['battersFaced'] if feat in ('k_pct', 'bb_pct', 'k_minus_bb_pct') else df['ip']
        n = pd.to_numeric(denom, errors='coerce').fillna(0)
        x = pd.to_numeric(df[feat], errors='coerce')
        # season/level-specific prior
        priors = df.apply(
            lambda r: LEAGUE_AVGS_BY_LEVEL.get((r['season'], r['level'], feat),
                                                LEAGUE_AVGS_BY_LEVEL.get(('global', None, feat), 0.0)),
            axis=1,
        )
        df[feat] = (n * x.fillna(priors) + k * priors) / (n + k)
    return df


def build_training_table(multi_year: int = 0) -> pd.DataFrame:
    """multi_year: 0 = current season only, 1 = T+T-1, 2 = T+T-1+T-2."""
    milb = consolidate_milb(MILB)
    populate_league_avgs(milb)
    milb_shrunk = shrink_features(milb)

    if multi_year >= 1:
        # Aggregate counts across recent seasons at the same level.
        agg = milb.copy()  # raw counts (already consolidated to one row per (p,s,l))
        rolling = []
        sum_cols = ['battersFaced', 'strikeOuts', 'baseOnBalls', 'homeRuns',
                    'hits', 'earnedRuns', 'gamesPitched', 'gamesStarted', 'ip']
        if 'groundOuts' in agg.columns:
            sum_cols += ['groundOuts', 'airOuts', 'numberOfPitches', 'strikes']
        for (pid, lvl), grp in agg.groupby(['pitcher', 'level']):
            grp = grp.sort_values('season').set_index('season')
            for season in grp.index:
                window = list(range(season - multi_year, season + 1))
                window = [s for s in window if s in grp.index and s != 2020]
                sub = grp.loc[window]
                row = {'pitcher': pid, 'level': lvl, 'season': season,
                       'name': grp.loc[season, 'name']}
                for col in sum_cols:
                    if col in sub.columns:
                        row[col] = float(sub[col].sum())
                rolling.append(row)
        m = pd.DataFrame(rolling)
        bf = m['battersFaced'].replace(0, np.nan)
        ip = m['ip'].replace(0, np.nan)
        g = m['gamesPitched'].replace(0, np.nan)
        m['k_pct'] = m['strikeOuts'] / bf
        m['bb_pct'] = m['baseOnBalls'] / bf
        m['k_minus_bb_pct'] = m['k_pct'] - m['bb_pct']
        m['hr_per_9'] = m['homeRuns'] * 9 / ip
        m['h_per_9'] = m['hits'] * 9 / ip
        m['er_per_9'] = m['earnedRuns'] * 9 / ip
        m['ip_per_g'] = m['ip'] / g
        m['whip'] = (m['baseOnBalls'] + m['hits']) / ip
        m['inningsPitched'] = m['ip']
        m['is_aaa'] = (m['level'] == 'AAA').astype(int)
        if 'groundOuts' in m.columns:
            out_total = (m['groundOuts'] + m['airOuts']).replace(0, np.nan)
            np_total = m['numberOfPitches'].replace(0, np.nan)
            m['gb_pct_outs'] = m['groundOuts'] / out_total
            m['pitches_per_bf'] = m['numberOfPitches'] / bf
            m['strike_pct'] = m['strikes'] / np_total
        milb_shrunk = shrink_features(m)
        milb_shrunk['inningsPitched'] = milb_shrunk['ip']
        milb_shrunk['is_aaa'] = (milb_shrunk['level'] == 'AAA').astype(int)
        if 'gb_pct_outs' in m.columns:
            milb_shrunk['gb_pct_outs'] = m['gb_pct_outs']
            milb_shrunk['pitches_per_bf'] = m['pitches_per_bf']
            milb_shrunk['strike_pct'] = m['strike_pct']

    # Attach age (years on July 1 of season)
    milb_shrunk = milb_shrunk.merge(AGES[['pitcher', 'birthDate']], on='pitcher', how='left')
    july1 = pd.to_datetime(milb_shrunk['season'].astype(str) + '-07-01')
    milb_shrunk['age'] = ((july1 - milb_shrunk['birthDate']).dt.days / 365.25).round(2)
    # age relative to level cohort mean (within (season, level))
    level_mean = milb_shrunk.groupby(['season', 'level'])['age'].transform('mean')
    milb_shrunk['age_relative'] = milb_shrunk['age'] - level_mean

    sp_next = SP[['pitcher', 'season', 'gs', 'ip_per_start', 'fp_per_start_actual']].rename(
        columns={'season': 'next_season',
                 'gs': 'mlb_gs',
                 'ip_per_start': 'mlb_ip_per_start',
                 'fp_per_start_actual': 'mlb_fp_per_start'})
    sp_next = sp_next[sp_next['mlb_gs'] >= 5]
    milb_shrunk['next_season'] = milb_shrunk['season'] + 1
    joined = milb_shrunk.merge(sp_next, on=['pitcher', 'next_season'], how='inner')
    joined = joined[joined['battersFaced'] >= 50]
    required_for_dropna = RATE_FEATURES + VOLUME_FEATURES + AGE_FEATURES + ['mlb_fp_per_start']
    joined = joined.dropna(subset=required_for_dropna)
    # Pitch features only available for ext substrate; fill NaN with median for rows without
    for c in PITCH_FEATURES:
        if c in joined.columns:
            med = joined[c].median()
            joined[c] = joined[c].fillna(med)
    return joined


def loo_cross_year(joined: pd.DataFrame, feats: list[str], model: str = 'ridge') -> dict:
    """For each test season T, train on all (season != T, season != 2020) rows
    and predict T's rows. Concat predictions, compute correlation."""
    preds, acts, levels = [], [], []
    seasons = sorted(s for s in joined['season'].unique() if s != 2020)
    for T in seasons:
        train = joined[(joined['season'] != T) & (joined['season'] != 2020)]
        test = joined[joined['season'] == T]
        if len(train) < 30 or len(test) < 5:
            continue
        if model == 'huber':
            est = HuberRegressor(alpha=0.001, max_iter=200)
        else:
            est = RidgeCV(alphas=np.logspace(-2, 5, 80), cv=5)
        pipe = Pipeline([('sc', StandardScaler()), ('r', est)])
        pipe.fit(train[feats].values, train['mlb_fp_per_start'].values)
        p = pipe.predict(test[feats].values)
        preds.extend(p.tolist())
        acts.extend(test['mlb_fp_per_start'].tolist())
        levels.extend(test['level'].tolist())
    preds = np.asarray(preds); acts = np.asarray(acts); levels = np.asarray(levels)
    overall_r = float(np.corrcoef(preds, acts)[0, 1]) if len(preds) >= 10 else float('nan')
    out = {'overall_r': round(overall_r, 4), 'n': len(preds)}
    for lvl in ('AAA', 'AA'):
        m = levels == lvl
        if m.sum() >= 10:
            r = float(np.corrcoef(preds[m], acts[m])[0, 1])
            out[f'{lvl}_r'] = round(r, 4)
            out[f'{lvl}_n'] = int(m.sum())
            out[f'{lvl}_mae'] = round(float(np.mean(np.abs(preds[m] - acts[m]))), 3)
    out['mae'] = round(float(np.mean(np.abs(preds - acts))), 3)
    return out


def main():
    joined = build_training_table()
    print(f'MiLB -> MLB SP training rows: {len(joined)}')
    print(f'  by level: {joined["level"].value_counts().to_dict()}')
    print(f'  MLB target mean = {joined["mlb_fp_per_start"].mean():.2f} '
          f'(sd={joined["mlb_fp_per_start"].std():.2f})')

    feature_sets = {
        'rates_only':         RATE_FEATURES,
        'rates_plus_volume':  RATE_FEATURES + VOLUME_FEATURES,
        'rates_volume_age':   RATE_FEATURES + VOLUME_FEATURES + AGE_FEATURES,
        'rates_volume_pitch': RATE_FEATURES + VOLUME_FEATURES + PITCH_FEATURES,
        'all':                RATE_FEATURES + VOLUME_FEATURES + LEVEL_FEATURES + AGE_FEATURES + PITCH_FEATURES,
    }

    print('\n--- LOO cross-year evaluation, BF >= 50 ---')
    for label, feats in feature_sets.items():
        m = loo_cross_year(joined, feats)
        print(f'{label:<24} {m}')

    # Higher MiLB-sample filter
    print('\n--- LOO cross-year evaluation, BF >= 120 ---')
    high = joined[joined['battersFaced'] >= 120]
    print(f'  rows: {len(high)} ({high["level"].value_counts().to_dict()})')
    for label, feats in feature_sets.items():
        m = loo_cross_year(high, feats)
        print(f'{label:<24} {m}')

    # AAA-only model
    print('\n--- LOO cross-year evaluation, AAA-only (BF >= 50) ---')
    aaa = joined[joined['level'] == 'AAA']
    for label, feats in feature_sets.items():
        m = loo_cross_year(aaa, feats)
        print(f'{label:<24} {m}')

    # Tiered baseline: lag (predict mlb_fp_per_start = league_mean)
    league_mu = joined['mlb_fp_per_start'].mean()
    naive_mae = float(np.mean(np.abs(joined['mlb_fp_per_start'] - league_mu)))
    print(f'\nNaive baseline (predict league_mu={league_mu:.2f}): MAE={naive_mae:.3f}')

    # Naive baseline restricted to AAA
    aaa_mu = aaa['mlb_fp_per_start'].mean()
    aaa_naive_mae = float(np.mean(np.abs(aaa['mlb_fp_per_start'] - aaa_mu)))
    print(f'Naive baseline AAA-only (mu={aaa_mu:.2f}): MAE={aaa_naive_mae:.3f}')

    print('\n--- LOO cross-year evaluation, MULTI-YEAR MiLB (T + T-1) ---')
    multi = build_training_table(multi_year=1)
    print(f'  rows: {len(multi)} ({multi["level"].value_counts().to_dict()})')
    for label, feats in feature_sets.items():
        m = loo_cross_year(multi, feats)
        print(f'{label:<24} {m}')

    print('\n--- LOO cross-year, MULTI-YEAR + AAA-only ---')
    multi_aaa = multi[multi['level'] == 'AAA']
    for label, feats in feature_sets.items():
        m = loo_cross_year(multi_aaa, feats)
        print(f'{label:<24} {m}')

    print('\n--- LOO cross-year, 3-YEAR MULTI (T+T-1+T-2) + AAA-only ---')
    triple = build_training_table(multi_year=2)
    triple_aaa = triple[triple['level'] == 'AAA']
    for label, feats in feature_sets.items():
        m = loo_cross_year(triple_aaa, feats)
        print(f'{label:<24} {m}')

    print('\n--- LOO cross-year, MULTI-YEAR + AAA-only, HUBER regressor ---')
    for label, feats in feature_sets.items():
        m = loo_cross_year(multi_aaa, feats, model='huber')
        print(f'{label:<24} {m}')

    print('\n--- LOO cross-year, 3-YEAR + AAA-only, HUBER regressor ---')
    for label, feats in feature_sets.items():
        m = loo_cross_year(triple_aaa, feats, model='huber')
        print(f'{label:<24} {m}')

    # Higher MiLB sample threshold for 3-year window (require ≥250 BF total)
    print('\n--- LOO cross-year, 3-YEAR + AAA-only, BF>=250 ---')
    triple_aaa_high = triple_aaa[triple_aaa['battersFaced'] >= 250]
    print(f'  rows: {len(triple_aaa_high)}')
    for label, feats in feature_sets.items():
        m = loo_cross_year(triple_aaa_high, feats)
        print(f'{label:<24} {m}')


if __name__ == '__main__':
    main()
