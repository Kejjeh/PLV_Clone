"""validate_drift_v5_sps.py — H1: SP within-season skill drift validation.

Mirrors v4 hitter framework for pitchers:
  - 6-week pre-cutoff window, split into halves
  - Compute half-vs-half delta for each metric:
      avg_velocity, swstr%, K%, BB%, chase%, hard_hit_allowed%
  - Component-level test: does pre-cutoff delta_M predict post-cutoff
    LEVEL of metric M (partial r controlling for first-half baseline)?
  - Integration test: does drift integration improve FP/start prediction
    over cumulative baseline?

Train 2018-2023, holdout 2024-2025.

Promotion bar:
  Component test: partial r ≥ 0.10, sign consistent 5/7 years, holdout ≥ 0.05
  Integration test: pooled r gain ≥ +0.01 over baseline-only model
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

CUTOFF_W = 6
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
TEST_YEARS = [2024, 2025]
ALL_YEARS = TRAIN_YEARS + TEST_YEARS

SP_METRICS = ['avg_velo', 'swstr_pct', 'k_pct', 'bb_pct', 'chase_pct',
               'hard_hit_allowed_pct']
MIN_PRE_BF = 100  # batters faced
MIN_POST_BF = 200


def partial_r(df, x, y, z):
    sub = df[[x, y, z]].dropna()
    if len(sub) < 20: return float('nan')
    sx, ix = np.polyfit(sub[z], sub[x], 1)
    sy, iy = np.polyfit(sub[z], sub[y], 1)
    rx = sub[x] - (sx * sub[z] + ix)
    ry = sub[y] - (sy * sub[z] + iy)
    return float(np.corrcoef(rx, ry)[0,1])


def load_year(year):
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists(): return pd.DataFrame()
    cols = ['game_date', 'pitcher', 'events', 'description', 'pitch_type',
            'launch_speed', 'release_speed', 'zone']
    df = pd.read_parquet(path, columns=cols)
    df['game_date'] = pd.to_datetime(df['game_date'])
    PA_EVENTS = {'single','double','triple','home_run','walk','intent_walk',
                  'hit_by_pitch','strikeout','strikeout_double_play','field_out',
                  'force_out','grounded_into_double_play','sac_fly','sac_bunt',
                  'fielders_choice','fielders_choice_out','double_play',
                  'triple_play','field_error','catcher_interf'}
    SWINGS = {'foul','foul_tip','hit_into_play','swinging_strike',
              'swinging_strike_blocked','missed_bunt'}
    WHIFFS = {'swinging_strike','swinging_strike_blocked'}
    df['is_pa'] = df['events'].isin(PA_EVENTS).astype(int)
    df['is_swing'] = df['description'].isin(SWINGS).astype(int)
    df['is_whiff'] = df['description'].isin(WHIFFS).astype(int)
    df['is_k'] = df['events'].isin({'strikeout','strikeout_double_play'}).astype(int)
    df['is_bb'] = df['events'].isin({'walk','intent_walk'}).astype(int)
    df['in_zone'] = ((df['zone'] >= 1) & (df['zone'] <= 9))
    df['out_zone'] = (df['zone'] >= 11) & (df['zone'] <= 14)
    return df


def metric_values(sub):
    """Compute per-pitcher metrics from a subset."""
    pa = sub[sub['is_pa']==1]
    n_bf = len(pa)
    if n_bf < 25:
        return {m: np.nan for m in SP_METRICS}
    out = {
        'avg_velo': float(sub['release_speed'].mean()) if sub['release_speed'].notna().any() else np.nan,
        'swstr_pct': float(sub['is_whiff'].sum() / len(sub) * 100),
        'k_pct': float(pa['is_k'].sum() / n_bf * 100),
        'bb_pct': float(pa['is_bb'].sum() / n_bf * 100),
    }
    o_swings = (sub['out_zone'] & sub['is_swing']).sum()
    o_pitches = sub['out_zone'].sum()
    out['chase_pct'] = float(o_swings / o_pitches * 100) if o_pitches >= 50 else np.nan
    bbe = sub[sub['launch_speed'].notna()]
    out['hard_hit_allowed_pct'] = float((bbe['launch_speed'] >= 95).mean() * 100) if len(bbe) >= 10 else np.nan
    return out


def skill_fp_per_start(sub):
    """Approx FP/start using BrownU SP formula:
       fp = K + IP*3.3 - H - 2*ER - BB - HBP
       For batters faced we approximate IP from PA outcomes and use simplified ERA via runs scored
       on home_run events. This is rough but consistent across split.
    """
    pa = sub[sub['is_pa']==1]
    if len(pa) == 0: return np.nan, 0
    K = pa['is_k'].sum()
    BB = pa['is_bb'].sum()
    # IP estimate: 3 outs per inning, outs = K + non-K-non-BB-non-H outs
    outs_per_pa = pa['events'].isin({
        'field_out','force_out','grounded_into_double_play','sac_fly','sac_bunt',
        'fielders_choice_out','double_play','triple_play','strikeout',
        'strikeout_double_play',
    }).sum()
    # Add DP/TP extra outs
    dp_extra = pa['events'].isin({'grounded_into_double_play','double_play'}).sum()
    tp_extra = (pa['events'] == 'triple_play').sum() * 2
    outs = outs_per_pa + dp_extra + tp_extra
    ip = outs / 3
    H = pa['events'].isin({'single','double','triple','home_run'}).sum()
    HR = (pa['events'] == 'home_run').sum()
    # Crude ER: assume HR + 30% of hits with runners (approximate). Use HR alone for simplicity.
    ER = HR * 1.5  # rough multiplier accounting for HR allowing 1+ runs avg
    fp = K + ip*3.3 - H - 2*ER - BB
    # Per-start: estimate appearances from game_pk if available; fallback to len/25
    n_starts = max(int(round(len(pa) / 24)), 1)
    return fp / n_starts, n_starts


def build_panel(year_data):
    rows = []
    for year, df in year_data.items():
        if df.empty: continue
        season_start = df['game_date'].min()
        cutoff = season_start + pd.Timedelta(weeks=CUTOFF_W)
        midpoint = season_start + pd.Timedelta(weeks=CUTOFF_W/2)
        pre = df[df['game_date'] < cutoff]
        post = df[df['game_date'] >= cutoff]
        h1 = pre[pre['game_date'] < midpoint]
        h2 = pre[pre['game_date'] >= midpoint]

        pre_bf = pre[pre['is_pa']==1].groupby('pitcher').size()
        post_bf = post[post['is_pa']==1].groupby('pitcher').size()
        qual = set(pre_bf[pre_bf>=MIN_PRE_BF].index) & set(post_bf[post_bf>=MIN_POST_BF].index)
        if not qual: continue
        pre_grp = pre.groupby('pitcher'); post_grp = post.groupby('pitcher')
        h1_grp = h1.groupby('pitcher') if not h1.empty else None
        h2_grp = h2.groupby('pitcher') if not h2.empty else None

        for pid in qual:
            try:
                pb = pre_grp.get_group(pid); pbost = post_grp.get_group(pid)
                h1b = h1_grp.get_group(pid) if h1_grp else None
                h2b = h2_grp.get_group(pid) if h2_grp else None
            except KeyError: continue
            if h1b is None or h2b is None: continue
            base_fp, _ = skill_fp_per_start(pb)
            post_fp, _ = skill_fp_per_start(pbost)
            if pd.isna(base_fp) or pd.isna(post_fp): continue
            m1 = metric_values(h1b); m2 = metric_values(h2b)
            entry = {'year': year, 'pitcher': pid,
                     'baseline_fp_start': base_fp, 'post_fp_start': post_fp}
            for m in SP_METRICS:
                entry[f'first_{m}'] = m1[m]
                entry[f'last_{m}'] = m2[m]
                entry[f'delta_{m}'] = m2[m] - m1[m] if pd.notna(m1[m]) and pd.notna(m2[m]) else np.nan
                # post-cutoff level of metric (for component-level r test)
                post_m = metric_values(pbost)[m]
                entry[f'post_{m}'] = post_m
            rows.append(entry)
    return pd.DataFrame(rows)


def main():
    print('Loading 2018-2025 SP data...')
    year_data = {}
    for y in ALL_YEARS:
        print(f'  {y}...')
        year_data[y] = load_year(y)

    print('\nBuilding SP panel...')
    panel = build_panel(year_data)
    print(f'Panel size: {len(panel)} pitcher-years')
    panel.to_csv(RES / 'drift_v5_sp_panel.csv', index=False)

    # ============== Component-level test (mirror v4 hitter) ==============
    print('\n' + '='*70)
    print('  H1a — COMPONENT-LEVEL: does pre-delta predict post-LEVEL?')
    print('='*70)
    train = panel[panel['year'].isin(TRAIN_YEARS)]
    holdout = panel[panel['year'].isin(TEST_YEARS)]
    print(f'\n{"METRIC":<22s} {"n_train":>8s} {"n_hold":>7s} {"r_train":>8s} {"r_hold":>8s}')
    component_results = []
    for m in SP_METRICS:
        sub_train = train[[f'delta_{m}', f'first_{m}', f'post_{m}']].dropna()
        sub_hold = holdout[[f'delta_{m}', f'first_{m}', f'post_{m}']].dropna()
        if len(sub_train) < 50 or len(sub_hold) < 30:
            print(f'  {m:<22s}  insufficient sample')
            continue
        pr_tr = partial_r(sub_train, f'delta_{m}', f'post_{m}', f'first_{m}')
        pr_ho = partial_r(sub_hold, f'delta_{m}', f'post_{m}', f'first_{m}')
        component_results.append((m, pr_tr, pr_ho))
        print(f'  {m:<22s}  {len(sub_train):>8d} {len(sub_hold):>7d} {pr_tr:>8.3f} {pr_ho:>8.3f}')

    # ============== Integration test (FP/start outcome) ==============
    print('\n' + '='*70)
    print('  H1b — INTEGRATION: does drift improve FP/start prediction?')
    print('='*70)
    delta_cols = [f'delta_{m}' for m in SP_METRICS]
    # Baseline only
    sub = panel.dropna(subset=['baseline_fp_start', 'post_fp_start'] + delta_cols)
    train_sub = sub[sub['year'].isin(TRAIN_YEARS)]
    test_sub = sub[sub['year'].isin(TEST_YEARS)]
    if len(train_sub) < 50 or len(test_sub) < 30:
        print(f'  Insufficient sample: train={len(train_sub)}, test={len(test_sub)}')
        return
    # Method A — baseline only
    X_train_a = np.column_stack([np.ones(len(train_sub)),
                                   train_sub['baseline_fp_start'].values])
    y_train = train_sub['post_fp_start'].values
    coefs_a, *_ = np.linalg.lstsq(X_train_a, y_train, rcond=None)
    X_test_a = np.column_stack([np.ones(len(test_sub)),
                                  test_sub['baseline_fp_start'].values])
    pred_a = X_test_a @ coefs_a
    actual = test_sub['post_fp_start'].values
    r_a = float(np.corrcoef(pred_a, actual)[0,1])

    # Method B — full drift
    X_train_b = np.column_stack([np.ones(len(train_sub)),
                                   train_sub['baseline_fp_start'].values,
                                   train_sub[delta_cols].values])
    coefs_b, *_ = np.linalg.lstsq(X_train_b, y_train, rcond=None)
    X_test_b = np.column_stack([np.ones(len(test_sub)),
                                  test_sub['baseline_fp_start'].values,
                                  test_sub[delta_cols].values])
    pred_b = X_test_b @ coefs_b
    r_b = float(np.corrcoef(pred_b, actual)[0,1])

    print(f'\n  Method A (baseline only):       r = {r_a:.4f}')
    print(f'  Method B (baseline + 6 deltas): r = {r_b:.4f}')
    print(f'  Gain: {r_b-r_a:+.4f}')

    print('\n  Coefficients (Method B):')
    print(f'    α (intercept):        {coefs_b[0]:+.4f}')
    print(f'    β_baseline:           {coefs_b[1]:+.4f}')
    for i, m in enumerate(SP_METRICS):
        print(f'    β_delta_{m:<22s}: {coefs_b[2+i]:+.6f}')

    # Verdict
    print(f'\n=== H1 VERDICT ===')
    n_pass_component = sum(1 for m, tr, ho in component_results
                            if pd.notna(tr) and tr >= 0.10 and pd.notna(ho) and ho >= 0.05)
    print(f'  Component-level: {n_pass_component} of {len(component_results)} metrics pass '
          f'(train r ≥ 0.10 & holdout r ≥ 0.05)')
    if r_b > r_a + 0.01:
        print(f'  Integration: PROMOTE (gain {r_b-r_a:+.4f} > +0.01 bar)')
    elif r_b > r_a:
        print(f'  Integration: marginal gain {r_b-r_a:+.4f}; do not promote')
    else:
        print(f'  Integration: REJECT (no gain)')

    # Save
    pd.DataFrame([{'metric': m, 'r_train': tr, 'r_holdout': ho}
                    for m, tr, ho in component_results]).to_csv(
        RES / 'drift_v5_sp_component_results.csv', index=False)
    pd.DataFrame([{
        'r_baseline': r_a, 'r_with_drift': r_b, 'gain': r_b-r_a,
        'n_train': len(train_sub), 'n_test': len(test_sub),
    }]).to_csv(RES / 'drift_v5_sp_integration_summary.csv', index=False)


if __name__ == '__main__':
    main()
