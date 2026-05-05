"""Build the redesigned xFP V11 dashboard (PLV-style UI).

Generates a self-contained HTML file with React+Babel inline, embedded
projection data, three tabs (Projections / Analysis / Model Info),
quadrant charts, favorites in localStorage, and PLV color/typography.

Outputs:
  - data/outputs/xfp_v11_dashboard.html
  - xfp-model/docs/index.html  (byte-identical copy for GitHub Pages)
"""
from __future__ import annotations
import json
import shutil
from datetime import date
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROJ_CSV = ROOT / 'data' / 'outputs' / 'xfp_v11_projections.csv'
MULTI_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_v11_pipeline.pkl'
OUT_PRIMARY = ROOT / 'data' / 'outputs' / 'xfp_v11_dashboard.html'
OUT_DOCS = ROOT / 'xfp-model' / 'docs' / 'index.html'


def build_records() -> list[dict]:
    proj = pd.read_csv(PROJ_CSV)
    multi = pd.read_csv(MULTI_CSV)
    latest = (
        multi.sort_values(['pitcher', 'year'])
             .groupby('pitcher')
             .tail(1)[['pitcher', 'swstr_pct']]
    )
    proj = proj.merge(latest, on='pitcher', how='left')

    def num(v, dp=None):
        if pd.isna(v):
            return None
        v = float(v)
        return round(v, dp) if dp is not None else v

    records = []
    for _, r in proj.iterrows():
        records.append({
            'mlbId': int(r['pitcher']),
            'name': r['player_name'],
            'xfpV11': num(r['xfp_v11'], 2),
            'xfpV85': num(r['xfp_v8_5'], 2),
            'delta': num(r['delta_v11_v85'], 2),
            'stuffXfp': num(r['stuff_xfp'], 2),
            'ipPremium': num(r['ip_premium'], 2),
            'ipTrend': r['ip_trend'],
            'kPct': num(r['k_pct_2026'], 3),
            'swstrPct': num(r.get('swstr_pct'), 3),
            'gs': int(r['gs_2026']) if pd.notna(r['gs_2026']) else None,
            'fpActual': num(r['fp_per_start_actual_2026'], 2),
            'hasFG': bool(r['v11_has_pitching_plus']),
            'rollingIp': num(r['rolling_ip_last5'], 2),
        })

    records.sort(key=lambda x: -x['xfpV11'])
    for i, rec in enumerate(records):
        rec['rank'] = i + 1
    return records


def build_meta() -> dict:
    bundle = joblib.load(MODEL_PKL)
    pipe = bundle['pipeline']
    ridge = pipe.named_steps['r']
    feats = bundle['features']
    coefs = [
        {'feat': f, 'coef': round(float(c), 3)}
        for f, c in zip(feats, ridge.coef_)
    ]
    coefs.sort(key=lambda x: -abs(x['coef']))
    return {
        'features': feats,
        'coefficients': coefs,
        'intercept': round(float(ridge.intercept_), 3),
        'alpha': round(float(ridge.alpha_), 3),
        'crossYearR': round(float(bundle['cross_year_r']), 3),
        'kBiasHi': round(float(bundle['k_bias_hi']), 3),
        'scoreCurrent': round(float(bundle['score_current']), 3),
        'scoreT1': round(float(bundle['score_tolerance_T1']), 3),
        'formula': bundle['formula'],
        'trainedDate': bundle['trained_date'],
        'nTrain': int(bundle['n_train']),
        'trainingYears': bundle.get('training_years', '2020-2025'),
        'ytdR': round(float(bundle.get('ytd_r_2026', 0)), 3),
        'ytdMae': round(float(bundle.get('ytd_mae_2026', 0)), 3),
        'comparison': bundle.get('comparison'),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>SP xFP Model — V11 Production</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Source+Serif+4:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap" rel="stylesheet" />
<style>html,body{margin:0;padding:0;}*{box-sizing:border-box;}</style>
<script>
window.XFP_META = __META_JSON__;
window.XFP_PROJECTIONS = __PROJECTIONS_JSON__;
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js" crossorigin></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js" crossorigin></script>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
// ═══ Constants ════════════════════════════════════════════════════════════════
const TABS = ['projections', 'analysis', 'model'];
const TAB_LABELS = { projections: 'Projections', analysis: 'Analysis', model: 'Model Info' };
const MONO  = '"IBM Plex Mono", ui-monospace, monospace';
const SERIF = '"Source Serif 4", "Source Serif Pro", "Iowan Old Style", Georgia, serif';

const TIER = (xfp) => {
  if (xfp >= 17) return 'Elite';
  if (xfp >= 14) return 'Strong';
  if (xfp >= 11) return 'Solid';
  return 'Streamer';
};

const K_TIERS = [
  { key: 'all',     label: 'All K%' },
  { key: 'elite',   label: 'Elite K (>28%)',  test: k => k != null && k > 0.28 },
  { key: 'high',    label: 'High K (22-28%)', test: k => k != null && k >= 0.22 && k <= 0.28 },
  { key: 'contact', label: 'Contact (<22%)',  test: k => k != null && k < 0.22 },
];

// ═══ Utilities ════════════════════════════════════════════════════════════════
const fmt = (n, d = 1) => {
  if (n == null || (typeof n === 'number' && Number.isNaN(n))) return '—';
  if (typeof n !== 'number') return n;
  return n.toFixed(d);
};
const fmtPct = (n, d = 1) => n == null ? '—' : (n * 100).toFixed(d) + '%';
const fmtSign = (n, d = 2) => {
  if (n == null) return '—';
  const s = n.toFixed(d);
  return n > 0 ? '+' + s : s;
};

function pearsonR(xs, ys) {
  const n = xs.length;
  if (n < 2) return NaN;
  const mx = xs.reduce((a,b)=>a+b,0)/n, my = ys.reduce((a,b)=>a+b,0)/n;
  let num = 0, dx = 0, dy = 0;
  for (let i=0;i<n;i++){ num += (xs[i]-mx)*(ys[i]-my); dx += (xs[i]-mx)**2; dy += (ys[i]-my)**2; }
  return num / Math.sqrt(dx*dy);
}
function median(arr) {
  const s = [...arr].sort((a,b)=>a-b);
  const n = s.length;
  if (!n) return 0;
  return n % 2 ? s[(n-1)>>1] : (s[n/2-1]+s[n/2])/2;
}

function exportCSV(rows, cols, filename = 'xfp_v11_projections.csv') {
  const escape = v => {
    if (v == null) return '';
    const s = String(v);
    return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.join(',');
  const body = rows.map(r => cols.map(c => escape(r[c])).join(',')).join('\n');
  const blob = new Blob([header + '\n' + body], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function dataCell(colors, color) {
  return {
    padding: '7px 8px', textAlign: 'right',
    fontFamily: MONO, fontSize: 11, fontVariantNumeric: 'tabular-nums',
    color: color || colors.text,
  };
}
function editorialBtn(colors) {
  return {
    padding: '5px 10px', fontSize: 10, fontFamily: MONO, letterSpacing: 1.2,
    background: colors.panel, color: colors.text,
    border: `1px solid ${colors.border}`, borderRadius: 2,
    cursor: 'pointer', textTransform: 'uppercase', fontWeight: 500,
  };
}
function makeEditorialHeat(dark) {
  return (v, min, max) => {
    if (typeof v !== 'number' || Number.isNaN(v)) return 'transparent';
    const t = Math.max(0, Math.min(1, (v - min) / (max - min)));
    if (dark) {
      return t < 0.5
        ? `oklch(${0.22 + (1 - t * 2) * 0.02} 0 0 / 0)`
        : `oklch(0.55 ${0.04 + (t - 0.5) * 0.18} 35 / ${0.10 + (t - 0.5) * 0.40})`;
    }
    return t < 0.5
      ? `oklch(0.97 0 0 / 0)`
      : `oklch(0.65 ${0.04 + (t - 0.5) * 0.20} 35 / ${0.06 + (t - 0.5) * 0.30})`;
  };
}

// ═══ SortTh ═══════════════════════════════════════════════════════════════════
function SortTh({ col, label, align = 'r', width, sortCol, sortDir, onSort, colors }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)} style={{
      textAlign: align === 'l' ? 'left' : 'right', padding: '8px 8px',
      fontSize: 9, fontWeight: 600, letterSpacing: 1.5, textTransform: 'uppercase',
      fontFamily: MONO, whiteSpace: 'nowrap', minWidth: width,
      cursor: 'pointer', userSelect: 'none',
      color: active ? colors.accent : colors.dim,
      background: colors.bg,
    }}>
      {label}{active ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  );
}

// ═══ Section heading ══════════════════════════════════════════════════════════
function SectionHeading({ num, label, right, colors }) {
  return (
    <div style={{ padding: '20px 32px 10px', display:'flex', alignItems:'baseline', gap:14 }}>
      <span style={{ fontSize:10, letterSpacing:3, textTransform:'uppercase', color:colors.accent, fontFamily:MONO, flexShrink:0 }}>§ {num}</span>
      <h2 style={{ fontSize:22, fontWeight:400, margin:0, fontStyle:'italic', letterSpacing:-0.3, whiteSpace:'nowrap', flexShrink:0 }}>{label}</h2>
      <div style={{ flex:1, borderBottom:`1px solid ${colors.border}`, marginBottom:6, minWidth:20 }} />
      {right && <span style={{ fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:1, whiteSpace:'nowrap', flexShrink:0 }}>{right}</span>}
    </div>
  );
}

// ═══ Projections Table ════════════════════════════════════════════════════════
function ProjectionsTable({ rows, colors, editorialHeat, sortCol, sortDir, onSort, favorites, toggleFavorite, expanded, setExpanded }) {
  return (
    <div style={{ overflow: 'auto' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${colors.text}` }}>
            <th style={{ padding:'8px 8px', fontSize:11, color:colors.dim, width:30, textAlign:'left' }}>★</th>
            <SortTh col="rank"     label="Rk"        align="l" width={36}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="name"     label="Pitcher"   align="l" width={170} sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpV11"   label="xFP V11"   width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpV85"   label="V8.5"      width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="delta"    label="Δ"         width={48}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="stuffXfp" label="Stuff"     width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="ipPremium" label="IP Prem"  width={60}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="ipTrend"  label="Trend"     width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="kPct"     label="K%"        width={50}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="swstrPct" label="SwStr%"    width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="gs"       label="GS"        width={36}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="fpActual" label="2026 FP"   width={60}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <th style={{ padding:'8px 8px', fontSize:9, color:colors.dim, fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', fontFamily:MONO, textAlign:'center', width:30 }}>FG</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, idx) => {
            const isFav = favorites.includes(p.mlbId);
            const isExp = expanded === p.mlbId;
            const tier = TIER(p.xfpV11);
            const tierColor = tier === 'Elite' ? colors.accent : tier === 'Strong' ? colors.pos : tier === 'Solid' ? colors.text : colors.dim;
            const trendStyle = p.ipTrend === 'HIGH'
              ? { color:colors.pos, border:`1px solid ${colors.pos}` }
              : p.ipTrend === 'LOW'
              ? { color:colors.warn, border:`1px solid ${colors.warn}` }
              : { color:colors.dim, border:`1px solid ${colors.border}` };
            return (
              <React.Fragment key={p.mlbId}>
                <tr onClick={() => setExpanded(isExp ? null : p.mlbId)}
                    style={{ borderBottom: `1px solid ${colors.faint}`, cursor: 'pointer',
                             background: isExp ? colors.panel : 'transparent' }}>
                  <td style={{ padding:'7px 8px', textAlign:'center' }}>
                    <span onClick={(e) => { e.stopPropagation(); toggleFavorite(p.mlbId); }}
                      style={{ color: isFav ? colors.accent : colors.faint,
                               cursor:'pointer', fontSize:13 }}>★</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: p.rank <= 3 ? colors.accent : colors.dim }}>{p.rank}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpV11, 8, 17) }}>
                    <span style={{ fontSize:17, fontFamily:SERIF, fontStyle:'italic',
                                   color:tierColor, fontVariantNumeric:'tabular-nums' }}>
                      {fmt(p.xfpV11, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{fmt(p.xfpV85, 2)}</td>
                  <td style={dataCell(colors, p.delta > 0.05 ? colors.pos : p.delta < -0.05 ? colors.neg : colors.dim)}>
                    {fmtSign(p.delta, 2)}
                  </td>
                  <td style={dataCell(colors)}>{fmt(p.stuffXfp, 2)}</td>
                  <td style={dataCell(colors, p.ipPremium > 0.1 ? colors.pos : p.ipPremium < -0.1 ? colors.neg : colors.dim)}>
                    {fmtSign(p.ipPremium, 2)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'center' }}>
                    <span style={{ ...trendStyle, padding:'1px 6px', fontFamily:MONO,
                                   fontSize:9, letterSpacing:1, borderRadius:2 }}>
                      {p.ipTrend}
                    </span>
                  </td>
                  <td style={dataCell(colors, p.kPct == null ? colors.faint : p.kPct > 0.28 ? colors.accent : colors.text)}>
                    {p.kPct == null ? '—' : fmtPct(p.kPct, 1)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)}</td>
                  <td style={dataCell(colors, p.gs == null ? colors.faint : colors.dim)}>{p.gs ?? '—'}</td>
                  <td style={dataCell(colors, p.fpActual == null ? colors.faint : (p.gs ?? 0) >= 5 ? colors.text : colors.dim)}>
                    {(p.gs ?? 0) >= 5 ? fmt(p.fpActual, 2) : '—'}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'center', fontSize:11,
                               color: p.hasFG ? colors.pos : colors.faint }}>
                    {p.hasFG ? '✓' : '·'}
                  </td>
                </tr>
                {isExp && (
                  <tr>
                    <td colSpan={14} style={{ padding:'14px 24px', background:colors.stripe, borderBottom:`1px solid ${colors.faint}` }}>
                      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:24 }}>
                        <div>
                          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:6 }}>Tier · {tier}</div>
                          <div style={{ fontSize:13, fontStyle:'italic', color:colors.text }}>
                            xFP V11 of <span style={{ color:tierColor, fontWeight:600 }}>{fmt(p.xfpV11, 2)}</span> ranks {p.name} #{p.rank} on the pre-season board.
                          </div>
                          <div style={{ marginTop:8, fontSize:11, color:colors.dim, fontFamily:MONO }}>
                            Stuff-only baseline: {fmt(p.stuffXfp, 2)} ·
                            IP premium: {fmtSign(p.ipPremium, 2)} ·
                            Last-5 IP: {p.rollingIp == null ? '—' : fmt(p.rollingIp, 2)}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:6 }}>2026 YTD reality</div>
                          <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:'6px 14px' }}>
                            {[['GS', p.gs ?? '—'],
                              ['FP/start', (p.gs ?? 0) >= 5 ? fmt(p.fpActual, 2) : '—'],
                              ['K%', p.kPct == null ? '—' : fmtPct(p.kPct, 1)],
                              ['SwStr%', p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)],
                              ['vs V8.5', fmtSign(p.delta, 2)],
                              ['Trend', p.ipTrend]].map(([lbl, val]) => (
                              <div key={lbl}>
                                <div style={{ fontSize:8, letterSpacing:2, color:colors.dim, fontFamily:MONO, textTransform:'uppercase' }}>{lbl}</div>
                                <div style={{ fontSize:13, fontFamily:MONO, color:colors.text }}>{val}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div style={{ display:'flex', alignItems:'center', justifyContent:'flex-end', gap:8 }}>
                          <button onClick={(e) => { e.stopPropagation(); toggleFavorite(p.mlbId); }}
                            style={{ ...editorialBtn(colors),
                                     background: isFav ? colors.accent : colors.panel,
                                     color: isFav ? '#fff' : colors.text,
                                     borderColor: isFav ? colors.accent : colors.border }}>
                            ★ {isFav ? 'UNSTAR' : 'STAR'}
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ═══ Quadrant chart ═══════════════════════════════════════════════════════════
function QuadrantChart({ data, xKey, yKey, xLabel, yLabel, xCenter, yCenter, quadLabels, colors, highlightId, onHighlight, xDp = 2, yDp = 2 }) {
  const W = 720, H = 460, PAD = { top: 28, right: 130, bottom: 50, left: 70 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  const valid = data.filter(d => typeof d[xKey] === 'number' && typeof d[yKey] === 'number'
                                 && !Number.isNaN(d[xKey]) && !Number.isNaN(d[yKey]));
  if (valid.length === 0) return (
    <div style={{ padding:32, color:colors.dim, fontStyle:'italic', textAlign:'center' }}>
      No data points (need 2026 GS ≥ 5).
    </div>
  );

  const xs = valid.map(d => d[xKey]);
  const ys = valid.map(d => d[yKey]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xPad = (xMax - xMin) * 0.06 || 0.1;
  const yPad = (yMax - yMin) * 0.06 || 0.1;
  const xLo = xMin - xPad, xHi = xMax + xPad;
  const yLo = yMin - yPad, yHi = yMax + yPad;
  const xc = xCenter ?? median(xs);
  const yc = yCenter ?? median(ys);

  const sx = v => PAD.left + ((v - xLo) / (xHi - xLo)) * cw;
  const sy = v => PAD.top + ch - ((v - yLo) / (yHi - yLo)) * ch;

  const xTicks = Array.from({length:5}, (_,i) => xLo + (xHi-xLo)*(i+0.5)/5);
  const yTicks = Array.from({length:5}, (_,i) => yLo + (yHi-yLo)*(i+0.5)/5);

  const hoverPt = highlightId ? valid.find(p => p.mlbId === highlightId) : null;
  let ttx = 0, tty = 0;
  if (hoverPt) {
    const cx = sx(hoverPt[xKey]), cy = sy(hoverPt[yKey]);
    ttx = cx + 12 + 160 > W - PAD.right ? cx - 172 : cx + 12;
    tty = cy - 64 < PAD.top ? cy + 8 : cy - 64;
  }

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block' }}
         onMouseLeave={() => onHighlight(null)}>
      {yTicks.map((v,i) => (
        <line key={`gy${i}`} x1={PAD.left} x2={PAD.left+cw} y1={sy(v)} y2={sy(v)}
              stroke={colors.faint} strokeWidth={0.5} />
      ))}
      {xTicks.map((v,i) => (
        <line key={`gx${i}`} x1={sx(v)} x2={sx(v)} y1={PAD.top} y2={PAD.top+ch}
              stroke={colors.faint} strokeWidth={0.5} />
      ))}
      <line x1={PAD.left} x2={PAD.left+cw} y1={PAD.top+ch} y2={PAD.top+ch} stroke={colors.border} strokeWidth={1} />
      <line x1={PAD.left} x2={PAD.left}     y1={PAD.top}    y2={PAD.top+ch} stroke={colors.border} strokeWidth={1} />

      <line x1={sx(xc)} x2={sx(xc)} y1={PAD.top} y2={PAD.top+ch}
            stroke={colors.dim} strokeWidth={1} strokeDasharray="5 3" opacity={0.55} />
      <line x1={PAD.left} x2={PAD.left+cw} y1={sy(yc)} y2={sy(yc)}
            stroke={colors.dim} strokeWidth={1} strokeDasharray="5 3" opacity={0.55} />

      {/* quadrant labels in corners */}
      {quadLabels && (
        <>
          <text x={PAD.left+cw-6} y={PAD.top+12} textAnchor="end" fontSize={9} fill={colors.pos}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.tr}
          </text>
          <text x={PAD.left+6} y={PAD.top+12} textAnchor="start" fontSize={9} fill={colors.warn}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.tl}
          </text>
          <text x={PAD.left+cw-6} y={PAD.top+ch-6} textAnchor="end" fontSize={9} fill={colors.warn}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.br}
          </text>
          <text x={PAD.left+6} y={PAD.top+ch-6} textAnchor="start" fontSize={9} fill={colors.neg}
                fontFamily={MONO} letterSpacing={1.5} opacity={0.85}>
            {quadLabels.bl}
          </text>
        </>
      )}

      {valid.map(p => {
        const x = p[xKey], y = p[yKey];
        const isHot  = x >= xc && y >= yc;
        const isCold = x <  xc && y <  yc;
        const dotColor = p.highlighted ? colors.accent : isHot ? colors.pos : isCold ? colors.neg : colors.dim;
        const dotR = p.highlighted ? 5.5 : 3.5;
        const dimmed = highlightId && highlightId !== p.mlbId;
        return (
          <g key={p.mlbId} onMouseEnter={() => onHighlight(p.mlbId)}>
            <circle cx={sx(x)} cy={sy(y)} r={dotR} fill={dotColor}
                    opacity={dimmed ? 0.18 : p.highlighted ? 0.95 : 0.65}
                    stroke={highlightId === p.mlbId ? colors.text : 'none'} strokeWidth={1.5}
                    style={{ cursor:'pointer' }} />
            {p.highlighted && !highlightId && (
              <text x={sx(x)+7} y={sy(y)+3} fontSize={8.5} fill={dotColor} fontFamily={MONO}
                    style={{ pointerEvents:'none' }}>
                {p.name.split(',')[0]}
              </text>
            )}
          </g>
        );
      })}

      {hoverPt && (
        <g style={{ pointerEvents:'none' }}>
          <rect x={ttx} y={tty} width={160} height={62} rx={2}
                fill={colors.panel} stroke={colors.border} strokeWidth={1} opacity={0.97} />
          <text x={ttx+7} y={tty+15} fontSize={11} fill={colors.text} fontFamily={SERIF} fontStyle="italic">
            {hoverPt.name}
          </text>
          <text x={ttx+7} y={tty+30} fontSize={9} fill={colors.dim} fontFamily={MONO}>
            {xLabel}: {hoverPt[xKey].toFixed(xDp)}
          </text>
          <text x={ttx+7} y={tty+43} fontSize={9} fill={colors.dim} fontFamily={MONO}>
            {yLabel}: {hoverPt[yKey].toFixed(yDp)}
          </text>
          <text x={ttx+7} y={tty+56} fontSize={9} fill={hoverPt.ipTrend === 'HIGH' ? colors.pos : hoverPt.ipTrend === 'LOW' ? colors.warn : colors.dim} fontFamily={MONO}>
            {hoverPt.ipTrend} · K%: {hoverPt.kPct == null ? '—' : (hoverPt.kPct*100).toFixed(1)}
          </text>
        </g>
      )}

      <text x={PAD.left + cw/2} y={H-12} textAnchor="middle" fontSize={11} fill={colors.dim} fontFamily={MONO}>{xLabel}</text>
      <text x={18} y={PAD.top + ch/2} textAnchor="middle" fontSize={11} fill={colors.dim} fontFamily={MONO}
            transform={`rotate(-90 18 ${PAD.top + ch/2})`}>{yLabel}</text>
      <text x={W - PAD.right - 2} y={PAD.top - 8} textAnchor="end" fontSize={9.5} fill={colors.accent} fontFamily={MONO}>
        r = {isNaN(pearsonR(xs,ys)) ? '—' : pearsonR(xs,ys).toFixed(3)} · n = {valid.length}
      </text>
      {xTicks.map((v,i) => (
        <text key={`tx${i}`} x={sx(v)} y={PAD.top+ch+15} textAnchor="middle" fontSize={9} fill={colors.dim} fontFamily={MONO}>
          {v.toFixed(xDp)}
        </text>
      ))}
      {yTicks.map((v,i) => (
        <text key={`ty${i}`} x={PAD.left-7} y={sy(v)+3} textAnchor="end" fontSize={9} fill={colors.dim} fontFamily={MONO}>
          {v.toFixed(yDp)}
        </text>
      ))}
    </svg>
  );
}

// ═══ K% distribution chart ════════════════════════════════════════════════════
function KDistributionChart({ data, colors }) {
  const W = 720, H = 280, PAD = { top: 28, right: 30, bottom: 50, left: 60 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const valid = data.filter(d => d.kPct != null);
  if (valid.length === 0) return null;

  // Bucket K% into 12 bins from 10% to 38%
  const lo = 0.10, hi = 0.38, nBins = 14;
  const bins = Array.from({length: nBins}, () => ({ count: 0, deltaSum: 0 }));
  valid.forEach(p => {
    const t = (p.kPct - lo) / (hi - lo);
    const i = Math.max(0, Math.min(nBins-1, Math.floor(t * nBins)));
    bins[i].count += 1;
    bins[i].deltaSum += p.delta;
  });
  const maxCount = Math.max(...bins.map(b => b.count), 1);
  const bw = cw / nBins;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block' }}>
      <text x={W/2} y={18} textAnchor="middle" fontSize={11} fill={colors.dim} fontFamily={MONO}
            letterSpacing={1.5} textTransform="uppercase">
        K% distribution · bar height = pitcher count · bar fill = mean V11 - V8.5 delta
      </text>
      {bins.map((b, i) => {
        const x = PAD.left + i * bw;
        const h = (b.count / maxCount) * ch;
        const meanDelta = b.count > 0 ? b.deltaSum / b.count : 0;
        const fill = meanDelta > 0.02 ? colors.pos : meanDelta < -0.02 ? colors.neg : colors.dim;
        const opacity = Math.min(1, 0.3 + Math.abs(meanDelta) * 2);
        return (
          <g key={i}>
            <rect x={x+1} y={PAD.top+ch-h} width={bw-2} height={h}
                  fill={fill} opacity={opacity} />
            {b.count > 0 && (
              <text x={x + bw/2} y={PAD.top+ch-h-4} textAnchor="middle" fontSize={8.5}
                    fill={colors.dim} fontFamily={MONO}>
                {meanDelta >= 0 ? '+' : ''}{meanDelta.toFixed(2)}
              </text>
            )}
          </g>
        );
      })}
      <line x1={PAD.left} x2={PAD.left+cw} y1={PAD.top+ch} y2={PAD.top+ch} stroke={colors.border} strokeWidth={1} />
      {[0.12, 0.18, 0.22, 0.28, 0.32, 0.38].map((tk, i) => {
        const x = PAD.left + ((tk - lo) / (hi - lo)) * cw;
        return (
          <text key={i} x={x} y={PAD.top+ch+18} textAnchor="middle" fontSize={9} fill={colors.dim} fontFamily={MONO}>
            {(tk*100).toFixed(0)}%
          </text>
        );
      })}
      <text x={PAD.left+cw/2} y={H-8} textAnchor="middle" fontSize={10} fill={colors.dim} fontFamily={MONO}>K rate</text>
    </svg>
  );
}

// ═══ Filter Bar ═══════════════════════════════════════════════════════════════
function FilterBar({ search, setSearch, ipTrend, setIpTrend, kTier, setKTier,
                     xfpMin, setXfpMin, xfpMax, setXfpMax, favOnly, setFavOnly,
                     onReset, count, total, colors }) {
  return (
    <div style={{ padding:'10px 32px', display:'flex', gap:14, alignItems:'center',
                  fontSize:10, fontFamily:MONO, textTransform:'uppercase', letterSpacing:1.5,
                  borderBottom:`1px solid ${colors.border}`, background:colors.stripe, flexWrap:'wrap' }}>
      <div style={{ position:'relative' }}>
        <input placeholder="search pitcher..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding:'4px 10px 4px 22px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.text, fontSize:11, width:160, outline:'none',
                   fontFamily:SERIF, fontStyle:'italic' }} />
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke={colors.dim} strokeWidth="1.5"
             style={{ position:'absolute', left:7, top:8 }}>
          <circle cx="4.5" cy="4.5" r="3.5" /><path d="M7.5 7.5l2.5 2.5" strokeLinecap="round" />
        </svg>
      </div>

      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Trend
        <select value={ipTrend} onChange={e => setIpTrend(e.target.value)}
          style={{ padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:10 }}>
          <option value="all">All</option>
          <option value="HIGH">HIGH (deeper)</option>
          <option value="NORMAL">NORMAL</option>
          <option value="LOW">LOW (managed)</option>
        </select>
      </label>

      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>K%
        <select value={kTier} onChange={e => setKTier(e.target.value)}
          style={{ padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:10 }}>
          {K_TIERS.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
        </select>
      </label>

      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>xFP ≥
        <input type="number" value={xfpMin} onChange={e => setXfpMin(+e.target.value || 0)} step="0.5"
          style={{ width:50, padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11, textAlign:'right' }} />
      </label>
      <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>≤
        <input type="number" value={xfpMax} onChange={e => setXfpMax(+e.target.value || 0)} step="0.5"
          style={{ width:50, padding:'3px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                   background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11, textAlign:'right' }} />
      </label>

      <button onClick={() => setFavOnly(!favOnly)}
        style={{ padding:'3px 9px', fontSize:10, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                 border:`1px solid ${favOnly ? colors.accent : colors.border}`, borderRadius:2,
                 background: favOnly ? colors.accent : colors.panel,
                 color: favOnly ? '#fff' : colors.dim, cursor:'pointer' }}>
        ★ Favorites
      </button>

      <button onClick={onReset} style={editorialBtn(colors)}>Reset</button>

      <div style={{ flex:1 }} />
      <span style={{ color:colors.dim }}>{count} / {total} pitchers</span>
    </div>
  );
}

// ═══ Watchlist strip ══════════════════════════════════════════════════════════
function WatchlistStrip({ favorites, allRows, toggleFavorite, colors }) {
  const stars = favorites
    .map(id => allRows.find(r => r.mlbId === id))
    .filter(Boolean)
    .sort((a,b) => b.xfpV11 - a.xfpV11);
  return (
    <div style={{ padding:'12px 32px', borderBottom:`1px solid ${colors.border}`,
                  display:'flex', gap:14, alignItems:'center', flexWrap:'wrap' }}>
      <span style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>
        ★ My Watchlist
      </span>
      {stars.length === 0 ? (
        <span style={{ fontStyle:'italic', fontSize:12, color:colors.dim }}>
          None pinned. Click ★ on any row to follow.
        </span>
      ) : stars.map(p => (
        <span key={p.mlbId} style={{
          display:'inline-flex', gap:8, alignItems:'center',
          padding:'3px 10px', borderRadius:2,
          border:`1px solid ${colors.accent}`, whiteSpace:'nowrap',
        }}>
          <span style={{ fontStyle:'italic', fontSize:13 }}>{p.name}</span>
          <span style={{ fontFamily:MONO, fontSize:10, color:colors.accent }}>{fmt(p.xfpV11, 2)}</span>
          <span onClick={() => toggleFavorite(p.mlbId)}
            style={{ color:colors.faint, fontSize:13, lineHeight:1, cursor:'pointer' }}>×</span>
        </span>
      ))}
    </div>
  );
}

// ═══ Main app ═════════════════════════════════════════════════════════════════
function Dashboard({ dark }) {
  const colors = dark ? {
    bg: '#1a1815', panel: '#211e1a', stripe: '#1d1b17', border: '#34302a', text: '#f5f1ea',
    dim: '#8d8579', faint: '#3a352e', accent: '#d97757',
    pos: '#7fb069', neg: '#c1666b', warn: '#d4a945',
  } : {
    bg: '#f7f3ec', panel: '#fdfaf3', stripe: '#f3eee4', border: '#e3dccb', text: '#1a1815',
    dim: '#7a7261', faint: '#d4ccba', accent: '#a8421f',
    pos: '#56753f', neg: '#9d3540', warn: '#a8761f',
  };
  const editorialHeat = makeEditorialHeat(dark);

  const [activeTab, setActiveTab] = React.useState('projections');

  // Favorites — localStorage-backed
  const [favorites, setFavorites] = React.useState(() => {
    try {
      const raw = localStorage.getItem('xfp_favorites');
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  });
  React.useEffect(() => {
    try { localStorage.setItem('xfp_favorites', JSON.stringify(favorites)); } catch {}
  }, [favorites]);
  const toggleFavorite = (id) => setFavorites(prev =>
    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

  // Filters (shared between Projections and Analysis)
  const [search, setSearch]     = React.useState('');
  const [ipTrend, setIpTrend]   = React.useState('all');
  const [kTier, setKTier]       = React.useState('all');
  const [xfpMin, setXfpMin]     = React.useState(0);
  const [xfpMax, setXfpMax]     = React.useState(20);
  const [favOnly, setFavOnly]   = React.useState(false);

  // Projections sort + expand
  const [sortCol, setSortCol]   = React.useState('xfpV11');
  const [sortDir, setSortDir]   = React.useState('desc');
  const [expanded, setExpanded] = React.useState(null);

  // Analysis hover
  const [hoverId, setHoverId]   = React.useState(null);

  const onReset = () => {
    setSearch(''); setIpTrend('all'); setKTier('all');
    setXfpMin(0); setXfpMax(20); setFavOnly(false);
  };

  const allRows = window.XFP_PROJECTIONS;
  const meta = window.XFP_META;

  // Apply filters
  const filtered = React.useMemo(() => {
    const kFn = K_TIERS.find(t => t.key === kTier)?.test;
    let rows = allRows.filter(p => {
      if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
      if (ipTrend !== 'all' && p.ipTrend !== ipTrend) return false;
      if (kFn && !kFn(p.kPct)) return false;
      if (p.xfpV11 < xfpMin || p.xfpV11 > xfpMax) return false;
      if (favOnly && !favorites.includes(p.mlbId)) return false;
      return true;
    });
    return rows;
  }, [allRows, search, ipTrend, kTier, xfpMin, xfpMax, favOnly, favorites]);

  // Sort rows
  const sortedRows = React.useMemo(() => {
    const rows = [...filtered].sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol];
      const aNum = typeof av === 'number' ? av : (av == null ? -Infinity : null);
      const bNum = typeof bv === 'number' ? bv : (bv == null ? -Infinity : null);
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      const an = aNum == null ? -Infinity : aNum;
      const bn = bNum == null ? -Infinity : bNum;
      return sortDir === 'asc' ? an - bn : bn - an;
    });
    return rows.map((p, i) => ({ ...p, rank: i + 1 }));
  }, [filtered, sortCol, sortDir]);

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortCol(col); setSortDir('desc'); }
  }

  // Analysis tab data points
  const analysisRows = React.useMemo(() =>
    filtered.map(p => ({ ...p, highlighted: favorites.includes(p.mlbId) })),
    [filtered, favorites]);

  const ytdRows = analysisRows.filter(p => p.gs != null && p.gs >= 5 && p.fpActual != null);

  return (
    <div style={{
      background: colors.bg, color: colors.text,
      fontFamily: SERIF, fontSize: 13, lineHeight: 1.5, minHeight: '100vh',
    }}>
      {/* Masthead */}
      <div style={{ padding:'20px 32px 14px', borderBottom:`2px solid ${colors.text}`,
                    display:'flex', alignItems:'baseline', justifyContent:'space-between', gap:24, flexWrap:'wrap' }}>
        <div>
          <div style={{ fontSize:9, letterSpacing:4, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>
            V11 PRODUCTION · 2026 SEASON · BUILD {meta.trainedDate}
          </div>
          <h1 style={{ fontSize:32, fontWeight:400, margin:'2px 0 0', letterSpacing:-0.5, fontStyle:'italic', whiteSpace:'nowrap' }}>
            SP xFP Model
          </h1>
        </div>
        <div style={{ display:'flex', gap:10, alignItems:'center', fontFamily:MONO, fontSize:10,
                      letterSpacing:1.2, color:colors.dim, textTransform:'uppercase' }}>
          <span>{allRows.length} SPs</span>
          <span style={{ color:colors.faint }}>·</span>
          <span>cross-yr r {meta.crossYearR}</span>
          <span style={{ color:colors.faint }}>·</span>
          <span>YTD r {meta.ytdR}</span>
          <button onClick={() => exportCSV(sortedRows,
            ['rank','mlbId','name','xfpV11','xfpV85','delta','stuffXfp','ipPremium','ipTrend','kPct','swstrPct','gs','fpActual','hasFG'],
            'xfp_v11_projections.csv')}
            style={{ ...editorialBtn(colors), marginLeft:6 }}>CSV</button>
        </div>
      </div>

      {/* Section nav */}
      <div style={{ padding:'10px 32px', borderBottom:`1px solid ${colors.border}`,
                    display:'flex', gap:24, fontSize:10, letterSpacing:2, textTransform:'uppercase',
                    fontFamily:MONO, alignItems:'center', flexWrap:'wrap' }}>
        {TABS.map(t => (
          <span key={t} onClick={() => setActiveTab(t)} style={{
            color: activeTab === t ? colors.text : colors.dim,
            fontWeight: activeTab === t ? 600 : 400,
            cursor: 'pointer',
            borderBottom: activeTab === t ? `2px solid ${colors.accent}` : 'none',
            paddingBottom: 4, marginBottom: -11,
          }}>{TAB_LABELS[t]}</span>
        ))}
      </div>

      {(activeTab === 'projections' || activeTab === 'analysis') && (
        <>
          <FilterBar
            search={search} setSearch={setSearch}
            ipTrend={ipTrend} setIpTrend={setIpTrend}
            kTier={kTier} setKTier={setKTier}
            xfpMin={xfpMin} setXfpMin={setXfpMin}
            xfpMax={xfpMax} setXfpMax={setXfpMax}
            favOnly={favOnly} setFavOnly={setFavOnly}
            onReset={onReset} count={filtered.length} total={allRows.length} colors={colors} />
          <WatchlistStrip favorites={favorites} allRows={allRows}
            toggleFavorite={toggleFavorite} colors={colors} />
        </>
      )}

      {activeTab === 'projections' && (
        <>
          <SectionHeading num="I" label="Projections Leaderboard"
            right={`SORTED BY ${sortCol.toUpperCase()} ${sortDir === 'desc' ? '↓' : '↑'}`} colors={colors} />
          <div style={{ padding:'0 32px 24px' }}>
            <ProjectionsTable rows={sortedRows} colors={colors} editorialHeat={editorialHeat}
              sortCol={sortCol} sortDir={sortDir} onSort={handleSort}
              favorites={favorites} toggleFavorite={toggleFavorite}
              expanded={expanded} setExpanded={setExpanded} />
            <div style={{ paddingTop:10, fontSize:10, color:colors.dim, fontFamily:MONO,
                          letterSpacing:1, textAlign:'right' }}>
              ↳ CLICK ROW TO EXPAND · ★ TO PIN · CLICK HEADER TO SORT
            </div>
          </div>
        </>
      )}

      {activeTab === 'analysis' && (
        <AnalysisTab rows={analysisRows} ytdRows={ytdRows} colors={colors}
          hoverId={hoverId} setHoverId={setHoverId} setActiveTab={setActiveTab} />
      )}

      {activeTab === 'model' && <ModelTab meta={meta} colors={colors} />}

      <div style={{ padding:'24px 32px', borderTop:`1px solid ${colors.border}`, marginTop:32,
                    fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:1, textTransform:'uppercase' }}>
        SP-only model · Statcast + FanGraphs Pitching+ · separate from PLV dashboard ·
        <a href="https://github.com/Kejjeh/xfp-model" style={{ color:colors.accent, marginLeft:6 }}>github.com/Kejjeh/xfp-model</a>
      </div>
    </div>
  );
}

// ═══ Analysis tab ═════════════════════════════════════════════════════════════
function AnalysisTab({ rows, ytdRows, colors, hoverId, setHoverId }) {
  return (
    <>
      <SectionHeading num="I" label="Projection vs Reality"
        right={`2026 YTD · n=${ytdRows.length} (gs ≥ 5)`} colors={colors} />
      <div style={{ padding:'0 32px 18px' }}>
        <QuadrantChart data={ytdRows} xKey="xfpV11" yKey="fpActual"
          xLabel="xFP V11 (projected FP/start)" yLabel="2026 actual FP/start"
          colors={colors} highlightId={hoverId} onHighlight={setHoverId}
          xDp={2} yDp={2}
          quadLabels={{ tr:'DELIVERING', tl:'OUTPERFORMING', br:'UNDERPERFORMING', bl:'AVOID' }} />
      </div>

      <SectionHeading num="II" label="Stuff vs Durability"
        right={`n=${rows.length}`} colors={colors} />
      <div style={{ padding:'0 32px 18px' }}>
        <QuadrantChart data={rows} xKey="stuffXfp" yKey="ipPremium"
          xLabel="Stuff xFP (pure stuff @ league avg IP)"
          yLabel="IP premium (FP from going deeper)"
          xCenter={null} yCenter={0}
          colors={colors} highlightId={hoverId} onHighlight={setHoverId}
          xDp={2} yDp={2}
          quadLabels={{ tr:'WORKHORSES', tl:'VOLUME ARMS', br:'STUFF SPECIALISTS', bl:'STREAMERS' }} />
      </div>

      <SectionHeading num="III" label="K% Distribution · V11 vs V8.5"
        right="bar fill = mean delta per K bucket" colors={colors} />
      <div style={{ padding:'0 32px 32px' }}>
        <KDistributionChart data={rows} colors={colors} />
        <div style={{ paddingTop:12, fontSize:11, color:colors.dim, fontStyle:'italic' }}>
          The k_bias warning was a cross-year artifact: V11 does <em>not</em> systematically lift
          high-K pitchers at projection time. Mean V11−V8.5 delta is roughly flat across the K
          distribution; in fact V11 trims a few high-K guys slightly. Each bar shows the count of
          pitchers in that K bucket; the fill color shows the average xFP delta within that bucket.
        </div>
      </div>
    </>
  );
}

// ═══ Model Info tab ═══════════════════════════════════════════════════════════
function ModelTab({ meta, colors }) {
  const accuracyRows = [
    { metric: 'Cross-year r',         v8: 0.558, v85: 0.600, v11: meta.crossYearR },
    { metric: 'k_bias_hi',            v8: 0.241, v85: 0.466, v11: meta.kBiasHi },
    { metric: 'Score (T=1.0)',        v8: 1.800, v85: 1.800, v11: meta.scoreT1 },
    { metric: '2026 YTD r (gs ≥ 5)',  v8: null,  v85: 0.475, v11: meta.ytdR },
    { metric: '2026 YTD MAE',         v8: null,  v85: 3.484, v11: meta.ytdMae },
  ];
  const archetypes = [
    { name: 'Schlittler',  takeaway: 'Mid-season swstr surge (+4.4 ppt 2025→2026); blended 2026 inputs lifted V11.' },
    { name: 'Glasnow',     takeaway: 'Healthy stuff; V11 captures the velo + pitching_plus jump.' },
    { name: 'Imanaga',     takeaway: 'Sample-weighted blend of 2025+2026 raises projection; FG Pitching+ supports.' },
    { name: 'Fried',       takeaway: 'Contact-manager archetype; bb_pfxz + xwoba_per_pa keep him appropriately scored.' },
    { name: 'Woodruff',    takeaway: 'Process model can\'t see injury — known overprojection until Phase 13 (injury history).' },
    { name: 'Ragans',      takeaway: 'Same archetype as Woodruff: stuff still grades elite, but availability is unsolved.' },
  ];
  const versions = [
    { v: 'V8',   feats: '4-feat core (swstr, c_plus_swstr, xwoba_per_pa, xwoba_x_swstr)', r: 0.558, status: 'frozen' },
    { v: 'V8.5', feats: 'V8 + bb_pfxz + pfxz_spread + pitch_entropy + ip_resid_lag1 + k_pct_lag1 (+ lag interactions)',  r: 0.600, status: 'superseded' },
    { v: 'V11',  feats: 'V8.5 + pitching_plus + fp_strike_pct (14 features total)', r: 0.614, status: 'production' },
  ];

  return (
    <>
      <SectionHeading num="I" label="Accuracy" right="V8 / V8.5 / V11 SIDE-BY-SIDE" colors={colors} />
      <div style={{ padding:'0 32px 24px' }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16, marginBottom:18 }}>
          {[
            { lbl: 'Cross-year r', v: meta.crossYearR, sub: 'leave-one-out 2015-2025 transitions, n=854' },
            { lbl: '2026 YTD r',   v: meta.ytdR, sub: 'live deployment correlation, gs ≥ 5' },
            { lbl: '2026 YTD MAE', v: meta.ytdMae, sub: 'mean absolute error, FP/start' },
          ].map(c => (
            <div key={c.lbl} style={{ borderTop:`2px solid ${colors.accent}`, paddingTop:8 }}>
              <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>{c.lbl}</div>
              <div style={{ fontSize:30, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, lineHeight:1.1, marginTop:4 }}>
                {typeof c.v === 'number' ? c.v.toFixed(3) : '—'}
              </div>
              <div style={{ fontSize:10, color:colors.dim, fontStyle:'italic', marginTop:4 }}>{c.sub}</div>
            </div>
          ))}
        </div>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Metric</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>V8 (frozen)</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>V8.5</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>V11 (prod)</th>
            </tr>
          </thead>
          <tbody>
            {accuracyRows.map(r => (
              <tr key={r.metric} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                <td style={{ padding:'7px 8px', fontSize:13 }}>{r.metric}</td>
                <td style={{ ...dataCell(colors, colors.dim) }}>{r.v8 == null ? '—' : r.v8.toFixed(3)}</td>
                <td style={{ ...dataCell(colors, colors.dim) }}>{r.v85.toFixed(3)}</td>
                <td style={{ ...dataCell(colors, colors.accent), fontWeight:600 }}>{r.v11.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="II" label="Features & Coefficients"
        right={`${meta.features.length} features · alpha=${meta.alpha} · intercept=${meta.intercept}`} colors={colors} />
      <div style={{ padding:'0 32px 24px' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Feature</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Standardized coef</th>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Direction</th>
            </tr>
          </thead>
          <tbody>
            {meta.coefficients.map(c => (
              <tr key={c.feat} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                <td style={{ padding:'7px 8px', fontSize:13, fontFamily:MONO }}>{c.feat}</td>
                <td style={{ ...dataCell(colors, c.coef > 0 ? colors.pos : colors.neg), fontWeight:600 }}>
                  {c.coef > 0 ? '+' : ''}{c.coef.toFixed(3)}
                </td>
                <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim }}>
                  {c.coef > 0 ? '↑ raises xFP' : '↓ lowers xFP'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="III" label="Archetype Notes" colors={colors} />
      <div style={{ padding:'0 32px 24px', display:'grid', gridTemplateColumns:'repeat(2, 1fr)', gap:16 }}>
        {archetypes.map(a => (
          <div key={a.name} style={{ borderTop:`1px solid ${colors.faint}`, paddingTop:8 }}>
            <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>Archetype</div>
            <div style={{ fontSize:18, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, marginTop:2 }}>{a.name}</div>
            <div style={{ fontSize:12, color:colors.text, marginTop:6, lineHeight:1.5 }}>{a.takeaway}</div>
          </div>
        ))}
      </div>

      <SectionHeading num="IV" label="Version History" colors={colors} />
      <div style={{ padding:'0 32px 24px' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Ver</th>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Features</th>
              <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Cross-yr r</th>
              <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {versions.map(v => (
              <tr key={v.v} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                <td style={{ padding:'7px 8px', fontSize:13, fontFamily:MONO, fontWeight:600,
                             color: v.status === 'production' ? colors.accent : colors.text }}>{v.v}</td>
                <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim }}>{v.feats}</td>
                <td style={dataCell(colors, v.status === 'production' ? colors.accent : colors.text)}>{v.r.toFixed(3)}</td>
                <td style={{ padding:'7px 8px', fontSize:10, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                             color: v.status === 'production' ? colors.accent : v.status === 'superseded' ? colors.dim : colors.warn }}>
                  {v.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="V" label="Methodology" colors={colors} />
      <div style={{ padding:'0 32px 32px', display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
        <div>
          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Scoring Formula</div>
          <div style={{ fontSize:13, fontFamily:MONO, color:colors.text, padding:'10px 14px',
                        background:colors.stripe, borderLeft:`3px solid ${colors.accent}` }}>
            ESPN: K×1 + IP×3.3 − H×1 − ER×2 − BB×1 − HBP×1
          </div>
          <div style={{ fontSize:12, color:colors.dim, marginTop:12, lineHeight:1.6, fontStyle:'italic' }}>
            V11 is a Ridge regression (StandardScaler → RidgeCV α={meta.alpha}) trained on
            {' '}{meta.nTrain} SP-seasons from {meta.trainingYears}. Mid-season inputs are
            sample-weighted blends of 2025 + 2026 (V8.1 layer). The non-circular constraint forbids
            per-start K/IP/H/ER/BB/HBP from appearing as features.
          </div>
        </div>
        <div>
          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Refresh Mid-Season</div>
          <pre style={{ fontSize:11, fontFamily:MONO, color:colors.text, padding:'10px 14px',
                        background:colors.stripe, borderLeft:`3px solid ${colors.accent}`,
                        margin:0, whiteSpace:'pre-wrap', lineHeight:1.5 }}>{`# 1. FanGraphs Pitching+ (undetected-chromedriver)
python scripts/xfp/pull_fg_undetected.py

# 2. Re-aggregate Statcast if 2026.parquet refreshed
python scripts/xfp/build_sp_multiyr.py

# 3. Re-blend, re-project, rebuild dashboard
python scripts/xfp/xfp_v11_lock.py
python scripts/xfp/build_v11_dashboard_v2.py

# 4. Push to refresh GitHub Pages
git -C xfp-model add docs/index.html
git -C xfp-model commit -m "data: refresh"
git -C xfp-model push`}</pre>
        </div>
      </div>
    </>
  );
}

// ═══ Theme toggle + root ══════════════════════════════════════════════════════
function ThemeToggle({ dark, setDark }) {
  return (
    <div style={{
      position:'fixed', top:10, right:14, zIndex:100,
      display:'flex', gap:4, padding:3, borderRadius:6,
      background:'rgba(255,255,255,0.85)', border:'1px solid rgba(0,0,0,.1)',
      fontFamily:'monospace', fontSize:11,
    }}>
      {['Light', 'Dark'].map((m, i) => {
        const active = dark === (i === 1);
        return (
          <button key={m} onClick={() => setDark(i === 1)} style={{
            padding:'3px 10px', borderRadius:4, border:'none', cursor:'pointer',
            background: active ? '#1a1a1a' : 'transparent',
            color: active ? '#fff' : '#555', fontWeight:500, fontSize:11,
          }}>{m}</button>
        );
      })}
    </div>
  );
}

function App() {
  const [dark, setDark] = React.useState(false);
  return (
    <div style={{ position:'relative', minHeight:'100vh' }}>
      <ThemeToggle dark={dark} setDark={setDark} />
      <Dashboard dark={dark} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>
"""


def main():
    records = build_records()
    meta = build_meta()
    proj_json = json.dumps(records, separators=(',', ':'))
    meta_json = json.dumps(meta, separators=(',', ':'))

    html = (HTML_TEMPLATE
            .replace('__PROJECTIONS_JSON__', proj_json)
            .replace('__META_JSON__', meta_json))

    OUT_PRIMARY.write_text(html, encoding='utf-8')
    OUT_DOCS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT_PRIMARY, OUT_DOCS)

    size_kb = OUT_PRIMARY.stat().st_size // 1024
    primary_bytes = OUT_PRIMARY.read_bytes()
    docs_bytes = OUT_DOCS.read_bytes()
    assert primary_bytes == docs_bytes, "primary and docs HTML are not byte-identical"

    print(f"wrote {OUT_PRIMARY} ({size_kb} KB, {len(records)} pitchers)")
    print(f"wrote {OUT_DOCS} (byte-identical)")


if __name__ == '__main__':
    main()
