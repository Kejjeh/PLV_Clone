"""
xfp_h2_midseason.py — PA-weighted blend of 2025 + 2026 hitter inputs.

Mirrors `scripts/xfp/xfp_v8_midseason.py` for hitters. Trains the H2 winning
feature set frozen on 2018-2025 (drop 2020), then compares two projection
input sets for the 2026 cohort:

A. **frozen H2**  — uses raw 2025-only inputs (where available)
B. **blended H2** — PA-weighted blend of 2025 + 2026 inputs, with
                    Bayesian shrinkage on xwoba_on_contact and contact_pct

Reports YTD r vs `fp_per_pa_actual_2026` (PA ≥ 80) for each.

Decision gate (per the plan):
    blended must beat frozen by ≥ +0.01 in YTD r.
    Otherwise ship frozen and document.
"""
from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / 'data' / 'research' / 'xfp_cache' / 'hitters_multiyr_2015_2026.csv'

# H2 winning feature set (from xfp_h2_pipeline.py output)
H2_FEATS = [
    'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
    'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
    'sprint_speed', 'sb_per_pa',
]

# Bayesian shrinkage priors (per plan)
PRIOR_XWOBA   = (80,  0.305)   # (PRIOR_N, PRIOR_MEAN) — applies to xwoba_on_contact
PRIOR_CONTACT = (200, 0.755)   # contact_pct league average; PA-scaled prior

# Training years (2018-2025 minus 2020)
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
YTD_MIN_PA  = 80      # 2026 hitters with this much PA become evaluable
TRAIN_MIN_PA = 200


def load_substrate() -> pd.DataFrame:
    return pd.read_csv(SUBSTRATE)


def train_h2(df: pd.DataFrame, feats: list[str]):
    """Train Ridge on 2018-2025 (drop 2020) ≥ 200 PA."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV

    train = df[
        (df['year'].isin(TRAIN_YEARS))
        & (df['pa'] >= TRAIN_MIN_PA)
    ].dropna(subset=feats + ['fp_per_pa_actual']).copy()

    pipe = Pipeline([('sc', StandardScaler()),
                     ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    pipe.fit(train[feats].values, train['fp_per_pa_actual'].values)
    return pipe, len(train)


def blend_hitter(row25: pd.Series | None, row26: pd.Series | None) -> dict | None:
    """PA-weighted blend of 2025 + 2026 inputs, with Bayesian shrinkage on
    contact-quality metrics (xwoba_on_contact, contact_pct).
    """
    has25 = row25 is not None and pd.notna(row25.get('pa')) and row25['pa'] > 0
    has26 = row26 is not None and pd.notna(row26.get('pa')) and row26['pa'] > 0
    if not has25 and not has26:
        return None

    if has26 and not has25:
        if row26['pa'] < YTD_MIN_PA:
            return None  # too small a 2026 sample to project from
        out = dict(row26)
        out['cohort'] = '2026_only'
        out['weight_2026'] = 1.0
        return out

    if has25 and not has26:
        # Require ≥ 200 PA in 2025 to project — keeps NL pitchers and
        # September call-ups out of the projection set.
        if row25['pa'] < TRAIN_MIN_PA:
            return None
        out = dict(row25)
        out['cohort'] = '2025_only'
        out['weight_2026'] = 0.0
        return out

    # Both present — require ≥ 50 PA in 2025 OR ≥ 80 PA in 2026 to avoid blending
    # tiny samples that would inflate top of the leaderboard with noise.
    if row25['pa'] < 50 and row26['pa'] < YTD_MIN_PA:
        return None
    n25, n26 = float(row25['pa']), float(row26['pa'])
    out: dict = {}

    rate_feats = [
        'iso', 'k_pct', 'hr_per_pa', 'hard_hit_pct', 'contact_pct', 'whiff_pct',
        'swstr_pct', 'bb_pct', 'z_contact_pct', 'chase_pct', 'in_play_pct',
        'sb_per_pa', 'xwoba_per_pa', 'xwoba_on_contact', 'barrel_pct',
        'avg_swing_speed', 'blast_rate', 'squared_up_rate',
    ]
    for f in rate_feats:
        v25 = row25.get(f)
        v26 = row26.get(f)
        if pd.notna(v25) and pd.notna(v26):
            out[f] = (n25 * v25 + n26 * v26) / (n25 + n26)
        elif pd.notna(v25):
            out[f] = v25
        elif pd.notna(v26):
            out[f] = v26
        else:
            out[f] = np.nan

    # Bayesian shrinkage on xwoba_on_contact (uses BIP-equivalent — approx pa*0.6)
    bip25 = max(1, int(n25 * 0.6))
    bip26 = max(1, int(n26 * 0.6))
    x25 = row25.get('xwoba_on_contact'); x26 = row26.get('xwoba_on_contact')
    if pd.notna(x25) and pd.notna(x26):
        prior_n, prior_mean = PRIOR_XWOBA
        out['xwoba_on_contact'] = ((bip25 * x25) + (bip26 * x26) + (prior_n * prior_mean)) / (bip25 + bip26 + prior_n)

    # contact_pct: shrink toward 0.755
    c25 = row25.get('contact_pct'); c26 = row26.get('contact_pct')
    if pd.notna(c25) and pd.notna(c26):
        prior_n, prior_mean = PRIOR_CONTACT
        out['contact_pct'] = ((n25 * c25) + (n26 * c26) + (prior_n * prior_mean)) / (n25 + n26 + prior_n)

    # Carry through identity + sprint_speed (which doesn't change much YoY)
    out['batter']      = row26.get('batter') if has26 else row25.get('batter')
    out['player_name'] = row26.get('player_name') or row25.get('player_name')
    out['team']        = row26.get('team') or row25.get('team')
    out['pa']          = n25 + n26
    sprint = row26.get('sprint_speed') if pd.notna(row26.get('sprint_speed')) else row25.get('sprint_speed')
    out['sprint_speed'] = sprint
    out['cohort'] = 'blended'
    out['weight_2026'] = n26 / (n25 + n26)
    return out


def project_set(pipe, df_inputs: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Apply trained pipe to a DataFrame of input rows."""
    valid = df_inputs.dropna(subset=feats).copy()
    if valid.empty:
        return valid
    valid['xfp_h2_per_pa'] = pipe.predict(valid[feats].values)
    return valid


def evaluate_ytd(proj: pd.DataFrame, df: pd.DataFrame, feats: list[str], min_pa: int = YTD_MIN_PA) -> dict:
    """YTD r against 2026 actual fp_per_pa, restricted to ≥ min_pa."""
    df_2026 = df[df['year'] == 2026]
    actual = df_2026[df_2026['pa'] >= min_pa][['batter', 'pa', 'fp_per_pa_actual', 'hr_per_pa', 'team']].copy()
    if actual.empty:
        return {'r': np.nan, 'n': 0}
    merged = actual.merge(proj[['batter', 'xfp_h2_per_pa']], on='batter', how='inner').dropna()
    if len(merged) < 5:
        return {'r': np.nan, 'n': len(merged)}
    r = float(np.corrcoef(merged['xfp_h2_per_pa'], merged['fp_per_pa_actual'])[0, 1])
    merged['resid'] = merged['xfp_h2_per_pa'] - merged['fp_per_pa_actual']
    rmse = float(np.sqrt(np.mean(merged['resid']**2)))
    mae  = float(np.mean(merged['resid'].abs()))
    pwr_bias = float(merged[merged['hr_per_pa'] > 0.05]['resid'].mean()) if (merged['hr_per_pa'] > 0.05).any() else 0.0
    return {'r': round(r, 4), 'rmse': round(rmse, 4), 'mae': round(mae, 4),
            'power_bias_hi': round(pwr_bias, 4), 'n': len(merged)}


def main():
    df = load_substrate()
    print(f'=== H3 mid-season blend — substrate {SUBSTRATE.name}: {len(df)} rows ===')
    print(f'H2 features ({len(H2_FEATS)}): {H2_FEATS}\n')

    # Train H2 frozen
    pipe, n_train = train_h2(df, H2_FEATS)
    print(f'Trained H2 on {n_train} rows (years {TRAIN_YEARS}, PA ≥ {TRAIN_MIN_PA})\n')

    df_25 = df[df['year'] == 2025].copy().set_index('batter', drop=True)
    df_26 = df[df['year'] == 2026].copy().set_index('batter', drop=True)
    df_25.index.name = '_batter_idx'
    df_26.index.name = '_batter_idx'

    # Cohort A: frozen H2 — 2025-only inputs (the "do nothing for mid-season" baseline)
    inputs_frozen = df_25.reset_index().rename(columns={'_batter_idx': 'batter'})
    proj_frozen = project_set(pipe, inputs_frozen, H2_FEATS)
    print(f'Cohort A (frozen): {len(proj_frozen)} hitters projected from 2025 inputs')

    # Cohort B: blended — 2025 + 2026 PA-weighted blend
    all_ids = set(df_25.index) | set(df_26.index)
    blended_rows = []
    for b in all_ids:
        r25 = df_25.loc[b] if b in df_25.index else None
        r26 = df_26.loc[b] if b in df_26.index else None
        # Drop pandas Series wrapping if multi-row case (shouldn't happen here)
        if isinstance(r25, pd.DataFrame):
            r25 = r25.iloc[0]
        if isinstance(r26, pd.DataFrame):
            r26 = r26.iloc[0]
        out = blend_hitter(r25, r26)
        if out is not None:
            out['batter'] = b
            blended_rows.append(out)
    inputs_blended = pd.DataFrame(blended_rows)
    proj_blended = project_set(pipe, inputs_blended, H2_FEATS)
    cohort_counts = inputs_blended['cohort'].value_counts().to_dict() if 'cohort' in inputs_blended.columns else {}
    print(f'Cohort B (blended): {len(proj_blended)} projected; cohort sizes = {cohort_counts}\n')

    # YTD evaluation
    print(f'--- YTD evaluation (2026 PA ≥ {YTD_MIN_PA}) ---')
    eval_frozen = evaluate_ytd(proj_frozen, df, H2_FEATS, min_pa=YTD_MIN_PA)
    eval_blend  = evaluate_ytd(proj_blended, df, H2_FEATS, min_pa=YTD_MIN_PA)
    print(f'Frozen  H2 (2025-only inputs):  r={eval_frozen["r"]} mae={eval_frozen["mae"]} pwr_bias={eval_frozen["power_bias_hi"]} n={eval_frozen["n"]}')
    print(f'Blended H2 (2025+2026 blend) :  r={eval_blend["r"]}  mae={eval_blend["mae"]} pwr_bias={eval_blend["power_bias_hi"]} n={eval_blend["n"]}')
    delta_r = eval_blend['r'] - eval_frozen['r'] if eval_frozen['r'] is not np.nan and eval_blend['r'] is not np.nan else np.nan
    print(f'\nΔr (blend - frozen): {delta_r:+.4f}')
    if pd.isna(delta_r):
        print('  Insufficient data — defer decision until more 2026 PAs accumulate.')
    elif delta_r >= 0.01:
        print('  PASS gate — blend ships in H4.')
    else:
        print('  FAIL gate — H4 ships frozen H2 (no blend).')


if __name__ == '__main__':
    main()
