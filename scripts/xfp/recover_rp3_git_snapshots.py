"""Recover as-of rp3 projections from git history.

The daily refresh commits data/outputs/xfp_rp3_projections.csv, so the repo IS
a point-in-time archive of what the model actually said each morning. This is
the leakage-free way to extend the backtest before player_projection_history
begins (2026-06-04) — and it is the same method the registry's forward-
calibration study used.

Why NOT re-run the pipeline with a date cutoff: rp3 trains on multi-year panels
and its derived inputs (marcel baselines, archetype priors, park factors, PL
joins) carry full-season state a date filter will not strip. That produces a
number we never actually had, with invisible leakage. A committed file cannot
have seen the future.

Conservatism: when a date has several commits, take the EARLIEST. A later
same-day commit may have been regenerated after that day's games began.
Schema drifted over the season (data_quality_tag arrived later), so columns are
resolved defensively and missing ones become NA rather than dropping the date.
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
PATH = "data/outputs/xfp_rp3_projections.csv"
OUT = ROOT / "data/research/rp3_git_snapshots.parquet"

WANT = {
    "pitcher": "mlbam_id",
    "player_name": "player_name",
    "rank": "our_rank",
    "xfp_rp3_per_start": "our_proj",
    "data_quality_tag": "data_quality_tag",
}


def run(args: list[str]) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main():
    log = run(["git", "log", "--follow", "--format=%H|%ad|%at",
               "--date=short", "--", PATH]).strip().splitlines()
    # earliest commit per calendar date == smallest unix ts
    best: dict[str, tuple[int, str]] = {}
    for line in log:
        try:
            sha, day, ts = line.split("|")
        except ValueError:
            continue
        ts = int(ts)
        if day not in best or ts < best[day][0]:
            best[day] = (ts, sha)
    print(f"{len(log)} commits -> {len(best)} distinct dates "
          f"({min(best)} .. {max(best)})")

    frames, failed = [], []
    for day, (_ts, sha) in sorted(best.items()):
        blob = run(["git", "show", f"{sha}:{PATH}"])
        if not blob.strip():
            failed.append((day, sha, "empty/missing at that commit"))
            continue
        try:
            df = pd.read_csv(io.StringIO(blob))
        except Exception as e:
            failed.append((day, sha, f"parse: {e}"))
            continue
        missing = [c for c in ("pitcher", "rank", "xfp_rp3_per_start") if c not in df.columns]
        if missing:
            failed.append((day, sha, f"missing cols {missing}"))
            continue
        keep = {src: dst for src, dst in WANT.items() if src in df.columns}
        sub = df[list(keep)].rename(columns=keep)
        for _src, dst in WANT.items():
            if dst not in sub.columns:
                sub[dst] = pd.NA
        sub["snapshot_date"] = day
        sub["source"] = "git"
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    out["mlbam_id"] = pd.to_numeric(out["mlbam_id"], errors="coerce")
    out = out.dropna(subset=["mlbam_id"])
    out["mlbam_id"] = out["mlbam_id"].astype(int)
    out.to_parquet(OUT, index=False)

    print(f"recovered {len(out):,} rows over {out['snapshot_date'].nunique()} dates")
    print(out.groupby(out["snapshot_date"].str[:7]).agg(
        dates=("snapshot_date", "nunique"), rows=("mlbam_id", "size")).to_string())
    if failed:
        print(f"\n{len(failed)} date(s) skipped:")
        for f in failed[:10]:
            print("   ", f)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
