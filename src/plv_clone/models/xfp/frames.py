"""frames.py — the ONE canonical xFP feature-assembly.

Why this module exists
----------------------
The rh3 feature assembly (Marcel prior -> AAA call-up blend -> career-profile
merges -> schedule-strength merge -> box-score prior merge -> shrinkage) had
drifted into **FOUR divergent copies** (this docstring said "three" when the
module was first written — an adversarial review found the fourth, and it was the
highest-traffic one; corrected 2026-07-29):

  1. ``rh3.main()``                                            (production)
  2. ``scripts/xfp/validate_inseason_discipline.py``           (validation harness)
  3. ``scripts/xfp/audit_model_ceiling.py::prep_rh3``          (ceiling audit)
  4. ``scripts/xfp/_validate_rh3_v3_helper.py``
     ``::load_and_prep_rh3_inputs``            (Rule-9 baseline for ~20 harnesses)

All four now delegate here.

Copy 3 had rotted in exactly the way a copied baseline always rots: it never
learned about ``ros_opp_sp_xwoba_weighted`` (promoted 2026-05-24),
``bx_prior_h`` (2026-07-10), or ``blend_callup_prior`` (2026-07-19), and it
still carried the ``if CSV.exists(): merge ... else: col = 0.0`` **silent-zero**
pattern that produced the -0.0368 baseline degradation documented in
``docs/rh3_harness_root_bug_2026-07-28.md``. It failed LOUDLY (``KeyError``), so
it could not have recorded a quietly-degraded number.

Copy 4 was the dangerous one. It is the baseline loader for roughly twenty
``/validate-feature`` harnesses, so every Rule-9 lift the repo has measured for a
hitter candidate was measured against it — and it carried the same silent-zero
pattern on ``lift_h2_aug150``, ``xwoba_residual_career``,
``ros_opp_sp_xwoba_weighted`` and ``bx_prior_h`` (ranked #2/#5/#7/#1 of 22 by
held-out permutation importance, 2026-07-29), while lacking production's two
frozen-cache guards. A stale cache there would have silently weakened the
BASELINE, inflating every candidate's apparent lift — the exact failure Rule 9
exists to prevent, inside the Rule-9 loader. It was measured LATENT at migration
(byte-equal to canonical on all 122 columns), so no recorded number is wrong.

So: one assembly, imported by every caller. Two invariants are enforced *here*,
inside the builder, so no caller can regress the class again:

  * **No silent defaults.** A missing required cache or a missing required
    substrate column raises. A validated feature never gets constant-filled
    just because its input vanished.
  * **The frame is self-validating.** Every name in ``RH3_FEATS`` /
    ``RP3_FEATS`` must be a column of the frame the builder returns, or it
    raises before the caller ever gets a chance to ``dropna(subset=FEATS)``
    and blow up (or worse, quietly proceed on a short feature list).

Production parity
-----------------
``build_rh3_frame`` is the code that used to live inline in ``rh3.main()``,
moved verbatim; ``rh3.main()`` now delegates to it. Byte-identity against the
pre-refactor assembly is asserted by ``tests/test_xfp_frames.py``, which keeps
a frozen verbatim copy of the old inline block as its reference implementation
and compares with ``pandas.testing.assert_frame_equal``.

``build_rp3_frame`` began as a faithful transcription of ``rp3.main()``'s prep
section, leaving rp3 as the LAST divergent copy in the repo — pinned only by a
fingerprint that re-checks at REFIT time rather than at edit time, so an edit to
one copy could sit undetected until the next refit. **2026-07-30: closed.**
``rp3.main()`` now delegates here, and the pre-refactor inline block is kept as
a frozen verbatim reference in ``tests/test_xfp_frames.py``
(``_legacy_rp3_assembly``) exactly as rh3's is.

Byte-identity was PROVEN before the switch, not assumed, on the real
2018-2026 cache (31,135 rows x 109 columns):

  * ``assert_frame_equal(check_exact=True)`` — shape, column order, dtypes and
    values all identical;
  * the shrinkage population means (which go into the shipped bundle) equal to
    the bit;
  * ``_fit_fingerprint`` equal across both assemblies AND equal to the
    ``fit_fingerprint`` in the shipped ``xfp_rp3_pipeline.pkl``
    (``46e24bc9b4187492b95a84fbc3bb57dd``);
  * ``cross_year_eval`` reproducing the bundle's recorded numbers from BOTH
    assemblies — r=0.5617, mae=2.8394, baseline r=0.5484, Delta r=+0.0133.

``RP3_FEATS`` is untouched in content and order (the fitted Ridge is positional,
so order is load-bearing); ``tests/test_xfp_frames.py`` pins it against the
``features`` list stored in the bundle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.models.xfp import rh3 as _rh3
from plv_clone.models.xfp import rp3 as _rp3


# ---------------------------------------------------------------------------
# Loud-failure helpers — the anti-silent-default primitives
# ---------------------------------------------------------------------------
def _noop(*_a, **_k) -> None:
    return None


def require_cache(path: Path, *, feature: str, builder: str) -> Path:
    """Return ``path``, or raise if it is missing.

    Replaces the ``if path.exists(): merge else: col = 0.0`` pattern. A
    validated feature must never be silently constant-filled because its cache
    disappeared — that is the 2026-07-28 root bug (-0.0368 cross-year r on the
    rh3 baseline, undetected for nine days behind confident-looking numbers).
    """
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Missing required cache for feature '{feature}': {path}. "
            f"Rebuild it with {builder}. Refusing to silently default a "
            f"validated feature (see docs/rh3_harness_root_bug_2026-07-28.md)."
        )
    return Path(path)


def require_columns(df: pd.DataFrame, cols: list[str], *, derivation: str) -> None:
    """Raise if any of ``cols`` is absent — never fall back to a neutral value."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(
            f"Cannot derive {derivation}: substrate is missing {missing}. "
            f"Refusing to fill a neutral constant instead."
        )


def assert_feats_present(df: pd.DataFrame, feats: list[str], *, label: str) -> None:
    """Assert every model feature is a real column of the assembled frame.

    This is the single check that would have caught the whole
    ``audit_model_ceiling.prep_rh3`` bug class: the audit read the LIVE
    ``RH3_FEATS`` (22 names) from production but assembled a frame that only
    carried 20 of them.
    """
    missing = [f for f in feats if f not in df.columns]
    if missing:
        raise KeyError(
            f"{label}: assembled frame is missing {len(missing)} of "
            f"{len(feats)} model features: {missing}. The feature assembly is "
            f"out of sync with the production FEATS list."
        )


# ---------------------------------------------------------------------------
# Frame containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rh3Frame:
    """The assembled rh3 substrate plus the artifacts ``main()`` bundles."""

    rolling: pd.DataFrame
    multiyr: pd.DataFrame
    pop_means_to: dict
    pop_means_last21: dict


@dataclass(frozen=True)
class Rp3Frame:
    rolling: pd.DataFrame
    multiyr: pd.DataFrame
    il: pd.DataFrame
    pop_means_to: dict
    pop_means_last21: dict
    # The un-merged Marcel prior table. ``rp3.main()`` needs it AFTER the frame
    # is assembled, for the IL-vet fallback (pitchers with a usable prior but no
    # rolling row at all). Returning it here means the delegating caller never
    # has to rebuild — and therefore can never rebuild it *differently*.
    prior: pd.DataFrame


# ---------------------------------------------------------------------------
# rh3 — canonical assembly (moved verbatim out of rh3.main())
# ---------------------------------------------------------------------------
def build_rh3_frame(
    *,
    rolling: pd.DataFrame | None = None,
    multiyr: pd.DataFrame | None = None,
    verbose: bool = True,
) -> Rh3Frame:
    """Assemble the full rh3 substrate: all 22 ``RH3_FEATS`` present, shrunken.

    This is the code that used to be inline in ``rh3.main()``. Callers that
    want the eval-filtered slice apply their own row filters afterwards
    (``pa_to >= EVAL_PA_MIN``, ``ros_pa >= ROS_PA_MIN``, ``year != 2020``) —
    the row filter is a caller concern, the feature assembly is not.
    """
    _p = print if verbose else _noop

    if rolling is None:
        rolling = pd.read_csv(_rh3.ROLLING_CSV)
    if multiyr is None:
        multiyr = pd.read_csv(_rh3.MULTIYR_CSV)
    _p(f'rolling: {len(rolling)} rows | multiyr: {len(multiyr)} rows')

    # Marcel prior
    _p('\nBuilding Marcel prior...')
    years_needed = sorted(rolling['year'].unique())
    prior = _rh3.build_prior_table(multiyr, years_needed)
    rolling = rolling.merge(prior, on=['batter', 'year'], how='left')
    league_mu = float(multiyr[multiyr['pa'] >= 200]['fp_per_pa_actual'].mean())
    rolling['prior_fp_per_pa'] = rolling['prior_fp_per_pa'].fillna(league_mu)
    rolling['prior_pa_eff']    = rolling['prior_pa_eff'].fillna(0.0)

    # AAA callup prior blend (validated PASS 2026-07-19, subgroup partial r
    # +0.276 train / +0.238 holdout / 7/7 yrs — milb_aaa_translation_2026-07-19.md;
    # integration sign-off same date). Blends the translated AAA rate profile
    # into prior_fp_per_pa for rows with < 150 MLB PA (prior_pa_eff + pa_to),
    # weight decaying to 0 at the boundary. Non-callup rows untouched.
    from plv_clone.models.xfp.aaa_translation import blend_callup_prior
    rolling = blend_callup_prior(rolling)

    # H2-locked career profile feature (Aug-01 cutoff, min 150 PA per half)
    require_cache(_rh3.H2_LOCKED_CSV, feature='lift_h2_aug150',
                  builder='scripts/xfp/seasonality_h2_locked.py')
    h2_locked = pd.read_csv(_rh3.H2_LOCKED_CSV)[['batter', 'lift_h2_aug150']]
    rolling = rolling.merge(h2_locked, on='batter', how='left')
    # Players without enough career data: fill with 0 (no seasonal tilt assumed)
    n_with = rolling['lift_h2_aug150'].notna().sum()
    rolling['lift_h2_aug150'] = rolling['lift_h2_aug150'].fillna(0.0)
    _p(f'  merged H2-locked feature: {n_with}/{len(rolling)} rows have career data')

    # xwOBA residual career feature (2018-2025 window)
    require_cache(_rh3.XWOBA_RESID_CSV, feature='xwoba_residual_career',
                  builder='scripts/xfp/hitter_xwoba_residual.py')
    xw = pd.read_csv(_rh3.XWOBA_RESID_CSV)[['batter', 'xwoba_residual_career']]
    rolling = rolling.merge(xw, on='batter', how='left')
    n_with = rolling['xwoba_residual_career'].notna().sum()
    rolling['xwoba_residual_career'] = rolling['xwoba_residual_career'].fillna(0.0)
    _p(f'  merged xwOBA residual feature: {n_with}/{len(rolling)} rows have career data')

    # xwoba_gap_to = within-season expected wOBA on contact − actual wOBA per PA.
    # NOT in RH3_FEATS (removed 2026-05-23, verdict MARGINAL) but retained as a
    # derived substrate column so retroactive analyses can still read it.
    require_columns(rolling, ['xwoba_on_contact_to', 'woba_d_sum_to', 'woba_v_sum_to'],
                    derivation='xwoba_gap_to')
    rolling['actual_woba_per_pa_to'] = np.where(
        rolling['woba_d_sum_to'] > 0,
        rolling['woba_v_sum_to'] / rolling['woba_d_sum_to'],
        np.nan)
    rolling['xwoba_gap_to'] = (rolling['xwoba_on_contact_to']
                                 - rolling['actual_woba_per_pa_to'])
    # Fill NaN with 0 (neutral signal)
    rolling['xwoba_gap_to'] = rolling['xwoba_gap_to'].fillna(0.0)
    n_with = (rolling['xwoba_gap_to'] != 0).sum()
    _p(f'  computed xwoba_gap_to: {n_with}/{len(rolling)} rows non-trivial')

    # career_stage = target year - first MLB year per batter
    first_year = multiyr.groupby('batter')['year'].min().to_dict()
    # vectorized (audit 2026-07-19): identical to the old row-wise apply —
    # unmapped batters fill with their own year (career_stage 0), then int.
    rolling['career_stage'] = (
        rolling['year'] - rolling['batter'].map(first_year).fillna(rolling['year'])
    ).astype(int)
    _p(f'  computed career_stage: range {rolling["career_stage"].min()}-{rolling["career_stage"].max()}')

    # RoS opposing-SP schedule strength (validated 2026-05-24, PASS Δr +0.0137).
    # Cache source: scripts/xfp/build_ros_opp_sp_xwoba_per_hitter.py.
    require_cache(_rh3.ROS_OPP_SP_CSV, feature='ros_opp_sp_xwoba_weighted',
                  builder='scripts/xfp/build_ros_opp_sp_xwoba_per_hitter.py')
    opp_sp = pd.read_csv(_rh3.ROS_OPP_SP_CSV)[
        ['batter', 'year', 'split_day', 'ros_opp_sp_xwoba_weighted']
    ]
    rolling = rolling.merge(opp_sp, on=['batter', 'year', 'split_day'], how='left')
    n_missing = int(rolling['ros_opp_sp_xwoba_weighted'].isna().sum())
    # HARD GUARD (audit 2026-07-04): the cache froze at split 58 for ~6 weeks
    # and this fillna silently constant-filled 100% of projection rows —
    # a VALIDATED feature served a year-mean while looking alive. If the
    # majority of CURRENT-SEASON rows are NaN pre-fill, the cache is frozen
    # again: fail loudly (refresh step 1.9 rebuilds it daily).
    _cur_yr = int(rolling['year'].max())
    _cur = rolling[rolling['year'] == _cur_yr]
    _cur_nan = float(_cur['ros_opp_sp_xwoba_weighted'].isna().mean()) if len(_cur) else 0.0
    if _cur_nan > 0.50:
        raise RuntimeError(
            f"ros_opp_sp_xwoba_weighted: {_cur_nan:.0%} of {_cur_yr} rows are NaN pre-fill — "
            "the ros schedule-strength cache looks FROZEN (see "
            "build_ros_schedule caches / refresh step 1.9). Refusing to "
            "silently constant-fill a validated feature.")
    year_means = rolling.groupby('year')['ros_opp_sp_xwoba_weighted'].transform('mean')
    rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(year_means)
    rolling['ros_opp_sp_xwoba_weighted'] = rolling['ros_opp_sp_xwoba_weighted'].fillna(
        rolling['ros_opp_sp_xwoba_weighted'].mean()
    )
    _p(f'  ros_opp_sp_xwoba_weighted missing pre-fill: {n_missing}/{len(rolling)} '
       f'({n_missing / max(len(rolling), 1):.1%}) — filled with year mean')

    # Box-score-era ensemble prior (validated 2026-07-10, B1 PASS + pre-flight
    # PROMOTE on the live-SB cache). Cache source: scripts/xfp/build_bx_priors.py.
    require_cache(_rh3.BX_PRIORS_CSV, feature='bx_prior_h',
                  builder='scripts/xfp/build_bx_priors.py')
    bx = pd.read_csv(_rh3.BX_PRIORS_CSV)[['mlbam', 'year', 'bx_prior_h']].rename(
        columns={'mlbam': 'batter'})
    rolling = rolling.merge(bx, on=['batter', 'year'], how='left')
    n_missing = int(rolling['bx_prior_h'].isna().sum())
    # HARD GUARD (mirrors ros_opp_sp_xwoba_weighted, audit 2026-07-04): the
    # bx prior is built from COMPLETED T-1 seasons, so ~35-40% NaN (rookies /
    # sub-floor T-1 lines) is the healthy state. If the MAJORITY of
    # current-season rows are NaN pre-fill, the cache is stale/broken.
    _cur_yr = int(rolling['year'].max())
    _cur = rolling[rolling['year'] == _cur_yr]
    _cur_nan = float(_cur['bx_prior_h'].isna().mean()) if len(_cur) else 0.0
    if _cur_nan > 0.50:
        raise RuntimeError(
            f"bx_prior_h: {_cur_nan:.0%} of {_cur_yr} rows are NaN pre-fill — "
            f"the bx priors cache looks STALE (expected ~35-40% NaN). Rerun "
            "scripts/xfp/build_bx_priors.py (refresh step 1.95). Refusing to "
            "silently constant-fill a validated feature.")
    year_means = rolling.groupby('year')['bx_prior_h'].transform('mean')
    rolling['bx_prior_h'] = rolling['bx_prior_h'].fillna(year_means)
    rolling['bx_prior_h'] = rolling['bx_prior_h'].fillna(rolling['bx_prior_h'].mean())
    _p(f'  bx_prior_h missing pre-fill: {n_missing}/{len(rolling)} '
       f'({n_missing / max(len(rolling), 1):.1%}) — filled with year mean')

    # Shrinkage on both windows
    _p('Shrinkage (cumulative + last21)...')
    pop_to = _rh3.compute_population_means(rolling, _rh3.TRAIN_YEARS, _rh3.SHRINK_SPEC_TO)
    pop_l21 = _rh3.compute_population_means(rolling, _rh3.TRAIN_YEARS, _rh3.SHRINK_SPEC_LAST21)
    rolling = _rh3.apply_shrinkage(rolling, pop_to, _rh3.SHRINK_SPEC_TO)
    rolling = _rh3.apply_shrinkage(rolling, pop_l21, _rh3.SHRINK_SPEC_LAST21)
    # last21 columns can be NaN (zero PA in window) — fill _sh with mean
    for col in (rate + '_sh' for rate in _rh3.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(_rh3.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['pa_last21'] = rolling['pa_last21'].fillna(0).astype(float)

    assert_feats_present(rolling, list(_rh3.RH3_FEATS), label='build_rh3_frame')
    return Rh3Frame(rolling=rolling, multiyr=multiyr,
                    pop_means_to=pop_to, pop_means_last21=pop_l21)


# ---------------------------------------------------------------------------
# rp3 — canonical assembly (faithful transcription of rp3.main()'s prep)
# ---------------------------------------------------------------------------
def build_rp3_frame(
    *,
    rolling: pd.DataFrame | None = None,
    multiyr: pd.DataFrame | None = None,
    il: pd.DataFrame | None = None,
    verbose: bool = True,
) -> Rp3Frame:
    """Assemble the full rp3 substrate: all 24 ``RP3_FEATS`` present, shrunken.

    Mirrors ``rp3.main()``'s prep section step for step, including the MiLB
    rookie-prior fallback, the IL-join hard guard, and the schedule-strength
    merge with its frozen-cache guard.
    """
    _p = print if verbose else _noop

    if rolling is None:
        rolling = pd.read_csv(_rp3.ROLLING_CSV)
    if multiyr is None:
        multiyr = pd.read_csv(_rp3.MULTIYR_CSV)
    if il is None:
        il = pd.read_csv(_rp3.IL_CSV)
    _p(f'rolling {len(rolling)} | multiyr {len(multiyr)} | il {len(il)}')

    # Marcel prior
    prior = _rp3.build_prior_table(multiyr, sorted(rolling['year'].unique()))
    rolling = rolling.merge(prior, on=['pitcher', 'year'], how='left')
    league_mu = float(multiyr[multiyr['gs'] >= 10]['fp_per_start_actual'].mean())

    # MiLB-derived rookie prior fallback (Phase MT-Pitchers v1). Tagged via
    # prior_source, so a missing cache degrades to an EXPLICITLY LABELLED
    # 'league_mean' prior rather than a silent one — but say so out loud.
    rolling['prior_source'] = np.where(
        rolling['prior_fp_per_start'].notna(), 'mlb_lag', None)
    if _rp3.MILB_PRIORS_CSV.exists():
        milb_pri = pd.read_csv(_rp3.MILB_PRIORS_CSV)[['pitcher', 'projected_fp_per_start']]
        milb_pri = milb_pri.rename(columns={'projected_fp_per_start': 'milb_prior_fp'})
        rolling = rolling.merge(milb_pri, on='pitcher', how='left')
        is_2026 = rolling['year'] == int(rolling['year'].max())
        needs_fallback = is_2026 & rolling['prior_fp_per_start'].isna()
        has_milb = needs_fallback & rolling['milb_prior_fp'].notna()
        rolling.loc[has_milb, 'prior_fp_per_start'] = rolling.loc[has_milb, 'milb_prior_fp']
        rolling.loc[has_milb, 'prior_source'] = 'milb_translation'
        n_milb = int(has_milb.sum())
        _p(f'  MiLB-derived priors applied to {n_milb} 2026 rookie rows')
    else:
        # OPTIONAL BY DESIGN — but never silent. Why this is a warning and not
        # a require_cache raise: (a) fallback rows are explicitly LABELLED
        # prior_source='league_mean', so the degradation is visible in the
        # output instead of masquerading as a real read; (b) the cache is a
        # one-off research artifact (MT3, 2026-05-07 — see
        # data/research/xfp_model_research.md) with no builder script in the
        # live tree and no refresh step, so a raise would brick every rp3
        # refit with no "rebuild it with X" remedy; (c) absence reproduces the
        # validated pre-MT3 behavior (league-mean rookie prior) rather than
        # zeroing a validated feature. The warning bypasses _p on purpose:
        # verbose=False callers (e.g. the Rule-9 harness loader) are exactly
        # the ones a silenced NOTE would hurt most.
        print(f'WARNING [build_rp3_frame]: optional MiLB rookie-prior cache '
              f'missing: {_rp3.MILB_PRIORS_CSV} — 2026 rookie rows fall back '
              f"to the league-mean prior, tagged prior_source='league_mean' "
              f'(affects prior_fp_per_start only).')

    rolling['prior_source'] = rolling['prior_source'].fillna('league_mean')
    rolling['prior_fp_per_start'] = rolling['prior_fp_per_start'].fillna(league_mu)
    rolling['prior_gs_eff']       = rolling['prior_gs_eff'].fillna(0.0)

    # IL
    rolling = rolling.merge(il, on=['pitcher', 'year', 'split_day'], how='left')
    rolling['il_stints_to']        = rolling['il_stints_to'].fillna(0).astype(int)
    rolling['is_on_il_at_split']   = rolling['is_on_il_at_split'].fillna(0).astype(int)
    _dsr_max = rolling['days_since_il_return'].max(skipna=True)
    # NaN-truthy fix (audit 2026-07-04): float(nan or 200) returns nan (nan is
    # truthy), poisoning the imputation for an all-NaN column.
    max_dsr = float(_dsr_max) if pd.notna(_dsr_max) else 200.0
    rolling['days_since_il_return_imp'] = rolling['days_since_il_return'].fillna(max_dsr + 1)
    # HARD GUARD (IL-join fix 2026-07-09): the IL cache must cover the rolling
    # substrate's split_day grid. On 2026-05-29 this join matched 0.45% of rows
    # and all three VALIDATED IL features silently degenerated to their fillna
    # constants for ~6 weeks. Healthy hit rate is ~25-30%.
    _il_hit = float((rolling['il_stints_to'] > 0).mean())
    if _il_hit < 0.02:
        raise RuntimeError(
            f"IL feature join degenerate: only {_il_hit:.2%} of rolling rows "
            "carry IL history (expected ~25-30%). The il_split_features cache "
            "split_day grid no longer matches the rolling substrate — rerun "
            "scripts/xfp/build_il_split_features.py (it derives its grid from "
            "the rolling CSVs). See rp3_il_join_fix_2026-07-09.md.")

    # RoS schedule-strength feature (validated 2026-05-24, PASS Δr +0.0145).
    require_cache(_rp3.ROS_SCHED_CSV, feature='ros_opp_xwoba_weighted',
                  builder='scripts/xfp/build_ros_schedule_features.py')
    sched_xw = pd.read_csv(_rp3.ROS_SCHED_CSV)[
        ['pitcher', 'year', 'split_day', 'ros_opp_xwoba_weighted']
    ]
    rolling = rolling.merge(sched_xw, on=['pitcher', 'year', 'split_day'], how='left')
    n_missing = int(rolling['ros_opp_xwoba_weighted'].isna().sum())
    # HARD GUARD (audit 2026-07-04): frozen-cache detector — see rh3 twin.
    _cur_yr = int(rolling['year'].max())
    _cur = rolling[rolling['year'] == _cur_yr]
    _cur_nan = float(_cur['ros_opp_xwoba_weighted'].isna().mean()) if len(_cur) else 0.0
    if _cur_nan > 0.50:
        raise RuntimeError(
            f"ros_opp_xwoba_weighted: {_cur_nan:.0%} of {_cur_yr} rows are NaN pre-fill — "
            "the ros schedule-strength cache looks FROZEN (see "
            "build_ros_schedule caches / refresh step 1.9). Refusing to "
            "silently constant-fill a validated feature.")
    year_means = rolling.groupby('year')['ros_opp_xwoba_weighted'].transform('mean')
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(year_means)
    rolling['ros_opp_xwoba_weighted'] = rolling['ros_opp_xwoba_weighted'].fillna(
        rolling['ros_opp_xwoba_weighted'].mean()
    )
    _p(f'  ros_opp_xwoba_weighted missing pre-fill: {n_missing}/{len(rolling)} '
       f'({n_missing / max(len(rolling), 1):.1%}) — filled with year mean')

    # Shrinkage on cumulative + last21
    pop_to = _rp3.compute_population_means(rolling, _rp3.TRAIN_YEARS, _rp3.SHRINK_SPEC_TO)
    pop_l21 = _rp3.compute_population_means(rolling, _rp3.TRAIN_YEARS, _rp3.SHRINK_SPEC_LAST21)
    rolling = _rp3.apply_shrinkage(rolling, pop_to, _rp3.SHRINK_SPEC_TO)
    rolling = _rp3.apply_shrinkage(rolling, pop_l21, _rp3.SHRINK_SPEC_LAST21)

    # SP within-season drift features (H1, validated 2026-05-12).
    # delta = last_21_day_rate − cumulative_to_date_rate (positive = recent uptick).
    require_columns(
        rolling,
        ['avg_velo_last21', 'avg_velo_to', 'swstr_pct_last21', 'swstr_pct_to',
         'k_pct_last21', 'k_pct_to', 'bb_pct_last21', 'bb_pct_to',
         'o_swing_pct_last21', 'o_swing_pct_to', 'zone_pct_last21', 'zone_pct_to'],
        derivation='the 6 SP within-season drift features (delta_*)')
    rolling['delta_velo']    = rolling['avg_velo_last21']   - rolling['avg_velo_to']
    rolling['delta_swstr']   = rolling['swstr_pct_last21']  - rolling['swstr_pct_to']
    rolling['delta_k_pct']   = rolling['k_pct_last21']      - rolling['k_pct_to']
    rolling['delta_bb_pct']  = rolling['bb_pct_last21']     - rolling['bb_pct_to']
    rolling['delta_chase']   = rolling['o_swing_pct_last21']- rolling['o_swing_pct_to']
    rolling['delta_zone']    = rolling['zone_pct_last21']   - rolling['zone_pct_to']
    # NaN drift (no last-21 data) → fill 0 (neutral)
    for c in ('delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
              'delta_chase', 'delta_zone'):
        rolling[c] = rolling[c].fillna(0.0)
    _p('  computed 6 within-season drift features')
    for col in (rate + '_sh' for rate in _rp3.SHRINK_SPEC_LAST21):
        if col in rolling.columns:
            mu = rolling.loc[rolling['year'].isin(_rp3.TRAIN_YEARS), col].mean(skipna=True)
            rolling[col] = rolling[col].fillna(mu)
    rolling['gs_last21'] = rolling['gs_last21'].fillna(0)
    rolling['fp_per_start_last21'] = rolling['fp_per_start_last21'].fillna(
        rolling['fp_per_start_to'])

    assert_feats_present(rolling, list(_rp3.RP3_FEATS), label='build_rp3_frame')
    return Rp3Frame(rolling=rolling, multiyr=multiyr, il=il,
                    pop_means_to=pop_to, pop_means_last21=pop_l21,
                    prior=prior)
