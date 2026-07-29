# Pre-registered: see data/research/validation_runs/sp_subs_fp_composite_2026-07-04.md
"""
rating_reimagine queue #1 — SP reweighted SWING_MISS-dominant sub-composite
as an rp3 candidate feature. Baseline: full RP3_FEATS (Rule 9). Framing:
in-season -> RoS from PRE-SPLIT columns only (Rule 8).

Pre-registered expectation: gain ~ 0 (every constituent's shrunk split-day
substrate is already a free Ridge parameter in RP3_FEATS — the documented
algebraic-redundancy pattern). Run to close the loop on the confounded +.434.
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Reuse the Rule-9 scaffolding from the prior rp3 validation (byte-identical prep).
from validate_pitch_shape_early_warning import (
    ROLLING_CSV, MULTIYR_CSV, RP3_FEATS, TARGET,
    build_full_training_frame, cross_year_r, holdout_r, partial_r_vs_baseline,
)

TRAIN_YEARS = [2018, 2019, 2021, 2022, 2023]
HOLDOUT = [2024, 2025]
CUTOFF_DAYS = [30, 42, 56, 70, 84]
CAND = "sp_subs_fp_composite"

# Frozen weights (rating_reimagine Angle 1 ridge fit; renormalized). Signs:
# higher = better for the pitcher.
W = {
    "swstr_pct_to": 0.174,       # SWING_MISS — dominant
    "c_plus_swstr_to": 0.036,    # CALLED_STRIKE substrate
    "avg_velo_to": 0.035,        # velo
    "xwoba_per_pa_to": -0.035,   # DAMAGE suppression (inverted)
    "zone_pct_to": 0.030,        # STRIKE_THROWING
    "bb_pct_to": -0.026,         # WALK_AVOID (inverted)
}


def build_candidate(df: pd.DataFrame) -> pd.Series:
    """Within-year z composite over pre-split columns, frozen weights."""
    total = sum(abs(v) for v in W.values())
    comp = pd.Series(0.0, index=df.index)
    valid = pd.Series(True, index=df.index)
    for col, w in W.items():
        z = df.groupby("year")[col].transform(
            lambda s: (s - s.mean()) / (s.std() or 1.0))
        comp = comp + (w / total) * z
        valid &= df[col].notna()
    comp[~valid] = np.nan
    return comp.rename(CAND)


def main():
    print("=== validate: sp_subs_fp_composite vs FULL rp3 baseline (Rule 9) ===")
    rolling = pd.read_csv(ROLLING_CSV)
    multiyr = pd.read_csv(MULTIYR_CSV)
    df = build_full_training_frame(rolling, multiyr)
    df[CAND] = build_candidate(df)
    n_ok = int(df[CAND].notna().sum())
    print(f"frame {len(df)} rows | candidate non-null {n_ok}")

    base = cross_year_r(df, RP3_FEATS, TARGET, TRAIN_YEARS)
    cand = cross_year_r(df, RP3_FEATS + [CAND], TARGET, TRAIN_YEARS)
    gain = cand["pooled_r"] - base["pooled_r"]
    print(f"\n[HEADLINE] cross-year r: baseline {base['pooled_r']:.4f} -> "
          f"+candidate {cand['pooled_r']:.4f}  gain {gain:+.4f}  "
          f"(strict bar +0.005)  n={base['n']}")
    print("per-year gains:")
    for y in TRAIN_YEARS:
        b, c = base["per_year"].get(y), cand["per_year"].get(y)
        if b is not None and c is not None:
            print(f"  {y}: {b:.4f} -> {c:.4f}  ({c-b:+.4f})")

    pr = partial_r_vs_baseline(df, [CAND], TARGET, TRAIN_YEARS)
    print(f"\n[GATE a] partial r of candidate vs baseline preds: {pr}")

    hb = holdout_r(df, RP3_FEATS, TARGET, TRAIN_YEARS, HOLDOUT)
    hc = holdout_r(df, RP3_FEATS + [CAND], TARGET, TRAIN_YEARS, HOLDOUT)
    print(f"[GATE c] holdout {HOLDOUT}: baseline {hb:.4f} -> {hc:.4f}  "
          f"gain {hc-hb:+.4f}")

    print("\n[RULE 8] convergence curve (gain at split_day cutoffs):")
    for cd in CUTOFF_DAYS:
        b = cross_year_r(df, RP3_FEATS, TARGET, TRAIN_YEARS, cutoff_day=cd)
        c = cross_year_r(df, RP3_FEATS + [CAND], TARGET, TRAIN_YEARS, cutoff_day=cd)
        if not np.isnan(b["pooled_r"]):
            print(f"  day<={cd}: {b['pooled_r']:.4f} -> {c['pooled_r']:.4f} "
                  f"({c['pooled_r']-b['pooled_r']:+.4f}, n={b['n']})")

    # Context (NOT the gate): candidate alone vs FP-level alone — the panel
    # claim translated to this framing.
    solo_c = cross_year_r(df, [CAND, "gs_to", "split_day"], TARGET, TRAIN_YEARS)
    solo_f = cross_year_r(df, ["fp_per_start_to", "gs_to", "split_day"], TARGET, TRAIN_YEARS)
    print(f"\n[CONTEXT] candidate-alone {solo_c['pooled_r']:.4f} vs "
          f"FP-level-alone {solo_f['pooled_r']:.4f}")


if __name__ == "__main__":
    main()
