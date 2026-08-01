"""
xfp_rp3 — Bayesian RoS pitcher model with recency + CI +
replacement deltas + schedule-strength adjustment.

Adds on top of RP2:
  1. Last-21-day rate features (shrunken with smaller k) + last21 FP/start
  2. Residual-based CI (p25/p50/p75) per projection
  3. Replacement-level delta vs SP-60 (12-team x 5 SPs)
  4. Schedule strength: opponent batting index for next 2 starts
  5. Composite drop / hold / add signal vs replacement

Outputs:
  data/models/xfp_rp3_pipeline.pkl
  data/outputs/xfp_rp3_projections.csv

ADR-0001: this module owns its own fit_and_project orchestration. The shared
`engine.py` is a toolkit composed at load-bearing steps, not an orchestrator.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import warnings
import numpy as np
import pandas as pd
import joblib

from plv_clone.models.xfp import engine as _engine
from plv_clone.models.xfp.engine import lookup_sigma, lookup_sigma_vec  # re-export
from plv_clone.league_config import SP_REPLACEMENT_RANK as REPLACEMENT_SP_RANK

warnings.filterwarnings('ignore')

# Path anchors: this file lives at src/plv_clone/models/xfp/rp3.py, so parents[4]
# is the repo root (rp3.py → xfp → models → plv_clone → src → repo root).
ROOT = Path(__file__).resolve().parents[4]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_pitchers_2018_2026.csv'
MULTIYR_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'sp_multiyr_2015_2025.csv'
IL_CSV      = ROOT / 'data' / 'research' / 'xfp_cache' / 'il_split_features_2018_2026.csv'
ROS_SCHED_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'ros_schedule_features_2018_2026.csv'
TEAM_STR_CSV  = ROOT / 'data' / 'research' / 'xfp_cache' / 'team_strength_2026.csv'
SCHEDULE_CSV  = ROOT / 'data' / 'research' / 'xfp_cache' / 'pitcher_schedule_2026.csv'
MILB_PRIORS_CSV = ROOT / 'data' / 'outputs' / 'xfp_milb_pitcher_priors_2026.csv'
# Third name-source tier (audit 2026-08-01, T29). The boxscore bridge
# (scripts/xfp/refresh_boxscores.py, refresh step 1.5) is mlbam-keyed and carries
# a fullName for every pitcher who has appeared, so it resolves ids the two
# name CSVs miss entirely.
BOXSCORE_PITCHERS = ROOT / 'data' / 'research' / 'xfp_cache' / 'boxscore_pitchers.parquet'
MODEL_PKL  = ROOT / 'data' / 'models' / 'xfp_rp3_pipeline.pkl'
PROJ_CSV   = ROOT / 'data' / 'outputs' / 'xfp_rp3_projections.csv'
# Sigma calibration config (added 2026-06-03). The raw LOO-residual sigma from
# fit_residual_ci() is ~2.3-2.4x too tight when read against the per-start
# panel — only 21.6% of actual FPs fell in p25-p75 vs the 50% Gaussian target.
# Apply a single empirical scaling factor (alpha_global ~ 2.41) post-lookup so
# xfp_rp3_p25 / xfp_rp3_p75 honestly bracket ~50% of historical outcomes.
# Derived in data/research/validation_runs/sigma_recalibration.md.
SIGMA_CALIB_JSON = ROOT / 'data' / 'research' / 'validation_runs' / 'sigma_calibration.json'

TARGET = 'ros_fp_per_start'
EVAL_GS_MIN = 2
ROS_GS_MIN = 5
# 2026 projection picks each pitcher's most-recent rolling snapshot, but only
# if it's within this many days of the global latest split — so a pitcher who
# has been inactive longer than this still falls through to the Marcel/IL prior
# rather than being projected on stale form. ~2 weekly snapshots.
PROJ_SPLIT_RECENCY_DAYS = 14
TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
PRIOR_K_GS = 5
MARCEL_WEIGHTS = (5, 4, 3)

SHRINK_SPEC_TO = {
    'k_pct_to':         ('tbf_to',     70),
    'bb_pct_to':        ('tbf_to',    170),
    'swstr_pct_to':     ('pitches_to', 300),
    'c_plus_swstr_to':  ('pitches_to', 300),
    'xwoba_per_pa_to':  ('tbf_to',    300),
    'zone_pct_to':      ('pitches_to', 200),
    'z_swing_pct_to':   ('in_zone_to', 200),
    'o_swing_pct_to':   ('out_zone_to', 200),
}
SHRINK_SPEC_LAST21 = {
    'k_pct_last21':         ('tbf_last21',     35),
    'bb_pct_last21':        ('tbf_last21',     85),
    'swstr_pct_last21':     ('pitches_last21', 150),
    'xwoba_per_pa_last21':  ('tbf_last21',    150),
}

# Model features = RP2 set. Last-21-day rates failed the +0.005 r gate
# (delta vs RP2 was only +0.0002 — within noise). They remain in the substrate
# but are NOT model inputs; recency_form_gap is a display-only column.
RP3_FEATS = [
    'k_pct_to_sh', 'bb_pct_to_sh', 'swstr_pct_to_sh', 'c_plus_swstr_to_sh',
    'xwoba_per_pa_to_sh', 'zone_pct_to_sh',
    'z_swing_pct_to_sh', 'o_swing_pct_to_sh',
    'avg_velo_to',
    'fp_per_start_to', 'gs_to',
    # Prior + IL
    'prior_fp_per_start', 'prior_gs_eff',
    'is_on_il_at_split', 'days_since_il_return_imp', 'il_stints_to',
    'split_day',
    # SP within-season drift (H1, validated 2026-05-12).
    # Integration backtest gain +0.0157 r over rp3 v1 (clears +0.005 bar).
    # Velocity is dominant driver; all 6 component metrics validated.
    'delta_velo', 'delta_swstr', 'delta_k_pct', 'delta_bb_pct',
    'delta_chase', 'delta_zone',
    # RoS schedule strength: per-(pitcher, year, split_day) weighted opp xwOBA
    # over the pitcher's primary team's remaining schedule. Validated PASS
    # 2026-05-24 (Δr +0.0145 vs full rp3 v2 baseline). Cache built by
    # scripts/xfp/build_ros_schedule_features.py — see
    # data/research/xfp_cache/ros_schedule_features_2018_2026.csv. Joined on
    # (pitcher, year, split_day); NaN filled with per-year mean (mostly
    # end-of-year IL rows with no RoS games).
    'ros_opp_xwoba_weighted',
]

# ADR-0003 phase-5 hard assert: every FEATS entry must have a PASS
# validation_runs record. Backfill completed 2026-05-23.
from plv_clone.models.xfp.validated_signals import check_feats_validated as _check_feats_validated
with warnings.catch_warnings():
    warnings.simplefilter("default", UserWarning)
    _check_feats_validated(RP3_FEATS, target="rp3", strict=True)


def _load_sigma_calibration() -> dict:
    """Return calibration config (method + alpha). Falls back to {alpha:1.0,
    method:'uncalibrated_v0'} if the JSON is missing so the pipeline still runs.
    """
    if SIGMA_CALIB_JSON.exists():
        cfg = json.loads(SIGMA_CALIB_JSON.read_text())
        cfg.setdefault('alpha_global', 1.0)
        cfg.setdefault('method', 'global_alpha_v1')
        return cfg
    return {'method': 'uncalibrated_v0', 'alpha_global': 1.0,
            'description': 'No sigma_calibration.json found; bands raw (under-confident).'}


def _ensure_derived_denoms(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if 'out_zone_to' not in out.columns:
        out = out.assign(out_zone_to=(out['pitches_to'] - out['in_zone_to']).clip(lower=0))
    return out


def build_prior_table(multiyr: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    rows = []
    by_yr = {y: multiyr[multiyr['year'] == y].set_index('pitcher')
             for y in multiyr['year'].unique()}
    league_mean_by_year = (multiyr[multiyr['gs'] >= 10]
                           .groupby('year')['fp_per_start_actual'].mean().to_dict())
    all_pitchers = set()
    for df in by_yr.values():
        all_pitchers.update(df.index)
    for tgt in years:
        offsets_use = []
        for off, w in zip([1, 2, 3], MARCEL_WEIGHTS):
            y = tgt - off
            if y in by_yr and y != 2020:
                offsets_use.append((y, w))
        league_mu = league_mean_by_year.get(tgt, np.nanmean(list(league_mean_by_year.values())))
        for p in all_pitchers:
            num = 0.0; denom = 0.0
            for y, w in offsets_use:
                df_y = by_yr[y]
                if p in df_y.index:
                    row = df_y.loc[p]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    gs = float(row.get('gs', 0) or 0)
                    fp = float(row.get('fp_per_start_actual', np.nan))
                    if gs >= 3 and not np.isnan(fp):
                        num += w * gs * fp
                        denom += w * gs
            prior = (num + PRIOR_K_GS * league_mu) / (denom + PRIOR_K_GS)
            rows.append({'pitcher': p, 'year': tgt,
                         'prior_fp_per_start': prior,
                         'prior_gs_eff': denom / max(sum(w for _, w in offsets_use), 1)})
    return pd.DataFrame(rows)


def compute_population_means(df: pd.DataFrame, train_years: list[int],
                              spec: dict) -> dict:
    return _engine.compute_population_means(_ensure_derived_denoms(df.copy()), train_years, spec)


def apply_shrinkage(df: pd.DataFrame, pop_means: dict, spec: dict) -> pd.DataFrame:
    return _engine.apply_shrinkage(_ensure_derived_denoms(df.copy()), pop_means, spec)


_FIT_FP_VERSION = 1


# eligibility mask shared by the fit stages (hoisted scaffolding, audit D2)
def _fit_filter(d: pd.DataFrame):
    return (d['gs_to'] >= EVAL_GS_MIN) & (d['ros_gs'] >= ROS_GS_MIN) & (d['year'] != 2020)


def _fit_fingerprint(rolling: pd.DataFrame, feats: list[str]) -> str:
    return _engine.fit_fingerprint(
        rolling, feats, target=TARGET, train_years=TRAIN_YEARS,
        extra=(TARGET,), fp_version=_FIT_FP_VERSION)


def cross_year_eval(df: pd.DataFrame, feats: list[str]):
    return _engine.cross_year_eval_ridge(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=_fit_filter, min_train=50, min_test=10)


def fit_residual_ci(df: pd.DataFrame, feats: list[str], resid: pd.DataFrame | None = None):
    # `resid`: per-row detail cross_year_eval already produced — the second LOO
    # pass here was fit-for-fit IDENTICAL (audit 2026-07-04, duplicate fitting).
    return _engine.fit_residual_ci_from(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=_fit_filter, min_train=50, min_test=10, resid=resid)


def train_final(df: pd.DataFrame, feats: list[str]):
    return _engine.train_final_ridge(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=lambda d: (d['gs_to'] >= EVAL_GS_MIN) & (d['ros_gs'] >= ROS_GS_MIN))


def fill_missing_player_names(valid: pd.DataFrame,
                              id_col: str = 'pitcher',
                              name_col: str = 'player_name') -> pd.DataFrame:
    """Last name-source tier: resolve a still-blank player_name from the mlbam id.

    sp_multiyr and the MiLB priors are both name CSVs keyed on ids they happen to
    carry; a pitcher present in the rolling substrate but in neither (canonical
    2026-08-01: Tyler Holton 663947, Eduardo Rivera 700842) shipped with a null
    name and was unreachable by every name-keyed board join. The mlbam-keyed
    boxscore store this same nightly chain writes knows them.

    Additive and conservative: an existing name is never overwritten, an id
    nothing can resolve stays null rather than being guessed at, and a missing
    store is a no-op. Touches no numeric column.
    """
    if name_col not in valid.columns:
        return valid
    # "No name" means null OR blank/whitespace — a CSV written with na_rep=''
    # produces the latter, and report_name_completeness already counts those
    # rows as missing. Gating on isna() alone let the two disagree: the
    # resolver skipped the row and the reporter warned about it forever.
    _blank = (valid[name_col].isna()
              | (valid[name_col].astype(str).str.strip() == ''))
    if not _blank.any():
        return valid
    if not Path(BOXSCORE_PITCHERS).exists():
        return valid
    try:
        box = pd.read_parquet(BOXSCORE_PITCHERS,
                              columns=['mlbam_id', 'player_name', 'game_date'])
    except Exception as e:                                  # pragma: no cover
        print(f'  !! could not read {BOXSCORE_PITCHERS.name} for name backfill: {e}')
        return valid
    box = box.dropna(subset=['mlbam_id', 'player_name'])
    box = box[box['player_name'].astype(str).str.strip() != '']
    if box.empty:
        return valid
    # Most recent appearance wins — a name spelling can be corrected upstream.
    box = (box.sort_values('game_date')
              .drop_duplicates('mlbam_id', keep='last')
              [['mlbam_id', 'player_name']]
              .rename(columns={'player_name': '_box_name'}))
    box['mlbam_id'] = pd.to_numeric(box['mlbam_id'], errors='coerce')

    out = valid.copy()
    key = pd.to_numeric(out[id_col], errors='coerce')
    lookup = dict(zip(box['mlbam_id'], box['_box_name']))
    resolved = key.map(lookup)
    # fill the SAME blank set the gate tested (fillna alone would leave '' rows
    # untouched); an existing real name is still never overwritten.
    blank = (out[name_col].isna()
             | (out[name_col].astype(str).str.strip() == ''))
    out.loc[blank, name_col] = resolved[blank]
    return out


def report_name_completeness(valid: pd.DataFrame,
                             id_col: str = 'pitcher',
                             name_col: str = 'player_name') -> int:
    """Announce rows still shipping without a name; return how many.

    Non-gating by design — this is a display column on a fail-soft nightly, and
    dropping the rows would discard legitimately projected pitchers. The point is
    that a future gap is announced instead of silently shipped.
    """
    if name_col not in valid.columns:
        return 0
    missing = valid[valid[name_col].isna() |
                    (valid[name_col].astype(str).str.strip() == '')]
    if len(missing):
        ids = ', '.join(str(i) for i in missing[id_col].tolist()[:20])
        print(f'  !! WARNING: {len(missing)} row(s) have no {name_col} and are '
              f'unreachable by every name-keyed join (pitcher ids: {ids})')
    return len(missing)


def main():
    print('=== xfp_rp3 (RP2 + recency + CI + replacement + schedule) ===')

    # ── Feature assembly: delegated to the ONE canonical builder (2026-07-30).
    # This prep block used to live inline here, making rp3 the LAST model in the
    # repo carrying a second copy of its own feature assembly. The rh3 postmortem
    # (docs/rh3_harness_root_bug_2026-07-28.md) is the reason that matters: a
    # divergent copy silently weakened the Rule-9 BASELINE for ~20 harnesses and
    # cost -0.0368 cross-year r for nine days while printing confident numbers.
    # rp3's copy was pinned only by the fit fingerprint, which re-checks at REFIT
    # time — an edit to one copy could sit undetected until the next refit.
    #
    # The switch was PROVEN byte-identical on the real 2018-2026 cache before it
    # was made (31,135 x 109, assert_frame_equal(check_exact=True), equal pop
    # means, fingerprint 46e24bc9b4187492b95a84fbc3bb57dd matching the shipped
    # bundle, cross_year r=0.5617 / mae=2.8394 / baseline 0.5484 / delta +0.0133
    # reproduced from both). tests/test_xfp_frames.py keeps a frozen verbatim
    # copy of the old inline block and re-asserts the equality every run.
    #
    # Local import: frames.py imports this module at module scope.
    from plv_clone.models.xfp.frames import build_rp3_frame
    _frame = build_rp3_frame()
    rolling = _frame.rolling
    multiyr = _frame.multiyr
    prior = _frame.prior
    pop_to = _frame.pop_means_to
    pop_l21 = _frame.pop_means_last21

    # Cross-year RP3
    print('\n--- LOO cross-year (RP3) ---')
    # ── Fingerprint warm-skip (audit 2026-07-04): fit stage is deterministic in
    # the immutable train-year slice + FEATS; on match load the bundle and jump
    # to projection. The Rule-9 gate re-runs exactly when the fingerprint moves.
    _fp = _fit_fingerprint(rolling, RP3_FEATS)
    _warm = None
    if MODEL_PKL.exists():
        try:
            _b = joblib.load(MODEL_PKL)
            if _b.get('fit_fingerprint') == _fp:
                _warm = _b
        except Exception:
            _warm = None
    if _warm is not None:
        print('\n[warm-fit] fingerprint match — LOO eval / Rule-9 gate / CI / final '
              'fit loaded from bundle (they re-run whenever train data or FEATS change)')
        per_year = _warm['per_year_r']
        overall = {'r': _warm['cross_year_r'], 'mae': _warm['cross_year_mae'], 'n': None}
        baseline = {'r': _warm['baseline_rp2_r']}
        delta = _warm['delta_r_vs_rp2']
        ci_table = _warm['ci_table']
        overall_sigma = _warm['overall_sigma']
        pipe = _warm['pipeline']
        n_train = _warm['n_train']
    else:
        per_year, overall, _resid_full = cross_year_eval(rolling, RP3_FEATS)
        for y, r in sorted(per_year.items()):
            print(f'  {y}: r={r["r"]:.4f}  mae={r["mae"]:.4f}  n={r["n"]}')
        print(f'  Overall: r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')

        # Rule 9 hard gate. 2026-05-23: the 6 SP-drift features
        # (delta_velo/swstr/k_pct/bb_pct/chase/zone) collectively contributed
        # only +0.0015 r over baseline — below the +0.005 gate. Demoted to
        # baseline; v2_added empty so the gate is vacuous until the next
        # claimed lift lands. Features stay in FEATS (still inputs to the
        # final Ridge) but are no longer "claimed" v2 lifts. ADR-0003.
        # 2026-05-24: promoted ros_opp_xwoba_weighted (rp3 v3). Validation run
        # data/research/validation_runs/ros_opp_xwoba_weighted_2026-05-24.md
        # showed Δr +0.0145 vs full rp3 v2 baseline — first PASS-gate signal in
        # 4 sessions. Rule 9 hard assert below now FIRES meaningfully against the
        # full prior-production baseline (RP3_FEATS minus this one feature).
        v2_added: set[str] = {"ros_opp_xwoba_weighted"}
        baseline_feats = [f for f in RP3_FEATS if f not in v2_added]
        _ , baseline, _ = cross_year_eval(rolling, baseline_feats)
        delta = overall['r'] - baseline['r']
        print(f'\n--- Baseline (drops v2 drift features {sorted(v2_added)}) ---  r={baseline["r"]}')
        print(f'  Δr (RP3 v2 − baseline) = {delta:+.4f}  (gate: ≥ +0.005)')
        if v2_added and delta < 0.005:
            # RuntimeError, not assert (audit 2026-07-04): assert vanishes under
            # python -O, silently disabling the Rule-9 promotion gate.
            raise RuntimeError(
                f"Rule 9 gate: Δr={delta:+.4f} below +0.005 for v2 features "
                f"{sorted(v2_added)}. Revert or re-validate.")

        # CI
        ci_table, overall_sigma = fit_residual_ci(rolling, RP3_FEATS, resid=_resid_full)
        print(f'\n  overall sigma = {overall_sigma:.3f} FP/start')

        # Train final
        pipe, n_train = train_final(rolling, RP3_FEATS)
        coefs = pipe.named_steps['r'].coef_
        print(f'\n--- Final RP3 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}) ---')
        print('  Top coefficients:')
        for f, c in sorted(zip(RP3_FEATS, coefs), key=lambda x: -abs(x[1]))[:14]:
            print(f'    {f:<28s} {c:+.4f}')


    # Project the current season = latest year in the substrate (audit R2:
    # the old hardcoded ==2026 would silently no-op on 2027-01-01)
    proj_year = int(rolling['year'].max())
    df_26 = rolling[rolling['year'] == proj_year].copy()
    if df_26.empty:
        return
    latest_split = int(df_26['split_day'].max())
    # Use each pitcher's MOST-RECENT rolling snapshot, not only the global latest
    # split. The rolling builder emits a split row only when the pitcher has a
    # subsequent start in the data (ros_gs>=1, the training target), so anyone
    # whose latest start has no "next start" logged yet — every rookie who just
    # debuted (Messick/Sasaki 2026) and any starter coming off their most recent
    # outing — has NO row at the global latest split and was silently dropped to
    # the suppressed marcel_il prior (gs_to forced to 0) despite having real
    # 2026 form. Take their latest snapshot instead, capped to recent splits so
    # long-inactive arms still fall through to the Marcel/IL fallback.
    df_26 = df_26[(df_26['split_day'] >= latest_split - PROJ_SPLIT_RECENCY_DAYS)
                  & (df_26['gs_to'] >= EVAL_GS_MIN)]
    df_26 = (df_26.sort_values('split_day')
                  .groupby('pitcher', as_index=False, sort=False)
                  .tail(1))
    valid = df_26.dropna(subset=RP3_FEATS).copy()
    valid['xfp_rp3_per_start'] = pipe.predict(valid[RP3_FEATS].values)
    valid['prior_source'] = 'rp3_model'

    # IL-vet fallback: any pitcher with a valid Marcel prior but no rolling
    # 2026 row (because they have 0 starts — IL all season). Project them
    # using prior alone, discounted for rust/IL.
    IL_PRIOR_DISCOUNT = 0.85
    IL_PRIOR_MIN_GS = 5  # need ≥5 GS-equivalent of prior history
    projected_ids = set(valid['pitcher'])
    prior_only = prior[~prior['pitcher'].isin(projected_ids)
                        & (prior['year'] == proj_year)
                        & (prior['prior_gs_eff'] >= IL_PRIOR_MIN_GS)].copy()
    if not prior_only.empty:
        prior_only['xfp_rp3_per_start'] = (prior_only['prior_fp_per_start']
                                            * IL_PRIOR_DISCOUNT).round(2)
        prior_only['gs_to'] = 0
        prior_only['fp_per_start_to'] = prior_only['prior_fp_per_start']
        prior_only['fp_per_start_last21'] = prior_only['prior_fp_per_start']
        prior_only['is_on_il_at_split'] = 1
        prior_only['split_day'] = latest_split
        prior_only['year'] = 2026
        prior_only['prior_source'] = 'marcel_il'
        # Align columns with valid by filling missing with 0 (numeric defaults)
        for c in valid.columns:
            if c not in prior_only.columns:
                prior_only[c] = 0.0
        prior_only = prior_only[valid.columns]
        valid = pd.concat([valid, prior_only], ignore_index=True)
        print(f'  injected {len(prior_only)} IL-vet projections from Marcel prior')

    # Pred-bucket cuts for sigma
    train_for_buckets = rolling.dropna(subset=RP3_FEATS + [TARGET])
    train_for_buckets = train_for_buckets[(train_for_buckets['gs_to'] >= EVAL_GS_MIN)
                                          & (train_for_buckets['ros_gs'] >= ROS_GS_MIN)
                                          & (train_for_buckets['year'].isin(TRAIN_YEARS))]
    train_pred = pipe.predict(train_for_buckets[RP3_FEATS].values)
    pred_buckets = {}
    for split in sorted(train_for_buckets['split_day'].unique()):
        ix = (train_for_buckets['split_day'].values == split)
        if ix.sum() < 30:
            continue
        cuts = np.quantile(train_pred[ix], [0.25, 0.5, 0.75])
        pred_buckets[int(split)] = cuts

    Z25 = 0.6745
    # (vectorized 2026-07-19, audit item 21/W2 — latest_split is constant here;
    # golden A/B verified byte-identical vs the scalar iterrows loop)
    sigmas = lookup_sigma_vec(ci_table, overall_sigma, latest_split,
                              valid['xfp_rp3_per_start'].to_numpy(), pred_buckets)
    valid['xfp_rp3_sigma_raw'] = sigmas
    # Empirical sigma recalibration (added 2026-06-03). Raw LOO residual sigma
    # under-covers the per-start panel by ~2.3x. Multiply by alpha_global so
    # xfp_rp3_p25 / xfp_rp3_p75 honestly bracket ~50% of historical outcomes.
    calib = _load_sigma_calibration()
    alpha = float(calib.get('alpha_global', 1.0))
    valid['xfp_rp3_sigma'] = np.array(sigmas) * alpha
    valid['sigma_calibration_method'] = calib.get('method', 'uncalibrated_v0')
    valid['xfp_rp3_p25'] = (valid['xfp_rp3_per_start'] - Z25 * valid['xfp_rp3_sigma']).clip(lower=0)
    valid['xfp_rp3_p75'] = valid['xfp_rp3_per_start'] + Z25 * valid['xfp_rp3_sigma']
    print(f'  sigma calibration: method={calib.get("method")} alpha={alpha:.3f} '
          f'(mean sigma raw={float(np.mean(sigmas)):.3f} -> calibrated={float(np.mean(sigmas))*alpha:.3f})')

    # Decision-band p25/p75 (added 2026-06-11). The displayed xfp_rp3_p25/p75
    # use the ×2.41 coverage-recalibrated sigma so the CI honestly brackets
    # ~50% of historical outcomes — but that wide band ALSO neutered the
    # add/drop trigger: the 2026-06-11 verdict_backtest found the SP signal
    # emitted 'hold' on 100% of rows because no p25 could clear (nor any p75
    # fall below) the SP-45 replacement once the band was that wide. We keep
    # the wide band for DISPLAY and add a SEPARATE narrower DECISION band built
    # from the raw (pre-recalibration) LOO-residual sigma for the add/drop
    # computation only. This restores a live add/hold/drop distribution without
    # touching the headline projection, the displayed CI, or any model fit.
    valid['xfp_rp3_decision_p25'] = (
        valid['xfp_rp3_per_start'] - Z25 * valid['xfp_rp3_sigma_raw']).clip(lower=0)
    valid['xfp_rp3_decision_p75'] = (
        valid['xfp_rp3_per_start'] + Z25 * valid['xfp_rp3_sigma_raw'])

    # Recency form gap
    valid['recency_form_gap'] = (valid['fp_per_start_last21'] -
                                  valid['fp_per_start_to']).round(3)

    # Names — multiyr only has MLB-active pitchers; for rookies (MiLB-prior
    # source) fall back to the MiLB priors CSV which carries their names.
    # Use ALL years of multiyr (not just 2026) so IL-vets with no 2026 games
    # still get their name.
    sp_any = (multiyr.sort_values('year', ascending=False)
              [['pitcher', 'player_name']].drop_duplicates('pitcher'))
    valid = valid.drop_duplicates('pitcher').merge(sp_any, on='pitcher', how='left')
    if MILB_PRIORS_CSV.exists():
        milb_names = pd.read_csv(MILB_PRIORS_CSV)[['pitcher', 'name']].rename(
            columns={'name': 'milb_name'}).drop_duplicates('pitcher')
        valid = valid.merge(milb_names, on='pitcher', how='left')
        valid['player_name'] = valid['player_name'].fillna(valid['milb_name'])
        valid = valid.drop(columns=['milb_name'])
    # Third tier: ids neither name CSV carries, resolved from the mlbam-keyed
    # boxscore store (audit 2026-08-01, T29). Name column only.
    valid = fill_missing_player_names(valid)

    # Schedule strength: opponent batting index for next 2 starts
    valid = apply_schedule_strength(valid)

    # Replacement-level
    valid = compute_replacement_delta(valid)

    # Data-quality transparency columns (added 2026-06-02).
    # Downstream consumers (dashboards, audits) need to distinguish a
    # projection backed by real 2026 form from one that is a Marcel
    # regression-to-mean fallback for an IL'd or zero-start pitcher.
    # No model semantics change: xfp_rp3_per_start remains the headline blend.
    #
    # data_quality_tag — bucket the signal-quality regime:
    #   data_driven_full : gs_to >= 8 — Ridge has solid 2026 input
    #   data_driven_thin : gs_to in 3..7 — Ridge has limited 2026 input
    #   marcel_no_data   : gs_to == 0 and not IL — should be rare/empty
    #   marcel_il        : prior_source == 'marcel_il' OR is_on_il_at_split == 1
    #                      (Marcel prior * IL_PRIOR_DISCOUNT, no 2026 form)
    # (vectorized 2026-07-19, audit item 21/W3 — golden A/B verified
    # byte-identical vs the row-wise _quality_tag closure)
    valid['data_quality_tag'] = np.select(
        [
            (valid['prior_source'] == 'marcel_il') | (valid['is_on_il_at_split'] == 1),
            valid['gs_to'] == 0,
            valid['gs_to'] >= 8,
        ],
        ['marcel_il', 'marcel_no_data', 'data_driven_full'],
        default='data_driven_thin',
    )

    # marcel_baseline — the pure Marcel prior (undiscounted), surfaced
    # explicitly so consumers can show "Marcel says X, 2026 data says Y,
    # blend says Z" for transparency on IL-return pitchers.
    valid['marcel_baseline'] = valid['prior_fp_per_start'].round(3)

    # data_driven_estimate — the model's 2026-informed estimate, exposed
    # only when there is real 2026 signal (gs_to >= 3). For marcel_il /
    # marcel_no_data / minimal-data rows this is NaN by design — the
    # consumer should fall back to marcel_baseline and treat the projection
    # as high-uncertainty. For gs_to >= 3 rows this equals xfp_rp3_per_start
    # (the Ridge prediction, which already blends prior + 2026 features).
    valid['data_driven_estimate'] = np.where(
        valid['gs_to'].fillna(0) >= 3,
        valid['xfp_rp3_per_start'],
        np.nan,
    )

    # Add/drop signal (vectorized 2026-07-19, audit item 21/W3 — golden A/B
    # verified byte-identical vs the row-wise _signal()). Uses the DECISION
    # band (narrow, raw-sigma) for the add/drop trigger — the wide ×2.41
    # display band is a coverage-calibrated CI, not a decision band; using it
    # for add/drop made the signal inert (100% hold, verdict_backtest
    # 2026-06-11). The is_on_il_at_split test replicates bool() truthiness
    # (NaN/non-zero -> 'il'); NaN comparisons match row-wise (NaN > x = False).
    _il = valid['is_on_il_at_split']
    _repl = valid['replacement_xfp_per_start']
    _p25 = valid['xfp_rp3_decision_p25']
    _p75 = valid['xfp_rp3_decision_p75']
    valid['signal'] = np.select(
        [
            _il.isna() | (_il != 0),
            valid['replacement_delta'].isna() | _repl.isna(),
            _p25.notna() & (_p25 > _repl),
            _p75.notna() & (_p75 < _repl),
        ],
        ['il', 'hold', 'add', 'drop'],
        default='hold',
    )
    valid = valid.sort_values('xfp_rp3_per_start', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1

    bundle = {
        'pipeline': pipe,
        'features': RP3_FEATS,
        'target': TARGET,
        'pop_means_to': pop_to,
        'pop_means_last21': pop_l21,
        'shrink_spec_to': SHRINK_SPEC_TO,
        'shrink_spec_last21': SHRINK_SPEC_LAST21,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rp2_r': baseline['r'],
        'delta_r_vs_rp2': round(delta, 4),
        'per_year_r': per_year,
        'ci_table': ci_table,
        'pred_buckets': {k: v.tolist() for k, v in pred_buckets.items()},
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'replacement_sp_rank': REPLACEMENT_SP_RANK,
        'fit_fingerprint': _fp,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rp3',
        'note': 'Bayesian RoS pitcher Ridge + last-21-day form + residual CI '
                '+ schedule-strength + replacement-level delta.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    # Slump-precedent merge (rolling-window career comparison vs current 2026)
    slump_path = ROOT / 'data' / 'outputs' / 'slump_precedent_sps_2026.csv'
    if slump_path.exists():
        sp_slump = pd.read_csv(slump_path)[
            ['pitcher', 'pct_rank', 'n_comparable', 'bounce_pct',
             'median_next_rate', 'median_delta']
        ].rename(columns={
            'pct_rank': 'slump_pct_rank',
            'n_comparable': 'slump_n_comparable',
            'bounce_pct': 'slump_bounce_pct',
            'median_next_rate': 'slump_next_rate',
            'median_delta': 'slump_delta',
        })
        valid = valid.merge(sp_slump, on='pitcher', how='left')

    out_cols = [
        'rank', 'pitcher', 'player_name',
        'gs_to', 'gs_last21', 'fp_per_start_to', 'fp_per_start_last21',
        'recency_form_gap',
        'prior_fp_per_start', 'prior_source',
        'data_quality_tag', 'marcel_baseline', 'data_driven_estimate',
        'is_on_il_at_split',
        'xfp_rp3_per_start', 'xfp_rp3_sigma', 'xfp_rp3_sigma_raw',
        'sigma_calibration_method',
        'xfp_rp3_p25', 'xfp_rp3_p75',
        'xfp_rp3_decision_p25', 'xfp_rp3_decision_p75',
        'next_opp_team', 'next_opp_bat_index',
        'next2_avg_bat_index', 'schedule_factor',
        'xfp_rp3_per_start_sched',
        'replacement_xfp_per_start', 'replacement_delta',
        'signal',
        'slump_pct_rank', 'slump_n_comparable', 'slump_bounce_pct',
        'slump_next_rate', 'slump_delta',
    ]
    out_cols = [c for c in out_cols if c in valid.columns]
    report_name_completeness(valid)
    valid[out_cols].to_csv(PROJ_CSV, index=False)
    print(f'Wrote {PROJ_CSV}: {len(valid)} pitchers')

    print('\nTop 10 by replacement_delta (best add candidates):')
    show = ['rank', 'player_name', 'gs_to', 'xfp_rp3_per_start',
            'xfp_rp3_p25', 'xfp_rp3_p75',
            'next_opp_team', 'next2_avg_bat_index', 'xfp_rp3_per_start_sched',
            'replacement_delta', 'signal']
    show = [c for c in show if c in valid.columns]
    top = valid.sort_values('replacement_delta', ascending=False).head(10)
    print(top[show].to_string(index=False))


def apply_schedule_strength(valid: pd.DataFrame) -> pd.DataFrame:
    """Multiply rp3_per_start by inverse of opponent strength for next 2 starts.
    schedule_factor < 1 means easier schedule -> higher adjusted xFP."""
    valid = valid.copy()
    if not (TEAM_STR_CSV.exists() and SCHEDULE_CSV.exists()):
        valid['next_opp_team'] = None
        valid['next_opp_bat_index'] = np.nan
        valid['next2_avg_bat_index'] = np.nan
        valid['schedule_factor'] = 1.0
        valid['xfp_rp3_per_start_sched'] = valid['xfp_rp3_per_start']
        return valid

    team = pd.read_csv(TEAM_STR_CSV)
    sched = pd.read_csv(SCHEDULE_CSV)
    # Staleness-visibility guard (audit 2026-07-19 R5): a frozen schedule CSV
    # silently yields schedule_factor=1.0 for everyone. Values unchanged —
    # just surface the cache's age so undetectable staleness can't recur.
    try:
        from datetime import datetime as _dt
        _age_d = (_dt.now() - _dt.fromtimestamp(SCHEDULE_CSV.stat().st_mtime)).days
        if _age_d >= 3:
            print(f'  !! WARNING: pitcher_schedule cache is {_age_d}d old — '
                  f'schedule_factor is running on a stale probables window')
    except OSError:
        pass
    sched = sched.merge(team[['team', 'bat_index']],
                        left_on='opp_team_abbrev', right_on='team',
                        how='left', suffixes=('', '_t'))
    sched = sched.rename(columns={'bat_index': 'opp_bat_index'})

    by_pitcher = sched.groupby('pitcher')
    next_opp = by_pitcher.first()[['opp_team_abbrev', 'opp_bat_index']].rename(
        columns={'opp_team_abbrev': 'next_opp_team',
                 'opp_bat_index': 'next_opp_bat_index'})
    next2_avg = by_pitcher['opp_bat_index'].mean().to_frame('next2_avg_bat_index')
    if 'park_factor' in sched.columns:
        next2_park = by_pitcher['park_factor'].mean().to_frame('next2_avg_park_factor')
    else:
        next2_park = pd.DataFrame({'next2_avg_park_factor': []})
    if 'platoon_factor' in sched.columns:
        next2_pla = by_pitcher['platoon_factor'].mean().to_frame('next2_avg_platoon_factor')
    else:
        next2_pla = pd.DataFrame({'next2_avg_platoon_factor': []})

    valid = valid.merge(next_opp, left_on='pitcher', right_index=True, how='left')
    valid = valid.merge(next2_avg, left_on='pitcher', right_index=True, how='left')
    if not next2_park.empty:
        valid = valid.merge(next2_park, left_on='pitcher', right_index=True, how='left')
    else:
        valid['next2_avg_park_factor'] = 1.0
    if not next2_pla.empty:
        valid = valid.merge(next2_pla, left_on='pitcher', right_index=True, how='left')
    else:
        valid['next2_avg_platoon_factor'] = 1.0
    valid['next2_avg_park_factor'] = valid['next2_avg_park_factor'].fillna(1.0)
    valid['next2_avg_platoon_factor'] = valid['next2_avg_platoon_factor'].fillna(1.0)

    # Combined schedule factor: opp strength × park. (Platoon factor was tested
    # but failed validation — cor with per-start residual was −0.005, no
    # meaningful signal. Kept in the substrate for transparency, NOT applied.)
    valid['opp_factor']     = 1.0 / valid['next2_avg_bat_index'].fillna(1.0)
    valid['park_factor']    = 1.0 / valid['next2_avg_park_factor']
    valid['platoon_factor'] = 1.0 / valid['next2_avg_platoon_factor']  # kept for display only
    valid['schedule_factor'] = (valid['opp_factor'] * valid['park_factor']).clip(0.80, 1.20)
    valid['xfp_rp3_per_start_sched'] = (
        valid['xfp_rp3_per_start'] * valid['schedule_factor']
    ).round(2)
    return valid


def compute_replacement_delta(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    sub = df.sort_values('xfp_rp3_per_start', ascending=False)
    n = REPLACEMENT_SP_RANK
    if len(sub) >= n:
        repl = float(sub['xfp_rp3_per_start'].iloc[n - 1])
    else:
        repl = float(sub['xfp_rp3_per_start'].median())
    df['replacement_xfp_per_start'] = round(repl, 3)
    df['replacement_delta'] = (df['xfp_rp3_per_start'] - repl).round(3)
    return df


if __name__ == '__main__':
    main()
