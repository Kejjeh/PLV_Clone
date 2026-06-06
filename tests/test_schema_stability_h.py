"""Schema-stability lock for xfp_rh3_projections.csv.

Asserts the required column set is present so refactors of the rh3 pipeline
do not accidentally drop a column that downstream consumers (triangulate,
matchup dashboard, blend scorer, fa-replacement-pool, etc.) read by name.

This is an ADDITIVE contract — extra columns are allowed (pipeline may
introduce new features), but removing one of the required columns is a
breaking change that this test will catch.
"""
from pathlib import Path

import pandas as pd
import pytest

RH3_PATH = Path("data/outputs/xfp_rh3_projections.csv")

# Validated 2026-06-06. Add columns when new features ship; remove only
# after auditing all consumers (grep the repo for the column name first).
REQUIRED_RH3_COLUMNS = {
    "rank",
    "batter",
    "player_name",
    "team",
    "primary_position",
    "pa_to",
    "prior_fp_per_pa",
    "recency_form_gap",
    "xfp_rh3_per_pa",
    "xfp_rh3_per_game",
    "xfp_rh3_sigma",
    "xfp_rh3_p25",
    "xfp_rh3_p75",
    "expected_pa_remaining",
    "expected_total_fp_remaining",
    "replacement_xfp_per_pa",
    "replacement_delta",
    "signal",
}


@pytest.fixture(scope="module")
def rh3_columns() -> set[str]:
    if not RH3_PATH.exists():
        pytest.skip(f"{RH3_PATH} not present in this checkout")
    df = pd.read_csv(RH3_PATH, nrows=1)
    return set(df.columns)


def test_rh3_required_columns_present(rh3_columns: set[str]) -> None:
    missing = REQUIRED_RH3_COLUMNS - rh3_columns
    assert not missing, (
        f"xfp_rh3_projections.csv is missing required columns: {sorted(missing)}. "
        "These are read by name by downstream consumers (triangulate, blend_score, "
        "fa-replacement-pool, matchup dashboard). If you intentionally renamed or "
        "removed one of these, audit the consumers FIRST."
    )
