# Pre-registered: data/research/validation_runs/milb_aaa_translation_2026-07-19.md
"""milb_aaa_translation — callup-subgroup AAA->MLB translated FP prior (Wave 3B).

Not a global feature add (AAA K% global add already MARGINAL 2026-05-24): asks
whether a translated AAA rate profile beats production rh3 handling WITHIN the
callup subgroup (prior_pa_eff < 150 & pa_to < 150), where the absorber is weakest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))

import _validate_rh3_v3_helper as H  # noqa: E402
from plv_clone.models.xfp import rh3  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
AAA_MIN_PA, MLB_MIN_PA = 150, 100
FIT_YEARS = range(2015, 2024)
TRANS_FEATS = ["k_pct", "bb_pct", "iso", "hr_per_pa", "age"]
SUB_PRIOR_MAX, SUB_PA_MAX = 150.0, 150.0
PRED_PA_MIN, PRED_ROS_MIN = 10.0, 50.0
EVAL_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
HOLDOUT = {2024, 2025}


def build_translation():
    milb = pd.read_csv(CACHE / "milb_hitters_2015_2026.csv")
    aaa = milb[(milb["level"] == "AAA") & (milb["plateAppearances"] >= AAA_MIN_PA)].copy()
    # collapse multi-stint rows: PA-weighted
    aaa = (
        aaa.groupby(["batter", "season"])
        .apply(lambda g: pd.Series({
            **{f: np.average(g[f], weights=g["plateAppearances"]) for f in TRANS_FEATS},
            "aaa_pa": g["plateAppearances"].sum()}), include_groups=False)
        .reset_index()
    )
    mlb = pd.read_csv(rh3.MULTIYR_CSV)[["batter", "year", "pa", "fp_per_pa_actual"]]
    mlb = mlb[mlb["pa"] >= MLB_MIN_PA]

    pairs = []
    for lag in (0, 1):  # same-year preferred, else next year
        m = aaa.merge(mlb, left_on=["batter"], right_on=["batter"])
        m = m[m["year"] == m["season"] + lag]
        m["lag"] = lag
        pairs.append(m)
    p = pd.concat(pairs, ignore_index=True).sort_values("lag").drop_duplicates(["batter", "season"])
    p = p[p["season"].isin(FIT_YEARS)]
    print(f"translation fit pairs (2015-2023): {len(p)}")

    pipe = Pipeline([("sc", StandardScaler()), ("m", LinearRegression())])
    pipe.fit(p[TRANS_FEATS].values, p["fp_per_pa_actual"].values)
    r = np.corrcoef(pipe.predict(p[TRANS_FEATS].values), p["fp_per_pa_actual"])[0, 1]
    print(f"in-sample translation r: {r:.3f}; coefs "
          f"{dict(zip(TRANS_FEATS, np.round(pipe.named_steps['m'].coef_, 4)))}")
    return pipe, aaa


def main() -> None:
    print("=== /validate-feature: milb_aaa_translation (rh3 callup subgroup, Wave 3B) ===")
    pipe, aaa = build_translation()

    rolling = H.load_and_prep_rh3_inputs()

    # candidate: latest AAA season <= year (prefer same year, min 150 PA)
    aaa["pred_fp_pa"] = pipe.predict(aaa[TRANS_FEATS].values)
    cand_rows = []
    for lag in (0, 1, 2):
        a = aaa.copy()
        a["year"] = a["season"] + lag
        a["lag"] = lag
        cand_rows.append(a[["batter", "year", "pred_fp_pa", "lag"]])
    cand = (pd.concat(cand_rows, ignore_index=True)
            .sort_values("lag").drop_duplicates(["batter", "year"]))

    sub = rolling[
        (rolling["prior_pa_eff"] < SUB_PRIOR_MAX) & (rolling["pa_to"] < SUB_PA_MAX)
        & (rolling["pa_to"] >= PRED_PA_MIN) & (rolling["ros_pa"] >= PRED_ROS_MIN)
    ].copy()
    sub = sub.sort_values("split_day").drop_duplicates(["batter", "year"])  # earliest split
    sub = sub.merge(cand[["batter", "year", "pred_fp_pa"]], on=["batter", "year"], how="inner")
    print(f"subgroup rows (callup x AAA-line, 1/batter-year): {len(sub)}")
    print(sub.groupby("year").size().to_string())

    feats = list(rh3.RH3_FEATS)
    target = rh3.TARGET
    prod_filter = (rolling["pa_to"] >= rh3.EVAL_PA_MIN) & (rolling["ros_pa"] >= rh3.ROS_PA_MIN)
    base_pool = rolling[prod_filter].dropna(subset=feats + [target])

    per_year = {}
    pooled_train, pooled_hold = [], []
    for held in EVAL_YEARS:
        test = sub[sub["year"] == held].dropna(subset=feats + [target, "pred_fp_pa"])
        train = base_pool[base_pool["year"] != held]
        if len(test) < 10:
            per_year[held] = None
            continue
        ridge = Pipeline([("sc", StandardScaler()),
                          ("r", RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])
        ridge.fit(train[feats].values, train[target].values)
        base_pred = ridge.predict(test[feats].values)
        resid = test[target].values - base_pred
        # residualize candidate on baseline prediction
        c = test["pred_fp_pa"].values
        beta = np.polyfit(base_pred, c, 1)
        c_res = c - np.polyval(beta, base_pred)
        r, pval = pearsonr(c_res, resid)
        per_year[held] = (r, len(test))
        rows = pd.DataFrame({"c_res": c_res, "resid": resid})
        (pooled_hold if held in HOLDOUT else pooled_train).append(rows)
        print(f"  {held}: partial r={r:+.3f} (n={len(test)})"
              f"{' [<30: sign-only]' if len(test) < 30 else ''}")

    tr = pd.concat(pooled_train, ignore_index=True)
    ho = pd.concat(pooled_hold, ignore_index=True)
    r_tr, p_tr = pearsonr(tr["c_res"], tr["resid"])
    r_ho, p_ho = pearsonr(ho["c_res"], ho["resid"])
    signs = [1 if v and v[0] > 0 else 0 for v in per_year.values() if v]
    print(f"\npooled TRAIN partial r = {r_tr:+.4f} (p={p_tr:.3f}, n={len(tr)})  [gate 0.10]")
    print(f"pooled HOLDOUT partial r = {r_ho:+.4f} (p={p_ho:.3f}, n={len(ho)})  [gate 0.05]")
    print(f"sign consistency: {sum(signs)}/{len(signs)} positive  [gate 5/7]")


if __name__ == "__main__":
    main()
