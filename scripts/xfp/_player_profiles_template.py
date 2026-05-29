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
  --dim: #a89e8a;
  --faint: #3a352e;
  --accent: #d97757;
  --pos: #7fb069;
  --neg: #c1666b;
  --warn: #d4a945;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: 'Source Serif 4', 'Iowan Old Style', Georgia, serif;
       background: var(--bg); color: var(--text); font-size: 16px; line-height: 1.6; }
.wrap { max-width: 1480px; margin: 0 auto; padding: 0 1.2em 4em 1.2em; }
.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; }

header { border-bottom: 1px solid var(--border); padding: .9em 0;
         position: sticky; top: 0; background: var(--bg); z-index: 100;
         margin-bottom: 1em; }
.header-row { display: flex; justify-content: space-between; align-items: baseline;
              flex-wrap: wrap; gap: 1.2em; }
h1 { color: var(--accent); margin: 0; font-size: 2em; font-weight: 700;
     letter-spacing: .01em; line-height: 1.15; }
h2 { color: var(--text); margin-top: 2em; font-size: 1.5em; font-weight: 600;
     border-bottom: 1px solid var(--border); padding-bottom: .35em;
     letter-spacing: .01em; line-height: 1.2; }
h3 { color: var(--text); margin: 1em 0 .4em 0; font-size: 1.125em; font-weight: 600; line-height: 1.3; }

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

.toc-strip { display: none; gap: .4em; flex-wrap: wrap; padding: .55em 0;
             margin: .4em 0 1em 0; border-top: 1px solid var(--faint);
             border-bottom: 1px solid var(--faint); font-family: 'IBM Plex Mono', monospace;
             font-size: .78em; overflow-x: auto; }
.toc-strip.active { display: flex; }
.toc-strip a { color: var(--dim); text-decoration: none; padding: .25em .7em;
                border-radius: 3px; white-space: nowrap; }
.toc-strip a:hover { color: var(--accent); background: var(--stripe); }
section[id] { scroll-margin-top: 160px; }

.modal-hero { display: flex; justify-content: space-between; align-items: center;
              padding: 1em 0 1.2em 0; border-bottom: 1px solid var(--border);
              margin-bottom: 1em; gap: 1em; flex-wrap: wrap; }
.modal-hero .hero-name { font-size: 1.6em; font-weight: 700; color: var(--accent);
                          font-family: 'Source Serif 4', serif; }
.modal-hero .hero-meta { color: var(--dim); font-family: 'IBM Plex Mono', monospace;
                          font-size: .85em; margin-top: .3em; }
.modal-hero .hero-stats { display: flex; gap: 1em; align-items: center; }
.modal-hero .hero-overall { background: var(--panel); padding: .6em 1em; border-radius: 4px;
                             border: 1px solid var(--border); text-align: center; }
.modal-hero .hero-overall .label { color: var(--dim); font-size: .7em; text-transform: uppercase;
                                    letter-spacing: .12em; font-family: 'IBM Plex Mono', monospace; }
.modal-hero .hero-overall .val { color: var(--accent); font-size: 2em; font-weight: 700;
                                  font-family: 'Source Serif 4', serif; line-height: 1; }
.modal-hero .hero-archetype { color: var(--text); font-family: 'IBM Plex Mono', monospace;
                               font-size: .9em; }

.modal-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 1em;
              font-family: 'IBM Plex Mono', monospace; }
.modal-tabs button { background: transparent; color: var(--dim); border: 0;
                      border-bottom: 2px solid transparent; padding: .55em 1.1em;
                      font-size: .78em; font-weight: 500; cursor: pointer;
                      font-family: inherit; text-transform: uppercase; letter-spacing: .12em; }
.modal-tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }
.modal-tabs button:hover { color: var(--text); }
.modal-mtab-panel { display: none; }
.modal-mtab-panel.active { display: block; }

table { border-collapse: collapse; width: 100%; margin-bottom: 1.2em;
        font-family: 'IBM Plex Mono', monospace; font-size: .87em; }
th { background: var(--panel); padding: .65em .8em;
      border-bottom: 1px solid var(--border); border-top: 1px solid var(--border);
      font-weight: 600; color: var(--dim);
      text-transform: uppercase; font-size: .72em; letter-spacing: .12em;
      text-align: left; font-family: 'IBM Plex Mono', monospace; }
th.num { text-align: right; }
td { padding: .55em .8em; border-bottom: 1px solid var(--faint);
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

/* All-players sortable table */
.alltable-controls { display: flex; gap: 1em; align-items: center; margin-bottom: .5em;
                      font-family: 'IBM Plex Mono', monospace; font-size: .82em; }
.alltable-controls input { background: var(--panel); color: var(--text);
                            border: 1px solid var(--border); border-radius: 3px;
                            padding: .35em .55em; font-family: 'IBM Plex Mono', monospace;
                            font-size: .9em; min-width: 320px; }
.alltable-controls input:focus { outline: 0; border-color: var(--accent); }

/* Horizontal scroll wrapper — works on both alltable and any wide table */
.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch;
                 border: 1px solid var(--border); border-radius: 4px;
                 background: var(--panel); }
.table-scroll::-webkit-scrollbar { height: 10px; }
.table-scroll::-webkit-scrollbar-track { background: var(--stripe); }
.table-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 5px; }
.table-scroll::-webkit-scrollbar-thumb:hover { background: var(--dim); }

table.alltable { min-width: max-content; width: max-content; margin-bottom: 0; }
table.alltable th, table.alltable td { white-space: nowrap; }
table.alltable th { cursor: pointer; user-select: none; }
table.alltable th:hover { color: var(--accent); background: var(--stripe); }
table.alltable th.sort-asc::after  { content: ' ▲'; color: var(--accent); font-size: .85em; }
table.alltable th.sort-desc::after { content: ' ▼'; color: var(--accent); font-size: .85em; }

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

#loading-overlay { position: fixed; inset: 0; background: var(--bg);
                    display: flex; align-items: center; justify-content: center;
                    flex-direction: column; gap: 1em; z-index: 1000;
                    transition: opacity .3s ease; }
#loading-overlay.hidden { opacity: 0; pointer-events: none; }
#loading-overlay .spinner { width: 40px; height: 40px; border: 3px solid var(--faint);
                             border-top-color: var(--accent); border-radius: 50%;
                             animation: spin 1s linear infinite; }
#loading-overlay .label { color: var(--dim); font-family: 'IBM Plex Mono', monospace;
                          font-size: .9em; letter-spacing: .1em; text-transform: uppercase; }
@keyframes spin { to { transform: rotate(360deg); } }

header { transition: padding .2s ease; }
header.collapsed { padding-top: .35em; padding-bottom: .35em; }
header.collapsed h1 { font-size: 1.25em; transition: font-size .2s ease; }
header.collapsed .controls { display: none; }
header.collapsed nav.topnav a { padding-top: .25em; padding-bottom: .25em; }

/* Composition tab — sub-domain breakdown for the selected year */
.composition { display: flex; flex-direction: column; gap: 1em; padding: .5em 0; }
.comp-domain { background: var(--panel); border: 1px solid var(--border);
                border-radius: 5px; padding: .9em 1.1em; }
.comp-domain h4 { margin: 0 0 .6em 0; color: var(--accent); font-size: .95em;
                   font-family: 'Source Serif 4', serif; display: flex;
                   justify-content: space-between; align-items: baseline; }
.comp-domain h4 .domain-rating { color: var(--text); font-family: 'IBM Plex Mono', monospace;
                                  font-size: .85em; font-weight: 400; }
.comp-bars { display: grid; grid-template-columns: 130px 1fr 40px; gap: .5em .8em;
              align-items: center; }
.comp-bars .sub-label { color: var(--dim); font-family: 'IBM Plex Mono', monospace;
                         font-size: .78em; text-transform: uppercase; letter-spacing: .08em; }
.comp-bars .sub-track { background: var(--stripe); height: 12px; border-radius: 6px;
                         position: relative; overflow: hidden; }
.comp-bars .sub-fill { position: absolute; left: 0; top: 0; bottom: 0;
                        background: var(--accent); border-radius: 6px;
                        transition: width .3s ease; }
.comp-bars .sub-fill.plus  { background: var(--pos); }
.comp-bars .sub-fill.minus { background: var(--neg); }
.comp-bars .sub-track .ref-50 { position: absolute; left: 50%; top: 0; bottom: 0;
                                  border-left: 1px dashed var(--dim); pointer-events: none; }
.comp-bars .sub-val { font-family: 'IBM Plex Mono', monospace; font-size: .9em;
                       text-align: right; color: var(--text); }
.comp-weight { color: var(--dim); font-size: .75em; font-family: 'IBM Plex Mono', monospace; }

/* Domain-cell hover tooltip in all-players table */
.alltable td.domain-cell { position: relative; cursor: help; }
.domain-tooltip { position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
                   background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
                   padding: .55em .8em; font-family: 'IBM Plex Mono', monospace;
                   font-size: .78em; white-space: nowrap; z-index: 50;
                   box-shadow: 0 4px 12px rgba(0,0,0,0.4); display: none;
                   margin-bottom: 5px; }
.alltable td.domain-cell:hover .domain-tooltip { display: block; }
.domain-tooltip .dom-sub { display: flex; justify-content: space-between; gap: 1.2em; }
.domain-tooltip .dom-sub b { color: var(--accent); }
.domain-tooltip .dom-sub .name { color: var(--dim); }
</style>
</head>
"""


BODY_HEADER = """
<div id="loading-overlay">
  <div class="spinner"></div>
  <div class="label">Loading dashboard…</div>
</div>
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
      <p><b>Overall.</b> Empirically-weighted composite of the three
      archetype-driving domains, re-rated within year to a clean 20-80
      distribution. Weights from OLS regression of FP rate on the
      domain ratings, full-season pool: <i>hitters Contact 0.55 / Power 0.40
      / Discipline 0.05 (n=3,163, R²=0.73); SPs Stuff 0.50 / Movement 0.35
      / Control 0.15 (n=1,205, R²=0.74).</i> Year-by-year weights vary by
      ±2-3pp. Overall correlates with realized FP rate at r=0.86 (hitters)
      and r=0.81 (SPs).</p>
      <p><b>Sub-domains.</b> Each domain decomposes into conceptually distinct
      sub-ratings (all 20-80), shown in the per-player modal's Composition tab and the
      "Sub-domain ratings" section at the bottom of each tab.</p>
      <p>Hitters:<br>
      • CONTACT = 0.05 Z-Contact + 0.05 Chase-contact + 0.45 K-avoidance
      + 0.40 Contact quality (xwOBACON) + 0.05 Spray diversity<br>
      • POWER = 0.25 Raw power (HardHit+Barrel+EV90) + 0.10 Launch optimization
      (SweetSpot+PullFB) + 0.65 Damage production (ISO+HR rate)<br>
      • DISCIPLINE = 0.70 Patience + 0.30 Aggression<br>
      • SB = 0.30 Speed tool + 0.70 SB conversion</p>
      <p>SPs:<br>
      • STUFF = 0.65 Swing-and-miss + 0.35 Called-strike<br>
      • MOVEMENT = 0.85 Damage suppression + 0.15 GB tendency<br>
      • CONTROL = 0.90 Walk avoidance + 0.10 Strike-throwing (zone%)</p>

      <p><b>Trajectory.</b> Each player-year gets a 3-year OVERALL slope (linear-regression slope across their last 3 seasons) and a career-percentile rank (where this OVERALL sits in their own historical distribution). Flags: <i>Trending up</i> (slope ≥ +3 per year), <i>Trending down</i> (slope ≤ -3), <i>Career high</i> (≥ 90th career percentile), <i>Career low</i> (≤ 10th). Shown as a chip in the modal hero.</p>

      <p><b>T+1 FP projection.</b> Each player-year's predicted FP rate for NEXT season, computed from a linear model regressing next-year FP on current-year sub-domain ratings + age. Trained on FULL-tier seasons 2015-2025. R² = 0.29 hitters / 0.33 SPs — explains about a third of next-year FP variance, which is typical for predictive baseball models. Top T+1 predictive features: RAW_POWER, K_AVOIDANCE, age (hitters); SWING_MISS, age, velo (SPs). Notable: xwOBACON (CONTACT_QUALITY) has near-zero T+1 weight despite dominating current-year FP — confirms it's a noisy single-year signal.</p>

      <p><b>Sub-domain comps.</b> Each player's modal includes a "Comps" tab listing the 5 historical seasons closest by Euclidean distance over the 12-dimensional sub-domain space (5 for SPs). Click any comp to drill into that player's career.</p>
      <p>Sub-domain weights derived from OLS regression of FP rate on sub-domain
      ratings, FULL-tier pool only. Z-contact and O-contact are kept primarily
      for diagnostic distinction even though their predictive weight is small —
      they let you see whether a hitter's contact comes from elite swing path
      (Z) vs salvaging bad swings (O).</p>
      <p><b>BABIP luck context.</b> BABIP year-to-year stability is r=0.39
      (mostly noise). Each batter-year's BABIP is compared to that batter's
      career mean; deltas ≥ +0.030 trigger a "Hot" flag (running hot, outcomes
      outpacing skill) and ≤ -0.030 trigger "Cold" (likely unlucky, buy-low).
      Shown as a chip in the per-player modal hero.</p>
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
  <nav id="h-toc" class="toc-strip">
    <a href="#h-section-snapshots">Snapshot movers</a>
    <a href="#h-section-quadrant">Quadrant</a>
    <a href="#h-section-roster">Roster</a>
    <a href="#h-section-all">All hitters</a>
    <a href="#h-section-subs">Sub-domains</a>
  </nav>
  <section id="h-section-snapshots">
  <div id="h-snapshots-section" style="display:none;">
    <h2>Season progression — snapshot movers</h2>
    <div class="quad-controls" style="margin-bottom:.4em;">
      <label>At date</label>
      <select id="h-snap-at"></select>
      <label>Compared to</label>
      <select id="h-snap-vs"></select>
      <label>Sort by</label>
      <select id="h-snap-sort">
        <option value="net">Net |ΔC|+|ΔP|+|ΔD|</option>
        <option value="C">ΔC (Contact)</option>
        <option value="P">ΔP (Power)</option>
        <option value="D">ΔD (Discipline)</option>
      </select>
      <span id="h-snap-note" class="filter-summary"></span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5em;">
      <div><h3 style="color:var(--pos);">Risers</h3><div id="h-snap-up"></div></div>
      <div><h3 style="color:var(--neg);">Fallers</h3><div id="h-snap-down"></div></div>
    </div>
  </div>
  </section>

  <section id="h-section-quadrant">
  <h2>Hitter custom quadrant</h2>
  <div class="quad-controls">
    <label>X axis</label>
    <select id="h-x">
      <option value="OVERALL">Overall</option>
      <option value="CONTACT">Contact</option>
      <option value="POWER" selected>Power</option>
      <option value="DISCIPLINE">Discipline</option>
      <option value="SB">SB</option>
    </select>
    <label>Y axis</label>
    <select id="h-y">
      <option value="OVERALL">Overall</option>
      <option value="CONTACT" selected>Contact</option>
      <option value="POWER">Power</option>
      <option value="DISCIPLINE">Discipline</option>
      <option value="SB">SB</option>
    </select>
    <span class="r-display" id="h-r"></span>
  </div>
  <div class="quadrant-host"><div id="h-quad" style="height: 540px;"></div></div>
  </section>

  <section id="h-section-roster">
  <h2>Hitter archetype roster</h2>
  <div id="h-archetype-tables"></div>
  </section>

  <section id="h-section-all">
  <h2>All hitters — sortable</h2>
  <div class="alltable-controls">
    <input type="text" id="h-alltable-search" placeholder="Search name, team, archetype, sub-type…" autocomplete="off">
    <span id="h-alltable-count" class="filter-summary"></span>
  </div>
  <div class="table-scroll"><table id="h-alltable" class="alltable"></table></div>
  </section>

  <section id="h-section-subs">
  <h2>Sub-domain ratings — all hitters</h2>
  <p style="color:var(--dim);font-size:.85em;font-family:'IBM Plex Mono',monospace;margin-bottom:.4em;">Each domain decomposed into its underlying sub-ratings (20-80 within year). Sort by any column.</p>
  <div class="alltable-controls">
    <input type="text" id="h-subtable-search" placeholder="Search name, team…" autocomplete="off">
    <span id="h-subtable-count" class="filter-summary"></span>
  </div>
  <div class="table-scroll"><table id="h-subtable" class="alltable"></table></div>
  </section>
</div>
"""


PITCHERS_TAB = """
<div id="tab-pitchers" class="tab-panel">
  <nav id="s-toc" class="toc-strip">
    <a href="#s-section-snapshots">Snapshot movers</a>
    <a href="#s-section-quadrant">Quadrant</a>
    <a href="#s-section-roster">Roster</a>
    <a href="#s-section-all">All pitchers</a>
    <a href="#s-section-subs">Sub-domains</a>
  </nav>
  <section id="s-section-snapshots">
  <div id="s-snapshots-section" style="display:none;">
    <h2>Season progression — snapshot movers</h2>
    <div class="quad-controls" style="margin-bottom:.4em;">
      <label>At date</label>
      <select id="s-snap-at"></select>
      <label>Compared to</label>
      <select id="s-snap-vs"></select>
      <label>Sort by</label>
      <select id="s-snap-sort">
        <option value="net">Net |ΔS|+|ΔM|+|ΔC|</option>
        <option value="S">ΔS (Stuff)</option>
        <option value="M">ΔM (Movement)</option>
        <option value="C">ΔC (Control)</option>
        <option value="V">ΔVelo</option>
      </select>
      <span id="s-snap-note" class="filter-summary"></span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5em;">
      <div><h3 style="color:var(--pos);">Risers</h3><div id="s-snap-up"></div></div>
      <div><h3 style="color:var(--neg);">Fallers</h3><div id="s-snap-down"></div></div>
    </div>
  </div>
  </section>

  <section id="s-section-quadrant">
  <h2>Pitcher custom quadrant</h2>
  <div class="quad-controls">
    <label>X axis</label>
    <select id="s-x">
      <option value="OVERALL">Overall</option>
      <option value="STUFF">Stuff</option>
      <option value="MOVEMENT" selected>Movement</option>
      <option value="CONTROL">Control</option>
      <option value="velo_rating">Velo</option>
    </select>
    <label>Y axis</label>
    <select id="s-y">
      <option value="OVERALL">Overall</option>
      <option value="STUFF" selected>Stuff</option>
      <option value="MOVEMENT">Movement</option>
      <option value="CONTROL">Control</option>
      <option value="velo_rating">Velo</option>
    </select>
    <span class="r-display" id="s-r"></span>
  </div>
  <div class="quadrant-host"><div id="s-quad" style="height: 540px;"></div></div>
  </section>

  <section id="s-section-roster">
  <h2>Pitcher archetype roster</h2>
  <div id="s-archetype-tables"></div>
  </section>

  <section id="s-section-all">
  <h2>All pitchers — sortable</h2>
  <div class="alltable-controls">
    <input type="text" id="s-alltable-search" placeholder="Search name, archetype, sub-type, pitch mix…" autocomplete="off">
    <span id="s-alltable-count" class="filter-summary"></span>
  </div>
  <div class="table-scroll"><table id="s-alltable" class="alltable"></table></div>
  </section>

  <section id="s-section-subs">
  <h2>Sub-domain ratings — all pitchers</h2>
  <p style="color:var(--dim);font-size:.85em;font-family:'IBM Plex Mono',monospace;margin-bottom:.4em;">Each domain decomposed into its underlying sub-ratings (20-80 within year). Sort by any column.</p>
  <div class="alltable-controls">
    <input type="text" id="s-subtable-search" placeholder="Search name…" autocomplete="off">
    <span id="s-subtable-count" class="filter-summary"></span>
  </div>
  <div class="table-scroll"><table id="s-subtable" class="alltable"></table></div>
  </section>
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

// Snapshots — indexed by (id, year) for per-player trajectories, and by (year, date) for movers
const HSNAP = D.hitter_snapshots || [];
const SSNAP = D.sp_snapshots     || [];
const HSNAP_BY_PY = {}; HSNAP.forEach(r => { const k = `${r.batter}|${r.year}`; (HSNAP_BY_PY[k] = HSNAP_BY_PY[k] || []).push(r); });
const SSNAP_BY_PY = {}; SSNAP.forEach(r => { const k = `${r.pitcher}|${r.year}`; (SSNAP_BY_PY[k] = SSNAP_BY_PY[k] || []).push(r); });
Object.values(HSNAP_BY_PY).forEach(arr => arr.sort((a,b) => a.date.localeCompare(b.date)));
Object.values(SSNAP_BY_PY).forEach(arr => arr.sort((a,b) => a.date.localeCompare(b.date)));

function snapshotDatesForYear(snaps, year) {
  return [...new Set(snaps.filter(r => r.year === year).map(r => r.date))].sort();
}

// ── Axis labels (display only) ──────────────────────────────────────────
const HITTER_AXIS_LABEL = { OVERALL: 'Overall', CONTACT: 'Contact', POWER: 'Power', DISCIPLINE: 'Discipline', SB: 'SB' };
const SP_AXIS_LABEL     = { OVERALL: 'Overall', STUFF: 'Stuff', MOVEMENT: 'Movement', CONTROL: 'Control', velo_rating: 'Velo' };

// Convert SCREAMING_SNAKE_CASE labels to "Title Case" for display
function prettyLabel(s) {
  if (s == null || s === '') return s;
  return String(s).split('_').map(w =>
    w ? (w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()) : w
  ).join(' ');
}

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
  hSnapAt: null, hSnapVs: null, hSnapSort: 'net',
  sSnapAt: null, sSnapVs: null, sSnapSort: 'net',
  // All-players table state — initial sort by Overall descending
  hTblSort: { col: 'OVERALL', dir: 'desc' },
  sTblSort: { col: 'OVERALL', dir: 'desc' },
  hTblQuery: '',
  sTblQuery: '',
  // Sub-domain table state — also defaults to Overall desc
  hSubSort: { col: 'OVERALL', dir: 'desc' },
  sSubSort: { col: 'OVERALL', dir: 'desc' },
  hSubQuery: '',
  sSubQuery: '',
};

// Inline badge for partial-season players
function partialBadge(r) {
  return r && r.data_tier === 'PARTIAL' ? ' <span class="badge partial">Partial</span>' : '';
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
         + `Overall=${r.OVERALL} · C=${r.CONTACT} P=${r.POWER} D=${r.DISCIPLINE} SB=${r.SB}<br>`
         + `${prettyLabel(r.archetype)} · ${prettyLabel(r.age_tier || '')} · ${prettyLabel(r.boundary_tier)}<br>`
         + `FP/PA = ${(r.fp_per_pa||0).toFixed(3)}`;
  }
  return `<b>${r.player_name}</b> ${r.year}<br>`
       + `Overall=${r.OVERALL} · S=${r.STUFF} M=${r.MOVEMENT} C=${r.CONTROL} velo=${r.velo_rating}<br>`
       + `${prettyLabel(r.archetype)} · ${prettyLabel(r.age_tier || '')} · ${prettyLabel(r.boundary_tier)}<br>`
       + `FP/start = ${(r.fp_per_start||0).toFixed(2)}`;
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
      name: prettyLabel(label),
      legendgroup: cat,
      legendgrouptitle: { text: prettyLabel(cat) },
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
      { x:70, y:75, text:'Plus both', showarrow:false, font:{ color:'#7fb069', size:10, family:'IBM Plex Mono' } },
      { x:30, y:75, text:`+ ${axisLabel[yKey]} only`, showarrow:false, font:{ color:'#d4a945', size:10, family:'IBM Plex Mono' } },
      { x:70, y:25, text:`+ ${axisLabel[xKey]} only`, showarrow:false, font:{ color:'#d4a945', size:10, family:'IBM Plex Mono' } },
      { x:30, y:25, text:'Minus both', showarrow:false, font:{ color:'#c1666b', size:10, family:'IBM Plex Mono' } },
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
      html += `<h3 style="color:var(--dim);font-size:.85em;letter-spacing:.05em;margin-top:1.2em;border-bottom:1px solid var(--faint);padding-bottom:.3em;">${prettyLabel(cat)}</h3>`;
      lastCat = cat;
    }
    rs.sort((a,b) => (b[fpKey]||0) - (a[fpKey]||0));
    const desc = archDesc[arch] || '';
    html += `<details><summary>${prettyLabel(arch)}<span class="count">n=${rs.length}, mean ${fpKey}=${mean.toFixed(role==='hitter'?3:2)}</span><span class="desc">${desc}</span></summary><table><thead>`;
    if (role === 'hitter') {
      html += '<tr><th class="num">#</th><th>Player</th><th>Team</th><th class="num">Overall</th><th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th><th>SB tier</th><th>Age</th><th>Bnd</th><th class="num">FP/PA</th><th class="num">Rank</th></tr></thead><tbody>';
      rs.forEach((r, i) => {
        html += `<tr><td class="num">${i+1}</td>`
              + `<td class="player" data-role="hitter" data-id="${r.batter}">${r.player_name}${partialBadge(r)}</td>`
              + `<td>${r.team||''}</td>`
              + `<td class="num"><b>${r.OVERALL}</b></td>`
              + `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
              + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
              + `<td>${prettyLabel(r.sb_tier||'')}</td><td>${prettyLabel(r.age_tier||'')}</td>`
              + `<td>${prettyLabel(r.boundary_tier||'')}</td>`
              + `<td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`
              + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
      });
    } else {
      html += '<tr><th class="num">#</th><th>Pitcher</th><th class="num">Overall</th><th class="num">S</th><th class="num">M</th><th class="num">C</th><th class="num">Velo</th><th>Velo tier</th><th>Age</th><th>Bnd</th><th class="num">FP/start</th><th class="num">Rank</th></tr></thead><tbody>';
      rs.forEach((r, i) => {
        html += `<tr><td class="num">${i+1}</td>`
              + `<td class="player" data-role="sp" data-id="${r.pitcher}">${r.player_name}${partialBadge(r)}</td>`
              + `<td class="num"><b>${r.OVERALL}</b></td>`
              + `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
              + `<td class="num">${r.CONTROL}</td><td class="num">${r.velo_rating??''}</td>`
              + `<td>${prettyLabel(r.velo_tier||'')}</td><td>${prettyLabel(r.age_tier||'')}</td>`
              + `<td>${prettyLabel(r.boundary_tier||'')}</td>`
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
  let html = '<table><thead><tr><th class="num">#</th><th>Player</th><th class="num">Overall</th><th class="num">T+1</th>';
  if (role === 'hitter') html += '<th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th><th>Archetype</th><th class="num">FP/PA</th>';
  else                    html += '<th class="num">S</th><th class="num">M</th><th class="num">C</th><th>Archetype</th><th class="num">FP/start</th>';
  html += '</tr></thead><tbody>';
  top.forEach((r, i) => {
    const t1 = r.t1_fp_projection;
    html += `<tr><td class="num">${i+1}</td>`
          + `<td class="player" data-role="${role}" data-id="${role==='hitter'?r.batter:r.pitcher}">${r.player_name}${partialBadge(r)}</td>`
          + `<td class="num"><b>${r.OVERALL}</b></td>`
          + `<td class="num">${t1 != null ? t1.toFixed(role === 'hitter' ? 3 : 2) : ''}</td>`;
    if (role === 'hitter') {
      html += `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
            + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
            + `<td>${prettyLabel(r.archetype)}</td><td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`;
    } else {
      html += `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
            + `<td class="num">${r.CONTROL}</td>`
            + `<td>${prettyLabel(r.archetype)}</td><td class="num">${(r.fp_per_start||0).toFixed(2)}</td>`;
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
    name: prettyLabel(label),
    legendgroup: catMap[label] || 'BELOW',
    legendgrouptitle: { text: prettyLabel(catMap[label] || 'BELOW') },
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
      html += `<tr><td>${prettyLabel(t)}</td><td class="num">${v.n_transitions}</td><td class="num">${v.retention_pct}%</td></tr>`;
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

  // Snapshot trajectory (only when Single Year mode + snapshots exist for that year)
  const snapKey = `${id}|${state.singleYear}`;
  const snapRows = role === 'hitter' ? HSNAP_BY_PY[snapKey] : SSNAP_BY_PY[snapKey];
  const hasSnap = state.yearMode === 'single' && snapRows && snapRows.length >= 2;

  // ── Hero block ──
  let hero = `<div class="modal-hero">`;
  hero += `<div><div class="hero-name">${last.player_name}${partialBadge(last)}</div>`;
  hero += `<div class="hero-meta">`;
  if (role === 'hitter') hero += `Latest: ${last.team || '—'} · age ${last.age ?? '?'} (${prettyLabel(last.age_tier)})`;
  else                    hero += `Latest: age ${last.age ?? '?'} (${prettyLabel(last.age_tier)})`;
  hero += `</div></div>`;
  hero += `<div class="hero-stats">`;
  hero += `<div class="hero-archetype">${prettyLabel(last.archetype)}</div>`;
  hero += `<div class="hero-overall"><div class="label">Overall</div><div class="val">${last.OVERALL}</div></div>`;
  const cur = sorted[sorted.length - 1];
  // Trajectory chip
  if (cur.traj_flag && cur.traj_flag !== 'STABLE') {
    const flag = cur.traj_flag;
    const color = flag === 'TRENDING_UP' || flag === 'CAREER_HIGH' ? 'pos'
                : flag === 'TRENDING_DOWN' || flag === 'CAREER_LOW' ? 'neg' : 'dim';
    const label = flag === 'TRENDING_UP'   ? 'Trending up'
                : flag === 'TRENDING_DOWN' ? 'Trending down'
                : flag === 'CAREER_HIGH'   ? 'Career high'
                : flag === 'CAREER_LOW'    ? 'Career low' : 'Stable';
    const slopeStr = cur.OVERALL_slope_3yr != null
      ? `${cur.OVERALL_slope_3yr > 0 ? '+' : ''}${cur.OVERALL_slope_3yr.toFixed(1)}/yr`
      : '';
    const pctStr = cur.OVERALL_career_pct != null
      ? `${Math.round(cur.OVERALL_career_pct * 100)}th pctile`
      : '';
    hero += `<div class="hero-overall" style="border-left:3px solid var(--${color});padding-left:.8em;">`;
    hero += `<div class="label">Trajectory</div>`;
    hero += `<div style="font-family:'IBM Plex Mono',monospace;font-size:.95em;color:var(--text);"><b>${label}</b></div>`;
    if (slopeStr || pctStr) {
      hero += `<div style="font-family:'IBM Plex Mono',monospace;font-size:.78em;color:var(--dim);">${slopeStr}${slopeStr && pctStr ? ' · ' : ''}${pctStr}</div>`;
    }
    hero += `</div>`;
  }
  // T+1 projection chip
  if (cur.t1_fp_projection != null) {
    hero += `<div class="hero-overall" style="border-left:3px solid var(--accent);padding-left:.8em;">`;
    hero += `<div class="label">T+1 projection</div>`;
    hero += `<div class="val" style="font-size:1.5em;">${cur.t1_fp_projection.toFixed(role === 'hitter' ? 3 : 2)}</div>`;
    hero += `<div style="color:var(--dim);font-size:.7em;font-family:'IBM Plex Mono',monospace;">fp/${role === 'hitter' ? 'pa' : 'start'} next yr</div>`;
    hero += `</div>`;
  }
  // BABIP luck context chip (hitters only)
  if (role === 'hitter' && cur.babip_delta != null) {
    const delta = cur.babip_delta;
    const flag = cur.babip_luck_flag;
    const sign = delta > 0 ? '+' : '';
    const label = flag === 'HOT' ? 'Hot' : (flag === 'COLD' ? 'Cold' : 'Normal');
    const borderColor = flag === 'HOT' ? 'neg' : (flag === 'COLD' ? 'warn' : 'dim');
    const textColor   = flag === 'HOT' ? 'neg' : (flag === 'COLD' ? 'warn' : 'dim');
    const babipVal = (cur.babip != null) ? cur.babip : ((cur.babip_career || 0) + (cur.babip_delta || 0));
    hero += `<div class="hero-overall" style="border-left:3px solid var(--${borderColor});padding-left:.8em;">`;
    hero += `<div class="label">BABIP context</div>`;
    hero += `<div style="font-family:'IBM Plex Mono',monospace;font-size:.95em;color:var(--text);"><b>${babipVal.toFixed(3)}</b> <span style="color:var(--dim);">vs career ${(cur.babip_career ?? 0).toFixed(3)}</span></div>`;
    hero += `<div style="font-family:'IBM Plex Mono',monospace;font-size:.85em;color:var(--${textColor});">${sign}${delta.toFixed(3)} · ${label}</div>`;
    hero += `</div>`;
  }
  hero += `</div></div>`;

  // ── Modal tabs ──
  let tabs = '<div class="modal-tabs">';
  tabs += '<button class="active" data-mtab="arc">Career arc</button>';
  tabs += '<button data-mtab="years">Year-by-year</button>';
  tabs += '<button data-mtab="comp">Composition</button>';
  tabs += '<button data-mtab="comps">Comps</button>';
  if (hasSnap) tabs += '<button data-mtab="snap">In-season</button>';
  tabs += '</div>';

  // ── Year table header + rows (shared by years panel) ──
  let yearHeader = '<tr><th class="num">Year</th><th class="num">Age</th><th class="num">Overall</th>';
  if (role === 'hitter') yearHeader += '<th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th><th>Archetype</th><th>Subtypes</th><th>Bnd</th><th class="num">FP/PA</th><th class="num">Rank</th>';
  else                    yearHeader += '<th class="num">S</th><th class="num">M</th><th class="num">C</th><th class="num">Velo</th><th>Archetype</th><th>Subtypes</th><th>Bnd</th><th class="num">FP/start</th><th class="num">Rank</th>';
  yearHeader += '</tr>';

  let yearRows = '';
  sorted.forEach(r => {
    const sub = role === 'hitter'
      ? [r.contact_subtype, r.power_subtype, r.discipline_subtype, r.sb_tier]
      : [r.stuff_subtype, r.velo_tier, r.pitch_archetype];
    const subStr = sub.filter(Boolean).map(prettyLabel).join(' / ');
    if (role === 'hitter') {
      yearRows += `<tr><td class="num">${r.year}${r.data_tier==='PARTIAL'?' <span class="badge partial">P</span>':''}</td><td class="num">${r.age ?? ''}</td>`
            + `<td class="num"><b>${r.OVERALL}</b></td>`
            + `<td class="num">${r.CONTACT}</td><td class="num">${r.POWER}</td>`
            + `<td class="num">${r.DISCIPLINE}</td><td class="num">${r.SB}</td>`
            + `<td>${prettyLabel(r.archetype)}</td>`
            + `<td><span style="color:var(--dim);">${subStr}</span></td>`
            + `<td>${prettyLabel(r.boundary_tier||'')}</td>`
            + `<td class="num">${(r.fp_per_pa||0).toFixed(3)}</td>`
            + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
    } else {
      yearRows += `<tr><td class="num">${r.year}${r.data_tier==='PARTIAL'?' <span class="badge partial">P</span>':''}</td><td class="num">${r.age ?? ''}</td>`
            + `<td class="num"><b>${r.OVERALL}</b></td>`
            + `<td class="num">${r.STUFF}</td><td class="num">${r.MOVEMENT}</td>`
            + `<td class="num">${r.CONTROL}</td><td class="num">${r.velo_rating ?? ''}</td>`
            + `<td>${prettyLabel(r.archetype)}</td>`
            + `<td><span style="color:var(--dim);">${subStr}</span></td>`
            + `<td>${prettyLabel(r.boundary_tier||'')}</td>`
            + `<td class="num">${(r.fp_per_start||0).toFixed(2)}</td>`
            + `<td class="num">${r.rank_in_year ?? ''}</td></tr>`;
    }
  });

  // ── Panels ──
  let panels = '<div class="modal-mtab-panel active" data-mtab="arc">';
  panels += '<div class="traj">' + sorted.map(r => `<span>${r.year}: <b>${prettyLabel(r.archetype)}</b></span>`).join('<span class="arrow">→</span>') + '</div>';
  panels += '<div id="modal-spark" style="height: 320px; margin-top: 1em;"></div>';
  panels += '</div>';

  panels += '<div class="modal-mtab-panel" data-mtab="years">';
  panels += '<div class="table-scroll"><table><thead>' + yearHeader + '</thead><tbody>' + yearRows + '</tbody></table></div>';
  panels += '</div>';

  // ── Composition panel — sub-domain breakdown for the most recent year ──
  const SUB_W_H = {
    CONTACT:    [['Z_CONTACT', 0.05, 'In-zone contact'],
                  ['O_CONTACT', 0.05, 'Chase contact'],
                  ['K_AVOIDANCE', 0.45, 'K avoidance'],
                  ['CONTACT_QUALITY', 0.40, 'Contact quality (xwOBACON)'],
                  ['SPRAY_PROFILE', 0.05, 'Spray diversity']],
    POWER:      [['RAW_POWER', 0.25, 'Raw power tools (HardHit+Barrel+EV90)'],
                  ['LAUNCH_OPTIM', 0.10, 'Launch optimization (SweetSpot+PullFB)'],
                  ['DAMAGE_PROD', 0.65, 'Damage production (ISO+HR rate)']],
    DISCIPLINE: [['PATIENCE', 0.70, 'Patience (BB+chase+HBP)'],
                  ['AGGRESSION', 0.30, 'Aggression in zone']],
    SB:         [['SPEED_TOOL', 0.30, 'Speed tool'],
                  ['SB_CONVERSION', 0.70, 'SB conversion']],
  };
  const SUB_W_S = {
    STUFF:    [['SWING_MISS', 0.65, 'Swing-and-miss'], ['CALLED_STRIKE', 0.35, 'Called strike']],
    MOVEMENT: [['DAMAGE_SUPP', 0.85, 'Damage suppression'], ['GB_TENDENCY', 0.15, 'GB tendency']],
    CONTROL:  [['WALK_AVOID', 0.90, 'Walk avoidance'],
                ['STRIKE_THROWING', 0.10, 'Strike-throwing (zone%)']],
  };

  let comp = `<div class="composition"><div style="color:var(--dim);font-size:.8em;font-family:'IBM Plex Mono',monospace;margin-bottom:.4em;">Composition for ${cur.year}${cur.data_tier === 'PARTIAL' ? ' (PARTIAL season)' : ''}</div>`;

  const subMap = role === 'hitter' ? SUB_W_H : SUB_W_S;
  const domainMap = role === 'hitter'
    ? { CONTACT: 'Contact', POWER: 'Power', DISCIPLINE: 'Discipline', SB: 'SB (overlay)' }
    : { STUFF: 'Stuff', MOVEMENT: 'Movement', CONTROL: 'Control' };

  Object.entries(domainMap).forEach(([dom, label]) => {
    const subs = subMap[dom] || [];
    const domVal = cur[dom];
    comp += `<div class="comp-domain"><h4>${label}<span class="domain-rating">domain rating <b>${domVal}</b></span></h4>`;
    comp += '<div class="comp-bars">';
    subs.forEach(([key, weight, name]) => {
      const v = cur[key];
      if (v == null) return;
      const pctWidth = Math.max(0, Math.min(100, (v - 20) / 60 * 100));
      const cls = v >= 60 ? 'plus' : (v < 40 ? 'minus' : '');
      comp += `<div class="sub-label">${name}</div>`;
      comp += `<div class="sub-track"><div class="ref-50"></div><div class="sub-fill ${cls}" style="width:${pctWidth}%;"></div></div>`;
      comp += `<div class="sub-val">${v} <span class="comp-weight">x${weight.toFixed(2)}</span></div>`;
    });
    comp += '</div></div>';
  });
  comp += '</div>';

  panels += '<div class="modal-mtab-panel" data-mtab="comp">' + comp + '</div>';

  // Comps panel — find 5 nearest historical seasons by sub-domain Euclidean distance
  panels += '<div class="modal-mtab-panel" data-mtab="comps">';
  panels += `<h3 style="color:var(--accent);">Most similar historical seasons (sub-domain distance)</h3>`;
  panels += '<div style="color:var(--dim);font-size:.82em;font-family:\'IBM Plex Mono\',monospace;margin-bottom:.4em;">';
  panels += 'Top 5 player-years closest to ' + cur.player_name + ' ' + cur.year + ' by Euclidean distance over the 12 sub-domain ratings.';
  panels += '</div>';
  panels += '<div class="table-scroll"><table id="modal-comps-table"></table></div>';
  panels += '</div>';

  if (hasSnap) {
    panels += '<div class="modal-mtab-panel" data-mtab="snap">';
    panels += `<h3 style="color:var(--accent);">In-season trajectory · ${state.singleYear}</h3>`;
    panels += '<div id="modal-snap" style="height: 320px;"></div>';
    panels += '</div>';
  }

  document.getElementById('modal-content').innerHTML = hero + tabs + panels;
  document.getElementById('modal-bg').classList.add('open');
  renderModalComps(cur, role);

  // Wire modal-tab click handler
  document.querySelectorAll('.modal-tabs button').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.modal-tabs button').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.modal-mtab-panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      document.querySelector(`.modal-mtab-panel[data-mtab="${b.dataset.mtab}"]`).classList.add('active');
      // Plotly needs resize when its tab becomes visible
      if (b.dataset.mtab === 'arc' && document.getElementById('modal-spark')) Plotly.Plots.resize('modal-spark');
      if (b.dataset.mtab === 'snap' && document.getElementById('modal-snap')) Plotly.Plots.resize('modal-snap');
    });
  });

  renderSparkline(sorted, role);
  if (hasSnap) renderSnapshotTrajectory(snapRows, role);
}

function renderSnapshotTrajectory(rows, role) {
  const xs = rows.map(r => r.date);
  const keys = role === 'hitter'
    ? [['CONTACT','#7fb069'], ['POWER','#c1666b'], ['DISCIPLINE','#b099d4'], ['SB','#d97757']]
    : [['STUFF','#c1666b'], ['MOVEMENT','#7fb069'], ['CONTROL','#b099d4'], ['velo_rating','#d97757']];
  const traces = keys.map(([k, color]) => ({
    x: xs, y: rows.map(r => r[k]), mode: 'lines+markers', name: k,
    line: { color, width: 2 }, marker: { size: 8 },
  }));
  const shapes = [
    { type:'line', xref:'paper', x0:0, x1:1, y0:60, y1:60, line:{ color:'#7fb069', dash:'dot', width:1 } },
    { type:'line', xref:'paper', x0:0, x1:1, y0:50, y1:50, line:{ color:'#8d8579', dash:'dot', width:1 } },
    { type:'line', xref:'paper', x0:0, x1:1, y0:40, y1:40, line:{ color:'#c1666b', dash:'dot', width:1 } },
  ];
  Plotly.react('modal-snap', traces, {
    paper_bgcolor: '#1a1815', plot_bgcolor: '#211e1a',
    font: { color: '#f5f1ea', family: 'IBM Plex Mono, monospace', size: 11 },
    margin: { l: 50, r: 10, t: 10, b: 50 },
    xaxis: { gridcolor: '#34302a', type: 'category' },
    yaxis: { gridcolor: '#34302a', range: [20, 80], tick0: 20, dtick: 10 },
    shapes,
    legend: { orientation: 'h', y: -0.15, font: { size: 10, family: 'IBM Plex Mono' } },
  }, { displayModeBar: false, responsive: true });
}

function closeModal() { document.getElementById('modal-bg').classList.remove('open'); }

function findSubDomainComps(focal, role, k) {
  k = k || 5;
  const SUB_KEYS_H = ['Z_CONTACT','O_CONTACT','K_AVOIDANCE','CONTACT_QUALITY','SPRAY_PROFILE',
                       'RAW_POWER','LAUNCH_OPTIM','DAMAGE_PROD',
                       'PATIENCE','AGGRESSION','SPEED_TOOL','SB_CONVERSION'];
  const SUB_KEYS_S = ['SWING_MISS','CALLED_STRIKE','DAMAGE_SUPP','GB_TENDENCY','WALK_AVOID','STRIKE_THROWING'];
  const keys = role === 'hitter' ? SUB_KEYS_H : SUB_KEYS_S;
  const pool = role === 'hitter' ? HITTERS : SPS;
  const idKey = role === 'hitter' ? 'batter' : 'pitcher';
  const focalId = focal[idKey];
  const focalYr = focal.year;
  // Filter: same role, different (player, year) than focal
  const candidates = pool.filter(r => !(r[idKey] === focalId && r.year === focalYr));
  // Compute squared euclidean distance
  candidates.forEach(c => {
    let d = 0;
    for (let i = 0; i < keys.length; i++) {
      const a = focal[keys[i]], b = c[keys[i]];
      if (a == null || b == null) continue;
      d += (a - b) * (a - b);
    }
    c._dist = Math.sqrt(d);
  });
  candidates.sort((a, b) => a._dist - b._dist);
  return candidates.slice(0, k);
}

function renderModalComps(focal, role) {
  const comps = findSubDomainComps(focal, role, 5);
  const tbl = document.getElementById('modal-comps-table');
  if (!tbl) return;
  let html = '<thead><tr><th class="num">#</th><th>Player</th><th class="num">Yr</th><th class="num">Overall</th>';
  if (role === 'hitter') html += '<th class="num">C</th><th class="num">P</th><th class="num">D</th><th class="num">SB</th>';
  else                    html += '<th class="num">S</th><th class="num">M</th><th class="num">C</th>';
  html += '<th class="num">Dist</th><th class="num">FP/' + (role === 'hitter' ? 'PA' : 'start') + '</th></tr></thead><tbody>';
  comps.forEach((c, i) => {
    html += `<tr><td class="num">${i+1}</td>`;
    html += `<td class="player" data-role="${role}" data-id="${c[role === 'hitter' ? 'batter' : 'pitcher']}">${c.player_name}</td>`;
    html += `<td class="num">${c.year}</td>`;
    html += `<td class="num"><b>${c.OVERALL}</b></td>`;
    if (role === 'hitter') {
      html += `<td class="num">${c.CONTACT}</td><td class="num">${c.POWER}</td>`;
      html += `<td class="num">${c.DISCIPLINE}</td><td class="num">${c.SB}</td>`;
    } else {
      html += `<td class="num">${c.STUFF}</td><td class="num">${c.MOVEMENT}</td><td class="num">${c.CONTROL}</td>`;
    }
    const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
    html += `<td class="num">${c._dist.toFixed(1)}</td>`;
    html += `<td class="num">${(c[fpKey] || 0).toFixed(role === 'hitter' ? 3 : 2)}</td></tr>`;
  });
  html += '</tbody>';
  tbl.innerHTML = html;
  // Wire player clicks
  tbl.querySelectorAll('td.player').forEach(td => {
    td.addEventListener('click', () => openModal(td.dataset.role, parseInt(td.dataset.id)));
  });
}

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

// ── All-players sortable table ────────────────────────────────────
// Column definitions: { key, label, num (right-align + numeric sort), w (optional width) }
// `pretty: true` means the cell's text value should pass through prettyLabel().
const H_TBL_COLS = [
  { key: 'player_name', label: 'Player', text: true },
  { key: 'team',        label: 'Tm', text: true },
  { key: 'year',        label: 'Yr',  num: true },
  { key: 'pa',          label: 'PA',  num: true },
  { key: 'fp_per_pa',   label: 'FP/PA', num: true, fmt: v => (v == null ? '' : v.toFixed(3)) },
  { key: 'OVERALL',     label: 'Overall', num: true, bold: true },
  { key: 'CONTACT',     label: 'C',   num: true },
  { key: 'POWER',       label: 'P',   num: true },
  { key: 'DISCIPLINE',  label: 'D',   num: true },
  { key: 'SB',          label: 'SB',  num: true },
  { key: 'archetype',           label: 'Archetype', text: true, pretty: true },
  { key: 'contact_subtype',     label: 'Contact sub', text: true, pretty: true },
  { key: 'power_subtype',       label: 'Power sub',   text: true, pretty: true },
  { key: 'discipline_subtype',  label: 'Disc sub',    text: true, pretty: true },
  { key: 'sb_tier',             label: 'SB tier', text: true, pretty: true },
  { key: 'spray_archetype',     label: 'Spray',   text: true, pretty: true },
  { key: 'age',                 label: 'Age', num: true },
  { key: 'age_tier',            label: 'Age tier', text: true, pretty: true },
  { key: 'boundary_tier',       label: 'Bnd', text: true, pretty: true },
  { key: 'data_tier',           label: 'Tier', text: true, pretty: true },
  { key: 'rank_in_year',        label: 'Rank', num: true },
];

const S_TBL_COLS = [
  { key: 'player_name', label: 'Pitcher', text: true },
  { key: 'year',        label: 'Yr',  num: true },
  { key: 'gs',          label: 'GS',  num: true },
  { key: 'tbf',         label: 'TBF', num: true },
  { key: 'fp_per_start', label: 'FP/start', num: true, fmt: v => (v == null ? '' : v.toFixed(2)) },
  { key: 'OVERALL',     label: 'Overall', num: true, bold: true },
  { key: 'STUFF',       label: 'S',   num: true },
  { key: 'MOVEMENT',    label: 'M',   num: true },
  { key: 'CONTROL',     label: 'C',   num: true },
  { key: 'velo_rating', label: 'Velo', num: true },
  { key: 'archetype',           label: 'Archetype', text: true, pretty: true },
  { key: 'stuff_subtype',       label: 'Stuff sub', text: true, pretty: true },
  { key: 'velo_tier',           label: 'Velo tier', text: true, pretty: true },
  { key: 'pitch_archetype',     label: 'Pitch arch', text: true, pretty: true },
  { key: 'primary_group',       label: 'Primary', text: true, pretty: true },
  { key: 'age',                 label: 'Age', num: true },
  { key: 'age_tier',            label: 'Age tier', text: true, pretty: true },
  { key: 'boundary_tier',       label: 'Bnd', text: true, pretty: true },
  { key: 'data_tier',           label: 'Tier', text: true, pretty: true },
  { key: 'rank_in_year',        label: 'Rank', num: true },
];

// Sub-domain tables — focused on the intermediate-layer ratings.
const H_SUB_COLS = [
  { key: 'player_name', label: 'Player', text: true },
  { key: 'team',        label: 'Tm', text: true },
  { key: 'year',        label: 'Yr', num: true },
  { key: 'OVERALL',     label: 'Overall', num: true, bold: true },
  { key: 'CONTACT',         label: 'Contact', num: true, bold: true },
  { key: 'Z_CONTACT',       label: 'Z-Cont', num: true },
  { key: 'O_CONTACT',       label: 'O-Cont', num: true },
  { key: 'K_AVOIDANCE',     label: 'K-Avoid', num: true },
  { key: 'CONTACT_QUALITY', label: 'Quality', num: true },
  { key: 'SPRAY_PROFILE',   label: 'Spray',   num: true },
  { key: 'POWER',           label: 'Power',   num: true, bold: true },
  { key: 'RAW_POWER',       label: 'Raw',     num: true },
  { key: 'LAUNCH_OPTIM',    label: 'Launch',  num: true },
  { key: 'DAMAGE_PROD',     label: 'Prod',    num: true },
  { key: 'DISCIPLINE',      label: 'Disc',    num: true, bold: true },
  { key: 'PATIENCE',        label: 'Patience',num: true },
  { key: 'AGGRESSION',      label: 'Aggr',    num: true },
  { key: 'SB',              label: 'SB',      num: true, bold: true },
  { key: 'SPEED_TOOL',      label: 'Speed',   num: true },
  { key: 'SB_CONVERSION',   label: 'Conv',    num: true },
  { key: 'babip_luck_flag', label: 'BABIP',   text: true, pretty: true },
  { key: 'age_tier',        label: 'Age',     text: true, pretty: true },
  { key: 'data_tier',       label: 'Tier',    text: true, pretty: true },
];

const S_SUB_COLS = [
  { key: 'player_name', label: 'Pitcher', text: true },
  { key: 'year',        label: 'Yr', num: true },
  { key: 'OVERALL',     label: 'Overall', num: true, bold: true },
  { key: 'STUFF',         label: 'Stuff',  num: true, bold: true },
  { key: 'SWING_MISS',    label: 'SwM',    num: true },
  { key: 'CALLED_STRIKE', label: 'Called', num: true },
  { key: 'MOVEMENT',      label: 'Move',   num: true, bold: true },
  { key: 'DAMAGE_SUPP',   label: 'Suppr',  num: true },
  { key: 'GB_TENDENCY',   label: 'GB',     num: true },
  { key: 'CONTROL',       label: 'Control',num: true, bold: true },
  { key: 'WALK_AVOID',    label: 'BB-avoid',num: true },
  { key: 'STRIKE_THROWING', label: 'Strikes', num: true },
  { key: 'velo_rating',   label: 'Velo',   num: true },
  { key: 'age_tier',      label: 'Age',    text: true, pretty: true },
  { key: 'data_tier',     label: 'Tier',   text: true, pretty: true },
];

function tblRowMatches(r, q) {
  if (!q) return true;
  const ql = q.toLowerCase();
  // Search across text-ish fields
  const candidates = [r.player_name, r.team, r.archetype, r.contact_subtype, r.power_subtype,
                       r.discipline_subtype, r.sb_tier, r.spray_archetype, r.age_tier,
                       r.boundary_tier, r.data_tier, r.stuff_subtype, r.velo_tier,
                       r.pitch_archetype, r.primary_group];
  for (const c of candidates) {
    if (c && String(c).toLowerCase().includes(ql)) return true;
  }
  return false;
}

function tblSortRows(rows, sort, cols) {
  const col = cols.find(c => c.key === sort.col);
  if (!col) return rows;
  const dir = sort.dir === 'asc' ? 1 : -1;
  const numeric = !!col.num;
  return rows.slice().sort((a, b) => {
    let va = a[col.key], vb = b[col.key];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;        // nulls last
    if (vb == null) return -1;
    if (numeric) {
      va = +va; vb = +vb;
      return dir * (va - vb);
    }
    return dir * String(va).localeCompare(String(vb));
  });
}

function renderAllTable(rows, role, kind) {
  const isSub = kind === 'sub';
  const cols = role === 'hitter'
    ? (isSub ? H_SUB_COLS : H_TBL_COLS)
    : (isSub ? S_SUB_COLS : S_TBL_COLS);
  const tblId = role === 'hitter'
    ? (isSub ? 'h-subtable' : 'h-alltable')
    : (isSub ? 's-subtable' : 's-alltable');
  const sort = isSub
    ? (role === 'hitter' ? state.hSubSort : state.sSubSort)
    : (role === 'hitter' ? state.hTblSort : state.sTblSort);
  const q = isSub
    ? (role === 'hitter' ? state.hSubQuery : state.sSubQuery)
    : (role === 'hitter' ? state.hTblQuery : state.sTblQuery);
  const cntEl = document.getElementById(
    role === 'hitter'
      ? (isSub ? 'h-subtable-count' : 'h-alltable-count')
      : (isSub ? 's-subtable-count' : 's-alltable-count'));
  const idKey = role === 'hitter' ? 'batter' : 'pitcher';

  // Domain → sub-domain map for hover tooltips on the per-domain cells
  const DOMAIN_SUBS = role === 'hitter'
    ? {
        CONTACT:    [['Z_CONTACT', 'Z-contact'],
                      ['O_CONTACT', 'Chase-contact'],
                      ['K_AVOIDANCE', 'K-avoid'],
                      ['CONTACT_QUALITY', 'Quality'],
                      ['SPRAY_PROFILE', 'Spray']],
        POWER:      [['RAW_POWER', 'Raw'], ['LAUNCH_OPTIM', 'Launch'], ['DAMAGE_PROD', 'Production']],
        DISCIPLINE: [['PATIENCE', 'Patience'], ['AGGRESSION', 'Aggression']],
        SB:         [['SPEED_TOOL', 'Speed'], ['SB_CONVERSION', 'Conversion']],
      }
    : {
        STUFF:    [['SWING_MISS', 'SwM'], ['CALLED_STRIKE', 'Called']],
        MOVEMENT: [['DAMAGE_SUPP', 'Suppr'], ['GB_TENDENCY', 'GB']],
        CONTROL:  [['WALK_AVOID', 'BB-avoid'], ['STRIKE_THROWING', 'Strikes']],
      };

  const filtered = rows.filter(r => tblRowMatches(r, q));
  const sorted   = tblSortRows(filtered, sort, cols);

  cntEl.textContent = q
    ? `${filtered.length} of ${rows.length} match "${q}"`
    : `${rows.length} rows`;

  // Build header
  let h = '<thead><tr>';
  h += '<th class="num">#</th>';
  cols.forEach(c => {
    const cls = (c.num ? 'num ' : '') + (sort.col === c.key ? `sort-${sort.dir}` : '');
    h += `<th class="${cls.trim()}" data-col="${c.key}">${c.label}</th>`;
  });
  h += '</tr></thead><tbody>';

  // Cap at 800 rows to keep render snappy; show note if truncated
  const cap = 800;
  const visible = sorted.slice(0, cap);
  visible.forEach((r, i) => {
    h += '<tr>';
    h += `<td class="num">${i+1}</td>`;
    cols.forEach(c => {
      let v = r[c.key];
      if (c.fmt) v = c.fmt(v);
      else if (c.pretty) v = (v == null ? '' : prettyLabel(v));
      else if (v == null) v = '';
      const cellCls = (c.num ? 'num' : '') + (c.key === 'player_name' ? ' player' : '');
      const tier = r.data_tier === 'PARTIAL' && c.key === 'player_name' ? partialBadge(r) : '';
      const display = c.bold ? `<b>${v}</b>` : v;
      if (c.key === 'player_name') {
        h += `<td class="${cellCls.trim()}" data-role="${role}" data-id="${r[idKey]}">${display}${tier}</td>`;
        return;
      }
      if (DOMAIN_SUBS[c.key]) {
        const subs = DOMAIN_SUBS[c.key];
        let tip = '<div class="domain-tooltip">';
        subs.forEach(([k, name]) => {
          if (r[k] == null) return;
          tip += `<div class="dom-sub"><span class="name">${name}</span><b>${r[k]}</b></div>`;
        });
        tip += '</div>';
        h += `<td class="${cellCls.trim()} domain-cell">${display}${tip}</td>`;
        return;
      }
      h += `<td class="${cellCls.trim()}">${display}</td>`;
    });
    h += '</tr>';
  });
  h += '</tbody>';
  if (sorted.length > cap) {
    h += `<tfoot><tr><td colspan="${cols.length + 1}" style="text-align:center;color:var(--dim);padding:.6em;">Showing first ${cap} of ${sorted.length} matches — refine search to see the rest.</td></tr></tfoot>`;
  }
  const tbl = document.getElementById(tblId);
  tbl.innerHTML = h;

  // Wire header click → sort
  tbl.querySelectorAll('thead th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.col;
      if (sort.col === k) sort.dir = (sort.dir === 'asc' ? 'desc' : 'asc');
      else { sort.col = k; sort.dir = 'desc'; }
      renderAllTable(rows, role, kind);
    });
  });
  // Wire player click → modal
  tbl.querySelectorAll('td.player').forEach(td => {
    td.addEventListener('click', () => openModal(td.dataset.role, parseInt(td.dataset.id)));
  });
}

// ── Snapshot section (Single Year mode only) ──────────────────────
function populateSnapshotPickers(role) {
  const snaps = role === 'hitter' ? HSNAP : SSNAP;
  const dates = snapshotDatesForYear(snaps, state.singleYear);
  const sec   = document.getElementById(role === 'hitter' ? 'h-snapshots-section' : 's-snapshots-section');
  const note  = document.getElementById(role === 'hitter' ? 'h-snap-note' : 's-snap-note');
  if (!dates.length) {
    sec.style.display = 'none';
    return false;
  }
  sec.style.display = state.yearMode === 'single' ? '' : 'none';
  const selAt = document.getElementById(role === 'hitter' ? 'h-snap-at' : 's-snap-at');
  const selVs = document.getElementById(role === 'hitter' ? 'h-snap-vs' : 's-snap-vs');
  selAt.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join('');
  selVs.innerHTML = dates.map(d => `<option value="${d}">${d}</option>`).join('');
  selAt.value = dates[dates.length - 1];
  selVs.value = dates[Math.max(0, dates.length - 2)];
  if (role === 'hitter') {
    state.hSnapAt = selAt.value; state.hSnapVs = selVs.value;
    note.textContent = `${dates.length} snapshot${dates.length>1?'s':''} for ${state.singleYear}`;
  } else {
    state.sSnapAt = selAt.value; state.sSnapVs = selVs.value;
    note.textContent = `${dates.length} snapshot${dates.length>1?'s':''} for ${state.singleYear}`;
  }
  return true;
}

function renderSnapshotMovers(role) {
  const snaps = role === 'hitter' ? HSNAP : SSNAP;
  const at = role === 'hitter' ? state.hSnapAt : state.sSnapAt;
  const vs = role === 'hitter' ? state.hSnapVs : state.sSnapVs;
  const sort = role === 'hitter' ? state.hSnapSort : state.sSnapSort;
  const upDiv   = document.getElementById(role === 'hitter' ? 'h-snap-up' : 's-snap-up');
  const downDiv = document.getElementById(role === 'hitter' ? 'h-snap-down' : 's-snap-down');
  if (!at || !vs) { upDiv.innerHTML = downDiv.innerHTML = ''; return; }

  const yr = state.singleYear;
  const atRows = snaps.filter(r => r.year === yr && r.date === at);
  const vsRows = snaps.filter(r => r.year === yr && r.date === vs);
  const idKey = role === 'hitter' ? 'batter' : 'pitcher';
  const vsByID = {};
  vsRows.forEach(r => { vsByID[r[idKey]] = r; });

  const dims = role === 'hitter' ? ['CONTACT','POWER','DISCIPLINE'] : ['STUFF','MOVEMENT','CONTROL'];
  const dimAlias = role === 'hitter' ? { C:'CONTACT', P:'POWER', D:'DISCIPLINE' }
                                      : { S:'STUFF', M:'MOVEMENT', C:'CONTROL', V:'velo_rating' };
  const movers = [];
  atRows.forEach(at_r => {
    const vs_r = vsByID[at_r[idKey]];
    if (!vs_r) return;
    const deltas = {};
    dims.forEach(k => { deltas[k] = at_r[k] - vs_r[k]; });
    let primary;
    if (sort === 'net') {
      primary = dims.reduce((s,k) => s + Math.abs(deltas[k]), 0);
    } else {
      const key = dimAlias[sort] || dims[0];
      primary = deltas[key];
    }
    movers.push({ at: at_r, vs: vs_r, deltas, primary });
  });

  const fpKey = role === 'hitter' ? 'fp_per_pa' : 'fp_per_start';
  const rateAtVal = at_r => null; // snapshot rows don't carry fp/pa; skip rate display

  const buildTable = (rows, descending) => {
    rows = rows.slice().sort((a,b) => descending ? b.primary - a.primary : a.primary - b.primary);
    rows = sort === 'net' ? rows : rows.slice(0, 15);
    rows = sort === 'net' ? rows.slice(0, 15) : rows;
    let h = '<table><thead><tr><th class="num">#</th><th>Player</th>';
    if (role === 'hitter') h += '<th class="num">ΔC</th><th class="num">ΔP</th><th class="num">ΔD</th><th class="num">C now</th><th class="num">P now</th><th class="num">D now</th>';
    else                    h += '<th class="num">ΔS</th><th class="num">ΔM</th><th class="num">ΔC</th><th class="num">S now</th><th class="num">M now</th><th class="num">C now</th>';
    h += '</tr></thead><tbody>';
    rows.forEach((m, i) => {
      const r = m.at;
      const id = role === 'hitter' ? r.batter : r.pitcher;
      const fmtD = v => (v > 0 ? '+' : '') + v;
      const cls = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : 'dim');
      const k1 = role === 'hitter' ? 'CONTACT'    : 'STUFF';
      const k2 = role === 'hitter' ? 'POWER'      : 'MOVEMENT';
      const k3 = role === 'hitter' ? 'DISCIPLINE' : 'CONTROL';
      h += `<tr><td class="num">${i+1}</td>`
         + `<td class="player" data-role="${role}" data-id="${id}">${r.player_name}</td>`
         + `<td class="num" style="color:var(--${cls(m.deltas[k1])})">${fmtD(m.deltas[k1])}</td>`
         + `<td class="num" style="color:var(--${cls(m.deltas[k2])})">${fmtD(m.deltas[k2])}</td>`
         + `<td class="num" style="color:var(--${cls(m.deltas[k3])})">${fmtD(m.deltas[k3])}</td>`
         + `<td class="num">${r[k1]}</td><td class="num">${r[k2]}</td><td class="num">${r[k3]}</td>`
         + `</tr>`;
    });
    h += '</tbody></table>';
    return h;
  };

  upDiv.innerHTML   = buildTable(movers, true);
  downDiv.innerHTML = buildTable(movers, false);
  // Wire player clicks
  [upDiv, downDiv].forEach(div => {
    div.querySelectorAll('td.player').forEach(td => {
      td.addEventListener('click', () => openModal(td.dataset.role, parseInt(td.dataset.id)));
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

  renderAllTable(hitterRows, 'hitter');
  renderAllTable(spRows,     'sp');
  renderAllTable(hitterRows, 'hitter', 'sub');
  renderAllTable(spRows,     'sp',     'sub');

  // Snapshot movers — only in Single Year mode
  if (state.yearMode === 'single') {
    if (populateSnapshotPickers('hitter')) renderSnapshotMovers('hitter');
    if (populateSnapshotPickers('sp'))     renderSnapshotMovers('sp');
  } else {
    document.getElementById('h-snapshots-section').style.display = 'none';
    document.getElementById('s-snapshots-section').style.display = 'none';
  }

  encodeStateToHash();
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

// ── URL state persistence ──────────────────────────────────────────
function encodeStateToHash() {
  const parts = [];
  parts.push(`mode=${state.yearMode}`);
  parts.push(`year=${state.singleYear}`);
  parts.push(`partial=${state.includePartial ? '1' : '0'}`);
  parts.push(`tab=${state.tab}`);
  parts.push(`hx=${state.hX}`); parts.push(`hy=${state.hY}`);
  parts.push(`sx=${state.sX}`); parts.push(`sy=${state.sY}`);
  history.replaceState(null, '', '#' + parts.join('&'));
}

function loadStateFromHash() {
  const h = window.location.hash.replace(/^#/, '');
  if (!h) return;
  const map = {};
  h.split('&').forEach(p => { const [k, v] = p.split('='); if (k && v != null) map[k] = decodeURIComponent(v); });
  if (map.mode) state.yearMode = map.mode;
  if (map.year) state.singleYear = parseInt(map.year);
  if (map.partial) state.includePartial = map.partial === '1';
  if (map.tab) state.tab = map.tab;
  if (map.hx) state.hX = map.hx;
  if (map.hy) state.hY = map.hy;
  if (map.sx) state.sX = map.sx;
  if (map.sy) state.sy = map.sy;
}

// ── Init ───────────────────────────────────────────────────────────
function init() {
  loadStateFromHash();

  const sel = document.getElementById('single-year-select');
  D.years.forEach(y => {
    const o = document.createElement('option'); o.value = y; o.textContent = y;
    if (y === state.singleYear) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener('change', () => { state.singleYear = parseInt(sel.value); renderAll(); });

  // Reflect loaded state into UI controls
  const ymRadio = document.querySelector(`input[name="year-mode"][value="${state.yearMode}"]`);
  if (ymRadio) ymRadio.checked = true;
  document.getElementById('include-partial').checked = state.includePartial;
  document.getElementById('single-year-wrap').style.display =
    state.yearMode === 'single' ? '' : 'none';

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

  // Axis selectors — reflect loaded state then wire change handlers
  document.getElementById('h-x').value = state.hX;
  document.getElementById('h-y').value = state.hY;
  document.getElementById('s-x').value = state.sX;
  document.getElementById('s-y').value = state.sY;
  document.getElementById('h-x').addEventListener('change', e => { state.hX = e.target.value; renderAll(); });
  document.getElementById('h-y').addEventListener('change', e => { state.hY = e.target.value; renderAll(); });
  document.getElementById('s-x').addEventListener('change', e => { state.sX = e.target.value; renderAll(); });
  document.getElementById('s-y').addEventListener('change', e => { state.sY = e.target.value; renderAll(); });

  // All-players search (debounced)
  let hSearchTimer = null, sSearchTimer = null;
  document.getElementById('h-alltable-search').addEventListener('input', e => {
    clearTimeout(hSearchTimer);
    hSearchTimer = setTimeout(() => {
      state.hTblQuery = e.target.value.trim();
      renderAllTable(filterRows(HITTERS, 'hitter'), 'hitter');
    }, 120);
  });
  document.getElementById('s-alltable-search').addEventListener('input', e => {
    clearTimeout(sSearchTimer);
    sSearchTimer = setTimeout(() => {
      state.sTblQuery = e.target.value.trim();
      renderAllTable(filterRows(SPS, 'sp'), 'sp');
    }, 120);
  });

  // Sub-domain table search (debounced)
  let hSubTimer = null, sSubTimer = null;
  document.getElementById('h-subtable-search').addEventListener('input', e => {
    clearTimeout(hSubTimer);
    hSubTimer = setTimeout(() => {
      state.hSubQuery = e.target.value.trim();
      renderAllTable(filterRows(HITTERS, 'hitter'), 'hitter', 'sub');
    }, 120);
  });
  document.getElementById('s-subtable-search').addEventListener('input', e => {
    clearTimeout(sSubTimer);
    sSubTimer = setTimeout(() => {
      state.sSubQuery = e.target.value.trim();
      renderAllTable(filterRows(SPS, 'sp'), 'sp', 'sub');
    }, 120);
  });

  // Snapshot pickers
  document.getElementById('h-snap-at').addEventListener('change', e => { state.hSnapAt = e.target.value; renderSnapshotMovers('hitter'); });
  document.getElementById('h-snap-vs').addEventListener('change', e => { state.hSnapVs = e.target.value; renderSnapshotMovers('hitter'); });
  document.getElementById('h-snap-sort').addEventListener('change', e => { state.hSnapSort = e.target.value; renderSnapshotMovers('hitter'); });
  document.getElementById('s-snap-at').addEventListener('change', e => { state.sSnapAt = e.target.value; renderSnapshotMovers('sp'); });
  document.getElementById('s-snap-vs').addEventListener('change', e => { state.sSnapVs = e.target.value; renderSnapshotMovers('sp'); });
  document.getElementById('s-snap-sort').addEventListener('change', e => { state.sSnapSort = e.target.value; renderSnapshotMovers('sp'); });

  // Tabs
  document.querySelectorAll('.tabs button').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      document.getElementById('tab-' + b.dataset.tab).classList.add('active');
      // Show the TOC for the active tab; hide others
      document.querySelectorAll('.toc-strip').forEach(t => t.classList.remove('active'));
      const tocId = b.dataset.tab === 'hitters' ? 'h-toc'
                  : b.dataset.tab === 'pitchers' ? 's-toc' : null;
      if (tocId) document.getElementById(tocId).classList.add('active');
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

  // "/" hotkey focuses the search box
  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      document.getElementById('search-input').focus();
    }
  });

  // Apply loaded tab state by clicking the right tab button (handlers are wired above)
  if (state.tab && state.tab !== 'home') {
    const tabBtn = document.querySelector(`.tabs button[data-tab="${state.tab}"]`);
    if (tabBtn) tabBtn.click();
  }

  renderBoundaryGlossary();
  renderHomeArchDist();
  renderAll();

  // After initial paint, resize again to ensure off-tab plots size correctly when first shown
  window.addEventListener('resize', resizeCurrentTabPlots);

  // Sticky-header collapse — frees vertical space while scrolling
  let lastScroll = 0;
  const hdr = document.querySelector('header');
  window.addEventListener('scroll', () => {
    const y = window.scrollY;
    if (y > 80 && !hdr.classList.contains('collapsed')) {
      hdr.classList.add('collapsed');
    } else if (y < 40 && hdr.classList.contains('collapsed')) {
      hdr.classList.remove('collapsed');
    }
    lastScroll = y;
  }, { passive: true });

  const overlay = document.getElementById('loading-overlay');
  if (overlay) {
    overlay.classList.add('hidden');
    setTimeout(() => overlay.remove(), 300);
  }
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
