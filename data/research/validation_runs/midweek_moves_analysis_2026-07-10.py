"""midweek_moves_analysis_2026-07-10.py — pre-registered study engine.

Prereg: data/research/validation_runs/midweek_moves_2026-07-10.md
Run AFTER the prereg was written. Matched-difference means with clustered
bootstrap CIs; no model fitting.

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python data/research/validation_runs/midweek_moves_analysis_2026-07-10.py
"""
from __future__ import annotations

import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

TX_PATH = ROOT / "data/research/transactions_history.parquet"
SNAP_PATH = ROOT / "data/research/matchup_rosters_history.parquet"
BOX_H = ROOT / "data/research/xfp_cache/boxscore_hitters.parquet"
BOX_P = ROOT / "data/research/xfp_cache/boxscore_pitchers.parquet"
PANEL_OUT = ROOT / "data/research/validation_runs/midweek_moves_panel_2026-07-10.csv"

JOSH_TEAM_ID = 8
LAST_CLOSED_WEEK_END = date(2026, 7, 5)
IL_STATES = {"TEN_DAY_DL", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "SEVEN_DAY_DL", "OUT"}
N_BOOT = 10_000
RNG = np.random.default_rng(20260710)


def norm(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for suf in (" jr.", " jr", " sr.", " sr", " ii", " iii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    s = "".join(c if c.isalpha() or c.isspace() else " " for c in s)
    return " ".join(s.split())


def week_start_of(d: date) -> date:
    if d <= date(2026, 3, 29):
        return date(2026, 3, 23)  # opening stub week
    return d - timedelta(days=d.weekday())


# ---------------------------------------------------------------- load data
tx = pd.read_parquet(TX_PATH)
tx["date"] = pd.to_datetime(tx["date"]).dt.date
tx["nname"] = tx["player_name"].map(norm)
tx = tx.sort_values("ts_ms").reset_index(drop=True)

snap = pd.read_parquet(SNAP_PATH)
snap["snapshot_date"] = pd.to_datetime(snap["snapshot_date"]).dt.date
snap["nname"] = snap["player_name"].map(norm)

bh = pd.read_parquet(BOX_H)
bp = pd.read_parquet(BOX_P)
for b in (bh, bp):
    b["game_date"] = pd.to_datetime(b["game_date"]).dt.date
    b["nname"] = b["player_name"].map(norm)

# per (mlbam, date) FP maps
fp_h = bh.groupby(["mlbam_id", "game_date"])["fp_h"].sum()
fp_sp = bp.groupby(["mlbam_id", "game_date"])["fp_sp"].sum()
fp_rp = bp.groupby(["mlbam_id", "game_date"])["fp_rp"].sum()
gs_map = bp.groupby(["mlbam_id", "game_date"])["gs"].sum()

# games-played dates per mlbam (activity proxy)
games_dates: dict[int, set] = {}
for df in (bh, bp):
    for mid, gd in df[["mlbam_id", "game_date"]].itertuples(index=False):
        games_dates.setdefault(int(mid), set()).add(gd)

# norm-name -> mlbam candidates from boxscores (skip-on-ambiguous resolver)
name2mlbam: dict[str, set] = {}
for df in (bh, bp):
    for nn, mid in df[["nname", "mlbam_id"]].drop_duplicates().itertuples(index=False):
        name2mlbam.setdefault(nn, set()).add(int(mid))

# position bucket per mlbam / per nname from snapshots (mode), fallback boxscore
pos_by_mlbam = (
    snap.dropna(subset=["mlbam_id"])
    .groupby("mlbam_id")["position"]
    .agg(lambda s: s.mode().iat[0])
    .to_dict()
)
pos_by_name = snap.groupby("nname")["position"].agg(lambda s: s.mode().iat[0]).to_dict()
mlbam_by_name_snap = (
    snap.dropna(subset=["mlbam_id"]).groupby("nname")["mlbam_id"].agg(lambda s: set(int(x) for x in s)).to_dict()
)

sp_ratio = bp.groupby("mlbam_id").agg(gs=("gs", "sum"), g=("gs", "size"))
pitcher_ids = set(int(i) for i in sp_ratio.index)
hitter_ids = set(int(i) for i in bh["mlbam_id"].unique())


def bucket_of(mlbam: int | None, nname: str) -> str | None:
    pos = None
    if mlbam is not None and mlbam in pos_by_mlbam:
        pos = pos_by_mlbam[mlbam]
    elif nname in pos_by_name:
        pos = pos_by_name[nname]
    if pos is not None:
        return pos if pos in ("SP", "RP") else "H"
    if mlbam is not None:
        if mlbam in pitcher_ids and mlbam not in hitter_ids:
            r = sp_ratio.loc[mlbam]
            return "SP" if r["gs"] / max(r["g"], 1) >= 0.4 else "RP"
        if mlbam in hitter_ids:
            return "H"
    return None


def resolve_mlbam(row) -> int | None:
    """Prereg resolution ladder: archived -> snapshot name+team -> resolver -> unique boxscore name."""
    if pd.notna(row.get("mlbam_id")):
        return int(row["mlbam_id"])
    nn = row["nname"]
    # (b) roster snapshots: same team within 21 days after add
    cand = snap[(snap["nname"] == nn) & (snap["team_id"] == row["team_id"])]
    cand = cand[(cand["snapshot_date"] >= row["date"]) & (cand["snapshot_date"] <= row["date"] + timedelta(days=21))]
    ids = set(int(x) for x in cand["mlbam_id"].dropna())
    if len(ids) == 1:
        return ids.pop()
    # (c) repo resolvers (no team hint available in tx — pro_team is blank)
    try:
        from plv_clone.utils.name_match import resolve_batter_id, resolve_pitcher_id
        mid = resolve_batter_id(row["player_name"])
        if mid is None:
            mid = resolve_pitcher_id(row["player_name"])
        if mid is not None:
            return int(mid)
    except Exception:
        pass
    # (b2) any-snapshot unique name match
    ids = mlbam_by_name_snap.get(nn, set())
    if len(ids) == 1:
        return next(iter(ids))
    # (d) unique boxscore name match (skip-on-ambiguous)
    ids = name2mlbam.get(nn, set())
    if len(ids) == 1:
        return next(iter(ids))
    return None


def fp_window(mlbam: int, bucket: str, d0: date, d1: date) -> float:
    src = {"H": fp_h, "SP": fp_sp, "RP": fp_rp}[bucket]
    try:
        s = src.loc[mlbam]
    except KeyError:
        return 0.0
    return float(s[(s.index >= d0) & (s.index <= d1)].sum())


def started_in_window(mlbam: int, d0: date, d1: date) -> bool:
    try:
        s = gs_map.loc[mlbam]
    except KeyError:
        return False
    return bool(s[(s.index >= d0) & (s.index <= d1)].sum() > 0)


# ------------------------------------------------- roster state machinery
class Roster:
    """Set-based roster membership: mlbam set + norm-name set (idempotent ops)."""

    def __init__(self):
        self.mids: set[int] = set()
        self.names: set[str] = set()
        self.name_of: dict[int, str] = {}

    def add(self, mid, nn):
        if mid is not None:
            self.mids.add(mid)
            self.name_of[mid] = nn
        if nn:
            self.names.add(nn)

    def remove(self, mid, nn):
        if mid is not None:
            self.mids.discard(mid)
            self.name_of.pop(mid, None)
        if nn:
            self.names.discard(nn)

    def members(self):
        """Return list of (mlbam|None, nname). Name-only members resolved later."""
        out = [(m, self.name_of.get(m, "")) for m in self.mids]
        covered = {nn for _, nn in out if nn}
        out += [(None, nn) for nn in self.names if nn not in covered]
        return out

    def copy(self):
        r = Roster()
        r.mids = set(self.mids)
        r.names = set(self.names)
        r.name_of = dict(self.name_of)
        return r


def snapshot_roster(snap_date: date) -> dict[int, Roster]:
    day = snap[snap["snapshot_date"] == snap_date]
    out: dict[int, Roster] = {}
    for row in day.itertuples(index=False):
        r = out.setdefault(int(row.team_id), Roster())
        mid = int(row.mlbam_id) if pd.notna(row.mlbam_id) else None
        r.add(mid, row.nname)
    return out


ANCHOR_DATE = date(2026, 6, 4)
anchor = snapshot_roster(ANCHOR_DATE)

tx_events = []
for row in tx.itertuples(index=False):
    mid = int(row.mlbam_id) if pd.notna(row.mlbam_id) else None
    tx_events.append((row.ts_ms, row.date, int(row.team_id), row.action_str, mid, row.nname))
tx_events.sort(key=lambda t: t[0])


def roster_at(boundary: date) -> dict[int, Roster]:
    """League roster state at boundary 00:00, reconstructed from anchor + tx."""
    state = {t: r.copy() for t, r in anchor.items()}
    if boundary <= ANCHOR_DATE:
        # walk backward: un-apply tx with date in [boundary, ANCHOR_DATE], desc order
        for ts, d, tid, act, mid, nn in reversed(tx_events):
            if d < boundary or d > ANCHOR_DATE:
                continue
            r = state.setdefault(tid, Roster())
            if "ADDED" in act:
                r.remove(mid, nn)
            elif act == "DROPPED":
                r.add(mid, nn)
    else:
        # walk forward: apply tx with date in [ANCHOR_DATE, boundary-1], asc order
        for ts, d, tid, act, mid, nn in tx_events:
            if d < ANCHOR_DATE or d >= boundary:
                continue
            r = state.setdefault(tid, Roster())
            if "ADDED" in act:
                r.add(mid, nn)
            elif act == "DROPPED":
                r.remove(mid, nn)
    return state


# For post-June weeks prefer the nearest real snapshot before the boundary
FULL_SNAP_DATES = sorted(d for d, n in snap.groupby("snapshot_date").size().items() if n >= 200)


def opening_roster(week_start: date) -> dict[int, Roster]:
    prior = [d for d in FULL_SNAP_DATES if d < week_start]
    if not prior or week_start <= ANCHOR_DATE:
        return roster_at(week_start)
    a = prior[-1]
    state = snapshot_roster(a)
    for ts, d, tid, act, mid, nn in tx_events:
        if d < a or d >= week_start:
            continue
        r = state.setdefault(tid, Roster())
        if "ADDED" in act:
            r.add(mid, nn)
        elif act == "DROPPED":
            r.remove(mid, nn)
    return state


# ------------------------------------------------------- fidelity check
print("=" * 70)
print("FIDELITY CHECK: reconstruct from 2026-06-04 anchor vs real snapshots")
mismatches = []
for target in (date(2026, 6, 15), date(2026, 6, 22), date(2026, 6, 29)):
    recon = roster_at(target)
    actual = snapshot_roster(target)
    for tid in sorted(actual):
        ra, rr = actual[tid], recon.get(tid, Roster())
        # compare on union key: mlbam where both have it, else names
        a_keys = {m for m in ra.mids} | {n for n in ra.names}
        r_keys = {m for m in rr.mids} | {n for n in rr.names}
        # symmetric diff counted on name level to avoid mlbam-null noise
        d_names = ra.names.symmetric_difference(rr.names)
        mismatches.append({"target": target, "team_id": tid, "n_mismatch": len(d_names) / 2.0,
                           "detail": "; ".join(sorted(d_names))[:120]})
fid = pd.DataFrame(mismatches)
mean_mm = fid["n_mismatch"].mean()
print(fid.groupby("target")["n_mismatch"].agg(["mean", "max"]).to_string())
print(f"MEAN ABS MISMATCH = {mean_mm:.2f} players/team  (gate: <= 1.5 -> full-season PRIMARY)")
FULL_SEASON_PRIMARY = mean_mm <= 1.5
worst = fid.sort_values("n_mismatch", ascending=False).head(5)
print(worst.to_string(index=False))

# ------------------------------------------------------- build add-event panel
adds = tx[tx["action_str"].str.contains("ADDED")].copy()
adds["week_start"] = adds["date"].map(week_start_of)
adds["week_end"] = adds["week_start"].map(lambda ws: date(2026, 3, 29) if ws == date(2026, 3, 23) else ws + timedelta(days=6))
adds = adds[adds["week_end"] <= LAST_CLOSED_WEEK_END]
adds = adds.sort_values("ts_ms").drop_duplicates(subset=["team_id", "nname", "week_start"], keep="first")
n_total_adds = len(adds)

adds["res_mlbam"] = adds.apply(resolve_mlbam, axis=1)
n_unresolved = int(adds["res_mlbam"].isna().sum())
adds = adds.dropna(subset=["res_mlbam"])
adds["res_mlbam"] = adds["res_mlbam"].astype(int)
adds["bucket"] = [bucket_of(m, n) for m, n in zip(adds["res_mlbam"], adds["nname"])]
n_nobucket = int(adds["bucket"].isna().sum())
adds = adds.dropna(subset=["bucket"])

# IL snapshot availability per week (Monday +/- 1 day)
il_by_week: dict[date, dict] = {}
for ws in sorted(adds["week_start"].unique()):
    near = [d for d in FULL_SNAP_DATES if abs((d - ws).days) <= 1]
    if near:
        day = snap[snap["snapshot_date"] == near[0]]
        il = day[(day["injury_status"].isin(IL_STATES)) | (day["lineup_slot"] == "IL")]
        il_by_week[ws] = {"mids": set(int(x) for x in il["mlbam_id"].dropna()), "names": set(il["nname"])}

opening_cache: dict[date, dict[int, Roster]] = {}
rows = []
n_empty_pool = 0
for ev in adds.itertuples(index=False):
    ws, we = ev.week_start, ev.week_end
    if ws not in opening_cache:
        opening_cache[ws] = opening_roster(ws)
    team_open = opening_cache[ws].get(int(ev.team_id), Roster())
    d0, d1 = ev.date, we
    days_rem = (d1 - d0).days + 1
    add_fp = fp_window(ev.res_mlbam, ev.bucket, d0, d1) / days_rem

    # matched hold pool: same team, same bucket, on opening roster, not IL
    hold_vals = []
    for mid, nn in team_open.members():
        if mid is None:
            ids = mlbam_by_name_snap.get(nn) or name2mlbam.get(nn) or set()
            if len(ids) != 1:
                continue
            mid = next(iter(ids))
        if mid == ev.res_mlbam:
            continue
        b = bucket_of(mid, nn)
        if b != ev.bucket:
            continue
        ilw = il_by_week.get(ws)
        if ilw is not None:
            if mid in ilw["mids"] or nn in ilw["names"]:
                continue
        else:  # proxy: 0 MLB games in 14 days before week start
            gd = games_dates.get(mid, set())
            if not any(ws - timedelta(days=14) <= g < ws for g in gd):
                continue
        hold_vals.append(fp_window(mid, ev.bucket, d0, d1) / days_rem)
    if not hold_vals:
        n_empty_pool += 1
        continue
    rows.append({
        "team_id": int(ev.team_id), "team_name": ev.team_name, "player": ev.player_name,
        "mlbam": ev.res_mlbam, "bucket": ev.bucket, "add_date": d0, "week_start": ws,
        "week_end": d1, "dow": d0.weekday(), "days_rem": days_rem,
        "add_fp_day": add_fp, "hold_fp_day": float(np.mean(hold_vals)),
        "n_holds": len(hold_vals),
        "d": add_fp - float(np.mean(hold_vals)),
        "sp_started": started_in_window(ev.res_mlbam, d0, d1) if ev.bucket == "SP" else np.nan,
        "is_josh": int(ev.team_id) == JOSH_TEAM_ID,
        "il_source": "snapshot" if ws in il_by_week else "proxy14d",
    })

panel = pd.DataFrame(rows)
panel.to_csv(PANEL_OUT, index=False)
print("\n" + "=" * 70)
print(f"PANEL: {len(panel)} matched add-events "
      f"(from {n_total_adds} adds in closed weeks; {n_unresolved} unresolved mlbam, "
      f"{n_nobucket} no bucket, {n_empty_pool} empty hold pool)")
if len(panel) < 60:
    print("UNDERPOWERED (<60 events) — STOP per prereg.")
    sys.exit(0)


# ------------------------------------------------------- inference helpers
def cluster_boot(df: pd.DataFrame, stat_fn, n_boot=N_BOOT):
    """Bootstrap resampling (team, week) clusters; stat_fn(df)->float."""
    clusters = df.groupby(["team_id", "week_start"]).indices
    keys = list(clusters.keys())
    idx_arrays = [np.asarray(clusters[k]) for k in keys]
    stats = []
    point = stat_fn(df)
    for _ in range(n_boot):
        pick = RNG.integers(0, len(keys), size=len(keys))
        idx = np.concatenate([idx_arrays[i] for i in pick])
        s = stat_fn(df.iloc[idx])
        if s is not None and not np.isnan(s):
            stats.append(s)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return point, lo, hi


def mean_d(df):
    return float(df["d"].mean()) if len(df) else np.nan


def report_cell(label, df):
    n = len(df)
    if n == 0:
        print(f"{label:<46} n=0")
        return None
    pt, lo, hi = cluster_boot(df.reset_index(drop=True), mean_d)
    tag = "SIGN-ONLY" if n < 30 else ("CI<0" if hi < 0 else ("CI>0" if lo > 0 else "NULL"))
    print(f"{label:<46} n={n:<4} d={pt:+.3f} FP/day  CI[{lo:+.3f},{hi:+.3f}]  {tag}")
    return dict(label=label, n=n, d=pt, lo=lo, hi=hi, tag=tag)


results = {}
print("\nH1 — adds vs same-position opening-day holds (d = add − hold, FP/day)")
results["H1_overall"] = report_cell("ALL adds", panel)
for b in ("H", "SP", "RP"):
    results[f"H1_{b}"] = report_cell(f"  bucket {b}", panel[panel["bucket"] == b])

print("\nH2 — SP adds: started-in-window vs not")
sp = panel[panel["bucket"] == "SP"].reset_index(drop=True)
sp_yes = sp[sp["sp_started"] == True]  # noqa: E712
sp_no = sp[sp["sp_started"] == False]  # noqa: E712
results["H2_started"] = report_cell("  SP adds w/ start in window", sp_yes)
results["H2_nostart"] = report_cell("  SP adds w/o start", sp_no)
if len(sp_yes) and len(sp_no):
    def h2_diff(df):
        a = df[df["sp_started"] == True]["d"]  # noqa: E712
        b = df[df["sp_started"] == False]["d"]  # noqa: E712
        if not len(a) or not len(b):
            return np.nan
        return float(a.mean() - b.mean())
    pt, lo, hi = cluster_boot(sp, h2_diff)
    print(f"  diff (started − not)                        Δ={pt:+.3f}  CI[{lo:+.3f},{hi:+.3f}]")
    results["H2_diff"] = dict(d=pt, lo=lo, hi=hi, n=len(sp))

print("\nH3 — add timing: Mon–Wed (dow 0-2) vs Thu–Sun (dow 3-6)")
early = panel[panel["dow"] <= 2].reset_index(drop=True)
late = panel[panel["dow"] >= 3].reset_index(drop=True)
results["H3_early"] = report_cell("  Mon–Wed adds", early)
results["H3_late"] = report_cell("  Thu–Sun adds", late)
def h3_diff(df):
    a = df[df["dow"] >= 3]["d"]
    b = df[df["dow"] <= 2]["d"]
    if not len(a) or not len(b):
        return np.nan
    return float(a.mean() - b.mean())
pt, lo, hi = cluster_boot(panel.reset_index(drop=True), h3_diff)
print(f"  diff (late − early)                         Δ={pt:+.3f}  CI[{lo:+.3f},{hi:+.3f}]")
results["H3_diff"] = dict(d=pt, lo=lo, hi=hi, n=len(panel))

print("\nSLICE — Josh (team 8) vs league (descriptive)")
report_cell("  Josh adds", panel[panel["is_josh"]].reset_index(drop=True))
report_cell("  Other 7 teams", panel[~panel["is_josh"]].reset_index(drop=True))

print("\nDESCRIPTIVE — day-of-week grid (mean d, n)")
dows = "Mon Tue Wed Thu Fri Sat Sun".split()
g = panel.groupby("dow").agg(n=("d", "size"), mean_d=("d", "mean"), add=("add_fp_day", "mean"), hold=("hold_fp_day", "mean"))
g.index = [dows[i] for i in g.index]
print(g.round(3).to_string())

print("\nDESCRIPTIVE — per-bucket x timing (mean d, n)")
panel["timing"] = np.where(panel["dow"] <= 2, "Mon-Wed", "Thu-Sun")
print(panel.pivot_table(index="bucket", columns="timing", values="d", aggfunc=["mean", "size"]).round(3).to_string())

print("\nDESCRIPTIVE — per-team (mean d, n)")
print(panel.groupby("team_name").agg(n=("d", "size"), mean_d=("d", "mean")).sort_values("mean_d").round(3).to_string())

print("\nDESCRIPTIVE — primary-scope check")
print(f"full-season primary per fidelity gate: {FULL_SEASON_PRIMARY}")
jun_on = panel[panel["week_start"] >= date(2026, 6, 8)].reset_index(drop=True)
report_cell("  snapshot-era only (weeks >= 2026-06-08)", jun_on)
print(f"\npanel csv -> {PANEL_OUT}")
