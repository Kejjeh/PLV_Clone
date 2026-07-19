"""build_triangulate_dashboard.py — pretty, cyclable triangulate report.

Runs the triangulate engine over my roster (or supplied names), injects live IL
status from the injury_status cache, and renders a single self-contained HTML
page: a roster rail you click through, prev/next + arrow-key cycling, and a card
per player showing the three-lens read (PL / model / archetype) with verdict and
IL caveat.

  python scripts/xfp/build_triangulate_dashboard.py            # my roster
  python scripts/xfp/build_triangulate_dashboard.py A B C      # specific names

Output: data/outputs/triangulate.html (+ xfp-model/docs/triangulate.html).

Split (2026-07-19 audit item 11): the engine/render internals now live in
lib/triangulate_dashboard_style (CSS/JS/nav blobs), lib/triangulate_cards
(card data + per-card HTML), lib/triangulate_fa (batch artifacts + FA
section), and lib/triangulate_links (profiles deep-links). Every moved name
is re-exported here so external callers keep importing from this module.
"""
from __future__ import annotations

import sys
from datetime import date
from html import escape as h

from plv_clone.paths import ROOT, XFP_DOCS
sys.path.insert(0, str(ROOT))

from scripts.xfp.lib.triangulate_core import triangulate_player  # noqa: E402
from scripts.xfp.lib.injury_status import il_status_for, load_il_map  # noqa: E402
from plv_clone.positions import (  # noqa: E402
    ALL_POSITION_GROUPS, GROUP_ORDER, GROUP_RANK, order_groups, position_group,
)

# Split modules — names re-exported so external callers can keep importing them
# from build_triangulate_dashboard (e.g. tests import build_card_data here).
from scripts.xfp.lib.triangulate_dashboard_style import (  # noqa: E402, F401  (re-export)
    _CSS, _FA_CSS, _JS, _NAV,
)
from scripts.xfp.lib.triangulate_cards import (  # noqa: E402, F401  (re-export)
    _GROUP_LABELS, _IL_STATES, _NEG_WORDS, _POS_WORDS, _TRAJ_COLORS,
    _adv_col, _advanced_panel, _arche_panel, _blend_panel, _boom_panel,
    _card_html, _ctx_cell, _context_panel, _delta_cls, _fmt, _kv,
    _model_panel, _num, _panel, _pct, _process_panel, _sgn, _sp_panel,
    _traj_svg, _trajectory_panel, _txt, _verdict_class, _word_cls,
    build_card_data,
)
from scripts.xfp.lib.triangulate_fa import (  # noqa: E402, F401  (re-export)
    _BATCH_CSV, _BATCH_JSON, _NIGHTLY_CSV, _fa_card_from_batch, _fa_rail_html,
    _freshest_nightly, _group_from_seam, _parse_domains, _resolve_group,
    load_batch_lens, load_fa_cards_store, load_fa_rows,
)
from scripts.xfp.lib.triangulate_links import (  # noqa: E402, F401  (re-export)
    _load_profile_id_map, _profile_link, _warn,
)

OUT = ROOT / 'data' / 'outputs'


def my_roster_names() -> list[str]:
    from plv_clone.league_state import LeagueState
    roster = LeagueState().my_roster()
    if roster.empty or 'player_name' not in roster.columns:
        return []
    return [str(n) for n in roster['player_name'].tolist() if n]


def collect_cards(names: list[str]) -> list[dict]:
    il_map = load_il_map()
    lens_map = load_batch_lens()
    cards = []
    for name in names:
        try:
            res = triangulate_player(name, il_status=il_status_for(name, il_map))
        except Exception as e:
            _warn(f'triangulate_player({name})', e)
            res = None
        if not res:
            continue
        c = build_card_data(res)
        c['vclass'] = _verdict_class(c)
        # attach the already-computed batch lenses (context-only enrichment)
        lens = lens_map.get(c.get('name'))
        c['lens'] = lens
        c['group'] = _resolve_group(c, lens)
        cards.append(c)
    # canonical position-group order (C, 1B/3B, 2B/SS, OF, UTIL, DH, SP, CLOSER,
    # SETUP), then by name — via plv_clone.positions, not a re-derived map.
    cards.sort(key=lambda c: (GROUP_RANK.get(c.get('group'), len(GROUP_ORDER)), str(c.get('name'))))
    return cards


# ---------------------------------------------------------------- HTML render

def _rail_html(cards: list[dict]) -> str:
    """Roster rail grouped by the canonical position taxonomy (C, 1B/3B, 2B/SS,
    OF, UTIL, DH, SP, CLOSER, SETUP) — header order via plv_clone.positions."""
    out = []
    last_group = None
    # canonical header order (only the groups actually present)
    present = order_groups(c.get('group') for c in cards if c.get('group'))
    rank = {g: i for i, g in enumerate(present)}
    cards = sorted(cards, key=lambda c: (rank.get(c.get('group'), len(present)), str(c.get('name'))))
    for c in cards:
        grp = c.get('group')
        if grp != last_group:
            last_group = grp
            out.append(f'<div class="grp">{h(str(_GROUP_LABELS.get(grp, grp or "—")))}</div>')
        vt = h(str(c['blend'].get('value_tier') or c.get('verdict_top') or ''))
        out.append(
            f'<button><span class="dot {c["vclass"]}"></span>{h(str(c["name"]))}'
            f'<span class="vt">{vt}</span></button>')
    return '\n'.join(out)


def render_page(cards: list[dict], fa_rows: list[dict] | None = None) -> str:
    today = date.today().isoformat()
    fa_rows = fa_rows or []
    n_il = sum(1 for c in cards if c['is_il'])
    if not cards and not fa_rows:
        body = '<div class="empty">No triangulate cards — roster empty or names unresolved.</div>'
    else:
        fa_rail = _fa_rail_html(fa_rows) if fa_rows else ''
        fa_cards = ''.join(_card_html(c, len(cards) + k) for k, c in enumerate(fa_rows))
        body = f"""
<div class="layout">
  <nav class="rail">{_rail_html(cards)}{fa_rail}</nav>
  <section class="main">
    <div class="cyc">
      <button id="prev">← Prev</button><button id="next">Next →</button>
      <span class="pos" id="pos"></span><span class="pos">· ←/→ keys</span>
    </div>
    {''.join(_card_html(c, k) for k, c in enumerate(cards))}{fa_cards}
  </section>
</div>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Triangulate — Ligers</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{_CSS}{_FA_CSS}</style></head>
<body>
<div class="topbar"><h1>🔱 Triangulate</h1>
<span class="sub">{len(cards)} roster · {len(fa_rows)} FA · {n_il} on IL · three-lens read · {today}</span>{_NAV}</div>
{body}
<script>{_JS}</script></body></html>"""


def main():
    argv = [a for a in sys.argv[1:] if a != '--live-fa']
    live_fa = '--live-fa' in sys.argv[1:]
    names = argv or my_roster_names()
    if not names:
        print('  no roster names — pass names as args')
        return
    print(f'  triangulating {len(names)} players...')
    cards = collect_cards(names)
    il_n = sum(1 for c in cards if c['is_il'])
    print(f'  built {len(cards)} cards ({il_n} on IL)')
    fa_raw = load_fa_rows({c.get('name') for c in cards})
    if live_fa:
        # Full-fidelity FA cards: run the live engine per FA (~5-8s each; the
        # 500+ pool takes ~45-60 min — background/nightly use only). Falls back
        # to the batch card for any FA the live engine can't resolve.
        print(f'  --live-fa: running the live engine over {len(fa_raw)} FAs...')
        fa_cards = collect_cards([j['name'] for j in fa_raw])
        got = {c['name'] for c in fa_cards}
        lens_map = load_batch_lens()
        fa_cards += [_fa_card_from_batch(j, lens_map.get(j.get('name')))
                     for j in fa_raw if j.get('name') not in got]
        by_name = {c['name']: c for c in fa_cards}
        order = {j['name']: k for k, j in enumerate(fa_raw)}
        fa_rows = sorted(by_name.values(), key=lambda c: order.get(c['name'], 9999))
        print(f'  FA section: {len(fa_rows)} free agents (LIVE engine; {len(fa_raw) - len(got)} batch-fallback)')
    else:
        lens_map = load_batch_lens()
        store = load_fa_cards_store()
        if store:
            # DEFAULT path since 2026-07-19: hydrate FA cards from the nightly
            # --cards-out store (same result-dict schema as the live engine) —
            # full fidelity (confidence / bands / watch list / value tier) with
            # no per-FA engine re-run. Replaces the ~50-min --live-fa refresh
            # step; --live-fa remains as a manual force-live override.
            fa_rows, n_fallback = [], 0
            for j in fa_raw:
                res = store.get(j.get('name'))
                if res:
                    c = build_card_data(res)
                    c['vclass'] = _verdict_class(c)
                    lens = lens_map.get(c.get('name'))
                    c['lens'] = lens
                    c['group'] = (j.get('position_group')
                                  if j.get('position_group') in GROUP_RANK
                                  else _resolve_group(c, lens))
                    fa_rows.append(c)
                else:
                    n_fallback += 1
                    fa_rows.append(_fa_card_from_batch(j, lens_map.get(j.get('name'))))
            print(f'  FA section: {len(fa_rows)} free agents (full-fidelity from '
                  f'nightly cards store; {n_fallback} flat-batch fallback)')
        else:
            fa_rows = [_fa_card_from_batch(j, lens_map.get(j.get('name'))) for j in fa_raw]
            print(f'  FA section: {len(fa_rows)} free agents (full-card render from nightly batch)')
    html_doc = render_page(cards, fa_rows)
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
