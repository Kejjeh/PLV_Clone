"""Settlement-gate contract for scripts/xfp/verdict_backtest.py.

WHY THIS EXISTS
---------------
Until 2026-07-30 the retro's settlement gate was a hardcoded literal:

    AS_OF = date(2026, 6, 9)   # "today" = data freshness cutoff

The caches advanced to split_day 125 (cutoff 2026-07-28/29) and the literal did
not. The gate therefore discarded 11 of 15 hitter split-days and 13 of 15 SP
split-days while the script printed n=1234 / n=263 as "the record". A third
defect hid alongside it: `main()` applied the gate to H and SP ONLY, so the
reliever number pooled all 15 splits including split_day 125 — a split whose
forward window contains zero games.

1210 tests passed through all three, because nothing tested the gate at all.
The missing test was the defect.

What is pinned here:
  * the cutoff is DERIVED, from the panel's own max(cutoff_date), not asserted
    by a literal -> a stale constant can no longer shrink the panel;
  * the cutoff is PER BUCKET, sourced from SETTLEMENT_WINDOWS (H 21d, SP/RP
    35d) -> one date can no longer stand in for three windows;
  * each bucket's anchor comes from ITS OWN panel's freshness;
  * a record whose window has NOT closed is EXCLUDED, at an inclusive boundary
    matching settler.settle_decision's `today >= snapshot + window_days`;
  * EVERY reported bucket is gated, RP included;
  * a missing / unparseable cutoff_date RAISES rather than being silently
    included or dropped (docs/rh3_harness_root_bug_2026-07-28.md class).

Every test below fails against the pre-2026-07-30 behaviour: the derived-anchor
and per-bucket tests because a single frozen 2026-06-09 literal cannot produce
these cutoffs, and the RP test because RP was never gated.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

VB = pytest.importorskip("verdict_backtest")

from plv_clone.decisions.settler import SETTLEMENT_WINDOWS  # noqa: E402


def _panel(cutoffs, start_split=30):
    """Minimal panel: one row per cutoff date, with a split_day column."""
    return pd.DataFrame({
        "split_day": [start_split + 7 * i for i in range(len(cutoffs))],
        "cutoff_date": [c.isoformat() for c in cutoffs],
    })


# --------------------------------------------------------------------------- #
# Derived, not literal.
# --------------------------------------------------------------------------- #
def test_anchor_is_derived_from_the_panel_not_a_frozen_literal():
    """Anchor tracks the data. A literal frozen at 2026-06-09 cannot do this.

    The panel below runs to 2026-09-01 — three months past LEGACY_AS_OF. Under
    the old gate every one of these rows was discarded (2026-06-09 minus 21d is
    2026-05-19, earlier than the OLDEST row here), so the retro would have
    reported n=0. Under the derived gate the anchor is the panel's own
    freshness and rows through 2026-08-11 settle.
    """
    fresh = date(2026, 9, 1)
    cutoffs = [fresh - timedelta(days=d) for d in (60, 40, 21, 10, 0)]
    panel = _panel(sorted(cutoffs))

    gated, asof, cutoff = VB.apply_settlement_gate(panel, "H")

    assert asof == fresh, "anchor must be max(cutoff_date) of the panel itself"
    assert cutoff == fresh - timedelta(days=21)
    kept = set(pd.to_datetime(gated["cutoff_date"]).dt.date)
    assert kept == {fresh - timedelta(days=d) for d in (60, 40, 21)}
    # and the old literal really would have emptied it
    stale, _, _ = VB.apply_settlement_gate(panel, "H", VB.LEGACY_AS_OF)
    assert stale.empty


def test_each_bucket_anchors_on_its_own_panel_freshness():
    """H and RP caches can be fresh to different dates; each uses its own."""
    h_panel = _panel([date(2026, 6, 1), date(2026, 7, 28)])
    rp_panel = _panel([date(2026, 6, 1), date(2026, 7, 29)])
    assert VB.data_asof(h_panel, "H") == date(2026, 7, 28)
    assert VB.data_asof(rp_panel, "RP") == date(2026, 7, 29)


# --------------------------------------------------------------------------- #
# Per bucket, sourced from SETTLEMENT_WINDOWS.
# --------------------------------------------------------------------------- #
def test_cutoff_is_per_bucket_and_reads_settlement_windows():
    asof = date(2026, 7, 28)
    for bucket, w in SETTLEMENT_WINDOWS.items():
        assert VB.settlement_cutoff(bucket, asof) == asof - timedelta(days=w["days"])
    # the three buckets do NOT share one cutoff — the shape a single date
    # cannot express
    h = VB.settlement_cutoff("H", asof)
    sp = VB.settlement_cutoff("SP", asof)
    assert h != sp and h > sp


def test_same_record_settles_for_H_but_not_for_SP():
    """A 25-day-old decision: closed under H's 21d window, open under SP's 35d.

    A single bucket-blind date must give both buckets the same answer, so this
    is unrepresentable in the old design.
    """
    asof = date(2026, 7, 28)
    panel = _panel([asof - timedelta(days=25)])
    h_gated, _, _ = VB.apply_settlement_gate(panel, "H", asof)
    sp_gated, _, _ = VB.apply_settlement_gate(panel, "SP", asof)
    assert len(h_gated) == 1, "21d window has closed on a 25-day-old decision"
    assert sp_gated.empty, "35d window has NOT closed on a 25-day-old decision"


def test_unknown_bucket_raises():
    with pytest.raises(KeyError, match="unknown settlement bucket"):
        VB.settlement_cutoff("OF", date(2026, 7, 28))


# --------------------------------------------------------------------------- #
# Open windows are excluded; the boundary matches the settler.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bucket", sorted(SETTLEMENT_WINDOWS))
def test_open_window_excluded_closed_window_kept(bucket):
    w = SETTLEMENT_WINDOWS[bucket]["days"]
    asof = date(2026, 7, 28)
    cutoffs = sorted({asof - timedelta(days=d)
                      for d in (w + 7, w + 1, w, w - 1, 1, 0)})
    gated, _, cutoff = VB.apply_settlement_gate(_panel(cutoffs), bucket, asof)
    kept = set(pd.to_datetime(gated["cutoff_date"]).dt.date)

    assert asof - timedelta(days=w) in kept, (
        "boundary is INCLUSIVE — settle_decision settles at exactly "
        "today == snapshot + window_days")
    for d in (w - 1, 1, 0):
        assert asof - timedelta(days=d) not in kept, (
            f"a decision {d}d old has an OPEN {w}d window and must not be graded")
    assert all(c <= cutoff for c in kept)


def test_zero_forward_data_split_is_excluded():
    """The freshest split (cutoff == data_asof) has no forward games at all.

    Measured on the live caches: split_day 125 carries ros_pa = NaN. It must
    never reach a reported statistic in any bucket.
    """
    asof = date(2026, 7, 28)
    panel = _panel([date(2026, 6, 20), asof])
    for bucket in SETTLEMENT_WINDOWS:
        gated, _, _ = VB.apply_settlement_gate(panel, bucket)
        kept = set(pd.to_datetime(gated["cutoff_date"]).dt.date)
        assert asof not in kept, f"{bucket}: graded a split with zero forward data"


# --------------------------------------------------------------------------- #
# EVERY reported bucket is gated — this is the RP defect.
# --------------------------------------------------------------------------- #
def test_gate_panels_gates_all_three_buckets_including_rp():
    """RP was silently ungated before 2026-07-30; this fails against that."""
    asof = date(2026, 7, 29)
    # one closed row (60d old, closed under every window) + one wide-open row
    panels = {b: _panel([asof - timedelta(days=60), asof])
              for b in ("H", "SP", "RP")}
    gated, report = VB.gate_panels(panels)

    for b in ("H", "SP", "RP"):
        assert report[b]["n_before"] == 2
        assert report[b]["n_after"] == 1, (
            f"{b}: the open-window row survived the gate — under the pre-"
            "2026-07-30 code this is exactly what RP did")
        assert report[b]["window_days"] == SETTLEMENT_WINDOWS[b]["days"]
        assert report[b]["asof"] == asof
        assert report[b]["split_days"] == [30]


def test_gate_panels_refuses_a_missing_reported_bucket():
    asof = date(2026, 7, 29)
    panels = {b: _panel([asof - timedelta(days=60)]) for b in ("H", "SP")}
    with pytest.raises(KeyError, match="RP"):
        VB.gate_panels(panels)


def test_gate_panels_honours_the_historical_override():
    """--as-of reproduces the old run rather than deriving from the panel."""
    panels = {b: _panel([date(2026, 4, 25), date(2026, 5, 2), date(2026, 5, 9),
                         date(2026, 7, 28)])
              for b in ("H", "SP", "RP")}
    _, report = VB.gate_panels(panels, VB.LEGACY_AS_OF)
    # 2026-06-09 minus 21d = 2026-05-19 -> all three May cutoffs settle
    assert report["H"]["n_after"] == 3
    # 2026-06-09 minus 35d = 2026-05-05 -> only 04-25 and 05-02 settle
    assert report["SP"]["n_after"] == 2
    assert report["H"]["asof"] == VB.LEGACY_AS_OF


# --------------------------------------------------------------------------- #
# Fail loud on a bad cutoff_date — never silently include or drop.
# --------------------------------------------------------------------------- #
def test_missing_cutoff_column_raises():
    df = pd.DataFrame({"split_day": [30, 37]})
    with pytest.raises(KeyError, match="cutoff_date"):
        VB.apply_settlement_gate(df, "H")


def test_unparseable_cutoff_date_raises():
    df = pd.DataFrame({"split_day": [30, 37],
                       "cutoff_date": ["2026-04-25", "not-a-date"]})
    with pytest.raises(ValueError, match="unparseable cutoff_date"):
        VB.apply_settlement_gate(df, "H")


def test_null_cutoff_date_raises():
    df = pd.DataFrame({"split_day": [30, 37],
                       "cutoff_date": ["2026-04-25", None]})
    with pytest.raises(ValueError, match="unparseable cutoff_date"):
        VB.apply_settlement_gate(df, "H")


def test_empty_panel_raises_rather_than_reporting_zero():
    df = pd.DataFrame({"split_day": [], "cutoff_date": []})
    with pytest.raises(ValueError, match="empty panel"):
        VB.apply_settlement_gate(df, "H")


# --------------------------------------------------------------------------- #
# No frozen anchor survives as a default.
# --------------------------------------------------------------------------- #
def test_module_exposes_no_default_as_of_constant():
    """`AS_OF` is gone. LEGACY_AS_OF exists only as an explicit override."""
    assert not hasattr(VB, "AS_OF"), (
        "a module-level AS_OF default is the bug: it goes stale silently and "
        "cannot express three per-bucket windows")
    assert VB.LEGACY_AS_OF == date(2026, 6, 9)
