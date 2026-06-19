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
    """Pure: extract the full display field set for one triangulate card from a
    triangulate_player() result dict. Surfaces every validated lens model_row +
    archetype_row compute. Tolerant of sparse results."""
    p = result.get('player') or {}
    model = result.get('model') or {}
    arche = result.get('arche') or {}
    have_a = bool(arche.get('have'))
    bucket = result.get('bucket')
    il_status = result.get('il_status')

    # Sustainability may be a plain bucket string OR a rich process dict —
    # normalize to a short label + readable detail (never dump the dict).
    sus_raw = model.get('sustainability')
    if isinstance(sus_raw, dict):
        sus_label = sus_raw.get('process_verdict') or sus_raw.get('bucket')
        sus_detail = sus_raw.get('process_detail')
    elif isinstance(sus_raw, str):
        sus_label, sus_detail = sus_raw, None
    else:
        sus_label, sus_detail = None, None

    # Boom/bust comes from SP fields for pitchers, hitter_* fields for hitters.
    if bucket == 'H':
        boom = {
            'stack': model.get('hitter_boom_stack'),
            'tier': None,
            'boom_rate': model.get('hitter_boom_rate_expected'),
            'bust_rate': model.get('hitter_boom_bust_expected'),
            'mean_fp': None,
            'components': model.get('hitter_boom_components'),
        }
    else:
        boom = {
            'stack': model.get('boom_stack'),
            'tier': model.get('boom_tier'),
            'boom_rate': model.get('boom_rate_expected'),
            'bust_rate': model.get('boom_bust_rate_expected'),
            'mean_fp': model.get('boom_mean_fp_expected'),
            'components': model.get('boom_components'),
        }

    return {
        'name': p.get('display_name') or result.get('name'),
        'bucket': bucket,
        'team': p.get('team'),
        'verdict': result.get('verdict'),
        'verdict_top': result.get('verdict_top'),
        'override_tag': result.get('override_tag'),
        'il_status': il_status,
        'is_il': bool(il_status) and str(il_status).upper() in _IL_STATES,
        'confidence': result.get('confidence'),
        'n_aligned': result.get('confidence_n_aligned'),
        'n_avail': result.get('confidence_n_available'),
        'rationale': result.get('rationale'),
        'watch_list': result.get('watch_list') or [],
        'sustainability': sus_label,
        'sustainability_detail': sus_detail,
        # --- back-compat flat keys (used by the rail/summary) ---
        'pl_rank': result.get('pl_main'),
        'model_rank': result.get('model_rank'),
        'model_proj': result.get('model_proj'),
        'model_signal': model.get('signal'),
        'arche_label': result.get('arche_label'),
        'arche_overall': result.get('arche_overall'),
        'arche_traj': result.get('arche_traj'),
        'arche_t1': arche.get('t1_fp') if have_a else None,
        'blended_xfp': result.get('blended_xfp'),
        # --- PL lens ---
        'pl': {
            'rank': result.get('pl_main'),
            'date': result.get('pl_main_date'),
            'stream': result.get('pl_stream'),
            'stream_opp': result.get('pl_stream_opp'),
        },
        # --- model lens (rank + projection band + quality) ---
        'model': {
            'rank': result.get('model_rank'),
            'proj': result.get('model_proj'),
            'proj_label': model.get('proj_label'),
            'signal': model.get('signal'),
            'p25': model.get('p25'),
            'p75': model.get('p75'),
            'sigma': model.get('sigma'),
            'dq_tag': model.get('data_quality_tag'),
        },
        # --- archetype lens (20-80 cell + trajectory + comps proxies) ---
        'arche': {
            'have': have_a,
            'label': arche.get('archetype') if have_a else None,
            'overall': arche.get('overall') if have_a else None,
            'cell': arche.get('cell') if have_a else None,
            'traj': arche.get('traj_flag') if have_a else None,
            't1': arche.get('t1_fp') if have_a else None,
            't2': arche.get('t2_fp') if have_a else None,
            'slope': arche.get('slope_3yr') if have_a else None,
            'career_pct': arche.get('career_pct') if have_a else None,
            'boundary': arche.get('boundary_tier') if have_a else None,
            'age_tier': arche.get('age_tier') if have_a else None,
            'velo_tier': arche.get('velo_tier') if have_a else None,
            'stuff_subtype': arche.get('stuff_subtype') if have_a else None,
        },
        # --- boom/bust + expected-value lens ---
        'boom': boom,
        # --- SP-only signal panel (decline / velo / recform / high-K / framing / IL-return / process) ---
        'sp': {
            'decline_tier': model.get('decline_tier'),
            'velo_severity': model.get('velo_severity'),
            'velo_yoy_flag': model.get('velo_yoy_flag'),
            'recform_tag': model.get('recform_tag'),
            'recform_z': model.get('recform_z'),
            'recform_mean': model.get('recform_mean_per_start_fp'),
            'high_k': bool(model.get('is_high_k_arm')),
            'high_k_z': model.get('high_k_z_score'),
            'elite_framer': bool(model.get('is_elite_framer')),
            'framing_tax': bool(model.get('is_framing_tax')),
            'il_return': bool(model.get('is_first_back_long_il')),
            'process_verdict': model.get('process_verdict'),
        },
        # --- blended xFP + value tier + role (RP) ---
        'blend': {
            'xfp': result.get('blended_xfp'),
            'ci': result.get('blended_ci'),
            'value_tier': result.get('value_tier'),
            'rep_delta': result.get('replacement_delta'),
            'role': result.get('role'),
            'role_char': result.get('role_characterization'),
            'ros': result.get('ros_estimate'),
        },
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
:root{--bg:#1a1815;--panel:#211e1a;--stripe:#1d1b17;--border:#34302a;
--text:#f5f1ea;--dim:#a89e8a;--faint:#3a352e;--accent:#d97757;
--pos:#7fb069;--neg:#c1666b;--warn:#d4a945;--info:#8aa8c4;}
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
.card{display:none;max-width:1320px}.card.show{display:block}
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


def _pct(x):
    return '—' if x is None else f'{x * 100:.0f}%'


def _kv(k, v, cls=''):
    return f'<div class="kv"><span class="k">{h(k)}</span><span class="v {cls}">{v}</span></div>'


def _panel(title, inner, tag='', span=False):
    t = f'<div class="pt">{h(title)}<span class="tag">{h(str(tag))}</span></div>' if tag \
        else f'<div class="pt">{h(title)}</div>'
    return f'<div class="panel{" span2" if span else ""}">{t}{inner}</div>'


# trajectory / tier -> semantic colour class
_POS_WORDS = ('RISING', 'IMPROVING', 'LEGIT', 'HOT', 'BREAKOUT', 'ELITE', 'STABLE_UP', 'BUY')
_NEG_WORDS = ('DECLINE', 'DECLINING', 'FADE', 'COLD', 'REGRESS', 'BAD', 'NOISE', 'SEVERE', 'CAREER_LOW')


def _word_cls(s):
    if not s:
        return ''
    u = str(s).upper()
    if any(w in u for w in _NEG_WORDS):
        return 'neg'
    if any(w in u for w in _POS_WORDS):
        return 'pos'
    return ''


def _model_panel(c):
    m = c['model']
    proj, p25, p75 = m['proj'], m['p25'], m['p75']
    band = ''
    if proj is not None and p25 is not None and p75 is not None and p75 > p25:
        lo, hi = p25, p75
        rng = hi - lo or 1
        pos = max(0, min(1, (proj - lo) / rng)) * 100
        band = (f'<div class="band"><div class="track"></div>'
                f'<div class="rng" style="left:8%;right:8%"></div>'
                f'<div class="pt2" style="left:calc(8% + {pos * 0.84:.0f}%)"></div></div>'
                f'<div class="kv"><span class="k mono">p25 {_fmt(p25,1)}</span>'
                f'<span class="v mono">p75 {_fmt(p75,1)}</span></div>')
    unit = 'FP/start' if c['bucket'] != 'H' else 'FP/g'
    inner = (f'<div class="big">{_fmt(proj,2)}<span class="u">{unit}</span></div>{band}'
             + _kv('rest-of-season rank', f'#{_fmt(m["rank"],0)}')
             + _kv('signal', h(str(m['signal'] or '—')), _word_cls(m['signal']))
             + (_kv('σ', _fmt(m['sigma'], 2)) if m['sigma'] is not None else '')
             + (_kv('data', h(str(m['dq_tag']))) if m['dq_tag'] else ''))
    return _panel('Model — xFP', inner, tag=m['proj_label'] or '')


def _arche_panel(c):
    a = c['arche']
    if not a['have']:
        return _panel('Archetype', '<div class="kv"><span class="k">not in panel</span></div>')
    extra = ''
    if c['bucket'] != 'H' and (a['velo_tier'] or a['stuff_subtype']):
        extra = _kv('velo / stuff', f'{h(str(a["velo_tier"] or "—"))} · {h(str(a["stuff_subtype"] or "—"))}')
    inner = (f'<div class="big">{h(str(a["label"] or "—"))}</div>'
             + _kv('overall (20-80)', _fmt(a['overall'], 0))
             + _kv('cell', f'<span class="mono">{h(str(a["cell"] or "—"))}</span>')
             + _kv('trajectory', h(str(a['traj'] or '—')), _word_cls(a['traj']))
             + _kv('T+1 / T+2', f'{_fmt(a["t1"],1)} / {_fmt(a["t2"],1)}')
             + (_kv('3-yr slope', _fmt(a['slope'], 1), _word_cls('RISING' if (a['slope'] or 0) > 0 else 'DECLINE')) if a['slope'] is not None else '')
             + (_kv('career pct', _pct(a['career_pct'])) if a['career_pct'] is not None else '')
             + _kv('boundary', h(str(a['boundary'] or '—')))
             + (_kv('age tier', h(str(a['age_tier']))) if a['age_tier'] else '')
             + extra)
    return _panel('Archetype — 20-80', inner, tag=a['boundary'] or '')


def _boom_panel(c):
    b = c['boom']
    if b['stack'] is None and b['boom_rate'] is None:
        return ''
    stk = b['stack']
    bar = ''
    if b['boom_rate'] is not None:
        bar = (f'<div class="bar"><i class="pos" style="width:{min(max(b["boom_rate"],0),1)*100:.0f}%"></i></div>')
    inner = (f'<div class="big">{_fmt(stk,0)}<span class="u">/4 stack</span></div>{bar}'
             + (_kv('boom rate', _pct(b['boom_rate']), 'pos') if b['boom_rate'] is not None else '')
             + (_kv('bust rate', _pct(b['bust_rate']), 'neg') if b['bust_rate'] is not None else '')
             + (_kv('E[FP]', _fmt(b['mean_fp'], 1)) if b['mean_fp'] is not None else ''))
    return _panel('Boom / Bust', inner, tag=(b['tier'] or '') and f"tier {b['tier']}")


def _blend_panel(c):
    bl = c['blend']
    if bl['xfp'] is None and bl['value_tier'] is None and bl['role'] is None:
        return ''
    ci = bl['ci']
    inner = (f'<div class="big">{_fmt(bl["xfp"],2)}<span class="u">blended</span></div>'
             + (_kv('95% CI', f'{_fmt(ci[0],1)} – {_fmt(ci[1],1)}') if ci else '')
             + (_kv('value tier', h(str(bl['value_tier'])), _word_cls(bl['value_tier'])) if bl['value_tier'] else '')
             + (_kv('Δ vs replacement', _fmt(bl['rep_delta'], 1), 'pos' if (bl['rep_delta'] or 0) > 0 else 'neg') if bl['rep_delta'] is not None else '')
             + (_kv('role', h(str(bl['role'] or bl['role_char'] or '—'))) if (bl['role'] or bl['role_char']) else ''))
    return _panel('Blended xFP & Value', inner)


def _process_panel(c):
    lab = c.get('sustainability')
    det = c.get('sustainability_detail')
    if not lab and not det:
        return ''
    body = f'<div class="big" style="font-size:18px;color:var(--{_word_cls(lab) or "text"})">{h(str(lab or "—"))}</div>'
    if det:
        body += f'<div style="color:var(--dim);font-size:13.5px;margin-top:8px;line-height:1.5">{h(str(det))}</div>'
    return _panel('Sustainability / process', body, span=bool(det))


def _sp_panel(c):
    if c['bucket'] != 'SP':
        return ''
    sp = c['sp']
    chips = []
    if sp['recform_tag']:
        chips.append(f'<span class="chip {_word_cls(sp["recform_tag"]) or "on"}">recform {h(str(sp["recform_tag"]))}'
                     + (f' z{_fmt(sp["recform_z"],1)}' if sp['recform_z'] is not None else '') + '</span>')
    if sp['decline_tier']:
        chips.append(f'<span class="chip {_word_cls(sp["decline_tier"])}">decline {h(str(sp["decline_tier"]))}</span>')
    if sp['velo_severity']:
        chips.append(f'<span class="chip neg">velo {h(str(sp["velo_severity"]))}</span>')
    if sp['high_k']:
        chips.append(f'<span class="chip pos">high-K' + (f' z{_fmt(sp["high_k_z"],1)}' if sp['high_k_z'] is not None else '') + '</span>')
    if sp['elite_framer']:
        chips.append('<span class="chip pos">🧊 elite framer</span>')
    if sp['framing_tax']:
        chips.append('<span class="chip neg">⚠ framing tax</span>')
    if sp['il_return']:
        chips.append('<span class="chip warn">🏥 first back from long IL</span>')
    if sp['process_verdict']:
        chips.append(f'<span class="chip {_word_cls(sp["process_verdict"]) or "on"}">process {h(str(sp["process_verdict"]))}</span>')
    if not chips:
        return ''
    return _panel('SP signals', f'<div class="chips">{"".join(chips)}</div>', span=True)


def _card_html(c: dict, idx: int) -> str:
    vcls = c['vclass']
    badge = (f'<span class="badge il">🏥 {h(str(c["il_status"]))}</span>'
             if c['is_il'] else '')
    top = h(str(c.get('verdict_top') or '—'))
    conf = c.get('confidence') or 0
    pl = c['pl']
    stream = (f' · streamer {h(str(pl["stream"]))}' if c['bucket'] == 'SP' and pl['stream'] and pl['stream'] != '—' else '')
    sus = c.get('sustainability')
    summary = _panel(
        'Three-lens read',
        _kv('Pitcher List', f'<span class="mono">{_fmt(pl["rank"])}</span>'
            + (f'<span class="tag" style="color:var(--dim)"> {h(str(pl["date"]))}</span>' if pl['date'] else '') + stream)
        + _kv('Model', f'#{_fmt(c["model"]["rank"],0)} · {_fmt(c["model"]["proj"],2)} · {h(str(c["model"]["signal"] or "—"))}', _word_cls(c['model']['signal']))
        + _kv('Archetype', f'{h(str(c["arche"]["label"] or "—"))} · {_fmt(c["arche"]["overall"],0)} OVR · {h(str(c["arche"]["traj"] or "—"))}', _word_cls(c['arche']['traj']))
        + (_kv('Sustainability', h(str(sus)), _word_cls(sus)) if sus else '')
        + f'<div class="conf"><i style="width:{min(max(conf,0),1)*100:.0f}%"></i></div>'
        + f'<div class="kv"><span class="k">confidence</span><span class="v mono">{conf:.2f} · {_fmt(c.get("n_aligned"),0)}/{_fmt(c.get("n_avail"),0)} agree</span></div>',
        span=True)
    watch = ''.join(f'<span class="chip">{h(str(w))}</span>' for w in c['watch_list'][:10])
    verdict_html = h(str(c.get('verdict') or '')).replace('🏥', '<span class="il">🏥')
    if '🏥' in str(c.get('verdict') or ''):
        verdict_html = verdict_html.replace(':', ':</span>', 1)
    panels = ''.join(p for p in [
        summary, _model_panel(c), _arche_panel(c), _boom_panel(c),
        _blend_panel(c), _process_panel(c), _sp_panel(c),
    ] if p)
    return f"""
<article class="card" data-i="{idx}">
  <div class="vhead">
    <h2>{h(str(c['name']))}</h2>
    <span class="team mono">{h(str(c.get('bucket') or ''))} · {h(str(c.get('team') or ''))}</span>
    <span class="badge {vcls}">{top}</span>{badge}
  </div>
  <div class="verdict">{verdict_html}</div>
  <div class="grid">{panels}</div>
  <div class="rat"><div class="pt">Rationale</div>{h(str(c.get('rationale') or '—'))}</div>
  {f'<div class="rat"><div class="pt">Watch</div><div class="chips">{watch}</div></div>' if watch else ''}
</article>"""


def _rail_html(cards: list[dict]) -> str:
    out = []
    last_bucket = None
    labels = {'H': 'Hitters', 'SP': 'Starting Pitchers', 'RP': 'Relievers'}
    for c in cards:
        if c.get('bucket') != last_bucket:
            last_bucket = c.get('bucket')
            out.append(f'<div class="grp">{labels.get(last_bucket, last_bucket or "")}</div>')
        vt = h(str(c['blend'].get('value_tier') or c.get('verdict_top') or ''))
        out.append(
            f'<button><span class="dot {c["vclass"]}"></span>{h(str(c["name"]))}'
            f'<span class="vt">{vt}</span></button>')
    return '\n'.join(out)


_NAV = ('<nav class="topnav"><a href="index.html">XFP</a>'
        '<a href="matchup.html">Matchup</a><a href="live_dashboard.html">Live</a>'
        '<a href="player_profiles.html">Profiles</a><a class="current">Triangulate</a></nav>')


def render_page(cards: list[dict]) -> str:
    today = date.today().isoformat()
    n_il = sum(1 for c in cards if c['is_il'])
    if not cards:
        body = '<div class="empty">No triangulate cards — roster empty or names unresolved.</div>'
    else:
        body = f"""
<div class="layout">
  <nav class="rail">{_rail_html(cards)}</nav>
  <section class="main">
    <div class="cyc">
      <button id="prev">← Prev</button><button id="next">Next →</button>
      <span class="pos" id="pos"></span><span class="pos">· ←/→ keys</span>
    </div>
    {''.join(_card_html(c, k) for k, c in enumerate(cards))}
  </section>
</div>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Triangulate — Ligers</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{_CSS}</style></head>
<body>
<div class="topbar"><h1>🔱 Triangulate</h1>
<span class="sub">{len(cards)} players · {n_il} on IL · three-lens read · {today}</span>{_NAV}</div>
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
