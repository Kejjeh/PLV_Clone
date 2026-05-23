"""Entry-point shim — orchestration lives in plv_clone.models.xfp.rp3.

Per ADR-0001, the per-model file owns its own fit_and_project orchestration.
This shim preserves back-compat for external callers that historically did
`from xfp_rp3_pipeline import ...` or `from scripts.xfp import xfp_rp3_pipeline as rp3mod`.
Re-exports the constants, helpers, and `main` from the package module.
"""
from __future__ import annotations

from plv_clone.models.xfp.rp3 import *  # noqa: F401,F403  re-export public names
from plv_clone.models.xfp.rp3 import (  # noqa: F401  explicit re-export for symbols external scripts reference
    # Constants
    ROOT,
    ROLLING_CSV, MULTIYR_CSV, IL_CSV,
    TEAM_STR_CSV, SCHEDULE_CSV, MILB_PRIORS_CSV,
    MODEL_PKL, PROJ_CSV,
    TARGET, EVAL_GS_MIN, ROS_GS_MIN, TRAIN_YEARS, PRIOR_K_GS,
    MARCEL_WEIGHTS,
    SHRINK_SPEC_TO, SHRINK_SPEC_LAST21, RP3_FEATS,
    REPLACEMENT_SP_RANK,
    # Helpers
    _ensure_derived_denoms,
    build_prior_table,
    compute_population_means, apply_shrinkage,
    cross_year_eval, fit_residual_ci, train_final,
    compute_replacement_delta, apply_schedule_strength,
    lookup_sigma,
    main,
)


if __name__ == '__main__':
    main()
