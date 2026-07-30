"""Internals tests for the I4 reliever-band calibration study.

Companion to ``tests/test_rp_band_crps.py`` (which locks the scoring rules and
the loud-failure sigma conversion). This file covers the machinery those tests
left dark: ``build_panel``, ``attach_band``, ``attach_prior_history``,
``mixture_crps``/``mixture_samples``, ``c_star``, ``bh_fdr``, and the paired
player-clustered bootstrap.

Why this file exists: the 2026-07-30 emp-misalignment bug lived ENTIRELY in
that dark zone. ``c_star`` selected panel rows with ``.loc``, pandas propagated
``.attrs`` through the selection unchanged, and ``mixture_crps`` then sliced
``attrs['emp']`` POSITIONALLY — so a non-contiguous row subset paired 3,515 of
3,516 TEST rows with a DIFFERENT pitcher's empirical history, silently, because
the slice LENGTHS still matched. The fix re-aligns via
``panel.index.get_indexer(sub.index)``. The regression tests here are built so
the OLD code path (simulated verbatim) fails them by a factor of >10x while the
fixed path passes with margin.

Everything below is deterministic synthetic data — no network, no real caches.
Real production files are never read; the module-level path constants are
monkeypatched to tmp_path fixtures.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import validate_rp_band_crps as vrb  # noqa: E402
from validate_rp_band_crps import (  # noqa: E402
    DEFAULT_RP_APP_RATE,
    EMP_LAST_N_RP,
    K_PRIOR_RP,
    SEED,
    SIGMA_PER_RP_GAME,
    attach_band,
    attach_prior_history,
    bh_fdr,
    build_panel,
    c_star,
    measured_team_games_per_day,
    mixture_crps,
    mixture_samples,
    paired_cluster_bootstrap,
)


# --------------------------------------------------------------------------- #
# Synthetic-store builders
# --------------------------------------------------------------------------- #
def _box_frame(relief_rows, filler_dates):
    """Boxscore-pitchers frame with a clean measured game rate.

    ``relief_rows`` is a list of ``(mlbam_id, 'YYYY-MM-DD', fp_rp)``. Each date
    in ``filler_dates`` gets 15 games x 2 teams of gs=1 filler rows so every
    date carries exactly 30 unique (game_pk, team_id) pairs — which makes
    ``measured_team_games_per_day`` come out to exactly 1.0 and keeps the
    n_exp assertions arithmetic instead of algebra. Relief rows reuse the
    filler's (game_pk, team_id) so they never change the per-day pair count.
    """
    rows = []
    for d in filler_dates:
        base_pk = int(d.replace("-", "")) * 100
        for g in range(15):
            for t in (2 * g, 2 * g + 1):
                rows.append({"mlbam_id": 90000 + len(rows), "game_date": d,
                             "game_pk": base_pk + g, "gs": 1, "fp_rp": 0.0,
                             "team_id": t})
    for pid, d, fp in relief_rows:
        rows.append({"mlbam_id": pid, "game_date": d,
                     "game_pk": int(d.replace("-", "")) * 100, "gs": 0,
                     "fp_rp": fp, "team_id": 0})
    return pd.DataFrame(rows)


def _write_stores(tmp_path, monkeypatch, hist, box, rprs2):
    hist_p = tmp_path / "hist.parquet"
    box_p = tmp_path / "box.parquet"
    rprs2_p = tmp_path / "rprs2.csv"
    hist.to_parquet(hist_p)
    box.to_parquet(box_p)
    rprs2.to_csv(rprs2_p, index=False)
    monkeypatch.setattr(vrb, "HIST", hist_p)
    monkeypatch.setattr(vrb, "BOX_P", box_p)
    monkeypatch.setattr(vrb, "RPRS2", rprs2_p)


_RPRS2_MINIMAL = pd.DataFrame({
    "pitcher": [101, 104, 105],
    "name_api": ["Good Band", "Inverted Band", "No Volume"],
    "xfp_ros": [120.0, 5.0, 80.0],
    "xfp_ros_p25": [100.0, 31.6, 60.0],
    "xfp_ros_p75": [157.4, -77.2, 100.0],
    "xfp_p25": [10.0, 20.0, 5.0],
    "xfp_p75": [23.5, 6.5, 15.0],
})


@pytest.fixture()
def synthetic_panel(tmp_path, monkeypatch):
    """A tiny end-to-end build_panel run with hand-checkable arithmetic.

    Snapshot 2026-07-01 (days_rem to SEASON_END 2026-09-28 = 89):
      101  proj_per=62.3 (= 89*0.7, so mu_prod = 2.0 exactly), vol=0.4
           relief 07-01 (SAME DAY — must NOT match) and 07-03 (must match)
      102  relief on 07-01 only — no strictly-forward appearance -> dropped
      103  proj_per=-5 with a valid 07-03 appearance -> dropped AND counted
      104  proj_volume=0 -> n_exp=0 -> mu_vol NaN (kept)
      105  player_type='SP' -> filtered before matching
      NaN  mlbam_id missing -> filtered before matching
    """
    hist = pd.DataFrame({
        "snapshot_date": ["2026-07-01"] * 6,
        "player_type": ["RP", "RP", "RP", "RP", "SP", "RP"],
        "mlbam_id": [101.0, 102.0, 103.0, 104.0, 105.0, np.nan],
        "proj_per": [62.3, 50.0, -5.0, 30.0, 40.0, 10.0],
        "proj_volume": [0.4, 0.3, 0.3, 0.0, 0.5, 0.2],
    })
    box = _box_frame(
        relief_rows=[(101, "2026-07-01", 7.0), (101, "2026-07-03", 3.5),
                     (102, "2026-07-01", 9.0),
                     (103, "2026-07-03", 1.0), (104, "2026-07-03", 2.0)],
        filler_dates=["2026-07-01", "2026-07-03"],
    )
    _write_stores(tmp_path, monkeypatch, hist, box, _RPRS2_MINIMAL)
    return build_panel(verbose=False)


# --------------------------------------------------------------------------- #
# 1. measured_team_games_per_day
# --------------------------------------------------------------------------- #
def test_measured_team_games_per_day_counts_unique_team_game_pairs():
    """Duplicated (game_pk, team_id) rows must not inflate the rate."""
    box = pd.DataFrame({
        "game_date": ["2026-06-01"] * 4 + ["2026-06-02"] * 3,
        "game_pk": [1, 1, 2, 2, 3, 3, 3],
        "team_id": [10, 11, 10, 12, 10, 11, 11],   # last row duplicates (3,11)
    })
    # date 1: 4 unique pairs; date 2: 2 unique pairs -> mean 3 -> /30 = 0.1
    assert measured_team_games_per_day(box) == pytest.approx(0.1)


def test_measured_team_games_per_day_raises_on_empty_store():
    empty = pd.DataFrame({"game_date": [], "game_pk": [], "team_id": []})
    with pytest.raises(ValueError, match="no dated rows"):
        measured_team_games_per_day(empty)


# --------------------------------------------------------------------------- #
# 2. build_panel — row construction, forward matching, degenerate rows
# --------------------------------------------------------------------------- #
def test_build_panel_forward_match_skips_same_day_appearance(synthetic_panel):
    """merge_asof(allow_exact_matches=False): the target is the first relief
    appearance STRICTLY after the snapshot, so 101's same-day 7.0 must be
    skipped in favour of the 07-03 outing."""
    r = synthetic_panel[synthetic_panel["mlbam_id"] == 101].iloc[0]
    assert r["y"] == pytest.approx(3.5)
    assert r["gap_days"] == 2
    assert r["days_rem"] == 89


def test_build_panel_production_location_formula(synthetic_panel):
    """mu_prod = (proj_per / days_rem) / 0.35 — verbatim project_rp algebra."""
    r = synthetic_panel[synthetic_panel["mlbam_id"] == 101].iloc[0]
    assert r["mu_prod"] == pytest.approx((62.3 / 89) / DEFAULT_RP_APP_RATE)
    assert r["mu_prod"] == pytest.approx(2.0)          # fixture chosen to land here


def test_build_panel_volume_fields(synthetic_panel):
    """n_exp = proj_volume * days_rem * gpd; mu_vol NaN when n_exp == 0."""
    assert synthetic_panel.attrs["gpd"] == pytest.approx(1.0)
    r101 = synthetic_panel[synthetic_panel["mlbam_id"] == 101].iloc[0]
    assert r101["n_exp"] == pytest.approx(0.4 * 89 * 1.0)
    assert r101["mu_vol"] == pytest.approx(62.3 / (0.4 * 89))
    r104 = synthetic_panel[synthetic_panel["mlbam_id"] == 104].iloc[0]
    assert r104["n_exp"] == pytest.approx(0.0)
    assert np.isnan(r104["mu_vol"])


def test_build_panel_drops_and_counts_degenerate_rows(synthetic_panel):
    """102 (no forward appearance), 103 (proj_per<=0, COUNTED), 105 (SP), and
    the NaN-mlbam row must all be gone; only 101 and 104 survive."""
    assert set(synthetic_panel["mlbam_id"]) == {101, 104}
    assert synthetic_panel.attrs["n_dropped_neg"] == 1


def test_build_panel_gap_days_is_at_least_one(synthetic_panel):
    """Exact-match exclusion means every matched row has gap_days >= 1 — the
    invariant that makes main()'s (0, 1] '1d' gap bucket well-defined."""
    assert (synthetic_panel["gap_days"] >= 1).all()


def test_build_panel_raises_on_missing_input_file(tmp_path, monkeypatch):
    monkeypatch.setattr(vrb, "HIST", tmp_path / "does_not_exist.parquet")
    with pytest.raises(FileNotFoundError, match="does_not_exist"):
        build_panel(verbose=False)


def test_build_panel_raises_on_missing_history_column(tmp_path, monkeypatch):
    hist = pd.DataFrame({"snapshot_date": ["2026-07-01"], "player_type": ["RP"],
                         "mlbam_id": [101.0], "proj_per": [10.0]})  # no proj_volume
    box = _box_frame([(101, "2026-07-02", 1.0)], ["2026-07-02"])
    _write_stores(tmp_path, monkeypatch, hist, box, _RPRS2_MINIMAL)
    with pytest.raises(KeyError, match="proj_volume"):
        build_panel(verbose=False)


# --------------------------------------------------------------------------- #
# 3. attach_band — degenerate published bands are counted, never floored
# --------------------------------------------------------------------------- #
def test_attach_band_sigma_and_degenerate_counters(tmp_path, monkeypatch):
    rprs2_p = tmp_path / "rprs2.csv"
    _RPRS2_MINIMAL.to_csv(rprs2_p, index=False)
    monkeypatch.setattr(vrb, "RPRS2", rprs2_p)

    panel = pd.DataFrame({"mlbam_id": [101, 104, 105, 999],
                          "n_exp": [25.0, 25.0, 0.0, 25.0]})
    out = attach_band(panel, verbose=False)

    # 101: healthy band -> (57.4/1.35)/sqrt(25)
    assert out["sigma_band"].iloc[0] == pytest.approx((57.4 / 1.35) / 5.0)
    # 104: inverted RoS band -> NaN + counted as bad width (House Rule 1: no floor)
    assert np.isnan(out["sigma_band"].iloc[1])
    # 105: good band but n_exp=0 -> NaN + counted separately
    assert np.isnan(out["sigma_band"].iloc[2])
    # 999: not in the published CSV at all
    assert np.isnan(out["sigma_band"].iloc[3])
    assert out.attrs["band_bad_width"] == 1
    assert out.attrs["band_bad_nexp"] == 1
    assert out.attrs["band_nomatch"] == 1

    # sigma_band_raw is the dashboard's UNGUARDED full-year expression: a
    # NEGATIVE value passes through here by design (main() masks > 0 later,
    # and R2b exists precisely to price what run_season_sim consumes).
    assert out["sigma_band_raw"].iloc[0] == pytest.approx(13.5 / 1.35)
    assert out["sigma_band_raw"].iloc[1] == pytest.approx((6.5 - 20.0) / 1.35)
    assert out["sigma_band_raw"].iloc[1] < 0
    assert np.isnan(out["sigma_band_raw"].iloc[3])


# --------------------------------------------------------------------------- #
# 4. attach_prior_history — leakage-safe, last-20 capped, relief-only
# --------------------------------------------------------------------------- #
def test_attach_prior_history_leakage_safe_and_capped(tmp_path, monkeypatch):
    """History must be STRICTLY before the snapshot (a same-day outing is the
    leak the searchsorted side='left' exists to prevent), capped at the last
    EMP_LAST_N_RP appearances, and drawn from relief (gs==0) rows only."""
    dates = [d.strftime("%Y-%m-%d")
             for d in pd.date_range("2026-05-01", "2026-05-25")]
    rows = [{"mlbam_id": 301, "game_date": d, "game_pk": 500 + i, "gs": 0,
             "fp_rp": float(i + 1)} for i, d in enumerate(dates)]
    rows.append({"mlbam_id": 301, "game_date": "2026-05-20", "game_pk": 900,
                 "gs": 1, "fp_rp": 55.0})                   # a START: excluded
    rows.append({"mlbam_id": 301, "game_date": "2026-06-01", "game_pk": 901,
                 "gs": 0, "fp_rp": 99.0})                   # snapshot day: leak
    rows.append({"mlbam_id": 301, "game_date": "2026-06-05", "game_pk": 902,
                 "gs": 0, "fp_rp": 98.0})                   # future: leak
    box_p = tmp_path / "box.parquet"
    pd.DataFrame(rows).to_parquet(box_p)
    monkeypatch.setattr(vrb, "BOX_P", box_p)

    panel = pd.DataFrame({"mlbam_id": [301, 302],
                          "snapshot_date": ["2026-06-01", "2026-06-01"]})
    out = attach_prior_history(panel)

    assert out["n_emp"].tolist() == [EMP_LAST_N_RP, 0]
    # last 20 of the 25 pre-snapshot relief outings = fp values 6..25;
    # 55 (start), 99 (same-day) and 98 (future) must all be absent.
    np.testing.assert_array_equal(out.attrs["emp"][0],
                                  np.arange(6.0, 26.0))
    assert len(out.attrs["emp"][1]) == 0


# --------------------------------------------------------------------------- #
# 5. mixture_samples — the production blend weight
# --------------------------------------------------------------------------- #
def test_mixture_samples_empirical_weight_fraction():
    """w = n_emp/(n_emp + K_PRIOR_RP): with n_emp=20 exactly 2/3 of draws come
    from the pitcher's own history, and an n_emp=0 row stays pure Gaussian."""
    panel = pd.DataFrame({"y": [0.0, 0.0], "n_emp": [20, 0]})
    panel.attrs["emp"] = [np.array([42.0]), np.array([])]
    rng = np.random.default_rng(SEED)
    out = mixture_samples(panel, mu=[0.0, 0.0], sigma=[1e-9, 1e-9], rng=rng)

    w = 20 / (20 + K_PRIOR_RP)
    frac = (out[0] == 42.0).mean()
    assert abs(frac - w) < 0.04              # binomial noise at m=2000 is ~0.01
    # the Gaussian remainder sits at mu=0 with the 1e-6 sigma clamp
    assert np.abs(out[0][out[0] != 42.0]).max() < 0.01
    assert not (out[1] == 42.0).any()
    assert np.abs(out[1]).max() < 0.01


# --------------------------------------------------------------------------- #
# 6. mixture_crps — THE emp-pairing regression zone
# --------------------------------------------------------------------------- #
def _point_mass_panel(y_vals, n_emp=20):
    """Panel whose empirical history is a point mass AT each row's own y, so a
    correctly-paired mixture CRPS is tiny and any cross-pitcher pairing is
    glaring (CRPS scales with the |y_i - y_j| distance)."""
    y = np.asarray(y_vals, float)
    panel = pd.DataFrame({"y": y, "mu": y,
                          "n_emp": np.full(len(y), n_emp),
                          "mlbam_id": np.arange(len(y))})
    panel.attrs["emp"] = [np.full(3, v) for v in y]
    return panel


def test_mixture_crps_pairs_each_row_with_its_own_pitcher_history():
    """Two pitchers with wildly different histories (+100 vs -100): correct
    pairing scores every row tiny; swapping the emp lists must blow the CRPS
    up by orders of magnitude. This is the property whose absence let the
    2026-07-30 misalignment run silent."""
    panel = _point_mass_panel([100.0, -100.0, 100.0, -100.0])
    mu = panel["mu"].to_numpy()
    sigma = np.full(4, 1.0)

    correct = mixture_crps(panel, mu, sigma, SEED)
    assert correct.max() < 2.0

    swapped = panel.copy()
    swapped.attrs["emp"] = list(reversed(panel.attrs["emp"]))
    detect = mixture_crps(swapped, mu, sigma, SEED)
    assert detect.min() > 30.0               # every row mispaired by 200 FP
    assert detect.min() > 10 * correct.max()


def test_mixture_crps_alignment_survives_the_chunk_boundary():
    """mixture_crps processes rows in chunks of 2000; rows past the boundary
    must still slice THEIR OWN emp entries. y is spread 10 FP apart per row so
    any off-by-a-chunk pairing would be unmissable."""
    n = 2050
    panel = _point_mass_panel(np.arange(n, dtype=float) * 10.0)
    mu = panel["mu"].to_numpy()
    res = mixture_crps(panel, mu, np.full(n, 0.5), SEED)
    assert res.shape == (n,)
    assert res.max() < 2.0                   # includes rows 2000..2049


# --------------------------------------------------------------------------- #
# 7. c_star — grid search + the non-contiguous-subset realignment fix
# --------------------------------------------------------------------------- #
def test_c_star_realigns_emp_for_noncontiguous_subset():
    """THE regression test for the 2026-07-30 bug.

    Panel alternates pitcher A (y=+50, history +50) and pitcher B (y=-50,
    history -50). The mask selects the four A rows — a NON-CONTIGUOUS label
    subset (positions 0,2,4,6). The OLD code carried the FULL emp list into
    the subset via .attrs propagation and mixture_crps then sliced it
    positionally, handing subset rows 1 and 3 pitcher B's -50 history against
    a +50 actual. Fixed c_star must score all four rows against A's own
    history; the verbatim old path (simulated below) must fail loudly.
    """
    y = np.array([50.0, -50.0] * 4)
    panel = _point_mass_panel(y)
    mask = pd.Series([True, False] * 4, index=panel.index)

    _, best_crps, _ = c_star(panel, mask, "mu", "mix",
                             grid=np.array([0.4]))          # sigma = 1.0
    assert best_crps < 2.0

    # -- the OLD behaviour, verbatim: full emp list + positional slice --------
    sub_old = panel.loc[mask].copy()
    sub_old.attrs["emp"] = list(panel.attrs["emp"])          # unchanged attrs
    mu_sub = sub_old["mu"].to_numpy()
    old = mixture_crps(sub_old, mu_sub, np.full(len(sub_old), 1.0), SEED)
    # subset rows 1 and 3 got pitcher B's history: mispaired by 100 FP
    assert old[1] > 10.0 and old[3] > 10.0
    assert old[0] < 2.0 and old[2] < 2.0     # silent-partner rows still fine
    assert old.mean() > 10 * best_crps       # the fix moves the answer, loudly


def test_c_star_grid_finds_known_optimal_sigma_gaussian():
    """y ~ N(3, 4.0) with mu=3: expected CRPS of N(mu, s) is minimized exactly
    at s = 4.0, i.e. c = 4.0/2.5 = 1.6. The default grid must land there."""
    rng = np.random.default_rng(99)
    n = 5000
    panel = pd.DataFrame({"y": rng.normal(3.0, 4.0, n),
                          "mu": np.full(n, 3.0)})
    mask = pd.Series(True, index=panel.index)
    c, best, curve = c_star(panel, mask, "mu", "gauss")
    assert abs(c - 1.6) <= 0.15
    # the curve is a real bowl, not a flat accident
    assert curve["crps"].iloc[0] > best
    assert curve["crps"].iloc[-1] > best


def test_c_star_mixture_reduces_to_gaussian_when_no_history():
    """With n_emp=0 everywhere the mixture IS the Gaussian, so the mixture
    grid search must pick the true sigma too (paired draws: each grid point
    reuses the same seed, so the argmin is stable at modest n)."""
    rng = np.random.default_rng(7)
    n = 600
    panel = pd.DataFrame({"y": rng.normal(2.0, 4.0, n),
                          "mu": np.full(n, 2.0),
                          "n_emp": np.zeros(n, dtype=int)})
    panel.attrs["emp"] = [np.array([])] * n
    mask = pd.Series(True, index=panel.index)
    c, _, _ = c_star(panel, mask, "mu", "mix",
                     grid=np.array([0.8, 1.6, 3.2]))
    assert c == pytest.approx(1.6)


def test_c_star_gauss_works_without_emp_attr():
    """build_panel output has no attrs['emp'] until attach_prior_history runs;
    the Gaussian path must not require it."""
    panel = pd.DataFrame({"y": [1.0, 2.0, 3.0], "mu": [2.0, 2.0, 2.0]})
    assert "emp" not in panel.attrs
    mask = pd.Series([True, True, False], index=panel.index)
    c, best, _ = c_star(panel, mask, "mu", "gauss",
                        grid=np.array([1.0, 2.0]))
    assert np.isfinite(best)
    assert c in (1.0, 2.0)


# --------------------------------------------------------------------------- #
# 8. bh_fdr
# --------------------------------------------------------------------------- #
def test_bh_fdr_known_reject_set():
    # m=4, q=0.05 -> thresholds .0125/.025/.0375/.05; cutoff lands at 0.03
    got = bh_fdr([0.01, 0.02, 0.03, 0.2])
    np.testing.assert_array_equal(got, [True, True, True, False])


def test_bh_fdr_all_none_and_singleton():
    np.testing.assert_array_equal(bh_fdr([0.001, 0.002]), [True, True])
    np.testing.assert_array_equal(bh_fdr([0.5, 0.9]), [False, False])
    np.testing.assert_array_equal(bh_fdr([0.04]), [True])    # 0.04 <= 0.05
    np.testing.assert_array_equal(bh_fdr([0.06]), [False])


def test_bh_fdr_step_up_rescues_smaller_p_below_the_cutoff():
    """BH is a STEP-UP procedure: the largest passing sorted p sets the
    cutoff, rescuing a smaller p that failed its own rank threshold. Here
    0.049 > .025 fails rank 2, but 0.050 <= .05 passes rank 4 -> ALL pass."""
    np.testing.assert_array_equal(bh_fdr([0.010, 0.049, 0.050, 0.050]),
                                  [True, True, True, True])


def test_bh_fdr_ties_reject_or_survive_together():
    # thresholds .0167/.0333/.05: the tied 0.03s pass via rank 2's threshold
    np.testing.assert_array_equal(bh_fdr([0.03, 0.03, 0.5]),
                                  [True, True, False])


# --------------------------------------------------------------------------- #
# 9. paired player-clustered bootstrap
# --------------------------------------------------------------------------- #
def test_bootstrap_same_seed_reproduces_exactly():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"a": rng.normal(2.0, 1.0, 30),
                       "b": rng.normal(2.1, 1.0, 30),
                       "cl": np.repeat(np.arange(6), 5)})
    r1 = paired_cluster_bootstrap(df, "a", "b", "cl", n_boot=200, seed=123)
    r2 = paired_cluster_bootstrap(df, "a", "b", "cl", n_boot=200, seed=123)
    assert r1 == r2


def test_bootstrap_resamples_clusters_not_rows():
    """Two clusters with row-constant diffs (0.0 and 0.1). Cluster resampling
    can only produce the three atoms {0, 0.05, 0.1}, so the CI must span the
    full [0.0, 0.1] and p must sit near 2*P(draw A twice) = 0.5. A row-level
    bootstrap over the 400 rows would put p at the 1/(2*n_boot) floor (SE of
    the mean diff ~0.0025 vs a 0.05 effect) — so a near-floor p here is the
    smoking gun that clustering broke."""
    df = pd.DataFrame({
        "a": np.ones(400),
        "b": np.concatenate([np.ones(200), np.full(200, 1.1)]),
        "cl": np.repeat(["A", "B"], 200),
    })
    r = paired_cluster_bootstrap(df, "a", "b", "cl", n_boot=1000, seed=SEED)
    assert r["n_clusters"] == 2
    assert r["n_rows"] == 400
    assert r["diff"] == pytest.approx(0.05, abs=1e-9)
    assert r["ci_lo"] == pytest.approx(0.0, abs=1e-12)       # the (A,A) atom
    assert r["ci_hi"] == pytest.approx(0.1, abs=1e-6)        # the (B,B) atom
    assert 0.40 <= r["p"] <= 0.60                            # NOT the floor
    assert r["p"] > 100 * (1.0 / (2 * 1000))


def test_bootstrap_degenerate_single_cluster_does_not_crash():
    """One cluster: every resample is the whole panel, so the CI collapses to
    the point estimate and p bottoms out at the declared 1/(2*n_boot) floor."""
    df = pd.DataFrame({"a": np.zeros(5), "b": np.full(5, 2.0),
                       "cl": ["only"] * 5})
    r = paired_cluster_bootstrap(df, "a", "b", "cl", n_boot=200, seed=1)
    assert r["n_clusters"] == 1
    assert r["diff"] == pytest.approx(2.0)
    assert r["ci_lo"] == r["ci_hi"] == pytest.approx(2.0)
    assert r["p"] == pytest.approx(1.0 / (2 * 200))


def test_bootstrap_drops_nan_rows_and_raises_on_empty():
    df = pd.DataFrame({"a": [1.0, np.nan, 1.0], "b": [1.5, 1.5, 1.5],
                       "cl": [1, 1, 2]})
    r = paired_cluster_bootstrap(df, "a", "b", "cl", n_boot=50, seed=2)
    assert r["n_rows"] == 2                                  # NaN row excluded
    empty = pd.DataFrame({"a": [np.nan], "b": [1.0], "cl": [1]})
    with pytest.raises(ValueError, match="empty paired panel"):
        paired_cluster_bootstrap(empty, "a", "b", "cl")
