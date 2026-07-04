"""monte_carlo.py — IL-aware, empirically-calibrated playoff & championship MC.

Simulates the remaining ESPN schedule N times, seeds the playoff bracket, and
reports per-team playoff / finals / title probabilities.

Methodology (audited + folded in 2026-06-19; see tests/test_monte_carlo.py):
  1. EMPIRICAL calibration. The per-week mean is anchored to the real league
     weekly mean and the per-team weekly SD is MEASURED from played box scores
     — not a guessed sigma on a /20-compressed mean (the pre-2026-06-19 version
     used sigma=80 on ~206 means => CV~0.39 vs the real ~0.20, which doubled the
     randomness and flattened the title race).
  2. IL TIME-PHASING via ESPN return dates. Each IL'd player's healthy weekly
     value is removed from their team's per-week mean only for the weeks they
     are OUT, and restored from the matchup period containing their return date.
     By the playoffs everyone is assumed healthy (returns precede the bracket).
  3. POINTS-FOR TIEBREAKER. Seeding ties are broken by total points-for
     (actual season-to-date + simulated remainder) — ESPN's real tiebreaker,
     not arbitrary dict order.

The pure helpers (return_period / phased_team_mean / seed_order / calibrate_means)
are import-tested in tests/test_monte_carlo.py; main() does the live wiring.

Output: data/outputs/monte_carlo.json (+ .csv)
"""
from __future__ import annotations
import sys, json
from datetime import date
from collections import defaultdict
import numpy as np
import pandas as pd

from plv_clone.paths import ROOT
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'data' / 'outputs'

N_SIMS = 20000
PLAYOFF_TEAMS = 6  # BrownU
IL_STATES = {'OUT', 'TEN_DAY_DL', 'FIFTEEN_DAY_DL', 'SIXTY_DAY_DL',
             'TEN_DAY_IL', 'FIFTEEN_DAY_IL', 'SIXTY_DAY_IL'}
H_GAMES_WK = 6.5      # hitter games per scoring week
from plv_clone.cap_math import STARTS_PER_SP_PER_WEEK as SP_STARTS_WK  # owner (audit 2026-07-04)
PLAYOFF_SIGMA_MULT = 1.4   # multi-week playoff rounds are wider
IL_FLOOR_FRAC = 0.6        # a team's phased mean can't fall below 60% of full strength


# ----------------------------- pure helpers --------------------------------

def current_period_monday(today: date | None = None) -> date:
    """Monday of the matchup period containing `today` (defaults to real today)."""
    t = today or date.today()
    return date.fromordinal(t.toordinal() - t.weekday())


def return_period(ret: date | None, cur_period: int, cur_monday: date,
                  out_sentinel: int = 999) -> int:
    """Matchup period a player is first available again.

    None (season-ending / unknown) -> out_sentinel (never returns in-sim).
    A return date in the current week (or past) maps to cur_period.
    """
    if ret is None:
        return out_sentinel
    delta_weeks = (ret - cur_monday).days // 7
    return cur_period + max(delta_weeks, 0)


def calibrate_means(value_by_team: dict[str, float], league_wk_mean: float
                    ) -> dict[str, float]:
    """Map relative roster strength to the real weekly-FP scale: a team with
    average roster value gets exactly league_wk_mean; spread scales proportionally."""
    mean_v = np.mean(list(value_by_team.values()))
    if mean_v <= 0:
        return {t: league_wk_mean for t in value_by_team}
    return {t: league_wk_mean * v / mean_v for t, v in value_by_team.items()}


def phased_team_mean(base_mean: float, il_phase: list[tuple[int, float]],
                     period: int, floor_frac: float = IL_FLOOR_FRAC) -> float:
    """Per-week mean with not-yet-returned IL players removed.

    il_phase: list of (return_period, healthy_weekly_fp). For each player still
    OUT this period (period < return_period), subtract their weekly value, with
    a floor so a heavily-injured team never collapses below floor_frac of full.
    """
    m = base_mean
    for rper, wfp in il_phase:
        if period < rper:
            m -= wfp
    return max(m, floor_frac * base_mean)


def seed_order(wins: dict[str, float], points: dict[str, float]) -> list[str]:
    """Seed teams by wins desc, then points-for desc (ESPN H2H tiebreaker)."""
    return sorted(wins, key=lambda t: (-wins[t], -points.get(t, 0.0)))


# ------------------------------- live wiring -------------------------------

def main():
    from plv_clone.league_state import LeagueState
    from scripts.xfp.opponent_lineup_overlap import (
        load_projections, build_team_players, fill_slots, _norm)
    from app.espn_connector import get_all_teams, get_injury_details

    lg = LeagueState()._get_league()
    cur = lg.currentMatchupPeriod
    reg_end = getattr(lg.settings, 'reg_season_count', 20)
    cur_monday = current_period_monday()

    # 1. empirical calibration from played weeks (box scores)
    wk_scores = defaultdict(list)
    for mp in range(1, cur):
        try:
            for bs in lg.box_scores(mp):
                if bs.home_team and bs.home_score > 0:
                    wk_scores[bs.home_team.team_name].append(bs.home_score)
                if bs.away_team and bs.away_score > 0:
                    wk_scores[bs.away_team.team_name].append(bs.away_score)
        except Exception:
            break
    all_w = [x for v in wk_scores.values() for x in v]
    league_wk_mean = float(np.mean(all_w)) if all_w else 340.0
    sds = [np.std(v, ddof=1) for v in wk_scores.values() if len(v) >= 4]
    sigma = float(np.mean(sds)) if sds else 67.0
    points_so_far = {tm: float(np.sum(v)) for tm, v in wk_scores.items()}

    # 2. healthy relative team strength via the shared slot/cap logic
    h_lookup, p_lookup = load_projections()
    V = {}
    for t in lg.teams:
        assigned, _ = fill_slots(build_team_players(t, h_lookup, p_lookup))
        V[t.team_name] = sum(s['value'] for s in assigned.values())
    base_mean = calibrate_means(V, league_wk_mean)

    # 3. IL phasing — per-player healthy weekly FP + return period
    allp = get_all_teams()
    il = allp[((allp['lineup_slot'].isin(['IL', 'IR'])) |
               (allp['injury_status'].isin(IL_STATES))) &
              (allp['injury_status'] != 'ACTIVE')].copy()
    det = get_injury_details(il['player_id'].dropna().astype(int).tolist())
    ret_by_id = {int(r.player_id): (r.return_date if pd.notna(r.return_date) else None)
                 for r in det.itertuples()} if len(det) else {}

    rh = pd.read_csv(OUT / 'xfp_rh3_projections.csv'); rh['nk'] = rh['player_name'].map(_norm)
    rp = pd.read_csv(OUT / 'xfp_rp3_projections.csv'); rp['nk'] = rp['player_name'].map(_norm)
    rh_i, rp_i = rh.set_index('nk'), rp.set_index('nk')

    def healthy_wk_fp(name, pos):
        nk = _norm(name)
        is_p = str(pos).upper() in {'SP', 'RP', 'P'}
        if is_p and nk in rp_i.index:
            return float(rp_i.loc[nk, 'xfp_rp3_per_start'] or 0) * SP_STARTS_WK
        if (not is_p) and nk in rh_i.index:
            return float(rh_i.loc[nk, 'xfp_rh3_per_game'] or 0) * H_GAMES_WK
        return 0.0

    il_phase = defaultdict(list)
    for r in il.itertuples():
        ret = ret_by_id.get(int(r.player_id)) if pd.notna(r.player_id) else None
        wfp = healthy_wk_fp(r.player_name, r.position)
        if wfp > 0:
            il_phase[r.team_name].append((return_period(ret, cur, cur_monday), wfp))

    # remaining schedule (deduped)
    standings = {t.team_name: {'w': t.wins, 'l': t.losses} for t in lg.teams}
    seen, cal = set(), defaultdict(list)
    for t in lg.teams:
        for i, m in enumerate(t.schedule):
            period = i + 1
            if period < cur or period > reg_end:
                continue
            opp = m.home_team if m.away_team.team_name == t.team_name else m.away_team
            key = tuple(sorted([t.team_name, opp.team_name])) + (period,)
            if key in seen:
                continue
            seen.add(key)
            cal[period].append((t.team_name, opp.team_name))
    periods = sorted(cal.keys())

    print(f'IL-aware MC | N={N_SIMS:,} | cur_period={cur} reg_end={reg_end} | '
          f'league_wk_mean={league_wk_mean:.0f} sigma={sigma:.1f} (empirical)')
    print('Remaining periods:', periods)

    pmean = {tm: {p: phased_team_mean(base_mean[tm], il_phase.get(tm, []), p)
                  for p in periods} for tm in standings}

    playoffs = {t: 0 for t in standings}
    finals = {t: 0 for t in standings}
    title = {t: 0 for t in standings}

    for _ in range(N_SIMS):
        wins = {t: standings[t]['w'] for t in standings}
        pts = {t: points_so_far.get(t, 0.0) for t in standings}
        for period in periods:
            for a, b in cal[period]:
                sa = np.random.normal(pmean[a][period], sigma)
                sb = np.random.normal(pmean[b][period], sigma)
                pts[a] += sa; pts[b] += sb
                if sa > sb: wins[a] += 1
                else: wins[b] += 1
        seeded = seed_order(wins, pts)[:PLAYOFF_TEAMS]
        for t in seeded:
            playoffs[t] += 1
        ps = sigma * PLAYOFF_SIGMA_MULT  # playoffs: everyone healthy -> base_mean

        def game(a, b):
            return a if np.random.normal(base_mean[a], ps) > np.random.normal(base_mean[b], ps) else b
        r1 = [game(seeded[2], seeded[5]), game(seeded[3], seeded[4])]
        semi = [game(seeded[0], r1[1]), game(seeded[1], r1[0])]
        for t in semi:
            finals[t] += 1
        title[game(semi[0], semi[1])] += 1

    rows = []
    for t in standings:
        rows.append({'team': t, 'current_record': f'{standings[t]["w"]}-{standings[t]["l"]}',
                     'pts_so_far': round(points_so_far.get(t, 0), 0),
                     'weekly_mean': round(base_mean[t], 1),      # back-compat alias
                     'base_wk_mean': round(base_mean[t], 1),
                     'playoff_pct': round(playoffs[t] / N_SIMS * 100, 1),
                     'finals_pct': round(finals[t] / N_SIMS * 100, 1),
                     'title_pct': round(title[t] / N_SIMS * 100, 1)})
    df = pd.DataFrame(rows).sort_values('title_pct', ascending=False)
    print(f'\n=== IL-Aware Calibrated MC (N={N_SIMS:,}) ===')
    print(df.to_string(index=False))

    payload = {'n_sims': N_SIMS, 'sigma_per_week': round(sigma, 1),
               'league_wk_mean': round(league_wk_mean, 1), 'il_aware': True,
               'standings_sim': df.to_dict(orient='records')}
    (OUT / 'monte_carlo.json').write_text(
        json.dumps(payload, separators=(',', ':'), default=str), encoding='utf-8')
    df.to_csv(OUT / 'monte_carlo.csv', index=False)
    print('\nwrote monte_carlo.json + .csv')


if __name__ == '__main__':
    main()
