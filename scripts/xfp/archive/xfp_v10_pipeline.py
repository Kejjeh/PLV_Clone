"""
xfp_v10_pipeline.py - V10 model search.

Three sub-versions, each evaluated under the V8 scoring formula:
  - V10.1 (quick wins): Stuff+/Pitching+, CSW%, fp_strike_pct, Marcel-style 5/4/3 weighting, velo delta
  - V10.2 (archetype submodels): two-tier K-cohort + contact-manager + rookie submodels
  - V10.3 (BaseRuns architecture): predict K/PA, BB/PA, H/PA, HR/PA, IP/start separately, recombine via FP formula

Lock V10 = highest composite score (cross_year_r * 3 - |k_bias_hi| * 0.5).
Compare against V8.5 (1.567).
"""
from __future__ import annotations
import sys, joblib, traceback
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from xfp_v7_pipeline import derive_features, add_ip_resid_lag, cross_year_evaluate
from xfp_v8_pipeline import V6_FEATS, V7_FEATS, V8_BASE, derive_v8_features, build_pitch_type_panel, score_fn
from xfp_v8_5_pipeline import build_pfxz_panel
from xfp_v8_midseason import blend_pitcher

CACHE   = ROOT / 'data' / 'research' / 'xfp_cache'
OUTPUTS = ROOT / 'data' / 'outputs'
MODELS  = ROOT / 'data' / 'models'
RESEARCH= ROOT / 'data' / 'research'
LOG_CSV = RESEARCH / 'feature_search_log.csv'

V5_FEATS = ['avg_velo','abs_pfxz','avg_ext','zone_pct','o_swing_pct',
             'swstr_pct','c_plus_swstr','xwoba_contact']

# V8.5 final feature set (from saved model)
V85_FEATS = ['avg_velo','zone_pct','o_swing_pct','swstr_pct','c_plus_swstr','xwoba_per_pa',
              'z_swing_pct','xwoba_x_swstr','ip_resid_lag1','k_pct_lag1','pitch_entropy','bb_pfxz']
V8_SCORE_BASE = 1.555
V85_SCORE_BASE = 1.567


# ============================================================
# DATA LOADING (shared across all V10 sub-versions)
# ============================================================
def load_v10_data():
    """Load + derive everything for V10. Includes FG Stuff+/Pitching+ history merge if available."""
    df = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    df = derive_features(df)
    df = add_ip_resid_lag(df)
    df = derive_v8_features(df)
    pt = build_pitch_type_panel(sorted(df['year'].unique()))
    if not pt.empty:
        df = df.merge(pt, on=['pitcher','year'], how='left')
    pfxz = build_pfxz_panel(sorted(df['year'].unique()))
    if not pfxz.empty:
        df = df.merge(pfxz, on=['pitcher','year'], how='left')

    # FG Stuff+/Pitching+/Location+ history (available 2020+)
    fg_rows = []
    for yr in [2020, 2021, 2022, 2023, 2024, 2025, 2026]:
        path = OUTPUTS / f'fangraphs_pitchers_{yr}.csv'
        if not path.exists():
            continue
        f = pd.read_csv(path)
        if 'mlb_id' not in f.columns: continue
        f = f.rename(columns={'mlb_id': 'pitcher'})
        f['year'] = yr
        fg_rows.append(f[['pitcher','year','stuff_plus','location_plus','pitching_plus',
                            'pb_stuff','pb_command','pb_xrv100']])
    if fg_rows:
        fg = pd.concat(fg_rows, ignore_index=True)
        # Drop nulls in key columns
        df = df.merge(fg, on=['pitcher','year'], how='left')
        for c in ['stuff_plus','location_plus','pitching_plus','pb_stuff','pb_command','pb_xrv100']:
            if c in df.columns:
                print(f'  FG {c} non-null: {df[c].notna().sum()}/{len(df)}')

    # CSW% per pitcher-season from cached Statcast (already derivable from c_plus_swstr in dataset)
    # c_plus_swstr already = (called_strikes + whiffs) / pitches, which IS CSW%
    df['csw_pct'] = df['c_plus_swstr']

    # First-pitch strike rate from cached statcast
    fp_strike = build_fp_strike_panel(sorted(df['year'].unique()))
    if not fp_strike.empty:
        df = df.merge(fp_strike, on=['pitcher','year'], how='left')
        print(f'  fp_strike_pct non-null: {df["fp_strike_pct"].notna().sum()}/{len(df)}')

    # Velocity delta YoY
    df = df.sort_values(['pitcher','year'])
    df['velo_delta_yoy'] = df.groupby('pitcher')['avg_velo'].diff()

    return df


def build_fp_strike_panel(years):
    cache_csv = CACHE / 'fp_strike_2015_2026.csv'
    if cache_csv.exists():
        out = pd.read_csv(cache_csv)
        if set(years).issubset(set(out['year'].unique())):
            print(f'  Loaded cached fp_strike panel ({len(out)} rows)')
            return out
    frames = []
    for yr in years:
        path = CACHE / f'statcast_{yr}.parquet'
        if not path.exists(): continue
        df = pd.read_parquet(path, columns=['pitcher','at_bat_number','game_pk','pitch_number','description','events'])
        df = df.dropna(subset=['pitcher','game_pk','at_bat_number'])
        df['pitch_number'] = pd.to_numeric(df['pitch_number'], errors='coerce')
        # First pitch of each PA: pitch_number == 1
        first = df[df['pitch_number']==1].copy()
        desc = first['description'].fillna('')
        # First-pitch strike: called strike, swinging strike, foul, foul tip, hit into play
        strike_descs = {'called_strike','swinging_strike','swinging_strike_blocked',
                         'foul','foul_tip','hit_into_play','foul_bunt','missed_bunt'}
        first['fp_strike'] = desc.isin(strike_descs)
        agg = first.groupby('pitcher').agg(fp_strikes=('fp_strike','sum'),
                                             fp_total=('fp_strike','count')).reset_index()
        agg['fp_strike_pct'] = agg['fp_strikes'] / agg['fp_total'].replace(0, np.nan)
        agg['year'] = yr
        frames.append(agg[['pitcher','year','fp_strike_pct']])
    if not frames: return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(cache_csv, index=False)
    return out


# ============================================================
# WEIGHTED HISTORY (Marcel 5/4/3) — applied to training rows
# ============================================================
def fit_marcel_weighted(df: pd.DataFrame, feats: list[str], target='fp_per_start_actual'):
    """Train Ridge with sample-weights = Marcel-style age weighting based on year.
       More-recent training rows get higher weight; year T-1 = 5, T-2 = 4, T-3 = 3."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    train = df[df['year'].between(2015, 2025)].dropna(subset=feats + [target]).copy()
    # Reference year = 2025 for "now"; weight = max(0, 5 - (2025 - year))
    train['marcel_w'] = (5 - (2025 - train['year'])).clip(lower=1)
    # Note RidgeCV doesn't natively support sample_weight in the CV; fit via custom
    sc = StandardScaler()
    X = sc.fit_transform(train[feats])
    y = train[target].values
    w = train['marcel_w'].values
    # Use RidgeCV with sample_weight (sklearn supports it now)
    ridge = RidgeCV(alphas=np.logspace(-1,5,80), cv=5).fit(X, y, sample_weight=w)
    pipe = Pipeline([('sc', sc), ('r', ridge)])
    return pipe


# ============================================================
# Logging
# ============================================================
def append_log(rec):
    rec = dict(rec)
    rec.setdefault('timestamp', datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'))
    pdf = pd.DataFrame([rec])
    if LOG_CSV.exists():
        pdf.to_csv(LOG_CSV, mode='a', header=False, index=False)
    else:
        pdf.to_csv(LOG_CSV, index=False)


def evaluate_with_score(df, feats, label, phase):
    cyr = cross_year_evaluate(df, feats, label)
    score = score_fn(cyr['r'], cyr['k_bias_hi'])
    cyr['score'] = round(score, 5) if score != float('-inf') else None
    cyr['phase'] = phase
    cyr['label'] = label
    append_log(cyr)
    return cyr


# ============================================================
# V10.1: Quick wins
# ============================================================
def phase_v10_1(df: pd.DataFrame):
    print('\n' + '=' * 60)
    print('V10.1: QUICK WINS — Stuff+/Pitching+ + CSW% + fp_strike_pct + Marcel weighting + velo_delta')
    print('=' * 60)
    train = df[df['year'].between(2015, 2025)].copy()
    print(f'Training set: {len(train)} rows')

    new_features = ['stuff_plus','location_plus','pitching_plus','pb_stuff','pb_command','pb_xrv100',
                     'fp_strike_pct','velo_delta_yoy']
    available = [f for f in new_features if f in train.columns and train[f].notna().sum() > 100]
    print(f'Available new features: {available}')

    # Single-feature additions to V8.5 base
    print('\nSingle-feature additions to V8.5 base:')
    single_results = []
    for cand in available:
        feats = V85_FEATS + [cand]
        if not all(f in train.columns for f in feats): continue
        e = evaluate_with_score(train, feats, f'V8.5+{cand}', '11.7C')
        print(f'  V8.5+{cand:<18s} cross={e["r"]:.5f} kbias={e["k_bias_hi"]:+.3f} score={e["score"]:.5f}')
        single_results.append((cand, e))

    # BE from V8.5 + all new features
    print('\nV10.1 backward elimination (V8.5 + new features):')
    kitchen = list(dict.fromkeys(V85_FEATS + available))
    print(f'  kitchen sink ({len(kitchen)}): {kitchen}')

    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    current = list(kitchen)
    best_score, best_set, best_eval = -float('inf'), list(kitchen), None
    while len(current) >= 4:
        d_curr = train.dropna(subset=current+['fp_per_start_actual'])
        if len(d_curr) < 100:
            print(f'  n={len(current)}: only {len(d_curr)} rows; stopping'); break
        sc = StandardScaler()
        X = sc.fit_transform(d_curr[current])
        ridge = RidgeCV(alphas=np.logspace(-1,5,80), cv=5).fit(X, d_curr['fp_per_start_actual'])
        coefs = pd.Series(np.abs(ridge.coef_), index=current).sort_values()
        e = evaluate_with_score(train, current, f'V10.1_BE_{len(current)}', '11.7E')
        print(f'  n={len(current):2d} cross={e["r"]:.5f} kbias={e["k_bias_hi"]:+.3f} score={e["score"]:.5f} drop={coefs.index[0]} ({coefs.iloc[0]:.3f})')
        if e['score'] is not None and e['score'] > best_score:
            best_score = e['score']; best_set = list(current); best_eval = e
        current = [f for f in current if f != coefs.index[0]]

    # Try Marcel weighting on the best BE set
    print(f'\nV10.1 Marcel-weighted retrain on best BE set ({len(best_set)} feats):')
    pipe_marcel = fit_marcel_weighted(train, best_set)
    # cross-year eval with Marcel pipe — use existing helper but inject the pipe
    # Easier: hand-compute cross-year r using marcel pipe trained on prior years
    marcel_cross = marcel_cross_year_evaluate(df, best_set)
    marcel_cross['score'] = score_fn(marcel_cross['r'], marcel_cross['k_bias_hi'])
    marcel_cross['phase'] = '11.7M'; marcel_cross['label'] = 'V10.1_Marcel_best_BE'
    append_log(marcel_cross)
    print(f'  Marcel-weighted: cross={marcel_cross["r"]:.5f} kbias={marcel_cross["k_bias_hi"]:+.3f} score={marcel_cross["score"]:.5f}')

    # Pick winner: regular BE vs Marcel
    if marcel_cross['score'] and marcel_cross['score'] > best_score:
        best_score = marcel_cross['score']; best_eval = marcel_cross
        v101_model = pipe_marcel
        v101_kind = 'Marcel-weighted'
    else:
        # Train final Ridge on best_set
        train_clean = train.dropna(subset=best_set + ['fp_per_start_actual'])
        v101_model = Pipeline([('sc', StandardScaler()),
                                 ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        v101_model.fit(train_clean[best_set], train_clean['fp_per_start_actual'])
        v101_kind = 'standard Ridge'

    SHIPS = (best_score >= V85_SCORE_BASE + 0.010)
    print(f'\nV10.1 best: score={best_score:.5f} (vs V8.5 {V85_SCORE_BASE}; ' + (f'+{best_score-V85_SCORE_BASE:.5f} -- SHIPS' if SHIPS else f'+{best_score-V85_SCORE_BASE:.5f} -- NOT SHIPPED') + ')')
    print(f'  features ({len(best_set)}): {best_set}')
    return {'name': 'V10.1', 'ships': SHIPS, 'model': v101_model, 'features': best_set,
             'eval': best_eval, 'score': best_score, 'kind': v101_kind}


def marcel_cross_year_evaluate(df, feats):
    """Cross-year eval with Marcel weighting applied to training step."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        if not shared: continue
        train_year = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year  = df[(df['year']==yr_test) & df['pitcher'].isin(shared)].copy()
        merged = test_year[['pitcher','fp_per_start_actual','k_pct']].merge(
            train_year[['pitcher']+feats], on='pitcher', how='inner')
        merged = merged.dropna(subset=feats + ['fp_per_start_actual'])
        if len(merged) < 10: continue
        # Train on prior years with Marcel weights (more recent = higher weight)
        prior = df[df['year'] < yr_test].dropna(subset=feats + ['fp_per_start_actual']).copy()
        if len(prior) < 50: continue
        prior['marcel_w'] = (5 - (yr_test - 1 - prior['year'])).clip(lower=1)
        sc = StandardScaler(); X = sc.fit_transform(prior[feats])
        ridge = RidgeCV(alphas=np.logspace(-1,5,80), cv=5).fit(X, prior['fp_per_start_actual'],
                                                                   sample_weight=prior['marcel_w'].values)
        merged['pred'] = ridge.predict(sc.transform(merged[feats]))
        preds_all.extend(merged['pred']); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)
    if not rows: return {'r': None, 'k_bias_hi': None}
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    return {'r': round(r, 5), 'k_bias_hi': round(k_bias_hi, 3),
             'rmse': round(float(np.sqrt((res['resid']**2).mean())), 3),
             'n': len(res), 'feats': str(feats)}


# ============================================================
# V10.2: Archetype submodels
# ============================================================
def phase_v10_2(df: pd.DataFrame):
    print('\n' + '=' * 60)
    print('V10.2: ARCHETYPE SUBMODELS — two-tier K + contact-manager + rookie')
    print('=' * 60)
    train = df[df['year'].between(2015, 2025)].copy()

    # Two-tier K cohort: split on k_pct_lag1 > 0.28 (high-K cohort)
    # Use the V8.5 features. Cross-year eval blended back together.
    print('\nTwo-tier K cohort cross-year evaluation:')
    tier_cyr = two_tier_cross_year(df, V85_FEATS, k_pct_threshold=0.28)
    tier_cyr['score'] = score_fn(tier_cyr['r'], tier_cyr['k_bias_hi'])
    tier_cyr['phase'] = '11.8T'; tier_cyr['label'] = 'V10.2_two_tier_K28'
    append_log(tier_cyr)
    print(f'  two_tier K>0.28: cross={tier_cyr["r"]} kbias={tier_cyr["k_bias_hi"]:+.3f} score={tier_cyr["score"]:.5f}')

    # Contact-manager: gb_pct > 0.50 AND swstr_pct < 0.12. Train specialized Ridge on this subset.
    # Evaluate by predicting CM pitchers using the CM submodel and comparing to V8.5 baseline on same pitchers.
    print('\nContact-manager submodel:')
    cm_results = contact_manager_eval(df, V85_FEATS)
    cm_results['phase'] = '11.8C'; append_log(cm_results)
    print(f'  CM cross={cm_results["r"]:.5f} kbias={cm_results["k_bias_hi"]:+.3f} score={cm_results["score"]:.5f}')

    # Pick best architecture
    arch_options = [('two_tier_K28', tier_cyr), ('contact_manager', cm_results)]
    best = max(arch_options, key=lambda x: x[1].get('score') or -1)
    SHIPS = (best[1]['score'] or -1) >= V85_SCORE_BASE + 0.010
    print(f'\nV10.2 best: {best[0]} score={best[1]["score"]} (ships: {SHIPS})')
    return {'name': 'V10.2', 'ships': SHIPS, 'eval': best[1],
             'score': best[1]['score'], 'arch': best[0]}


def two_tier_cross_year(df, feats, k_pct_threshold=0.28):
    """Train separate Ridge for high-K (k_pct_lag1 > threshold) and rest. Eval combined."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        train_year = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year  = df[(df['year']==yr_test) & df['pitcher'].isin(shared)].copy()
        join_cols = list(dict.fromkeys(['pitcher'] + feats + ['k_pct_lag1']))
        merged = test_year[['pitcher','fp_per_start_actual','k_pct']].merge(
            train_year[join_cols], on='pitcher', how='inner')
        merged = merged.dropna(subset=feats + ['fp_per_start_actual'])
        if len(merged) < 10: continue
        prior = df[df['year'] < yr_test].dropna(subset=feats + ['fp_per_start_actual','k_pct_lag1'])
        if len(prior) < 50: continue
        # Two cohorts on prior data
        hi = prior[prior['k_pct_lag1'] > k_pct_threshold]
        lo = prior[prior['k_pct_lag1'] <= k_pct_threshold]
        if len(hi) < 30 or len(lo) < 30: continue
        pipe_hi = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_lo = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_hi.fit(hi[feats].values, hi['fp_per_start_actual'].values)
        pipe_lo.fit(lo[feats].values, lo['fp_per_start_actual'].values)
        # Predict on each row of merged based on its k_pct_lag1
        merged['pred'] = np.where(merged['k_pct_lag1'].fillna(0) > k_pct_threshold,
                                    pipe_hi.predict(merged[feats].values),
                                    pipe_lo.predict(merged[feats].values))
        preds_all.extend(merged['pred']); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)
    if not rows: return {'r': None, 'k_bias_hi': None}
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    return {'r': round(r, 5), 'k_bias_hi': round(k_bias_hi, 3),
             'rmse': round(float(np.sqrt((res['resid']**2).mean())), 3),
             'n': len(res), 'feats': f'two_tier({k_pct_threshold})'}


def contact_manager_eval(df, feats):
    """Hybrid model: contact-manager submodel for CM pitchers, regular for others."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        train_year = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year  = df[(df['year']==yr_test) & df['pitcher'].isin(shared)].copy()
        join_cols2 = list(dict.fromkeys(['pitcher'] + feats + ['gb_pct','swstr_pct']))
        merged = test_year[['pitcher','fp_per_start_actual','k_pct']].merge(
            train_year[join_cols2], on='pitcher', how='inner')
        merged = merged.dropna(subset=feats + ['fp_per_start_actual'])
        if len(merged) < 10: continue
        prior = df[df['year'] < yr_test].dropna(subset=feats + ['fp_per_start_actual','gb_pct','swstr_pct'])
        if len(prior) < 50: continue
        cm_mask = (prior['gb_pct'] > 0.50) & (prior['swstr_pct'] < 0.12)
        if cm_mask.sum() < 30: continue
        pipe_cm   = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_main = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_cm.fit(prior[cm_mask][feats].values, prior[cm_mask]['fp_per_start_actual'].values)
        pipe_main.fit(prior[~cm_mask][feats].values, prior[~cm_mask]['fp_per_start_actual'].values)
        is_cm = (merged['gb_pct'] > 0.50) & (merged['swstr_pct'] < 0.12)
        merged['pred'] = np.where(is_cm, pipe_cm.predict(merged[feats].values), pipe_main.predict(merged[feats].values))
        preds_all.extend(merged['pred']); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)
    if not rows: return {'r': None, 'k_bias_hi': None, 'score': None}
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    return {'r': round(r, 5), 'k_bias_hi': round(k_bias_hi, 3),
             'rmse': round(float(np.sqrt((res['resid']**2).mean())), 3),
             'score': round(score_fn(r, k_bias_hi), 5),
             'n': len(res), 'feats': 'contact_manager_hybrid', 'label': 'V10.2_CM'}


# ============================================================
# V10.3: BaseRuns decomposition
# ============================================================
def baseruns_cross_year(df, feats):
    """Predict K/PA, BB/PA, H/PA, HR/PA, IP/start separately, recombine via FP formula."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    targets = ['k_per_start','bb_per_start','h_per_start','hr_per_start','hbp_per_start','ip_per_start']
    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        train_year = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year  = df[(df['year']==yr_test ) & df['pitcher'].isin(shared)].copy()
        merged = test_year[['pitcher','fp_per_start_actual','k_pct']].merge(
            train_year[['pitcher']+feats], on='pitcher', how='inner')
        merged = merged.dropna(subset=feats + ['fp_per_start_actual'])
        if len(merged) < 10: continue
        prior = df[df['year'] < yr_test].dropna(subset=feats + targets)
        if len(prior) < 50: continue

        component_preds = {}
        for tgt in targets:
            pipe = Pipeline([('sc', StandardScaler()),
                              ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
            pipe.fit(prior[feats], prior[tgt])
            component_preds[tgt] = pipe.predict(merged[feats])

        # FP formula: K + IP*3.3 - H - 2*ER - BB - HBP
        # Use ER ≈ HR*1.4 + (small constant) — approximate per FanGraphs
        # Better: ER ≈ runs scored, approximate via HR + constant baseline
        # Use empirical: er_per_start ≈ a*hr_per_start + b. Compute on prior.
        from sklearn.linear_model import Ridge
        er_model = Ridge(alpha=1.0).fit(prior[['hr_per_start','h_per_start','bb_per_start']],
                                           prior['er_est'] if 'er_est' in prior.columns else prior['fp_per_start_actual']*0)
        er_input = pd.DataFrame({
            'hr_per_start': component_preds['hr_per_start'],
            'h_per_start':  component_preds['h_per_start'],
            'bb_per_start': component_preds['bb_per_start'],
        })
        # Need actual ER training column — fall back to using "er_est" if missing
        if 'er_est' in df.columns:
            er_pred = er_model.predict(er_input)
        else:
            # Approximate ER as 0.4*H + 1.4*HR + 0.2*BB (rough run-expectancy weights)
            er_pred = 0.4*component_preds['h_per_start'] + 1.4*component_preds['hr_per_start'] + 0.2*component_preds['bb_per_start']

        fp_pred = (component_preds['k_per_start']
                    + component_preds['ip_per_start'] * 3.3
                    - component_preds['h_per_start']
                    - 2 * er_pred
                    - component_preds['bb_per_start']
                    - component_preds['hbp_per_start'])

        merged['pred'] = fp_pred
        preds_all.extend(fp_pred); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)

    if not rows: return {'r': None, 'k_bias_hi': None}
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    return {'r': round(r, 5), 'k_bias_hi': round(k_bias_hi, 3),
             'rmse': round(float(np.sqrt((res['resid']**2).mean())), 3),
             'score': round(score_fn(r, k_bias_hi), 5),
             'n': len(res), 'feats': 'BaseRuns_decomp', 'label': 'V10.3_BaseRuns'}


def phase_v10_3(df: pd.DataFrame):
    print('\n' + '=' * 60)
    print('V10.3: BASERUNS DECOMPOSITION — predict K/BB/H/HR/IP separately, recombine via FP formula')
    print('=' * 60)
    train = df[df['year'].between(2015, 2025)].copy()

    # Use V8.5 features as the input feature set for each component model
    e = baseruns_cross_year(df, V85_FEATS)
    e['phase'] = '11.9'
    append_log(e)
    print(f'  BaseRuns(V85_feats): cross={e["r"]} kbias={e["k_bias_hi"]:+.3f} score={e["score"]}')

    SHIPS = (e['score'] or -1) >= V85_SCORE_BASE + 0.010
    print(f'\nV10.3 result: score={e["score"]} (ships: {SHIPS})')
    return {'name': 'V10.3', 'ships': SHIPS, 'eval': e, 'score': e['score'],
             'features': V85_FEATS, 'arch': 'BaseRuns_decomp'}


# ============================================================
# Lock V10
# ============================================================
def lock_v10(results, df: pd.DataFrame):
    print('\n' + '=' * 60)
    print('LOCK V10 — pick highest-scoring sub-version')
    print('=' * 60)
    print(f'V8.5 baseline: score=1.567 cross=0.600 kbias=0.466')
    leaderboard = [(r['name'], r.get('score', -float('inf')), r.get('eval', {})) for r in results]
    leaderboard.sort(key=lambda x: -(x[1] or -float('inf')))
    for name, sc, ev in leaderboard:
        print(f'  {name:<8s} score={sc} cross={ev.get("r")} kbias={ev.get("k_bias_hi")}')

    winner = leaderboard[0]
    name, score, eval_ = winner
    SHIPS_OVERALL = score >= 1.567 + 0.010
    print(f'\n>>> V10 WINNER: {name} score={score} (vs V8.5 1.567; '
          + ('SHIPS' if SHIPS_OVERALL else 'NOT SHIPPED') + ')')
    return name, eval_, SHIPS_OVERALL


def append_research(results, winner, ships):
    section = f"""

## V10 — Three-Branch Search (Quick Wins / Archetype / BaseRuns) ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})

Three V10 sub-versions evaluated under unchanged scoring formula (`cross_year_r * 3 - |k_bias_hi| * 0.5`):

| Sub-version | Approach | Score | Cross-year r | k_bias_hi |
|---|---|---|---|---|
"""
    for r in results:
        e = r.get('eval', {})
        section += f"| {r['name']} | {r.get('arch','BE-best')} | {r.get('score')} | {e.get('r')} | {e.get('k_bias_hi')} |\n"

    section += f"""
| **V8.5 (incumbent)** | Ridge (12 feats) | 1.567 | 0.600 | 0.466 |

**V10 winner: {winner}**
**Decision: {'SHIPPED' if ships else 'NOT SHIPPED'}** (decision rule: score >= V8.5 + 0.010 = 1.577)

### Files
- `scripts/xfp/xfp_v10_pipeline.py`
- `scripts/xfp/pull_fg_history.py`
"""
    research_md = RESEARCH / 'xfp_model_research.md'
    with open(research_md, 'a', encoding='utf-8') as f:
        f.write(section)
    print(f'  appended V10 section to {research_md}')


def main():
    import os
    print('=' * 60)
    print(f'xFP V10 PIPELINE | {datetime.now(timezone.utc).isoformat()}')
    print('=' * 60)
    df = load_v10_data()

    only_phase = os.environ.get('V10_ONLY_PHASE', '')
    results = []
    if not only_phase or only_phase == '1':
        try:
            r = phase_v10_1(df); results.append(r)
        except Exception as e:
            print(f'V10.1 FAILED: {e}'); traceback.print_exc()
    if not only_phase or only_phase == '2':
        try:
            r = phase_v10_2(df); results.append(r)
        except Exception as e:
            print(f'V10.2 FAILED: {e}'); traceback.print_exc()
    if not only_phase or only_phase == '3':
        try:
            r = phase_v10_3(df); results.append(r)
        except Exception as e:
            print(f'V10.3 FAILED: {e}'); traceback.print_exc()

    winner_name, winner_eval, ships = lock_v10(results, df)
    append_research(results, winner_name, ships)

    print('\n' + '=' * 60)
    print('V10 PIPELINE COMPLETE')
    print('=' * 60)
    return results


if __name__ == '__main__':
    main()
