"""A bad SP lever key must raise, not report the move as free.

WHY THIS EXISTS
When the draw dicts moved from name-keys to mlbam-keys (2026-07-29), callers
still passing a NAME matched nothing, so every "what if I bench him" delta
silently read 0.00pp — a wrong answer that looked like a legitimate "benching
him costs nothing". `assemble()` gained a hard KeyError for that.

It gained it for the HITTER lever, and later the RP lever. The two SP levers —
`bench_starts` and `drop_sp_mlbams` — never got it, even though the bug is
named after a BENCH delta:

  * `_sp_side_total._benched()` accepts (mlbam, date) or (name, date) and
    returns False for anything else;
  * `drop_sp_mlbams` is an `int(event mlbam) not in ...` filter.

So a string mlbam ("201" — plausible, ESPN ids often arrive as strings), a
bare id with no date, or an unknown name each changed nothing and reported the
move as free. Measured 2026-08-27 on the fixtures below: all three returned a
+0.00 FP delta against a true -19.94.

The guard validates the PLAYER component only, never the date — benching a
date on which he has no start is a legitimate no-op, and so is dropping an SP
with no remaining starts. Those two must keep returning a real zero, which is
what separates this guard from an over-fit one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

E = pytest.importorskip("scripts.xfp.lib.leverage_engine",
                        reason="leverage engine needs the dashboard import chain")

from test_leverage_engine import _draws, _state  # noqa: E402


@pytest.fixture
def scenario():
    state = _state(cap_mine=10)
    D = _draws(
        hitters=[(101, "Hit A", 5.0)],
        my_sp=[(201, "SP One", "2026-08-28", 20.0),
               (202, "SP Two", "2026-08-29", 20.0)],
        spread=3.0,
    )
    return state, D


def _delta(state, D, **kw) -> float:
    base, _ = E.assemble(state, D)
    my, _ = E.assemble(state, D, **kw)
    return float(my.mean() - base.mean())


# ── the good forms still work ────────────────────────────────────────────────

@pytest.mark.parametrize("key", [(201, "2026-08-28"), ("SP One", "2026-08-28")])
def test_valid_bench_key_actually_benches(scenario, key):
    state, D = scenario
    assert _delta(state, D, bench_starts={key}) < -1.0


def test_valid_drop_sp_actually_drops(scenario):
    state, D = scenario
    assert _delta(state, D, drop_sp_mlbams={201}) < -1.0


# ── the bug forms now raise instead of reporting the move as free ────────────

@pytest.mark.parametrize("bad,why", [
    ({("201", "2026-08-28")}, "string mlbam"),
    ({201}, "bare mlbam, no date"),
    ({("Nobody", "2026-08-28")}, "unknown name"),
    ({(201,)}, "1-tuple"),
    ({(None, "2026-08-28")}, "None player"),
])
def test_bad_bench_key_raises(scenario, bad, why):
    state, D = scenario
    with pytest.raises(KeyError):
        E.assemble(state, D, bench_starts=bad)


@pytest.mark.parametrize("bad,why", [
    ({"201"}, "string mlbam"),
    ({"SP One"}, "name instead of id"),
])
def test_bad_drop_sp_key_raises(scenario, bad, why):
    state, D = scenario
    with pytest.raises(KeyError):
        E.assemble(state, D, drop_sp_mlbams=bad)


# ── the legitimate zeros must stay zeros, not become errors ──────────────────

def test_benching_a_date_with_no_start_is_a_real_zero(scenario):
    """An over-broad bench window is legal, not a caller bug."""
    state, D = scenario
    assert _delta(state, D, bench_starts={(201, "2026-08-30")}) == pytest.approx(0.0)


def test_dropping_an_sp_with_no_remaining_starts_is_a_real_zero(scenario):
    """Membership is deliberately NOT required for drop_sp_mlbams."""
    state, D = scenario
    assert _delta(state, D, drop_sp_mlbams={999}) == pytest.approx(0.0)


def test_empty_levers_are_noops(scenario):
    state, D = scenario
    assert _delta(state, D, bench_starts=set()) == pytest.approx(0.0)
    assert _delta(state, D, drop_sp_mlbams=set()) == pytest.approx(0.0)


def test_bench_key_may_name_an_extra_sp(scenario):
    """extra_my_sp (an FA add) is part of the pool the guard validates against."""
    state, D = scenario
    extra = [{"event": {"name": "FA Arm", "date": "2026-08-30",
                        "confirmed": True, "mlbam": 301},
              "fp": D["my_sp"][0]["fp"], "occ": D["my_sp"][0]["occ"]}]
    E.assemble(state, D, extra_my_sp=extra,
               bench_starts={(301, "2026-08-30")})  # must not raise
