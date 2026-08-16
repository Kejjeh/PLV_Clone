"""rprs2 rank/replacement_delta/signal — behavioral spec (issue #9).

Regression coverage for the sunk-cost ranking bug: rank / replacement_xfp /
replacement_delta / signal must be computed off xfp_ros (the genuine forward
figure), never off xfp_full_year (which includes FP already banked this
season). Ranking off xfp_full_year makes an RP who missed time read as a
false 'drop' regardless of forward outlook, and can make a heavily-used
healthy arm read as a false 'hold' even with a weak forward projection.
"""
import numpy as np
import pandas as pd

from plv_clone.models.xfp.rprs2 import assign_ranking_columns


def _make_pool(rows):
    """rows: list of (name, xfp_full_year, fp_actual_2026, sigma) — xfp_ros
    and its p25/p75 bands are derived the same way production does."""
    df = pd.DataFrame(rows, columns=["name", "xfp_full_year", "fp_actual_2026", "sigma"])
    df["xfp_ros"] = (df["xfp_full_year"] - df["fp_actual_2026"]).round(1)
    Z25 = 0.6745
    df["xfp_p25"] = (df["xfp_full_year"] - Z25 * df["sigma"]).clip(lower=0)
    df["xfp_p75"] = df["xfp_full_year"] + Z25 * df["sigma"]
    df["xfp_ros_p25"] = (df["xfp_p25"] - df["fp_actual_2026"]).round(1).clip(lower=0)
    df["xfp_ros_p75"] = (df["xfp_p75"] - df["fp_actual_2026"]).round(1)
    return df


def test_injured_high_leverage_arm_outranks_healthy_low_leverage_arm():
    """Canonical case from issue #9: Pagan-like (missed 2 months as a closer,
    high forward projection) must rank AHEAD of a Weaver-like arm (never
    hurt, but a low-leverage setup role with a weaker forward number) once
    ranking is forward-based — even though Pagan's season TOTAL is lower."""
    pool = _make_pool([
        ("pagan_like", 238.9, 138.2, 25.0),   # injured 2mo, closer, high xfp_ros
        ("weaver_like", 256.6, 185.1, 25.0),  # never hurt, setup, low xfp_ros
    ])
    out = assign_ranking_columns(pool, replacement_rank=1)

    pagan_rank = out.loc[out["name"] == "pagan_like", "rank"].iloc[0]
    weaver_rank = out.loc[out["name"] == "weaver_like", "rank"].iloc[0]
    assert pagan_rank < weaver_rank, "higher xfp_ros must rank ahead despite lower xfp_full_year"

    pagan_signal = out.loc[out["name"] == "pagan_like", "signal"].iloc[0]
    assert pagan_signal != "drop", "an RP projecting well above replacement RoS must not read as drop"


def test_high_usage_low_forward_arm_does_not_outrank_better_ros_projection():
    """Mirror-image failure from issue #9 (Kevin Kelly): a healthy, heavily
    used arm with a big banked total but a weak forward number must NOT
    outrank an arm with a stronger xfp_ros."""
    pool = _make_pool([
        ("kelly_like", 274.4, 245.7, 20.0),   # huge banked total, weak xfp_ros
        ("better_ros", 150.0, 50.0, 20.0),    # smaller total, much better xfp_ros
    ])
    out = assign_ranking_columns(pool, replacement_rank=1)

    kelly_rank = out.loc[out["name"] == "kelly_like", "rank"].iloc[0]
    better_rank = out.loc[out["name"] == "better_ros", "rank"].iloc[0]
    assert better_rank < kelly_rank, "the stronger xfp_ros must outrank the bigger banked total"


def test_rank_tracks_xfp_ros_not_xfp_full_year():
    """Rank must correlate with the forward figure, not the contaminated
    season-total figure — the core diagnostic used to confirm issue #9."""
    rng = np.random.default_rng(0)
    n = 60
    banked = rng.uniform(0, 200, n)
    ros = rng.uniform(20, 150, n)  # deliberately uncorrelated with `banked`
    rows = [
        (f"p{i}", banked[i] + ros[i], banked[i], 20.0)
        for i in range(n)
    ]
    pool = _make_pool(rows)
    out = assign_ranking_columns(pool, replacement_rank=10)

    corr_ros = out["rank"].corr(out["xfp_ros"])
    corr_full = out["rank"].corr(out["xfp_full_year"])
    assert corr_ros < -0.9, f"rank should track xfp_ros tightly, got r={corr_ros:.3f}"
    assert abs(corr_ros) > abs(corr_full), (
        f"rank must track xfp_ros (r={corr_ros:.3f}) more strongly than "
        f"the banked-FP-contaminated xfp_full_year (r={corr_full:.3f})"
    )


def test_replacement_delta_uncorrelated_with_banked_fp_after_controlling_for_ros():
    """Acceptance criterion from issue #9: the add/drop decision must not be
    movable by banked points alone once xfp_ros is held fixed. Construct two
    arms with IDENTICAL xfp_ros but very different banked FP — they must land
    on the same side of the replacement line."""
    pool = _make_pool([
        ("banked_low", 100.0, 10.0, 20.0),   # xfp_ros = 90
        ("banked_high", 300.0, 210.0, 20.0),  # xfp_ros = 90, same forward value
        ("replacement", 60.0, 0.0, 20.0),     # xfp_ros = 60, sets the bar
    ])
    out = assign_ranking_columns(pool, replacement_rank=3)

    low = out.loc[out["name"] == "banked_low", "replacement_delta"].iloc[0]
    high = out.loc[out["name"] == "banked_high", "replacement_delta"].iloc[0]
    assert low == high, (
        "two arms with identical xfp_ros must get identical replacement_delta "
        "regardless of how much FP either has already banked"
    )


def test_xfp_full_year_retained_but_not_used_for_ranking():
    """xfp_full_year must survive as a diagnostic column (not dropped), but
    must not be the sort key rank is derived from."""
    pool = _make_pool([
        ("a", 500.0, 480.0, 20.0),  # huge total, almost all banked -> tiny xfp_ros
        ("b", 100.0, 0.0, 20.0),    # small total, nothing banked -> larger xfp_ros
    ])
    out = assign_ranking_columns(pool, replacement_rank=1)
    assert "xfp_full_year" in out.columns
    a_rank = out.loc[out["name"] == "a", "rank"].iloc[0]
    b_rank = out.loc[out["name"] == "b", "rank"].iloc[0]
    assert b_rank < a_rank, "b has the better xfp_ros (100) vs a (20) and must rank ahead"
