"""build_skill_drift.py — produce per-hitter drift signals for 2026.

Uses the v4-validated half-vs-half framing. For each hitter with ≥50 pre-PA:
  - Split 2026 statcast into two halves at the midpoint of season-to-date
  - Compute pre-half level and post-half level for each metric
  - Output the delta (drift signal)
  - Apply the v4 partial-r weighting to translate into "expected post-cutoff
    level shift": adjusted_M = first_half_M + r * (late_half_M - first_half_M)

Output: data/outputs/skill_drift_2026.csv
        columns: batter, name, pa, k_pct_first, k_pct_last, k_pct_delta,
                 k_pct_drift_adjusted, (×7 metrics)
"""
from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd
import numpy as np

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'

# v4-validated partial r values (delta predicts post-level)
# from data/research/rolling_trend_v4_results.csv (H2 half-vs-half rows)
DRIFT_WEIGHTS = {
    'ev_p90':         0.53,
    'k_pct':          0.47,
    'whiff_per_swing':0.47,
    'ev_mean':        0.45,
    'hard_hit_pct':   0.45,
    'bb_pct':         0.37,
    'barrel_pct':     0.16,
}

# Direction: True if higher is better for hitter
HIGHER_IS_BETTER = {
    'ev_p90': True, 'ev_mean': True, 'hard_hit_pct': True,
    'bb_pct': True, 'barrel_pct': True,
    'k_pct': False, 'whiff_per_swing': False,
}


def main():
    path = CACHE / 'statcast_2026.parquet'
    df = pd.read_parquet(path, columns=['game_date', 'batter', 'events',
                                          'description', 'launch_speed',
                                          'launch_angle'])
    df['game_date'] = pd.to_datetime(df['game_date'])
    PA_EVENTS = {
        'single','double','triple','home_run','walk','intent_walk','hit_by_pitch',
        'strikeout','strikeout_double_play','field_out','force_out',
        'grounded_into_double_play','sac_fly','sac_bunt','fielders_choice',
        'fielders_choice_out','double_play','triple_play','field_error',
        'catcher_interf',
    }
    SWINGS = {'foul','foul_tip','hit_into_play','swinging_strike',
              'swinging_strike_blocked','missed_bunt'}
    WHIFFS = {'swinging_strike','swinging_strike_blocked'}
    df['is_pa'] = df['events'].isin(PA_EVENTS).astype(int)
    df['is_swing'] = df['description'].isin(SWINGS).astype(int)
    df['is_whiff'] = df['description'].isin(WHIFFS).astype(int)
    df['is_k'] = df['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    df['is_bb'] = df['events'].isin({'walk','intent_walk'}).astype(int)

    season_start = df['game_date'].min()
    season_end = df['game_date'].max()
    midpoint = season_start + (season_end - season_start) / 2
    print(f'Season span {season_start.date()} → {season_end.date()}, midpoint {midpoint.date()}')

    h1 = df[df['game_date'] < midpoint]
    h2 = df[df['game_date'] >= midpoint]
    pa1 = h1[h1['is_pa']==1].groupby('batter').size()
    pa2 = h2[h2['is_pa']==1].groupby('batter').size()
    qual = set(pa1[pa1>=25].index) & set(pa2[pa2>=25].index)
    print(f'Qualified batters: {len(qual)}')

    def compute_metrics(sub):
        pa = sub[sub['is_pa']==1]
        bbe = sub[sub['launch_speed'].notna()]
        bbe_w_angle = sub[sub['launch_speed'].notna() & sub['launch_angle'].notna()]
        result = {
            'pa': len(pa),
            'k_pct': float(pa['is_k'].sum() / len(pa) * 100) if len(pa) else np.nan,
            'bb_pct': float(pa['is_bb'].sum() / len(pa) * 100) if len(pa) else np.nan,
            'whiff_per_swing': float(sub['is_whiff'].sum() / sub['is_swing'].sum() * 100) if sub['is_swing'].sum() else np.nan,
            'ev_mean': float(bbe['launch_speed'].mean()) if len(bbe) else np.nan,
            'ev_p90': float(np.percentile(bbe['launch_speed'], 90)) if len(bbe) >= 10 else np.nan,
            'hard_hit_pct': float((bbe['launch_speed'] >= 95).mean() * 100) if len(bbe) else np.nan,
            'barrel_pct': float(((bbe_w_angle['launch_speed'] >= 98) &
                                  bbe_w_angle['launch_angle'].between(26, 30)).mean() * 100) if len(bbe_w_angle) >= 5 else np.nan,
        }
        return result

    h1g = h1.groupby('batter'); h2g = h2.groupby('batter')

    # Load name map from rh3
    rh3 = pd.read_csv(OUT / 'xfp_rh3_projections.csv')
    name_map = rh3.set_index('batter')['player_name'].to_dict() if 'batter' in rh3.columns else {}

    rows = []
    for bid in qual:
        m1 = compute_metrics(h1g.get_group(bid))
        m2 = compute_metrics(h2g.get_group(bid))
        row = {'batter': bid, 'name': name_map.get(bid, str(bid)),
               'pa_total': m1['pa'] + m2['pa']}
        for metric, weight in DRIFT_WEIGHTS.items():
            v1 = m1[metric]; v2 = m2[metric]
            if pd.isna(v1) or pd.isna(v2):
                row[f'{metric}_first'] = np.nan
                row[f'{metric}_last'] = np.nan
                row[f'{metric}_delta'] = np.nan
                row[f'{metric}_drift_adj'] = np.nan
                continue
            row[f'{metric}_first'] = round(v1, 3)
            row[f'{metric}_last'] = round(v2, 3)
            row[f'{metric}_delta'] = round(v2 - v1, 3)
            # v4-validated drift-adjusted level
            adj = v1 + weight * (v2 - v1)
            row[f'{metric}_drift_adj'] = round(adj, 3)
        rows.append(row)

    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUT / 'skill_drift_2026.csv', index=False)
    print(f'wrote {OUT / "skill_drift_2026.csv"} ({len(out_df)} hitters)')

    # Quick summary: biggest positive and negative drifts on EV90
    print('\n=== Largest positive EV90 drift (improving power) ===')
    sub = out_df.dropna(subset=['ev_p90_delta']).sort_values('ev_p90_delta', ascending=False).head(10)
    print(sub[['name', 'pa_total', 'ev_p90_first', 'ev_p90_last',
               'ev_p90_delta', 'ev_p90_drift_adj']].to_string(index=False))

    print('\n=== Largest negative EV90 drift (declining power) ===')
    sub = out_df.dropna(subset=['ev_p90_delta']).sort_values('ev_p90_delta').head(10)
    print(sub[['name', 'pa_total', 'ev_p90_first', 'ev_p90_last',
               'ev_p90_delta', 'ev_p90_drift_adj']].to_string(index=False))

    print('\n=== Largest K% improvements (negative delta = better) ===')
    sub = out_df.dropna(subset=['k_pct_delta']).sort_values('k_pct_delta').head(10)
    print(sub[['name', 'pa_total', 'k_pct_first', 'k_pct_last',
               'k_pct_delta', 'k_pct_drift_adj']].to_string(index=False))


if __name__ == '__main__':
    main()
