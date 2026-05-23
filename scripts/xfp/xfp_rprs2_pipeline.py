"""Entry-point shim — orchestration lives in plv_clone.models.xfp.rprs2.

Per ADR-0001, the per-model file owns its own fit_and_project orchestration.
No external callers currently import from this module, but we mirror the
re-export pattern used by the rh3/rp3 shims for consistency and future-proofing.
"""
from __future__ import annotations

from plv_clone.models.xfp.rprs2 import *  # noqa: F401,F403  re-export public names
from plv_clone.models.xfp.rprs2 import (  # noqa: F401
    # Constants
    ROOT,
    ROLLING_CSV, COUNTING_DIR, MODEL_PKL, PROJ_CSV,
    TARGET, EVAL_G_MIN, TRAIN_YEARS,
    BASE_FEATS, NEW_FEATS, FEATS_RPRS2,
    REPLACEMENT_RANK_RP,
    # Helpers
    cross_year_eval, role_change_mask,
    fit_residual_ci, train_final,
    lookup_sigma,
    main,
)


if __name__ == '__main__':
    main()
