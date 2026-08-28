"""
run_positional_board.py — ROS + Playoff positional comparison board.

Shows My Roster vs Top-10 FA at each slot:
  C | 1B/3B | 2B/SS | OF | UTIL | SP | RP

Two cuts per slot:
  ROS    = full remaining-season xFP
  PLAYOFFS = last 6 wks (~30% of RoS)

Data sources:
  Hitters: fa_pool_H_latest.parquet + rh3_projections.csv (my roster join)
  SPs    : xfp_rp3_projections.csv + available_fa() size=2000
  RPs    : fa_pool_RP_latest.parquet + rprs2_projections.csv (my roster join)
  PL     : pl_cache/pl_hitters_top150.json, pl_sps_top100.json, pl_closers.json
"""
from __future__ import annotations
import io, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# UTF-8 stdout on Windows
if sys.platform == "win32" and sys.stdout is sys.__stdout__:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import unicodedata
import pandas as pd
from plv_clone.projections import PROJECTIONS

OUT = ROOT / "data" / "outputs"
SNAPSHOTS = ROOT / "data" / "research" / "fa_snapshots"
PL_CACHE = ROOT / "data" / "research" / "pl_cache"

# ── DATE-PARAMETERIZED HORIZON (audit T44, 2026-08-01) ───────────────────────
# These were frozen literals — `WEEKS_REMAINING = 15.5` and `PLAYOFF_SHARE =
# 6/20`, the calendar as of 2026-06-15 — while the rh3/rprs2 ROS columns beside
# them shrink with the season. By 2026-08-01 the SP column claimed 18.4 starts
# against a real 8.5, and the frozen 0.30 playoff share understated the PLYO
# column for hitters and RPs as well as SPs. Idiom copied from the owner,
# build_xfp_boards.py:66-77.
#
# NOTE (pre-existing, deliberately not silently resolved here): the repo carries
# two season-end dates — 2026-09-20 in build_xfp_boards.py and run_consensus_diff.py,
# 2026-09-28 in build_matchup_dashboard.py. This board follows the two that agree.
# Settling that belongs in a shared owner (league_config), not in a third fork.
from datetime import date
from plv_clone.cap_math import STARTS_PER_SP_PER_WEEK as _SPW  # owner (audit 2026-07-04)

SEASON_END = date(2026, 9, 20)
PLAYOFF_START = date(2026, 8, 17)
RATE = _SPW / 7.0              # empirical SP starts per active SP per day


def _days_left(today: date | None = None) -> int:
    return max(0, (SEASON_END - (today or date.today())).days)


def _playoff_days_left(today: date | None = None) -> int:
    today = today or date.today()
    return max(0, (SEASON_END - max(today, PLAYOFF_START)).days)


def sp_starts_remaining(today: date | None = None) -> float:
    """Starts a healthy SP has left between *today* and season end."""
    return round(_days_left(today) * RATE, 1)


def playoff_sp_starts(today: date | None = None) -> float:
    """Starts a healthy SP has left inside the fantasy playoff window."""
    return round(_playoff_days_left(today) * RATE, 1)


def playoff_share(today: date | None = None) -> float:
    """Share of the remaining season that falls inside the playoff window.

    Scales the PLYO column for hitters and RPs (whose ROS is a full-season
    total) the way `playoff_sp_starts` scales the SP column.
    """
    return _playoff_days_left(today) / max(1, _days_left(today))


PLAYOFF_SHARE = playoff_share()
PLAYOFF_SP_STARTS = playoff_sp_starts()
SP_STARTS_REMAINING = sp_starts_remaining()

# ──────────────────────────────────────────────────────────────────────────────
# Data loaders
# ──────────────────────────────────────────────────────────────────────────────

def load_pl_ranks() -> dict[str, int]:
    """name_norm -> PL rank integer (from all three PL cache files).

    PL cache format: {"ranks": {"Player Name": rank_int, ...}, ...}

    Keys go through `_ascii_lower` (= name_match.safe_name_key), the SAME
    normalizer that builds every `name_norm` column below. It used to be a bare
    `.strip().lower()`, which kept accents and punctuation while the lookup side
    stripped them — so "José Ramírez", "Ryan O’Hearn" (the PL caches write a
    CURLY U+2019) and "C.J. Abrams" silently returned no PL rank. Fixed 2026-07-30.
    """
    ranks: dict[str, int] = {}
    for fname in ("pl_hitters_top150.json", "pl_sps_top100.json", "pl_closers.json"):
        p = PL_CACHE / fname
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("ranks", {})
        if isinstance(raw, dict):
            for name, rk in raw.items():
                nm = _ascii_lower(name)
                if nm and rk is not None:
                    ranks[nm] = int(rk)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    nm = _ascii_lower(item.get("name") or "")
                    rk = item.get("rank")
                else:
                    continue
                if nm and rk is not None:
                    ranks[nm] = int(rk)
    return ranks


def load_rh3() -> pd.DataFrame:
    df = PROJECTIONS.rh3()
    df["name_norm"] = df["player_name"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    df["ros"] = df["expected_total_fp_remaining"].fillna(0).round(1)
    df["playoffs"] = (df["ros"] * PLAYOFF_SHARE).round(1)
    out = df[["name_norm", "player_name", "batter", "primary_position",
              "ros", "playoffs", "xfp_rh3_per_pa", "signal"]].copy()
    # Deduplicate same-name players: keep higher-ROS entry (handles Max Muncy LAD/ATH)
    out = out.sort_values("ros", ascending=False).drop_duplicates("name_norm")
    return out


# Name join key — OWNER: name_match.safe_name_key (order-preserving, space-
# separated, collapses curly/straight apostrophes + C.J./CJ + hyphens). Every
# `name_norm` column in this file must come from this one function or the merges
# below join on nothing. The old local `_ascii_lower` kept punctuation, so an
# ESPN "C.J. Abrams" never matched an rh3 "CJ Abrams".
from plv_clone.utils.name_match import safe_name_key as _ascii_lower  # noqa: E402


# safe_name_key already rewrites "Last, First" -> "first last", so the rp3 flip
# this used to hand-roll is now the owner's job.
from plv_clone.utils.name_match import safe_name_key as _norm_sp_name  # noqa: E402


def load_rp3() -> pd.DataFrame:
    df = PROJECTIONS.rp3()
    # rp3 stores names as "Lastname, Firstname" — normalize to "firstname lastname"
    df["name_norm"] = df["player_name"].apply(_norm_sp_name)
    # RoS = per_start × SP_STARTS_REMAINING (weeks left × 1.19/wk)
    df["ros"] = (df["xfp_rp3_per_start"].fillna(0) * SP_STARTS_REMAINING).round(1)
    df["playoffs"] = (df["xfp_rp3_per_start"].fillna(0) * PLAYOFF_SP_STARTS).round(1)
    return df[["name_norm", "player_name", "pitcher", "xfp_rp3_per_start",
               "ros", "playoffs", "data_quality_tag", "signal"]].copy()


def load_rprs2() -> pd.DataFrame:
    df = PROJECTIONS.rprs2()
    df["name_norm"] = df["name_api"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    df["ros"] = df["xfp_ros"].fillna(0).round(1)
    df["playoffs"] = (df["ros"] * PLAYOFF_SHARE).round(1)
    return df[["name_norm", "name_api", "pitcher", "role_lag1",
               "sv_to", "hld_to", "ros", "playoffs", "signal"]].copy()


def latest_snapshot(prefix: str) -> pd.DataFrame | None:
    """Load the most recent fa_pool_{prefix}_latest.parquet."""
    p = SNAPSHOTS / f"fa_pool_{prefix}_latest.parquet"
    if p.exists():
        return pd.read_parquet(p)
    # Fall back to most recent dated file
    files = sorted(SNAPSHOTS.glob(f"fa_pool_{prefix}_*.parquet"))
    if files:
        return pd.read_parquet(files[-1])
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Roster + FA retrieval
# ──────────────────────────────────────────────────────────────────────────────

def load_my_roster() -> pd.DataFrame:
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    df = ls.my_roster()
    df["name_norm"] = df["player_name"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    # eligible_slots is a list; stringify for easy contains-checks
    df["slots_str"] = df["eligible_slots"].apply(
        lambda x: ",".join(x) if isinstance(x, list) else str(x)
    )
    return df


def load_fa_hitters() -> pd.DataFrame:
    """125-row rh3-joined FA hitter pool from latest snapshot."""
    snap = latest_snapshot("H")
    if snap is None:
        return pd.DataFrame()
    snap["name_norm"] = snap["player_name"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    # eligible_slots stored as comma-string in snapshot
    if "eligible_slots" not in snap.columns:
        snap["eligible_slots"] = snap.get("position", "")
    snap["slots_str"] = snap["eligible_slots"].astype(str)
    snap["playoffs"] = (snap["ros"] * PLAYOFF_SHARE).round(1)
    return snap


def load_fa_rp() -> pd.DataFrame:
    """243-row rprs2-joined FA RP pool from latest snapshot."""
    snap = latest_snapshot("RP")
    if snap is None:
        return pd.DataFrame()
    snap["name_norm"] = snap["player_name"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    snap["playoffs"] = (snap["ros"] * PLAYOFF_SHARE).round(1)
    return snap


def load_fa_sp_full(all_rostered_norm: set[str]) -> pd.DataFrame:
    """Full SP FA pool: available_fa() + rp3 join (wider than the 6-row snapshot)."""
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    fa_raw = ls.available_fa()
    # Filter to SP-eligible
    fa_sp = fa_raw[fa_raw["position"] == "SP"].copy()
    fa_sp["name_norm"] = fa_sp["player_name"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    # Remove rostered players
    fa_sp = fa_sp[~fa_sp["name_norm"].isin(all_rostered_norm)]
    # Join rp3
    rp3 = load_rp3()
    fa_sp = fa_sp.merge(rp3.drop(columns=["player_name"]), on="name_norm", how="left")
    fa_sp["playoffs"] = fa_sp["playoffs"].fillna(0)
    fa_sp["ros"] = fa_sp["ros"].fillna(0)
    return fa_sp


# ──────────────────────────────────────────────────────────────────────────────
# Position eligibility helpers
# ──────────────────────────────────────────────────────────────────────────────

def elig(slots_str: str, tokens: list[str]) -> bool:
    """True if any token appears as a whole slot token in the CSV string."""
    parts = {s.strip().upper() for s in slots_str.split(",")}
    return any(t.upper() in parts for t in tokens)


POS_SLOTS = {
    "C":     ["C"],
    "1B3B":  ["1B", "3B", "1B/3B"],
    "2BSS":  ["2B", "SS", "2B/SS"],
    "OF":    ["OF", "LF", "CF", "RF"],
    "UTIL":  ["UTIL"],
    "SP":    ["SP"],
    "RP":    ["RP"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Table formatter
# ──────────────────────────────────────────────────────────────────────────────

HDR = f"  {'Name':<28} {'Tag':<7} {'ROS':>6} {'PLYO':>6}  {'PL':>6}  {'Own%':>5}  Notes"
SEP = f"  {'-'*28} {'-'*7} {'-'*6} {'-'*6}  {'-'*6}  {'-'*5}  {'-'*20}"


def fmt_row(name, tag, ros, playoffs, pl_rank, own_pct, notes=""):
    pl = f"PL#{pl_rank:<3}" if pl_rank else "  —  "
    own = f"{own_pct:.0f}%" if own_pct else "  —"
    return (f"  {name:<28} {tag:<7} {ros:>6.1f} {playoffs:>6.1f}  {pl}  {own:>5}  {notes}")


def print_group(label: str, my_rows: list[dict], fa_rows: list[dict]):
    print(f"\n{'='*76}")
    print(f"  {label}")
    print(f"{'='*76}")
    print(HDR)
    print(SEP)

    print(f"  {'— MY ROSTER —'}")
    if not my_rows:
        print("    (none)")
    for r in my_rows:
        print(fmt_row(r["name"], "MINE", r["ros"], r["playoffs"],
                      r.get("pl_rank"), r.get("own_pct", 0), r.get("notes", "")))

    print(f"  {'— TOP FA —'}")
    if not fa_rows:
        print("    (none)")
    for i, r in enumerate(fa_rows, 1):
        print(fmt_row(r["name"], f"FA#{i}", r["ros"], r["playoffs"],
                      r.get("pl_rank"), r.get("own_pct", 0), r.get("notes", "")))


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#'*76}")
    print(f"  POSITIONAL BOARD  —  {date.today()}")
    print(f"  ROS = xFP through {SEASON_END} ({SP_STARTS_REMAINING} SP starts left) | "
          f"PLYO = from {PLAYOFF_START} ({PLAYOFF_SHARE:.0%} of RoS)")
    print(f"  Models: rh3 (H) | rp3 (SP) | rprs2 (RP)")
    print(f"{'#'*76}")

    print("\nLoading data...")
    pl_ranks = load_pl_ranks()
    rh3 = load_rh3()
    rp3 = load_rp3()
    rprs2 = load_rprs2()
    my_roster = load_my_roster()
    fa_h = load_fa_hitters()
    fa_rp = load_fa_rp()

    # Build all-rostered name set for SP filter
    from plv_clone.league_state import LeagueState
    ls = LeagueState()
    all_teams_df = ls.all_teams()
    all_rostered_norm = set(all_teams_df["player_name"].str.strip().str.lower().unique())
    fa_sp = load_fa_sp_full(all_rostered_norm)

    print(f"  rh3: {len(rh3)} | rp3: {len(rp3)} | rprs2: {len(rprs2)} | PL: {len(pl_ranks)}")
    print(f"  My roster: {len(my_roster)} | FA H: {len(fa_h)} | FA RP: {len(fa_rp)} | FA SP: {len(fa_sp)}")

    # ─── HITTER GROUPS ──────────────────────────────────────────────────────

    hitter_groups = [
        ("C  — Catcher",                       "C"),
        ("1B/3B — First & Third Base",         "1B3B"),
        ("2B/SS — Second Base & Shortstop",    "2BSS"),
        ("OF — Outfield",                      "OF"),
        ("UTIL — Best Hitter Available",       "UTIL"),
    ]

    for label, grp in hitter_groups:
        tokens = POS_SLOTS[grp]

        # My roster side: filter by slots_str, join rh3
        my_elig = my_roster[my_roster["slots_str"].apply(lambda s: elig(s, tokens))].copy()
        my_elig = my_elig.merge(rh3[["name_norm","ros","playoffs","xfp_rh3_per_pa","signal"]],
                                on="name_norm", how="left")
        my_elig["ros"] = my_elig["ros"].fillna(0)
        my_elig["playoffs"] = my_elig["playoffs"].fillna(0)

        my_rows = []
        for _, r in my_elig.sort_values("ros", ascending=False).iterrows():
            inj = r.get("injury_status", "")
            notes = f"[{inj}]" if inj and inj not in ("ACTIVE", "") else ""
            my_rows.append({
                "name": r["player_name"],
                "ros": r["ros"], "playoffs": r["playoffs"],
                "pl_rank": pl_ranks.get(r["name_norm"]),
                "own_pct": 100.0,
                "notes": notes,
            })

        # FA side: from fa_pool_H snapshot
        if fa_h.empty:
            fa_rows_raw = []
        else:
            fa_elig = fa_h[fa_h["slots_str"].apply(lambda s: elig(s, tokens))].copy()
            fa_elig = fa_elig.sort_values("ros", ascending=False).head(10)
            fa_rows_raw = []
            for _, r in fa_elig.iterrows():
                nm = r.get("player_name", "")
                nm_norm = str(nm).strip().lower()
                inj = ""  # snapshot doesn't carry injury status
                fa_rows_raw.append({
                    "name": nm,
                    "ros": r.get("ros", 0), "playoffs": r.get("playoffs", 0),
                    "pl_rank": pl_ranks.get(nm_norm),
                    "own_pct": r.get("percent_owned", 0),
                    "notes": inj,
                })

        print_group(label, my_rows, fa_rows_raw)

    # ─── SP ─────────────────────────────────────────────────────────────────

    # My SP roster
    my_sp = my_roster[my_roster["slots_str"].apply(lambda s: elig(s, ["SP"]))].copy()
    my_sp = my_sp.merge(rp3[["name_norm","ros","playoffs","xfp_rp3_per_start",
                               "data_quality_tag","signal"]],
                        on="name_norm", how="left")
    my_sp["ros"] = my_sp["ros"].fillna(0)
    my_sp["playoffs"] = my_sp["playoffs"].fillna(0)

    my_sp_rows = []
    for _, r in my_sp.sort_values("ros", ascending=False).iterrows():
        inj = r.get("injury_status", "")
        dq = r.get("data_quality_tag", "") or ""
        notes_parts = []
        if inj and inj not in ("ACTIVE", ""):
            notes_parts.append(f"[{inj}]")
        if "marcel" in str(dq):
            notes_parts.append("marcel_IL")
        per_s = r.get("xfp_rp3_per_start") or 0
        try:
            per_s = float(per_s)
        except (TypeError, ValueError):
            per_s = 0
        if per_s:
            notes_parts.append(f"{per_s:.1f}/start")
        my_sp_rows.append({
            "name": r["player_name"],
            "ros": r["ros"], "playoffs": r["playoffs"],
            "pl_rank": pl_ranks.get(r["name_norm"]),
            "own_pct": 100.0,
            "notes": "  ".join(notes_parts),
        })

    # FA SP
    fa_sp_rows = []
    if not fa_sp.empty:
        fa_sp_sorted = fa_sp.sort_values("ros", ascending=False).head(10)
        for _, r in fa_sp_sorted.iterrows():
            nm = r.get("player_name", "")
            nm_norm = str(nm).strip().lower()
            dq = r.get("data_quality_tag", "") or ""
            per_s = r.get("xfp_rp3_per_start") or 0
            try:
                per_s = float(per_s)
            except (TypeError, ValueError):
                per_s = 0
            notes_parts = []
            if "marcel" in str(dq):
                notes_parts.append("marcel_IL")
            if per_s:
                notes_parts.append(f"{per_s:.1f}/start")
            own = r.get("percent_owned", 0) or 0
            fa_sp_rows.append({
                "name": nm,
                "ros": r.get("ros", 0), "playoffs": r.get("playoffs", 0),
                "pl_rank": pl_ranks.get(nm_norm),
                "own_pct": own,
                "notes": "  ".join(notes_parts),
            })

    print_group("SP — Starting Pitchers", my_sp_rows, fa_sp_rows)

    # ─── RP ─────────────────────────────────────────────────────────────────

    # My RP roster
    my_rp = my_roster[my_roster["slots_str"].apply(lambda s: elig(s, ["RP"]))].copy()
    # Exclude SP/RP combos that are primarily starters
    my_rp = my_rp[~my_rp["slots_str"].apply(lambda s: elig(s, ["SP"]) and not elig(s, ["RP"]))].copy()
    my_rp = my_rp.merge(rprs2[["name_norm","ros","playoffs","role_lag1","sv_to","hld_to","signal"]],
                        on="name_norm", how="left")
    my_rp["ros"] = my_rp["ros"].fillna(0)
    my_rp["playoffs"] = my_rp["playoffs"].fillna(0)

    my_rp_rows = []
    for _, r in my_rp.sort_values("ros", ascending=False).iterrows():
        inj = r.get("injury_status", "")
        role = str(r.get("role_lag1", "") or "")
        role = "" if role in ("nan", "None", "") else role
        sv_raw = r.get("sv_to", 0)
        hld_raw = r.get("hld_to", 0)
        sv = 0 if (sv_raw is None or (isinstance(sv_raw, float) and sv_raw != sv_raw)) else int(sv_raw)
        hld = 0 if (hld_raw is None or (isinstance(hld_raw, float) and hld_raw != hld_raw)) else int(hld_raw)
        notes_parts = []
        if inj and inj not in ("ACTIVE", ""):
            notes_parts.append(f"[{inj}]")
        if role:
            notes_parts.append(role)
        if sv:
            notes_parts.append(f"{sv}SV")
        if hld:
            notes_parts.append(f"{hld}HLD")
        my_rp_rows.append({
            "name": r["player_name"],
            "ros": r["ros"], "playoffs": r["playoffs"],
            "pl_rank": pl_ranks.get(r["name_norm"]),
            "own_pct": 100.0,
            "notes": "  ".join(notes_parts),
        })

    # FA RP from snapshot
    fa_rp_rows = []
    if not fa_rp.empty:
        fa_rp_sorted = fa_rp.sort_values("ros", ascending=False).head(10)
        for _, r in fa_rp_sorted.iterrows():
            nm = r.get("player_name", "")
            nm_norm = str(nm).strip().lower()
            role = str(r.get("role_lag1", "") or "")
            role = "" if role in ("nan", "None", "") else role
            sv_raw = r.get("sv_lag1", 0)
            hld_raw = r.get("hld_lag1", 0)
            sv = 0 if (sv_raw is None or (isinstance(sv_raw, float) and sv_raw != sv_raw)) else int(sv_raw)
            hld = 0 if (hld_raw is None or (isinstance(hld_raw, float) and hld_raw != hld_raw)) else int(hld_raw)
            notes_parts = [role] if role else []
            if sv:
                notes_parts.append(f"{sv}SV")
            if hld:
                notes_parts.append(f"{hld}HLD")
            fa_rp_rows.append({
                "name": nm,
                "ros": r.get("ros", 0), "playoffs": r.get("playoffs", 0),
                "pl_rank": pl_ranks.get(nm_norm),
                "own_pct": r.get("percent_owned", 0) or 0,
                "notes": "  ".join(notes_parts),
            })

    print_group("RP — Relief Pitchers", my_rp_rows, fa_rp_rows)

    # ─── Footer ─────────────────────────────────────────────────────────────
    print(f"\n{'#'*76}")
    print(f"  END — ROS = rh3/rp3/rprs2 remaining FP | PLYO = {PLAYOFF_SHARE:.0%}×ROS")
    print(f"  FA hitters from fa_pool_H snapshot ({len(fa_h)} rh3-joined)")
    print(f"  FA SPs from available_fa() + rp3 join ({len(fa_sp)} SPs)")
    print(f"  FA RPs from fa_pool_RP snapshot ({len(fa_rp)} rprs2-joined)")
    print(f"  PL cache: {len(pl_ranks)} ranks loaded")
    print(f"{'#'*76}\n")


if __name__ == "__main__":
    main()
