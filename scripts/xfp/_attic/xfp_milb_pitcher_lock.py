"""xfp_milb_pitcher_lock.py — lock the MiLB->MLB SP translation model.

Trains the production-locked Ridge translator on:
  - 3-year MiLB AAA windows (T + T-1 + T-2 counts summed; rates re-derived)
  - features: k_pct, bb_pct, k_minus_bb_pct, h_per_9, er_per_9, whip,
              inningsPitched, gamesPitched, gamesStarted, ip_per_g
  - target:   next-season MLB fp_per_start_actual (>=5 GS in MLB year T+1)
  - sample filter: battersFaced >= 50 in the MiLB window
  - all 2018-2025 transitions used; trained on full table (no held-out)

Validation gate decision:
  - Plan called for r >= 0.30 overall + AAA, AA >= 0.20.
  - Empirical ceiling with available data is r=0.277 (AAA-only, 3-year).
  - DECISION: ship anyway with explicit prior_source='milb_translation'
    tagging and conservative shrinkage at integration time.
  - Justification: model strictly beats the existing fillna(league_mu)
    fallback (MAE 2.65 vs 2.72, ~3% improvement); rookies get a pitcher-
    specific prior instead of a flat constant. RP target had near-zero
    carryover; SP-only deployment.

Outputs:
  data/models/xfp_milb_pitcher_pipeline.pkl
  data/outputs/xfp_milb_pitcher_priors_2026.csv
"""
from __future__ import annotations
from pathlib import Path
import json
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

# Feature set (locked: rates + volume; pitch-detail features didn't lift LOO r)
FEATURES = [
    'k_pct', 'bb_pct', 'k_minus_bb_pct',
    'h_per_9', 'er_per_9', 'whip',
    'inningsPitched', 'gamesPitched', 'gamesStarted', 'ip_per_g',
]

SHRINK_K = {
    'k_pct': 70,
    'bb_pct': 170,
    'k_minus_bb_pct': 100,
    'h_per_9': 60,
    'er_per_9': 60,
    'whip': 50,
}

LEAGUE_AVGS: dict = {}


def ip_to_float(s) -> float:
    s = str(s) if s is not None else ''
    if not s or s == 'nan':
        return 0.0
    try:
        whole, _, frac = s.partition('.')
        whole_i = int(whole or 0)
        if frac == '1':
            return whole_i + 1/3
        if frac == '2':
            return whole_i + 2/3
        return float(s)
    except Exception:
        return 0.0


def load_milb() -> pd.DataFrame:
    ext = CACHE / 'milb_pitchers_ext_2015_2026.csv'
    src = ext if ext.exists() else CACHE / 'milb_pitchers_2015_2026.csv'
    df = pd.read_csv(src)
    if 'ip' not in df.columns:
        df['ip'] = df['inningsPitched'].apply(ip_to_float)
    return df


def consolidate(df: pd.DataFrame) -> pd.DataFrame:
    sum_fields = ['battersFaced', 'strikeOuts', 'baseOnBalls', 'homeRuns',
                  'hits', 'earnedRuns', 'gamesPitched', 'gamesStarted', 'ip']
    for c in sum_fields:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    grp = df.groupby(['pitcher', 'season', 'level'], as_index=False).agg(
        **{c: (c, 'sum') for c in sum_fields}, name=('name', 'first'))
    bf = grp['battersFaced'].replace(0, np.nan)
    ip = grp['ip'].replace(0, np.nan)
    grp['k_pct'] = grp['strikeOuts'] / bf
    grp['bb_pct'] = grp['baseOnBalls'] / bf
    grp['k_minus_bb_pct'] = grp['k_pct'] - grp['bb_pct']
    grp['h_per_9'] = grp['hits'] * 9 / ip
    grp['er_per_9'] = grp['earnedRuns'] * 9 / ip
    grp['whip'] = (grp['baseOnBalls'] + grp['hits']) / ip
    return grp


def rolling_3yr(milb: pd.DataFrame) -> pd.DataFrame:
    """Window of T + T-1 + T-2 at the same level. Re-derive rates from sums."""
    milb = milb.copy().sort_values(['pitcher', 'level', 'season'])
    rolling = []
    for (pid, lvl), grp in milb.groupby(['pitcher', 'level']):
        g = grp.set_index('season')
        for season in g.index:
            window = [s for s in (season - 2, season - 1, season) if s in g.index and s != 2020]
            sub = g.loc[window]
            row = {'pitcher': pid, 'level': lvl, 'season': season,
                   'name': g.loc[season, 'name']}
            for col in ('battersFaced', 'strikeOuts', 'baseOnBalls', 'homeRuns',
                        'hits', 'earnedRuns', 'gamesPitched', 'gamesStarted', 'ip'):
                row[col] = float(sub[col].sum())
            rolling.append(row)
    out = pd.DataFrame(rolling)
    bf = out['battersFaced'].replace(0, np.nan)
    ip = out['ip'].replace(0, np.nan)
    g = out['gamesPitched'].replace(0, np.nan)
    out['k_pct'] = out['strikeOuts'] / bf
    out['bb_pct'] = out['baseOnBalls'] / bf
    out['k_minus_bb_pct'] = out['k_pct'] - out['bb_pct']
    out['hr_per_9'] = out['homeRuns'] * 9 / ip
    out['h_per_9'] = out['hits'] * 9 / ip
    out['er_per_9'] = out['earnedRuns'] * 9 / ip
    out['ip_per_g'] = out['ip'] / g
    out['whip'] = (out['baseOnBalls'] + out['hits']) / ip
    out['inningsPitched'] = out['ip']
    return out


def populate_league_avgs(milb: pd.DataFrame):
    for (season, level), sub in milb.groupby(['season', 'level']):
        for feat, _ in SHRINK_K.items():
            denom = sub['battersFaced'] if feat in ('k_pct', 'bb_pct', 'k_minus_bb_pct') else sub['ip']
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
        denom = df['battersFaced'] if feat in ('k_pct', 'bb_pct', 'k_minus_bb_pct') else df['ip']
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

    milb_raw = load_milb()
    milb = consolidate(milb_raw)
    populate_league_avgs(milb)
    rolling = rolling_3yr(milb)
    rolling = shrink(rolling)

    # Build training table: AAA + (T -> T+1) MLB SP join
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv').rename(columns={'year': 'season'})
    sp_next = sp[['pitcher', 'season', 'gs', 'fp_per_start_actual']].rename(
        columns={'season': 'next_season',
                 'gs': 'mlb_gs',
                 'fp_per_start_actual': 'mlb_fp_per_start'})
    sp_next = sp_next[sp_next['mlb_gs'] >= 5]
    rolling['next_season'] = rolling['season'] + 1

    aaa = rolling[rolling['level'] == 'AAA'].copy()
    train = aaa.merge(sp_next, on=['pitcher', 'next_season'], how='inner')
    train = train[train['battersFaced'] >= 50].dropna(subset=FEATURES + ['mlb_fp_per_start'])
    print(f'Training rows: {len(train)}')

    # LOO cross-year r (re-confirm)
    seasons = sorted(s for s in train['season'].unique() if s != 2020)
    preds, acts = [], []
    for T in seasons:
        tr = train[train['season'] != T]
        te = train[train['season'] == T]
        if len(tr) < 30 or len(te) < 5:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-2, 5, 80), cv=5))])
        pipe.fit(tr[FEATURES].values, tr['mlb_fp_per_start'].values)
        preds.extend(pipe.predict(te[FEATURES].values).tolist())
        acts.extend(te['mlb_fp_per_start'].tolist())
    preds = np.asarray(preds); acts = np.asarray(acts)
    cross_year_r = float(np.corrcoef(preds, acts)[0, 1])
    cross_year_mae = float(np.mean(np.abs(preds - acts)))
    print(f'LOO cross-year r = {cross_year_r:.4f}  MAE = {cross_year_mae:.3f}  n = {len(preds)}')

    # Final fit on full training set
    final = Pipeline([('sc', StandardScaler()),
                      ('r', RidgeCV(alphas=np.logspace(-2, 5, 80), cv=5))])
    final.fit(train[FEATURES].values, train['mlb_fp_per_start'].values)
    coefs = dict(zip(FEATURES, final.named_steps['r'].coef_.tolist()))

    bundle = {
        'pipeline': final,
        'features': FEATURES,
        'shrink_k': SHRINK_K,
        'league_avgs': LEAGUE_AVGS,
        'level': 'AAA',
        'window_years': 3,
        'min_battersFaced': 50,
        'cross_year_r_aaa': round(cross_year_r, 4),
        'cross_year_mae_aaa': round(cross_year_mae, 3),
        'n_train': len(train),
        'gate_target': 0.30,
        'gate_passed': cross_year_r >= 0.30,
        'note': ('MT-Pitchers-v1: AAA-only 3-year rolling MiLB->MLB SP '
                 'translator. Misses strict r>=0.30 gate but beats league_mu '
                 'fallback by ~3% MAE. Shipped with prior_source tagging.'),
        'coefs': coefs,
        'version': 'mt1',
    }
    out_path = MODELS / 'xfp_milb_pitcher_pipeline.pkl'
    joblib.dump(bundle, out_path)
    print(f'Wrote {out_path}')

    # 2026 priors: for each AAA pitcher with stats in {2024,2025,2026}, use the
    # 3-year window ending on their MOST RECENT AAA season (often 2025 if they
    # haven't pitched 2026 AAA yet).
    recent = aaa[aaa['season'].isin([2024, 2025, 2026])]
    latest = recent.sort_values('season').drop_duplicates('pitcher', keep='last')
    cur = latest[latest['battersFaced'] >= 30].copy()
    cur = cur.dropna(subset=FEATURES)
    cur['projected_fp_per_start'] = final.predict(cur[FEATURES].values)
    cur['anchor_season'] = cur['season']
    cur['sample_quality'] = pd.cut(
        cur['battersFaced'],
        bins=[-np.inf, 100, 250, np.inf],
        labels=['low', 'med', 'high'])
    out_csv = OUTPUTS / 'xfp_milb_pitcher_priors_2026.csv'
    keep = ['pitcher', 'name', 'level', 'anchor_season', 'battersFaced',
            'inningsPitched', 'gamesStarted', 'k_pct', 'bb_pct',
            'projected_fp_per_start', 'sample_quality']
    cur[keep].sort_values('projected_fp_per_start', ascending=False).to_csv(out_csv, index=False)
    print(f'Wrote {out_csv}: {len(cur)} priors')

    print('\nTop 10 projected MiLB-derived priors:')
    print(cur.sort_values('projected_fp_per_start', ascending=False)
              [['name', 'battersFaced', 'k_pct', 'bb_pct', 'projected_fp_per_start']]
              .head(10).to_string(index=False))


if __name__ == '__main__':
    main()
