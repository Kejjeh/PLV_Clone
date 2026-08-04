"""window_split — pin the discipline that made the 2026-08-03 Teo read work.

The read that motivated this module: "3 HR in 5 games, is he waking up?" The
honest answer needed three things that prose checklists reliably lose —

  1. every metric gated against its OWN empirical minimum, so a 19-PA HR
     streak is reported as unknowable rather than as weak evidence;
  2. under-sampled metrics listed EXPLICITLY, because silently dropping them
     reads as "we looked and there was nothing there";
  3. a league-relative baseline, because Teo's raw bat speed looked flat
     (71.4 -> 70.5) while his edge over the league collapsed (+1.71 -> +0.33).

Each of those is a test below.
"""
import math

import pytest

WS = pytest.importorskip("scripts.xfp.lib.window_split")


# ── gating: the after-window must clear its own minimum ──────────────────────

def test_undersized_after_window_is_not_readable_and_carries_no_delta():
    """Teo's post-ASG chase: 113 out-of-zone pitches against a 150 minimum.

    38.9% vs a 26.4% baseline LOOKS like a collapse in plate discipline. At
    113 OOZ it is not knowable, and the module must refuse to hand back a
    delta a caller could accidentally render.
    """
    r = WS.split_read("chase", "H", before=26.4, before_denom=546,
                      after=38.9, after_denom=113)
    assert r.level_readable is False
    assert r.delta_readable is False
    assert r.delta is None
    assert r.minimum == 150 and r.unit == "ooz_pitches"


def test_both_windows_clearing_makes_the_delta_readable():
    """SwStr%: 1028 pitches before, 213 after, both past the 150 gate."""
    r = WS.split_read("swstr", "H", before=14.2, before_denom=1028,
                      after=15.5, after_denom=213)
    assert r.level_readable is True
    assert r.delta_readable is True
    assert r.delta == pytest.approx(1.3)


def test_after_clears_but_before_does_not_gives_a_level_without_a_delta():
    """A level and a change are different claims with different requirements.

    A player back from the IL can have a readable CURRENT window and no
    comparable baseline; saying "he is at 24% now" is honest, saying "he is
    up 6 points" is not.
    """
    r = WS.split_read("k_pct", "H", before=27.9, before_denom=30,
                      after=19.0, after_denom=58)
    assert r.level_readable is True
    assert r.delta_readable is False
    assert r.delta is None


def test_k_pct_at_58_pa_clears_because_the_minimum_is_50():
    """The one Teo metric that WAS readable post-ASG. If this ever silently
    starts failing, the module has drifted off plv_clone.stabilization."""
    r = WS.split_read("k_pct", "H", before=27.9, before_denom=251,
                      after=19.0, after_denom=58)
    assert r.delta_readable is True
    assert r.delta == pytest.approx(-8.9)


# ── never-stabilizes metrics must degrade, not explode ───────────────────────

def test_a_never_stabilizing_metric_is_flagged_rather_than_raising():
    """Pitcher hard-hit-against never stabilizes in-window. A board asking for
    it has a design bug, but it must surface as a labelled row — one bad
    column cannot take down the whole card."""
    r = WS.split_read("hard_hit", "SP", before=38.0, before_denom=400,
                      after=31.0, after_denom=300)
    assert r.never_stabilizes is True
    assert r.level_readable is False and r.delta_readable is False
    assert "never" in r.note.lower()


def test_an_unregistered_metric_raises_rather_than_inventing_a_gate():
    """A hand-picked threshold is the exact failure this repo keeps having."""
    with pytest.raises(WS.UnknownMetric):
        WS.split_read("vibes", "H", before=1, before_denom=999,
                      after=2, after_denom=999)


# ── league-relative: the bat-speed lesson ────────────────────────────────────

def test_league_drift_is_removed_from_the_delta():
    """Teo 2024 -> 2026: raw bat speed -0.92mph looks like mild aging.

    The league gained +0.46 over the same span, so his EDGE fell 1.71 -> 0.33
    and the true relative move is -1.38 — three times the raw read. A lens
    that compares raw mph across seasons systematically under-reports decline
    in a rising-baseline league (this is live today in lib/trend_signal.py).
    """
    r = WS.split_read("bat_speed", "H", before=71.39, before_denom=1222,
                      after=70.47, after_denom=557,
                      league_before=69.68, league_after=70.14)
    assert r.delta == pytest.approx(-0.92, abs=1e-9)
    assert r.rel_before == pytest.approx(1.71, abs=1e-9)
    assert r.rel_after == pytest.approx(0.33, abs=1e-9)
    assert r.rel_delta == pytest.approx(-1.38, abs=1e-9)


def test_relative_fields_are_none_without_a_league_baseline():
    r = WS.split_read("bat_speed", "H", before=71.0, before_denom=800,
                      after=70.5, after_denom=500)
    assert r.rel_delta is None and r.rel_after is None


def test_rel_delta_can_invert_the_sign_of_the_raw_delta():
    """The whole point: a metric can rise in absolute terms and still be a
    decline relative to the field."""
    r = WS.split_read("bat_speed", "H", before=70.0, before_denom=800,
                      after=70.2, after_denom=500,
                      league_before=69.0, league_after=70.1)
    assert r.delta > 0
    assert r.rel_delta < 0


# ── summary: only readable metrics may vote ──────────────────────────────────

def _reads():
    return [
        WS.split_read("k_pct", "H", 27.9, 251, 19.0, 58),          # better, readable
        WS.split_read("hard_hit", "H", 26.4, 295, 17.6, 74),       # worse, readable
        WS.split_read("swstr", "H", 14.2, 1028, 15.5, 213),        # worse, readable
        WS.split_read("chase", "H", 26.4, 546, 38.9, 113),         # unreadable
        WS.split_read("bb_pct", "H", 9.6, 251, 5.2, 58),           # unreadable
    ]


def test_summary_counts_only_readable_metrics():
    s = WS.summarize(_reads())
    assert {r.metric for r in s.improved} == {"k_pct"}
    assert {r.metric for r in s.worsened} == {"hard_hit", "swstr"}
    assert {r.metric for r in s.unreadable} == {"chase", "bb_pct"}


def test_unreadable_metrics_are_never_silently_dropped():
    """Silence reads as absence of evidence. The Diaz closer-watch bug in
    another module was the same mistake; it must not recur here."""
    s = WS.summarize(_reads())
    named = ({r.metric for r in s.improved} | {r.metric for r in s.worsened}
             | {r.metric for r in s.unreadable})
    assert named == {"k_pct", "hard_hit", "swstr", "chase", "bb_pct"}


def test_direction_is_polarity_aware():
    """Lower is better for K% and whiff; higher is better for hard-hit. A
    naive sign test would call Teo's K-rate drop a regression."""
    better = WS.split_read("k_pct", "H", 27.9, 251, 19.0, 58)
    worse = WS.split_read("hard_hit", "H", 26.4, 295, 17.6, 74)
    assert better.direction == "better"
    assert worse.direction == "worse"


def test_summary_verdict_reflects_the_readable_balance_not_the_headline():
    """Teo's case: results up 41%, but 1 readable metric better and 2 worse."""
    s = WS.summarize(_reads())
    assert s.net_readable == -1
    assert "worse" in s.headline.lower() or "mixed" in s.headline.lower()


# ── BrownU translation ───────────────────────────────────────────────────────

def test_k_rate_delta_converts_to_fp_per_pa_at_one_point_per_strikeout():
    """BrownU subtracts exactly 1 FP per K, so a K%-point is 0.01 fp/PA. This
    is what let the Teo read answer 'does the improvement close the gap?'
    (26.2 -> 19.0 = +0.072 fp/PA against a 0.169 deficit = 43%)."""
    assert WS.fp_per_pa_from_k_delta(26.2, 19.0) == pytest.approx(0.072)
    assert WS.fp_per_pa_from_k_delta(19.0, 26.2) == pytest.approx(-0.072)


def test_closes_fraction_of_gap_is_reported_not_rounded_to_a_verdict():
    assert WS.closes_gap_fraction(0.072, 0.169) == pytest.approx(0.426, abs=1e-3)
    assert math.isnan(WS.closes_gap_fraction(0.072, 0.0))
