"""run_roster_audit.py's drop-candidate ranking must never let an
unresolved-name row (proj=NaN) occupy a drop-candidate slot ahead of a
real, worse-projected player — issue #23."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from run_roster_audit import rank_drop_candidates  # noqa: E402


def _roster(rows):
    return pd.DataFrame(rows, columns=["player_name", "proj"])


def test_nan_projection_row_excluded_from_bottom_n():
    """3 real hitters with valid low projections + 1 unresolved-name row
    (proj=NaN). The bottom-3 must be the 3 REAL worst performers, not the
    NaN row bumping the actual 3rd-worst out."""
    df = _roster([
        ("Star Hitter", 2.50),
        ("Weakest Real", 0.08),
        ("Second Weakest", 0.09),
        ("Third Weakest", 0.10),
        ("Unresolved Name", float("nan")),
    ])
    bottom3 = rank_drop_candidates(df, 3)
    names = list(bottom3["player_name"])
    assert "Unresolved Name" not in names
    assert names == ["Weakest Real", "Second Weakest", "Third Weakest"]


def test_all_valid_projections_unaffected():
    df = _roster([("A", 3.0), ("B", 1.0), ("C", 2.0)])
    bottom2 = rank_drop_candidates(df, 2)
    assert list(bottom2["player_name"]) == ["B", "C"]
