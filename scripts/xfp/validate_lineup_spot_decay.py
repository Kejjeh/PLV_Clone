"""Validation: lineup_spot_to * exp(-split_day/30) decay candidate for rh3.

Pre-reg: data/research/validation_runs/lineup_spot_decay_2026-05-24.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_piecewise_helper import run_piecewise_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: lineup_spot_decay (exp(-split_day/30)) ===")
    print("Pre-reg: data/research/validation_runs/lineup_spot_decay_2026-05-24.md")

    def transform(df):
        decay = np.exp(-df["split_day"].astype(float) / 30.0)
        return df["lineup_spot_to"].astype(float) * decay

    run_piecewise_eval(
        name="lineup_spot_decay",
        transform=transform,
        expected_sign="-",
        description="lineup_spot_to * exp(-split_day/30)",
    )


if __name__ == "__main__":
    main()
