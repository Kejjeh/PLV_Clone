"""Validation script: pa_to * hr_per_pa_to_sh interaction for rh3.

Pre-reg: data/research/validation_runs/pa_to_x_hr_per_pa_to_sh_2026-05-24.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_interaction_helper import run_interaction_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: pa_to_x_hr_per_pa_to_sh (rh3 interaction) ===")
    print("Pre-reg: data/research/validation_runs/pa_to_x_hr_per_pa_to_sh_2026-05-24.md")
    run_interaction_eval(
        name="pa_to_x_hr_per_pa_to_sh",
        col_a="pa_to",
        col_b="hr_per_pa_to_sh",
        expected_sign="+",
    )


if __name__ == "__main__":
    main()
