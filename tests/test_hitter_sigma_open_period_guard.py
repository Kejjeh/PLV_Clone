"""Guard test for validate_hitter_sigma_scale._load_live_history (2026-07-30).

The §7b re-score on repaired labels added an OPEN-PERIOD GUARD: a non-null
``actual_*_final`` is not necessarily a final — the pre-fix labeller wrote
running single-day partials, and ``fetch_closed_matchup_actuals --repair`` can
only rewrite periods ESPN has DECIDED, so a still-open period keeps its garbage
until the nightly closes it (canonical: period 17 on 2026-07-30). The guard's
signature: a decided period's labels are ONE constant pair across its live
snapshots; per-snapshot-VARYING "finals" are partials by construction.

The adversarial verifier of that track noted no test exercised the guard —
reverting it would silently re-pool open-period partials into the calibration
panel. This file closes that hole with a synthetic history store.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))


def _history_fixture() -> pd.DataFrame:
    """Two closed periods (constant labels) + one open period whose labels VARY
    across snapshot dates (running partials) + synthetic backfill noise."""
    rows = []
    # closed periods 12-13: same final on every snapshot
    for period, (my, opp) in ((12, (294.6, 385.0)), (13, (322.1, 331.3))):
        for day in (1, 2):
            rows.append(dict(
                date=f"2026-07-{20 + day:02d}", period=period,
                model_version="baseline", win_probability=0.4,
                my_projected_total=330.0, opp_projected_total=340.0,
                my_wtd=100.0, opp_wtd=110.0,
                actual_my_final=my, actual_opp_final=opp))
    # OPEN period 17: labels vary by snapshot — running partials, not finals
    for day, (my, opp) in ((28, (3.3, 23.3)), (29, (81.1, 68.5))):
        rows.append(dict(
            date=f"2026-07-{day}", period=17,
            model_version="baseline", win_probability=0.38,
            my_projected_total=320.0, opp_projected_total=330.0,
            my_wtd=50.0, opp_wtd=60.0,
            actual_my_final=my, actual_opp_final=opp))
    # synthetic backfill row — excluded by model_version, never by the guard
    rows.append(dict(
        date="2026-07-01", period=12,
        model_version="backfill_2025_bayes_shrink", win_probability=0.31,
        my_projected_total=400.0, opp_projected_total=410.0,
        my_wtd=0.0, opp_wtd=0.0,
        actual_my_final=411.0, actual_opp_final=388.0))
    return pd.DataFrame(rows)


def test_open_period_guard_drops_varying_label_periods(tmp_path, monkeypatch, capsys):
    import validate_hitter_sigma_scale as VHS

    hist = tmp_path / "predictions_history.csv"
    _history_fixture().to_csv(hist, index=False)
    monkeypatch.setattr(VHS, "HISTORY", hist)

    df = VHS._load_live_history()

    # the open period (varying labels) is gone; the closed ones survive
    assert sorted(df["period"].unique()) == [12, 13]
    assert 17 not in set(df["period"])
    # and it was excluded LOUDLY, naming the period
    out = capsys.readouterr().out
    assert "open-period guard" in out and "[17]" in out
    # synthetic backfill rows never reach the panel either
    assert not df.get("mv", pd.Series(dtype=str)).astype(str).str.startswith(
        "backfill_").any()


def test_guard_keeps_constant_label_periods_intact(tmp_path, monkeypatch):
    """A decided period — ONE constant label pair across snapshots — must pass
    the guard untouched (the guard's premise, inverted)."""
    import validate_hitter_sigma_scale as VHS

    fx = _history_fixture()
    fx = fx[fx["period"] != 17]                      # only closed periods
    hist = tmp_path / "predictions_history.csv"
    fx.to_csv(hist, index=False)
    monkeypatch.setattr(VHS, "HISTORY", hist)

    df = VHS._load_live_history()
    assert sorted(df["period"].unique()) == [12, 13]
    # one row per (period, mv) after the first-snapshot dedup
    assert len(df) == 2


def test_removing_the_guard_would_ingest_the_partials(tmp_path, monkeypatch):
    """Non-vacuousness: with the guard's filter simulated away (the pre-guard
    data flow — live rows + notna only), period 17's partials DO land in the
    panel. If this ever starts failing while the guard tests pass, the fixture
    no longer represents the hazard and both need re-checking."""
    fx = _history_fixture()
    live = fx[fx["model_version"].isin(("baseline", "MA_v1"))]
    labelled = live[live["actual_my_final"].notna()
                    & live["actual_opp_final"].notna()]
    assert 17 in set(labelled["period"])             # the hazard is real
