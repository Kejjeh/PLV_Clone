"""
xfp_bx v0 — next-season FP-rate model on the box-score-era panel.

Protocol pre-registered at
data/research/validation_runs/xfp_bx_v0_2026-07-10.md (written BEFORE this
script was first run). Baseline = Marcel-lite; model = Ridge (house idiom:
StandardScaler + RidgeCV, same alphas/cv as rh3.cross_year_eval).
Evaluation = LOO-by-DECADE (hold out entire target decades 1970s..2020s).

Run:  python data/research/boxscore_era/xfp_bx_v0.py
Artifacts:
  data/research/boxscore_era/bx_v0_eval_results.json
  data/research/boxscore_era/bx_v0_holdout_preds_{hitters,pitchers}.csv
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV

HERE = Path(__file__).resolve().parent

MARCEL_W = (5, 4, 3)
K_HIT_PA = 200.0
K_PIT_GS = 20.0
DECADES = [1970, 1980, 1990, 2000, 2010, 2020]

HIT_FEATS = ["k_pct", "bb_pct", "iso", "hr_per_pa", "sb_per_pa", "babip",
             "r_per_pa", "rbi_per_pa", "fp_per_pa", "marcel_prior",
             "age", "age_sq", "log_vol"]
PIT_FEATS = ["k_pct", "bb_pct", "hr9", "era", "fip_box", "ip_per_gs",
             "fp_per_start", "marcel_prior", "age", "age_sq", "log_vol"]


def _make_pipe():
    return Pipeline([("sc", StandardScaler()),
                     ("r", RidgeCV(alphas=np.logspace(-1, 5, 80), cv=5))])


def load_leg(kind: str) -> pd.DataFrame:
    """Return T->T+1 pair frame with features, target, marcel prior."""
    if kind == "hitters":
        df = pd.read_csv(HERE / "hitter_season_panel.csv")
        rate, vol, vol_min, k_reg = "fp_per_pa", "pa", 200.0, K_HIT_PA
    else:
        df = pd.read_csv(HERE / "pitcher_season_panel.csv")
        rate, vol, vol_min, k_reg = "fp_per_start", "gs", 10.0, K_PIT_GS
        df = df[df["gs"] > 0]
    df = df[df["year"] <= 2025]

    # league mean per year from qualifying seasons (era drift absorber)
    qual = df[df[vol] >= vol_min]
    league_mu = qual.groupby("year")[rate].mean().to_dict()

    # (mlbam, year) -> (rate, vol) for marcel lookback (any volume)
    lut = {(int(m), int(y)): (r, v) for m, y, r, v in
           zip(df["mlbam"], df["year"], df[rate], df[vol]) if v > 0}

    # build pairs
    cur = df[df[vol] >= vol_min].copy()
    nxt = df[df[vol] >= vol_min][["mlbam", "year", rate]].copy()
    nxt["year"] = nxt["year"] - 1  # align: row (m, T) gets rate of T+1
    nxt = nxt.rename(columns={rate: "target"})
    pairs = cur.merge(nxt, on=["mlbam", "year"], how="inner")
    pairs = pairs[~pairs["year"].isin([2019, 2020])]
    # 2019 dropped because its target year is 2020 (excluded); 2020 dropped
    # as an excluded feature year. (prereg: 2020 out as T and as T+1)

    # marcel prior
    priors = []
    for m, t in zip(pairs["mlbam"].astype(int), pairs["year"].astype(int)):
        num = den = 0.0
        for off, w in zip((0, 1, 2), MARCEL_W):
            rv = lut.get((m, t - off))
            if rv is not None:
                num += w * rv[1] * rv[0]
                den += w * rv[1]
        mu = league_mu.get(t, np.nan)
        priors.append((num + k_reg * mu) / (den + k_reg))
    pairs["marcel_prior"] = priors

    pairs["age"] = pd.to_numeric(pairs["age"], errors="coerce")
    pairs["age_sq"] = pairs["age"] ** 2
    pairs["log_vol"] = np.log(pairs[vol])
    pairs["decade"] = ((pairs["year"] + 1) // 10) * 10
    feats = HIT_FEATS if kind == "hitters" else PIT_FEATS
    pairs = pairs.dropna(subset=feats + ["target"]).reset_index(drop=True)
    return pairs


def loo_by_decade(pairs: pd.DataFrame, feats: list[str]) -> tuple[dict, pd.DataFrame]:
    per_decade = {}
    held_frames = []
    for dec in DECADES:
        test = pairs[pairs["decade"] == dec]
        train = pairs[pairs["decade"] != dec]
        if len(test) < 50 or len(train) < 500:
            continue
        pipe = _make_pipe()
        pipe.fit(train[feats].values, train["target"].values)
        pred = pipe.predict(test[feats].values)
        r_model = float(np.corrcoef(pred, test["target"])[0, 1])
        r_marcel = float(np.corrcoef(test["marcel_prior"], test["target"])[0, 1])
        per_decade[dec] = {"n": int(len(test)),
                           "r_model": round(r_model, 4),
                           "r_marcel": round(r_marcel, 4),
                           "delta": round(r_model - r_marcel, 4)}
        hf = test[["mlbam", "player_name", "year", "age", "decade",
                   "marcel_prior", "target"]].copy()
        hf["pred_model"] = pred
        held_frames.append(hf)
    held = pd.concat(held_frames, ignore_index=True)
    pooled_model = float(np.corrcoef(held["pred_model"], held["target"])[0, 1])
    pooled_marcel = float(np.corrcoef(held["marcel_prior"], held["target"])[0, 1])
    # Statcast-era slice: target year (T+1) in 2015-2025
    sl = held[(held["year"] + 1).between(2015, 2025)]
    r_slice_model = float(np.corrcoef(sl["pred_model"], sl["target"])[0, 1])
    r_slice_marcel = float(np.corrcoef(sl["marcel_prior"], sl["target"])[0, 1])
    summary = {
        "per_decade": per_decade,
        "pooled": {"n": int(len(held)),
                   "r_model": round(pooled_model, 4),
                   "r_marcel": round(pooled_marcel, 4),
                   "delta": round(pooled_model - pooled_marcel, 4)},
        "slice_2015_2025": {"n": int(len(sl)),
                            "r_model": round(r_slice_model, 4),
                            "r_marcel": round(r_slice_marcel, 4)},
    }
    return summary, held


def main():
    results = {}
    for kind, feats in [("hitters", HIT_FEATS), ("pitchers", PIT_FEATS)]:
        print(f"\n=== xfp_bx v0 — {kind} ===")
        pairs = load_leg(kind)
        print(f"pairs: {len(pairs)}  (target years "
              f"{pairs['year'].min()+1}-{pairs['year'].max()+1})")
        summary, held = loo_by_decade(pairs, feats)
        for dec, row in summary["per_decade"].items():
            print(f"  {dec}s: n={row['n']:5d}  model r={row['r_model']:.4f}  "
                  f"marcel r={row['r_marcel']:.4f}  Δ={row['delta']:+.4f}")
        p = summary["pooled"]
        print(f"  POOLED: n={p['n']}  model r={p['r_model']:.4f}  "
              f"marcel r={p['r_marcel']:.4f}  Δ={p['delta']:+.4f}")
        s = summary["slice_2015_2025"]
        print(f"  2015-2025 slice: n={s['n']}  model r={s['r_model']:.4f}  "
              f"marcel r={s['r_marcel']:.4f}")
        # gates
        wins = sum(1 for v in summary["per_decade"].values() if v["delta"] > 0)
        g1 = p["delta"] >= 0.01
        g2 = wins >= 5
        floor = 0.35 if kind == "hitters" else 0.30
        g3 = (s["r_model"] >= floor) and (s["r_model"] < 0.62)
        summary["gates"] = {"g1_pooled_delta_ge_0.01": g1,
                            "g2_sign_consistency_5of6": f"{wins}/6 -> {g2}",
                            "g3_statcast_slice": g3,
                            "verdict": "PASS" if (g1 and g2 and g3) else "FAIL"}
        print(f"  GATES: pooled Δ≥+0.01: {g1} | decades won: {wins}/6 "
              f"(need ≥5) | slice floor {floor} & <0.62: {g3} "
              f"| VERDICT: {summary['gates']['verdict']}")
        held.to_csv(HERE / f"bx_v0_holdout_preds_{kind}.csv", index=False)
        results[kind] = summary
    (HERE / "bx_v0_eval_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print("\nwrote bx_v0_eval_results.json + holdout pred CSVs")


if __name__ == "__main__":
    main()
