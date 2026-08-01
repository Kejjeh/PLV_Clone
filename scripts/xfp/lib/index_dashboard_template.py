"""Verbatim home of the index-dashboard HTML/React template (audit T48).

`render_app()` returns the template string previously assigned to
`HTML_TEMPLATE` at module level in scripts/xfp/build_index_dashboard.py
(lines 861-4383 pre-extraction). The literal was MOVED byte-for-byte --
same r-prefix, same quotes, same whitespace -- wrapped in exactly
`def render_app():` + `    return (` ... `)`. It takes NO parameters because
the AST enumeration of the literal found ZERO FormattedValue interpolation
points and ZERO free names: it is a RAW (r\"\"\") ast.Constant, deliberately NOT
an f-string, so every `{}` in the JSX is literal and there is no
brace-doubling hazard. Substitution is the 12 named __TOKEN__ .replace()
calls in build_index_dashboard.main();
tests/test_index_dashboard_template.py keeps that token interface in sync.

One-time extraction proof (2026-08-01, T48 second attempt), all offline:
  (a) SOURCE IDENTITY -- the AST-extracted source segment of this module's
      string constant == the AST-extracted HTML_TEMPLATE literal from
      `git show 8dc9200:scripts/xfp/build_index_dashboard.py`, byte-for-byte.
      The ONLY transform applied to either side is CRLF->LF normalisation of
      on-disk working copies (undoing core.autocrlf=true checkout; git blobs
      are LF); the `return (`/`)` wrapper never enters the comparison because
      both sides are source segments of the string-literal AST node alone.
      201407 chars / 204573 UTF-8 bytes,
      sha256 7e501a8d30bd80d41fdb1664a9ff576107e3b4908480c96016104a8a0bd2da22.
  (b) FREE-VARIABLE COMPLETENESS -- enumerated free-name set of the literal
      == render_app's parameter set == set() (empty), and the call site
      passes exactly that: `HTML_TEMPLATE = render_app()`.
  (c) SYNTHETIC-NAMESPACE A/B -- a function reconstructed by exec() around
      the git-HEAD literal and this module's render_app were evaluated on
      the same (empty, because there are no free variables) namespace;
      outputs byte-identical (201400 chars,
      value sha256 ff303f6f552c1200ad7515bd9fe0ee2eeea60675b9b03429b1b12219d48030fc).
"""


def render_app():
    return (r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>xFP Model — Ligers</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Source+Serif+4:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap" rel="stylesheet" />
<style>html,body{margin:0;padding:0;}*{box-sizing:border-box;}
/* Pre-React shell paint (2026-07-23): the React app mounts a beat after Babel
   transpiles, so paint the correct theme background immediately to avoid a
   white flash. Dark is the default; the boot script sets [data-theme=light]
   from the shared xfp_theme key before first paint. */
body{background:#1a1815;color:#f5f1ea;}
html[data-theme="light"] body{background:#f7f3ec;color:#1a1815;}
/* Top-nav strip — now uses the shared suite palette (was a third, GitHub-dark
   palette; audit 2026-07-23) with a light-theme override so it tracks the toggle. */
.xfp-topnav-bar { background:#211e1a; border-bottom:1px solid #34302a;
  padding:.55em 1em; display:flex; justify-content:flex-end; }
.xfp-topnav-bar nav.topnav { display:flex; align-items:center; gap:0;
  font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:.72em;
  text-transform:uppercase; letter-spacing:.15em; }
.xfp-topnav-bar nav.topnav a { color:#b3a996; text-decoration:none;
  padding:.35em .9em; border:1px solid #34302a; border-right:0; }
.xfp-topnav-bar nav.topnav a:first-child { border-radius:3px 0 0 3px; }
.xfp-topnav-bar nav.topnav a:last-child  { border-radius:0 3px 3px 0;
  border-right:1px solid #34302a; }
.xfp-topnav-bar nav.topnav a:hover { color:#f5f1ea; background:#1a1815; }
.xfp-topnav-bar nav.topnav a.current { color:#d97757; background:#1a1815;
  border-color:#d97757; }
html[data-theme="light"] .xfp-topnav-bar { background:#fdfaf3; border-bottom-color:#e3dccb; }
html[data-theme="light"] .xfp-topnav-bar nav.topnav a { color:#6e6654; border-color:#e3dccb; }
html[data-theme="light"] .xfp-topnav-bar nav.topnav a:hover { color:#1a1815; background:#f7f3ec; }
html[data-theme="light"] .xfp-topnav-bar nav.topnav a.current { color:#a8421f; background:#f7f3ec; border-color:#a8421f; }
</style>
__THEME_BOOT__
<script>
window.XFP_META = __META_JSON__;
window.XFP_H2_META = __H2_META_JSON__;
window.XFP_PROJECTIONS = __PROJECTIONS_JSON__;
window.XFP_HITTERS = __HITTERS_JSON__;
window.XFP_RELIEVERS = __RELIEVERS_JSON__;
window.XFP_MY_TEAM = __MY_TEAM_JSON__;
window.XFP_AUDIT = __AUDIT_JSON__;
window.XFP_ADVISORY = __ADVISORY_JSON__;
window.XFP_WEEKLY = __WEEKLY_JSON__;
window.XFP_DECISION = __DECISION_JSON__;
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js" crossorigin></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js" crossorigin></script>
<!-- JSX PRE-TRANSPILE — DEFERRED (item 8, 2026-07-04). The <script type="text/babel">
     block below (~lines 812-3983) is transpiled in-browser by babel-standalone.
     Pre-transpiling it (extract the block to index_app.jsx, `npx @babel/cli
     --presets @babel/preset-react`, embed the compiled JS as a plain <script>,
     and drop this babel-standalone tag) would remove the ~1s in-browser
     transpile + the cdnjs babel dependency. It is TRACTABLE — the block is pure
     JSX with NO Python-format interpolation (data is injected via the separate
     window.XFP_* placeholder script above using .replace(), not .format()). It
     was deferred because doing it correctly adds a per-refresh Node build step
     (or a committed compiled asset with a freshness guard) to the daily PYTHON
     refresh — a fragility tradeoff on the flagship dashboard not worth taking in
     a broad sweep. Do it as a dedicated change with its own verification. -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js" crossorigin></script>
</head>
<body>
<div class="xfp-topnav-bar">
  __TOPNAV__
</div>
<div id="root"></div>
<script type="text/babel">
// ═══ Constants ════════════════════════════════════════════════════════════════
const TABS = ['my-team', 'decision', 'audit', 'projections', 'hitters', 'analysis', 'advisory', 'model'];
const TAB_LABELS = { 'my-team': 'My Team', decision: 'Decision', audit: 'Team Audit', projections: 'Pitchers', hitters: 'Hitters', analysis: 'Analysis', advisory: 'Advisory', model: 'Model Info' };
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
            <SortTh col="rosTotalFp"     label="Proj FP"   width={86}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="rosReplDeltaTotal" label="Δ Repl FP" width={80}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="signal"   label="Sig"       width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpRoS"   label="RoS/St"    width={86}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpRoSSched" label="Sched"  width={64}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="recencyGap" label="L21Δ"    width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="gsToDate" label="GS-to"     width={48}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpV12"   label="xFP"       width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="replDelta" label="Δ Repl/St" width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="xfpV11"   label="prev"      width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="il60Lag1" label="IL60"      width={48}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="fpTotal"  label="FP Total"  width={64}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="delta"    label="Δ vs Act"  width={64}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="stuffXfp" label="Stuff"     width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="ipPremium" label="IP Prem"  width={60}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="ipTrend"  label="Trend"     width={70}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="kPct"     label="K%"        width={50}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="swstrPct" label="SwStr%"    width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="gs"       label="GS"        width={36}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="fpActual" label="2026 FP"   width={60}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <SortTh col="roster"  label="Own"        width={56}  sortCol={sortCol} sortDir={sortDir} onSort={onSort} colors={colors} />
            <th style={{ padding:'8px 8px', fontSize:9, color:colors.dim, fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', fontFamily:MONO, textAlign:'center', width:30 }}>FG</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, idx) => {
            const isFav = favorites.includes(p.mlbId);
            const isExp = expanded === p.mlbId;
            const tier = TIER(p.xfpV12);
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
                    {p.dataQualityTag && String(p.dataQualityTag).startsWith('marcel') && (
                      <span title="Suppressed Marcel prior (IL / no recent sample) — NOT a real projection; rank by Stuff+ instead (gotcha #1)"
                            style={{ marginLeft:6, fontSize:9, fontFamily:MONO, letterSpacing:1,
                                     padding:'1px 4px', border:`1px solid ${colors.faint}`,
                                     color:colors.faint, borderRadius:2 }}>LOW-CONF</span>
                    )}
                    {p.priorSource === 'milb_translation' && (
                      <span title="Prior derived from AAA stats (no recent MLB sample)"
                            style={{ marginLeft:6, fontSize:9, fontFamily:MONO, letterSpacing:1,
                                     padding:'1px 4px', border:`1px solid ${colors.accent}`,
                                     color:colors.accent, borderRadius:2 }}>MiLB</span>
                    )}
                    {p.slumpPct != null && p.slumpPct < 20 && p.slumpBouncePct != null && p.slumpBouncePct >= 70 && (
                      <span title={`Cold streak at ${p.slumpPct}-th percentile of his career; ${p.slumpBouncePct}% historical bounce-back over next 100 IP`}
                            style={{ marginLeft:6, fontSize:9, fontFamily:MONO, letterSpacing:1,
                                     padding:'1px 4px', border:`1px solid ${colors.pos}`,
                                     color:colors.pos, borderRadius:2 }}>BUY-LOW</span>
                    )}
                    {p.slumpPct != null && p.slumpPct < 5 && p.slumpBouncePct != null && p.slumpBouncePct < 50 && (
                      <span title={`Cold streak at ${p.slumpPct}-th percentile; only ${p.slumpBouncePct}% bounce-back rate — possible regime change`}
                            style={{ marginLeft:6, fontSize:9, fontFamily:MONO, letterSpacing:1,
                                     padding:'1px 4px', border:`1px solid ${colors.warn}`,
                                     color:colors.warn, borderRadius:2 }}>FADE</span>
                    )}
                  </td>
                  {/* HEADLINE: Projected total RoS FP (= xfpRoS × est remaining starts) */}
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.rosTotalFp, 100, 350) }}>
                    <span style={{ fontSize:17, fontFamily:SERIF, fontStyle:'italic',
                                   color: p.rosTotalFp != null ? colors.accent : colors.faint,
                                   fontVariantNumeric:'tabular-nums' }}>
                      {p.rosTotalFp == null ? '—' : fmt(p.rosTotalFp, 0)}
                    </span>
                  </td>
                  {/* Δ Repl FP (total) */}
                  <td style={dataCell(colors,
                      p.rosReplDeltaTotal == null ? colors.faint :
                      p.rosReplDeltaTotal > 0 ? colors.pos : colors.warn)}>
                    {p.rosReplDeltaTotal == null ? '—' : fmtSign(p.rosReplDeltaTotal, 0)}
                  </td>
                  <td style={{ padding:'5px 6px', textAlign:'center' }}>
                    {(() => {
                      const s = p.signal || 'hold';
                      const styles = {
                        add:  { color:colors.accent, border:`1px solid ${colors.accent}` },
                        hold: { color:colors.dim,    border:`1px solid ${colors.border}` },
                        drop: { color:colors.warn,   border:`1px solid ${colors.warn}` },
                        il:   { color:colors.neg,    border:`1px solid ${colors.neg}` },
                      };
                      const lbl = s === 'il' ? 'IL' : s.toUpperCase();
                      return (
                        <span style={{ ...(styles[s] || styles.hold), padding:'1px 6px',
                                       fontFamily:MONO, fontSize:9, letterSpacing:1, borderRadius:2,
                                       whiteSpace:'nowrap' }}>
                          {lbl}
                        </span>
                      );
                    })()}
                  </td>
                  {/* Per-start RoS rate (with CI bounds) */}
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpRoS, 8, 17) }}>
                    <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', lineHeight:1.0 }}>
                      <span style={{ fontSize:13, fontFamily:SERIF, fontStyle:'italic',
                                     color: p.xfpRoS != null ? colors.text : colors.faint }}>
                        {p.xfpRoS == null ? '—' : fmt(p.xfpRoS, 2)}
                      </span>
                      {p.xfpRoSp25 != null && p.xfpRoSp75 != null && (
                        <span style={{ fontSize:9, color:colors.dim, fontFamily:MONO, marginTop:2 }}>
                          {fmt(p.xfpRoSp25, 1)}–{fmt(p.xfpRoSp75, 1)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={dataCell(colors,
                      p.xfpRoSSched == null ? colors.faint : colors.text)}>
                    {p.xfpRoSSched == null ? '—' :
                      <span title={p.nextOpp ? `next: ${p.nextOpp}` : ''}>
                        {fmt(p.xfpRoSSched, 2)}
                      </span>}
                  </td>
                  <td style={dataCell(colors,
                      p.recencyGap == null ? colors.faint :
                      p.recencyGap > 0.5 ? colors.pos :
                      p.recencyGap < -0.5 ? colors.warn : colors.dim)}>
                    {p.recencyGap == null ? '—' : fmtSign(p.recencyGap, 1)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.gsToDate ?? '—'}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right' }}>
                    <span style={{ fontSize:13, fontFamily:SERIF, fontStyle:'italic',
                                   color:tierColor, fontVariantNumeric:'tabular-nums' }}>
                      {fmt(p.xfpV12, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors,
                      p.replDelta == null ? colors.faint :
                      p.replDelta > 0 ? colors.pos :
                      colors.warn)}>
                    {p.replDelta == null ? '—' : fmtSign(p.replDelta, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{fmt(p.xfpV11, 2)}</td>
                  <td style={dataCell(colors, p.il60Lag1 > 0 ? colors.warn : colors.faint)}>
                    {p.il60Lag1 > 0 ? p.il60Lag1 : '—'}
                  </td>
                  <td style={dataCell(colors, p.fpTotal == null ? colors.faint : colors.text)}>
                    {p.fpTotal == null ? '—' : fmt(p.fpTotal, 1)}
                  </td>
                  <td style={dataCell(colors, p.delta == null ? colors.faint : p.delta > 0.5 ? colors.neg : p.delta < -0.5 ? colors.pos : colors.dim)}>
                    {p.delta == null ? '—' : fmtSign(p.delta, 2)}
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
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {p.roster === 'mine' ? (
                      <span style={{ padding:'1px 6px', border:`1px solid ${colors.accent}`,
                                     color:colors.accent, fontFamily:MONO, fontSize:9,
                                     letterSpacing:1, borderRadius:2, whiteSpace:'nowrap' }}>
                        ★ MINE
                      </span>
                    ) : p.roster === 'taken' ? (
                      <span title={p.taken_by_team ? `Rostered by ${p.taken_by_team}` : 'Rostered by another team'}
                            style={{ color:colors.dim, fontFamily:MONO, fontSize:9, letterSpacing:0.5,
                                     whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis',
                                     display:'inline-block', maxWidth:64, verticalAlign:'bottom' }}>
                        {p.taken_by_team || 'TAKEN'}
                      </span>
                    ) : (
                      <span style={{ color:colors.faint, fontFamily:MONO, fontSize:9, letterSpacing:1 }}>—</span>
                    )}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'center', fontSize:11,
                               color: p.hasFG ? colors.pos : colors.faint }}>
                    {p.hasFG ? '✓' : '·'}
                  </td>
                </tr>
                {isExp && (
                  <tr>
                    <td colSpan={19} style={{ padding:'14px 24px', background:colors.stripe, borderBottom:`1px solid ${colors.faint}` }}>
                      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:24 }}>
                        <div>
                          <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:6 }}>Tier · {tier}</div>
                          <div style={{ fontSize:13, fontStyle:'italic', color:colors.text }}>
                            prior-season xFP of <span style={{ color:tierColor, fontWeight:600 }}>{fmt(p.xfpV11, 2)}</span> ranks {p.name} #{p.rank} on the pre-season board.
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
                              ['FP total', p.fpTotal == null ? '—' : fmt(p.fpTotal, 1)],
                              ['K%', p.kPct == null ? '—' : fmtPct(p.kPct, 1)],
                              ['SwStr%', p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)],
                              ['Δ vs actual', p.delta == null ? '—' : fmtSign(p.delta, 2)],
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
  const valid = data.filter(d => d.kPct != null && d.delta != null);
  if (valid.length === 0) return null;

  // Bucket K% into bins from 10% to 38%, mean residual per bucket.
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
        K% bucket · bar height = pitcher count · fill = mean (V11 − actual)
      </text>
      {bins.map((b, i) => {
        const x = PAD.left + i * bw;
        const h = (b.count / maxCount) * ch;
        const meanDelta = b.count > 0 ? b.deltaSum / b.count : 0;
        // Positive residual = V11 over-projecting (red), negative = pitchers
        // outperforming projection (green).
        const fill = meanDelta > 0.5 ? colors.neg : meanDelta < -0.5 ? colors.pos : colors.dim;
        const opacity = Math.min(1, 0.3 + Math.abs(meanDelta) * 0.4);
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
                     roster, setRoster, hasMyTeam, onReset, count, total, colors }) {
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

      {hasMyTeam && (
        <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Roster
          {[
            { k:'all',   l:'All' },
            { k:'mine',  l:'My Team' },
            { k:'fa',    l:'Free Agents' },
            { k:'taken', l:'Other Teams' },
          ].map(opt => (
            <button key={opt.k} onClick={() => setRoster(opt.k)}
              style={{ padding:'3px 8px', fontSize:10, fontFamily:MONO, letterSpacing:1,
                       textTransform:'uppercase',
                       border:`1px solid ${roster===opt.k ? colors.accent : colors.border}`,
                       borderRadius:2,
                       background: roster===opt.k ? colors.accent : colors.panel,
                       color: roster===opt.k ? '#fff' : colors.dim, cursor:'pointer' }}>
              {opt.l}
            </button>
          ))}
        </label>
      )}

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

  const myTeam = window.XFP_MY_TEAM || { teamName: null, pitchers: [] };
  const hasMyTeam = !!(myTeam.teamName && myTeam.pitchers && myTeam.pitchers.length);
  const [activeTab, setActiveTab] = React.useState(hasMyTeam ? 'my-team' : 'projections');

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
  const [roster, setRoster]     = React.useState('all'); // 'all' | 'mine' | 'other'

  // Projections sort + expand
  const [sortCol, setSortCol]   = React.useState('rosTotalFp');
  const [sortDir, setSortDir]   = React.useState('desc');
  const [expanded, setExpanded] = React.useState(null);

  // Analysis hover
  const [hoverId, setHoverId]   = React.useState(null);

  const onReset = () => {
    setSearch(''); setIpTrend('all'); setKTier('all');
    setXfpMin(0); setXfpMax(20); setFavOnly(false); setRoster('all');
  };

  const allRows = window.XFP_PROJECTIONS;
  const meta = window.XFP_META;
  const hitterRows = window.XFP_HITTERS || [];
  const h2Meta = window.XFP_H2_META || null;

  // Apply filters
  const filtered = React.useMemo(() => {
    const kFn = K_TIERS.find(t => t.key === kTier)?.test;
    let rows = allRows.filter(p => {
      if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
      if (ipTrend !== 'all' && p.ipTrend !== ipTrend) return false;
      if (kFn && !kFn(p.kPct)) return false;
      if (p.xfpV11 < xfpMin || p.xfpV11 > xfpMax) return false;
      if (favOnly && !favorites.includes(p.mlbId)) return false;
      if (roster !== 'all' && p.roster !== roster) return false;
      return true;
    });
    return rows;
  }, [allRows, search, ipTrend, kTier, xfpMin, xfpMax, favOnly, favorites, roster]);

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
            XFP MODEL · 2026 SEASON · MODEL FIT {meta.trainedDate}{meta.dataThru ? ` · DATA THRU ${meta.dataThru}` : ''}
            {hasMyTeam && <span style={{ color:colors.accent, marginLeft:10 }}>· {myTeam.teamName}</span>}
          </div>
          <h1 style={{ fontSize:32, fontWeight:400, margin:'2px 0 0', letterSpacing:-0.5, fontStyle:'italic', whiteSpace:'nowrap' }}>
            xFP Model
          </h1>
          <div style={{ fontSize:12, color:colors.dim, fontStyle:'italic', margin:'5px 0 0', maxWidth:'72ch', lineHeight:1.45 }}>
            Roster-decision board — ranks your team, the FA pool and the league by <b>projected fantasy points</b> (rh3 hitters · rp3 SPs) to call starts, adds and drops. The scouting layer behind these numbers — the 20-80 expected-skill ratings and archetype process — lives on <a href="player_profiles.html" style={{ color:colors.accent, textDecoration:'none' }}>Player Profiles</a>.
          </div>
        </div>
        <div style={{ display:'flex', gap:10, alignItems:'center', fontFamily:MONO, fontSize:10,
                      letterSpacing:1.2, color:colors.dim, textTransform:'uppercase' }}>
          <span>{allRows.length} SPs</span>
          <span style={{ color:colors.faint }}>·</span>
          <span>cross-yr r {meta.crossYearR}</span>
          <span style={{ color:colors.faint }}>·</span>
          <span>YTD r {meta.ytdR}</span>
          <button onClick={() => exportCSV(sortedRows,
            ['rank','mlbId','name','xfpV11','fpTotal','fpActual','delta','stuffXfp','ipPremium','ipTrend','kPct','swstrPct','gs','hasFG'],
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

      {activeTab === 'my-team' && (
        <MyTeamTab myTeam={myTeam} allRows={allRows} colors={colors}
          editorialHeat={editorialHeat} favorites={favorites}
          toggleFavorite={toggleFavorite} setActiveTab={setActiveTab}
          setSearch={setSearch} />
      )}

      {(activeTab === 'projections' || activeTab === 'analysis') && (
        <>
          <FilterBar
            search={search} setSearch={setSearch}
            ipTrend={ipTrend} setIpTrend={setIpTrend}
            kTier={kTier} setKTier={setKTier}
            xfpMin={xfpMin} setXfpMin={setXfpMin}
            xfpMax={xfpMax} setXfpMax={setXfpMax}
            favOnly={favOnly} setFavOnly={setFavOnly}
            roster={roster} setRoster={setRoster} hasMyTeam={hasMyTeam}
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

      {activeTab === 'hitters' && (
        <HittersTab hitters={hitterRows} colors={colors} editorialHeat={editorialHeat}
          favorites={favorites} toggleFavorite={toggleFavorite} h2Meta={h2Meta} />
      )}

      {activeTab === 'model' && (
        <ModelTab meta={meta} h2Meta={h2Meta} colors={colors} />
      )}

      {activeTab === 'audit' && (
        <AuditTab audit={window.XFP_AUDIT} colors={colors} />
      )}

      {activeTab === 'advisory' && (
        <AdvisoryTab advisory={window.XFP_ADVISORY || {}} myTeam={myTeam} colors={colors} />
      )}

      {activeTab === 'decision' && (
        <DecisionTab data={window.XFP_DECISION} colors={colors} />
      )}

      <div style={{ padding:'24px 32px', borderTop:`1px solid ${colors.border}`, marginTop:32,
                    fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:1, textTransform:'uppercase' }}>
        Pitchers: V11 (SP only, Statcast + FG Pitching+) · Hitters: H2 (Ridge, 13 features) ·
        <a href="https://github.com/Kejjeh/xfp-model" style={{ color:colors.accent, marginLeft:6 }}>github.com/Kejjeh/xfp-model</a>
      </div>
    </div>
  );
}

// ═══ Decision tab (My Team vs FA console — VIEW-ONLY over the precomputed
// console_data.json payload; every number was computed server-side in
// scripts/xfp/lib/decision_console.py. Allowed ops here: lookup, sort
// comparison, subtracting two payload numbers for display, sign→color.) ════════
function DecisionTab({ data, colors }) {
  const [axis, setAxis] = React.useState('ros');
  const [bucket, setBucket] = React.useState('SP');
  const [mineId, setMineId] = React.useState('');
  const [faId, setFaId] = React.useState('');

  if (!data) {
    return (
      <div style={{ padding:'32px', fontFamily:MONO, color:colors.dim }}>
        Decision console payload not built today — run the daily refresh
        (matchup build or scripts/xfp/build_console_data.py) to populate
        console_data.json.
      </div>
    );
  }

  const AXES = [['ros', 'RoS'], ['week', 'Week'], ['po', 'Playoffs']];
  const idx = {};
  data.buckets.forEach(b => b.players.forEach(p => { if (!idx[p.id]) idx[p.id] = p; }));
  const nameOf = id => (idx[id] ? idx[id].name : id);
  const active = data.buckets.find(b => b.key === bucket) || data.buckets[0];
  const spB = data.buckets.find(b => b.key === 'SP');
  const spIds = {};
  if (spB) spB.players.forEach(p => { spIds[p.id] = true; });
  const axKey = 'xfp_' + axis;
  const rows = active.players.slice().sort((a, b) => {
    const av = a[axKey] == null ? -Infinity : a[axKey];
    const bv = b[axKey] == null ? -Infinity : b[axKey];
    return bv - av;
  });
  const wk = data.week;
  const dcell = (v) => v == null
    ? <td style={{ padding:'4px 10px', color:colors.dim }}>—</td>
    : <td style={{ padding:'4px 10px', fontWeight:600,
                   color: v > 0 ? colors.pos : (v < 0 ? colors.neg : colors.dim) }}>
        {(v > 0 ? '+' : '') + v}</td>;
  const chip = (txt, col) => (
    <span style={{ marginLeft:6, padding:'0 5px', borderRadius:3, fontSize:9,
                   background:col + '33', color:col }}>{txt}</span>);

  // simulator: pure payload lookups + one subtraction (SP week uses the
  // precomputed pairwise cap-aware map)
  let sim = null;
  const m = idx[mineId], f = idx[faId];
  if (m && f) {
    const shared = m.slots.filter(s => f.slots.indexOf(s) >= 0);
    const dRos = (f.xfp_ros == null || m.xfp_ros == null) ? null
      : Math.round((f.xfp_ros - m.xfp_ros) * 10) / 10;
    const dPo = (f.xfp_po == null || m.xfp_po == null) ? null
      : Math.round((f.xfp_po - m.xfp_po) * 10) / 10;
    let dWeek = null, weekApprox = false;
    if (spB && spIds[m.id] && spIds[f.id]) {
      const pw = spB.pair_week_deltas[m.id + '|' + f.id];
      if (pw !== undefined && pw !== null) dWeek = pw;
      else if (f.xfp_week != null && m.xfp_week != null) {
        dWeek = Math.round((f.xfp_week - m.xfp_week) * 10) / 10;
        weekApprox = true;
      }
    } else if (f.xfp_week != null && m.xfp_week != null) {
      dWeek = Math.round((f.xfp_week - m.xfp_week) * 10) / 10;
    }
    sim = { dRos, dWeek, dPo, weekApprox, shared,
            warns: ['LOW_CONF', 'IL', 'WEEK_EST'].filter(fl => f.flags.indexOf(fl) >= 0) };
  }

  const btn = (on) => ({
    background: on ? colors.panel : 'transparent', color: on ? colors.text : colors.dim,
    border: `1px solid ${on ? colors.accent : colors.border}`, borderRadius:4,
    padding:'3px 12px', marginRight:6, cursor:'pointer', fontFamily:MONO, fontSize:11 });
  const th = { padding:'5px 10px', textAlign:'left', color:colors.dim, fontFamily:MONO,
               fontSize:10, letterSpacing:1, textTransform:'uppercase',
               borderBottom:`1px solid ${colors.border}` };
  const td = { padding:'4px 10px', borderBottom:`1px solid ${colors.border}`,
               fontFamily:MONO, fontSize:12 };

  return (
    <>
      <SectionHeading num="I" label="Decision Console — My Team vs FA"
        right={`generated ${data.generated_at} · source ${data.source}`} colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        <div style={{ marginBottom:10 }}>
          {AXES.map(([k, lbl]) => (
            <button key={k} style={btn(axis === k)} onClick={() => setAxis(k)}>{lbl}</button>
          ))}
        </div>
        <div style={{ fontFamily:MONO, fontSize:11, color:colors.dim,
                      border:`1px dashed ${colors.border}`, borderRadius:4,
                      padding:'6px 10px', marginBottom:14 }}>
          {wk
            ? <>Period <b style={{color:colors.text}}>{wk.period}</b> ({wk.week_start} → {wk.week_end})
                · SP cap <b style={{color:colors.text}}>{wk.sp_cap}</b>
                · banked <b style={{color:colors.text}}>{wk.banked_mine == null ? '?' : wk.banked_mine}</b>
                · scheduled <b style={{color:colors.text}}>{wk.scheduled_mine}</b>
                · cap room <b style={{color:colors.text}}>{wk.cap_room == null ? '?' : wk.cap_room}</b>
                {wk.week_est && chip('estimates in play', colors.warn)}</>
            : <>Week axis estimated — no period/schedule context in this payload.</>}
        </div>
      </div>

      <SectionHeading num="II" label="Top Swap Recommendations" colors={colors} />
      <div style={{ padding:'0 32px 18px' }}>
        {data.headline_recs.length === 0
          ? <div style={{ fontFamily:MONO, fontSize:12, color:colors.dim }}>
              No swap clears the verdict threshold right now.</div>
          : <table style={{ borderCollapse:'collapse', width:'100%' }}>
              <thead><tr>
                <th style={th}>Drop</th><th style={th}>Add</th><th style={th}>Bucket</th>
                <th style={th}>ΔRoS</th><th style={th}>ΔWeek</th><th style={th}>ΔPO</th>
                <th style={th}>Verdict</th>
              </tr></thead>
              <tbody>
                {data.headline_recs.map((r, i) => (
                  <tr key={i}>
                    <td style={{...td, color:colors.neg}}>{nameOf(r.drop_id)}</td>
                    <td style={{...td, color:colors.pos}}>{nameOf(r.add_id)}</td>
                    <td style={{...td, color:colors.dim}}>{r.bucket}</td>
                    {dcell(r.delta_ros)}{dcell(r.delta_week)}{dcell(r.delta_po)}
                    <td style={td}>
                      <span style={{ padding:'1px 7px', borderRadius:3, fontSize:10, fontWeight:600,
                        background:(r.verdict === 'STRONG' ? colors.pos : r.verdict === 'MODEST' ? colors.warn : colors.dim) + '33',
                        color: r.verdict === 'STRONG' ? colors.pos : r.verdict === 'MODEST' ? colors.warn : colors.dim }}>
                        {r.verdict}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>}
      </div>

      <SectionHeading num="III" label="Position Boards" colors={colors} />
      <div style={{ padding:'0 32px 18px' }}>
        <div style={{ marginBottom:10 }}>
          {data.buckets.map(b => (
            <button key={b.key} style={btn(bucket === b.key)}
              onClick={() => setBucket(b.key)}>{b.key}</button>
          ))}
        </div>
        {active.note && <div style={{ fontFamily:MONO, fontSize:10, color:colors.dim,
                                      marginBottom:8 }}>{active.note}</div>}
        <table style={{ borderCollapse:'collapse', width:'100%' }}>
          <thead><tr>
            <th style={th}>Player</th><th style={th}>Own</th><th style={th}>Team</th>
            <th style={th}>Slots</th><th style={th}>Rate</th>
            <th style={th}>xFP {AXES.find(a => a[0] === axis)[1]}</th>
          </tr></thead>
          <tbody>
            {rows.map(p => (
              <tr key={p.id} style={p.owner === 'MINE' ? { background:colors.mine || '#2a332022' } : null}>
                <td style={td}>{p.name}
                  {p.flags.map(fl => chip(fl.replace('_', '-'),
                    fl === 'IL' ? colors.neg : fl === 'TWO_START' ? colors.pos : colors.warn))}
                  {p.ret && chip(p.ret, colors.warn)}</td>
                <td style={{...td, color: p.owner === 'MINE' ? colors.pos : colors.dim}}>
                  {p.owner === 'MINE' ? 'MINE' : (p.own_pct == null ? 'FA' : p.own_pct + '%')}</td>
                <td style={{...td, color:colors.dim}}>{p.team}</td>
                <td style={{...td, color:colors.dim}}>{p.slots.join('/')}</td>
                <td style={td}>{p.rate == null ? '—' : p.rate}</td>
                <td style={{...td, color:colors.accent, fontWeight:600}}>
                  {p[axKey] == null ? '—' : p[axKey]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHeading num="IV" label="Swap Simulator" colors={colors} />
      <div style={{ padding:'0 32px 24px', fontFamily:MONO, fontSize:12 }}>
        <label style={{ color:colors.dim, marginRight:16 }}>Drop (mine){' '}
          <select value={mineId} onChange={e => setMineId(e.target.value)}
            style={{ background:colors.panel, color:colors.text,
                     border:`1px solid ${colors.border}`, borderRadius:4, padding:'2px 6px' }}>
            <option value="">—</option>
            {data.sim.mine_ids.map(id => <option key={id} value={id}>{nameOf(id)}</option>)}
          </select>
        </label>
        <label style={{ color:colors.dim }}>Add (FA){' '}
          <select value={faId} onChange={e => setFaId(e.target.value)}
            style={{ background:colors.panel, color:colors.text,
                     border:`1px solid ${colors.border}`, borderRadius:4, padding:'2px 6px' }}>
            <option value="">—</option>
            {data.buckets.map(b => (
              <optgroup key={b.key} label={b.label}>
                {(data.sim.fa_ids_by_bucket[b.key] || []).map(id => (
                  <option key={id} value={id}>{nameOf(id)}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <div style={{ marginTop:12, color:colors.text }}>
          {!sim
            ? <span style={{ color:colors.dim }}>Pick a drop and an add to simulate the swap on all three axes.</span>
            : <>Drop <b>{m.name}</b> → add <b>{f.name}</b>:{' '}
                {[['ΔRoS', sim.dRos], ['ΔWeek', sim.dWeek], ['ΔPO', sim.dPo]].map(([lbl, v], i) => (
                  <span key={lbl} style={{ marginRight:12,
                    color: v == null ? colors.dim : v > 0 ? colors.pos : v < 0 ? colors.neg : colors.dim }}>
                    {lbl} {v == null ? '—' : (v > 0 ? '+' : '') + v}
                    {lbl === 'ΔWeek' && sim.weekApprox && chip('≈ cap-approx', colors.warn)}
                  </span>
                ))}
                {sim.shared.length === 0 && chip('no shared slot — needs a matching open slot', colors.neg)}
                {sim.warns.map(w => chip('add is ' + w, colors.warn))}
              </>}
        </div>
        <div style={{ marginTop:14, fontSize:10, color:colors.dim }}>
          {data.note}. LOW-CONF / IL FAs never appear in recommendations but stay visible in the tables.
        </div>
      </div>
    </>
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
          xLabel="prior-season xFP (projected FP/start)" yLabel="2026 actual FP/start"
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

      <SectionHeading num="III" label="K% Residual · V11 vs Actual"
        right="bar fill = mean (V11 − actual FP/start)" colors={colors} />
      <div style={{ padding:'0 32px 32px' }}>
        <KDistributionChart data={rows} colors={colors} />
        <div style={{ paddingTop:12, fontSize:11, color:colors.dim, fontStyle:'italic' }}>
          Each bar = pitcher count in that K-bucket. Fill color = average residual
          (V11 expected − 2026 actual FP/start) across pitchers with ≥ 5 GS.
          Red = V11 over-projecting; green = pitchers outperforming projection.
        </div>
      </div>
    </>
  );
}

// ═══ Hitters tab ══════════════════════════════════════════════════════════════
function HittersTab({ hitters, colors, editorialHeat, favorites, toggleFavorite, h2Meta }) {
  const [hSort, setHSort] = React.useState({ col: 'expTotalFp', dir: 'desc' });
  const [hPos,  setHPos]  = React.useState('all');     // 'all' | 'C' | '1B' | ... | 'OF' | 'DH'
  const [hMinPa, setHMinPa] = React.useState(50);
  const [hRoster, setHRoster] = React.useState('all'); // 'all' | 'mine' | 'other'
  const [hCohort, setHCohort] = React.useState('all'); // 'all' | 'blended' | '2025_only' | '2026_only'

  const POS_OPTIONS = ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH', '1B/3B', '2B/SS'];

  const hasMine = hitters.some(h => h.roster === 'mine');

  // Filter
  const filtered = hitters.filter(h => {
    if (hPos !== 'all') {
      const pos = h.pos || '';
      const fpos = (h.fpos || '').split(/[,\s|]+/).map(s => s.trim());
      const targets = hPos.includes('/') ? hPos.split('/') : [hPos];
      const match = targets.some(t => pos === t || fpos.includes(t));
      if (!match) return false;
    }
    if (hRoster !== 'all' && h.roster !== hRoster) return false;
    if (hCohort !== 'all' && h.cohort !== hCohort) return false;
    if (h.pa != null && h.pa < hMinPa) return false;
    if (h.pa == null && hMinPa > 0) return false;  // skip 2025-only when min PA > 0
    return true;
  });
  const sorted = sortRows(filtered, hSort.col, hSort.dir);

  function handleSort(col) {
    if (hSort.col === col) setHSort({ col, dir: hSort.dir === 'desc' ? 'asc' : 'desc' });
    else setHSort({ col, dir: 'desc' });
  }

  return (
    <>
      {/* Filter bar */}
      <div style={{ padding:'10px 32px', display:'flex', gap:14, alignItems:'center',
                    fontSize:10, fontFamily:MONO, textTransform:'uppercase', letterSpacing:1.5,
                    borderBottom:`1px solid ${colors.border}`, background:colors.stripe, flexWrap:'wrap' }}>
        <div style={{ display:'flex', gap:4, alignItems:'center' }}>
          <span style={{ color:colors.dim, marginRight:4 }}>Pos</span>
          {['All', ...POS_OPTIONS].map(p => {
            const active = (p === 'All' && hPos === 'all') || hPos === p;
            return (
              <span key={p} onClick={() => setHPos(p === 'All' ? 'all' : p)} style={{
                padding:'2px 7px', borderRadius:2, cursor:'pointer', fontSize:10,
                fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                border:`1px solid ${active ? colors.accent : colors.border}`,
                color: active ? colors.accent : colors.dim,
                background: active ? `${colors.accent}18` : 'transparent',
              }}>{p}</span>
            );
          })}
        </div>
        <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Min PA
          <input type="number" value={hMinPa} onChange={e => setHMinPa(+e.target.value || 0)}
            style={{ width:48, padding:'2px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
                     background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11, textAlign:'right' }} />
        </label>
        <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Cohort
          <select value={hCohort} onChange={e => setHCohort(e.target.value)}
            style={{ padding:'2px 4px', border:`1px solid ${colors.border}`, borderRadius:2,
                     background:colors.panel, color:colors.accent, fontFamily:MONO, fontSize:11 }}>
            <option value="all">All</option>
            <option value="blended">Blended (25+26)</option>
            <option value="2025_only">2025 only</option>
            <option value="2026_only">2026 only</option>
          </select>
        </label>
        {hasMine && (
          <label style={{ color:colors.dim, display:'flex', alignItems:'center', gap:6 }}>Roster
            {[
              { k:'all',   l:'All' },
              { k:'mine',  l:'My Team' },
              { k:'fa',    l:'Free Agents' },
              { k:'taken', l:'Other Teams' },
            ].map(opt => (
              <button key={opt.k} onClick={() => setHRoster(opt.k)}
                style={{ padding:'3px 8px', fontSize:10, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase',
                         border:`1px solid ${hRoster===opt.k ? colors.accent : colors.border}`, borderRadius:2,
                         background: hRoster===opt.k ? colors.accent : colors.panel,
                         color: hRoster===opt.k ? '#fff' : colors.dim, cursor:'pointer' }}>{opt.l}</button>
            ))}
          </label>
        )}
        <button onClick={() => { setHPos('all'); setHMinPa(50); setHRoster('all'); setHCohort('all'); }}
          style={editorialBtn(colors)}>Reset</button>
        <div style={{ flex:1 }} />
        <span style={{ color:colors.dim }}>{filtered.length} / {hitters.length} hitters</span>
      </div>

      <SectionHeading num="I" label="Hitter Projections (xFP H2)"
        right={`SORTED BY ${hSort.col.toUpperCase()} ${hSort.dir === 'desc' ? '↓' : '↑'}`} colors={colors} />
      <div style={{ padding:'0 32px 24px', overflow:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                           fontWeight:600, letterSpacing:1.5, textTransform:'uppercase', fontFamily:MONO, width:30 }}>★</th>
              <SortTh col="rank"          label="Rk"        align="l" width={36}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="name"          label="Hitter"    align="l" width={170} sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pos"           label="Pos"       align="l" width={48}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="team"          label="Tm"        align="l" width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="expTotalFp"    label="Proj FP"     width={86}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="replDeltaTotal" label="Δ Repl FP" width={80}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="signal"        label="Sig"       width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpRoSPerPa"   label="RoS/PA"    width={86}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="recencyGap"    label="L21Δ"      width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpPerPa"      label="xFP/PA"    width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="replDelta"     label="Δ Repl/PA" width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpRoSFullFp"  label="RoS/G"     width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpFullFp"     label="xFP/G"     width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="coreXfpPerPa"  label="Core/PA"   width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="paPremium"     label="PA Prem"   width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pa"            label="PA"        width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpPerPaActual" label="Act/PA"    width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="delta"         label="Δ vs Act"  width={68}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpTotal"       label="FP Tot"    width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="hr"            label="HR"        width={36}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="cohort"        label="Cohort"    align="l" width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="roster"        label="Own"       width={56}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, idx) => {
              const isFav = favorites.includes(h.mlbId);
              const cohortColor = h.cohort === 'blended' ? colors.pos
                : h.cohort === '2026_only' ? colors.warn
                : h.cohort === '2025_only' ? colors.dim : colors.faint;
              return (
                <tr key={h.mlbId} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', textAlign:'center' }}>
                    <span onClick={() => toggleFavorite(h.mlbId)}
                      style={{ color: isFav ? colors.accent : colors.faint, cursor:'pointer', fontSize:13 }}>★</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: h.rank <= 3 ? colors.accent : colors.dim }}>{h.rank}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    <span style={{ fontSize:14, fontWeight:500 }}>{h.name}</span>
                    {h.slumpPct != null && h.slumpPct < 20 && h.slumpBouncePct != null && h.slumpBouncePct >= 80 && (
                      <span title={`Cold streak at ${h.slumpPct}-th percentile of his career; ${h.slumpBouncePct}% historical bounce-back over next 200 PA`}
                            style={{ marginLeft:6, fontSize:9, fontFamily:MONO, letterSpacing:1,
                                     padding:'1px 4px', border:`1px solid ${colors.pos}`,
                                     color:colors.pos, borderRadius:2 }}>BUY-LOW</span>
                    )}
                    {h.slumpPct != null && h.slumpPct < 5 && h.slumpBouncePct != null && h.slumpBouncePct < 60 && (
                      <span title={`Cold streak at ${h.slumpPct}-th percentile; only ${h.slumpBouncePct}% bounce-back rate — possible regime change`}
                            style={{ marginLeft:6, fontSize:9, fontFamily:MONO, letterSpacing:1,
                                     padding:'1px 4px', border:`1px solid ${colors.warn}`,
                                     color:colors.warn, borderRadius:2 }}>FADE</span>
                    )}
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.pos || '—'}</td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.team || '—'}</td>
                  {/* HEADLINE: Projected total FP rest of season */}
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(h.expTotalFp, 100, 350) }}>
                    <span style={{ fontSize:17, fontFamily:SERIF, fontStyle:'italic',
                                   color: h.expTotalFp != null ? colors.accent : colors.faint,
                                   fontVariantNumeric:'tabular-nums' }}>
                      {h.expTotalFp == null ? '—' : h.expTotalFp.toFixed(0)}
                    </span>
                  </td>
                  {/* Δ Repl FP — total-FP version */}
                  <td style={dataCell(colors,
                      h.replDeltaTotal == null ? colors.faint :
                      h.replDeltaTotal > 0 ? colors.pos : colors.warn)}>
                    {h.replDeltaTotal == null ? '—' : fmtSign(h.replDeltaTotal, 0)}
                  </td>
                  <td style={{ padding:'5px 6px', textAlign:'center' }}>
                    {(() => {
                      const s = h.signal || 'hold';
                      const styles = {
                        add:  { color:colors.accent, border:`1px solid ${colors.accent}` },
                        hold: { color:colors.dim,    border:`1px solid ${colors.border}` },
                        drop: { color:colors.warn,   border:`1px solid ${colors.warn}` },
                      };
                      return (
                        <span style={{ ...(styles[s] || styles.hold), padding:'1px 6px',
                                       fontFamily:MONO, fontSize:9, letterSpacing:1, borderRadius:2,
                                       whiteSpace:'nowrap' }}>
                          {s.toUpperCase()}
                        </span>
                      );
                    })()}
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(h.xfpRoSPerPa, 0.3, 0.85) }}>
                    <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', lineHeight:1.0 }}>
                      <span style={{ fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                                     color: h.xfpRoSPerPa != null ? colors.text : colors.faint,
                                     fontVariantNumeric:'tabular-nums' }}>
                        {h.xfpRoSPerPa == null ? '—' : h.xfpRoSPerPa.toFixed(3)}
                      </span>
                      {h.xfpRoSp25 != null && h.xfpRoSp75 != null && (
                        <span style={{ fontSize:9, color:colors.dim, fontFamily:MONO, marginTop:2 }}>
                          {h.xfpRoSp25.toFixed(2)}–{h.xfpRoSp75.toFixed(2)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={dataCell(colors,
                      h.recencyGap == null ? colors.faint :
                      h.recencyGap > 0.02 ? colors.pos :
                      h.recencyGap < -0.02 ? colors.warn : colors.dim)}>
                    {h.recencyGap == null ? '—' : fmtSign(h.recencyGap, 3)}
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right' }}>
                    <span style={{ fontSize:13, fontFamily:SERIF, fontStyle:'italic',
                                   color: h.xfpPerPa != null ? colors.dim : colors.faint,
                                   fontVariantNumeric:'tabular-nums' }}>
                      {h.xfpPerPa == null ? '—' : h.xfpPerPa.toFixed(3)}
                    </span>
                  </td>
                  <td style={dataCell(colors,
                      h.replDelta == null ? colors.faint :
                      h.replDelta > 0 ? colors.pos : colors.warn)}>
                    {h.replDelta == null ? '—' : fmtSign(h.replDelta, 3)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{h.xfpRoSFullFp == null ? '—' : h.xfpRoSFullFp.toFixed(2)}</td>
                  <td style={dataCell(colors)}>{h.xfpFullFp == null ? '—' : h.xfpFullFp.toFixed(2)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.coreXfpPerPa == null ? '—' : h.coreXfpPerPa.toFixed(3)}</td>
                  <td style={dataCell(colors, h.paPremium > 0.05 ? colors.pos : h.paPremium < -0.05 ? colors.neg : colors.dim)}>
                    {h.paPremium == null ? '—' : fmtSign(h.paPremium, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{h.pa ?? '—'}</td>
                  <td style={dataCell(colors, h.fpPerPaActual == null ? colors.faint : colors.text)}>
                    {h.fpPerPaActual == null ? '—' : h.fpPerPaActual.toFixed(3)}
                  </td>
                  <td style={dataCell(colors, h.delta == null ? colors.faint : h.delta > 0.05 ? colors.neg : h.delta < -0.05 ? colors.pos : colors.dim)}>
                    {h.delta == null ? '—' : fmtSign(h.delta, 3)}
                  </td>
                  <td style={dataCell(colors)}>{h.fpTotal == null ? '—' : h.fpTotal.toFixed(0)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.hr ?? '—'}</td>
                  <td style={{ padding:'7px 8px', textAlign:'left', fontSize:9, fontFamily:MONO,
                               letterSpacing:1, color: cohortColor }}>{h.cohort || '—'}</td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {h.roster === 'mine' ? (
                      <span style={{ padding:'1px 6px', border:`1px solid ${colors.accent}`,
                                     color:colors.accent, fontFamily:MONO, fontSize:9,
                                     letterSpacing:1, borderRadius:2, whiteSpace:'nowrap' }}>★ MINE</span>
                    ) : h.roster === 'taken' ? (
                      <span title={h.taken_by_team ? `Rostered by ${h.taken_by_team}` : 'Rostered by another team'}
                            style={{ color:colors.dim, fontFamily:MONO, fontSize:9, letterSpacing:0.5,
                                     whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis',
                                     display:'inline-block', maxWidth:64, verticalAlign:'bottom' }}>
                        {h.taken_by_team || 'TAKEN'}
                      </span>
                    ) : (
                      <span style={{ color:colors.faint, fontFamily:MONO, fontSize:9 }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ paddingTop:10, fontSize:10, color:colors.dim, fontFamily:MONO,
                      letterSpacing:1, textAlign:'right' }}>
          ↳ CLICK ANY HEADER TO SORT · ★ TO PIN · COHORT = BLENDED IS MOST RELIABLE
        </div>
        {h2Meta && (
          <div style={{ marginTop:14, padding:'8px 12px', background:colors.stripe, borderLeft:`3px solid ${colors.accent}`,
                        fontSize:11, color:colors.dim, fontStyle:'italic', lineHeight:1.5 }}>
            xFP H2 (Ridge, {h2Meta.features.length} features). Cross-year r {h2Meta.crossYearR},
            YTD r {h2Meta.ytdR} (n={h2Meta.ytdN}, PA ≥ 80).
            Trained on {h2Meta.nTrain} hitter-seasons, mid-season blend with Bayesian shrinkage on contact-quality metrics.
          </div>
        )}
      </div>
    </>
  );
}


// Generic sort: numeric → numeric, string → localeCompare, nulls always last.
function sortRows(rows, col, dir) {
  return [...rows].sort((a, b) => {
    const av = a[col], bv = b[col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'string' && typeof bv === 'string') {
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return dir === 'asc' ? av - bv : bv - av;
  });
}

// ═══ My Team tab ══════════════════════════════════════════════════════════════
function MyTeamTab({ myTeam, allRows, colors, editorialHeat, favorites, toggleFavorite, setActiveTab, setSearch }) {
  const rotation = myTeam.pitchers.filter(p => p.role === 'SP');
  const bullpen  = myTeam.pitchers.filter(p => p.role === 'RP');

  // Per-table sort state — each table can be sorted independently.
  const [rotSort, setRotSort]     = React.useState({ col: 'xfpV11',   dir: 'desc' });
  const [availSort, setAvailSort] = React.useState({ col: 'xfpV11',   dir: 'desc' });
  const [bpSort, setBpSort]       = React.useState({ col: 'rpFullYear', dir: 'desc' });

  function makeSortHandler(state, setState) {
    return (col) => {
      if (state.col === col) setState({ col, dir: state.dir === 'desc' ? 'asc' : 'desc' });
      else setState({ col, dir: 'desc' });
    };
  }

  // Mean xFP of my rotation (matched only)
  const matched = rotation.filter(p => p.xfpV11 != null);
  const meanXfp = matched.length
    ? matched.reduce((s, p) => s + p.xfpV11, 0) / matched.length
    : null;

  // Add/Drop suggestions: only TRUE free agents (not on any league roster).
  // r.roster is set by _label_roster_status in the Python builder to
  // 'mine' | 'taken' | 'fa'. We only suggest FAs since "taken" players can't
  // actually be picked up — comparing against owned players is misleading.
  const allAvailable = allRows.filter(r => r.roster === 'fa');
  const available = allAvailable.slice(0, 25); // top 25 by xFP V11 (allRows is pre-sorted)
  const myWeakest = matched.length
    ? [...matched].sort((a, b) => a.xfpV11 - b.xfpV11).slice(0, 5)
    : [];
  const swaps = [];
  for (const drop of myWeakest) {
    for (const add of available) {
      if (add.xfpV11 > drop.xfpV11 + 0.5) {
        swaps.push({ drop, add, gain: add.xfpV11 - drop.xfpV11 });
        break; // best available drop pair
      }
    }
  }
  swaps.sort((a, b) => b.gain - a.gain);

  // Sorted views for the three on-screen tables.
  const rotationDisplay = sortRows(rotation, rotSort.col, rotSort.dir);
  const availableDisplay = sortRows(allAvailable, availSort.col, availSort.dir).slice(0, 15);
  const bullpenDisplay  = sortRows(bullpen, bpSort.col, bpSort.dir);

  const handleRotSort   = makeSortHandler(rotSort,   setRotSort);
  const handleAvailSort = makeSortHandler(availSort, setAvailSort);
  const handleBpSort    = makeSortHandler(bpSort,    setBpSort);

  return (
    <>
      {/* Hero */}
      <div style={{ padding:'24px 32px 18px', borderBottom:`1px solid ${colors.border}`,
                    display:'grid', gridTemplateColumns:'1.2fr 1fr', gap:32 }}>
        <div>
          <div style={{ fontSize:10, letterSpacing:3, textTransform:'uppercase',
                        color:colors.accent, fontFamily:MONO, marginBottom:8 }}>
            Lede · ESPN Connector
          </div>
          <h2 style={{ fontSize:26, fontWeight:400, lineHeight:1.15, margin:0, letterSpacing:-0.5 }}>
            <span style={{ fontStyle:'italic' }}>{myTeam.teamName}</span> ·{' '}
            <span style={{ color:colors.accent, fontVariantNumeric:'tabular-nums' }}>
              {rotation.length}
            </span> SP /{' '}
            <span style={{ color:colors.accent, fontVariantNumeric:'tabular-nums' }}>
              {bullpen.length}
            </span> RP
          </h2>
          <p style={{ fontSize:13, color:colors.dim, margin:'8px 0 0', fontStyle:'italic', lineHeight:1.5 }}>
            Rotation averages an xFP of{' '}
            <span style={{ color:colors.accent, fontVariantNumeric:'tabular-nums' }}>
              {meanXfp == null ? '—' : meanXfp.toFixed(2)}
            </span>{' '}FP/start across {matched.length} of {rotation.length} arms with V11 coverage.
            {' '}{swaps.length > 0 && (<>The model flags <strong>{swaps.length}</strong> potential xFP-positive swaps below.</>)}
          </p>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'12px 24px' }}>
          {[
            { lbl:'Top Rotation Arm',
              p: matched[0] ? matched.reduce((b,p) => p.xfpV11 > b.xfpV11 ? p : b, matched[0]) : null,
              vKey: 'xfpV11' },
            { lbl:'Weakest Slot',
              p: myWeakest[0] || null, vKey: 'xfpV11' },
            { lbl:'Best Available',
              p: available[0] || null, vKey: 'xfpV11' },
            { lbl:'Best Swap Gain',
              custom: swaps[0]
                ? `+${swaps[0].gain.toFixed(2)} FP/start (${(swaps[0].add.name || '').split(',')[0]} → ${(swaps[0].drop.name || '').split(' ').pop()})`
                : '—' },
          ].map((c, i) => (
            <div key={i} style={{ borderTop:`1px solid ${colors.faint}`, paddingTop:6 }}>
              <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO }}>{c.lbl}</div>
              {c.custom != null ? (
                <div style={{ fontSize:14, marginTop:4, color:colors.accent, fontFamily:SERIF, fontStyle:'italic' }}>
                  {c.custom}
                </div>
              ) : c.p ? (
                <>
                  <div style={{ fontSize:20, fontFamily:SERIF, fontStyle:'italic', color:colors.accent, lineHeight:1, marginTop:4 }}>
                    {fmt(c.p[c.vKey], 2)}
                  </div>
                  <div style={{ fontSize:11, marginTop:4 }}>{c.p.name}</div>
                </>
              ) : (
                <div style={{ fontSize:14, color:colors.dim, marginTop:4 }}>—</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Rotation table */}
      <SectionHeading num="I" label="My Rotation"
        right={`${rotation.length} SP · CLICK ANY HEADER TO SORT`} colors={colors} />
      <div style={{ padding:'0 32px 6px', fontSize:11, color:colors.dim, fontStyle:'italic', lineHeight:1.45 }}>
        League cap — only the first <b style={{ color:colors.text, fontStyle:'normal' }}>10 SP starts each week</b> score;
        starts 11+ are zeros. At ~1.19 starts per active SP a deep rotation can overflow — when it does, bench the
        lowest-EV <i>start</i>, not the lowest-ranked arm.
      </div>
      <div style={{ padding:'0 32px 8px', overflow:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                           fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
              <SortTh col="name"      label="Pitcher"   align="l" width={170} sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="proTeam"   label="Team"      align="l" width={50}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="xfpV11"    label="xFP prev"  width={70}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="xfpRank"   label="Rank"      width={50}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="kPct"      label="K%"        width={50}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="ipTrend"   label="Trend"     width={70}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="gs"        label="GS"        width={36}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="fpActual"  label="2026 FP"   width={60}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="fpPerGame" label="ESPN FP/G" width={70}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <SortTh col="pctOwned"  label="% Owned"   width={64}  sortCol={rotSort.col} sortDir={rotSort.dir} onSort={handleRotSort} colors={colors} />
              <th style={{ padding:'8px 8px', textAlign:'right', fontSize:9, color:colors.dim,
                           fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}></th>
            </tr>
          </thead>
          <tbody>
            {rotationDisplay.map((p, idx) => {
              const isFav = p.mlbId != null && favorites.includes(p.mlbId);
              const trendStyle = p.ipTrend === 'HIGH'
                ? { color:colors.pos, border:`1px solid ${colors.pos}` }
                : p.ipTrend === 'LOW'
                ? { color:colors.warn, border:`1px solid ${colors.warn}` }
                : { color:colors.dim, border:`1px solid ${colors.border}` };
              return (
                <tr key={p.name} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: idx < 3 ? colors.accent : colors.dim }}>{idx + 1}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    {p.mlbId != null && (
                      <span onClick={() => toggleFavorite(p.mlbId)}
                        style={{ color: isFav ? colors.accent : colors.faint,
                                 cursor:'pointer', fontSize:11, marginRight:6 }}>★</span>
                    )}
                    <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>
                    {p.proTeam || '—'}
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpV11, 8, 17) }}>
                    <span style={{ fontSize:17, fontFamily:SERIF, fontStyle:'italic',
                                   color: p.xfpV11 != null ? colors.accent : colors.faint }}>
                      {p.xfpV11 == null ? '—' : fmt(p.xfpV11, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors, colors.dim)}>
                    {p.xfpRank == null ? '—' : '#' + p.xfpRank}
                  </td>
                  <td style={dataCell(colors, p.kPct == null ? colors.faint : colors.text)}>
                    {p.kPct == null ? '—' : fmtPct(p.kPct, 1)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {p.ipTrend ? (
                      <span style={{ ...trendStyle, padding:'1px 6px', fontFamily:MONO,
                                     fontSize:9, letterSpacing:1, borderRadius:2 }}>
                        {p.ipTrend}
                      </span>
                    ) : <span style={{ color:colors.faint }}>—</span>}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.gs == null ? '—' : p.gs}</td>
                  <td style={dataCell(colors, p.fpActual == null ? colors.faint : colors.text)}>
                    {p.fpActual == null || (p.gs ?? 0) < 5 ? '—' : fmt(p.fpActual, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>
                    {p.fpPerGame == null ? '—' : fmt(p.fpPerGame, 2)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>
                    {p.pctOwned == null ? '—' : fmt(p.pctOwned, 1) + '%'}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    {p.xfpV11 == null ? (
                      <span style={{ color:colors.warn, fontSize:9, fontFamily:MONO,
                                     letterSpacing:1, padding:'1px 6px',
                                     border:`1px solid ${colors.warn}`, borderRadius:2 }}>
                        NO PRIOR
                      </span>
                    ) : (
                      <span style={{ color:colors.faint, fontSize:9, fontFamily:MONO }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ paddingTop:6, fontSize:10, color:colors.dim, fontFamily:MONO,
                      letterSpacing:1, fontStyle:'italic' }}>
          ↳ "NO PRIOR" tag = pitcher not in the prior-season model universe (rookie debut without FG Pitching+ history)
        </div>
      </div>

      {/* Add/Drop suggestions */}
      <SectionHeading num="II" label="Add / Drop Targets"
        right={swaps.length > 0 ? `${swaps.length} SUGGESTED` : 'NO POSITIVE SWAPS'} colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        {swaps.length === 0 ? (
          <div style={{ padding:'14px 0', fontSize:13, fontStyle:'italic', color:colors.dim }}>
            Your rotation already projects above the available pool. No xFP-positive swaps to flag.
          </div>
        ) : (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(360px, 1fr))', gap:14 }}>
            {swaps.map((s, i) => (
              <div key={i} style={{ borderTop:`2px solid ${colors.accent}`, paddingTop:10 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
                  <span style={{ fontSize:9, letterSpacing:2, color:colors.dim, fontFamily:MONO,
                                 textTransform:'uppercase' }}>Swap #{i + 1}</span>
                  <span style={{ fontSize:14, fontStyle:'italic', fontFamily:SERIF, color:colors.pos }}>
                    +{s.gain.toFixed(2)} FP/start
                  </span>
                </div>
                <div style={{ marginTop:8, display:'grid', gridTemplateColumns:'1fr 24px 1fr', gap:8, alignItems:'center' }}>
                  <div style={{ padding:'8px 10px', border:`1px solid ${colors.neg}`, borderRadius:2, background:colors.stripe }}>
                    <div style={{ fontSize:9, letterSpacing:2, color:colors.neg, fontFamily:MONO,
                                  textTransform:'uppercase' }}>Drop</div>
                    <div style={{ fontSize:13, fontStyle:'italic', fontFamily:SERIF, color:colors.text, marginTop:2 }}>
                      {s.drop.name}
                    </div>
                    <div style={{ fontSize:11, color:colors.dim, fontFamily:MONO, marginTop:4 }}>
                      xFP {fmt(s.drop.xfpV11, 2)} · {s.drop.ipTrend ?? '—'} · #{s.drop.xfpRank ?? '—'}
                    </div>
                  </div>
                  <div style={{ textAlign:'center', fontSize:18, color:colors.accent }}>→</div>
                  <div style={{ padding:'8px 10px', border:`1px solid ${colors.pos}`, borderRadius:2, background:colors.stripe }}>
                    <div style={{ fontSize:9, letterSpacing:2, color:colors.pos, fontFamily:MONO,
                                  textTransform:'uppercase' }}>Add</div>
                    <div style={{ fontSize:13, fontStyle:'italic', fontFamily:SERIF, color:colors.text, marginTop:2 }}>
                      {s.add.name}
                    </div>
                    <div style={{ fontSize:11, color:colors.dim, fontFamily:MONO, marginTop:4 }}>
                      xFP {fmt(s.add.xfpV11, 2)} · {s.add.ipTrend} · #{s.add.rank}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{ padding:'4px 32px 18px', fontSize:11, fontStyle:'italic', color:colors.dim }}>
        Caveat: "available" = any SP not currently on your roster. Some may be rostered on other
        league teams. Verify ownership in ESPN before adding/dropping.
      </div>

      {/* Available leaderboard */}
      <SectionHeading num="III" label="Top Available SPs"
        right="NOT ON YOUR ROSTER · CLICK ANY HEADER TO SORT" colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                           fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
              <SortTh col="name"     label="Pitcher"   align="l" width={170} sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="xfpV11"   label="xFP prev"  width={70}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="stuffXfp" label="Stuff"     width={56}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="ipPremium" label="IP Prem"  width={64}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="ipTrend"  label="Trend"     width={70}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="kPct"     label="K%"        width={50}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="swstrPct" label="SwStr%"    width={56}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="gs"       label="GS"        width={36}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
              <SortTh col="fpActual" label="2026 FP"   width={60}  sortCol={availSort.col} sortDir={availSort.dir} onSort={handleAvailSort} colors={colors} />
            </tr>
          </thead>
          <tbody>
            {availableDisplay.map((p, idx) => {
              const isFav = favorites.includes(p.mlbId);
              const trendStyle = p.ipTrend === 'HIGH'
                ? { color:colors.pos, border:`1px solid ${colors.pos}` }
                : p.ipTrend === 'LOW'
                ? { color:colors.warn, border:`1px solid ${colors.warn}` }
                : { color:colors.dim, border:`1px solid ${colors.border}` };
              return (
                <tr key={p.mlbId} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: idx < 3 ? colors.accent : colors.dim }}>{idx + 1}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    <span onClick={() => toggleFavorite(p.mlbId)}
                      style={{ color: isFav ? colors.accent : colors.faint,
                               cursor:'pointer', fontSize:11, marginRight:6 }}>★</span>
                    <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
                  </td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(p.xfpV11, 8, 17) }}>
                    <span style={{ fontSize:16, fontFamily:SERIF, fontStyle:'italic', color:colors.accent }}>
                      {fmt(p.xfpV11, 2)}
                    </span>
                  </td>
                  <td style={dataCell(colors)}>{fmt(p.stuffXfp, 2)}</td>
                  <td style={dataCell(colors, p.ipPremium > 0.1 ? colors.pos : p.ipPremium < -0.1 ? colors.neg : colors.dim)}>
                    {fmtSign(p.ipPremium, 2)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'right' }}>
                    <span style={{ ...trendStyle, padding:'1px 6px', fontFamily:MONO,
                                   fontSize:9, letterSpacing:1, borderRadius:2 }}>
                      {p.ipTrend}
                    </span>
                  </td>
                  <td style={dataCell(colors, p.kPct == null ? colors.faint : colors.text)}>
                    {p.kPct == null ? '—' : fmtPct(p.kPct, 1)}
                  </td>
                  <td style={dataCell(colors, colors.dim)}>{p.swstrPct == null ? '—' : fmtPct(p.swstrPct, 1)}</td>
                  <td style={dataCell(colors, colors.dim)}>{p.gs ?? '—'}</td>
                  <td style={dataCell(colors, p.fpActual == null || (p.gs ?? 0) < 5 ? colors.faint : colors.text)}>
                    {p.fpActual == null || (p.gs ?? 0) < 5 ? '—' : fmt(p.fpActual, 2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ paddingTop:8, fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:1 }}>
          <span style={{ color:colors.accent, cursor:'pointer' }}
            onClick={() => { setActiveTab('projections'); setSearch(''); }}>
            ↳ See full projections leaderboard →
          </span>
        </div>
      </div>

      {/* Bullpen */}
      {bullpen.length > 0 && (
        <>
          <SectionHeading num="IV" label="My Bullpen"
            right={`${bullpen.length} RP · rprs2 MODEL · CLICK ANY HEADER TO SORT`} colors={colors} />
          <div style={{ padding:'0 32px 6px', fontSize:11, color:colors.dim, fontStyle:'italic', lineHeight:1.45 }}>
            Ranked by <b style={{ color:colors.text, fontStyle:'normal' }}>rprs2</b> full-season xFP total — the RP
            model (saves + holds included), the same basis as its rank, Δ Repl and Sig — so add/drop calls here are
            model-backed, not just ESPN totals. <b style={{ color:colors.text, fontStyle:'normal' }}>RoS</b> = remaining-season
            total; <b style={{ color:colors.text, fontStyle:'normal' }}>Δ&nbsp;Repl</b> = FP above a replacement RP;
            <b style={{ color:colors.text, fontStyle:'normal' }}> Sig</b> = the model's add/hold/drop call. “—” = outside rprs2 coverage.
          </div>
          <div style={{ padding:'0 32px 24px', overflow:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
              <thead>
                <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
                  <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim,
                               fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
                  <SortTh col="name"        label="Pitcher"   align="l" width={170} sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="proTeam"     label="Team"      align="l" width={44}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="rpFullYear"  label="Full-yr"   width={64}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="rpRoSFp"     label="RoS"       width={56}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="rpReplDelta" label="Δ Repl"    width={62}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="rpSignal"    label="Sig"       width={54}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="rpRolePrior" label="Role"      align="l" width={72}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="fpPerGame"   label="ESPN FP/G" width={72}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                  <SortTh col="pctOwned"    label="% Owned"   width={62}  sortCol={bpSort.col} sortDir={bpSort.dir} onSort={handleBpSort} colors={colors} />
                </tr>
              </thead>
              <tbody>
                {bullpenDisplay.map((p, idx) => (
                  <tr key={p.name} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                    <td style={{ padding:'7px 8px', fontSize:13, fontFamily:SERIF, fontStyle:'italic', color:colors.dim }}>{idx + 1}</td>
                    <td style={{ padding:'7px 8px', fontSize:14, fontWeight:500 }}>{p.name}</td>
                    <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{p.proTeam || '—'}</td>
                    <td style={dataCell(colors, p.rpFullYear == null ? colors.faint : colors.text)}>
                      {p.rpFullYear == null ? '—' : fmt(p.rpFullYear, 0)}
                    </td>
                    <td style={dataCell(colors, colors.dim)}>
                      {p.rpRoSFp == null ? '—' : fmt(p.rpRoSFp, 0)}
                    </td>
                    <td style={dataCell(colors, p.rpReplDelta == null ? colors.faint : (p.rpReplDelta >= 0 ? colors.pos : colors.neg))}>
                      {p.rpReplDelta == null ? '—' : (p.rpReplDelta >= 0 ? '+' : '') + fmt(p.rpReplDelta, 0)}
                    </td>
                    <td style={{ padding:'7px 8px', textAlign:'center' }}>
                      {p.rpSignal ? (
                        <span style={{ fontFamily:MONO, fontSize:9, letterSpacing:1, fontWeight:600,
                                       color: p.rpSignal === 'add' ? colors.pos : p.rpSignal === 'drop' ? colors.neg : colors.dim }}>
                          {p.rpSignal.toUpperCase()}
                        </span>
                      ) : <span style={{ color:colors.faint }}>—</span>}
                    </td>
                    <td style={{ padding:'7px 8px', fontSize:10, color:colors.dim, fontFamily:MONO, textTransform:'uppercase' }}>{p.rpRolePrior || '—'}</td>
                    <td style={dataCell(colors)}>{p.fpPerGame == null ? '—' : fmt(p.fpPerGame, 2)}</td>
                    <td style={dataCell(colors, colors.dim)}>{p.pctOwned == null ? '—' : fmt(p.pctOwned, 1) + '%'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── My Lineup (hitters with xFP H2) ──────────────────────────────── */}
      <MyLineupSection myTeam={myTeam} colors={colors} editorialHeat={editorialHeat}
        favorites={favorites} toggleFavorite={toggleFavorite} />
    </>
  );
}

// ═══ My Lineup section (hitters within My Team tab) ═══════════════════════════
function MyLineupSection({ myTeam, colors, editorialHeat, favorites, toggleFavorite }) {
  const hitters = (myTeam.hitters || []);
  if (hitters.length === 0) return null;

  const [hSort, setHSort] = React.useState({ col: 'expTotalFp', dir: 'desc' });
  function handleSort(col) {
    if (hSort.col === col) setHSort({ col, dir: hSort.dir === 'desc' ? 'asc' : 'desc' });
    else setHSort({ col, dir: 'desc' });
  }
  const sorted = sortRows(hitters, hSort.col, hSort.dir);
  const matched = hitters.filter(h => h.xfpPerPa != null);
  const meanXfpPerPa = matched.length
    ? matched.reduce((s, h) => s + h.xfpPerPa, 0) / matched.length
    : null;

  return (
    <>
      <SectionHeading num="V" label="My Lineup"
        right={`${hitters.length} HITTERS · ${matched.length} WITH xFP H2 COVERAGE`} colors={colors} />
      <div style={{ padding:'0 32px 8px' }}>
        <div style={{ marginBottom:10, fontSize:12, fontStyle:'italic', color:colors.dim }}>
          {meanXfpPerPa != null && (
            <>
              Mean xFP/PA across matched lineup: <span style={{ color:colors.accent, fontFamily:MONO, fontVariantNumeric:'tabular-nums' }}>{meanXfpPerPa.toFixed(3)}</span>
              {' · '}× 3.5 PA/G ≈ <span style={{ color:colors.accent, fontFamily:MONO, fontVariantNumeric:'tabular-nums' }}>{(meanXfpPerPa * 3.5).toFixed(2)}</span> FP/game per slot.
            </>
          )}
        </div>
      </div>
      <div style={{ padding:'0 32px 24px', overflow:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums' }}>
          <thead>
            <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
              <th style={{ padding:'8px 8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase', fontWeight:600 }}>#</th>
              <SortTh col="name"          label="Hitter"  align="l" width={170} sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="espnPos"       label="Slot"    align="l" width={50}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="proTeam"       label="Tm"      align="l" width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpPerPa"      label="xFP/PA"  width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpFullFp"     label="xFP/G"   width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="xfpRank"       label="Rk"      width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pa"            label="PA"      width={42}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpPerPaActual" label="Act/PA"  width={64}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="cohort"        label="Cohort"  align="l" width={70}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpTotal"       label="ESPN FP" width={68}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="fpPerGame"     label="ESPN FP/G" width={70} sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
              <SortTh col="pctOwned"      label="% Owned" width={62}  sortCol={hSort.col} sortDir={hSort.dir} onSort={handleSort} colors={colors} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((h, idx) => {
              const isFav = h.mlbId != null && favorites.includes(h.mlbId);
              const cohortColor = h.cohort === 'blended' ? colors.pos
                : h.cohort === '2026_only' ? colors.warn
                : h.cohort === '2025_only' ? colors.dim : colors.faint;
              return (
                <tr key={h.name} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                  <td style={{ padding:'7px 8px', fontSize:14, fontFamily:SERIF, fontStyle:'italic',
                               color: idx < 3 ? colors.accent : colors.dim }}>{idx + 1}</td>
                  <td style={{ padding:'7px 8px', whiteSpace:'nowrap' }}>
                    {h.mlbId != null && (
                      <span onClick={() => toggleFavorite(h.mlbId)}
                        style={{ color: isFav ? colors.accent : colors.faint, cursor:'pointer',
                                 fontSize:11, marginRight:6 }}>★</span>
                    )}
                    <span style={{ fontSize:14, fontWeight:500 }}>{h.name}</span>
                  </td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.espnPos || h.pos || '—'}</td>
                  <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim, fontFamily:MONO }}>{h.proTeam || h.team || '—'}</td>
                  <td style={{ padding:'5px 8px', textAlign:'right',
                               background: editorialHeat(h.xfpPerPa, 0.3, 0.85) }}>
                    <span style={{ fontSize:16, fontFamily:SERIF, fontStyle:'italic',
                                   color: h.xfpPerPa != null ? colors.accent : colors.faint }}>
                      {h.xfpPerPa == null ? '—' : h.xfpPerPa.toFixed(3)}
                    </span>
                  </td>
                  <td style={dataCell(colors)}>{h.xfpFullFp == null ? '—' : h.xfpFullFp.toFixed(2)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.xfpRank == null ? '—' : '#' + h.xfpRank}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.pa ?? '—'}</td>
                  <td style={dataCell(colors, h.fpPerPaActual == null ? colors.faint : colors.text)}>
                    {h.fpPerPaActual == null ? '—' : h.fpPerPaActual.toFixed(3)}
                  </td>
                  <td style={{ padding:'7px 8px', textAlign:'left', fontSize:9, fontFamily:MONO, letterSpacing:1, color:cohortColor }}>
                    {h.cohort || '—'}
                  </td>
                  <td style={dataCell(colors)}>{h.fpTotal == null ? '—' : fmt(h.fpTotal, 1)}</td>
                  <td style={dataCell(colors)}>{h.fpPerGame == null ? '—' : fmt(h.fpPerGame, 2)}</td>
                  <td style={dataCell(colors, colors.dim)}>{h.pctOwned == null ? '—' : fmt(h.pctOwned, 1) + '%'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ═══ Model Info tab ═══════════════════════════════════════════════════════════
function ModelTab({ meta, h2Meta, colors }) {
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
python scripts/xfp/build_index_dashboard.py

# 4. Push to refresh GitHub Pages
git -C xfp-model add docs/index.html
git -C xfp-model commit -m "data: refresh"
git -C xfp-model push`}</pre>
        </div>
      </div>

      {/* ── Hitter (H2) model section ───────────────────────────────────── */}
      {h2Meta && h2Meta.features && (
        <>
          <SectionHeading num="VI" label="Hitter Model — H2 (parallel to V11)"
            right={`${h2Meta.features.length} FEATURES · RIDGE`} colors={colors} />
          <div style={{ padding:'0 32px 24px' }}>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:16, marginBottom:18 }}>
              {[
                { lbl: 'Cross-year r',   v: h2Meta.crossYearR, sub: 'leave-one-out 2018–2025 transitions' },
                { lbl: '2026 YTD r',     v: h2Meta.ytdR, sub: `live deployment, PA ≥ 80, n=${h2Meta.ytdN}` },
                { lbl: '2026 YTD MAE',   v: h2Meta.ytdMae, sub: 'mean absolute error, FP/PA' },
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
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
              <div>
                <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Bias diagnostics</div>
                <div style={{ fontSize:13, fontFamily:MONO, color:colors.text, padding:'8px 12px',
                              background:colors.stripe, borderLeft:`3px solid ${colors.accent}` }}>
                  power_bias_hi: {h2Meta.powerBiasHi >= 0 ? '+' : ''}{h2Meta.powerBiasHi.toFixed(3)}<br/>
                  team_context_bias: {h2Meta.teamContextBias >= 0 ? '+' : ''}{h2Meta.teamContextBias.toFixed(3)}<br/>
                  score (T=1.0): {h2Meta.scoreT1.toFixed(3)}
                </div>
              </div>
              <div>
                <div style={{ fontSize:9, letterSpacing:2, textTransform:'uppercase', color:colors.dim, fontFamily:MONO, marginBottom:8 }}>Bayesian shrinkage priors</div>
                <div style={{ fontSize:12, fontFamily:MONO, color:colors.text, padding:'8px 12px',
                              background:colors.stripe, borderLeft:`3px solid ${colors.accent}` }}>
                  xwoba_on_contact: PRIOR_N={h2Meta.priorXwoba[0]}, PRIOR_MEAN={h2Meta.priorXwoba[1]}<br/>
                  contact_pct: PRIOR_N={h2Meta.priorContact[0]}, PRIOR_MEAN={h2Meta.priorContact[1]}<br/>
                  pa_per_game (display): {h2Meta.paPerGame}
                </div>
              </div>
            </div>
            <table style={{ width:'100%', borderCollapse:'collapse', fontVariantNumeric:'tabular-nums', marginTop:18 }}>
              <thead>
                <tr style={{ borderBottom:`2px solid ${colors.text}` }}>
                  <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Feature</th>
                  <th style={{ padding:'8px', textAlign:'right', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Standardized coef</th>
                  <th style={{ padding:'8px', textAlign:'left', fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1.5, textTransform:'uppercase' }}>Direction</th>
                </tr>
              </thead>
              <tbody>
                {h2Meta.coefficients.map(c => (
                  <tr key={c.feat} style={{ borderBottom:`1px solid ${colors.faint}` }}>
                    <td style={{ padding:'7px 8px', fontSize:13, fontFamily:MONO }}>{c.feat}</td>
                    <td style={{ ...dataCell(colors, c.coef > 0 ? colors.pos : colors.neg), fontWeight:600 }}>
                      {c.coef > 0 ? '+' : ''}{c.coef.toFixed(4)}
                    </td>
                    <td style={{ padding:'7px 8px', fontSize:11, color:colors.dim }}>
                      {c.coef > 0 ? '↑ raises xFP/PA' : '↓ lowers xFP/PA'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop:14, fontSize:11, color:colors.dim, fontStyle:'italic', lineHeight:1.6 }}>
              <strong>Caveat — team context.</strong> H2 has no per-team run-environment feature.
              R and RBI are noisy across teams (a hitter who moves Yankees → A's keeps his xwOBA but loses ~30 RBI of lineup protection).
              The team_context_bias diagnostic above tracks this gap; if it grows past ±0.05 the model will need a team feature.
            </div>
          </div>
        </>
      )}
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
  // Shared cross-dashboard theme: read/write the same `xfp_theme` localStorage
  // key every other page uses, and mirror it onto <html data-theme> so the
  // pre-React shell + top-nav strip (static CSS) stay in sync. Default DARK to
  // match the rest of the suite (2026-07-23).
  const [dark, setDark] = React.useState(() => {
    try { return localStorage.getItem('xfp_theme') !== 'light'; } catch (e) { return true; }
  });
  React.useEffect(() => {
    try { localStorage.setItem('xfp_theme', dark ? 'dark' : 'light'); } catch (e) {}
    if (dark) document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', 'light');
  }, [dark]);
  return (
    <div style={{ position:'relative', minHeight:'100vh' }}>
      <ThemeToggle dark={dark} setDark={setDark} />
      <Dashboard dark={dark} />
    </div>
  );
}

// ═══ Compare View — me vs one opponent + sneaky trade suggestions ═══════════
function CompareView({ myName, oppName, myBuckets, oppBuckets, trades, colors, posOrder, posLabel }) {
  const fmt = (v, dp = 2) => v == null || isNaN(v) ? '—' : Number(v).toFixed(dp);
  const fmtPct = (v) => v == null || isNaN(v) ? '—' : `${Number(v).toFixed(0)}%`;

  // Compact player line for comparison (smaller than full PlayerRow)
  const CompareRow = ({ p }) => {
    if (!p) return <div style={{ padding:'8px 10px', color:colors.faint, fontFamily:MONO, fontSize:10, fontStyle:'italic' }}>(empty slot)</div>;
    const fpLabel = (p.role === 'SP' || p.role === 'RP')
      ? (p.role === 'SP' ? 'fp/start' : 'fp/G')
      : 'fp/G';
    const sampleTxt = p.role === 'SP' ? `${p.sample}GS`
                    : p.role === 'RP' ? `${p.sample}G`
                    : `${p.sample}PA`;
    const fpVal = p.fp_per != null ? fmt(p.fp_per, 2)
                  : (p.marcel_3yr != null ? fmt(p.marcel_3yr, 2) + '*' : '—');
    return (
      <div style={{ padding:'7px 10px', borderBottom:`1px solid ${colors.faint}` }}>
        <div style={{ display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' }}>
          <span style={{ fontSize:13, fontWeight:500 }}>{p.name}</span>
          {p.rank != null && (
            <span style={{ fontSize:9, color:colors.dim, fontFamily:MONO }}>#{p.rank}</span>
          )}
          {p.signal === 'add' && (
            <span style={{ fontSize:8, padding:'1px 4px', border:`1px solid ${colors.accent}`,
                           color:colors.accent, borderRadius:2, fontFamily:MONO }}>ADD</span>
          )}
          {p.signal === 'drop' && (
            <span style={{ fontSize:8, padding:'1px 4px', border:`1px solid ${colors.warn}`,
                           color:colors.warn, borderRadius:2, fontFamily:MONO }}>DROP</span>
          )}
          {p.slump_pct != null && p.slump_pct < 20 && p.slump_bounce >= 80 && (
            <span style={{ fontSize:8, padding:'1px 4px', border:`1px solid ${colors.pos}`,
                           color:colors.pos, borderRadius:2, fontFamily:MONO }}>BUY-LOW</span>
          )}
          {p.slump_pct != null && p.slump_pct >= 90 && p.slump_bounce != null && p.slump_bounce < 60 && (
            <span style={{ fontSize:8, padding:'1px 4px', border:`1px solid ${colors.warn}`,
                           color:colors.warn, borderRadius:2, fontFamily:MONO }}>SELL-HIGH</span>
          )}
        </div>
        <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO, marginTop:2 }}>
          {fpVal} {fpLabel} · {sampleTxt}
          {p.ytd_fp != null && p.ytd_fp > 0 && (<> · YTD <span style={{ color:colors.text }}>{fmt(p.ytd_fp, 0)}</span></>)}
          {p.ros_fp != null && p.ros_fp > 0 && (<> · RoS <span style={{ color:colors.accent }}>{fmt(p.ros_fp, 0)}</span></>)}
        </div>
      </div>
    );
  };

  // Compute team-level RoS totals for the header
  const sumRos = (bucks) => {
    let t = 0;
    for (const k of posOrder) for (const p of (bucks[k] || [])) t += (p.ros_fp || 0);
    return t;
  };
  const myRos = sumRos(myBuckets);
  const oppRos = sumRos(oppBuckets);

  // Sneaky trade card
  const TradeCard = ({ t }) => (
    <div style={{ padding:'12px 14px', border:`1px solid ${colors.border}`, borderRadius:4,
                  marginBottom:10, background:colors.panel }}>
      <div style={{ display:'flex', alignItems:'baseline', gap:10, marginBottom:6 }}>
        <span style={{ fontSize:9, fontFamily:MONO, color:colors.dim, letterSpacing:1.5,
                       textTransform:'uppercase' }}>{t.bucket} swap</span>
        <span style={{ fontSize:14, fontFamily:SERIF, fontStyle:'italic', color:colors.accent }}>
          edge for me: +{t.edge_for_me} FP
        </span>
        <span style={{ fontSize:10, color:colors.dim, fontFamily:MONO, marginLeft:'auto' }}>
          (perceived diff {t.perceived_diff >= 0 ? '+' : ''}{t.perceived_diff} · model diff {t.model_diff >= 0 ? '+' : ''}{t.model_diff})
        </span>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr auto 1fr', gap:12, alignItems:'center' }}>
        <div style={{ textAlign:'right' }}>
          <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:1, textTransform:'uppercase' }}>
            you send
          </div>
          <div style={{ fontSize:14, fontWeight:500 }}>{t.mine.name}
            <span style={{ fontSize:9, color:colors.dim, fontFamily:MONO, marginLeft:6 }}>#{t.mine.rank}</span>
          </div>
          <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO }}>
            YTD {fmt(t.mine.ytd_fp, 0)} · RoS {fmt(t.mine.ros_fp, 0)}
            {t.mine.slump_pct != null && (<> · slump {fmtPct(t.mine.slump_pct)}/bnc {fmtPct(t.mine.slump_bounce)}</>)}
          </div>
        </div>
        <div style={{ fontSize:14, color:colors.accent, fontFamily:MONO }}>↔</div>
        <div>
          <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:1, textTransform:'uppercase' }}>
            you receive
          </div>
          <div style={{ fontSize:14, fontWeight:500 }}>{t.theirs.name}
            <span style={{ fontSize:9, color:colors.dim, fontFamily:MONO, marginLeft:6 }}>#{t.theirs.rank}</span>
          </div>
          <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO }}>
            YTD {fmt(t.theirs.ytd_fp, 0)} · RoS {fmt(t.theirs.ros_fp, 0)}
            {t.theirs.slump_pct != null && (<> · slump {fmtPct(t.theirs.slump_pct)}/bnc {fmtPct(t.theirs.slump_bounce)}</>)}
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div style={{ marginTop:8, marginBottom:24, padding:16, border:`1px solid ${colors.border}`,
                  background:colors.panel, borderRadius:6 }}>
      <div style={{ display:'flex', alignItems:'baseline', gap:18, marginBottom:14 }}>
        <h2 style={{ fontSize:20, margin:0, fontWeight:400, fontFamily:SERIF, fontStyle:'italic' }}>
          {myName} <span style={{ color:colors.dim }}>vs</span> {oppName}
        </h2>
        <span style={{ fontSize:11, fontFamily:MONO, color:colors.dim, letterSpacing:1 }}>
          RoS FP: {fmt(myRos, 0)} vs {fmt(oppRos, 0)}
          {myRos > oppRos
            ? <span style={{ color:colors.pos, marginLeft:6 }}>(+{fmt(myRos - oppRos, 0)} edge)</span>
            : <span style={{ color:colors.warn, marginLeft:6 }}>({fmt(myRos - oppRos, 0)} deficit)</span>}
        </span>
      </div>

      {/* Trade suggestions */}
      {trades && trades.length > 0 ? (
        <div style={{ marginBottom:18 }}>
          <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:2,
                        textTransform:'uppercase', marginBottom:8 }}>
            Top sneaky trade ideas — fair-looking by YTD totals, model says I gain RoS
          </div>
          {trades.slice(0, 5).map((t, i) => <TradeCard key={i} t={t} />)}
          {trades.length === 0 && (
            <div style={{ fontSize:11, color:colors.dim, fontFamily:MONO }}>
              No qualifying trades found (need edge ≥ 25 FP, perceived gap ≤ 30 FP).
            </div>
          )}
        </div>
      ) : (
        <div style={{ padding:'10px 12px', color:colors.dim, fontFamily:MONO, fontSize:11,
                      marginBottom:18 }}>
          No qualifying trades found (need edge ≥ 25 FP, perceived gap ≤ 30 FP).
        </div>
      )}

      {/* Side-by-side roster */}
      <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:2,
                    textTransform:'uppercase', marginBottom:8, paddingBottom:4,
                    borderBottom:`1px solid ${colors.faint}` }}>
        Position-by-position roster
      </div>
      {posOrder.map(pos => {
        const mine = myBuckets[pos] || [];
        const theirs = oppBuckets[pos] || [];
        if (mine.length === 0 && theirs.length === 0) return null;
        const maxRows = Math.max(mine.length, theirs.length);
        return (
          <div key={pos} style={{ marginTop:14 }}>
            <div style={{ fontSize:11, fontFamily:MONO, color:colors.text, letterSpacing:1.5,
                          textTransform:'uppercase', marginBottom:4 }}>
              {posLabel[pos]}
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:18 }}>
              <div>
                {Array.from({length: maxRows}).map((_, i) => <CompareRow key={i} p={mine[i]} />)}
              </div>
              <div>
                {Array.from({length: maxRows}).map((_, i) => <CompareRow key={i} p={theirs[i]} />)}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ═══ Team Audit Tab ═══════════════════════════════════════════════════════════
// ═══ Lineup Overlap Analyzer (used inside AdvisoryTab) ═══════════════════════
function LineupOverlap({ overlap, colors }) {
  const [selectedOpp, setSelectedOpp] = React.useState(null);
  if (!overlap || !overlap.opponents) {
    return <div style={{ fontSize:11, fontFamily:MONO, color:colors.dim }}>
      (run scripts/xfp/opponent_lineup_overlap.py to populate)
    </div>;
  }

  const POS_ORDER = ['C', '1B', '2B', '3B', 'SS', 'MI (2B/SS)', 'CI (1B/3B)',
                     'OF', 'UTIL', 'SP', 'RP'];
  const fmt = (v, d = 1) => v == null || isNaN(v) ? '—' : Number(v).toFixed(d);
  const sign = (v, d = 1) => {
    if (v == null || isNaN(v)) return '—';
    const n = Number(v);
    return (n >= 0 ? '+' : '') + n.toFixed(d);
  };

  const cellStyle = { padding:'4px 8px', borderBottom:`1px solid ${colors.border}`,
                      fontFamily:MONO, fontSize:11, fontVariantNumeric:'tabular-nums' };
  const headStyle = { ...cellStyle, fontWeight:600, color:colors.dim, textTransform:'uppercase',
                      fontSize:9, letterSpacing:0.5 };
  const edgeColor = (e) => e == null ? colors.text : e > 0 ? '#33aa44' : e < 0 ? '#cc5544' : colors.text;
  const detail = selectedOpp ? overlap.opponents.find(o => o.opp_name === selectedOpp) : null;

  return (
    <div>
      <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, marginBottom:8 }}>
        Per-position projected RoS FP value for each opposing team's STARTING
        lineup (1 C, 1 1B, 1 2B, 1 3B, 1 SS, 3 OF, 5 SP, 3 RP).
        Edge = (my position value − their position value). Sum total = expected
        weekly fp gap before luck/scheduling. Click a row for per-position detail.
      </div>

      <div style={{ overflowX:'auto', marginBottom:16 }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr>
            <th style={headStyle}>Opponent</th>
            <th style={{...headStyle, textAlign:'center'}}>Standing</th>
            <th style={{...headStyle, textAlign:'center'}}>H2H</th>
            <th style={{...headStyle, textAlign:'right'}}>Total Edge</th>
            <th style={headStyle}>Biggest Strength</th>
            <th style={headStyle}>Biggest Weakness</th>
            <th style={{...headStyle, textAlign:'right'}}>Top Trade Tgt</th>
          </tr></thead>
          <tbody>
            {overlap.opponents.map(o => {
              const isSel = selectedOpp === o.opp_name;
              const tgt = (o.trade_targets && o.trade_targets[0]) || null;
              return (
                <tr key={o.opp_name}
                    onClick={() => setSelectedOpp(isSel ? null : o.opp_name)}
                    style={{ cursor:'pointer', background: isSel ? colors.faint : 'transparent' }}>
                  <td style={cellStyle}>{o.opp_name}</td>
                  <td style={{...cellStyle, textAlign:'center'}}>{o.standing ?? '—'}</td>
                  <td style={{...cellStyle, textAlign:'center'}}>{o.h2h_record || '—'}</td>
                  <td style={{...cellStyle, textAlign:'right', color: edgeColor(o.total_edge), fontWeight:600}}>
                    {sign(o.total_edge, 1)}
                  </td>
                  <td style={cellStyle}>
                    {o.biggest_advantage} <span style={{ color:edgeColor(o.biggest_advantage_edge) }}>
                      ({sign(o.biggest_advantage_edge, 0)})
                    </span>
                  </td>
                  <td style={cellStyle}>
                    {o.biggest_weakness} <span style={{ color:edgeColor(o.biggest_weakness_edge) }}>
                      ({sign(o.biggest_weakness_edge, 0)})
                    </span>
                  </td>
                  <td style={{...cellStyle, textAlign:'right'}}>
                    {tgt ? `${tgt.position} (edge ${sign(tgt.my_edge,0)})` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {detail && (
        <div style={{ border:`1px solid ${colors.border}`, padding:12, marginBottom:12 }}>
          <div style={{ fontSize:12, fontFamily:MONO, fontWeight:600, marginBottom:6 }}>
            Detail: Ligers vs {detail.opp_name}
          </div>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr>
              <th style={headStyle}>Pos</th>
              <th style={{...headStyle, textAlign:'right'}}>My RoS FP</th>
              <th style={headStyle}>My Starters</th>
              <th style={{...headStyle, textAlign:'right'}}>Their RoS FP</th>
              <th style={headStyle}>Their Starters</th>
              <th style={{...headStyle, textAlign:'right'}}>Edge</th>
            </tr></thead>
            <tbody>
              {POS_ORDER.map(slot => {
                const pp = detail.per_position && detail.per_position[slot];
                if (!pp) return null;
                return (
                  <tr key={slot}>
                    <td style={{...cellStyle, fontWeight:600}}>{slot}</td>
                    <td style={{...cellStyle, textAlign:'right'}}>{fmt(pp.my_value)}</td>
                    <td style={cellStyle}>{(pp.my_starters || []).join(', ') || '—'}</td>
                    <td style={{...cellStyle, textAlign:'right'}}>{fmt(pp.opp_value)}</td>
                    <td style={cellStyle}>{(pp.opp_starters || []).join(', ') || '—'}</td>
                    <td style={{...cellStyle, textAlign:'right', color: edgeColor(pp.edge), fontWeight:600}}>
                      {sign(pp.edge, 1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {detail.trade_targets && detail.trade_targets.length > 0 && (
            <div style={{ marginTop:10 }}>
              <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO, marginBottom:4,
                            textTransform:'uppercase', letterSpacing:0.5 }}>
                Trade-target positions (they have surplus, we're thin)
              </div>
              {detail.trade_targets.map((t, i) => (
                <div key={i} style={{ fontSize:11, fontFamily:MONO, marginBottom:2 }}>
                  <strong>{t.position}</strong>: my edge {sign(t.my_edge,0)} FP;
                  their bench at this pos has {fmt(t.their_bench_value)} FP of surplus.
                  Surplus starters: {(t.their_starters || []).join(', ')}.
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═══ Trade Simulator (used inside AdvisoryTab) ═══════════════════════════════
function TradeSimulator({ weekly, myTeam, colors }) {
  const players = weekly.players || [];
  const playerByPid = React.useMemo(() => {
    const m = {};
    for (const p of players) m[p.pid] = p;
    return m;
  }, [players]);

  const [giveQ, setGiveQ] = React.useState('');
  const [getQ, setGetQ] = React.useState('');
  const [givePid, setGivePid] = React.useState(null);
  const [getPid, setGetPid] = React.useState(null);
  const [year, setYear] = React.useState('2025');
  const [weekIdx, setWeekIdx] = React.useState(0);

  const yearWeeks = (weekly.weeks || {})[year] || [];

  const matchOptions = (q) => {
    if (q.length < 2) return [];
    const qn = q.toLowerCase();
    return players.filter(p => (p.name || '').toLowerCase().includes(qn)).slice(0, 8);
  };
  const giveOpts = matchOptions(giveQ);
  const getOpts = matchOptions(getQ);

  const giveP = givePid != null ? playerByPid[givePid] : null;
  const getP  = getPid  != null ? playerByPid[getPid]  : null;

  const computeReplay = (player) => {
    if (!player) return { weekly_after: [], cumulative: 0, total_pa: 0 };
    const arr = (player.weekly_fp && player.weekly_fp[year]) || [];
    const after = arr.slice(weekIdx);
    const cum = after.reduce((s, v) => s + (v || 0), 0);
    return { weekly_after: after, cumulative: cum };
  };

  const giveR = computeReplay(giveP);
  const getR  = computeReplay(getP);
  const deltaCum = (getR.cumulative || 0) - (giveR.cumulative || 0);
  const weekLabels = yearWeeks.slice(weekIdx);

  const cellStyle = { padding:'4px 8px', borderBottom:`1px solid ${colors.border}`,
                      fontFamily:MONO, fontSize:11, fontVariantNumeric:'tabular-nums' };
  const headStyle = { ...cellStyle, fontWeight:600, color:colors.dim,
                      textTransform:'uppercase', fontSize:9, letterSpacing:0.5 };
  const inputStyle = { padding:'4px 8px', fontSize:12, fontFamily:MONO,
                       border:`1px solid ${colors.border}`,
                       background:colors.panel, color:colors.text, width:240 };
  const btnStyle = (active) => ({
    padding:'4px 10px', fontSize:11, fontFamily:MONO, cursor:'pointer',
    border:`1px solid ${active ? colors.accent : colors.border}`,
    background: active ? colors.accent : colors.panel,
    color: active ? '#fff' : colors.dim, marginRight:4,
  });

  return (
    <div>
      <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, marginBottom:12 }}>
        Pick give/get/date and see what would have actually happened.
        FP uses league formulas (TB+R+RBI+BB+HBP+SB−K for hitters;
        K+IP*3.3−H−2*ER−BB−HBP for pitchers). R is HR-based proxy and SB is
        rate-based, so absolute totals run ~15% low — relative comparison
        between two players is what matters.
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:16, marginBottom:16 }}>
        <div>
          <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase', marginBottom:4 }}>Give up (Player you'd trade away)</div>
          <input value={giveQ} onChange={e => { setGiveQ(e.target.value); setGivePid(null); }}
                 style={inputStyle} placeholder="Type to search…" />
          {giveOpts.length > 0 && givePid == null && (
            <div style={{ marginTop:4, maxHeight:160, overflowY:'auto', border:`1px solid ${colors.border}` }}>
              {giveOpts.map(p => (
                <div key={p.pid} onClick={() => { setGivePid(p.pid); setGiveQ(p.name); }}
                     style={{ padding:'4px 8px', cursor:'pointer', fontFamily:MONO, fontSize:11,
                              background: colors.panel, borderBottom:`1px solid ${colors.faint}` }}>
                  {p.name} <span style={{ color:colors.dim }}>({p.role})</span>
                </div>
              ))}
            </div>
          )}
          {giveP && <div style={{ marginTop:4, fontSize:11, fontFamily:MONO, color:colors.accent }}>
            ✓ {giveP.name} ({giveP.role}) {' '}
            <span onClick={() => { setGivePid(null); setGiveQ(''); }} style={{ cursor:'pointer', color:colors.dim }}>(clear)</span>
          </div>}
        </div>
        <div>
          <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase', marginBottom:4 }}>Get (Player you'd receive)</div>
          <input value={getQ} onChange={e => { setGetQ(e.target.value); setGetPid(null); }}
                 style={inputStyle} placeholder="Type to search…" />
          {getOpts.length > 0 && getPid == null && (
            <div style={{ marginTop:4, maxHeight:160, overflowY:'auto', border:`1px solid ${colors.border}` }}>
              {getOpts.map(p => (
                <div key={p.pid} onClick={() => { setGetPid(p.pid); setGetQ(p.name); }}
                     style={{ padding:'4px 8px', cursor:'pointer', fontFamily:MONO, fontSize:11,
                              background: colors.panel, borderBottom:`1px solid ${colors.faint}` }}>
                  {p.name} <span style={{ color:colors.dim }}>({p.role})</span>
                </div>
              ))}
            </div>
          )}
          {getP && <div style={{ marginTop:4, fontSize:11, fontFamily:MONO, color:colors.accent }}>
            ✓ {getP.name} ({getP.role}) {' '}
            <span onClick={() => { setGetPid(null); setGetQ(''); }} style={{ cursor:'pointer', color:colors.dim }}>(clear)</span>
          </div>}
        </div>
        <div>
          <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase', marginBottom:4 }}>Year</div>
          <div style={{ marginBottom:8 }}>
            {Object.keys(weekly.weeks || {}).sort().map(y => (
              <button key={y} onClick={() => { setYear(y); setWeekIdx(0); }} style={btnStyle(year === y)}>{y}</button>
            ))}
          </div>
          <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase', marginBottom:4 }}>Trade week (start)</div>
          <select value={weekIdx} onChange={e => setWeekIdx(parseInt(e.target.value))}
                  style={{...inputStyle, width:200 }}>
            {yearWeeks.map((w, i) => <option key={i} value={i}>{w}</option>)}
          </select>
        </div>
      </div>

      {giveP && getP && yearWeeks.length > 0 && (
        <div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:24, marginBottom:16 }}>
            <div style={{ padding:12, border:`1px solid ${colors.border}` }}>
              <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase' }}>GIVE: {giveP.name}</div>
              <div style={{ fontSize:24, fontFamily:MONO, marginTop:4 }}>{Number(giveR.cumulative || 0).toFixed(1)} FP</div>
              <div style={{ fontSize:10, color:colors.dim }}>from {weekLabels[0] || '—'} on ({weekLabels.length} wk)</div>
            </div>
            <div style={{ padding:12, border:`1px solid ${colors.border}` }}>
              <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase' }}>GET: {getP.name}</div>
              <div style={{ fontSize:24, fontFamily:MONO, marginTop:4 }}>{Number(getR.cumulative || 0).toFixed(1)} FP</div>
              <div style={{ fontSize:10, color:colors.dim }}>same window</div>
            </div>
            <div style={{ padding:12, border:`2px solid ${deltaCum >= 0 ? '#33aa44' : '#cc5544'}` }}>
              <div style={{ fontSize:9, color:colors.dim, fontFamily:MONO, letterSpacing:1, textTransform:'uppercase' }}>NET (got − gave)</div>
              <div style={{ fontSize:28, fontFamily:MONO, marginTop:4, color: deltaCum >= 0 ? '#33aa44' : '#cc5544' }}>
                {deltaCum >= 0 ? '+' : ''}{Number(deltaCum).toFixed(1)} FP
              </div>
              <div style={{ fontSize:11, fontFamily:MONO, marginTop:2 }}>{deltaCum >= 0 ? 'WIN' : 'LOSS'} for the trade</div>
            </div>
          </div>

          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr>
                <th style={headStyle}>Week</th>
                <th style={{...headStyle, textAlign:'right'}}>GIVE fp</th>
                <th style={{...headStyle, textAlign:'right'}}>GET fp</th>
                <th style={{...headStyle, textAlign:'right'}}>Δ (week)</th>
                <th style={{...headStyle, textAlign:'right'}}>Δ cumulative</th>
              </tr></thead>
              <tbody>
                {weekLabels.map((w, i) => {
                  const gv = giveR.weekly_after[i] || 0;
                  const gt = getR.weekly_after[i] || 0;
                  const d = gt - gv;
                  const cumThru = (giveR.weekly_after.slice(0, i+1).reduce((s, v) => s + (v||0), 0)
                                    - getR.weekly_after.slice(0, i+1).reduce((s, v) => s + (v||0), 0));
                  return (
                    <tr key={i}>
                      <td style={cellStyle}>{w}</td>
                      <td style={{...cellStyle, textAlign:'right'}}>{gv.toFixed(1)}</td>
                      <td style={{...cellStyle, textAlign:'right'}}>{gt.toFixed(1)}</td>
                      <td style={{...cellStyle, textAlign:'right', color: d >= 0 ? '#33aa44' : '#cc5544' }}>
                        {d >= 0 ? '+' : ''}{d.toFixed(1)}
                      </td>
                      <td style={{...cellStyle, textAlign:'right', color: -cumThru >= 0 ? '#33aa44' : '#cc5544' }}>
                        {(-cumThru) >= 0 ? '+' : ''}{(-cumThru).toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {(!giveP || !getP) && (
        <div style={{ padding:'16px 0', fontSize:11, fontFamily:MONO, color:colors.dim }}>
          Pick both players above to run the replay.
        </div>
      )}
    </div>
  );
}

// ═══ Advisory tab ═════════════════════════════════════════════════════════════
function AdvisoryTab({ advisory, myTeam, colors }) {
  const [ligersOnly, setLigersOnly] = React.useState(false);
  const [pitchFilter, setPitchFilter] = React.useState('SL');

  // Build set of my-team names (both "First Last" and rh3 "Last, First")
  const myNames = React.useMemo(() => {
    const s = new Set();
    const add = (n) => {
      if (!n) return;
      s.add(n);
      const parts = n.split(' ');
      if (parts.length >= 2) {
        s.add(parts.slice(-1)[0] + ', ' + parts.slice(0, -1).join(' '));
      }
      if (n.includes(',')) {
        const [last, first] = n.split(',').map(p => p.trim());
        s.add(first + ' ' + last);
      }
    };
    (myTeam?.pitchers || []).forEach(p => add(p.name || p.player_name));
    (myTeam?.hitters || []).forEach(p => add(p.name || p.player_name));
    return s;
  }, [myTeam]);

  const filt = (rows) => {
    if (!ligersOnly) return rows;
    return rows.filter(r => myNames.has(r.player_name));
  };

  const cellStyle = { padding:'4px 8px', borderBottom:`1px solid ${colors.border}`,
                      fontFamily:MONO, fontSize:11, fontVariantNumeric:'tabular-nums' };
  const headStyle = { ...cellStyle, fontWeight:600, color:colors.dim, textTransform:'uppercase', fontSize:9, letterSpacing:0.5 };
  const sectionH = { fontSize:14, fontFamily:MONO, fontWeight:600, letterSpacing:1, textTransform:'uppercase',
                     color:colors.text, margin:'24px 0 4px 0' };
  const subH = { fontSize:10, fontFamily:MONO, color:colors.dim, marginBottom:8 };

  const fmt = (v, dp = 2) => v == null || isNaN(v) ? '—' : Number(v).toFixed(dp);
  const sign = (v, dp = 4) => {
    if (v == null || isNaN(v)) return '—';
    const n = Number(v);
    return (n > 0 ? '+' : '') + n.toFixed(dp);
  };

  // Color a divergence cell green=our model bullish, red=our model bearish
  const divColor = (v) => {
    if (v == null) return colors.text;
    return v > 0 ? '#33aa44' : v < 0 ? '#cc5544' : colors.text;
  };

  const Table = ({ rows, columns, keyCol }) => (
    rows.length === 0
      ? <div style={{...subH, padding:'8px 0'}}>No rows match.</div>
      : <div style={{ overflowX:'auto', marginBottom:8 }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr>{columns.map(c => <th key={c.key} style={{...headStyle, textAlign: c.align || 'left'}}>{c.label}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) =>
            <tr key={r[keyCol] || i}>
              {columns.map(c => <td key={c.key} style={{...cellStyle, textAlign: c.align || 'left',
                                                          color: c.color ? c.color(r[c.key]) : colors.text}}>
                {c.render ? c.render(r) : (r[c.key] == null ? '—' : r[c.key])}
              </td>)}
            </tr>
          )}</tbody>
        </table>
      </div>
  );

  // Panel 1 — Velocity drop
  const velo = filt(advisory.velocity || []);
  const veloCols = [
    { key:'player_name', label:'Pitcher' },
    { key:'starts_2026', label:'2026 GS', align:'right', render: r => fmt(r.starts_2026, 0) },
    { key:'career_velo', label:'Career FB', align:'right', render: r => fmt(r.career_velo, 2) },
    { key:'last5_velo', label:'Last 5 FB', align:'right', render: r => fmt(r.last5_velo, 2) },
    { key:'velo_drop_mph', label:'Δ mph', align:'right', color: v => v <= -1.0 ? '#cc5544' : v >= 1.0 ? '#33aa44' : colors.text,
      render: r => sign(r.velo_drop_mph, 2) },
    { key:'alert', label:'Flag', align:'center' },
    { key:'last_start_date', label:'Last Start' },
  ];

  // Panels 2/3 — Ensemble divergence (over-bull = our model > consensus)
  const h_over = filt(advisory.ensemble_hitters_overbull || []);
  const h_under = filt(advisory.ensemble_hitters_underbull || []);
  const p_over = filt(advisory.ensemble_pitchers_overbull || []);
  const p_under = filt(advisory.ensemble_pitchers_underbull || []);
  const ensembleHitterCols = [
    { key:'player_name', label:'Hitter' },
    { key:'team', label:'Team', align:'center' },
    { key:'xfp_rh3_per_pa', label:'Our fp/PA', align:'right', render: r => fmt(r.xfp_rh3_per_pa, 3) },
    { key:'ext_mean_fp_per_pa', label:'Consensus fp/PA', align:'right', render: r => fmt(r.ext_mean_fp_per_pa, 3) },
    { key:'divergence', label:'Δ (Ours − Consensus)', align:'right', color: divColor, render: r => sign(r.divergence, 4) },
    { key:'ext_n_systems', label:'# Systems', align:'center', render: r => fmt(r.ext_n_systems, 0) },
  ];
  const ensemblePitcherCols = [
    { key:'player_name', label:'Pitcher' },
    { key:'xfp_rp3_per_start', label:'Our fp/G', align:'right', render: r => fmt(r.xfp_rp3_per_start, 2) },
    { key:'ext_mean_fp_per_g', label:'Consensus fp/G', align:'right', render: r => fmt(r.ext_mean_fp_per_g, 2) },
    { key:'divergence', label:'Δ', align:'right', color: divColor, render: r => sign(r.divergence, 2) },
    { key:'ext_n_systems', label:'# Systems', align:'center', render: r => fmt(r.ext_n_systems, 0) },
  ];

  // Panel 4 — TTO penalty
  const tto = filt(advisory.tto_penalty || []);
  const ttoCols = [
    { key:'player_name', label:'Pitcher' },
    { key:'total_pa', label:'Career PA', align:'right', render: r => fmt(r.total_pa, 0) },
    { key:'tto1_rate', label:'1st time', align:'right', render: r => fmt(r.tto1_rate, 3) },
    { key:'tto2_rate', label:'2nd time', align:'right', render: r => fmt(r.tto2_rate, 3) },
    { key:'tto3_rate', label:'3rd time', align:'right', render: r => fmt(r.tto3_rate, 3) },
    { key:'tto3_minus_tto1', label:'Δ', align:'right', color: v => v < -0.05 ? '#cc5544' : colors.text,
      render: r => sign(r.tto3_minus_tto1, 4) },
  ];

  // Panel 5 — Bullpen quality
  const bp = advisory.bullpen_2026 || [];
  const bpCols = [
    { key:'team', label:'Team', align:'center' },
    { key:'bullpen_fp_per_ip', label:'fp/IP', align:'right', render: r => fmt(r.bullpen_fp_per_ip, 3) },
    { key:'n_rps', label:'# RPs', align:'right', render: r => fmt(r.n_rps, 0) },
    { key:'bullpen_ip', label:'Total IP', align:'right', render: r => fmt(r.bullpen_ip, 1) },
  ];

  // Panel 6 — Pitch weakness
  const allWeakness = advisory.pitch_weakness_top || [];
  const filteredWeakness = filt(allWeakness.filter(r => r.ptg === pitchFilter));
  const weaknessCols = [
    { key:'player_name', label:'Hitter' },
    { key:'ptg', label:'Pitch', align:'center' },
    { key:'swings', label:'Swings', align:'right', render: r => fmt(r.swings, 0) },
    { key:'whiff_per_swing', label:'Whiff %', align:'right', color: v => v >= 40 ? '#cc5544' : colors.text,
      render: r => fmt(r.whiff_per_swing, 1) + '%' },
    { key:'xwoba_avg', label:'xwOBA when contact', align:'right', render: r => fmt(r.xwoba_avg, 3) },
  ];

  return (
    <div style={{ padding:'16px 32px' }}>
      <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:8 }}>
        <h2 style={{ fontSize:16, fontFamily:MONO, fontWeight:600, letterSpacing:1, textTransform:'uppercase',
                     color:colors.text, margin:0 }}>Advisory signals</h2>
        <label style={{ fontSize:11, fontFamily:MONO, color:colors.dim, cursor:'pointer' }}>
          <input type="checkbox" checked={ligersOnly} onChange={e => setLigersOnly(e.target.checked)}
                 style={{ marginRight:4 }} /> My team only
        </label>
      </div>
      <div style={{ fontSize:10, fontFamily:MONO, color:colors.dim, marginBottom:16 }}>
        Decision-support signals — none of these are model features. They're validated as marginal or
        as decision-support tools only. Use for tactical roster moves, not for model predictions.
      </div>

      <h3 style={sectionH}>1. SP velocity decline (injury early-warning)</h3>
      <div style={subH}>Rolling-5-start mean fastball velocity vs career baseline. ≥ −1.0 mph drop flagged DECLINING.</div>
      <Table rows={velo} columns={veloCols} keyCol="player_name" />

      <h3 style={sectionH}>2. Ensemble divergence — HITTERS</h3>
      <div style={subH}>Where our RH3 model disagrees with the average of ATC / Steamer / ZiPS / TheBatX RoS projections. Big gaps = re-examine.</div>
      <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Our model MORE bullish (potential trade targets):</div>
      <Table rows={h_over} columns={ensembleHitterCols} keyCol="player_name" />
      <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Our model LESS bullish (potential trade chips):</div>
      <Table rows={h_under} columns={ensembleHitterCols} keyCol="player_name" />

      <h3 style={sectionH}>3. Ensemble divergence — PITCHERS</h3>
      <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Our model MORE bullish:</div>
      <Table rows={p_over} columns={ensemblePitcherCols} keyCol="player_name" />
      <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Our model LESS bullish:</div>
      <Table rows={p_under} columns={ensemblePitcherCols} keyCol="player_name" />

      <h3 style={sectionH}>4. Time-through-order penalty (SP hook-early candidates)</h3>
      <div style={subH}>core_fp/PA drop from 1st to 3rd time through. Strongly negative Δ = SP gets clobbered late — bullpen takes over → fewer Ks for fantasy.</div>
      <Table rows={tto} columns={ttoCols} keyCol="player_name" />

      <h3 style={sectionH}>5. Bullpen quality — 2026 team rankings</h3>
      <div style={subH}>Team RP fp/IP through current date. Bad bullpens = SPs less likely to get wins (less reliable cleanups); also affects RP holds/saves leverage.</div>
      <Table rows={bp} columns={bpCols} keyCol="team" />

      <h3 style={sectionH}>6. Lineup optimizer — this week's SP cap picture</h3>
      {advisory.lineup_optimizer ? (
        <div>
          <div style={subH}>
            As of {advisory.lineup_optimizer.as_of}. Cap: {advisory.lineup_optimizer.cap} SP starts/wk.
            Total projected starts: <strong>{advisory.lineup_optimizer.total_starts}</strong>
            {' • '}counting toward score: <strong>{advisory.lineup_optimizer.counting_starts}</strong>
            {' • '}expected fp from counting starts: <strong>{advisory.lineup_optimizer.expected_counting_fp}</strong>
            {advisory.lineup_optimizer.total_starts > advisory.lineup_optimizer.cap &&
              <span style={{ color:'#cc5544', marginLeft:8 }}>
                ⚠ OVER CAP — bench-loss if unoptimized: {advisory.lineup_optimizer.bench_loss_if_unoptimized} fp
              </span>}
          </div>
          <Table rows={advisory.lineup_optimizer.starts || []} keyCol="gamePk" columns={[
            { key:'date', label:'Date' },
            { key:'pitcher', label:'Pitcher' },
            { key:'team_abbr', label:'Team', align:'center' },
            { key:'opp_team_abbr', label:'vs', align:'center' },
            { key:'is_home', label:'Home', align:'center', render: r => r.is_home ? 'H' : 'A' },
            { key:'xfp_per_start', label:'Base fp/G', align:'right', render: r => fmt(r.xfp_per_start, 2) },
            { key:'xfp_per_start_sched', label:'Adj fp/G', align:'right', render: r => fmt(r.xfp_per_start_sched, 2) },
            { key:'rank', label:'Rank', align:'center' },
            { key:'decision', label:'Action', align:'center',
              color: v => v === 'START' ? '#33aa44' : '#cc5544' },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/lineup_optimizer.py to populate)</div>}

      <h3 style={sectionH}>7. Opponent scouting — league-wide roster value vs standing</h3>
      {advisory.opponent_scouting ? (
        <div>
          <div style={subH}>
            Underperformers (value-rank ≪ standing-rank) may be trade targets;
            overperformers (value-rank ≫ standing-rank) are likely to regress.
          </div>
          <Table rows={advisory.opponent_scouting} keyCol="team_id" columns={[
            { key:'team_name', label:'Team' },
            { key:'wins', label:'W', align:'right' },
            { key:'losses', label:'L', align:'right' },
            { key:'standing', label:'Rank', align:'right' },
            { key:'total_value', label:'Total Value', align:'right', render: r => fmt(r.total_value, 0) },
            { key:'hitter_ros_fp_total', label:'Hitter RoS', align:'right', render: r => fmt(r.hitter_ros_fp_total, 0) },
            { key:'sp_value_proxy', label:'SP Proxy', align:'right', render: r => fmt(r.sp_value_proxy, 0) },
            { key:'adds_30d', label:'Adds/30d', align:'right' },
            { key:'drops_30d', label:'Drops/30d', align:'right' },
            { key:'trades_30d', label:'Trades/30d', align:'right' },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/opponent_scouting.py to populate)</div>}

      <h3 style={sectionH}>8. Lineup overlap — per-opponent positional edge map</h3>
      <LineupOverlap overlap={advisory.lineup_overlap} colors={colors} />

      <h3 style={sectionH}>9. Smart trade finder — model-favored 1-for-1s</h3>
      {advisory.smart_trade_finder ? (
        <div>
          <div style={subH}>
            Found {(advisory.smart_trade_finder.global_top || []).length > 0 ?
              Object.values(advisory.smart_trade_finder.by_opponent || {})
                    .reduce((s, list) => s + list.length, 0) : 0
            } fair trades (perceived value within {(advisory.smart_trade_finder.fairness_threshold * 100).toFixed(0)}%) projecting at least +{advisory.smart_trade_finder.min_gain} RoS FP gain.
            "Fair" = YTD FP gap. Sortable by RoS gain.
          </div>
          {Object.entries(advisory.smart_trade_finder.by_opponent || {}).map(([opp, trades]) => (
            <div key={opp} style={{ marginBottom:12 }}>
              <div style={{ fontSize:11, fontFamily:MONO, fontWeight:600, color:colors.text, marginTop:8, marginBottom:4 }}>
                vs {opp} ({trades.length} ideas)
              </div>
              <Table rows={trades} keyCol="get" columns={[
                { key:'give', label:'Give' },
                { key:'give_ytd', label:'YTD', align:'right', render: r => fmt(r.give_ytd, 0) },
                { key:'get', label:'Get' },
                { key:'get_ytd', label:'YTD', align:'right', render: r => fmt(r.get_ytd, 0) },
                { key:'fair_ratio', label:'Fair Gap', align:'right',
                  render: r => (r.fair_ratio * 100).toFixed(0) + '%',
                  color: v => v < 0.20 ? '#33aa44' : v < 0.30 ? colors.text : '#cc5544' },
                { key:'edge_gain_ros', label:'+RoS FP', align:'right', color: () => '#33aa44',
                  render: r => '+' + fmt(r.edge_gain_ros, 1) },
              ]} />
            </div>
          ))}
        </div>
      ) : <div style={subH}>(run scripts/xfp/smart_trade_finder.py to populate)</div>}

      <h3 style={sectionH}>10. Waiver watch — who's scooping value, who's leaking it</h3>
      {advisory.waiver_watch ? (
        <div>
          <div style={subH}>
            Last {advisory.waiver_watch.days} days of league transactions × RoS projection lookup.
          </div>

          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:12}}>Net waiver effectiveness (added FP − dropped FP):</div>
          <Table rows={advisory.waiver_watch.net_effectiveness || []} keyCol="team_name" columns={[
            { key:'team_name', label:'Team' },
            { key:'value_added', label:'Added RoS', align:'right', render: r => fmt(r.value_added, 0) },
            { key:'value_dropped', label:'Dropped RoS', align:'right', render: r => fmt(r.value_dropped, 0) },
            { key:'net', label:'Net', align:'right', color: v => v >= 0 ? '#33aa44' : '#cc5544',
              render: r => sign(r.net, 0) },
          ]} />

          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:12}}>Biggest pickups (other teams scooped these — what you might've missed):</div>
          <Table rows={(advisory.waiver_watch.biggest_pickups || []).slice(0, 15)} keyCol="player" columns={[
            { key:'date', label:'Date', render: r => String(r.date).slice(0, 10) },
            { key:'team_name', label:'Team' },
            { key:'player', label:'Player' },
            { key:'role', label:'Role', align:'center' },
            { key:'ros_fp', label:'RoS FP', align:'right', render: r => fmt(r.ros_fp, 0) },
          ]} />

          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:12}}>Valuable drops (these were dropped — if any are still FAs, claim now):</div>
          <Table rows={(advisory.waiver_watch.valuable_drops || []).slice(0, 15)} keyCol="player" columns={[
            { key:'date', label:'Date', render: r => String(r.date).slice(0, 10) },
            { key:'team_name', label:'Dropped By' },
            { key:'player', label:'Player' },
            { key:'role', label:'Role', align:'center' },
            { key:'ros_fp', label:'RoS FP', align:'right', render: r => fmt(r.ros_fp, 0) },
          ]} />

          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:12}}>Leaky-roster teams (high cumulative value dropped — monitor for future drops):</div>
          <Table rows={advisory.waiver_watch.leaky_teams || []} keyCol="team_name" columns={[
            { key:'team_name', label:'Team' },
            { key:'n_drops', label:'# Drops', align:'right' },
            { key:'total_value_dropped', label:'Total RoS Dropped', align:'right',
              render: r => fmt(r.total_value_dropped, 0) },
            { key:'worst_drop_value', label:'Worst', align:'right',
              render: r => fmt(r.worst_drop_value, 0) },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/waiver_watch.py to populate)</div>}

      <h3 style={sectionH}>11. Trade simulator — counterfactual week-by-week replay</h3>
      <TradeSimulator weekly={window.XFP_WEEKLY || {players:[],weeks:{}}}
                       myTeam={myTeam} colors={colors} />

      <h3 style={sectionH}>12. Season simulation — playoff & title probabilities (Monte Carlo)</h3>
      {advisory.monte_carlo ? (
        <div>
          <div style={subH}>
            {advisory.monte_carlo.n_sims.toLocaleString()} simulated seasons from current state.
            σ per team-week = {advisory.monte_carlo.sigma_per_week} FP.
          </div>
          <Table rows={advisory.monte_carlo.standings_sim || []} keyCol="team" columns={[
            { key:'team', label:'Team' },
            { key:'current_record', label:'Now', align:'center' },
            { key:'weekly_mean', label:'Weekly Mean', align:'right' },
            { key:'playoff_pct', label:'Playoff %', align:'right',
              render: r => fmt(r.playoff_pct, 1) + '%' },
            { key:'finals_pct', label:'Finals %', align:'right',
              render: r => fmt(r.finals_pct, 1) + '%' },
            { key:'title_pct', label:'Title %', align:'right',
              color: () => '#33aa44',
              render: r => fmt(r.title_pct, 1) + '%' },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/monte_carlo.py to populate)</div>}

      <h3 style={sectionH}>13. Playoff-weighted RoS (top hitters / pitchers for weeks 21-23)</h3>
      {advisory.playoff_ros ? (
        <div>
          <div style={subH}>
            Playoff weeks: {advisory.playoff_ros.playoff_weeks} of {advisory.playoff_ros.ros_weeks_total} remaining
            ({(advisory.playoff_ros.playoff_share * 100).toFixed(0)}% of RoS).
            Top players ranked by projected fp during playoff window.
          </div>
          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Top hitters in playoff window:</div>
          <Table rows={(advisory.playoff_ros.top_hitter_playoff_picks || []).slice(0, 15)} keyCol="batter" columns={[
            { key:'player_name', label:'Hitter' },
            { key:'primary_position', label:'Pos', align:'center' },
            { key:'team', label:'Team', align:'center' },
            { key:'expected_total_fp_remaining', label:'Season RoS', align:'right', render: r => fmt(r.expected_total_fp_remaining, 1) },
            { key:'playoff_ros', label:'Playoff RoS', align:'right',
              color: () => '#33aa44', render: r => fmt(r.playoff_ros, 1) },
            { key:'signal', label:'Signal', align:'center' },
          ]} />
          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Top pitchers in playoff window:</div>
          <Table rows={(advisory.playoff_ros.top_pitcher_playoff_picks || []).slice(0, 15)} keyCol="pitcher" columns={[
            { key:'player_name', label:'Pitcher' },
            { key:'xfp_rp3_per_start', label:'fp/start', align:'right', render: r => fmt(r.xfp_rp3_per_start, 2) },
            { key:'playoff_ros', label:'Playoff RoS', align:'right',
              color: () => '#33aa44', render: r => fmt(r.playoff_ros, 1) },
            { key:'prior_source', label:'Source', align:'center' },
            { key:'signal', label:'Signal', align:'center' },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/playoff_ros.py to populate)</div>}

      <h3 style={sectionH}>14. 2-start week alerts (upcoming SPs with 2 probables)</h3>
      {advisory.two_start_alerts ? (
        <div>
          <div style={{...subH, fontWeight:600, color:colors.text}}>Ligers SPs with 2-start weeks:</div>
          {(advisory.two_start_alerts.ligers_two_start || []).length === 0
            ? <div style={subH}>(none in next 4 weeks)</div>
            : <Table rows={advisory.two_start_alerts.ligers_two_start} keyCol="pitcher_id" columns={[
                { key:'pitcher_name', label:'Pitcher' },
                { key:'week_start', label:'Week' },
                { key:'starts', label:'Starts', align:'right' },
              ]} />}
          <div style={{...subH, fontWeight:600, color:colors.text, marginTop:8}}>Top FA streamers with 2-start weeks:</div>
          <Table rows={(advisory.two_start_alerts.fa_two_start_streamers || []).slice(0, 12)} keyCol="pitcher_id" columns={[
            { key:'pitcher_name', label:'Pitcher' },
            { key:'week_start', label:'Week' },
            { key:'starts', label:'#', align:'right' },
            { key:'fp_per_start', label:'fp/start', align:'right', render: r => fmt(r.fp_per_start, 2) },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/two_start_alerts.py to populate)</div>}

      <h3 style={sectionH}>15. Punt-detector — this week's SP-cap utilization</h3>
      {advisory.punt_detector ? (
        <div>
          <div style={subH}>
            Period {advisory.punt_detector.period} ({advisory.punt_detector.week_start} → {advisory.punt_detector.week_end}).
            vs <strong>{advisory.punt_detector.opp_name}</strong>.
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:8 }}>
            <div style={{ padding:8, border:`1px solid ${colors.border}` }}>
              <div style={{ fontSize:9, color:colors.dim, textTransform:'uppercase', letterSpacing:1 }}>Ligers SP starts this week</div>
              <div style={{ fontSize:24, fontFamily:MONO }}>{advisory.punt_detector.my_starts} / {advisory.punt_detector.cap}</div>
            </div>
            <div style={{ padding:8, border:`1px solid ${colors.border}` }}>
              <div style={{ fontSize:9, color:colors.dim, textTransform:'uppercase', letterSpacing:1 }}>{advisory.punt_detector.opp_name} SP starts</div>
              <div style={{ fontSize:24, fontFamily:MONO }}>{advisory.punt_detector.opp_starts} / {advisory.punt_detector.cap}</div>
            </div>
          </div>
          {(advisory.punt_detector.advice || []).map((a, i) => (
            <div key={i} style={{ fontSize:11, fontFamily:MONO, color:colors.accent, marginBottom:2 }}>⚠ {a}</div>
          ))}
        </div>
      ) : <div style={subH}>(run scripts/xfp/punt_detector.py to populate)</div>}

      <h3 style={sectionH}>16. Save handcuffs — per-MLB-team closer chain</h3>
      {advisory.save_handcuffs ? (
        <div>
          <div style={subH}>RPs ranked by save+hold leverage in last 21 days. FA handcuffs are rank-2 RPs still on waivers.</div>
          <Table rows={(advisory.save_handcuffs.fa_handcuffs || []).slice(0, 15)} keyCol="name" columns={[
            { key:'team', label:'MLB', align:'center' },
            { key:'rank', label:'Rk', align:'center' },
            { key:'name', label:'Pitcher' },
            { key:'saves', label:'SV', align:'right' },
            { key:'holds', label:'HLD', align:'right' },
            { key:'games', label:'G', align:'right' },
          ]} />
          <div style={{...subH, marginTop:8, fontWeight:600, color:colors.text}}>Your RPs' leverage rank:</div>
          <Table rows={(advisory.save_handcuffs.ligers_rps_leverage || [])} keyCol="name" columns={[
            { key:'name', label:'Pitcher' },
            { key:'team', label:'MLB', align:'center' },
            { key:'rank', label:'Rank', align:'center' },
            { key:'saves', label:'SV', align:'right' },
            { key:'holds', label:'HLD', align:'right' },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/save_handcuffs.py to populate)</div>}

      <h3 style={sectionH}>17. Eligibility changes (any new positions since last snapshot)</h3>
      {advisory.eligibility_changes ? (
        ((advisory.eligibility_changes.changes || []).filter(c => (c.gained_eligibilities||[]).length > 0)).length === 0
          ? <div style={subH}>No new position eligibilities since last snapshot ({advisory.eligibility_changes.as_of}).</div>
          : <Table rows={advisory.eligibility_changes.changes.filter(c => (c.gained_eligibilities||[]).length > 0).slice(0, 15)} keyCol="name" columns={[
              { key:'name', label:'Player' },
              { key:'team', label:'Team' },
              { key:'gained_eligibilities', label:'Gained',
                render: r => (r.gained_eligibilities || []).join(', ') },
            ]} />
      ) : <div style={subH}>(run scripts/xfp/eligibility_watch.py to populate)</div>}

      <h3 style={sectionH}>18. Bench tracker — points left on bench cumulatively</h3>
      {advisory.bench_tracker ? (
        <div>
          <div style={subH}>
            Cumulative FP left on bench across snapshots: <strong>{fmt(advisory.bench_tracker.cumulative_left_on_bench, 1)}</strong>.
            Run weekly after each matchup completes.
          </div>
          <Table rows={advisory.bench_tracker.snapshots || []} keyCol="week" columns={[
            { key:'week', label:'Week' },
            { key:'left_on_bench', label:'Left on bench (FP)', align:'right', render: r => fmt(r.left_on_bench, 1) },
          ]} />
        </div>
      ) : <div style={subH}>(run scripts/xfp/bench_tracker.py to populate)</div>}

      <h3 style={sectionH}>19. Pitch arsenal × hitter weakness (matchup spotter)</h3>
      <div style={subH}>Per-batter whiff% by pitch group (career, 2015-2025). Use for streaming/benching when opposing SP has a heavy mix of the right pitch.</div>
      <div style={{ marginBottom:8 }}>
        {['FB','SI','SL','CB','CH','CT','SP'].map(g => (
          <span key={g} onClick={() => setPitchFilter(g)} style={{
            display:'inline-block', padding:'4px 10px', marginRight:6, fontSize:11, fontFamily:MONO,
            cursor:'pointer', borderBottom: pitchFilter === g ? `2px solid ${colors.accent}` : 'none',
            color: pitchFilter === g ? colors.text : colors.dim,
          }}>{g}</span>
        ))}
      </div>
      <Table rows={filteredWeakness} columns={weaknessCols} keyCol="player_name" />
    </div>
  );
}

function AuditTab({ audit, colors }) {
  const [selectedOpp, setSelectedOpp] = React.useState(null);
  if (!audit || audit.error || !audit.roster_buckets) {
    return (
      <div style={{ padding:'24px 32px', color:colors.dim, fontFamily:MONO }}>
        Team audit unavailable. {audit?.error || ''}
      </div>
    );
  }
  const POS_ORDER = ['C', '1B', '2B', '3B', 'SS', 'OF', 'SP', 'RP'];
  const POS_LABEL = { C: 'Catcher', '1B': 'First Base', '2B': 'Second Base',
                       '3B': 'Third Base', SS: 'Shortstop', OF: 'Outfield',
                       SP: 'Starting Pitching', RP: 'Relief Pitching' };

  const fmt = (v, dp = 2) => v == null || isNaN(v) ? '—' : Number(v).toFixed(dp);
  const fmtPct = (v) => v == null || isNaN(v) ? '—' : `${Number(v).toFixed(0)}%`;

  const slumpBadge = (sp, bp) => {
    if (sp == null || bp == null) return null;
    if (sp < 20 && bp >= 90) {
      return <span title={`Cold streak ${sp.toFixed(0)}-th pct, ${bp.toFixed(0)}% bounce`}
                   style={{ marginLeft:6, fontSize:9, fontFamily:MONO, padding:'1px 5px',
                            border:`1px solid ${colors.pos}`, color:colors.pos, borderRadius:2 }}>BUY-LOW</span>;
    }
    if (sp < 5 && bp < 60) {
      return <span title={`Cold streak ${sp.toFixed(0)}-th pct, only ${bp.toFixed(0)}% bounce`}
                   style={{ marginLeft:6, fontSize:9, fontFamily:MONO, padding:'1px 5px',
                            border:`1px solid ${colors.warn}`, color:colors.warn, borderRadius:2 }}>FADE</span>;
    }
    if (sp >= 90 && bp != null && bp < 60) {
      return <span title={`Peak ${sp.toFixed(0)}-th pct, only ${bp.toFixed(0)}% sustain`}
                   style={{ marginLeft:6, fontSize:9, fontFamily:MONO, padding:'1px 5px',
                            border:`1px solid ${colors.warn}`, color:colors.warn, borderRadius:2 }}>SELL-HIGH</span>;
    }
    return null;
  };

  const ilBadge = (player) => {
    if (player.marcel_3yr != null && player.rank == null) {
      return <span title="No 2026 sample (likely IL); 3-yr Marcel projection shown"
                   style={{ marginLeft:6, fontSize:9, fontFamily:MONO, padding:'1px 5px',
                            border:`1px solid ${colors.dim}`, color:colors.dim, borderRadius:2 }}>IL/MARCEL</span>;
    }
    return null;
  };

  const PlayerRow = ({ p, isFA = false }) => {
    const fpLabel = (p.role === 'SP' || p.role === 'RP') ? 'fp/start' : 'fp/G';
    const sampleLabel = (p.role === 'SP') ? `${p.sample} GS`
                       : (p.role === 'RP') ? `${p.sample} G`
                       : `${p.sample} PA`;
    const fpDisplay = p.fp_per != null
      ? `${fmt(p.fp_per, 2)} ${fpLabel}`
      : (p.marcel_3yr != null ? `${fmt(p.marcel_3yr, 2)} ${fpLabel} (3yr Marcel)` : '—');
    const rankDisplay = p.rank != null ? `mdl #${p.rank}` : '—';
    return (
      <div style={{ borderBottom:`1px solid ${colors.faint}`, padding:'10px 12px',
                    display:'flex', flexDirection:'column', gap:4, background: isFA ? colors.panel : 'transparent' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
          <span style={{ fontSize:14, fontWeight:500 }}>{p.name}</span>
          {isFA && p.team && (
            <span style={{ fontSize:10, color:colors.dim, fontFamily:MONO }}>{p.team}</span>
          )}
          <span style={{ fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:1 }}>
            {p.espn_pos || p.pos || '—'}
          </span>
          {ilBadge(p)}
          {slumpBadge(p.slump_pct, p.slump_bounce)}
          {p.signal === 'add' && (
            <span style={{ fontSize:9, padding:'1px 5px', border:`1px solid ${colors.accent}`,
                           color:colors.accent, borderRadius:2, fontFamily:MONO }}>ADD</span>
          )}
          {p.signal === 'drop' && (
            <span style={{ fontSize:9, padding:'1px 5px', border:`1px solid ${colors.warn}`,
                           color:colors.warn, borderRadius:2, fontFamily:MONO }}>DROP</span>
          )}
        </div>
        <div style={{ fontSize:11, color:colors.dim, fontFamily:MONO, letterSpacing:0.5 }}>
          {rankDisplay} · {fpDisplay} · {sampleLabel}
          {p.slump_pct != null && (
            <> · slump <span style={{ color:colors.text }}>{fmtPct(p.slump_pct)}</span> /
               bnc <span style={{ color:colors.text }}>{fmtPct(p.slump_bounce)}</span>
               {p.slump_n != null && p.slump_n > 0 ? ` (n=${p.slump_n})` : ''}</>
          )}
          {p.repl_delta != null && (
            <> · ΔRepl <span style={{ color: p.repl_delta > 0 ? colors.pos : colors.warn }}>
              {p.repl_delta >= 0 ? '+' : ''}{fmt(p.repl_delta, 3)}</span></>
          )}
          {p.ros_total != null && (
            <> · RoS <span style={{ color:colors.text }}>{fmt(p.ros_total, 0)} FP</span></>
          )}
        </div>
        {p.commentary && !isFA && (
          <div style={{ fontSize:11, color:colors.text, fontFamily:SERIF, fontStyle:'italic', lineHeight:1.4 }}>
            {p.commentary}
          </div>
        )}
        {isFA && p.slump_next != null && (
          <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO }}>
            Median next-window rate: {fmt(p.slump_next, 3)}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ padding:'0 32px 32px' }}>
      <SectionHeading num="A" label={`${audit.my_team_name} — Team Audit`}
        right={`AS OF ${audit.as_of_date.toUpperCase()}`} colors={colors} />

      {/* Standings strip — opponent tiles clickable to launch compare view */}
      {audit.standings && audit.standings.length > 0 && (
        <div style={{ display:'flex', flexWrap:'wrap', gap:8, padding:'12px 0', marginBottom:16 }}>
          {audit.standings.map((s, i) => {
            const isOpp = !s.is_mine;
            const isSelected = selectedOpp === s.team_name;
            return (
              <div key={s.team_name}
                   onClick={isOpp ? () => setSelectedOpp(isSelected ? null : s.team_name) : undefined}
                   style={{
                     padding:'6px 10px', fontFamily:MONO, fontSize:11,
                     border:`1px solid ${s.is_mine ? colors.accent : (isSelected ? colors.text : colors.faint)}`,
                     color: s.is_mine ? colors.accent : (isSelected ? colors.text : colors.dim),
                     fontWeight: (s.is_mine || isSelected) ? 600 : 400,
                     borderRadius:3,
                     cursor: isOpp ? 'pointer' : 'default',
                     background: isSelected ? colors.panel : 'transparent',
                   }}
                   title={isOpp ? `Click to compare vs ${s.team_name} + see trade suggestions` : ''}>
                {i+1}. {s.team_name} ({s.wins}-{s.losses})
                {isOpp && !isSelected && <span style={{ marginLeft:6, opacity:0.5 }}>↔</span>}
                {isSelected && <span style={{ marginLeft:6 }}>✕</span>}
              </div>
            );
          })}
        </div>
      )}

      {/* Compare view (only when an opponent is selected) */}
      {selectedOpp && audit.all_team_buckets && audit.all_team_buckets[selectedOpp] && (
        <CompareView
          myName={audit.my_team_name}
          oppName={selectedOpp}
          myBuckets={audit.roster_buckets}
          oppBuckets={audit.all_team_buckets[selectedOpp]}
          trades={(audit.trades_vs && audit.trades_vs[selectedOpp]) || []}
          colors={colors}
          posOrder={POS_ORDER}
          posLabel={POS_LABEL}
        />
      )}

      {/* Position-by-position */}
      {POS_ORDER.map(pos => {
        const players = audit.roster_buckets[pos] || [];
        const fa = (audit.fa && audit.fa[pos]) || [];
        if (players.length === 0 && fa.length === 0) return null;
        return (
          <div key={pos} style={{ marginTop:32, borderTop:`1px solid ${colors.border}`, paddingTop:16 }}>
            <div style={{ display:'flex', alignItems:'baseline', gap:12, marginBottom:8 }}>
              <h2 style={{ fontSize:20, fontWeight:400, margin:0, fontFamily:SERIF, fontStyle:'italic' }}>
                {POS_LABEL[pos] || pos}
              </h2>
              <span style={{ fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:2,
                             textTransform:'uppercase' }}>
                Roster: {players.length} · FA pool: {fa.length}
              </span>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:24 }}>
              <div>
                <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:2,
                              textTransform:'uppercase', marginBottom:6, paddingBottom:4,
                              borderBottom:`1px solid ${colors.faint}` }}>
                  Your Roster
                </div>
                {players.length === 0 && (
                  <div style={{ padding:'12px 12px', color:colors.dim, fontFamily:MONO, fontSize:11 }}>
                    (none rostered at this position)
                  </div>
                )}
                {players.map((p, idx) => <PlayerRow key={idx} p={p} />)}
              </div>
              <div>
                <div style={{ fontSize:10, color:colors.dim, fontFamily:MONO, letterSpacing:2,
                              textTransform:'uppercase', marginBottom:6, paddingBottom:4,
                              borderBottom:`1px solid ${colors.faint}` }}>
                  Top Free-Agent Replacements
                </div>
                {fa.length === 0 && (
                  <div style={{ padding:'12px 12px', color:colors.dim, fontFamily:MONO, fontSize:11 }}>
                    (no qualifying FAs)
                  </div>
                )}
                {fa.map((p, idx) => <PlayerRow key={idx} p={p} isFA />)}
              </div>
            </div>
          </div>
        );
      })}

      <div style={{ marginTop:32, padding:'16px 0', borderTop:`1px solid ${colors.border}`,
                    fontSize:10, fontFamily:MONO, color:colors.dim, letterSpacing:1, textTransform:'uppercase' }}>
        ↳ BUY-LOW = ≤20-pct slump + ≥90% career bounce-back ·
        FADE = ≤5-pct + &lt;60% bounce ·
        SELL-HIGH = ≥90-pct hot streak + &lt;60% sustain ·
        IL/MARCEL = no 2026 sample, projected via 3-year weighted Marcel
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>
""")
