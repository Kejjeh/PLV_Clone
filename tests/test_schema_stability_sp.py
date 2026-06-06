"""Schema-stability lock for xfp_rp3_projections.csv (SP).

See test_schema_stability_h.py for the rationale (ADDITIVE contract).
"""
from pathlib import Path

import pandas as pd
import pytest

RP3_PATH = Path("data/outputs/xfp_rp3_projections.csv")

REQUIRED_RP3_COLUMNS = {
    "rank",
    "pitcher",
    "player_name",
    "gs_to",
    "gs_last21",
    "fp_per_start_to",
    "fp_per_start_last21",
    "recency_form_gap",
    "prior_fp_per_start",
    "data_quality_tag",
    "marcel_baseline",
    "data_driven_estimate",
    "is_on_il_at_split",
    "xfp_rp3_per_start",
    "xfp_rp3_sigma",
    "xfp_rp3_p25",
    "xfp_rp3_p75",
    "replacement_xfp_per_start",
    "replacement_delta",
    "signal",
}


@pytest.fixture(scope="module")
def rp3_columns() -> set[str]:
    if not RP3_PATH.exists():
        pytest.skip(f"{RP3_PATH} not present in this checkout")
    df = pd.read_csv(RP3_PATH, nrows=1)
    return set(df.columns)


def test_rp3_required_columns_present(rp3_columns: set[str]) -> None:
    missing = REQUIRED_RP3_COLUMNS - rp3_columns
    assert not missing, (
        f"xfp_rp3_projections.csv is missing required columns: {sorted(missing)}. "
        "These are read by name by triangulate, matchup dashboard, sp-week-plan, "
        "blend_score, and the variance/data_quality_tag display contract."
    )
