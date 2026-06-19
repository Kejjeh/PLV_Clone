"""build_triangulate_dashboard.py — pretty, cyclable triangulate report.

Runs the triangulate engine over my roster (or supplied names), injects live IL
status from the injury_status cache, and renders a single self-contained HTML
page: a roster rail you click through, prev/next + arrow-key cycling, and a card
per player showing the three-lens read (PL / model / archetype) with verdict and
IL caveat.

  python scripts/xfp/build_triangulate_dashboard.py            # my roster
  python scripts/xfp/build_triangulate_dashboard.py A B C      # specific names

Output: data/outputs/triangulate.html (+ xfp-model/docs/triangulate.html).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from html import escape as h

from plv_clone.paths import ROOT, XFP_DOCS
sys.path.insert(0, str(ROOT))

from scripts.xfp.lib.triangulate_core import triangulate_player  # noqa: E402
from scripts.xfp.lib.injury_status import il_status_for, load_il_map  # noqa: E402

OUT = ROOT / 'data' / 'outputs'

_IL_STATES = {'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL', 'INJURY_RESERVE',
              'OUT', 'IL', 'IL10', 'IL15', 'IL60'}


def build_card_data(result: dict) -> dict:
    """Pure: extract the display fields for one triangulate card from a
    triangulate_player() result dict. Tolerant of sparse results."""
    p = result.get('player') or {}
    model = result.get('model') or {}
    arche = result.get('arche') or {}
    il_status = result.get('il_status')
    return {
        'name': p.get('display_name') or result.get('name'),
        'bucket': result.get('bucket'),
        'team': p.get('team'),
        'verdict': result.get('verdict'),
        'verdict_top': result.get('verdict_top'),
        'override_tag': result.get('override_tag'),
        'il_status': il_status,
        'is_il': bool(il_status) and str(il_status).upper() in _IL_STATES,
        'confidence': result.get('confidence'),
        'n_aligned': result.get('confidence_n_aligned'),
        'n_avail': result.get('confidence_n_available'),
        'pl_rank': result.get('pl_main'),
        'model_rank': result.get('model_rank'),
        'model_proj': result.get('model_proj'),
        'model_signal': model.get('signal'),
        'arche_label': result.get('arche_label'),
        'arche_overall': result.get('arche_overall'),
        'arche_traj': result.get('arche_traj'),
        'arche_t1': arche.get('t1_fp') if arche.get('have') else None,
        'blended_xfp': result.get('blended_xfp'),
        'rationale': result.get('rationale'),
        'watch_list': result.get('watch_list') or [],
    }


def my_roster_names() -> list[str]:
    from plv_clone.league_state import LeagueState
    roster = LeagueState().my_roster()
    if roster.empty or 'player_name' not in roster.columns:
        return []
    return [str(n) for n in roster['player_name'].tolist() if n]


def _verdict_class(card: dict) -> str:
    if card.get('is_il'):
        return 'il'
    top = (card.get('verdict_top') or '').upper()
    if 'BUY' in top:
        return 'buy'
    if 'SELL' in top or 'DROP' in top:
        return 'sell'
    if 'HOLD' in top:
        return 'hold'
    return 'mixed'


def collect_cards(names: list[str]) -> list[dict]:
    il_map = load_il_map()
    cards = []
    for name in names:
        try:
            res = triangulate_player(name, il_status=il_status_for(name, il_map))
        except Exception:
            res = None
        if not res:
            continue
        c = build_card_data(res)
        c['vclass'] = _verdict_class(c)
        cards.append(c)
    # bucket order H, SP, RP then by name
    order = {'H': 0, 'SP': 1, 'RP': 2}
    cards.sort(key=lambda c: (order.get(c.get('bucket'), 9), str(c.get('name'))))
    return cards


# ---------------------------------------------------------------- HTML render

_CSS = """
:root{--bg:#0f172a;--panel:#1e293b;--ink:#e2e8f0;--mut:#94a3b8;--line:#334155;
--buy:#10b981;--sell:#ef4444;--hold:#f59e0b;--mixed:#6366f1;--il:#a855f7;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;
align-items:baseline;gap:14px}header h1{margin:0;font-size:20px;font-weight:700}
header .sub{color:var(--mut);font-size:12px}
.layout{display:grid;grid-template-columns:260px 1fr;min-height:calc(100vh - 61px)}
.rail{border-right:1px solid var(--line);overflow:auto;max-height:calc(100vh - 61px)}
.rail .grp{padding:10px 16px 4px;color:var(--mut);font-size:11px;letter-spacing:.08em;
text-transform:uppercase}
.rail button{display:flex;align-items:center;gap:8px;width:100%;text-align:left;
background:none;border:0;color:var(--ink);padding:8px 16px;cursor:pointer;font-size:13px}
.rail button:hover{background:#172033}.rail button.active{background:#243049;
box-shadow:inset 3px 0 0 var(--mixed)}
.dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
.dot.buy{background:var(--buy)}.dot.sell{background:var(--sell)}
.dot.hold{background:var(--hold)}.dot.mixed{background:var(--mixed)}.dot.il{background:var(--il)}
.main{padding:24px 28px;overflow:auto;max-height:calc(100vh - 61px)}
.nav{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.nav button{background:var(--panel);border:1px solid var(--line);color:var(--ink);
border-radius:8px;padding:7px 14px;cursor:pointer}.nav button:hover{border-color:var(--mixed)}
.nav .pos{color:var(--mut);font-size:12px}
.card{display:none;max-width:880px}.card.show{display:block}
.vhead{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.vhead h2{margin:0;font-size:26px}
.badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;letter-spacing:.04em}
.badge.buy{background:rgba(16,185,129,.15);color:var(--buy)}
.badge.sell{background:rgba(239,68,68,.15);color:var(--sell)}
.badge.hold{background:rgba(245,158,11,.15);color:var(--hold)}
.badge.mixed{background:rgba(99,102,241,.15);color:var(--mixed)}
.badge.il{background:rgba(168,85,247,.18);color:var(--il)}
.team{color:var(--mut);font-size:13px}
.verdict{font-size:15px;margin:4px 0 18px;color:#cbd5e1}
.lenses{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:18px}
.lens{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.lens .lt{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px}
.lens .big{font-size:22px;font-weight:700}.lens .sm{color:var(--mut);font-size:12px;margin-top:2px}
.meta{display:flex;gap:22px;flex-wrap:wrap;margin-bottom:16px}
.meta .k{color:var(--mut);font-size:11px;text-transform:uppercase}.meta .v{font-size:16px;font-weight:600}
.conf{height:7px;background:#0b1220;border-radius:999px;overflow:hidden;width:160px;margin-top:6px}
.conf i{display:block;height:100%;background:var(--mixed)}
.rat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
.rat .lt{color:var(--mut);font-size:11px;text-transform:uppercase;margin-bottom:6px}
.watch{display:flex;flex-wrap:wrap;gap:8px}.watch span{background:#0b1220;border:1px solid var(--line);
border-radius:8px;padding:5px 10px;font-size:12px}
.empty{color:var(--mut);padding:40px}
"""

_JS = """
const cards=[...document.querySelectorAll('.card')];
const btns=[...document.querySelectorAll('.rail button')];
let i=0;
function show(n){i=(n+cards.length)%cards.length;
 cards.forEach((c,k)=>c.classList.toggle('show',k===i));
 btns.forEach((b,k)=>b.classList.toggle('active',k===i));
 document.getElementById('pos').textContent=(i+1)+' / '+cards.length;
 const a=btns[i]; if(a) a.scrollIntoView({block:'nearest'});}
btns.forEach((b,k)=>b.onclick=()=>show(k));
document.getElementById('prev').onclick=()=>show(i-1);
document.getElementById('next').onclick=()=>show(i+1);
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(i-1);
 if(e.key==='ArrowRight')show(i+1);});
show(0);
"""


def _fmt(x, nd=2):
    if x is None:
        return '—'
    if isinstance(x, float):
        return f'{x:.{nd}f}'
    return h(str(x))


def _card_html(c: dict, idx: int) -> str:
    vcls = c['vclass']
    badge = (f'<span class="badge il">🏥 {h(str(c["il_status"]))}</span>'
             if c['is_il'] else '')
    top = h(str(c.get('verdict_top') or '—'))
    t1 = _fmt(c.get('arche_t1'), 1)
    over = c.get('arche_overall')
    conf = c.get('confidence') or 0
    watch = ''.join(f'<span>{h(str(w))}</span>' for w in c['watch_list'][:8])
    return f"""
<article class="card" data-i="{idx}">
  <div class="vhead">
    <h2>{h(str(c['name']))}</h2>
    <span class="team">{h(str(c.get('bucket') or ''))} · {h(str(c.get('team') or ''))}</span>
    <span class="badge {vcls}">{top}</span>{badge}
  </div>
  <div class="verdict">{h(str(c.get('verdict') or ''))}</div>
  <div class="lenses">
    <div class="lens"><div class="lt">Pitcher List</div>
      <div class="big">{_fmt(c.get('pl_rank'))}</div><div class="sm">weekly rank</div></div>
    <div class="lens"><div class="lt">Model</div>
      <div class="big">#{_fmt(c.get('model_rank'))}</div>
      <div class="sm">proj {_fmt(c.get('model_proj'))} · {h(str(c.get('model_signal') or '—'))}</div></div>
    <div class="lens"><div class="lt">Archetype</div>
      <div class="big">{h(str(c.get('arche_label') or '—'))}</div>
      <div class="sm">{_fmt(over,0) if over is not None else '—'} OVR · {h(str(c.get('arche_traj') or '—'))} · T+1 {t1}</div></div>
  </div>
  <div class="meta">
    <div><div class="k">Confidence</div><div class="v">{conf:.2f}</div>
      <div class="conf"><i style="width:{min(max(conf,0),1)*100:.0f}%"></i></div>
      <div class="sm" style="color:var(--mut);font-size:11px">{_fmt(c.get('n_aligned'),0)} of {_fmt(c.get('n_avail'),0)} signals agree</div></div>
    <div><div class="k">Blended xFP</div><div class="v">{_fmt(c.get('blended_xfp'))}</div></div>
  </div>
  <div class="rat"><div class="lt">Rationale</div>{h(str(c.get('rationale') or '—'))}</div>
  {f'<div class="rat"><div class="lt">Watch</div><div class="watch">{watch}</div></div>' if watch else ''}
</article>"""


def _rail_html(cards: list[dict]) -> str:
    out = []
    last_bucket = None
    labels = {'H': 'Hitters', 'SP': 'Starting Pitchers', 'RP': 'Relievers'}
    for k, c in enumerate(cards):
        if c.get('bucket') != last_bucket:
            last_bucket = c.get('bucket')
            out.append(f'<div class="grp">{labels.get(last_bucket, last_bucket or "")}</div>')
        out.append(
            f'<button><span class="dot {c["vclass"]}"></span>{h(str(c["name"]))}</button>')
    return '\n'.join(out)


def render_page(cards: list[dict]) -> str:
    today = date.today().isoformat()
    if not cards:
        body = '<div class="empty">No triangulate cards — roster empty or names unresolved.</div>'
    else:
        body = f"""
<div class="layout">
  <nav class="rail">{_rail_html(cards)}</nav>
  <section class="main">
    <div class="nav">
      <button id="prev">← Prev</button><button id="next">Next →</button>
      <span class="pos" id="pos"></span>
      <span class="pos">· use ←/→ keys</span>
    </div>
    {''.join(_card_html(c, k) for k, c in enumerate(cards))}
  </section>
</div>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Triangulate — Ligers</title><style>{_CSS}</style></head>
<body>
<header><h1>🔱 Triangulate</h1><span class="sub">{len(cards)} players · three-lens read · {today}</span>
<nav style="margin-left:auto;display:flex;gap:14px;font-size:13px">
<a href="index.html" style="color:var(--mut);text-decoration:none">XFP</a>
<a href="matchup.html" style="color:var(--mut);text-decoration:none">Matchup</a>
<a href="live_dashboard.html" style="color:var(--mut);text-decoration:none">Live</a>
<a href="player_profiles.html" style="color:var(--mut);text-decoration:none">Profiles</a>
<a style="color:var(--ink)">Triangulate</a></nav></header>
{body}
<script>{_JS}</script></body></html>"""


def main():
    names = sys.argv[1:] or my_roster_names()
    if not names:
        print('  no roster names — pass names as args')
        return
    print(f'  triangulating {len(names)} players...')
    cards = collect_cards(names)
    il_n = sum(1 for c in cards if c['is_il'])
    print(f'  built {len(cards)} cards ({il_n} on IL)')
    html_doc = render_page(cards)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'triangulate.html').write_text(html_doc, encoding='utf-8')
    print(f'  wrote {OUT / "triangulate.html"}')
    try:
        xfp = XFP_DOCS / 'triangulate.html'
        xfp.parent.mkdir(parents=True, exist_ok=True)
        xfp.write_text(html_doc, encoding='utf-8')
        print(f'  wrote {xfp}')
    except Exception as e:
        print(f'  (skipped xfp-model copy: {e})')


if __name__ == '__main__':
    main()
