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

Note on rp3: `rp3.py` was deliberately NOT refactored to delegate (it is
outside the change's file set), so it still holds its own copy of the prep.
`test_frame_fit_fingerprint_matches_production_bundle` pins `build_rp3_frame`
to it empirically instead — the fit fingerprint is an md5 over the train-year
substrate, so a match proves the frame this module builds is the exact frame
production last fitted on.
"""
from __future__ import annotations

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
    fp = rh3_mod._fit_fingerprint(rh3_frame.rolling, rh3_mod.RH3_FEATS)
    assert fp == bundle["fit_fingerprint"], (
        "build_rh3_frame produces a different train substrate than the shipped "
        "bundle was fitted on. If rh3's assembly changed on purpose, re-run "
        "the model; otherwise this is a real divergence."
    )


@needs_rp3_cache
def test_rp3_frame_fit_fingerprint_matches_production_bundle(rp3_frame):
    """Pins build_rp3_frame to rp3.main()'s (unrefactored) inline prep."""
    import joblib
    if not rp3_mod.MODEL_PKL.exists():
        pytest.skip("no fitted rp3 bundle on disk")
    bundle = joblib.load(rp3_mod.MODEL_PKL)
    fp = rp3_mod._fit_fingerprint(rp3_frame.rolling, rp3_mod.RP3_FEATS)
    assert fp == bundle["fit_fingerprint"], (
        "build_rp3_frame has drifted from rp3.main()'s own prep — rp3.py still "
        "holds a second copy of the assembly; reconcile them."
    )


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
