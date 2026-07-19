#!/usr/bin/env python
"""
Validate PLPlvModel against all available Pitcher List reference years.

Usage:
    python scripts/validate_pl_plv.py

Prints:
  - Summary table: Year | N | r(PLV) | MAE(PLV) | r(PLA) | MAE(PLA)
  - Worst PLV disagreements for the most recent available year
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy.stats import pearsonr

# Allow running from repo root without editable install
_repo_root = Path(__file__).parent.parent

from plv_clone.config import get_config
from plv_clone.models.pl_plv_model import (
    COMPONENT_FEATS,
    PLPlvModel,
    load_and_clean_reference,
)
from plv_clone.utils.io import read_parquet

_REF_DIR = _repo_root / "data" / "reference" / "pitcher_list"
_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]

_PITCH_COLS = [
    "pitcher",
    "player_name",
    "pitch_type",
    "delta_run_exp",
    "is_in_play",
    "estimated_woba_using_speedangle",
]
_PLV_SCORE_COLS = [
    "pitcher",
    "player_name",
    "pitch_type",
    "plv_raw",
]
_COMPONENT_COLS = ["pitcher", "player_name", "pitch_type"] + COMPONENT_FEATS


def main() -> None:
    cfg = get_config()

    scaling_path = cfg.models_dir / "pl_plv_scaling.json"
    if not scaling_path.exists():
        print(
            f"ERROR: PLPlvModel not trained -- {scaling_path} not found.\n"
            "Run `plv train-pl-plv` first."
        )
        sys.exit(1)

    model = PLPlvModel.load(cfg.models_dir)
    rv_method = model.scaling_params.get("rv_method", "delta_run_exp")
    print(f"PLPlvModel loaded  rv_method={rv_method}")

    rows: list[dict] = []
    latest: dict = {}

    for year in _YEARS:
        scores_dir = cfg.processed_dir / "plv_scores" / f"year={year}"
        pitch_dir = cfg.processed_dir / "pitch_features" / f"year={year}"
        ref_path = _REF_DIR / f"pl_plv_{year}.csv"

        if not ref_path.exists():
            print(f"  {year}: reference CSV not found -- skipping.")
            continue

        # Choose data source based on rv_method
        if rv_method == "plv_components" and scores_dir.exists():
            data_dir = scores_dir
            cols = _COMPONENT_COLS
            used_method = "plv_components"
        elif rv_method == "plv_raw" and scores_dir.exists():
            data_dir = scores_dir
            cols = _PLV_SCORE_COLS
            used_method = "plv_raw"
        elif rv_method in ("plv_components", "plv_raw") and not scores_dir.exists():
            # plv_scores required but unavailable -- skip rather than produce invalid scores
            print(f"  {year}: plv_scores required for rv_method={rv_method} but not found -- skipping.")
            continue
        elif pitch_dir.exists():
            data_dir = pitch_dir
            cols = _PITCH_COLS
            used_method = rv_method
        else:
            print(f"  {year}: no pitch data found -- skipping.")
            continue

        print(f"  {year}: scoring ({used_method}) ...", end="", flush=True)
        pitch_df = read_parquet(data_dir, columns=cols)
        ref_df = load_and_clean_reference(ref_path)

        score_model = model

        min_pitches = 400 if len(ref_df) >= 400 else 200
        scored = score_model.score_pitches(pitch_df)
        agg = score_model.aggregate(scored, min_pitches=min_pitches, year=year)

        ref_clean = ref_df.rename(columns={"MLBAMID": "pitcher"}).copy()
        ref_clean["pitcher"] = ref_clean["pitcher"].astype(int)
        merged = agg.merge(
            ref_clean[["pitcher", "PLV", "PLA"]], on="pitcher", how="inner"
        )

        if merged.empty:
            print(" no matched pitchers -- skipping.")
            continue

        r_plv, _ = pearsonr(merged["pl_plv"], merged["PLV"])
        mae_plv = (merged["pl_plv"] - merged["PLV"]).abs().mean()
        r_pla, _ = pearsonr(merged["pl_pla"], merged["PLA"])
        mae_pla = (merged["pl_pla"] - merged["PLA"]).abs().mean()

        print(f" {len(merged)} pitchers, r(PLV)={r_plv:.4f}")

        rows.append(
            {
                "Year": year,
                "N": len(merged),
                "r(PLV)": round(r_plv, 4),
                "MAE(PLV)": round(mae_plv, 4),
                "r(PLA)": round(r_pla, 4),
                "MAE(PLA)": round(mae_pla, 4),
            }
        )
        latest = {"merged": merged, "year": year}

    if not rows:
        print("\nNo validation data available.")
        return

    table = pd.DataFrame(rows)
    print("\n-- PLPlvModel Validation Summary --")
    print(table.to_string(index=False))

    if latest:
        merged = latest["merged"]
        year = latest["year"]
        merged = merged.copy()
        merged["plv_delta"] = (merged["pl_plv"] - merged["PLV"]).abs()
        top10 = merged.nlargest(10, "plv_delta")[
            ["pitcher_name", "PLV", "pl_plv", "plv_delta"]
        ]
        print(f"\n-- Worst PLV Disagreements ({year}) --")
        print(f"  {'Pitcher':<25} {'PL_PLV':>7} {'Our_PLV':>8} {'|d|':>6}")
        print(f"  {'-'*25} {'-------':>7} {'--------':>8} {'------':>6}")
        for _, row in top10.iterrows():
            print(
                f"  {row['pitcher_name']:<25} {row['PLV']:>7.3f} "
                f"{row['pl_plv']:>8.3f} {row['plv_delta']:>6.3f}"
            )
    print()


if __name__ == "__main__":
    main()
