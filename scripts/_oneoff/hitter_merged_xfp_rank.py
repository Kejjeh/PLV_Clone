"""Merged hitter board: MY hitters + every FA hitter, one ranking by xFP-RoS
and xFP-playoffs, sliced into FIVE position buckets (C, 1B/3B, 2B/SS, OF, UTIL).

Hitter parallel of scripts/_oneoff/sp_merged_xfp_rank.py — same window math,
same live IL-return folding, same availability scaling. Headline lens is rh3
(the validated RoS hitter projection per CLAUDE.md). No other lenses layered:
rank purely by rh3 per_game projected over the RoS / playoff windows.

Window math (parallel to the SP board):
  per_game  = xfp_rh3_per_game
  GPW       = 6.3 games/week (MLB everyday cadence; analogue of SP RATE=1.19/7)
  PLAYOFF_GAMES_FULL = 18 (~6 g/wk x 3 playoff wk; analogue of SP PLAYOFF_FULL=3.6)
  avail     = max(TODAY, return_date) if injured else TODAY
  ros_games = max(0,(SEASON_END-avail).days)/7 * GPW ;  xFP_ros = per_game*ros_games
  po_days   = max(0,(SEASON_END-max(avail,PLAYOFF_START)).days)
  xFP_po    = per_game * PLAYOFF_GAMES_FULL * po_days/PLAYOFF_DAYS

Name-collision safety (CLAUDE.md rule #10): join roster/FA names to rh3 by MLBAM
batter id via resolve_batter_id(name, team=, position=) when possible; otherwise
fall back to the SP script's two-pass norm-exact -> (last, first-initial) match.
"""
from __future__ import annotations
import sys, re, unicodedata
from pathlib import Path
from datetime import date
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))
from plv_clone.league_state import LeagueState
from app.espn_connector import get_my_roster_with_injuries
from plv_clone.utils.name_match import resolve_batter_id
import talent_prior as TP   # calibrated talent-prior fallback for rh3-absent elites

TODAY = date(2026, 6, 11)
SEASON_END = date(2026, 9, 20)
PLAYOFF_START = date(2026, 8, 17)
PLAYOFF_DAYS = (SEASON_END - PLAYOFF_START).days
GPW = 6.3                  # hitter games/week (MLB everyday cadence)
PLAYOFF_GAMES_FULL = 18    # ~6 g/wk x 3 playoff wk
HEUR = {"SIXTY_DAY_DL": 56, "FIFTEEN_DAY_DL": 21, "TEN_DAY_DL": 15,
        "OUT": 14, "DAY_TO_DAY": 0, "DOUBTFUL": 5, "QUESTIONABLE": 0}

# ESPN slot -> our bucket membership
OF_SLOTS = {"OF", "LF", "CF", "RF"}
HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH", "UTIL", "IF"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


# ── rh3 lookup tables (id-keyed primary + name-keyed fallback) ───────────────
RH3 = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv").dropna(subset=["player_name"])
RH3 = RH3[RH3["batter"].notna()].copy()
RH3["batter"] = RH3["batter"].astype(int)
RH3_BY_ID = RH3.set_index("batter")

# ESPN proTeam abbreviations differ from the abbreviations used in
# KNOWN_COLLISIONS / the multiyr cache. Alias them BEFORE resolve_batter_id so
# the team hint actually matches (canonical: ESPN "Oak" vs collision-list "ATH"
# for the second Max Muncy — without this, team match fails, ESPN gives
# position "DH" not "C", resolve returns None, and the norm fallback would
# silently grab the wrong Muncy row — the exact rule #10 footgun).
ESPN_TEAM_ALIAS = {"OAK": "ATH", "WSH": "WSH", "CHW": "CWS", "AZ": "ARI"}


def alias_team(t):
    if not t:
        return t
    return ESPN_TEAM_ALIAS.get(str(t).upper(), str(t).upper())


# name-keyed map (exact-norm fallback ONLY when id resolution fails).
# NOTE 1: the SP template's (last, first-initial) fallback is DELIBERATELY
# DROPPED here. With common hitter surnames it collapses many distinct ESPN
# FAs onto one rh3 row (e.g. Jesus/Jorge/Jose/Jeremy/Johnathan Rodriguez all
# false-mapping to Julio Rodriguez rank 16, or Lonnie White Jr./Lourdes
# Gurriel Jr./LaMonte Wade Jr. all -> Luis Garcia Jr. rank 42). resolve_batter_id
# (id-keyed via the multiyr cache) already covers the real players; exact-norm
# catches the rest. A first-initial fuzzy match only manufactures phantom dupes.
# NOTE 2: the exact-norm map is built COLLISION-SAFE — when a normalized name
# maps to >1 distinct rh3 batter id (Max Muncy LAD vs ATH), we mark it ambiguous
# and the fallback REFUSES to guess, mirroring resolve_batter_id's contract.
_FULL = {}
_FULL_IDS: dict[str, set] = {}
for _, _r in RH3.iterrows():
    _nn = norm(_r["player_name"])
    _FULL[_nn] = _r
    _FULL_IDS.setdefault(_nn, set()).add(int(_r["batter"]))
_AMBIG_NAMES = {k for k, v in _FULL_IDS.items() if len(v) > 1}

# multiyr cache pre-loaded once for resolve_batter_id
_MULTIYR = pd.read_csv(ROOT / "data/research/xfp_cache/hitters_multiyr_2015_2026.csv")


def rh3_row(name, team=None, position=None):
    """Return (rh3_row_series, source_str) or (None, 'NO_DATA').
    Primary: resolve_batter_id -> RH3_BY_ID. Fallback: two-pass name match."""
    # --- primary: id resolution (collision-safe), with ESPN team alias ---
    try:
        bid = resolve_batter_id(name, team=alias_team(team), position=position, multiyr=_MULTIYR)
    except Exception:
        bid = None
    if bid is not None and bid in RH3_BY_ID.index:
        row = RH3_BY_ID.loc[bid]
        if isinstance(row, pd.DataFrame):      # dup id (shouldn't happen) -> first
            row = row.iloc[0]
        return row, "id"
    # --- fallback: exact normalized name; REFUSE if name is ambiguous in rh3 ---
    nn = norm(name)
    if nn in _AMBIG_NAMES:
        return None, "NO_DATA"  # collision-safe: don't silently grab a row
    if nn in _FULL:
        return _FULL[nn], "name"
    return None, "NO_DATA"


def project(name, team=None, position=None):
    """(per_game, rank, signal, etfr, src). Falls back to the calibrated
    talent prior (LOW-CONF, src='talent_prior') for elites absent from rh3
    (Judge/Elly/Robert-class IL stashes the in-season model can't score)."""
    row, src = rh3_row(name, team=team, position=position)
    if row is not None:
        return (float(row["xfp_rh3_per_game"]), int(row["rank"]), str(row["signal"]),
                round(float(row["expected_total_fp_remaining"]), 0), src)
    try:
        bid = resolve_batter_id(name, team=alias_team(team), position=position, multiyr=_MULTIYR)
    except Exception:
        bid = None
    tp = TP.hitter_prior_pg(bid) if bid is not None else None
    if tp is not None:
        return (tp, None, "stash", None, "talent_prior")
    return (None, None, "", None, "NO_DATA")


def windows(avail):
    ros_games = max(0.0, (SEASON_END - avail).days) / 7.0 * GPW
    po_days = max(0, (SEASON_END - max(avail, PLAYOFF_START)).days)
    po_games = PLAYOFF_GAMES_FULL * po_days / PLAYOFF_DAYS
    return ros_games, po_games


def buckets_for(slots):
    """Given an iterable of ESPN eligible-slot strings, return the set of board
    buckets this hitter belongs to. UTIL = every hitter."""
    s = {str(x).upper() for x in (slots or [])}
    out = {"UTIL"}                              # everyone is in UTIL
    if "C" in s:
        out.add("C")
    if "1B" in s or "3B" in s:
        out.add("1B/3B")
    if "2B" in s or "SS" in s:
        out.add("2B/SS")
    if s & OF_SLOTS:
        out.add("OF")
    return out


def is_hitter_slots(slots):
    s = {str(x).upper() for x in (slots or [])}
    return bool(s & HITTER_POSITIONS)


def main():
    rows = []

    # ── MY hitters ───────────────────────────────────────────────────────────
    ros_my = get_my_roster_with_injuries()
    mine = ros_my[~ros_my["position"].isin(["SP", "RP", "P"])].copy()
    for _, p in mine.iterrows():
        nm = p["player_name"]
        team = p.get("pro_team", "") or None
        pos = p.get("position", "") or None
        per_game, rk, sig, etfr, src = project(nm, team=team, position=pos)
        injured = bool(p.get("injured"))
        rd = pd.to_datetime(p.get("return_date"), errors="coerce")
        ret = rd.date() if (injured and pd.notna(rd)) else TODAY
        avail = max(TODAY, ret)
        rg, pg = windows(avail)
        slots = p.get("eligible_slots", [])
        rows.append(dict(
            owner="MINE", name=nm, team=team or "", own="",
            slots=list(slots),
            per_game=None if per_game is None else round(per_game, 2),
            rank=rk, signal=sig, etfr=etfr, src=src,
            inj=p.get("injury_status", "") if injured else "",
            ret=ret if injured else "",
            xfp_ros=None if per_game is None else round(per_game * rg, 0),
            xfp_po=None if per_game is None else round(per_game * pg, 0),
        ))

    # ── FA pool: pull across every hitter position, dedupe by playerId ────────
    ls = LeagueState(); lg = ls._get_league()
    seen, fa_players = set(), []
    for fa_pos in ["C", "1B", "2B", "3B", "SS", "OF", "DH"]:
        try:
            for pl in lg.free_agents(size=1500, position=fa_pos):
                pid = int(pl.playerId)
                if pid in seen:
                    continue
                # only keep hitters
                if not is_hitter_slots(getattr(pl, "eligibleSlots", [])):
                    continue
                seen.add(pid)
                fa_players.append(pl)
        except Exception as e:
            print(f"[free_agents pos={fa_pos}] {type(e).__name__}: {e}")

    inj_ids = [int(p.playerId) for p in fa_players if getattr(p, "injured", False)]
    ret_map = {}
    try:
        idf = ls.injury_details(inj_ids)
        rc = next((c for c in idf.columns if "return" in c.lower()), None)
        ic = next((c for c in idf.columns if c.lower() in ("player_id", "playerid", "id")), None)
        if rc and ic:
            for _, r in idf.iterrows():
                rv = pd.to_datetime(r[rc], errors="coerce")
                if pd.notna(rv):
                    ret_map[int(r[ic])] = rv.date()
    except Exception as e:
        print(f"[injury_details] {type(e).__name__}: {e}")

    for p in fa_players:
        nm = p.name; pid = int(p.playerId)
        team = getattr(p, "proTeam", "") or None
        pos = getattr(p, "position", "") or None
        per_game, rk, sig, etfr, src = project(nm, team=team, position=pos)
        injured = bool(getattr(p, "injured", False))
        status = getattr(p, "injuryStatus", "ACTIVE")
        if injured:
            ret = ret_map.get(pid) or (pd.Timestamp(TODAY) + pd.Timedelta(days=HEUR.get(status, 21))).date()
        else:
            ret = TODAY
        avail = max(TODAY, ret)
        rg, pg = windows(avail)
        rows.append(dict(
            owner="FA", name=nm, team=team or "",
            own=round(getattr(p, "percent_owned", 0) or 0, 1),
            slots=list(getattr(p, "eligibleSlots", [])),
            per_game=None if per_game is None else round(per_game, 2),
            rank=rk, signal=sig, etfr=etfr, src=src,
            inj=status if injured else "", ret=ret if injured else "",
            xfp_ros=None if per_game is None else round(per_game * rg, 0),
            xfp_po=None if per_game is None else round(per_game * pg, 0),
        ))

    df = pd.DataFrame(rows)
    # attach bucket membership set per row
    df["buckets"] = df["slots"].apply(buckets_for)
    have = df[df["per_game"].notna()].copy()
    nodata = df[df["per_game"].isna()].copy()

    # ── write full merged board ──────────────────────────────────────────────
    out = ROOT / "data/research/hitter_merged_xfp_rank_2026-06-11.csv"
    out_df = df.copy()
    out_df["buckets"] = out_df["buckets"].apply(lambda s: "|".join(sorted(s)))
    out_df["slots"] = out_df["slots"].apply(lambda s: "|".join(map(str, s)))
    out_df.sort_values("xfp_ros", ascending=False, na_position="last").to_csv(out, index=False)

    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 500)
    COLS = ["name", "owner", "team", "own", "per_game", "rank", "signal", "src", "inj", "ret", "xfp_ros", "xfp_po"]

    BUCKETS = [
        ("C", "CATCHER (C)", 20),
        ("1B/3B", "CORNER INFIELD (1B / 3B)", 20),
        ("2B/SS", "MIDDLE INFIELD (2B / SS)", 20),
        ("OF", "OUTFIELD (OF)", 20),
        ("UTIL", "UTIL (ALL HITTERS)", 40),
    ]

    def show_bucket(bkey, label, n):
        sub = have[have["buckets"].apply(lambda s: bkey in s)].copy()
        nmine = (sub["owner"] == "MINE").sum()
        nfa = (sub["owner"] == "FA").sum()
        print(f"\n############################################################")
        print(f"### BUCKET: {label}   ({nmine} MINE + {nfa} FA = {len(sub)} ranked)")
        print(f"############################################################")
        for sortcol, sub_label in [("xfp_ros", "xFP ROS"), ("xfp_po", "xFP PLAYOFFS")]:
            v = sub.sort_values(sortcol, ascending=False).head(n).copy()
            v["name"] = v.apply(lambda r: ("* " if r.owner == "MINE" else "  ") + str(r["name"]), axis=1)
            print(f"\n--- {label} :: RANK BY {sub_label} (top {n}; * = MINE) ---")
            print(v[COLS].to_string(index=False))

    print("=" * 80)
    print(f"MERGED HITTER UNIVERSE: {len(have)} ranked "
          f"({(have['owner']=='MINE').sum()} MINE + {(have['owner']=='FA').sum()} FA)  |  "
          f"no rh3 data: {len(nodata)} "
          f"({(nodata['owner']=='MINE').sum()} MINE + {(nodata['owner']=='FA').sum()} FA)")
    print(f"id-keyed joins: {(have['src']=='id').sum()} | name-fallback: "
          f"{have['src'].isin(['name','name_li']).sum()} | "
          f"talent-prior (LOW-CONF stash): {(have['src']=='talent_prior').sum()} "
          f"[calib rh3_pg={TP.calib()[0]:.2f}+{TP.calib()[1]:.2f}*raw]")
    print("=" * 80)

    # smoke test: Max Muncy collision resolves
    mm_lad = resolve_batter_id("Max Muncy", team="LAD", position="3B", multiyr=_MULTIYR)
    mm_ath = resolve_batter_id("Max Muncy", team="ATH", position="C", multiyr=_MULTIYR)
    print(f"[smoke] Max Muncy LAD/3B -> {mm_lad} | ATH/C -> {mm_ath} "
          f"(distinct={mm_lad != mm_ath})")

    for bkey, label, n in BUCKETS:
        show_bucket(bkey, label, n)

    # ── no-data tail (rh3-absent FAs that are at least somewhat owned) ────────
    if not nodata.empty:
        tail = nodata[nodata["owner"] == "FA"].copy()
        tail["own_n"] = pd.to_numeric(tail["own"], errors="coerce").fillna(0)
        tail = tail.sort_values("own_n", ascending=False).head(20)
        print(f"\n--- NO rh3 DATA TAIL (FA, top 20 by own%) — absent from rh3, NOT rankable ---")
        if len(tail):
            print(tail[["name", "team", "own"]].to_string(index=False))
        mine_nodata = nodata[nodata["owner"] == "MINE"]
        if len(mine_nodata):
            print("\n[!] MINE hitters with NO rh3 data:",
                  ", ".join(mine_nodata["name"].tolist()))

    print(f"\nFull merged board -> {out}")


if __name__ == "__main__":
    main()
