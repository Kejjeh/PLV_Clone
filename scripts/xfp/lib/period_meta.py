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

from plv_clone.cap_math import (  # noqa: F401  (re-exported for callers)
    sp_cap_for_period,
    period_window,
    is_period_covered,
    weeks_in_period,
    SP_CAP,
)


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
        week_start = today - timedelta(days=today.weekday())
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
