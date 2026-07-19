"""run_consensus_diff.py — engine for the /consensus-diff skill.

Divergence board: OUR validated models vs the external projection CONSENSUS
(Steamer / ZiPS / ATC / FanGraphs Depth Charts rest-of-season, snapshotted
daily into data/research/fg_proj_cache/ by the FG RoS snapshotter).

Per player:
  our_ros_total   — the validated rate x volume convention:
                      hitter: xfp_rh3_per_pa x proj_ros_pa_per_teamgame x team_games_remaining
                      SP:     xfp_rp3_per_start x proj_ros_gs_per_teamgame x team_games_remaining
                      RP:     xfp_rprs2 xfp_ros directly
  consensus_mean  — mean of the systems' precomputed BrownU-FP RoS totals
                    (brownu_fp bats / brownu_fp_sp / brownu_fp_rp), plus spread
                    (std) and n_systems (Steamer covers ~everyone; the others
                    only rostered-ish players).
  diff / z        — ours - consensus_mean, z-scored within the role bucket
                    (H / SP / RP).
  decomposition   — VOLUME vs RATE: is the disagreement about playing time
                    (our projected RoS PA/GS vs theirs) or about the rate
                    (our per-PA / per-start FP vs theirs)? Log-additive:
                    log(our/cons) = log(vol_ratio) + log(rate_ratio); the
                    share of |log vol| labels VOLUME / RATE / MIXED.
                    (RPs: n/a — rprs2 is a direct-total model.)

Rule 13: divergence NEVER moves rh3/rp3/rprs2 and never re-ranks. It routes
attention (buy-early / sell-high second looks) to /triangulate. A validated
consensus-ENSEMBLE feature is a separate future study once ~4 weeks of
snapshots exist (~2026-08-06).

marcel_il / marcel-suppressed rp3 rows are EXCLUDED from the headline boards
(a suppressed prior is not a real model read) but kept in the CSV with a
MARCEL flag.

Usage:
  python scripts/xfp/run_consensus_diff.py                 # all roles
  python scripts/xfp/run_consensus_diff.py --role sp --top 8
  python scripts/xfp/run_consensus_diff.py --no-espn       # skip ownership
Outputs: console boards + data/outputs/consensus_diff.csv
         + data/outputs/consensus_diff.html
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plv_clone.utils.name_match import join_key as _nrm  # noqa: E402
from plv_clone.league_config import MY_TEAM_NAME

MY = MY_TEAM_NAME
CACHE = _ROOT / "data" / "research" / "fg_proj_cache"
OUT = _ROOT / "data" / "outputs"
SYSTEMS = ["steamerr", "rzips", "ratcdc", "rfangraphsdc"]
SYS_LABEL = {"steamerr": "Steamer", "rzips": "ZiPS", "ratcdc": "ATC",
             "rfangraphsdc": "FG-DC"}

# team-games-remaining idiom (mirrors build_xfp_boards.py: days/7 x GPW)
SEASON_END = date(2026, 9, 20)
GPW = 6.3
TEAM_GAMES_REMAINING = max(1.0, (SEASON_END - date.today()).days / 7.0 * GPW)

Z_FLAG = 1.0          # |z| above this lands on a board
VOL_SHARE_HI = 0.65   # decomposition labels
VOL_SHARE_LO = 0.35
MIN_CONS_FP = 25.0    # ignore deep-roster noise rows (max(ours, consensus) floor)


# ── FG cache loading ─────────────────────────────────────────────────────────

def _latest(system: str, side: str):
    """Latest snapshot file for (system, side); returns (date_str, path) or None."""
    files = sorted(CACHE.glob(f"*_{system}_{side}.csv"))
    if not files:
        return None
    f = files[-1]
    return f.name.split("_")[0], f


def load_consensus(side: str) -> tuple[pd.DataFrame, dict]:
    """Stack the latest snapshot of every system for one side (bat|pit).
    Returns (long df, meta {system: (date, n_rows)})."""
    frames, meta = [], {}
    for system in SYSTEMS:
        hit = _latest(system, side)
        if hit is None:
            continue
        snap_date, path = hit
        d = pd.read_csv(path)
        d = d.dropna(subset=["mlbam_id"]).copy()
        d["mlbam"] = d["mlbam_id"].astype(float).astype(int)
        d["system"] = system
        d["snap_date"] = snap_date
        if side == "bat":
            keep = ["mlbam", "system", "snap_date", "PlayerName", "Team",
                    "PA", "brownu_fp", "brownu_fp_per_pa"]
        else:
            keep = ["mlbam", "system", "snap_date", "PlayerName", "Team",
                    "GS", "ip_decimal", "brownu_fp_sp", "brownu_fp_rp",
                    "brownu_fp_per_start", "brownu_fp_rp_per_g"]
        d = d[keep].drop_duplicates(subset=["mlbam"], keep="first")
        meta[system] = (snap_date, len(d))
        frames.append(d)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), meta


def _agg(cons: pd.DataFrame, fp_col: str, vol_col: str, rate_col: str) -> pd.DataFrame:
    """Per-mlbam consensus aggregates: mean/std/n of the FP total, plus mean
    projected volume and rate across the covering systems."""
    c = cons.dropna(subset=[fp_col])
    g = c.groupby("mlbam")
    out = pd.DataFrame({
        "cons_mean": g[fp_col].mean(),
        "cons_std": g[fp_col].std(),
        "n_sys": g[fp_col].count(),
        "cons_vol": g[vol_col].mean() if vol_col else np.nan,
        "cons_rate": g[rate_col].mean() if rate_col else np.nan,
        "fg_name": g["PlayerName"].first(),
        "fg_team": g["Team"].first(),
        "systems": g["system"].apply(lambda s: "+".join(SYS_LABEL[x] for x in sorted(set(s)))),
    }).reset_index()
    return out


# ── our-side RoS totals (rate x volume convention) ──────────────────────────

def our_hitters() -> pd.DataFrame:
    rh3 = pd.read_csv(OUT / "xfp_rh3_projections.csv").dropna(
        subset=["batter", "xfp_rh3_per_pa"])
    vol = pd.read_csv(OUT / "xfp_volume_projections.csv")[
        ["mlbam_id", "proj_ros_pa_per_teamgame"]]
    df = rh3.merge(vol, left_on="batter", right_on="mlbam_id", how="left")
    df["our_vol"] = df["proj_ros_pa_per_teamgame"] * TEAM_GAMES_REMAINING  # RoS PA
    df["our_rate"] = df["xfp_rh3_per_pa"]
    df["our_total"] = df["our_rate"] * df["our_vol"]
    df["flag"] = np.where(df["our_vol"].isna(), "NO-VOL", "")
    df["role"] = "H"
    return df.rename(columns={"batter": "mlbam"})[
        ["mlbam", "player_name", "role", "our_total", "our_vol", "our_rate", "flag"]]


def our_sps() -> pd.DataFrame:
    rp3 = pd.read_csv(OUT / "xfp_rp3_projections.csv").dropna(
        subset=["pitcher", "xfp_rp3_per_start"])
    vol = pd.read_csv(OUT / "xfp_sp_volume_projections.csv")[
        ["mlbam_id", "proj_ros_gs_per_teamgame"]]
    df = rp3.merge(vol, left_on="pitcher", right_on="mlbam_id", how="left")
    df["our_vol"] = df["proj_ros_gs_per_teamgame"] * TEAM_GAMES_REMAINING  # RoS GS
    df["our_rate"] = df["xfp_rp3_per_start"]
    df["our_total"] = df["our_rate"] * df["our_vol"]
    tag = df.get("data_quality_tag", pd.Series("", index=df.index)).astype(str)
    df["flag"] = np.where(tag.str.contains("marcel"), "MARCEL",
                          np.where(df["our_vol"].isna(), "NO-VOL", ""))
    df["role"] = "SP"
    return df.rename(columns={"pitcher": "mlbam"})[
        ["mlbam", "player_name", "role", "our_total", "our_vol", "our_rate", "flag"]]


def our_rps(sp_ids: set) -> pd.DataFrame:
    rp = pd.read_csv(OUT / "xfp_rprs2_projections.csv").dropna(
        subset=["pitcher", "xfp_ros"])
    rp = rp[~rp["pitcher"].isin(sp_ids)].copy()   # dual rows rank as SP (rp3)
    rp["our_total"] = rp["xfp_ros"]
    rp["our_vol"] = np.nan
    rp["our_rate"] = np.nan
    rp["flag"] = ""
    rp["role"] = "RP"
    return rp.rename(columns={"pitcher": "mlbam", "name_api": "player_name"})[
        ["mlbam", "player_name", "role", "our_total", "our_vol", "our_rate", "flag"]]


# ── decomposition ────────────────────────────────────────────────────────────

def decompose(df: pd.DataFrame) -> pd.DataFrame:
    """log(our/cons) = log(vol ratio) + log(rate ratio) -> VOLUME/RATE/MIXED."""
    ok = (df["our_vol"].notna() & df["cons_vol"].notna() & df["cons_rate"].notna()
          & (df["our_vol"] > 0) & (df["cons_vol"] > 0)
          & (df["our_rate"] > 0) & (df["cons_rate"] > 0)
          & (df["our_total"] > 0) & (df["cons_mean"] > 0))
    df["vol_ratio"] = np.where(ok, df["our_vol"] / df["cons_vol"], np.nan)
    df["rate_ratio"] = np.where(ok, df["our_rate"] / df["cons_rate"], np.nan)
    lv = np.abs(np.log(df["vol_ratio"].where(ok)))
    lr = np.abs(np.log(df["rate_ratio"].where(ok)))
    share = lv / (lv + lr).replace(0, np.nan)
    df["vol_share"] = share.round(2)
    # swing-man guard (SP): if vol x rate doesn't reconstruct the consensus
    # total (FG credits relief innings inside brownu_fp_sp), the log-additive
    # split is invalid -> n/a
    implied = df["cons_vol"] * df["cons_rate"]
    swing = (df["role"] == "SP") & implied.notna() & (
        (implied / df["cons_mean"]).sub(1).abs() > 0.25)
    df["decomp"] = np.select(
        [share.isna() | swing, share >= VOL_SHARE_HI, share <= VOL_SHARE_LO],
        ["n/a", "VOLUME", "RATE"], default="MIXED")
    return df


# ── ownership (live ESPN walk; collision-safe with team hints) ──────────────
# Name-only join is the standing idiom (conviction-scan), but the Muncy class
# (two mlbams, same normalized full name) needs a TEAM hint: for board names
# that map to >1 mlbam, require ESPN pro_team == FG team (canonicalized).

_TEAM_CANON = {  # ESPN pro_team -> FG team code
    "KC": "KCR", "SD": "SDP", "SF": "SFG", "TB": "TBR", "WSH": "WSN",
    "OAK": "ATH", "CWS": "CHW",
}


def _canon_team(t) -> str:
    t = str(t).upper().strip()
    return _TEAM_CANON.get(t, t)


def ownership_fn(no_espn: bool, ambiguous_keys: set):
    if no_espn:
        return lambda name, team: "?"
    from app.espn_connector import get_all_teams
    teams = get_all_teams()
    keyed: dict[str, list] = {}
    for n, t, pt in zip(teams["player_name"], teams["team_name"],
                        teams["pro_team"]):
        keyed.setdefault(_nrm(n), []).append((t, _canon_team(pt)))

    def _fmt(t):
        return "MINE" if t == MY else f"opp:{t[:14]}"

    def own(name, fg_team):
        k = _nrm(name)
        entries = keyed.get(k)
        if entries is None:
            return "FA"
        if len(entries) == 1 and k not in ambiguous_keys:
            return _fmt(entries[0][0])
        # collision (either side) — resolve on team
        hits = [t for t, pt in entries if pt == _canon_team(fg_team)]
        if len(hits) == 1:
            return _fmt(hits[0])
        if not hits and k in ambiguous_keys and len(entries) == len(
                {pt for _, pt in entries}):
            return "FA"           # rostered same-name player is on another team
        return "CHECK"            # can't disambiguate — verify live
    return own


# ── boards ───────────────────────────────────────────────────────────────────

def fmt_row(r) -> str:
    spread = f"+-{r['cons_std']:.0f}" if pd.notna(r["cons_std"]) else "  --"
    if r["decomp"] in ("n/a",):
        dec = "decomp n/a"
    else:
        dec = (f"{r['decomp']:<6} vol x{r['vol_ratio']:.2f} / rate x{r['rate_ratio']:.2f}"
               f" (vol share {r['vol_share']:.0%})")
    fl = f"  [{r['flag']}]" if r["flag"] else ""
    return (f"  {str(r['player_name'])[:22]:<22} {str(r['own'])[:16]:<16} "
            f"ours {r['our_total']:>5.0f}  cons {r['cons_mean']:>5.0f}{spread} "
            f"(n={int(r['n_sys'])})  z {r['z']:+.2f}  {dec}{fl}")


def build_html(df: pd.DataFrame, meta_lines: list[str]):
    rows = []
    for _, r in df.sort_values("z", ascending=False).iterrows():
        cls = "hi" if r["z"] >= Z_FLAG else ("lo" if r["z"] <= -Z_FLAG else "")
        if str(r["own"]) == "FA":
            cls += " fa"
        elif str(r["own"]) == "MINE":
            cls += " mine"
        dec = "" if r["decomp"] == "n/a" else (
            f"{r['decomp']} (vol x{r['vol_ratio']:.2f} / rate x{r['rate_ratio']:.2f})")
        rows.append(
            f"<tr class='{cls}'><td>{r['player_name']}</td><td>{r['role']}</td>"
            f"<td>{r['own']}</td><td>{r['our_total']:.0f}</td>"
            f"<td>{r['cons_mean']:.0f}</td>"
            f"<td>{'' if pd.isna(r['cons_std']) else format(r['cons_std'], '.0f')}</td>"
            f"<td>{int(r['n_sys'])}</td><td>{r['z']:+.2f}</td><td>{dec}</td>"
            f"<td>{r['flag']}</td></tr>")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>consensus-diff — ours vs Steamer/ZiPS/ATC/DC ({date.today()})</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#111;color:#ddd;margin:20px}}
table{{border-collapse:collapse;font-size:13px}}
td,th{{padding:3px 9px;border-bottom:1px solid #333;text-align:left}}
th{{color:#8ab;position:sticky;top:0;background:#111;cursor:default}}
tr.hi td{{background:#16240f}} tr.lo td{{background:#2a1414}}
tr.fa td:first-child{{color:#7fd77f;font-weight:600}}
tr.mine td:first-child{{color:#7fb8ff;font-weight:600}}
.small{{color:#888;font-size:12px}}
</style></head><body>
<h2>consensus-diff — our RoS totals vs FG consensus</h2>
<p class="small">{'<br>'.join(meta_lines)}<br>
Rule 13: display/conviction only — divergence never moves rh3/rp3/rprs2.
Green rows = we're higher (z &ge; +{Z_FLAG}); red rows = consensus higher
(z &le; -{Z_FLAG}). FA names green, MINE names blue.</p>
<table><tr><th>player</th><th>role</th><th>own</th><th>ours</th><th>cons</th>
<th>spread</th><th>nSys</th><th>z</th><th>decomposition</th><th>flags</th></tr>
{''.join(rows)}
</table></body></html>"""
    (OUT / "consensus_diff.html").write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="all", choices=["h", "sp", "rp", "all"])
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--no-espn", action="store_true", help="skip live ownership")
    ap.add_argument("--min-fp", type=float, default=MIN_CONS_FP)
    a = ap.parse_args()

    cons_bat, meta_bat = load_consensus("bat")
    cons_pit, meta_pit = load_consensus("pit")
    meta_lines = []
    for side, meta in (("bat", meta_bat), ("pit", meta_pit)):
        meta_lines.append("  ".join(
            f"{SYS_LABEL[s]}:{d} ({n} rows, {side})" for s, (d, n) in meta.items()))
        print(f"[{side}] " + meta_lines[-1])

    agg_bat = _agg(cons_bat, "brownu_fp", "PA", "brownu_fp_per_pa")
    # SP consensus rate/vol need GS>0 rows (per_start undefined otherwise);
    # RP consensus total uses ALL rows (brownu_fp_rp = full value incl. SV/HLD)
    agg_sp = _agg(cons_pit[cons_pit["GS"] > 0.5], "brownu_fp_sp", "GS",
                  "brownu_fp_per_start")
    agg_rp = _agg(cons_pit, "brownu_fp_rp", None, None)

    sp = our_sps()
    frames = []
    roles = {"h": ["H"], "sp": ["SP"], "rp": ["RP"],
             "all": ["H", "SP", "RP"]}[a.role]
    if "H" in roles:
        frames.append(our_hitters().merge(agg_bat, on="mlbam", how="inner"))
    if "SP" in roles:
        frames.append(sp.merge(agg_sp, on="mlbam", how="inner"))
    if "RP" in roles:
        frames.append(our_rps(set(sp["mlbam"])).merge(agg_rp, on="mlbam", how="inner"))
    df = pd.concat(frames, ignore_index=True)

    # name fallback (a few rp3/rprs2 rows carry NaN player_name)
    df["player_name"] = df["player_name"].fillna(df["fg_name"])

    # floor out deep-roster noise, then diff + within-role z
    # (z params fit on non-marcel rows — a suppressed prior would skew them)
    df = df[np.maximum(df["our_total"].fillna(0), df["cons_mean"].fillna(0)) >= a.min_fp].copy()
    df["diff"] = df["our_total"] - df["cons_mean"]
    fit = df[df["flag"] != "MARCEL"]
    stats = fit.groupby("role")["diff"].agg(["mean", "std"])
    df["z"] = (df["diff"] - df["role"].map(stats["mean"])) / df["role"].map(stats["std"])
    df = decompose(df)

    # board-side name collisions (same normalized name, different mlbam)
    df["_nk"] = df["player_name"].map(_nrm)
    amb = set(df.groupby("_nk")["mlbam"].nunique().pipe(lambda s: s[s > 1]).index)
    own = ownership_fn(a.no_espn, amb)
    df["own"] = [own(n, t) for n, t in zip(df["player_name"], df["fg_team"])]
    df = df.drop(columns="_nk")

    df["team_games_remaining"] = round(TEAM_GAMES_REMAINING, 1)
    csv_cols = ["mlbam", "player_name", "role", "own", "our_total", "our_vol",
                "our_rate", "cons_mean", "cons_std", "n_sys", "systems",
                "cons_vol", "cons_rate", "diff", "z", "vol_ratio", "rate_ratio",
                "vol_share", "decomp", "flag", "fg_team", "team_games_remaining"]
    df[csv_cols].round(3).to_csv(OUT / "consensus_diff.csv", index=False)

    # headline boards exclude marcel-suppressed rows (prior != model read)
    board = df[df["flag"] != "MARCEL"]
    print(f"\nteam games remaining: {TEAM_GAMES_REMAINING:.1f}  |  floor: "
          f"max(ours, cons) >= {a.min_fp:.0f} FP  |  {len(df)} joined rows "
          f"({(df['flag'] == 'MARCEL').sum()} marcel rows CSV-only)")
    print("Rule 13: display/conviction layer only — divergence never moves "
          "rh3/rp3/rprs2. Ensemble-feature validation unlocks ~2026-08-06.")

    for role in roles:
        sub = board[board["role"] == role]
        if not len(sub):
            continue
        mv, mr = sub["vol_ratio"].median(), sub["rate_ratio"].median()
        if pd.notna(mv):
            print(f"\n[{role} calibration] bucket-median vol ratio x{mv:.2f}, "
                  f"rate ratio x{mr:.2f} — our volume model is conditional-on-"
                  f"availability (systematically below FG's healthy-return "
                  f"assumption); read ratios RELATIVE to these medians")
        print(f"\n===== {role} — WE'RE HIGHER (our model ahead of consensus; "
              f"buy-early watch OR our-model-wrong watch) =====")
        for _, r in sub[sub["z"] >= Z_FLAG].sort_values("z", ascending=False).head(a.top).iterrows():
            print(fmt_row(r))
        print(f"----- {role} — WE'RE LOWER (consensus likes him more; "
              f"sell-high / second-look list) -----")
        for _, r in sub[sub["z"] <= -Z_FLAG].sort_values("z").head(a.top).iterrows():
            print(fmt_row(r))

    mine = board[board["own"] == "MINE"].sort_values("z")
    if len(mine):
        print("\n===== REALITY-CHECK MY ROSTER (all MINE rows, consensus-lowest "
              "first) =====")
        for _, r in mine.iterrows():
            print(fmt_row(r))

    fa_hi = board[(board["own"] == "FA") & (board["z"] >= Z_FLAG)]
    if len(fa_hi):
        print(f"\n({len(fa_hi)} FA rows on the WE'RE-HIGHER board — the "
              f"buy-before-the-market-catches-up surface)")

    build_html(df, meta_lines)
    print(f"\nwrote {OUT / 'consensus_diff.csv'} and consensus_diff.html")


if __name__ == "__main__":
    main()
