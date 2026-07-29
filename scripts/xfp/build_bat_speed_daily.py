"""build_bat_speed_daily.py — per-batter, per-DAY bat-tracking accumulator.

Why this exists
---------------
Bat speed is the ONLY hitter process metric validated to add forward-FP signal
beyond the season FP level (2026-06-26 window study; re-confirmed by the
60-cell delta-family rejection 2026-07-29). Yet every consumer could read it
only as a YEAR-over-YEAR delta, because the two bat-tracking artifacts we had
are both season aggregates:

  * `data/research/bat_tracking_all_2023_2026.csv` — Savant season leaderboards
    (research one-off; the Savant endpoints have no date parameter at all).
  * `data/research/bat_speed_trending_2026.csv` — 2026-to-date vs prior year,
    OVERWRITTEN nightly, so no history survives.

That gap is exactly why the in-season bat-speed delta could not be tested when
the rest of the in-season-delta family was closed — and it is the family's sole
declared re-open condition. This builder closes it.

Where the data comes from
-------------------------
Per-PITCH `bat_speed` already lands in `data/research/xfp_cache/statcast_{yr}.parquet`
(2024+): the canonical pybaseball pull carries it, and `lib/gf_statcast.py` maps
Savant's per-game feed `batSpeed` into the same column, so the gf bridge
(refresh step 1.05) keeps today's games current. NOTE the raw mirror
`data/raw/statcast_{yr}.parquet` does NOT have the column — read the xfp_cache
copy only.

Coverage is ~45% of pitches, which is not a gap: bat_speed is recorded on
SWINGS, and roughly 45% of pitches are swung at. `bat_speed > 10` drops sensor
junk (same filter as `lib/trend_signal._hitter_season`).

Output
------
`data/research/bat_speed_daily.parquet`, one row per (batter, game_date):
    batter, game_date, n_swings, mean_bat_speed, p90_bat_speed,
    fast_swing_rate, mean_swing_length, provisional_share, built_at
Idempotent on (batter, game_date) — a re-run replaces a day rather than
duplicating it, so a provisional day is silently upgraded once the canonical
pull finalizes. Atomic temp+replace (the 4.94 snapshot-logger pattern).

Usage
-----
    python scripts/xfp/build_bat_speed_daily.py --backfill          # 2024->today
    python scripts/xfp/build_bat_speed_daily.py                     # last 10 days
    python scripts/xfp/build_bat_speed_daily.py --days 30
    python scripts/xfp/build_bat_speed_daily.py --coverage-report
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

CACHE = ROOT / "data" / "research" / "xfp_cache"
OUT_PARQUET = ROOT / "data" / "research" / "bat_speed_daily.parquet"

# bat tracking begins in 2024; earlier seasons have no bat_speed column at all
FIRST_YEAR = 2024
MIN_BAT_SPEED = 10.0     # sensor-junk floor (matches lib/trend_signal)
FAST_SWING_MPH = 75.0    # "fast swing" definition used across the repo

KEY = ["batter", "game_date"]


def _statcast_path(year: int) -> Path:
    return CACHE / f"statcast_{year}.parquet"


def _available_columns(path: Path) -> set[str]:
    import pyarrow.parquet as pq
    return set(pq.ParquetFile(path).schema.names)


def _load_year(year: int, since: date | None = None) -> pd.DataFrame:
    """Load the swing-level slice for one season (empty frame if unavailable)."""
    path = _statcast_path(year)
    if not path.exists():
        print(f"  {year}: {path.name} missing — skipped")
        return pd.DataFrame()
    cols = _available_columns(path)
    if "bat_speed" not in cols:
        print(f"  {year}: no bat_speed column (pre-2024 season) — skipped")
        return pd.DataFrame()

    want = ["batter", "game_date", "bat_speed"]
    for opt in ("swing_length", "source"):
        if opt in cols:
            want.append(opt)
    df = pd.read_parquet(path, columns=want)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce").dt.date
    df = df[df["game_date"].notna()]
    if since is not None:
        df = df[df["game_date"] >= since]
    # swings only
    df = df[df["bat_speed"].notna() & (df["bat_speed"] > MIN_BAT_SPEED)]
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse swing-level rows to one row per (batter, game_date)."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["_fast"] = (d["bat_speed"] >= FAST_SWING_MPH).astype(float)
    if "source" in d.columns:
        # gf_provisional rows are same-day estimates that the canonical pull
        # later overwrites; carrying the share lets a study exclude or weight them
        d["_prov"] = (d["source"].astype(str) == "gf_provisional").astype(float)
    else:
        d["_prov"] = 0.0

    agg = {
        "n_swings": ("bat_speed", "size"),
        "mean_bat_speed": ("bat_speed", "mean"),
        "p90_bat_speed": ("bat_speed", lambda s: float(np.quantile(s, 0.90))),
        "fast_swing_rate": ("_fast", "mean"),
        "provisional_share": ("_prov", "mean"),
    }
    if "swing_length" in d.columns:
        agg["mean_swing_length"] = ("swing_length", "mean")

    out = d.groupby(KEY).agg(**agg).reset_index()
    if "mean_swing_length" not in out.columns:
        # gf feed carries batSpeed but NOT swing_length/attack_angle; keep the
        # column present so the schema is stable across builds
        out["mean_swing_length"] = np.nan
    out["batter"] = out["batter"].astype(int)
    return out


def upsert(new: pd.DataFrame) -> tuple[int, int]:
    """Idempotent append keyed on (batter, game_date). Returns (added, replaced)."""
    if new.empty:
        return (0, 0)
    new = new.copy()
    new["built_at"] = pd.Timestamp.now().isoformat(timespec="seconds")

    if OUT_PARQUET.exists():
        old = pd.read_parquet(OUT_PARQUET)
        old["game_date"] = pd.to_datetime(old["game_date"], errors="coerce").dt.date
        before = len(old)
        merged = pd.concat([old, new], ignore_index=True)
        # last wins -> a re-run upgrades a provisional day in place
        merged = merged.drop_duplicates(subset=KEY, keep="last")
        replaced = before + len(new) - len(merged)
        added = len(merged) - before
    else:
        merged = new
        added, replaced = len(new), 0

    merged = merged.sort_values(KEY).reset_index(drop=True)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PARQUET.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    os.replace(tmp, OUT_PARQUET)
    return (added, replaced)


def coverage_report() -> None:
    """Per-season swing coverage — is the store actually usable for a study?"""
    if not OUT_PARQUET.exists():
        print("no store yet; run with --backfill")
        return
    d = pd.read_parquet(OUT_PARQUET)
    d["game_date"] = pd.to_datetime(d["game_date"])
    d["year"] = d["game_date"].dt.year
    print(f"\n{OUT_PARQUET.name}: {len(d):,} batter-days\n")
    g = d.groupby("year").agg(
        batter_days=("batter", "size"),
        batters=("batter", "nunique"),
        days=("game_date", "nunique"),
        swings=("n_swings", "sum"),
        med_swings_per_day=("n_swings", "median"),
        mean_bs=("mean_bat_speed", "mean"),
        prov_share=("provisional_share", "mean"),
        swing_len_fill=("mean_swing_length", lambda s: float(s.notna().mean())),
    )
    print(g.round(3).to_string())
    print(f"\ndate range: {d['game_date'].min().date()} -> {d['game_date'].max().date()}")
    # a study needs enough swings per player-window to clear a stabilization gate
    per_player_season = d.groupby([d["year"], "batter"])["n_swings"].sum()
    print("\nseason swings per batter (quantiles):")
    print(per_player_season.groupby(level=0).quantile([.25, .5, .75, .95]).round(0).to_string())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backfill", action="store_true",
                    help=f"rebuild from {FIRST_YEAR} through today")
    ap.add_argument("--days", type=int, default=10,
                    help="incremental window in days (default 10)")
    ap.add_argument("--coverage-report", action="store_true",
                    help="print store coverage and exit")
    args = ap.parse_args()

    if args.coverage_report:
        coverage_report()
        return 0

    today = date.today()
    if args.backfill:
        years = list(range(FIRST_YEAR, today.year + 1))
        since = None
        print(f"BACKFILL {years[0]}-{years[-1]}")
    else:
        since = today - timedelta(days=args.days)
        years = sorted({since.year, today.year})
        print(f"INCREMENTAL since {since} (years {years})")

    frames = []
    for yr in years:
        df = _load_year(yr, since=since if yr == min(years) else None)
        if df.empty:
            continue
        out = aggregate(df)
        print(f"  {yr}: {len(df):,} swings -> {len(out):,} batter-days")
        frames.append(out)

    if not frames:
        print("nothing to write (no bat_speed data in range)")
        return 0

    new = pd.concat(frames, ignore_index=True).drop_duplicates(subset=KEY, keep="last")
    added, replaced = upsert(new)
    total = len(pd.read_parquet(OUT_PARQUET))
    print(f"\n{OUT_PARQUET.relative_to(ROOT)}: +{added} new, {replaced} replaced, "
          f"{total:,} batter-days total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
