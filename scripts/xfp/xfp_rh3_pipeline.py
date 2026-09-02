"""Entry-point shim — orchestration lives in plv_clone.models.xfp.rh3.

Per ADR-0001, the per-model file owns its own fit_and_project orchestration.
This shim preserves back-compat for external callers that historically did
`from xfp_rh3_pipeline import ...` or `from scripts.xfp import xfp_rh3_pipeline as rh3mod`.
Re-exports the constants, helpers, and `main` from the package module.
"""
from __future__ import annotations

from plv_clone.models.xfp.rh3 import *  # noqa: F401,F403  re-export public names
from plv_clone.models.xfp.rh3 import (  # noqa: F401  explicit re-export for symbols external scripts reference
    # Constants
    ROOT,
    ROLLING_CSV, MULTIYR_CSV, IL_CSV,
    MODEL_PKL, PROJ_CSV,
    H2_LOCKED_CSV, XWOBA_RESID_CSV,
    TARGET, EVAL_PA_MIN, ROS_PA_MIN, TRAIN_YEARS, PRIOR_K_PA,
    MARCEL_WEIGHTS, PA_PER_GAME_LEAGUE, SEASON_GAMES,
    SHRINK_SPEC_TO, SHRINK_SPEC_LAST21, RH3_FEATS,
    REPLACEMENT_RANK,
    # Helpers
    _ensure_derived_denoms,
    build_prior_table,
    compute_population_means, apply_shrinkage,
    cross_year_eval, fit_residual_ci, train_final,
    compute_replacement_delta,
    lookup_sigma,
    main,
)


if __name__ == '__main__':
    main()
