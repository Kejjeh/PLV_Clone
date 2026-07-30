"""Smoke + lockstep tests for scripts/xfp/verdict_backtest.py.

WHY THIS EXISTS
---------------
`verdict_backtest.run_hitters()` and `run_pitchers()` were BOTH dead:

  * `run_pitchers()` raised `AttributeError: module
    'plv_clone.models.xfp.rp3' has no attribute '_signal'` from commit de9f6e6
    ("model vectorization"), which deleted the row-wise `_signal` helpers and
    inlined an `np.select` block into each pipeline's `main()`.
  * `run_hitters()` raised the same AttributeError, and before that would have
    raised `KeyError: ['bx_prior_h']` from the 2026-07-10 `bx_prior_h`
    promotion, which never updated this script's feature reconstruction.

931 tests passed through all of it, because the only thing that ever imported
this module (`validate_band_crps.py`) imported the panel BUILDERS and never
executed the hosts. The missing test was the defect. These tests EXECUTE both
hosts, so an AttributeError / KeyError / missing-feature regression fails here.

The lockstep tests are the second half of the fix: the backtest reimplements
production's vectorized add/hold/drop rule (production has no importable seam —
the rule lives inline in `main()`), so these tests replay the backtest's helper
over the shipped production projection CSVs and assert the emitted signal is
IDENTICAL to what the pipelines actually wrote. Drift in either direction fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_XFP = ROOT / "scripts" / "xfp"
if str(SCRIPTS_XFP) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_XFP))

VB = pytest.importorskip("verdict_backtest")

RH3_CSV = ROOT / "data" / "outputs" / "xfp_rh3_projections.csv"
RP3_CSV = ROOT / "data" / "outputs" / "xfp_rp3_projections.csv"

# Keep the smoke tests quick: the hosts loop over every 2026 split_day, and two
# splits exercise every code path (predict -> sigma -> band -> replacement ->
# signal -> row emit) that a full run does.
N_SMOKE_SPLITS = 2


def _first_splits(panel: pd.DataFrame, n: int = N_SMOKE_SPLITS) -> pd.DataFrame:
    """Subsample to the first n 2026 split_days (the hosts only read year==2026)."""
    d26 = panel[panel["year"] == 2026]
    keep = sorted(d26["split_day"].unique())[:n]
    assert keep, "no 2026 split_days in panel"
    return d26[d26["split_day"].isin(keep)].copy()


# --------------------------------------------------------------------------- #
# Host smoke tests — these EXECUTE the functions that were dead.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def hitter_panel():
    from plv_clone.models.xfp import rh3 as RH3
    if not Path(RH3.ROLLING_CSV).exists():
        pytest.skip(f"{RH3.ROLLING_CSV} not present in this checkout")
    return VB.build_hitter_panel()


@pytest.fixture(scope="module")
def pitcher_panel():
    from plv_clone.models.xfp import rp3 as RP3
    if not Path(RP3.ROLLING_CSV).exists():
        pytest.skip(f"{RP3.ROLLING_CSV} not present in this checkout")
    return VB.build_pitcher_panel()


def test_build_hitter_panel_has_all_model_features(hitter_panel):
    """Panel reconstruction must cover every production feature.

    This is the `bx_prior_h` rot (2026-07-10 promotion, never mirrored here):
    the host then died on `dropna(subset=feats)` with a KeyError.
    """
    from plv_clone.models.xfp import rh3 as RH3
    rolling, _ = hitter_panel
    missing = [f for f in RH3.RH3_FEATS if f not in rolling.columns]
    assert not missing, (
        f"build_hitter_panel() does not reconstruct {missing} — every feature in "
        "RH3_FEATS must be rebuilt here or run_hitters() dies on dropna(subset=feats)")


def test_build_pitcher_panel_has_all_model_features(pitcher_panel):
    from plv_clone.models.xfp import rp3 as RP3
    missing = [f for f in RP3.RP3_FEATS if f not in pitcher_panel.columns]
    assert not missing, (
        f"build_pitcher_panel() does not reconstruct {missing} — every feature in "
        "RP3_FEATS must be rebuilt here or run_pitchers() dies on dropna(subset=feats)")


def test_run_hitters_executes(hitter_panel):
    """Executes run_hitters(); fails on AttributeError/KeyError, not just import."""
    from plv_clone.models.xfp import rh3 as RH3
    if not Path(RH3.MODEL_PKL).exists():
        pytest.skip(f"{RH3.MODEL_PKL} not present in this checkout")
    rolling, multiyr = hitter_panel
    out = VB.run_hitters(_first_splits(rolling), multiyr)

    assert isinstance(out, pd.DataFrame) and not out.empty
    assert set(out.columns) >= {
        "bucket", "player", "split_day", "cutoff_date", "proj_per", "p25", "p75",
        "replacement", "signal", "realized_per", "n_events", "eligible"}
    assert (out["bucket"] == "H").all()
    assert out["split_day"].nunique() == N_SMOKE_SPLITS
    assert set(out["signal"].unique()) <= {"add", "hold", "drop"}
    assert out["proj_per"].notna().all()
    assert (out["p25"] <= out["proj_per"]).all() and (out["proj_per"] <= out["p75"]).all()


def test_run_pitchers_executes(pitcher_panel):
    """Executes run_pitchers(); this is the call site that raised AttributeError."""
    from plv_clone.models.xfp import rp3 as RP3
    if not Path(RP3.MODEL_PKL).exists():
        pytest.skip(f"{RP3.MODEL_PKL} not present in this checkout")
    out = VB.run_pitchers(_first_splits(pitcher_panel))

    assert isinstance(out, pd.DataFrame) and not out.empty
    assert set(out.columns) >= {
        "bucket", "player", "split_day", "cutoff_date", "proj_per", "p25", "p75",
        "replacement", "signal", "realized_per", "n_events", "eligible"}
    assert (out["bucket"] == "SP").all()
    assert out["split_day"].nunique() == N_SMOKE_SPLITS
    assert set(out["signal"].unique()) <= {"add", "hold", "drop", "il"}
    assert out["proj_per"].notna().all()


def test_run_pitchers_signal_is_not_inert(pitcher_panel):
    """The SP signal must stay LIVE (not 100% hold).

    Feeding the wide DISPLAY band (sigma x alpha_global ~= 2.41) to the add/drop
    rule instead of the raw-sigma DECISION band silently produces 100% 'hold'
    (found 2026-06-11, fixed in rp3 by 13bb4a1). It does not error — it just
    flattens every backtested verdict. This asserts the failure mode is absent.
    """
    from plv_clone.models.xfp import rp3 as RP3
    if not Path(RP3.MODEL_PKL).exists():
        pytest.skip(f"{RP3.MODEL_PKL} not present in this checkout")
    out = VB.run_pitchers(_first_splits(pitcher_panel))
    live = set(out["signal"].unique()) & {"add", "drop"}
    assert live == {"add", "drop"}, (
        f"SP add/drop signal is inert (observed signals: "
        f"{sorted(out['signal'].unique())}) — the decision band was probably "
        "replaced by the wide display band")


def test_run_relievers_executes():
    from plv_clone.models.xfp import rprs2 as RPRS2
    if not (Path(RPRS2.ROLLING_CSV).exists() and Path(RPRS2.MODEL_PKL).exists()):
        pytest.skip("rprs2 cache/model not present in this checkout")
    panel = VB.build_reliever_panel()
    out = VB.run_relievers(_first_splits(panel))
    assert isinstance(out, pd.DataFrame) and not out.empty
    assert (out["bucket"] == "RP").all()
    assert set(out["signal"].unique()) <= {"add", "hold", "drop"}


# --------------------------------------------------------------------------- #
# Lockstep: the backtest's signal must equal what production actually wrote.
# --------------------------------------------------------------------------- #
def test_hitter_signal_matches_production():
    """Replay hitter_signal_vec over the shipped rh3 CSV; must match `signal`."""
    if not RH3_CSV.exists():
        pytest.skip(f"{RH3_CSV} not present in this checkout")
    df = pd.read_csv(RH3_CSV)
    got = VB.hitter_signal_vec(df)
    mism = df.loc[got != df["signal"].values,
                  ["player_name", "xfp_rh3_p25", "xfp_rh3_p75",
                   "replacement_xfp_per_pa", "signal"]]
    assert mism.empty, (
        f"hitter_signal_vec has DRIFTED from rh3.main()'s np.select on "
        f"{len(mism)}/{len(df)} production rows:\n{mism.head(10).to_string()}")
    # guard against a vacuous pass
    assert set(df["signal"].unique()) >= {"add", "hold", "drop"}


def test_pitcher_signal_matches_production():
    """Replay pitcher_signal_vec over the shipped rp3 CSV; must match `signal`."""
    if not RP3_CSV.exists():
        pytest.skip(f"{RP3_CSV} not present in this checkout")
    df = pd.read_csv(RP3_CSV)
    got = VB.pitcher_signal_vec(df)
    mism = df.loc[got != df["signal"].values,
                  ["player_name", "xfp_rp3_decision_p25", "xfp_rp3_decision_p75",
                   "replacement_xfp_per_start", "is_on_il_at_split", "signal"]]
    assert mism.empty, (
        f"pitcher_signal_vec has DRIFTED from rp3.main()'s np.select on "
        f"{len(mism)}/{len(df)} production rows:\n{mism.head(10).to_string()}")
    assert set(df["signal"].unique()) >= {"add", "hold", "drop"}


def test_pitcher_signal_reads_decision_band_not_display_band():
    """Synthetic proof that the DECISION band drives add/drop.

    Row A: decision band clears replacement (add) while the display band does
    not. Row B: decision band is entirely below replacement (drop) while the
    display band straddles it. If someone swaps the bands, this flips to hold.
    """
    df = pd.DataFrame({
        "is_on_il_at_split": [0, 0],
        "replacement_delta": [1.0, -1.0],
        "replacement_xfp_per_start": [10.0, 10.0],
        # narrow, raw-sigma decision band
        "xfp_rp3_decision_p25": [10.5, 7.0],
        "xfp_rp3_decision_p75": [11.5, 9.0],
        # wide display band (sigma x ~2.41) — would yield 'hold' for both
        "xfp_rp3_p25": [7.0, 4.0],
        "xfp_rp3_p75": [15.0, 12.0],
    })
    assert list(VB.pitcher_signal_vec(df)) == ["add", "drop"]


def test_pitcher_signal_il_takes_precedence():
    df = pd.DataFrame({
        "is_on_il_at_split": [1, np.nan],
        "replacement_delta": [5.0, 5.0],
        "replacement_xfp_per_start": [10.0, 10.0],
        "xfp_rp3_decision_p25": [14.0, 14.0],
        "xfp_rp3_decision_p75": [16.0, 16.0],
    })
    assert list(VB.pitcher_signal_vec(df)) == ["il", "il"]


def test_hitter_signal_nan_band_holds():
    """NaN band / NaN replacement must fall through to 'hold', as production does."""
    df = pd.DataFrame({
        "replacement_delta": [np.nan, 0.05, 0.05],
        "replacement_xfp_per_pa": [0.50, np.nan, 0.50],
        "xfp_rh3_p25": [0.60, 0.60, np.nan],
        "xfp_rh3_p75": [0.70, 0.70, np.nan],
    })
    assert list(VB.hitter_signal_vec(df)) == ["hold", "hold", "hold"]


# --------------------------------------------------------------------------- #
# Fail-loud contract: a missing input must RAISE, never default to 'hold'.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("drop_col", VB.H_SIGNAL_COLS)
def test_hitter_signal_missing_input_raises(drop_col):
    df = pd.DataFrame({c: [0.5] for c in VB.H_SIGNAL_COLS}).drop(columns=[drop_col])
    with pytest.raises(KeyError, match=drop_col):
        VB.hitter_signal_vec(df)


@pytest.mark.parametrize("drop_col", VB.SP_SIGNAL_COLS)
def test_pitcher_signal_missing_input_raises(drop_col):
    df = pd.DataFrame({c: [1.0] for c in VB.SP_SIGNAL_COLS}).drop(columns=[drop_col])
    with pytest.raises(KeyError, match=drop_col):
        VB.pitcher_signal_vec(df)


def test_build_hitter_panel_raises_on_missing_bx_cache(monkeypatch):
    """The bx_prior_h cache is REQUIRED — a silent 0.0 fill would be the
    2026-07-28 ROOT-bug pattern (confident numbers from a defaulted feature)."""
    from plv_clone.models.xfp import rh3 as RH3
    if not Path(RH3.ROLLING_CSV).exists():
        pytest.skip("rolling hitter cache not present in this checkout")
    monkeypatch.setattr(RH3, "BX_PRIORS_CSV", ROOT / "data" / "_no_such_bx_cache.csv")
    # 2026-07-30: the message comes from frames.require_cache now (the inline
    # else-raise was replaced by the shared fail-fast check); pin the FEATURE
    # name, which both wordings carry and which is the part a fixer needs.
    with pytest.raises(FileNotFoundError, match="bx_prior_h"):
        VB.build_hitter_panel()
