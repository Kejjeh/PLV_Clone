"""period_meta — the ONE shared period-resolver for cap / window / banked count.

Three engines resolve the CURRENT matchup period's SP-start cap, its date
window, and the authoritative per-team banked count from THIS module, not three
copies:

  • ``run_matchup_leverage.py``   (win-probability strategy layer)
  • ``run_roster_audit.py``       (/roster-audit SP cap math)
  • ``build_matchup_dashboard.py``(matchup.html cap / starts-remaining display)

The PURE cap math (``sp_cap_for_period`` / ``weeks_in_period`` / ``period_window``
/ ``is_period_covered``) lives in :mod:`plv_clone.cap_math` and stays
dependency-light. This module wraps it with the two ESPN reads that need a live
league object — the ``matchup_periods`` week-count and the statId-33 banked
counter — so every consumer gets an identical cap + window + banked count.

Default-preserving: a standard single-week period resolves to
``SP_CAP`` (10) + a Mon–Sun week, byte-identical to the pre-2026-07-11 behavior.
The ASG two-week block (period 15) resolves to cap 16 over Jul 6–19, and clean
multi-week playoff rounds resolve to ``10×weeks`` over an N-week span.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Tuple

import pandas as pd

from plv_clone.cap_math import (  # noqa: F401  (re-exported for callers)
    sp_cap_for_period,
    period_window,
    is_period_covered,
    weeks_in_period,
    PERIOD_WINDOW_OVERRIDES,
    SP_CAP,
)


def _calendar_weeks(period, mp) -> int:
    """True CALENDAR-week span of a period. The ASG block (period 15) spans two
    calendar weeks but ESPN lists it as a single scoring index, so trust its
    explicit override window over the scoring-index count."""
    win = period_window(period)
    if win is not None:
        return max(1, round(((win[1] - win[0]).days + 1) / 7))
    return weeks_in_period(mp, period)


def _walk(from_p: int, from_start: date, to_p: int, mp) -> date:
    """Walk from one period's known Monday start to another's, summing each
    intervening period's *calendar* weeks. Monday-preserving by construction
    (every step is a multiple of 7 days)."""
    d = from_start
    if to_p > from_p:
        for p in range(from_p, to_p):
            d = d + timedelta(days=7 * _calendar_weeks(p, mp))
    else:
        for p in range(from_p - 1, to_p - 1, -1):
            d = d - timedelta(days=7 * _calendar_weeks(p, mp))
    return d


def _anchored_current_start(cur_mp: int, mp, today: date) -> date | None:
    """True Monday start of a MULTI-week current period that has no explicit
    override window of its own (a clean 2-week playoff round).

    The week-of-``today`` guess is only right during the period's FIRST week —
    in week 2 it re-anchors a week late and extends 7 days past the true period
    end (found by adversarial review 2026-07-30; would have gone live in the
    Sept playoff rounds). But the season DOES carry an absolute calendar anchor:
    every ASG-style entry in ``PERIOD_WINDOW_OVERRIDES`` pins one period to real
    dates (2026: period 15 → Mon Jul 6). Walking week-counts from that anchor
    yields the current period's true start regardless of which week today falls
    in. Sanity-gated: the derived window must actually CONTAIN today (protects
    against a hole-ridden ``matchup_periods`` map making the walk drift);
    otherwise return None and let the caller fall back to the week-of-today
    guess, warning loudly."""
    n_days = 7 * _calendar_weeks(cur_mp, mp)
    for p in sorted(PERIOD_WINDOW_OVERRIDES):
        if p == cur_mp:
            continue                       # its own override is handled upstream
        cand = _walk(p, PERIOD_WINDOW_OVERRIDES[p][0], cur_mp, mp)
        if cand <= today <= cand + timedelta(days=n_days - 1):
            return cand
    return None


def _period_start(league, period, mp, today: date) -> date:
    """Monday of the requested period's first week.

    The CURRENT period's start is resolved first: its explicit override window
    if one exists (ASG); the week of ``today`` for a standard single-week period
    (byte-identical to the pre-fix behavior); and for a multi-week period with
    no override (clean playoff round), the absolute-anchor walk in
    :func:`_anchored_current_start` — the week-of-today guess is only correct in
    week 1, so weeks 2+ NEED the anchor. Any OTHER period then walks
    forward/back from that start, summing each intervening period's *calendar*
    weeks, so an ASG/playoff block longer than one week shifts later periods by
    the right number of days (the original bug: the old code returned the week
    of ``today`` for every period, so any non-current period resolved to the
    wrong window)."""
    cur_monday = today - timedelta(days=today.weekday())
    cur_mp = getattr(league, "currentMatchupPeriod", None)
    if cur_mp is None or period is None:
        return cur_monday
    cur_win = period_window(cur_mp)          # ASG current → its real start
    if cur_win is not None:
        cur_start = cur_win[0]
    elif _calendar_weeks(cur_mp, mp) <= 1:
        cur_start = cur_monday               # single week: today's week IS it
    else:
        cur_start = _anchored_current_start(cur_mp, mp, today)
        if cur_start is None:
            print(f'  ⚠ period_meta: period {cur_mp} spans '
                  f'{_calendar_weeks(cur_mp, mp)} weeks but no override anchor '
                  f'reaches it — assuming today is in its FIRST week. If this '
                  f'is week 2+, the window is a week late; add the period to '
                  f'PERIOD_WINDOW_OVERRIDES to pin it.')
            cur_start = cur_monday
    if cur_mp == period:
        return cur_start
    return _walk(cur_mp, cur_start, period, mp)


def resolve_period_meta(league, period, *, today: date | None = None) -> dict:
    """Resolve cap + date window + week-count for a matchup ``period``.

    The single source of truth for "what is the cap and window RIGHT NOW":

      • ``weeks`` = ``len(settings.matchup_periods[period])`` (ESPN), else 1;
      • ``sp_cap`` = ``sp_cap_for_period(period, weeks=weeks)`` — the ASG override
        (period 15 → 16) beats the general ``10×weeks`` rule;
      • ``week_start``/``week_end`` = the explicit override window (ASG) if one
        exists, else the current Mon .. Mon+7×weeks-1 span (a plain single-week
        period → a Mon–Sun week, byte-identical to before).

    ``today`` defaults to ``date.today()``; callers with a timezone-correct
    "today" (e.g. the dashboard's ET helper) pass it explicitly so the derived
    week window matches their other date math.

    Returns a dict:
        ``{period, weeks, sp_cap, week_start, week_end, covered}``.
    """
    if today is None:
        today = date.today()
    try:
        mp = getattr(getattr(league, "settings", None), "matchup_periods", {}) or {}
    except Exception:
        mp = {}
    weeks = weeks_in_period(mp, period)
    sp_cap = sp_cap_for_period(period, weeks=weeks)
    win = period_window(period)
    if win is not None:                       # ASG override (real date span)
        week_start, week_end = win
    else:                                     # standard OR multi-week playoff
        week_start = _period_start(league, period, mp, today)
        week_end = week_start + timedelta(days=7 * max(1, weeks) - 1)
    return {
        "period": period,
        "weeks": weeks,
        "sp_cap": sp_cap,
        "week_start": week_start,
        "week_end": week_end,
        "covered": is_period_covered(period),
    }


def resolve_current_period_meta(league, *, today: date | None = None) -> dict:
    """Resolve cap + window + week-count for the league's CURRENT matchup period.

    The one seam every cap consumer should call: it reads the live period off
    ``league.currentMatchupPeriod`` (ESPN) and delegates to
    :func:`resolve_period_meta`, so no engine re-duplicates the
    ``getattr(league, 'currentMatchupPeriod') → resolve`` dance (which used to be
    copy-pasted into run_roster_audit / run_matchup_leverage / the matchup
    dashboard). Returns the same dict as ``resolve_period_meta``. A league
    missing ``currentMatchupPeriod`` resolves as period ``None`` → the safe
    single-week default (cap 10)."""
    period = getattr(league, "currentMatchupPeriod", None)
    return resolve_period_meta(league, period, today=today)


def espn_period_meta(league, period, my_team_id, opp_team_id) -> dict:
    """AUTHORITATIVE per-team banked SP-start count for the current matchup period,
    read straight from ESPN (the same statId-33 counter ESPN uses to enforce the
    cap): cumulativeScore.statBySlot["22"].value. This is ground truth — it's the
    3/16, 6/16 shown on the matchup screen — and supersedes the boxscore-store
    inference. Also returns the elapsed scoring-period span (for the loud
    multi-week warning) and the per-scoring-period cap rate (for a cross-check).

    ``opp_team_id`` may be ``None`` (e.g. roster-audit only needs its own count);
    the opponent slot is simply left unset. Returns ``{}`` on any failure so the
    caller falls back to the boxscore count.
    """
    out: dict = {}
    try:
        data = league.espn_request.league_get(params={'view': ['mMatchupScore']})
    except Exception as exc:
        print(f'  WARN espn_period_meta: mMatchupScore fetch failed ({exc}); '
              f'falling back to boxscore-store banked count')
        return out

    def _gs(side):
        cum = (side or {}).get('cumulativeScore', {}) or {}
        slot = (cum.get('statBySlot') or {}).get('22') or {}
        if slot.get('statId') != 33:
            return None
        val = slot.get('value')
        return int(round(val)) if val is not None else None

    for m in data.get('schedule', []):
        if m.get('matchupPeriodId') != period:
            continue
        for side in ('home', 'away'):
            s = m.get(side)
            if not s:
                continue
            tid = s.get('teamId')
            if tid == my_team_id:
                out['my_banked'] = _gs(s)
                pbsp = s.get('pointsByScoringPeriod') or {}
                if pbsp:
                    sps = sorted(int(k) for k in pbsp.keys())
                    out['elapsed_span_days'] = sps[-1] - sps[0]
            elif opp_team_id is not None and tid == opp_team_id:
                out['opp_banked'] = _gs(s)

    # per-scoring-period start rate (statId 33) — for the cap cross-check warning
    try:
        sett = league.espn_request.league_get(params={'view': ['mSettings']})['settings']
        lim = (sett.get('rosterSettings', {}) or {}).get('lineupSlotStatLimits', {}) or {}
        rate = (lim.get('22') or {}).get('limitValue')
        if rate:
            out['cap_rate_per_sp'] = float(rate)
    except Exception:
        pass
    return out


# ─────────────────────────────────────────────────────────────────────────
# Pure ISO-week period math (merged from lib/period_math.py, audit
# 2026-07-19 item 18 — that module had a single importer). These are the
# NAIVE Mon–Sun ISO-week helpers used by the closed-week actuals backfill
# (fetch_closed_matchup_actuals.py); they are DISTINCT from the ESPN-aware
# ``period_window``/``resolve_period_meta`` above, which honor the ASG /
# playoff multi-week overrides. Plan v11 PR 3a extracted the pure layer so
# it can be exhaustively parametrized (tests/test_period_math.py).
# ─────────────────────────────────────────────────────────────────────────

def compute_period_window(period_first_snapshot_date: date) -> Tuple[date, date]:
    """Return the (Monday start, Sunday end) of the matchup-period ISO week
    that contains ``period_first_snapshot_date``.

    BrownU matchup periods run Mon-Sun. The first roster snapshot in a
    period typically lands on Monday but can drift (e.g. delayed
    snapshot after a weekend). The function anchors on the ISO week.

    Examples:
        >>> compute_period_window(date(2026, 6, 1))   # Monday
        (datetime.date(2026, 6, 1), datetime.date(2026, 6, 7))
        >>> compute_period_window(date(2026, 6, 4))   # Thursday
        (datetime.date(2026, 6, 1), datetime.date(2026, 6, 7))
    """
    start = period_first_snapshot_date - timedelta(days=period_first_snapshot_date.weekday())
    end = start + timedelta(days=6)
    return start, end


def is_period_closed(period_end: date, today: date) -> bool:
    """A period closes the day AFTER its Sunday end. ``today`` strictly
    later than ``period_end`` means the period's box-score finals are
    now available.

    Args:
        period_end: The Sunday end-of-period date (from
            ``compute_period_window`` or equivalent).
        today: Reference "now" date. Pure-function input so tests can
            simulate any clock.

    Returns:
        True if today is strictly past the period's Sunday end.

    Examples:
        >>> is_period_closed(date(2026, 6, 7), date(2026, 6, 8))
        True
        >>> is_period_closed(date(2026, 6, 7), date(2026, 6, 7))   # Sunday itself
        False
    """
    return today > period_end


def period_window_for_snapshots(snapshot_dates: Iterable[date]) -> Tuple[date, date]:
    """Compute the period window covering ``min(snapshot_dates)``.

    Convenience for callers that have a list of snapshot dates and want
    the ISO-week window containing the EARLIEST snapshot (which is
    typically the period's first snapshot).
    """
    snaps = sorted(snapshot_dates)
    if not snaps:
        raise ValueError("period_window_for_snapshots: empty snapshot list")
    return compute_period_window(snaps[0])


def adapter_period_closed_from_history_df(
    history_df: pd.DataFrame,
    *,
    period_col: str = "matchup_period",
    date_col: str = "snapshot_date",
    today: date | None = None,
) -> dict[int, bool]:
    """Given a roster-history DataFrame with one row per (matchup_period,
    snapshot_date), return ``{period: is_closed}`` using the pure
    ``is_period_closed`` underneath.

    This is the I/O-bearing adapter. Production code (e.g.
    fetch_closed_matchup_actuals.py) should call THIS function, not
    the raw pure helpers, so that:
      1. DataFrame column conventions live in ONE place.
      2. Pure helpers stay test-isolated.

    Args:
        history_df: Roster-history DataFrame.
        period_col: Column with the matchup-period int.
        date_col: Column with the snapshot date (date or parseable string).
        today: Reference date (default: pd.Timestamp.today().date()).

    Returns:
        Mapping of matchup_period int -> bool (True if closed).
    """
    if today is None:
        today = pd.Timestamp.today().date()

    out: dict[int, bool] = {}
    if history_df.empty:
        return out

    # Normalize the date column to date objects for the pure layer.
    dates = pd.to_datetime(history_df[date_col]).dt.date
    for period, group_idx in history_df.groupby(period_col).groups.items():
        snaps = [dates.loc[i] for i in group_idx]
        _, end = period_window_for_snapshots(snaps)
        out[int(period)] = is_period_closed(end, today)
    return out
