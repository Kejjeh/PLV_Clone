"""Validation script: prior_pa_eff * pa_to interaction for rh3.

Pre-reg: data/research/validation_runs/prior_pa_eff_x_pa_to_2026-05-24.md

Column-name note: `prior_pa_eff` is created in
`_validate_rh3_v3_helper.load_and_prep_rh3_inputs()` via Marcel prior
merge with fillna(0.0). It IS in RH3_FEATS.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _validate_rh3_interaction_helper import run_interaction_eval  # noqa: E402


def main() -> None:
    print("=== /validate-feature: prior_pa_eff_x_pa_to (rh3 interaction) ===")
    print("Pre-reg: data/research/validation_runs/prior_pa_eff_x_pa_to_2026-05-24.md")
    run_interaction_eval(
        name="prior_pa_eff_x_pa_to",
        col_a="prior_pa_eff",
        col_b="pa_to",
        expected_sign="+",
    )


if __name__ == "__main__":
    main()
