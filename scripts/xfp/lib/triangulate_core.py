"""Core triangulate analytics: model row, archetype row, verdict synthesis,
4th-lens overrides, and the high-level `triangulate_player` entry point.
"""
from __future__ import annotations
import pandas as pd

from .bucket_dispatch import resolve_player
from .cached_data import _load_projection, _load_archetype
from .pl_cache import pl_rank, pl_streamer_rank
from .schedule_strength import schedule_idx_for
from .boom_stack import compute_boom_stack, STREAMER_RANK_FLOOR, compute_high_k_pitcher
from .catcher_framing import compute_catcher_framing
from .il_return_flag import compute_il_return_flag, IL_RETURN_DAYS_THRESHOLD, IL_RETURN_BUST_LIFT_PP
from .hitter_boom_stack import (
    compute_hitter_boom_stack,
    resolve_opp_sp_id_for_today,
)

import os as _os
from functools import lru_cache as _lru_cache

_PITCHER_SCHEDULE_PATH = _os.path.join(
    _os.path.dirname(__file__), '..', '..', '..',
    'data', 'research', 'xfp_cache', 'pitcher_schedule_2026.csv',
)


_STATCAST_2026_PATH = _os.path.join(
    _os.path.dirname(__file__), '..', '..', '..',
    'data', 'research', 'xfp_cache', 'statcast_2026.parquet',
)


@_lru_cache(maxsize=1)
def _load_pitcher_team_map() -> dict:
    """Pitcher MLBAM -> team_abbrev. Tries pitcher_schedule_2026.csv first
    (live probables feed), falls back to statcast_2026 most-recent-team.
    The fallback catches IL'd / non-scheduled pitchers that the probables
    feed omits (e.g. Soriano on 2026-06-03)."""
    out: dict = {}
    path = _os.path.abspath(_PITCHER_SCHEDULE_PATH)
    if _os.path.exists(path):
        df = pd.read_csv(path)
        if 'pitcher' in df.columns and 'team_abbrev' in df.columns:
            df = df.dropna(subset=['pitcher', 'team_abbrev']).copy()
            if 'game_date' in df.columns:
                df = df.sort_values('game_date')
            df = df.drop_duplicates('pitcher', keep='last')
            out = {int(p): str(t) for p, t in zip(df['pitcher'], df['team_abbrev'])}
    # Statcast fallback for pitchers missing from the schedule feed.
    sc_path = _os.path.abspath(_STATCAST_2026_PATH)
    if _os.path.exists(sc_path):
        try:
            sc = pd.read_parquet(
                sc_path,
                columns=['pitcher', 'home_team', 'away_team', 'inning_topbot', 'game_date'],
            )
            sc = sc.dropna(subset=['pitcher']).copy()
            sc['ptm'] = sc['home_team'].where(sc['inning_topbot'] == 'Top', sc['away_team'])
            sc = sc.dropna(subset=['ptm'])
            sc = sc.sort_values('game_date').drop_duplicates('pitcher', keep='last')
            for p, t in zip(sc['pitcher'], sc['ptm']):
                pid = int(p)
                if pid not in out:
                    out[pid] = str(t)
        except Exception:
            pass
    return out


def _pitcher_team_for(pitcher_id) -> str | None:
    try:
        return _load_pitcher_team_map().get(int(pitcher_id))
    except Exception:
        return None


# ---------- model row ----------

def model_row(player: dict) -> dict:
    bucket = player['bucket']
    df = _load_projection(bucket)
    if bucket == 'H':
        m = df[df['batter'] == player['id']]
    else:
        m = df[df['pitcher'] == player['id']]
    if m.empty:
        return {'rank': '—', 'proj': None, 'signal': '—', 'rep_delta': None, 'recform': None, 'schedule_idx': None}
    r = m.iloc[0]
    if bucket == 'H':
        # Hitter boom_stack tag (display only; advisory).
        # Validated 2026-06-03 (SHIP-CAUTIOUS as ADVISORY TAG). Stack=3 vs
        # stack=0 edge is +6.7 pp boom rate, year-stable 2018-2025.
        # NOT a feature in RH3_FEATS, NOT a verdict override.
        hboom_stack = None
        hboom_components = None
        hboom_rate_expected = None
        hboom_bust_expected = None
        hboom_detail = None
        try:
            team_str = r.get('team') if 'team' in r.index else None
            if isinstance(team_str, float) and pd.isna(team_str):
                team_str = None
            opp_sp_id = resolve_opp_sp_id_for_today(team_str if isinstance(team_str, str) else None)
            hbs = compute_hitter_boom_stack(
                batter_id=int(player['id']),
                opp_sp_id=opp_sp_id,
                team=team_str if isinstance(team_str, str) else None,
            )
            hboom_stack = hbs['boom_stack']
            hboom_components = hbs['components']
            hboom_rate_expected = hbs['boom_rate_expected']
            hboom_bust_expected = hbs['bust_rate_expected']
            hboom_detail = hbs.get('detail')
        except Exception:
            # Defensive: never break hitter cards on boom_stack failure.
            hboom_stack = None
            hboom_detail = None
        return {
            'rank': int(r['rank']),
            'proj_label': 'fp/game',
            'proj': float(r['xfp_rh3_per_game']),
            'signal': r['signal'],
            'rep_delta': float(r['replacement_delta']),
            'recform': float(r['recency_form_gap']),
            'extra': f"pa_to={int(r['pa_to'])}",
            'hitter_boom_stack': hboom_stack,
            'hitter_boom_components': hboom_components,
            'hitter_boom_rate_expected': hboom_rate_expected,
            'hitter_boom_bust_expected': hboom_bust_expected,
            'hitter_boom_detail': hboom_detail,
        }
    if bucket == 'SP':
        sched = schedule_idx_for(player['id'])
        # Variance band + data-quality tag + marcel-vs-data divergence flag.
        # These are additive; existing callers ignoring them keep working.
        def _f(col):
            v = r.get(col) if col in r.index else None
            try:
                return float(v) if v is not None and pd.notna(v) else None
            except (TypeError, ValueError):
                return None
        p25 = _f('xfp_rp3_p25')
        p75 = _f('xfp_rp3_p75')
        sigma = _f('xfp_rp3_sigma')
        marcel = _f('marcel_baseline')
        data_driven = _f('data_driven_estimate')
        dq_tag = r.get('data_quality_tag') if 'data_quality_tag' in r.index else None
        if dq_tag is not None:
            try:
                if pd.isna(dq_tag):
                    dq_tag = None
            except (TypeError, ValueError):
                pass
        # Divergence flag: only when both estimates exist and differ by >= 2 FP
        marcel_data_div = None
        if marcel is not None and data_driven is not None:
            diff = abs(marcel - data_driven)
            if diff >= 2.0:
                marcel_data_div = diff
        # Boom-stack tag (display only, ALL SP tiers as of 2026-06-03 — rank floor dropped).
        # Validated 2026-06-03 (Mode B PASS / SHIP_AS_TAG). NOT a verdict override.
        # Per-tier rates from `data/research/validation_runs/boom_stack_by_tier.md`.
        boom_stack = None
        boom_components = None
        boom_tier = None
        boom_rate_expected = None
        boom_bust_rate_expected = None
        boom_mean_fp_expected = None
        boom_skill_spike_anti_predictive = None
        sp_rank_int = int(r['rank'])
        next_opp = r.get('next_opp_team') if 'next_opp_team' in r.index else None
        if isinstance(next_opp, float) and pd.isna(next_opp):
            next_opp = None
        try:
            bs = compute_boom_stack(
                pitcher_id=int(player['id']),
                recency_form_gap=float(r['recency_form_gap']) if pd.notna(r['recency_form_gap']) else None,
                next_opp_team=next_opp if isinstance(next_opp, str) else None,
                rp3_rank=sp_rank_int,
            )
            boom_stack = bs['boom_stack']
            boom_components = bs['components']
            boom_tier = bs['tier']
            boom_rate_expected = bs['boom_rate_expected']
            boom_bust_rate_expected = bs['bust_rate_expected']
            boom_mean_fp_expected = bs['mean_fp_expected']
            boom_skill_spike_anti_predictive = bs['skill_spike_anti_predictive']
        except Exception:
            # Defensive: don't break SP cards if boom_stack errors out.
            boom_stack = None
        # HIGH-K ARM standalone display tag (validated 2026-06-03,
        # PASS_AS_DISPLAY_TAG). NOT a 4th component of boom_stack — this is
        # an INDEPENDENT TYPE signal that compounds with whatever boom_stack
        # is present. See data/research/validation_runs/boom_stack_v2_validation.md.
        is_high_k_arm = None
        high_k_z_score = None
        high_k_cohort_label = None
        high_k_lift_pp_expected = None
        try:
            hk = compute_high_k_pitcher(int(player['id']))
            is_high_k_arm = bool(hk['is_high_k'])
            high_k_z_score = hk['z_score']
            high_k_cohort_label = hk['cohort_label']
            # If the flag fires, surface the tier-appropriate amplified lift
            # given the current boom_stack value; else fall back to standalone.
            if is_high_k_arm:
                if isinstance(boom_stack, int) and boom_stack in hk['tier_amp_lift_pp_by_v1_stack']:
                    high_k_lift_pp_expected = hk['tier_amp_lift_pp_by_v1_stack'][boom_stack]
                else:
                    high_k_lift_pp_expected = hk['standalone_lift_pp']
        except Exception:
            # Defensive: never break SP cards on high-k compute failure.
            is_high_k_arm = None
        # CATCHER FRAMING standalone display tag (validated 2026-06-03).
        # SHIP_AS_DISPLAY_TAG — within-pitcher paired test t=2.40 p=0.017,
        # +3.06 pp boom-rate edge on the same SP between Q1 and Q5 framers.
        # Independent of boom_stack — pure visual context, layered like HIGH-K ARM.
        # See data/research/validation_runs/catcher_framing_boom_modifier.md.
        catcher_modal_name = None
        catcher_csaa = None
        catcher_quintile = None
        is_elite_framer = False
        is_framing_tax = False
        try:
            pteam = _pitcher_team_for(player['id'])
            cf = compute_catcher_framing(pteam)
            catcher_modal_name = cf.get('modal_catcher_name')
            catcher_csaa = cf.get('csaa_runs')
            catcher_quintile = cf.get('framing_quintile')
            is_elite_framer = bool(cf.get('is_elite_framer'))
            is_framing_tax = bool(cf.get('is_framing_tax'))
        except Exception:
            # Defensive: never break SP cards on catcher-framing compute failure.
            pass
        # IL_RETURN salvage tag (validated 2026-06-03, +2.93 pp bust lift,
        # n=640, p=0.044). Standalone display tag — NOT a boom_stack/bust
        # component. Fires when previous MLB start was >= 30 days before the
        # next scheduled start. See
        # data/research/validation_runs/bust_stack_v2_context_validation.md.
        is_first_back_long_il = None
        il_return_days = None
        il_return_last_start = None
        il_return_ref_date = None
        il_return_ref_source = None
        try:
            il = compute_il_return_flag(int(player['id']))
            is_first_back_long_il = bool(il.get('is_first_back_long_il'))
            il_return_days = il.get('days_since_last_start')
            il_return_last_start = il.get('last_start_date')
            il_return_ref_date = il.get('reference_date')
            il_return_ref_source = il.get('reference_source')
        except Exception:
            # Defensive: never break SP cards on IL-return compute failure.
            is_first_back_long_il = None
        return {
            'rank': int(r['rank']),
            'proj_label': 'fp/start',
            'proj': float(r['xfp_rp3_per_start']),
            'signal': r['signal'],
            'rep_delta': float(r['replacement_delta']),
            'recform': float(r['recency_form_gap']),
            'extra': f"gs_to={int(r['gs_to'])}",
            'schedule_idx': sched,
            'p25': p25,
            'p75': p75,
            'sigma': sigma,
            'data_quality_tag': dq_tag,
            'marcel_baseline': marcel,
            'data_driven_estimate': data_driven,
            'marcel_data_divergence': marcel_data_div,
            'boom_stack': boom_stack,
            'boom_components': boom_components,
            'boom_tier': boom_tier,
            'boom_rate_expected': boom_rate_expected,
            'boom_bust_rate_expected': boom_bust_rate_expected,
            'boom_mean_fp_expected': boom_mean_fp_expected,
            'boom_skill_spike_anti_predictive': boom_skill_spike_anti_predictive,
            'is_high_k_arm': is_high_k_arm,
            'high_k_z_score': high_k_z_score,
            'high_k_cohort_label': high_k_cohort_label,
            'high_k_boom_lift_expected': high_k_lift_pp_expected,
            'catcher_modal_name': catcher_modal_name,
            'catcher_csaa': catcher_csaa,
            'catcher_quintile': catcher_quintile,
            'is_elite_framer': is_elite_framer,
            'is_framing_tax': is_framing_tax,
            'is_first_back_long_il': is_first_back_long_il,
            'il_return_days_since_last_start': il_return_days,
            'il_return_last_start_date': il_return_last_start,
            'il_return_reference_date': il_return_ref_date,
            'il_return_reference_source': il_return_ref_source,
            'il_return_threshold_days': IL_RETURN_DAYS_THRESHOLD,
            'il_return_bust_lift_pp': IL_RETURN_BUST_LIFT_PP,
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


# ---------- verdict consolidation ----------

# Map full verdict label -> (verdict_top, reason_tag).
_VERDICT_MAP = {
    'STRONG HOLD/BUY':                    ('BUY',     'strong_hold'),
    'BUY — archetype breakout':           ('BUY',     'archetype_breakout'),
    'BUY — model anchored on prior':      ('BUY',     'model_anchored'),
    'BUY — process upgrade':              ('BUY',     'process_upgrade'),
    'BUY — under-the-radar':              ('BUY',     'under_the_radar'),
    'BUY — outcomes only (no archetype)': ('BUY',     'outcomes_only_rookie'),
    'HOLD — post-TJ ramp candidate':      ('HOLD',    'post_tj_ramp'),
    'HOLD — process intact':              ('HOLD',    'process_intact'),
    'CAUTION':                            ('CAUTION', 'process_red_flag'),
    'FADE — PL chasing outcomes':         ('FADE',    'pl_outcome_chase'),
    'MIXED — see profile':                ('MIXED',   'no_convergence'),
}


def consolidate_verdict(verdict: str) -> tuple[str, str]:
    """Collapse full verdict label to (verdict_top, reason_tag)."""
    if verdict in _VERDICT_MAP:
        return _VERDICT_MAP[verdict]
    # Prefix fallback for any unexpected variant
    if verdict.startswith('STRONG'):    return ('BUY',     'strong_hold')
    if verdict.startswith('BUY'):       return ('BUY',     'other')
    if verdict.startswith('HOLD'):      return ('HOLD',    'other')
    if verdict.startswith('FADE'):      return ('FADE',    'other')
    if verdict.startswith('CAUTION'):   return ('CAUTION', 'process_red_flag')
    if verdict.startswith('MIXED'):     return ('MIXED',   'no_convergence')
    return ('MIXED', 'unknown')


# ---------- confidence scoring ----------

def _verdict_direction(verdict_top: str) -> str:
    """bullish / bearish / neutral for alignment scoring."""
    if verdict_top == 'BUY':
        return 'bullish'
    if verdict_top in ('FADE', 'CAUTION'):
        return 'bearish'
    return 'neutral'  # HOLD, MIXED


def compute_confidence(verdict_top: str, pl_rank, model_rank, arche: dict) -> tuple[float, int, int]:
    """Return (confidence_0_1, n_signals_aligned, n_signals_available)."""
    direction = _verdict_direction(verdict_top)
    aligned = 0
    available = 4

    pl_int = pl_rank if isinstance(pl_rank, int) else None
    m_int = model_rank if isinstance(model_rank, int) else None
    has_arche = bool(arche.get('have'))
    a_traj = arche.get('traj_flag') if has_arche else None
    a_overall = arche.get('overall') if has_arche else None

    # Signal 1: PL rank alignment
    if pl_int is not None:
        if direction == 'bullish' and pl_int <= 80:
            aligned += 1
        elif direction == 'bearish' and pl_int > 80:
            aligned += 1
        elif direction == 'neutral':
            aligned += 1  # presence counts for HOLD/MIXED
    elif direction == 'bullish' and verdict_top == 'BUY':
        # UR/unranked is consistent with under-the-radar BUYs
        pass

    # Signal 2: Model rank alignment
    if m_int is not None:
        if direction == 'bullish' and m_int <= 80:
            aligned += 1
        elif direction == 'bearish' and m_int > 80:
            aligned += 1
        elif direction == 'neutral':
            aligned += 1

    # Signal 3: Archetype data present
    if has_arche:
        aligned += 1

    # Signal 4: Archetype trajectory aligned
    if has_arche and a_traj is not None:
        if direction == 'bullish' and a_traj == 'TRENDING_UP':
            aligned += 1
        elif direction == 'bearish' and a_traj in ('TRENDING_DOWN', 'CAREER_LOW'):
            aligned += 1
        elif direction == 'neutral' and a_traj in ('STABLE', 'TRENDING_UP', 'TRENDING_DOWN', 'CAREER_LOW', 'CAREER_HIGH'):
            # Any concrete trajectory counts as a signal for HOLD/MIXED
            aligned += 1

    confidence = aligned / available
    return confidence, aligned, available


# ---------- counterfactual watch-list ----------

def build_watch_list(verdict_top: str, reason_tag: str, model: dict, arche: dict, pl_rank) -> list[str]:
    """4-5 templated counterfactual triggers that would flip the verdict."""
    m_rank = model.get('rank') if isinstance(model.get('rank'), int) else None
    has_arche = bool(arche.get('have'))
    overall = arche.get('overall') if has_arche else None
    a_traj = arche.get('traj_flag') if has_arche else None

    items: list[str] = []

    if verdict_top == 'HOLD':
        if reason_tag == 'process_intact':
            items.append(f"model rank slips past #35 (currently #{m_rank})")
            items.append("SwingMiss sub-rating drops below 45")
            items.append("archetype trajectory worsens to CAREER_LOW")
            items.append("velo_tier drops to FINESSE")
        elif reason_tag == 'post_tj_ramp':
            items.append("SwingMiss rating falls below 50 (stuff actually eroding)")
            items.append("WalkAvoid fails to recover above 45 after 4 starts")
            items.append("model rank slips past #60")
            items.append("archetype label shifts away from WILD_MID/FILLER without K-rate gain")
        else:
            items.append(f"model rank moves outside top-50 (currently #{m_rank})")
            items.append("archetype OVERALL drops below 50")
            items.append("traj_flag flips to TRENDING_DOWN")
    elif verdict_top == 'CAUTION':
        items.append("career_pct drops below current floor")
        items.append("L21d xwOBACON drops more than 0.020 from season")
        items.append("archetype OVERALL drops below 45")
        items.append(f"PL rank deteriorates past #100 (currently {pl_rank})")
        if has_arche and arche.get('velo_tier') == 'FINESSE':
            items.append("velo drops further (already FINESSE tier)")
    elif verdict_top == 'MIXED':
        items.append(f"PL rank changes by >20 (currently {pl_rank})")
        items.append(f"model rank changes by >20 (currently #{m_rank})")
        items.append(f"archetype OVERALL changes by >10 (currently {overall})")
        items.append("traj_flag flips direction")
    elif verdict_top == 'BUY':
        items.append("archetype trajectory flips to TRENDING_DOWN")
        items.append("model rank slips past #80")
        items.append("PL rank drops more than 30 ranks")
        items.append("archetype OVERALL drops below 55")
    elif verdict_top == 'FADE':
        items.append("model rank improves to top-50")
        items.append("archetype OVERALL climbs above 55")
        items.append("traj_flag flips to TRENDING_UP")
        items.append("PL rank holds or improves over next 2 weeks")

    return items[:5]


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

    verdict_top, reason_tag = consolidate_verdict(verdict)
    m_rank_for_conf = model.get('rank') if isinstance(model.get('rank'), int) else None
    confidence, n_aligned, n_avail = compute_confidence(verdict_top, pl_main, m_rank_for_conf, arche)
    watch_list = build_watch_list(verdict_top, reason_tag, model, arche, pl_main)

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
        'verdict_top': verdict_top,
        'reason_tag': reason_tag,
        'confidence': confidence,
        'confidence_n_aligned': n_aligned,
        'confidence_n_available': n_avail,
        'watch_list': watch_list,
        'rationale': rationale,
        'override_tag': override_tag,
    }
