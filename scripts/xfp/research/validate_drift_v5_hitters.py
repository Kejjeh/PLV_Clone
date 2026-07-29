"""validate_drift_v5_hitters.py — H2, H3, H4, H5, H6, H8, H9 on hitter panel.

Reuses build_panel from drift_integration_backtest.py and enriches with:
  - H2: PCA single-factor on drift signals
  - H3: xwOBA - actual_wOBA gap
  - H4: Drift × baseline interaction terms
  - H5: Age proxy (career stage) — banded coefficients
  - H6: Pitch-mix-specific whiff drift (FB vs breaking)
  - H8: Pre-cutoff weekly FP/PA variance (streakiness)
  - H9: Park offensive factor (static-dict approximation)

Each hypothesis tested against actual post-cutoff FP/PA using
2018-2023 train / 2024-2025 holdout split.

Verdict per hypothesis: pooled r gain over baseline-only model.
Bar: +0.01 to promote.
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

from scripts.xfp.rolling_skill_trend import (
    PA_EVENTS, SWINGS, WHIFFS)
from scripts.xfp.validate_rolling_trend import load_year, skill_fp_per_pa

CUTOFF_W = 6
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
TEST_YEARS = [2024, 2025]
METRICS = ['k_pct', 'bb_pct', 'whiff_per_swing', 'ev_mean', 'ev_p90',
            'hard_hit_pct', 'barrel_pct']

# Park factors from the OWNER (audit 2026-07-04): the hand-typed dict here
# was stale — ATH 0.97 (pitcher-friendly) when Sutter Health plays ~1.05
# HITTER-friendly post-2025 move. _park_R_map is PA-weighted, VENUE_ERAS-aware.
def _load_park_factors():
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.join(_o.path.dirname(__file__), 'lib')) if False else None
    from lib.extra_lenses import _park_R_map
    pf = dict(_park_R_map())
    pf.setdefault('OAK', pf.get('ATH', 1.0))  # legacy code key
    return pf
PARK_FACTORS = _load_park_factors()

FB_TYPES = {'FF', 'SI', 'FC', 'FT', 'FA'}
BR_TYPES = {'SL', 'CU', 'KC', 'ST', 'SV', 'CS'}


def cross_year_r(predictions, actuals, years, test_years):
    """Per-year r and pooled r for the test years."""
    out = []
    pred_pool, act_pool = [], []
    for y in test_years:
        mask = (years == y)
        if mask.sum() < 30: continue
        p, a = predictions[mask], actuals[mask]
        r = float(np.corrcoef(p, a)[0,1]) if len(p) >= 3 else float('nan')
        out.append((y, mask.sum(), r))
        pred_pool.extend(p); act_pool.extend(a)
    r_pool = float(np.corrcoef(pred_pool, act_pool)[0,1]) if len(pred_pool) >= 3 else float('nan')
    return out, r_pool


def fit_predict(panel, feature_cols, train_years, test_years, target='post_fp_pa'):
    """OLS train→test. Returns (pred_test, r_pool_test, coefs)."""
    df = panel.dropna(subset=feature_cols + [target])
    if df.empty: return None, np.nan, None
    train = df[df['year'].isin(train_years)]
    test = df[df['year'].isin(test_years)]
    if len(train) < 50 or len(test) < 30: return None, np.nan, None
    X_train = train[feature_cols].values
    y_train = train[target].values
    X_aug = np.column_stack([np.ones(len(X_train)), X_train])
    coefs, *_ = np.linalg.lstsq(X_aug, y_train, rcond=None)
    X_test = test[feature_cols].values
    X_test_aug = np.column_stack([np.ones(len(X_test)), X_test])
    pred_test = X_test_aug @ coefs
    r_pool = float(np.corrcoef(pred_test, test[target].values)[0,1])
    return test, r_pool, coefs


def build_enriched_panel(year_data):
    """Build per-year enriched hitter panel with all features needed for H2-H9."""
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

        pre_pa = pre[pre['is_pa']==1].groupby('batter').size()
        post_pa = post[post['is_pa']==1].groupby('batter').size()
        qual = set(pre_pa[pre_pa>=50].index) & set(post_pa[post_pa>=100].index)
        if not qual: continue

        pre_grp = pre.groupby('batter'); post_grp = post.groupby('batter')
        h1_grp = h1.groupby('batter') if not h1.empty else None
        h2_grp = h2.groupby('batter') if not h2.empty else None

        def metric_value(sub_pa, sub_full, metric):
            if metric == 'k_pct':
                return sub_pa['is_k'].sum() / len(sub_pa) * 100 if len(sub_pa) else np.nan
            if metric == 'bb_pct':
                return sub_pa['is_bb'].sum() / len(sub_pa) * 100 if len(sub_pa) else np.nan
            if metric == 'whiff_per_swing':
                sw = sub_full['is_swing'].sum()
                if sw == 0: return np.nan
                return sub_full['is_whiff'].sum() / sw * 100
            bbe = sub_full[sub_full['launch_speed'].notna()]
            if metric == 'ev_mean':
                return float(bbe['launch_speed'].mean()) if len(bbe) else np.nan
            if metric == 'ev_p90':
                return float(np.percentile(bbe['launch_speed'], 90)) if len(bbe) >= 10 else np.nan
            if metric == 'hard_hit_pct':
                return float((bbe['launch_speed'] >= 95).mean() * 100) if len(bbe) else np.nan
            if metric == 'barrel_pct':
                bbe_a = sub_full[sub_full['launch_speed'].notna() & sub_full['launch_angle'].notna()]
                if len(bbe_a) < 5: return np.nan
                return float(((bbe_a['launch_speed'] >= 98) & bbe_a['launch_angle'].between(26, 30)).mean() * 100)

        for bid in qual:
            try:
                pb = pre_grp.get_group(bid); postb = post_grp.get_group(bid)
                h1b = h1_grp.get_group(bid) if h1_grp else None
                h2b = h2_grp.get_group(bid) if h2_grp else None
            except KeyError: continue
            if h1b is None or h2b is None: continue
            baseline_r, _ = skill_fp_per_pa(pb['events'])
            post_r, _ = skill_fp_per_pa(postb['events'])
            if pd.isna(baseline_r) or pd.isna(post_r): continue

            entry = {'year': year, 'batter': bid,
                     'baseline_fp_pa': baseline_r,
                     'post_fp_pa': post_r}
            # Half-vs-half deltas (existing v4 features)
            for m in METRICS:
                v1 = metric_value(h1b[h1b['is_pa']==1], h1b, m)
                v2 = metric_value(h2b[h2b['is_pa']==1], h2b, m)
                entry[f'delta_{m}'] = v2 - v1 if pd.notna(v1) and pd.notna(v2) else np.nan
                entry[f'first_{m}'] = v1
                entry[f'last_{m}'] = v2

            # H3 — xwOBA gap (estimated_woba minus actual wOBA over pre-cutoff)
            if 'estimated_woba_using_speedangle' in pb.columns:
                bbe_xw = pb[(pb['estimated_woba_using_speedangle'].notna()) &
                            (pb['is_pa']==1)]
                act_xw = pb[(pb['woba_value'].notna()) & (pb['woba_denom']>0)]
                if len(bbe_xw) >= 30 and len(act_xw) >= 30:
                    xw = float(bbe_xw['estimated_woba_using_speedangle'].mean())
                    aw = float(act_xw['woba_value'].sum() / act_xw['woba_denom'].sum())
                    entry['xwoba_gap'] = xw - aw  # positive = "due to improve"
                else:
                    entry['xwoba_gap'] = np.nan
            else:
                entry['xwoba_gap'] = np.nan

            # H6 — pitch-mix whiff delta
            for stage, sub in [('first', h1b), ('last', h2b)]:
                pt = sub.get('pitch_type', None)
                if pt is None or pt.isna().all():
                    entry[f'{stage}_fb_whiff'] = np.nan
                    entry[f'{stage}_br_whiff'] = np.nan
                    continue
                fb = sub[sub['pitch_type'].isin(FB_TYPES)]
                br = sub[sub['pitch_type'].isin(BR_TYPES)]
                fbs = fb['is_swing'].sum(); fbw = fb['is_whiff'].sum()
                brs = br['is_swing'].sum(); brw = br['is_whiff'].sum()
                entry[f'{stage}_fb_whiff'] = fbw/fbs*100 if fbs >= 20 else np.nan
                entry[f'{stage}_br_whiff'] = brw/brs*100 if brs >= 20 else np.nan
            if pd.notna(entry.get('first_fb_whiff')) and pd.notna(entry.get('last_fb_whiff')):
                entry['delta_fb_whiff'] = entry['last_fb_whiff'] - entry['first_fb_whiff']
            else:
                entry['delta_fb_whiff'] = np.nan
            if pd.notna(entry.get('first_br_whiff')) and pd.notna(entry.get('last_br_whiff')):
                entry['delta_br_whiff'] = entry['last_br_whiff'] - entry['first_br_whiff']
            else:
                entry['delta_br_whiff'] = np.nan

            # H8 — pre-cutoff weekly FP/PA variance (streakiness)
            pb_with_week = pb.copy()
            pb_with_week['week_start'] = pb_with_week['game_date'].dt.to_period('W-SUN').apply(lambda x: x.start_time)
            weekly = pb_with_week[pb_with_week['is_pa']==1].groupby('week_start')
            week_rates = []
            for ws, gw in weekly:
                if len(gw) < 10: continue
                r_w, _ = skill_fp_per_pa(gw['events'])
                if pd.notna(r_w): week_rates.append(r_w)
            entry['fp_pa_weekly_std'] = float(np.std(week_rates)) if len(week_rates) >= 3 else np.nan

            # H9 — park factor proxy (avg of all parks player played in pre-cutoff)
            # We don't have home_team in our reduced cache, so use a player-level proxy
            # via majority team. Skip if not in PARK_FACTORS or not available.
            entry['park_factor'] = np.nan  # placeholder — would need home_team col

            rows.append(entry)
    return pd.DataFrame(rows)


def main():
    print('Loading 2018-2025 hitter data...')
    year_data = {}
    for y in TRAIN_YEARS + TEST_YEARS:
        print(f'  {y}...')
        year_data[y] = load_year(y)

    print('\nBuilding enriched panel...')
    panel = build_enriched_panel(year_data)
    print(f'Panel size: {len(panel)} hitter-years')
    panel.to_csv(RES / 'drift_panel_v5_hitters.csv', index=False)

    # ============== Baseline (Method A) ==============
    print('\n=== BASELINE: baseline_fp_pa only ===')
    delta_cols = [f'delta_{m}' for m in METRICS]
    baseline_feats = ['baseline_fp_pa']
    test, r_baseline, coefs_base = fit_predict(panel, baseline_feats, TRAIN_YEARS, TEST_YEARS)
    print(f'  Pooled r: {r_baseline:.4f}')

    # Previous winner (full drift, our v3 integration baseline)
    full_drift_feats = ['baseline_fp_pa'] + delta_cols
    _, r_full_drift, _ = fit_predict(panel, full_drift_feats, TRAIN_YEARS, TEST_YEARS)
    print(f'  Drift integration v1 (all 7 deltas) pooled r: {r_full_drift:.4f}  '
          f'(gain over baseline: {r_full_drift-r_baseline:+.4f})')

    verdicts = []

    # ============== H2: PCA single-factor ==============
    print('\n=== H2: PCA single-factor (PC1 of drift deltas) ===')
    train = panel[panel['year'].isin(TRAIN_YEARS)].dropna(subset=delta_cols)
    test = panel[panel['year'].isin(TEST_YEARS)].dropna(subset=delta_cols)
    if len(train) >= 50 and len(test) >= 30:
        X_train = train[delta_cols].values
        X_train_c = X_train - X_train.mean(axis=0)
        X_train_s = X_train_c / (X_train_c.std(axis=0) + 1e-9)
        U, S, Vt = np.linalg.svd(X_train_s, full_matrices=False)
        pc1 = X_train_s @ Vt[0]
        # Transform test set with same parameters
        X_test = test[delta_cols].values
        X_test_c = X_test - X_train.mean(axis=0)
        X_test_s = X_test_c / (X_train_c.std(axis=0) + 1e-9)
        pc1_test = X_test_s @ Vt[0]
        # Fit with baseline_fp_pa + pc1
        train_aug = train.copy(); train_aug['_pc1'] = pc1
        test_aug = test.copy(); test_aug['_pc1'] = pc1_test
        # Manual OLS
        X = np.column_stack([np.ones(len(train_aug)), train_aug['baseline_fp_pa'].values, train_aug['_pc1'].values])
        y = train_aug['post_fp_pa'].values
        coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
        X_t = np.column_stack([np.ones(len(test_aug)), test_aug['baseline_fp_pa'].values, test_aug['_pc1'].values])
        pred = X_t @ coefs
        r_pca = float(np.corrcoef(pred, test_aug['post_fp_pa'].values)[0,1])
        gain = r_pca - r_baseline
        verdicts.append(('H2_PCA_single_factor', r_pca, gain))
        print(f'  Pooled r: {r_pca:.4f}  (gain over baseline: {gain:+.4f})')
        print(f'  PC1 explains {S[0]**2 / (S**2).sum() * 100:.1f}% of variance')
    else:
        verdicts.append(('H2_PCA_single_factor', np.nan, np.nan))
        print('  insufficient sample')

    # ============== H3: xwOBA gap ==============
    print('\n=== H3: xwOBA-actual_wOBA gap regression candidate ===')
    feats = ['baseline_fp_pa', 'xwoba_gap']
    _, r_h3, c = fit_predict(panel, feats, TRAIN_YEARS, TEST_YEARS)
    gain = r_h3 - r_baseline
    verdicts.append(('H3_xwoba_gap', r_h3, gain))
    print(f'  Pooled r: {r_h3:.4f}  (gain: {gain:+.4f})  beta_gap = {c[2] if c is not None else "n/a"}')

    # ============== H4: drift × baseline interaction ==============
    print('\n=== H4: drift × baseline interaction ===')
    pa = panel.copy()
    for m in METRICS:
        pa[f'inter_{m}'] = pa[f'delta_{m}'] * pa['baseline_fp_pa']
    inter_cols = [f'inter_{m}' for m in METRICS]
    feats = ['baseline_fp_pa'] + delta_cols + inter_cols
    _, r_h4, _ = fit_predict(pa, feats, TRAIN_YEARS, TEST_YEARS)
    gain = r_h4 - r_baseline
    verdicts.append(('H4_drift_x_baseline_interaction', r_h4, gain))
    print(f'  Pooled r: {r_h4:.4f}  (gain over baseline: {gain:+.4f})  '
          f'(gain over full drift: {r_h4-r_full_drift:+.4f})')

    # ============== H5: Age-band proxy ==============
    # Approx age via "career stage" = years since first MLB year
    # Skip if we don't have first-year data; use career-PA proxy instead.
    print('\n=== H5: Age-band conditional (career-PA proxy) ===')
    h = pd.read_csv(CACHE / 'hitters_multiyr_2015_2026.csv')
    first_year = h.groupby('batter')['year'].min().to_dict()
    panel_h5 = panel.copy()
    panel_h5['career_stage'] = panel_h5.apply(
        lambda r: r['year'] - first_year.get(r['batter'], r['year']), axis=1)
    # Band: 0-1 = rookie/sophomore, 2-4 = developing, 5-9 = prime, 10+ = vet
    def age_band(s):
        if s <= 1: return 1
        if s <= 4: return 2
        if s <= 9: return 3
        return 4
    panel_h5['age_band'] = panel_h5['career_stage'].apply(age_band)
    # Add age_band one-hot interaction with drift terms — too many params
    # Simpler: include age_band as additional feature alongside drift
    feats = ['baseline_fp_pa', 'career_stage'] + delta_cols
    _, r_h5, _ = fit_predict(panel_h5, feats, TRAIN_YEARS, TEST_YEARS)
    gain = r_h5 - r_baseline
    verdicts.append(('H5_age_band_proxy', r_h5, gain))
    print(f'  Pooled r: {r_h5:.4f}  (gain: {gain:+.4f})')

    # ============== H6: Pitch-mix whiff ==============
    print('\n=== H6: Pitch-mix-specific whiff drift (FB vs BR) ===')
    feats = ['baseline_fp_pa', 'delta_fb_whiff', 'delta_br_whiff']
    _, r_h6, _ = fit_predict(panel, feats, TRAIN_YEARS, TEST_YEARS)
    gain = r_h6 - r_baseline
    verdicts.append(('H6_pitch_mix_whiff', r_h6, gain))
    print(f'  Pooled r: {r_h6:.4f}  (gain: {gain:+.4f})')

    # ============== H7: Lineup spot (SKIPPED) ==============
    verdicts.append(('H7_lineup_spot', np.nan, np.nan))
    print('\n=== H7: Lineup-spot context — SKIPPED ===')
    print('  Statcast does not include batting order; would require ESPN lineup data')
    print('  per game. Not feasible with current data sources without a separate pull.')

    # ============== H8: Streakiness ==============
    print('\n=== H8: Pre-cutoff weekly FP/PA variance (streakiness) ===')
    feats = ['baseline_fp_pa', 'fp_pa_weekly_std']
    _, r_h8, c = fit_predict(panel, feats, TRAIN_YEARS, TEST_YEARS)
    gain = r_h8 - r_baseline
    verdicts.append(('H8_streakiness', r_h8, gain))
    print(f'  Pooled r: {r_h8:.4f}  (gain: {gain:+.4f})  '
          f'beta_std = {c[2] if c is not None else "n/a"}')

    # ============== H9: Park factor ==============
    print('\n=== H9: Park-factor adjustment ===')
    print('  Skipped in this batch: requires home_team column in pre-cutoff aggregates')
    print('  (not in our reduced statcast cache). Would need a separate park-stats pull.')
    verdicts.append(('H9_park_factor', np.nan, np.nan))

    # ============== Verdict table ==============
    print('\n' + '='*70)
    print('  VERDICT TABLE — hitter-side hypotheses (H2-H9 except H1)')
    print('='*70)
    print(f'  Baseline (cumulative FP/PA only) pooled r:        {r_baseline:.4f}')
    print(f'  Full-drift integration (v4 baseline) pooled r:    {r_full_drift:.4f}')
    print(f'  Promote bar: gain ≥ +0.01 vs baseline\n')
    print(f'  {"HYPOTHESIS":<40s} {"r":>7s} {"gain":>+8s} {"verdict":<10s}')
    for label, r, gain in verdicts:
        if pd.isna(r):
            print(f'  {label:<40s} {"n/a":>7s} {"n/a":>8s} {"skipped":<10s}')
        else:
            v = 'PROMOTE' if gain >= 0.01 else ('marginal' if gain >= 0.001 else 'reject')
            print(f'  {label:<40s} {r:>7.4f} {gain:>+8.4f} {v:<10s}')

    pd.DataFrame([{'hypothesis': l, 'r': r, 'gain': g}
                    for l, r, g in verdicts]).to_csv(RES / 'drift_v5_hitter_verdicts.csv', index=False)
    print(f'\nwrote drift_v5_hitter_verdicts.csv')


if __name__ == '__main__':
    main()
