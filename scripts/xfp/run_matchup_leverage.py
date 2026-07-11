"""run_matchup_leverage — /matchup-leverage engine (win-probability strategy layer).

THE INSIGHT: every other skill maximizes expected FP, but BrownU H2H is won by
P(my_total > opp_total). When TRAILING, variance is an ASSET (prefer boom/bust);
when LEADING, variance is a LIABILITY (prefer floor); when CLOSE, E[FP] is ~right.
Nothing else in the repo reasons this way.

RULE 13 (decision layer only): this NEVER touches rh3/rp3/rprs2/Blended xFP.
It converts existing projections + empirical game-log distributions into
P(win) and Delta-P(win) for the decisions Josh can actually make this period.

Pipeline
  1. STATE   — live matchup (get_matchup), week window, remaining games/starts
               per roster (both sides), banked SP starts vs the 10-start cap.
  2. MC      — ~10k sims of the rest of the matchup. Per remaining player-game
               the FP draw is a Bayesian blend of (a) bootstrap from the player's
               empirical per-game FP history (boxscore parquets, mlbam-keyed) and
               (b) a parametric draw at the model mean/sigma (weight n/(n+k), so
               thin histories lean on the model — the sp_bench_mc idiom).
               SP starts are event-level with the chronological 10-start cap
               applied INSIDE each trial; unconfirmed rotation-gap starts occur
               with p=0.80 (dashboard convention).
  3. ADVICE  — Delta-P(win), not Delta-E[FP], for: (a) hitter sit-priority,
               (b) SP start bench scenarios under the cap, (c) top FA streamer
               adds with confirmed/probable starts left this week. Regime label
               (TRAILING/CLOSE/LEADING) tells /pregame-check and /sp-week-plan
               WHICH objective to optimize.
  4. OUTPUT  — console report + data/outputs/matchup_leverage.json.
  5. --calibrate — honesty smoke test: re-sim closed periods as-of their start
               (realized game counts from the boxscore store, FP distributions
               strictly PRE-period) and check the realized outcome lands inside
               the simulated middle-80% band.

Usage
  python scripts/xfp/run_matchup_leverage.py                 # full live run
  python scripts/xfp/run_matchup_leverage.py --simulate-only # state + P(win) only
  python scripts/xfp/run_matchup_leverage.py --sims 20000
  python scripts/xfp/run_matchup_leverage.py --calibrate auto
  python scripts/xfp/run_matchup_leverage.py --calibrate "15,16,17"
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

# ── reuse dashboard machinery (never reimplement; never edit it) ─────────────
from build_matchup_dashboard import (  # noqa: E402
    get_matchup,
    load_projections,
    fetch_espn_week_schedule,
    fetch_schedules_by_team,
    build_sp_starts_by_pitcher,
    project_player,
    player_mlbam_lookup,
    _resolve_mlbam_via_api,
    _resolve_pitcher_mlbam,
    _is_active_slot,
    _today_et,
    _norm,
    IL_INJURY_STATES,
    ESPN_TO_MLB_TEAM,
    SIGMA_PER_SP_START,
    SIGMA_PER_RP_GAME,
    FALLBACK_SP_PER_START,
)
from scripts.xfp.lib.pitcher_role import detect_pitcher_role  # noqa: E402
from scripts.xfp.lib.boom_bust import (  # noqa: E402
    SP_BOOM, SP_BUST, H_BOOM, H_BUST, RP_BOOM, RP_BUST,
)
# Period-aware SP cap + window (2026-07-11): the ASG/playoff multi-week blocks
# carry a different cap (period 15 = 16) and a >7-day span. Default single-week
# periods resolve to SP_CAP(10) + Mon–Sun, byte-identical to before.
from plv_clone.cap_math import (  # noqa: E402
    sp_cap_for_period, period_window, is_period_covered, weeks_in_period,
)
# The period-resolver (cap + window) and the authoritative ESPN banked-count
# reader are SHARED with run_roster_audit + build_matchup_dashboard so all three
# engines agree on the current period's cap/window/banked count (2026-07-11).
from scripts.xfp.lib.period_meta import (  # noqa: E402
    resolve_period_meta, espn_period_meta,
)
# Era-general subseason variance bands (2026-07-10): honest FALLBACK sigma for
# thin-history players only — the primary empirical-bootstrap path is untouched.
from scripts.xfp.lib.variance_bands import fallback_sigma  # noqa: E402

CACHE = ROOT / 'data' / 'research' / 'xfp_cache'
OUT = ROOT / 'data' / 'outputs'
BOX_P = CACHE / 'boxscore_pitchers.parquet'
BOX_H = CACHE / 'boxscore_hitters.parquet'

# Bayesian blend priors (sp_bench_mc idiom: weight = n_emp / (n_emp + K)).
K_PRIOR_SP = 12       # ~15-start history -> 56% empirical
K_PRIOR_H = 8         # ~25-game history -> 76% empirical
K_PRIOR_RP = 10
EMP_LAST_N = {'SP': 15, 'H': 25, 'RP': 20}
UNCONFIRMED_START_P = 0.80   # dashboard's rotation-gap occurrence probability

# Regime cuts on baseline P(win)
TRAILING_MAX = 0.40
LEADING_MIN = 0.60


# ─────────────────────────────────────────────────────────────────────────────
# Empirical FP series (boxscore parquets — mlbam-keyed, the best variance source)
# ─────────────────────────────────────────────────────────────────────────────
_BOX_CACHE: dict = {}


def _box(kind: str):
    """kind 'P'/'H' -> parquet frame (or None). Cached per process."""
    if kind not in _BOX_CACHE:
        path = BOX_P if kind == 'P' else BOX_H
        try:
            _BOX_CACHE[kind] = pd.read_parquet(path)
        except Exception:
            _BOX_CACHE[kind] = None
    return _BOX_CACHE[kind]


def emp_series(mlbam, bucket: str, before: str | None = None,
               last_n: int | None = None) -> list[float]:
    """Time-ordered per-game BrownU FP for one player from the boxscore store.
    bucket in {SP,RP,H}. `before` (ISO date) filters to games strictly earlier —
    the leakage guard for --calibrate. Uses the store's precomputed fp columns."""
    df = _box('P' if bucket in ('SP', 'RP') else 'H')
    if df is None or not mlbam:
        return []
    sub = df[df['mlbam_id'] == int(mlbam)]
    if bucket == 'SP':
        sub = sub[sub['gs'] == 1]; col = 'fp_sp'
    elif bucket == 'RP':
        sub = sub[sub['gs'] == 0]; col = 'fp_rp'
    else:
        col = 'fp_h'
    if before:
        sub = sub[sub['game_date'].astype(str) < before]
    if sub.empty:
        return []
    sub = sub.sort_values(['game_date', 'game_pk'])
    vals = [float(x) for x in sub[col].tolist()]
    n = last_n if last_n is not None else EMP_LAST_N[bucket]
    return vals[-n:]


def pooled_series(bucket: str, before: str | None = None,
                  max_n: int = 5000) -> list[float]:
    """League-pooled per-game FP distribution for a bucket (calibration fallback
    for thin-history players)."""
    df = _box('P' if bucket in ('SP', 'RP') else 'H')
    if df is None:
        return []
    sub = df
    if before:
        sub = sub[sub['game_date'].astype(str) < before]
    if bucket == 'SP':
        vals = sub.loc[sub['gs'] == 1, 'fp_sp']
    elif bucket == 'RP':
        vals = sub.loc[sub['gs'] == 0, 'fp_rp']
    else:
        vals = sub['fp_h']
    vals = vals.astype(float)
    if len(vals) > max_n:
        vals = vals.sample(max_n, random_state=0)
    return [float(x) for x in vals.tolist()]


def series_stats(vals: list[float], boom_thr: float, bust_thr: float) -> dict:
    if not vals:
        return {'n': 0, 'mean': None, 'std': None, 'boom_pct': None, 'bust_pct': None}
    a = np.asarray(vals, dtype=float)
    return {
        'n': int(len(a)),
        'mean': round(float(a.mean()), 2),
        'std': round(float(a.std(ddof=1)), 2) if len(a) > 1 else 0.0,
        'boom_pct': round(float((a >= boom_thr).mean()) * 100),
        'bust_pct': round(float((a < bust_thr).mean()) * 100),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Draw helpers (blend = empirical bootstrap + parametric at model mean/sigma)
# ─────────────────────────────────────────────────────────────────────────────

def _blend_draws(rng, emp: list[float], mean: float, sigma: float,
                 k_prior: int, n: int) -> np.ndarray:
    """One game/start worth of FP draws. Empirical bootstrap with prob
    w = n_emp/(n_emp+k); parametric normal otherwise. Falls back cleanly to
    pure-parametric (thin history) or pure-empirical (no model mean)."""
    sigma = max(float(sigma or 0) or 1e-6, 1e-6)
    n_emp = len(emp)
    if mean is None:
        if n_emp == 0:
            return np.zeros(n)
        w = 1.0
        mean = 0.0
    else:
        w = n_emp / (n_emp + k_prior) if n_emp else 0.0
    out = rng.normal(float(mean), sigma, n)
    if w > 0:
        mask = rng.random(n) < w
        n_m = int(mask.sum())
        if n_m:
            out[mask] = rng.choice(np.asarray(emp, dtype=float), size=n_m, replace=True)
    return out


def _hitter_total_draws(rng, n_games: int, emp, mean_g, sigma_g, n_sims) -> np.ndarray:
    total = np.zeros(n_sims)
    for _ in range(max(n_games, 0)):
        total += _blend_draws(rng, emp, mean_g, sigma_g, K_PRIOR_H, n_sims)
    return total


def _rp_total_draws(rng, n_rem_games: int, p_app: float, emp, mean_app,
                    sigma_app, n_sims) -> np.ndarray:
    """Appearance count ~ Binomial(n_rem_games, p_app) per sim; each appearance
    draws blended FP (SV/HLD credit lives inside the empirical fp_rp values)."""
    if n_rem_games <= 0 or p_app <= 0:
        return np.zeros(n_sims)
    n_apps = rng.binomial(n_rem_games, min(p_app, 1.0), n_sims)
    total = np.zeros(n_sims)
    for g in range(n_rem_games):
        active = n_apps > g
        if not active.any():
            break
        total += _blend_draws(rng, emp, mean_app, sigma_app, K_PRIOR_RP, n_sims) * active
    return total


# ─────────────────────────────────────────────────────────────────────────────
# STATE assembly
# ─────────────────────────────────────────────────────────────────────────────

def resolve_player_mlbam(p):
    """Collision-safe mlbam for a rostered ESPN player object."""
    pos = (p.position or '?')
    if pos in ('SP', 'RP', 'P'):
        return _resolve_pitcher_mlbam(p.name, team=(p.proTeam or None),
                                      role=(pos if pos in ('SP', 'RP') else None))
    return player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)


def banked_sp_starts_from_box(sp_mlbams: set[int], week_start: date, today: date) -> int:
    """SP starts already banked this scoring week (week_start..yesterday) from the
    boxscore store — role-correct (gs flag) and no per-pitcher API calls."""
    df = _box('P')
    if df is None or not sp_mlbams:
        return 0
    sub = df[(df['mlbam_id'].isin(list(sp_mlbams))) & (df['gs'] == 1)]
    dates = sub['game_date'].astype(str)
    return int(((dates >= week_start.isoformat()) & (dates < today.isoformat())).sum())


def build_state(verbose=True):
    """Pull live matchup + schedules + projections; classify every active-slot
    player into H/SP/RP with remaining units and model mean/sigma."""
    mu = get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map = load_projections()
    today = _today_et()
    period = mu['period']

    # ── PERIOD-AWARE cap + window (2026-07-11) ───────────────────────────────
    # General rule: cap = 10 × weeks, weeks = len(matchupPeriods[period]) from
    # ESPN settings — so regular weeks -> 10 and 2-week playoff rounds -> 20
    # automatically. The ASG block (period 15) is the ONE exception: an explicit
    # override (cap 16 + a real Jul 6–19 window) that beats the formula, because
    # the All-Star break removes game-days AND ESPN lists it as a single week.
    # A standard single-week period resolves to SP_CAP(10) + a Mon–Sun week —
    # byte-identical to before.
    pmeta = resolve_period_meta(mu['league_obj'], period, today=today)
    weeks = pmeta['weeks']
    sp_cap = pmeta['sp_cap']
    week_start, week_end = pmeta['week_start'], pmeta['week_end']

    # Authoritative banked counts + loud multi-week / cap cross-checks from ESPN.
    meta = espn_period_meta(mu['league_obj'], period,
                            getattr(mu['mine'], 'team_id', None),
                            getattr(mu['opp'], 'team_id', None))
    # Warn ONLY when the period LOOKS single-week (weeks==1, no override) yet has
    # already scored across >1 week — the ASG-without-override trap. A clean
    # multi-week playoff round (weeks>=2) is handled by 10×weeks and must NOT warn.
    if not is_period_covered(period) and weeks == 1:
        span = meta.get('elapsed_span_days')
        if span is not None and span > 6:
            print('  ' + '!' * 70)
            print(f'  LOUD WARNING: matchup period {period} has already scored across '
                  f'{span + 1} calendar days (>1 week) but ESPN lists it as a single '
                  f'week and it has NO override in cap_math.PERIOD_CAP_OVERRIDES. '
                  f'Falling back to cap {sp_cap} + a single Mon–Sun week — very likely '
                  f'WRONG for an ASG-style block. Add {{{period}: <cap>}} + a window to '
                  f'cap_math.py. See the maintenance note there.')
            print('  ' + '!' * 70)

    if verbose:
        cov = ('OVERRIDE' if is_period_covered(period)
               else (f'10×{weeks}wk' if weeks > 1 else 'default'))
        print(f'  period {period}  cap {sp_cap} ({cov})  weeks {weeks}  '
              f'window {week_start} -> {week_end}  today {today}')
        print(f'  WTD: Ligers {mu["my_score"]:.1f} | {mu["opp"].team_name} {mu["opp_score"]:.1f}')

    # Schedules: ESPN primary, MLB Stats fallback — but ALWAYS fetch the all-30
    # MLB schedule too (probable-pitcher hydrate powers the FA streamer scan).
    schedules_by_team = fetch_espn_week_schedule(mu['league_obj'], week_start, week_end)
    all30 = sorted(set(ESPN_TO_MLB_TEAM.values()))
    mlb_sched_all = fetch_schedules_by_team(all30, today.isoformat(), week_end.isoformat())
    if not schedules_by_team or sum(len(v) for v in schedules_by_team.values()) == 0:
        schedules_by_team = mlb_sched_all
        if sum(len(v) for v in schedules_by_team.values()) == 0:
            raise RuntimeError('No schedule data for the week — refusing to simulate.')

    # Role-aware SP id sets (gotcha #8 — never trust .position alone)
    def _sp_ids(lineup):
        ids = {}
        for p in lineup:
            if (p.position or '?') not in ('SP', 'RP', 'P'):
                continue
            m = resolve_player_mlbam(p)
            if not m:
                continue
            role = detect_pitcher_role(p, mlbam_id=int(m))
            if role == 'SP':
                ids[p.name] = int(m)
        return ids

    my_sp_ids = _sp_ids(mu['my_lineup'])
    opp_sp_ids = _sp_ids(mu['opp_lineup'])
    sp_starts_by_pitcher = build_sp_starts_by_pitcher(
        set(my_sp_ids.values()) | set(opp_sp_ids.values()),
        schedules_by_team, today, week_end)

    # rp3 CSV frame for data_quality_tag (marcel_il gotcha #1) keyed by mlbam
    try:
        rp3_csv = pd.read_csv(OUT / 'xfp_rp3_projections.csv',
                              usecols=['pitcher', 'data_quality_tag'])
        dq_by_mlbam = dict(zip(rp3_csv['pitcher'].astype(int), rp3_csv['data_quality_tag']))
    except Exception:
        dq_by_mlbam = {}

    def _classify(lineup, side_label):
        """-> (hitters, rps, sp_start_events) for one roster side."""
        hitters, rps, sp_events = [], [], []
        for p in lineup:
            if not _is_active_slot(p):     # IL/IR slots only — BE counts (gotcha #7)
                continue
            proj = project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                  rh3_map, rp3_map, rp3_by_mlbam, rprs2_map,
                                  ts_map, today, week_end)
            mlbam = resolve_player_mlbam(p)
            pos = (p.position or '?')
            is_sp_proj = any(b.get('type') == 'start' for b in proj.get('breakdown', []))
            if is_sp_proj:
                nk = _norm(p.name)
                rp_info = rp3_map.get(nk, {})
                per_start = rp_info.get('per_start') or None
                sigma = (rp_info.get('sigma')
                         or fallback_sigma('SP', default=SIGMA_PER_SP_START))
                dq = dq_by_mlbam.get(int(mlbam)) if mlbam else None
                for b in proj['breakdown']:
                    if b.get('type') != 'start':
                        continue
                    sp_events.append({
                        'name': p.name, 'mlbam': int(mlbam) if mlbam else None,
                        'date': b.get('date'), 'opp': b.get('opp') or b.get('opp_team'),
                        'confirmed': bool(b.get('confirmed', True)),
                        'model_fp': float(b.get('fp_original', b.get('fp', 0)) or 0),
                        'per_start': per_start, 'sigma': float(sigma),
                        'data_quality_tag': dq,
                    })
            elif pos in ('SP', 'RP', 'P'):
                units = float(proj.get('units') or 0)
                if units <= 0 or not mlbam:
                    continue
                mlb_id = ESPN_TO_MLB_TEAM.get((p.proTeam or '').upper())
                n_rem = len([g for g in schedules_by_team.get(mlb_id, [])
                             if today.isoformat() <= g['date'] <= week_end.isoformat()])
                if n_rem <= 0:
                    continue
                rps.append({'name': p.name, 'mlbam': int(mlbam),
                            'n_rem_games': n_rem,
                            'p_app': min(units / n_rem, 1.0),
                            'mean_app': (proj['fp'] / units) if units else 0.0,
                            'sigma_app': (math.sqrt(max(proj['sigma2'], 0) / units)
                                          or fallback_sigma('RP', default=SIGMA_PER_RP_GAME))
                                         if units
                                         else fallback_sigma('RP', default=SIGMA_PER_RP_GAME)})
            else:
                units = float(proj.get('units') or 0)
                if units <= 0 or proj.get('fp', 0) <= 0:
                    continue
                n_games = int(round(units))
                if n_games <= 0 or not mlbam:
                    continue
                hitters.append({'name': p.name, 'mlbam': int(mlbam),
                                'n_games': n_games,
                                'mean_g': proj['fp'] / n_games,
                                'sigma_g': math.sqrt(max(proj['sigma2'], 0) / n_games)
                                           if proj['sigma2']
                                           else fallback_sigma('H', default=3.0),
                                'slot': getattr(p, 'lineup_slot', None)
                                        or getattr(p, 'lineupSlot', '') or '',
                                'injury': str(getattr(p, 'injuryStatus', '') or '')})
        # chronological cap ordering (BrownU live rule: starts 11+ are zeros)
        sp_events.sort(key=lambda e: (e['date'] or '9999', e['name']))
        return hitters, rps, sp_events

    my_h, my_rp, my_sp = _classify(mu['my_lineup'], 'mine')
    opp_h, opp_rp, opp_sp = _classify(mu['opp_lineup'], 'opp')

    # Banked SP starts: ESPN's authoritative statId-33 count is ground truth
    # (matches the x/CAP shown on the matchup screen); the boxscore-store count
    # over the resolved window is the fallback AND an independent cross-check.
    box_mine = banked_sp_starts_from_box(set(my_sp_ids.values()), week_start, today)
    box_opp = banked_sp_starts_from_box(set(opp_sp_ids.values()), week_start, today)
    banked_mine = meta.get('my_banked') if meta.get('my_banked') is not None else box_mine
    banked_opp = meta.get('opp_banked') if meta.get('opp_banked') is not None else box_opp
    if verbose:
        src = 'ESPN' if meta.get('my_banked') is not None else 'box'
        print(f'  banked SP starts: mine {banked_mine} (source {src}; box cross-check '
              f'{box_mine}), opp {banked_opp} (box {box_opp})  cap {sp_cap}')
        if meta.get('my_banked') is not None and meta['my_banked'] != box_mine:
            print(f'  note: ESPN banked ({meta["my_banked"]}) != box cross-check '
                  f'({box_mine}) — ESPN wins (bench-day starts / roster churn differ)')
    if banked_mine >= sp_cap or banked_opp >= sp_cap:
        print(f'  WARNING: a side has banked >= cap ({banked_mine}/{banked_opp} vs cap '
              f'{sp_cap}) — if starts remain, the cap for period {period} may be too low.')

    return {
        'mu': mu, 'today': today, 'week_start': week_start, 'week_end': week_end,
        'period': period, 'sp_cap': sp_cap, 'period_weeks': weeks,
        'period_covered': is_period_covered(period),
        'days_remaining': (week_end - today).days + 1,
        'schedules_by_team': schedules_by_team, 'mlb_sched_all': mlb_sched_all,
        'my_hitters': my_h, 'my_rps': my_rp, 'my_sp_events': my_sp,
        'opp_hitters': opp_h, 'opp_rps': opp_rp, 'opp_sp_events': opp_sp,
        'banked_mine': banked_mine, 'banked_opp': banked_opp,
        'cap_remaining_mine': max(sp_cap - banked_mine, 0),
        'cap_remaining_opp': max(sp_cap - banked_opp, 0),
        'rp3_map': None,  # not needed post-classify
    }


# ─────────────────────────────────────────────────────────────────────────────
# MONTE CARLO (draws precomputed once; scenarios are cheap numpy re-assemblies)
# ─────────────────────────────────────────────────────────────────────────────

def precompute_draws(state, n_sims: int, seed: int):
    rng = np.random.default_rng(seed)
    D = {'n_sims': n_sims}

    def _hitter_arrays(hitters, bucket='H'):
        out = {}
        for h in hitters:
            emp = emp_series(h['mlbam'], 'H')
            out[h['name']] = _hitter_total_draws(
                rng, h['n_games'], emp, h['mean_g'], h['sigma_g'], n_sims)
        return out

    def _rp_arrays(rps):
        out = {}
        for r in rps:
            emp = emp_series(r['mlbam'], 'RP')
            out[r['name']] = _rp_total_draws(
                rng, r['n_rem_games'], r['p_app'], emp, r['mean_app'],
                r['sigma_app'], n_sims)
        return out

    def _sp_event_draws(events):
        """Per start-event: fp draw array + occurrence mask (Bernoulli 0.80 for
        rotation-gap predicted starts). Empirical per-start FP blended with a
        parametric draw at the rp3 per-start mean; marcel_il rows lean parametric
        automatically (thin/no 2026 start history -> low empirical weight)."""
        arr = []
        emp_cache = {}
        for e in events:
            key = e['mlbam']
            if key not in emp_cache:
                emp_cache[key] = emp_series(key, 'SP')
            emp = emp_cache[key]
            mean = e['per_start'] if e['per_start'] else (
                float(np.mean(emp)) if len(emp) >= 3 else FALLBACK_SP_PER_START)
            base = _blend_draws(rng, emp, mean, e['sigma'], K_PRIOR_SP, n_sims)
            # opp factor: the model_fp already carries opp_bat via project_sp_starts;
            # scale the whole draw distribution to the model's per-start EV so the
            # matchup tilt survives while empirical variance shape is preserved.
            ev = float(np.mean(base))
            if ev > 1.0 and e['model_fp'] > 0:
                # model_fp includes the 0.80 unconfirmed discount; undo it since
                # occurrence is simulated explicitly below.
                target = e['model_fp'] / (1.0 if e['confirmed'] else UNCONFIRMED_START_P)
                base = base * (target / ev)
            occ = (np.ones(n_sims, dtype=bool) if e['confirmed']
                   else rng.random(n_sims) < UNCONFIRMED_START_P)
            arr.append({'event': e, 'fp': base, 'occ': occ})
        return arr

    D['my_h'] = _hitter_arrays(state['my_hitters'])
    D['opp_h'] = _hitter_arrays(state['opp_hitters'])
    D['my_rp'] = _rp_arrays(state['my_rps'])
    D['opp_rp'] = _rp_arrays(state['opp_rps'])
    D['my_sp'] = _sp_event_draws(state['my_sp_events'])
    D['opp_sp'] = _sp_event_draws(state['opp_sp_events'])
    D['rng'] = rng
    return D


def _sp_side_total(sp_draws: list[dict], cap_remaining: int,
                   bench: set | None = None, extra: list[dict] | None = None) -> np.ndarray:
    """Chronological cap inside each trial: among starts that OCCUR, only the
    first `cap_remaining` (by date) score. bench = {(name, date)} start events
    withheld; extra = additional event-draw dicts (FA adds)."""
    events = [d for d in sp_draws
              if not (bench and (d['event']['name'], d['event']['date']) in bench)]
    if extra:
        events = events + list(extra)
    if not events:
        n = sp_draws[0]['fp'].shape[0] if sp_draws else (extra[0]['fp'].shape[0] if extra else 0)
        return np.zeros(n)
    events.sort(key=lambda d: (d['event']['date'] or '9999', d['event']['name']))
    occ = np.stack([d['occ'] for d in events])           # (E, S)
    fp = np.stack([d['fp'] for d in events])             # (E, S)
    order_count = np.cumsum(occ, axis=0)                 # nth occurred start
    keep = occ & (order_count <= cap_remaining)
    return (fp * keep).sum(axis=0)


def assemble(state, D, *, zero_hitters: set = frozenset(),
             bench_starts: set = frozenset(), extra_my_sp: list | None = None):
    """-> (my_total, opp_total) arrays for one scenario."""
    n = D['n_sims']
    my = np.full(n, float(state['mu']['my_score']))
    opp = np.full(n, float(state['mu']['opp_score']))
    for name, arr in D['my_h'].items():
        if name not in zero_hitters:
            my = my + arr
    for arr in D['my_rp'].values():
        my = my + arr
    my = my + _sp_side_total(D['my_sp'], state['cap_remaining_mine'],
                             bench=bench_starts, extra=extra_my_sp)
    for arr in D['opp_h'].values():
        opp = opp + arr
    for arr in D['opp_rp'].values():
        opp = opp + arr
    opp = opp + _sp_side_total(D['opp_sp'], state['cap_remaining_opp'])
    return my, opp


def pwin(my: np.ndarray, opp: np.ndarray) -> float:
    return float((my > opp).mean() + 0.5 * (my == opp).mean())


def variance_sensitivity(state, my: np.ndarray, opp: np.ndarray,
                         scale: float = 1.2) -> dict:
    """dP(win)/d(variance): rescale MY remaining-FP deviations around their mean
    (the 'variance-scaled bench alternative' at team level) and re-measure P(win)."""
    base_score = float(state['mu']['my_score'])
    rem = my - base_score
    mu_rem = rem.mean()
    hi = base_score + mu_rem + (rem - mu_rem) * scale
    lo = base_score + mu_rem + (rem - mu_rem) / scale
    p0 = pwin(my, opp)
    return {
        'pwin_var_up20': round(pwin(hi, opp), 4),
        'pwin_var_down20': round(pwin(lo, opp), 4),
        'dpwin_dvar': round(pwin(hi, opp) - pwin(lo, opp), 4),
        'baseline': round(p0, 4),
    }


def classify_regime(p: float) -> str:
    if p < TRAILING_MAX:
        return 'TRAILING'
    if p > LEADING_MIN:
        return 'LEADING'
    return 'CLOSE'


REGIME_BLURB = {
    'TRAILING': 'variance is an ASSET — prefer boom/bust (high-sigma, high boom%) plays',
    'LEADING': 'variance is a LIABILITY — prefer floor (SAFE-tier, low bust%) plays',
    'CLOSE': 'E[FP] is approximately the right objective — rank by expected points',
}


# ─────────────────────────────────────────────────────────────────────────────
# LEVERAGE ADVICE (Delta-P(win) per actionable decision)
# ─────────────────────────────────────────────────────────────────────────────

def hitter_sit_priority(state, D, base_p, opp_total):
    """Delta-P(win) of ZEROING each of my hitters' remaining games — the
    'if a lineup slot forces a sit, sit the least-costly profile' ranking.
    (BE counts as active for Josh, so a literal swap is a choice of which
    13 hitters score; marginal Delta-P(win) is the honest lever.)"""
    rows = []
    for h in state['my_hitters']:
        my2, _ = assemble(state, D, zero_hitters={h['name']})
        dp = pwin(my2, opp_total) - base_p
        st = series_stats(emp_series(h['mlbam'], 'H'), H_BOOM, H_BUST)
        rows.append({'name': h['name'], 'n_games': h['n_games'],
                     'mean_g': round(h['mean_g'], 2),
                     'dpwin_if_benched': round(dp, 4),
                     'emp_sigma': st['std'], 'boom_pct': st['boom_pct'],
                     'bust_pct': st['bust_pct'], 'slot': h['slot']})
    rows.sort(key=lambda r: -r['dpwin_if_benched'])  # least costly (closest to 0/positive) first
    return rows


def sp_bench_scenarios(state, D, base_p, opp_total):
    """Delta-P(win) of CAP-BENCHING each remaining start (mirror of sp_bench_mc
    but scored in win-prob space with boom/floor regime tags)."""
    try:
        from scripts.xfp.lib.extra_lenses import floor_lens
    except Exception:
        floor_lens = lambda name: None  # noqa: E731
    rows = []
    for d in D['my_sp']:
        e = d['event']
        my2, _ = assemble(state, D, bench_starts={(e['name'], e['date'])})
        dp = pwin(my2, opp_total) - base_p
        st = series_stats(emp_series(e['mlbam'], 'SP'), SP_BOOM, SP_BUST)
        fl = None
        try:
            fl = floor_lens(e['name'])
        except Exception:
            fl = None
        rows.append({'name': e['name'], 'date': e['date'], 'opp': e['opp'],
                     'confirmed': e['confirmed'],
                     'model_fp': round(e['model_fp'], 2),
                     'marcel_il': (e.get('data_quality_tag') == 'marcel_il'),
                     'dpwin_if_benched': round(dp, 4),
                     'emp_boom_pct': st['boom_pct'], 'emp_bust_pct': st['bust_pct'],
                     'emp_n': st['n'],
                     'floor_tier': (fl or {}).get('tier'),
                     'floor_bust_prob': (fl or {}).get('bust_prob')})
    rows.sort(key=lambda r: -r['dpwin_if_benched'])
    return rows


def fa_streamer_adds(state, D, base_p, opp_total, regime, max_candidates=8):
    """Top FA SP streamer adds: FA pool (size=2000 — never per-position, gotcha #6)
    x confirmed probables left this week (all-30 MLB schedule), scored by
    Delta-P(win) of ADDING that start under the chronological cap."""
    league = state['mu']['league_obj']
    try:
        fas = league.free_agents(size=2000)
    except Exception as exc:
        print(f'  WARN fa pool fetch failed: {exc}')
        return []
    today_s = state['today'].isoformat()
    week_end_s = state['week_end'].isoformat()

    # probable-pitcher events left this week, keyed (norm_name, team_id)
    probables = {}
    for tid, games in state['mlb_sched_all'].items():
        for g in games:
            if not (today_s <= g['date'] <= week_end_s):
                continue
            pid, pname = g.get('my_probable_id'), g.get('my_probable_name')
            if pid and pname:
                probables.setdefault((_norm(pname), tid), []).append(
                    {'pid': int(pid), 'date': g['date'], 'opp': g['opp_team']})

    # FA pool -> (norm_name, team_id) match. Full-name + team join (collision-safe
    # per gotcha #10 — never last-name contains). free_agents() IS the live
    # availability verification (gotcha: PL rank / percent_owned are not).
    cands = []
    for p in fas:
        pos = (getattr(p, 'position', '') or '')
        elig = set(getattr(p, 'eligibleSlots', []) or [])
        if pos not in ('SP', 'RP', 'P') and 'SP' not in {str(s) for s in elig}:
            continue
        inj = str(getattr(p, 'injuryStatus', '') or '').upper()
        if inj in IL_INJURY_STATES and inj != 'DAY_TO_DAY':
            continue
        tid = ESPN_TO_MLB_TEAM.get((getattr(p, 'proTeam', '') or '').upper())
        if tid is None:
            continue
        hits = probables.get((_norm(p.name), tid))
        if not hits:
            continue
        cands.append({'player': p, 'starts': hits, 'team_id': tid})

    if not cands:
        return []

    # rp3 frame for per-start EV + marcel_il tag; Stuff+ fallback deliberately
    # NOT loaded here (sp_stuff_model.build() is heavy) — marcel rows just get
    # flagged so /sp-stuff-board can re-rank them.
    try:
        rp3 = pd.read_csv(OUT / 'xfp_rp3_projections.csv',
                          usecols=['pitcher', 'xfp_rp3_per_start', 'xfp_rp3_sigma',
                                   'data_quality_tag'])
        rp3_by_id = {int(r['pitcher']): r for _, r in rp3.iterrows()}
    except Exception:
        rp3_by_id = {}

    scored = []
    for c in cands:
        s0 = c['starts'][0]
        info = rp3_by_id.get(s0['pid'])
        per_start = (float(info['xfp_rp3_per_start'])
                     if info is not None and pd.notna(info['xfp_rp3_per_start']) else None)
        scored.append((per_start or FALLBACK_SP_PER_START, c, info))
    scored.sort(key=lambda t: -t[0])
    scored = scored[:max_candidates]

    rng = D['rng']
    n_sims = D['n_sims']
    rows = []
    for per_start_ev, c, info in scored:
        p = c['player']
        s0 = c['starts'][0]
        emp = emp_series(s0['pid'], 'SP')
        sigma = (float(info['xfp_rp3_sigma'])
                 if info is not None and pd.notna(info.get('xfp_rp3_sigma'))
                 else fallback_sigma('SP', default=SIGMA_PER_SP_START))
        fp_draw = _blend_draws(rng, emp, per_start_ev, sigma, K_PRIOR_SP, n_sims)
        extra = [{'event': {'name': p.name, 'date': s0['date'], 'opp': s0['opp'],
                            'confirmed': True, 'mlbam': s0['pid']},
                  'fp': fp_draw, 'occ': np.ones(n_sims, dtype=bool)}]
        my2, _ = assemble(state, D, extra_my_sp=extra)
        dp = pwin(my2, opp_total) - base_p
        st = series_stats(emp, SP_BOOM, SP_BUST)
        rows.append({'name': p.name, 'team': getattr(p, 'proTeam', ''),
                     'date': s0['date'], 'opp': s0['opp'],
                     'per_start_ev': round(per_start_ev, 2),
                     'marcel_il': bool(info is not None
                                       and info.get('data_quality_tag') == 'marcel_il'),
                     'dpwin_if_added': round(dp, 4),
                     'emp_boom_pct': st['boom_pct'], 'emp_bust_pct': st['bust_pct'],
                     'emp_n': st['n'],
                     'pct_owned': round(float(getattr(p, 'percent_owned', 0) or 0), 1)})
    # Delta-P(win) is the headline sort; regime breaks near-ties via boom/bust
    if regime == 'TRAILING':
        rows.sort(key=lambda r: (-r['dpwin_if_added'], -(r['emp_boom_pct'] or 0)))
    elif regime == 'LEADING':
        rows.sort(key=lambda r: (-r['dpwin_if_added'], (r['emp_bust_pct'] or 100)))
    else:
        rows.sort(key=lambda r: -r['dpwin_if_added'])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Calibration smoke test (--calibrate)
# ─────────────────────────────────────────────────────────────────────────────

def calibrate(periods_arg: str, n_sims: int, seed: int):
    """Re-sim closed periods as-of their start. Reconstruction: realized event
    counts (games/starts/appearances) come from the boxscore store inside the
    period window; the FP DISTRIBUTION each event is drawn from is strictly
    PRE-period (leakage-safe). Checks whether the realized team total and the
    realized margin land inside the simulated middle-80% band.

    Honest caveats (smoke test, not a protocol run):
      - lineups are as-of the period's final box score (intra-week adds/drops
        smear), and all MLB games by rostered players count (bench-day games a
        passive manager left unscored inflate the sim for THAT side);
      - period->calendar mapping assumes 7-day periods aligned to the current
        week (true for BrownU regular season).
    """
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    cur = league.currentMatchupPeriod
    today = _today_et()
    week_start_cur = today - timedelta(days=today.weekday())
    try:
        _mp = getattr(league.settings, 'matchup_periods', {}) or {}
    except Exception:
        _mp = {}

    if periods_arg == 'auto':
        periods = [cur - 2, cur - 1]
    else:
        periods = [int(x) for x in periods_arg.split(',') if x.strip()]
    periods = [p for p in periods if 1 <= p < cur]
    if not periods:
        print('No closed periods to calibrate against.')
        return []

    box_p, box_h = _box('P'), _box('H')
    results = []
    for per in periods:
        # Period-aware window: use the documented override for a multi-week/ASG
        # period, else the 7-day offset from the current week (BrownU default).
        pw = period_window(per)
        if pw is not None:
            win_start, win_end = pw
        else:
            offset = cur - per
            win_start = week_start_cur - timedelta(days=7 * offset)
            win_end = win_start + timedelta(days=6)
        per_cap = sp_cap_for_period(per, weeks=weeks_in_period(_mp, per))
        ws, we = win_start.isoformat(), win_end.isoformat()
        print(f'\n--- calibrate period {per}: {ws} -> {we} ---')

        # Past-period lineups require a scoring_period hint (ESPN daily id);
        # without it box_scores returns period totals with EMPTY lineups.
        sp_hint = league.scoringPeriodId - (today - win_end).days
        target = None
        for bs in league.box_scores(matchup_period=per, scoring_period=sp_hint):
            for side, other in (('home', 'away'), ('away', 'home')):
                t = getattr(bs, f'{side}_team', None)
                if t and 'Ligers' in getattr(t, 'team_name', ''):
                    target = {'my_score': getattr(bs, f'{side}_score'),
                              'opp_score': getattr(bs, f'{other}_score'),
                              'my_lineup': getattr(bs, f'{side}_lineup'),
                              'opp_lineup': getattr(bs, f'{other}_lineup'),
                              'opp_name': getattr(getattr(bs, f'{other}_team'), 'team_name', '?')}
            if target:
                break
        if not target:
            print(f'  period {per}: no Ligers box score found — skipped')
            continue

        pooled = {b: pooled_series(b, before=ws) for b in ('SP', 'RP', 'H')}
        rng = np.random.default_rng(seed + per)

        def _sim_side(lineup):
            total = np.zeros(n_sims)
            n_events = {'H': 0, 'SP': 0, 'RP': 0}
            start_events = []  # (date, draws) for the 10-cap
            for p in lineup:
                mlbam = resolve_player_mlbam(p)
                if not mlbam:
                    continue
                mlbam = int(mlbam)
                # realized in-window events from the boxscore store
                if box_p is not None:
                    sub = box_p[(box_p['mlbam_id'] == mlbam)]
                    sub = sub[(sub['game_date'].astype(str) >= ws)
                              & (sub['game_date'].astype(str) <= we)]
                    for _, r in sub[sub['gs'] == 1].iterrows():
                        emp = emp_series(mlbam, 'SP', before=ws)
                        src = emp if len(emp) >= 5 else pooled['SP']
                        start_events.append((str(r['game_date']),
                                             rng.choice(np.asarray(src), n_sims)))
                        n_events['SP'] += 1
                    n_rp = int((sub['gs'] == 0).sum())
                    if n_rp:
                        emp = emp_series(mlbam, 'RP', before=ws)
                        src = emp if len(emp) >= 5 else pooled['RP']
                        for _ in range(n_rp):
                            total += rng.choice(np.asarray(src), n_sims)
                        n_events['RP'] += n_rp
                if box_h is not None:
                    subh = box_h[(box_h['mlbam_id'] == mlbam)]
                    subh = subh[(subh['game_date'].astype(str) >= ws)
                                & (subh['game_date'].astype(str) <= we)]
                    n_hg = len(subh)
                    if n_hg:
                        emp = emp_series(mlbam, 'H', before=ws)
                        src = emp if len(emp) >= 5 else pooled['H']
                        for _ in range(n_hg):
                            total += rng.choice(np.asarray(src), n_sims)
                        n_events['H'] += n_hg
            # chronological start cap (period-aware: 10 default, 16 for ASG)
            start_events.sort(key=lambda t: t[0])
            for i, (_, draws) in enumerate(start_events):
                if i < per_cap:
                    total += draws
            return total, n_events

        my_sim, my_ev = _sim_side(target['my_lineup'])
        opp_sim, opp_ev = _sim_side(target['opp_lineup'])
        margin_sim = my_sim - opp_sim
        real_margin = target['my_score'] - target['opp_score']

        def band(a):
            return float(np.percentile(a, 10)), float(np.percentile(a, 90))

        my_lo, my_hi = band(my_sim)
        mg_lo, mg_hi = band(margin_sim)
        ok_total = my_lo <= target['my_score'] <= my_hi
        ok_margin = mg_lo <= real_margin <= mg_hi
        print(f"  vs {target['opp_name']}  realized {target['my_score']:.0f}-"
              f"{target['opp_score']:.0f} (margin {real_margin:+.0f})")
        print(f"  events mine H/SP/RP = {my_ev['H']}/{my_ev['SP']}/{my_ev['RP']}  "
              f"opp = {opp_ev['H']}/{opp_ev['SP']}/{opp_ev['RP']}")
        print(f"  sim my_total  p10-p90 [{my_lo:.0f}, {my_hi:.0f}]  "
              f"realized {target['my_score']:.0f}  -> {'INSIDE' if ok_total else 'OUTSIDE'}")
        print(f"  sim margin    p10-p90 [{mg_lo:+.0f}, {mg_hi:+.0f}]  "
              f"realized {real_margin:+.0f}  -> {'INSIDE' if ok_margin else 'OUTSIDE'}")
        results.append({'period': per, 'window': [ws, we],
                        'realized_my': float(target['my_score']),
                        'realized_margin': float(real_margin),
                        'sim_my_p10_p90': [round(my_lo, 1), round(my_hi, 1)],
                        'sim_margin_p10_p90': [round(mg_lo, 1), round(mg_hi, 1)],
                        'my_total_inside_80': bool(ok_total),
                        'margin_inside_80': bool(ok_margin)})
    return results


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='/matchup-leverage engine — win-prob strategy layer')
    ap.add_argument('--sims', type=int, default=10000)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--simulate-only', action='store_true',
                    help='State + P(win) + regime only (skip Delta-P(win) advice)')
    ap.add_argument('--calibrate', default=None,
                    help='"auto" or comma-separated closed period numbers — run the '
                         'calibration smoke test instead of the live advice flow')
    args = ap.parse_args()

    if args.calibrate:
        res = calibrate(args.calibrate, args.sims, args.seed)
        path = OUT / 'matchup_leverage_calibration.json'
        path.write_text(json.dumps(res, indent=2), encoding='utf-8')
        print(f'\nwrote {path}')
        return

    print('=== /matchup-leverage ===')
    print('Building live matchup state...')
    state = build_state()
    print(f"  mine: {len(state['my_hitters'])} hitters, {len(state['my_rps'])} RPs, "
          f"{len(state['my_sp_events'])} SP starts remaining "
          f"(banked {state['banked_mine']}, cap_remaining {state['cap_remaining_mine']})")
    print(f"  opp:  {len(state['opp_hitters'])} hitters, {len(state['opp_rps'])} RPs, "
          f"{len(state['opp_sp_events'])} SP starts remaining "
          f"(banked {state['banked_opp']}, cap_remaining {state['cap_remaining_opp']})")

    print(f'Simulating rest of matchup ({args.sims} draws)...')
    D = precompute_draws(state, args.sims, args.seed)
    my, opp = assemble(state, D)
    base_p = pwin(my, opp)
    vs = variance_sensitivity(state, my, opp)
    regime = classify_regime(base_p)
    margin = my - opp

    print('\n--- STATE ---')
    _cov = 'OVERRIDE' if state['period_covered'] else 'default'
    print(f"  period {state['period']}  SP cap {state['sp_cap']} ({_cov})  "
          f"window {state['week_start']} -> {state['week_end']}")
    print(f"  Ligers {state['mu']['my_score']:.1f}  vs  "
          f"{state['mu']['opp'].team_name} {state['mu']['opp_score']:.1f}   "
          f"(days left incl today: {state['days_remaining']})")
    print(f"  SP starts banked/cap: mine {state['banked_mine']}/{state['sp_cap']} "
          f"(remaining {state['cap_remaining_mine']}), "
          f"opp {state['banked_opp']}/{state['sp_cap']} "
          f"(remaining {state['cap_remaining_opp']})")
    print(f"  projected final: {my.mean():.0f} vs {opp.mean():.0f}   "
          f"margin p10/p50/p90 = {np.percentile(margin,10):+.0f} / "
          f"{np.percentile(margin,50):+.0f} / {np.percentile(margin,90):+.0f}")
    print(f"  P(win) = {base_p*100:.1f}%")
    print(f"  variance sensitivity: +20% my variance -> {vs['pwin_var_up20']*100:.1f}%, "
          f"-20% -> {vs['pwin_var_down20']*100:.1f}%  (dP/dVar {vs['dpwin_dvar']*100:+.2f}pp)")
    print(f"  REGIME: {regime} — {REGIME_BLURB[regime]}")

    payload = {
        'generated': str(state['today']), 'period': state['mu']['period'],
        'opp_team': state['mu']['opp'].team_name,
        'my_score': float(state['mu']['my_score']),
        'opp_score': float(state['mu']['opp_score']),
        'days_remaining_incl_today': state['days_remaining'],
        'sims': args.sims,
        'pwin': round(base_p, 4),
        'proj_final_mine': round(float(my.mean()), 1),
        'proj_final_opp': round(float(opp.mean()), 1),
        'margin_p10_p50_p90': [round(float(np.percentile(margin, q)), 1) for q in (10, 50, 90)],
        'variance_sensitivity': vs,
        'regime': regime,
        'regime_note': REGIME_BLURB[regime],
        'sp_cap': state['sp_cap'],
        'period_weeks': state['period_weeks'],
        'period_covered': state['period_covered'],
        'period_window': [str(state['week_start']), str(state['week_end'])],
        'banked_sp_starts': state['banked_mine'],
        'banked_sp_starts_opp': state['banked_opp'],
        'cap_remaining': state['cap_remaining_mine'],
        'cap_remaining_opp': state['cap_remaining_opp'],
        'rule13': 'decision layer only — projections (rh3/rp3/rprs2) untouched',
    }

    if not args.simulate_only:
        print('\n--- (a) HITTER SIT-PRIORITY (Delta-P(win) if benched; least costly first) ---')
        hp = hitter_sit_priority(state, D, base_p, opp)
        for r in hp[:8]:
            print(f"  {r['name']:<24} g={r['n_games']} mean/g={r['mean_g']:>5.2f} "
                  f"sigma={r['emp_sigma'] if r['emp_sigma'] is not None else '-':>4} "
                  f"boom%={r['boom_pct'] if r['boom_pct'] is not None else '-':>3} "
                  f"bust%={r['bust_pct'] if r['bust_pct'] is not None else '-':>3} "
                  f"dP(win) if benched: {r['dpwin_if_benched']*100:+.2f}pp")
        payload['hitter_sit_priority'] = hp

        print('\n--- (b) SP START SCENARIOS (Delta-P(win) if CAP-BENCHED) ---')
        sb = sp_bench_scenarios(state, D, base_p, opp)
        if not sb:
            print('  no remaining SP starts this period')
        for r in sb:
            tag = []
            if r['floor_tier']:
                tag.append(f"floor={r['floor_tier']}")
            if r['marcel_il']:
                tag.append('marcel_il')
            print(f"  {r['name']:<22} {r['date'] or '?'} vs {str(r['opp'] or '?'):<4} "
                  f"{'CONF' if r['confirmed'] else 'pred'} model {r['model_fp']:>5.1f} "
                  f"boom%={r['emp_boom_pct'] if r['emp_boom_pct'] is not None else '-':>3} "
                  f"bust%={r['emp_bust_pct'] if r['emp_bust_pct'] is not None else '-':>3} "
                  f"dP(win) if benched: {r['dpwin_if_benched']*100:+.2f}pp  {' '.join(tag)}")
        payload['sp_bench_scenarios'] = sb

        print('\n--- (c) FA STREAMER ADDS (Delta-P(win) if added; regime-aware tiebreak) ---')
        fa = fa_streamer_adds(state, D, base_p, opp, regime)
        if not fa:
            print('  no FA SP with a probable start left this period')
        for r in fa[:3]:
            print(f"  {r['name']:<22} ({r['team']}) {r['date'] or '?'} vs {str(r['opp'] or '?'):<4} "
                  f"EV {r['per_start_ev']:>5.1f}{' (marcel_il — verify via /sp-stuff-board)' if r['marcel_il'] else ''} "
                  f"boom%={r['emp_boom_pct'] if r['emp_boom_pct'] is not None else '-':>3} "
                  f"bust%={r['emp_bust_pct'] if r['emp_bust_pct'] is not None else '-':>3} "
                  f"dP(win) if added: {r['dpwin_if_added']*100:+.2f}pp")
        payload['fa_streamer_adds'] = fa[:8]

        # synthesized top moves across all three decision families
        moves = []
        for r in (sb or []):
            if r['dpwin_if_benched'] > 0:
                moves.append({'move': f"CAP-BENCH {r['name']} {r['date']} vs {r['opp']}",
                              'dpwin': r['dpwin_if_benched'],
                              'why': f"start is net-negative in win-prob space "
                                     f"(bust% {r['emp_bust_pct']}, floor {r['floor_tier']})"})
        for r in (fa or [])[:3]:
            if r['dpwin_if_added'] > 0:
                moves.append({'move': f"ADD {r['name']} (FA) for {r['date']} vs {r['opp']}",
                              'dpwin': r['dpwin_if_added'],
                              'why': f"extra cap-eligible start, EV {r['per_start_ev']}, "
                                     f"boom% {r['emp_boom_pct']}"})
        moves.sort(key=lambda m: -m['dpwin'])
        payload['top_moves'] = moves[:5]
        print('\n--- TOP Delta-P(win) MOVES ---')
        if not moves:
            print('  no positive-dP(win) roster move found — hold the line; '
                  'regime guidance above still applies to daily lineup calls')
        for m in moves[:3]:
            print(f"  {m['dpwin']*100:+.2f}pp  {m['move']}  — {m['why']}")

    path = OUT / 'matchup_leverage.json'
    path.write_text(json.dumps(payload, indent=2, default=float), encoding='utf-8')
    print(f'\nwrote {path}')


if __name__ == '__main__':
    main()
