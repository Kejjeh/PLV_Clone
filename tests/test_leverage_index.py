"""Golden tests for the empirical LI table (leverage_index.py, Wave 1B 2026-07-19)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from lib.leverage_index import build_li_table, li_lookup, STATE_COLS  # noqa: E402


@pytest.fixture(scope="module")
def table():
    return build_li_table()


def _li(table, inning_c, is_top, outs, base_code, diff_c):
    df = pd.DataFrame(
        [[inning_c, is_top, outs, base_code, diff_c]], columns=STATE_COLS
    )
    return float(li_lookup(df, table).iloc[0])


def test_league_mean_near_one(table):
    n = table["n"].clip(lower=0)
    weighted = (table["li"] * n).sum() / n.sum()
    assert 0.85 < weighted < 1.15


def test_ninth_close_beats_blowout(table):
    # NOTE: absolute values run lower than Tango's published table for some
    # states (one-step empirical ΔWP vs Markov enumeration); the feature only
    # consumes relative ordering, so goldens assert structure, not calibration.
    close_9th = _li(table, 9, 0, 0, 0, -1)   # bottom 9, down 1, bases empty
    blowout = _li(table, 5, 0, 0, 0, 5)      # bottom 5, up 5
    assert close_9th > 1.0
    assert blowout < 0.5
    assert close_9th > 4 * blowout


def test_runners_raise_leverage(table):
    empty = _li(table, 8, 1, 1, 0, 0)        # top 8, tied, 1 out, empty
    loaded = _li(table, 8, 1, 1, 7, 0)       # same but bases loaded
    assert loaded > empty


def test_late_beats_early_when_close(table):
    first = _li(table, 1, 1, 0, 0, 0)
    ninth = _li(table, 9, 1, 0, 0, 0)
    assert ninth > first
