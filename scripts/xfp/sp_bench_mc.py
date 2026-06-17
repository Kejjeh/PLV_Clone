"""SP-bench Monte Carlo — decision tool.

Compares bench scenarios for the current week's matchup, using empirical
pitcher game-log FP distributions (2024+2025+2026) blended with rp3 priors.
Models the EV-based 10-SP cap inside each MC trial.

Addresses the structural gaps in the prior inline analysis:
  - real per-pitcher samples (n=30+, not n=4)
  - matchup conditioning via opp_factor
  - opp SPs treated distributionally too
  - EV-based cap modeled inside each trial (matches apply_sp_cap)
  - Bayesian blend prior to avoid small-n sandbagging (Rodon n=2 post-IL)
  - self-aware verdict that flags when MC isn't earning its complexity

Usage:
    python scripts/xfp/sp_bench_mc.py
    python scripts/xfp/sp_bench_mc.py --bench Soriano --bench Warren
    python scripts/xfp/sp_bench_mc.py --prior empirical
"""
from __future__ import annotations
import argparse
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

# Reuse dashboard internals (don't reimplement)
from build_matchup_dashboard import (
    get_matchup,
    load_projections,
    fetch_schedules_by_team,
    build_sp_starts_by_pitcher,
    player_mlbam_lookup,
    _resolve_mlbam_via_api,
    _norm,
    _fetch_json,
    project_player,
    apply_sp_cap,
    MAX_SP_STARTS_PER_WEEK,
    ESPN_TO_MLB_TEAM,
    SIGMA_PER_SP_START,
)

CACHE = ROOT / 'data' / 'research' / 'xfp_cache'


# ─── per-start FP fetcher ─────────────────────────────────────────────
def sp_fp_from_stat(stat: dict) -> float:
    """BrownU SP FP = K + IP*3.3 - H - 2*ER - BB - HBP."""
    ip = float(stat.get('inningsPitched', '0') or 0)
    h = int(stat.get('hits', 0))
    er = int(stat.get('earnedRuns', 0))
    bb = int(stat.get('baseOnBalls', 0))
    k = int(stat.get('strikeOuts', 0))
    hbp = int(stat.get('hitByPitch', 0))
    return k + ip * 3.3 - h - 2 * er - bb - hbp


def fetch_pitcher_starts_multi_year(mlbam: int, years=(2024, 2025, 2026),
                                      limit: int = 30) -> list[dict]:
    """Pull most-recent `limit` started games across years (newest first)."""
    if not mlbam:
        return []
    all_starts = []
    for yr in sorted(years, reverse=True):
        url = (f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?'
               f'stats=gameLog&group=pitching&season={yr}')
        try:
            data = _fetch_json(url)
        except Exception:
            continue
        stats_list = data.get('stats') or []
        splits = stats_list[0].get('splits', []) if stats_list else []
        for s in splits:
            if int(s.get('stat', {}).get('gamesStarted', 0)) > 0:
                all_starts.append({
                    'date': s['date'],
                    'fp': sp_fp_from_stat(s['stat']),
                    'year': yr,
                })
        if len(all_starts) >= limit:
            break
    all_starts.sort(key=lambda x: x['date'], reverse=True)
    return all_starts[:limit]


# ─── distribution samplers ────────────────────────────────────────────
def _lognormal_draws(rng, mu: float, sigma: float, n: int) -> np.ndarray:
    """Match a lognormal to (mean=mu, std=sigma). Fall back to normal if mu<=0."""
    if mu <= 0 or sigma <= 0:
        return rng.normal(mu, max(sigma, 1e-6), n)
    var = sigma * sigma
    sig2 = math.log(1 + var / (mu * mu))
    lmu = math.log(mu) - sig2 / 2
    return rng.lognormal(lmu, math.sqrt(sig2), n)


def build_sp_sampler(emp_fps: list[float], rp3_mean: float, rp3_sigma: float,
                      prior: str, k_prior: int = 20):
    """Returns a fn(rng, n_trials) → np.ndarray of FP draws for ONE start.

    prior:
      'empirical' — bootstrap from emp_fps only (or fall back to rp3 if empty)
      'rp3' — lognormal from rp3_mean + rp3_sigma
      'blend' — Bayesian blend: weight = n/(n+k_prior). Rodon n=2 → 9% emp,
                Valdez n=30 → 60% emp.
    """
    n_emp = len(emp_fps)
    emp_arr = np.array(emp_fps, dtype=float) if n_emp else None
    sigma = rp3_sigma if rp3_sigma and rp3_sigma > 0 else SIGMA_PER_SP_START

    if prior == 'rp3' or n_emp == 0:
        def _draw(rng, n):
            return _lognormal_draws(rng, rp3_mean, sigma, n)
        emp_weight = 0.0
    elif prior == 'empirical':
        def _draw(rng, n):
            return rng.choice(emp_arr, size=n, replace=True)
        emp_weight = 1.0
    else:  # blend
        w = n_emp / (n_emp + k_prior)
        def _draw(rng, n):
            mask = rng.random(n) < w
            n_emp_draws = int(mask.sum())
            out = _lognormal_draws(rng, rp3_mean, sigma, n)
            if n_emp_draws > 0:
                out[mask] = rng.choice(emp_arr, size=n_emp_draws, replace=True)
            return out
        emp_weight = w
    return _draw, emp_weight


# ─── matchup state assembly ───────────────────────────────────────────
def _predict_rotation_starts_robust(mlbam, team_id, schedules_by_team,
                                     confirmed_dates, today, week_end):
    """Like dashboard's _predict_rotation_starts but uses MEDIAN gap across
    the last several starts (more robust to skipped/double turns).

    The dashboard's predictor uses the gap between the two most recent starts
    only — if the pitcher just skipped a turn (Warren's 5/19 ← 5/12 = 7-day
    gap), it extrapolates the skipped gap forward and misses real starts.
    """
    if not mlbam:
        return []
    try:
        url = (f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?'
               f'stats=gameLog&group=pitching&season={today.year}')
        data = _fetch_json(url)
    except Exception:
        return []
    stats_list = data.get('stats') or []
    splits = stats_list[0].get('splits', []) if stats_list else []
    starts = [s for s in splits
              if int(s.get('stat', {}).get('gamesStarted', 0)) > 0]
    if not starts:
        return []
    starts.sort(key=lambda s: s['date'], reverse=True)
    dates = [datetime.fromisoformat(s['date']).date() for s in starts[:6]]
    latest_actual = dates[0]
    gaps = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
    if gaps:
        gap = int(np.clip(np.median(gaps), 4, 7))
    else:
        gap = 5

    confirmed_dt = [datetime.fromisoformat(d).date() for d in confirmed_dates]
    anchor = max([latest_actual] + confirmed_dt)
    team_games = schedules_by_team.get(team_id, [])
    team_dates_in_window = {g['date']: g for g in team_games
                              if today.isoformat() <= g['date'] <= week_end.isoformat()}
    predicted = []
    nd = anchor
    for _ in range(3):
        nd = nd + timedelta(days=gap)
        if nd > week_end:
            break
        if any(abs((nd - cd).days) <= 1 for cd in confirmed_dt):
            continue
        match_game = None
        # Match within ±2 days (was ±1 in dashboard) — wider net for cases where
        # rotation slot drifts by a day due to off-days
        for offset in (0, 1, -1, 2, -2):
            d_try = (nd + timedelta(days=offset)).isoformat()
            if (d_try in team_dates_in_window
                    and today.isoformat() <= d_try <= week_end.isoformat()):
                match_game = team_dates_in_window[d_try]
                break
        if match_game:
            predicted.append({
                'date': match_game['date'],
                'opp_team': match_game['opp_team'],
                'my_probable_id': mlbam,
                'confirmed': False,
            })
    return predicted


def collect_remaining_sp_starts(team_lineup, schedules_by_team, today, week_end,
                                  extra_starts=None):
    """For each SP in lineup, return list of remaining-week starts.

    extra_starts: optional list of (pitcher_name, date_iso, opp_team) tuples
    to force-include (use when rotation predictor misses a known start).

    Returns list of (pitcher_name, mlbam, start_dict) tuples.
    """
    starts = []
    name_to_mlbam = {}
    for p in team_lineup:
        pos = p.position or '?'
        if pos != 'SP':
            continue
        if getattr(p, 'injured', False):
            continue
        mlbam = player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)
        if not mlbam:
            continue
        name_to_mlbam[p.name] = mlbam
        team_abbr = (p.proTeam or '').upper()
        team_id = ESPN_TO_MLB_TEAM.get(team_abbr)
        if team_id is None:
            continue
        team_games = schedules_by_team.get(team_id, [])
        confirmed = [g for g in team_games
                      if g.get('my_probable_id') == mlbam]
        confirmed_dates = [g['date'] for g in confirmed]
        predicted = _predict_rotation_starts_robust(
            mlbam, team_id, schedules_by_team, confirmed_dates, today, week_end)
        for g in confirmed + predicted:
            starts.append((p.name, mlbam, {
                'date': g['date'],
                'opp_team': g['opp_team'],
            }))
    # Layer in any manually-included starts (dedup by name+date)
    if extra_starts:
        seen = {(n, sd['date']) for n, _, sd in starts}
        for name, date_iso, opp in extra_starts:
            mlbam = name_to_mlbam.get(name)
            if not mlbam:
                continue
            if (name, date_iso) in seen:
                continue
            starts.append((name, mlbam, {'date': date_iso, 'opp_team': opp.upper()}))
    return starts


def make_opp_factor(opp_team: str, ts_map: dict, opp_window: str = 'season') -> float:
    """Mirror dashboard's rule. opp_window='season' uses bat_index, 'recent'
    uses bat_index_recent (must reload ts_map from team_strength_2026.csv for recent)."""
    key = 'bat_index_recent' if opp_window == 'recent' else 'bat_index'
    opp_idx = ts_map.get(opp_team, {}).get(key) or 1.0
    return max(0.80, min(1.20, 1.0 / opp_idx))


def banked_sp_starts_count(team_lineup, schedules_by_team, today, week_end) -> int:
    """How many SP starts ALREADY happened this scoring week (banked into WTD)."""
    week_start = today - timedelta(days=today.weekday())
    if today == week_start:
        return 0
    count = 0
    for p in team_lineup:
        if (p.position or '?') != 'SP':
            continue
        mlbam = player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)
        if not mlbam:
            continue
        try:
            url = (f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats?'
                   f'stats=gameLog&group=pitching&season={today.year}')
            data = _fetch_json(url)
        except Exception:
            continue
        stats_list = data.get('stats') or []
        splits = stats_list[0].get('splits', []) if stats_list else []
        for s in splits:
            d = s.get('date', '')
            if (week_start.isoformat() <= d < today.isoformat()
                    and int(s.get('stat', {}).get('gamesStarted', 0)) > 0):
                count += 1
    return count


# ─── MC harness ───────────────────────────────────────────────────────
def run_mc(my_proj, opp_proj, mu_state, sp_samplers_mine, sp_samplers_opp,
           remaining_starts_mine, remaining_starts_opp, ts_map, opp_window,
           bench_set: set[str], cap_remaining_mine: int, cap_remaining_opp: int,
           n_trials: int, seed: int, cap_rule: str = 'chronological'):
    """Runs MC; returns (my_totals, opp_totals)."""
    rng = np.random.default_rng(seed=seed)

    # Non-SP contribution: lognormal per player (fp, sigma2 from project_player).
    # SPs from project_player are REPLACED by our sampler-driven draws.
    def _non_sp_total(proj_dict):
        total = np.zeros(n_trials)
        for name, p in proj_dict.items():
            if 'breakdown' in p and any(b.get('type') == 'start'
                                          for b in p['breakdown']):
                continue  # skip SP, handled separately
            fp = p.get('fp', 0)
            sig = math.sqrt(p.get('sigma2', 0))
            total = total + _lognormal_draws(rng, fp, sig, n_trials)
        return total

    my_non_sp = _non_sp_total(my_proj)
    opp_non_sp = _non_sp_total(opp_proj)

    # SP contribution per team — with cap mechanics inside each trial.
    # BrownU rule is CHRONOLOGICAL (starts 11+ are zeros, regardless of FP),
    # NOT EV-based. The dashboard's apply_sp_cap uses EV-based but that's a
    # projection convention; the live league rule is by start-order.
    def _sp_total(remaining_starts, samplers, bench_set, cap_remaining, cap_rule):
        if not remaining_starts:
            return np.zeros(n_trials)
        # Sort chronologically (same-day tiebreak: name) — matches live rule
        sorted_starts = sorted(remaining_starts, key=lambda x: (x[2]['date'], x[0]))
        active = [(n, m, sd) for n, m, sd in sorted_starts if n not in bench_set]

        if cap_rule == 'chronological':
            kept = active[:cap_remaining]
            total = np.zeros(n_trials)
            for pname, _, sd in kept:
                draw, _ = samplers[pname]
                base = draw(rng, n_trials)
                opp_factor = make_opp_factor(sd['opp_team'], ts_map, opp_window)
                total = total + base * opp_factor
            return total
        else:  # ev — dashboard projection convention
            n_starts = len(active)
            if n_starts == 0:
                return np.zeros(n_trials)
            mat = np.zeros((n_starts, n_trials))
            for i, (pname, _, sd) in enumerate(active):
                draw, _ = samplers[pname]
                base = draw(rng, n_trials)
                opp_factor = make_opp_factor(sd['opp_team'], ts_map, opp_window)
                mat[i, :] = base * opp_factor
            if n_starts > cap_remaining:
                sorted_desc = -np.sort(-mat, axis=0)
                kept = sorted_desc[:cap_remaining, :]
                return kept.sum(axis=0)
            return mat.sum(axis=0)

    my_sp = _sp_total(remaining_starts_mine, sp_samplers_mine, bench_set,
                       cap_remaining_mine, cap_rule)
    opp_sp = _sp_total(remaining_starts_opp, sp_samplers_opp, set(),
                        cap_remaining_opp, cap_rule)

    my_total = mu_state['my_score'] + my_non_sp + my_sp
    opp_total = mu_state['opp_score'] + opp_non_sp + opp_sp
    return my_total, opp_total


def bootstrap_ci(samples: np.ndarray, n_resamples: int = 1000,
                 ci: float = 0.95) -> tuple[float, float]:
    """95% bootstrap CI for a sample mean."""
    rng = np.random.default_rng(seed=99)
    n = len(samples)
    means = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, n)
        means.append(samples[idx].mean())
    means = np.array(means)
    lo = float(np.percentile(means, (1 - ci) / 2 * 100))
    hi = float(np.percentile(means, (1 + ci) / 2 * 100))
    return lo, hi


# ─── main ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='SP-bench Monte Carlo decision tool')
    parser.add_argument('--bench', action='append', default=[],
                        help='SP name to evaluate benching (repeatable). '
                             'Default: auto-enumerate all healthy SPs with remaining starts.')
    parser.add_argument('--prior', choices=['empirical', 'rp3', 'blend'],
                        default='blend')
    parser.add_argument('--history-window', type=int, default=30,
                        help='Max recent starts per pitcher (default 30)')
    parser.add_argument('--trials', type=int, default=10000)
    parser.add_argument('--opp-window', choices=['season', 'recent'], default='recent',
                        help="bat_index window for opp_factor ('recent' = last 35d as of 2026-06-02)")
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--k-prior', type=int, default=20,
                        help='Bayesian blend prior weight (higher = trust rp3 more)')
    parser.add_argument('--add-start', action='append', default=[],
                        help='Force-include a known start the rotation predictor missed. '
                             'Format: "Pitcher Name:YYYY-MM-DD:OPP" (e.g. "Will Warren:2026-05-24:TB"). Repeatable.')
    parser.add_argument('--cap-rule', choices=['chronological', 'ev'],
                        default='chronological',
                        help='Chronological matches BrownU live rule (starts 11+ zero); '
                             'ev matches dashboard projection convention (optimistic).')
    args = parser.parse_args()

    # Parse manual start additions
    extra_starts = []
    for spec in args.add_start:
        try:
            name, date_iso, opp = spec.split(':')
            extra_starts.append((name.strip(), date_iso.strip(), opp.strip().upper()))
        except ValueError:
            print(f'  warning: ignoring malformed --add-start "{spec}" '
                  f'(expected "Name:YYYY-MM-DD:OPP")')

    print(f'\n=== SP-bench MC ({args.trials} trials, {args.prior} prior, '
          f"opp_window={args.opp_window}) ===\n")

    # Load state
    print('Loading matchup + projections...')
    mu = get_matchup()
    rh3_map, rp3_map, rp3_by_mlbam, rprs2_map, ts_map_base = load_projections()

    # Override ts_map with full team_strength (need bat_index_recent if requested)
    ts_full = pd.read_csv(CACHE / 'team_strength_2026.csv')
    ts_full['team'] = ts_full['team'].str.upper()
    ts_map = ts_full.set_index('team')[['bat_index', 'bat_index_recent']].to_dict('index')

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    print(f'  period: {mu["period"]}  week: {week_start} → {week_end} (today: {today})')
    print(f'  WTD: Ligers {mu["my_score"]:.1f} | Opp {mu["opp_score"]:.1f}')

    # Build schedules
    all_teams = set()
    for p in mu['my_lineup'] + mu['opp_lineup']:
        t = (p.proTeam or '').upper()
        if t:
            all_teams.add(t)
    print(f'  fetching schedules for {len(all_teams)} teams...')
    mlb_ids = [ESPN_TO_MLB_TEAM[t] for t in all_teams if ESPN_TO_MLB_TEAM.get(t) is not None]
    schedules_by_team = fetch_schedules_by_team(
        mlb_ids, today.isoformat(), week_end.isoformat()) if mlb_ids else {}

    # SP probable/predicted starts keyed by MLBAM — required by the refactored
    # project_player signature. Only affects the SP path of project_player,
    # which the MC discards (SPs are handled by our own sampler-driven draws via
    # collect_remaining_sp_starts); built here so project_player runs cleanly.
    sp_pitcher_ids = []
    for p in mu['my_lineup'] + mu['opp_lineup']:
        if (p.position or '?') != 'SP' or getattr(p, 'injured', False):
            continue
        mlbam = player_mlbam_lookup(p.name) or _resolve_mlbam_via_api(p.name)
        if mlbam:
            sp_pitcher_ids.append(int(mlbam))
    sp_starts_by_pitcher = build_sp_starts_by_pitcher(
        sp_pitcher_ids, schedules_by_team, today, week_end)

    # Project all players using dashboard's logic (gives us non-SP fp+sigma2)
    print('  projecting all players via dashboard logic...')
    ts_map_for_proj = {t: {'bat_index': d['bat_index'], 'pit_index': 1.0}
                        for t, d in ts_map.items()}
    my_proj = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                         rh3_map, rp3_map, rp3_by_mlbam, rprs2_map,
                                         ts_map_for_proj, today, week_end)
               for p in mu['my_lineup']}
    opp_proj = {p.name: project_player(p, schedules_by_team, sp_starts_by_pitcher,
                                          rh3_map, rp3_map, rp3_by_mlbam, rprs2_map,
                                          ts_map_for_proj, today, week_end)
                for p in mu['opp_lineup']}

    # Remaining SP starts (mine + opp) — these are what the cap operates on
    remaining_mine = collect_remaining_sp_starts(mu['my_lineup'], schedules_by_team,
                                                   today, week_end, extra_starts)
    remaining_opp = collect_remaining_sp_starts(mu['opp_lineup'], schedules_by_team,
                                                  today, week_end)
    banked_mine = banked_sp_starts_count(mu['my_lineup'], schedules_by_team,
                                          today, week_end)
    banked_opp = banked_sp_starts_count(mu['opp_lineup'], schedules_by_team,
                                         today, week_end)
    cap_remaining_mine = max(MAX_SP_STARTS_PER_WEEK - banked_mine, 0)
    cap_remaining_opp = max(MAX_SP_STARTS_PER_WEEK - banked_opp, 0)
    print(f'  Ligers SP starts: {banked_mine} banked + {len(remaining_mine)} remaining '
          f'(cap_remaining={cap_remaining_mine})')
    print(f'  Opp    SP starts: {banked_opp} banked + {len(remaining_opp)} remaining '
          f'(cap_remaining={cap_remaining_opp})')

    # Per-pitcher empirical FPs + samplers
    print(f'  pulling gameLog for {len({n for n,_,_ in remaining_mine + remaining_opp})} '
          f'pitchers (last {args.history_window} starts each, 2024-2026)...')
    sp_samplers_mine = {}
    sp_samplers_opp = {}
    per_pitcher_stats = {}
    unique_mine = {(n, m) for n, m, _ in remaining_mine}
    unique_opp = {(n, m) for n, m, _ in remaining_opp}
    for name, mlbam in unique_mine | unique_opp:
        emp = fetch_pitcher_starts_multi_year(mlbam, limit=args.history_window)
        emp_fps = [s['fp'] for s in emp]
        rp_info = rp3_map.get(_norm(name), {})
        # Prefer schedule-adjusted to match dashboard convention (W1 fix)
        rp3_mean = rp_info.get('per_start_sched') or rp_info.get('per_start') or 0
        rp3_sigma = rp_info.get('sigma') or SIGMA_PER_SP_START
        if rp3_sigma is None or rp3_sigma <= 0:
            rp3_sigma = SIGMA_PER_SP_START
        draw_fn, emp_w = build_sp_sampler(emp_fps, rp3_mean, rp3_sigma,
                                            args.prior, args.k_prior)
        per_pitcher_stats[name] = {
            'n_starts': len(emp_fps),
            'emp_mean': float(np.mean(emp_fps)) if emp_fps else None,
            'rp3_mean': rp3_mean,
            'rp3_sigma': rp3_sigma,
            'emp_weight': emp_w,
        }
        if (name, mlbam) in unique_mine:
            sp_samplers_mine[name] = (draw_fn, emp_w)
        if (name, mlbam) in unique_opp:
            sp_samplers_opp[name] = (draw_fn, emp_w)

    # Scenarios to evaluate
    if args.bench:
        scenarios = [(name, {name}) for name in args.bench]
    else:
        # auto-enumerate every healthy mine SP with at least one remaining start
        bench_candidates = sorted({n for n, _, _ in remaining_mine})
        scenarios = [(name, {name}) for name in bench_candidates]
    scenarios = [('baseline (no bench)', set())] + scenarios

    # Run MC for each scenario
    results = []
    for label, bench_set in scenarios:
        my_t, opp_t = run_mc(my_proj, opp_proj, mu, sp_samplers_mine,
                               sp_samplers_opp, remaining_mine, remaining_opp,
                               ts_map, args.opp_window, bench_set,
                               cap_remaining_mine, cap_remaining_opp,
                               args.trials, args.seed, args.cap_rule)
        margin = my_t - opp_t
        win_prob = float((my_t > opp_t).mean())
        ci_lo, ci_hi = bootstrap_ci((my_t > opp_t).astype(float))
        results.append({
            'label': label,
            'bench': bench_set,
            'my_mean': float(my_t.mean()),
            'my_p10': float(np.percentile(my_t, 10)),
            'my_p90': float(np.percentile(my_t, 90)),
            'margin_mean': float(margin.mean()),
            'win_prob': win_prob,
            'win_prob_ci': (ci_lo, ci_hi),
            'ev_delta': None,  # filled relative to baseline
            'wp_delta': None,
        })

    baseline_wp = results[0]['win_prob']
    baseline_ev = results[0]['my_mean']
    for r in results[1:]:
        r['wp_delta'] = r['win_prob'] - baseline_wp
        r['ev_delta'] = r['my_mean'] - baseline_ev

    # Output
    print(f'\n--- Per-pitcher sample stats ---')
    for name, s in sorted(per_pitcher_stats.items()):
        emp_mean_str = f"{s['emp_mean']:>5.1f}" if s['emp_mean'] is not None else '  n/a'
        print(f"  {name:<22} n={s['n_starts']:>3}  "
              f"emp_mean={emp_mean_str}  rp3={s['rp3_mean']:>5.2f}  "
              f"emp_weight={s['emp_weight']*100:>5.1f}%")

    print(f'\n--- Scenario results ---')
    print(f'{"Scenario":<32} {"WinProb":>10} {"95% CI":>16} {"MyMean":>8} {"ΔWin":>8} {"ΔEV":>8}')
    print('-' * 90)
    for r in results:
        ci_str = f"[{r['win_prob_ci'][0]*100:.1f}-{r['win_prob_ci'][1]*100:.1f}]"
        dwp = f"{r['wp_delta']*100:+.2f}pp" if r['wp_delta'] is not None else '   —'
        dev = f"{r['ev_delta']:+.1f}" if r['ev_delta'] is not None else '   —'
        print(f"{r['label']:<32} {r['win_prob']*100:>9.2f}% {ci_str:>16} "
              f"{r['my_mean']:>8.1f} {dwp:>8} {dev:>8}")

    # Self-aware verdict
    if len(results) > 1:
        deltas = [abs(r['wp_delta']) for r in results[1:]]
        max_gap = max(deltas) if deltas else 0
        best = max(results[1:], key=lambda r: r['win_prob'])
        worst = min(results[1:], key=lambda r: r['win_prob'])
        print(f'\n--- Verdict ---')
        if max_gap < 0.01:
            # Within MC noise — fall back to rp3 × opp_factor ranking
            print(f'  Win-prob spread across scenarios is {max_gap*100:.2f}pp '
                  f'(< 1.0pp noise floor).')
            print(f'  → MC is not earning its complexity here. Decide by rp3 × opp_factor:')
            ranked = []
            for name, mlbam, sd in remaining_mine:
                rp_info = rp3_map.get(_norm(name), {})
                # Prefer schedule-adjusted (W1 fix)
                rp3_mean = rp_info.get('per_start_sched') or rp_info.get('per_start') or 0
                f = make_opp_factor(sd['opp_team'], ts_map, args.opp_window)
                ranked.append((name, sd['date'], sd['opp_team'], rp3_mean * f))
            ranked.sort(key=lambda x: x[3])
            print(f'  {"Pitcher":<20} {"Date":<11} {"Opp":<5} {"adj_EV":>8}  (lowest at top → bench candidate)')
            for n, d, o, ev in ranked:
                print(f'  {n:<20} {d:<11} {o:<5} {ev:>8.2f}')
        else:
            print(f'  Best:  bench {best["label"]}  → win prob {best["win_prob"]*100:.2f}% '
                  f'({best["wp_delta"]*100:+.2f}pp vs baseline)')
            print(f'  Worst: bench {worst["label"]} → win prob {worst["win_prob"]*100:.2f}% '
                  f'({worst["wp_delta"]*100:+.2f}pp vs baseline)')
            print(f'  Gap:   {max_gap*100:.2f}pp')


if __name__ == '__main__':
    main()
