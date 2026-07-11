"""
build_bx_priors.py — vintage (as-of) xfp_bx v0 predictions + aging-curve
levels for the bx-ensemble validation (prereg
data/research/validation_runs/bx_ensemble_2026-07-10.md).

For each target year T in 2018-2026:
  * fit the xfp_bx v0 ridge on panel PAIRS whose target year <= T-1
    (LOO-safe vintage — no train-on-future),
  * predict year T's full-season rate from each player's year-(T-1) box
    line (T=2021 uses 2019 lines: 2020 excluded as a feature year),
  * refit the delta-method aging curve on panel years <= T-1 and record
    the cum_curve level at each player's year-T age.

Imports feature lists / constants from data/research/boxscore_era/xfp_bx_v0.py
(originals NOT modified). Emits:
  data/research/xfp_cache/bx_priors_2018_2026.csv
  (mlbam, year, bx_prior_h, bx_prior_sp, bx_age_mult_h, bx_age_mult_sp)

Run: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/build_bx_priors.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BX_DIR = ROOT / "data" / "research" / "boxscore_era"
sys.path.insert(0, str(BX_DIR))
from xfp_bx_v0 import (  # noqa: E402
    HIT_FEATS, PIT_FEATS, MARCEL_W, K_HIT_PA, K_PIT_GS, _make_pipe,
)

OUT_CSV = ROOT / "data" / "research" / "xfp_cache" / "bx_priors_2018_2026.csv"
TARGET_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
AGE_LO, AGE_HI = 20, 40


def _load_panel(kind: str):
    if kind == "hitters":
        df = pd.read_csv(BX_DIR / "hitter_season_panel.csv")
        return df, "fp_per_pa", "pa", 200.0, K_HIT_PA, HIT_FEATS
    df = pd.read_csv(BX_DIR / "pitcher_season_panel.csv")
    df = df[df["gs"] > 0]
    return df, "fp_per_start", "gs", 10.0, K_PIT_GS, PIT_FEATS


def _marcel(mlbams, anchor_year, lut, league_mu, k_reg):
    """Marcel-lite prior anchored at `anchor_year` (v0 formula, no lookahead)."""
    out = []
    for m in mlbams:
        num = den = 0.0
        for off, w in zip((0, 1, 2), MARCEL_W):
            rv = lut.get((int(m), anchor_year - off))
            if rv is not None:
                num += w * rv[1] * rv[0]
                den += w * rv[1]
        mu = league_mu.get(anchor_year, np.nan)
        if np.isnan(mu):  # anchor year absent from history (shouldn't happen)
            mu = float(np.nanmean(list(league_mu.values())))
        out.append((num + k_reg * mu) / (den + k_reg))
    return out


def _build_pairs(hist: pd.DataFrame, rate: str, vol: str, vol_min: float,
                 k_reg: float, lut: dict, league_mu: dict) -> pd.DataFrame:
    """Replicates xfp_bx_v0.load_leg pair construction on a history slice."""
    cur = hist[hist[vol] >= vol_min].copy()
    nxt = hist.loc[hist[vol] >= vol_min, ["mlbam", "year", rate]].copy()
    nxt["year"] = nxt["year"] - 1
    nxt = nxt.rename(columns={rate: "target"})
    pairs = cur.merge(nxt, on=["mlbam", "year"], how="inner")
    pairs = pairs[~pairs["year"].isin([2019, 2020])]
    # per-row Marcel anchored at each pair's feature year (v0 formula)
    priors = []
    for m, t in zip(pairs["mlbam"].astype(int), pairs["year"].astype(int)):
        num = den = 0.0
        for off, w in zip((0, 1, 2), MARCEL_W):
            rv = lut.get((m, t - off))
            if rv is not None:
                num += w * rv[1] * rv[0]
                den += w * rv[1]
        mu = league_mu.get(t, np.nan)
        if np.isnan(mu):
            mu = float(np.nanmean(list(league_mu.values())))
        priors.append((num + k_reg * mu) / (den + k_reg))
    pairs["marcel_prior"] = priors
    pairs["age"] = pd.to_numeric(pairs["age"], errors="coerce")
    pairs["age_sq"] = pairs["age"] ** 2
    pairs["log_vol"] = np.log(pairs[vol])
    return pairs


def _aging_curve(hist: pd.DataFrame, rate: str, vol: str,
                 vol_min: float) -> pd.DataFrame:
    """Delta-method curve, exact aging_curves.py methodology, on `hist`."""
    df = hist[(hist["year"] != 2020) & (hist[vol] >= vol_min)].copy()
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df = df.dropna(subset=["age", rate])
    cur = df[["mlbam", "year", "age", rate, vol]]
    nxt = cur.copy()
    nxt["year"] = nxt["year"] - 1
    nxt = nxt.rename(columns={rate: "rate_next", vol: "vol_next",
                              "age": "age_next"})
    m = cur.merge(nxt, on=["mlbam", "year"], how="inner")
    m = m[m["age_next"] == m["age"] + 1]
    m = m[m["year"] != 2019]  # T+1 == 2020 excluded
    m["delta"] = m["rate_next"] - m[rate]
    m["w"] = 2 * m[vol] * m["vol_next"] / (m[vol] + m["vol_next"])
    m = m[(m["age"] >= AGE_LO) & (m["age"] < AGE_HI)]
    g = m.groupby("age").apply(
        lambda s: pd.Series({
            "mean_delta": np.average(s["delta"], weights=s["w"]),
            "n": len(s)}), include_groups=False).reset_index()
    g = g.sort_values("age")
    g["cum_curve"] = g["mean_delta"].cumsum().shift(1).fillna(0.0)
    return g[["age", "cum_curve"]]


def _curve_level(curve: pd.DataFrame, ages: pd.Series) -> np.ndarray:
    """cum_curve at age: linear interpolation, endpoint clamping."""
    xs = curve["age"].values.astype(float)
    ys = curve["cum_curve"].values.astype(float)
    a = pd.to_numeric(ages, errors="coerce").values.astype(float)
    out = np.interp(a, xs, ys, left=ys[0], right=ys[-1])
    out[np.isnan(a)] = np.nan
    return out


def build_leg(kind: str) -> pd.DataFrame:
    panel, rate, vol, vol_min, k_reg, feats = _load_panel(kind)
    suffix = "h" if kind == "hitters" else "sp"
    # age-at-year lookup across the full panel (any volume; 2026 rows OK —
    # ages only, never features/targets)
    age_lut = {(int(m), int(y)): a for m, y, a in zip(
        panel["mlbam"], panel["year"],
        pd.to_numeric(panel["age"], errors="coerce")) if not np.isnan(a)}

    rows = []
    for T in TARGET_YEARS:
        hist = panel[panel["year"] <= T - 1].copy()
        qual = hist[hist[vol] >= vol_min]
        league_mu = qual.groupby("year")[rate].mean().to_dict()
        lut = {(int(m), int(y)): (r, v) for m, y, r, v in
               zip(hist["mlbam"], hist["year"], hist[rate], hist[vol])
               if v > 0}

        pairs = _build_pairs(hist, rate, vol, vol_min, k_reg, lut, league_mu)
        pairs = pairs.dropna(subset=feats + ["target"])
        pipe = _make_pipe()
        pipe.fit(pairs[feats].values, pairs["target"].values)

        # feature year: T-1 (2021 exception -> 2019; 2020 never a feature yr)
        F = T - 1 if T != 2021 else 2019
        base = hist[(hist["year"] == F) & (hist[vol] >= vol_min)].copy()
        base["marcel_prior"] = _marcel(base["mlbam"].astype(int), F, lut,
                                       league_mu, k_reg)
        base["age"] = pd.to_numeric(base["age"], errors="coerce")
        base["age_sq"] = base["age"] ** 2
        base["log_vol"] = np.log(base[vol])
        base = base.dropna(subset=feats)
        pred = pipe.predict(base[feats].values)

        # aging-curve level at year-T age (curve refit on <= T-1 history)
        curve = _aging_curve(hist, rate, vol, vol_min)
        out = pd.DataFrame({"mlbam": base["mlbam"].astype(int).values,
                            "year": T,
                            f"bx_prior_{suffix}": pred})
        age_T = [age_lut.get((m, T),
                             (age_lut.get((m, F), np.nan)
                              + (T - F) if (m, F) in age_lut else np.nan))
                 for m in out["mlbam"]]
        out[f"bx_age_mult_{suffix}"] = _curve_level(
            curve, pd.Series(age_T, dtype=float))
        rows.append(out)
        print(f"  {kind} T={T}: train pairs={len(pairs)} "
              f"(target yrs <= {T-1}), feature yr={F}, "
              f"predicted={len(out)}, curve ages={len(curve)}")
    return pd.concat(rows, ignore_index=True)


def main():
    print("=== build_bx_priors — vintage xfp_bx predictions ===")
    h = build_leg("hitters")
    p = build_leg("pitchers")
    merged = h.merge(p, on=["mlbam", "year"], how="outer")
    merged = merged.sort_values(["year", "mlbam"]).reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}: {len(merged)} rows")
    for c in ["bx_prior_h", "bx_prior_sp", "bx_age_mult_h", "bx_age_mult_sp"]:
        print(f"  {c}: non-null {merged[c].notna().sum()}")


if __name__ == "__main__":
    main()
