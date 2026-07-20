"""run_sp_breakout.py — /sp-form breakout-lens engine (sp-breakout-signal).

Transcribes the sp-breakout-signal SKILL.md rolling-window good-start recipe
(33,063 SP starts, 2018-2025 calibration) so the breakout lens stops being
hand-rebuilt inline every run. NO new signal invention — every threshold below
is copied verbatim from `.claude/skills/sp-breakout-signal/SKILL.md`:

  fp_proxy_per_bf = (K - BB - H - HR) / BF   per start (BF >= 10 filter)
  Good start: fp_proxy_per_bf >= -0.0476     (65th pct, 2018-2025)
  Rolling windows L3/L4/L5 mapped to the persistence table
  (baseline next-start good rate 36.0%):
    2/3 WATCH  3/4 ACTIONABLE  4/5 STRONG  3/3 STRONG  4/4 LOCK  5/5 LOCK
    2/4 NOISE  3/5 WATCH  0/N NEGATIVE  1/anything NOISE (unlisted -> NOISE)

TIER PRECEDENCE (QA'd ambiguity, 2026-07-20): when windows fire BOTH a
NEGATIVE (0/N) and a NOISE signal for the same arm, **NEGATIVE outranks
NOISE** — a cold-arm read is more informative than "no signal". Overall
ordering used for the verdict and the sort:
    NOISE < NEGATIVE < WATCH < ACTIONABLE < STRONG < LOCK
(positive tiers cannot co-fire with 0/N — the windows overlap — so NEGATIVE
never suppresses a real positive signal).

Supplementary flags, also verbatim from the SKILL:
  Signal A (4-8 GS only): season fpp >= +0.02 AND whiff% >= 26%
  SigStuff (stuff_contact_composite): gs >= 6 AND season fpp >= 0.0 AND
    ((whiff% >= 26 AND xwOBA-contact <= 0.320) OR
     (CSW% >= 30 AND xwOBA-contact <= 0.310))
  MODEL-LAG?: gs_2026 >= 10 AND signal >= 3/4 (ACTIONABLE+). The SKILL's third
    leg ("rp3 rank implies hold/drop") is qualitative — the engine prints the
    rp3 rank alongside and leaves that judgment to the reader; deep-dive via
    /fa-pickup-deep-dive.

Usage:
  python scripts/xfp/run_sp_breakout.py                       # my healthy SPs (live)
  python scripts/xfp/run_sp_breakout.py --names "Will Warren, Jose Soriano"

Output: one tier-table row per SP, sorted worst -> best.
Owners reused: plv_clone.utils.name_match resolvers, lib.pitcher_role
detect_pitcher_role, statcast_2026.parquet, xfp_rp3_projections.csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pandas as pd

_HERE = Path(__file__).resolve().parent
for p in (_HERE.parent.parent, _HERE.parent.parent / 'src', _HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plv_clone.paths import ROOT  # noqa: E402

STATCAST = ROOT / 'data' / 'research' / 'xfp_cache' / 'statcast_2026.parquet'
RP3_CSV = ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'

GOOD_THRESH = -0.0476      # 65th pct fp_proxy_per_bf, 2018-2025 calibration
BASELINE = 36.0            # next-start good rate, rolling-window baseline (%)

# (k, n) -> (tier, next-start good rate %). Verbatim SKILL persistence table.
TIER_TABLE: dict[tuple[int, int], tuple[str, float]] = {
    (2, 3): ('WATCH', 43.6),
    (3, 4): ('ACTIONABLE', 47.7),
    (4, 5): ('STRONG', 51.1),
    (3, 3): ('STRONG', 52.7),
    (4, 4): ('LOCK', 54.1),
    (5, 5): ('LOCK', 57.5),
    (2, 4): ('NOISE', 28.9),
    (3, 5): ('WATCH', 35.5),
}
# NEGATIVE outranks NOISE (see module docstring — documented precedence).
TIER_RANK = {'NOISE': 0, 'NEGATIVE': 1, 'WATCH': 2, 'ACTIONABLE': 3,
             'STRONG': 4, 'LOCK': 5}
ACTION = {'NOISE': 'IGNORE', 'NEGATIVE': 'NOTE NEGATIVE — avoid streaming',
          'WATCH': 'WATCH — re-check next start',
          'ACTIONABLE': 'ADD / ROSTER PROTECT',
          'STRONG': 'ADD / ROSTER PROTECT',
          'LOCK': 'LOCK IN'}


def _window_tier(k: int, n: int) -> tuple[str, float | None]:
    """(tier, next-start good rate %) for a K/N rolling window."""
    if k == 0:
        return 'NEGATIVE', 12.0        # 0/N ~12% per the SKILL table
    if k == 1:
        return 'NOISE', None           # 1/anything = noise, do not act
    if (k, n) in TIER_TABLE:
        return TIER_TABLE[(k, n)]
    return 'NOISE', None               # unlisted combos (e.g. 2/5) = no signal


def _roster_healthy_sps() -> list[tuple[str, str]]:
    """Live my-roster healthy SPs as (name, pro_team) — detect_pitcher_role
    is the role truth (gotcha #8), IL/IR slot is the health truth (gotcha #7:
    BE = active for Josh)."""
    from app.espn_connector import get_my_roster_with_injuries
    from lib.pitcher_role import detect_pitcher_role
    roster = get_my_roster_with_injuries()
    pitchers = roster[roster['eligible_slots'].apply(
        lambda s: any(p in str(s) for p in ('SP', 'RP')))].copy()
    if pitchers.empty:
        return []
    pitchers['role'] = pitchers.apply(detect_pitcher_role, axis=1)
    sps = pitchers[(pitchers['role'] == 'SP')
                   & (~pitchers['lineup_slot'].isin(['IL', 'IR']))]
    return list(zip(sps['player_name'], sps['pro_team']))


def _resolve(name: str, team: str | None):
    """Collision-safe name -> mlbam via the owner resolvers."""
    from plv_clone.utils.name_match import (
        canonical_pitcher_spelling, resolve_pitcher_id)
    for n in (name, canonical_pitcher_spelling(name)):
        pid = resolve_pitcher_id(n, team=team or None, role='SP')
        if pid is None and team:
            pid = resolve_pitcher_id(n, role='SP')
        if pid:
            return int(pid)
    return None


def _per_start_frame(pids: list[int]) -> pd.DataFrame:
    """Per-start aggregates (BF>=10) for all pitchers in one duckdb pass —
    the SKILL Step 1 query plus the whiff/csw/xwoba-contact columns the
    alternate signals need."""
    import duckdb
    id_list = ','.join(str(p) for p in pids)
    sql = f"""
    WITH raw AS (
      SELECT pitcher, game_date::DATE AS gd,
        COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) AS bf,
        SUM(CASE WHEN events='strikeout' THEN 1 ELSE 0 END) AS k,
        SUM(CASE WHEN events='walk' THEN 1 ELSE 0 END) AS bb,
        SUM(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
        SUM(CASE WHEN events='home_run' THEN 1 ELSE 0 END) AS hr,
        COUNT(*) AS total_pitches,
        COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked',
              'foul','foul_tip','hit_into_play') OR description LIKE 'foul%' THEN 1 END) AS swings,
        COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip')
              THEN 1 END) AS whiffs,
        COUNT(CASE WHEN description IN ('swinging_strike','swinging_strike_blocked','foul_tip',
              'called_strike') THEN 1 END) AS csw,
        AVG(CASE WHEN events IS NOT NULL AND events != ''
              THEN estimated_woba_using_speedangle END) AS xwoba_contact
      FROM read_parquet('{STATCAST.as_posix()}')
      WHERE pitcher IN ({id_list})
      GROUP BY pitcher, game_date::DATE
      HAVING COUNT(CASE WHEN events IS NOT NULL AND events != '' THEN 1 END) >= 10
    )
    SELECT *, ROUND((k-bb-h-hr)*1.0/NULLIF(bf,0), 4) AS fp_proxy_per_bf
    FROM raw ORDER BY pitcher, gd
    """
    con = duckdb.connect()
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def _analyze(name: str, pid: int, starts: pd.DataFrame, rp3: pd.DataFrame) -> dict:
    df = starts[starts['pitcher'] == pid].sort_values('gd')
    row: dict = {'name': name, 'mlbam': pid, 'gs': len(df)}
    if df.empty:
        row.update(tier='NO-DATA', rank=-1, action='no 2026 starts in statcast cache')
        return row

    df = df.copy()
    df['good'] = (df['fp_proxy_per_bf'] >= GOOD_THRESH).astype(int)
    goods = df['good'].tolist()

    best_tier, best_rate, windows = 'NOISE', None, {}
    for w in (3, 4, 5):
        if len(goods) >= w:
            k = sum(goods[-w:])
            tier, rate = _window_tier(k, w)
            windows[f'L{w}'] = f'{k}/{w}'
            if TIER_RANK[tier] > TIER_RANK[best_tier]:
                best_tier, best_rate = tier, rate
    row.update(windows)
    row['tier'] = best_tier
    row['rank'] = TIER_RANK[best_tier]
    row['rate'] = best_rate
    row['delta'] = None if best_rate is None else round(best_rate - BASELINE, 1)
    row['action'] = ACTION[best_tier]

    # Season aggregates for the alternate signals (verbatim SKILL gates).
    tot = df[['bf', 'k', 'bb', 'h', 'hr', 'swings', 'whiffs', 'csw',
              'total_pitches']].sum()
    season_fpp = (tot['k'] - tot['bb'] - tot['h'] - tot['hr']) / max(tot['bf'], 1)
    whiff_pct = 100.0 * tot['whiffs'] / max(tot['swings'], 1)
    csw_pct = 100.0 * tot['csw'] / max(tot['total_pitches'], 1)
    xwc = df['xwoba_contact'].mean()
    gs = len(df)
    flags = []
    if 4 <= gs <= 8 and season_fpp >= 0.02 and whiff_pct >= 26.0:
        flags.append('SigA')
    if gs >= 6 and season_fpp >= 0.0 and (
            (whiff_pct >= 26.0 and xwc == xwc and xwc <= 0.320)
            or (csw_pct >= 30.0 and xwc == xwc and xwc <= 0.310)):
        flags.append('SigStuff')

    # rp3 cross-reference (SP model — never rprs2 here).
    r = rp3[rp3['pitcher'] == pid]
    if not r.empty:
        r = r.iloc[0]
        row['rp3_rank'] = int(r['rank'])
        row['rp3_xfp'] = float(r['xfp_rp3_per_start'])
        row['dq_tag'] = str(r.get('data_quality_tag', ''))
        if gs >= 10 and TIER_RANK[best_tier] >= TIER_RANK['ACTIONABLE']:
            flags.append('MODEL-LAG?')
    row['flags'] = ' '.join(flags)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(
        description='sp-breakout-signal rolling-window engine (the /sp-form '
                    'breakout lens). Transcribes the SKILL persistence table; '
                    'no new signals.',
        epilog='Tier precedence: NEGATIVE (0/N cold arm) OUTRANKS NOISE when '
               'both fire across windows — the verdict ordering is '
               'NOISE < NEGATIVE < WATCH < ACTIONABLE < STRONG < LOCK. '
               'MODEL-LAG? fires on gs>=10 + signal>=3/4; the "rp3 rank '
               'implies hold/drop" leg is left to the reader (rank printed).')
    ap.add_argument('--names', default=None,
                    help='comma-separated SP names; default = my-roster '
                         'healthy SPs (live pull, detect_pitcher_role)')
    args = ap.parse_args()

    if args.names:
        targets = [(n.strip(), None) for n in args.names.split(',') if n.strip()]
    else:
        targets = _roster_healthy_sps()
        if not targets:
            print('no healthy SPs found on roster (live pull)')
            return 1

    resolved, unresolved = [], []
    for name, team in targets:
        pid = _resolve(name, team)
        (resolved.append((name, pid)) if pid else unresolved.append(name))
    if not resolved:
        print('no names resolved:', ', '.join(unresolved))
        return 1

    starts = _per_start_frame([pid for _, pid in resolved])
    rp3 = pd.read_csv(RP3_CSV) if RP3_CSV.exists() else pd.DataFrame(
        columns=['pitcher', 'rank', 'xfp_rp3_per_start'])

    rows = [_analyze(name, pid, starts, rp3) for name, pid in resolved]
    rows.sort(key=lambda r: (r['rank'], r.get('delta') or -99))  # worst first

    print(f'SP BREAKOUT SIGNAL — rolling good-start windows '
          f'(good = fp_proxy/BF >= {GOOD_THRESH}; baseline {BASELINE}%)')
    print('=' * 98)
    hdr = (f"{'SP':24s} {'GS':>3s} {'L3':>4s} {'L4':>4s} {'L5':>4s} "
           f"{'TIER':10s} {'Δpp':>6s} {'rp3':>5s} {'xFP/st':>7s}  ACTION / FLAGS")
    print(hdr)
    print('-' * 98)
    for r in rows:
        d = '' if r.get('delta') is None else f"{r['delta']:+.1f}"
        rk = f"#{r['rp3_rank']}" if r.get('rp3_rank') else '—'
        xfp = f"{r['rp3_xfp']:.2f}" if r.get('rp3_xfp') is not None else '—'
        extra = ' '.join(x for x in (r.get('action', ''), r.get('flags', '')) if x)
        if r.get('dq_tag', '').startswith('marcel'):
            extra += f"  [{r['dq_tag']} — rp3 is a suppressed prior, rank by Stuff+]"
        print(f"{r['name']:24s} {r['gs']:>3d} {r.get('L3', '—'):>4s} "
              f"{r.get('L4', '—'):>4s} {r.get('L5', '—'):>4s} "
              f"{r['tier']:10s} {d:>6s} {rk:>5s} {xfp:>7s}  {extra}")
    if unresolved:
        print('\n⚠ unresolved (no mlbam):', ', '.join(unresolved))
    print('\nSorted worst → best. 1/anything = noise; act at 3/4+; 0/N = cold '
          '(NEGATIVE outranks NOISE). MODEL-LAG? → /fa-pickup-deep-dive.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
