"""rule9 — the position-agnostic Rule-9 lift scoring primitive.

The 9-rule multi-testing protocol's accountability step (Rule 9) compares a
baseline model's cross-year correlation against baseline+candidate, then checks
per-year sign consistency and a holdout lift. That arithmetic is pure over the
*outputs* of ``cross_year_eval`` (per-year r dicts + overall r) and is identical
whether the target is rh3, rp3, or rprs2 — yet it was re-derived inline in the
validation harness and ~34 bespoke ``validate_*.py`` scripts.

This module owns that math once. It takes already-computed cross-year results;
it does NOT run any model or touch data (those steps legitimately differ per
target — see ADR-0001). Tested with literals.
"""
from __future__ import annotations

import numpy as np


def rule9_lift(py_base: dict, py_full: dict, *, r_base: float, r_full: float,
               holdout_years=(2024, 2025)) -> dict:
    """Score a candidate feature's Rule-9 lift.

    Args:
        py_base / py_full: per-year cross-year results, ``{year: {'r': float}}``,
            for the baseline and baseline+candidate feature sets.
        r_base / r_full: the corresponding overall (pooled) cross-year r.
        holdout_years: years whose mean lift forms the holdout check.

    Returns dict: ``lift``, ``per_year_lift``, ``sign_match_years``,
    ``n_total_years``, ``holdout_lift`` (None if no holdout years present).
    """
    lift = r_full - r_base

    sign_match = 0
    n_total = 0
    per_year_lift: dict = {}
    for y in sorted(py_full.keys()):
        if y in py_base:
            d = py_full[y]['r'] - py_base[y]['r']
            per_year_lift[y] = round(d, 4)
            n_total += 1
            if d > 0:
                sign_match += 1

    holdout_full = [py_full[y]['r'] for y in holdout_years if y in py_full]
    holdout_base = [py_base[y]['r'] for y in holdout_years if y in py_base]
    holdout_lift = (
        float(np.mean(holdout_full) - np.mean(holdout_base))
        if holdout_full and holdout_base else None
    )

    return {
        'lift': lift,
        'per_year_lift': per_year_lift,
        'sign_match_years': sign_match,
        'n_total_years': n_total,
        'holdout_lift': holdout_lift,
    }
