"""validate_drift_v5_fixes.py — corrections to v5_hitters.

Issues fixed:
  1. Apples-to-apples sample comparison: re-run baseline r on the SAME
     hitters used in each hypothesis (avoids sample-selection bias).
  2. H3 (xwOBA gap): load estimated_woba/woba_value into panel.
  3. H9 (park factor): attempt with home_team column.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
RES = ROOT / 'data' / 'research'
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'

PA_EVENTS = {'single','double','triple','home_run','walk','intent_walk',
              'hit_by_pitch','strikeout','strikeout_double_play','field_out',
              'force_out','grounded_into_double_play','sac_fly','sac_bunt',
              'fielders_choice','fielders_choice_out','double_play',
              'triple_play','field_error','catcher_interf'}
SWINGS = {'foul','foul_tip','hit_into_play','swinging_strike',
          'swinging_strike_blocked','missed_bunt'}
WHIFFS = {'swinging_strike','swinging_strike_blocked'}

CUTOFF_W = 6
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
TEST_YEARS = [2024, 2025]

PARK_FACTORS = {
    'COL': 1.20, 'CIN': 1.10, 'BOS': 1.07, 'PHI': 1.05, 'TEX': 1.05,
    'BAL': 1.04, 'TOR': 1.04, 'NYY': 1.04, 'CHC': 1.03, 'HOU': 1.03,
    'ATL': 1.02, 'MIL': 1.02, 'WSH': 1.01, 'ARI': 1.01, 'MIN': 1.00,
    'STL': 1.00, 'CWS': 1.00, 'CLE': 1.00, 'LAA': 1.00, 'NYM': 0.99,
    'TB': 0.97, 'OAK': 0.97, 'ATH': 0.97, 'PIT': 0.97, 'KC': 0.96,
    'SEA': 0.95, 'DET': 0.95, 'MIA': 0.94, 'SF': 0.94, 'SD': 0.92, 'LAD': 1.00,
}


def load_year_full(year):
    """Load with woba columns AND home_team for H3/H9."""
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists(): return pd.DataFrame()
    cols_try = ['game_date', 'batter', 'events', 'description',
                'launch_speed', 'launch_angle',
                'estimated_woba_using_speedangle', 'woba_value', 'woba_denom',
                'home_team']
    actual = pd.read_parquet(path).columns.tolist()
    cols_have = [c for c in cols_try if c in actual]
    df = pd.read_parquet(path, columns=cols_have)
    df['game_date'] = pd.to_datetime(df['game_date'])
    df['is_pa'] = df['events'].isin(PA_EVENTS).astype(int)
    df['is_swing'] = df['description'].isin(SWINGS).astype(int)
    df['is_whiff'] = df['description'].isin(WHIFFS).astype(int)
    df['is_k'] = df['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    df['is_bb'] = df['events'].isin({'walk','intent_walk'}).astype(int)
    return df


def main():
    panel = pd.read_csv(RES / 'drift_panel_v5_hitters.csv')
    print(f'Existing panel: {len(panel)} hitter-years')

    # === Add xwOBA gap and park factor columns ===
    print('Loading per-year statcast with wOBA and home_team...')
    new_features = []
    for y in TRAIN_YEARS + TEST_YEARS:
        print(f'  {y}...')
        df = load_year_full(y)
        if df.empty: continue
        season_start = df['game_date'].min()
        cutoff = season_start + pd.Timedelta(weeks=CUTOFF_W)
        pre = df[df['game_date'] < cutoff]
        pre_pa_cnt = pre[pre['is_pa']==1].groupby('batter').size()
        qual = pre_pa_cnt[pre_pa_cnt>=50].index

        for bid in qual:
            pb = pre[pre['batter'] == bid]
            entry = {'year': y, 'batter': bid}
            # H3: xwOBA gap
            if 'estimated_woba_using_speedangle' in pb.columns:
                bbe = pb[pb['estimated_woba_using_speedangle'].notna()]
                act = pb[pb['woba_denom'] > 0] if 'woba_denom' in pb.columns else pd.DataFrame()
                if len(bbe) >= 30 and len(act) >= 30:
                    xw = float(bbe['estimated_woba_using_speedangle'].mean())
                    aw = float(act['woba_value'].sum() / act['woba_denom'].sum())
                    entry['xwoba_gap'] = xw - aw
                else:
                    entry['xwoba_gap'] = np.nan
            else:
                entry['xwoba_gap'] = np.nan
            # H9: park factor (majority home_team)
            if 'home_team' in pb.columns:
                ht = pb['home_team'].mode()
                if len(ht):
                    entry['home_park'] = ht.iloc[0]
                    entry['park_factor'] = PARK_FACTORS.get(ht.iloc[0], 1.00)
                else:
                    entry['home_park'] = None; entry['park_factor'] = 1.00
            new_features.append(entry)
    fdf = pd.DataFrame(new_features)
    print(f'  new features dataframe: {len(fdf)} rows')

    # Merge into panel
    merged = panel.merge(fdf, on=['year', 'batter'], how='left',
                          suffixes=('', '_new'))
    if 'xwoba_gap_new' in merged.columns:
        merged['xwoba_gap'] = merged['xwoba_gap_new']
        merged.drop(columns=['xwoba_gap_new'], inplace=True)
    print(f'  xwoba_gap non-null after merge: {merged["xwoba_gap"].notna().sum()}')
    print(f'  park_factor non-null after merge: {merged["park_factor"].notna().sum()}')

    # === Helper: fit and predict, with apples-to-apples sample ===
    def fit_predict(panel_, feature_cols, target='post_fp_pa'):
        sub = panel_.dropna(subset=feature_cols + [target])
        train = sub[sub['year'].isin(TRAIN_YEARS)]
        test = sub[sub['year'].isin(TEST_YEARS)]
        if len(train) < 50 or len(test) < 30:
            return None, np.nan, len(test)
        X_train = np.column_stack([np.ones(len(train))] + [train[c].values for c in feature_cols])
        X_test = np.column_stack([np.ones(len(test))] + [test[c].values for c in feature_cols])
        coefs, *_ = np.linalg.lstsq(X_train, train[target].values, rcond=None)
        pred = X_test @ coefs
        r = float(np.corrcoef(pred, test[target].values)[0,1])
        return coefs, r, len(test)

    METRICS = ['k_pct', 'bb_pct', 'whiff_per_swing', 'ev_mean', 'ev_p90',
                'hard_hit_pct', 'barrel_pct']
    delta_cols = [f'delta_{m}' for m in METRICS]

    print('\n' + '='*70)
    print('  APPLES-TO-APPLES verdict table (each hypothesis compared to')
    print('  the SAME sample baseline)')
    print('='*70)
    print(f'\n  {"HYPOTHESIS":<42s} {"N":>5s} {"r_base":>7s} {"r_hyp":>7s} {"gain":>8s} {"verdict":<8s}')

    tests = [
        ('Drift integration v1 (all 7 deltas)', ['baseline_fp_pa'] + delta_cols, delta_cols),
        ('H3 xwOBA gap', ['baseline_fp_pa', 'xwoba_gap'], ['xwoba_gap']),
        ('H4 drift x baseline interaction', ['baseline_fp_pa'] + delta_cols +
            [f'inter_{m}' for m in METRICS],
            delta_cols + [f'inter_{m}' for m in METRICS]),
        ('H5 career-stage feature', ['baseline_fp_pa', 'career_stage'] + delta_cols,
            ['career_stage'] + delta_cols),
        ('H6 pitch-mix whiff (FB+BR)', ['baseline_fp_pa', 'delta_fb_whiff', 'delta_br_whiff'],
            ['delta_fb_whiff', 'delta_br_whiff']),
        ('H8 streakiness (weekly std)', ['baseline_fp_pa', 'fp_pa_weekly_std'],
            ['fp_pa_weekly_std']),
        ('H9 park factor', ['baseline_fp_pa', 'park_factor'], ['park_factor']),
    ]

    # Add interaction columns
    for m in METRICS:
        merged[f'inter_{m}'] = merged[f'delta_{m}'] * merged['baseline_fp_pa']

    # Add career_stage
    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    first_year = h.groupby('batter')['year'].min().to_dict()
    merged['career_stage'] = merged.apply(
        lambda r: r['year'] - first_year.get(r['batter'], r['year']), axis=1)

    verdicts = []
    for label, feats, extra_cols in tests:
        # Apples-to-apples baseline: same sample, baseline_fp_pa only
        sub_drop = merged.dropna(subset=feats + ['post_fp_pa'])
        train_b = sub_drop[sub_drop['year'].isin(TRAIN_YEARS)]
        test_b = sub_drop[sub_drop['year'].isin(TEST_YEARS)]
        if len(train_b) < 50 or len(test_b) < 30:
            print(f'  {label:<42s} {"n/a":>5s}  insufficient sample')
            continue
        # Baseline on same sample
        X = np.column_stack([np.ones(len(train_b)), train_b['baseline_fp_pa'].values])
        cb, *_ = np.linalg.lstsq(X, train_b['post_fp_pa'].values, rcond=None)
        Xt = np.column_stack([np.ones(len(test_b)), test_b['baseline_fp_pa'].values])
        r_b = float(np.corrcoef(Xt @ cb, test_b['post_fp_pa'].values)[0,1])
        # Hypothesis on same sample
        _, r_h, _ = fit_predict(sub_drop, feats)
        gain = r_h - r_b
        v = 'PROMOTE' if gain >= 0.01 else ('marginal' if gain >= 0.001 else 'reject')
        print(f'  {label:<42s} {len(test_b):>5d} {r_b:>7.4f} {r_h:>7.4f} {gain:>+8.4f} {v:<8s}')
        verdicts.append({'hypothesis': label, 'n_test': len(test_b), 'r_baseline': r_b,
                          'r_hypothesis': r_h, 'gain': gain, 'verdict': v})

    pd.DataFrame(verdicts).to_csv(RES / 'drift_v5_apples_to_apples_verdicts.csv', index=False)
    print(f'\nwrote drift_v5_apples_to_apples_verdicts.csv')


if __name__ == '__main__':
    main()
