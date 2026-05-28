"""_player_profiles_template.py — HTML/CSS/JS for the Player Profiles dashboard.

Exposes `render_page(payload) -> str`. Imported by build_player_profiles_dashboard.py.

UI mirrors the main XFP dashboard's "editorial" palette (warm beige/cream dark
mode, IBM Plex Mono for numerics, Source Serif 4 for headings). Each side
(Hitters / Pitchers) has ONE custom quadrant where the user picks X and Y axes
from a dropdown; 50/50 reference lines mark the league-average crosshair so the
top-right quadrant reads as "good at both."

Archetype legend is grouped + color-coded by primary trait category
(ELITE / POWER / CONTACT / DISCIPLINE / AVERAGE / BELOW for hitters;
ELITE / STUFF / MOVEMENT / CONTROL / AVERAGE / BELOW for SPs).
"""
from __future__ import annotations
import json


HEAD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Player Profiles — Archetype Browser</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:wght@400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
:root {
  --bg: #1a1815;
  --panel: #211e1a;
  --stripe: #1d1b17;
  --border: #34302a;
  --text: #f5f1ea;
  --dim: #8d8579;
  --faint: #3a352e;
  --accent: #d97757;
  --pos: #7fb069;
  --neg: #c1666b;
  --warn: #d4a945;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: 'Source Serif 4', 'Iowan Old Style', Georgia, serif;
       background: var(--bg); color: var(--text); line-height: 1.5; }
.wrap { max-width: 1480px; margin: 0 auto; padding: 0 1.2em 4em 1.2em; }
.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; }

header { border-bottom: 1px solid var(--border); padding: .9em 0;
         position: sticky; top: 0; background: var(--bg); z-index: 100;
         margin-bottom: 1em; }
.header-row { display: flex; justify-content: space-between; align-items: baseline;
              flex-wrap: wrap; gap: 1.2em; }
h1 { color: var(--accent); margin: 0; font-size: 1.6em; font-weight: 700;
     letter-spacing: .01em; }
h2 { color: var(--text); margin-top: 1.4em; font-size: 1.25em; font-weight: 600;
     border-bottom: 1px solid var(--border); padding-bottom: .35em;
     letter-spacing: .01em; }
h3 { color: var(--text); margin: 1em 0 .4em 0; font-size: 1.05em; font-weight: 600; }

nav.topnav { display: flex; align-items: center; gap: 0; font-family: 'IBM Plex Mono', monospace;
             font-size: .72em; text-transform: uppercase; letter-spacing: .15em; }
nav.topnav a { color: var(--dim); text-decoration: none; padding: .35em .9em;
               border: 1px solid var(--border); border-right: 0; }
nav.topnav a:first-child { border-radius: 3px 0 0 3px; }
nav.topnav a:last-child  { border-radius: 0 3px 3px 0; border-right: 1px solid var(--border); }
nav.topnav a:hover { color: var(--text); background: var(--panel); }
nav.topnav a.current { color: var(--accent); background: var(--panel); border-color: var(--accent); }

.search-wrap { position: relative; min-width: 280px; }
.search-wrap input { width: 100%; padding: .5em .7em; background: var(--panel);
                     color: var(--text); border: 1px solid var(--border); border-radius: 3px;
                     font-family: 'IBM Plex Mono', monospace; font-size: .85em; }
.search-wrap input::placeholder { color: var(--dim); }
.search-wrap input:focus { outline: 0; border-color: var(--accent); }
.search-results { position: absolute; top: 100%; left: 0; right: 0;
                   background: var(--panel); border: 1px solid var(--border); border-radius: 3px;
                   max-height: 340px; overflow-y: auto; display: none; z-index: 200;
                   margin-top: 4px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
.search-results.open { display: block; }
.search-results .item { padding: .5em .7em; cursor: pointer; font-size: .85em;
                         border-bottom: 1px solid var(--faint);
                         font-family: 'IBM Plex Mono', monospace; }
.search-results .item:hover { background: var(--stripe); }
.search-results .item:last-child { border-bottom: 0; }
.search-results .item .meta { color: var(--dim); font-size: .82em; margin-left: .6em; }
.search-results .item .role { color: var(--accent); font-size: .72em; text-transform: uppercase;
                                margin-right: .6em; letter-spacing: .1em; }

.controls { display: flex; flex-wrap: wrap; gap: 1.5em; align-items: center;
            padding: .7em 0 .2em 0; font-family: 'IBM Plex Mono', monospace; font-size: .8em; }
.controls label { color: var(--dim); margin-right: .4em; text-transform: uppercase;
                  letter-spacing: .1em; font-size: .92em; }
.controls select { background: var(--panel); color: var(--text);
                    border: 1px solid var(--border); border-radius: 3px;
                    padding: .3em .5em; font-size: .9em;
                    font-family: 'IBM Plex Mono', monospace; }
.controls select:focus { outline: 0; border-color: var(--accent); }
.radio-group { display: inline-flex; gap: 1em; align-items: center; }
.radio-group label { color: var(--text); cursor: pointer; text-transform: none;
                     font-family: 'IBM Plex Mono', monospace; }
.radio-group input[type=radio] { accent-color: var(--accent); margin-right: .3em; }
.filter-summary { color: var(--dim); font-style: italic; }

.tabs { display: flex; gap: 0; margin-top: .8em; font-family: 'IBM Plex Mono', monospace; }
.tabs button { background: transparent; color: var(--dim); border: 0;
               border-bottom: 2px solid transparent; padding: .55em 1.1em;
               font-size: .82em; font-weight: 500; cursor: pointer;
               font-family: 'IBM Plex Mono', monospace;
               text-transform: uppercase; letter-spacing: .15em; }
.tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }
.tabs button:hover { color: var(--text); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

table { border-collapse: collapse; width: 100%; margin-bottom: 1.2em;
        font-family: 'IBM Plex Mono', monospace; font-size: .82em; }
th { background: var(--panel); padding: .55em .7em;
      border-bottom: 1px solid var(--border); border-top: 1px solid var(--border);
      font-weight: 600; color: var(--dim);
      text-transform: uppercase; font-size: .72em; letter-spacing: .12em;
      text-align: left; font-family: 'IBM Plex Mono', monospace; }
th.num { text-align: right; }
td { padding: .42em .7em; border-bottom: 1px solid var(--faint);
      font-variant-numeric: tabular-nums; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:nth-child(even) td { background: var(--stripe); }
tbody tr:hover td { background: var(--panel); }
td.player { color: var(--accent); cursor: pointer; font-weight: 500;
             font-family: 'Source Serif 4', Georgia, serif; }
td.player:hover { text-decoration: underline; }

.badge { display: inline-block; padding: 1px 7px; border-radius: 2px;
          font-size: .72em; font-family: 'IBM Plex Mono', monospace;
          background: var(--faint); color: var(--text); letter-spacing: .08em; }
.badge.plus { background: rgba(127,176,105,0.18); color: var(--pos); }
.badge.minus { background: rgba(193,102,107,0.18); color: var(--neg); }
.badge.avg { background: var(--faint); color: var(--dim); }
.badge.partial { background: rgba(212,169,69,0.18); color: var(--warn);
                 font-size: .65em; vertical-align: middle; margin-left: .5em;
                 letter-spacing: .08em; padding: 0 5px; }

/* Quadrant — one big customizable scatter per side */
.quad-controls { display: flex; gap: 1em; align-items: center; margin-bottom: .5em;
                  font-family: 'IBM Plex Mono', monospace; font-size: .82em; }
.quad-controls label { color: var(--dim); text-transform: uppercase;
                        letter-spacing: .1em; font-size: .9em; }
.quad-controls select { background: var(--panel); color: var(--text);
                         border: 1px solid var(--border); border-radius: 3px;
                         padding: .25em .5em; font-family: inherit; }
.quad-controls .r-display { margin-left: auto; color: var(--accent);
                             font-weight: 600; font-size: .9em; }
.quadrant-host { background: var(--panel); border: 1px solid var(--border);
                  border-radius: 4px; padding: .8em; }

details { margin: .6em 0; }
details > summary { cursor: pointer; color: var(--text); font-size: .92em;
                     font-weight: 600; padding: .55em 0; user-select: none;
                     font-family: 'IBM Plex Mono', monospace;
                     text-transform: uppercase; letter-spacing: .12em;
                     border-bottom: 1px solid var(--faint); }
details > summary:hover { color: var(--accent); }
details > summary::marker { color: var(--dim); }
details > summary .count { color: var(--dim); font-weight: 400; font-size: .85em;
                            margin-left: .8em; text-transform: none; letter-spacing: 0; }
details > summary .desc { color: var(--dim); font-weight: 400; font-size: .82em;
                          margin-left: 1em; font-style: italic; text-transform: none;
                          font-family: 'Source Serif 4', Georgia, serif; letter-spacing: 0; }

.glossary { background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
            padding: 1em 1.4em; margin: 1em 0; font-size: .92em; }
.glossary p { color: var(--text); }
.glossary .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5em; margin-top: .7em; }
@media (max-width: 700px) { .glossary .grid { grid-template-columns: 1fr; } }

.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.75); display: none;
            align-items: center; justify-content: center; z-index: 500; }
.modal-bg.open { display: flex; }
.modal { background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
         max-width: 980px; max-height: 92vh; width: 96%; overflow-y: auto;
         padding: 1.4em 1.8em; }
.modal-close { float: right; cursor: pointer; color: var(--dim); font-size: 1.4em;
                background: none; border: 0; padding: 0 .3em; }
.modal-close:hover { color: var(--neg); }
.modal h2 { margin-top: 0; color: var(--accent); border-bottom: 1px solid var(--border); }
.modal .traj { font-size: .82em; color: var(--accent); margin: .6em 0;
                font-family: 'IBM Plex Mono', monospace; letter-spacing: .04em; }
.modal .traj .arrow { color: var(--dim); margin: 0 .3em; }
.modal .latest-line { color: var(--dim); margin-top: .3em;
                       font-family: 'IBM Plex Mono', monospace; font-size: .82em; }

.meta { color: var(--dim); font-size: .78em; margin-top: 2em; text-align: center;
         border-top: 1px solid var(--faint); padding-top: 1em;
         font-family: 'IBM Plex Mono', monospace; letter-spacing: .08em; }
</style>
</head>
"""


BODY_HEADER = """
<div class="wrap">
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
    <label>Year mode</label>
    <label><input type="radio" name="year-mode" value="single" checked> Single Year</label>
    <label><input type="radio" name="year-mode" value="all"> All Years</label>
    <label><input type="radio" name="year-mode" value="blend"> 2025+2026 Blend</label>
  </span>
  <span id="single-year-wrap">
    <label>Year</label>
    <select id="single-year-select"></select>
  </span>
  <span>
    <label><input type="checkbox" id="include-partial" checked style="accent-color:var(--accent);margin-right:.3em;"> Include partial seasons</label>
  </span>
  <span id="filter-summary" class="filter-summary"></span>
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
  <div id="home-arch-hit" style="height: 580px;"></div>
  <div id="home-arch-sp"  style="height: 580px; margin-top: 1.2em;"></div>

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
      <p><b>Archetype color groupings.</b> Within the legend, archetypes are
      grouped by primary trait family: hitters use ELITE / POWER / CONTACT /
      DISCIPLINE / AVERAGE / BELOW; SPs use ELITE / STUFF / MOVEMENT / CONTROL
      / AVERAGE / BELOW. Each family gets its own color hue; lighter shades
      within a family indicate stronger sub-archetypes.</p>
      <p><b>Custom quadrant.</b> Pick any X and Y from the rating dimensions.
      Reference lines at x=50 and y=50 mark the league-average crosshair —
      the top-right quadrant is "good at both."</p>
      <p><b>Year mode semantics.</b> <i>Single Year</i> filters to that
      season's qualifiers (PA ≥ 250 hitters / GS ≥ 20 SPs full season,
      lower in-progress). <i>All Years</i> shows every player-year as an
      independent row. <i>2025+2026 Blend</i> aggregates one row per player
      via PA-weighted (hitter) / GS-weighted (SP) mean of each rating, then
      re-buckets the archetype label from the blended ratings.</p>
      <div class="grid" id="boundary-glossary"></div>
    </div>
  </details>
</div>
"""


HITTERS_TAB = """
<div id="tab-hitters" class="tab-panel">
  <h2>Hitter custom quadrant</h2>
  <div class="quad-controls">
    <label>X axis</label>
    <select id="h-x">
      <option value="CONTACT">Contact</option>
      <option value="POWER" selected>Power</option>
      <option value="DISCIPLINE">Discipline</option>
      <option value="SB">SB</option>
    </select>
    <label>Y axis</label>
    <select id="h-y">
      <option value="CONTACT" selected>Contact</option>
      <option value="POWER">Power</option>
      <option value="DISCIPLINE">Discipline</option>
      <option value="SB">SB</option>
    </select>
    <span class="r-display" id="h-r"></span>
  </div>
  <div class="quadrant-host"><div id="h-quad" style="height: 540px;"></div></div>

  <h2>Hitter archetype roster</h2>
  <div id="h-archetype-tables"></div>
</div>
"""


PITCHERS_TAB = """
<div id="tab-pitchers" class="tab-panel">
  <h2>Pitcher custom quadrant</h2>
  <div class="quad-controls">
    <label>X axis</label>
    <select id="s-x">
      <option value="STUFF">Stuff</option>
      <option value="MOVEMENT" selected>Movement</option>
      <option value="CONTROL">Control</option>
      <option value="velo_rating">Velo</option>
    </select>
    <label>Y axis</label>
    <select id="s-y">
      <option value="STUFF" selected>Stuff</option>
      <option value="MOVEMENT">Movement</option>
      <option value="CONTROL">Control</option>
      <option value="velo_rating">Velo</option>
    </select>
    <span class="r-display" id="s-r"></span>
  </div>
  <div class="quadrant-host"><div id="s-quad" style="height: 540px;"></div></div>

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


JS = r"""
<script>
const D = window.PROFILES_DATA;
const HITTERS = D.hitters;
const SPS     = D.sps;
const HDEFS   = D.hitter_archetype_defs;
const SDEFS   = D.sp_archetype_defs;

const HARCH_DESC = {}; Object.values(HDEFS).forEach(v => HARCH_DESC[v.label] = v.description);
const SARCH_DESC = {}; Object.values(SDEFS).forEach(v => SARCH_DESC[v.label] = v.description);

const H_BY_ID = {}; HITTERS.forEach(r => { (H_BY_ID[r.batter] = H_BY_ID[r.batter] || []).push(r); });
const S_BY_ID = {}; SPS.forEach(r => { (S_BY_ID[r.pitcher] = S_BY_ID[r.pitcher] || []).push(r); });

// ── Axis labels (display only) ──────────────────────────────────────────
const HITTER_AXIS_LABEL = { CONTACT: 'Contact', POWER: 'Power', DISCIPLINE: 'Discipline', SB: 'SB' };
const SP_AXIS_LABEL     = { STUFF: 'Stuff', MOVEMENT: 'Movement', CONTROL: 'Control', velo_rating: 'Velo' };

// ── Archetype category classification ──────────────────────────────────
// Hitters: every cell -> category. Categories: ELITE, POWER, CONTACT, DISCIPLINE, AVERAGE, BELOW.
const HITTER_ARCH_CAT = {
  GOAT_TIER:         'ELITE',
  CONTACT_POWER:     'ELITE',
  AGGRESSIVE_STAR:   'ELITE',
  CONTACT_EYE:       'ELITE',
  POWER_EYE:         'ELITE',
  SLAP_AND_WALK:     'ELITE',
  THREE_TRUE_OUTCOMES:'ELITE',

  PURE_HITTER:       'CONTACT',
  CONTACT_HACKER:    'CONTACT',
  SLAP_HITTER:       'CONTACT',
  AGGRESSIVE_SLAP:   'CONTACT',

  POWER_HITTER:      'POWER',
  ALL_OR_NOTHING:    'POWER',
  POWER_K:           'POWER',
  POWER_HACKER:      'POWER',

  BALANCED_EYE:      'DISCIPLINE',
  SECONDARY_LEADOFF: 'DISCIPLINE',
  PATIENT_K:         'DISCIPLINE',
  WALK_ONLY_FRINGE:  'DISCIPLINE',

  AVERAGE_HITTER:    'AVERAGE',
  AVG_HACKER:        'AVERAGE',
  GENERIC_NO_POWER:  'AVERAGE',
  NO_POWER_HACKER:   'AVERAGE',

  BACKUP_BAT:        'BELOW',
  K_PRONE_FILLER:    'BELOW',
  FRINGE:            'BELOW',
  BUST:              'BELOW',
};

// SPs: every cell -> category. ELITE / STUFF / MOVEMENT / CONTROL / AVERAGE / BELOW.
const SP_ARCH_CAT = {
  MT_RUSHMORE:           'ELITE',
  STUFF_PLUS_MOVE:       'ELITE',
  STUFF_MOVE_WILD:       'ELITE',
  STUFF_PLUS_CTRL:       'ELITE',
  MOVE_CTRL_ACE:         'ELITE',
  SOFT_TOSS_ARTIST:      'ELITE',

  PURE_STUFF:            'STUFF',
  WILD_FIREBALLER:       'STUFF',
  K_AND_CTRL_HR_RISK:    'STUFF',
  STUFF_NO_MOVE:         'STUFF',
  PURE_STUFF_LIABILITY:  'STUFF',

  PURE_MOVEMENT:         'MOVEMENT',
  MOVE_WILD:             'MOVEMENT',
  SINKER_ONLY:           'MOVEMENT',
  SINKER_WILD:           'MOVEMENT',

  PURE_CONTROL:          'CONTROL',
  CTRL_HR_PRONE:         'CONTROL',
  JUNKBALLER:            'CONTROL',
  PIT_CHF_CTRL:          'CONTROL',

  AVERAGE_4_5:           'AVERAGE',
  WILD_MID:              'AVERAGE',
  GENERIC_HR_PRONE:      'AVERAGE',

  FILLER:                'BELOW',
  LIABILITY:             'BELOW',
  BAD_BIG_INNINGS:       'BELOW',
  PIT_CHF:               'BELOW',
  FRINGE:                'BELOW',
};

// Category color anchors + a small family ramp per category
const CAT_ORDER_HITTER = ['ELITE','POWER','CONTACT','DISCIPLINE','AVERAGE','BELOW'];
const CAT_ORDER_SP     = ['ELITE','STUFF','MOVEMENT','CONTROL','AVERAGE','BELOW'];

const CAT_FAMILY = {
  ELITE:      ['#d97757','#e89576','#f0b298','#c45c39','#a8421f'],            // accent / warm orange-red family
  POWER:      ['#c1666b','#d48289','#e6a3a8','#a8424a','#8a3038'],            // red family
  STUFF:      ['#c1666b','#d48289','#e6a3a8','#a8424a','#8a3038'],            // red family (same idea: high-K)
  CONTACT:    ['#7fb069','#9bc784','#b7d9a4','#5e8a4b','#456a37'],            // sage green family
  MOVEMENT:   ['#7fb069','#9bc784','#b7d9a4','#5e8a4b','#456a37'],            // sage green family
  DISCIPLINE: ['#b099d4','#c9b5e0','#dfd0ed','#9077b8','#735a99'],            // muted lavender
  CONTROL:    ['#b099d4','#c9b5e0','#dfd0ed','#9077b8','#735a99'],            // muted lavender
  AVERAGE:    ['#a89e8a','#b8af9d','#c9c1b0','#8d8579','#6a6258'],            // warm gray
  BELOW:      ['#5a5347','#6a6258','#7a7261','#48433b','#34302a'],            // dim
};

// Assign a stable color to each archetype label within its family
function buildColorMap(catMap, catOrder) {
  // group by category, sort labels for stable shade assignment
  const byCat = {};
  Object.entries(catMap).forEach(([label, cat]) => { (byCat[cat] = byCat[cat] || []).push(label); });
  catOrder.forEach(c => { (byCat[c] || []).sort(); });
  const out = {};
  catOrder.forEach(cat => {
    const labels = byCat[cat] || [];
    const family = CAT_FAMILY[cat];
    labels.forEach((label, i) => {
      out[label] = family[i % family.length];
    });
  });
  return out;
}
const HITTER_COLOR = buildColorMap(HITTER_ARCH_CAT, CAT_ORDER_HITTER);
const SP_COLOR     = buildColorMap(SP_ARCH_CAT,     CAT_ORDER_SP);

// Global UI state
const state = {
  tab: 'home',
  yearMode: 'single',
  singleYear: D.current_year,
  includePartial: true,
  hX: 'POWER', hY: 'CONTACT',
  sX: 'MOVEMENT', sY: 'STUFF',
};

// Inline badge for partial-season players
function partialBadge(r) {
  return r && r.data_tier === 'PARTIAL' ? ' <span class="badge partial">PARTIAL</span>' : '';
}

// ── Pearson r ──────────────────────────────────────────────────────────
function pearson(xs, ys) {
  const px = [], py = [];
  for (let i = 0; i < xs.length; i++) {
    if (Number.isFinite(xs[i]) && Number.isFinite(ys[i])) { px.push(xs[i]); py.push(ys[i]); }
  }
  const n = px.length;
  if (n < 3) return { r: null, n };
  const mx = px.reduce((a,b)=>a+b,0)/n, my = py.reduce((a,b)=>a+b,0)/n;
  let sxx=0, syy=0, sxy=0;
  for (let i = 0; i < n; i++) { const dx = px[i]-mx, dy = py[i]-my; sxx+=dx*dx; syy+=dy*dy; sxy+=dx*dy; }
  if (sxx === 0 || syy === 0) return { r: null, n };
  return { r: sxy / Math.sqrt(sxx*syy), n };
}

function olsLine(xs, ys) {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a,b)=>a+b,0)/n, my = ys.reduce((a,b)=>a+b,0)/n;
  let sxx=0, sxy=0;
  for (let i = 0; i < n; i++) { sxx += (xs[i]-mx)**2; sxy += (xs[i]-mx)*(ys[i]-my); }
  if (sxx === 0) return null;
  const slope = sxy/sxx, icpt = my - slope*mx;
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  return { x: [xmin, xmax], y: [xmin*slope+icpt, xmax*slope+icpt] };
}

// ── Filtering / blend ─────────────────────────────────────────────────
function bucket(v) { return v >= 60 ? 'PLUS' : (v >= 40 ? 'AVG' : 'MINUS'); }
function lookupHitterArch(c,p,d){ return (HDEFS[bucket(c)+'/'+bucket(p)+'/'+bucket(d)] || {label:'UNKNOWN'}).label; }
function lookupSpArch(s,m,c){ return (SDEFS[bucket(s)+'/'+bucket(m)+'/'+bucket(c)] || {label:'UNKNOWN'}).label; }

function paWeightBlend(rows, idKey, fpKey) {
  const byId = {};
  rows.forEach(r => { (byId[r[idKey]] = byId[r[idKey]] || []).push(r); });
  const PA_KEY = idKey === 'batter' ? 'pa' : 'gs';
  const HITTER_NUMS = ['CONTACT','POWER','DISCIPLINE','SB',
    'r_Contact','r_K','r_BABIP','r_xCON','r_Barrel','r_HardHit','r_ISO','r_HRrate','r_PullFB',
    'r_BB','r_Chase','r_ZSwing','r_SBrate','r_Sprint'];
  const SP_NUMS = ['STUFF','MOVEMENT','CONTROL','velo_rating',
    'r_K','r_SwStr','r_CSW','r_HRrate','r_Barrel','r_HardHit','r_GB','r_xCON','r_BB'];
  const NUMS = idKey === 'batter' ? HITTER_NUMS : SP_NUMS;
  const out = [];
  Object.entries(byId).forEach(([id, recs]) => {
    const sel = recs.filter(r => r.year === 2025 || r.year === 2026);
    if (!sel.length) return;
    const wsum = sel.reduce((a,r) => a + (r[PA_KEY] || 0), 0);
    if (!wsum) return;
    const last = sel.slice().sort((a,b) => b.year - a.year)[0];
    const blend = { ...last };
    blend.year = 'blend';
    NUMS.forEach(c => {
      let s = 0;
      sel.forEach(r => { s += (r[c] || 0) * (r[PA_KEY] || 0); });
      blend[c] = Math.round(s / wsum);
    });
    blend[PA_KEY] = wsum;
    blend.archetype = idKey === 'batter'
      ? lookupHitterArch(blend.CONTACT, blend.POWER, blend.DISCIPLINE)
      : lookupSpArch(blend.STUFF, blend.MOVEMENT, blend.CONTROL);
    blend[fpKey] = sel.reduce((a,r) => a + (r[fpKey] || 0) * (r[PA_KEY] || 0), 0) / wsum;
    blend.rank_in_year = null;
    out.push(blend);
  });
  out.sort((a,b) => b[fpKey] - a[fpKey]);
  out.forEach((r, i) => r.rank_in_year = i + 1);
  return out;
}

function filterRows(rows, role) {
  let r;
  if (state.yearMode === 'single')      r = rows.filter(x => x.year === state.singleYear);
  else if (state.yearMode === 'all')    r = rows.slice();
  else r = paWeightBlend(rows, role === 'hitter' ? 'batter' : 'pitcher',
                          role === 'hitter' ? 'fp_per_pa' : 'fp_per_start');
  // Partial-season filter — blend mode keeps everyone (already aggregated)
  if (!state.includePartial && state.yearMode !== 'blend') {
    r = r.filter(x => x.data_tier !== 'PARTIAL');
  }
  return r;
}

// ── Quadrant rendering ────────────────────────────────────────────────
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

function renderQuadrant(divId, rDispId, rows, xKey, yKey, role) {
  const idKey = role === 'hitter' ? 'batter' : 'pitcher';
  const catMap = role === 'hitter' ? HITTER_ARCH_CAT : SP_ARCH_CAT;
  const colorMap = role === 'hitter' ? HITTER_COLOR : SP_COLOR;
  const catOrder = role === 'hitter' ? CAT_ORDER_HITTER : CAT_ORDER_SP;
  const axisLabel = role === 'hitter' ? HITTER_AXIS_LABEL : SP_AXIS_LABEL;

  // build aligned points
  const px=[], py=[], meta=[];
  rows.forEach(r => {
    const x = r[xKey], y = r[yKey];
    if (Number.isFinite(x) && Number.isFinite(y)) { px.push(x); py.push(y); meta.push(r); }
  });
  const rRes = pearson(px, py);
  document.getElementById(rDispId).innerHTML = rRes.r == null
    ? `r = — (n=${rRes.n})`
    : `r = ${rRes.r.toFixed(3)} · n = ${rRes.n}`;

  // group points by archetype, ordered by category so legend reads top-down
  const byArch = {};
  meta.forEach((r, i) => {
    const a = r.archetype || 'UNK';
    (byArch[a] = byArch[a] || { x:[], y:[], txt:[], ids:[] });
    byArch[a].x.push(px[i]); byArch[a].y.push(py[i]);
    byArch[a].txt.push(hoverText(r, role));
    byArch[a].ids.push(r[idKey]);
  });
  // sort labels by category order then alpha
  const orderedLabels = Object.keys(byArch).sort((a,b) => {
    const ca = catOrder.indexOf(catMap[a] || 'BELOW');
    const cb = catOrder.indexOf(catMap[b] || 'BELOW');
    if (ca !== cb) return ca - cb;
    return a.localeCompare(b);
  });

  const traces = orderedLabels.map(label => {
    const g = byArch[label];
    const cat = catMap[label] || 'BELOW';
    return {
      x: g.x, y: g.y,
      name: label,
      legendgroup: cat,
      legendgrouptitle: { text: cat },
      mode: 'markers', type: 'scattergl',
      text: g.txt, hovertemplate: '%{text}<extra></extra>',
      customdata: g.ids,
      marker: { color: colorMap[label] || '#888', size: 8, opacity: 0.85,
                 line: { width: 0.5, color: 'rgba(0,0,0,0.4)' } },
    };
  });

  // OLS overlay
  const ols = olsLine(px, py);
  if (ols) traces.push({
    x: ols.x, y: ols.y, mode: 'lines', type: 'scatter',
    name: 'OLS fit', legendgroup: 'fit',
    line: { color: '#d97757', width: 1.5, dash: 'dash' },
    hoverinfo: 'skip', showlegend: true,
  });

  // Plot range — keep [20,80] when both axes are 20-80 ratings; auto for velo
  const ratingAxes = ['CONTACT','POWER','DISCIPLINE','SB','STUFF','MOVEMENT','CONTROL','velo_rating'];
  const xRange = ratingAxes.includes(xKey) ? [20, 80] : undefined;
  const yRange = ratingAxes.includes(yKey) ? [20, 80] : undefined;

  // 50/50 reference lines (only when on rating scale)
  const shapes = [];
  if (xRange) shapes.push({ type:'line', x0:50, x1:50, yref:'paper', y0:0, y1:1,
                            line:{ color:'#8d8579', width:1, dash:'dot' } });
  if (yRange) shapes.push({ type:'line', xref:'paper', x0:0, x1:1, y0:50, y1:50,
                            line:{ color:'#8d8579', width:1, dash:'dot' } });

  // Quadrant labels (only when both 20-80)
  const annotations = [];
  if (xRange && yRange) {
    annotations.push(
      { x:70, y:75, text:'PLUS both', showarrow:false, font:{ color:'#7fb069', size:10, family:'IBM Plex Mono' } },
      { x:30, y:75, text:`+ ${axisLabel[yKey]} only`, showarrow:false, font:{ color:'#d4a945', size:10, family:'IBM Plex Mono' } },
      { x:70, y:25, text:`+ ${axisLabel[xKey]} only`, showarrow:false, font:{ color:'#d4a945', size:10, family:'IBM Plex Mono' } },
      { x:30, y:25, text:'MINUS both', showarrow:false, font:{ color:'#c1666b', size:10, family:'IBM Plex Mono' } },
    );
  }

  Plotly.react(divId, traces, {
    paper_bgcolor: '#211e1a', plot_bgcolor: '#1a1815',
    font: { color: '#f5f1ea', family: 'IBM Plex Mono, monospace', size: 11 },
    margin: { l: 56, r: 10, t: 10, b: 50 },
    xaxis: { title: { text: axisLabel[xKey] || xKey, font: { size: 13, color: '#d97757' } },
             gridcolor: '#34302a', zerolinecolor: '#34302a',
             range: xRange, tick0: 20, dtick: 10 },
    yaxis: { title: { text: axisLabel[yKey] || yKey, font: { size: 13, color: '#d97757' } },
             gridcolor: '#34302a', zerolinecolor: '#34302a',
             range: yRange, tick0: 20, dtick: 10 },
    shapes, annotations,
    showlegend: true,
    legend: { font: { size: 10, color: '#f5f1ea', family: 'IBM Plex Mono' },
              bgcolor: 'rgba(33,30,26,0.85)', bordercolor: '#34302a', borderwidth: 1,
              groupclick: 'togglegroup', tracegroupgap: 8,
              x: 1.02, y: 1 },
  }, { displayModeBar: false, responsive: true });

  // Click → modal
  const div = document.getElementById(divId);
  if (div._clickWired) return;
  div._clickWired = true;
  div.on('plotly_click', e => {
    const pt = e.points[0];
    const id = pt.customdata;
    if (id != null) openModal(role, id);
  });
}

// ── Archetype tables ──────────────────────────────────────────────────
function renderArchetypeTables(rows, role, targetId) {
  const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
  const archDesc = role === 'hitter' ? HARCH_DESC : SARCH_DESC;
  const catMap = role === 'hitter' ? HITTER_ARCH_CAT : SP_ARCH_CAT;
  const catOrder = role === 'hitter' ? CAT_ORDER_HITTER : CAT_ORDER_SP;
  const byArch = {};
  rows.forEach(r => { (byArch[r.archetype] = byArch[r.archetype] || []).push(r); });

  const arches = Object.entries(byArch).map(([a, rs]) => {
    const mean = rs.reduce((s,r) => s + (r[fpKey]||0), 0) / rs.length;
    return { arch: a, rows: rs, mean, cat: catMap[a] || 'BELOW' };
  }).sort((a,b) => {
    const ca = catOrder.indexOf(a.cat), cb = catOrder.indexOf(b.cat);
    if (ca !== cb) return ca - cb;
    return b.mean - a.mean;
  });

  let html = '';
  let lastCat = null;
  arches.forEach(({arch, rows: rs, mean, cat}) => {
    if (cat !== lastCat) {
      html += `<h3 style="color:var(--dim);font-size:.78em;text-transform:uppercase;letter-spacing:.15em;margin-top:1.2em;border-bottom:1px solid var(--faint);padding-bottom:.3em;">${cat}</h3>`;
      lastCat = cat;
    }
    rs.sort((a,b) => (b[fpKey]||0) - (a[fpKey]||0));
    const desc = archDesc[arch] || '';
    html += `<details><summary>${arch}<span class="count">n=${rs.length}, mean ${fpKey}=${mean.toFixed(role==='hitter'?3:2)}</span><span class="desc">${desc}</span></summary><table><thead>`;
    if (role === 'hitter') {
      html += '<tr><th class="num">#</th><th>Player</th><th>Team</th><th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th><th>SB tier</th><th>Age</th><th>Bnd</th><th class="num">FP/PA</th><th class="num">Rank</th></tr></thead><tbody>';
      rs.forEach((r, i) => {
        html += `<tr><td class="num">${i+1}</td>`
              + `<td class="player" data-role="hitter" data-id="${r.batter}">${r.player_name}${partialBadge(r)}</td>`
              + `<td>${r.team||''}</td>`
              + `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
              + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
              + `<td>${r.sb_tier||''}</td><td>${r.age_tier||''}</td>`
              + `<td>${r.boundary_tier||''}</td>`
              + `<td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`
              + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
      });
    } else {
      html += '<tr><th class="num">#</th><th>Pitcher</th><th class="num">S</th><th class="num">M</th><th class="num">C</th><th class="num">Velo</th><th>Velo tier</th><th>Age</th><th>Bnd</th><th class="num">FP/start</th><th class="num">Rank</th></tr></thead><tbody>';
      rs.forEach((r, i) => {
        html += `<tr><td class="num">${i+1}</td>`
              + `<td class="player" data-role="sp" data-id="${r.pitcher}">${r.player_name}${partialBadge(r)}</td>`
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
  document.querySelectorAll(`#${targetId} td.player`).forEach(td => {
    td.addEventListener('click', () => openModal(td.dataset.role, parseInt(td.dataset.id)));
  });
}

// ── Leaderboards ──────────────────────────────────────────────────────
function renderLeaderboard(rows, role, targetId) {
  const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
  const top = rows.slice().sort((a,b) => (b[fpKey]||0) - (a[fpKey]||0)).slice(0, 15);
  let html = '<table><thead><tr><th class="num">#</th><th>Player</th>';
  if (role === 'hitter') html += '<th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th><th>Archetype</th><th class="num">FP/PA</th>';
  else                    html += '<th class="num">S</th><th class="num">M</th><th class="num">C</th><th>Archetype</th><th class="num">FP/start</th>';
  html += '</tr></thead><tbody>';
  top.forEach((r, i) => {
    html += `<tr><td class="num">${i+1}</td>`
          + `<td class="player" data-role="${role}" data-id="${role==='hitter'?r.batter:r.pitcher}">${r.player_name}${partialBadge(r)}</td>`;
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

// ── Home stacked-bar archetype distribution (grouped by category) ─────
function renderHomeArchDist() {
  renderStackedArchDist('home-arch-hit', HITTERS, HITTER_ARCH_CAT, CAT_ORDER_HITTER, HITTER_COLOR, 'Hitter archetypes per year');
  renderStackedArchDist('home-arch-sp',  SPS,     SP_ARCH_CAT,     CAT_ORDER_SP,     SP_COLOR,     'SP archetypes per year');
}

function renderStackedArchDist(divId, rows, catMap, catOrder, colorMap, title) {
  const byYrArch = {};
  rows.forEach(r => {
    const k = `${r.year}|${r.archetype}`;
    byYrArch[k] = (byYrArch[k] || 0) + 1;
  });
  const years = [...new Set(rows.map(r => r.year))].sort();
  const labels = [...new Set(rows.map(r => r.archetype))];
  // Sort labels by category order (so stack order is consistent + legend reads top-down)
  labels.sort((a,b) => {
    const ca = catOrder.indexOf(catMap[a] || 'BELOW');
    const cb = catOrder.indexOf(catMap[b] || 'BELOW');
    if (ca !== cb) return ca - cb;
    return a.localeCompare(b);
  });
  const traces = labels.map(label => ({
    name: label,
    legendgroup: catMap[label] || 'BELOW',
    legendgrouptitle: { text: catMap[label] || 'BELOW' },
    x: years,
    y: years.map(y => byYrArch[`${y}|${label}`] || 0),
    type: 'bar',
    marker: { color: colorMap[label] || '#888' },
  }));
  Plotly.react(divId, traces, {
    barmode: 'stack',
    paper_bgcolor: '#211e1a', plot_bgcolor: '#1a1815',
    font: { color: '#f5f1ea', family: 'IBM Plex Mono, monospace', size: 11 },
    title: { text: title, font: { color: '#d97757', family: 'Source Serif 4, serif', size: 16 },
             x: 0.02 },
    margin: { l: 60, r: 30, t: 50, b: 50 },
    xaxis: { gridcolor: '#34302a', tickmode: 'linear', dtick: 1 },
    yaxis: { gridcolor: '#34302a', title: { text: 'qualified players', font: { size: 11 } } },
    legend: { font: { size: 9, color: '#f5f1ea', family: 'IBM Plex Mono' },
              bgcolor: 'rgba(33,30,26,0.85)', bordercolor: '#34302a', borderwidth: 1,
              groupclick: 'togglegroup', tracegroupgap: 6 },
  }, { displayModeBar: false, responsive: true });
}

// ── Boundary glossary ────────────────────────────────────────────────
function renderBoundaryGlossary() {
  const sides = [
    { title: 'Hitters',           data: D.hitter_boundary },
    { title: 'Starting pitchers', data: D.sp_boundary },
  ];
  let html = '';
  sides.forEach(s => {
    html += `<div><h3 style="color:var(--accent);font-family:Source Serif 4,serif;">${s.title}</h3>`;
    html += '<table><thead><tr><th>Tier</th><th class="num">n transitions</th><th class="num">YoY retention</th></tr></thead><tbody>';
    ['EDGE','NEAR_EDGE','SOLID'].forEach(t => {
      const v = s.data[t];
      if (!v) return;
      html += `<tr><td>${t}</td><td class="num">${v.n_transitions}</td><td class="num">${v.retention_pct}%</td></tr>`;
    });
    html += '</tbody></table></div>';
  });
  document.getElementById('boundary-glossary').innerHTML = html;
}

// ── Modal ───────────────────────────────────────────────────────────
function openModal(role, id) {
  const records = (role === 'hitter' ? H_BY_ID[id] : S_BY_ID[id]) || [];
  if (!records.length) return;
  const sorted = records.slice().sort((a,b) => a.year - b.year);
  const last = sorted[sorted.length - 1];
  let html = `<h2>${last.player_name}${partialBadge(last)}</h2>`;
  if (role === 'hitter') html += `<div class="latest-line">Latest: ${last.team || '—'} · age ${last.age ?? '?'} (${last.age_tier})</div>`;
  else                    html += `<div class="latest-line">Latest: age ${last.age ?? '?'} (${last.age_tier})</div>`;
  html += '<div class="traj">' + sorted.map(r => `<span>${r.year}: <b>${r.archetype}</b></span>`).join('<span class="arrow">→</span>') + '</div>';
  html += '<table><thead><tr><th class="num">Year</th><th class="num">Age</th>';
  if (role === 'hitter') html += '<th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th><th>Archetype</th><th>Subtypes</th><th>Bnd</th><th class="num">FP/PA</th><th class="num">Rank</th>';
  else                    html += '<th class="num">S</th><th class="num">M</th><th class="num">C</th><th class="num">Velo</th><th>Archetype</th><th>Subtypes</th><th>Bnd</th><th class="num">FP/start</th><th class="num">Rank</th>';
  html += '</tr></thead><tbody>';
  sorted.forEach(r => {
    if (role === 'hitter') {
      html += `<tr><td class="num">${r.year}${r.data_tier==='PARTIAL'?' <span class="badge partial">P</span>':''}</td><td class="num">${r.age ?? ''}</td>`
            + `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
            + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
            + `<td>${r.archetype}</td>`
            + `<td><span style="color:var(--dim);">${[r.contact_subtype, r.power_subtype, r.discipline_subtype, r.sb_tier].filter(Boolean).join(' / ')}</span></td>`
            + `<td>${r.boundary_tier||''}</td>`
            + `<td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`
            + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
    } else {
      html += `<tr><td class="num">${r.year}${r.data_tier==='PARTIAL'?' <span class="badge partial">P</span>':''}</td><td class="num">${r.age ?? ''}</td>`
            + `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
            + `<td class="num">${r.CONTROL}</td><td class="num">${r.velo_rating ?? ''}</td>`
            + `<td>${r.archetype}</td>`
            + `<td><span style="color:var(--dim);">${[r.stuff_subtype, r.velo_tier, r.pitch_archetype].filter(Boolean).join(' / ')}</span></td>`
            + `<td>${r.boundary_tier||''}</td>`
            + `<td class="num">${(r.fp_per_start||0).toFixed(2)}</td>`
            + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
    }
  });
  html += '</tbody></table>';
  html += '<div id="modal-spark" style="height: 300px; margin-top: 1em;"></div>';
  document.getElementById('modal-content').innerHTML = html;
  document.getElementById('modal-bg').classList.add('open');
  renderSparkline(sorted, role);
}

function closeModal() { document.getElementById('modal-bg').classList.remove('open'); }

function renderSparkline(sorted, role) {
  const xs = sorted.map(r => r.year);
  const keys = role === 'hitter'
    ? [['CONTACT','#7fb069'], ['POWER','#c1666b'], ['DISCIPLINE','#b099d4'], ['SB','#d97757']]
    : [['STUFF','#c1666b'], ['MOVEMENT','#7fb069'], ['CONTROL','#b099d4'], ['velo_rating','#d97757']];
  const traces = keys.map(([k, color]) => ({
    x: xs, y: sorted.map(r => r[k]), mode: 'lines+markers', name: k,
    line: { color, width: 2 }, marker: { size: 8 },
  }));
  const shapes = [
    { type:'line', xref:'paper', x0:0, x1:1, y0:60, y1:60, line:{ color:'#7fb069', dash:'dot', width:1 } },
    { type:'line', xref:'paper', x0:0, x1:1, y0:50, y1:50, line:{ color:'#8d8579', dash:'dot', width:1 } },
    { type:'line', xref:'paper', x0:0, x1:1, y0:40, y1:40, line:{ color:'#c1666b', dash:'dot', width:1 } },
  ];
  Plotly.react('modal-spark', traces, {
    paper_bgcolor: '#1a1815', plot_bgcolor: '#211e1a',
    font: { color: '#f5f1ea', family: 'IBM Plex Mono, monospace', size: 11 },
    margin: { l: 50, r: 10, t: 10, b: 35 },
    xaxis: { gridcolor: '#34302a', tickmode: 'linear', dtick: 1 },
    yaxis: { gridcolor: '#34302a', range: [20, 80], tick0: 20, dtick: 10 },
    shapes,
    legend: { orientation: 'h', y: -0.15, font: { size: 10, family: 'IBM Plex Mono' } },
  }, { displayModeBar: false, responsive: true });
}

// ── Search ──────────────────────────────────────────────────────────
function buildSearchIndex() {
  const idx = [];
  Object.entries(H_BY_ID).forEach(([id, recs]) => {
    const last = recs.slice().sort((a,b) => b.year - a.year)[0];
    idx.push({ id: parseInt(id), role: 'hitter', name: last.player_name,
               label: last.player_name, meta: `Hitter · ${last.team || '—'} · last ${last.year}` });
  });
  Object.entries(S_BY_ID).forEach(([id, recs]) => {
    const last = recs.slice().sort((a,b) => b.year - a.year)[0];
    idx.push({ id: parseInt(id), role: 'sp', name: last.player_name,
               label: last.player_name, meta: `SP · last ${last.year}` });
  });
  return idx;
}
const SEARCH_INDEX = buildSearchIndex();

function runSearch(q) {
  const box = document.getElementById('search-results');
  if (!q || q.length < 2) { box.classList.remove('open'); box.innerHTML = ''; return; }
  const ql = q.toLowerCase();
  const hits = SEARCH_INDEX.filter(o => o.name.toLowerCase().includes(ql)).slice(0, 20);
  if (!hits.length) { box.innerHTML = '<div class="item" style="color:var(--dim);">no match</div>'; box.classList.add('open'); return; }
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

// ── Master render ──────────────────────────────────────────────────
function renderAll() {
  const hitterRows = filterRows(HITTERS, 'hitter');
  const spRows     = filterRows(SPS,     'sp');

  const ym = state.yearMode === 'single' ? `Single ${state.singleYear}` :
             state.yearMode === 'all'    ? 'All years' : '2025+2026 Blend';
  document.getElementById('filter-summary').textContent =
    `${ym} · ${hitterRows.length} hitters · ${spRows.length} SPs`;

  renderLeaderboard(hitterRows, 'hitter', 'lb-hitters');
  renderLeaderboard(spRows,    'sp',     'lb-sps');

  renderQuadrant('h-quad', 'h-r', hitterRows, state.hX, state.hY, 'hitter');
  renderQuadrant('s-quad', 's-r', spRows,     state.sX, state.sY, 'sp');

  renderArchetypeTables(hitterRows, 'hitter', 'h-archetype-tables');
  renderArchetypeTables(spRows,     'sp',     's-archetype-tables');
}

// ── Resize Plotly when its tab becomes visible ──────────────────────
function resizeCurrentTabPlots() {
  const ids = state.tab === 'home'    ? ['home-arch-hit','home-arch-sp']
            : state.tab === 'hitters' ? ['h-quad']
            : state.tab === 'pitchers'? ['s-quad'] : [];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el && el.data) Plotly.Plots.resize(el);
  });
}

// ── Init ───────────────────────────────────────────────────────────
function init() {
  const sel = document.getElementById('single-year-select');
  D.years.forEach(y => {
    const o = document.createElement('option'); o.value = y; o.textContent = y;
    if (y === D.current_year) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener('change', () => { state.singleYear = parseInt(sel.value); renderAll(); });

  document.querySelectorAll('input[name="year-mode"]').forEach(rb => {
    rb.addEventListener('change', () => {
      state.yearMode = rb.value;
      document.getElementById('single-year-wrap').style.display =
        state.yearMode === 'single' ? '' : 'none';
      renderAll();
    });
  });

  // Partial-season filter
  document.getElementById('include-partial').addEventListener('change', e => {
    state.includePartial = e.target.checked;
    renderAll();
  });

  // Axis selectors
  document.getElementById('h-x').addEventListener('change', e => { state.hX = e.target.value; renderAll(); });
  document.getElementById('h-y').addEventListener('change', e => { state.hY = e.target.value; renderAll(); });
  document.getElementById('s-x').addEventListener('change', e => { state.sX = e.target.value; renderAll(); });
  document.getElementById('s-y').addEventListener('change', e => { state.sY = e.target.value; renderAll(); });

  // Tabs
  document.querySelectorAll('.tabs button').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      document.getElementById('tab-' + b.dataset.tab).classList.add('active');
      state.tab = b.dataset.tab;
      // After display:block transition, ask Plotly to recompute sizes
      requestAnimationFrame(resizeCurrentTabPlots);
    });
  });

  // Search
  const si = document.getElementById('search-input');
  si.addEventListener('input', () => runSearch(si.value.trim()));
  si.addEventListener('blur', () => setTimeout(() => {
    document.getElementById('search-results').classList.remove('open');
  }, 200));

  // Modal
  document.getElementById('modal-bg').addEventListener('click', closeModal);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  renderBoundaryGlossary();
  renderHomeArchDist();
  renderAll();

  // After initial paint, resize again to ensure off-tab plots size correctly when first shown
  window.addEventListener('resize', resizeCurrentTabPlots);
}

document.addEventListener('DOMContentLoaded', init);
</script>
"""

CLOSE = """
</div><!-- /.wrap -->
"""


def render_page(payload: dict) -> str:
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
            + CLOSE
            + f'<script>window.PROFILES_DATA = {payload_json};</script>\n'
            + JS
            + '</body>\n</html>\n')
