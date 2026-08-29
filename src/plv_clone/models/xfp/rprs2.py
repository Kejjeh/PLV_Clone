"""xfp_rprs2 — RP RoS model with in-season role-usage features.

Adds (vs RP-RS1):
  - gf_pct_to        (current-year games-finished % through cutoff)
  - sv_per_g_to      (current-year saves per appearance through cutoff)
  - hld_per_g_to     (current-year holds per appearance through cutoff)
  - sv_plus_hld_to   (raw count, captures total high-leverage usage)
  - sv_per_g_lag1    (prior year saves rate)
  - hld_per_g_lag1   (prior year holds rate)
  - fp_with_role_to  (FP-to-date with SV/HLD bonuses included — closer to actual)

These were identified by comparing PL Top 50 ranking correlations: PL leans
heavily on gf_pct_now / sv_pct_now (ρ ≈ -0.74) which our prior model didn't see.

Stratified validation gate:
  1. OVERALL LOO cross-year r must NOT regress vs RP-RS1 baseline (gate >= 0.0)
  2. ROLE-CHANGE SUBSET cross-year r MUST improve by >= +0.05.
     Subset definition: rows where current-season SV pace differs from
     prior-year SV/G by > 0.10 SV/G in absolute terms (excluding pitchers with
     no lag data — those are pure rookies, separate problem).

If both pass, ship as production. If overall regresses, hard fail (don't trade
overall accuracy for niche signal). If only role-change fails, document the
negative result and revert.

Unit note (rest-of-season is NOT mis-scaled — verified 2026-06-11):
  The model TARGET is `fp_year_total` (a full-SEASON FP total), and
  `xfp_full_year` is that full-season projection. The user-facing
  rest-of-season figure `xfp_ros` is NOT the raw full-season number — it is
  `xfp_full_year - fp_actual_2026`, i.e. the full-season projection MINUS the
  FP already banked this season (computed live from the counting-stats JSON).
  So `xfp_ros` is a genuine forward/RoS figure (mean ~82 FP vs full-year ~142
  in the 2026-06-09 run; the subtraction is live for every row). The "RP is
  mis-scaled mid-season" flag from `verdict_backtest_2026-06-11.md` was a
  BACKTEST-COMPARISON ARTIFACT, not a production bug: that backtest's RANKING
  LENS deliberately compared the full-season projection against a partial
  (season-to-date) actual — a unit mismatch the backtest itself flagged — and
  did so only to get a leakage-safe rank check while the season is incomplete.
  Production already converts to RoS correctly, so NO production change is
  warranted here. (See the comment at the `xfp_ros` assignment below.)

Ranking-layer fix (issue #9, fixed 2026-08-16):
  `xfp_ros` itself was always correct (see above), but `rank` /
  `replacement_xfp` / `replacement_delta` / `signal` were computed off
  `xfp_full_year` — which INCLUDES banked FP — not off `xfp_ros`. Net effect:
  an RP who missed time read as a false 'drop' regardless of forward outlook
  (e.g. Pagán, 10 SV as CIN's current closer, ranked below Weaver, a low-SV
  setup man, purely because Pagán's injury absence was baked into his total).
  Fixed by `assign_ranking_columns()` below, which sorts/replaces on
  `xfp_ros`/`xfp_ros_p25`/`xfp_ros_p75`. `xfp_full_year` remains in the
  output CSV as a season-to-date diagnostic only — never the ranking basis.

ADR-0001: this module owns its own fit_and_project orchestration. The shared
`engine.py` is a toolkit composed at load-bearing steps, not an orchestrator.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import warnings
import json
import numpy as np
import pandas as pd
import joblib

from plv_clone.models.xfp import engine as _engine
from plv_clone.models.xfp.engine import lookup_sigma, lookup_sigma_vec  # re-export
from plv_clone.models.xfp.engine import quantile_band  # noqa: F401  the ONE band owner
from plv_clone.league_config import RP_REPLACEMENT_RANK as REPLACEMENT_RANK_RP

warnings.filterwarnings('ignore')

# Path anchors: this file lives at src/plv_clone/models/xfp/rprs2.py, so parents[4]
# is the repo root (rprs2.py → xfp → models → plv_clone → src → repo root).
ROOT = Path(__file__).resolve().parents[4]
ROLLING_CSV = ROOT / 'data' / 'research' / 'xfp_cache' / 'rolling_relievers_2018_2026.csv'
COUNTING_DIR = ROOT / 'data' / 'research' / 'xfp_cache'
MODEL_PKL = ROOT / 'data' / 'models' / 'xfp_rprs2_pipeline.pkl'
PROJ_CSV  = ROOT / 'data' / 'outputs' / 'xfp_rprs2_projections.csv'

# Per-rebuild coefficient dump dir. Diagnostic only — never wire into
# downstream consumers. Supports per-feature audits (e.g., cohort-shift
# analysis in rprs2_audit_phase0_REAUDIT_2026-06-05.md, which couldn't
# fully reproduce read-only because fitted pipelines weren't persisted).
COEF_DIR = ROOT / 'data' / 'research' / 'model_coefficients'
_HLD_WEIGHT = 3  # BrownU RP scoring: SV*5 + HLD*3 (ESPN statId 60 = 3.0, verified live 2026-08-12)

# 2020 COVID-shortened season is excluded from TRAIN_YEARS by construction.

TARGET = 'fp_year_total'
EVAL_G_MIN = 5
TRAIN_YEARS = [2019, 2021, 2022, 2023, 2024, 2025]

# Baseline (RP-RS1) feature set — for the gate comparison
BASE_FEATS = [
    'k_pct_to', 'bb_pct_to', 'swstr_pct_to', 'c_plus_swstr_to',
    'xwoba_per_pa_to', 'avg_velo_to', 'zone_pct_to', 'o_swing_pct_to',
    'g_to', 'ip_to', 'fp_skill_to',
    'role_closer_lag1', 'role_setup_lag1', 'role_middle_lag1',
    'sv_lag1', 'hld_lag1', 'g_lag1', 'ip_lag1',
    'fp_per_g_lag1', 'fp_lag1',
    'split_day',
]
# New features added in RP-RS2
NEW_FEATS = [
    'gf_pct_to', 'sv_per_g_to', 'hld_per_g_to', 'sv_plus_hld_to',
    'fp_with_role_to',
    'sv_per_g_lag1', 'hld_per_g_lag1',
]
FEATS_RPRS2 = BASE_FEATS + NEW_FEATS

# ADR-0003 phase-5 hard assert: every FEATS entry must have a PASS
# validation_runs record. Backfill completed 2026-05-23.
from plv_clone.models.xfp.validated_signals import check_feats_validated as _check_feats_validated
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402
with warnings.catch_warnings():
    warnings.simplefilter("default", UserWarning)
    _check_feats_validated(FEATS_RPRS2, target="rprs2", strict=True)


def _dump_coefs(pipe, feats: list[str], fit_type: str, n_train: int,
                is_latest: bool = False) -> None:
    """Persist standardized ridge coefficients for diagnostic per-feature audits.

    Atomic write (temp + rename). NaN-safe — skips dump if any coef is NaN.
    Never read by downstream consumers; pure diagnostic artifact.
    """
    try:
        ridge = pipe.named_steps['r']
        coefs = np.asarray(ridge.coef_, dtype=float)
        intercept = float(ridge.intercept_)
        if not np.all(np.isfinite(coefs)) or not np.isfinite(intercept):
            print(f'  [dump_coefs] skip {fit_type}: non-finite coef/intercept')
            return
        from datetime import datetime as _dt
        ts = _dt.now()
        payload = {
            'fit_timestamp': ts.isoformat(timespec='seconds'),
            'fit_type': fit_type,
            'hld_weight': _HLD_WEIGHT,
            'intercept': intercept,
            'features': list(feats),
            'coefficients': coefs.tolist(),
            'n_train_rows': int(n_train),
            'target_col': TARGET,
        }
        COEF_DIR.mkdir(parents=True, exist_ok=True)
        stamp = ts.strftime('%Y-%m-%d-%H%M')
        dated = COEF_DIR / f'rprs2_coefs_{stamp}_{fit_type}.json'
        tmp = dated.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(dated)
        if is_latest:
            latest = COEF_DIR / 'rprs2_coefs_latest.json'
            tmp2 = latest.with_suffix('.json.tmp')
            tmp2.write_text(json.dumps(payload, indent=2))
            tmp2.replace(latest)
    except Exception as e:
        print(f'  [dump_coefs] error {fit_type}: {e}')


_FIT_FP_VERSION = 1


# eligibility mask shared by the fit stages (hoisted scaffolding, audit D2).
# NOTE: cross_year_eval below stays LOCAL by design — its indexed detail frame
# (for subset masks), coef dumps, and mae rounding differ from the rh3/rp3
# shape that engine.cross_year_eval_ridge captures.
def _fit_filter(d: pd.DataFrame):
    return d['year'].isin(TRAIN_YEARS) & (d['g_to'] >= EVAL_G_MIN)


def _fit_fingerprint(rolling: pd.DataFrame, feats: list[str]) -> str:
    return _engine.fit_fingerprint(
        rolling, feats, target=TARGET, train_years=TRAIN_YEARS,
        extra=(TARGET,), fp_version=_FIT_FP_VERSION)


def cross_year_eval(df: pd.DataFrame, feats: list[str], subset_mask=None,
                    dump_coefs_tag: str | None = None):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import RidgeCV
    df = df.dropna(subset=feats + [TARGET]).copy()
    df = df[df['year'].isin(TRAIN_YEARS) & (df['g_to'] >= EVAL_G_MIN)]
    per_year, preds_all, acts_all = {}, [], []
    test_indices = []
    for held in TRAIN_YEARS:
        train = df[df['year'] != held]; test = df[df['year'] == held]
        if len(train) < 100 or len(test) < 30:
            continue
        pipe = Pipeline([('sc', StandardScaler()),
                         ('r', RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        pipe.fit(train[feats].values, train[TARGET].values)
        if dump_coefs_tag is not None:
            _dump_coefs(pipe, feats, fit_type=f'{dump_coefs_tag}_loo_year_{held}',
                        n_train=len(train), is_latest=False)
        preds = pipe.predict(test[feats].values)
        r = float(np.corrcoef(preds, test[TARGET].values)[0, 1])
        mae = float(np.mean(np.abs(preds - test[TARGET].values)))
        per_year[held] = {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(test)}
        preds_all.extend(preds.tolist())
        acts_all.extend(test[TARGET].tolist())
        test_indices.extend(test.index.tolist())
    detail = pd.DataFrame({'pred': preds_all,
                           'actual': acts_all,
                           'split_day': df.loc[test_indices, 'split_day'].values},
                          index=test_indices)
    detail['resid'] = detail['actual'] - detail['pred']
    if subset_mask is not None:
        return per_year, _masked_overall(detail, subset_mask), detail
    overall_r = float(np.corrcoef(preds_all, acts_all)[0, 1]) if preds_all else np.nan
    overall_mae = float(np.mean(np.abs(np.array(preds_all) - np.array(acts_all))))
    return per_year, {'r': round(overall_r, 4), 'mae': round(overall_mae, 2),
                      'n': len(preds_all)}, detail


def _masked_overall(detail: pd.DataFrame, subset_mask) -> dict:
    """Subset metrics from an ALREADY-FIT detail frame — this used to refit the
    entire LOO just to score a subset (audit 2026-07-04, ~18s/run duplicate)."""
    keep = subset_mask.reindex(detail.index).fillna(False).values
    preds_arr = detail['pred'].values[keep]
    acts_arr = detail['actual'].values[keep]
    if len(preds_arr) < 30:
        return {'r': np.nan, 'mae': np.nan, 'n': len(preds_arr)}
    r = float(np.corrcoef(preds_arr, acts_arr)[0, 1])
    mae = float(np.mean(np.abs(preds_arr - acts_arr)))
    return {'r': round(r, 4), 'mae': round(mae, 2), 'n': len(preds_arr)}


def role_change_mask(df: pd.DataFrame) -> pd.Series:
    """Identify rows where current-year SV pace differs from prior-year SV pace
    by > 0.10 SV/G in absolute terms. Excludes rows with no lag data (sv_per_g_lag1
    will be 0 if no prior). For role-change detection, both sides should be > 0
    OR have a meaningful gap."""
    sv_now_per_g = df['sv_to'] / df['g_to'].replace(0, np.nan)
    sv_lag_per_g = df['sv_per_g_lag1']
    gap = (sv_now_per_g - sv_lag_per_g).abs()
    has_lag = df['sv_per_g_lag1'].notna() & (df['g_lag1'] >= 20)
    return (gap > 0.10) & has_lag


def fit_residual_ci(df, feats, resid=None):
    # `resid`: detail frame from cross_year_eval — identical fits (same filters,
    # 100/30 mins verified); the second LOO pass was pure duplication.
    return _engine.fit_residual_ci_from(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=_fit_filter, min_train=100, min_test=30, resid=resid,
        min_split_n=30)


def train_final(df, feats):
    return _engine.train_final_ridge(
        df, feats, target=TARGET, train_years=TRAIN_YEARS,
        filter_fn=lambda d: d['g_to'] >= EVAL_G_MIN)


def ros_band(mean, sigma, z=0.6745):
    """RoS p25/p75 (issue #29). Thin alias — see :func:`quantile_band`."""
    return quantile_band(mean, sigma, z=z)


def assign_ranking_columns(valid: pd.DataFrame, replacement_rank: int) -> pd.DataFrame:
    """Compute replacement_xfp / replacement_delta / signal / rank off
    `xfp_ros` — the genuine forward figure — not `xfp_full_year`, which
    includes FP already banked this season. Ranking off xfp_full_year makes
    the decision-facing columns read as season-to-date accounting instead of
    a rest-of-season call: an RP who missed time reads as a false 'drop' no
    matter his forward outlook, and a heavily-used healthy arm can read as a
    false 'hold' even with a weak forward projection. See GitHub issue #9.
    `xfp_full_year` is retained in the output CSV as a diagnostic only.
    """
    sorted_by_ros = valid.sort_values('xfp_ros', ascending=False).reset_index(drop=True)
    if len(sorted_by_ros) >= replacement_rank:
        repl = float(sorted_by_ros['xfp_ros'].iloc[replacement_rank - 1])
    else:
        repl = float(sorted_by_ros['xfp_ros'].median())
    valid['replacement_xfp'] = round(repl, 1)
    valid['replacement_delta'] = (valid['xfp_ros'] - repl).round(1)

    _rep = valid['replacement_xfp']
    valid['signal'] = np.select(
        [
            valid['replacement_delta'].isna() | _rep.isna(),
            valid['xfp_ros_p25'].notna() & (valid['xfp_ros_p25'] > _rep),
            valid['xfp_ros_p75'].notna() & (valid['xfp_ros_p75'] < _rep),
        ],
        ['hold', 'add', 'drop'],
        default='hold',
    )
    valid = valid.sort_values('xfp_ros', ascending=False).reset_index(drop=True)
    valid['rank'] = valid.index + 1
    return valid


def main():
    print('=== xfp_rprs2_pipeline (RoS RP + role-usage features) ===')
    rolling = pd.read_csv(ROLLING_CSV)
    print(f'rolling substrate: {len(rolling)} rows')

    # Identify the role-change subset (validation cohort)
    rc_mask = role_change_mask(rolling)
    print(f'\nRole-change subset (|sv/g_now − sv/g_lag1| > 0.10 AND has lag): {rc_mask.sum()} rows')

    # ── Fingerprint warm-skip (audit 2026-07-04): both gates re-run exactly
    # when the train slice or FEATS change; on a match the prior PASS stands.
    _fp = _fit_fingerprint(rolling, FEATS_RPRS2)
    _warm = None
    if MODEL_PKL.exists():
        try:
            _b = joblib.load(MODEL_PKL)
            if _b.get('fit_fingerprint') == _fp:
                _warm = _b
        except Exception:
            _warm = None
    if _warm is not None:
        print('\n[warm-fit] fingerprint match — LOO evals / gates / CI / final fit '
              'loaded from bundle (re-run whenever train data or FEATS change)')
        per_year = _warm['per_year_r']
        overall = {'r': _warm['cross_year_r'], 'mae': _warm['cross_year_mae'], 'n': None}
        baseline_overall = {'r': _warm['baseline_rprs1_r']}
        overall_rc = {'r': _warm['role_change_subset_r']}
        baseline_rc = {'r': _warm['role_change_subset_baseline_r']}
        delta_overall = _warm['delta_overall']
        delta_rc = _warm['delta_role_change']
        ci_table = _warm['ci_table']
        overall_sigma = _warm['overall_sigma']
        pipe = _warm['pipeline']
        n_train = _warm['n_train']
    else:
        # Baseline RP-RS1: BASE_FEATS only
        print('\n--- BASELINE RP-RS1 (BASE_FEATS only) ---')
        _per, baseline_overall, _detB = cross_year_eval(rolling, BASE_FEATS)
        baseline_rc = _masked_overall(_detB, rc_mask)   # from the SAME fit (was a full re-fit)
        print(f'  Overall:        r={baseline_overall["r"]}  mae={baseline_overall["mae"]}  n={baseline_overall["n"]}')
        print(f'  Role-change:    r={baseline_rc["r"]}       mae={baseline_rc["mae"]}      n={baseline_rc["n"]}')

        # RP-RS2: BASE + NEW
        print('\n--- RP-RS2 (BASE + role-usage features) ---')
        per_year, overall, _detF = cross_year_eval(rolling, FEATS_RPRS2, dump_coefs_tag='rprs2')
        overall_rc = _masked_overall(_detF, rc_mask)    # from the SAME fit (was a full re-fit)
        for y, m in sorted(per_year.items()):
            print(f'  {y}: r={m["r"]:.4f}  mae={m["mae"]:.2f}  n={m["n"]}')
        print(f'  Overall:        r={overall["r"]}  mae={overall["mae"]}  n={overall["n"]}')
        print(f'  Role-change:    r={overall_rc["r"]}       mae={overall_rc["mae"]}      n={overall_rc["n"]}')

        delta_overall = overall['r'] - baseline_overall['r']
        delta_rc      = overall_rc['r'] - baseline_rc['r']
        print(f'\n--- GATE EVALUATION ---')
        print(f'  Δr overall (gate ≥ 0.0):       {delta_overall:+.4f}  '
              f'{"PASS" if delta_overall >= 0.0 else "FAIL"}')
        print(f'  Δr role-change (gate ≥ +0.05): {delta_rc:+.4f}  '
              f'{"PASS" if delta_rc >= 0.05 else "FAIL"}')

        overall_pass = (delta_overall >= 0.0)
        rc_pass = (delta_rc >= 0.05)
        if not overall_pass:
            print('\nOVERALL r REGRESSED — rejecting RP-RS2 (would degrade general accuracy).')
            raise SystemExit(1)   # audit 2026-07-04: exiting 0 silently served a STALE projections CSV
        if not rc_pass:
            print('\nROLE-CHANGE subset DID NOT IMPROVE — features have no signal where it matters.')
            print('Documenting negative result; not promoting.')
            raise SystemExit(1)   # ditto — gate failure must be loud, not a stale-serve

        print('\n[BOTH GATES PASSED] Promoting RP-RS2 to production.')

        # Residual CI + final train
        ci_table, overall_sigma = fit_residual_ci(rolling, FEATS_RPRS2, resid=_detF)
        pipe, n_train = train_final(rolling, FEATS_RPRS2)
        # Persist final-fit coefficients (diagnostic; latest pointer).
        _dump_coefs(pipe, FEATS_RPRS2, fit_type='full_fit', n_train=n_train, is_latest=True)
        coefs = pipe.named_steps['r'].coef_
        print(f'\n--- Final RP-RS2 (n={n_train}, alpha={pipe.named_steps["r"].alpha_:.1f}, '
              f'{len(FEATS_RPRS2)} features) ---')
        print('  Top 12 coefficients:')
        for f, c in sorted(zip(FEATS_RPRS2, coefs), key=lambda x: -abs(x[1]))[:12]:
            print(f'    {f:<22s} {c:+.4f}')
        print('  NEW feature coefficients:')
        for f, c in zip(FEATS_RPRS2, coefs):
            if f in NEW_FEATS:
                print(f'    {f:<22s} {c:+.4f}')


    # Project 2026
    # projection year = latest season in the substrate (audit R2: the old
    # hardcoded ==2026 would silently no-op on 2027-01-01)
    proj_year = int(rolling['year'].max())
    df_26 = rolling[rolling['year'] == proj_year].copy()
    if df_26.empty:
        return
    latest_split = int(df_26['split_day'].max())
    df_26 = df_26[(df_26['split_day'] == latest_split) & (df_26['g_to'] >= EVAL_G_MIN)]
    valid = df_26.dropna(subset=FEATS_RPRS2).copy()
    valid['xfp_full_year'] = pipe.predict(valid[FEATS_RPRS2].values).round(1)

    train_for_buckets = rolling.dropna(subset=FEATS_RPRS2 + [TARGET])
    train_for_buckets = train_for_buckets[
        train_for_buckets['year'].isin(TRAIN_YEARS) & (train_for_buckets['g_to'] >= EVAL_G_MIN)]
    train_pred = pipe.predict(train_for_buckets[FEATS_RPRS2].values)
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
    valid['xfp_sigma'] = lookup_sigma_vec(
        ci_table, overall_sigma, latest_split,
        valid['xfp_full_year'].to_numpy(), pred_buckets)
    # Full-year band through the same owner as the RoS band. The old
    # `.clip(lower=0)` on p25 ALONE inverted the band for every reliever
    # projected below zero (29/397 rows by 2026-08-29). See quantile_band.
    valid['xfp_p25'], valid['xfp_p75'] = quantile_band(
        valid['xfp_full_year'].to_numpy(), valid['xfp_sigma'].to_numpy(), z=Z25)
    assert ((valid['xfp_p25'] <= valid['xfp_full_year'])
            & (valid['xfp_full_year'] <= valid['xfp_p75'])).all(),         'rprs2 full-year band inversion — see quantile_band'

    # counting-stats path follows the projection year (audit R2). NOTE: the
    # fp_actual_2026 / sv_2026 / hld_2026 COLUMN names are downstream schema
    # (dashboards read them) and stay fixed regardless of season.
    cnt = json.loads((COUNTING_DIR / f'pitcher_counting_stats_{proj_year}.json').read_text())
    cnt_df = pd.DataFrame(cnt)
    def parse_ip(v):
        # Delegates to the ONE canonical parser (issue #78). NaN (not 0.0) on a
        # miss — this is Series-mapped and a zero would be a real value.
        if v is None or pd.isna(v):
            return np.nan
        return _canon_parse_ip(v, default=np.nan)
    cnt_df['ip'] = cnt_df['inningsPitched'].map(parse_ip)
    # canonical BrownU weights via scoring.pitcher_fp (audit #4 — this was one
    # of ~15 inline re-derivations). A/B-verified vs the old inline expression
    # 2026-07-19: projections CSV identical.
    from plv_clone.fantasy.scoring import pitcher_fp as _pfp
    cnt_df['fp_actual_2026'] = _pfp(
        k=cnt_df['strikeOuts'], ip=cnt_df['ip'], h=cnt_df['hits'],
        er=cnt_df['earnedRuns'], bb=cnt_df['baseOnBalls'],
        hbp=cnt_df['hitByPitch'], sv=cnt_df['saves'], hld=cnt_df['holds'],
    ).round(1)
    cnt_df = cnt_df[['pitcher','name','saves','holds','fp_actual_2026']].rename(
        columns={'name':'name_api','saves':'sv_2026','holds':'hld_2026'})
    valid = valid.merge(cnt_df, on='pitcher', how='left')
    # Match-rate guard (audit 2026-07-19, same failure shape as the 6-week
    # rp3 IL-join regression): if the counting-stats id space desyncs from the
    # rolling substrate, every fp_actual_2026 silently becomes 0 and xfp_ros
    # collapses to xfp_full_year for the whole board. Fail LOUD instead.
    _cnt_match = float(valid['fp_actual_2026'].notna().mean()) if len(valid) else 0.0
    print(f'  counting-stats join match rate: {_cnt_match:.0%} ({valid["fp_actual_2026"].notna().sum()}/{len(valid)})')
    if len(valid) >= 20 and _cnt_match < 0.5:
        raise RuntimeError(
            f'rprs2 counting-stats join matched only {_cnt_match:.0%} of the RP pool '
            f'— pitcher_counting_stats JSON is stale or id-desynced; refusing to '
            f'publish an xfp_ros board with the RoS subtraction silently zeroed.')
    valid['fp_actual_2026'] = valid['fp_actual_2026'].fillna(0)
    # xfp_ros is the GENUINE rest-of-season figure: the full-season projection
    # (model target = fp_year_total) MINUS the FP already banked in 2026. This
    # is the correct mid-season scaling — do NOT publish xfp_full_year as the
    # forward number. The verdict_backtest_2026-06-11 "RP mis-scale" note was a
    # backtest-comparison artifact (its ranking lens compares full-season proj
    # vs partial actual on purpose); production is correct. See module docstring.
    valid['xfp_ros'] = (valid['xfp_full_year'] - valid['fp_actual_2026']).round(1)
    valid['xfp_ros_p25'], valid['xfp_ros_p75'] = quantile_band(
        valid['xfp_ros'].to_numpy(), valid['xfp_sigma'].to_numpy())
    assert ((valid['xfp_ros_p25'] <= valid['xfp_ros'])
            & (valid['xfp_ros'] <= valid['xfp_ros_p75'])).all(),         'rprs2 RoS band inversion — see issue #29'

    # rank / replacement_xfp / replacement_delta / signal are forward-looking
    # (xfp_ros-based) as of the issue #9 fix — xfp_full_year is retained below
    # as a season-to-date diagnostic only, not the ranking basis.
    valid = assign_ranking_columns(valid, REPLACEMENT_RANK_RP)

    # data_quality_tag — mirrors the rp3 convention so a prior-driven row is
    # never mistaken for a measured one.
    #
    # 47% of the live RP universe (174/368 on 2026-08-18) has NO prior-year
    # relief role: rookies, converted starters, and mid-season call-ups. For
    # those rows `role_lag1` is null and the one-hots are all zero, but the
    # NUMERIC lag features (sv_lag1 / hld_lag1) are mean-imputed by the
    # pipeline — so the model effectively reads "had ~4 SV and ~8 HLD last
    # year" where the truth is "unknown". The projection is then substantially
    # prior-driven, exactly like rp3's `marcel_il` rows.
    #
    # Canonical miss this prevents: Jacob Latz, 25 SV and a 67% GF share in
    # 2026 and PL's #6 reliever, projected BELOW replacement purely because his
    # lag features were imputed — which read as a drop signal.
    #
    # This is a LABEL, not a model change: no feature is added, removed or
    # reweighted, so it needs no /validate-feature gate. Fixing the imputation
    # itself (e.g. a missing-role indicator feature) WOULD be a model change
    # and must go through Rule 9 first.
    #
    # Issue #30: this ships as its OWN column (lag_quality_tag) — it tracks
    # PRIOR-season availability, the opposite axis from rp3's current-season
    # data_quality_tag, and reusing that name inverted its meaning (Latz, 25
    # SV in 2026, read as untrustworthy). data_quality_tag below mirrors
    # rp3's convention on CURRENT-season sample size instead.
    if 'role_lag1' in valid.columns:
        valid['lag_quality_tag'] = np.where(
            valid['role_lag1'].isna(), 'lag_imputed', 'lag_observed')
    else:  # schema drift upstream must not KeyError mid-write
        valid['lag_quality_tag'] = 'lag_imputed'
    _g_to = valid['g_to'].fillna(0)
    valid['data_quality_tag'] = np.select(
        [_g_to == 0, _g_to >= 10],
        ['marcel_no_data', 'data_driven_full'],
        default='data_driven_thin')

    bundle = {
        'pipeline': pipe,
        'features': FEATS_RPRS2,
        'features_baseline': BASE_FEATS,
        'features_new': NEW_FEATS,
        'target': TARGET,
        'cross_year_r': overall['r'],
        'cross_year_mae': overall['mae'],
        'baseline_rprs1_r': baseline_overall['r'],
        'role_change_subset_r': overall_rc['r'],
        'role_change_subset_baseline_r': baseline_rc['r'],
        'delta_overall': round(delta_overall, 4),
        'delta_role_change': round(delta_rc, 4),
        'per_year_r': per_year,
        'ci_table': ci_table,
        'pred_buckets': {k: v.tolist() for k, v in pred_buckets.items()},
        'overall_sigma': overall_sigma,
        'training_years': TRAIN_YEARS,
        'min_g_to': EVAL_G_MIN,
        'replacement_rank': REPLACEMENT_RANK_RP,
        'gate_overall': 0.0,
        'gate_role_change': 0.05,
        'fit_fingerprint': _fp,
        'trained_date': str(date.today()),
        'n_train': n_train,
        'version': 'rprs2',
        'note': 'RP RoS model with statcast-derived in-season role-usage features '
                '(GF%, SV/G, HLD/G, SV+HLD, FP-with-role). Stratified-validated.',
    }
    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PKL)
    print(f'\nWrote {MODEL_PKL}')

    keep = ['rank','pitcher','name_api','data_quality_tag','lag_quality_tag',
            'role_lag1','sv_lag1','hld_lag1',
            'g_to','sv_to','hld_to','gf_to','gf_pct_to','sv_per_g_to',
            'sv_2026','hld_2026',
            'fp_actual_2026','xfp_full_year','xfp_p25','xfp_p75',
            'xfp_ros','xfp_ros_p25','xfp_ros_p75',
            'replacement_xfp','replacement_delta','signal']
    keep = [c for c in keep if c in valid.columns]
    # ATOMIC write (temp + rename), matching _dump_coefs and the pl_cache
    # writer. A plain to_csv leaves the file zero-length for a beat, and
    # readers of this path are NOT coordinated with the writer: the nightly
    # triangulate batch reads it via lib/cached_data._load_projection('RP')
    # and died with `EmptyDataError: No columns to parse from file` on
    # 2026-08-18 when a rebuild overlapped the daily refresh. Rename is atomic
    # on the same filesystem, so a concurrent reader sees either the old file
    # or the new one, never a truncated one.
    _tmp = PROJ_CSV.with_suffix('.csv.tmp')
    valid[keep].to_csv(_tmp, index=False)
    _tmp.replace(PROJ_CSV)
    print(f'Wrote {PROJ_CSV}: {len(valid)} 2026 RP RoS projections')

    print('\nTop 15 by projected RoS FP:')
    show = valid.sort_values('xfp_ros', ascending=False).head(15)
    cols_show = ['rank','name_api','data_quality_tag','lag_quality_tag','role_lag1','g_to','sv_to','gf_to','sv_2026',
                 'fp_actual_2026','xfp_full_year','xfp_ros','signal','replacement_delta']
    print(show[cols_show].to_string(index=False))


if __name__ == '__main__':
    main()
