"""triangulate_cards.py — card-data extraction + per-card HTML render for the
triangulate dashboard.

Split verbatim from build_triangulate_dashboard.py (2026-07-19 audit item 11);
the dashboard re-exports these names for external callers (tests import
build_card_data from build_triangulate_dashboard).
"""
from __future__ import annotations

import math
from html import escape as h

from plv_clone.positions import ALL_POSITION_GROUPS

from .triangulate_links import _profile_link

# Group display labels (canonical taxonomy) + the order_groups()-driven ordering.
_GROUP_LABELS = dict(ALL_POSITION_GROUPS)
_GROUP_LABELS.update({  # short rail headers
    'C': 'Catchers', '1B/3B': 'Corner Infield', '2B/SS': 'Middle Infield',
    'OF': 'Outfield', 'UTIL': 'UTIL', 'DH': 'DH / non-fielder',
    'SP': 'Starting Pitchers', 'CLOSER': 'Closers', 'SETUP': 'Setup / Middle Relief',
})

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


def _num(v):
    """CSV/JSON scalar -> float|None (NaN, '', '—', 'nan' all collapse to None)."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s in ('', '—', 'nan', 'NaN', 'None'):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _txt(v):
    """CSV/JSON scalar -> stripped str|None (NaN/empty/sentinels collapse to None)."""
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return None if s in ('', '—', 'nan', 'NaN', 'None') else s


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
    lens = c.get('lens')
    bb = lens['bb'] if lens else None
    # the boom/bust actuals window label (L8/L15/L21) sits next to the numbers
    window = (bb or {}).get('window') if bb else None
    has_actuals = bool(bb) and (bb.get('mean') is not None or bb.get('boom_pct') is not None)
    if b['stack'] is None and b['boom_rate'] is None and not has_actuals:
        return ''
    stk = b['stack']
    bar = ''
    if b['boom_rate'] is not None:
        bar = (f'<div class="bar"><i class="pos" style="width:{min(max(b["boom_rate"],0),1)*100:.0f}%"></i></div>')
    inner = (f'<div class="big">{_fmt(stk,0)}<span class="u">/4 stack</span></div>{bar}'
             + (_kv('boom rate', _pct(b['boom_rate']), 'pos') if b['boom_rate'] is not None else '')
             + (_kv('bust rate', _pct(b['bust_rate']), 'neg') if b['bust_rate'] is not None else '')
             + (_kv('E[FP]', _fmt(b['mean_fp'], 1)) if b['mean_fp'] is not None else ''))
    # actuals (boom-bust-history window) folded in with the window label as caption
    if has_actuals:
        win_cap = f'<div class="bb-win mono">actuals · {h(str(window or "recent"))}</div>'
        inner += win_cap
        inner += (_kv('mean / std', f'{_fmt(bb["mean"],1)} ± {_fmt(bb["std"],1)}')
                  if bb.get('mean') is not None else '')
        inner += (_kv('boom% / bust%', f'{_fmt(bb["boom_pct"],0)}% / {_fmt(bb["bust_pct"],0)}%',
                      'pos' if (bb.get('boom_pct') or 0) >= (bb.get('bust_pct') or 0) else 'neg')
                  if bb.get('boom_pct') is not None else '')
        inner += (_kv('L3 mean', _fmt(bb['l3_mean'], 1),
                      _word_cls('RISING' if (bb.get('trend') or '').upper() == 'UP' else 'DECLINE'
                                if (bb.get('trend') or '').upper() == 'DOWN' else ''))
                  if bb.get('l3_mean') is not None else '')
        if bb.get('trend'):
            inner += _kv('trend', h(str(bb['trend'])),
                         _word_cls('RISING' if bb['trend'].upper() == 'UP'
                                   else 'DECLINE' if bb['trend'].upper() == 'DOWN' else ''))
    tag = (f"tier {b['tier']}" if b['tier'] else (window or ''))
    return _panel('Boom / Bust', inner, tag=tag)


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


def _delta_cls(v):
    """Numeric delta -> pos/neg/'' colour class."""
    if v is None:
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


def _sgn(v, nd=0):
    if v is None:
        return '—'
    return f'{v:+.{nd}f}'


_TRAJ_COLORS = ['#8aa8c4', '#7fb069', '#d4a945']  # domain lines (OVR = accent)


def _traj_svg(t: dict) -> str:
    """Inline SVG line chart of the in-season arc (2026-07-18, ported from the
    profiles page's trajectory chart): OVERALL (accent, bold) + rated domain
    lines over the weekly snapshot points, fixed 20-80 y-scale, y=50 guide."""
    pts = t.get('points') or []
    if len(pts) < 2:
        return ''
    keys = [k for k in pts[0] if k not in ('label', 'archetype', 'OVERALL')]
    series = ['OVERALL'] + keys[:3]
    W, H, P = 252, 92, 8
    n = len(pts)
    xs = [P + (W - 2 * P) * k / (n - 1) for k in range(n)]

    def y(v):
        v = min(max(v, 20), 80)
        return P + (H - 2 * P) * (1 - (v - 20) / 60)

    y50 = y(50)
    parts = [f'<line x1="{P}" y1="{y50:.1f}" x2="{W-P}" y2="{y50:.1f}" '
             f'stroke="var(--line)" stroke-dasharray="3 3" stroke-width="1"/>']
    legend = []
    for i, name in enumerate(series):
        vals = [_num(p.get(name)) for p in pts]
        if any(v is None for v in vals):
            continue
        col = 'var(--accent)' if name == 'OVERALL' else _TRAJ_COLORS[(i - 1) % 3]
        wid = '2' if name == 'OVERALL' else '1.2'
        op = '1' if name == 'OVERALL' else '.72'
        path = ' '.join(f'{x:.1f},{y(v):.1f}' for x, v in zip(xs, vals))
        parts.append(f'<polyline points="{path}" fill="none" stroke="{col}" '
                     f'stroke-width="{wid}" opacity="{op}"/>')
        legend.append(f'<span class="tl-item" style="color:{col}">'
                      f'{h(name.title() if name != "OVERALL" else "OVR")}</span>')
    if len(parts) <= 1:
        return ''
    lo_lab, hi_lab = h(str(pts[0].get('label') or '')), h(str(pts[-1].get('label') or ''))
    return (f'<svg class="traj-chart" viewBox="0 0 {W} {H}" preserveAspectRatio="none">'
            + ''.join(parts) + '</svg>'
            f'<div class="tl-row"><span class="mono tl-x">{lo_lab}</span>'
            + ''.join(legend)
            + f'<span class="mono tl-x">{hi_lab}</span></div>')


def _trajectory_panel(c: dict) -> str:
    """In-season trajectory arc: First->Last OVERALL + labels, OVERALL delta, last
    archetype, and the 3-domain last values + deltas (context-only)."""
    lens = c.get('lens')
    if not lens:
        return ''
    t = lens['traj']
    if t['ovr_first'] is None and t['ovr_last'] is None and not t['dom_last']:
        return ''
    first_l = t['first_label'] or 'first'
    last_l = t['last_label'] or 'last'
    arc = (f'<div class="big">{_fmt(t["ovr_first"],0)} '
           f'<span class="u" style="font-size:18px;color:var(--dim)">→</span> '
           f'{_fmt(t["ovr_last"],0)}<span class="u">OVERALL</span></div>')
    sub = (f'<div class="kv"><span class="k mono">{h(str(first_l))} → {h(str(last_l))}</span>'
           f'<span class="v {_delta_cls(t["ovr_delta"])}">{_sgn(t["ovr_delta"])}</span></div>')
    rows = ''
    deltas = {k: v for k, v in t['dom_deltas']}
    for name, val in t['dom_last']:
        d = deltas.get(name)
        dnum = _num(d)
        dtxt = (f' <span class="{_delta_cls(dnum)}">({d})</span>') if d is not None else ''
        rows += (f'<div class="kv"><span class="k">{h(name.title())}</span>'
                 f'<span class="v mono">{h(str(val))}{dtxt}</span></div>')
    if not rows and deltas:
        for name, d in t['dom_deltas']:
            dnum = _num(d)
            rows += (f'<div class="kv"><span class="k">{h(name.title())}</span>'
                     f'<span class="v mono {_delta_cls(dnum)}">{h(str(d))}</span></div>')
    last_arch = (_kv('last archetype', f'<span class="mono">{h(str(t["last_archetype"]))}</span>')
                 if t['last_archetype'] else '')
    cad = (t['cadence'] or '')
    n = t['n']
    tag = (f'{int(n)} pts · {cad}' if n is not None else cad)
    chart = _traj_svg(t)
    return _panel('In-season trajectory', arc + sub + chart + last_arch + rows, tag=tag)


def _ctx_cell(label, value, sub='', cls=''):
    v = value if value not in (None, '') else '—'
    sub_html = f'<div class="cc-sub mono">{sub}</div>' if sub else ''
    return (f'<div class="cc"><div class="cc-t">{h(label)}</div>'
            f'<div class="cc-v {cls}">{v}</div>{sub_html}</div>')


def _context_panel(c: dict) -> str:
    """4-cell validated-lens context: Stuff+, SP-floor, physical trend, shadow grade.
    SPs show all 4; hitters/RPs show whichever apply (trend always; stuff/floor/
    shadow are SP signals). Context-only (CLAUDE.md #13)."""
    lens = c.get('lens')
    if not lens:
        return ''
    ctx = lens['ctx']
    is_sp = c.get('bucket') == 'SP'
    cells = []
    if is_sp:
        sp_sub = ''
        if ctx['stuff_ros'] is not None:
            sp_sub = f'RoS {_fmt(ctx["stuff_ros"],1)} FP'
        if ctx['stuff_gap'] is not None:
            sp_sub += (' · ' if sp_sub else '') + f'gap {_sgn(ctx["stuff_gap"])}'
        cells.append(_ctx_cell('Stuff+', _fmt(ctx['stuff_plus'], 0), sp_sub))
        floor_cls = {'SAFE': 'pos', 'RISKY': 'neg', 'MODERATE': 'warn'}.get(
            (ctx['floor_tier'] or '').upper(), '')
        floor_sub = f'bust {_fmt(ctx["floor_bust"],0)}%' if ctx['floor_bust'] is not None else ''
        cells.append(_ctx_cell('Floor', h(str(ctx['floor_tier'] or '—')), floor_sub, floor_cls))
    # physical trend (all roles)
    trend = ctx['trend_tag']
    if trend or is_sp:
        cells.append(_ctx_cell('Physical trend', h(str(trend or '—')), '', _word_cls(trend)))
    if is_sp:
        sh_cls = _word_cls(ctx['shadow_verdict']) or (
            'pos' if (ctx['shadow_grade'] or 0) >= 55 else ('neg' if (ctx['shadow_grade'] or 99) < 45 else ''))
        sh_sub = h(str(ctx['shadow_verdict'])) if ctx['shadow_verdict'] else ''
        cells.append(_ctx_cell('Shadow scout', _fmt(ctx['shadow_grade'], 0), sh_sub, sh_cls))
    cells = [x for x in cells if x]
    if not cells:
        return ''
    return _panel('Context lenses', f'<div class="cctx">{"".join(cells)}</div>',
                  tag='Stuff+ / floor / trend / shadow' if is_sp else 'physical trend', span=True)


def _adv_col(header, rows):
    """One column of the advanced panel: a labelled header + its kv rows."""
    return f'<div class="adv-col"><div class="adv-h">{h(header)}</div>{rows}</div>'


def _advanced_panel(c: dict) -> str:
    """Collapsible advanced detail: platoon splits, expected-vs-actual, home/road,
    times-through-order. All context-only; absent values are skipped."""
    lens = c.get('lens')
    if not lens:
        return ''
    sp_, xs, ha, tto = lens['split'], lens['xstat'], lens['ha'], lens['tto']
    blocks = []

    # platoon splits
    if sp_['rate_L'] is not None or sp_['rate_R'] is not None:
        rows = ''
        rows += _kv('vs LHP', f'{_fmt(sp_["rate_L"],3)}'
                    + (f' · lift {_sgn(sp_["lift_L"],1)}%' if sp_['lift_L'] is not None else '')
                    + (f' · {_fmt(sp_["pa_L"],0)} PA' if sp_['pa_L'] is not None else ''),
                    _delta_cls(sp_['lift_L']))
        rows += _kv('vs RHP', f'{_fmt(sp_["rate_R"],3)}'
                    + (f' · lift {_sgn(sp_["lift_R"],1)}%' if sp_['lift_R'] is not None else '')
                    + (f' · {_fmt(sp_["pa_R"],0)} PA' if sp_['pa_R'] is not None else ''),
                    _delta_cls(sp_['lift_R']))
        if sp_['dominant']:
            rows += _kv('dominant side', h(str(sp_['dominant'])))
        blocks.append(_adv_col('Platoon splits', rows))

    # expected vs actual
    if xs['xwoba'] is not None or xs['woba'] is not None:
        rows = _kv('xwOBA / wOBA', f'{_fmt(xs["xwoba"],3)} / {_fmt(xs["woba"],3)}')
        if xs['gap'] is not None:
            rows += _kv('gap (x − actual)', _sgn(xs['gap'], 3), _delta_cls(-xs['gap']))
        if xs['regression']:
            rows += _kv('regression', h(str(xs['regression'])), _word_cls(xs['regression']))
        if xs['vL_xwoba'] is not None or xs['vR_xwoba'] is not None:
            rows += _kv('vs LHP x/actual', f'{_fmt(xs["vL_xwoba"],3)} / {_fmt(xs["vL_woba"],3)}'
                        + (f' ({h(str(xs["vL_reg"]))})' if xs['vL_reg'] else ''))
            rows += _kv('vs RHP x/actual', f'{_fmt(xs["vR_xwoba"],3)} / {_fmt(xs["vR_woba"],3)}'
                        + (f' ({h(str(xs["vR_reg"]))})' if xs['vR_reg'] else ''))
        blocks.append(_adv_col('Expected vs actual', rows))

    # home / road
    if ha['rate_home'] is not None or ha['rate_away'] is not None:
        rows = _kv('home', f'{_fmt(ha["rate_home"],3)}'
                   + (f' · {_sgn(ha["lift_home"],1)}%' if ha['lift_home'] is not None else ''),
                   _delta_cls(ha['lift_home']))
        rows += _kv('away', f'{_fmt(ha["rate_away"],3)}'
                    + (f' · {_sgn(ha["lift_away"],1)}%' if ha['lift_away'] is not None else ''),
                    _delta_cls(ha['lift_away']))
        if ha['dominant']:
            rows += _kv('dominant', h(str(ha['dominant'])))
        blocks.append(_adv_col('Home / road', rows))

    # times through order
    if tto['tier'] or tto['penalty'] is not None:
        rows = ''
        if tto['tier']:
            rows += _kv('TTO tier', h(str(tto['tier'])), _word_cls(tto['tier']))
        if tto['penalty'] is not None:
            rows += _kv('TTO penalty', _sgn(tto['penalty'], 3), _delta_cls(tto['penalty']))
        if tto['r1'] is not None or tto['r3'] is not None:
            rows += _kv('1st / 3rd time rate', f'{_fmt(tto["r1"],3)} / {_fmt(tto["r3"],3)}')
        blocks.append(_adv_col('Times through order', rows))

    if not blocks:
        return ''
    inner = ''.join(blocks)
    return (f'<details class="panel adv span2"><summary class="pt">Advanced '
            f'<span class="tag">platoon · x-vs-actual · home/road · TTO</span></summary>'
            f'<div class="adv-body">{inner}</div></details>')


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
        summary, _model_panel(c), _arche_panel(c), _trajectory_panel(c),
        _boom_panel(c), _blend_panel(c), _process_panel(c),
        _context_panel(c), _sp_panel(c),
    ] if p)
    advanced = _advanced_panel(c)
    grp_lab = _GROUP_LABELS.get(c.get('group'), c.get('group') or '')
    plink = _profile_link(c)
    return f"""
<article class="card" data-i="{idx}">
  <div class="vhead">
    <h2>{h(str(c['name']))}</h2>
    <span class="team mono">{h(str(grp_lab))} · {h(str(c.get('team') or ''))}</span>
    <span class="badge {vcls}">{top}</span>{badge}{plink}
  </div>
  <div class="verdict">{verdict_html}</div>
  <div class="grid">{panels}</div>
  {advanced}
  <div class="rat"><div class="pt">Rationale</div>{h(str(c.get('rationale') or '—'))}</div>
  {f'<div class="rat"><div class="pt">Watch</div><div class="chips">{watch}</div></div>' if watch else ''}
</article>"""
