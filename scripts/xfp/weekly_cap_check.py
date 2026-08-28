"""weekly_cap_check.py — Monday SP-start cap planner.

Projects your rostered starters' starts in the CURRENT scoring period against
the period SP-start cap, subtracts starts already banked this period (ESPN
statId-33), and — when you're over the cap — names exactly which start(s) to
bench (the lowest projected-FP ones, which would otherwise score zero past the
cap).

Cap is period-aware (10 standard week / 16 ASG block / 20 two-week playoff) via
``resolve_current_period_meta``; never hardcoded. Bench = active for scoring, so
only IL slots / injury statuses zero a starter. Projected starts come from
confirmed MLB probables where posted, filled out by each arm's recent rotation
cadence for the back half of the week.

Run:  python scripts/xfp/weekly_cap_check.py
      python scripts/xfp/weekly_cap_check.py --date 2026-07-20   # plan a future Monday
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata

# Windows cp1252 console guard — header prints —/→/· etc. (item 23)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from plv_clone.league_state import LeagueState                       # noqa: E402
from lib.period_meta import resolve_current_period_meta, espn_period_meta  # noqa: E402
from lib.pitcher_role import detect_pitcher_role                     # noqa: E402
from lib.bucket_dispatch import _flip_lastfirst as _flip             # noqa: E402  shared 'Last, First' flip (audit item 9)

MLB = "https://statsapi.mlb.com/api/v1"
OUT = ROOT / "data" / "outputs"
IL_STATES = {"FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "TEN_DAY_DL", "SEVEN_DAY_DL", "OUT"}
IL_SLOTS = {"IL", "IL10", "IL15", "IL60", "IR"}
DEFAULT_CADENCE = 5


# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402
from plv_clone.fantasy.scoring import parse_ip as _canon_parse_ip  # noqa: E402


def _get(url, params=None):
    for _ in range(3):
        try:
            return requests.get(url, params=params, timeout=20).json()
        except Exception:
            pass
    return {}


def _per_start_map() -> dict:
    """mlbam -> (per_start value, source tag). Stuff+ handled implicitly via
    rp3's own source tiering; talent_prior rows flagged LOW-CONF."""
    rp3 = pd.read_csv(OUT / "xfp_rp3_projections.csv")
    m = {}
    for r in rp3.itertuples():
        m[int(r.pitcher)] = (round(float(r.xfp_rp3_per_start), 2), str(r.data_quality_tag))
    return m


def _name_to_mlbam() -> dict:
    rp3 = pd.read_csv(OUT / "xfp_rp3_projections.csv")
    return {_norm(_flip(n)): int(p) for n, p in zip(rp3["player_name"], rp3["pitcher"])}


def _ip_float(s) -> float:
    # Delegates to the ONE canonical parser (issue #78). Fifteen private
    # copies of this logic is how two of them drifted (PR #77).
    return _canon_parse_ip(s, default=0.0)


def _arm_form(mlbam: int):
    """(last start date, recent cadence days, L5 start FP avg) from the game log.
    L5 lets us de-stale rp3 for role-change arms (an opener-turned-starter whose
    season rp3 lags his real recent starts)."""
    gl = _get(f"{MLB}/people/{mlbam}/stats",
              {"stats": "gameLog", "group": "pitching", "season": 2026})
    try:
        splits = gl["stats"][0]["splits"]
    except Exception:
        return None, DEFAULT_CADENCE, None
    dts, fps = [], []
    for s in splits:
        st = s["stat"]
        if int(st.get("gamesStarted", 0)) < 1:
            continue
        dts.append(date.fromisoformat(s["date"]))
        ip = _ip_float(st.get("inningsPitched"))
        fps.append(int(st.get("strikeOuts", 0)) + ip * 3.3 - int(st.get("hits", 0))
                   - 2 * int(st.get("earnedRuns", 0)) - int(st.get("baseOnBalls", 0))
                   - int(st.get("hitByPitch", 0)))
    if not dts:
        return None, DEFAULT_CADENCE, None
    if len(dts) >= 4:
        gaps = [(dts[i] - dts[i - 1]).days for i in range(-3, 0)]
        cad = max(4, min(round(sum(gaps) / len(gaps)), 7))
    else:
        cad = DEFAULT_CADENCE
    l5 = round(sum(fps[-5:]) / len(fps[-5:]), 2) if fps else None
    return dts[-1], cad, l5


def _proj_val(rp3_val, l5):
    """Bench-ranking value: blend rp3 with recent L5 so a stale/opener-dragged
    rp3 can't mis-bench a hot arm (the Jax case). Median of the two when both
    exist; else whichever is present."""
    xs = [x for x in (rp3_val, l5) if x is not None]
    if not xs:
        return 0.0
    return round(sorted(xs)[len(xs) // 2] if len(xs) % 2 else sum(xs) / 2, 2)


def _window_schedule(mlbams: set, start: date, end: date):
    """One pass over the window → (confirmed probables {mlbam:[date]}, set of
    days with MLB games). Reused for both confirmed starts and cadence sliding,
    so we hit the schedule endpoint once per day, not once per pitcher-day."""
    confirmed: dict[int, list] = {}
    game_days: set[date] = set()
    d = start
    while d <= end:
        sched = _get(f"{MLB}/schedule",
                     {"sportId": 1, "date": d.isoformat(), "hydrate": "probablePitcher"})
        if sched.get("totalGames", 0):
            game_days.add(d)
        for dd in sched.get("dates", []):
            for g in dd.get("games", []):
                for side in ("home", "away"):
                    pp = g["teams"][side].get("probablePitcher")
                    if pp and pp["id"] in mlbams:
                        confirmed.setdefault(pp["id"], []).append(d)
        d += timedelta(days=1)
    return confirmed, game_days


def _project_starts(mlbam, last, cad, confirmed, game_days, win_start, win_end):
    """Confirmed probables in-window, else roll the rotation forward by cadence,
    sliding off any dead day (All-Star break / off-day) to the next game day so a
    start is never dropped just because its slot lands on a no-game date."""
    if mlbam in confirmed:
        return sorted(d for d in confirmed[mlbam] if win_start <= d <= win_end)
    if last is None:
        return []
    out, d = [], last + timedelta(days=cad)
    while d <= win_end:
        slid = d
        while slid <= win_end and slid not in game_days:
            slid += timedelta(days=1)     # dead day → next game day
        if slid > win_end:
            break
        if slid >= win_start:
            out.append(slid)
        d = slid + timedelta(days=cad)     # next turn measured from the actual start
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="as-of date YYYY-MM-DD (default: today)")
    ap.add_argument("--period", type=int, default=None,
                    help="explicit matchup period (QA 2026-07-20: on rollover "
                         "mornings ESPN's currentMatchupPeriod lags and the "
                         "default resolves the CLOSED period — pass the new "
                         "period number to plan the week that just started)")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now().date()

    ls = LeagueState()
    lg = ls._get_league()
    me = ls._find_my_team()
    myteam = next(t for t in lg.teams if t.team_name == me.team_name)

    if args.period is not None:
        from lib.period_meta import resolve_period_meta
        pm = resolve_period_meta(lg, args.period)
    else:
        pm = resolve_current_period_meta(lg, today=today)
        # rollover tripwire: if the resolved window ENDED before today, ESPN's
        # currentMatchupPeriod is lagging — say so instead of a moot verdict
        try:
            if date.fromisoformat(str(pm["week_end"])) < today:
                print(f"  !! period {pm['period']} window ended "
                      f"{pm['week_end']} (< today) — ESPN period pointer is "
                      f"lagging; re-run with --period {pm['period'] + 1} for "
                      f"the week that just started")
        except Exception:
            pass
    cap = pm["sp_cap"]
    ws, we = date.fromisoformat(str(pm["week_start"])), date.fromisoformat(str(pm["week_end"]))
    banked = espn_period_meta(lg, pm["period"], me.team_id, None).get("my_banked")
    banked_known = banked is not None
    banked = banked or 0
    remaining_cap = max(0, cap - banked)

    print("=" * 60)
    print(f"WEEKLY SP CAP CHECK — {today}   (team: {me.team_name})")
    print("=" * 60)
    print(f"Period {pm['period']} ({ws}→{we}, {pm['weeks']}wk) · SP cap {cap}")
    print(f"Banked so far: {banked}{'' if banked_known else ' (ESPN unavailable — assumed 0)'}"
          f" · remaining cap: {remaining_cap}")

    per_start = _per_start_map()
    n2m = _name_to_mlbam()

    # rostered, active (non-IL) SPs
    sps = []
    for p in myteam.roster:
        slot = str(getattr(p, "lineup_slot", "") or "").upper()
        status = str(getattr(p, "injuryStatus", "") or "").upper()
        if slot in IL_SLOTS or status in IL_STATES:
            continue
        try:
            role = detect_pitcher_role(p)
        except Exception:
            elig = {str(s).upper() for s in (getattr(p, "eligibleSlots", []) or [])}
            role = "SP" if "SP" in elig else None
        if role != "SP":
            continue
        mid = n2m.get(_norm(p.name))
        sps.append((p.name, mid))

    win_start = max(today, ws)
    mlbams = {mid for _, mid in sps if mid}
    confirmed, game_days = _window_schedule(mlbams, win_start, we)

    # project starts + value
    starts = []  # (date, name, blended_value, tag, confirmed?)
    for name, mid in sps:
        if not mid:
            print(f"  ! {name}: no mlbam match — skipped")
            continue
        last, cad, l5 = _arm_form(mid)
        rp3_val, tag = per_start.get(mid, (None, "?"))
        val = _proj_val(rp3_val, l5)
        for d in _project_starts(mid, last, cad, confirmed, game_days, win_start, we):
            starts.append((d, name, val, tag, mid in confirmed))

    starts.sort(key=lambda x: x[0])
    n_proj = len(starts)
    total = banked + n_proj

    print(f"\nProjected remaining starts this period: {n_proj}")
    print("value = blend of rp3 season projection + recent L5 form "
          "(de-stales opener/role-change arms, sits the coldest arm this week)")
    print(f"{'date':<12}{'pitcher':<20}{'value':>9}  src")
    for d, name, val, tag, conf in starts:
        flag = "" if conf else " ~proj"
        lc = " LOW-CONF" if str(tag).startswith(("talent_prior", "marcel")) else ""
        print(f"{d.isoformat():<12}{name:<20}{val:>9.2f}  {'conf' if conf else 'proj'}{lc}{flag}")

    print(f"\nbanked {banked} + projected {n_proj} = {total}  vs cap {cap}")

    if n_proj <= remaining_cap:
        print(f"\n>> UNDER CAP — start everyone. {remaining_cap - n_proj} slot(s) to spare"
              f"{' (stream a start if a good one is available)' if remaining_cap - n_proj else ''}.")
    else:
        over = n_proj - remaining_cap
        # keep the highest-value starts; bench the lowest `over`
        ranked = sorted(starts, key=lambda x: x[2])  # ascending value
        bench = ranked[:over]
        print(f"\n>> OVER CAP by {over} — bench the {over} lowest-value start(s) "
              f"(they'd score 0 past the cap):")
        for d, name, val, tag, conf in sorted(bench, key=lambda x: x[0]):
            print(f"   BENCH  {d.isoformat()}  {name}  ({val:.2f} FP/start)")
        keep = sorted(ranked[over:], key=lambda x: -x[2])
        print(f"   (keep your {len(keep)} best; lowest kept: "
              f"{keep[-1][1]} {keep[-1][2]:.2f} on {keep[-1][0].isoformat()})")

    print("\nnotes:")
    print("  · 'proj' starts use rotation cadence (not yet announced) — re-run mid-week as probables post.")
    print("  · benching is a THIS-WEEK form call (sit the coldest start); it is NOT a drop signal —")
    print("    a cold arm with good process (velo/K-BB up) stays rostered, just benched for the week.")
    print("  · LOW-CONF = talent_prior/marcel prior; rank those by Stuff+ if streaming.")


if __name__ == "__main__":
    main()
