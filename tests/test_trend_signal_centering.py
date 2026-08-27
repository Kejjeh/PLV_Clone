"""The physical-trend z-scores must be centred on the pool, not just scaled.

`hitter_trend_table` scored each axis as `d / d.std()` with no mean removed.
For RANKING that is harmless — subtracting a constant cannot reorder anything,
and the regression test below pins that it still doesn't. But `trend_tag`
compares the composite to the ABSOLUTE cutoffs +/-1.0 sigma, and there a
league-wide drift walks the whole pool across the boundary.

Measured on the live 2026-vs-2025 table (365 hitters, 2026-08-03): every axis
drifted upward — bat speed +0.207 sigma, fast-swing +0.185, attack-angle
+0.112 — for a +0.168 sigma constant offset on z_comp. That mislabelled
**33 of 365 players (9.0%)**: 20 phantom "breakout watch" and 13 missed
"decline watch".

The question a physical-trend lens is asked is "is this player's tool
improving relative to the field", not "did his number go up in a year when
everyone's did". Canonical case: Teoscar Hernandez read as `stable` on a raw
-0.5mph while the league gained, and his edge over the field was falling three
times faster than the raw delta showed.

Rule 13 throughout: display only, and centring cannot move a rank.
"""
import numpy as np
import pandas as pd
import pytest

TS = pytest.importorskip("scripts.xfp.lib.trend_signal")


def _pool(drift=0.0, n=200, seed=7):
    """A synthetic pool whose true spread is fixed and whose DRIFT is a knob."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "d_bat_speed": rng.normal(drift, 1.0, n),
        "d_fast_swing": rng.normal(drift * 0.05, 0.05, n),
        "aa_toward": rng.normal(drift, 1.5, n),
    })


def _z(df):
    out = df.copy()
    for col, z in (("d_bat_speed", "z_bs"), ("d_fast_swing", "z_fast"),
                   ("aa_toward", "z_aa")):
        out[z] = TS._centered_z(out[col])
    out["z_comp"] = out[["z_bs", "z_fast", "z_aa"]].mean(axis=1)
    return out


def test_centered_z_has_zero_mean_and_unit_scale():
    z = TS._centered_z(pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert z.std() == pytest.approx(1.0, abs=1e-12)


def test_a_league_wide_drift_does_not_manufacture_breakouts():
    """The whole pool gaining a mph is not 200 breakouts. Without centring the
    composite shifts bodily and the +1.0 cutoff sweeps up players who merely
    kept pace."""
    flat = _z(_pool(drift=0.0))
    drifted = _z(_pool(drift=1.0))
    n_flat = int((flat["z_comp"] >= 1.0).sum())
    n_drift = int((drifted["z_comp"] >= 1.0).sum())
    assert abs(n_drift - n_flat) <= 3, (
        f"drift changed the breakout count {n_flat} -> {n_drift}; the tag must "
        f"measure position in the field, not the field's own movement")


def test_centering_never_reorders_the_pool():
    """The safety property that makes this a calibration fix rather than a
    signal change: any prior validation that ranked on z is untouched.
    Verified live at Spearman 1.000 on the 2026 table."""
    raw = _pool(drift=0.4)
    uncentered = raw["d_bat_speed"] / raw["d_bat_speed"].std()
    centered = TS._centered_z(raw["d_bat_speed"])
    assert centered.corr(uncentered, method="spearman") == pytest.approx(1.0)


def test_a_player_who_merely_keeps_pace_reads_as_stable():
    """The Teoscar case in miniature: match the league's gain exactly and the
    honest tag is 'stable', not 'breakout'."""
    pool = _pool(drift=1.0)
    pool.loc[0, "d_bat_speed"] = 1.0          # exactly the league's gain
    pool.loc[0, "d_fast_swing"] = 0.05
    pool.loc[0, "aa_toward"] = 1.0
    z = _z(pool)
    assert abs(z.loc[0, "z_comp"]) < 1.0, (
        f"keeping pace scored {z.loc[0, 'z_comp']:+.2f} sigma — a player who "
        f"moved exactly with the field must not trip an absolute cutoff")


def test_a_real_decline_still_trips_the_cutoff_under_drift():
    """Centring must not blunt the detector — losing ground while the field
    gains should read MORE negative, not less."""
    pool = _pool(drift=1.0)
    pool.loc[0, "d_bat_speed"] = -1.5
    pool.loc[0, "d_fast_swing"] = -0.075
    pool.loc[0, "aa_toward"] = -2.0
    z = _z(pool)
    assert z.loc[0, "z_comp"] <= -1.0


def test_live_table_exposes_centered_axes():
    """Smoke: the production table still builds and its axes are centred."""
    # The empty-table guard below sat one step too late: hitter_trend_table
    # reads statcast_{year}.parquet, which is gitignored, so on a fresh
    # checkout it raised FileNotFoundError before it could return anything to
    # check. That turned "no data here" into a hard failure, which is how a
    # data-gated test ends up masquerading as a broken one. (Fixed 2026-08-27.)
    try:
        t = TS.hitter_trend_table(2026, 2025)
    except FileNotFoundError as exc:
        pytest.skip(f"statcast substrate not present in this checkout ({exc})")
    if not len(t):
        pytest.skip("no bat-tracking table available in this checkout")
    for z in ("z_bs", "z_fast", "z_aa"):
        assert abs(t[z].mean()) < 1e-6, f"{z} is not pool-centred"
