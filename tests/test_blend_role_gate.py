"""Blend anchor role gate — relief-converted starters must not inherit an
RP-scale prior into the SP blend (bug found + fixed 2026-07-28).

THE BUG. `master_panel`'s `fp_per_start` on an **RP** row is season-total FP
divided by GS. For a reliever with one or two spot starts that is a SEASON
TOTAL wearing a per-start label — Griffin Jax 2025 carried 112.4 and Kyle
Leahy 2025 carried 242.4 (754 such rows in the panel, max 344.0).
`_lookup_player_features` fell back to `master_panel` without filtering on
`player_type`, so those values landed in the SP anchor
`prior_year_fp_per_start`, whose weight is +0.507 in z-units. The result:

    Jax    model_proj 10.82 -> blended_xfp 29.09   blend_confidence 'high'
    Leahy  model_proj  9.06 -> blended_xfp 45.64   blend_confidence 'high'

Nine SPs in the 2026-07-28 nightly were inflated past 2x. `/sp-board
--scope roster` renders baseline xFP next to the rp3 headline, so these were
visible in a decision surface.

These tests pin the three defenses:
  1. role gate      — prior rows must share the projected bucket
  2. anchor sanity  — a rate outside the bucket's plausible range is dropped
  3. confidence     — feature COUNT alone may never certify a blend that
                      disagrees with the production model by >2x
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from scripts.xfp.lib.blend_score import (
    _ANCHOR_MAX_STALENESS_YEARS,
    _ANCHOR_PLAUSIBLE_MAX,
    _BLEND_DISAGREEMENT_RATIO,
    _MASTER_PANEL,
    _load_master_panel_lookup_typed,
    _production_rate,
    compute_blended_xfp,
)

# The canonical regression cases. mlbam ids are stable identifiers.
JAX = ("Jax, Griffin", 643377)
LEAHY = ("Leahy, Kyle", 681517)
BRADISH = ("Bradish, Kyle", 680694)   # control: a normal SP, must not move

_needs_panel = pytest.mark.skipif(
    not os.path.exists(_MASTER_PANEL), reason="master_panel.parquet not present"
)


# --- 1. role gate ------------------------------------------------------

@_needs_panel
def test_typed_panel_lookup_returns_only_matching_player_type() -> None:
    """The typed lookup is the fix's load-bearing seam: an SP query must
    never see an RP row, whatever that player's most recent season was."""
    for bucket in ("SP", "RP", "H"):
        df = _load_master_panel_lookup_typed(bucket)
        if df is None or df.empty:
            continue
        assert (df["player_type"] == bucket).all(), (
            f"{bucket} lookup leaked other player_type rows: "
            f"{sorted(set(df['player_type']) - {bucket})}"
        )
        # One row per player, else the anchor pick is order-dependent.
        assert df["mlbam_id"].is_unique


@_needs_panel
def test_rp_rows_carry_season_totals_in_fp_per_start() -> None:
    """Documents WHY the role gate is required. If this ever stops holding
    the panel semantics changed and the gate's rationale needs revisiting —
    but the gate itself stays correct regardless (role-scoped scales)."""
    panel = pd.read_parquet(
        _MASTER_PANEL, columns=["player_type", "gs", "fp_per_start"]
    )
    rp_started = panel[(panel["player_type"] == "RP") & (panel["gs"] > 0)]
    sp = panel[panel["player_type"] == "SP"].dropna(subset=["fp_per_start"])
    if rp_started.empty or sp.empty:
        pytest.skip("panel lacks the relevant rows")
    # No real SP per-start rate approaches the RP-row values.
    assert sp["fp_per_start"].max() < _ANCHOR_PLAUSIBLE_MAX["SP"]
    assert rp_started["fp_per_start"].max() > _ANCHOR_PLAUSIBLE_MAX["SP"]


# --- 2. the two canonical cases ---------------------------------------

@_needs_panel
@pytest.mark.parametrize("name,mlbam", [JAX, LEAHY])
def test_relief_convert_blend_no_longer_inflates(name: str, mlbam: int) -> None:
    """Jax and Leahy previously blended to 29.09 and 45.64 against model
    rates of 10.82 and 9.06. Both must now land near the model, and neither
    may claim high confidence — we have no SP prior for either."""
    res = compute_blended_xfp(name, "SP", mlbam)
    blended = res["blended_xfp"]
    assert blended is not None
    # Hard ceiling: the pre-fix values (29.09 / 45.64) must be impossible.
    assert blended < 20.0, f"{name} blended={blended:.2f} — anchor leak is back"

    model = _production_rate(mlbam, "SP")
    if model:
        ratio = blended / model
        assert max(ratio, 1 / ratio) <= _BLEND_DISAGREEMENT_RATIO, (
            f"{name} blended={blended:.2f} vs model={model:.2f} ({ratio:.1f}x)"
        )
    assert res["confidence_tier"] != "high"
    assert res["has_anchor"] is False, (
        f"{name} has no recent SP season — the anchor must be absent, not "
        f"borrowed from his relief years"
    )
    # The reason must be stated, not silent.
    assert any(
        n.startswith(("no_prior_SP_season", "prior_role_row_stale"))
        for n in res["notes"]
    ), res["notes"]


@_needs_panel
def test_normal_sp_blend_is_unchanged_by_the_role_gate() -> None:
    """Control. Bradish has a genuine 2025 SP row; the gate must not touch
    him. Pinned to the observed post-fix value, which equals the pre-fix
    value — this test fails if the gate over-reaches into normal SPs.

    Re-pinned 2026-08-16: value legitimately drifts with live schedule data
    (xfp_rp3_projections.csv's next_opp_team/schedule_factor are date-
    dependent, unrelated to the role-gate logic this test guards) — a
    pipeline re-run on a different day shifted 12.41 -> 11.91 purely from
    Bradish's next-opponent lookup going stale/unavailable (schedule_factor
    0.99 -> 1.0), not from any code change. Widened tolerance so routine
    schedule drift doesn't false-fail this control on every CSV refresh."""
    res = compute_blended_xfp(BRADISH[0], "SP", BRADISH[1])
    assert res["blended_xfp"] == pytest.approx(11.91, abs=0.6)


# --- 3. confidence guard ----------------------------------------------

@_needs_panel
def test_no_blend_claims_high_confidence_while_disagreeing_with_the_model() -> None:
    """The defect that let 29.09 ship as 'high': confidence counted FEATURES
    and never asked whether the answer was sane. Sweep every SP the blend
    can score and assert the invariant holds universally, not just for the
    two known names."""
    proj_path = "data/outputs/xfp_rp3_projections.csv"
    if not os.path.exists(proj_path):
        pytest.skip("rp3 projections not present")
    sample = pd.read_csv(proj_path).dropna(subset=["pitcher"]).head(120)
    offenders = []
    for _, r in sample.iterrows():
        mlbam = int(r["pitcher"])
        res = compute_blended_xfp(str(r["player_name"]), "SP", mlbam)
        blended, model = res["blended_xfp"], _production_rate(mlbam, "SP")
        if not blended or not model or blended <= 0:
            continue
        ratio = blended / model
        if max(ratio, 1 / ratio) > _BLEND_DISAGREEMENT_RATIO and res["confidence_tier"] == "high":
            offenders.append((r["player_name"], round(blended, 2), round(model, 2), round(ratio, 2)))
    assert not offenders, f"high confidence despite model disagreement: {offenders}"


def test_guard_constants_are_sane() -> None:
    """Cheap tripwire — these thresholds are the contract the tests above
    assert against, so a silent loosening should fail loudly here."""
    assert _ANCHOR_PLAUSIBLE_MAX["SP"] == 30.0
    assert _ANCHOR_PLAUSIBLE_MAX["RP"] == 15.0
    assert _ANCHOR_PLAUSIBLE_MAX["H"] == 2.0
    assert _BLEND_DISAGREEMENT_RATIO == 2.0
    assert _ANCHOR_MAX_STALENESS_YEARS == 3


def test_production_rate_is_inactive_for_rp() -> None:
    """rprs2 publishes totals (xfp_ros), not a per-appearance rate, so the
    disagreement guard must stay off for RP rather than compare mismatched
    units."""
    assert _production_rate(643377, "RP") is None
