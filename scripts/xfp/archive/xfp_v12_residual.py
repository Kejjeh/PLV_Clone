"""
xfp_v12_residual.py - V12 residual-correction architecture.

V8.5 model stays frozen as the base predictor. A second Ridge model is fit on
(actual_FP - V8.5_pred) using FG Stuff+/Pitching+/pb_stuff/pb_command/pb_xrv100 features.
The residual model is heavily regularized to capture only the additional cross-year
signal in Stuff+ without re-introducing k_bias.

Final V12 prediction: xfp_v12 = V8.5_pred + residual_correction

Decision rule: ship if V12 score >= V8.5 (1.567) + 0.010 = 1.577.
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

V85_FEATS = ['avg_velo','zone_pct','o_swing_pct','swstr_pct','c_plus_swstr','xwoba_per_pa',
              'z_swing_pct','xwoba_x_swstr','ip_resid_lag1','k_pct_lag1','pitch_entropy','bb_pfxz']
FG_FEATS_ALL = ['stuff_plus','location_plus','pitching_plus','pb_stuff','pb_command','pb_xrv100']
V8_SCORE_BASE = 1.555
V85_SCORE_BASE = 1.567


def load_data():
    df = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    df = derive_features(df)
    df = add_ip_resid_lag(df)
    df = derive_v8_features(df)
    pt = build_pitch_type_panel(sorted(df['year'].unique()))
    if not pt.empty: df = df.merge(pt, on=['pitcher','year'], how='left')
    pfxz = build_pfxz_panel(sorted(df['year'].unique()))
    if not pfxz.empty: df = df.merge(pfxz, on=['pitcher','year'], how='left')

    # FG history
    fg_rows = []
    for yr in [2020, 2021, 2022, 2023, 2024, 2025, 2026]:
        path = OUTPUTS / f'fangraphs_pitchers_{yr}.csv'
        if not path.exists(): continue
        f = pd.read_csv(path).rename(columns={'mlb_id': 'pitcher'})
        f['year'] = yr
        fg_rows.append(f[['pitcher','year'] + FG_FEATS_ALL])
    if fg_rows:
        fg = pd.concat(fg_rows, ignore_index=True)
        df = df.merge(fg, on=['pitcher','year'], how='left')
    return df


def build_v85_predictions_cross_year(df: pd.DataFrame):
    """For each (pitcher, year T+1) row, compute V8.5 cross-year prediction = pred from year-T features.
       Returns df augmented with v85_pred column for years 2016..2025 (where lag features exist)."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    df = df.copy()
    df['v85_pred'] = np.nan

    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        # Use train_year features merged onto test_year row, predict test_year actual
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        if not shared: continue
        train_year_rows = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year_rows  = df[(df['year']==yr_test ) & df['pitcher'].isin(shared)]

        # Fit V8.5 on all prior data (years < yr_test)
        prior = df[df['year'] < yr_test].dropna(subset=V85_FEATS + ['fp_per_start_actual'])
        if len(prior) < 50: continue

        pipe = Pipeline([('sc', StandardScaler()),
                          ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe.fit(prior[V85_FEATS], prior['fp_per_start_actual'])

        # Predict using year-T (yr_train) features for the test_year pitchers
        # Merge: lookup yr_train features for each test_year pitcher
        merged = test_year_rows[['pitcher']].merge(
            train_year_rows[['pitcher'] + V85_FEATS], on='pitcher', how='inner').dropna(subset=V85_FEATS)
        if len(merged) == 0: continue
        merged['v85_pred'] = pipe.predict(merged[V85_FEATS])
        # Write back to df at the test_year rows
        for _, r in merged.iterrows():
            mask = (df['year']==yr_test) & (df['pitcher']==r['pitcher'])
            df.loc[mask, 'v85_pred'] = r['v85_pred']

    return df


def append_log(rec):
    rec = dict(rec)
    rec.setdefault('timestamp', datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'))
    pdf = pd.DataFrame([rec])
    if LOG_CSV.exists(): pdf.to_csv(LOG_CSV, mode='a', header=False, index=False)
    else: pdf.to_csv(LOG_CSV, index=False)


def cross_year_evaluate_v12(df: pd.DataFrame, fg_feats: list[str], alpha_floor: float = 10.0):
    """Cross-year eval of V12 = V8.5 + residual model on FG features.
    Trains V8.5 on prior years, computes residuals on prior years, fits residual model
    with high alpha (alpha_floor) on FG features for those prior-year residuals,
    applies V12 = V8.5_pred + residual_pred to test-year rows.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV, Ridge
    from sklearn.preprocessing import StandardScaler

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2020, 2025)]  # FG data starts 2020

    for yr_train, yr_test in transitions:
        # Pitchers in both years
        pt_train = set(df[df['year']==yr_train]['pitcher'])
        pt_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared   = pt_train & pt_test
        if not shared: continue
        ty = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        te = df[(df['year']==yr_test ) & df['pitcher'].isin(shared)].copy()
        merged = te[['pitcher','fp_per_start_actual','k_pct']].merge(
            ty[['pitcher'] + V85_FEATS + fg_feats], on='pitcher', how='inner')
        merged = merged.dropna(subset=V85_FEATS + fg_feats + ['fp_per_start_actual'])
        if len(merged) < 10: continue

        # Train V8.5 on all years < yr_test
        prior = df[df['year'] < yr_test].dropna(subset=V85_FEATS + ['fp_per_start_actual'])
        if len(prior) < 50: continue
        pipe85 = Pipeline([('sc', StandardScaler()),
                            ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe85.fit(prior[V85_FEATS], prior['fp_per_start_actual'])

        # Train residual model on prior cross-year transitions (T -> T+1) where FG data exists
        # For each prior transition, compute (actual_T+1 - V8.5_pred_at_T+1_using_T_feats)
        residuals_X, residuals_y = [], []
        for tt_train, tt_test in [(y, y+1) for y in range(2020, yr_test)]:
            tt_pt_tr = set(df[df['year']==tt_train]['pitcher'])
            tt_pt_te = set(df[df['year']==tt_test ]['pitcher'])
            tt_shared = tt_pt_tr & tt_pt_te
            if not tt_shared: continue
            tt_ty = df[(df['year']==tt_train) & df['pitcher'].isin(tt_shared)]
            tt_te = df[(df['year']==tt_test ) & df['pitcher'].isin(tt_shared)]
            tt_merged = tt_te[['pitcher','fp_per_start_actual']].merge(
                tt_ty[['pitcher'] + V85_FEATS + fg_feats], on='pitcher', how='inner').dropna(
                subset=V85_FEATS + fg_feats + ['fp_per_start_actual'])
            if len(tt_merged) == 0: continue
            tt_v85_pred = pipe85.predict(tt_merged[V85_FEATS])
            tt_resid = tt_merged['fp_per_start_actual'].values - tt_v85_pred
            residuals_X.append(tt_merged[fg_feats].values)
            residuals_y.append(tt_resid)

        if not residuals_X:
            # No prior FG data to fit residual model — fall back to V8.5 only
            v12_pred = pipe85.predict(merged[V85_FEATS])
        else:
            X = np.vstack(residuals_X)
            y = np.concatenate(residuals_y)
            sc_r = StandardScaler()
            X_sc = sc_r.fit_transform(X)
            # Heavy regularization: use Ridge with high alpha
            pipe_r = Ridge(alpha=alpha_floor).fit(X_sc, y)
            # V12 prediction = V8.5 + residual
            v85_test_pred = pipe85.predict(merged[V85_FEATS])
            X_test = sc_r.transform(merged[fg_feats].values)
            resid_test_pred = pipe_r.predict(X_test)
            v12_pred = v85_test_pred + resid_test_pred

        merged['pred_v12'] = v12_pred
        preds_all.extend(v12_pred); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)

    if not rows: return None
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred_v12']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    return {'r': round(r,5), 'k_bias_hi': round(k_bias_hi,3),
             'rmse': round(float(np.sqrt((res['resid']**2).mean())),3),
             'score': round(score_fn(r, k_bias_hi), 5),
             'n': len(res), 'feats': str(fg_feats), 'alpha': alpha_floor,
             'phase': '11.10', 'label': f'V12_residual_alpha{alpha_floor}'}


def cross_year_evaluate_v85_subset(df: pd.DataFrame, fg_feats: list[str]):
    """V8.5 cross-year r evaluated on the SAME pitcher subset as V12 (those with FG features), for fair comparison."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2020, 2025)]
    for yr_train, yr_test in transitions:
        pt_train = set(df[df['year']==yr_train]['pitcher'])
        pt_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pt_train & pt_test
        ty = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        te = df[(df['year']==yr_test ) & df['pitcher'].isin(shared)].copy()
        merged = te[['pitcher','fp_per_start_actual','k_pct']].merge(
            ty[['pitcher']+V85_FEATS+fg_feats], on='pitcher', how='inner').dropna(
            subset=V85_FEATS+fg_feats+['fp_per_start_actual'])
        if len(merged) < 10: continue
        prior = df[df['year']<yr_test].dropna(subset=V85_FEATS+['fp_per_start_actual'])
        if len(prior) < 50: continue
        pipe = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe.fit(prior[V85_FEATS], prior['fp_per_start_actual'])
        merged['pred'] = pipe.predict(merged[V85_FEATS])
        preds_all.extend(merged['pred']); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)
    if not rows: return None
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    return {'r': round(r,5), 'k_bias_hi': round(k_bias_hi,3),
             'rmse': round(float(np.sqrt((res['resid']**2).mean())),3),
             'score': round(score_fn(r, k_bias_hi), 5),
             'n': len(res), 'feats': 'V85_subset_2020_2024'}


def build_v12_dashboard_and_projections(df, residual_pipe, fg_feats_used, sc_residual,
                                          v85_eval, v12_eval, alpha_used):
    """Build 2026 V12 projections + dashboard."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    # Final V8.5 trained on full 2015-2025
    train_85 = df[df['year'].between(2015, 2025)].dropna(subset=V85_FEATS + ['fp_per_start_actual'])
    pipe_85 = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
    pipe_85.fit(train_85[V85_FEATS], train_85['fp_per_start_actual'])

    # Build 2026 blended inputs (mid-season blend logic)
    df_25 = df[df['year']==2025].set_index('pitcher')
    df_26 = df[df['year']==2026].set_index('pitcher')
    rows = []
    for p in sorted(set(df_25.index) | set(df_26.index)):
        r25 = df_25.loc[p].to_dict() if p in df_25.index else None
        r26 = df_26.loc[p].to_dict() if p in df_26.index else None
        if r25: r25 = pd.Series({**r25, 'pitcher':p})
        if r26: r26 = pd.Series({**r26, 'pitcher':p})
        b = blend_pitcher(r25, r26)
        if b is None: continue
        all_feats = list(set(V85_FEATS + fg_feats_used))
        for f in all_feats:
            if f in b: continue
            if r26 is not None and pd.notna(r26.get(f)):
                b[f] = float(r26.get(f))
            elif r25 is not None and pd.notna(r25.get(f)):
                b[f] = float(r25.get(f))
            else:
                b[f] = np.nan
        rows.append(b)
    blended = pd.DataFrame(rows)
    blended['xwoba_per_pa']  = blended['xwoba_contact'] * blended['bip_pct']
    blended['xwoba_x_swstr'] = blended['xwoba_contact'] * blended['swstr_pct']

    # Predict V8.5 (need all V85 feats present)
    v85_valid = blended.dropna(subset=V85_FEATS).copy()
    v85_valid['xfp_v8_5'] = pipe_85.predict(v85_valid[V85_FEATS])

    # Predict residual where FG feats present
    fg_valid = v85_valid.dropna(subset=fg_feats_used).copy()
    X = sc_residual.transform(fg_valid[fg_feats_used].values)
    fg_valid['residual_correction'] = residual_pipe.predict(X)
    fg_valid['xfp_v12'] = fg_valid['xfp_v8_5'] + fg_valid['residual_correction']

    # For pitchers without FG features, V12 = V8.5
    out = v85_valid.merge(fg_valid[['pitcher','xfp_v12','residual_correction']],
                           on='pitcher', how='left')
    out['xfp_v12'] = out['xfp_v12'].fillna(out['xfp_v8_5'])
    out['residual_correction'] = out['residual_correction'].fillna(0.0)

    # Merge with V8.5 dashboard projections for full context
    v85 = pd.read_csv(OUTPUTS / 'xfp_v8_5_projections.csv')
    cols_to_drop = [c for c in ['xfp_v8_5','xfp_v12','residual_correction'] if c in v85.columns]
    if cols_to_drop:
        v85 = v85.drop(columns=cols_to_drop)
    proj = out[['pitcher','player_name','xfp_v8_5','xfp_v12','residual_correction']].merge(
        v85[['pitcher','xfp_v8_1','xfp_v8','xfp_v7','xfp_v6','xfp_v5','gs_2026','fp_per_start_actual_2026','k_pct_2026',
              'stuff_xfp','ip_premium','ip_trend','rolling_ip_last5']],
        on='pitcher', how='left')
    proj['delta_v12_v85'] = proj['xfp_v12'] - proj['xfp_v8_5']

    proj.to_csv(OUTPUTS / 'xfp_v12_projections.csv', index=False)
    print(f'  wrote {OUTPUTS / "xfp_v12_projections.csv"}')

    # Save residual model + scaler
    joblib.dump({'v85_pipeline': pipe_85, 'v85_features': V85_FEATS,
                  'residual_pipeline': residual_pipe, 'residual_scaler': sc_residual,
                  'residual_features': fg_feats_used,
                  'alpha': alpha_used, 'metrics': v12_eval},
                 MODELS / 'xfp_v12_pipeline.pkl')
    print(f'  saved {MODELS / "xfp_v12_pipeline.pkl"}')

    # YTD evaluation
    ytd = proj[(proj['gs_2026'] >= 5) & proj['fp_per_start_actual_2026'].notna()
                & proj['xfp_v12'].notna() & proj['xfp_v8_5'].notna()].copy()
    r_v85 = float(np.corrcoef(ytd['xfp_v8_5'], ytd['fp_per_start_actual_2026'])[0,1]) if len(ytd) >= 10 else None
    r_v12 = float(np.corrcoef(ytd['xfp_v12'], ytd['fp_per_start_actual_2026'])[0,1]) if len(ytd) >= 10 else None
    print(f'  2026 YTD r: V8.5={r_v85:.5f}  V12={r_v12:.5f}  Δ={r_v12-r_v85:+.5f}')

    return proj, r_v85, r_v12


def build_dashboard(proj, v85_eval, v12_eval, alpha_used, fg_feats_used, r_v85_ytd, r_v12_ytd):
    proj_d = proj.sort_values('xfp_v12', ascending=False, na_position='last').reset_index(drop=True)
    proj_d['rank_v12'] = proj_d.index + 1
    proj_d['rank_v85'] = proj_d['xfp_v8_5'].rank(ascending=False, method='min')

    def fmt(x, p=2):
        try:
            f = float(x)
            if not np.isfinite(f): return '-'
            return f'{f:.{p}f}'
        except (TypeError, ValueError): return '-'

    def archetype_card(name):
        r = proj_d[proj_d['player_name'].fillna('').str.contains(name, na=False)]
        if not len(r): return f'<div class="card"><div class="cardh">{name}</div><div>not in set</div></div>'
        s = r.iloc[0]
        return (f'<div class="card"><div class="cardh">{s["player_name"]}</div>'
                f'<div class="kv"><span class="kv-k">V8.5 xFP</span><span class="kv-v">{fmt(s["xfp_v8_5"])}</span></div>'
                f'<div class="kv"><span class="kv-k">V12 xFP</span><span class="kv-v" style="color:#3fb950">{fmt(s["xfp_v12"])}</span></div>'
                f'<div class="kv"><span class="kv-k">residual</span><span class="kv-v">{s["residual_correction"]:+.2f}</span></div>'
                f'<div class="kv"><span class="kv-k">2026 actual</span><span class="kv-v">{fmt(s["fp_per_start_actual_2026"])}</span></div>'
                f'</div>')

    archetype_html = ''.join(archetype_card(n) for n in
        ['Schlittler','Glasnow','Imanaga','Fried','Wheeler','Skubal','Woodruff','Ragans'])

    # Top 80 main table
    main_rows = []
    for _, s in proj_d.head(80).iterrows():
        try: dv = float(s['delta_v12_v85']); dvc = 'up' if dv>0 else 'dn' if dv<0 else ''
        except: dvc=''; dv=0
        cls = 't1' if s['rank_v12']==1 else 't2' if s['rank_v12']==2 else 't3' if s['rank_v12']==3 else ''
        gold = ' style="color:#ffd700"' if 'Schlittler' in str(s['player_name']) else ''
        main_rows.append(
            f'<tr><td class="{cls}">{int(s["rank_v12"])}</td><td{gold}>{s["player_name"]}</td>'
            f'<td class="num">{fmt(s.get("xfp_v8"))}</td>'
            f'<td class="num">{fmt(s.get("xfp_v8_1"))}</td>'
            f'<td class="num">{fmt(s["xfp_v8_5"])}</td>'
            f'<td class="num"><b>{fmt(s["xfp_v12"])}</b></td>'
            f'<td class="num {dvc}">{dv:+.2f}</td>'
            f'<td class="num">{fmt(s.get("residual_correction"))}</td>'
            f'<td class="num">{fmt(s["gs_2026"],0)}</td>'
            f'<td class="num">{fmt(s["fp_per_start_actual_2026"])}</td></tr>')

    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>xFP v12 — Residual Correction</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#e6edf3;padding:18px}}
.hdr{{background:linear-gradient(135deg,#1a2332,#0d1b2a);border:1px solid #30363d;border-radius:8px;padding:14px 18px;margin-bottom:14px}}
.title{{font-size:20px;font-weight:700;color:#58a6ff}}.title span{{color:#f0883e}}
.sub{{font-size:11.5px;color:#8b949e;margin-top:4px;line-height:1.5}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px}}
.cardh{{font-size:11px;font-weight:700;text-transform:uppercase;color:#8b949e;letter-spacing:.7px;margin-bottom:9px}}
.banner{{background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.4);border-radius:8px;padding:12px 16px;margin-bottom:14px;font-size:12px}}
.grid8{{display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:10px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;padding:6px 6px;color:#8b949e;border-bottom:2px solid #21262d;font-weight:600}}
td{{padding:5px 6px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums}}
td.num{{text-align:right}}
.t1{{color:#ffd700;font-weight:700}}.t2{{color:#c0c0c0;font-weight:600}}.t3{{color:#cd7f32}}
.up{{color:#3fb950}}.dn{{color:#f85149}}
.kv{{display:flex;justify-content:space-between;padding:3px 0;font-size:11.5px}}
.kv-k{{color:#8b949e}}.kv-v{{font-weight:700}}
</style></head><body>
<div class="hdr">
<div class="title">xFP <span>v12</span> — Residual Correction</div>
<div class="sub">V8.5 frozen base + heavily-regularized Ridge (alpha={alpha_used}) on FG features ({", ".join(fg_feats_used)}).
Residual model fit on (actual_FP - V8.5_pred) over cross-year transitions 2020→2024.
V12 cross-year r = {v12_eval["r"]} (V8.5 same-subset = {v85_eval["r"]}).
V12 k_bias_hi = {v12_eval["k_bias_hi"]} (V8.5 same-subset = {v85_eval["k_bias_hi"]}).
2026 YTD r: V8.5={fmt(r_v85_ytd,5)} V12={fmt(r_v12_ytd,5)}.</div>
</div>

<div class="banner">
V12 score = {v12_eval["score"]} | V8.5 (same subset) score = {v85_eval["score"]} | Δ = {v12_eval["score"]-v85_eval["score"]:+.5f}
</div>

<div class="grid8">{archetype_html}</div>

<div class="card"><div class="cardh">Top 80 SP — V8 → V8.1 → V8.5 → V12 (Schlittler in gold)</div>
<table><thead><tr>
<th>Rk</th><th>Pitcher</th>
<th class="num">V8</th><th class="num">V8.1</th><th class="num">V8.5</th><th class="num">V12</th>
<th class="num">Δ vs V8.5</th><th class="num">resid corr</th>
<th class="num">2026 GS</th><th class="num">2026 actual</th>
</tr></thead><tbody>{''.join(main_rows)}</tbody></table></div>
</body></html>'''
    out = OUTPUTS / 'xfp_v12_dashboard.html'
    out.write_text(html, encoding='utf-8')
    print(f'  wrote {out}')


def main():
    print('=' * 60)
    print(f'xFP V12 RESIDUAL CORRECTION | {datetime.now(timezone.utc).isoformat()}')
    print('=' * 60)
    df = load_data()
    print(f'Data: {len(df)} rows; FG-non-null pitching_plus: {df["pitching_plus"].notna().sum()}')

    # ===== STEP 1: V8.5 baseline (same subset as V12 will use) =====
    print('\n--- V8.5 cross-year r on 2020→2024 transitions (subset where FG data exists) ---')
    fg_feats = ['stuff_plus','pitching_plus','pb_stuff','pb_command']  # try a reasonable subset first
    v85_subset = cross_year_evaluate_v85_subset(df, fg_feats)
    print(f'  V8.5 (same subset): cross={v85_subset["r"]} kbias={v85_subset["k_bias_hi"]} score={v85_subset["score"]} n={v85_subset["n"]}')

    # ===== STEP 2: V12 residual at multiple alpha values =====
    print('\n--- V12 residual correction across alpha (regularization strength) ---')
    feat_combos = [
        ('pitching_plus', ['pitching_plus']),
        ('pb_stuff',      ['pb_stuff']),
        ('stuff+pitching',['stuff_plus','pitching_plus']),
        ('all_FG',        ['stuff_plus','location_plus','pitching_plus']),
        ('all_FG+PB',     ['stuff_plus','location_plus','pitching_plus','pb_stuff','pb_command']),
    ]
    alphas = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 500.0]
    leaderboard = []
    for cname, cfeats in feat_combos:
        for a in alphas:
            e = cross_year_evaluate_v12(df, cfeats, alpha_floor=a)
            if e is None: continue
            e['feat_combo'] = cname
            append_log(e)
            leaderboard.append((cname, a, cfeats, e))
            print(f'  {cname:<18s} alpha={a:>6.1f}  cross={e["r"]} kbias={e["k_bias_hi"]:+.3f} score={e["score"]}')

    # Sort by score
    leaderboard.sort(key=lambda x: -(x[3]['score'] or -1e9))
    print('\nTop 5 V12 configs by score:')
    for cname, a, cfeats, e in leaderboard[:5]:
        print(f'  {cname:<18s} alpha={a:>6.1f}  score={e["score"]}  cross={e["r"]} kbias={e["k_bias_hi"]:+.3f}')

    best = leaderboard[0]
    best_cname, best_alpha, best_feats, best_eval = best
    SHIPS = (best_eval['score'] or -1) >= V85_SCORE_BASE + 0.010
    SHIPS_ON_SUBSET = (best_eval['score'] or -1) >= (v85_subset['score'] or -1) + 0.010
    print(f'\nBest: {best_cname} alpha={best_alpha} score={best_eval["score"]}')
    print(f'  vs V8.5 absolute (1.567): {"SHIPS" if SHIPS else "no ship"} (Δ {best_eval["score"]-V85_SCORE_BASE:+.5f})')
    print(f'  vs V8.5 same-subset ({v85_subset["score"]}): {"SHIPS" if SHIPS_ON_SUBSET else "no ship"} (Δ {best_eval["score"]-v85_subset["score"]:+.5f})')

    # Build final V12 model using full training set
    if SHIPS or SHIPS_ON_SUBSET:
        print('\n--- Training final V12 (V8.5 + residual) and building 2026 projections ---')
        from sklearn.pipeline import Pipeline
        from sklearn.linear_model import RidgeCV, Ridge
        from sklearn.preprocessing import StandardScaler

        # Full V8.5 (we already train inside build_v12_dashboard_and_projections)
        # We need to compute residuals on training data for the residual model
        train_full = df[df['year'].between(2015, 2025)].dropna(subset=V85_FEATS + ['fp_per_start_actual'])
        pipe85_full = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe85_full.fit(train_full[V85_FEATS], train_full['fp_per_start_actual'])

        # Residual training set: cross-year transitions 2020->2024 with FG feats
        Xs, ys = [], []
        for tt_train, tt_test in [(y, y+1) for y in range(2020, 2025)]:
            tt_pt_tr = set(df[df['year']==tt_train]['pitcher'])
            tt_pt_te = set(df[df['year']==tt_test ]['pitcher'])
            tt_shared = tt_pt_tr & tt_pt_te
            if not tt_shared: continue
            tt_ty = df[(df['year']==tt_train) & df['pitcher'].isin(tt_shared)]
            tt_te = df[(df['year']==tt_test ) & df['pitcher'].isin(tt_shared)]
            tt_merged = tt_te[['pitcher','fp_per_start_actual']].merge(
                tt_ty[['pitcher'] + V85_FEATS + best_feats], on='pitcher', how='inner').dropna(
                subset=V85_FEATS + best_feats + ['fp_per_start_actual'])
            if len(tt_merged) == 0: continue
            v85_pred = pipe85_full.predict(tt_merged[V85_FEATS])
            resid = tt_merged['fp_per_start_actual'].values - v85_pred
            Xs.append(tt_merged[best_feats].values); ys.append(resid)

        X_full = np.vstack(Xs); y_full = np.concatenate(ys)
        sc_r = StandardScaler(); X_sc = sc_r.fit_transform(X_full)
        residual_pipe = Ridge(alpha=best_alpha).fit(X_sc, y_full)
        print(f'  residual model trained on {len(y_full)} prior cross-year residuals')
        print(f'  residual coefs: {dict(zip(best_feats, residual_pipe.coef_.round(3)))}')

        proj, r_v85_ytd, r_v12_ytd = build_v12_dashboard_and_projections(
            df, residual_pipe, best_feats, sc_r, v85_subset, best_eval, best_alpha)
        build_dashboard(proj, v85_subset, best_eval, best_alpha, best_feats, r_v85_ytd, r_v12_ytd)

        # Spot check
        print('\nSPOT CHECK:')
        for n in ['Schlittler','Glasnow','Imanaga','Fried','Wheeler','Woodruff','Ragans']:
            r = proj[proj['player_name'].fillna('').str.contains(n, na=False)]
            if len(r):
                s = r.iloc[0]
                actual = s['fp_per_start_actual_2026']
                actual_str = f'{actual:.2f}' if pd.notna(actual) else 'n/a'
                print(f'  {n:<13s} V8.5={s["xfp_v8_5"]:.2f}  V12={s["xfp_v12"]:.2f}  '
                      f'resid={s["residual_correction"]:+.2f}  actual={actual_str}')

    append_research(leaderboard, v85_subset, best, SHIPS, SHIPS_ON_SUBSET)

    print('\n' + '=' * 60)
    print('V12 PIPELINE COMPLETE')
    print('=' * 60)


def append_research(leaderboard, v85_subset, best, SHIPS, SHIPS_ON_SUBSET):
    best_cname, best_alpha, best_feats, best_eval = best
    section_lines = ['', '## V12 — Residual Correction Architecture (2026-05-05)', '',
                      'V8.5 base + Ridge on FG features fit on cross-year residuals (2020-2024 transitions only,',
                      'where FG history exists). Heavy regularization (alpha tested 1-500) to capture only',
                      'the additional cross-year signal in Stuff+/Pitching+ without re-introducing k_bias.',
                      '',
                      f'**Decision rules**:',
                      f'- vs V8.5 absolute baseline (score 1.567): need score >= 1.577',
                      f'- vs V8.5 same-subset baseline (score {v85_subset["score"]}): need score >= {v85_subset["score"]+0.010:.4f}',
                      '',
                      '### Top configurations (sorted by composite score)',
                      '',
                      '| Features | alpha | cross-year r | k_bias_hi | score |',
                      '|---|---|---|---|---|',
    ]
    for cname, a, cfeats, e in leaderboard[:10]:
        section_lines.append(f'| {cname} | {a} | {e["r"]} | {e["k_bias_hi"]} | {e["score"]} |')
    section_lines.append(f'| **V8.5 same-subset baseline** | - | {v85_subset["r"]} | {v85_subset["k_bias_hi"]} | **{v85_subset["score"]}** |')

    section_lines.extend(['',
                            '### Result',
                            '',
                            f'**Best V12: {best_cname} (alpha={best_alpha})** — score {best_eval["score"]}',
                            f'- vs V8.5 absolute: {"SHIPS" if SHIPS else "DOES NOT SHIP"} (Δ {best_eval["score"]-1.567:+.5f})',
                            f'- vs V8.5 same-subset: {"SHIPS" if SHIPS_ON_SUBSET else "DOES NOT SHIP"} (Δ {best_eval["score"]-v85_subset["score"]:+.5f})',
                            '',
                            'V12 evaluates only on 2020-2024 transitions because FG history starts 2020. The',
                            'absolute V8.5 score (1.567) is computed on 2015-2024 transitions, so the comparison',
                            'is unfair. The fair comparison is V12 vs V8.5-same-subset.',
                            '',
                            '### Files',
                            '- `scripts/xfp/xfp_v12_residual.py`',
                            '- `data/models/xfp_v12_pipeline.pkl` (if shipped)',
                            '- `data/outputs/xfp_v12_projections.csv` (if shipped)',
                            '- `data/outputs/xfp_v12_dashboard.html` (if shipped)',
                            ''])

    research_md = RESEARCH / 'xfp_model_research.md'
    with open(research_md, 'a', encoding='utf-8') as f:
        f.write('\n'.join(section_lines))
    print('  appended V12 section to research notes')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'FATAL: {e}')
        traceback.print_exc()
