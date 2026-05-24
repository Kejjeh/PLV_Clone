"""Entry-point shim — orchestration lives in plv_clone.models.xfp.rh3_april.

April-only variant of rh3 (substrate filtered to split_day <= 30, includes
lineup_spot_to in FEATS). Sibling to xfp_rh3_pipeline.py shim.
"""
from __future__ import annotations

from plv_clone.models.xfp.rh3_april import *  # noqa: F401,F403
from plv_clone.models.xfp.rh3_april import (  # noqa: F401
    ROOT,
    ROLLING_CSV, MULTIYR_CSV, H2_PROJ_CSV, IL_CSV, MASTER_HITTER,
    MODEL_PKL, PROJ_CSV,
    H2_LOCKED_CSV, XWOBA_RESID_CSV,
    TARGET, EVAL_PA_MIN, ROS_PA_MIN, TRAIN_YEARS, PRIOR_K_PA,
    MARCEL_WEIGHTS, PA_PER_GAME_LEAGUE, SEASON_GAMES,
    APRIL_SPLIT_MAX,
    SHRINK_SPEC_TO, SHRINK_SPEC_LAST21, RH3_APRIL_FEATS,
    REPLACEMENT_RANK,
    _ensure_derived_denoms,
    build_prior_table,
    compute_population_means, apply_shrinkage,
    cross_year_eval, fit_residual_ci, train_final,
    lookup_sigma,
    main,
)


if __name__ == '__main__':
    main()
