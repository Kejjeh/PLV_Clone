"""Lock the matchup dashboard's PERIOD-TRUE projection window (fix 2026-07-30).

Defect being pinned: ``build_matchup_dashboard.main()`` derived its projection
window as the flat ISO calendar week of ``today`` (``Mon .. Mon+6``) while only
the SP-start CAP was period-aware. Multi-week periods exist — the 2026 ASG
block (period 15, Jul 6–19) and 2-week playoff rounds — so every projection
for them was truncated to one week: the period-15 07-06 build projected
322/383 against finals of 552/581 (+230/+198 FP each side), documented in
``data/research/validation_runs/pwin_mean_bias_2026-07-30.md`` §5 ("the
dashboard's projection horizon is not using resolve_period_meta").

The fix routes the window through ``derive_projection_window()``, a pure seam
that delegates to the ONE shared resolver (``lib/period_meta
.resolve_period_meta``) exactly the way ``leverage_engine.build_state``
already did. These tests prove, on synthetic period metadata (no live ESPN):

  • a standard 1-week period yields its exact Mon–Sun span — byte-identical
    to the old derivation, so nothing observable changes on an ordinary week;
  • a 2-week playoff round yields the FULL 14-day span (the old code's +6
    would have truncated it);
  • the period-15-style explicit override window (Jul 6–19) is honored, even
    when ``today`` sits in the SECOND week of the block;
  • the window and the cap come from the same resolver dict, so they can
    never diverge again;
  • ``main()`` actually calls the seam — the flat ``+ timedelta(days=6)``
    window derivation is gone from the source (same source-pin style as
    tests/test_audit_regressions_0704.py).
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from build_matchup_dashboard import derive_projection_window  # noqa: E402


# ── synthetic league carrying only what the resolver reads (no ESPN creds) ────

class _FakeSettings:
    def __init__(self, matchup_periods):
        self.matchup_periods = matchup_periods


class _FakeLeague:
    def __init__(self, matchup_periods, current_period=None):
        self.settings = _FakeSettings(matchup_periods)
        self.currentMatchupPeriod = current_period


# ESPN's real mapping shape (mirrors tests/test_period_meta.py): the ASG block
# lists as a single scoring index despite its 2-week span (that's why period 15
# is an explicit override), playoff rounds span two scoring weeks.
_MP = {"8": [8], "15": [15], "17": [17], "21": [21],
       "22": [22, 23], "23": [24, 25]}

# The FULL real-season shape (every period 8..23 present) — required by the
# absolute-anchor walk, which sums calendar weeks from the ASG override (period
# 15 = Mon Jul 6) through every intervening period. With 16-21 single-week,
# period 22 truly spans Aug 31 – Sep 13 and period 23 spans Sep 14 – 27.
_MP_FULL = dict(_MP, **{"16": [16], "18": [18], "19": [19], "20": [20]})


# ── 1-week period: exact span, byte-identical to the old derivation ───────────

def test_single_week_period_yields_exact_mon_sun_span():
    """A plain 1-week period (the live period 17 as of 2026-07-30) resolves to
    the Mon–Sun week of `today` — precisely what the old flat-week code
    produced, so the fix is observable-identical on any ordinary week."""
    league = _FakeLeague(_MP, current_period=17)
    today = date(2026, 7, 30)                       # Thursday, period 17
    ws, we, days_rem, pmeta = derive_projection_window(league, 17, today)
    # the old derivation, verbatim:
    old_ws = today - timedelta(days=today.weekday())
    old_we = old_ws + timedelta(days=6)
    assert ws == old_ws == date(2026, 7, 27)
    assert we == old_we == date(2026, 8, 2)
    assert days_rem == (old_we - today).days == 3
    assert pmeta["sp_cap"] == 10 and pmeta["weeks"] == 1


# ── 2-week playoff round: the FULL 14-day span, not a truncated week ──────────

def test_two_week_playoff_round_yields_full_14_day_span():
    """A 2-week playoff round (period 22 → scoring weeks [22, 23]) projects
    its whole 14-day span. The old code would have stopped at Mon+6 — assert
    the window extends a full week past that truncation point."""
    league = _FakeLeague(_MP, current_period=22)
    today = date(2026, 9, 14)                       # Monday, round start
    ws, we, days_rem, pmeta = derive_projection_window(league, 22, today)
    assert ws == date(2026, 9, 14)
    assert (we - ws).days + 1 == 14
    assert we == ws + timedelta(days=13)
    # the defect this file exists to prevent: the flat-week window
    assert we != ws + timedelta(days=6)
    assert days_rem == 13
    # cap and window travel together (10×weeks rule)
    assert pmeta["sp_cap"] == 20 and pmeta["weeks"] == 2


# ── ASG-style override: the explicit Jul 6–19 window is honored ───────────────

def test_asg_override_window_is_honored():
    """Period 15 (ASG block) carries an explicit PERIOD_WINDOW_OVERRIDES span,
    Jul 6–19 — a 2-calendar-week block whose dead days make it cap 16, not 20.
    The projection window must be that real span, not the week of `today`."""
    league = _FakeLeague(_MP, current_period=15)
    today = date(2026, 7, 8)                        # Wednesday of week 1
    ws, we, days_rem, pmeta = derive_projection_window(league, 15, today)
    assert ws == date(2026, 7, 6)
    assert we == date(2026, 7, 19)
    assert days_rem == 11
    assert pmeta["sp_cap"] == 16                    # override beats 10×weeks


def test_asg_override_holds_in_second_week():
    """Mid-SECOND-week of the ASG block the old code re-anchored week_start to
    the current Monday (Jul 13) and kept a 7-day window — which also broke the
    week-to-date actuals load and the fallback banked-start count. The
    override span must hold from either week of the block."""
    league = _FakeLeague(_MP, current_period=15)
    today = date(2026, 7, 15)                       # Wednesday of week 2
    ws, we, days_rem, pmeta = derive_projection_window(league, 15, today)
    assert ws == date(2026, 7, 6)                   # NOT re-anchored to Jul 13
    assert we == date(2026, 7, 19)
    assert days_rem == 4


def test_stale_build_past_override_end_clamps_days_remaining_to_zero():
    """If ESPN hasn't rolled the period yet and a build runs after the
    override window closed, days_remaining is 0 (nothing left to project),
    never negative — and the window itself stays the period's true span, so
    no phantom next-week games are projected onto a finished period (the
    'stale post-period snapshots' defect in the same memo)."""
    league = _FakeLeague(_MP, current_period=15)
    today = date(2026, 7, 20)                       # Monday after the block
    ws, we, days_rem, _ = derive_projection_window(league, 15, today)
    assert (ws, we) == (date(2026, 7, 6), date(2026, 7, 19))
    assert days_rem == 0


# ── week 2 of a CLEAN 2-week round: the absolute-anchor walk (fix 2026-07-30) ─
# Found by the adversarial verifier of the window fix: for a 2-week playoff
# round with NO explicit override, the current period's start was guessed as
# the Monday of `today` — right in week 1, a week late in week 2 (and 7 days
# past the true period end). The fix walks calendar weeks from the season's
# absolute anchor (the ASG PERIOD_WINDOW_OVERRIDES entry, period 15 = Mon
# Jul 6) to derive the TRUE start, sanity-gated on the derived window
# containing `today`.

def test_clean_two_week_round_holds_its_window_in_week_two():
    """THE regression: today is the second Monday of playoff period 22
    (Aug 31 – Sep 13). The window must stay anchored at Aug 31 — the old code
    re-anchored to Sep 7 and projected phantom days through Sep 20."""
    league = _FakeLeague(_MP_FULL, current_period=22)
    today = date(2026, 9, 7)                        # Monday of week TWO
    ws, we, days_rem, pmeta = derive_projection_window(league, 22, today)
    assert ws == date(2026, 8, 31)                  # NOT re-anchored to Sep 7
    assert we == date(2026, 9, 13)                  # NOT extended to Sep 20
    assert days_rem == 6
    assert pmeta["sp_cap"] == 20 and pmeta["weeks"] == 2


def test_next_period_walk_composes_from_the_anchored_current_start():
    """Asking for period 23 while inside week 2 of period 22 must walk from
    the ANCHORED start (Aug 31), not the week-of-today guess: 23 spans
    Sep 14 – 27. Under the old guess the walk started a week late and put 23
    at Sep 21 – Oct 4."""
    league = _FakeLeague(_MP_FULL, current_period=22)
    today = date(2026, 9, 7)
    ws, we, _days_rem, pmeta = derive_projection_window(league, 23, today)
    assert (ws, we) == (date(2026, 9, 14), date(2026, 9, 27))
    assert pmeta["sp_cap"] == 20


def test_anchorless_multiweek_falls_back_to_week_one_and_warns(monkeypatch, capsys):
    """With no override anchor reachable (a season whose PERIOD_WINDOW_OVERRIDES
    is empty), the resolver degrades to the documented week-1 assumption — and
    says so out loud instead of silently re-anchoring."""
    # patch the SAME module instance the dashboard imported (scripts.xfp.lib…)
    from scripts.xfp.lib import period_meta
    monkeypatch.setattr(period_meta, "PERIOD_WINDOW_OVERRIDES", {})
    league = _FakeLeague(_MP_FULL, current_period=22)
    today = date(2026, 9, 7)
    ws, we, _days_rem, _pmeta = derive_projection_window(league, 22, today)
    assert ws == date(2026, 9, 7)                   # degraded: week-of-today
    assert we == date(2026, 9, 20)
    out = capsys.readouterr().out
    assert "period_meta" in out and "PERIOD_WINDOW_OVERRIDES" in out


# ── source pin: main() uses the seam, the flat-week derivation is gone ────────

def test_main_routes_window_through_the_seam():
    """Pin main() to the tested seam: the flat `week_end = week_start +
    timedelta(days=6)` derivation must not reappear, and the seam call must
    be present. (Source-text pin, same style as test_audit_regressions_0704.)"""
    src = (ROOT / "scripts" / "xfp" / "build_matchup_dashboard.py").read_text(
        encoding="utf-8")
    assert "derive_projection_window(mu['league_obj'], mu['period'], today)" in src
    # the old one-week window derivation must be gone from main()
    assert not re.search(
        r"week_end\s*=\s*week_start\s*\+\s*timedelta\(days=6\)", src), \
        "flat one-week window derivation is back in build_matchup_dashboard"
