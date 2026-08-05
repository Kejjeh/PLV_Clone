"""Build a timestamped FA-pool snapshot for live marginal-value scoring.

Phase 2 (2026-06-05): RP-only.
Phase 2.5 (2026-06-06): Extended to H + SP. Three independent snapshot
files (fa_pool_RP_*, fa_pool_H_*, fa_pool_SP_*).

ROS estimates for H/SP (Phase 2.5 proxy assumptions — honest about limits):
  - H : ros_h_estimate  = xfp_rh3_per_pa * E[remaining_PA]
        E[remaining_PA] = `expected_pa_remaining` from rh3 CSV when
        present, else (162 - games_today_proxy) * 3.85 PA/G fallback.
        We use the CSV's published expected_pa_remaining when available
        (this is itself an ESPN-schedule-informed estimate).
  - SP: ros_sp_estimate = xfp_rp3_per_start * E[remaining_starts]
        E[remaining_starts] = max(0, 32 - gs_to) clamped to [0, 28]. This
        is a rough proxy — the goal is RELATIVE comparison across the FA
        pool, not absolute precision.

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
RH3   = REPO / "data/outputs/xfp_rh3_projections.csv"
RP3   = REPO / "data/outputs/xfp_rp3_projections.csv"
SNAP_DIR = REPO / "data/research/fa_snapshots"

# Hitter position buckets we capture. UTIL/DH treated as their own
# bucket; multi-eligibility hitters keep their primary position.
_HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF", "DH", "UTIL"}
# SP fallback: 162 / 5 = ~32 starts/season per rotation slot.
_SP_SEASON_STARTS = 32
# Hitter PA/G fallback if rh3 row missing expected_pa_remaining.
_PA_PER_GAME = 3.85
_GAMES_PER_SEASON = 162


# _norm routed to the name_match owner (item 10, 2026-07-04). Self-consistent
# (roster set + the rprs2 lookup dict are built + looked up with this helper).
# join_key is order-independent — strictly correct (zero false-merge), and fixes
# cross-format RP matching (rprs2 uses "Last, First" vs ESPN "First Last").
from plv_clone.utils.name_match import join_key as _norm  # noqa: E402


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
    fa_sps = [
        p for p in fas
        if getattr(p, "position", "") == "SP"
        and _norm(p.name) not in rostered_names
    ]
    fa_hitters = [
        p for p in fas
        if getattr(p, "position", "") in _HITTER_POSITIONS
        and _norm(p.name) not in rostered_names
    ]
    print(f"  raw FAs: {len(fas)} · RP after guard: {len(fa_rps)} · "
          f"SP after guard: {len(fa_sps)} · H after guard: {len(fa_hitters)}")

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

    # ============================================================
    # Phase 2.5 — Hitter snapshot.
    # ============================================================
    if RH3.exists() and fa_hitters:
        h_df = pd.read_csv(RH3)
        h_name_col = "player_name" if "player_name" in h_df.columns else "name_api"
        h_df["_norm_name"] = h_df[h_name_col].map(_norm)
        h_lookup = {row["_norm_name"]: row for _, row in h_df.iterrows()}

        h_rows: list[dict] = []
        for p in fa_hitters:
            nm = _norm(p.name)
            proj = h_lookup.get(nm)
            if proj is None:
                continue
            # ROS proxy: prefer published expected_total_fp_remaining when
            # present (this IS rh3's own ROS estimate). Falls back to
            # per_pa * expected_pa_remaining, then to per_pa * 3.85 * remG.
            ros_h = None
            try:
                if pd.notna(proj.get("expected_total_fp_remaining")):
                    ros_h = float(proj["expected_total_fp_remaining"])
                elif pd.notna(proj.get("xfp_rh3_per_pa")) and pd.notna(proj.get("expected_pa_remaining")):
                    ros_h = float(proj["xfp_rh3_per_pa"]) * float(proj["expected_pa_remaining"])
                elif pd.notna(proj.get("xfp_rh3_per_game")):
                    # Last-ditch fallback: assume half-season remaining proxy
                    ros_h = float(proj["xfp_rh3_per_game"]) * 80.0
            except (TypeError, ValueError):
                ros_h = None

            per_pa = None
            try:
                if pd.notna(proj.get("xfp_rh3_per_pa")):
                    per_pa = float(proj["xfp_rh3_per_pa"])
            except (TypeError, ValueError):
                per_pa = None
            pa_to = None
            try:
                if pd.notna(proj.get("pa_to")):
                    pa_to = int(proj["pa_to"])
            except (TypeError, ValueError):
                pa_to = None

            primary_pos = getattr(p, "position", "") or proj.get("primary_position") or "UTIL"
            try:
                eligible_slots = list(getattr(p, "eligibleSlots", []) or [])
            except Exception:
                eligible_slots = []

            h_rows.append({
                "snapshot_ts": now,
                "snapshot_label": label,
                "player_type": "H",
                "mlbam_id": int(proj["batter"]) if pd.notna(proj.get("batter")) else None,
                "player_name": str(proj[h_name_col]),
                "position": str(primary_pos),
                # carried so the cross-source identity guard below can check
                # this join against the club the mlbam actually plays for
                "pro_team": str(getattr(p, "proTeam", "") or ""),
                "eligible_slots": ",".join(str(s) for s in eligible_slots),
                "ros": ros_h,
                "blended_xfp_per_PA": per_pa,
                "pa_to": pa_to,
                "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
            })

        h_snap = pd.DataFrame(h_rows)
        print(f"\n  hitter snapshot rows (rh3-joined): {len(h_snap)}")
        # Cross-source identity guard. join_key makes the name match exact, but
        # exactness is not identity: a 0.1%-owned catcher named "Julio
        # Rodriguez" is unique in the FA pool AND the real J-Rod is unique in
        # rh3, so no duplicate fires and the join hands a replacement-level
        # bat a #12 projection at the top of every downstream board. The only
        # tell is that the joined mlbam plays for a club this row never claims.
        # Fail-soft: no club map -> everything UNVERIFIED, nothing dropped.
        if not h_snap.empty:
            try:
                from scripts.xfp.lib.team_override import (
                    identity_report, load_map, verify_identity)
                _kept, _drop = verify_identity(
                    h_snap, load_map(), mlbam_col="mlbam_id", team_col="pro_team")
                print(f"  {identity_report(_kept, _drop)}")
                for _r in _drop.itertuples(index=False):
                    print(f"    - dropped {_r.player_name} "
                          f"[{_r.identity_status}] espn={_r.pro_team} "
                          f"mlbam={_r.mlbam_id}")
                h_snap = _kept.drop(columns=["identity_status"])
            except Exception as _exc:
                print(f"  identity guard skipped ({_exc}) — NOT an all-clear")
        if not h_snap.empty:
            h_dated = SNAP_DIR / f"fa_pool_H_{label}.parquet"
            h_latest = SNAP_DIR / "fa_pool_H_latest.parquet"
            _atomic_write_parquet(h_snap, h_dated)
            _atomic_write_parquet(h_snap, h_latest)
            print(f"  WROTE {h_dated.name}")
            print(f"  WROTE {h_latest.name} (pointer)")
            print("  Top-3 ROS by position bucket:")
            for pos, group in h_snap.groupby("position"):
                top = group.sort_values("ros", ascending=False).head(3)
                print(f"    [{pos}] n={len(group)}")
                for _, r in top.iterrows():
                    ros = r["ros"] if pd.notna(r["ros"]) else float("nan")
                    print(f"      {r['player_name']:<28s}  ROS {ros:6.0f}  "
                          f"pa_to={r['pa_to']}  own={r['percent_owned']:.1f}%")
    else:
        print(f"\n  hitter snapshot skipped (RH3 exists={RH3.exists()}, "
              f"fa_hitters={len(fa_hitters)})")

    # ============================================================
    # Phase 2.5 — SP snapshot.
    # ============================================================
    if RP3.exists() and fa_sps:
        sp_df = pd.read_csv(RP3)
        sp_name_col = "player_name" if "player_name" in sp_df.columns else "name_api"
        sp_df["_norm_name"] = sp_df[sp_name_col].map(_norm)
        sp_lookup = {row["_norm_name"]: row for _, row in sp_df.iterrows()}

        sp_rows: list[dict] = []
        for p in fa_sps:
            nm = _norm(p.name)
            proj = sp_lookup.get(nm)
            if proj is None:
                continue
            per_start = None
            try:
                if pd.notna(proj.get("xfp_rp3_per_start")):
                    per_start = float(proj["xfp_rp3_per_start"])
            except (TypeError, ValueError):
                per_start = None
            gs_to = 0
            try:
                if pd.notna(proj.get("gs_to")):
                    gs_to = int(proj["gs_to"])
            except (TypeError, ValueError):
                gs_to = 0
            # E[remaining_starts]: rough 32-start season proxy, clamped.
            # Relative comparison is what matters; absolute precision is not
            # the goal here.
            remaining_starts = max(0, min(28, _SP_SEASON_STARTS - gs_to))
            ros_sp = per_start * remaining_starts if per_start is not None else None
            dq = proj.get("data_quality_tag")
            try:
                if pd.isna(dq):
                    dq = None
            except (TypeError, ValueError):
                pass

            sp_rows.append({
                "snapshot_ts": now,
                "snapshot_label": label,
                "player_type": "SP",
                "mlbam_id": int(proj["pitcher"]) if pd.notna(proj.get("pitcher")) else None,
                "player_name": str(proj[sp_name_col]),
                "ros": ros_sp,
                "blended_xfp_per_start": per_start,
                "gs_to": gs_to,
                "expected_remaining_starts": remaining_starts,
                "data_quality_tag": str(dq) if dq is not None else None,
                "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
            })

        sp_snap = pd.DataFrame(sp_rows)
        print(f"\n  SP snapshot rows (rp3-joined): {len(sp_snap)}")
        if not sp_snap.empty:
            sp_dated = SNAP_DIR / f"fa_pool_SP_{label}.parquet"
            sp_latest = SNAP_DIR / "fa_pool_SP_latest.parquet"
            _atomic_write_parquet(sp_snap, sp_dated)
            _atomic_write_parquet(sp_snap, sp_latest)
            print(f"  WROTE {sp_dated.name}")
            print(f"  WROTE {sp_latest.name} (pointer)")
            print("  Top-5 SP by ROS:")
            top = sp_snap.sort_values("ros", ascending=False).head(5)
            for _, r in top.iterrows():
                ros = r["ros"] if pd.notna(r["ros"]) else float("nan")
                ps = r["blended_xfp_per_start"] if pd.notna(r["blended_xfp_per_start"]) else float("nan")
                print(f"      {r['player_name']:<28s}  ROS {ros:6.0f}  "
                      f"per_start={ps:5.2f}  gs_to={r['gs_to']:>2d}  "
                      f"dq={r['data_quality_tag']}")
    else:
        print(f"\n  SP snapshot skipped (RP3 exists={RP3.exists()}, "
              f"fa_sps={len(fa_sps)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
