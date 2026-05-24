"""build_milb_aaa_priors.py — per-(batter, MLB year) AAA prior-year features.

For each MLB rolling year Y, looks at the batter's AAA season Y-1 and
emits prior-year aggregates. Used as candidate features for rh3
validation (callup / Quad-A signal).

Source: data/research/xfp_cache/milb_hitters_2015_2026.csv (already built
        by build_milb_hitter_counting.py from MLB Stats API; AAA=sportId=11).

Output: data/research/xfp_cache/milb_aaa_priors.csv
        Columns: batter, year, milb_aaa_pa_prior, milb_aaa_iso_prior,
                 milb_aaa_kpct_prior, milb_aaa_bbpct_prior.

Honesty notes (Rule 5):
- 2020 MiLB season was cancelled (COVID). 2021 MLB rolling rows therefore
  get NO prior-year AAA features and rely entirely on NaN-fill.
- AAA Statcast (i.e. xwOBA) is not in this leaderboard pull — only
  counting-stat derived rates (iso, k_pct, bb_pct). xwOBA would need a
  separate pybaseball.statcast_minor_league_batter pull (2021+).
- Min 50 PA AAA filter to avoid 1-game cup-of-coffee noise.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "research" / "xfp_cache" / "milb_hitters_2015_2026.csv"
OUT = ROOT / "data" / "research" / "xfp_cache" / "milb_aaa_priors.csv"

MIN_PA = 50


def main() -> None:
    m = pd.read_csv(SRC)
    aaa = m[(m["level"] == "AAA") & (m["plateAppearances"] >= MIN_PA)].copy()
    print(f"AAA hitter-seasons (>= {MIN_PA} PA): {len(aaa)}")

    # Build prior-year features: for MLB year Y, use AAA season Y-1
    aaa = aaa.rename(columns={"season": "prev_season"})
    aaa["year"] = aaa["prev_season"] + 1

    grouped = (
        aaa.groupby(["batter", "year"])
        .agg(
            milb_aaa_pa_prior=("plateAppearances", "sum"),
            milb_aaa_iso_prior=("iso", "mean"),
            milb_aaa_kpct_prior=("k_pct", "mean"),
            milb_aaa_bbpct_prior=("bb_pct", "mean"),
        )
        .reset_index()
    )
    grouped.to_csv(OUT, index=False)
    print(f"Wrote {OUT} shape={grouped.shape}")
    print(f"  median iso prior  : {grouped['milb_aaa_iso_prior'].median():.4f}")
    print(f"  median k%  prior  : {grouped['milb_aaa_kpct_prior'].median():.4f}")
    print(f"  median bb% prior  : {grouped['milb_aaa_bbpct_prior'].median():.4f}")
    print(f"  median PA  prior  : {grouped['milb_aaa_pa_prior'].median():.1f}")


if __name__ == "__main__":
    main()
