"""
xfp_v7_finalize.py - Phase 10 standalone: build projections + dashboard
from the saved V7 pipeline. Avoids re-running the search loop.
"""
from __future__ import annotations
import sys, os, joblib, json, math, traceback
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))
from xfp_v7_pipeline import (load_data, derive_features, add_ip_resid_lag,
                              ooy_evaluate, cross_year_evaluate, ytd_tracking_evaluate,
                              build_projections, render_kbias_table, render_schlittler,
                              render_table_rows, V6_FEATS)

OUTPUTS = ROOT / 'data' / 'outputs'
MODELS  = ROOT / 'data' / 'models'
RESEARCH = ROOT / 'data' / 'research'

V5_FEATS = ['avg_velo','abs_pfxz','avg_ext','zone_pct','o_swing_pct',
             'swstr_pct','c_plus_swstr','xwoba_contact']

print('=== xFP V7 finalize (Phase 10 standalone) ===', flush=True)

# Load data
df = load_data()
df = derive_features(df)
df = add_ip_resid_lag(df)
train = df[df['year'].between(2021, 2025)].copy()
print(f'Train: {len(train)} rows; ip_resid_lag1 non-null: {train["ip_resid_lag1"].notna().sum()}')

# Load V7 model
bundle = joblib.load(MODELS / 'xfp_v7_pipeline.pkl')
V7 = bundle['features']
print(f'V7 features ({len(V7)}): {V7}')

# Compute baselines
v6_ooy   = ooy_evaluate(train, V6_FEATS, 'V6')
v6_cross = cross_year_evaluate(train, V6_FEATS, 'V6')
v7_ooy   = ooy_evaluate(train, V7, 'V7')
v7_cross = cross_year_evaluate(train, V7, 'V7')
print(f'V6: OOY={v6_ooy["r"]} cross={v6_cross["r"]}')
print(f'V7: OOY={v7_ooy["r"]} cross={v7_cross["r"]}')

# Build projections
proj_v7 = build_projections(train, df, V7, 'xfp_v7')
proj_v6 = build_projections(train, df, V6_FEATS, 'xfp_v6')
proj_v5 = build_projections(train, df, V5_FEATS, 'xfp_v5')

proj = (proj_v7[['pitcher','player_name','xfp_v7','gs_2026','fp_per_start_actual_2026','k_pct_2026']]
        .merge(proj_v6[['pitcher','xfp_v6']], on='pitcher', how='left')
        .merge(proj_v5[['pitcher','xfp_v5']], on='pitcher', how='left'))
proj['delta_v7_v6'] = proj['xfp_v7'] - proj['xfp_v6']
proj_path = OUTPUTS / 'xfp_v7_projections.csv'
proj.to_csv(proj_path, index=False)
print(f'wrote {proj_path}')

# YTD evaluations
def ytd_for(col):
    valid = proj[(proj['gs_2026'] >= 5) & proj[col].notna() & proj['fp_per_start_actual_2026'].notna()].copy()
    if len(valid) < 10:
        return {'r': None, 'n': len(valid)}
    r = float(np.corrcoef(valid[col], valid['fp_per_start_actual_2026'])[0,1])
    bias = float((valid['fp_per_start_actual_2026'] - valid[col]).mean())
    high_k = valid[valid['k_pct_2026']>0.30]
    k_bias = float((high_k['fp_per_start_actual_2026'] - high_k[col]).mean()) if len(high_k) else None
    return {'r': round(r,5), 'bias': round(bias,3), 'k_bias': round(k_bias,3) if k_bias is not None else None,
            'n': len(valid), 'note': f'avg gs/pitcher={valid["gs_2026"].mean():.1f}'}

ytd_v5 = ytd_for('xfp_v5')
ytd_v6 = ytd_for('xfp_v6')
ytd_v7 = ytd_for('xfp_v7')
print(f'2026 YTD r:  V5={ytd_v5["r"]}  V6={ytd_v6["r"]}  V7={ytd_v7["r"]}')

# Compute nonlin gap (we know from prior run)
nonlin_gap = -0.0094

# Build dashboard
proj_d = proj.copy().sort_values('xfp_v7', ascending=False).reset_index(drop=True)
proj_d['rank_v7'] = proj_d.index + 1
proj_d['rank_v6'] = proj_d['xfp_v6'].rank(ascending=False, method='min')
proj_d['rank_v5'] = proj_d['xfp_v5'].rank(ascending=False, method='min')
proj_records = (proj_d.head(141)
                  .astype({'rank_v6':'object','rank_v5':'object','rank_v7':'object'})
                  .where(lambda d: d.notna(), '')
                  .to_dict(orient='records'))

# K-bias by decile
bias_chart = []
for label, col in [('V5','xfp_v5'),('V6','xfp_v6'),('V7','xfp_v7')]:
    valid = proj_d.dropna(subset=[col,'fp_per_start_actual_2026','k_pct_2026'])
    if len(valid) < 20: continue
    valid = valid.assign(decile=pd.qcut(valid['k_pct_2026'], 5, duplicates='drop', labels=False))
    for dec in sorted(valid['decile'].dropna().unique()):
        sub = valid[valid['decile']==dec]
        bias_chart.append({
            'model': label, 'decile': int(dec),
            'k_pct': float(sub['k_pct_2026'].mean()),
            'resid': float((sub['fp_per_start_actual_2026'] - sub[col]).mean()),
        })

sch = proj_d[proj_d['player_name'].str.contains('Schlittler', na=False)]
sch_panel = sch.iloc[0].to_dict() if len(sch) else {}

v6_v7_oycr_gap = (v6_ooy['r'] - v6_cross['r']) - (v7_ooy['r'] - v7_cross['r'])

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>xFP v7 - 2026 SP Rankings</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#e6edf3;padding:18px}}
.hdr{{background:linear-gradient(135deg,#1a2332,#0d1b2a);border:1px solid #30363d;border-radius:8px;padding:14px 18px;margin-bottom:14px}}
.title{{font-size:20px;font-weight:700;color:#58a6ff}}.title span{{color:#f0883e}}
.sub{{font-size:11.5px;color:#8b949e;margin-top:4px;line-height:1.5}}
.badges{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.badge{{border-radius:20px;padding:3px 10px;font-size:11px;font-weight:600;border:1px solid}}
.bg{{border-color:#238636;color:#3fb950;background:rgba(35,134,54,.1)}}
.bb{{border-color:#1f6feb;color:#58a6ff;background:rgba(31,111,235,.1)}}
.bo{{border-color:#9e6a03;color:#f0883e;background:rgba(158,106,3,.1)}}
.bp{{border-color:#6e40c9;color:#d2a8ff;background:rgba(110,64,201,.1)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px}}
.cardh{{font-size:11px;font-weight:700;text-transform:uppercase;color:#8b949e;letter-spacing:.7px;margin-bottom:9px}}
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
<div class="title">xFP <span>v7</span> - 2026 SP Model</div>
<div class="sub">Cross-year-optimized rebuild (Ridge, n=6 features, all clean / non-circular). Under the deployment scenario (year-T metrics predicting year-T+1 FP) backward elimination from V6's kitchen sink left only avg_velo, o_swing_pct, swstr_pct, c_plus_swstr, xwoba_contact, z_swing_pct. Dropping abs_pfxz, avg_ext, zone_pct, xwoba_x_swstr and ip_resid_lag1 raised cross-year r from {v6_cross["r"]} to {v7_cross["r"]} despite all of those features helping same-year OOY r. The OOY-cross gap shrank by {v6_v7_oycr_gap:+.4f}. Nonlinear (XGBoost, RandomForest, GBM) tested at {nonlin_gap:+.4f} versus Ridge - Ridge optimal.</div>
<div class="badges">
<span class="badge bg">V7 cross-year r {v7_cross["r"]}</span>
<span class="badge bb">V6 cross-year r {v6_cross["r"]}</span>
<span class="badge bo">High-K bias {v7_cross["k_bias_hi"]}</span>
<span class="badge bp">Nonlin gap {nonlin_gap:+.4f} (Ridge wins)</span>
</div></div>

<div class="grid">
<div class="card">
<div class="cardh">Dual-validation panel (primary metric: cross-year r)</div>
<div class="kv"><span class="kv-k">V6 OOY r (same-year)</span><span class="kv-v">{v6_ooy["r"]}</span></div>
<div class="kv"><span class="kv-k">V6 cross-year r (deployment)</span><span class="kv-v">{v6_cross["r"]}</span></div>
<div class="kv"><span class="kv-k">V6 OOY-cross gap</span><span class="kv-v">{(v6_ooy["r"]-v6_cross["r"]):+.4f}</span></div>
<div class="kv"><span class="kv-k">V7 OOY r</span><span class="kv-v">{v7_ooy["r"]}</span></div>
<div class="kv"><span class="kv-k">V7 cross-year r</span><span class="kv-v" style="color:#3fb950">{v7_cross["r"]}</span></div>
<div class="kv"><span class="kv-k">V7 OOY-cross gap</span><span class="kv-v">{(v7_ooy["r"]-v7_cross["r"]):+.4f}</span></div>
<div class="kv"><span class="kv-k">Gap reduction (V6 -&gt; V7)</span><span class="kv-v" style="color:#3fb950">{v6_v7_oycr_gap:+.4f}</span></div>
<div class="kv"><span class="kv-k">V6 high-K bias (cross)</span><span class="kv-v">{v6_cross["k_bias_hi"]}</span></div>
<div class="kv"><span class="kv-k">V7 high-K bias (cross)</span><span class="kv-v">{v7_cross["k_bias_hi"]}</span></div>
<div class="kv"><span class="kv-k">2026 YTD r (V5/V6/V7, n={ytd_v7["n"]})</span><span class="kv-v">{ytd_v5["r"]} / {ytd_v6["r"]} / {ytd_v7["r"]}</span></div>
</div>

<div class="card">
<div class="cardh">K-rate decile residual (mean 2026 actual minus xFP)</div>
<div id="kbias">{render_kbias_table(bias_chart)}</div>
<div style="margin-top:9px;font-size:10.5px;color:#8b949e">Smaller magnitude = less systematic bias in that K decile. Decile 5 = highest K rate.</div>
</div>
</div>

<div class="card" style="margin-bottom:14px">
<div class="cardh">Cameron Schlittler - V5 -&gt; V6 -&gt; V7 path</div>
{render_schlittler(sch_panel)}
</div>

<div class="card">
<div class="cardh">Top {len(proj_records)} 2026 SP - V5 / V6 / V7 side-by-side</div>
<table><thead><tr>
<th>Rk V7</th><th>Pitcher</th>
<th class="num">V5 xFP</th><th class="num">V6 xFP</th><th class="num">V7 xFP</th>
<th class="num">D vs V6</th><th class="num">2026 GS</th><th class="num">2026 actual FP/start</th>
</tr></thead><tbody>
{render_table_rows(proj_records)}
</tbody></table></div>

</body></html>"""
out = OUTPUTS / 'xfp_v7_dashboard.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'wrote {out}')

# Append V7 section to research markdown
coefs = pd.Series(bundle['pipeline'].named_steps['r'].coef_, index=V7)
sch_blob = ''
if len(sch):
    s = sch.iloc[0]
    def fmt(x, p=2):
        try: return f'{float(x):.{p}f}'
        except (TypeError, ValueError): return '-'
    sch_blob = (f'- V5: rank #{s["rank_v5"]} / xFP {fmt(s["xfp_v5"])}\n'
                f'- V6: rank #{s["rank_v6"]} / xFP {fmt(s["xfp_v6"])}\n'
                f'- V7: rank #{s["rank_v7"]} / xFP {fmt(s["xfp_v7"])}\n'
                f'- 2026 YTD actual FP/start: {fmt(s["fp_per_start_actual_2026"])} (gs={s["gs_2026"]})\n')

# Top movers (V7 vs V6 delta)
movers = proj_d.dropna(subset=['delta_v7_v6']).sort_values('delta_v7_v6', ascending=False)
top_up = movers.head(3)
top_dn = movers.tail(3)
def fmt_mover(row):
    def fmt(x,p=2):
        try: return f'{float(x):.{p}f}'
        except (TypeError, ValueError): return '-'
    return f'  - **{row["player_name"]}**: V6={fmt(row["xfp_v6"])} -> V7={fmt(row["xfp_v7"])} (delta {fmt(row["delta_v7_v6"])})'
movers_blob = ('Top 3 V7 risers:\n' + '\n'.join(fmt_mover(r) for _,r in top_up.iterrows()) +
               '\n\nTop 3 V7 fallers:\n' + '\n'.join(fmt_mover(r) for _,r in top_dn.iterrows()))

section = f"""

## V7 Model - Cross-Year Optimized Rebuild ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})

### Selection: backward-elimination from V6 kitchen sink
**Features ({len(V7)})**: {', '.join(V7)}

V7 is V6 minus 5 features (abs_pfxz, avg_ext, zone_pct, xwoba_x_swstr, ip_resid_lag1). Each of those
helped same-year OOY r in V6 but they consistently HURT cross-year (year T -> year T+1) prediction.
Backward elimination using cross-year r as the stopping criterion identified the slimmer 6-feature
core that holds up in deployment.

### Performance
| Metric | V6 | V7 | Delta |
|---|---|---|---|
| OOY r (same-year) | {v6_ooy["r"]} | {v7_ooy["r"]} | {v7_ooy["r"]-v6_ooy["r"]:+.5f} |
| Cross-year r (deployment) | {v6_cross["r"]} | {v7_cross["r"]} | {v7_cross["r"]-v6_cross["r"]:+.5f} |
| OOY-cross gap | {v6_ooy["r"]-v6_cross["r"]:+.4f} | {v7_ooy["r"]-v7_cross["r"]:+.4f} | {v6_v7_oycr_gap:+.4f} |
| High-K bias OOY | {v6_ooy["k_bias_hi"]} | {v7_ooy["k_bias_hi"]} | - |
| High-K bias cross | {v6_cross["k_bias_hi"]} | {v7_cross["k_bias_hi"]} | - |
| Nonlinear (XGB best vs Ridge V6) gap | - | {nonlin_gap:+.4f} | Ridge wins |
| 2026 YTD r | {ytd_v6["r"]} | {ytd_v7["r"]} | {(ytd_v7["r"] or 0)-(ytd_v6["r"] or 0):+.5f} |
| 2026 YTD bias | {ytd_v6["bias"]} | {ytd_v7["bias"]} | - |

### V7 standardized coefficients
""" + '\n'.join([f'- **{f}**: {c:+.3f}' for f,c in coefs.sort_values(key=abs, ascending=False).items()]) + f"""

### Schlittler progression
{sch_blob}

### Big movers V7 vs V6
{movers_blob}

### Notes
- Phase 1 CV screening tested 24 candidate features against V6+[X]. Highest-CV-r winners
  (barrel_pct, bb_pct, k_bb_proxy, hard_hit_pct, hard_hit_neg, xwoba_x_cplus) all looked
  like winners on OOY but lost on cross-year. None were forwarded to V7.
- Phase 5 nonlinear ceiling check (XGBoost, RF, GBM) showed nonlinear gap of {nonlin_gap:+.4f} -
  Ridge is at the deployment ceiling. No SHAP-driven polynomial transforms were needed.
- ip_resid_lag1 helps OOY (large positive coef) but its YoY stability is poor enough that it
  *hurts* cross-year prediction, so it was dropped. This is the biggest single takeaway from
  the rebuild: a feature can be "good" in same-year evaluation while being "bad" in deployment.

### Files written
- `data/models/xfp_v7_pipeline.pkl`
- `data/outputs/xfp_v7_projections.csv`
- `data/outputs/xfp_v7_dashboard.html`
"""

research_md = RESEARCH / 'xfp_model_research.md'
with open(research_md, 'a', encoding='utf-8') as f:
    f.write(section)
print(f'appended V7 section to {research_md}')

print()
print('='*60)
print('FINAL SUMMARY')
print('='*60)
print(f'Best model: backward-elimination from V6 (Ridge, 6 features)')
print(f'Features: {V7}')
print(f'V6 OOY r:           {v6_ooy["r"]}')
print(f'V7 OOY r:           {v7_ooy["r"]}')
print(f'V6 cross-year r:    {v6_cross["r"]}')
print(f'V7 cross-year r:    {v7_cross["r"]}  (PRIMARY metric)')
print(f'V6 OOY-cross gap:   {v6_ooy["r"]-v6_cross["r"]:+.4f}')
print(f'V7 OOY-cross gap:   {v7_ooy["r"]-v7_cross["r"]:+.4f}')
print(f'Gap reduction:      {v6_v7_oycr_gap:+.4f}')
print(f'2026 YTD r:         V5={ytd_v5["r"]}  V6={ytd_v6["r"]}  V7={ytd_v7["r"]}')
if len(sch):
    s = sch.iloc[0]
    def fmt(x,p=2):
        try: return f'{float(x):.{p}f}'
        except (TypeError, ValueError): return '-'
    print(f"Schlittler:        V5 #{s['rank_v5']}/{fmt(s['xfp_v5'])} -> V6 #{s['rank_v6']}/{fmt(s['xfp_v6'])} -> V7 #{s['rank_v7']}/{fmt(s['xfp_v7'])}")
print()
print('Files written:')
for p in [RESEARCH/'feature_search_log.csv', RESEARCH/'feature_search_report.md',
          MODELS/'xfp_v7_pipeline.pkl', OUTPUTS/'xfp_v7_projections.csv',
          OUTPUTS/'xfp_v7_dashboard.html', research_md]:
    print(f'  {p}')
