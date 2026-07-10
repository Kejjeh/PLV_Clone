"""
xfp_bx aging curves — delta-method career arcs for hitter fp_per_pa and
SP fp_per_start, on the box-score-era panel (huge-n, ages 20-40).

Delta method: for each player with qualifying consecutive seasons at ages
a -> a+1, take delta = rate(T+1) - rate(T), weighted by the harmonic mean
of the two volumes. The cumulative sum of mean deltas (anchored at the
youngest age) is the aging curve. Computed overall and by era bucket
(1970s / 2000s / 2020s + the rest) to test for regime shift in the curve
itself.

Known bias (documented): the delta method conditions on playing BOTH
years above the volume floor — survivor bias flattens the decline tail.
This is uniform across eras, so ERA COMPARISON is still apples-to-apples.

Outputs:
  data/research/boxscore_era/aging_curve_hitters.csv
  data/research/boxscore_era/aging_curve_pitchers.csv
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
AGE_LO, AGE_HI = 20, 40

ERAS = {
    "1970s": (1970, 1979), "1980s": (1980, 1989), "1990s": (1990, 1999),
    "2000s": (2000, 2009), "2010s": (2010, 2019), "2020s": (2020, 2025),
}


def deltas(kind: str) -> pd.DataFrame:
    if kind == "hitters":
        df = pd.read_csv(HERE / "hitter_season_panel.csv")
        rate, vol, vol_min = "fp_per_pa", "pa", 200.0
    else:
        df = pd.read_csv(HERE / "pitcher_season_panel.csv")
        rate, vol, vol_min = "fp_per_start", "gs", 10.0
        df = df[df["gs"] > 0]
    df = df[(df["year"] <= 2025) & (df["year"] != 2020) & (df[vol] >= vol_min)]
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df = df.dropna(subset=["age", rate])
    cur = df[["mlbam", "year", "age", rate, vol]]
    nxt = cur.copy()
    nxt["year"] = nxt["year"] - 1
    nxt = nxt.rename(columns={rate: "rate_next", vol: "vol_next",
                              "age": "age_next"})
    m = cur.merge(nxt, on=["mlbam", "year"], how="inner")
    m = m[m["age_next"] == m["age"] + 1]  # consecutive ages only
    m = m[(m["year"] != 2019)]            # T+1 == 2020 excluded
    m["delta"] = m["rate_next"] - m[rate]
    m["w"] = 2 * m[vol] * m["vol_next"] / (m[vol] + m["vol_next"])
    m["era"] = pd.cut(m["year"] + 1, bins=[e[0] for e in ERAS.values()] + [2026],
                      labels=list(ERAS.keys()), right=False)
    return m[(m["age"] >= AGE_LO) & (m["age"] < AGE_HI)]


def curve(m: pd.DataFrame, label: str) -> pd.DataFrame:
    g = m.groupby("age").apply(
        lambda s: pd.Series({
            "mean_delta": np.average(s["delta"], weights=s["w"]),
            "n": len(s)}), include_groups=False).reset_index()
    g = g.sort_values("age")
    g["cum_curve"] = g["mean_delta"].cumsum().shift(1).fillna(0.0)
    g["era"] = label
    return g


def main():
    for kind in ["hitters", "pitchers"]:
        m = deltas(kind)
        out = [curve(m, "ALL")]
        for era in ERAS:
            sub = m[m["era"] == era]
            if len(sub) >= 300:
                out.append(curve(sub, era))
        res = pd.concat(out, ignore_index=True)
        res.to_csv(HERE / f"aging_curve_{kind}.csv", index=False)

        print(f"\n=== {kind.upper()} aging curve (delta method, "
              f"n={len(m)} transitions) ===")
        for label in res["era"].unique():
            c = res[res["era"] == label]
            peak_age = int(c.loc[c["cum_curve"].idxmax(), "age"])
            # decline slope: mean delta per year over ages 30-36
            d = c[(c["age"] >= 30) & (c["age"] <= 36)]
            slope = float(d["mean_delta"].mean()) if len(d) else np.nan
            n = int(c["n"].sum())
            print(f"  {label:6s} n={n:6d}  peak age={peak_age}  "
                  f"decline slope 30-36={slope:+.4f}/yr")


if __name__ == "__main__":
    main()
