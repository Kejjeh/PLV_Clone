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
import math
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

OUT = ROOT / 'data' / 'outputs'


def _warn(section, exc):
    print(f"WARN build_triangulate_dashboard.{section}: {exc}", file=sys.stderr)

# Batch artifacts the canonical triangulate builder persists (another step owns
# writing these). The dashboard READS them to surface the ~40 already-computed
# lens columns that the live triangulate_player() result does not carry. All
# CONTEXT-ONLY (CLAUDE.md #13) — never moves the rh3/rp3/rprs2/blended headline.
#
# Source repoint (audit 2026-07-04): the hidden .tri_* files were written by a
# MANUAL run and froze on 2026-06-22 — published cards mixed a fresh verdict
# with 12-day-old boom%/bust%/trajectory. Read the freshest NIGHTLY batch
# instead (shape-compatible, ~592 players incl. floor fields), falling back to
# the legacy manual file only when no nightly exists.


def _freshest_nightly():
    import glob as _glob
    import os as _os
    import time as _time
    cands = _glob.glob(str(ROOT / 'data' / 'research' / 'triangulate_universe'
                           / 'triangulate_nightly_*.json'))
    if not cands:
        return None
    newest = max(cands, key=_os.path.getmtime)
    age_h = (_time.time() - _os.path.getmtime(newest)) / 3600.0
    if age_h > 48:
        print(f'  ⚠ freshest nightly batch is {age_h:.0f}h old ({newest}) — '
              'enrichment may be stale')
    from pathlib import Path as _P
    return _P(newest)


_BATCH_JSON = _freshest_nightly() or (ROOT / 'data' / 'research' / '.tri_team_fa_out.json')
_BATCH_CSV = ROOT / 'data' / 'research' / '.tri_grouped.csv'

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


def _parse_domains(s):
    """'CONTACT=65;POWER=74;DISCIPLINE=61' / 'STUFF:+1;MOVEMENT:-1' -> [(name, val)]."""
    out = []
    s = _txt(s)
    if not s:
        return out
    for part in s.split(';'):
        part = part.strip()
        if not part:
            continue
        sep = '=' if '=' in part else (':' if ':' in part else None)
        if not sep:
            continue
        k, _, v = part.partition(sep)
        out.append((k.strip(), v.strip()))
    return out


def load_batch_lens() -> dict:
    """Build {player_name: lens_dict} from the canonical batch artifacts.

    Merges the nested-rich JSON (trajectory.points / boom_bust.last arrays) with
    the wide CSV (traj_* / bb_* / split_* / xstat_* / ha_* / tto_* scalars + the
    canonical `group` column). Returns {} (never raises) if the batch files are
    missing, so the dashboard degrades to live-only rendering. Pure read — these
    fields are display/context only and never feed the headline number.
    """
    out: dict[str, dict] = {}
    jrec: dict[str, dict] = {}
    try:
        if _BATCH_JSON.exists():
            data = json.loads(_BATCH_JSON.read_text(encoding='utf-8'))
            for p in data.get('players', []):
                nm = p.get('name')
                if nm:
                    jrec[str(nm)] = p
    except Exception as e:
        _warn('load_batch_lens.json', e)
        jrec = {}
    crows: dict[str, dict] = {}
    try:
        if _BATCH_CSV.exists():
            import csv
            with _BATCH_CSV.open(encoding='utf-8', newline='') as fh:
                for row in csv.DictReader(fh):
                    nm = row.get('player_name')
                    if nm:
                        crows[str(nm)] = row
    except Exception as e:
        _warn('load_batch_lens.csv', e)
        crows = {}

    for nm in set(jrec) | set(crows):
        j = jrec.get(nm, {})
        r = crows.get(nm, {})
        bucket = _txt(j.get('bucket')) or _txt(r.get('bucket')) or 'H'
        # canonical group: prefer the batch `position_group`/`group` column; else
        # derive once via the canonical seam (never re-derive the taxonomy here).
        grp = _txt(j.get('position_group')) or _txt(r.get('position_group')) or _txt(r.get('group'))
        if grp not in GROUP_RANK:
            grp = _group_from_seam(nm, bucket, j, r)
        out[nm] = {
            'bucket': bucket,
            'group': grp,
            # in-season trajectory arc
            'traj': {
                'n': _num(r.get('traj_n')),
                'cadence': _txt(r.get('traj_cadence')),
                'first_label': _txt(r.get('traj_first_label')),
                'last_label': _txt(r.get('traj_last_label')),
                'ovr_first': _num(r.get('traj_ovr_first')),
                'ovr_last': _num(r.get('traj_ovr_last')),
                'ovr_delta': _num(r.get('traj_ovr_delta')),
                'last_archetype': _txt(r.get('traj_last_archetype')),
                'dom_last': _parse_domains(r.get('traj_dom_last')),
                'dom_deltas': _parse_domains(r.get('traj_dom_deltas')),
                'points': (j.get('trajectory') or {}).get('points') or [],
                'domains': (j.get('trajectory') or {}).get('domains') or [],
            },
            # 4-cell context lenses (the 4 validated signals)
            'ctx': {
                'stuff_plus': _num(r.get('stuff_plus')) if _num(r.get('stuff_plus')) is not None else _num(j.get('stuff_plus')),
                'stuff_ros': _num(r.get('stuff_proj_ros_fp')) if _num(r.get('stuff_proj_ros_fp')) is not None else _num(j.get('stuff_proj_ros_fp')),
                'stuff_gap': _num(r.get('stuff_breakout_gap')) if _num(r.get('stuff_breakout_gap')) is not None else _num(j.get('stuff_breakout_gap')),
                'floor_tier': _txt(r.get('floor_tier')) or _txt(j.get('floor_tier')),
                'floor_bust': _num(r.get('floor_bust_prob')) if _num(r.get('floor_bust_prob')) is not None else _num(j.get('floor_bust_prob')),
                'trend_tag': _txt(r.get('trend_tag')) or _txt(j.get('trend_tag')),
                'shadow_grade': _num(r.get('shadow_grade')) if _num(r.get('shadow_grade')) is not None else _num(j.get('shadow_grade')),
                'shadow_verdict': _txt(r.get('shadow_verdict')) or _txt(j.get('shadow_verdict')),
            },
            # advanced (collapsible) — platoon / expected-vs-actual / home-road / TTO
            'split': {
                'dominant': _txt(r.get('split_dominant')),
                'rate_L': _num(r.get('split_rate_vs_L')), 'rate_R': _num(r.get('split_rate_vs_R')),
                'lift_L': _num(r.get('split_lift_vs_L_pct')), 'lift_R': _num(r.get('split_lift_vs_R_pct')),
                'pa_L': _num(r.get('split_pa_vs_L')), 'pa_R': _num(r.get('split_pa_vs_R')),
            },
            'xstat': {
                'xwoba': _num(r.get('xstat_xwoba')), 'woba': _num(r.get('xstat_woba')),
                'gap': _num(r.get('xstat_gap')), 'regression': _txt(r.get('xstat_regression')),
                'vL_xwoba': _num(r.get('xstat_vs_L_xwoba')), 'vL_woba': _num(r.get('xstat_vs_L_woba')),
                'vL_reg': _txt(r.get('xstat_vs_L_reg')), 'vL_pa': _num(r.get('xstat_vs_L_pa')),
                'vR_xwoba': _num(r.get('xstat_vs_R_xwoba')), 'vR_woba': _num(r.get('xstat_vs_R_woba')),
                'vR_reg': _txt(r.get('xstat_vs_R_reg')), 'vR_pa': _num(r.get('xstat_vs_R_pa')),
            },
            'ha': {
                'dominant': _txt(r.get('ha_dominant')),
                'rate_home': _num(r.get('ha_rate_home')), 'rate_away': _num(r.get('ha_rate_away')),
                'lift_home': _num(r.get('ha_lift_home_pct')), 'lift_away': _num(r.get('ha_lift_away_pct')),
            },
            'tto': {
                'tier': _txt(r.get('tto_tier')), 'penalty': _num(r.get('tto_penalty')),
                'r1': _num(r.get('tto1_rate')), 'r3': _num(r.get('tto3_rate')),
            },
            # boom/bust window label + actuals (window label sits next to the numbers)
            'bb': {
                'window': _txt(r.get('bb_window')) or _txt(j.get('boom_window')),
                'n': _num(r.get('bb_n')), 'mean': _num(r.get('bb_mean')), 'std': _num(r.get('bb_std')),
                'boom_pct': _num(r.get('bb_boom_pct')), 'bust_pct': _num(r.get('bb_bust_pct')),
                'min': _num(r.get('bb_min')), 'max': _num(r.get('bb_max')),
                'l3_mean': _num(r.get('bb_l3_mean')), 'trend': _txt(r.get('bb_trend')),
                'last': (j.get('boom_bust') or {}).get('last') or [],
            },
        }
    return out


def _group_from_seam(name, bucket, jrec, crow) -> str:
    """Single canonical group via plv_clone.positions when the batch did not emit
    one. Pulls sv/hld/position/slots from whatever the batch rows carry; falls
    back gracefully (RP with no sv/hld -> SETUP). Never re-derives the taxonomy."""
    pl = {}
    for src in (crow, jrec):
        for k in ('position', 'primary_position', 'gpos', 'eligible_slots',
                  'eligibleSlots', 'sv_to', 'hld_to', 'saves', 'holds', 'role_lag1'):
            if k in src and src.get(k) not in (None, ''):
                pl.setdefault(k, src.get(k))
    b = (bucket or 'H').upper()
    seam_bucket = 'SP' if b == 'SP' else ('RP' if b == 'RP' else 'H')
    try:
        return position_group(pl, bucket=seam_bucket, rp_row=pl)
    except Exception as e:
        _warn(f'group_from_seam({name})', e)
        return {'SP': 'SP', 'RP': 'SETUP'}.get(b, 'UTIL')


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


def _resolve_group(c: dict, lens: dict | None) -> str:
    """Canonical position group for a card: batch lens `group` first, else derive
    via the canonical seam from the live card's bucket. Never re-derives taxonomy."""
    if lens and lens.get('group') in GROUP_RANK:
        return lens['group']
    return _group_from_seam(c.get('name'), c.get('bucket'), {}, {})


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
    return _panel('In-season trajectory', arc + sub + last_arch + rows, tag=tag)


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
    return f"""
<article class="card" data-i="{idx}">
  <div class="vhead">
    <h2>{h(str(c['name']))}</h2>
    <span class="team mono">{h(str(grp_lab))} · {h(str(c.get('team') or ''))}</span>
    <span class="badge {vcls}">{top}</span>{badge}
  </div>
  <div class="verdict">{verdict_html}</div>
  <div class="grid">{panels}</div>
  {advanced}
  <div class="rat"><div class="pt">Rationale</div>{h(str(c.get('rationale') or '—'))}</div>
  {f'<div class="rat"><div class="pt">Watch</div><div class="chips">{watch}</div></div>' if watch else ''}
</article>"""


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


from lib.dashboard_chrome import topnav as _topnav  # noqa: E402
_NAV = _topnav('triangulate')  # unified nav owner (item 8) — was hand-copied


# ---------------------------------------------------------------- FA section
# Second rail section (2026-07-18): every FA from the freshest NIGHTLY batch,
# grouped by the same canonical position taxonomy, collapsed <details> per
# group so 500+ rows aren't all visible at once. Sorted within group by
# in-season archetype OVERALL (the "latest overall" read), then headline proj.
# FA cards render through the SAME _card_html as roster cards (user feedback
# 2026-07-18: "cards must look exactly the same") — the card dict is built
# from batch fields instead of a live triangulate_player() call, so fields the
# batch doesn't carry (confidence, watch list, p25/p75 band, value tier)
# gracefully render as the panels' own empty states.

def _fa_card_from_batch(j: dict, lens: dict | None) -> dict:
    bucket = _txt(j.get('bucket')) or 'H'
    il_status = _txt(j.get('il_status'))
    boom_none = {'stack': None, 'tier': None, 'boom_rate': None,
                 'bust_rate': None, 'mean_fp': None, 'components': None}
    c = {
        'name': j.get('name'), 'bucket': bucket, 'team': j.get('team'),
        'verdict': j.get('verdict'),
        'verdict_top': _txt(j.get('category')) or _txt(j.get('verdict')),
        'override_tag': j.get('override_tag'),
        'il_status': il_status,
        'is_il': bool(il_status) and str(il_status).upper() in _IL_STATES,
        'confidence': None, 'n_aligned': None, 'n_avail': None,
        'rationale': j.get('rationale'), 'watch_list': [],
        'sustainability': None, 'sustainability_detail': None,
        'pl_rank': j.get('pl_rank'), 'model_rank': j.get('model_rank'),
        'model_proj': _num(j.get('model_proj')),
        'model_signal': _txt(j.get('model_signal')),
        'arche_label': _txt(j.get('arche_label')),
        'arche_overall': _num(j.get('arche_overall')),
        'arche_traj': _txt(j.get('arche_traj')),
        'arche_t1': _num(j.get('arche_t1_fp')),
        'blended_xfp': _num(j.get('blended_xfp')),
        'pl': {'rank': j.get('pl_rank'), 'date': None,
               'stream': None, 'stream_opp': None},
        'model': {'rank': j.get('model_rank'), 'proj': _num(j.get('model_proj')),
                  'proj_label': _txt(j.get('model_proj_label')),
                  'signal': _txt(j.get('model_signal')),
                  'p25': None, 'p75': None, 'sigma': None, 'dq_tag': None},
        'arche': {'have': bool(j.get('arche_have')),
                  'label': _txt(j.get('arche_label')),
                  'overall': _num(j.get('arche_overall')),
                  'cell': _txt(j.get('arche_cell')),
                  'traj': _txt(j.get('arche_traj')),
                  't1': _num(j.get('arche_t1_fp')), 't2': None, 'slope': None,
                  'career_pct': _num(j.get('arche_career_pct')),
                  'boundary': None, 'age_tier': None, 'velo_tier': None,
                  'stuff_subtype': None},
        'boom': dict(boom_none),
        'sp': {'decline_tier': None, 'velo_severity': None, 'velo_yoy_flag': None,
               'recform_tag': None, 'recform_z': None, 'recform_mean': None,
               'high_k': False, 'high_k_z': None, 'elite_framer': False,
               'framing_tax': False, 'il_return': False, 'process_verdict': None},
        'blend': {'xfp': _num(j.get('blended_xfp')), 'ci': None,
                  'value_tier': None, 'rep_delta': None, 'role': None,
                  'role_char': None, 'ros': None},
    }
    c['vclass'] = _verdict_class(c)
    c['lens'] = lens
    c['group'] = (j.get('position_group') if j.get('position_group') in GROUP_RANK
                  else _resolve_group(c, lens))
    return c


def load_fa_rows(exclude_names: set[str] | None = None) -> list[dict]:
    """FA rows from the freshest nightly batch. `exclude_names` guards against
    batch-lag: a player added to the roster AFTER the nightly ran still carries
    owner_team='FA' in the batch (Mead 2026-07-18 canonical) — the live roster
    card wins and the stale FA row is dropped."""
    try:
        batch = json.loads(_BATCH_JSON.read_text(encoding='utf-8'))
    except Exception as e:
        _warn('fa_rows', e)
        return []
    excl = {str(n).lower() for n in (exclude_names or set())}
    rows = [r for r in batch.get('players', [])
            if (r.get('owner_team') == 'FA')
            and str(r.get('name', '')).lower() not in excl
            and (r.get('model_rank') is not None or r.get('pl_rank') is not None
                 or r.get('arche_have'))]
    present = order_groups(r.get('position_group') for r in rows if r.get('position_group'))
    grank = {g: i for i, g in enumerate(present)}

    def key(r):
        ov = r.get('arche_overall')
        hp = r.get('headline_proj')
        return (grank.get(r.get('position_group'), len(present)),
                -(ov if isinstance(ov, (int, float)) else -1),
                -(hp if isinstance(hp, (int, float)) else -999))
    return sorted(rows, key=key)


def _fa_rail_html(fa_cards: list[dict]) -> str:
    """Collapsible FA rail: <details> per position group; button order MUST
    match the FA card render order (index-based nav)."""
    out = [f'<div class="fa-head">FREE AGENTS <span class="mono">({len(fa_cards)})</span></div>']
    cur = None
    for c in fa_cards:
        grp = c.get('group')
        if grp != cur:
            if cur is not None:
                out.append('</details>')
            cur = grp
            n_grp = sum(1 for x in fa_cards if x.get('group') == grp)
            out.append(f'<details class="fa-grp"><summary>{h(str(_GROUP_LABELS.get(grp, grp or "—")))}'
                       f' <span class="mono">({n_grp})</span></summary>')
        ov = c['arche'].get('overall')
        vt = f'{ov:.0f}' if isinstance(ov, (int, float)) else '—'
        out.append(f'<button><span class="dot {c["vclass"]}"></span>{h(str(c["name"]))}'
                   f'<span class="vt">{vt}</span></button>')
    if cur is not None:
        out.append('</details>')
    return '\n'.join(out)


_FA_CSS = """
.fa-head{padding:18px 16px 6px;color:var(--accent);font-size:11px;letter-spacing:.14em;
 font-weight:600;border-top:1px solid var(--line);margin-top:12px}
.fa-grp summary{padding:9px 16px;cursor:pointer;color:var(--dim);font-size:11.5px;
 letter-spacing:.08em;list-style:none;user-select:none}
.fa-grp summary:hover{background:var(--panel);color:var(--accent)}
.fa-grp summary::before{content:'▸ '}
.fa-grp[open] summary::before{content:'▾ '}
"""


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
