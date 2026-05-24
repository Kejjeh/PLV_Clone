"""Validation script: lineup_spot_to * split_day interaction for rh3.

Pre-reg: data/research/validation_runs/lineup_spot_x_split_day_2026-05-24.md

Column-name note (per spec verification step): the rolling cache
column is `lineup_spot_to` (PA-weighted season-to-date lineup spot).
`split_day` is the cutoff-day index used by all rh3 pipeline framing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_interaction_helper import run_interaction_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: lineup_spot_x_split_day (rh3 interaction) ===")
    print("Pre-reg: data/research/validation_runs/lineup_spot_x_split_day_2026-05-24.md")
    run_interaction_eval(
        name="lineup_spot_x_split_day",
        col_a="lineup_spot_to",
        col_b="split_day",
        expected_sign="-",
    )


if __name__ == "__main__":
    main()
