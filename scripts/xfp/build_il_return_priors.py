"""build_il_return_priors.py — empirical IL time-to-return priors (E1.5a).

From the consolidated MLB transactions log (il_transactions_2015_2026.parquet,
18k IL events 2015-2026), assembles placement→activation stints and computes
the empirical days-to-return distribution stratified by:
  - IL tier (7/10/15/60-day; pre-2020 "disabled list" wording handled)
  - pitcher vs hitter (parsed from the description's position prefix)
  - coarse injury bucket (keyword match on the description tail)
  - month of placement (Sept placements are often season-ending)

Honesty rule: activation-conditional duration quantiles UNDERSTATE true time
on the IL (censoring: stints with no activation — season-ending, release,
outright — never enter the quantiles). Every stratum therefore reports its
censor rate alongside; a consumer scaling availability must treat
p50/p75 as conditional-on-return, and the censor rate as P(no return this
season) mass.

Outputs:
  data/research/il_return_priors.csv   (one row per stratum)
  stdout study summary

Downstream (gated, NOT wired here): build_xfp_boards.py's four availability
branches would blend the ESPN estimated return date toward these
tier-conditional priors via one calibrated_avail() helper — only after a
pre-registered validation vs the current raw-ESPN-date behavior.

Run: python -X utf8 scripts/xfp/build_il_return_priors.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT

TX_PARQUET = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_transactions_2015_2026.parquet'
OUT_CSV = ROOT / 'data' / 'research' / 'il_return_priors.csv'

# Position tokens that mark a pitcher in the transaction description
_PITCHER_POS = re.compile(r'\b(RHP|LHP|P)\b')

_INJURY_BUCKETS = [
    ('tommy_john_elbow', re.compile(r'tommy john|ucl|elbow', re.I)),
    ('shoulder_lat', re.compile(r'shoulder|lat |rotator|labrum', re.I)),
    ('forearm', re.compile(r'forearm|flexor', re.I)),
    ('oblique_core', re.compile(r'oblique|abdomin|core|intercostal', re.I)),
    ('hamstring', re.compile(r'hamstring', re.I)),
    ('back_neck', re.compile(r'\bback\b|spine|neck', re.I)),
    ('knee_leg', re.compile(r'knee|quad|calf|achilles|ankle|shin|groin|hip', re.I)),
    ('hand_wrist', re.compile(r'hand|wrist|finger|thumb', re.I)),
    ('concussion', re.compile(r'concussion', re.I)),
]


def _tier(desc: str) -> str:
    m = re.search(r'(\d+)-day', desc.lower())
    return f'IL{m.group(1)}' if m else 'IL_unspecified'


def _is_pitcher(desc: str) -> bool:
    m = re.search(r'placed\s+(\S+)', desc)
    return bool(m and _PITCHER_POS.fullmatch(m.group(1)))


def _injury_bucket(desc: str) -> str:
    for name, pat in _INJURY_BUCKETS:
        if pat.search(desc):
            return name
    return 'other_unspecified'


def build_stints(tx: pd.DataFrame) -> pd.DataFrame:
    """Assemble PLACE→(TRANSFER)*→RETURN stints per player, within season."""
    tx = tx.sort_values(['mlbam_id', 'date']).copy()
    tx['date'] = pd.to_datetime(tx['date'])
    tx['year'] = tx['date'].dt.year
    stints = []
    for (pid, yr), g in tx.groupby(['mlbam_id', 'year']):
        open_stint = None
        for _, r in g.iterrows():
            act = r['il_action']
            if act == 'PLACE':
                if open_stint is not None:
                    # unreturned earlier stint in the same season: censored
                    stints.append(open_stint)
                open_stint = {
                    'mlbam_id': pid, 'year': yr,
                    'place_date': r['date'],
                    'tier': _tier(r['description']),
                    'is_pitcher': _is_pitcher(r['description']),
                    'injury': _injury_bucket(r['description']),
                    'month': int(r['date'].month),
                    'transferred_60': False,
                    'return_date': None,
                }
            elif act == 'TRANSFER' and open_stint is not None:
                open_stint['transferred_60'] = True
            elif act == 'ACTIVATE' and open_stint is not None:
                open_stint['return_date'] = r['date']
                stints.append(open_stint)
                open_stint = None
        if open_stint is not None:
            stints.append(open_stint)   # censored at season end
    df = pd.DataFrame(stints)
    df['return_date'] = pd.to_datetime(df['return_date'])
    df['days'] = (df['return_date'] - df['place_date']).dt.days
    df['censored'] = df['return_date'].isna()
    # effective tier: a 10/15-day stint transferred to the 60-day IL behaves
    # like a 60-day stint for availability purposes
    df['tier_eff'] = np.where(df['transferred_60'] & df['tier'].isin(
        ['IL10', 'IL15', 'IL7']), 'IL60_via_transfer', df['tier'])
    return df


def _stratum_row(label_cols: dict, g: pd.DataFrame) -> dict:
    ok = g[~g['censored'] & g['days'].notna() & (g['days'] >= 0)]
    row = dict(label_cols)
    row.update({
        'n_stints': len(g),
        'n_returned': len(ok),
        'censor_rate': round(1 - len(ok) / max(len(g), 1), 3),
    })
    if len(ok) >= 10:
        q = ok['days'].quantile([0.25, 0.5, 0.75, 0.9])
        row.update({
            'p25_days': round(q[0.25], 1), 'p50_days': round(q[0.5], 1),
            'p75_days': round(q[0.75], 1), 'p90_days': round(q[0.9], 1),
            'mean_days': round(float(ok['days'].mean()), 1),
        })
    return row


def main() -> int:
    tx = pd.read_parquet(TX_PARQUET)
    print(f'=== IL return priors (E1.5a) — {len(tx)} events 2015-2026 ===')
    print(f'il_action values: {tx["il_action"].value_counts().to_dict()}')

    stints = build_stints(tx)
    print(f'\nassembled {len(stints)} stints '
          f'({(~stints.censored).sum()} returned, '
          f'{stints.censored.sum()} censored/season-ending)')

    rows = []
    # tier × pitcher/hitter (the board-facing headline strata)
    for (tier, is_p), g in stints.groupby(['tier_eff', 'is_pitcher']):
        rows.append(_stratum_row(
            {'stratum': 'tier_x_pos', 'tier': tier,
             'pos': 'P' if is_p else 'H', 'injury': '', 'month': ''}, g))
    # tier × injury bucket (pitchers only — the stash-valuation case)
    for (tier, inj), g in stints[stints.is_pitcher].groupby(['tier_eff', 'injury']):
        rows.append(_stratum_row(
            {'stratum': 'tier_x_injury_P', 'tier': tier, 'pos': 'P',
             'injury': inj, 'month': ''}, g))
    # month of placement (all tiers pooled — the season-ending gradient)
    for m, g in stints.groupby('month'):
        rows.append(_stratum_row(
            {'stratum': 'by_month', 'tier': '', 'pos': '', 'injury': '',
             'month': m}, g))

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    print(f'\nwrote {OUT_CSV.name} ({len(out)} strata)')

    print('\n--- headline: tier × position (returned-only quantiles | censor) ---')
    head = out[(out.stratum == 'tier_x_pos') & (out.n_stints >= 30)]
    print(head.drop(columns=['stratum', 'injury', 'month'])
              .sort_values(['tier', 'pos']).to_string(index=False))

    print('\n--- month-of-placement censor gradient ---')
    bym = out[out.stratum == 'by_month']
    print(bym[['month', 'n_stints', 'censor_rate', 'p50_days']]
          .sort_values('month').to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
