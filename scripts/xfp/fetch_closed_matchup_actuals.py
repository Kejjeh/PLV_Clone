"""Fetch closed matchup final scores from ESPN and backfill
`actual_my_final` / `actual_opp_final` columns in predictions_history.csv.

For each unique period in predictions_history that has any NaN actuals, asks
ESPN whether that matchup is DECIDED and, if so, writes the matchup totals
back to the rows where the actuals are missing.

Idempotent: safe to re-run anytime. Only fills NaN rows; never overwrites
unless `--repair` is passed (which rewrites rows whose stored actuals
disagree with ESPN's authoritative final).

Emits a one-line summary suitable for log scraping:
  Backfilled M new rows; total backfilled now N/T.

Run periodically (e.g., as part of refresh_dashboards.py) or on demand.

--------------------------------------------------------------------------
2026-07-30 CORRECTNESS FIX (track I5, `pwin_mean_bias_2026-07-30.md`)
--------------------------------------------------------------------------
The previous implementation decided "is this period closed?" from the ISO
week of the FIRST SNAPSHOT date and then read finals through
`league.box_scores(matchup_period=N)`.  Both halves were wrong:

  * the ISO-week rule declares a MULTI-week period closed after seven days,
    so the 2026 All-Star block (period 15, Jul 6-19) was fetched on Jul 13
    while it was still running;
  * `espn_api`'s `box_scores()` only overrides `scoring_period` when the
    caller passes it explicitly, so `scoringPeriodId` stayed at TODAY, and
    `H2HPointsBoxScore` prefers `totalPointsLive` whenever the payload
    carries it -- i.e. the CURRENT DAY's points, not the period total.

Together they wrote single-day scores into five of eleven live periods as if
they were finals (period 13 was stored as 25.7-64.5; the real final was
322.1-331.3).  Those corrupted labels are what the win-probability
calibration harness has been grading against.

The fix reads the raw `mMatchupScore` schedule, takes `totalPoints`, and
refuses to write anything for a matchup ESPN still reports as UNDECIDED.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HISTORY = ROOT / 'data' / 'outputs' / 'predictions_history.csv'

UNDECIDED = 'UNDECIDED'
#: tolerance (FP) below which a stored actual is treated as agreeing with ESPN
REPAIR_TOL = 0.05


class PeriodNotFinal(RuntimeError):
    """ESPN still reports the matchup as UNDECIDED — refuse to write a final."""


class MatchupNotFound(RuntimeError):
    """No schedule entry for (period, team) — fail loudly rather than guess."""


def _ensure_actual_cols(df: pd.DataFrame) -> pd.DataFrame:
    for c in ('actual_my_final', 'actual_opp_final', 'model_version'):
        if c not in df.columns:
            df[c] = pd.NA
    return df


def finals_from_schedule(schedule, my_team_id: int, period: int) -> tuple[float, float]:
    """(my_final, opp_final) for `period` out of a raw mMatchupScore schedule.

    Reads ``totalPoints`` — the MATCHUP total — never ``totalPointsLive``,
    which is the current scoring period's (i.e. today's) points and is what
    corrupted five periods of `predictions_history.csv` before 2026-07-30.

    Raises `PeriodNotFinal` if ESPN has not declared a winner, `MatchupNotFound`
    if the team does not appear in that period, and `KeyError` if ESPN omitted
    ``totalPoints``. Never returns a defaulted or zeroed score.
    """
    for m in schedule:
        if m.get('matchupPeriodId') != period:
            continue
        home = m.get('home') or {}
        away = m.get('away') or {}
        if home.get('teamId') == my_team_id:
            mine, opp = home, away
        elif away.get('teamId') == my_team_id:
            mine, opp = away, home
        else:
            continue
        winner = str(m.get('winner') or UNDECIDED).upper()
        if winner == UNDECIDED:
            raise PeriodNotFinal(
                f'period {period}: ESPN winner=UNDECIDED — matchup still open')
        for side, lbl in ((mine, 'my'), (opp, 'opp')):
            if 'totalPoints' not in side:
                raise KeyError(
                    f'period {period}: ESPN {lbl} side has no totalPoints '
                    f'(keys={sorted(side)})')
        return float(mine['totalPoints']), float(opp['totalPoints'])
    raise MatchupNotFound(f'period {period}: no schedule entry for team {my_team_id}')


def fetch_schedule_and_team_id(team_name_fragment: str = 'Ligers'):
    """Live ESPN read: (raw mMatchupScore schedule, my team_id)."""
    from plv_clone.league_state import LeagueState
    league = LeagueState()._get_league()
    mine = [t.team_id for t in league.teams
            if team_name_fragment in (t.team_name or '')]
    if len(mine) != 1:
        raise MatchupNotFound(
            f'expected exactly one team matching {team_name_fragment!r}, got {mine}')
    data = league.espn_request.league_get(params={'view': ['mMatchupScore']})
    return data['schedule'], int(mine[0])


# Model versions that correspond to REAL logged matchups. Anything else in
# predictions_history.csv (the `backfill_2024_*` / `backfill_2025_*` families) is
# SYNTHETIC panel data that happens to reuse the `period` column, and must never
# be touched by a live-matchup backfill or repair.
LIVE_MODEL_VERSIONS = ('baseline', 'MA_v1')


def run_backfill(verbose: bool = True, repair: bool = False,
                 schedule=None, my_team_id: int | None = None) -> tuple[int, int, int]:
    """Run the incremental backfill.

    `schedule` / `my_team_id` are injection seams for tests; when omitted they
    are read live from ESPN.

    Returns (new_rows_filled, total_backfilled_now, total_rows).
    """
    if not HISTORY.exists():
        if verbose:
            print(f'No predictions_history at {HISTORY}')
        return 0, 0, 0
    df = pd.read_csv(HISTORY)
    df = _ensure_actual_cols(df)

    if schedule is None or my_team_id is None:
        try:
            schedule, my_team_id = fetch_schedule_and_team_id()
        except Exception as e:            # network/auth — report, do not guess
            print(f'ESPN schedule fetch failed: {e}')
            return 0, int(df['actual_my_final'].notna().sum()), int(len(df))

    new_filled = 0
    repaired = 0
    for period in sorted(df['period'].dropna().unique()):
        period = int(period)
        # LIVE ROWS ONLY. The 141 synthetic `backfill_2024_*` / `backfill_2025_*`
        # rows reuse the same `period` column, so an unfiltered mask sweeps them
        # into a real-matchup repair: measured on a copy of the real store,
        # `--repair` changed 285 rows of which 105 were synthetic, and periods 2-6
        # have NO live rows at all so those repairs were 100% collateral. Worse,
        # every synthetic row in a period collapses to one identical value, which
        # annihilates the within-period spread that is the entire point of that
        # panel. Found by adversarial review 2026-07-30, before anyone ran it.
        rows = (df['period'] == period) & df['model_version'].isin(LIVE_MODEL_VERSIONS)
        missing = rows & df['actual_my_final'].isna()
        if not missing.any() and not repair:
            continue
        try:
            my_final, opp_final = finals_from_schedule(schedule, my_team_id, period)
        except PeriodNotFinal as e:
            if verbose:
                print(f'  Period {period}: {e}. Skipping.')
            continue
        except (MatchupNotFound, KeyError) as e:
            print(f'  Period {period}: {e}')
            continue
        if missing.any():
            df.loc[missing, 'actual_my_final'] = my_final
            df.loc[missing, 'actual_opp_final'] = opp_final
            new_filled += int(missing.sum())
            if verbose:
                print(f'  Period {period}: filled {int(missing.sum())} missing rows '
                      f'with my={my_final:.1f}, opp={opp_final:.1f}')
        if repair:
            stale = rows & (
                ((df['actual_my_final'] - my_final).abs() > REPAIR_TOL)
                | ((df['actual_opp_final'] - opp_final).abs() > REPAIR_TOL))
            if stale.any():
                old = df.loc[stale, ['actual_my_final', 'actual_opp_final']].iloc[0]
                df.loc[stale, 'actual_my_final'] = my_final
                df.loc[stale, 'actual_opp_final'] = opp_final
                repaired += int(stale.sum())
                print(f'  Period {period}: REPAIRED {int(stale.sum())} rows '
                      f'{old["actual_my_final"]:.1f}-{old["actual_opp_final"]:.1f} '
                      f'-> {my_final:.1f}-{opp_final:.1f}')

    if new_filled or repaired:
        df.to_csv(HISTORY, index=False)

    total_backfilled = int(df['actual_my_final'].notna().sum())
    total = int(len(df))
    print(f'Backfilled {new_filled} new rows; total backfilled now '
          f'{total_backfilled}/{total}.'
          + (f' Repaired {repaired} stale rows.' if repair else ''))
    return new_filled, total_backfilled, total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repair', action='store_true',
                    help='overwrite stored actuals that disagree with ESPN finals')
    args = ap.parse_args()
    run_backfill(verbose=True, repair=args.repair)


if __name__ == '__main__':
    main()
