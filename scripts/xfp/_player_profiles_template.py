"""_player_profiles_template.py — HTML/CSS/JS for the Player Profiles dashboard.

Exposes `render_page(payload) -> str`. Imported by build_player_profiles_dashboard.py.

Phase B: HTML shell + CSS theme (mirrors matchup.html palette).
Phase C: Plotly scatters + sparklines + Pearson r computed in JS.
Phase D: Search + leaderboards + archetype tables + career-arc modal.

The HTML embeds the full data payload as `window.PROFILES_DATA`. All filtering,
correlation, and rendering happens client-side so the year-mode selector,
color-by dropdown, and search update live without page reload.
"""
from __future__ import annotations
import json


HEAD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Player Profiles — Archetype Browser</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
* { box-sizing: border-box; }
body { font-family: -apple-system, system-ui, sans-serif; background: #0d1117;
       color: #c9d1d9; max-width: 1480px; margin: 0 auto; padding: 0 1em 4em 1em;
       line-height: 1.5; }
header { border-bottom: 2px solid #30363d; padding: .8em 0; margin-bottom: 1em;
         position: sticky; top: 0; background: #0d1117; z-index: 100; }
.header-row { display: flex; justify-content: space-between; align-items: baseline;
              flex-wrap: wrap; gap: 1em; }
h1 { color: #58a6ff; margin: 0; font-size: 1.5em; }
h2 { color: #79c0ff; margin-top: 1.5em; }
h3 { color: #a5d6ff; margin: .8em 0 .4em 0; font-size: 1.1em; }
nav.topnav a { color: #58a6ff; text-decoration: none; margin-left: 1em; font-size: .85em; }
nav.topnav a:hover { text-decoration: underline; }
nav.topnav a.current { color: #c9d1d9; font-weight: 600; }

/* Search */
.search-wrap { position: relative; min-width: 260px; }
.search-wrap input { width: 100%; padding: .4em .6em; background: #161b22;
                     color: #c9d1d9; border: 1px solid #30363d; border-radius: 5px;
                     font-size: .9em; }
.search-results { position: absolute; top: 100%; left: 0; right: 0;
                   background: #161b22; border: 1px solid #30363d; border-radius: 5px;
                   max-height: 320px; overflow-y: auto; display: none; z-index: 200; }
.search-results.open { display: block; }
.search-results .item { padding: .4em .7em; cursor: pointer; font-size: .9em;
                         border-bottom: 1px solid #21262d; }
.search-results .item:hover { background: #21262d; }
.search-results .item .meta { color: #8b949e; font-size: .8em; margin-left: .5em; }
.search-results .item .role { color: #d2a8ff; font-size: .7em; text-transform: uppercase;
                                margin-right: .5em; }

/* Year mode + color-by controls */
.controls { display: flex; flex-wrap: wrap; gap: 1.2em; align-items: center;
            padding: .6em 0; font-size: .85em; }
.controls label { color: #8b949e; margin-right: .4em; }
.controls select, .controls input[type=radio] { background: #161b22; color: #c9d1d9;
                                                  border: 1px solid #30363d; border-radius: 4px;
                                                  padding: .25em .4em; font-size: .9em; }
.radio-group { display: inline-flex; gap: .8em; align-items: center; }
.radio-group label { color: #c9d1d9; cursor: pointer; }
.radio-group label.active { color: #58a6ff; font-weight: 600; }

/* Tabs */
.tabs { display: flex; gap: .3em; margin-top: .6em; }
.tabs button { background: transparent; color: #8b949e; border: 0;
               border-bottom: 2px solid transparent; padding: .5em 1em;
               font-size: .95em; font-weight: 600; cursor: pointer;
               font-family: inherit; }
.tabs button.active { color: #58a6ff; border-bottom-color: #58a6ff; }
.tabs button:hover { color: #a5d6ff; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Tables */
table { border-collapse: collapse; width: 100%; margin-bottom: 1em; font-size: .87em; }
th { background: #161b22; padding: .45em .6em; text-align: left;
      border-bottom: 2px solid #30363d; font-weight: 600; color: #8b949e;
      text-transform: uppercase; font-size: .72em; }
td { padding: .3em .6em; border-bottom: 1px solid #21262d; }
tr:hover td { background: #161b22; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.player { color: #58a6ff; cursor: pointer; font-weight: 500; }
td.player:hover { text-decoration: underline; }
.badge { background: #21262d; color: #c9d1d9; padding: 1px 6px; border-radius: 3px;
          font-size: .75em; }
.badge.plus  { background: #1a3d22; color: #79c275; }
.badge.minus { background: #4d1c1c; color: #ffa198; }
.badge.avg   { background: #21262d; color: #8b949e; }

/* Quadrants */
.quadrants { display: grid; grid-template-columns: repeat(3, 1fr); gap: .8em;
             margin: 1em 0; }
@media (max-width: 1200px) { .quadrants { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 800px)  { .quadrants { grid-template-columns: 1fr; } }
.quadrant { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
            padding: .4em; }
.quadrant-title { color: #79c0ff; font-size: .85em; padding: .3em .5em; }
.quadrant-title .r { color: #d2a8ff; font-variant-numeric: tabular-nums; }
.quadrant-title .n { color: #8b949e; font-size: .85em; }

/* Collapsibles */
details { margin: .6em 0; }
details > summary { cursor: pointer; color: #79c0ff; font-size: 1em;
                     font-weight: 600; padding: .4em 0; user-select: none; }
details > summary:hover { color: #a5d6ff; }
details > summary::marker { color: #6e7681; }
details > summary .count { color: #8b949e; font-weight: 400; font-size: .85em; margin-left: .5em; }
details > summary .desc { color: #8b949e; font-weight: 400; font-size: .85em; margin-left: .8em; font-style: italic; }

/* Glossary */
.glossary { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
            padding: 1em 1.5em; margin: 1em 0; font-size: .9em; }
.glossary table { font-size: .85em; }
.glossary .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5em; }
@media (max-width: 700px) { .glossary .grid { grid-template-columns: 1fr; } }

/* Modal */
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: none;
            align-items: center; justify-content: center; z-index: 500; }
.modal-bg.open { display: flex; }
.modal { background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
         max-width: 900px; max-height: 90vh; width: 95%; overflow-y: auto;
         padding: 1.2em 1.6em; }
.modal-close { float: right; cursor: pointer; color: #8b949e; font-size: 1.4em;
                background: none; border: 0; }
.modal-close:hover { color: #f85149; }
.modal h2 { margin-top: 0; color: #58a6ff; }
.modal .traj { font-size: .85em; color: #d2a8ff; margin: .5em 0; }
.modal .traj .arrow { color: #6e7681; }
.modal .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: .5em;
                       padding: .8em 0; }
.modal .summary-grid .stat { background: #161b22; padding: .5em; border-radius: 5px;
                              text-align: center; }
.modal .summary-grid .stat .label { color: #8b949e; font-size: .75em; text-transform: uppercase; }
.modal .summary-grid .stat .val { font-size: 1.3em; font-weight: bold; }

.meta { color: #6e7681; font-size: .8em; margin-top: 2em; text-align: center;
         border-top: 1px solid #21262d; padding-top: 1em; }
</style>
</head>
"""


BODY_HEADER = """
<header>
<div class="header-row">
  <div>
    <h1>Player Profiles</h1>
    <nav class="topnav">
      <a href="index.html">XFP</a>
      <a href="matchup.html">Matchup</a>
      <a href="live_dashboard.html">Live</a>
      <a class="current">Profiles</a>
    </nav>
  </div>
  <div class="search-wrap">
    <input id="search-input" type="text" placeholder="Search any hitter or pitcher…" autocomplete="off">
    <div id="search-results" class="search-results"></div>
  </div>
</div>
<div class="controls">
  <span class="radio-group">
    <label>Year mode:</label>
    <label><input type="radio" name="year-mode" value="single" checked> Single Year</label>
    <label><input type="radio" name="year-mode" value="all"> All Years</label>
    <label><input type="radio" name="year-mode" value="blend"> 2025+2026 Blend</label>
  </span>
  <span id="single-year-wrap">
    <label>Year:</label>
    <select id="single-year-select"></select>
  </span>
  <span>
    <label>Color by:</label>
    <select id="color-by">
      <option value="archetype">Archetype</option>
      <option value="age_tier">Age tier</option>
      <option value="fp">FP rate</option>
    </select>
  </span>
  <span id="filter-summary" class="muted"></span>
</div>
<div class="tabs">
  <button data-tab="home" class="active">Home</button>
  <button data-tab="hitters">Hitters</button>
  <button data-tab="pitchers">Pitchers</button>
</div>
</header>
"""


HOME_TAB = """
<div id="tab-home" class="tab-panel active">
  <h2>League archetype distribution by year</h2>
  <div id="home-arch-hit" style="height: 360px;"></div>
  <div id="home-arch-sp"  style="height: 360px;"></div>

  <h2>Current view leaderboards</h2>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5em;">
    <div>
      <h3>Top hitters</h3>
      <div id="lb-hitters"></div>
    </div>
    <div>
      <h3>Top starting pitchers</h3>
      <div id="lb-sps"></div>
    </div>
  </div>

  <details>
    <summary>Glossary &amp; methodology</summary>
    <div class="glossary">
      <p><b>20-80 scale.</b> 50 = league mean for that year, 10 points = 1 SD,
      capped to [20, 80]. PLUS = ≥60, AVG = 40–59, MINUS = &lt;40.</p>
      <p><b>27-cell archetype matrix.</b> Hitters: every combination of
      Contact / Power / Discipline bucket. SPs: Stuff / Movement / Control.
      SB (hitters) and Velo (SPs) are overlay ratings — shown alongside but
      excluded from the archetype label and from comp-matching distance.</p>
      <p><b>Year mode semantics.</b> <i>Single Year</i> filters to that
      season's qualifiers (PA ≥ 250 hitters / GS ≥ 20 SPs full season,
      lower in-progress). <i>All Years</i> shows every player-year as an
      independent row. <i>2025+2026 Blend</i> aggregates one row per player
      via PA-weighted (hitter) / GS-weighted (SP) mean of each rating, then
      re-buckets the archetype label from the blended ratings; sub-types
      come from the most-recent year.</p>
      <div class="grid" id="boundary-glossary"></div>
    </div>
  </details>
</div>
"""


def _quadrant(div_id, title):
    return f'  <div class="quadrant"><div class="quadrant-title" id="{div_id}-title">{title}</div><div id="{div_id}" style="height: 320px;"></div></div>\n'


HITTERS_TAB = """
<div id="tab-hitters" class="tab-panel">
  <h2>Hitter quadrants</h2>
  <div class="quadrants">
""" + ''.join([
    _quadrant('h-cp',  'Contact × Power'),
    _quadrant('h-cd',  'Contact × Discipline'),
    _quadrant('h-pd',  'Power × Discipline'),
    _quadrant('h-csb', 'Contact × SB'),
    _quadrant('h-psb', 'Power × SB'),
    _quadrant('h-dsb', 'Discipline × SB'),
]) + """  </div>

  <h2>Hitter archetype roster</h2>
  <div id="h-archetype-tables"></div>
</div>
"""


PITCHERS_TAB = """
<div id="tab-pitchers" class="tab-panel">
  <h2>Pitcher quadrants</h2>
  <div class="quadrants">
""" + ''.join([
    _quadrant('s-sm', 'Stuff × Movement'),
    _quadrant('s-sc', 'Stuff × Control'),
    _quadrant('s-mc', 'Movement × Control'),
    _quadrant('s-vs', 'Velo × Stuff'),
    _quadrant('s-vm', 'Velo × Movement'),
    _quadrant('s-vc', 'Velo × Control'),
]) + """  </div>

  <h2>Pitcher archetype roster</h2>
  <div id="s-archetype-tables"></div>
</div>
"""


MODAL_HTML = """
<div id="modal-bg" class="modal-bg">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">×</button>
    <div id="modal-content"></div>
  </div>
</div>
"""


# Major JS block — pure functions for filter / pearson / render scatters /
# render tables / leaderboards / modal / search. Compact and tightly scoped.
JS = r"""
<script>
const D = window.PROFILES_DATA;
const HITTERS = D.hitters;
const SPS     = D.sps;
const HDEFS   = D.hitter_archetype_defs;
const SDEFS   = D.sp_archetype_defs;

// Build (cell -> description) maps for archetype titles
const HARCH_DESC = {}; Object.values(HDEFS).forEach(v => HARCH_DESC[v.label] = v.description);
const SARCH_DESC = {}; Object.values(SDEFS).forEach(v => SARCH_DESC[v.label] = v.description);

// Index by stable id for modal lookups
const H_BY_ID = {}; HITTERS.forEach(r => { (H_BY_ID[r.batter] = H_BY_ID[r.batter] || []).push(r); });
const S_BY_ID = {}; SPS.forEach(r => { (S_BY_ID[r.pitcher] = S_BY_ID[r.pitcher] || []).push(r); });

// Global UI state
const state = {
  tab: 'home',
  yearMode: 'single',     // 'single' | 'all' | 'blend'
  singleYear: D.current_year,
  colorBy: 'archetype',   // 'archetype' | 'age_tier' | 'fp'
};

// ── Pearson r in JS ────────────────────────────────────────────────────────
function pearson(xs, ys) {
  const px = [], py = [];
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i], y = ys[i];
    if (Number.isFinite(x) && Number.isFinite(y)) { px.push(x); py.push(y); }
  }
  const n = px.length;
  if (n < 3) return { r: null, n: n };
  const mx = px.reduce((a,b)=>a+b,0) / n;
  const my = py.reduce((a,b)=>a+b,0) / n;
  let sxx = 0, syy = 0, sxy = 0;
  for (let i = 0; i < n; i++) {
    const dx = px[i] - mx, dy = py[i] - my;
    sxx += dx*dx; syy += dy*dy; sxy += dx*dy;
  }
  if (sxx === 0 || syy === 0) return { r: null, n: n };
  return { r: sxy / Math.sqrt(sxx * syy), n: n };
}

// ── Filtering by year mode ────────────────────────────────────────────────
function paWeightBlend(rows, blendKey, rateKey) {
  // group by id, PA-weight ratings (and rateKey), take last-year sub-types/team/age
  const byId = {};
  rows.forEach(r => { (byId[r[blendKey]] = byId[r[blendKey]] || []).push(r); });
  const out = [];
  const PA_KEY = blendKey === 'batter' ? 'pa' : 'gs';
  // Numeric domain cols to weighted-mean
  const HITTER_NUMS = ['CONTACT','POWER','DISCIPLINE','SB',
    'r_Contact','r_K','r_BABIP','r_xCON','r_Barrel','r_HardHit','r_ISO','r_HRrate','r_PullFB',
    'r_BB','r_Chase','r_ZSwing','r_SBrate','r_Sprint'];
  const SP_NUMS = ['STUFF','MOVEMENT','CONTROL','velo_rating',
    'r_K','r_SwStr','r_CSW','r_HRrate','r_Barrel','r_HardHit','r_GB','r_xCON','r_BB'];
  const NUMS = blendKey === 'batter' ? HITTER_NUMS : SP_NUMS;

  Object.entries(byId).forEach(([id, recs]) => {
    const sel = recs.filter(r => r.year === 2025 || r.year === 2026);
    if (!sel.length) return;
    const wsum = sel.reduce((a, r) => a + (r[PA_KEY] || 0), 0);
    if (!wsum) return;
    const last = sel.slice().sort((a,b) => b.year - a.year)[0];
    const blend = { ...last };  // copy display fields
    blend.year = 'blend';
    NUMS.forEach(c => {
      let s = 0;
      sel.forEach(r => { s += (r[c] || 0) * (r[PA_KEY] || 0); });
      blend[c] = Math.round(s / wsum);
    });
    blend[PA_KEY] = wsum;
    // Re-bucket archetype from blended ratings
    if (blendKey === 'batter') {
      blend.archetype = lookupHitterArch(blend.CONTACT, blend.POWER, blend.DISCIPLINE);
    } else {
      blend.archetype = lookupSpArch(blend.STUFF, blend.MOVEMENT, blend.CONTROL);
    }
    // Re-rank within blend population added below
    blend.rank_in_year = null;
    blend[rateKey] = sel.reduce((a, r) => a + (r[rateKey] || 0) * (r[PA_KEY] || 0), 0) / wsum;
    out.push(blend);
  });
  // Rank
  out.sort((a,b) => b[rateKey] - a[rateKey]);
  out.forEach((r, i) => r.rank_in_year = i + 1);
  return out;
}

function bucket(v) { return v >= 60 ? 'PLUS' : (v >= 40 ? 'AVG' : 'MINUS'); }

function lookupHitterArch(c, p, d) {
  const cell = bucket(c) + '/' + bucket(p) + '/' + bucket(d);
  return (HDEFS[cell] || {label:'UNKNOWN'}).label;
}
function lookupSpArch(s, m, c) {
  const cell = bucket(s) + '/' + bucket(m) + '/' + bucket(c);
  return (SDEFS[cell] || {label:'UNKNOWN'}).label;
}

function filterRows(rows, role) {
  // role: 'hitter' | 'sp'
  if (state.yearMode === 'single') {
    return rows.filter(r => r.year === state.singleYear);
  }
  if (state.yearMode === 'all') return rows.slice();
  // blend
  return paWeightBlend(rows, role === 'hitter' ? 'batter' : 'pitcher',
                       role === 'hitter' ? 'fp_per_pa' : 'fp_per_start');
}

// ── Color mapping ─────────────────────────────────────────────────────────
const ARCH_PALETTE = ['#58a6ff','#3fb950','#d29922','#f85149','#d2a8ff',
  '#f0883e','#79c0ff','#79c275','#ff7b72','#a5d6ff','#ffa657','#56d364',
  '#ffa198','#bc8cff','#7ee787','#ffc680','#79c0ff','#d2a8ff','#3fb950',
  '#f85149','#58a6ff','#8b949e','#6e7681','#484f58','#30363d','#21262d','#161b22'];

function colorMap(rows, key) {
  if (key === 'archetype') {
    const labels = [...new Set(rows.map(r => r.archetype))];
    labels.sort();
    const map = {};
    labels.forEach((l, i) => map[l] = ARCH_PALETTE[i % ARCH_PALETTE.length]);
    return { type: 'cat', map, key: 'archetype' };
  }
  if (key === 'age_tier') {
    return { type: 'cat',
             map: { 'PRE_PEAK': '#79c275', 'PEAK': '#58a6ff', 'POST_PEAK': '#f0883e' },
             key: 'age_tier' };
  }
  // fp continuous
  return { type: 'fp' };
}

// ── Scatter rendering ─────────────────────────────────────────────────────
function ratingTitleR(rRes) {
  if (rRes.r == null) return ` <span class="r">r = —</span> <span class="n">(n=${rRes.n})</span>`;
  return ` <span class="r">r = ${rRes.r.toFixed(3)}</span> <span class="n">(n=${rRes.n})</span>`;
}

function olsLine(xs, ys) {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a,b)=>a+b,0)/n;
  const my = ys.reduce((a,b)=>a+b,0)/n;
  let sxx = 0, sxy = 0;
  for (let i = 0; i < n; i++) { sxx += (xs[i]-mx)**2; sxy += (xs[i]-mx)*(ys[i]-my); }
  if (sxx === 0) return null;
  const slope = sxy / sxx;
  const icpt = my - slope * mx;
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  return { x: [xmin, xmax], y: [xmin*slope + icpt, xmax*slope + icpt] };
}

function renderScatter(divId, titleBase, rows, xKey, yKey, idKey, role) {
  const xs = rows.map(r => r[xKey]).filter(Number.isFinite);
  const ys = rows.map(r => r[yKey]).filter(Number.isFinite);
  // align
  const px = [], py = [], meta = [];
  for (let i = 0; i < rows.length; i++) {
    const x = rows[i][xKey], y = rows[i][yKey];
    if (Number.isFinite(x) && Number.isFinite(y)) { px.push(x); py.push(y); meta.push(rows[i]); }
  }
  const rRes = pearson(px, py);
  document.getElementById(divId + '-title').innerHTML = titleBase + ratingTitleR(rRes);

  const cmap = colorMap(rows, state.colorBy);
  let traces;
  if (cmap.type === 'cat') {
    const byCat = {};
    for (let i = 0; i < meta.length; i++) {
      const cat = meta[i][cmap.key] || 'UNK';
      (byCat[cat] = byCat[cat] || { x:[], y:[], txt:[], ids:[], idx:[] });
      byCat[cat].x.push(px[i]); byCat[cat].y.push(py[i]);
      byCat[cat].txt.push(hoverText(meta[i], role));
      byCat[cat].ids.push(meta[i][idKey]);
    }
    traces = Object.entries(byCat).map(([cat, g]) => ({
      x: g.x, y: g.y, name: cat,
      mode: 'markers', type: 'scattergl',
      text: g.txt, hovertemplate: '%{text}<extra></extra>',
      customdata: g.ids,
      marker: { color: cmap.map[cat] || '#8b949e', size: 7, opacity: 0.85 },
    }));
  } else {
    // fp continuous
    const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
    const cs = meta.map(r => r[fpKey]);
    traces = [{
      x: px, y: py, mode: 'markers', type: 'scattergl',
      text: meta.map(r => hoverText(r, role)),
      hovertemplate: '%{text}<extra></extra>',
      customdata: meta.map(r => r[idKey]),
      marker: { color: cs, colorscale: 'Viridis', size: 8, opacity: 0.85,
                colorbar: { title: fpKey } },
    }];
  }
  // OLS overlay
  const ols = olsLine(px, py);
  if (ols) traces.push({
    x: ols.x, y: ols.y, mode: 'lines', type: 'scatter',
    line: { color: '#d2a8ff', width: 2, dash: 'dash' }, hoverinfo: 'skip',
    showlegend: false, name: 'OLS',
  });

  Plotly.react(divId, traces, {
    paper_bgcolor: '#161b22', plot_bgcolor: '#0d1117',
    font: { color: '#c9d1d9', size: 11 },
    margin: { l: 38, r: 10, t: 8, b: 32 },
    xaxis: { title: xKey, gridcolor: '#21262d', zerolinecolor: '#30363d' },
    yaxis: { title: yKey, gridcolor: '#21262d', zerolinecolor: '#30363d' },
    showlegend: cmap.type === 'cat',
    legend: { font: { size: 9 }, bgcolor: 'rgba(0,0,0,0)' },
  }, { displayModeBar: false, responsive: true });

  // Click → modal
  const div = document.getElementById(divId);
  div.removeAllListeners && div.removeAllListeners('plotly_click');
  div.on('plotly_click', e => {
    const pt = e.points[0];
    const id = pt.customdata;
    if (id != null) openModal(role, id);
  });
}

function hoverText(r, role) {
  if (role === 'hitter') {
    return `<b>${r.player_name}</b> ${r.year} (${r.team})<br>`
         + `C=${r.CONTACT} P=${r.POWER} D=${r.DISCIPLINE} SB=${r.SB}<br>`
         + `${r.archetype} · ${r.age_tier || ''} · ${r.boundary_tier}<br>`
         + `fp/pa = ${(r.fp_per_pa||0).toFixed(3)}`;
  }
  return `<b>${r.player_name}</b> ${r.year}<br>`
       + `S=${r.STUFF} M=${r.MOVEMENT} C=${r.CONTROL} velo=${r.velo_rating}<br>`
       + `${r.archetype} · ${r.age_tier || ''} · ${r.boundary_tier}<br>`
       + `fp/start = ${(r.fp_per_start||0).toFixed(2)}`;
}

// ── Archetype roster tables ───────────────────────────────────────────────
function renderArchetypeTables(rows, role, targetId) {
  const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
  const archDesc = role === 'hitter' ? HARCH_DESC : SARCH_DESC;
  const byArch = {};
  rows.forEach(r => { (byArch[r.archetype] = byArch[r.archetype] || []).push(r); });
  const arches = Object.entries(byArch).map(([a, rs]) => {
    const mean = rs.reduce((s,r) => s + (r[fpKey]||0), 0) / rs.length;
    return { arch: a, rows: rs, mean };
  }).sort((a,b) => b.mean - a.mean);

  let html = '';
  arches.forEach(({arch, rows: rs, mean}) => {
    rs.sort((a,b) => (b[fpKey] || 0) - (a[fpKey] || 0));
    const desc = archDesc[arch] || '';
    html += `<details><summary>${arch}<span class="count">n=${rs.length}, mean ${fpKey}=${mean.toFixed(role==='hitter'?3:2)}</span><span class="desc">${desc}</span></summary><table><thead>`;
    if (role === 'hitter') {
      html += '<tr><th>#</th><th>Player</th><th>Team</th><th>C</th><th>P</th><th>D</th><th>SB</th><th>SB tier</th><th>Age</th><th>Bnd</th><th>FP/PA</th><th>Rank</th></tr></thead><tbody>';
      rs.forEach((r, i) => {
        html += `<tr><td>${i+1}</td>`
              + `<td class="player" data-role="hitter" data-id="${r.batter}">${r.player_name}</td>`
              + `<td>${r.team||''}</td>`
              + `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
              + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
              + `<td>${r.sb_tier||''}</td><td>${r.age_tier||''}</td>`
              + `<td>${r.boundary_tier||''}</td>`
              + `<td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`
              + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
      });
    } else {
      html += '<tr><th>#</th><th>Pitcher</th><th>S</th><th>M</th><th>C</th><th>Velo</th><th>Velo tier</th><th>Age</th><th>Bnd</th><th>FP/start</th><th>Rank</th></tr></thead><tbody>';
      rs.forEach((r, i) => {
        html += `<tr><td>${i+1}</td>`
              + `<td class="player" data-role="sp" data-id="${r.pitcher}">${r.player_name}</td>`
              + `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
              + `<td class="num">${r.CONTROL}</td><td class="num">${r.velo_rating??''}</td>`
              + `<td>${r.velo_tier||''}</td><td>${r.age_tier||''}</td>`
              + `<td>${r.boundary_tier||''}</td>`
              + `<td class="num">${(r.fp_per_start||0).toFixed(2)}</td>`
              + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
      });
    }
    html += '</tbody></table></details>';
  });
  document.getElementById(targetId).innerHTML = html;
  // Wire clicks
  document.querySelectorAll(`#${targetId} td.player`).forEach(td => {
    td.addEventListener('click', () => openModal(td.dataset.role, parseInt(td.dataset.id)));
  });
}

// ── Leaderboards ──────────────────────────────────────────────────────────
function renderLeaderboard(rows, role, targetId) {
  const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
  const top = rows.slice().sort((a,b) => (b[fpKey]||0) - (a[fpKey]||0)).slice(0, 15);
  let html = '<table><thead><tr><th>#</th><th>Player</th>';
  if (role === 'hitter') html += '<th>C</th><th>P</th><th>D</th><th>SB</th><th>Arch</th><th>FP/PA</th>';
  else                    html += '<th>S</th><th>M</th><th>C</th><th>Arch</th><th>FP/start</th>';
  html += '</tr></thead><tbody>';
  top.forEach((r, i) => {
    html += `<tr><td>${i+1}</td>`
          + `<td class="player" data-role="${role}" data-id="${role==='hitter'?r.batter:r.pitcher}">${r.player_name}</td>`;
    if (role === 'hitter') {
      html += `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
            + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
            + `<td>${r.archetype}</td><td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`;
    } else {
      html += `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
            + `<td class="num">${r.CONTROL}</td>`
            + `<td>${r.archetype}</td><td class="num">${(r.fp_per_start||0).toFixed(2)}</td>`;
    }
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById(targetId).innerHTML = html;
  document.querySelectorAll(`#${targetId} td.player`).forEach(td => {
    td.addEventListener('click', () => openModal(td.dataset.role, parseInt(td.dataset.id)));
  });
}

// ── Home archetype-distribution stacked bars (all years, fixed) ──────────
function renderHomeArchDist() {
  // hitters
  renderStackedArchDist('home-arch-hit', HITTERS, 'archetype', 'Hitter archetypes per year');
  renderStackedArchDist('home-arch-sp',  SPS,     'archetype', 'SP archetypes per year');
}

function renderStackedArchDist(divId, rows, key, title) {
  // group by (year, archetype) count
  const byYrArch = {};
  rows.forEach(r => {
    const k = `${r.year}|${r[key]}`;
    byYrArch[k] = (byYrArch[k] || 0) + 1;
  });
  const years = [...new Set(rows.map(r => r.year))].sort();
  const arches = [...new Set(rows.map(r => r[key]))].sort();
  const traces = arches.map((a, i) => ({
    name: a,
    x: years,
    y: years.map(y => byYrArch[`${y}|${a}`] || 0),
    type: 'bar',
    marker: { color: ARCH_PALETTE[i % ARCH_PALETTE.length] },
  }));
  Plotly.react(divId, traces, {
    barmode: 'stack',
    paper_bgcolor: '#161b22', plot_bgcolor: '#0d1117',
    font: { color: '#c9d1d9', size: 11 },
    title: { text: title, font: { color: '#79c0ff', size: 13 } },
    margin: { l: 40, r: 10, t: 36, b: 36 },
    xaxis: { gridcolor: '#21262d', tickmode: 'linear', dtick: 1 },
    yaxis: { gridcolor: '#21262d' },
    legend: { font: { size: 9 }, orientation: 'h', y: -0.2 },
  }, { displayModeBar: false, responsive: true });
}

// ── Boundary glossary ─────────────────────────────────────────────────────
function renderBoundaryGlossary() {
  const sides = [
    { title: 'Hitters', data: D.hitter_boundary },
    { title: 'Starting pitchers', data: D.sp_boundary },
  ];
  let html = '';
  sides.forEach(s => {
    html += `<div><h3>${s.title} boundary retention</h3>`;
    html += '<table><thead><tr><th>Tier</th><th>n transitions</th><th>YoY archetype retention</th></tr></thead><tbody>';
    ['EDGE','NEAR_EDGE','SOLID'].forEach(t => {
      const v = s.data[t];
      if (!v) return;
      html += `<tr><td>${t}</td><td class="num">${v.n_transitions}</td><td class="num">${v.retention_pct}%</td></tr>`;
    });
    html += '</tbody></table></div>';
  });
  document.getElementById('boundary-glossary').innerHTML = html;
}

// ── Modal ────────────────────────────────────────────────────────────────
function openModal(role, id) {
  const records = (role === 'hitter' ? H_BY_ID[id] : S_BY_ID[id]) || [];
  if (!records.length) return;
  const sorted = records.slice().sort((a,b) => a.year - b.year);
  const last = sorted[sorted.length - 1];
  let html = `<h2>${last.player_name}</h2>`;
  if (role === 'hitter') {
    html += `<div class="muted">Latest: ${last.team || '—'}, age ${last.age ?? '?'} (${last.age_tier})</div>`;
  } else {
    html += `<div class="muted">Latest: age ${last.age ?? '?'} (${last.age_tier})</div>`;
  }
  // Trajectory
  html += '<div class="traj">' + sorted.map(r => `<span>${r.year}: <b>${r.archetype}</b></span>`).join(' <span class="arrow">→</span> ') + '</div>';
  // Year table
  html += '<table><thead><tr><th>Year</th><th>Age</th>';
  if (role === 'hitter') html += '<th>C</th><th>P</th><th>D</th><th>SB</th><th>Archetype</th><th>Subtypes</th><th>Bnd</th><th>FP/PA</th><th>Rank</th>';
  else                    html += '<th>S</th><th>M</th><th>C</th><th>Velo</th><th>Archetype</th><th>Subtypes</th><th>Bnd</th><th>FP/start</th><th>Rank</th>';
  html += '</tr></thead><tbody>';
  sorted.forEach(r => {
    if (role === 'hitter') {
      html += `<tr><td>${r.year}</td><td>${r.age ?? ''}</td>`
            + `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
            + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
            + `<td>${r.archetype}</td>`
            + `<td><span class="muted">${[r.contact_subtype, r.power_subtype, r.discipline_subtype, r.sb_tier].filter(Boolean).join(' / ')}</span></td>`
            + `<td>${r.boundary_tier||''}</td>`
            + `<td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`
            + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
    } else {
      html += `<tr><td>${r.year}</td><td>${r.age ?? ''}</td>`
            + `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
            + `<td class="num">${r.CONTROL}</td><td class="num">${r.velo_rating ?? ''}</td>`
            + `<td>${r.archetype}</td>`
            + `<td><span class="muted">${[r.stuff_subtype, r.velo_tier, r.pitch_archetype].filter(Boolean).join(' / ')}</span></td>`
            + `<td>${r.boundary_tier||''}</td>`
            + `<td class="num">${(r.fp_per_start||0).toFixed(2)}</td>`
            + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
    }
  });
  html += '</tbody></table>';
  html += '<div id="modal-spark" style="height: 280px; margin-top: .8em;"></div>';
  document.getElementById('modal-content').innerHTML = html;
  document.getElementById('modal-bg').classList.add('open');
  renderSparkline(sorted, role);
}

function closeModal() {
  document.getElementById('modal-bg').classList.remove('open');
}

function renderSparkline(sorted, role) {
  const xs = sorted.map(r => r.year);
  const keys = role === 'hitter'
    ? [['CONTACT','#58a6ff'], ['POWER','#f0883e'], ['DISCIPLINE','#d2a8ff'], ['SB','#3fb950']]
    : [['STUFF','#58a6ff'], ['MOVEMENT','#f0883e'], ['CONTROL','#d2a8ff'], ['velo_rating','#3fb950']];
  const traces = keys.map(([k, color]) => ({
    x: xs, y: sorted.map(r => r[k]), mode: 'lines+markers', name: k,
    line: { color }, marker: { size: 7 },
  }));
  // Bucket boundary lines
  const shapes = [
    { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 60, y1: 60, line: { color: '#3fb950', dash: 'dot', width: 1 } },
    { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 40, y1: 40, line: { color: '#f85149', dash: 'dot', width: 1 } },
  ];
  Plotly.react('modal-spark', traces, {
    paper_bgcolor: '#0d1117', plot_bgcolor: '#161b22',
    font: { color: '#c9d1d9', size: 11 },
    margin: { l: 40, r: 10, t: 10, b: 30 },
    xaxis: { gridcolor: '#21262d', tickmode: 'linear', dtick: 1 },
    yaxis: { gridcolor: '#21262d', range: [20, 80] },
    shapes,
    legend: { orientation: 'h', y: -0.15 },
  }, { displayModeBar: false, responsive: true });
}

// ── Search ──────────────────────────────────────────────────────────────
function buildSearchIndex() {
  // De-dup per id, attach a display label with most-recent team
  const idx = [];
  Object.entries(H_BY_ID).forEach(([id, recs]) => {
    const last = recs.slice().sort((a,b) => b.year - a.year)[0];
    idx.push({ id: parseInt(id), role: 'hitter', name: last.player_name,
               label: `${last.player_name}`, meta: `Hitter · ${last.team || '—'} · last ${last.year}` });
  });
  Object.entries(S_BY_ID).forEach(([id, recs]) => {
    const last = recs.slice().sort((a,b) => b.year - a.year)[0];
    idx.push({ id: parseInt(id), role: 'sp', name: last.player_name,
               label: `${last.player_name}`, meta: `SP · last ${last.year}` });
  });
  return idx;
}
const SEARCH_INDEX = buildSearchIndex();

function runSearch(q) {
  const box = document.getElementById('search-results');
  if (!q || q.length < 2) { box.classList.remove('open'); box.innerHTML = ''; return; }
  const ql = q.toLowerCase();
  const hits = SEARCH_INDEX.filter(o => o.name.toLowerCase().includes(ql)).slice(0, 20);
  if (!hits.length) { box.innerHTML = '<div class="item muted">no match</div>'; box.classList.add('open'); return; }
  box.innerHTML = hits.map(o =>
    `<div class="item" data-role="${o.role}" data-id="${o.id}">`
    + `<span class="role">${o.role}</span>${o.label}<span class="meta">${o.meta}</span></div>`
  ).join('');
  box.classList.add('open');
  box.querySelectorAll('.item').forEach(d => {
    d.addEventListener('click', () => {
      openModal(d.dataset.role, parseInt(d.dataset.id));
      box.classList.remove('open');
      document.getElementById('search-input').value = '';
    });
  });
}

// ── Master render: re-runs everything dependent on state ─────────────────
function renderAll() {
  const hitterRows = filterRows(HITTERS, 'hitter');
  const spRows     = filterRows(SPS,     'sp');

  // Filter summary
  const ym = state.yearMode === 'single' ? `Single ${state.singleYear}` :
             state.yearMode === 'all'    ? 'All years' : '2025+2026 Blend';
  document.getElementById('filter-summary').textContent =
    `${ym} · ${hitterRows.length} hitters · ${spRows.length} SPs`;

  // Home
  renderLeaderboard(hitterRows, 'hitter', 'lb-hitters');
  renderLeaderboard(spRows, 'sp', 'lb-sps');

  // Hitters
  renderScatter('h-cp',  'Contact × Power',      hitterRows, 'CONTACT', 'POWER',      'batter', 'hitter');
  renderScatter('h-cd',  'Contact × Discipline', hitterRows, 'CONTACT', 'DISCIPLINE', 'batter', 'hitter');
  renderScatter('h-pd',  'Power × Discipline',   hitterRows, 'POWER',   'DISCIPLINE', 'batter', 'hitter');
  renderScatter('h-csb', 'Contact × SB',         hitterRows, 'CONTACT', 'SB',         'batter', 'hitter');
  renderScatter('h-psb', 'Power × SB',           hitterRows, 'POWER',   'SB',         'batter', 'hitter');
  renderScatter('h-dsb', 'Discipline × SB',      hitterRows, 'DISCIPLINE', 'SB',      'batter', 'hitter');
  renderArchetypeTables(hitterRows, 'hitter', 'h-archetype-tables');

  // SPs
  renderScatter('s-sm',  'Stuff × Movement',     spRows, 'STUFF',    'MOVEMENT',    'pitcher', 'sp');
  renderScatter('s-sc',  'Stuff × Control',      spRows, 'STUFF',    'CONTROL',     'pitcher', 'sp');
  renderScatter('s-mc',  'Movement × Control',   spRows, 'MOVEMENT', 'CONTROL',     'pitcher', 'sp');
  renderScatter('s-vs',  'Velo × Stuff',         spRows, 'velo_rating', 'STUFF',    'pitcher', 'sp');
  renderScatter('s-vm',  'Velo × Movement',      spRows, 'velo_rating', 'MOVEMENT', 'pitcher', 'sp');
  renderScatter('s-vc',  'Velo × Control',       spRows, 'velo_rating', 'CONTROL',  'pitcher', 'sp');
  renderArchetypeTables(spRows, 'sp', 's-archetype-tables');
}

// ── Init ─────────────────────────────────────────────────────────────────
function init() {
  // Populate year dropdown
  const sel = document.getElementById('single-year-select');
  D.years.forEach(y => {
    const o = document.createElement('option'); o.value = y; o.textContent = y;
    if (y === D.current_year) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener('change', () => { state.singleYear = parseInt(sel.value); renderAll(); });

  // Year-mode radios
  document.querySelectorAll('input[name="year-mode"]').forEach(rb => {
    rb.addEventListener('change', () => {
      state.yearMode = rb.value;
      document.getElementById('single-year-wrap').style.display =
        state.yearMode === 'single' ? '' : 'none';
      renderAll();
    });
  });

  // Color-by
  document.getElementById('color-by').addEventListener('change', e => {
    state.colorBy = e.target.value;
    renderAll();
  });

  // Tabs
  document.querySelectorAll('.tabs button').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      document.getElementById('tab-' + b.dataset.tab).classList.add('active');
      state.tab = b.dataset.tab;
      // Plotly needs a relayout after becoming visible from display:none
      window.dispatchEvent(new Event('resize'));
    });
  });

  // Search
  const si = document.getElementById('search-input');
  si.addEventListener('input', () => runSearch(si.value.trim()));
  si.addEventListener('blur', () => setTimeout(() => {
    document.getElementById('search-results').classList.remove('open');
  }, 200));

  // Modal background click
  document.getElementById('modal-bg').addEventListener('click', closeModal);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  // First render
  renderBoundaryGlossary();
  renderHomeArchDist();
  renderAll();
}

document.addEventListener('DOMContentLoaded', init);
</script>
"""


def render_page(payload: dict) -> str:
    """Assemble the complete HTML document."""
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    meta = (f'<div class="meta">Generated {payload["last_refresh"]} · '
            f'{len(payload["hitters"])} hitter-years · '
            f'{len(payload["sps"])} SP-years · '
            f'years {payload["years"][0]}–{payload["years"][-1]}</div>')
    return (HEAD
            + '<body>\n'
            + BODY_HEADER
            + HOME_TAB
            + HITTERS_TAB
            + PITCHERS_TAB
            + MODAL_HTML
            + meta
            + f'<script>window.PROFILES_DATA = {payload_json};</script>\n'
            + JS
            + '</body>\n</html>\n')
