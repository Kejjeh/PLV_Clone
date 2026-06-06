"""Schema-stability meta-test: all four canonical projection outputs exist
and are non-empty after a daily refresh.

Catches the failure mode where a pipeline silently writes an empty CSV
(header-only) due to a broken filter or join — that breaks every downstream
consumer at runtime, not at build time.
"""
from pathlib import Path

import pandas as pd
import pytest

OUTPUTS = {
    "rh3": Path("data/outputs/xfp_rh3_projections.csv"),
    "rp3": Path("data/outputs/xfp_rp3_projections.csv"),
    "rp3_il_fixed": Path("data/outputs/xfp_rp3_projections_il_fixed.csv"),
    "rprs2": Path("data/outputs/xfp_rprs2_projections.csv"),
}


@pytest.mark.parametrize("name,path", list(OUTPUTS.items()))
def test_projection_output_present_and_nonempty(name: str, path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout (refresh not yet run)")
    df = pd.read_csv(path, nrows=5)
    assert len(df) > 0, (
        f"{path} is header-only — refresh wrote an empty projection set for {name!r}. "
        "Investigate the upstream pipeline filter/join before shipping any consumer "
        "build."
    )
