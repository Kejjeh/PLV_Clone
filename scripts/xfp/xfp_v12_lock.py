"""
xfp_v12_lock.py — production lock for V12 (V11 + IL injury features).

P13.4 + P13.5 of the plan. Trains the V12 winning Ridge on 2018-2025
(drop 2020 transition pool noise — but 2020 itself is fine for training
because IL_60_stints from 2019 still applies). Generates blended 2026
projections and writes:

  data/models/xfp_v12_pipeline.pkl     — production bundle
  data/outputs/xfp_v12_projections.csv — blended 2026 projections

Mirrors `scripts/xfp/xfp_v11_lock.py`.
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
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_v12_pipeline import load_substrate, cross_year_evaluate, score_fn  # noqa
from v11_spotcheck import build_blended_inputs  # noqa

V12_FEATS = [
    'zone_pct', 'xwoba_per_pa', 'ip_resid_lag1', 'k_pct_lag1',
    'pitch_entropy', 'bb_pfxz', 'pitching_plus', 'fp_strike_pct',
    'il_60_stints_lag1',
]

# Training window mirrors V11 (2020-2025 where pitching_plus exists)
TRAIN_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

OUT_PKL = ROOT / 'data' / 'models' / 'xfp_v12_pipeline.pkl'
OUT_CSV = ROOT / 'data' / 'outputs' / 'xfp_v12_projections.csv'

# Archetype names to spot-check
ARCHETYPES = ['Bello', 'Littell', 'Scherzer', 'Senga', 'Woodruff', 'Ragans',
              'Glasnow', 'Schlittler', 'Imanaga']


def main():
    print('=== xfp_v12_lock — production lock ===\n')
    df = load_substrate()
    print(f'Substrate rows: {len(df)}')
    print(f'V12 features ({len(V12_FEATS)}): {V12_FEATS}\n')

    # Cross-year r for the bundle
    cy = cross_year_evaluate(df.dropna(subset=V12_FEATS + ['fp_per_start_actual']),
                              V12_FEATS, label='V12')
    score_t1 = score_fn(cy['r'], cy['k_bias_hi'])
    print(f'Cross-year r: {cy["r"]:.4f}  k_bias_hi: {cy["k_bias_hi"]:+.3f}  score(T=1): {score_t1:.4f}\n')

    # Train final pipeline
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    train = df[df['year'].isin(TRAIN_YEARS) & (df['gs'] >= 10)].dropna(subset=V12_FEATS + ['fp_per_start_actual']).copy()
    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=10))])
    pipe.fit(train[V12_FEATS].values, train['fp_per_start_actual'].values)
    print(f'Trained on {len(train)} rows (years {TRAIN_YEARS}, gs ≥ 10)')
    print(f'Selected alpha: {pipe.named_steps["r"].alpha_:.3f}')

    coefs = pipe.named_steps['r'].coef_
    print('\nStandardized coefficients (sorted by |coef|):')
    for f, c in sorted(zip(V12_FEATS, coefs), key=lambda x: -abs(x[1])):
        print(f'  {f:<28s} {c:+.3f}')

    # Build blended 2026 inputs (V8.1 layer)
    blended = build_blended_inputs(df, V12_FEATS)
    print(f'\nBlended 2026 inputs: {len(blended)} pitchers')

    # Project
    valid = blended.dropna(subset=V12_FEATS).copy()
    valid['xfp_v12'] = pipe.predict(valid[V12_FEATS].values)

    # Pull V11 projections for side-by-side comparison
    v11_proj = pd.read_csv(ROOT / 'data' / 'outputs' / 'xfp_v11_projections.csv')
    v11_keep = ['pitcher', 'player_name', 'xfp_v11', 'xfp_v8_5',
                'gs_2026', 'fp_per_start_actual_2026', 'k_pct_2026',
                'stuff_xfp', 'ip_premium', 'rolling_ip_last5', 'ip_trend',
                'ip_trend_score', 'v11_has_pitching_plus']
    v11_keep = [c for c in v11_keep if c in v11_proj.columns]
    out = valid[['pitcher', 'xfp_v12'] + V12_FEATS].merge(v11_proj[v11_keep], on='pitcher', how='left')
    out['delta_v12_v11'] = (out['xfp_v12'] - out['xfp_v11']).round(3)
    out['xfp_v12'] = out['xfp_v12'].round(3)

    # Ranks
    out['rank_v12'] = out['xfp_v12'].rank(ascending=False, method='min').astype(int)
    out['rank_v11'] = out['xfp_v11'].rank(ascending=False, method='min').fillna(0).astype(int)
    out['rank_change'] = out['rank_v11'] - out['rank_v12']  # positive = climbed (better in V12)

    out = out.sort_values('xfp_v12', ascending=False).reset_index(drop=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f'\nWrote {OUT_CSV}: {len(out)} rows')

    # Bundle
    bundle = {
        'pipeline': pipe,
        'features': V12_FEATS,
        'cross_year_r': cy['r'],
        'k_bias_hi': cy['k_bias_hi'],
        'score_T1': score_t1,
        'formula': 'r * 3 - max(0, |k_bias_hi| - 1.0) * 0.5  (T=1.0 production)',
        'trained_date': str(date.today()),
        'n_train': len(train),
        'training_years': TRAIN_YEARS,
        'version': 'v12',
        'alpha': float(pipe.named_steps['r'].alpha_),
        'note': 'V12 = pruned V11 + il_60_stints_lag1. The IL feature is the only injury signal that survived BE.',
    }
    OUT_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, OUT_PKL)
    print(f'Wrote {OUT_PKL}')

    # Verify reload
    bundle2 = joblib.load(OUT_PKL)
    sample = valid[V12_FEATS].head(5).values
    p1 = pipe.predict(sample)
    p2 = bundle2['pipeline'].predict(sample)
    diff = float(np.max(np.abs(p1 - p2)))
    print(f'Reload verify: max diff {diff:.2e} ✓')

    # P13.5 — Archetype spot-check
    print('\n=== P13.5: Archetype spot-check (V12 vs V11 vs actual 2026) ===')
    for name in ARCHETYPES:
        rec = out[out['player_name'].astype(str).str.contains(name, na=False)]
        if rec.empty:
            print(f'  {name:16s}: not found')
            continue
        r = rec.iloc[0]
        actual = r.get('fp_per_start_actual_2026')
        gs = r.get('gs_2026')
        actual_str = f'{actual:5.2f} (gs={int(gs)})' if pd.notna(actual) and pd.notna(gs) else '—'
        print(f'  {r["player_name"]:25s} V11={r["xfp_v11"]:5.2f} → V12={r["xfp_v12"]:5.2f} '
              f'Δ={r["delta_v12_v11"]:+.2f}  rank: {r["rank_v11"]}→{r["rank_v12"]}  actual={actual_str}')

    # Coverage of il_60_stints_lag1
    print(f'\nil_60_stints_lag1 distribution in projection set:')
    print(out['il_60_stints_lag1'].value_counts().sort_index().to_string())

    # Biggest movers V12 vs V11
    print('\n=== Biggest V12 → V11 changes (top 8 each direction) ===')
    print('\nDOWN (V12 lower than V11 — IL history hurts):')
    drops = out.dropna(subset=['xfp_v11']).nsmallest(8, 'delta_v12_v11')
    show_cols = ['player_name', 'xfp_v11', 'xfp_v12', 'delta_v12_v11', 'il_60_stints_lag1', 'fp_per_start_actual_2026', 'gs_2026']
    print(drops[show_cols].to_string(index=False))
    print('\nUP (V12 higher than V11 — clean IL history bonus):')
    ups = out.dropna(subset=['xfp_v11']).nlargest(8, 'delta_v12_v11')
    print(ups[show_cols].to_string(index=False))


if __name__ == '__main__':
    main()
