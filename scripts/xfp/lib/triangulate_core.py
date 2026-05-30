"""Core triangulate analytics: model row, archetype row, verdict synthesis,
4th-lens overrides, and the high-level `triangulate_player` entry point.
"""
from __future__ import annotations
import pandas as pd

from .bucket_dispatch import resolve_player
from .cached_data import _load_projection, _load_archetype
from .pl_cache import pl_rank, pl_streamer_rank


# ---------- model row ----------

def model_row(player: dict) -> dict:
    bucket = player['bucket']
    df = _load_projection(bucket)
    if bucket == 'H':
        m = df[df['batter'] == player['id']]
    else:
        m = df[df['pitcher'] == player['id']]
    if m.empty:
        return {'rank': '—', 'proj': None, 'signal': '—', 'rep_delta': None, 'recform': None}
    r = m.iloc[0]
    if bucket == 'H':
        return {
            'rank': int(r['rank']),
            'proj_label': 'fp/game',
            'proj': float(r['xfp_rh3_per_game']),
            'signal': r['signal'],
            'rep_delta': float(r['replacement_delta']),
            'recform': float(r['recency_form_gap']),
            'extra': f"pa_to={int(r['pa_to'])}",
        }
    if bucket == 'SP':
        return {
            'rank': int(r['rank']),
            'proj_label': 'fp/start',
            'proj': float(r['xfp_rp3_per_start']),
            'signal': r['signal'],
            'rep_delta': float(r['replacement_delta']),
            'recform': float(r['recency_form_gap']),
            'extra': f"gs_to={int(r['gs_to'])}",
        }
    return {
        'rank': int(r['rank']),
        'proj_label': 'xfp_ros',
        'proj': float(r['xfp_ros']),
        'signal': r['signal'],
        'rep_delta': float(r['replacement_delta']),
        'recform': None,
        'extra': f"role={r['role_lag1']} sv_to={int(r.get('sv_to') or 0)} hld_to={int(r.get('hld_to') or 0)}",
    }


# ---------- archetype row ----------

def _is_truthy_flag(v) -> bool:
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        return False
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return bool(v)


def archetype_row(player: dict) -> dict:
    bucket = player['bucket']
    p = _load_archetype(bucket)
    if p is None:
        return {'have': False, 'reason': 'panel missing'}
    id_col = 'batter' if bucket == 'H' else 'pitcher'
    rows = p[p[id_col] == player['id']].sort_values('year')
    if rows.empty:
        return {'have': False, 'reason': 'not in archetype panel (insufficient innings/PA)'}
    cur = rows[rows['year'] == 2026]
    if cur.empty:
        cur = rows.iloc[[-1]]
    r = cur.iloc[0]
    out = {
        'have': True,
        'year': int(r['year']),
        'archetype': r.get('archetype'),
        'cell': r.get('cell'),
        'stuff_subtype': r.get('stuff_subtype'),
        'age': int(r['age']) if pd.notna(r.get('age')) else None,
        'age_tier': r.get('age_tier'),
        'overall': int(r['OVERALL']) if pd.notna(r.get('OVERALL')) else None,
        'traj_flag': r.get('traj_flag'),
        'slope_3yr': r.get('OVERALL_slope_3yr'),
        'career_pct': r.get('OVERALL_career_pct'),
        't1_fp': r.get('t1_fp_projection'),
        't2_fp': r.get('t2_fp_projection'),
        'velo': r.get('avg_velo'),
        'velo_tier': r.get('velo_tier'),
        'boundary_tier': r.get('boundary_tier'),
    }
    if bucket == 'SP':
        out['ratings'] = {'STUFF': int(r['STUFF']), 'MOVEMENT': int(r['MOVEMENT']), 'CONTROL': int(r['CONTROL'])}
        out['pitch_archetype'] = r.get('pitch_archetype')
        for sub in ('SWING_MISS', 'CALLED_STRIKE', 'WALK_AVOID', 'STRIKE_THROWING'):
            if sub in p.columns and pd.notna(r.get(sub)):
                out.setdefault('sub_ratings', {})[sub] = int(r[sub])
        if pd.notna(r.get('career_year')):
            out['career_year'] = int(r['career_year'])
    elif bucket == 'RP':
        out['ratings'] = {'STUFF': int(r['STUFF']), 'CONTROL': int(r['CONTROL']), 'BATTED_BALL': int(r['BATTED_BALL'])}
        out['leverage_tier'] = r.get('leverage_tier')
        out['closer']   = _is_truthy_flag(r.get('CLOSER'))
        out['fireman']  = _is_truthy_flag(r.get('FIREMAN'))
        out['high_lev'] = _is_truthy_flag(r.get('HIGH_LEVERAGE'))
    else:
        for k in ('C', 'P', 'D', 'SB'):
            if k in p.columns:
                out.setdefault('ratings', {})[k] = int(r[k]) if pd.notna(r.get(k)) else None
        if 'SPEED_TOOL' in p.columns and pd.notna(r.get('SPEED_TOOL')):
            out.setdefault('sub_ratings', {})['SPEED_TOOL'] = int(r['SPEED_TOOL'])
    arc = rows.tail(4)[['year', 'archetype', 'OVERALL']]
    out['arc'] = [(int(y), a, int(o) if pd.notna(o) else None) for y, a, o in zip(arc['year'], arc['archetype'], arc['OVERALL'])]
    return out


# ---------- verdict synthesis ----------

def synthesize(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche):
    bucket = player['bucket']
    notes = []
    pl_r = pl_main
    m_r = model.get('rank')
    a_t1 = arche.get('t1_fp') if arche.get('have') else None
    a_traj = arche.get('traj_flag') if arche.get('have') else None
    a_cell = arche.get('cell') if arche.get('have') else None
    a_archetype = arche.get('archetype') if arche.get('have') else None
    overall = arche.get('overall', 50) if arche.get('have') else 50
    label = a_archetype

    if arche.get('have'):
        if a_traj == 'TRENDING_UP' and isinstance(pl_r, int) and isinstance(m_r, int) and (m_r - pl_r) > 50:
            return 'BUY — archetype breakout', f"Archetype TRENDING_UP to {a_archetype} ({a_cell}); PL has caught it (#{pl_r}); model lagging (#{m_r}). Buy before model catches up."
        if a_traj == 'TRENDING_DOWN' and isinstance(pl_r, int) and pl_r <= 50:
            notes.append(f"WARN Archetype TRENDING_DOWN (slope {arche['slope_3yr']:+.1f}) while PL still has him #{pl_r} — sell-high candidate.")
        if a_archetype in ('GENERIC_HR_PRONE', 'FILLER', 'WILD_MID', 'PIT_CHF'):
            notes.append(f"WARN Archetype flag: {a_archetype} — bottom-tier process profile.")
        if a_traj in ('CAREER_LOW',) and arche.get('career_pct', 0) == 0:
            notes.append(f"WARN Career-low season ({arche['career_pct']*100:.0f}% career-percentile).")
        velo_tier = arche.get('velo_tier')
        if velo_tier == 'FINESSE' and a_traj == 'TRENDING_DOWN':
            notes.append("WARN FINESSE velo tier + declining = drop tier.")

    if isinstance(pl_r, int) and isinstance(m_r, int) and arche.get('have'):
        ov = arche.get('overall', 50)
        if pl_r <= 30 and m_r <= 50 and ov >= 55:
            return 'STRONG HOLD/BUY', f"All 3 lenses agree — PL #{pl_r}, model #{m_r}, archetype OVERALL {ov} ({a_archetype}). High conviction."

    if isinstance(pl_r, int) and isinstance(m_r, int):
        gap = m_r - pl_r
        if gap > 60 and arche.get('have') and arche.get('overall', 50) < 50 and a_traj != 'TRENDING_UP':
            return 'FADE — PL chasing outcomes', f"PL #{pl_r} but model #{m_r} and archetype OVERALL {arche['overall']} ({a_archetype}) — process doesn't support PL rank."
        if gap < -50 and arche.get('have') and arche.get('overall', 50) >= 55:
            return 'BUY — model anchored on prior', f"Model #{m_r} but PL #{pl_r} and archetype OVERALL {arche['overall']} ({a_archetype}) — model lagging."

    if arche.get('have') and overall >= 60 and a_traj == 'TRENDING_UP' and \
       ((isinstance(pl_r, int) and pl_r <= 80) or (isinstance(m_r, int) and m_r <= 80)):
        return 'BUY — process upgrade', (
            f"Archetype {label} OVERALL {overall} TRENDING_UP; ranked top-80 by at least one outcome lens. "
            f"Process leads the outcomes."
        )

    if (pl_r in ('UR', '—')) and isinstance(m_r, int) and m_r <= 80 \
       and arche.get('have') and overall >= 60:
        return 'BUY — under-the-radar', (
            f"PL hasn't ranked him but model #{m_r} and archetype OVERALL {overall} ({label}) both endorse."
        )

    if (not arche.get('have')) and isinstance(m_r, int) and m_r <= 60 \
       and (model.get('rep_delta') or 0) > 0:
        rd = model.get('rep_delta') or 0.0
        return 'BUY — outcomes only (no archetype)', (
            f"Model #{m_r} with rep_d {rd:+.2f}; insufficient IP/PA for archetype profile yet."
        )

    if not notes:
        return 'MIXED — see profile', "Signals don't converge to a single verdict; weigh the rate metrics against the trajectory before acting."
    return 'CAUTION', ' '.join(notes)


# ---------- 4th-lens overrides ----------
#
# Calibrated 2026-05-30 via scripts/xfp/calibrate_overrides.py against the full
# archetype career panels. Report: docs/triangulate_calibration_2026.md.
#
# - SPEED_PROFILE (Override A): REJECTED. At SB/SPEED ≥ 60 the override actually
#   UNDERPERFORMED the comparison set by 2.4pp on T+1 bounce rate (N=321). The
#   Trea Turner case-study intuition did not generalize. Removed from production.
# - POST_TJ_RAMP (Override B): KEPT but flagged unvalidated. N=13 in the strict
#   trigger set is below the validation threshold; named comps (Eovaldi 2019,
#   Quintana 2021, Bradish 2026) make the rule plausible but not empirically
#   confirmed. Re-validate when panel grows.
# - PROCESS_INTACT (Override C): TIGHTENED from rank ≤ 50 to rank ≤ 25. The lift
#   at top-25 is small (+2.2pp) but cleaner than at ranks 26-50, which add noise.
#   Named comps at top-25 (Kershaw 2015, Kluber 2016, Sale 2016, Scherzer 2016,
#   Glasnow 2025) all delivered strong T+1 bounces.

def apply_overrides(verdict, rationale, player, arche, model):
    if not arche.get('have'):
        return verdict, rationale, None
    is_bearish = verdict.startswith('FADE') or verdict.startswith('CAUTION')
    if not is_bearish:
        return verdict, rationale, None

    bucket = player['bucket']
    sub = arche.get('sub_ratings', {}) or {}

    # Override A (SPEED_PROFILE) — REMOVED after empirical calibration showed
    # negative lift. Kept in the rule book as documentation; do not re-enable
    # without re-running calibrate_overrides.py on fresh data.

    # Override B — POST_TJ_RAMP (SP; unvalidated, n=13 — kept on case-study merit)
    if bucket == 'SP':
        sm = sub.get('SWING_MISS')
        wa = sub.get('WALK_AVOID')
        cy = arche.get('career_year') or 0
        cp = arche.get('career_pct')
        is_career_low = (cp is not None and not pd.isna(cp) and cp <= 0.0)
        walk_driven = arche.get('archetype') in ('WILD_MID', 'FILLER', 'GENERIC_HR_PRONE')
        if (is_career_low and cy >= 3 and walk_driven
                and sm is not None and wa is not None and (sm - wa) >= 10):
            return (
                'HOLD — post-TJ ramp candidate',
                f"4th-lens override (unvalidated, n=13): CAREER_LOW + {arche.get('archetype')} but SwingMiss rating {sm} far outpaces WalkAvoid {wa} (Δ +{sm-wa}); career_yr={cy}. Walk-driven downgrade with K-stuff intact = post-injury command-recovery pattern. Original: {verdict}.",
                'POST_TJ_RAMP',
            )

    # Override C — PROCESS_INTACT (SP; calibrated to model rank ≤ 25)
    if bucket == 'SP':
        m_r = model.get('rank')
        m_traj = arche.get('traj_flag')
        if (m_traj in ('TRENDING_DOWN', 'CAREER_LOW')
                and isinstance(m_r, int) and m_r <= 25):
            return (
                'HOLD — process intact',
                f"4th-lens override (calibrated): archetype {m_traj} but model still ranks #{m_r} (top-25 SP — calibration validated this band). Outcome decline outpacing process decline. Original: {verdict}.",
                'PROCESS_INTACT',
            )

    return verdict, rationale, None


# ---------- public high-level entry point ----------

def triangulate_player(name: str, bucket: str | None = None) -> dict | None:
    """Run the full triangulate pipeline for one player.

    Returns a structured dict, or None if the player couldn't be resolved.
    """
    player = resolve_player(name, bucket)
    if not player:
        return None
    b = player['bucket']
    model = model_row(player)
    m_rank_int = model.get('rank') if isinstance(model.get('rank'), int) else None
    pl_main, pl_main_date = pl_rank(player['display_name'], b, model_rank=m_rank_int)
    if b == 'SP':
        pl_stream, pl_stream_opp, pl_stream_date = pl_streamer_rank(player['display_name'])
    else:
        pl_stream, pl_stream_opp, pl_stream_date = '—', None, None
    arche = archetype_row(player)
    verdict, rationale = synthesize(player, pl_main, pl_main_date, pl_stream, pl_stream_date, model, arche)
    verdict, rationale, override_tag = apply_overrides(verdict, rationale, player, arche, model)

    return {
        'player': player,
        'bucket': b,
        'pl_main': pl_main,
        'pl_main_date': pl_main_date,
        'pl_stream': pl_stream,
        'pl_stream_opp': pl_stream_opp,
        'pl_stream_date': pl_stream_date,
        'pl_rank': pl_main,
        'model_rank': model.get('rank') if model.get('rank') != '—' else None,
        'model_proj': model.get('proj'),
        'arche_overall': arche.get('overall') if arche.get('have') else None,
        'arche_label': arche.get('archetype') if arche.get('have') else None,
        'arche_traj': arche.get('traj_flag') if arche.get('have') else None,
        'model': model,
        'arche': arche,
        'verdict': verdict,
        'rationale': rationale,
        'override_tag': override_tag,
    }
