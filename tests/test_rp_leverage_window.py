"""RP leverage-window diagnostic tests (PR 7, Gate 0c).

Plan v11 Decision 7: SAVE_PROMOTION_WINDOW and SETUP_CONSOLIDATION_WINDOW
are DELIBERATELY DISTINCT signals -- prior code treated high HLD as a
SV proxy when SV was thin, conflating two role transitions with very
different fantasy implications.
"""
import pytest

from scripts.xfp.lib.rp_leverage_window import (
    SAVE_PROMOTION_MAX_SV_PRIOR,
    SAVE_PROMOTION_MIN_SV_RECENT,
    SETUP_CONSOLIDATION_MAX_SV_RECENT,
    SETUP_CONSOLIDATION_MIN_HLD_RECENT,
    classify_rp_leverage_window,
)


@pytest.mark.parametrize(
    "sv_recent,hld_recent,sv_prior,hld_prior,expected",
    [
        # Plain SAVE_PROMOTION: 3 saves recent, 0 prior.
        (3, 1, 0, 2, "SAVE_PROMOTION_WINDOW"),
        # Exactly at threshold: 2 saves recent, 0 prior.
        (2, 0, 0, 0, "SAVE_PROMOTION_WINDOW"),
        # SAVE wins over SETUP when both conditions could fire.
        # (sv_recent=2 satisfies SAVE; hld_recent=5 would satisfy SETUP
        # but sv_recent=2 > SETUP_CONSOLIDATION_MAX_SV_RECENT=1 anyway.)
        (2, 5, 0, 1, "SAVE_PROMOTION_WINDOW"),
        # Prior saves > 0 disqualifies SAVE_PROMOTION (player already had
        # the role).
        (3, 0, 1, 0, None),
        # Plain SETUP_CONSOLIDATION: 5 holds, 0 saves.
        (0, 5, 0, 2, "SETUP_CONSOLIDATION_WINDOW"),
        # SETUP at threshold: 4 holds.
        (0, 4, 0, 0, "SETUP_CONSOLIDATION_WINDOW"),
        # SETUP allows up to 1 SV (occasional save while consolidating
        # setup role).
        (1, 6, 0, 4, "SETUP_CONSOLIDATION_WINDOW"),
        # SETUP fails: 2 SV pushes into save territory but recent SAVE
        # also fails because sv_prior > 0 -> neither window.
        (2, 6, 1, 4, None),
        # Quiet RP: low usage all-around.
        (0, 1, 0, 1, None),
    ],
    ids=[
        "save_promotion_plain",
        "save_promotion_at_threshold",
        "save_wins_over_setup_when_both_could_fire",
        "save_disqualified_by_prior_saves",
        "setup_consolidation_plain",
        "setup_at_threshold",
        "setup_allows_occasional_save",
        "neither_window_when_sv_recent_with_prior",
        "quiet_rp_returns_none",
    ],
)
def test_classify_rp_leverage_window(
    sv_recent: int,
    hld_recent: int,
    sv_prior: int,
    hld_prior: int,
    expected: str | None,
) -> None:
    out = classify_rp_leverage_window(
        sv_recent=sv_recent,
        hld_recent=hld_recent,
        sv_prior=sv_prior,
        hld_prior=hld_prior,
    )
    assert out == expected


def test_threshold_constants_are_lockable() -> None:
    """Lock the threshold values so a future refactor that loosens them
    has to be explicit. Plan v11 Gate 0c calibrated these against
    BrownU scoring + historical promotion patterns."""
    assert SAVE_PROMOTION_MIN_SV_RECENT == 2
    assert SAVE_PROMOTION_MAX_SV_PRIOR == 0
    assert SETUP_CONSOLIDATION_MIN_HLD_RECENT == 4
    assert SETUP_CONSOLIDATION_MAX_SV_RECENT == 1
