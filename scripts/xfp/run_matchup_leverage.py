"""run_matchup_leverage — /matchup-leverage engine (win-probability strategy layer).

THE INSIGHT: every other skill maximizes expected FP, but BrownU H2H is won by
P(my_total > opp_total). When TRAILING, variance is an ASSET (prefer boom/bust);
when LEADING, variance is a LIABILITY (prefer floor); when CLOSE, E[FP] is ~right.
Nothing else in the repo reasons this way.

RULE 13 (decision layer only): this NEVER touches rh3/rp3/rprs2/baseline xFP.
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

# ── THE ENGINE lives in lib/leverage_engine (extracted 2026-07-29) ───────────
# This file is now a thin CLI + the advice families. The MC engine, state
# assembly and the Delta-P(win) primitive are shared with the weekly optimizer
# and the dpwin history logger so there is exactly ONE implementation.
from scripts.xfp.lib.leverage_engine import (  # noqa: E402
    # constants
    CACHE, OUT, BOX_P, BOX_H,
    K_PRIOR_SP, K_PRIOR_H, K_PRIOR_RP, EMP_LAST_N, UNCONFIRMED_START_P,
    TRAILING_MAX, LEADING_MIN,
    # empirical series
    emp_series, pooled_series, series_stats, _box,
    # draws
    _blend_draws, _hitter_total_draws, _rp_total_draws,
    candidate_rng, _draw_key,
    # state + MC
    resolve_player_mlbam, banked_sp_starts_from_box, build_state,
    precompute_draws, _sp_side_total, assemble, pwin, mc_se,
    delta_pwin, ensure_candidate_draws,
    variance_sensitivity, classify_regime, REGIME_BLURB,
)
# Upstream names the advice families + calibrate still reference directly.
from build_matchup_dashboard import (  # noqa: E402
    project_player, player_mlbam_lookup, _resolve_pitcher_mlbam,
    _is_active_slot, _today_et, _norm,
    IL_INJURY_STATES, ESPN_TO_MLB_TEAM,
    SIGMA_PER_SP_START, SIGMA_PER_RP_GAME, FALLBACK_SP_PER_START,
    fetch_schedules_by_team, build_sp_starts_by_pitcher, get_matchup,
    load_projections,
)
from scripts.xfp.lib.pitcher_role import detect_pitcher_role  # noqa: E402
from scripts.xfp.lib.boom_bust import (  # noqa: E402
    SP_BOOM, SP_BUST, H_BOOM, H_BUST, RP_BOOM, RP_BUST,
)
from plv_clone.cap_math import (  # noqa: E402
    sp_cap_for_period, period_window, is_period_covered, weeks_in_period,
)
from scripts.xfp.lib.period_meta import (  # noqa: E402
    resolve_period_meta, espn_period_meta,
)
from scripts.xfp.lib.variance_bands import fallback_sigma  # noqa: E402


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
