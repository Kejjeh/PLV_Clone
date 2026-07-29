"""xfp_milb_hitter_lock.py — lock the MiLB->MLB hitter translation model.

3-year AAA-only Ridge translator: MiLB rates -> MLB fp_per_pa.

Outputs:
  data/models/xfp_milb_hitter_pipeline.pkl
  data/outputs/xfp_milb_hitter_priors_2026.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
MODELS = ROOT / 'data' / 'models'
OUTPUTS = ROOT / 'data' / 'outputs'

# Features kept after carryover screen (|cor| >= 0.10 in AAA min_pa=200 cell):
FEATURES = [
    'k_pct', 'bb_pct', 'k_minus_bb_pct',
    'avg', 'obp', 'slg', 'ops', 'iso',
    'plateAppearances',
]

SHRINK_K = {
    'k_pct': 60,
    'bb_pct': 100,
    'k_minus_bb_pct': 80,
    'avg': 200,
    'obp': 180,
    'slg': 200,
    'ops': 180,
    'iso': 200,
}

LEAGUE_AVGS: dict = {}


def consolidate(df: pd.DataFrame) -> pd.DataFrame:
    sum_fields = ['plateAppearances', 'atBats', 'hits', 'doubles', 'triples',
                  'homeRuns', 'baseOnBalls', 'strikeOuts', 'hitByPitch',
                  'stolenBases', 'caughtStealing', 'gamesPlayed', 'totalBases']
    for c in sum_fields:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    grp = df.groupby(['batter', 'season', 'level'], as_index=False).agg(
        **{c: (c, 'sum') for c in sum_fields}, name=('name', 'first'))
    pa = grp['plateAppearances'].replace(0, np.nan)
    ab = grp['atBats'].replace(0, np.nan)
    grp['k_pct'] = grp['strikeOuts'] / pa
    grp['bb_pct'] = grp['baseOnBalls'] / pa
    grp['k_minus_bb_pct'] = grp['k_pct'] - grp['bb_pct']
    grp['avg'] = grp['hits'] / ab
    grp['obp'] = (grp['hits'] + grp['baseOnBalls'] + grp['hitByPitch']) / pa
    grp['slg'] = grp['totalBases'] / ab
    grp['ops'] = grp['obp'] + grp['slg']
    grp['iso'] = (grp['totalBases'] - grp['hits']) / ab
    grp['hr_per_pa'] = grp['homeRuns'] / pa
    return grp


def rolling_3yr(milb: pd.DataFrame) -> pd.DataFrame:
    milb = milb.copy().sort_values(['batter', 'level', 'season'])
    rolling = []
    sum_cols = ['plateAppearances', 'atBats', 'hits', 'doubles', 'triples',
                'homeRuns', 'baseOnBalls', 'strikeOuts', 'hitByPitch',
                'stolenBases', 'caughtStealing', 'gamesPlayed', 'totalBases']
    for (bid, lvl), grp in milb.groupby(['batter', 'level']):
        g = grp.set_index('season')
        for season in g.index:
            window = [s for s in (season - 2, season - 1, season)
                      if s in g.index and s != 2020]
            sub = g.loc[window]
            row = {'batter': bid, 'level': lvl, 'season': season,
                   'name': g.loc[season, 'name']}
            for col in sum_cols:
                row[col] = float(sub[col].sum())
            rolling.append(row)
    out = pd.DataFrame(rolling)
    pa = out['plateAppearances'].replace(0, np.nan)
    ab = out['atBats'].replace(0, np.nan)
    out['k_pct'] = out['strikeOuts'] / pa
    out['bb_pct'] = out['baseOnBalls'] / pa
    out['k_minus_bb_pct'] = out['k_pct'] - out['bb_pct']
    out['avg'] = out['hits'] / ab
    out['obp'] = (out['hits'] + out['baseOnBalls'] + out['hitByPitch']) / pa
    out['slg'] = out['totalBases'] / ab
    out['ops'] = out['obp'] + out['slg']
    out['iso'] = (out['totalBases'] - out['hits']) / ab
    out['hr_per_pa'] = out['homeRuns'] / pa
    return out


def populate_league_avgs(milb: pd.DataFrame):
    for (season, level), sub in milb.groupby(['season', 'level']):
        for feat, _ in SHRINK_K.items():
            denom = sub['plateAppearances']
            x = pd.to_numeric(sub[feat], errors='coerce')
            w = pd.to_numeric(denom, errors='coerce')
            m = x.notna() & w.notna() & (w > 0)
            if m.any() and m.sum() >= 20:
                LEAGUE_AVGS[(season, level, feat)] = float((x[m] * w[m]).sum() / w[m].sum())
            elif m.any():
                LEAGUE_AVGS[(season, level, feat)] = float(x[m].mean())
            else:
                LEAGUE_AVGS[(season, level, feat)] = 0.0


def shrink(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for feat, k in SHRINK_K.items():
        denom = df['plateAppearances']
        n = pd.to_numeric(denom, errors='coerce').fillna(0)
        x = pd.to_numeric(df[feat], errors='coerce')
        priors = df.apply(
            lambda r: LEAGUE_AVGS.get((r['season'], r['level'], feat), 0.0),
            axis=1)
        df[feat] = (n * x.fillna(priors) + k * priors) / (n + k)
    return df


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    milb_raw = pd.read_csv(CACHE / 'milb_hitters_2015_2026.csv')
    milb = consolidate(milb_raw)
    populate_league_avgs(milb)
    rolling = rolling_3yr(milb)
    rolling = shrink(rolling)

    # Build training table
    hit = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv').rename(columns={'year': 'season'})
    hit_next = hit[['batter', 'season', 'pa', 'fp_per_pa_actual']].rename(
        columns={'season': 'next_season',
                 'pa': 'mlb_pa',
                 'fp_per_pa_actual': 'mlb_fp_per_pa'})
    hit_next = hit_next[hit_next['mlb_pa'] >= 100]
    rolling['next_season'] = rolling['season'] + 1

    aaa = rolling[rolling['level'] == 'AAA'].copy()
    train = aaa.merge(hit_next, on=['batter', 'next_season'], how='inner')
    train = train[train['plateAppearances'] >= 100].dropna(subset=FEATURES + ['mlb_fp_per_pa'])
    print(f'Training rows: {len(train)}')

    # LOO cross-year r
    seasons = sorted(s for s in train['season'].unique() if s != 2020)
    preds, acts = [], []
    for T in seasons:
        tr = train[train['season'] != T]
        te = train[train['season'] == T]
        if len(tr) < 30 or len(te) < 5:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-2, 5, 80), cv=5))])
        pipe.fit(tr[FEATURES].values, tr['mlb_fp_per_pa'].values)
        preds.extend(pipe.predict(te[FEATURES].values).tolist())
        acts.extend(te['mlb_fp_per_pa'].tolist())
    preds = np.asarray(preds); acts = np.asarray(acts)
    cross_year_r = float(np.corrcoef(preds, acts)[0, 1])
    cross_year_mae = float(np.mean(np.abs(preds - acts)))
    print(f'LOO cross-year r = {cross_year_r:.4f}  MAE = {cross_year_mae:.4f}  n = {len(preds)}')

    # Naive baseline
    league_mu = float(train['mlb_fp_per_pa'].mean())
    naive_mae = float(np.mean(np.abs(train['mlb_fp_per_pa'] - league_mu)))
    print(f'Naive baseline (league_mu={league_mu:.3f}): MAE={naive_mae:.4f}')

    # Final fit
    final = Pipeline([('sc', StandardScaler()),
                      ('r', RidgeCV(alphas=np.logspace(-2, 5, 80), cv=5))])
    final.fit(train[FEATURES].values, train['mlb_fp_per_pa'].values)
    coefs = dict(zip(FEATURES, final.named_steps['r'].coef_.tolist()))

    bundle = {
        'pipeline': final,
        'features': FEATURES,
        'shrink_k': SHRINK_K,
        'league_avgs': LEAGUE_AVGS,
        'level': 'AAA',
        'window_years': 3,
        'min_plateAppearances': 100,
        'cross_year_r_aaa': round(cross_year_r, 4),
        'cross_year_mae_aaa': round(cross_year_mae, 4),
        'naive_mae': round(naive_mae, 4),
        'n_train': len(train),
        'gate_target': 0.30,
        'gate_passed': cross_year_r >= 0.30,
        'coefs': coefs,
        'note': 'MT-Hitters-v1: AAA-only 3-year MiLB->MLB hitter translator.',
        'version': 'mth1',
    }
    out_path = MODELS / 'xfp_milb_hitter_pipeline.pkl'
    joblib.dump(bundle, out_path)
    print(f'Wrote {out_path}')

    # 2026 priors anchored on most recent AAA season
    recent = aaa[aaa['season'].isin([2024, 2025, 2026])]
    latest = recent.sort_values('season').drop_duplicates('batter', keep='last')
    cur = latest[latest['plateAppearances'] >= 50].copy()
    cur = cur.dropna(subset=FEATURES)
    cur['projected_fp_per_pa'] = final.predict(cur[FEATURES].values)
    cur['anchor_season'] = cur['season']
    cur['sample_quality'] = pd.cut(
        cur['plateAppearances'],
        bins=[-np.inf, 200, 500, np.inf],
        labels=['low', 'med', 'high'])
    out_csv = OUTPUTS / 'xfp_milb_hitter_priors_2026.csv'
    keep = ['batter', 'name', 'level', 'anchor_season', 'plateAppearances',
            'k_pct', 'bb_pct', 'iso', 'hr_per_pa', 'projected_fp_per_pa',
            'sample_quality']
    cur[keep].sort_values('projected_fp_per_pa', ascending=False).to_csv(out_csv, index=False)
    print(f'Wrote {out_csv}: {len(cur)} priors')

    print('\nTop 10 projected MiLB-derived hitter priors:')
    print(cur.sort_values('projected_fp_per_pa', ascending=False)
              [['name', 'plateAppearances', 'k_pct', 'iso', 'projected_fp_per_pa']]
              .head(10).to_string(index=False))

    print('\nCoefs:')
    for f, c in sorted(coefs.items(), key=lambda x: -abs(x[1])):
        print(f'  {f:<22s}  {c:+.4f}')


if __name__ == '__main__':
    main()
