"""validate_pitch_shape_deep.py — comprehensive pitch-shape feature sweep.

After level-1 (velo/ext/iVB) validated at +0.04 r, test additional features
that PL writers mention but our model doesn't see yet:

  Level 2 — pitch-shape additions:
    - HB (horizontal break) — same calculation as iVB, x-axis
    - Spin rate per pitch type
    - Vertical Approach Angle (VAA): atan((plate_z − release_pos_z) /
        (60.5 − extension))  in degrees. Lower = flatter "rising" FB.
    - Whiff per swing PER pitch type (does declining FB whiff% predict FP loss?)
    - Release-point stability (std of release_pos_x within season)

  Level 3 — usage / stamina additions:
    - Pitch-mix delta (FB% / BR% / OFF% vs career)
    - Velocity dispersion within season (career std vs current std)
    - Within-game velocity decline (first 25 pitches vs pitches 60+)
      ← this is the Sheehan-specific "velocity drops in-game" concern

Each new feature added progressively; r gain reported.

Promote bar: +0.005 incremental r over best previous model.
"""
from __future__ import annotations
from pathlib import Path
import sys
import math
import unicodedata
import re
import numpy as np
import pandas as pd

ROOT = Path('c:/Users/Joshua/plv_clone')
sys.path.insert(0, str(ROOT))
CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
RES = ROOT / 'data' / 'research'

YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
TRAIN = [2018, 2019, 2021, 2022, 2023]
TEST = [2024, 2025]

FB_TYPES = {'FF', 'SI', 'FC', 'FT', 'FA'}
BR_TYPES = {'SL', 'CU', 'KC', 'ST', 'SV', 'CS'}
OFF_TYPES = {'CH', 'FS', 'SC'}

PA_EVENTS = {'single','double','triple','home_run','walk','intent_walk',
              'hit_by_pitch','strikeout','strikeout_double_play','field_out',
              'force_out','grounded_into_double_play','sac_fly','sac_bunt',
              'fielders_choice','fielders_choice_out','double_play',
              'triple_play','field_error','catcher_interf'}
SWINGS = {'foul','foul_tip','hit_into_play','swinging_strike',
          'swinging_strike_blocked','missed_bunt'}
WHIFFS = {'swinging_strike','swinging_strike_blocked'}


# Name join key — OWNER: plv_clone.utils.name_match.join_key (order-independent,
# so "Fried, Max" == "Max Fried"). NEVER re-derive locally: 127 local copies
# drifted apart and mis-keyed Ryan O'Hearn's curly apostrophe (2026-07-28).
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


def load_year(year):
    path = CACHE / f'statcast_{year}.parquet'
    if not path.exists(): return pd.DataFrame()
    cols_try = ['pitcher', 'game_pk', 'inning', 'pitch_number', 'at_bat_number',
                'pitch_type', 'description', 'events',
                'release_speed', 'release_extension', 'release_spin_rate',
                'release_pos_x', 'release_pos_z',
                'plate_x', 'plate_z', 'pfx_x', 'pfx_z']
    actual = pd.read_parquet(path).columns.tolist()
    cols = [c for c in cols_try if c in actual]
    df = pd.read_parquet(path, columns=cols)
    return df


def compute_pitcher_features(df: pd.DataFrame) -> pd.DataFrame:
    """For one year's statcast, compute per-pitcher features."""
    if df.empty: return pd.DataFrame()
    df = df.copy()
    df['is_fb'] = df['pitch_type'].isin(FB_TYPES)
    df['is_br'] = df['pitch_type'].isin(BR_TYPES)
    df['is_off'] = df['pitch_type'].isin(OFF_TYPES)
    df['is_swing'] = df['description'].isin(SWINGS)
    df['is_whiff'] = df['description'].isin(WHIFFS)
    df['ivb_in'] = df['pfx_z'] * 12  # ft→in
    df['hb_in'] = df['pfx_x'] * 12
    # VAA: degrees. approx via release_pos_z & plate_z & extension.
    distance = (60.5 - df['release_extension']).clip(lower=30, upper=60)
    df['vaa'] = np.degrees(np.arctan((df['plate_z'] - df['release_pos_z']) / distance))

    # Overall agg
    agg = df.groupby('pitcher').agg(
        n_pitches=('release_speed', 'size'),
        velo_all=('release_speed', 'mean'),
        velo_std_all=('release_speed', 'std'),
        ext_all=('release_extension', 'mean'),
        ivb_all=('ivb_in', 'mean'),
        hb_all=('hb_in', 'mean'),
        spin_all=('release_spin_rate', 'mean'),
        release_x_all=('release_pos_x', 'mean'),
        release_x_std=('release_pos_x', 'std'),
        release_z_all=('release_pos_z', 'mean'),
        vaa_all=('vaa', 'mean'),
        n_swings=('is_swing', 'sum'),
        n_whiffs=('is_whiff', 'sum'),
    )
    agg['whiff_per_swing'] = agg['n_whiffs'] / agg['n_swings'].replace(0, np.nan) * 100

    # Per-pitch-type FB metrics
    fb = df[df['is_fb']]
    if not fb.empty:
        fb_agg = fb.groupby('pitcher').agg(
            n_fb=('release_speed', 'size'),
            velo_fb=('release_speed', 'mean'),
            ivb_fb=('ivb_in', 'mean'),
            hb_fb=('hb_in', 'mean'),
            ext_fb=('release_extension', 'mean'),
            spin_fb=('release_spin_rate', 'mean'),
            vaa_fb=('vaa', 'mean'),
            n_swings_fb=('is_swing', 'sum'),
            n_whiffs_fb=('is_whiff', 'sum'),
        )
        fb_agg['whiff_fb'] = fb_agg['n_whiffs_fb'] / fb_agg['n_swings_fb'].replace(0, np.nan) * 100
        agg = agg.join(fb_agg[['velo_fb', 'ivb_fb', 'hb_fb', 'ext_fb',
                                'spin_fb', 'vaa_fb', 'whiff_fb', 'n_fb']], how='left')

    # Per-pitch-type BR metrics
    br = df[df['is_br']]
    if not br.empty:
        br_agg = br.groupby('pitcher').agg(
            n_br=('release_speed', 'size'),
            velo_br=('release_speed', 'mean'),
            ivb_br=('ivb_in', 'mean'),
            spin_br=('release_spin_rate', 'mean'),
            n_swings_br=('is_swing', 'sum'),
            n_whiffs_br=('is_whiff', 'sum'),
        )
        br_agg['whiff_br'] = br_agg['n_whiffs_br'] / br_agg['n_swings_br'].replace(0, np.nan) * 100
        agg = agg.join(br_agg[['velo_br', 'ivb_br', 'spin_br', 'whiff_br', 'n_br']], how='left')

    # Usage mix
    if 'n_fb' in agg.columns:
        agg['fb_usage'] = agg['n_fb'] / agg['n_pitches'] * 100
    if 'n_br' in agg.columns:
        agg['br_usage'] = agg['n_br'] / agg['n_pitches'] * 100

    # Within-game velocity decline (Sheehan-specific)
    # First 25 pitches per game vs pitches 60+ per game; avg across games.
    if 'pitch_number' in df.columns and 'game_pk' in df.columns and df['is_fb'].any():
        fb_pitches = df[df['is_fb']].copy()
        fb_pitches['stage'] = pd.cut(fb_pitches['pitch_number'],
                                       bins=[0, 25, 60, 200], labels=['early','mid','late'])
        by_stage = fb_pitches.groupby(['pitcher', 'stage'], observed=True)['release_speed'].mean().unstack('stage')
        if 'early' in by_stage.columns and 'late' in by_stage.columns:
            by_stage['in_game_velo_decline'] = by_stage['early'] - by_stage['late']
            agg = agg.join(by_stage[['in_game_velo_decline']], how='left')

    return agg.reset_index()


def main():
    print('Loading statcast per year...')
    year_data = {}
    for y in YEARS:
        print(f'  {y}...')
        df = load_year(y)
        feats = compute_pitcher_features(df)
        feats['year'] = y
        year_data[y] = feats

    all_feats = pd.concat([d for d in year_data.values() if not d.empty], ignore_index=True)
    print(f'  total feature rows: {len(all_feats)}')

    # Career baseline = prior 2-3 years for each (pitcher, year)
    sp = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    fp_lookup = {}
    for _, r in sp[sp['gs'] >= 5].iterrows():
        fp_lookup[(int(r['pitcher']), int(r['year']))] = (int(r['gs']), float(r.get('fp_per_start_actual', 0)))

    feat_by_pid_year = {(int(r['pitcher']), int(r['year'])): r for _, r in all_feats.iterrows()}

    metric_cols = ['velo_all', 'ext_all', 'ivb_all', 'hb_all', 'spin_all',
                    'vaa_all', 'velo_std_all', 'release_x_std',
                    'whiff_per_swing',
                    'velo_fb', 'ivb_fb', 'hb_fb', 'ext_fb', 'spin_fb',
                    'vaa_fb', 'whiff_fb', 'fb_usage',
                    'velo_br', 'ivb_br', 'whiff_br', 'br_usage',
                    'in_game_velo_decline']

    rows = []
    for (pid, year), (gs, fp) in fp_lookup.items():
        if year not in YEARS: continue
        if gs < 10: continue
        # career baseline
        baseline_rows = []
        prior_weights = []
        for off in [1, 2, 3]:
            py = year - off
            if py in YEARS and (pid, py) in feat_by_pid_year:
                baseline_rows.append(feat_by_pid_year[(pid, py)])
                prior_weights.append(feat_by_pid_year[(pid, py)].get('n_pitches', 0))
        if not baseline_rows: continue
        if sum(prior_weights) < 500: continue
        cur = feat_by_pid_year.get((pid, year))
        if cur is None: continue
        # prior fp/start
        prior_fp = None
        for off in [1, 2, 3]:
            py = year - off
            if (pid, py) in fp_lookup and fp_lookup[(pid, py)][0] >= 5:
                prior_fp = fp_lookup[(pid, py)][1]
                break
        if prior_fp is None: continue

        row = {'pitcher': pid, 'year': year, 'fp_per_start': fp,
               'prior_fp_per_start': prior_fp}
        # Compute deltas
        for c in metric_cols:
            if c not in cur or pd.isna(cur.get(c)): continue
            # weighted baseline
            vals = [b.get(c) for b in baseline_rows]
            valid = [(v, w) for v, w in zip(vals, prior_weights) if pd.notna(v)]
            if not valid: continue
            base = sum(v*w for v,w in valid) / sum(w for _,w in valid)
            row[f'd_{c}'] = cur[c] - base
        rows.append(row)

    panel = pd.DataFrame(rows)
    print(f'\nPanel: {len(panel)} SP-years')

    def fit_eval(features, label):
        # Skip features that don't exist in the panel
        features = [f for f in features if f in panel.columns]
        if not features and label != 'baseline (prior_fp only)':
            return None, None, 0
        sub = panel.dropna(subset=features + ['fp_per_start', 'prior_fp_per_start'])
        if len(sub) < 100:
            return None, None, len(sub)
        train = sub[sub['year'].isin(TRAIN)]
        test = sub[sub['year'].isin(TEST)]
        if len(train) < 50 or len(test) < 30:
            return None, None, len(sub)
        X = np.column_stack([np.ones(len(train)), train['prior_fp_per_start'].values]
                              + [train[c].values for c in features])
        y = train['fp_per_start'].values
        coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
        Xt = np.column_stack([np.ones(len(test)), test['prior_fp_per_start'].values]
                                + [test[c].values for c in features])
        pred = Xt @ coefs
        r = float(np.corrcoef(pred, test['fp_per_start'].values)[0,1])
        return r, dict(zip(['α','prior_fp']+features, coefs)), len(test)

    print('\n' + '='*80)
    print('  PROGRESSIVE FEATURE SWEEP — pitch-shape predictors')
    print('='*80)

    baseline_feats = []
    r_base, _, n_test = fit_eval(baseline_feats, 'baseline (prior_fp only)')
    print(f'\n  baseline (prior_fp only):                          r = {r_base:.4f}  (n={n_test})')

    # Level 1 features (already validated)
    L1 = ['d_velo_all', 'd_ext_all', 'd_ivb_all']
    r_l1, _, _ = fit_eval(L1, 'L1')
    print(f'\n  L1 (velo/ext/iVB overall):                         r = {r_l1:.4f}  Δ={r_l1-r_base:+.4f}')

    # Level 2 additions: tested one-at-a-time over L1
    print(f'\n  Level 2 — single-feature ADDITIONS over L1:')
    L2_candidates = ['d_hb_all', 'd_spin_all', 'd_vaa_all',
                      'd_velo_std_all', 'd_release_x_std',
                      'd_whiff_per_swing', 'd_velo_fb', 'd_ivb_fb',
                      'd_spin_fb', 'd_vaa_fb', 'd_whiff_fb',
                      'd_velo_br', 'd_ivb_br', 'd_whiff_br',
                      'd_fb_usage', 'd_br_usage',
                      'd_in_game_velo_decline']
    L2_results = []
    for f in L2_candidates:
        r, _, n = fit_eval(L1 + [f], f)
        if r is not None:
            gain = r - r_l1
            mark = '★' if gain >= 0.005 else (' ' if gain >= 0 else '↓')
            print(f'    {mark} L1 + {f:<28s} → r = {r:.4f}  Δ={gain:+.4f}  (n={n})')
            L2_results.append((f, r, gain, n))

    # Now build a "best-of" combined model: L1 + all features with gain ≥ 0.005
    winners = [f for f, r, g, n in L2_results if g >= 0.005]
    if winners:
        all_feats = L1 + winners
        r_combined, coefs, n = fit_eval(all_feats, 'L1 + winners')
        print(f'\n  L1 + all level-2 winners ({len(winners)} feats):    r = {r_combined:.4f}')
        print(f'    gain over L1: {r_combined-r_l1:+.4f}')
        print(f'    gain over baseline: {r_combined-r_base:+.4f}')
        if coefs:
            print(f'\n  Final combined coefficients:')
            for name, c in coefs.items():
                print(f'    {name:<30s} {c:+.5f}')

    # Save panel for further use
    panel.to_csv(RES / 'pitch_shape_deep_panel.csv', index=False)
    print(f'\nwrote {RES / "pitch_shape_deep_panel.csv"}')


if __name__ == '__main__':
    main()
