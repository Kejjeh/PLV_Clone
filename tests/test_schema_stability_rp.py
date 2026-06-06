"""Schema-stability lock for xfp_rprs2_projections.csv (RP).

See test_schema_stability_h.py for the rationale (ADDITIVE contract).
"""
from pathlib import Path

import pandas as pd
import pytest

RPRS2_PATH = Path("data/outputs/xfp_rprs2_projections.csv")

REQUIRED_RPRS2_COLUMNS = {
    "rank",
    "pitcher",
    "name_api",
    "role_lag1",
    "sv_lag1",
    "hld_lag1",
    "g_to",
    "sv_to",
    "hld_to",
    "gf_to",
    "gf_pct_to",
    "sv_per_g_to",
    "xfp_full_year",
    "xfp_p25",
    "xfp_p75",
    "xfp_ros",
    "xfp_ros_p25",
    "xfp_ros_p75",
    "replacement_xfp",
    "replacement_delta",
    "signal",
}


@pytest.fixture(scope="module")
def rprs2_columns() -> set[str]:
    if not RPRS2_PATH.exists():
        pytest.skip(f"{RPRS2_PATH} not present in this checkout")
    df = pd.read_csv(RPRS2_PATH, nrows=1)
    return set(df.columns)


def test_rprs2_required_columns_present(rprs2_columns: set[str]) -> None:
    missing = REQUIRED_RPRS2_COLUMNS - rprs2_columns
    assert not missing, (
        f"xfp_rprs2_projections.csv is missing required columns: {sorted(missing)}. "
        "These are read by name by triangulate (RP card), live_marginal Phase 2 "
        "(fa_pool_RP snapshot), save_handcuffs, and the RP signal display contract."
    )
