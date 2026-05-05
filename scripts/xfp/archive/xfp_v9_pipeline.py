"""
xfp_v9_pipeline.py - V9 IP-decomposition refit.

Predicts (FP - IP*3.3) and ip_per_start separately, sums:
  xfp_v9 = stuff_pred + 3.3 * ip_pred

Decision: ship if cross-year r >= V8 (0.558) + 0.005 = 0.563 AND k_bias_hi <= 0.30.
"""
from __future__ import annotations
import sys, joblib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from xfp_v7_pipeline import derive_features, add_ip_resid_lag
from xfp_v8_pipeline import V6_FEATS, V7_FEATS, V8_BASE, derive_v8_features, build_pitch_type_panel, score_fn
from xfp_v8_5_pipeline import build_pfxz_panel

CACHE   = ROOT / 'data' / 'research' / 'xfp_cache'
OUTPUTS = ROOT / 'data' / 'outputs'
MODELS  = ROOT / 'data' / 'models'
RESEARCH= ROOT / 'data' / 'research'

LOG_CSV = RESEARCH / 'feature_search_log.csv'

V5_FEATS = ['avg_velo','abs_pfxz','avg_ext','zone_pct','o_swing_pct',
            'swstr_pct','c_plus_swstr','xwoba_contact']
V8_FEATS = ['swstr_pct','c_plus_swstr','xwoba_per_pa','xwoba_x_swstr']

V8_CROSS_R     = 0.55839
V8_K_BIAS_HI   = 0.241
SHIP_R_DELTA   = 0.005
SHIP_K_BIAS_MAX= 0.30


def cross_year_evaluate_decomp(df: pd.DataFrame, stuff_feats: list[str], ip_feats: list[str],
                                target_col: str = 'fp_per_start_actual', label: str = ''):
    """Cross-year r predicting full FP via decomposition: stuff_pred + 3.3 * ip_pred."""
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    all_feats = list(set(stuff_feats + ip_feats))

    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        if not shared:
            continue
        train_year = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year  = df[(df['year']==yr_test)  & df['pitcher'].isin(shared)].copy()
        merged = test_year[['pitcher','fp_per_start_actual','ip_per_start','k_pct']].merge(
            train_year[['pitcher'] + all_feats], on='pitcher', how='inner')
        merged = merged.dropna(subset=stuff_feats + ip_feats + ['fp_per_start_actual','ip_per_start'])
        if len(merged) < 10:
            continue
        # Fit on all prior years
        prior = df[df['year'] < yr_test].copy()
        prior['fp_no_ip'] = prior['fp_per_start_actual'] - prior['ip_per_start'] * 3.3
        prior_stuff = prior.dropna(subset=stuff_feats + ['fp_no_ip'])
        prior_ip    = prior.dropna(subset=ip_feats + ['ip_per_start'])
        if len(prior_stuff) < 50 or len(prior_ip) < 50:
            continue
        pipe_stuff = Pipeline([('sc', StandardScaler()),
                                ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_ip = Pipeline([('sc', StandardScaler()),
                             ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_stuff.fit(prior_stuff[stuff_feats], prior_stuff['fp_no_ip'])
        pipe_ip.fit(prior_ip[ip_feats], prior_ip['ip_per_start'])

        merged['pred_stuff'] = pipe_stuff.predict(merged[stuff_feats])
        merged['pred_ip']    = pipe_ip.predict(merged[ip_feats])
        merged['pred_v9']    = merged['pred_stuff'] + 3.3 * merged['pred_ip']
        preds_all.extend(merged['pred_v9']); acts_all.extend(merged['fp_per_start_actual']); rows.append(merged)

    if not rows:
        return {'r': None, 'k_bias_hi': None, 'score': None, 'n': 0}
    res = pd.concat(rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred_v9']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    k_bias_hi = float(res[res['k_pct']>0.30]['resid'].mean()) if (res['k_pct']>0.30).any() else float('nan')
    score = score_fn(r, k_bias_hi)
    return {'r': round(r,5), 'k_bias_hi': round(k_bias_hi,3), 'score': round(score,5),
            'n': len(res), 'feats': label}


def cross_year_stuff_only(df, stuff_feats, label=''):
    """Cross-year r predicting fp_no_ip alone (ignores IP)."""
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    preds_all, acts_all, rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year']==yr_train]['pitcher'])
        pitchers_test  = set(df[df['year']==yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        if not shared: continue
        train_year = df[(df['year']==yr_train) & df['pitcher'].isin(shared)]
        test_year  = df[(df['year']==yr_test)  & df['pitcher'].isin(shared)].copy()
        merged = test_year[['pitcher','fp_per_start_actual','ip_per_start','k_pct']].merge(
            train_year[['pitcher'] + stuff_feats], on='pitcher', how='inner')
        merged = merged.dropna(subset=stuff_feats + ['fp_per_start_actual','ip_per_start'])
        merged['fp_no_ip'] = merged['fp_per_start_actual'] - merged['ip_per_start'] * 3.3
        if len(merged) < 10: continue
        prior = df[df['year'] < yr_test].copy()
        prior['fp_no_ip'] = prior['fp_per_start_actual'] - prior['ip_per_start'] * 3.3
        prior = prior.dropna(subset=stuff_feats + ['fp_no_ip'])
        if len(prior) < 50: continue
        pipe = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe.fit(prior[stuff_feats], prior['fp_no_ip'])
        merged['pred'] = pipe.predict(merged[stuff_feats])
        preds_all.extend(merged['pred']); acts_all.extend(merged['fp_no_ip']); rows.append(merged)
    if not rows: return None
    res = pd.concat(rows)
    res['resid'] = res['fp_no_ip'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0,1])
    return {'r': round(r,5), 'rmse': round(float(np.sqrt((res['resid']**2).mean())),3), 'n': len(res)}


def append_log(rec):
    rec = dict(rec)
    rec.setdefault('timestamp', datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'))
    df = pd.DataFrame([rec])
    if LOG_CSV.exists():
        df.to_csv(LOG_CSV, mode='a', header=False, index=False)
    else:
        df.to_csv(LOG_CSV, index=False)


def main():
    print('=' * 60)
    print(f'xFP V9 IP-DECOMPOSITION REFIT | {datetime.now(timezone.utc).isoformat()}')
    print('=' * 60)

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

    train = df[df['year'].between(2015, 2025)].copy()
    print(f'\nTraining: {len(train)} rows. Verifying decomposition target:')
    train_check = train.dropna(subset=['fp_per_start_actual','ip_per_start']).copy()
    train_check['fp_no_ip'] = train_check['fp_per_start_actual'] - train_check['ip_per_start'] * 3.3
    print(f'  fp_no_ip mean: {train_check["fp_no_ip"].mean():.3f}  (expect ~ -7.2)')
    print(f'  fp_no_ip std:  {train_check["fp_no_ip"].std():.3f}   (expect lower than full FP std ~3.8)')
    print(f'  full FP std:   {train_check["fp_per_start_actual"].std():.3f}')

    # Try V8.5 best feature set if available, else V8 features
    v85_pkl = MODELS / 'xfp_v8_5_pipeline.pkl'
    if v85_pkl.exists():
        bundle = joblib.load(v85_pkl)
        v85_feats = bundle['features']
        print(f'\nUsing V8.5 features ({len(v85_feats)}) as starting point: {v85_feats}')
    else:
        v85_feats = V8_FEATS
        print(f'\nV8.5 not available; using V8 features: {V8_FEATS}')

    # ===== STEP 2: Stuff model BE on fp_no_ip =====
    print('\n===== STEP 2: Stuff model backward elimination on fp_no_ip target =====')
    other_pt = [c for c in ['FF_spin','breaking_spin','offspeed_spin','vaa_ff','velo_diff','pitch_entropy']
                 if c in train.columns and train[c].notna().sum() > 100]
    pfxz_feats = [c for c in ['fb_pfxz','bb_pfxz','pfxz_spread'] if c in train.columns]
    kitchen = list(dict.fromkeys(V8_BASE + ['k_pct_lag1','bb_pct_lag1'] + other_pt + pfxz_feats))
    print(f'  kitchen sink ({len(kitchen)}): {kitchen}')

    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    current = list(kitchen)
    best_score, best_set, best_eval = -float('inf'), None, None
    while len(current) >= 4:
        d_curr = train.dropna(subset=current+['fp_per_start_actual','ip_per_start'])
        if len(d_curr) < 100:
            print(f'  n={len(current)}: only {len(d_curr)} rows, stopping'); break
        d_curr_so = d_curr.copy()
        d_curr_so['fp_no_ip'] = d_curr_so['fp_per_start_actual'] - d_curr_so['ip_per_start'] * 3.3
        sc = StandardScaler()
        X = sc.fit_transform(d_curr_so[current])
        ridge = RidgeCV(alphas=np.logspace(-1,5,80), cv=5).fit(X, d_curr_so['fp_no_ip'])
        coefs = pd.Series(np.abs(ridge.coef_), index=current).sort_values()
        # Eval combined V9 (stuff + IP) cross-year r on full FP
        e = cross_year_evaluate_decomp(train, current, V5_FEATS, label=f'V9_BE_{len(current)}')
        e['phase'] = '11.6E_v9'
        append_log(e)
        e_so = cross_year_stuff_only(train, current, label=f'V9_stuff_only_{len(current)}')
        print(f'  n={len(current):2d} V9 cross={e["r"]} kbias={e["k_bias_hi"]:+.3f} '
              f'score={e["score"]} | stuff-only r_no_ip={e_so["r"] if e_so else "-"} '
              f'drop={coefs.index[0]} ({coefs.iloc[0]:.3f})')
        if e['score'] is not None and e['score'] > best_score:
            best_score = e['score']; best_set = list(current); best_eval = e
        current = [f for f in current if f != coefs.index[0]]

    print(f'\n>>> V9 best: score={best_score} cross={best_eval["r"]} kbias={best_eval["k_bias_hi"]}')
    print(f'    stuff features ({len(best_set)}): {best_set}')

    # ===== STEP 3: IP model =====
    print('\n===== STEP 3: IP model (V5 features predicting ip_per_start) =====')
    train_ip = train.dropna(subset=V5_FEATS + ['ip_per_start'])
    pipe_ip = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
    pipe_ip.fit(train_ip[V5_FEATS], train_ip['ip_per_start'])
    print(f'  IP model train r: {float(np.corrcoef(pipe_ip.predict(train_ip[V5_FEATS]), train_ip["ip_per_start"])[0,1]):.5f}')

    # IP model cross-year r alone
    ip_results = []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    for yr_train, yr_test in transitions:
        train_year = train[train['year']==yr_train]
        test_year  = train[train['year']==yr_test ]
        shared = set(train_year['pitcher']) & set(test_year['pitcher'])
        merged = test_year[['pitcher','ip_per_start']].merge(
            train_year[['pitcher']+V5_FEATS], on='pitcher', how='inner').dropna(subset=V5_FEATS+['ip_per_start'])
        if len(merged) < 10: continue
        prior = train[train['year'] < yr_test].dropna(subset=V5_FEATS + ['ip_per_start'])
        if len(prior) < 50: continue
        pipe_ip_local = Pipeline([('sc', StandardScaler()),
                                   ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_ip_local.fit(prior[V5_FEATS], prior['ip_per_start'])
        merged['pred_ip'] = pipe_ip_local.predict(merged[V5_FEATS])
        ip_results.append(merged)
    ip_res = pd.concat(ip_results)
    ip_cross_r = float(np.corrcoef(ip_res['pred_ip'], ip_res['ip_per_start'])[0,1])
    print(f'  IP model cross-year r: {ip_cross_r:.5f} (ceiling ~0.29 YoY stability)')

    # ===== STEP 4: Decision =====
    cross_r_v9 = best_eval['r']
    k_bias_v9  = best_eval['k_bias_hi']
    SHIPS = (cross_r_v9 >= V8_CROSS_R + SHIP_R_DELTA) and (abs(k_bias_v9) <= SHIP_K_BIAS_MAX)
    print(f'\nDECISION: V9 {"SHIPS" if SHIPS else "DOES NOT SHIP"}')
    print(f'  cross-year r: {cross_r_v9} >= {V8_CROSS_R + SHIP_R_DELTA} ? {cross_r_v9 >= V8_CROSS_R + SHIP_R_DELTA}')
    print(f'  k_bias_hi: {abs(k_bias_v9)} <= {SHIP_K_BIAS_MAX} ? {abs(k_bias_v9) <= SHIP_K_BIAS_MAX}')

    if SHIPS:
        # Train final stuff + IP models
        train_v9 = train.dropna(subset=best_set + V5_FEATS + ['fp_per_start_actual','ip_per_start'])
        train_v9 = train_v9.copy()
        train_v9['fp_no_ip'] = train_v9['fp_per_start_actual'] - train_v9['ip_per_start'] * 3.3
        pipe_stuff = Pipeline([('sc', StandardScaler()),
                                ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_stuff.fit(train_v9[best_set], train_v9['fp_no_ip'])
        pipe_ip_final = Pipeline([('sc', StandardScaler()),
                                   ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe_ip_final.fit(train_v9[V5_FEATS], train_v9['ip_per_start'])

        joblib.dump({'pipeline': pipe_stuff, 'features': best_set, 'name':'V9_stuff',
                      'metrics': best_eval, 'target': 'fp_no_ip'},
                     MODELS / 'xfp_v9_no_ip_pipeline.pkl')
        joblib.dump({'pipeline': pipe_ip_final, 'features': V5_FEATS, 'name':'V9_ip',
                      'target': 'ip_per_start'},
                     MODELS / 'xfp_v9_ip_pipeline.pkl')
        print(f'  saved data/models/xfp_v9_no_ip_pipeline.pkl + xfp_v9_ip_pipeline.pkl')

        coef_stuff = pd.Series(pipe_stuff.named_steps['r'].coef_, index=best_set)
        coef_ip = pd.Series(pipe_ip_final.named_steps['r'].coef_, index=V5_FEATS)

        # Build V9 projections from V8.1 mid-season blend (same blend logic, both models applied)
        proj = build_v9_projections(df, best_set, pipe_stuff, pipe_ip_final)
        proj.to_csv(OUTPUTS / 'xfp_v9_projections.csv', index=False)
        print(f'  wrote {OUTPUTS / "xfp_v9_projections.csv"}')

        # Build dashboard
        build_v9_dashboard(proj, best_eval, best_set, coef_stuff, coef_ip, ip_cross_r)
        print(f'  wrote {OUTPUTS / "xfp_v9_dashboard.html"}')

    append_v9_research(SHIPS, best_set, best_eval, ip_cross_r, V8_CROSS_R)
    print('\nWORKSTREAM 3 COMPLETE — V9 ' + ('SHIPPED' if SHIPS else 'NOT SHIPPED'))
    return SHIPS, best_set, best_eval, ip_cross_r


def build_v9_projections(df, stuff_feats, pipe_stuff, pipe_ip):
    """V9 projections: blend 2025+2026, predict each component, sum."""
    from xfp_v8_midseason import blend_pitcher
    df_25 = df[df['year']==2025].set_index('pitcher')
    df_26 = df[df['year']==2026].set_index('pitcher')
    pitchers_union = sorted(set(df_25.index) | set(df_26.index))
    rows = []
    for p in pitchers_union:
        r25 = df_25.loc[p].to_dict() if p in df_25.index else None
        r26 = df_26.loc[p].to_dict() if p in df_26.index else None
        if r25: r25 = pd.Series({**r25, 'pitcher': p})
        if r26: r26 = pd.Series({**r26, 'pitcher': p})
        b = blend_pitcher(r25, r26)
        if b is None: continue
        # Pull non-blended features (lag, pfxz, pitch type) from 2026 if present else 2025
        all_v9_feats = list(set(stuff_feats + V5_FEATS))
        for f in all_v9_feats:
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

    valid = blended.dropna(subset=stuff_feats + V5_FEATS).copy()
    valid['xfp_v9_no_ip']     = pipe_stuff.predict(valid[stuff_feats])
    valid['xfp_v9_ip_part']   = pipe_ip.predict(valid[V5_FEATS])
    valid['xfp_v9']           = valid['xfp_v9_no_ip'] + 3.3 * valid['xfp_v9_ip_part']

    v85 = pd.read_csv(OUTPUTS / 'xfp_v8_5_projections.csv') if (OUTPUTS / 'xfp_v8_5_projections.csv').exists() else \
          pd.read_csv(OUTPUTS / 'xfp_v8_1_projections.csv')
    v85_xfp_col = 'xfp_v8_5' if 'xfp_v8_5' in v85.columns else 'xfp_v8_1'
    out = valid[['pitcher','player_name','xfp_v9','xfp_v9_no_ip','xfp_v9_ip_part','cohort']].merge(
        v85[['pitcher', v85_xfp_col, 'xfp_v8_1', 'xfp_v8', 'xfp_v7','xfp_v6','xfp_v5',
             'gs_2026','fp_per_start_actual_2026','k_pct_2026']],
        on='pitcher', how='left')
    out['delta_v9_v85'] = out['xfp_v9'] - out[v85_xfp_col]
    return out


def build_v9_dashboard(proj, best_eval, stuff_feats, coef_stuff, coef_ip, ip_cross_r):
    proj_d = proj.sort_values('xfp_v9', ascending=False, na_position='last').reset_index(drop=True)
    proj_d['rank_v9'] = proj_d.index + 1

    def fmt(x, p=2):
        try:
            f = float(x)
            if not np.isfinite(f): return '-'
            return f'{f:.{p}f}'
        except (TypeError, ValueError):
            return '-'

    # Decomposition stack
    rows_stack = []
    for _, s in proj_d.head(30).iterrows():
        ip_part = float(s['xfp_v9_ip_part']) * 3.3 if pd.notna(s['xfp_v9_ip_part']) else 0
        stuff_part = float(s['xfp_v9_no_ip']) if pd.notna(s['xfp_v9_no_ip']) else 0
        total = ip_part + stuff_part
        # Bar widths normalized
        scale = max(abs(total), 1)
        ip_pct = abs(ip_part) / scale * 100
        stuff_pct = abs(stuff_part) / scale * 100
        rows_stack.append(
            f'<div class="row" style="display:flex;align-items:center;gap:8px;margin:3px 0">'
            f'<span style="width:160px;font-size:11px">{s["player_name"]}</span>'
            f'<div style="width:60px;font-size:11px;text-align:right">{fmt(total)}</div>'
            f'<div style="flex:1;height:14px;background:#21262d;display:flex;border-radius:3px;overflow:hidden">'
            f'  <div style="width:{ip_pct:.1f}%;background:#1f6feb" title="IP component {fmt(ip_part)}"></div>'
            f'  <div style="width:{stuff_pct:.1f}%;background:#f0883e" title="Stuff component {fmt(stuff_part)}"></div>'
            f'</div>'
            f'<span style="width:60px;font-size:10.5px;color:#8b949e">IP {fmt(ip_part)}</span>'
            f'<span style="width:60px;font-size:10.5px;color:#8b949e">stuff {fmt(stuff_part)}</span>'
            f'</div>'
        )
    decomp_html = '\n'.join(rows_stack)

    # Archetypes
    def archetype_card(name):
        r = proj_d[proj_d['player_name'].fillna('').str.contains(name, na=False)]
        if not len(r): return f'<div class="card"><div class="cardh">{name}</div><div>not in set</div></div>'
        s = r.iloc[0]
        return (f'<div class="card"><div class="cardh">{s["player_name"]}</div>'
                f'<div class="kv"><span class="kv-k">V9 xFP</span><span class="kv-v" style="color:#3fb950">{fmt(s["xfp_v9"])}</span></div>'
                f'<div class="kv"><span class="kv-k">  ip*3.3</span><span class="kv-v">{fmt(float(s["xfp_v9_ip_part"])*3.3 if pd.notna(s["xfp_v9_ip_part"]) else None)}</span></div>'
                f'<div class="kv"><span class="kv-k">  stuff</span><span class="kv-v">{fmt(s["xfp_v9_no_ip"])}</span></div>'
                f'<div class="kv"><span class="kv-k">2026 actual</span><span class="kv-v">{fmt(s["fp_per_start_actual_2026"])}</span></div>'
                f'</div>')
    archetype_html = ''.join(archetype_card(n) for n in
        ['Schlittler','Glasnow','Imanaga','Fried','Woodruff','Ragans'])

    # Top 80 main table
    main_rows = []
    v85col = 'xfp_v8_5' if 'xfp_v8_5' in proj_d.columns else 'xfp_v8_1'
    for _, s in proj_d.head(80).iterrows():
        try: dv = float(s['delta_v9_v85']); dvc = 'up' if dv>0 else 'dn' if dv<0 else ''
        except: dvc=''; dv=0
        cls = 't1' if s['rank_v9']==1 else 't2' if s['rank_v9']==2 else 't3' if s['rank_v9']==3 else ''
        gold = ' style="color:#ffd700"' if 'Schlittler' in str(s['player_name']) else ''
        main_rows.append(
            f'<tr><td class="{cls}">{int(s["rank_v9"])}</td><td{gold}>{s["player_name"]}</td>'
            f'<td class="num">{fmt(s["xfp_v8"])}</td>'
            f'<td class="num">{fmt(s["xfp_v8_1"])}</td>'
            f'<td class="num">{fmt(s.get(v85col))}</td>'
            f'<td class="num"><b>{fmt(s["xfp_v9"])}</b></td>'
            f'<td class="num {dvc}">{dv:+.2f}</td>'
            f'<td class="num">{fmt(s["gs_2026"],0)}</td>'
            f'<td class="num">{fmt(s["fp_per_start_actual_2026"])}</td></tr>')

    coef_stuff_html = ''.join(f'<div class="kv"><span class="kv-k">{f}</span><span class="kv-v">{c:+.3f}</span></div>'
                                for f,c in coef_stuff.sort_values(key=abs, ascending=False).items())
    coef_ip_html = ''.join(f'<div class="kv"><span class="kv-k">{f}</span><span class="kv-v">{c:+.3f}</span></div>'
                             for f,c in coef_ip.sort_values(key=abs, ascending=False).items())

    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>xFP v9 IP-decomposition</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#e6edf3;padding:18px}}
.hdr{{background:linear-gradient(135deg,#1a2332,#0d1b2a);border:1px solid #30363d;border-radius:8px;padding:14px 18px;margin-bottom:14px}}
.title{{font-size:20px;font-weight:700;color:#58a6ff}}.title span{{color:#f0883e}}
.sub{{font-size:11.5px;color:#8b949e;margin-top:4px;line-height:1.5}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px}}
.cardh{{font-size:11px;font-weight:700;text-transform:uppercase;color:#8b949e;letter-spacing:.7px;margin-bottom:9px}}
.grid6{{display:grid;grid-template-columns:repeat(6, minmax(0, 1fr));gap:10px;margin-bottom:14px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
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
<div class="title">xFP <span>v9</span> IP-Decomposition Refit</div>
<div class="sub">Two models summed. Stuff model predicts (FP - IP×3.3) on V8.5 features. IP model predicts ip_per_start from V5 features. Cross-year r {best_eval["r"]} (V8: 0.55839). k_bias_hi {best_eval["k_bias_hi"]} (V8: 0.241). Score {best_eval["score"]} (V8: 1.555). IP model standalone cross-year r: {ip_cross_r:.5f}.</div>
</div>

<div class="card" style="margin-bottom:14px"><div class="cardh">V9 archetype callouts (decomposed)</div>
<div class="grid6">{archetype_html}</div></div>

<div class="grid2">
<div class="card"><div class="cardh">Stuff model coefs ({len(stuff_feats)})</div>{coef_stuff_html}</div>
<div class="card"><div class="cardh">IP model coefs (V5)</div>{coef_ip_html}</div>
</div>

<div class="card" style="margin-bottom:14px"><div class="cardh">Top 30 decomposition stack — IP component (blue) + Stuff component (orange)</div>
{decomp_html}
</div>

<div class="card"><div class="cardh">Top 80 SP — V8 / V8.1 / V8.5 / V9 (Schlittler in gold)</div>
<table><thead><tr><th>Rk V9</th><th>Pitcher</th><th class="num">V8</th><th class="num">V8.1</th><th class="num">V8.5</th><th class="num">V9</th><th class="num">Δ vs V8.5</th><th class="num">2026 GS</th><th class="num">Actual</th></tr></thead>
<tbody>{''.join(main_rows)}</tbody></table></div>
</body></html>'''
    out_path = OUTPUTS / 'xfp_v9_dashboard.html'
    out_path.write_text(html, encoding='utf-8')


def append_v9_research(SHIPS, best_set, best_eval, ip_cross_r, v8_cross_r):
    section = f"""

## V9 — IP-Decomposition Refit ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})

Architecture: predict (FP - IP×3.3) and ip_per_start separately, sum at projection time.
Motivated by Breakdown 2: IP × 3.3 contributes ~17.5 pts on a 10.2-pt mean net FP/start, and stripping
it makes every stuff metric correlate harder with the residual.

### Result: V9 {"SHIPPED" if SHIPS else "NOT SHIPPED"}

Decision rule: cross-year r >= V8 + 0.005 ({v8_cross_r:.5f} + 0.005 = {v8_cross_r+0.005:.5f}) AND k_bias_hi <= 0.30.

| | V8 | V9 | Δ |
|---|---|---|---|
| Cross-year r | {v8_cross_r:.5f} | {best_eval['r']} | {(best_eval['r'] or 0)-v8_cross_r:+.5f} |
| k_bias_hi | 0.241 | {best_eval['k_bias_hi']} | {(best_eval['k_bias_hi'] or 0)-0.241:+.3f} |
| Score | 1.555 | {best_eval['score']} | {(best_eval['score'] or 0)-1.555:+.5f} |

IP model standalone cross-year r: {ip_cross_r:.5f} (ceiling ~0.29 YoY stability)

### V9 stuff feature set ({len(best_set)})
{', '.join(best_set)}

### Files
{('- `data/models/xfp_v9_no_ip_pipeline.pkl`' + chr(10) + '- `data/models/xfp_v9_ip_pipeline.pkl`' + chr(10) + '- `data/outputs/xfp_v9_projections.csv`' + chr(10) + '- `data/outputs/xfp_v9_dashboard.html`') if SHIPS else 'No model artifacts saved (decision rule failed).'}
"""
    research_md = RESEARCH / 'xfp_model_research.md'
    with open(research_md, 'a', encoding='utf-8') as f:
        f.write(section)
    print(f'  appended V9 section to {research_md}')


if __name__ == '__main__':
    main()
