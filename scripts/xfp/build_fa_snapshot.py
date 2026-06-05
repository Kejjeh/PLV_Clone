"""Build a timestamped FA-pool snapshot for live marginal-value scoring.

Phase 2 (2026-06-05): RP-only.

For each verified FA reliever in the BrownU league, join with the rprs2
projection CSV to attach `xfp_ros`, `role_lag1`, `replacement_delta`,
`sv_lag1`, `hld_lag1` — the same fields blend_score.py already surfaces
for rostered RPs. The snapshot is the live universe of "best available
alternative at this role" that triangulate RP cards consume.

Reproducibility:
    - Dated parquet: data/research/fa_snapshots/fa_pool_RP_<YYYY-MM-DD-HHMM>.parquet
      (never overwritten)
    - Latest pointer: data/research/fa_snapshots/fa_pool_RP_latest.parquet
      (overwrite-style; downstream code prefers latest within 24h freshness window)

Required FA-verification guard (per feedback_free_agents_leaks_rostered.md):
    Pull `league.teams` first, build a `rostered_set` of normalized names,
    and subtract anyone in rostered_set from the FA list. This is the
    Julio Rodriguez bug — `league.free_agents()` occasionally leaks
    players who are actually on a roster.

Usage:
    python -X utf8 scripts/xfp/build_fa_snapshot.py
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

RPRS2 = REPO / "data/outputs/xfp_rprs2_projections.csv"
SNAP_DIR = REPO / "data/research/fa_snapshots"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def main() -> int:
    from app.espn_connector import _get_league

    SNAP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"FA SNAPSHOT BUILD — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Pull league + build rostered_set (Julio Rodriguez guard).
    league = _get_league()
    rostered_names: set[str] = set()
    for team in league.teams:
        for p in team.roster:
            rostered_names.add(_norm(p.name))
    print(f"  rostered guard: {len(rostered_names)} normalized names across {len(league.teams)} teams")

    # 2. Pull FA pool (unfiltered size=2000) and apply rostered guard.
    fas = league.free_agents(size=2000)
    fa_rps = [
        p for p in fas
        if getattr(p, "position", "") == "RP"
        and _norm(p.name) not in rostered_names
    ]
    print(f"  raw FAs: {len(fas)} · RP after rostered guard: {len(fa_rps)}")

    if not fa_rps:
        print("  no FA RPs — nothing to snapshot")
        return 0

    # 3. Load rprs2 and build name→row lookup.
    if not RPRS2.exists():
        print(f"  ERROR: missing {RPRS2}")
        return 1
    rp_df = pd.read_csv(RPRS2)
    name_col = "name_api" if "name_api" in rp_df.columns else "player_name"
    rp_df["_norm_name"] = rp_df[name_col].map(_norm)
    rp_lookup = {row["_norm_name"]: row for _, row in rp_df.iterrows()}

    # 4. Build snapshot rows.
    now = datetime.now()
    label = now.strftime("%Y-%m-%d-%H%M")
    rows: list[dict] = []
    for p in fa_rps:
        nm = _norm(p.name)
        proj = rp_lookup.get(nm)
        if proj is None:
            # Skip FAs not in our rprs2 universe — they can't anchor the
            # marginal comparison meaningfully without a projection.
            continue
        rows.append({
            "snapshot_ts": now,
            "snapshot_label": label,
            "player_type": "RP",
            "mlbam_id": int(proj["pitcher"]) if pd.notna(proj.get("pitcher")) else None,
            "player_name": str(proj[name_col]),
            "role_lag1": str(proj.get("role_lag1") or ""),
            "ros": float(proj["xfp_ros"]) if pd.notna(proj.get("xfp_ros")) else None,
            "replacement_delta": (
                float(proj["replacement_delta"])
                if pd.notna(proj.get("replacement_delta")) else None
            ),
            "sv_lag1": int(proj["sv_lag1"]) if pd.notna(proj.get("sv_lag1")) else 0,
            "hld_lag1": int(proj["hld_lag1"]) if pd.notna(proj.get("hld_lag1")) else 0,
            "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
        })

    snap = pd.DataFrame(rows)
    print(f"  snapshot rows (rprs2-joined): {len(snap)}")
    if snap.empty:
        print("  no joined rows — nothing to write")
        return 0

    # 5. Atomic write — dated + latest.
    dated = SNAP_DIR / f"fa_pool_RP_{label}.parquet"
    latest = SNAP_DIR / "fa_pool_RP_latest.parquet"
    _atomic_write_parquet(snap, dated)
    _atomic_write_parquet(snap, latest)
    print(f"  WROTE {dated.name}")
    print(f"  WROTE {latest.name} (pointer)")

    # 6. Summary: top-5 by ROS per role bucket.
    print("\n  Top-5 ROS by role bucket:")
    for role, group in snap.groupby("role_lag1"):
        top = group.sort_values("ros", ascending=False).head(5)
        print(f"    [{role or 'unknown'}] n={len(group)}")
        for _, r in top.iterrows():
            ros = r["ros"] if r["ros"] is not None else float("nan")
            print(f"      {r['player_name']:<28s}  ROS {ros:6.1f}  "
                  f"sv={r['sv_lag1']:>2d}  hld={r['hld_lag1']:>2d}  "
                  f"own={r['percent_owned']:.1f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
