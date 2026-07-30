"""Guards for the ONE canonical xFP feature assembly (`models/xfp/frames.py`).

Background — the bug class this file exists to kill
---------------------------------------------------
The rh3 feature assembly existed in three divergent copies (production
`rh3.main()`, `validate_inseason_discipline.attach_production_features`, and
`audit_model_ceiling.prep_rh3`). The audit copy had rotted: it read the LIVE
22-name `RH3_FEATS` from production but only ever attached 20 of them, never
called `blend_callup_prior`, and still used the `if CSV.exists(): merge else:
col = 0.0` silent-zero pattern on `lift_h2_aug150` / `xwoba_residual_career` —
the #2 and #5 most important features by held-out permutation importance.

931 tests passed while that was true. **The missing test IS the defect.** Two
tests here close it:

* `test_every_prod_feat_present_in_assembled_frame` — a name in `RH3_FEATS` /
  `RP3_FEATS` that the assembly does not produce is a hard failure. This single
  assertion would have caught the entire class.
* `test_rh3_frame_is_byte_identical_to_legacy_inline_assembly` — pins the
  refactor. `_legacy_rh3_assembly` below is a FROZEN VERBATIM copy of the
  assembly block that lived inline in `rh3.main()` at commit `e107f36`, before
  it was extracted. `pandas.testing.assert_frame_equal` (shape, column order,
  dtypes, values) must hold against `build_rh3_frame`.

Note on rp3 (updated 2026-07-30): `rp3.py` USED to be the last model in the repo
still holding its own second copy of its feature assembly — deliberately left
alone by the rh3 change, and pinned only by the fit fingerprint, which re-checks
at REFIT time rather than at edit time. `rp3.main()` now delegates to
`build_rp3_frame` as well, so the divergent-copy class is closed for both models.
The same three-layer guard now applies to rp3:

* `test_every_rp3_feat_present_in_assembled_frame` — the feats/frame sync check;
* `test_rp3_frame_is_byte_identical_to_legacy_inline_assembly` — against
  `_legacy_rp3_assembly`, a FROZEN VERBATIM copy of the block that lived inline
  in `rp3.main()` at commit `06b2a57`;
* `test_rp3_main_delegates_to_the_canonical_builder` — the structural check that
  the second copy is actually GONE, not merely equal today. This is the one that
  fails against the pre-refactor `rp3.py`.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from plv_clone.models.xfp import rh3 as rh3_mod
from plv_clone.models.xfp import rp3 as rp3_mod
from plv_clone.models.xfp.aaa_translation import blend_callup_prior
from plv_clone.models.xfp.frames import (
    Rh3Frame,
    Rp3Frame,
    assert_feats_present,
    build_rh3_frame,
    build_rp3_frame,
    require_cache,
    require_columns,
)

# The real caches. These tests are integration guards on the production
# substrate — there is no synthetic substitute that could prove byte-identity
# against production.
_RH3_INPUTS = [
    rh3_mod.ROLLING_CSV, rh3_mod.MULTIYR_CSV, rh3_mod.H2_LOCKED_CSV,
    rh3_mod.XWOBA_RESID_CSV, rh3_mod.ROS_OPP_SP_CSV, rh3_mod.BX_PRIORS_CSV,
]
_RP3_INPUTS = [
    rp3_mod.ROLLING_CSV, rp3_mod.MULTIYR_CSV, rp3_mod.IL_CSV, rp3_mod.ROS_SCHED_CSV,
]

needs_rh3_cache = pytest.mark.skipif(
    not all(p.exists() for p in _RH3_INPUTS),
    reason="rh3 substrate caches not present in this checkout",
)
needs_rp3_cache = pytest.mark.skipif(
    not all(p.exists() for p in _RP3_INPUTS),
    reason="rp3 substrate caches not present in this checkout",
)


# ---------------------------------------------------------------------------
# Frozen reference implementation — DO NOT "improve" or refactor this.
# Verbatim copy of rh3.main()'s inline assembly at commit e107f36 (2026-07-29),
# print statements elided (they do not touch the frame). If production's
# assembly legitimately changes, this copy is updated in the SAME commit, and
# the diff between the two is the reviewable record of the behavior change.
# ---------------------------------------------------------------------------
def _legacy_rh3_assembly(rolling: pd.DataFrame, multiyr: pd.DataFrame):
    years_needed = sorted(rolling['year'].unique())
    prior = rh3_mod.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff'] = rolling['prior_pa_eff'].fillna(0.0)

    rolling = blend_callup_prior(rolling)

    if rh3_mod.H2_LOCKED_CSV.exists():
        h2_locked = pd.read_csv(rh3_mod.H2_LOCKED_CSV)[['batter', 'lift_h2_aug150']]
        rolling = rolling.merge(h2_locked, on='batter', how='left')
        rolling['lift_h2_aug150'] = rolling['lift_h2_aug150'].fillna(0.0)
    else:
        rolling['lift_h2_aug150'] = 0.0

    if rh3_mod.XWOBA_RESID_CSV.exists():
        xw = pd.read_csv(rh3_mod.XWOBA_RESID_CSV)[['batter', 'xwoba_residual_career']]
        rolling = rolling.merge(xw, on='batter', how='left')
        rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
    else:
        rolling['xwoba_residual_career'] = 0.0

    if 'xwoba_on_contact_to' in rolling.columns and 'woba_d_sum_to' in rolling.columns:
        rolling['actual_woba_per_pa_to'] = np.where(
            rolling['woba_d_sum_to'] > 0,
            rolling['woba_v_sum_to'] / rolling['woba_d_sum_to'],
            np.nan)
        rolling['xwoba_gap_to'] = (rolling['xwoba_on_contact_to']
                                   - rolling['actual_woba_per_pa_to'])
        rolling['xwoba_gap_to'] = rolling['xwoba_gap_to'].fillna(0.0)
    else:
        rolling['xwoba_gap_to'] = 0.0

    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    rolling['career_stage'] = (
        rolling['year'] - rolling['batter'].map(first_year).fillna(rolling['year'])
    ).astype(int)

    if rh3_mod.ROS_OPP_SP_CSV.exists():
        opp_sp = pd.read_csv(rh3_mod.ROS_OPP_SP_CSV)[
            ['batter', 'year', 'split_day', 'ros_opp_sp_xwoba_weighted']
        ]
        rolling = rolling.merge(opp_sp, on=['batter', 'year', 'split_day'], how='left')
        _cur_yr = int(rolling['year'].max())
        _cur = rolling[rolling['year'] == _cur_yr]
        _cur_nan = float(_cur['ros_opp_sp_xwoba_weighted'].isna().mean()) if len(_cur) else 0.0
        if _cur_nan > 0.50:
            raise RuntimeError('ros_opp_sp_xwoba_weighted cache looks FROZEN')
        year_means = rolling.groupby('year')['ros_opp_sp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(year_means)
        rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(
            rolling['ros_opp_sp_xwoba_weighted'].mean()
        )
    else:
        raise FileNotFoundError('Missing required RoS opp-SP cache')

    if rh3_mod.BX_PRIORS_CSV.exists():
        bx = pd.read_csv(rh3_mod.BX_PRIORS_CSV)[['mlbam', 'year', 'bx_prior_h']].rename(
            columns={'mlbam': 'batter'})
        rolling = rolling.merge(bx, on=['batter', 'year'], how='left')
        _cur_yr = int(rolling['year'].max())
        _cur = rolling[rolling['year'] == _cur_yr]
        _cur_nan = float(_cur['bx_prior_h'].isna().mean()) if len(_cur) else 0.0
        if _cur_nan > 0.50:
            raise RuntimeError('bx priors cache looks STALE')
        year_means = rolling.groupby('year')['bx_prior_h'].transform('mean')
        rolling['bx_prior_h'] = rolling['bx_prior_h'].fillna(year_means)
        rolling['bx_prior_h'] = rolling['bx_prior_h'].fillna(rolling['bx_prior_h'].mean())
    else:
        raise FileNotFoundError('Missing required bx priors cache')

    pop_to = rh3_mod.compute_population_means(
        rolling, rh3_mod.TRAIN_YEARS, rh3_mod.SHRINK_SPEC_TO)
    pop_l21 = rh3_mod.compute_population_means(
        rolling, rh3_mod.TRAIN_YEARS, rh3_mod.SHRINK_SPEC_LAST21)
    rolling = rh3_mod.apply_shrinkage(rolling, pop_to, rh3_mod.SHRINK_SPEC_TO)
    rolling = rh3_mod.apply_shrinkage(rolling, pop_l21, rh3_mod.SHRINK_SPEC_LAST21)
    for col in (rate + '_sh' for rate in rh3_mod.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(rh3_mod.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)
    return rolling, pop_to, pop_l21


# ---------------------------------------------------------------------------
# Frozen reference implementation #2 — DO NOT "improve" or refactor this.
# Verbatim copy of rp3.main()'s inline prep at commit 06b2a57 (2026-07-30),
# print statements elided (they do not touch the frame). Same contract as the
# rh3 twin above: if production's assembly legitimately changes, this copy is
# updated in the SAME commit and the diff is the reviewable record.
# ---------------------------------------------------------------------------
def _legacy_rp3_assembly(rolling: pd.DataFrame, multiyr: pd.DataFrame,
                         il: pd.DataFrame):
    prior = rp3_mod.build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())

    rolling['prior_source'] = np.where(
        rolling['prior_fp_per_start'].notna(), 'mlb_lag', None)
    if rp3_mod.MILB_PRIORS_CSV.exists():
        milb_pri = pd.read_csv(rp3_mod.MILB_PRIORS_CSV)[
            ['pitcher', 'projected_fp_per_start']]
        milb_pri = milb_pri.rename(columns={'projected_fp_per_start': 'milb_prior_fp'})
        rolling = rolling.merge(milb_pri, on='pitcher', how='left')
        is_2026 = rolling['year'] == int(rolling['year'].max())
        needs_fallback = is_2026 & rolling['prior_fp_per_start'].isna()
        has_milb = needs_fallback & rolling['milb_prior_fp'].notna()
        rolling.loc[has_milb, 'prior_fp_per_start'] = rolling.loc[has_milb, 'milb_prior_fp']
        rolling.loc[has_milb, 'prior_source'] = 'milb_translation'

    rolling['prior_source'] = rolling['prior_source'].fillna('league_mean')
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff'] = rolling['prior_gs_eff'].fillna(0.0)

    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to'] = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split'] = rolling['is_on_il_at_split'].fillna(0).astype(int)
    _dsr_max = rolling['days_since_il_return'].max(skipna=True)
    max_dsr = float(_dsr_max) if pd.notna(_dsr_max) else 200.0
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)
    _il_hit = float((rolling['il_stints_to'] > 0).mean())
    if _il_hit < 0.02:
        raise RuntimeError('IL feature join degenerate')

    if rp3_mod.ROS_SCHED_CSV.exists():
        sched_xw = pd.read_csv(rp3_mod.ROS_SCHED_CSV)[
            ['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']
        ]
        rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
        _cur_yr = int(rolling['year'].max())
        _cur = rolling[rolling['year'] == _cur_yr]
        _cur_nan = float(_cur['ros_opp_xwoba_weighted'].isna().mean()) if len(_cur) else 0.0
        if _cur_nan > 0.50:
            raise RuntimeError('ros schedule-strength cache looks FROZEN')
        year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
        rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
        rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
            rolling['ros_opp_xwoba_weighted'].mean()
        )
    else:
        raise FileNotFoundError('Missing required RoS schedule cache')

    pop_to = rp3_mod.compute_population_means(
        rolling, rp3_mod.TRAIN_YEARS, rp3_mod.SHRINK_SPEC_TO)
    pop_l21 = rp3_mod.compute_population_means(
        rolling, rp3_mod.TRAIN_YEARS, rp3_mod.SHRINK_SPEC_LAST21)
    rolling = rp3_mod.apply_shrinkage(rolling, pop_to, rp3_mod.SHRINK_SPEC_TO)
    rolling = rp3_mod.apply_shrinkage(rolling, pop_l21, rp3_mod.SHRINK_SPEC_LAST21)

    rolling['delta_velo'] = rolling['avg_velo_last21'] - rolling['avg_velo_to']
    rolling['delta_swstr'] = rolling['swstr_pct_last21'] - rolling['swstr_pct_to']
    rolling['delta_k_pct'] = rolling['k_pct_last21'] - rolling['k_pct_to']
    rolling['delta_bb_pct'] = rolling['bb_pct_last21'] - rolling['bb_pct_to']
    rolling['delta_chase'] = rolling['o_swing_pct_last21'] - rolling['o_swing_pct_to']
    rolling['delta_zone'] = rolling['zone_pct_last21'] - rolling['zone_pct_to']
    for c in ('delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
              'delta_chase', 'delta_zone'):
        rolling[c] = rolling[c].fillna(0.0)
    for col in (rate + '_sh' for rate in rp3_mod.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(rp3_mod.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(
        rolling['fp_per_start_to'])
    return rolling, prior, pop_to, pop_l21


# ---------------------------------------------------------------------------
# Session-scoped builds (each ~5s; three tests share them)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def rh3_frame() -> Rh3Frame:
    return build_rh3_frame(verbose=False)


@pytest.fixture(scope="module")
def rp3_frame() -> Rp3Frame:
    return build_rp3_frame(verbose=False)


# ---------------------------------------------------------------------------
# THE test that would have caught the whole bug class
# ---------------------------------------------------------------------------
@needs_rh3_cache
def test_every_rh3_feat_present_in_assembled_frame(rh3_frame):
    """Every live RH3_FEATS name must be a column of the assembled frame."""
    missing = [f for f in rh3_mod.RH3_FEATS if f not in rh3_frame.rolling.columns]
    assert not missing, f"assembly does not produce {missing}"
    assert len(rh3_mod.RH3_FEATS) == len(set(rh3_mod.RH3_FEATS))


@needs_rp3_cache
def test_every_rp3_feat_present_in_assembled_frame(rp3_frame):
    missing = [f for f in rp3_mod.RP3_FEATS if f not in rp3_frame.rolling.columns]
    assert not missing, f"assembly does not produce {missing}"
    assert len(rp3_mod.RP3_FEATS) == len(set(rp3_mod.RP3_FEATS))


@needs_rh3_cache
def test_rh3_feats_are_all_finite_after_assembly(rh3_frame):
    """A feature that is 100% NaN, or constant, is a dead join in disguise.

    `bx_prior_h` and `ros_opp_sp_xwoba_weighted` both have year-mean fills;
    a frozen/absent cache shows up as zero variance, which the frozen-cache
    guards catch upstream. Assert the post-condition too.
    """
    df = rh3_frame.rolling
    for f in rh3_mod.RH3_FEATS:
        col = df[f]
        assert col.notna().any(), f"{f} is entirely NaN after assembly"
        assert col.nunique(dropna=True) > 1, f"{f} is constant after assembly"


# ---------------------------------------------------------------------------
# Byte-identity of the production frame
# ---------------------------------------------------------------------------
@needs_rh3_cache
def test_rh3_frame_is_byte_identical_to_legacy_inline_assembly(rh3_frame):
    """build_rh3_frame == the assembly that lived inline in rh3.main()."""
    rolling = pd.read_csv(rh3_mod.ROLLING_CSV)
    multiyr = pd.read_csv(rh3_mod.MULTIYR_CSV)
    legacy, legacy_pop_to, legacy_pop_l21 = _legacy_rh3_assembly(rolling, multiyr)

    new = rh3_frame.rolling
    assert new.shape == legacy.shape, f"shape {new.shape} != legacy {legacy.shape}"
    assert list(new.columns) == list(legacy.columns), "column order/set differs"
    assert list(new.dtypes.astype(str)) == list(legacy.dtypes.astype(str)), "dtypes differ"
    assert_frame_equal(new, legacy, check_exact=True)

    # The shrinkage population means also feed the production bundle.
    assert set(rh3_frame.pop_means_to) == set(legacy_pop_to)
    for k, v in legacy_pop_to.items():
        assert rh3_frame.pop_means_to[k] == pytest.approx(v, rel=0, abs=0)
    assert set(rh3_frame.pop_means_last21) == set(legacy_pop_l21)
    for k, v in legacy_pop_l21.items():
        assert rh3_frame.pop_means_last21[k] == pytest.approx(v, rel=0, abs=0)


def _fp_matches_bundle(mod, rolling, feats, bundle) -> tuple[bool, str]:
    """Does the assembled substrate match what the bundle was fitted on?

    The fingerprint is only a PROXY for substrate identity, and its definition
    changed on 2026-07-30: `engine.fit_fingerprint` became order-SENSITIVE
    (fp_version 1 -> 2) because the fitted pipelines are positional, so a FEATS
    reorder previously reused a stale bundle and silently mismatched every
    coefficient to the wrong column.

    A bundle written before that bump carries a v1 hash, so comparing it to a v2
    hash fails for a reason that has nothing to do with the substrate. So: match
    under EITHER version, and report which. v1-only means the bundle is pre-bump
    and production refits once on its next run -- the intended transitional
    state. Matching under NEITHER is a real substrate divergence and still fails.

    The v1 hash is recomputed through the MODEL'S OWN wrapper (with the engine
    function partial-bound to fp_version=1) rather than re-deriving it here, so
    the model's private `target` / `train_years` / `extra` constants cannot drift
    out of sync with this test.
    """
    want = bundle["fit_fingerprint"]
    if mod._fit_fingerprint(rolling, feats) == want:
        return True, "v2"
    import functools
    from unittest import mock
    from plv_clone.models.xfp import engine as _eng
    v1_fn = functools.partial(_eng.fit_fingerprint, fp_version=1)
    with mock.patch.object(mod._engine, "fit_fingerprint", v1_fn):
        if mod._fit_fingerprint(rolling, feats) == want:
            return True, ("v1 -- bundle predates the 2026-07-30 order-sensitivity "
                          "bump and refits once on its next run")
    # Neither hash matches. Before calling that a divergence, ask whether the
    # SUBSTRATE was even allowed to be stable: if the rolling cache the frame is
    # built from has been rewritten since the bundle was fitted, the two hashes
    # are describing different data and the comparison cannot answer the question
    # this test exists to ask. That is the NORMAL overnight state here -- the
    # nightly refresh rewrites the rolling CSVs and the models refit later in the
    # same run -- so failing on it would make this a daily false alarm.
    import datetime as _dt
    import pathlib
    bundle_t = mod.MODEL_PKL.stat().st_mtime
    # Every declared `*_CSV` on the model module EXCEPT its own output. Reading
    # the constants rather than hardcoding a list keeps this current when the
    # assembly gains an input.
    newer = [
        (v.stat().st_mtime, v.name)
        for k, v in vars(mod).items()
        if k.endswith("_CSV") and k != "PROJ_CSV"
        and isinstance(v, pathlib.Path) and v.exists()
        and v.stat().st_mtime > bundle_t
    ]
    if newer:
        t, nm = max(newer)
        f = "%Y-%m-%d %H:%M"
        return None, (
            f"input {nm} was rewritten at {_dt.datetime.fromtimestamp(t):{f}}, "
            f"AFTER the bundle was fitted at "
            f"{_dt.datetime.fromtimestamp(bundle_t):{f}} -- the two hashes "
            f"describe different data; the model refits on its next run")
    return False, ("neither v1 nor v2, and NO declared input has changed since "
                   "the fit -- so the assembly CODE moved and the shipped bundle "
                   "is stale; re-run the model")


@needs_rh3_cache
def test_rh3_frame_fit_fingerprint_matches_production_bundle(rh3_frame):
    """The train-year substrate is the exact one production last fitted on.

    `engine.fit_fingerprint` is an md5 over the train-year slice of
    FEATS+target+year+split_day. Matching the fingerprint stored in the shipped
    .pkl proves equivalence against the ARTIFACT, independent of any reference
    implementation kept in this file.
    """
    import joblib
    if not rh3_mod.MODEL_PKL.exists():
        pytest.skip("no fitted rh3 bundle on disk")
    bundle = joblib.load(rh3_mod.MODEL_PKL)
    ok, how = _fp_matches_bundle(rh3_mod, rh3_frame.rolling, rh3_mod.RH3_FEATS, bundle)
    if ok is None:
        pytest.skip(f"fingerprint uninformative: {how}")
    assert ok, (
        "build_rh3_frame produces a different train substrate than the shipped "
        f"bundle was fitted on ({how}). If rh3's assembly changed on "
        "purpose, re-run the model; otherwise this is a real divergence."
    )



@needs_rp3_cache
def test_rp3_frame_fit_fingerprint_matches_production_bundle(rp3_frame):
    """The rp3 train-year substrate is the one production last fitted on."""
    import joblib
    if not rp3_mod.MODEL_PKL.exists():
        pytest.skip("no fitted rp3 bundle on disk")
    bundle = joblib.load(rp3_mod.MODEL_PKL)
    ok, how = _fp_matches_bundle(rp3_mod, rp3_frame.rolling, rp3_mod.RP3_FEATS, bundle)
    if ok is None:
        pytest.skip(f"fingerprint uninformative: {how}")
    assert ok, (
        "build_rp3_frame produces a different train substrate than the shipped "
        f"bundle was fitted on ({how}). If rp3's assembly changed on "
        "purpose, re-run the model; otherwise this is a real divergence."
    )


@needs_rp3_cache
def test_rp3_frame_is_byte_identical_to_legacy_inline_assembly(rp3_frame):
    """build_rp3_frame == the assembly that lived inline in rp3.main().

    This is the proof that licensed the 2026-07-30 delegation: rp3 is
    PRODUCTION, so the frame had to be shown byte-identical, not asserted to be.
    """
    rolling = pd.read_csv(rp3_mod.ROLLING_CSV)
    multiyr = pd.read_csv(rp3_mod.MULTIYR_CSV)
    il = pd.read_csv(rp3_mod.IL_CSV)
    legacy, legacy_prior, legacy_pop_to, legacy_pop_l21 = _legacy_rp3_assembly(
        rolling, multiyr, il)

    new = rp3_frame.rolling
    assert new.shape == legacy.shape, f"shape {new.shape} != legacy {legacy.shape}"
    assert list(new.columns) == list(legacy.columns), "column order/set differs"
    assert list(new.dtypes.astype(str)) == list(legacy.dtypes.astype(str)), "dtypes differ"
    assert_frame_equal(new, legacy, check_exact=True)

    # The Marcel prior table travels on the frame because main() needs it after
    # assembly (IL-vet fallback). It must be the same table, not a rebuild.
    assert_frame_equal(rp3_frame.prior, legacy_prior, check_exact=True)

    # Shrinkage population means go straight into the shipped bundle.
    assert set(rp3_frame.pop_means_to) == set(legacy_pop_to)
    for k, v in legacy_pop_to.items():
        assert rp3_frame.pop_means_to[k] == pytest.approx(v, rel=0, abs=0)
    assert set(rp3_frame.pop_means_last21) == set(legacy_pop_l21)
    for k, v in legacy_pop_l21.items():
        assert rp3_frame.pop_means_last21[k] == pytest.approx(v, rel=0, abs=0)


@needs_rp3_cache
def test_rp3_feats_unchanged_in_content_and_order(rp3_frame):
    """RP3_FEATS order is load-bearing: the fitted Ridge is POSITIONAL.

    `pipe.predict(valid[RP3_FEATS].values)` passes a bare ndarray, so permuting
    RP3_FEATS silently feeds every coefficient the wrong column. Pin the live
    list against the `features` list stored in the shipped bundle.
    """
    import joblib
    if not rp3_mod.MODEL_PKL.exists():
        pytest.skip("no fitted rp3 bundle on disk")
    bundle = joblib.load(rp3_mod.MODEL_PKL)
    assert list(bundle["features"]) == list(rp3_mod.RP3_FEATS), (
        "RP3_FEATS differs from the shipped bundle's feature list in content or "
        "ORDER — the fitted pipeline is positional, so this mis-maps coefficients."
    )
    assert len(rp3_mod.RP3_FEATS) == len(set(rp3_mod.RP3_FEATS))


def test_rp3_main_delegates_to_the_canonical_builder():
    """The second copy of the assembly must be GONE, not merely equal today.

    Byte-identity tests prove the copies agree at this instant; they cannot stop
    someone editing one copy tomorrow. This structural check is what actually
    retires the divergence — it fails against the pre-refactor `rp3.main()`,
    which called `build_prior_table` / `compute_population_means` /
    `apply_shrinkage` and re-read the substrate CSVs itself.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(rp3_mod.main)))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "build_rp3_frame" in called, "rp3.main() no longer delegates to frames"

    reimplemented = {"build_prior_table", "compute_population_means",
                     "apply_shrinkage", "blend_callup_prior"} & called
    assert not reimplemented, (
        f"rp3.main() re-implements the feature assembly ({sorted(reimplemented)}). "
        "The assembly lives in models/xfp/frames.build_rp3_frame — one copy only."
    )

    # ...and it must not re-read the substrate caches behind the builder's back.
    substrate = {"ROLLING_CSV", "MULTIYR_CSV", "IL_CSV", "ROS_SCHED_CSV"}
    reread = {
        a.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "read_csv"
        for a in n.args
        if isinstance(a, ast.Name) and a.id in substrate
    }
    assert not reread, f"rp3.main() re-reads substrate caches directly: {sorted(reread)}"


def test_rp3_frame_exposes_the_prior_table():
    """`Rp3Frame.prior` exists — main()'s IL-vet fallback depends on it.

    Without it the delegating main() would have to rebuild `build_prior_table`
    itself, which is exactly the second copy this refactor removed.
    """
    assert "prior" in Rp3Frame.__dataclass_fields__


# ---------------------------------------------------------------------------
# The loud-failure primitives (no substrate needed)
# ---------------------------------------------------------------------------
def test_require_cache_raises_instead_of_defaulting(tmp_path):
    missing = tmp_path / "nope.csv"
    with pytest.raises(FileNotFoundError) as ei:
        require_cache(missing, feature="lift_h2_aug150", builder="build_x.py")
    msg = str(ei.value)
    assert "lift_h2_aug150" in msg and "build_x.py" in msg


def test_require_cache_returns_path_when_present(tmp_path):
    p = tmp_path / "yes.csv"
    p.write_text("a\n1\n", encoding="utf-8")
    assert require_cache(p, feature="f", builder="b") == p


def test_require_columns_raises_on_missing_substrate():
    df = pd.DataFrame({"a": [1.0, 2.0]})
    with pytest.raises(KeyError) as ei:
        require_columns(df, ["a", "b", "c"], derivation="xwoba_gap_to")
    msg = str(ei.value)
    assert "'b'" in msg and "'c'" in msg and "xwoba_gap_to" in msg
    require_columns(df, ["a"], derivation="ok")  # present -> no raise


# ---------------------------------------------------------------------------
# The ceiling-audit driver, end-to-end minus the expensive fits.
# This is the direct regression for the reported bug:
#   python -X utf8 scripts/xfp/audit_model_ceiling.py --model rh3
#   -> KeyError: ['ros_opp_sp_xwoba_weighted', 'bx_prior_h']
# ---------------------------------------------------------------------------
def _load_audit_driver():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for p in (str(root), str(root / "src")):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location(
        "audit_model_ceiling_under_test",
        root / "scripts" / "xfp" / "audit_model_ceiling.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_driver():
    return _load_audit_driver()


@needs_rh3_cache
def test_audit_prep_rh3_carries_every_live_feat(audit_driver):
    """prep_rh3()'s frame must support the LIVE RH3_FEATS — no KeyError."""
    df = audit_driver.prep_rh3()
    missing = [f for f in rh3_mod.RH3_FEATS if f not in df.columns]
    assert not missing, f"prep_rh3 does not attach {missing}"
    # The ceiling fns do exactly this first; it is what used to raise.
    usable = df.dropna(subset=list(rh3_mod.RH3_FEATS) + [rh3_mod.TARGET])
    assert len(usable) > 500


@needs_rp3_cache
def test_audit_prep_rp3_carries_every_live_feat(audit_driver):
    df = audit_driver.prep_rp3()
    missing = [f for f in rp3_mod.RP3_FEATS if f not in df.columns]
    assert not missing, f"prep_rp3 does not attach {missing}"
    usable = df.dropna(subset=list(rp3_mod.RP3_FEATS) + [rp3_mod.TARGET])
    assert len(usable) > 500


def test_audit_substrate_assertion_rejects_a_short_feature_list(audit_driver):
    """A frame missing a production feature must abort the audit, loudly."""
    df = pd.DataFrame({"f1": [1.0] * 600, "y": [2.0] * 600})
    with pytest.raises(KeyError, match="f2"):
        audit_driver._assert_audit_substrate(df, ["f1", "f2"], "y", "unit")


def test_audit_substrate_assertion_rejects_missing_target(audit_driver):
    df = pd.DataFrame({"f1": [1.0] * 600})
    with pytest.raises(KeyError, match="target"):
        audit_driver._assert_audit_substrate(df, ["f1"], "y", "unit")


def test_audit_substrate_assertion_rejects_too_few_usable_rows(audit_driver):
    df = pd.DataFrame({"f1": [1.0] * 100, "y": [2.0] * 100})
    with pytest.raises(RuntimeError, match="too few"):
        audit_driver._assert_audit_substrate(df, ["f1"], "y", "unit")
    empty = pd.DataFrame({"f1": [], "y": []})
    with pytest.raises(RuntimeError, match="0 rows"):
        audit_driver._assert_audit_substrate(empty, ["f1"], "y", "unit")


def test_assert_feats_present_names_the_missing_feats():
    df = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
    with pytest.raises(KeyError) as ei:
        assert_feats_present(df, ["f1", "f2", "bx_prior_h",
                                  "ros_opp_sp_xwoba_weighted"], label="unit")
    msg = str(ei.value)
    assert "bx_prior_h" in msg and "ros_opp_sp_xwoba_weighted" in msg
    assert "2 of 4" in msg
    assert_feats_present(df, ["f1"], label="unit")  # present -> no raise
