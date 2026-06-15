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
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import unicodedata
import pandas as pd

OUT = ROOT / "data" / "outputs"
SNAPSHOTS = ROOT / "data" / "research" / "fa_snapshots"
PL_CACHE = ROOT / "data" / "research" / "pl_cache"

PLAYOFF_SHARE = 6 / 20         # last 6 of ~20 remaining weeks
PLAYOFF_SP_STARTS = round(1.19 * 6, 1)   # ~7.1 playoff starts per healthy SP
# Weeks remaining in regular season (June 15 → ~Sep 28)
WEEKS_REMAINING = 15.5
SP_STARTS_REMAINING = round(1.19 * WEEKS_REMAINING, 1)  # ~18.4

# ──────────────────────────────────────────────────────────────────────────────
# Data loaders
# ──────────────────────────────────────────────────────────────────────────────

def load_pl_ranks() -> dict[str, int]:
    """name_norm -> PL rank integer (from all three PL cache files).

    PL cache format: {"ranks": {"Player Name": rank_int, ...}, ...}
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
                nm = name.strip().lower()
                if nm and rk is not None:
                    ranks[nm] = int(rk)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    nm = (item.get("name") or "").strip().lower()
                    rk = item.get("rank")
                else:
                    continue
                if nm and rk is not None:
                    ranks[nm] = int(rk)
    return ranks


def load_rh3() -> pd.DataFrame:
    df = pd.read_csv(OUT / "xfp_rh3_projections.csv")
    df["name_norm"] = df["player_name"].apply(
        lambda x: _ascii_lower(str(x).strip()) if isinstance(x, str) else "")
    df["ros"] = df["expected_total_fp_remaining"].fillna(0).round(1)
    df["playoffs"] = (df["ros"] * PLAYOFF_SHARE).round(1)
    out = df[["name_norm", "player_name", "batter", "primary_position",
              "ros", "playoffs", "xfp_rh3_per_pa", "signal"]].copy()
    # Deduplicate same-name players: keep higher-ROS entry (handles Max Muncy LAD/ATH)
    out = out.sort_values("ros", ascending=False).drop_duplicates("name_norm")
    return out


def _ascii_lower(s: str) -> str:
    """Normalize accented chars to ASCII and lowercase."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()


def _norm_sp_name(raw) -> str:
    """Convert rp3 'Lastname, Firstname' → ascii-lowered 'firstname lastname'."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if "," in raw:
        parts = raw.split(",", 1)
        return _ascii_lower(f"{parts[1].strip()} {parts[0].strip()}")
    return _ascii_lower(raw)


def load_rp3() -> pd.DataFrame:
    df = pd.read_csv(OUT / "xfp_rp3_projections.csv")
    # rp3 stores names as "Lastname, Firstname" — normalize to "firstname lastname"
    df["name_norm"] = df["player_name"].apply(_norm_sp_name)
    # RoS = per_start × SP_STARTS_REMAINING (weeks left × 1.19/wk)
    df["ros"] = (df["xfp_rp3_per_start"].fillna(0) * SP_STARTS_REMAINING).round(1)
    df["playoffs"] = (df["xfp_rp3_per_start"].fillna(0) * PLAYOFF_SP_STARTS).round(1)
    return df[["name_norm", "player_name", "pitcher", "xfp_rp3_per_start",
               "ros", "playoffs", "data_quality_tag", "signal"]].copy()


def load_rprs2() -> pd.DataFrame:
    df = pd.read_csv(OUT / "xfp_rprs2_projections.csv")
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
    print(f"  POSITIONAL BOARD  —  2026-06-15")
    print(f"  ROS = full remaining season xFP | PLYO = last 6 wks ({PLAYOFF_SHARE:.0%} of RoS)")
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
