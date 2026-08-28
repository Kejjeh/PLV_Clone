"""run_window_split — "show me X since <date>", with every claim sample-gated.

Answers the shape of question that produced the 2026-08-03 Teo read: a player
looks hot (or cold) inside some window, and you need to know which parts of
that are knowable yet. Results are always reported; PROCESS metrics are
reported only where the window clears the empirical minimum, and the ones that
do not clear are named rather than omitted.

  python scripts/xfp/run_window_split.py "Teoscar Hernandez" --since asg
  python scripts/xfp/run_window_split.py "Spencer Horwitz" --since 2026-08-02
  python scripts/xfp/run_window_split.py "Hunter Greene" --since asg --side SP

`--since asg` resolves the All-Star break from the schedule (the largest
mid-July gap in the MLB slate) rather than a hardcoded date, so it keeps
working next season.

Rule 13: display only. Nothing here moves rh3/rp3/rprs2.
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
_REPO_ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]  # repo root, NOT cwd (issue #72)
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, 'src')

import datetime  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from plv_clone.utils.name_match import resolve_batter_id, safe_name_key  # noqa: E402
from scripts.xfp.lib.window_split import (  # noqa: E402
    fp_per_pa_from_k_delta, render, split_read, summarize,
)

SWING = {'swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip',
         'hit_into_play', 'foul_bunt', 'missed_bunt', 'bunt_foul_tip'}
MISS = {'swinging_strike', 'swinging_strike_blocked', 'missed_bunt',
        'foul_tip', 'bunt_foul_tip'}
BAT_SPEED_STORE = 'data/research/bat_speed_daily.parquet'


def resolve_asg_break(year: int):
    """First game-day AFTER the largest gap in the mid-July slate.

    Derived, not hardcoded: the break is the only multi-day hole in a season,
    and its dates move every year.
    """
    try:
        r = requests.get('https://statsapi.mlb.com/api/v1/schedule',
                         params={'sportId': 1,
                                 'startDate': f'{year}-07-05',
                                 'endDate': f'{year}-07-25'}, timeout=45).json()
    except Exception as exc:
        raise SystemExit(f'schedule fetch failed ({exc}); pass --since YYYY-MM-DD')
    days = sorted({d['date'] for d in r.get('dates', [])
                   if len(d.get('games', [])) >= 5})
    if len(days) < 2:
        raise SystemExit('could not resolve the ASG break; pass --since YYYY-MM-DD')
    dates = [datetime.date.fromisoformat(x) for x in days]
    gaps = [(dates[i + 1] - dates[i], dates[i + 1]) for i in range(len(dates) - 1)]
    return max(gaps, key=lambda t: t[0])[1]


def brownu_hitter_log(mlbam: int, year: int) -> pd.DataFrame:
    r = requests.get(f'https://statsapi.mlb.com/api/v1/people/{mlbam}/stats',
                     params={'stats': 'gameLog', 'group': 'hitting',
                             'season': year}, timeout=45).json()
    sp = r.get('stats') or []
    if not sp:
        return pd.DataFrame()
    rows = []
    for s in sp[0].get('splits', []):
        st = s['stat']
        g = lambda k: int(st.get(k, 0) or 0)  # noqa: E731
        rows.append(dict(
            date=s['date'], PA=g('plateAppearances'), AB=g('atBats'),
            H=g('hits'), HR=g('homeRuns'), R=g('runs'), RBI=g('rbi'),
            BB=g('baseOnBalls'), K=g('strikeOuts'), TB=g('totalBases'),
            SB=g('stolenBases'),
            FP=(g('runs') + g('totalBases') + g('rbi') + g('baseOnBalls')
                + g('hitByPitch') + g('stolenBases') - g('strikeOuts'))))
    return pd.DataFrame(rows).sort_values('date')


def _pitch_window(d: pd.DataFrame):
    """(metric -> (value, denom)) for one slice of pitch-level rows."""
    inz = d['zone'].between(1, 9)
    ooz = ~inz
    sw = d['description'].isin(SWING)
    miss = d['description'].isin(MISS)
    # BATTED BALLS, not "every tracked contact". Statcast reports launch_speed
    # on fouls too, and fouls are weakly hit by construction, so including them
    # roughly halves the measured hard-hit rate. Requiring a PA-ending event
    # restricts to balls in play, which is what hard-hit%/barrel% mean.
    # (Caught 2026-08-05: Teoscar Hernandez post-ASG read 19.8% on the loose
    # denominator vs a true 33.3% -- the DIRECTION held but every level was wrong.)
    bip = d[d['launch_speed'].notna() & d['events'].notna()]
    pct = lambda n, dn: (100.0 * n / dn) if dn else None  # noqa: E731
    out = {
        'chase': (pct((sw & ooz).sum(), ooz.sum()), int(ooz.sum())),
        'zswing': (pct((sw & inz).sum(), inz.sum()), int(inz.sum())),
        'whiff': (pct(miss.sum(), sw.sum()), int(sw.sum())),
        'swstr': (pct(miss.sum(), len(d)), int(len(d))),
    }
    if len(bip):
        out['hard_hit'] = (float((bip['launch_speed'] >= 95).mean() * 100), len(bip))
        out['barrel'] = (float(((bip['launch_speed'] >= 98)
                                & (bip['launch_angle'].between(26, 30))).mean() * 100),
                         len(bip))
    return out


def _bat_speed(mlbam, lo, hi):
    """(player mean, player n, league mean) over [lo, hi)."""
    try:
        b = pd.read_parquet(BAT_SPEED_STORE)
    except Exception:
        return None, 0, None
    b['game_date'] = pd.to_datetime(b['game_date'])
    win = b[(b['game_date'] >= pd.Timestamp(lo)) & (b['game_date'] < pd.Timestamp(hi))]
    if not len(win):
        return None, 0, None
    lg_w = win['n_swings']
    league = float((win['mean_bat_speed'] * lg_w).sum() / lg_w.sum()) if lg_w.sum() else None
    me = win[win['batter'] == mlbam]
    w = me['n_swings']
    if not len(me) or w.sum() == 0:
        return None, 0, league
    return float((me['mean_bat_speed'] * w).sum() / w.sum()), int(w.sum()), league


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--since', default='asg',
                    help='"asg" (default) or YYYY-MM-DD — start of the AFTER window')
    ap.add_argument('--side', default='H', choices=('H', 'SP', 'RP'))
    ap.add_argument('--year', type=int, default=datetime.date.today().year)
    a = ap.parse_args()

    mlbam = resolve_batter_id(a.name)
    if mlbam is None:
        print(f'could not resolve {a.name!r} to an mlbam id — try the accented '
              f'spelling, or use /player-id-resolve')
        return 1
    split = (resolve_asg_break(a.year) if a.since == 'asg'
             else datetime.date.fromisoformat(a.since))
    # The break itself belongs to neither window.
    pre_end = split - datetime.timedelta(days=2)
    print(f'=== {a.name} (mlbam {mlbam}) — split {split} '
          f'[BEFORE < {pre_end}, AFTER >= {split}] ===\n')

    log = brownu_hitter_log(mlbam, a.year)
    if len(log):
        pre = log[log['date'] < pre_end.isoformat()]
        post = log[log['date'] >= split.isoformat()]
        print('--- RESULTS (BrownU FP; always reported) ---')
        print(f"{'window':<10} {'G':>4} {'PA':>5} {'FP':>6} {'FP/g':>6} {'FP/PA':>7} "
              f"{'HR':>3} {'K%':>6} {'AVG':>6} {'SLG':>6}")
        for lbl, t in (('BEFORE', pre), ('AFTER', post)):
            n, pa = len(t), int(t.PA.sum())
            if not n:
                continue
            print(f'{lbl:<10} {n:>4} {pa:>5} {int(t.FP.sum()):>6} '
                  f'{t.FP.sum()/n:>6.2f} {t.FP.sum()/max(pa,1):>7.3f} '
                  f'{int(t.HR.sum()):>3} {100*t.K.sum()/max(pa,1):>6.1f} '
                  f'{t.H.sum()/max(t.AB.sum(),1):>6.3f} '
                  f'{t.TB.sum()/max(t.AB.sum(),1):>6.3f}')
        print()

    try:
        sc = pd.read_parquet(
            f'data/research/xfp_cache/statcast_{a.year}.parquet',
            columns=['batter', 'game_date', 'zone', 'description',
                     'launch_speed', 'launch_angle', 'events'])
    except Exception as exc:
        print(f'statcast unavailable ({exc}) — results only, no process read')
        return 0
    sc = sc[sc['batter'] == mlbam].copy()
    sc['game_date'] = pd.to_datetime(sc['game_date'])
    pre_p = _pitch_window(sc[sc['game_date'] < pd.Timestamp(pre_end)])
    post_p = _pitch_window(sc[sc['game_date'] >= pd.Timestamp(split)])

    reads = []
    if len(log):
        pre_pa, post_pa = int(pre.PA.sum()), int(post.PA.sum())
        for m, col in (('k_pct', 'K'), ('bb_pct', 'BB')):
            reads.append(split_read(
                m, a.side,
                before=100 * pre[col].sum() / max(pre_pa, 1), before_denom=pre_pa,
                after=100 * post[col].sum() / max(post_pa, 1), after_denom=post_pa))
    for m in ('chase', 'zswing', 'whiff', 'swstr', 'hard_hit', 'barrel'):
        if m not in post_p and m not in pre_p:
            continue
        bv, bn = pre_p.get(m, (None, 0))
        av, an = post_p.get(m, (None, 0))
        reads.append(split_read(m, a.side, before=bv, before_denom=bn,
                                after=av, after_denom=an))
    bs_b, bs_bn, lg_b = _bat_speed(mlbam, f'{a.year}-01-01', pre_end)
    bs_a, bs_an, lg_a = _bat_speed(mlbam, split, f'{a.year}-12-31')
    if bs_a is not None or bs_b is not None:
        reads.append(split_read('bat_speed', a.side, before=bs_b, before_denom=bs_bn,
                                after=bs_a, after_denom=bs_an,
                                league_before=lg_b, league_after=lg_a))

    print('--- PROCESS (gated on plv_clone.stabilization minimums) ---')
    print(render(reads))
    s = summarize(reads)
    print(f'\n  {s.headline}')
    if s.unreadable:
        print('  NOT YET KNOWABLE in this window: '
              + ', '.join(sorted(r.metric for r in s.unreadable)))
    kr = next((r for r in reads if r.metric == 'k_pct' and r.delta_readable), None)
    if kr:
        print(f'  K-rate move is worth '
              f'{fp_per_pa_from_k_delta(kr.before, kr.after):+.3f} fp/PA in BrownU')
    print('\n  Rule 13: display only — rh3/rp3/rprs2 untouched.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
