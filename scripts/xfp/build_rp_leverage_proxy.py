"""build_rp_leverage_proxy.py — Cleanup #1.

Build a PL-rank-equivalent proxy for non-closer RPs using FanGraphs gmLI
+ BBRef IR/IS% + FG Shutdowns-Meltdowns. Save to historical_panel/.

Proxy construction (per (year) cohort with >=20 IP):
    z_gmLI            (FanGraphs gmLI)
    z_ir_pct          (BBRef IR/IS% — higher IS% = WORSE; we invert)
    z_sd_minus_md     (FG Shutdowns - Meltdowns)
    proxy_value = 0.5*z_gmLI + 0.3*z_ir_inv + 0.2*z_sd_minus_md
    proxy_rank  = rank by proxy_value (1=best) within year
    proxy_pl_rank_mid_inv = 1.0 / (proxy_rank + 5.0)  # matches blend_score
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
FG = ROOT / 'data/research/xfp_cache/fangraphs_rp_leverage_2018_2026.csv'
IR = ROOT / 'data/research/xfp_cache/rp_ir_is_2018_2026.csv'
OUT = ROOT / 'data/research/historical_panel/rp_leverage_proxy_panel.parquet'

IP_FLOOR = 20.0


def _ip_to_float(s):
    # FG/BBRef IP encoded as e.g. 68.1 == 68 + 1/3
    def conv(x):
        try:
            f = float(x)
        except Exception:
            return np.nan
        whole = int(f)
        frac = round((f - whole) * 10)
        if frac == 1:
            return whole + 1.0 / 3.0
        if frac == 2:
            return whole + 2.0 / 3.0
        return float(whole)
    return s.apply(conv)


def main():
    fg = pd.read_csv(FG)
    ir = pd.read_csv(IR)
    print(f'FG raw: {len(fg)}  IR raw: {len(ir)}')

    fg = fg.rename(columns={'season': 'year'})
    ir = ir.rename(columns={'season': 'year'})

    # IP from FG is float-string already; convert
    fg['ip_fg'] = _ip_to_float(fg['ip'])
    fg = fg[fg['ip_fg'] >= IP_FLOOR].copy()

    # IR/IS: is_pct is 0-100; higher = worse stranding. invert so higher=better.
    ir['ir_inv'] = 100.0 - ir['is_pct']

    keep_fg = ['mlb_id', 'year', 'ip_fg', 'gmli', 'shutdowns', 'meltdowns']
    keep_ir = ['mlb_id', 'year', 'ir', 'is_pct', 'ir_inv']
    df = fg[keep_fg].merge(ir[keep_ir], on=['mlb_id', 'year'], how='left')
    df = df.rename(columns={'mlb_id': 'mlbam_id', 'gmli': 'gmLI'})
    df['sd_minus_md'] = df['shutdowns'].fillna(0) - df['meltdowns'].fillna(0)

    # Drop 2020 COVID and 2026 in-progress for fit panel (keep them for ref)
    df['covid_short'] = df['year'] == 2020

    # Z-score within year cohort (only across RPs above IP floor)
    def _z(grp, col):
        m = grp[col].mean()
        s = grp[col].std(ddof=0)
        if not s or np.isnan(s):
            return pd.Series(np.zeros(len(grp)), index=grp.index)
        return (grp[col] - m) / s

    df['z_gmLI'] = df.groupby('year', group_keys=False).apply(lambda g: _z(g, 'gmLI'))
    df['z_ir_inv'] = df.groupby('year', group_keys=False).apply(lambda g: _z(g, 'ir_inv'))
    df['z_sd_minus_md'] = df.groupby('year', group_keys=False).apply(lambda g: _z(g, 'sd_minus_md'))

    # NaN-safe: if ir missing for a row, downweight (use only gmLI + sd-md, renorm)
    has_ir = df['z_ir_inv'].notna()
    df['proxy_value'] = np.where(
        has_ir,
        0.5 * df['z_gmLI'].fillna(0) + 0.3 * df['z_ir_inv'].fillna(0) + 0.2 * df['z_sd_minus_md'].fillna(0),
        # No IR data: 0.5/0.2 -> renorm to 0.714/0.286
        (0.5 / 0.7) * df['z_gmLI'].fillna(0) + (0.2 / 0.7) * df['z_sd_minus_md'].fillna(0),
    )

    # Rank within year (1 = best). Larger proxy_value -> smaller (better) rank.
    df['proxy_rank'] = df.groupby('year')['proxy_value'].rank(ascending=False, method='min').astype(int)
    df['proxy_pl_rank_mid_inv'] = 1.0 / (df['proxy_rank'] + 5.0)

    # Confidence tier
    df['proxy_confidence'] = np.where(df['ip_fg'] >= 40, 'high',
                                      np.where(df['ip_fg'] >= 25, 'mid', 'low'))
    df.loc[df['z_ir_inv'].isna(), 'proxy_confidence'] = 'low'

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f'wrote {OUT}  rows={len(df)}')

    # Verification prints
    print('\nCoverage by year:')
    print(df.groupby('year').size().to_string())
    print('\nConfidence dist:')
    print(df['proxy_confidence'].value_counts().to_string())

    # Top-20 non-closer-ish: low sv but high proxy_rank (most recent full year)
    yr = 2025
    snap = df[df['year'] == yr].merge(
        pd.read_csv(FG)[['mlb_id', 'season', 'player_name_fg', 'team', 'sv']]
        .rename(columns={'mlb_id': 'mlbam_id', 'season': 'year'}),
        on=['mlbam_id', 'year'], how='left')
    non_closer = snap[snap['sv'].fillna(0) < 10].sort_values('proxy_rank').head(20)
    print(f'\nTop-20 non-closer (sv<10) RPs by proxy in {yr}:')
    print(non_closer[['player_name_fg', 'team', 'ip_fg', 'gmLI', 'is_pct',
                      'sd_minus_md', 'proxy_value', 'proxy_rank', 'sv']].to_string(index=False))

    return df


if __name__ == '__main__':
    main()
