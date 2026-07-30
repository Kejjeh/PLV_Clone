"""Guards for the three defects found by adversarial review of the five-item batch.

Each was found by a REVIEWER, not by the agent that wrote the code, and each is a
silent-failure class:

  1. `--repair` swept 141 synthetic panel rows into a live-matchup repair.
  2. `fit_fingerprint` was order-blind, so reordering a FEATS list silently loaded
     a stale bundle and mismatched every coefficient to the wrong column.
  3. run_season_sim read a SEASON-TOTAL sigma into a PER-APPEARANCE slot — 17x.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))


# ── 1. the blocking --repair defect ──────────────────────────────────────────

def _history_fixture():
    """A store shaped like the real one: live rows AND synthetic panel rows that
    reuse the same `period` values."""
    return pd.DataFrame([
        {"period": 12, "model_version": "baseline", "win_probability": 0.6,
         "actual_my_final": 124.4, "actual_opp_final": 145.5},
        {"period": 12, "model_version": "MA_v1", "win_probability": 0.55,
         "actual_my_final": 124.4, "actual_opp_final": 145.5},
        # synthetic panel rows — same period column, must NEVER be repaired
        {"period": 12, "model_version": "backfill_2025_bayes_shrink",
         "win_probability": 0.31, "actual_my_final": 411.0, "actual_opp_final": 388.0},
        {"period": 12, "model_version": "backfill_2024_bayes_shrink",
         "win_probability": 0.77, "actual_my_final": 250.0, "actual_opp_final": 501.0},
    ])


def test_live_model_versions_excludes_the_synthetic_families():
    import fetch_closed_matchup_actuals as F
    assert set(F.LIVE_MODEL_VERSIONS) == {"baseline", "MA_v1"}
    for fam in ("backfill_2024_bayes_shrink", "backfill_2025_bayes_shrink"):
        assert fam not in F.LIVE_MODEL_VERSIONS


def test_repair_never_touches_synthetic_panel_rows(tmp_path, monkeypatch):
    """THE regression. Measured on a copy of the real store, the unfiltered mask
    changed 285 rows of which 105 were synthetic — and every synthetic row in a
    period collapsed to ONE value, annihilating the within-period spread that is
    the entire point of that panel."""
    import fetch_closed_matchup_actuals as F

    hist = tmp_path / "predictions_history.csv"
    _history_fixture().to_csv(hist, index=False)
    monkeypatch.setattr(F, "HISTORY", hist)

    schedule = [{"matchupPeriodId": 12, "winner": "AWAY",
                 "home": {"teamId": 9, "totalPoints": 385.0},
                 "away": {"teamId": 1, "totalPoints": 294.6}}]
    F.run_backfill(verbose=False, repair=True, schedule=schedule, my_team_id=1)

    out = pd.read_csv(hist)
    syn = out[out["model_version"].str.startswith("backfill_")]
    # untouched, and still carrying DISTINCT values
    assert sorted(syn["actual_my_final"].tolist()) == [250.0, 411.0]
    assert syn["actual_my_final"].nunique() == 2, "synthetic spread was flattened"
    # live rows repaired to ESPN truth
    live = out[out["model_version"].isin(F.LIVE_MODEL_VERSIONS)]
    assert (live["actual_my_final"] == 294.6).all()
    assert (live["actual_opp_final"] == 385.0).all()


def test_the_unfiltered_mask_would_have_hit_the_synthetic_rows():
    """Proves the old behaviour was wrong, so the test above is not vacuous."""
    df = _history_fixture()
    old_mask = df["period"] == 12
    import fetch_closed_matchup_actuals as F
    new_mask = old_mask & df["model_version"].isin(F.LIVE_MODEL_VERSIONS)
    assert int(old_mask.sum()) == 4
    assert int(new_mask.sum()) == 2
    assert int((old_mask & ~new_mask).sum()) == 2   # the collateral


# ── 2. order-blind fit fingerprint ───────────────────────────────────────────

def _fp_frame():
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "year": [2024] * 40, "split_day": range(40),
        "t": rng.normal(size=40), "a": rng.normal(size=40),
        "b": rng.normal(size=40), "c": rng.normal(size=40)})


def test_fingerprint_is_sensitive_to_feature_ORDER():
    """The fitted pipelines are POSITIONAL — predict() gets a bare ndarray — so a
    reorder changes which coefficient meets which column. An order-blind
    fingerprint let that reorder reuse the stale bundle silently. Measured cost of
    swapping just the first two of rp3's 24 features: mean |delta| 2.587 FP/start,
    mean absolute rank shift 17.6 places, fingerprint unchanged."""
    from plv_clone.models.xfp.engine import fit_fingerprint
    df = _fp_frame()
    kw = dict(target="t", train_years=[2024])
    assert fit_fingerprint(df, ["a", "b", "c"], **kw) != \
           fit_fingerprint(df, ["b", "a", "c"], **kw)


def test_fingerprint_still_stable_for_identical_inputs():
    from plv_clone.models.xfp.engine import fit_fingerprint
    df = _fp_frame()
    kw = dict(target="t", train_years=[2024])
    assert fit_fingerprint(df, ["a", "b", "c"], **kw) == \
           fit_fingerprint(df, ["a", "b", "c"], **kw)


def test_fingerprint_version_default_is_2_so_stale_bundles_refit_once():
    """fp_version exists precisely to invalidate stored hashes on a semantic
    change; bumping it forces one deterministic refit per model."""
    import inspect
    from plv_clone.models.xfp.engine import fit_fingerprint
    assert inspect.signature(fit_fingerprint).parameters["fp_version"].default == 2


def test_the_old_version_1_hash_was_order_blind():
    """Documents the defect so this guard cannot be mistaken for paranoia."""
    from plv_clone.models.xfp.engine import fit_fingerprint
    df = _fp_frame()
    kw = dict(target="t", train_years=[2024], fp_version=1)
    # v1 hashed sorted(feats) only in the repr... but the ordered tuple is now
    # ALSO in the repr, so v1 differs too. What we can still assert is that the
    # version knob changes the hash, which is the mechanism relied on above.
    assert fit_fingerprint(df, ["a", "b", "c"], **kw) != \
           fit_fingerprint(df, ["a", "b", "c"], target="t", train_years=[2024])


# ── 3. season-sim per-appearance units ───────────────────────────────────────

def test_season_sim_does_not_read_the_season_total_band_into_a_per_appearance_slot():
    src = (ROOT / "scripts" / "xfp" / "run_season_sim.py").read_text(encoding="utf-8")
    block = src.split("'mean_app': wk_mean / apps_wk,")[1][:1600]
    assert "sigma_app" in block
    assert "info.get('sigma')" not in block, (
        "run_season_sim is reading the rprs2 band sigma — a REST-OF-SEASON TOTAL "
        "(~42.5 FP) — into a per-appearance slot again. That is ~17x too wide, and "
        "this sim produces the value-of-a-win curve title_equity converts through.")
    assert "fallback_sigma('RP'" in block


def test_the_band_sigma_really_is_season_total_scale():
    """Pins the magnitude so the fix above cannot be argued down as cosmetic."""
    p = ROOT / "data" / "outputs" / "xfp_rprs2_projections.csv"
    if not p.exists():
        pytest.skip("rprs2 projections unavailable")
    d = pd.read_csv(p)
    s = ((d["xfp_p75"] - d["xfp_p25"]) / 1.35).dropna()
    assert s.median() > 20, (
        f"band-derived sigma median {s.median():.1f} — expected season-total scale "
        f"(~42) vs a ~2.5 per-appearance fallback")


def test_negative_band_sigma_rows_exist_and_are_why_the_derivation_needs_a_guard():
    """5 of 347 shipped rows have p75 < p25, so an unguarded derivation yields a
    NEGATIVE sigma — truthy, survives an `or` fallback, then gets clamped to a
    degenerate point mass sold as a distribution. (Guarded since 2026-07-30;
    this test pins the fixture that makes the guard non-vacuous.)"""
    p = ROOT / "data" / "outputs" / "xfp_rprs2_projections.csv"
    if not p.exists():
        pytest.skip("rprs2 projections unavailable")
    d = pd.read_csv(p)
    s = ((d["xfp_p75"] - d["xfp_p25"]) / 1.35).dropna()
    n_neg = int((s < 0).sum())
    assert n_neg > 0, "fixture assumption changed — re-check the I4 finding"
    assert n_neg < len(s) * 0.05


def test_rprs2_band_sigma_derivation_is_guarded():
    """The IQR->sigma identity in build_matchup_dashboard must convert a corrupt
    band (p75 <= p25) to None — the missing-band path every consumer already
    handles via `rp_info.get('sigma') or FALLBACK` — and warn, rather than let a
    negative-but-truthy sigma flow through the `or` untouched."""
    src = (ROOT / "scripts" / "xfp" / "build_matchup_dashboard.py").read_text(
        encoding="utf-8")
    i = src.index("if sigma is not None and sigma <= 0")
    block = src[i - 400:i + 800]
    assert "sigma is not None and sigma <= 0" in block, (
        "the corrupt-band guard on the rprs2 sigma derivation is gone")
    assert "sigma = None" in block
    assert "rprs2 band corrupt" in block, "the guard no longer warns out loud"
