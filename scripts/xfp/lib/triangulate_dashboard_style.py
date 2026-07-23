"""triangulate_dashboard_style.py — static CSS / JS / nav blobs for the
triangulate dashboard.

Split verbatim from build_triangulate_dashboard.py (2026-07-19 audit item 11);
the dashboard re-exports these names for external callers.
"""
from __future__ import annotations

from .dashboard_chrome import topnav as _topnav

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font-family:'Source Serif 4','Iowan Old Style',Georgia,serif;font-size:16px;line-height:1.55}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace}
.topbar{position:sticky;top:0;z-index:50;background:var(--bg);border-bottom:1px solid var(--border);
display:flex;align-items:center;gap:16px;padding:12px 22px}
.topbar h1{margin:0;font-size:18px;font-weight:600;letter-spacing:.01em}
.topbar .sub{color:var(--dim);font-size:12.5px;font-family:'IBM Plex Mono',monospace}
nav.topnav{margin-left:auto;display:flex;font-family:'IBM Plex Mono',monospace;font-size:12.5px}
nav.topnav a{color:var(--dim);text-decoration:none;padding:.35em .9em;border:1px solid var(--border);
border-right:0}nav.topnav a:first-child{border-radius:3px 0 0 3px}
nav.topnav a:last-child{border-radius:0 3px 3px 0;border-right:1px solid var(--border)}
nav.topnav a:hover{color:var(--text);background:var(--panel)}
nav.topnav a.current{color:var(--accent);background:var(--panel);border-color:var(--accent)}
.layout{display:grid;grid-template-columns:248px 1fr;min-height:calc(100vh - 53px)}
.rail{border-right:1px solid var(--border);overflow:auto;max-height:calc(100vh - 53px);background:var(--stripe)}
.rail .grp{padding:14px 16px 5px;color:var(--dim);font-size:10.5px;letter-spacing:.1em;
text-transform:uppercase;font-family:'IBM Plex Mono',monospace}
.rail button{display:flex;align-items:center;gap:9px;width:100%;text-align:left;background:none;
border:0;color:var(--text);padding:7px 16px;cursor:pointer;font-family:inherit;font-size:14.5px}
.rail button:hover{background:var(--panel)}
.rail button.active{background:var(--panel);box-shadow:inset 3px 0 0 var(--accent);color:var(--accent)}
.rail button .vt{margin-left:auto;font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--dim)}
.dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
.dot.buy{background:var(--pos)}.dot.sell{background:var(--neg)}.dot.hold{background:var(--warn)}
.dot.mixed{background:var(--info)}.dot.il{background:var(--accent)}
.main{padding:22px 30px 60px;overflow:auto;max-height:calc(100vh - 53px)}
.cyc{display:flex;align-items:center;gap:12px;margin-bottom:20px;font-family:'IBM Plex Mono',monospace;font-size:12.5px}
.cyc button{background:var(--panel);border:1px solid var(--border);color:var(--text);
border-radius:3px;padding:6px 13px;cursor:pointer;font-family:inherit}
.cyc button:hover{border-color:var(--accent);color:var(--accent)}.cyc .pos{color:var(--dim)}
.card{display:none;max-width:none}.card.show{display:block}
.vhead{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:4px}
.vhead h2{margin:0;font-size:30px;font-weight:600}
.vhead .team{color:var(--dim);font-family:'IBM Plex Mono',monospace;font-size:12.5px}
.badge{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;padding:3px 9px;
border-radius:3px;letter-spacing:.03em}
.badge.buy{background:rgba(127,176,105,.16);color:var(--pos)}
.badge.sell{background:rgba(193,102,107,.16);color:var(--neg)}
.badge.hold{background:rgba(212,169,69,.16);color:var(--warn)}
.badge.mixed{background:rgba(138,168,196,.16);color:var(--info)}
.badge.il{background:rgba(217,119,87,.18);color:var(--accent)}
.verdict{font-size:16px;margin:6px 0 20px;color:var(--text)}
.verdict .il{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));gap:14px;margin-bottom:6px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:15px 16px}
.panel.span2{grid-column:span 2}
.pt{color:var(--accent);font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.1em;
text-transform:uppercase;margin-bottom:11px;display:flex;justify-content:space-between}
.pt .tag{color:var(--dim)}
.big{font-size:27px;font-weight:600;line-height:1}.big .u{font-size:13px;color:var(--dim);margin-left:3px}
.kv{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-top:1px solid var(--faint);
font-size:14px}.kv:first-of-type{border-top:0}
.kv .k{color:var(--dim)}.kv .v{font-family:'IBM Plex Mono',monospace}
.v.pos{color:var(--pos)}.v.neg{color:var(--neg)}.v.warn{color:var(--warn)}.v.acc{color:var(--accent)}
.bar{height:6px;background:var(--bg);border-radius:99px;overflow:hidden;margin:8px 0 4px}
.bar i{display:block;height:100%;background:var(--accent)}
.bar i.pos{background:var(--pos)}.bar i.neg{background:var(--neg)}
.band{position:relative;height:26px;margin:10px 0 4px}
.band .track{position:absolute;top:11px;left:0;right:0;height:4px;background:var(--bg);border-radius:99px}
.band .rng{position:absolute;top:9px;height:8px;background:rgba(217,119,87,.35);border-radius:99px}
.band .pt2{position:absolute;top:6px;width:3px;height:14px;background:var(--accent);border-radius:2px}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{font-family:'IBM Plex Mono',monospace;font-size:11.5px;padding:4px 9px;border-radius:3px;
background:var(--bg);border:1px solid var(--border);color:var(--dim)}
.chip.on{color:var(--text);border-color:var(--accent)}
.chip.pos{color:var(--pos);border-color:rgba(127,176,105,.4)}
.chip.neg{color:var(--neg);border-color:rgba(193,102,107,.4)}
.chip.warn{color:var(--warn);border-color:rgba(212,169,69,.4)}
.rat{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin-top:14px}
.rat .pt{margin-bottom:7px}
.conf{height:6px;background:var(--bg);border-radius:99px;overflow:hidden;width:100%;margin:7px 0 3px}
.conf i{display:block;height:100%;background:var(--accent)}
.empty{color:var(--dim);padding:48px;font-family:'IBM Plex Mono',monospace}
/* boom/bust actuals window caption */
.bb-win{color:var(--dim);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
margin:11px 0 5px;border-top:1px solid var(--faint);padding-top:9px}
/* 4-cell context lens grid */
.cctx{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.cc{background:var(--bg);border:1px solid var(--faint);border-radius:5px;padding:10px 11px}
.cc-t{color:var(--dim);font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.08em;
text-transform:uppercase;margin-bottom:5px}
.cc-v{font-size:17px;font-weight:600;line-height:1.15}
.cc-v.pos{color:var(--pos)}.cc-v.neg{color:var(--neg)}.cc-v.warn{color:var(--warn)}
.cc-sub{color:var(--dim);font-size:11px;margin-top:3px;line-height:1.35}
/* collapsible advanced panel */
details.adv{margin-top:14px;max-width:none}
details.adv>summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;
align-items:center;margin-bottom:0}
details.adv>summary::-webkit-details-marker{display:none}
details.adv>summary::after{content:'▸';color:var(--dim);font-size:12px;margin-left:8px}
details.adv[open]>summary::after{content:'▾'}
details.adv[open]>summary{margin-bottom:12px}
.adv-body{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px 26px}
.adv-col{min-width:0}
.adv-h{color:var(--accent);font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.08em;
text-transform:uppercase;margin:0 0 4px}
.adv-col .kv:first-of-type{border-top:0}
"""

_JS = """
const cards=[...document.querySelectorAll('.card')];
const btns=[...document.querySelectorAll('.rail button')];
let i=0;
function show(n){i=(n+cards.length)%cards.length;
 cards.forEach((c,k)=>c.classList.toggle('show',k===i));
 btns.forEach((b,k)=>b.classList.toggle('active',k===i));
 document.getElementById('pos').textContent=(i+1)+' / '+cards.length;
 const a=btns[i]; if(a){const d=a.closest('details'); if(d) d.open=true;
  a.scrollIntoView({block:'nearest'});}}
btns.forEach((b,k)=>b.onclick=()=>show(k));
document.getElementById('prev').onclick=()=>show(i-1);
document.getElementById('next').onclick=()=>show(i+1);
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(i-1);
 if(e.key==='ArrowRight')show(i+1);});
let start=0;
if(location.hash.startsWith('#p=')){const w=decodeURIComponent(location.hash.slice(3)).toLowerCase();
 const k=cards.findIndex(c=>{const h2=c.querySelector('h2');return h2&&h2.textContent.trim().toLowerCase()===w;});
 if(k>=0)start=k;}
show(start);
"""

_FA_CSS = """
.xlink{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--dim);
 text-decoration:none;border:1px solid var(--line);border-radius:3px;padding:3px 8px;margin-left:8px}
.xlink:hover{color:var(--accent);border-color:var(--accent)}
.traj-chart{width:100%;height:92px;margin:6px 0 2px;display:block}
.tl-row{display:flex;gap:10px;align-items:center;font-size:10px;margin-bottom:4px}
.tl-item{font-family:'IBM Plex Mono',monospace;font-weight:500}
.tl-x{color:var(--dim);font-size:9.5px}
.tl-row .tl-x:last-child{margin-left:auto}
.fa-head{padding:18px 16px 6px;color:var(--accent);font-size:11px;letter-spacing:.14em;
 font-weight:600;border-top:1px solid var(--line);margin-top:12px}
.fa-grp summary{padding:9px 16px;cursor:pointer;color:var(--dim);font-size:11.5px;
 letter-spacing:.08em;list-style:none;user-select:none}
.fa-grp summary:hover{background:var(--panel);color:var(--accent)}
.fa-grp summary::before{content:'▸ '}
.fa-grp[open] summary::before{content:'▾ '}
"""

_NAV = _topnav('triangulate')  # unified nav owner (item 8) — was hand-copied
