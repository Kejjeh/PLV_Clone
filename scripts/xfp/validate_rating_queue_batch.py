# Pre-registered: low_fb_reliance / stuff_x_control / prior_k_per_start _2026-07-04.md
"""
rating_reimagine queue #2/#4/#5 — three pre-registered rp3 candidates vs the
FULL RP3_FEATS baseline (Rule 9), in-season framing (Rule 8), batch Bonferroni
N=3 (Rule 3: adjusted bar noted alongside raw).

  low_fb_reliance   : prior-year FB share < .48 flag        (expect: recent-era only)
  stuff_x_control   : z(swstr_sh) * z(-bb_sh) interaction   (genuine non-linear test)
  prior_k_per_start : prior-year K/GS                       (expect: REJECTED, spanned)
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_ROOT = Path(__file__).resolve().parents[2]
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from validate_pitch_shape_early_warning import (
    ROLLING_CSV, MULTIYR_CSV, RP3_FEATS, TARGET,
    build_full_training_frame, cross_year_r, holdout_r,
)

TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
HOLDOUT = [2024, 2025]
CUTOFFS = [42, 70]
CACHE = _ROOT / "data" / "research" / "xfp_cache"
FB_TYPES = ("FF", "SI", "FC")


def build_prior_fb_share(years: range) -> pd.DataFrame:
    """Per (pitcher, season) fastball share from statcast, to be lagged +1."""
    rows = []
    for yr in years:
        p = CACHE / f"statcast_{yr}.parquet"
        if not p.exists():
            continue
        sc = pd.read_parquet(p, columns=["pitcher", "pitch_type"])
        g = sc.groupby("pitcher")["pitch_type"].agg(
            n="size", fb=lambda s: s.isin(FB_TYPES).sum())
        g = g[g["n"] >= 500]
        rows.append(pd.DataFrame({
            "pitcher": g.index, "year_next": yr + 1,
            "prior_fb_share": g["fb"] / g["n"]}))
    return pd.concat(rows, ignore_index=True)


def main():
    print("=== rating queue batch: 3 candidates vs FULL rp3 baseline ===")
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    df = build_full_training_frame(rolling, multiyr)

    # -- candidate 1: low_fb_reliance (prior-year FB share < .48) --------------
    fb = build_prior_fb_share(range(2017, 2026))
    df = df.merge(fb, left_on=["pitcher", "year"],
                  right_on=["pitcher", "year_next"], how="left")
    df["low_fb_reliance"] = (df["prior_fb_share"] < 0.48).astype(float)
    df.loc[df["prior_fb_share"].isna(), "low_fb_reliance"] = np.nan

    # -- candidate 2: stuff_x_control interaction ------------------------------
    zs = df.groupby("year")["swstr_pct_to_sh"].transform(
        lambda s: (s - s.mean()) / (s.std() or 1.0))
    zc = df.groupby("year")["bb_pct_to_sh"].transform(
        lambda s: -(s - s.mean()) / (s.std() or 1.0))
    df["stuff_x_control"] = zs * zc

    # -- candidate 3: prior_k_per_start ----------------------------------------
    pk = multiyr[multiyr["gs"] >= 5][["pitcher", "year", "k", "gs"]].copy()
    pk["prior_k_per_start"] = pk["k"] / pk["gs"]
    pk["year_next"] = pk["year"] + 1
    df = df.merge(pk[["pitcher", "year_next", "prior_k_per_start"]],
                  left_on=["pitcher", "year"], right_on=["pitcher", "year_next"],
                  how="left", suffixes=("", "_pk"))

    base = cross_year_r(df, RP3_FEATS, TARGET, TRAIN_YEARS)
    hb = holdout_r(df, RP3_FEATS, TARGET, TRAIN_YEARS, HOLDOUT)
    print(f"baseline: cross-year {base['pooled_r']:.4f} (n={base['n']}) | "
          f"holdout {hb:.4f}")
    print("Bonferroni: N=3 pre-registered candidates -> adjusted strict bar "
          "+0.005 becomes ~+0.0087 equivalent-stringency; report raw vs both.\n")

    for cand in ("low_fb_reliance", "stuff_x_control", "prior_k_per_start"):
        sub = df[df[cand].notna()].copy()
        c = cross_year_r(sub, RP3_FEATS + [cand], TARGET, TRAIN_YEARS)
        b2 = cross_year_r(sub, RP3_FEATS, TARGET, TRAIN_YEARS)  # same-row baseline
        gain = c["pooled_r"] - b2["pooled_r"]
        hc = holdout_r(sub, RP3_FEATS + [cand], TARGET, TRAIN_YEARS, HOLDOUT)
        hb2 = holdout_r(sub, RP3_FEATS, TARGET, TRAIN_YEARS, HOLDOUT)
        print(f"--- {cand} ---")
        print(f"  cross-year: {b2['pooled_r']:.4f} -> {c['pooled_r']:.4f}  "
              f"gain {gain:+.4f}  (n={b2['n']})")
        yrs = []
        for y in TRAIN_YEARS:
            if y in c["per_year"] and y in b2["per_year"]:
                yrs.append(f"{y}:{c['per_year'][y]-b2['per_year'][y]:+.4f}")
        print(f"  per-year gain: {'  '.join(yrs)}")
        print(f"  holdout: {hb2:.4f} -> {hc:.4f}  gain {hc-hb2:+.4f}")
        for cd in CUTOFFS:
            bcut = cross_year_r(sub, RP3_FEATS, TARGET, TRAIN_YEARS, cutoff_day=cd)
            ccut = cross_year_r(sub, RP3_FEATS + [cand], TARGET, TRAIN_YEARS, cutoff_day=cd)
            if not np.isnan(bcut["pooled_r"]):
                print(f"  day<={cd}: gain {ccut['pooled_r']-bcut['pooled_r']:+.4f}")
        # recent-era read for the regime-emergent flag (declared for low_fb)
        if cand == "low_fb_reliance":
            rec_b = cross_year_r(sub, RP3_FEATS, TARGET, [2022, 2023, 2024])
            rec_c = cross_year_r(sub, RP3_FEATS + [cand], TARGET, [2022, 2023, 2024])
            print(f"  RECENT-ERA (22-24 LOYO): {rec_b['pooled_r']:.4f} -> "
                  f"{rec_c['pooled_r']:.4f}  gain {rec_c['pooled_r']-rec_b['pooled_r']:+.4f}")
        print()


if __name__ == "__main__":
    main()
