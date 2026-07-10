"""
xfp_bx 2026 output — fit v0 on ALL history (all decades pooled), score
2026 full-season xFP rates for current players from their 2025 box lines,
and compare against the Statcast-stack projections (rh3 / rp3) on the
overlap population.

- "Current players" = mlbam ids appearing in the 2026 panel rows.
- Features come from 2025 seasons meeting the pair volume floors
  (hitters PA >= 200, SP GS >= 10) — same floors the model was trained on.
- Implied totals use reference volumes (hitter: min(pa_2025, 650) PA;
  SP: min(gs_2025 + 2, 32) GS), which are REFERENCE conversions, not a
  volume model (the validated volume layer lives elsewhere).
- ENSEMBLE-RESEARCH ARTIFACT, NOT A RANKER. rh3/rp3 stay the headline.

Output: data/outputs/xfp_bx_season_2026.csv
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from xfp_bx_v0 import load_leg, HIT_FEATS, PIT_FEATS, _make_pipe, MARCEL_W, \
    K_HIT_PA, K_PIT_GS  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / "data" / "outputs" / "xfp_bx_season_2026.csv"


def score_leg(kind: str) -> pd.DataFrame:
    feats = HIT_FEATS if kind == "hitters" else PIT_FEATS
    pairs = load_leg(kind)
    pipe = _make_pipe()
    pipe.fit(pairs[feats].values, pairs["target"].values)

    if kind == "hitters":
        panel = pd.read_csv(HERE / "hitter_season_panel.csv")
        rate, vol, vol_min, k_reg = "fp_per_pa", "pa", 200.0, K_HIT_PA
    else:
        panel = pd.read_csv(HERE / "pitcher_season_panel.csv")
        panel = panel[panel["gs"] > 0]
        rate, vol, vol_min, k_reg = "fp_per_start", "gs", 10.0, K_PIT_GS

    current = set(panel.loc[panel["year"] == 2026, "mlbam"].astype(int))
    hist = panel[panel["year"] <= 2025]
    qual = hist[hist[vol] >= vol_min]
    league_mu = qual.groupby("year")[rate].mean().to_dict()
    lut = {(int(m), int(y)): (r, v) for m, y, r, v in
           zip(hist["mlbam"], hist["year"], hist[rate], hist[vol]) if v > 0}

    base = hist[(hist["year"] == 2025) & (hist[vol] >= vol_min)].copy()
    base = base[base["mlbam"].astype(int).isin(current)]

    priors = []
    for m in base["mlbam"].astype(int):
        num = den = 0.0
        for off, w in zip((0, 1, 2), MARCEL_W):
            rv = lut.get((m, 2025 - off))
            if rv is not None:
                num += w * rv[1] * rv[0]
                den += w * rv[1]
        priors.append((num + k_reg * league_mu[2025]) / (den + k_reg))
    base["marcel_prior"] = priors
    # model was trained on age at feature-year T, so use 2025 age as-is
    base["age"] = pd.to_numeric(base["age"], errors="coerce")
    base["age_sq"] = base["age"] ** 2
    base["log_vol"] = np.log(base[vol])
    base = base.dropna(subset=feats)
    base["xfp_bx_rate_2026"] = pipe.predict(base[feats].values)

    if kind == "hitters":
        ref_vol = base["pa"].clip(upper=650)
        out = base[["mlbam", "player_name", "lahman_id", "age", "pa",
                    "fp_per_pa", "marcel_prior", "xfp_bx_rate_2026"]].copy()
        out["rate_units"] = "fp_per_pa"
        out["ref_volume"] = ref_vol
        out["leg"] = "hitter"
    else:
        ref_vol = (base["gs"] + 2).clip(upper=32)
        out = base[["mlbam", "player_name", "lahman_id", "age", "gs",
                    "fp_per_start", "marcel_prior", "xfp_bx_rate_2026"]].copy()
        out = out.rename(columns={"gs": "pa"})  # unified volume col name fixed below
        out["rate_units"] = "fp_per_start"
        out["ref_volume"] = ref_vol
        out["leg"] = "sp"
    out = out.rename(columns={"pa": "vol_2025",
                              "fp_per_pa": "rate_2025",
                              "fp_per_start": "rate_2025"})
    out["xfp_bx_implied_total_2026"] = (out["xfp_bx_rate_2026"]
                                        * out["ref_volume"]).round(1)
    return out


def compare(out: pd.DataFrame):
    rh = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv")
    rp = pd.read_csv(ROOT / "data/outputs/xfp_rp3_projections.csv")

    h = out[out["leg"] == "hitter"].merge(
        rh[["batter", "xfp_rh3_per_pa", "rank"]],
        left_on="mlbam", right_on="batter", how="inner")
    r_h = float(np.corrcoef(h["xfp_bx_rate_2026"], h["xfp_rh3_per_pa"])[0, 1])
    print(f"\nHITTERS overlap n={len(h)}  corr(bx, rh3 per-PA) = {r_h:.3f}")
    h["z_bx"] = (h["xfp_bx_rate_2026"] - h["xfp_bx_rate_2026"].mean()) / h["xfp_bx_rate_2026"].std()
    h["z_rh3"] = (h["xfp_rh3_per_pa"] - h["xfp_rh3_per_pa"].mean()) / h["xfp_rh3_per_pa"].std()
    h["dz"] = h["z_bx"] - h["z_rh3"]
    print("\nTop 10 BX HIGHER than rh3 (box history likes them more):")
    print(h.nlargest(10, "dz")[["player_name", "age", "xfp_bx_rate_2026",
                                "xfp_rh3_per_pa", "dz"]].round(3).to_string(index=False))
    print("\nTop 10 BX LOWER than rh3 (Statcast stack likes them more):")
    print(h.nsmallest(10, "dz")[["player_name", "age", "xfp_bx_rate_2026",
                                 "xfp_rh3_per_pa", "dz"]].round(3).to_string(index=False))

    rp_dd = rp[rp["data_quality_tag"].astype(str).str.startswith("data_driven")]
    p = out[out["leg"] == "sp"].merge(
        rp_dd[["pitcher", "xfp_rp3_per_start"]],
        left_on="mlbam", right_on="pitcher", how="inner")
    r_p = float(np.corrcoef(p["xfp_bx_rate_2026"], p["xfp_rp3_per_start"])[0, 1])
    print(f"\nSP overlap n={len(p)} (data_driven rp3 only)  "
          f"corr(bx, rp3 per-start) = {r_p:.3f}")
    p["z_bx"] = (p["xfp_bx_rate_2026"] - p["xfp_bx_rate_2026"].mean()) / p["xfp_bx_rate_2026"].std()
    p["z_rp3"] = (p["xfp_rp3_per_start"] - p["xfp_rp3_per_start"].mean()) / p["xfp_rp3_per_start"].std()
    p["dz"] = p["z_bx"] - p["z_rp3"]
    print("\nTop 10 BX HIGHER than rp3:")
    print(p.nlargest(10, "dz")[["player_name", "age", "xfp_bx_rate_2026",
                                "xfp_rp3_per_start", "dz"]].round(3).to_string(index=False))
    print("\nTop 10 BX LOWER than rp3:")
    print(p.nsmallest(10, "dz")[["player_name", "age", "xfp_bx_rate_2026",
                                 "xfp_rp3_per_start", "dz"]].round(3).to_string(index=False))
    return r_h, len(h), r_p, len(p)


def main():
    legs = [score_leg("hitters"), score_leg("pitchers")]
    out = pd.concat(legs, ignore_index=True)
    out = out.sort_values(["leg", "xfp_bx_rate_2026"], ascending=[True, False])
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} rows "
          f"({(out['leg']=='hitter').sum()} hitters, {(out['leg']=='sp').sum()} SP)")
    compare(out)


if __name__ == "__main__":
    main()
