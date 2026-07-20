"""aaa_translation.py — AAA→MLB translated FP prior for the rh3 callup blend.

Validated PASS 2026-07-19 (`milb_aaa_translation_2026-07-19.md`): within the
callup subgroup (prior_pa_eff < 150 & pa_to < 150) the translated AAA rate
profile carries large forward signal the thin MLB sample cannot (pooled train
partial r +0.276 / holdout +0.238 / 7/7 years). Production integration
(this module + the blend call in rh3.main, sign-off 2026-07-19): blend the
translated prior into `prior_fp_per_pa` with weight decaying as MLB PA accrue.

FROZEN SPEC (do not tune without a fresh prereg):
- Translation fit: 2015–2023 AAA→MLB pairs only (982 at build time), OLS on
  standardized [k_pct, bb_pct, iso, hr_per_pa, age]; MLB target
  fp_per_pa_actual (≥100 PA, same-year preferred then next-year).
- AAA line per (batter, year): most recent AAA season ≤ year with ≥150 AAA PA
  (PA-weighted across stints), lag preference 0 → 1 → 2 seasons.
- Blend (parameter-free, anchored on the validated 150-PA subgroup boundary):
    mlb_pa  = prior_pa_eff + pa_to
    w_aaa   = clip(150 − mlb_pa, 0, 150)          # decays to 0 at the boundary
    prior'  = (prior_pa_eff·prior + w_aaa·aaa_pred) / (prior_pa_eff + w_aaa)
  Rows without an AAA line, or with mlb_pa ≥ 150, are untouched.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from plv_clone.paths import ROOT

MILB_CSV = ROOT / "data" / "research" / "xfp_cache" / "milb_hitters_2015_2026.csv"
MULTIYR_CSV = ROOT / "data" / "research" / "xfp_cache" / "hitters_multiyr_2015_2026.csv"

AAA_MIN_PA, MLB_MIN_PA = 150, 100
FIT_SEASONS = range(2015, 2024)  # FROZEN — the validation's training window
TRANS_FEATS = ["k_pct", "bb_pct", "iso", "hr_per_pa", "age"]
CALLUP_PA_BOUNDARY = 150.0
MAX_AAA_LAG = 2


@lru_cache(maxsize=1)
def _aaa_seasons() -> pd.DataFrame:
    milb = pd.read_csv(MILB_CSV)
    aaa = milb[(milb["level"] == "AAA") & (milb["plateAppearances"] >= AAA_MIN_PA)]
    return (
        aaa.groupby(["batter", "season"])
        .apply(lambda g: pd.Series({
            **{f: np.average(g[f], weights=g["plateAppearances"]) for f in TRANS_FEATS},
            "aaa_pa": g["plateAppearances"].sum()}), include_groups=False)
        .reset_index()
    )


@lru_cache(maxsize=1)
def _translation_pipe() -> Pipeline:
    aaa = _aaa_seasons()
    mlb = pd.read_csv(MULTIYR_CSV)[["batter", "year", "pa", "fp_per_pa_actual"]]
    mlb = mlb[mlb["pa"] >= MLB_MIN_PA]
    pairs = []
    for lag in (0, 1):
        m = aaa.merge(mlb, on="batter")
        m = m[m["year"] == m["season"] + lag]
        m["lag"] = lag
        pairs.append(m)
    p = (pd.concat(pairs, ignore_index=True).sort_values("lag")
         .drop_duplicates(["batter", "season"]))
    p = p[p["season"].isin(FIT_SEASONS)]
    pipe = Pipeline([("sc", StandardScaler()), ("m", LinearRegression())])
    pipe.fit(p[TRANS_FEATS].values, p["fp_per_pa_actual"].values)
    return pipe


def aaa_pred_table(years: list[int]) -> pd.DataFrame:
    """(batter, year, aaa_pred_fp_pa) — most recent qualifying AAA line, lag 0-2."""
    aaa = _aaa_seasons().copy()
    aaa["aaa_pred_fp_pa"] = _translation_pipe().predict(aaa[TRANS_FEATS].values)
    rows = []
    for lag in range(MAX_AAA_LAG + 1):
        a = aaa[["batter", "season", "aaa_pred_fp_pa"]].copy()
        a["year"] = a["season"] + lag
        a["lag"] = lag
        rows.append(a)
    cand = (pd.concat(rows, ignore_index=True).sort_values("lag")
            .drop_duplicates(["batter", "year"]))
    return cand[cand["year"].isin(years)][["batter", "year", "aaa_pred_fp_pa"]]


def blend_callup_prior(rolling: pd.DataFrame) -> pd.DataFrame:
    """Blend the translated AAA prior into prior_fp_per_pa for callup rows.

    Expects prior_fp_per_pa / prior_pa_eff / pa_to already present (post-Marcel).
    Returns the frame with prior_fp_per_pa updated in place on qualifying rows.
    """
    years = sorted(rolling["year"].unique())
    cand = aaa_pred_table(years)
    out = rolling.merge(cand, on=["batter", "year"], how="left")

    mlb_pa = out["prior_pa_eff"].fillna(0.0) + out["pa_to"].fillna(0.0)
    w_aaa = (CALLUP_PA_BOUNDARY - mlb_pa).clip(lower=0.0, upper=CALLUP_PA_BOUNDARY)
    mask = out["aaa_pred_fp_pa"].notna() & (w_aaa > 0)

    denom = out["prior_pa_eff"] + w_aaa
    blended = (
        out["prior_pa_eff"] * out["prior_fp_per_pa"] + w_aaa * out["aaa_pred_fp_pa"]
    ) / denom
    out.loc[mask, "prior_fp_per_pa"] = blended[mask]

    n_rows = int(mask.sum())
    n_players = out.loc[mask, "batter"].nunique()
    print(f"  [aaa_blend] translated AAA prior blended into {n_rows} rows "
          f"({n_players} callup batters); other rows untouched")
    return out.drop(columns=["aaa_pred_fp_pa"])
