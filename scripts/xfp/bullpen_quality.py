"""bullpen_quality.py — per-team-year bullpen aggregate.

For each (team, year), compute the team's bullpen FP-per-IP using
relievers_multiyr_2018_2026.csv. Higher = better bullpen (preserves SP wins,
fewer blown leads). Joinable to SPs via team to test as feature.

Output: data/outputs/bullpen_quality.csv
  columns: team, year, bullpen_fp_per_ip, n_rps, total_ip
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('c:/Users/Joshua/plv_clone')
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Use rolling_relievers which has team_abbr (relievers_multiyr does not)
    rel = pd.read_csv(CACHE / 'rolling_relievers_2018_2026.csv')
    # Take latest split per pitcher-year (cumulative season totals)
    rel = rel.sort_values(['pitcher', 'year', 'split_day'])
    rel = rel.drop_duplicates(['pitcher', 'year'], keep='last')
    rel = rel.dropna(subset=['team_abbr', 'year'])
    rel = rel[rel['ip_to'] >= 5]

    # Compute RP FP from raw stats (formula: K + IP*3.3 + SV*5 + HLD*2 - BB - 2*ER - H - HBP)
    rel['rp_fp_full'] = (
        rel['k_to'].fillna(0) + rel['ip_to'].fillna(0) * 3.3
        + rel['sv_to'].fillna(0) * 5 + rel['hld_to'].fillna(0) * 2
        - rel['bb_to'].fillna(0) - 2 * rel['er_to'].fillna(0)
        - rel['h_to'].fillna(0) - rel['hbp_to'].fillna(0)
    )

    agg = rel.groupby(['team_abbr', 'year'], as_index=False).agg(
        bullpen_fp=('rp_fp_full', 'sum'),
        bullpen_ip=('ip_to', 'sum'),
        n_rps=('pitcher', 'nunique'))
    agg['bullpen_fp_per_ip'] = agg['bullpen_fp'] / agg['bullpen_ip'].replace(0, np.nan)
    agg = agg.rename(columns={'team_abbr': 'team'})

    fname = OUT / 'bullpen_quality.csv'
    agg.to_csv(fname, index=False)
    print(f'  wrote {fname} ({len(agg)} team-year rows)')

    # Show 2026 ranking
    cur = agg[agg['year'] == 2026].sort_values('bullpen_fp_per_ip', ascending=False)
    print(f'\n  Best 2026 bullpens (fp/IP):')
    print(cur.head(10)[['team', 'bullpen_fp_per_ip', 'n_rps', 'bullpen_ip']].to_string(index=False))
    print(f'\n  Worst 2026 bullpens:')
    print(cur.tail(5)[['team', 'bullpen_fp_per_ip', 'n_rps', 'bullpen_ip']].to_string(index=False))


if __name__ == '__main__':
    main()
