"""T23 — a CANDIDATE reliever's appearance COUNT must stay uncertain.

``run_weekly_optimizer._cand_for_engine`` handed the engine
``n_rem_games = units``. For an RP, ``units`` is a fractional expected-appearance
count (``matchup_projection.project_rp`` returns ``round(expected_appearances, 1)``),
not a game count. The engine then did ``n_rem = int(n_rem_games)``, so:

  * units 1.7 -> n_rem 1, p_app = min(1.7/1, 1.0) = 1.0 — every simulated week
    gave the reliever EXACTLY ONE appearance, deleting both the appearance-count
    variance and 0.7 of his expected appearances; and
  * units 0.8 -> n_rem 0 -> p_app 0.0 -> the whole draw array is zeros, so such
    a candidate could never score a positive dpwin at all.

The denominator the projection actually used is already on the projection —
``breakdown[0]['n_team_games']`` — so the fix reads it back rather than
re-deriving a schedule that could disagree.

Fixtures are synthetic: a real ``project_rp`` result plus a monkeypatched
``emp_series`` (empty history -> the pure-parametric draw path), so the expected
mean is exactly the projection's own fp and the assertions are analytic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

E = pytest.importorskip("scripts.xfp.lib.leverage_engine",
                        reason="leverage engine needs the dashboard import chain")
import run_weekly_optimizer as WO  # noqa: E402
from plv_clone import matchup_projection as MP  # noqa: E402

N_SIMS = 40_000
MLBAM = 596133  # Luke Weaver — the RP the 2026-07-30 optimizer actually adopted


def _rp_candidate(*, xfp_ros=79.4, n_team_games=4, app_rate=0.4273,
                  days_remaining_season=60):
    """A candidate dict in ``build_candidates`` shape, projected for real."""
    res = MP.project_rp(xfp_ros, n_team_games, role="closer", app_rate=app_rate,
                        days_remaining_season=days_remaining_season, rp_sigma=2.5)
    proj = {"fp": res.fp, "units": res.units, "sigma2": res.sigma2,
            "breakdown": res.breakdown}
    return {"name": "Luke Weaver", "bucket": "RP", "mlbam": MLBAM,
            "proj": proj, "starts": [], "units": res.units, "fp": res.fp}, res


def _draws_for(cand, monkeypatch):
    monkeypatch.setattr(E, "emp_series", lambda *a, **k: [])
    D = {"n_sims": N_SIMS, "seed": 11, "cand": {}}
    return E.ensure_candidate_draws({}, D, WO._cand_for_engine(cand))["arr"]


def test_added_reliever_appearance_count_is_uncertain(monkeypatch):
    """A candidate RP projected for fewer appearances than his team has games
    left shows a non-degenerate appearance count, and his simulated total
    centres on the projection's own fp — not on a single appearance's worth."""
    cand, res = _rp_candidate()
    assert res.units < 4, "fixture must project fewer appearances than team games"

    arr = _draws_for(cand, monkeypatch)

    # Some simulated weeks must contain ZERO appearances: with 4 team games and
    # p_app ~ 0.425 that is (1-0.425)**4 ~ 10.9% of sims. Pinning p_app to 1.0
    # makes it exactly 0.
    zero_share = float(np.mean(arr == 0.0))
    assert zero_share > 0.02, (
        f"appearance count is degenerate — {zero_share:.1%} of sims had zero "
        f"appearances; the reliever appears in every single simulated week")

    # And the total must centre on the projection, not on fp/units.
    assert float(arr.mean()) == pytest.approx(res.fp, rel=0.05), (
        f"scored mean {arr.mean():.3f} does not centre on the projection's "
        f"fp {res.fp:.3f} (one-appearance-only would give {res.fp / res.units:.3f})")


def test_reliever_projected_for_under_one_appearance_can_still_score(monkeypatch):
    """A candidate RP whose window projects fewer than one expected appearance
    is a low-value add, not an impossible one — his simulated total must centre
    on his projection rather than collapsing to an unbeatable hard zero."""
    cand, res = _rp_candidate(n_team_games=2, app_rate=0.40)
    assert 0 < res.units < 1, "fixture must project under one appearance"

    arr = _draws_for(cand, monkeypatch)

    assert float(arr.mean()) > 0.0, (
        "a sub-appearance candidate scored an all-zero draw array, so no add "
        "involving him could ever show a positive dpwin")
    assert float(arr.mean()) == pytest.approx(res.fp, rel=0.05)
