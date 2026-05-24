"""Validation: lineup_spot_to * I[split_day <= 60] piecewise candidate for rh3.

Pre-reg: data/research/validation_runs/lineup_spot_early_2026-05-24.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_piecewise_helper import run_piecewise_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: lineup_spot_early (piecewise, split_day<=60) ===")
    print("Pre-reg: data/research/validation_runs/lineup_spot_early_2026-05-24.md")

    def transform(df):
        mask = (df["split_day"] <= 60).astype(float)
        return df["lineup_spot_to"].astype(float) * mask

    run_piecewise_eval(
        name="lineup_spot_early",
        transform=transform,
        expected_sign="-",
        description="lineup_spot_to * I[split_day<=60]",
    )


if __name__ == "__main__":
    main()
