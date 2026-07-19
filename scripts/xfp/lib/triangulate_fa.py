"""triangulate_fa.py — FA-section loaders + batch-artifact resolution for the
triangulate dashboard.

Split verbatim from build_triangulate_dashboard.py (2026-07-19 audit item 11);
the dashboard re-exports these names for external callers.
"""
from __future__ import annotations

import json
from html import escape as h

from plv_clone.paths import ROOT
from plv_clone.positions import GROUP_RANK, order_groups, position_group

from .triangulate_cards import _GROUP_LABELS, _IL_STATES, _num, _txt, _verdict_class
from .triangulate_links import _warn

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
    # the *_cards.json sidecar (full result-dict store, --cards-out) shares the
    # prefix — it is NOT the batch payload; never let it win the glob.
    cands = [c for c in cands if not c.endswith('_cards.json')]
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
# The CSV sibling of the nightly JSON carries the 49 flat lens columns
# (traj_*/bb_*/split_*/xstat_*/ha_*/tto_*). The legacy .tri_grouped.csv FROZE
# on 2026-06-22 — reading it pinned every card's in-season trajectory at
# 04-25→06-20 no matter how fresh the snapshots were (fixed 2026-07-18).
_NIGHTLY_CSV = (_BATCH_JSON.with_suffix('.csv')
                if _BATCH_JSON.name.startswith('triangulate_nightly') else None)
_BATCH_CSV = (_NIGHTLY_CSV if _NIGHTLY_CSV is not None and _NIGHTLY_CSV.exists()
              else ROOT / 'data' / 'research' / '.tri_grouped.csv')


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


def _resolve_group(c: dict, lens: dict | None) -> str:
    """Canonical position group for a card: batch lens `group` first, else derive
    via the canonical seam from the live card's bucket. Never re-derives taxonomy."""
    if lens and lens.get('group') in GROUP_RANK:
        return lens['group']
    return _group_from_seam(c.get('name'), c.get('bucket'), {}, {})


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


def load_fa_cards_store() -> dict:
    """Full-fidelity FA card store: {name: result-dict} in the LIVE-card schema
    (triangulate_core.assemble_result), written by run_triangulate --cards-out
    alongside the nightly batch (refresh step 4.72b). Hydrating from this store
    makes FA cards identical to roster cards at ~zero cost — no per-FA engine
    re-run. Returns {} when absent (pre-store nights) so callers fall back to
    the flat batch card."""
    if not _BATCH_JSON.name.startswith('triangulate_nightly'):
        return {}
    store_path = _BATCH_JSON.with_name(_BATCH_JSON.stem + '_cards.json')
    if not store_path.exists():
        return {}
    try:
        return json.loads(store_path.read_text(encoding='utf-8'))
    except Exception as e:
        _warn('fa_cards_store', e)
        return {}


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
