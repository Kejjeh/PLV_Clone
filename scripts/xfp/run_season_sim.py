"""run_season_sim — /season-sim engine (championship-equity layer).

THE INSIGHT: /matchup-leverage answers "can I win THIS week and should I play
boom or floor". This answers "what are my playoff/title odds, and how
aggressive should I be for the REST of the season". The marginal value of a
weekly win is NOT constant — it depends on the standings race, and the value
of VARIANCE in Josh's weekly distribution flips sign with his seeding safety.

RULE 13 (decision layer only): never touches rh3/rp3/rprs2/baseline xFP.
It converts existing rate x volume projections + empirical weekly actuals
into P(playoffs) / seed distribution / P(title) and championship-equity
sensitivities for strategy calls (FAAB pacing, stream aggressiveness,
sell-the-future trades). No number here ever feeds back into a projection.

Pipeline
  1. STATE    — live standings (W-L + points-for from played box scores),
                remaining regular-season schedule per period (team.schedule),
                playoff structure straight from ESPN settings (6 of 8 teams;
                rounds = matchup periods 21 [1wk], 22 [2wks], 23 [2wks];
                seed tie rule H2H_RECORD then points-for).
  2. STRENGTH — per-team weekly-total FP distribution from the CURRENT roster:
                one ~2k-draw MC of a representative week (rate x volume layer:
                rh3 per-PA x hitter volume PA/team-game, rp3 per-start x SP
                volume GS/team-game with the 10-start cap inside each draw,
                rprs2 RoS/week for RPs; per-player variance via the empirical
                boxscore bootstrap blended with model sigma — shared machinery
                imported from run_matchup_leverage). The MC mean is then
                rescaled to the league's real weekly-FP scale and blended
                50/50 with the team's own played-week mean/SD (manager
                behavior — streaming, bench management — lives in the
                empirical component; current-roster talent in the MC one).
                DOCUMENTED SIMPLIFICATION: a weekly total is approximated as
                Normal(mu_t, sd_t) per team; a roster-churn haircut shrinks
                each mu 15% toward the league mean and inflates sd 5%
                (rosters change over ~10 remaining weeks: FA churn, injuries,
                trades — today's roster edge decays).
  3. SIMULATE — N (default 5000) seasons: current period finishes from the
                live WTD scores + the remaining-days fraction of the weekly
                distribution; periods cur+1..20 are full weekly draws; wins /
                points-for / pairwise H2H accumulate; seeding applies wins ->
                H2H record within tie group -> points-for; the 6-team bracket
                plays out with the same team distributions (multi-week rounds
                = Normal(mu*L, sd*sqrt(L))). Outputs per team: P(playoffs),
                seed distribution, P(final), P(title).
  4. JOSH     — championship-equity sensitivity: (a) dTitle/d(this week's
                result) — P(title | win period 15) vs P(title | lose), and the
                same conditional for EVERY remaining period (the value-of-a-
                win curve /matchup-leverage plugs into); (b) dTitle/d(weekly
                mean +2 FP) and dTitle/d(weekly sigma +10%) — the
                aggressiveness dial (variance helps a seeding underdog,
                hurts a safe seed).
  5. OUTPUT   — console report + data/outputs/season_sim.json.

Usage
  python scripts/xfp/run_season_sim.py                # live, 5000 sims
  python scripts/xfp/run_season_sim.py --sims 10000 --seed 11
  python scripts/xfp/run_season_sim.py --team-sims 4000
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

# ── shared machinery (import, never copy) ────────────────────────────────────
from run_matchup_leverage import (  # noqa: E402  (empirical bootstrap + blend)
    emp_series, _blend_draws, resolve_player_mlbam,
    K_PRIOR_SP, K_PRIOR_H, K_PRIOR_RP,
)
from build_matchup_dashboard import (  # noqa: E402
    load_projections, _today_et, _norm,
    IL_INJURY_STATES, MAX_SP_STARTS_PER_WEEK,
    SIGMA_PER_SP_START, SIGMA_PER_RP_GAME, FALLBACK_SP_PER_START,
)
from monte_carlo import calibrate_means, current_period_monday  # noqa: E402
from scripts.xfp.lib.pitcher_role import detect_pitcher_role  # noqa: E402
# Era-general subseason variance bands (2026-07-10): honest FALLBACK sigma for
# thin-history players only — the primary empirical-bootstrap path is untouched.
from scripts.xfp.lib.variance_bands import fallback_sigma  # noqa: E402
from plv_clone.cap_math import (  # noqa: E402
    STARTS_PER_SP_PER_WEEK, period_window, is_period_covered, weeks_in_period,
)

OUT = ROOT / 'data' / 'outputs'

# ── model constants (documented simplifications) ─────────────────────────────
TEAM_G_WK = 6.2          # MLB team games per scoring week (representative)
H_GAMES_WK = 6           # games a healthy everyday hitter plays per week
HITTER_ACTIVE = 13       # BrownU active hitter slots
RP_ACTIVE_CAP = 4        # BrownU active RP cap
CHURN_SHRINK = 0.15      # roster-churn haircut: shrink mu 15% toward league mean
CHURN_SD_INFLATE = 1.05  # ...and widen sd 5% (future rosters are uncertain)
MC_EMP_BLEND = 0.5       # weight on roster-MC mean vs played-week empirical mean
# per-game hitter FP sd fallback (thin history) — era-general variance band
# (H/game/T2/2021-25) when available; 3.2 if the bands CSV is missing.
DEFAULT_SIGMA_G_H = float(fallback_sigma('H', default=3.2))
JOSH_TAG = 'Ligers'


def _log(msg):
    print(msg, flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. STATE — standings, schedule, playoff structure
# ─────────────────────────────────────────────────────────────────────────────

def build_state():
    from plv_clone.league_state import LeagueState
    lg = LeagueState()._get_league()
    cur = lg.currentMatchupPeriod
    st = lg.settings
    reg_end = getattr(st, 'reg_season_count', 20)
    n_playoff = getattr(st, 'playoff_team_count', 6)
    mp = getattr(st, 'matchup_periods', {}) or {}
    # playoff rounds: matchup periods beyond reg season; round length = number
    # of scoring weeks that period spans (BrownU: 21->1wk, 22->2wks, 23->2wks)
    playoff_rounds = sorted(
        (int(k), len(v)) for k, v in mp.items() if int(k) > reg_end)
    if not playoff_rounds:
        playoff_rounds = [(reg_end + 1, 1), (reg_end + 2, 2), (reg_end + 3, 2)]
    last_scoring_week = max((max(v) for v in mp.values()), default=25)
    remain_weeks = max(last_scoring_week - cur + 1, 1)

    teams = list(lg.teams)
    names = [t.team_name for t in teams]
    josh = next(n for n in names if JOSH_TAG in n)

    wins0, losses0 = {}, {}
    pts0 = defaultdict(float)
    wtd = {}
    h2h0 = defaultdict(int)          # (a, b) -> wins of a over b, played periods
    cal = defaultdict(list)          # period -> [(a, b)] remaining matchups
    seen = set()
    for t in teams:
        wins0[t.team_name] = int(t.wins)
        losses0[t.team_name] = int(t.losses)
        for i, m in enumerate(t.schedule):
            per = i + 1
            ht, at = m.home_team, m.away_team
            if ht is None or at is None:
                continue
            key = (tuple(sorted((ht.team_name, at.team_name))), per)
            if key in seen:
                continue
            seen.add(key)
            hs = float(getattr(m, 'home_final_score', 0) or 0)
            as_ = float(getattr(m, 'away_final_score', 0) or 0)
            if per < cur:                                   # played
                pts0[ht.team_name] += hs
                pts0[at.team_name] += as_
                if hs > as_:
                    h2h0[(ht.team_name, at.team_name)] += 1
                elif as_ > hs:
                    h2h0[(at.team_name, ht.team_name)] += 1
            elif per <= reg_end:                            # current + future
                cal[per].append((ht.team_name, at.team_name))
                if per == cur:                              # live WTD scores
                    wtd[ht.team_name] = hs
                    wtd[at.team_name] = as_

    # fraction of the CURRENT matchup period still unplayed (incl. today) and how
    # many scoring-weeks it spans. A standard period = 1 week (Mon–Sun). The ASG
    # block uses its documented span (period 15 override). A multi-week playoff
    # ROUND (matchupPeriods len > 1) spans that many Mon–Sun weeks. So frac_left
    # and the current-period draw scale (mu * weeks) are right (2026-07-11).
    today = _today_et()
    pw = period_window(cur)
    if pw is not None:                        # ASG override (real date span)
        p_start, p_end = pw
        span_days = (p_end - p_start).days + 1
        cur_period_weeks = max(1.0, round(span_days / 7.0))
        frac_left = min(max(((p_end - today).days + 1) / span_days, 0.0), 1.0)
    else:                                     # standard OR multi-week playoff
        cur_period_weeks = float(weeks_in_period(mp, cur))
        monday = current_period_monday(today)
        span_days = 7 * int(cur_period_weeks)
        week_end = monday + timedelta(days=span_days - 1)
        frac_left = min(max(((week_end - today).days + 1) / span_days, 0.0), 1.0)

    return {
        'league': lg, 'teams': teams, 'names': names, 'josh': josh,
        'cur': cur, 'reg_end': reg_end, 'n_playoff': n_playoff,
        'playoff_rounds': playoff_rounds, 'remain_weeks': remain_weeks,
        'wins0': wins0, 'losses0': losses0, 'pts0': dict(pts0),
        'wtd': wtd, 'h2h0': dict(h2h0), 'cal': dict(cal),
        'today': today, 'frac_left': frac_left,
        'cur_period_weeks': cur_period_weeks,
        'cur_period_covered': is_period_covered(cur),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. TEAM STRENGTH — weekly-total normal per team from a roster MC
# ─────────────────────────────────────────────────────────────────────────────

def _is_out(p) -> bool:
    """Only IL/IR slots or an IL injuryStatus zero a player (gotcha #7 —
    BE counts as active; DAY_TO_DAY does not zero)."""
    slot = str(getattr(p, 'lineupSlot', '') or '').upper()
    if slot in ('IL', 'IR'):
        return True
    inj = str(getattr(p, 'injuryStatus', '') or '').upper()
    return inj in IL_INJURY_STATES and inj != 'DAY_TO_DAY'


def _load_volume_maps():
    """Validated volume layer: hitter PA/team-game and SP GS/team-game,
    mlbam-keyed (rate x volume = RoS totals, validated 2026-07-09)."""
    vol_h, vol_sp = {}, {}
    try:
        vh = pd.read_csv(OUT / 'xfp_volume_projections.csv',
                         usecols=['mlbam_id', 'proj_ros_pa_per_teamgame'])
        vol_h = dict(zip(vh['mlbam_id'].astype(int),
                         vh['proj_ros_pa_per_teamgame'].astype(float)))
    except Exception as e:
        _log(f'  WARN hitter volume load failed: {e}')
    try:
        vs = pd.read_csv(OUT / 'xfp_sp_volume_projections.csv',
                         usecols=['mlbam_id', 'proj_ros_gs_per_teamgame'])
        vol_sp = dict(zip(vs['mlbam_id'].astype(int),
                          vs['proj_ros_gs_per_teamgame'].astype(float)))
    except Exception as e:
        _log(f'  WARN sp volume load failed: {e}')
    return vol_h, vol_sp


def classify_team_roster(team, rh3_map, rp3_map, rprs2_map, vol_h, vol_sp,
                         remain_weeks):
    """-> dict with hitters / sps / rps parameter lists for one team's MC."""
    hitters, sps, rps = [], [], []
    n_out = 0
    for p in team.roster:
        if _is_out(p):
            n_out += 1
            continue
        pos = (getattr(p, 'position', '') or '')
        nk = _norm(p.name)
        mlbam = None
        try:
            mlbam = resolve_player_mlbam(p)
            mlbam = int(mlbam) if mlbam else None
        except Exception:
            mlbam = None
        if pos in ('SP', 'RP', 'P'):
            role = detect_pitcher_role(p, mlbam_id=mlbam)
            if role == 'SP':
                info = rp3_map.get(nk, {})
                per_start = float(info.get('per_start') or 0) or None
                emp = emp_series(mlbam, 'SP') if mlbam else []
                if per_start is None:
                    per_start = (float(np.mean(emp)) if len(emp) >= 3
                                 else FALLBACK_SP_PER_START)
                lam = None
                if mlbam and mlbam in vol_sp:
                    lam = float(vol_sp[mlbam]) * TEAM_G_WK
                if lam is None or lam <= 0:
                    lam = STARTS_PER_SP_PER_WEEK
                lam = float(np.clip(lam, 0.4, 2.0))
                sps.append({'name': p.name, 'mlbam': mlbam, 'emp': emp,
                            'per_start': per_start,
                            'sigma': float(info.get('sigma')
                                           or fallback_sigma('SP', default=SIGMA_PER_SP_START)),
                            'lam': lam})
            else:
                info = rprs2_map.get(nk, {})
                xfp_ros = float(info.get('xfp_ros') or 0)
                emp = emp_series(mlbam, 'RP') if mlbam else []
                wk_mean = (xfp_ros / remain_weeks if xfp_ros > 0 else
                           (float(np.mean(emp)) * 3.0 if len(emp) >= 5 else 0.0))
                if wk_mean <= 0:
                    continue
                apps_wk = 3.0
                rps.append({'name': p.name, 'mlbam': mlbam, 'emp': emp,
                            'wk_mean': wk_mean, 'apps_wk': apps_wk,
                            'mean_app': wk_mean / apps_wk,
                            'sigma_app': float(info.get('sigma')
                                               or fallback_sigma('RP', default=SIGMA_PER_RP_GAME))})
        else:
            info = rh3_map.get(nk, {})
            per_pa = float(info.get('per_pa') or 0)
            per_game = float(info.get('per_game') or 0)
            emp = emp_series(mlbam, 'H') if mlbam else []
            pa_pg = vol_h.get(mlbam) if mlbam else None
            if per_pa and pa_pg:
                wk_mean = per_pa * float(pa_pg) * TEAM_G_WK   # rate x volume
            elif per_game:
                wk_mean = per_game * 5.7
            elif len(emp) >= 5:
                wk_mean = float(np.mean(emp)) * 5.5
            else:
                continue
            sig = (float(np.std(emp, ddof=1)) if len(emp) >= 8
                   else DEFAULT_SIGMA_G_H)
            hitters.append({'name': p.name, 'mlbam': mlbam, 'emp': emp,
                            'wk_mean': wk_mean,
                            'mean_g': wk_mean / H_GAMES_WK,
                            'sigma_g': sig})
    hitters.sort(key=lambda h: -h['wk_mean'])
    rps.sort(key=lambda r: -r['wk_mean'])
    return {'hitters': hitters[:HITTER_ACTIVE], 'sps': sps,
            'rps': rps[:RP_ACTIVE_CAP], 'n_out': n_out,
            'n_hitters_all': len(hitters)}


def mc_week_draws(roster, n_draws, rng) -> np.ndarray:
    """One representative-week MC for a team -> (n_draws,) weekly-total FP.
    Per-player draws reuse run_matchup_leverage's empirical-bootstrap/model
    blend. SP starts ~ Poisson(lam) truncated at 2, with the 10-start weekly
    cap applied inside each draw (overflow drops the WORST arm's start —
    managers bench overflow optimally, a mild upper bound)."""
    total = np.zeros(n_draws)
    for h in roster['hitters']:
        for _ in range(H_GAMES_WK):
            total += _blend_draws(rng, h['emp'], h['mean_g'], h['sigma_g'],
                                  K_PRIOR_H, n_draws)
    # SPs — best arms consume the cap first
    cap_left = np.full(n_draws, MAX_SP_STARTS_PER_WEEK, dtype=int)
    for s in sorted(roster['sps'], key=lambda x: -x['per_start']):
        n_starts = np.minimum(rng.poisson(s['lam'], n_draws), 2)
        take = np.minimum(n_starts, cap_left)
        cap_left -= take
        for k in range(2):
            active = take > k
            if not active.any():
                break
            total += _blend_draws(rng, s['emp'], s['per_start'], s['sigma'],
                                  K_PRIOR_SP, n_draws) * active
    for r in roster['rps']:
        p_app = min(r['apps_wk'] / 6.0, 1.0)
        apps = rng.binomial(6, p_app, n_draws)
        for g in range(6):
            active = apps > g
            if not active.any():
                break
            total += _blend_draws(rng, r['emp'], r['mean_app'], r['sigma_app'],
                                  K_PRIOR_RP, n_draws) * active
    return total


def build_team_strength(state, n_team_sims, seed):
    """-> {team: {'mu','sd','mc_mu','mc_sd','emp_mu','emp_sd',...}}"""
    _log('Building per-team weekly-strength distributions (roster MC)...')
    rh3_map, rp3_map, _rp3_by_mlbam, rprs2_map, _ts = load_projections()
    vol_h, vol_sp = _load_volume_maps()
    rng = np.random.default_rng(seed)

    # empirical played-week scores per team (manager behavior + real scale)
    emp_scores = defaultdict(list)
    seen = set()
    for t in state['teams']:
        for i, m in enumerate(t.schedule):
            per = i + 1
            if per >= state['cur']:
                continue
            ht, at = m.home_team, m.away_team
            key = (tuple(sorted((ht.team_name, at.team_name))), per)
            if key in seen:
                continue
            seen.add(key)
            emp_scores[ht.team_name].append(float(m.home_final_score))
            emp_scores[at.team_name].append(float(m.away_final_score))
    all_wk = [x for v in emp_scores.values() for x in v]
    league_wk_mean = float(np.mean(all_wk)) if all_wk else 340.0
    league_wk_sd = float(np.mean([np.std(v, ddof=1) for v in emp_scores.values()
                                  if len(v) >= 4])) if emp_scores else 60.0

    strength = {}
    mc_mu_raw = {}
    rosters = {}
    for t in state['teams']:
        roster = classify_team_roster(t, rh3_map, rp3_map, rprs2_map,
                                      vol_h, vol_sp, state['remain_weeks'])
        rosters[t.team_name] = roster
        draws = mc_week_draws(roster, n_team_sims, rng)
        mc_mu_raw[t.team_name] = float(draws.mean())
        strength[t.team_name] = {'mc_sd': float(draws.std(ddof=1))}
        _log(f"  {t.team_name:<28} MC {draws.mean():6.1f} +/- {draws.std(ddof=1):5.1f}  "
             f"(H {len(roster['hitters'])}/{roster['n_hitters_all']}, "
             f"SP {len(roster['sps'])}, RP {len(roster['rps'])}, out {roster['n_out']})")

    # rescale MC means to the league's real weekly scale, then blend with each
    # team's own empirical played-week mean/SD
    mc_mu_cal = calibrate_means(mc_mu_raw, league_wk_mean)
    for tn in mc_mu_raw:
        s = strength[tn]
        emp = emp_scores.get(tn, [])
        emp_mu = float(np.mean(emp)) if emp else league_wk_mean
        emp_sd = (float(np.std(emp, ddof=1)) if len(emp) >= 4 else league_wk_sd)
        mu = MC_EMP_BLEND * mc_mu_cal[tn] + (1 - MC_EMP_BLEND) * emp_mu
        sd = math.sqrt(MC_EMP_BLEND * s['mc_sd'] ** 2
                       + (1 - MC_EMP_BLEND) * emp_sd ** 2)
        # roster-churn haircut
        mu = league_wk_mean + (mu - league_wk_mean) * (1 - CHURN_SHRINK)
        sd = sd * CHURN_SD_INFLATE
        s.update({'mc_mu_raw': round(mc_mu_raw[tn], 1),
                  'mc_mu_cal': round(mc_mu_cal[tn], 1),
                  'emp_mu': round(emp_mu, 1), 'emp_sd': round(emp_sd, 1),
                  'mu': mu, 'sd': sd})
    strength['_league'] = {'wk_mean': league_wk_mean, 'wk_sd': league_wk_sd}
    return strength


# ─────────────────────────────────────────────────────────────────────────────
# 3. SEASON SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

def seed_teams(win_d: dict, pf_d: dict, h2h_get) -> list[str]:
    """ESPN BrownU seeding: wins desc -> H2H record within tie group ->
    points-for. h2h_get(a, b) -> wins of a over b (this sim, incl played).
    Circular multi-team H2H knots resolve by group H2H win pct then PF."""
    by_w = defaultdict(list)
    for t, w in win_d.items():
        by_w[w].append(t)
    order = []
    for w in sorted(by_w, reverse=True):
        grp = by_w[w]
        if len(grp) > 1:
            def key(t):
                hw = sum(h2h_get(t, o) for o in grp if o != t)
                hl = sum(h2h_get(o, t) for o in grp if o != t)
                tot = hw + hl
                return (hw / tot if tot else 0.5, pf_d[t])
            grp = sorted(grp, key=key, reverse=True)
        order.extend(grp)
    return order


def simulate(state, strength, n_sims, seed, josh_mu_delta=0.0,
             josh_sd_mult=1.0):
    """Vectorized weekly draws + per-sim seeding/bracket. Returns per-team
    playoff/seed/final/title arrays and Josh's per-period win indicators."""
    names = state['names']
    josh = state['josh']
    rng = np.random.default_rng(seed)
    mu = {t: strength[t]['mu'] for t in names}
    sd = {t: strength[t]['sd'] for t in names}
    mu[josh] = mu[josh] + josh_mu_delta
    sd[josh] = sd[josh] * josh_sd_mult

    periods = sorted(state['cal'].keys())
    f = state['frac_left']
    # current period may span >1 scoring week (ASG block): its remaining scoring
    # is mu * weeks * frac_left, and sd scales by sqrt(weeks * frac_left). W=1 for
    # a standard week -> byte-identical to the pre-2026-07-11 single-week draw.
    W = float(state.get('cur_period_weeks', 1.0))

    # weekly score draws per team per period
    S = {}
    for t in names:
        S[t] = {}
        for p in periods:
            if p == state['cur']:
                fw = max(f * W, 1e-9)
                S[t][p] = (state['wtd'].get(t, 0.0)
                           + rng.normal(mu[t] * f * W, sd[t] * math.sqrt(fw),
                                        n_sims))
            else:
                S[t][p] = rng.normal(mu[t], sd[t], n_sims)

    # wins / points-for / pairwise H2H
    wins = {t: np.full(n_sims, state['wins0'][t], dtype=int) for t in names}
    pf = {t: np.full(n_sims, state['pts0'].get(t, 0.0)) for t in names}
    h2h = defaultdict(lambda: np.zeros(n_sims, dtype=int))
    for (a, b), w in state['h2h0'].items():
        h2h[(a, b)] += w
    josh_win_by_period = {}
    for p in periods:
        for a, b in state['cal'][p]:
            wa = S[a][p] > S[b][p]
            wins[a] += wa
            wins[b] += ~wa
            pf[a] += S[a][p]
            pf[b] += S[b][p]
            h2h[(a, b)] += wa
            h2h[(b, a)] += ~wa
            if josh in (a, b):
                josh_win_by_period[p] = wa if a == josh else ~wa

    # playoff bracket random pool: 5 matchups x 2 teams
    Z = rng.standard_normal((n_sims, 10))
    rounds = state['playoff_rounds']           # [(21,1),(22,2),(23,2)]
    L1 = rounds[0][1] if len(rounds) > 0 else 1
    L2 = rounds[1][1] if len(rounds) > 1 else 2
    L3 = rounds[2][1] if len(rounds) > 2 else 2
    n_po = state['n_playoff']

    idx = {t: i for i, t in enumerate(names)}
    playoff_ct = {t: 0 for t in names}
    final_ct = {t: 0 for t in names}
    title_ct = {t: 0 for t in names}
    seed_ct = {t: np.zeros(n_po + 1, dtype=int) for t in names}  # [miss,1..n_po]
    champion = np.empty(n_sims, dtype=int)
    josh_seed = np.zeros(n_sims, dtype=int)     # 0 = missed playoffs

    for i in range(n_sims):
        win_d = {t: int(wins[t][i]) for t in names}
        pf_d = {t: float(pf[t][i]) for t in names}

        def h2h_get(a, b, _i=i):
            return int(h2h[(a, b)][_i])
        seeded = seed_teams(win_d, pf_d, h2h_get)[:n_po]
        for s_i, t in enumerate(seeded):
            playoff_ct[t] += 1
            seed_ct[t][s_i + 1] += 1
        for t in names:
            if t not in seeded:
                seed_ct[t][0] += 1
        if josh in seeded:
            josh_seed[i] = seeded.index(josh) + 1

        def game(a, b, za, zb, L, _i=i):
            sa = mu[a] * L + sd[a] * math.sqrt(L) * Z[_i, za]
            sb = mu[b] * L + sd[b] * math.sqrt(L) * Z[_i, zb]
            return a if sa > sb else b
        # 6-team bracket: 1-2 byes; R1 3v6 + 4v5; semis 1 vs w(4v5), 2 vs w(3v6)
        r1a = game(seeded[2], seeded[5], 0, 1, L1)
        r1b = game(seeded[3], seeded[4], 2, 3, L1)
        s1 = game(seeded[0], r1b, 4, 5, L2)
        s2 = game(seeded[1], r1a, 6, 7, L2)
        final_ct[s1] += 1
        final_ct[s2] += 1
        champ = game(s1, s2, 8, 9, L3)
        title_ct[champ] += 1
        champion[i] = idx[champ]

    return {
        'n_sims': n_sims,
        'playoff_p': {t: playoff_ct[t] / n_sims for t in names},
        'final_p': {t: final_ct[t] / n_sims for t in names},
        'title_p': {t: title_ct[t] / n_sims for t in names},
        'seed_dist': {t: (seed_ct[t] / n_sims).tolist() for t in names},
        'champion': champion, 'idx': idx,
        'josh_win_by_period': josh_win_by_period,
        'josh_seed': josh_seed,
        'exp_wins': {t: float(wins[t].mean()) for t in names},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. JOSH sensitivities + strategy directive
# ─────────────────────────────────────────────────────────────────────────────

def josh_sensitivities(state, strength, base, n_sims, seed):
    josh = state['josh']
    jid = base['idx'][josh]
    title_flag = base['champion'] == jid
    playoff_flag = base['josh_seed'] > 0

    # (a) value-of-a-win curve: P(title | win period p) - P(title | lose)
    win_curve = []
    for p in sorted(base['josh_win_by_period'].keys()):
        w = base['josh_win_by_period'][p]
        if w.sum() < 50 or (~w).sum() < 50:
            continue
        pt_w = float(title_flag[w].mean())
        pt_l = float(title_flag[~w].mean())
        pp_w = float(playoff_flag[w].mean())
        pp_l = float(playoff_flag[~w].mean())
        win_curve.append({'period': p, 'p_win_week': round(float(w.mean()), 3),
                          'p_title_if_win': round(pt_w, 4),
                          'p_title_if_lose': round(pt_l, 4),
                          'dtitle_pp': round((pt_w - pt_l) * 100, 2),
                          'dplayoffs_pp': round((pp_w - pp_l) * 100, 2)})

    # (b) aggressiveness dials — full re-sims on the same seed (common random
    # numbers keep MC noise on the DIFFERENCE small)
    up_mu = simulate(state, strength, n_sims, seed, josh_mu_delta=2.0)
    up_sd = simulate(state, strength, n_sims, seed, josh_sd_mult=1.10)
    sens = {
        'dtitle_mean_plus2_pp': round((up_mu['title_p'][josh]
                                       - base['title_p'][josh]) * 100, 2),
        'dplayoffs_mean_plus2_pp': round((up_mu['playoff_p'][josh]
                                          - base['playoff_p'][josh]) * 100, 2),
        'dtitle_sigma_up10_pp': round((up_sd['title_p'][josh]
                                       - base['title_p'][josh]) * 100, 2),
        'dplayoffs_sigma_up10_pp': round((up_sd['playoff_p'][josh]
                                          - base['playoff_p'][josh]) * 100, 2),
    }
    return win_curve, sens


def strategy_directive(state, base, win_curve, sens):
    josh = state['josh']
    pp = base['playoff_p'][josh]
    pt = base['title_p'][josh]
    seed_dist = base['seed_dist'][josh]
    modal_seed = int(np.argmax(seed_dist[1:]) + 1) if pp > 0 else 0
    cur_row = next((r for r in win_curve if r['period'] == state['cur']), None)
    late_rows = [r for r in win_curve if r['period'] >= state['reg_end'] - 1]
    d_now = cur_row['dtitle_pp'] if cur_row else None
    d_late = (float(np.mean([r['dtitle_pp'] for r in late_rows]))
              if late_rows else None)
    dvar = sens['dtitle_sigma_up10_pp']

    lines = []
    lines.append(f"Playoff odds {pp*100:.0f}%, title odds {pt*100:.1f}%, "
                 f"modal seed {modal_seed} "
                 f"(P(miss) {seed_dist[0]*100:.0f}%).")
    if d_now is not None and d_late is not None:
        lines.append(f"A win THIS period is worth {d_now:+.1f}pp title equity "
                     f"(vs {d_late:+.1f}pp avg for periods "
                     f"{state['reg_end']-1}-{state['reg_end']}).")
    if pp >= 0.95:
        lines.append("SAFE: playoff spot near-locked — bank floor, hoard "
                     "FAAB/streams for the playoff weeks; a marginal regular-"
                     "season win buys little. Position the playoff roster "
                     "(/playoff-team-build, /sp-stash-finder).")
    elif pp >= 0.85:
        lines.append(f"MOSTLY SAFE: entry likely but not locked "
                     f"(P(miss) {seed_dist[0]*100:.0f}%) — take cheap wins and "
                     f"free streams, but don't burn premium FAAB on marginal "
                     f"regular-season edges; start positioning the playoff "
                     f"roster (/playoff-team-build, /sp-stash-finder).")
    elif pp >= 0.30:
        urgency = 'NOW' if (d_now or 0) >= (d_late or 0) else 'evenly paced'
        lines.append(f"CONTESTED: every weekly win moves real title equity — "
                     f"spend streams/waiver priority {urgency}. Marginal wins "
                     f"are worth more than hoarded FAAB in this band.")
    else:
        lines.append("LONGSHOT: playoff entry itself is the bottleneck — "
                     "maximize variance everywhere (boom rosters, "
                     "high-upside stashes over steady veterans).")
    dvar_po = sens['dplayoffs_sigma_up10_pp']
    if dvar > 0.1 and dvar_po < -0.1:
        lines.append(f"VARIANCE SPLITS: +10% weekly sigma helps title upside "
                     f"({dvar:+.2f}pp — you'd be a bracket underdog) but "
                     f"costs playoff entry ({dvar_po:+.2f}pp — you're an "
                     f"entry favorite). Play floor until the spot is "
                     f"clinched, then tilt boom for the bracket.")
    elif dvar > 0.15:
        lines.append(f"VARIANCE HELPS: +10% weekly sigma is worth "
                     f"{dvar:+.2f}pp title equity — as a seeding underdog, "
                     f"prefer boom/bust construction (high-sigma hitters, "
                     f"high-boom% arms) even at slight E[FP] cost.")
    elif dvar < -0.15:
        lines.append(f"VARIANCE HURTS: +10% weekly sigma costs "
                     f"{dvar:+.2f}pp title equity — you are protecting a "
                     f"position; prefer floor (SAFE-tier arms, low bust%).")
    else:
        lines.append(f"Variance is roughly title-neutral right now "
                     f"({dvar:+.2f}pp per +10% sigma) — optimize E[FP].")
    lines.append(f"Mean dial: +2 FP/week of true strength = "
                 f"{sens['dtitle_mean_plus2_pp']:+.2f}pp title / "
                 f"{sens['dplayoffs_mean_plus2_pp']:+.2f}pp playoffs — the "
                 f"scale for valuing any add/trade in equity terms.")
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# 5. Sanity / consistency checks
# ─────────────────────────────────────────────────────────────────────────────

def consistency_checks(state, base):
    checks = {}
    names = state['names']
    # (1) P(playoffs) coherent with standings: rank-correlate current wins
    w = np.array([state['wins0'][t] for t in names], dtype=float)
    p = np.array([base['playoff_p'][t] for t in names])
    rw = pd.Series(w).rank()
    rp_ = pd.Series(p).rank()
    rho = float(np.corrcoef(rw, rp_)[0, 1])
    leader = max(names, key=lambda t: (state['wins0'][t],
                                       state['pts0'].get(t, 0)))
    checks['spearman_wins_vs_playoffP'] = round(rho, 3)
    checks['leader_has_top_playoffP'] = bool(
        base['playoff_p'][leader] >= max(p) - 1e-9
        or base['playoff_p'][leader] >= sorted(p)[-2])
    # (2) sum of title probabilities
    checks['sum_title_p'] = round(sum(base['title_p'].values()), 4)
    # (3) current-period P(win) vs /matchup-leverage
    josh = state['josh']
    cur_w = base['josh_win_by_period'].get(state['cur'])
    p_cur = float(cur_w.mean()) if cur_w is not None else None
    checks['p_win_current_period'] = round(p_cur, 4) if p_cur is not None else None
    try:
        ml = json.loads((OUT / 'matchup_leverage.json').read_text(encoding='utf-8'))
        if ml.get('period') == state['cur']:
            checks['matchup_leverage_pwin'] = ml.get('pwin')
            if p_cur is not None and ml.get('pwin') is not None:
                checks['pwin_gap_pp'] = round((p_cur - ml['pwin']) * 100, 1)
    except Exception:
        pass
    return checks


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='/season-sim engine — championship-equity layer')
    ap.add_argument('--sims', type=int, default=5000)
    ap.add_argument('--team-sims', type=int, default=2000,
                    help='draws for each team-strength representative-week MC')
    ap.add_argument('--seed', type=int, default=7)
    args = ap.parse_args()

    print('=== /season-sim ===')
    print('Building league state...')
    state = build_state()
    print(f"  period {state['cur']} of {state['reg_end']} regular; playoffs: "
          f"{state['n_playoff']} teams, rounds "
          f"{[(p, f'{L}wk') for p, L in state['playoff_rounds']]}")
    _wk = state.get('cur_period_weeks', 1.0)
    _span = f", ~{_wk:.0f} scoring-week span (ASG/multi-week)" if _wk != 1.0 else ""
    print(f"  current-period fraction remaining: {state['frac_left']:.2f}{_span}")
    for t in sorted(state['names'],
                    key=lambda x: (-state['wins0'][x], -state['pts0'].get(x, 0))):
        print(f"  {t:<28} {state['wins0'][t]:>2}-{state['losses0'][t]:<2}  "
              f"PF {state['pts0'].get(t, 0):7.1f}  WTD {state['wtd'].get(t, 0):6.1f}")

    strength = build_team_strength(state, args.team_sims, args.seed)
    print('\n--- TEAM WEEKLY STRENGTH (post-blend, churn-haircut) ---')
    for t in sorted(state['names'], key=lambda x: -strength[x]['mu']):
        s = strength[t]
        print(f"  {t:<28} mu {s['mu']:6.1f}  sd {s['sd']:5.1f}   "
              f"(MC-cal {s['mc_mu_cal']:6.1f} / emp {s['emp_mu']:6.1f})")

    print(f"\nSimulating rest of season x{args.sims}...")
    base = simulate(state, strength, args.sims, args.seed)

    print('\n--- SEASON OUTLOOK (all 8 teams) ---')
    print(f"  {'team':<28} {'rec':>5} {'P(playoffs)':>11} {'P(final)':>9} "
          f"{'P(title)':>9} {'E[wins]':>8}")
    for t in sorted(state['names'], key=lambda x: -base['title_p'][x]):
        print(f"  {t:<28} {state['wins0'][t]:>2}-{state['losses0'][t]:<2} "
              f"{base['playoff_p'][t]*100:>10.1f}% {base['final_p'][t]*100:>8.1f}% "
              f"{base['title_p'][t]*100:>8.1f}% {base['exp_wins'][t]:>8.1f}")

    josh = state['josh']
    sd_j = base['seed_dist'][josh]
    print(f"\n--- {josh} SEED DISTRIBUTION ---")
    print('  ' + '  '.join(f"seed{k}: {sd_j[k]*100:.1f}%"
                           for k in range(1, state['n_playoff'] + 1)))
    print(f"  miss: {sd_j[0]*100:.1f}%")

    win_curve, sens = josh_sensitivities(state, strength, base,
                                         args.sims, args.seed)
    print('\n--- CHAMPIONSHIP-EQUITY SENSITIVITY (Josh) ---')
    print('  value-of-a-win curve (P(title|win) - P(title|lose), by period):')
    for r in win_curve:
        cur_tag = '  <- THIS WEEK' if r['period'] == state['cur'] else ''
        print(f"    period {r['period']:>2}: dTitle {r['dtitle_pp']:+5.2f}pp   "
              f"dPlayoffs {r['dplayoffs_pp']:+5.2f}pp   "
              f"P(win wk) {r['p_win_week']*100:.0f}%{cur_tag}")
    print(f"  mean dial:  +2 FP/wk  -> dTitle {sens['dtitle_mean_plus2_pp']:+.2f}pp, "
          f"dPlayoffs {sens['dplayoffs_mean_plus2_pp']:+.2f}pp")
    print(f"  sigma dial: +10%      -> dTitle {sens['dtitle_sigma_up10_pp']:+.2f}pp, "
          f"dPlayoffs {sens['dplayoffs_sigma_up10_pp']:+.2f}pp")

    directive = strategy_directive(state, base, win_curve, sens)
    print('\n--- STRATEGY DIRECTIVE ---')
    for ln in directive:
        print(f"  * {ln}")

    checks = consistency_checks(state, base)
    print('\n--- CONSISTENCY CHECKS ---')
    for k, v in checks.items():
        print(f"  {k}: {v}")

    caveats = [
        'Team weekly totals approximated as a fitted Normal from one 2k-draw '
        'representative-week roster MC, blended 50/50 with played-week actuals.',
        'Roster-churn haircut: means shrunk 15% toward league mean, sd +5% — '
        'future rosters will differ from today\'s (FA churn, injuries, trades).',
        'Currently-IL players are excluded from team strength with NO return '
        'phasing (a team stashing elite IL returners — e.g. late-summer '
        'activations — is underrated here; cross-check /sp-rehab-tracker).',
        'marcel_il-tagged SP rows use the suppressed rp3 prior (gotcha #1) — '
        'FA-tier arms on sim rosters may be slightly underrated.',
        'Thin-history teams lean on the league-average weekly sd.',
        'Current-period span: covered ASG/multi-week periods scale the weekly '
        'draw by round(span_days/7) weeks; the ~3 ASG dead days are counted in '
        'the calendar span, a mild (~2 nominal vs ~1.6 game-weeks) over-count of '
        'that single period only. Standard 1-week periods are unchanged.',
        'Seeding tiebreak: H2H record within tie group then points-for; ESPN '
        'circular-knot edge cases resolve by group H2H win pct.',
        'Rule 13: decision layer only — nothing here moves rh3/rp3/rprs2.',
    ]

    payload = {
        'generated': str(state['today']),
        'period': state['cur'], 'reg_season_end': state['reg_end'],
        'playoff_teams': state['n_playoff'],
        'playoff_rounds': state['playoff_rounds'],
        'sims': args.sims, 'team_sims': args.team_sims, 'seed': args.seed,
        'frac_current_week_left': round(state['frac_left'], 3),
        'cur_period_weeks': state.get('cur_period_weeks', 1.0),
        'cur_period_covered': state.get('cur_period_covered', False),
        'standings': {t: {'wins': state['wins0'][t],
                          'losses': state['losses0'][t],
                          'pf': round(state['pts0'].get(t, 0), 1),
                          'wtd': round(state['wtd'].get(t, 0), 1)}
                      for t in state['names']},
        'team_strength': {t: {k: round(v, 2) if isinstance(v, float) else v
                              for k, v in strength[t].items()}
                          for t in state['names']},
        'league_weekly': {k: round(v, 1)
                          for k, v in strength['_league'].items()},
        'results': {t: {'p_playoffs': round(base['playoff_p'][t], 4),
                        'p_final': round(base['final_p'][t], 4),
                        'p_title': round(base['title_p'][t], 4),
                        'exp_wins': round(base['exp_wins'][t], 2),
                        'seed_dist': [round(x, 4)
                                      for x in base['seed_dist'][t]]}
                    for t in state['names']},
        'josh': {
            'team': josh,
            'p_playoffs': round(base['playoff_p'][josh], 4),
            'p_title': round(base['title_p'][josh], 4),
            'seed_dist_miss_then_1toN': [round(x, 4) for x in sd_j],
            'value_of_win_curve': win_curve,
            'sensitivity': sens,
            'strategy_directive': directive,
        },
        'consistency_checks': checks,
        'caveats': caveats,
        'rule13': 'decision layer only — projections (rh3/rp3/rprs2) untouched',
    }
    path = OUT / 'season_sim.json'
    path.write_text(json.dumps(payload, indent=2, default=float),
                    encoding='utf-8')
    print(f'\nwrote {path}')


if __name__ == '__main__':
    main()
