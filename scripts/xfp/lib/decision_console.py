"""decision_console.py — the shared brain of the embedded "My Team vs FA"
decision console (matchup.html / xfp_board.html / index.html).

DESIGN LAW: every number is computed ONCE, here, in Python, under test. The
payload carries precomputed values for all three axes (RoS / This-week /
Playoff), all swap deltas, verdicts and flags. The page renderers (vanilla JS
on matchup + xfp_board, React on index) are pure views — allowed client ops
are dict lookup, sort comparison, subtracting two payload numbers for display,
and sign→CSS class. Nothing else.

Axes
----
- xfp_ros / xfp_po  : from build_xfp_boards (source tiering, LOW-CONF,
                      IL-return availability scaling, forward-volume models —
                      all inherited, never recomputed here).
- xfp_week          : cap-aware current-period FP. SPs run through
                      cap_math.weekly_sp_projection with the PERIOD cap
                      (resolve_current_period_meta — 10 standard / 16 ASG /
                      20 playoff, NEVER hardcoded) minus ESPN statId-33
                      banked starts. Hitters = per_game × in-window team
                      games. RPs = axis unsupported ("—").
  NOTE (documented simplification): week FP uses the boards' flat rates —
  no opponent/park adjusters — so it can differ slightly from the matchup
  roster table, which is the adjusted source of truth.

Week context comes from the matchup build when available (zero refetch) or
from compute_week_ctx() otherwise; BOTH paths reuse the canonical engines
(build_sp_starts_by_pitcher / fetch_week_probables / weekly_sp_projection) —
never a new rotation-gap implementation (the cap concept is already smeared
across five implementations; this module must not add a sixth).

Circular-import guard: build_matchup_dashboard imports this module inside
main(), and this module imports build_matchup_dashboard inside functions.
Neither imports the other at module level.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
for _p in (str(ROOT / "src"), str(ROOT), str(ROOT / "scripts" / "xfp"),
           str(ROOT / "scripts" / "xfp" / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_xfp_boards as B
from plv_clone.cap_math import (
    RosterPitcher,
    WeekProbables,
    weekly_sp_projection,
)

try:
    from lib.period_meta import resolve_current_period_meta, espn_period_meta
except ImportError:                                       # imported as lib sibling
    from period_meta import resolve_current_period_meta, espn_period_meta

SCHEMA_VERSION = 1
RPRS2_CSV = ROOT / "data" / "outputs" / "xfp_rprs2_projections.csv"

# Swap-verdict thresholds — extracted from eval_team_vs_fa.py (print-only
# main(); :173/:239 per-pair pitcher swings, :327 hitter slot totals).
# Boundaries are strict `>` to match the source.
PAIR_STRONG_FP = 30
PAIR_MODEST_FP = 10
SLOT_STRONG_FP = 50
SLOT_MODEST_FP = 20

# FA rows embedded per bucket (payload size control — never the 2000-FA pool).
SP_FA_N = 40
RP_FA_N = 25
BUCKET_FA_N = {"C": 20, "1B/3B": 25, "2B/SS": 25, "OF": 30, "UTIL": 50}
PAIR_TOP_FA = 25          # pairwise cap-aware week-delta map: MINE × top-N FA
REC_WORST_N = 5           # drop candidates considered per bucket
HEADLINE_MAX = 8

IL_LINEUP_SLOTS = {"IL", "IL10", "IL15", "IL60", "IR"}

BUCKET_ORDER = [
    ("SP", "Starting Pitchers"),
    ("RP", "Relief Pitchers"),
    ("C", "Catcher (C)"),
    ("1B/3B", "Corner Infield (1B / 3B)"),
    ("2B/SS", "Middle Infield (2B / SS)"),
    ("OF", "Outfield (OF)"),
    ("UTIL", "UTIL (all hitters)"),
]

RP_NOTE = ("RP active-slot cap 4 — 1-for-1 swaps only; ranked by rprs2 "
           "(never rp3)")
WEEK_METHOD_NOTE = ("Week FP uses flat board rates (no opponent/park "
                    "adjusters); the matchup roster table is the adjusted "
                    "source of truth")


# ── small helpers ────────────────────────────────────────────────────────────
def _r1(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return round(f, 1)


def _iso(d):
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        return d
    try:
        return d.isoformat()
    except AttributeError:
        return str(d)


def _as_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        ts = pd.to_datetime(v, errors="coerce")
        return None if pd.isna(ts) else ts.date()
    except Exception:
        return None


def _row_id(mlbam, espn_id, name):
    if mlbam:
        return f"m-{int(mlbam)}"
    if espn_id:
        return f"e-{int(espn_id)}"
    return f"n-{B.norm(name)}"


def _verdict(delta, strong, modest):
    if delta is None:
        return "MARGINAL"
    if delta > strong:
        return "STRONG"
    if delta > modest:
        return "MODEST"
    return "MARGINAL"


def _counted_total(starts):
    return sum(s.projected_fp for s in starts if s.counts_toward_cap)


def _default_role_detector(player_or_row):
    try:
        from lib.pitcher_role import detect_pitcher_role
    except ImportError:
        from pitcher_role import detect_pitcher_role
    return detect_pitcher_role(player_or_row)


def _default_id_resolver(name, team=None, role=None):
    from plv_clone.utils.name_match import resolve_pitcher_id
    try:
        pid = resolve_pitcher_id(name, team=(B.alias_team(team) or None), role=role)
        return int(pid) if pid else None
    except Exception:
        return None


def _elig_set(p):
    return {str(s).upper() for s in (getattr(p, "eligibleSlots", None) or [])}


# ── matchup adapter ──────────────────────────────────────────────────────────
def roster_from_lineup(players, il_returns=None) -> pd.DataFrame:
    """ESPN lineup player objects -> the my_roster_with_injuries column set,
    so matchup's main() can feed the console WITHOUT re-instantiating
    LeagueState (network diet). `il_returns` maps espn playerId -> return
    date (matchup's in-hand IL map)."""
    il_returns = il_returns or {}
    rows = []
    for p in players:
        pid = int(getattr(p, "playerId", 0) or 0)
        rows.append({
            "player_name": getattr(p, "name", ""),
            "player_id": pid,
            "position": getattr(p, "position", ""),
            "pro_team": getattr(p, "proTeam", ""),
            "eligible_slots": list(getattr(p, "eligibleSlots", []) or []),
            "lineup_slot": getattr(p, "lineupSlot", ""),
            "injured": bool(getattr(p, "injured", False)),
            "injury_status": getattr(p, "injuryStatus", "ACTIVE"),
            "return_date": il_returns.get(pid),
        })
    cols = ["player_name", "player_id", "position", "pro_team",
            "eligible_slots", "lineup_slot", "injured", "injury_status",
            "return_date"]
    return pd.DataFrame(rows, columns=cols)


# ── week context ─────────────────────────────────────────────────────────────
def compute_week_ctx(league, roster: pd.DataFrame, fas: list, *,
                     my_team_id=None, today: date | None = None,
                     fa_week_top_n: int = SP_FA_N,
                     fa_sp_names: list | None = None) -> dict | None:
    """Assemble the week context the matchup build already has in-hand, for
    callers (xfp_board / standalone CLI) that don't. Reuses the canonical
    engines via a FUNCTION-LOCAL matchup import (circularity guard). Returns
    None on total failure — the console then falls back to est-everywhere,
    it never raises (fail-soft, unlike the matchup page gate).

    `fa_sp_names` optionally names the FA SPs worth projecting (e.g. the
    board's top-N by xfp_ros); default = first `fa_week_top_n` FA SPs.
    """
    try:
        import build_matchup_dashboard as M   # function-local: circularity guard
    except Exception:
        return None
    try:
        if today is None:
            today = datetime.now(ZoneInfo("America/New_York")).date()
        pmeta = resolve_current_period_meta(league, today=today)
        banked = None
        try:
            bm = espn_period_meta(league, pmeta["period"], my_team_id, None)
            banked = bm.get("my_banked")
        except Exception:
            banked = None

        win_start = max(pmeta["week_start"], today)
        week_end = pmeta["week_end"]
        schedules = M.fetch_espn_week_schedule(league, win_start, week_end)
        if not schedules:
            mlb_ids = set(M.ESPN_TO_MLB_TEAM.values())
            schedules = M.fetch_schedules_by_team(
                mlb_ids, win_start.isoformat(), week_end.isoformat())
        if not schedules or not any(schedules.values()):
            return {"pmeta": pmeta, "banked_mine": banked,
                    "schedules_by_team": {}, "sp_starts_by_pitcher": {},
                    "today": today, "source": "computed",
                    "team_map": dict(M.ESPN_TO_MLB_TEAM)}

        # pitcher ids: MINE SPs + the named / first-N FA SPs
        ids = []
        mine_sp = roster[roster["position"] == "SP"] if len(roster) else roster
        for _, r in mine_sp.iterrows():
            pid = _default_id_resolver(r["player_name"], team=r.get("pro_team"),
                                       role="SP")
            if pid:
                ids.append(pid)
        wanted = None
        if fa_sp_names is not None:
            wanted = {B.norm(n) for n in fa_sp_names}
        n_taken = 0
        for p in fas:
            if getattr(p, "position", None) != "SP":
                continue
            if wanted is not None and B.norm(p.name) not in wanted:
                continue
            if wanted is None and n_taken >= fa_week_top_n:
                break
            pid = _default_id_resolver(p.name, team=getattr(p, "proTeam", None),
                                       role="SP")
            if pid:
                ids.append(pid)
                n_taken += 1

        starts = M.build_sp_starts_by_pitcher(ids, schedules, win_start, week_end)
        return {"pmeta": pmeta, "banked_mine": banked,
                "schedules_by_team": schedules,
                "sp_starts_by_pitcher": starts,
                "today": today, "source": "computed",
                "team_map": dict(M.ESPN_TO_MLB_TEAM)}
    except Exception as e:
        print(f"[decision_console] compute_week_ctx failed "
              f"({type(e).__name__}: {e}) — week axis falls back to estimates")
        return None


def _ctx_team_map(week_ctx):
    tm = (week_ctx or {}).get("team_map")
    if tm:
        return tm
    try:
        import build_matchup_dashboard as M   # function-local: circularity guard
        return dict(M.ESPN_TO_MLB_TEAM)
    except Exception:
        return {}


def _probables_from_ctx(week_ctx):
    """{mlbam: [start_dict]} -> (WeekProbables, {mlbam: [start_dict]})."""
    starts, confirmed = {}, set()
    by_pid = week_ctx.get("sp_starts_by_pitcher") or {}
    for pid, games in by_pid.items():
        for g in games or []:
            d = _as_date(g.get("date"))
            if d is None:
                continue
            key = (int(pid), d)
            starts[key] = str(g.get("opp_team", "") or "")
            if g.get("confirmed"):
                confirmed.add(key)
    return WeekProbables(starts=starts, confirmed_keys=frozenset(confirmed)), by_pid


# ── the payload builder ──────────────────────────────────────────────────────
def build_console_data(*, roster, fas, league=None, injury_details=None,
                       my_team_id=None, week_ctx=None,
                       sp_board=None, hitter_board=None,
                       fa_week_top_n: int = SP_FA_N,
                       role_detector=None, id_resolver=None,
                       rprs2=None, starts_fetcher=None,
                       today: date | None = None,
                       source: str | None = None) -> dict:
    """Build the schema_version=1 console payload. Everything precomputed —
    see module docstring for the design law and axis definitions."""
    role_detector = role_detector or _default_role_detector
    id_resolver = id_resolver or _default_id_resolver
    if today is None:
        today = (week_ctx or {}).get("today") or B.TODAY

    # boards (skip rebuild when the caller already has them in hand)
    if sp_board is None:
        sp_board = B.build_sp_board(roster=roster, fas=fas,
                                    injury_details=injury_details)
    if hitter_board is None:
        hitter_board = B.build_hitter_board(roster=roster, fas=fas,
                                            injury_details=injury_details)

    # week context (compute only if the caller could not supply one)
    if week_ctx is None and league is not None:
        week_ctx = compute_week_ctx(
            league, roster, fas, my_team_id=my_team_id,
            fa_week_top_n=fa_week_top_n, today=today,
            fa_sp_names=list(
                sp_board[sp_board["owner"] == "FA"]
                .sort_values("xfp_ros", ascending=False)["name"]
                .head(fa_week_top_n)))

    # ── lookup maps off the raw inputs ──
    fa_by_norm = {}
    for p in fas or []:
        fa_by_norm.setdefault(B.norm(p.name), []).append(p)
    roster_meta = {}
    for _, r in (roster if roster is not None else pd.DataFrame()).iterrows():
        roster_meta[B.norm(r["player_name"])] = {
            "espn_id": int(r.get("player_id") or 0) or None,
            "lineup_slot": str(r.get("lineup_slot", "") or ""),
            "slots": [str(s).upper() for s in (r.get("eligible_slots") or [])],
            "injury_status": str(r.get("injury_status", "") or "ACTIVE"),
        }

    def _meta_for(row):
        """(espn_id, slots, lineup_slot, injury_status, player_obj|None)."""
        nn = B.norm(row["name"])
        if row["owner"] == "MINE":
            m = roster_meta.get(nn, {})
            return (m.get("espn_id"), m.get("slots", []),
                    m.get("lineup_slot", ""), m.get("injury_status", "ACTIVE"),
                    None)
        cands = fa_by_norm.get(nn, [])
        p = None
        if len(cands) == 1:
            p = cands[0]
        elif len(cands) > 1:
            team = str(row.get("team", "") or "").upper()
            p = next((c for c in cands
                      if str(getattr(c, "proTeam", "") or "").upper() == team),
                     None)
        if p is None:
            return (None, [], "", str(row.get("inj") or "ACTIVE"), None)
        return (int(p.playerId), sorted(_elig_set(p)), "",
                str(getattr(p, "injuryStatus", "ACTIVE") or "ACTIVE"), p)

    # ── week frame ──
    pmeta = (week_ctx or {}).get("pmeta")
    week_block = None
    win_start = win_end = None
    eff_cap = None
    ctx_est = week_ctx is None or pmeta is None
    if pmeta is not None:
        banked = (week_ctx or {}).get("banked_mine")
        win_start = max(pmeta["week_start"], today)
        win_end = pmeta["week_end"]
        eff_cap = max(0, int(pmeta["sp_cap"]) - int(banked or 0))
        week_block = {
            "period": pmeta["period"], "weeks": pmeta["weeks"],
            "sp_cap": pmeta["sp_cap"],
            "week_start": _iso(pmeta["week_start"]),
            "week_end": _iso(pmeta["week_end"]),
            "covered": bool(pmeta.get("covered")),
            "banked_mine": None if banked is None else int(banked),
            "banked_source": "espn" if banked is not None else "unavailable",
            "scheduled_mine": 0,          # filled below
            "cap_room": None if banked is None else eff_cap,
            "week_est": banked is None,   # may be OR'd below
        }
    rem_days = (max(0, (win_end - win_start).days) + 1) if pmeta is not None else 7

    probables, starts_by_pid = (WeekProbables(), {})
    if week_ctx is not None:
        probables, starts_by_pid = _probables_from_ctx(week_ctx)
    team_map = _ctx_team_map(week_ctx) if week_ctx is not None else {}
    sched = (week_ctx or {}).get("schedules_by_team") or {}

    buckets = {k: {"key": k, "label": lbl,
                   "axis_support": {"ros": True, "week": k != "RP",
                                    "po": True},
                   "note": RP_NOTE if k == "RP" else "",
                   "players": [], "recs": [], "pair_week_deltas": {}}
               for k, lbl in BUCKET_ORDER}

    # =========================================================================
    # SP bucket
    # =========================================================================
    sp_rows = sp_board.copy()
    sp_mine = sp_rows[sp_rows["owner"] == "MINE"]
    sp_fa = (sp_rows[sp_rows["owner"] == "FA"]
             .sort_values("xfp_ros", ascending=False).head(SP_FA_N))
    sp_take = pd.concat([sp_mine, sp_fa])

    # dual-eligible pool arms whose REAL role is SP (Detmers class): the board's
    # position=='SP' filter misses them — surface them honestly (rate from the
    # rp3 lookup where available, NO_DATA otherwise), never let them hide in RP.
    sp_extras = []
    board_norms = {B.norm(n) for n in sp_rows["name"]}
    dual_sp_norms = set()
    for p in fas or []:
        elig = _elig_set(p)
        if not ({"SP", "RP"} <= elig):
            continue
        try:
            role = role_detector(p)
        except Exception:
            role = "RP"
        if role != "SP":
            continue
        dual_sp_norms.add(B.norm(p.name))
        if B.norm(p.name) in board_norms:
            continue
        sp_extras.append(p)

    def _sp_mlbam(name, team):
        return id_resolver(name, team=team, role="SP")

    sp_players, mine_rps, rates = [], [], {}
    mlbam_by_rowid = {}
    for _, r in sp_take.iterrows():
        espn_id, _slots, lslot, istatus, _p = _meta_for(r)
        mlbam = _sp_mlbam(r["name"], r.get("team"))
        rid = _row_id(mlbam, espn_id, r["name"])
        flags = []
        src = str(r.get("src", "") or "")
        if src.startswith("talent_prior"):
            flags.append("LOW_CONF")
        if src.endswith("·flat↓"):
            flags.append("DOCKED")
        inj = str(r.get("inj") or "")
        if inj:
            flags.append("IL")
        per_start = r.get("per_start")
        if per_start is None or pd.isna(per_start):
            flags.append("NO_DATA")
        row = {
            "id": rid, "mlbam": mlbam, "espn_id": espn_id,
            "name": str(r["name"]), "owner": str(r["owner"]),
            "team": str(r.get("team", "") or ""),
            "own_pct": _r1(r.get("own")) if r["owner"] == "FA" else None,
            "slots": ["SP"], "rate": _r1(per_start),
            "rate_unit": "per_start", "src": src,
            "xfp_ros": _r1(r.get("xfp_ros")), "xfp_po": _r1(r.get("xfp_po")),
            "xfp_week": None, "xfp_week_marginal": None,
            "week_detail": {"starts": [], "games": None},
            "flags": flags, "inj": inj, "ret": _iso(r.get("ret")),
            "extras": {}, "_lslot": lslot, "_istatus": istatus,
        }
        if mlbam:
            mlbam_by_rowid[rid] = int(mlbam)
        sp_players.append(row)
        if row["owner"] == "MINE" and mlbam and _r1(per_start) is not None:
            mine_rps.append(RosterPitcher(name=row["name"], mlbam_id=int(mlbam),
                                          injury_status=istatus, position="SP"))
        if _r1(per_start) is not None:
            rates[row["name"]] = float(per_start)

    for p in sp_extras:
        espn_id = int(p.playerId)
        mlbam = _sp_mlbam(p.name, getattr(p, "proTeam", None))
        ps = _extra_sp_rate(p.name)
        if ps is None and B.norm(p.name) not in roster_meta:
            continue   # rate-less FA extras are noise (same rule as RP NO_DATA)
        flags = ["ROLE_SP"]
        rate = None
        xros = xpo = None
        src = "role_detect"
        if ps is not None:
            rate = _r1(ps[0])
            src = ps[1]
            ros_s, po_s = B._sp_starts(today)
            xros, xpo = _r1(ps[0] * ros_s), _r1(ps[0] * po_s)
        else:
            flags.append("NO_DATA")
        inj = (getattr(p, "injuryStatus", "") or ""
               if getattr(p, "injured", False) else "")
        if inj:
            flags.append("IL")
        rid = _row_id(mlbam, espn_id, p.name)
        sp_players.append({
            "id": rid, "mlbam": mlbam, "espn_id": espn_id, "name": p.name,
            "owner": "FA", "team": str(getattr(p, "proTeam", "") or ""),
            "own_pct": _r1(getattr(p, "percent_owned", None)),
            "slots": ["SP"], "rate": rate, "rate_unit": "per_start",
            "src": src, "xfp_ros": xros, "xfp_po": xpo,
            "xfp_week": None, "xfp_week_marginal": None,
            "week_detail": {"starts": [], "games": None},
            "flags": flags, "inj": inj, "ret": "", "extras": {},
            "_lslot": "", "_istatus": str(getattr(p, "injuryStatus", "ACTIVE")),
        })
        if mlbam and rate is not None:
            mlbam_by_rowid[rid] = int(mlbam)
            rates[p.name] = float(rate)

    # ---- week axis: cap-marginal engine ----
    week_est_fired = False
    if pmeta is not None and probables.starts:
        # FA candidates missing from ctx probables get ONE extra batch fetch
        missing = [mlbam_by_rowid[r["id"]] for r in sp_players
                   if r["owner"] == "FA" and r["id"] in mlbam_by_rowid
                   and mlbam_by_rowid[r["id"]] not in starts_by_pid]
        if missing:
            fetched = {}
            try:
                if starts_fetcher is not None:
                    fetched = starts_fetcher(missing, sched, win_start, win_end)
                else:
                    import build_matchup_dashboard as M   # circularity guard
                    fetched = M.build_sp_starts_by_pitcher(
                        missing, sched, win_start, win_end)
            except Exception as e:
                print(f"[decision_console] FA probables fetch failed "
                      f"({type(e).__name__}: {e})")
            if fetched:
                merged = dict(starts_by_pid)
                merged.update(fetched)
                week_ctx = dict(week_ctx or {})
                week_ctx["sp_starts_by_pitcher"] = merged
                probables, starts_by_pid = _probables_from_ctx(week_ctx)

        base = weekly_sp_projection(
            roster=mine_rps, week_start=win_start, week_end=win_end,
            rp3=rates, probables=probables, cap=eff_cap)
        week_block["scheduled_mine"] = len(base)
        by_pid_counts = {}
        for s in base:
            by_pid_counts.setdefault(s.mlbam_id, []).append(s)
        base_total = _counted_total(base)

        for row in sp_players:
            mlbam = mlbam_by_rowid.get(row["id"])
            if mlbam is None or row["rate"] is None:
                # per-row fallback: WEEK_EST flag on the row only — the header
                # week_est stays a CTX-level signal (banked missing / no
                # probables at all), not "some FA didn't resolve".
                _sp_week_est(row, rem_days, eff_cap)
                continue
            in_window = [g for g in (starts_by_pid.get(mlbam) or [])
                         if _as_date(g.get("date")) is not None
                         and win_start <= _as_date(g["date"]) <= win_end]
            if row["owner"] == "MINE":
                counted = by_pid_counts.get(mlbam, [])
                counted_dates = {s.start_date for s in counted
                                 if s.counts_toward_cap}
                row["xfp_week"] = _r1(sum(s.projected_fp for s in counted
                                          if s.counts_toward_cap))
                row["week_detail"]["starts"] = [
                    {"date": g["date"], "opp": g.get("opp_team", ""),
                     "confirmed": bool(g.get("confirmed")),
                     "counts": _as_date(g["date"]) in counted_dates}
                    for g in in_window]
            else:
                fa_rp = RosterPitcher(name=row["name"], mlbam_id=int(mlbam),
                                      injury_status=row["_istatus"],
                                      position="SP")
                union = weekly_sp_projection(
                    roster=mine_rps + [fa_rp], week_start=win_start,
                    week_end=win_end, rp3=rates, probables=probables,
                    cap=eff_cap)
                row["xfp_week_marginal"] = _r1(
                    _counted_total(union) - base_total)
                row["xfp_week"] = row["xfp_week_marginal"]
                union_counted = {s.start_date for s in union
                                 if s.counts_toward_cap
                                 and s.mlbam_id == int(mlbam)}
                row["week_detail"]["starts"] = [
                    {"date": g["date"], "opp": g.get("opp_team", ""),
                     "confirmed": bool(g.get("confirmed")),
                     "counts": _as_date(g["date"]) in union_counted}
                    for g in in_window]
            if len(in_window) >= 2:
                row["flags"].append("TWO_START")

        # pairwise cap-aware deltas: MINE SP i × top-N FA j
        fa_ranked = sorted(
            (r for r in sp_players
             if r["owner"] == "FA" and r["xfp_week_marginal"] is not None
             and "WEEK_EST" not in r["flags"]),
            key=lambda r: r["xfp_week_marginal"], reverse=True)[:PAIR_TOP_FA]
        pw = {}
        for mrow in (r for r in sp_players if r["owner"] == "MINE"):
            m_id = mlbam_by_rowid.get(mrow["id"])
            if m_id is None:
                continue
            rest = [rp for rp in mine_rps if rp.mlbam_id != m_id]
            for frow in fa_ranked:
                f_id = mlbam_by_rowid.get(frow["id"])
                if f_id is None:
                    continue
                fa_rp = RosterPitcher(name=frow["name"], mlbam_id=int(f_id),
                                      injury_status=frow["_istatus"],
                                      position="SP")
                sim = weekly_sp_projection(
                    roster=rest + [fa_rp], week_start=win_start,
                    week_end=win_end, rp3=rates, probables=probables,
                    cap=eff_cap)
                pw[f"{mrow['id']}|{frow['id']}"] = _r1(
                    _counted_total(sim) - base_total)
        buckets["SP"]["pair_week_deltas"] = pw
    else:
        for row in sp_players:
            _sp_week_est(row, rem_days, eff_cap)
        week_est_fired = True

    if week_block is not None and week_est_fired:
        week_block["week_est"] = True
    buckets["SP"]["players"] = sp_players

    # =========================================================================
    # Hitter buckets
    # =========================================================================
    have = hitter_board[hitter_board["per_game"].notna()].copy()
    mine_all = hitter_board[hitter_board["owner"] == "MINE"]

    hit_rows_by_bucket = {}
    for bkey in ("C", "1B/3B", "2B/SS", "OF", "UTIL"):
        # .astype(bool): an EMPTY apply() mask is object-dtype and pandas would
        # treat it as column-label selection instead of a row filter.
        sub = have[have["buckets"].apply(lambda s: bkey in s).astype(bool)]
        sub_fa = (sub[sub["owner"] == "FA"]
                  .sort_values("xfp_ros", ascending=False)
                  .head(BUCKET_FA_N.get(bkey, 25)))
        sub_mine = mine_all[
            mine_all["buckets"].apply(lambda s: bkey in s).astype(bool)]
        hit_rows_by_bucket[bkey] = pd.concat([sub_mine, sub_fa])

    hit_row_cache = {}   # norm name+owner -> built row (dedupe across buckets)
    for bkey, sub in hit_rows_by_bucket.items():
        out = []
        for _, r in sub.iterrows():
            ck = (B.norm(r["name"]), r["owner"], str(r.get("team", "")))
            if ck in hit_row_cache:
                out.append(hit_row_cache[ck])
                continue
            espn_id, slots, lslot, istatus, _p = _meta_for(r)
            slots = slots or [str(s).upper() for s in (r.get("slots") or [])]
            rid = _row_id(None, espn_id, r["name"])
            flags = []
            src = str(r.get("src", "") or "")
            if src.startswith("talent_prior"):
                flags.append("LOW_CONF")
            if src.endswith("·flat↓"):
                flags.append("DOCKED")
            inj = str(r.get("inj") or "")
            if inj:
                flags.append("IL")
            per_game = r.get("per_game")
            if per_game is None or pd.isna(per_game):
                flags.append("NO_DATA")
            row = {
                "id": rid, "mlbam": None, "espn_id": espn_id,
                "name": str(r["name"]), "owner": str(r["owner"]),
                "team": str(r.get("team", "") or ""),
                "own_pct": _r1(r.get("own")) if r["owner"] == "FA" else None,
                "slots": slots, "rate": _r1(per_game),
                "rate_unit": "per_game", "src": src,
                "xfp_ros": _r1(r.get("xfp_ros")),
                "xfp_po": _r1(r.get("xfp_po")),
                "xfp_week": None, "xfp_week_marginal": None,
                "week_detail": {"starts": None, "games": None},
                "flags": flags, "inj": inj, "ret": _iso(r.get("ret")),
                "extras": {}, "_lslot": lslot, "_istatus": istatus,
            }
            _hitter_week(row, r, team_map, sched, win_start, win_end,
                         rem_days, pmeta)
            hit_row_cache[ck] = row
            out.append(row)
        buckets[bkey]["players"] = out

    # =========================================================================
    # RP bucket
    # =========================================================================
    buckets["RP"]["players"] = _rp_bucket(
        roster, fas, rprs2, role_detector, id_resolver, injury_details,
        dual_sp_norms, today, _meta_for)

    # =========================================================================
    # Recs + headline + sim
    # =========================================================================
    for bkey, _lbl in BUCKET_ORDER:
        pitcher_bucket = bkey in ("SP", "RP")
        strong = PAIR_STRONG_FP if pitcher_bucket else SLOT_STRONG_FP
        modest = PAIR_MODEST_FP if pitcher_bucket else SLOT_MODEST_FP
        buckets[bkey]["recs"] = _bucket_recs(
            bkey, buckets[bkey]["players"],
            buckets[bkey]["pair_week_deltas"], strong, modest)

    headline = {}
    for bkey, _lbl in BUCKET_ORDER:
        for rec in buckets[bkey]["recs"]:
            key = (rec["drop_id"], rec["add_id"])
            if key not in headline or abs(rec["delta_ros"] or 0) > abs(
                    headline[key]["delta_ros"] or 0):
                headline[key] = rec
    headline_recs = sorted(headline.values(),
                           key=lambda r: -(r["delta_ros"] or 0))[:HEADLINE_MAX]

    sim = {"mine_ids": [], "fa_ids_by_bucket": {}}
    seen_mine = set()
    for bkey, _lbl in BUCKET_ORDER:
        fa_ids = []
        for p in buckets[bkey]["players"]:
            if p["owner"] == "MINE":
                if p["id"] not in seen_mine:
                    seen_mine.add(p["id"])
                    sim["mine_ids"].append(p["id"])
            else:
                fa_ids.append(p["id"])
        sim["fa_ids_by_bucket"][bkey] = fa_ids

    # strip private keys
    for bkey, _lbl in BUCKET_ORDER:
        for p in buckets[bkey]["players"]:
            p.pop("_lslot", None)
            p.pop("_istatus", None)

    gen = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": gen,
        "source": source or ((week_ctx or {}).get("source") or "board"),
        "today": _iso(today),
        "season_end": _iso(B.SEASON_END),
        "playoff_start": _iso(B.PLAYOFF_START),
        "note": WEEK_METHOD_NOTE,
        "week": week_block,
        "buckets": [buckets[k] for k, _ in BUCKET_ORDER],
        "headline_recs": headline_recs,
        "sim": sim,
        "thresholds": {"pair_strong": PAIR_STRONG_FP,
                       "pair_modest": PAIR_MODEST_FP,
                       "slot_strong": SLOT_STRONG_FP,
                       "slot_modest": SLOT_MODEST_FP},
    }


# ── per-section helpers ──────────────────────────────────────────────────────
_EXTRA_SP_MAPS = None


def _extra_sp_rate(name):
    """(per_start, src) for a role-corrected dual-eligible arm absent from the
    SP board — rp3 lookup (data_driven preferred, marcel labelled LOW-CONF)."""
    global _EXTRA_SP_MAPS
    if _EXTRA_SP_MAPS is None:
        try:
            import talent_prior as TP
            rp3 = B.PROJECTIONS.rp3().dropna(subset=["player_name"])
            tag = rp3["data_quality_tag"].astype(str)
            dd = rp3[tag.str.startswith("data_driven")]
            mar = rp3[tag.str.contains("marcel")]
            _EXTRA_SP_MAPS = [
                (*B._build_map(dd["player_name"].map(TP.flip_name),
                               dd["xfp_rp3_per_start"]), "rp3_dd"),
                (*B._build_map(mar["player_name"].map(TP.flip_name),
                               mar["xfp_rp3_per_start"]), "talent_prior"),
            ]
        except Exception:
            _EXTRA_SP_MAPS = []
    if not _EXTRA_SP_MAPS:
        return None
    v, src = B._lookup(_EXTRA_SP_MAPS, name)
    return None if v is None else (float(v), src)


def _sp_week_est(row, rem_days, eff_cap):
    """Flat-rate week estimate for an SP with no usable probables read."""
    if row["rate"] is None:
        return
    est = float(row["rate"]) * B.RATE * rem_days
    if row["owner"] == "MINE":
        row["xfp_week"] = _r1(est)
    else:
        row["xfp_week_marginal"] = _r1(est if (eff_cap is None or eff_cap > 0)
                                       else 0.0)
        row["xfp_week"] = row["xfp_week_marginal"]
    if "WEEK_EST" not in row["flags"]:
        row["flags"].append("WEEK_EST")


def _hitter_week(row, board_row, team_map, sched, win_start, win_end,
                 rem_days, pmeta):
    """Fill xfp_week + week_detail.games for a hitter row (server-side)."""
    if row["rate"] is None:
        return
    per_game = float(row["rate"])
    ret_d = _as_date(board_row.get("ret"))
    if pmeta is not None and sched and team_map:
        tid = team_map.get(str(row["team"]).upper())
        games = sched.get(tid) or []
        eff_start = win_start if ret_d is None else max(win_start, ret_d)
        if ret_d is not None and ret_d > win_end:
            row["xfp_week"] = 0.0
            row["week_detail"]["games"] = 0
            return
        n = sum(1 for g in games
                if (_as_date(g.get("date")) is not None
                    and eff_start <= _as_date(g["date"]) <= win_end))
        if games:
            row["xfp_week"] = _r1(per_game * n)
            row["week_detail"]["games"] = n
            return
    # est fallback (no schedule for this team / no ctx)
    if ret_d is not None and win_end is not None and ret_d > win_end:
        row["xfp_week"] = 0.0
        row["week_detail"]["games"] = 0
        return
    row["xfp_week"] = _r1(per_game * B.GPW / 7.0 * rem_days)
    row["week_detail"]["games"] = None
    if "WEEK_EST" not in row["flags"]:
        row["flags"].append("WEEK_EST")


def _load_rprs2(rprs2):
    if rprs2 is not None:
        return rprs2
    try:
        return pd.read_csv(RPRS2_CSV)
    except Exception as e:
        print(f"[decision_console] rprs2 unavailable "
              f"({type(e).__name__}: {e}) — RP bucket empty")
        return pd.DataFrame(columns=["pitcher", "name_api", "xfp_ros",
                                     "role_lag1", "sv_2026", "hld_2026",
                                     "signal"])


def _rp_bucket(roster, fas, rprs2, role_detector, id_resolver, injury_details,
               dual_sp_norms, today, _meta_for):
    """RP rows: rprs2-ranked (NEVER rp3), availability-scaled totals.

    rprs2 `xfp_ros` is already a rest-of-season TOTAL, so IL scaling is a
    day-ratio: total × avail_days/remaining_days — algebraically identical to
    (per-appearance rate) × (availability-scaled appearance count) under the
    uniform-appearance assumption."""
    df = _load_rprs2(rprs2)
    by_mlbam = {}
    if len(df):
        d = df.dropna(subset=["pitcher"])
        by_mlbam = {int(r["pitcher"]): r for _, r in d.iterrows()}
    norm_counts = {}
    for _, r in df.iterrows():
        nn = B.norm(str(r.get("name_api", "")))
        norm_counts[nn] = norm_counts.get(nn, 0) + 1
    by_norm = {B.norm(str(r.get("name_api", ""))): r for _, r in df.iterrows()
               if norm_counts.get(B.norm(str(r.get("name_api", "")))) == 1}
    injury_details = injury_details or {}

    remaining = max(1, (B.SEASON_END - today).days)

    def _axes(xfp_ros_total, avail):
        avail_days = max(0, (B.SEASON_END - avail).days)
        po_days = max(0, (B.SEASON_END - max(avail, B.PLAYOFF_START)).days)
        return (_r1(xfp_ros_total * avail_days / remaining),
                _r1(xfp_ros_total * po_days / remaining))

    def _join(name, team):
        pid = id_resolver(name, team=team, role="RP")
        if pid and int(pid) in by_mlbam:
            return int(pid), by_mlbam[int(pid)]
        r = by_norm.get(B.norm(name))
        if r is not None:
            return (int(r["pitcher"]) if pd.notna(r.get("pitcher")) else None), r
        return (int(pid) if pid else None), None

    rows = []

    # MINE
    if roster is not None and len(roster):
        mine = roster[roster["position"].isin(["RP", "P"])]
        for _, p in mine.iterrows():
            nm = p["player_name"]
            try:
                if role_detector(p) != "RP":
                    continue
            except Exception:
                pass
            mlbam, rr = _join(nm, p.get("pro_team"))
            injured = bool(p.get("injured"))
            istatus = str(p.get("injury_status", "") or "ACTIVE")
            ret = _as_date(p.get("return_date")) if injured else None
            avail = max(today, ret) if ret else today
            flags = []
            if injured:
                flags.append("IL")
            if rr is None:
                flags.append("NO_DATA")
                xros = xpo = raw = None
            else:
                raw = float(rr["xfp_ros"])
                xros, xpo = _axes(raw, avail)
            rows.append(_rp_row(
                nm, "MINE", str(p.get("pro_team", "") or ""), None,
                int(p.get("player_id") or 0) or None, mlbam, raw, xros, xpo,
                flags, istatus if injured else "", ret, rr))

    # FA
    for p in fas or []:
        elig = _elig_set(p)
        if "RP" not in elig:
            continue
        if B.norm(p.name) in dual_sp_norms:
            continue                      # Detmers class: real role is SP
        if {"SP", "RP"} <= elig:
            try:
                if role_detector(p) != "RP":
                    continue
            except Exception:
                continue
        mlbam, rr = _join(p.name, getattr(p, "proTeam", None))
        if rr is None:
            continue                      # FA RPs without rprs2: noise control
        injured = bool(getattr(p, "injured", False))
        istatus = str(getattr(p, "injuryStatus", "ACTIVE") or "ACTIVE")
        ret = None
        if injured:
            ret = injury_details.get(int(p.playerId))
            if ret is None:
                ret = today + timedelta(days=B.HEUR.get(istatus, 21))
        avail = max(today, ret) if ret else today
        flags = ["IL"] if injured else []
        raw = float(rr["xfp_ros"])
        xros, xpo = _axes(raw, avail)
        rows.append(_rp_row(
            p.name, "FA", str(getattr(p, "proTeam", "") or ""),
            _r1(getattr(p, "percent_owned", None)), int(p.playerId), mlbam,
            raw, xros, xpo, flags, istatus if injured else "", ret, rr))

    rows.sort(key=lambda r: -(r["xfp_ros"] if r["xfp_ros"] is not None
                              else -1e9))
    fa_rows = [r for r in rows if r["owner"] == "FA"][:RP_FA_N]
    mine_rows = [r for r in rows if r["owner"] == "MINE"]
    out = sorted(mine_rows + fa_rows,
                 key=lambda r: -(r["xfp_ros"] if r["xfp_ros"] is not None
                                 else -1e9))
    return out


def _rp_row(name, owner, team, own_pct, espn_id, mlbam, raw, xros, xpo,
            flags, inj, ret, rr):
    extras = {}
    if rr is not None:
        extras = {"role_lag1": str(rr.get("role_lag1", "") or ""),
                  "sv_2026": None if pd.isna(rr.get("sv_2026")) else int(rr["sv_2026"]),
                  "hld_2026": None if pd.isna(rr.get("hld_2026")) else int(rr["hld_2026"]),
                  "signal": str(rr.get("signal", "") or "")}
    return {
        "id": _row_id(mlbam, espn_id, name), "mlbam": mlbam,
        "espn_id": espn_id, "name": name, "owner": owner, "team": team,
        "own_pct": own_pct if owner == "FA" else None,
        "slots": ["RP"], "rate": _r1(raw), "rate_unit": "rprs2_ros",
        "src": "rprs2", "xfp_ros": xros, "xfp_po": xpo,
        "xfp_week": None, "xfp_week_marginal": None,
        "week_detail": {"starts": None, "games": None},
        "flags": flags, "inj": inj, "ret": _iso(ret) if ret else "",
        "extras": extras, "_lslot": "", "_istatus": inj or "ACTIVE",
    }


def _bucket_recs(bkey, players, pair_week_deltas, strong, modest):
    """Within-bucket greedy pairing: worst-N droppable MINE × best clean FA.
    LOW-CONF / IL / NO_DATA FAs never appear in recs (they stay in tables)."""
    mine = [p for p in players
            if p["owner"] == "MINE" and p["xfp_ros"] is not None
            and str(p.get("_lslot", "")).upper() not in IL_LINEUP_SLOTS]
    mine.sort(key=lambda p: p["xfp_ros"])
    fa = [p for p in players
          if p["owner"] == "FA" and p["xfp_ros"] is not None
          and not ({"LOW_CONF", "IL", "NO_DATA"} & set(p["flags"]))]
    fa.sort(key=lambda p: -p["xfp_ros"])

    recs, used = [], set()
    for d in mine[:REC_WORST_N]:
        for a in fa:
            if a["id"] in used:
                continue
            if bkey not in ("SP", "RP") and not (set(d["slots"]) & set(a["slots"])):
                continue
            delta_ros = _r1((a["xfp_ros"] or 0) - (d["xfp_ros"] or 0))
            if delta_ros is None or delta_ros <= modest:
                continue
            delta_po = (None if a["xfp_po"] is None or d["xfp_po"] is None
                        else _r1(a["xfp_po"] - d["xfp_po"]))
            pw_key = f"{d['id']}|{a['id']}"
            if pw_key in pair_week_deltas:
                delta_week = pair_week_deltas[pw_key]
            elif a["xfp_week"] is not None and d["xfp_week"] is not None:
                delta_week = _r1(a["xfp_week"] - d["xfp_week"])
            else:
                delta_week = None
            recs.append({
                "drop_id": d["id"], "add_id": a["id"], "bucket": bkey,
                "delta_ros": delta_ros, "delta_week": delta_week,
                "delta_po": delta_po,
                "verdict": _verdict(delta_ros, strong, modest),
                "why": (f"{bkey} slot-compatible; FA modeled (not LOW-CONF); "
                        f"ΔRoS {delta_ros:+.0f}"),
            })
            used.add(a["id"])
            break
    return recs


# ═════════════════════════════════════════════════════════════════════════════
# RENDERER — display-only. All numbers come precomputed from the payload; the
# embedded JS is limited to dict lookup, sort comparison, subtracting two
# payload numbers for display, and sign→CSS class (the module's design law).
# ═════════════════════════════════════════════════════════════════════════════
from html import escape as _h

# matchup.html and xfp_board.html share the warm-dark palette; the theme param
# stays so a future host page can diverge without touching call sites.
_THEMES = {
    "board":   {"bg": "#1a1815", "panel": "#211e1a", "stripe": "#1d1b17",
                "border": "#34302a", "text": "#f5f1ea", "dim": "#a89e8a",
                "accent": "#d97757", "pos": "#7fb069", "neg": "#c1666b",
                "warn": "#d4a945", "mine": "#2a3320"},
}
_THEMES["matchup"] = _THEMES["board"]

_FLAG_LABELS = {"LOW_CONF": "LOW-CONF", "IL": "IL", "WEEK_EST": "wk-est",
                "DOCKED": "flat↓", "TWO_START": "2-START", "NO_DATA": "no data",
                "ROLE_SP": "role:SP"}

_AXES = [("ros", "RoS"), ("week", "Week"), ("po", "Playoffs")]


def _fmtv(v):
    return "—" if v is None else f"{v:g}"


def _flags_html(flags):
    return "".join(
        f'<span class="dc-flag dc-flag-{f.lower()}">{_h(_FLAG_LABELS.get(f, f))}</span>'
        for f in flags)


def _val_cell(p):
    week = p["xfp_week"]
    attrs = " ".join(
        f'data-{ax}="{"" if v is None else v}"'
        for ax, v in (("ros", p["xfp_ros"]), ("week", week), ("po", p["xfp_po"])))
    spans = "".join(
        f'<span class="v v-{ax}">{_fmtv(v)}</span>'
        for ax, v in (("ros", p["xfp_ros"]), ("week", week), ("po", p["xfp_po"])))
    return f'<td class="dc-val" {attrs}>{spans}</td>'


def _bucket_table(b):
    rows = []
    for p in b["players"]:
        cls = "dc-mine" if p["owner"] == "MINE" else ""
        own = "MINE" if p["owner"] == "MINE" else (
            f'{p["own_pct"]:g}%' if p["own_pct"] is not None else "FA")
        ret = f' <span class="dc-ret">{_h(p["ret"])}</span>' if p["ret"] else ""
        rows.append(
            f'<tr class="{cls}" data-id="{_h(p["id"])}">'
            f'<td class="dc-name">{_h(p["name"])}{_flags_html(p["flags"])}{ret}</td>'
            f'<td class="dc-dim">{_h(own)}</td>'
            f'<td class="dc-dim">{_h(p["team"])}</td>'
            f'<td class="dc-dim">{_h("/".join(p["slots"]))}</td>'
            f'<td data-rate="{"" if p["rate"] is None else p["rate"]}">'
            f'{_fmtv(p["rate"])}</td>'
            f'{_val_cell(p)}</tr>')
    week_head = ('<th class="dc-sort" data-col="val">xFP '
                 '<span class="v v-ros">RoS</span><span class="v v-week">Week'
                 '</span><span class="v v-po">PO</span> ↕</th>')
    if not b["axis_support"]["week"]:
        week_head = week_head.replace('<span class="v v-week">Week</span>',
                                      '<span class="v v-week">Week —</span>')
    return (
        f'<table class="dc-table"><thead><tr>'
        f'<th>Player</th><th>Own</th><th>Team</th><th>Slots</th>'
        f'<th class="dc-sort" data-col="rate">Rate ↕</th>{week_head}'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _recs_table(data, name_of):
    if not data["headline_recs"]:
        return ('<p class="dc-dim dc-norecs">No swap clears the verdict '
                'threshold right now — the FA pool offers no upgrade over '
                'your worst droppable starters.</p>')
    rows = []
    for r in data["headline_recs"]:
        def _d(v):
            if v is None:
                return '<td class="dc-dim">—</td>'
            cls = "dc-pos" if v > 0 else ("dc-neg" if v < 0 else "dc-dim")
            return f'<td class="{cls}">{v:+g}</td>'
        rows.append(
            f'<tr><td class="dc-name">{_h(name_of(r["drop_id"]))}</td>'
            f'<td class="dc-name">{_h(name_of(r["add_id"]))}</td>'
            f'<td class="dc-dim">{_h(r["bucket"])}</td>'
            f'{_d(r["delta_ros"])}{_d(r["delta_week"])}{_d(r["delta_po"])}'
            f'<td><span class="dc-verdict dc-verdict-{r["verdict"].lower()}">'
            f'{_h(r["verdict"])}</span></td></tr>')
    return (
        '<table class="dc-table"><thead><tr>'
        '<th>Drop</th><th>Add</th><th>Bucket</th><th>ΔRoS</th><th>ΔWeek</th>'
        '<th>ΔPO</th><th>Verdict</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')


def _cap_line(data):
    wk = data["week"]
    if wk is None:
        return ('<div class="dc-cap dc-est">Week axis is <b>estimated</b> '
                '(no period/schedule context this build) — flat league rates, '
                'no cap awareness.</div>')
    banked = "?" if wk["banked_mine"] is None else wk["banked_mine"]
    room = "?" if wk["cap_room"] is None else wk["cap_room"]
    est = (' <span class="dc-flag dc-flag-week_est">estimates in play</span>'
           if wk["week_est"] else "")
    return (
        f'<div class="dc-cap">Period <b>{wk["period"]}</b> '
        f'({_h(wk["week_start"])} → {_h(wk["week_end"])}, {wk["weeks"]}-wk) · '
        f'SP cap <b>{wk["sp_cap"]}</b> · banked <b>{banked}</b> · '
        f'scheduled <b>{wk["scheduled_mine"]}</b> · cap room <b>{room}</b>'
        f'{est}</div>')


def _sim_selects(data, name_of):
    mine_opts = "".join(
        f'<option value="{_h(pid)}">{_h(name_of(pid))}</option>'
        for pid in data["sim"]["mine_ids"])
    fa_groups = []
    for b in data["buckets"]:
        ids = data["sim"]["fa_ids_by_bucket"].get(b["key"], [])
        if not ids:
            continue
        opts = "".join(f'<option value="{_h(pid)}">{_h(name_of(pid))}</option>'
                       for pid in ids)
        fa_groups.append(f'<optgroup label="{_h(b["label"])}">{opts}</optgroup>')
    return (
        '<div class="dc-sim"><h4>Swap simulator</h4>'
        '<label>Drop (mine) <select class="dc-sim-mine">'
        f'<option value="">—</option>{mine_opts}</select></label>'
        '<label>Add (FA) <select class="dc-sim-fa">'
        f'<option value="">—</option>{"".join(fa_groups)}</select></label>'
        '<div class="dc-sim-out dc-dim">Pick a drop and an add to simulate '
        'the swap on all three axes.</div></div>')


def _console_css(theme):
    t = _THEMES.get(theme, _THEMES["board"])
    v = "".join(f"--dc-{k}:{val};" for k, val in t.items())
    return f"""
.dc {{ {v} background:var(--dc-panel); border:1px solid var(--dc-border);
  border-radius:8px; padding:1em 1.2em 1.2em; margin:1.2em 0;
  color:var(--dc-text); font-size:.95em; }}
.dc h3.dc-title {{ margin:0; color:var(--dc-accent); font-size:1.15em; }}
.dc .dc-gen {{ color:var(--dc-dim); font-size:.78em;
  font-family:'IBM Plex Mono',ui-monospace,monospace; }}
.dc .dc-head {{ display:flex; flex-wrap:wrap; gap:.8em; align-items:baseline;
  justify-content:space-between; margin-bottom:.6em; }}
.dc .dc-axes button, .dc .dc-tabs button {{ background:var(--dc-stripe);
  color:var(--dc-dim); border:1px solid var(--dc-border); border-radius:4px;
  padding:.25em .8em; cursor:pointer; font:inherit; font-size:.85em; }}
.dc .dc-axes button.on, .dc .dc-tabs button.on {{ color:var(--dc-text);
  border-color:var(--dc-accent); background:var(--dc-panel); }}
.dc .dc-cap {{ font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:.82em; color:var(--dc-dim); border:1px dashed var(--dc-border);
  border-radius:4px; padding:.45em .7em; margin:.5em 0 .8em; }}
.dc .dc-cap b {{ color:var(--dc-text); }}
.dc .dc-cap.dc-est {{ color:var(--dc-warn); }}
.dc h4 {{ margin:.9em 0 .35em; color:var(--dc-accent); font-size:.95em;
  font-family:'IBM Plex Mono',ui-monospace,monospace; letter-spacing:.04em; }}
.dc .dc-table {{ border-collapse:collapse; width:100%;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.8em; }}
.dc .dc-table th {{ background:var(--dc-stripe); color:var(--dc-dim);
  text-align:left; padding:.4em .6em; border-bottom:1px solid var(--dc-border);
  font-weight:600; font-size:.85em; text-transform:uppercase;
  letter-spacing:.06em; }}
.dc .dc-table th.dc-sort {{ cursor:pointer; }}
.dc .dc-table td {{ padding:.35em .6em;
  border-bottom:1px solid var(--dc-border); font-variant-numeric:tabular-nums; }}
.dc .dc-table tbody tr:nth-child(even) td {{ background:var(--dc-stripe); }}
.dc .dc-table tbody tr.dc-mine td {{ background:var(--dc-mine); }}
.dc .dc-name {{ color:var(--dc-text); }}
.dc .dc-dim {{ color:var(--dc-dim); }}
.dc .dc-pos {{ color:var(--dc-pos); font-weight:600; }}
.dc .dc-neg {{ color:var(--dc-neg); font-weight:600; }}
.dc .dc-ret {{ color:var(--dc-warn); font-size:.85em; }}
.dc .dc-flag {{ display:inline-block; margin-left:.45em; padding:0 4px;
  border-radius:2px; font-size:.72em; letter-spacing:.03em;
  background:rgba(212,169,69,.18); color:var(--dc-warn); }}
.dc .dc-flag-two_start {{ background:rgba(127,176,105,.18);
  color:var(--dc-pos); }}
.dc .dc-flag-il {{ background:rgba(193,102,107,.18); color:var(--dc-neg); }}
.dc .dc-verdict {{ padding:.1em .5em; border-radius:3px; font-size:.78em;
  font-weight:600; }}
.dc .dc-verdict-strong {{ background:rgba(127,176,105,.2);
  color:var(--dc-pos); }}
.dc .dc-verdict-modest {{ background:rgba(212,169,69,.2);
  color:var(--dc-warn); }}
.dc .dc-verdict-marginal {{ background:var(--dc-stripe); color:var(--dc-dim); }}
.dc .v {{ display:none; }}
.dc[data-axis="ros"] .v-ros {{ display:inline; }}
.dc[data-axis="week"] .v-week {{ display:inline; }}
.dc[data-axis="po"] .v-po {{ display:inline; }}
.dc .dc-bucket {{ display:none; }}
.dc .dc-bucket.on {{ display:block; }}
.dc .dc-note {{ color:var(--dc-dim); font-size:.78em; margin-top:.6em; }}
.dc .dc-sim {{ border-top:1px solid var(--dc-border); margin-top:1em;
  padding-top:.6em; }}
.dc .dc-sim label {{ margin-right:1.2em; color:var(--dc-dim);
  font-size:.85em; }}
.dc .dc-sim select {{ background:var(--dc-stripe); color:var(--dc-text);
  border:1px solid var(--dc-border); border-radius:4px; padding:.2em .4em;
  font:inherit; font-size:.9em; max-width:16em; }}
.dc .dc-sim-out {{ margin-top:.55em;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.85em; }}
"""


_CONSOLE_JS = r"""
(function () {
  var root = document.getElementById('dc-__PK__');
  if (!root) return;
  var D = window.__DC_DATA___PK__;
  var idx = {};
  D.buckets.forEach(function (b) {
    b.players.forEach(function (p) { if (!idx[p.id]) idx[p.id] = p; });
  });
  var spBucket = null, spIds = {};
  D.buckets.forEach(function (b) {
    if (b.key === 'SP') {
      spBucket = b;
      b.players.forEach(function (p) { spIds[p.id] = true; });
    }
  });

  function fmt(v) { return v === null || v === undefined || v === '' ? '—' : v; }
  function cls(v) { return v > 0 ? 'dc-pos' : (v < 0 ? 'dc-neg' : 'dc-dim'); }

  root.addEventListener('click', function (ev) {
    var ax = ev.target.closest('.dc-axes button');
    if (ax) {
      root.dataset.axis = ax.dataset.axis;
      root.querySelectorAll('.dc-axes button').forEach(function (b) {
        b.classList.toggle('on', b === ax);
      });
      return;
    }
    var tab = ev.target.closest('.dc-tabs button');
    if (tab) {
      root.querySelectorAll('.dc-tabs button').forEach(function (b) {
        b.classList.toggle('on', b === tab);
      });
      root.querySelectorAll('.dc-bucket').forEach(function (d) {
        d.classList.toggle('on', d.dataset.bucket === tab.dataset.bucket);
      });
      return;
    }
    var th = ev.target.closest('th.dc-sort');
    if (th) {
      var table = th.closest('table');
      var tbody = table.querySelector('tbody');
      var attr = th.dataset.col === 'rate' ? 'rate' : root.dataset.axis;
      var sel = th.dataset.col === 'rate' ? '[data-rate]' : '.dc-val';
      var dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
      th.dataset.dir = dir;
      var rows = Array.prototype.slice.call(tbody.rows);
      rows.sort(function (a, b) {
        var av = parseFloat(a.querySelector(sel).dataset[attr]);
        var bv = parseFloat(b.querySelector(sel).dataset[attr]);
        if (isNaN(av)) av = -Infinity;
        if (isNaN(bv)) bv = -Infinity;
        return dir === 'asc' ? av - bv : bv - av;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    }
  });

  var mineSel = root.querySelector('.dc-sim-mine');
  var faSel = root.querySelector('.dc-sim-fa');
  var out = root.querySelector('.dc-sim-out');
  function runSim() {
    var m = idx[mineSel.value], f = idx[faSel.value];
    if (!m || !f) {
      out.className = 'dc-sim-out dc-dim';
      out.textContent = 'Pick a drop and an add to simulate the swap on all three axes.';
      return;
    }
    var shared = m.slots.filter(function (s) { return f.slots.indexOf(s) >= 0; });
    var parts = [];
    ['ros', 'po'].forEach(function (ax) {
      var a = f['xfp_' + ax], b = m['xfp_' + ax];
      var lbl = ax === 'ros' ? 'ΔRoS' : 'ΔPO';
      if (a === null || b === null) { parts.push(lbl + ' —'); return; }
      var d = Math.round((a - b) * 10) / 10;
      parts.push('<span class="' + cls(d) + '">' + lbl + ' ' +
                 (d > 0 ? '+' : '') + d + '</span>');
    });
    var wtxt = 'ΔWeek —', approx = '';
    if (spBucket && spIds[m.id] && spIds[f.id]) {
      var pw = spBucket.pair_week_deltas[m.id + '|' + f.id];
      if (pw !== undefined && pw !== null) {
        wtxt = '<span class="' + cls(pw) + '">ΔWeek ' + (pw > 0 ? '+' : '') + pw + '</span>';
      } else if (f.xfp_week !== null && m.xfp_week !== null) {
        var dw = Math.round((f.xfp_week - m.xfp_week) * 10) / 10;
        wtxt = '<span class="' + cls(dw) + '">ΔWeek ' + (dw > 0 ? '+' : '') + dw + '</span>';
        approx = ' <span class="dc-flag">≈ cap-approx</span>';
      }
    } else if (f.xfp_week !== null && m.xfp_week !== null) {
      var dh = Math.round((f.xfp_week - m.xfp_week) * 10) / 10;
      wtxt = '<span class="' + cls(dh) + '">ΔWeek ' + (dh > 0 ? '+' : '') + dh + '</span>';
    }
    parts.splice(1, 0, wtxt + approx);
    var warn = [];
    if (!shared.length) {
      warn.push('no shared slot — cross-position move needs a matching open slot');
    }
    ['LOW_CONF', 'IL', 'WEEK_EST'].forEach(function (fl) {
      if (f.flags.indexOf(fl) >= 0) warn.push('add is ' + fl);
    });
    var caps = '';
    if (spIds[f.id] && f.week_detail && f.week_detail.starts) {
      var c = f.week_detail.starts.filter(function (s) { return s.counts; }).length;
      caps = ' · adds ' + c + ' countable start' + (c === 1 ? '' : 's') + ' this period';
    }
    out.className = 'dc-sim-out';
    out.innerHTML = 'Drop <b>' + m.name + '</b> → add <b>' + f.name + '</b>: ' +
      parts.join(' · ') + caps +
      (warn.length ? ' <span class="dc-ret">⚠ ' + warn.join('; ') + '</span>' : '');
  }
  mineSel.addEventListener('change', runSim);
  faSel.addEventListener('change', runSim);
})();
"""


def render_console_html(data, *, theme: str = "board", page_key: str,
                        default_axis: str = "ros") -> str:
    """Self-contained console block (scoped CSS + vanilla display-only JS).
    Safe to interpolate into an f-string host page; when a host uses
    str.format, pass this block as a format ARGUMENT (its braces are then
    never re-parsed)."""
    names = {}
    for b in data["buckets"]:
        for p in b["players"]:
            names.setdefault(p["id"], p["name"])

    def name_of(pid):
        return names.get(pid, pid)

    axes_btns = "".join(
        f'<button data-axis="{ax}" class="{"on" if ax == default_axis else ""}"'
        f'>{lbl}</button>' for ax, lbl in _AXES)
    tab_btns = "".join(
        f'<button data-bucket="{_h(b["key"])}" '
        f'class="{"on" if i == 0 else ""}">{_h(b["key"])}</button>'
        for i, b in enumerate(data["buckets"]))
    bucket_divs = "".join(
        f'<div class="dc-bucket {"on" if i == 0 else ""}" '
        f'data-bucket="{_h(b["key"])}">'
        + (f'<p class="dc-note">{_h(b["note"])}</p>' if b["note"] else "")
        + _bucket_table(b) + "</div>"
        for i, b in enumerate(data["buckets"]))

    payload = json.dumps(data).replace("</", "<\\/")
    js = _CONSOLE_JS.replace("__PK__", page_key)
    gen = _h(str(data["generated_at"]))

    return f"""<section class="dc" id="dc-{_h(page_key)}" data-axis="{_h(default_axis)}">
<style>{_console_css(theme)}</style>
<div class="dc-head">
  <div><h3 class="dc-title">🧭 Decision Console — My Team vs FA</h3>
  <div class="dc-gen">generated {gen} · source {_h(str(data["source"]))}</div></div>
  <div class="dc-axes">{axes_btns}</div>
</div>
{_cap_line(data)}
<h4>Top swap recommendations</h4>
{_recs_table(data, name_of)}
<h4>Position boards</h4>
<div class="dc-tabs">{tab_btns}</div>
{bucket_divs}
{_sim_selects(data, name_of)}
<p class="dc-note">{_h(data["note"])}. LOW-CONF / IL FAs never appear in
recommendations but stay visible in the tables. MINE rows are always shown,
even below the FA display cut.</p>
<script>window.__DC_DATA_{page_key} = {payload};{js}</script>
</section>"""


# ── CLI (standalone payload writer — refresh step 4.52 fallback) ────────────
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Build console_data.json")
    ap.add_argument("--out", default=str(ROOT / "data/outputs/console_data.json"))
    ap.add_argument("--if-stale", action="store_true",
                    help="skip when the existing payload is from today")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if args.if_stale and out.exists():
        try:
            cur = json.loads(out.read_text(encoding="utf-8"))
            gen = str(cur.get("generated_at", ""))[:10]
            if (cur.get("schema_version") == SCHEMA_VERSION
                    and gen == date.today().isoformat()):
                print(f"console_data.json fresh ({gen}) — skipped")
                return 0
        except Exception:
            pass
    inputs = B.fetch_board_inputs()
    data = build_console_data(
        roster=inputs["roster"], fas=inputs["fas"], league=inputs["league"],
        injury_details=inputs["injury_details"],
        my_team_id=inputs["my_team_id"], source="board")
    out.write_text(json.dumps(data), encoding="utf-8")
    print(f"wrote {out} ({len(json.dumps(data))//1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
