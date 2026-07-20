"""
gen_leaderboards.py — Generate pitcher_leaderboard.csv and pitch_type_leaderboard.csv
from existing PLV scored data (no re-training required).

Usage:
    python scripts/gen_leaderboards.py [--year 2026]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

from plv_clone.config import get_config
from plv_clone.utils.io import read_parquet
from run_plv_review import write_leaderboards

CFG = get_config()


def main(year: int = 2026) -> None:
    scored_path = CFG.processed_dir / "plv_scores" / f"year={year}"
    if not scored_path.exists():
        print(f"ERROR: {scored_path} not found. Run `plv build-exports {year}` first.")
        sys.exit(1)

    scored_df = read_parquet(scored_path)
    print(f"Loaded {len(scored_df):,} scored pitches for {year}.")

    rdir = CFG.outputs_dir / f"review_{year}"
    rdir.mkdir(parents=True, exist_ok=True)

    pitcher_lb, pt_lb = write_leaderboards(
        scored_df, year,
        rdir / "pitcher_leaderboard.csv",
        rdir / "pitch_type_leaderboard.csv",
    )
    print(f"pitcher_leaderboard.csv: {len(pitcher_lb)} pitchers")
    print(f"pitch_type_leaderboard.csv: {len(pt_lb)} pitch-type rows")
    print(f"Output directory: {rdir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    main(args.year)
