"""build_il_stash_boards — what an IL'd player is actually worth to you.

Refresh step 4.947 (non-gating).

rp3/rh3 cannot read a player whose season the injury erased; rp3 says so
explicitly by tagging him `marcel_il` and returning a SUPPRESSED prior with
gs_to=0. Ranking a stash pool on that number is how Corbin Burnes lands below
replacement level and Spencer Schwellenbach reads as the best arm available —
while neither will throw another pitch this season.

This board answers the real question, which has three parts:

  1. **How good is he?**  `lib/il_marcel` — a plain Marcel over PRIOR SEASONS,
     validated 2026-08-05 against league-mean and last-season baselines
     (pitchers wRMSE 3.085 vs 3.540/4.236; hitters 0.0971 vs 0.1286/0.1111).
  2. **When is he back?**  ESPN's public athlete endpoint via
     `get_injury_details`, which supplied real dates for 62/73 hitters and
     116/179 pitchers. Falls back to the empirical IL-tier duration prior.
  3. **Will he be back at all?**  The censor rate from
     `data/research/il_return_priors.csv` — IL60 pitchers never return that
     season **43.2%** of the time, IL60 hitters 42.6%, IL15 hitters 17.3%.

EV = projected rate x projected remaining volume x P(returns). A pitcher with
no runway scores 0 no matter how good he is, which is the entire point.

Outputs data/outputs/il_stash_board.csv and il_stash_board_hitters.csv.
Rule 13: never edits an rp3/rh3 row, stands beside one.
"""
import datetime
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, 'src')

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from plv_clone.utils.name_match import safe_name_key  # noqa: E402
from scripts.xfp.lib.il_marcel import (  # noqa: E402
    BatterSeason, SeasonLine, blend_current, blend_current_hitter,
    project, project_hitter,
)

OUT_P = Path('data/outputs/il_stash_board.csv')
OUT_H = Path('data/outputs/il_stash_board_hitters.csv')
PRIORS = Path('data/research/il_return_priors.csv')
from plv_clone.il_states import IL_STATES_STRICT as IL_STATES  # issue #28
TIER = {'SIXTY_DAY_DL': 'IL60', 'FIFTEEN_DAY_DL': 'IL15', 'TEN_DAY_DL': 'IL10',
        'SEVEN_DAY_DL': 'IL7', 'INJURY_RESERVE': 'IL60'}
HIT_POS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH'}
GAMES_PER_DAY = 6.0 / 7.0
SP_SLOT_RATE = 0.20      # a rotation slot, in starts per team-game
PLAY_RATE = 0.90         # share of team games a returning regular starts
SEASON_END = datetime.date(datetime.date.today().year, 9, 28)


def _ip(x):
    s = str(x)
    if '.' not in s:
        return float(s or 0)
    w, f = s.split('.')
    return float(w) + {'0': 0.0, '1': 1 / 3, '2': 2 / 3}.get(f, 0.0)


def _yby(pid, group):
    try:
        r = requests.get(f'https://statsapi.mlb.com/api/v1/people/{pid}/stats',
                         params={'stats': 'yearByYear', 'group': group},
                         timeout=30).json()
    except Exception:
        return []
    sp = r.get('stats') or []
    out = []
    for s in (sp[0].get('splits', []) if sp else []):
        st = s['stat']
        g = lambda k: int(st.get(k, 0) or 0)  # noqa: E731
        try:
            yr = int(s['season'])
        except (KeyError, ValueError):
            continue
        if group == 'pitching':
            if not g('gamesStarted'):
                continue
            out.append(SeasonLine(yr, g('gamesStarted'),
                                  _ip(st.get('inningsPitched', '0')),
                                  g('strikeOuts'), g('hits'), g('earnedRuns'),
                                  g('baseOnBalls'), g('hitBatsmen')))
        else:
            if not g('plateAppearances'):
                continue
            out.append(BatterSeason(yr, g('gamesPlayed'), g('plateAppearances'),
                                    g('runs'), g('totalBases'), g('rbi'),
                                    g('baseOnBalls'), g('hitByPitch'),
                                    g('stolenBases'), g('strikeOuts')))
    return out


def main() -> int:
    today = datetime.date.today()
    year = today.year
    try:
        from app.espn_connector import (_get_league, get_all_teams,
                                        get_injury_details)
        lg = _get_league()
        fas = lg.free_agents(size=2000)
        tm = get_all_teams()
    except Exception as exc:
        print(f'  il-stash: ESPN unavailable ({exc}) — no board '
              f'(non-gating; NOT an all-clear)')
        return 0
    try:
        pr_all = pd.read_csv(PRIORS)
    except Exception as exc:
        print(f'  il-stash: IL priors unreadable ({exc}) — no board')
        return 0

    mine = tm[tm['team_name'].str.contains('Ligers', na=False)]
    my_il = mine[mine['lineup_slot'] == 'IL']

    for side, group, pos_ok, out_path in (
            ('P', 'pitching', lambda p: p == 'SP', OUT_P),
            ('H', 'hitting', lambda p: p in HIT_POS, OUT_H)):
        tp = pr_all[(pr_all.stratum == 'tier_x_pos')
                    & (pr_all.pos == side)].set_index('tier')
        cand = [dict(name=p.name, espn_id=p.playerId,
                     pos=getattr(p, 'position', ''),
                     team=getattr(p, 'proTeam', ''),
                     status=str(getattr(p, 'injuryStatus', '') or ''),
                     pct=float(getattr(p, 'percent_owned', 0) or 0), own='FA')
                for p in fas
                if str(getattr(p, 'injuryStatus', '') or '') in IL_STATES
                and pos_ok(getattr(p, 'position', ''))]
        for r in my_il.itertuples(index=False):
            if pos_ok(r.position):
                cand.append(dict(name=r.player_name,
                                 espn_id=int(r.player_id) if str(r.player_id).isdigit() else None,
                                 pos=r.position, team=r.pro_team,
                                 status=r.injury_status, pct=100.0, own='MINE'))
        if not cand:
            print(f'  il-stash [{side}]: nobody on the IL — skipped')
            continue
        c = pd.DataFrame(cand)
        try:
            det = get_injury_details([int(i) for i in c['espn_id'].dropna()])
            det = det.dropna(subset=['return_date'])
            rd = dict(zip(det['player_id'],
                          pd.to_datetime(det['return_date']).dt.date))
        except Exception as exc:
            print(f'  il-stash [{side}]: ESPN return dates unavailable ({exc}) '
                  f'— falling back to tier priors for everyone')
            rd = {}

        model = ('data/outputs/xfp_rp3_projections.csv' if side == 'P'
                 else 'data/outputs/xfp_rh3_projections.csv')
        idc, ratec = (('pitcher', 'xfp_rp3_per_start') if side == 'P'
                      else ('batter', 'xfp_rh3_per_pa'))
        try:
            m = pd.read_csv(model)
            m['k'] = m['player_name'].map(safe_name_key)
            c['k'] = c['name'].map(safe_name_key)
            c = c.merge(m[['k', idc, 'rank', ratec]], on='k', how='left')
            c = c[c[idc].notna()]
        except Exception as exc:
            print(f'  il-stash [{side}]: model join failed ({exc}) — skipped')
            continue

        rows = []
        for r in c.itertuples(index=False):
            lines = _yby(int(getattr(r, idc)), group)
            if not lines:
                continue
            cur = next((l for l in lines if l.season == year), None)
            if side == 'P':
                est = blend_current(project(lines, as_of_season=year), cur)
                rate_units = SP_SLOT_RATE
            else:
                est = blend_current_hitter(project_hitter(lines, as_of_season=year), cur)
                heavy = [l for l in lines if l.pa >= 300]
                newest = max(heavy, key=lambda l: l.season) if heavy else None
                rate_units = ((newest.pa / max(newest.g, 1)) if newest else 3.9) * PLAY_RATE
            tier = TIER.get(r.status, 'IL15')
            pri = tp.loc[tier] if tier in tp.index else None
            ret, src = rd.get(r.espn_id), 'ESPN'
            if ret is None and pri is not None:
                ret = today + datetime.timedelta(days=float(pri['p50_days']) / 2)
                src = f'{tier} prior'
            days = (SEASON_END - max(ret, today)).days if ret else 0
            vol = max(days, 0) * GAMES_PER_DAY * rate_units
            censor = float(pri['censor_rate']) if pri is not None else 0.30
            rows.append(dict(name=r.name, own=r.own, pos=r.pos, team=r.team,
                             status=r.status, pct=r.pct,
                             model_rank=getattr(r, 'rank'),
                             model_rate=getattr(r, ratec),
                             marcel=est.fp_per_start, conf=est.confidence,
                             eff=est.effective_starts, ret=ret, ret_src=src,
                             volume=round(vol, 1), censor=censor,
                             ev=round(est.fp_per_start * vol * (1 - censor), 1)))
        if not rows:
            print(f'  il-stash [{side}]: no rows survived — skipped')
            continue
        b = pd.DataFrame(rows).sort_values('ev', ascending=False)
        # NONE/LOW confidence is the league prior wearing a name; it must not
        # outrank a player with an actual track record.
        b = b[b['conf'].isin(['HIGH', 'MEDIUM'])].reset_index(drop=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        b.to_csv(out_path, index=False)
        dead = int((b['volume'] <= 1).sum())
        print(f'  il-stash [{side}]: {len(b)} rows, {dead} with NO runway '
              f'this season -> {out_path}')
        for r in b[b['own'] == 'MINE'].itertuples(index=False):
            print(f'      MINE  EV {r.ev:>6.1f}  {r.marcel} ({r.conf})  '
                  f'ret {r.ret} ({r.ret_src})  censor {r.censor:.0%}  {r.name}')
        top = b[(b['own'] == 'FA') & (b['volume'] > 1)].head(3)
        for r in top.itertuples(index=False):
            print(f'      FA    EV {r.ev:>6.1f}  {r.marcel} ({r.conf})  '
                  f'ret {r.ret}  own% {r.pct:.0f}  {r.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
