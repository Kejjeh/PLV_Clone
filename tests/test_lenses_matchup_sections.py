"""Behavioral spec: a failed matchup.html section must never vanish silently.

Audit item T30 (backlog group "lenses", 2026-08-01), re-scoped to the verifier's
corrected claim.

The filed finding — "11 of 17 section builders lack the `_section_error` guard,
so one throwing section can blank the page" — has an exact count but the wrong
consequence. `matchup.html` is written only AFTER every section has been built,
and the publish-integrity guard raises on the `_section_error` marker before
that write, so an unguarded throw aborts the process and a guarded throw aborts
the build; neither publishes a partial page. Wrapping the eleven buys
diagnostics, not integrity, and is DEFERRED (see the audit record).

The real exposure is the opposite shape: the two builders that catch their own
exception and fall back to something the publish guard cannot see.

  * `render_trend_watch` returned `''` — the whole "Physical Trend Watch"
    section disappeared from the published page with one stderr line as the
    only trace.
  * `render_closer_tracker` shipped the degraded simple table with an inline
    note that does not read as degraded at a glance.

Fail-soft is DELIBERATE for both (they are display/context-only, CLAUDE.md #13,
and must not gate the nightly publish). So these tests pin visibility, not
abortion: the section must still render, and it must SAY it is unavailable or
degraded.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

bmd = importlib.import_module("build_matchup_dashboard")
trend_signal = importlib.import_module("scripts.xfp.lib.trend_signal")


def _boom(*a, **kw):
    raise RuntimeError("bat-tracking store unreadable")


def test_a_failed_trend_watch_still_renders_a_visible_unavailable_section(monkeypatch):
    """A broken Physical Trend Watch must announce itself on the page.

    `return ''` removed the section from the HTML entirely: the publish-integrity
    guard's regex cannot match a section that is not there, so a reader saw a
    page with no trend section and no reason given.
    """
    monkeypatch.setattr(trend_signal, "hitter_trend_table", _boom)

    html = bmd.render_trend_watch([])

    assert html.strip(), "a failed section must not vanish from the page"
    assert "Physical Trend Watch" in html, (
        "the section keeps its heading so a reader can see it is present-but-dead")
    assert "unavailable" in html.lower()
    assert "bat-tracking store unreadable" in html, (
        "the reason belongs on the page, not only in the build log")


def test_the_trend_watch_failure_does_not_gate_the_publish(monkeypatch):
    """Fail-soft is deliberate — a display lens may not abort the nightly build.

    The publish-integrity guard aborts on `<h2>…</h2><p class="muted">error:`.
    The unavailable notice must NOT match it: a bat-tracking hiccup gating the
    whole GitHub-Pages publish would be a behavior change, not a visibility one.
    """
    import re

    monkeypatch.setattr(trend_signal, "hitter_trend_table", _boom)
    html = bmd.render_trend_watch([])

    assert not re.findall(r'<h2>([^<]*)</h2>\s*<p class="muted">error:', html)


def _rp_ratings_repo(tmp_path: Path) -> Path:
    """Minimal repo root carrying the rp_ratings_master.csv the tracker reads."""
    research = tmp_path / "data" / "research"
    research.mkdir(parents=True)
    pd.DataFrame([dict(year=2026, player_name="Test Closer", gmli=1.8,
                       leverage_tier="ELITE")]).to_csv(
        research / "rp_ratings_master.csv", index=False)
    return tmp_path


def test_a_degraded_closer_tracker_says_it_is_degraded(tmp_path, monkeypatch):
    """The leverage-enrichment fallback ships a DIFFERENT table than advertised.

    It still renders (correctly fail-soft), but the note has to read as a
    degradation warning so nobody reads the simple table as the full
    leverage-tier tracker.
    """
    monkeypatch.setattr(bmd, "ROOT", _rp_ratings_repo(tmp_path))
    monkeypatch.setattr(bmd, "_load_closer_leaders_cache", _boom)
    monkeypatch.setattr(bmd, "_render_closer_tracker_simple",
                        lambda: "<h2>Closer Tracker</h2><table></table>")

    html = bmd.render_closer_tracker()

    assert "Closer Tracker" in html, "the fallback table still renders"
    assert "DEGRADED" in html.upper(), (
        "a reader must see that leverage tiers are missing from this table")
    assert "bat-tracking store unreadable" in html
