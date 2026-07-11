"""validate_learner_upgrade.py — LEARNER UPGRADE test (Ridge -> HistGB), 2026-07-10.

Pre-registered: data/research/validation_runs/learner_upgrade_2026-07-10.md
(read it first — grid, gates, and honesty checks are frozen there).

Cells:
  L1 rh3 HistGradientBoostingRegressor vs production RidgeCV
  L2 rp3 HistGradientBoostingRegressor vs production RidgeCV
  L3 rh3 blend 0.5*Ridge + 0.5*GBM (out-of-fold, fixed weights)
  L4 rp3 blend

Identical rows / features / target / LOO folds as production cross_year_eval.
The prepped rolling frame is pickled once per model to a cache dir so every
fold chunk sees the SAME data even if the rolling CSV regenerates mid-session.

Usage (chunked so each foreground call stays under the 10-min cap):
  python scripts/xfp/validate_learner_upgrade.py --model rh3 --years 2025
  python scripts/xfp/validate_learner_upgrade.py --model rh3 --years 2018,2019,2021
  ...
  python scripts/xfp/validate_learner_upgrade.py --model rh3 --report
"""
from __future__ import annotations

import argparse
import json
import os
import time
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.metrics import make_scorer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))   # harness modules live next to this script
sys.path.insert(0, str(ROOT))   # for scripts.xfp.lib imports inside harness

TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
HOLDOUT_YEARS = [2024, 2025]
SEEDS = [0, 1, 2]

# Pre-registered grid (learner_upgrade_2026-07-10.md). Do NOT edit after runs.
GBM_GRID = {
    "max_iter": [200, 500],
    "learning_rate": [0.05, 0.1],
    "max_leaf_nodes": [15, 31],
    "min_samples_leaf": [50, 200],
}


def pearson_r(y_true, y_pred):
    """Inner-CV selection metric == outer metric (pre-registered)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if np.std(y_pred) < 1e-12 or np.std(y_true) < 1e-12:
        return 0.0
    return float(np.corrcoef(y_true, y_pred)[0, 1])


PEARSON_SCORER = make_scorer(pearson_r, greater_is_better=True)


# ---------------------------------------------------------------------------
# Model configs (production parity)
# ---------------------------------------------------------------------------

def _load_rh3():
    from _validate_rh3_v3_helper import load_and_prep_rh3_inputs
    from plv_clone.models.xfp import rh3
    df = load_and_prep_rh3_inputs()
    feats = list(rh3.RH3_FEATS)
    target = rh3.TARGET
    df = df.dropna(subset=feats + [target]).copy()
    df = df[(df["pa_to"] >= rh3.EVAL_PA_MIN) & (df["ros_pa"] >= rh3.ROS_PA_MIN)
            & (df["year"] != 2020)]
    return df, feats, target, {"min_train": 100, "min_test": 30}


def _load_rp3():
    from _rp3_validation_harness import prep_rolling
    from plv_clone.models.xfp import rp3
    df = prep_rolling()
    feats = list(rp3.RP3_FEATS)
    target = rp3.TARGET
    df = df.dropna(subset=feats + [target]).copy()
    df = df[(df["gs_to"] >= rp3.EVAL_GS_MIN) & (df["ros_gs"] >= rp3.ROS_GS_MIN)
            & (df["year"] != 2020)]
    return df, feats, target, {"min_train": 50, "min_test": 10}


LOADERS = {"rh3": _load_rh3, "rp3": _load_rp3}


def get_prepped(model: str, cache_dir: Path):
    """Load-once semantics: pickle the prepped+filtered frame on first call."""
    cache = cache_dir / f"learner_upgrade_prepped_{model}.pkl"
    meta_p = cache_dir / f"learner_upgrade_prepped_{model}.meta.json"
    if cache.exists():
        import pickle
        with open(cache, "rb") as f:
            bundle = pickle.load(f)
        print(f"[cache] loaded prepped {model} frame: n={len(bundle['df'])} "
              f"(prepped at {json.loads(meta_p.read_text())['prepped_at']})")
        return bundle["df"], bundle["feats"], bundle["target"], bundle["fold_min"]
    df, feats, target, fold_min = LOADERS[model]()
    import pickle
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump({"df": df, "feats": feats, "target": target,
                     "fold_min": fold_min}, f)
    meta_p.write_text(json.dumps({"prepped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                  "n": len(df), "n_feats": len(feats)}))
    print(f"[cache] prepped + froze {model} frame: n={len(df)}, "
          f"{len(feats)} feats, target={target}")
    return df, feats, target, fold_min


# ---------------------------------------------------------------------------
# Fold runner
# ---------------------------------------------------------------------------

def run_fold(df, feats, target, held, fold_min, out_dir: Path, model: str):
    train = df[df["year"] != held]
    test = df[df["year"] == held]
    if len(train) < fold_min["min_train"] or len(test) < fold_min["min_test"]:
        print(f"  [fold {held}] skipped (train={len(train)}, test={len(test)})")
        return None

    Xtr, ytr = train[feats].values, train[target].values
    Xte, yte = test[feats].values, test[target].values

    t0 = time.time()
    # --- Ridge: production pipeline exactly ---
    ridge = Pipeline([("sc", StandardScaler()),
                      ("r", RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
    ridge.fit(Xtr, ytr)
    pred_ridge = ridge.predict(Xte)
    insample_ridge = pearson_r(ytr, ridge.predict(Xtr))
    t_ridge = time.time() - t0

    # --- GBM: pre-registered light inner-CV tune on TRAIN years only ---
    t0 = time.time()
    inner = KFold(n_splits=3, shuffle=True, random_state=0)
    gs = GridSearchCV(
        HistGradientBoostingRegressor(random_state=0, early_stopping=False),
        GBM_GRID, cv=inner, scoring=PEARSON_SCORER, n_jobs=-1, refit=True,
    )
    gs.fit(Xtr, ytr)
    best = gs.best_params_
    gbm0 = gs.best_estimator_          # random_state=0, refit on full train fold
    pred_gbm = {0: gbm0.predict(Xte)}
    insample_gbm = pearson_r(ytr, gbm0.predict(Xtr))
    t_gbm = time.time() - t0

    # --- Stability seeds (same selected config, seeds 1 & 2) ---
    for s in SEEDS[1:]:
        g = HistGradientBoostingRegressor(random_state=s, early_stopping=False,
                                          **best)
        g.fit(Xtr, ytr)
        pred_gbm[s] = g.predict(Xte)

    # Fairness assert: identical rows for both learners
    assert len(pred_ridge) == len(pred_gbm[0]) == len(test), "row mismatch"

    fold_rows = pd.DataFrame({
        "year": held,
        "actual": yte,
        "pred_ridge": pred_ridge,
        "pred_gbm_s0": pred_gbm[0],
        "pred_gbm_s1": pred_gbm[1],
        "pred_gbm_s2": pred_gbm[2],
    })
    out_dir.mkdir(parents=True, exist_ok=True)
    fold_rows.to_csv(out_dir / f"{model}_fold_{held}_preds.csv", index=False)

    meta = {
        "model": model, "held_year": held,
        "n_train": len(train), "n_test": len(test),
        "best_params": best,
        "inner_cv_best_score": round(float(gs.best_score_), 4),
        "r_ridge": round(pearson_r(yte, pred_ridge), 4),
        "r_gbm_s0": round(pearson_r(yte, pred_gbm[0]), 4),
        "insample_r_ridge": round(insample_ridge, 4),
        "insample_r_gbm": round(insample_gbm, 4),
        "t_ridge_s": round(t_ridge, 1), "t_gbm_s": round(t_gbm, 1),
    }
    (out_dir / f"{model}_fold_{held}_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  [fold {held}] n_test={len(test)}  "
          f"ridge r={meta['r_ridge']:.4f} (in-sample {insample_ridge:.4f})  "
          f"gbm r={meta['r_gbm_s0']:.4f} (in-sample {insample_gbm:.4f})  "
          f"best={best}  [ridge {t_ridge:.0f}s, gbm {t_gbm:.0f}s]")
    return meta


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _pooled_stats(frames: dict[int, pd.DataFrame], pred_col: str):
    pooled = pd.concat(frames.values(), ignore_index=True)
    r = pearson_r(pooled["actual"], pooled[pred_col])
    mae = float(np.mean(np.abs(pooled[pred_col] - pooled["actual"])))
    per_year = {y: pearson_r(f["actual"], f[pred_col]) for y, f in sorted(frames.items())}
    return r, mae, per_year, pooled


def _decile_table(pooled: pd.DataFrame, pred_col: str) -> pd.DataFrame:
    q = pd.qcut(pooled[pred_col], 10, labels=False, duplicates="drop")
    g = pooled.groupby(q).agg(mean_pred=(pred_col, "mean"),
                              mean_actual=("actual", "mean"),
                              n=("actual", "size"))
    g["bias"] = g["mean_pred"] - g["mean_actual"]
    return g


def report(model: str, out_dir: Path, gate: float = 0.005):
    frames, metas = {}, {}
    for y in TRAIN_YEARS:
        p = out_dir / f"{model}_fold_{y}_preds.csv"
        m = out_dir / f"{model}_fold_{y}_meta.json"
        if p.exists():
            frames[y] = pd.read_csv(p)
            metas[y] = json.loads(m.read_text())
    if not frames:
        print(f"No fold outputs for {model} in {out_dir}")
        return None
    print(f"\n================ {model.upper()} REPORT "
          f"({len(frames)}/{len(TRAIN_YEARS)} folds) ================")

    frames_b = {y: f.assign(pred_blend=0.5 * f["pred_ridge"] + 0.5 * f["pred_gbm_s0"])
                for y, f in frames.items()}

    r_ridge, mae_ridge, py_ridge, pooled = _pooled_stats(frames_b, "pred_ridge")
    r_gbm, mae_gbm, py_gbm, _ = _pooled_stats(frames_b, "pred_gbm_s0")
    r_blend, mae_blend, py_blend, _ = _pooled_stats(frames_b, "pred_blend")
    r_s1 = pearson_r(pooled["actual"], pooled["pred_gbm_s1"])
    r_s2 = pearson_r(pooled["actual"], pooled["pred_gbm_s2"])

    print(f"\nPer-year r (n in parens):")
    print(f"  {'year':<6}{'n':>7}  {'ridge':>8}  {'gbm':>8}  {'blend':>8}  "
          f"{'d_gbm':>8}  {'d_blend':>8}")
    signs_gbm = signs_blend = 0
    for y in sorted(frames_b):
        n = len(frames_b[y])
        dg = py_gbm[y] - py_ridge[y]
        db = py_blend[y] - py_ridge[y]
        signs_gbm += dg > 0
        signs_blend += db > 0
        print(f"  {y:<6}{n:>7}  {py_ridge[y]:>8.4f}  {py_gbm[y]:>8.4f}  "
              f"{py_blend[y]:>8.4f}  {dg:>+8.4f}  {db:>+8.4f}")

    n_pool = len(pooled)
    print(f"\nPooled (n={n_pool}):")
    print(f"  ridge  r={r_ridge:.4f}  mae={mae_ridge:.4f}   <- measured baseline of record")
    print(f"  gbm    r={r_gbm:.4f}  mae={mae_gbm:.4f}   lift={r_gbm - r_ridge:+.4f}")
    print(f"  blend  r={r_blend:.4f}  mae={mae_blend:.4f}   lift={r_blend - r_ridge:+.4f}")

    ho_gbm = [py_gbm[y] - py_ridge[y] for y in HOLDOUT_YEARS if y in py_gbm]
    ho_blend = [py_blend[y] - py_ridge[y] for y in HOLDOUT_YEARS if y in py_blend]

    def verdict(lift, signs, ho):
        gates = {
            "lift_ge_0.005": lift >= gate,
            "signs_ge_5of7": signs >= 5,
            "holdout_avg_pos": (float(np.mean(ho)) > 0) if ho else False,
        }
        if lift < gate:
            v = "REJECTED"
        elif lift < 0.010:
            v = "MARGINAL" if all(gates.values()) else "REJECTED (gate fail)"
        else:
            v = "PASS (pending diagnostics)" if all(gates.values()) else "REJECTED (gate fail)"
        return v, gates

    v_gbm, g_gbm = verdict(r_gbm - r_ridge, signs_gbm, ho_gbm)
    v_blend, g_blend = verdict(r_blend - r_ridge, signs_blend, ho_blend)

    print(f"\nGates (gate=+{gate}):")
    print(f"  GBM   lift={r_gbm - r_ridge:+.4f}  signs={signs_gbm}/{len(frames_b)}  "
          f"holdout_d={['%+.4f' % d for d in ho_gbm]}  -> {v_gbm}")
    print(f"  BLEND lift={r_blend - r_ridge:+.4f}  signs={signs_blend}/{len(frames_b)}  "
          f"holdout_d={['%+.4f' % d for d in ho_blend]}  -> {v_blend}")

    # (a) Overfit diagnostic
    print("\n(a) Overfit diagnostic (train in-sample r vs held-out r):")
    gaps_r, gaps_g = [], []
    for y in sorted(metas):
        m = metas[y]
        gr = m["insample_r_ridge"] - m["r_ridge"]
        gg = m["insample_r_gbm"] - m["r_gbm_s0"]
        gaps_r.append(gr); gaps_g.append(gg)
        print(f"  {y}: ridge in={m['insample_r_ridge']:.4f} out={m['r_ridge']:.4f} "
              f"gap={gr:+.4f} | gbm in={m['insample_r_gbm']:.4f} "
              f"out={m['r_gbm_s0']:.4f} gap={gg:+.4f}  best={m['best_params']}")
    print(f"  mean gap: ridge {np.mean(gaps_r):+.4f} | gbm {np.mean(gaps_g):+.4f}")

    # (b) Tail check
    print("\n(b) Tail check — pooled pred-decile calibration (bias = mean_pred - mean_actual):")
    for name, col in [("ridge", "pred_ridge"), ("gbm", "pred_gbm_s0"),
                      ("blend", "pred_blend")]:
        t = _decile_table(pooled, col)
        lo, hi = t.iloc[0], t.iloc[-1]
        print(f"  {name:<6} decile1: pred={lo['mean_pred']:.4f} act={lo['mean_actual']:.4f} "
              f"bias={lo['bias']:+.4f} | decile10: pred={hi['mean_pred']:.4f} "
              f"act={hi['mean_actual']:.4f} bias={hi['bias']:+.4f}")

    # (c) Stability
    print("\n(c) Stability — pooled GBM r by seed:")
    print(f"  seed0={r_gbm:.4f}  seed1={r_s1:.4f}  seed2={r_s2:.4f}  "
          f"spread={max(r_gbm, r_s1, r_s2) - min(r_gbm, r_s1, r_s2):.4f}")

    results = {
        "model": model, "n_pooled": n_pool, "folds": sorted(frames),
        "pooled": {"r_ridge": round(r_ridge, 4), "r_gbm": round(r_gbm, 4),
                   "r_blend": round(r_blend, 4), "mae_ridge": round(mae_ridge, 4),
                   "mae_gbm": round(mae_gbm, 4), "mae_blend": round(mae_blend, 4)},
        "per_year": {str(y): {"n": len(frames_b[y]), "ridge": round(py_ridge[y], 4),
                              "gbm": round(py_gbm[y], 4), "blend": round(py_blend[y], 4)}
                     for y in sorted(frames_b)},
        "gates": {"gbm": g_gbm, "blend": g_blend},
        "verdict": {"gbm": v_gbm, "blend": v_blend},
        "overfit_gap_mean": {"ridge": round(float(np.mean(gaps_r)), 4),
                             "gbm": round(float(np.mean(gaps_g)), 4)},
        "seed_stability": {"s0": round(r_gbm, 4), "s1": round(r_s1, 4),
                           "s2": round(r_s2, 4)},
        "decile_tables": {name: _decile_table(pooled, col).round(4).to_dict("index")
                          for name, col in [("ridge", "pred_ridge"),
                                            ("gbm", "pred_gbm_s0"),
                                            ("blend", "pred_blend")]},
        "best_params_by_fold": {str(y): metas[y]["best_params"] for y in sorted(metas)},
    }
    res_path = ROOT / "data" / "research" / "validation_runs" / \
        f"learner_upgrade_2026-07-10_{model}_results.json"
    res_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {res_path}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["rh3", "rp3"], required=True)
    ap.add_argument("--years", default=None,
                    help="comma-separated held-out years to run (fold chunking)")
    ap.add_argument("--report", action="store_true",
                    help="pool saved fold outputs and print the full report")
    ap.add_argument("--outdir", default=None,
                    help="dir for fold outputs + prepped-frame cache")
    args = ap.parse_args()

    out_dir = Path(args.outdir) if args.outdir else \
        Path(os.environ.get("LEARNER_UPGRADE_OUTDIR", ROOT / ".cache" / "learner_upgrade"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.report:
        report(args.model, out_dir)
        return

    years = [int(y) for y in args.years.split(",")] if args.years else TRAIN_YEARS
    df, feats, target, fold_min = get_prepped(args.model, out_dir)
    print(f"[{args.model}] filtered frame n={len(df)}  feats={len(feats)}  "
          f"target={target}  running folds {years}")
    for y in years:
        run_fold(df, feats, target, y, fold_min, out_dir, args.model)


if __name__ == "__main__":
    main()
