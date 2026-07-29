"""
xfp_v8_ensemble.py - Test V6+V8 ensemble. Three parts:
  1. Cross-year ensemble evaluation across alpha in [0.0..1.0].
  2. 2026 YTD ensemble check.
  3. Save best ensemble to projections + dashboard.
"""
from __future__ import annotations
import sys, joblib
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from xfp_v7_pipeline import derive_features, add_ip_resid_lag
from xfp_v8_pipeline import V6_FEATS, V8_BASE, derive_v8_features, build_pitch_type_panel, score_fn

CACHE   = ROOT / 'data' / 'research' / 'xfp_cache'
OUTPUTS = ROOT / 'data' / 'outputs'
MODELS  = ROOT / 'data' / 'models'

# ============================================================
# PART 1: cross-year ensemble eval
# ============================================================
def cross_year_evaluate_ensemble(df, feats_v6, feats_v8, alpha):
    """Year-T metrics from BOTH models, ensemble pred, score year-T+1 actual FP."""
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    preds_all, acts_all, res_rows = [], [], []
    transitions = [(y, y+1) for y in range(2015, 2025)]
    all_feats = list(set(feats_v6 + feats_v8))

    for yr_train, yr_test in transitions:
        pitchers_train = set(df[df['year'] == yr_train]['pitcher'])
        pitchers_test  = set(df[df['year'] == yr_test ]['pitcher'])
        shared = pitchers_train & pitchers_test
        if not shared:
            continue
        train_rows = df[(df['year'] == yr_train) & df['pitcher'].isin(shared)]
        test_rows  = df[(df['year'] == yr_test ) & df['pitcher'].isin(shared)].copy()

        merged = test_rows[['pitcher','fp_per_start_actual','k_pct']].merge(
            train_rows[['pitcher'] + all_feats], on='pitcher', how='inner')
        merged = merged.dropna(subset=feats_v6 + feats_v8 + ['fp_per_start_actual'])
        if len(merged) < 10:
            continue

        prior6 = df[df['year'] < yr_test].dropna(subset=feats_v6 + ['fp_per_start_actual'])
        prior8 = df[df['year'] < yr_test].dropna(subset=feats_v8 + ['fp_per_start_actual'])
        if len(prior6) < 50 or len(prior8) < 50:
            continue

        pipe6 = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe8 = Pipeline([('sc', StandardScaler()), ('r', RidgeCV(alphas=np.logspace(-1,5,80), cv=5))])
        pipe6.fit(prior6[feats_v6], prior6['fp_per_start_actual'])
        pipe8.fit(prior8[feats_v8], prior8['fp_per_start_actual'])

        pred_v6 = pipe6.predict(merged[feats_v6])
        pred_v8 = pipe8.predict(merged[feats_v8])
        ensemble_pred = alpha * pred_v6 + (1 - alpha) * pred_v8

        m = merged.copy(); m['pred'] = ensemble_pred
        preds_all.extend(ensemble_pred)
        acts_all.extend(m['fp_per_start_actual'])
        res_rows.append(m)

    res = pd.concat(res_rows)
    res['resid'] = res['fp_per_start_actual'] - res['pred']
    r = float(np.corrcoef(preds_all, acts_all)[0, 1])
    k_bias_hi = float(res[res['k_pct'] > 0.30]['resid'].mean())
    rmse = float(np.sqrt((res['resid']**2).mean()))
    return {
        'alpha':     alpha,
        'r':         round(r, 5),
        'k_bias_hi': round(k_bias_hi, 3),
        'score':     round(score_fn(r, k_bias_hi), 5),
        'rmse':      round(rmse, 3),
        'n':         len(res),
    }


def main():
    # Load extended training data + derive features
    df = pd.read_csv(CACHE / 'sp_multiyr_2015_2025.csv')
    df = derive_features(df)
    df = add_ip_resid_lag(df)
    df = derive_v8_features(df)
    pt = build_pitch_type_panel(sorted(df['year'].unique()))
    if not pt.empty:
        df = df.merge(pt, on=['pitcher','year'], how='left')
    print(f'Data: {len(df)} rows, years {sorted(df["year"].unique())}')

    # Load V8 features
    bundle_v8 = joblib.load(MODELS / 'xfp_v8_pipeline.pkl')
    V8_FEATS = bundle_v8['features']
    print(f'V6 features: {V6_FEATS}')
    print(f'V8 features: {V8_FEATS}')

    # ===== PART 1: cross-year ensemble eval =====
    print('\n' + '=' * 60)
    print('PART 1: CROSS-YEAR ENSEMBLE EVALUATION')
    print('=' * 60)
    rows = []
    alphas = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
    for a in alphas:
        e = cross_year_evaluate_ensemble(df, V6_FEATS, V8_FEATS, a)
        rows.append(e)
        label = f'alpha={a}' + ('  (V8 only)' if a==0.0 else '  (V6 only)' if a==1.0 else '')
        print(f'  {label:<25s} cross_r={e["r"]} kbias={e["k_bias_hi"]:+.3f} score={e["score"]} n={e["n"]}')

    df_cross = pd.DataFrame(rows).sort_values('score', ascending=False)
    best_row = df_cross.iloc[0]
    best_alpha = float(best_row['alpha'])
    print('\n  Cross-year leaderboard (sorted by score):')
    print('  ' + df_cross.to_string(index=False))
    print(f'\n>>> Best alpha by cross-year score: {best_alpha} (score={best_row["score"]})')

    # ===== PART 2: 2026 YTD ensemble check =====
    print('\n' + '=' * 60)
    print('PART 2: 2026 YTD ENSEMBLE CHECK')
    print('=' * 60)
    proj = pd.read_csv(OUTPUTS / 'xfp_v8_projections.csv')
    valid = proj[(proj['gs_2026'] >= 5)
                  & proj['xfp_v6'].notna()
                  & proj['xfp_v8'].notna()
                  & proj['fp_per_start_actual_2026'].notna()].copy()
    print(f'  YTD eligible (gs>=5, both V6+V8 non-null): {len(valid)}')

    ytd_rows = []
    for a in alphas:
        valid['pred'] = a * valid['xfp_v6'] + (1 - a) * valid['xfp_v8']
        valid['resid'] = valid['fp_per_start_actual_2026'] - valid['pred']
        if len(valid) < 10:
            ytd_rows.append({'alpha': a, 'r': None, 'k_bias_hi': None, 'score': None, 'n': len(valid)})
            continue
        r = float(np.corrcoef(valid['pred'], valid['fp_per_start_actual_2026'])[0,1])
        high_k = valid[valid['k_pct_2026'] > 0.30]
        k_bias = float(high_k['resid'].mean()) if len(high_k) else 0.0
        ytd_rows.append({
            'alpha': a, 'r': round(r,5), 'k_bias_hi': round(k_bias,3),
            'score': round(score_fn(r, k_bias),5), 'n': len(valid), 'n_highk': len(high_k),
        })
        label = f'alpha={a}' + ('  (V8 only)' if a==0.0 else '  (V6 only)' if a==1.0 else '')
        print(f'  {label:<25s} ytd_r={r:.5f} kbias={k_bias:+.3f} score={score_fn(r,k_bias):.5f} n={len(valid)} (highk n={len(high_k)})')

    df_ytd = pd.DataFrame(ytd_rows).sort_values('score', ascending=False)
    print('\n  YTD leaderboard:')
    print('  ' + df_ytd.to_string(index=False))

    # ===== PART 3: Save best ensemble + update projections + update dashboard =====
    print('\n' + '=' * 60)
    print('PART 3: SAVE BEST ENSEMBLE + UPDATE OUTPUTS')
    print('=' * 60)

    # Compute ensemble with NaN-aware fallback: if either side missing, use the other.
    # At alpha=0 this collapses to V8; at alpha=1 to V6.
    v6 = proj['xfp_v6']; v8 = proj['xfp_v8']
    blended = best_alpha * v6 + (1 - best_alpha) * v8
    proj['xfp_ensemble'] = blended.where(blended.notna(),
                                          v8.where(v8.notna(), v6))
    proj.to_csv(OUTPUTS / 'xfp_v8_projections.csv', index=False)
    print(f'  added xfp_ensemble column to xfp_v8_projections.csv (alpha={best_alpha}, '
          f'non-null={proj["xfp_ensemble"].notna().sum()})')

    # Update dashboard
    dash_path = OUTPUTS / 'xfp_v8_dashboard.html'
    update_dashboard(dash_path, proj, best_alpha, best_row, df_cross, df_ytd, V6_FEATS, V8_FEATS)
    print(f'  updated {dash_path}')

    # Final verdict
    v6_row  = df_cross[df_cross['alpha'] == 1.0].iloc[0]
    v8_row  = df_cross[df_cross['alpha'] == 0.0].iloc[0]
    ens_row = df_cross[df_cross['alpha'] == best_alpha].iloc[0]
    beats_both = (ens_row['score'] >= v6_row['score']) and (ens_row['score'] >= v8_row['score'])
    sch = proj[proj['player_name'].str.contains('Schlittler', na=False)]
    sch_row = sch.iloc[0] if len(sch) else {}
    def fmt(x, p=2):
        try: return f'{float(x):.{p}f}'
        except (TypeError, ValueError): return '-'

    print()
    print('=' * 60)
    print('FINAL VERDICT')
    print('=' * 60)
    print(f'Ensemble beats both standalone models: {"YES" if beats_both else "NO"}')
    print(f'Best alpha: {best_alpha}  (V6 weight = {best_alpha}, V8 weight = {1-best_alpha})')
    print()
    print(f'                ensemble        V6 only         V8 only')
    print(f'Cross-year r:   {ens_row["r"]:<12}    {v6_row["r"]:<12}    {v8_row["r"]}')
    print(f'k_bias_hi:      {ens_row["k_bias_hi"]:+.3f}          {v6_row["k_bias_hi"]:+.3f}          {v8_row["k_bias_hi"]:+.3f}')
    print(f'Composite:      {ens_row["score"]:<12}    {v6_row["score"]:<12}    {v8_row["score"]}')
    if len(sch):
        ens_sch = best_alpha * sch_row['xfp_v6'] + (1 - best_alpha) * sch_row['xfp_v8'] if pd.notna(sch_row['xfp_v6']) else sch_row['xfp_v8']
        print(f'Schlittler:     ensemble xFP={fmt(ens_sch)} (V6={fmt(sch_row.get("xfp_v6"))}, V8={fmt(sch_row.get("xfp_v8"))})')
    # Alpha=0 means ensemble == V8; alpha=1 means ensemble == V6.
    # Pick the human-readable recommendation.
    if best_alpha == 0.0:
        rec = 'use V8 alone (ensemble best alpha=0 collapses to V8)'
    elif best_alpha == 1.0:
        rec = 'use V6 alone (ensemble best alpha=1 collapses to V6)'
    else:
        rec = f'use ensemble (alpha={best_alpha} -- V6 weight {best_alpha}, V8 weight {1-best_alpha:.2f})'
    print(f'Recommendation: {rec}')


def update_dashboard(dash_path: Path, proj: pd.DataFrame, best_alpha: float,
                      best_row: dict, df_cross: pd.DataFrame, df_ytd: pd.DataFrame,
                      v6_feats, v8_feats):
    """Inject ensemble banner + ensemble column into existing V8 dashboard."""
    import re
    text = dash_path.read_text(encoding='utf-8')

    sch = proj[proj['player_name'].str.contains('Schlittler', na=False)]
    sch_panel = sch.iloc[0].to_dict() if len(sch) else {}
    def fmt(x, p=2):
        try:
            f = float(x)
            if not np.isfinite(f): return '-'
            return f'{f:.{p}f}'
        except (TypeError, ValueError):
            return '-'
    def ensemble_for(row, alpha):
        v6 = row.get('xfp_v6'); v8 = row.get('xfp_v8')
        if pd.notna(v6) and pd.notna(v8):
            return alpha * v6 + (1-alpha) * v8
        if pd.notna(v8): return v8
        if pd.notna(v6): return v6
        return None

    if best_alpha == 0.0:
        banner_title = 'Recommended: V8 alone (ensemble best alpha=0 collapses to V8)'
    elif best_alpha == 1.0:
        banner_title = 'Recommended: V6 alone (ensemble best alpha=1 collapses to V6)'
    else:
        banner_title = f'Recommended ensemble: V6 x {best_alpha} + V8 x {1-best_alpha:.2f}'

    banner = (f'<div class="card" style="margin-bottom:14px;border-color:rgba(63,185,80,.5);background:rgba(63,185,80,.05)">'
              f'<div class="cardh" style="color:#3fb950">{banner_title}</div>'
              f'<div class="kv"><span class="kv-k">Cross-year r</span><span class="kv-v">{best_row["r"]}</span></div>'
              f'<div class="kv"><span class="kv-k">k_bias_hi</span><span class="kv-v">{best_row["k_bias_hi"]:+.3f}</span></div>'
              f'<div class="kv"><span class="kv-k">Composite score</span><span class="kv-v" style="color:#3fb950">{best_row["score"]}</span></div>'
              f'<div class="kv"><span class="kv-k">Schlittler ensemble xFP</span><span class="kv-v" style="color:#ffd700">'
              f'{fmt(ensemble_for(sch_panel, best_alpha)) if sch_panel else "-"}'
              f' (V6={fmt(sch_panel.get("xfp_v6"))}, V8={fmt(sch_panel.get("xfp_v8"))})</span></div>'
              f'<div style="margin-top:6px;font-size:10.5px;color:#8b949e">Linear blend of V6 ({v6_feats}) and V8 ({v8_feats}). '
              f'Pure V6: r={float(df_cross[df_cross["alpha"]==1.0]["r"].iloc[0])} kbias={float(df_cross[df_cross["alpha"]==1.0]["k_bias_hi"].iloc[0]):+.3f}. '
              f'Pure V8: r={float(df_cross[df_cross["alpha"]==0.0]["r"].iloc[0])} kbias={float(df_cross[df_cross["alpha"]==0.0]["k_bias_hi"].iloc[0]):+.3f}.</div>'
              f'</div>')

    # Insert banner right after </div></div> closing the .hdr div (search for first card after header)
    insert_anchor = '<div class="grid3">'
    if insert_anchor in text and 'Recommended ensemble' not in text:
        text = text.replace(insert_anchor, banner + '\n\n' + insert_anchor, 1)
    elif 'Recommended ensemble' in text:
        # Replace existing banner if present
        text = re.sub(r'<div class="card"[^>]*>\s*<div class="cardh"[^>]*>Recommended ensemble.*?</div>\s*</div>',
                       banner, text, count=1, flags=re.DOTALL)

    # Add Ensemble column to the comparison table.
    # Locate the <thead> with V5/V6/V7/V8 headers and add an Ensemble column.
    # Header pattern (current):
    #   <th>Rk V8</th><th>Pitcher</th>
    #   <th class="num">V5 xFP</th><th class="num">V6 xFP</th><th class="num">V7 xFP</th><th class="num">V8 xFP</th>
    #   <th class="num">D(V8-V7)</th><th class="num">D(V8-V6)</th>
    #   <th class="num">2026 GS</th><th class="num">2026 actual FP</th>
    # Replace with ensemble column inserted after V8 xFP header.
    new_header = ('<th class="num">V5 xFP</th><th class="num">V6 xFP</th><th class="num">V7 xFP</th>'
                   '<th class="num">V8 xFP</th><th class="num">Ensemble</th>'
                   '<th class="num">D(V8-V7)</th><th class="num">D(V8-V6)</th>')
    old_header = ('<th class="num">V5 xFP</th><th class="num">V6 xFP</th><th class="num">V7 xFP</th>'
                   '<th class="num">V8 xFP</th>\n<th class="num">D(V8-V7)</th><th class="num">D(V8-V6)</th>')
    if old_header in text:
        text = text.replace(old_header, new_header)
    else:
        # Looser pattern - just insert ensemble before D(V8-V7)
        text = text.replace('<th class="num">V8 xFP</th>',
                              '<th class="num">V8 xFP</th><th class="num">Ensemble</th>', 1)

    # Add ensemble cell to each row. Each row has:
    #   ...V8 xFP: <td class="num"><b>X.XX</b></td><td class="num D-class">D(V8-V7)</td>...
    # We'll add after the V8 cell (which has <b> wrapping).
    # Build a per-pitcher ensemble lookup (sorted in same order as dashboard table - by xfp_v8 desc).
    proj_d = proj.copy().sort_values('xfp_v8', ascending=False).reset_index(drop=True)
    # Highlight Schlittler ensemble cell
    sch_player = sch_panel.get('player_name', None)

    # Iterate row-by-row, replacing one row at a time using the player_name embedded in the row.
    import re as _re
    rows_pattern = _re.compile(
        r'<tr>(<td class="[^"]*">[^<]*</td><td>([^<]+)</td>'           # pitcher cell
        r'<td class="num">[^<]*</td>'                                   # V5
        r'<td class="num">[^<]*</td>'                                   # V6
        r'<td class="num">[^<]*</td>'                                   # V7
        r'<td class="num"><b>[^<]*</b></td>)'                           # V8
        r'(?!<td class="num">\s*[+\-]?\d)'                              # not yet has ensemble inserted
    )
    # Map player_name -> ensemble value
    ens_map = {}
    for _, r in proj_d.iterrows():
        a = best_alpha
        v6 = r.get('xfp_v6')
        v8 = r.get('xfp_v8')
        if pd.notna(v6) and pd.notna(v8):
            ens = a * v6 + (1 - a) * v8
        elif pd.notna(v8):
            ens = v8
        elif pd.notna(v6):
            ens = v6
        else:
            ens = None
        ens_map[r['player_name']] = ens

    def add_ens_cell(m):
        prefix = m.group(1)
        player = m.group(2)
        ens = ens_map.get(player)
        if ens is None:
            cell_html = '<td class="num">-</td>'
        else:
            color = ' style="color:#ffd700"' if sch_player and player == sch_player else ''
            cell_html = f'<td class="num"{color}><b>{ens:.2f}</b></td>'
        return f'<tr>{prefix}{cell_html}'

    text = rows_pattern.sub(add_ens_cell, text)

    dash_path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
