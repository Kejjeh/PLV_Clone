"""
capture_upcoming_starts.py — snapshot the upcoming SP slate to disk.

Probables move (scratches, rain, rotation shuffles, "-" placeholders that fill
in the morning of), so "what the slate looked like when I decided" is not
recoverable after the fact. This writes a timestamped, append-only record of
every posted probable start in a date window:

    data/research/probables_snapshots/upcoming_starts_<start>_<end>_<ts>.csv
    data/research/probables_snapshots/upcoming_starts_<start>_<end>_<ts>.md

Both carry `captured_at` so a later capture of the same window is a diffable
second observation, never an overwrite.

The fetch delegates to the `plv_clone.mlb_stats.get_schedule` owner (item 9,
audit 2026-07-04) — do NOT re-implement `schedule?hydrate=probablePitcher` here.
Games with NO probable posted are recorded too (`pitcher_name = "-"`), because a
TBD side is a real streamer signal, not a hole in the capture.

Model annotation is an ID join (MLBAM `pitcher` column of
xfp_rp3_projections.csv) — never a name match (gotcha #10). `dq` is carried so
a suppressed `marcel_il` prior can never be read as a real rp3 number
(gotcha #1). Stdlib + requests only; no pandas.

Observed overlay
----------------
Scoreboard apps post projected probables the MLB Stats API has not confirmed
yet (verified 2026-07-27: the API had TEX/STL/SEA/LAD/SD/TB sides blank that the
app already showed). Those sides can be recorded in

    data/research/probables_snapshots/observed_probables.csv
        date,team,observed_name,source,observed_at,note

and this script fills them into blank API sides ONLY, tagging `source=observed`
so an unconfirmed name can never be mistaken for a confirmed one. "M. Liberatore"
is resolved to an MLBAM id by matching last name + first initial against THAT
TEAM's pitchers (`mlb_stats.get_team_pitchers`), skipping on ambiguity — a
league-wide abbreviated-name match is the gotcha #10 trap.

Usage
-----
    python scripts/xfp/capture_upcoming_starts.py                  # today..+2
    python scripts/xfp/capture_upcoming_starts.py --days 3
    python scripts/xfp/capture_upcoming_starts.py --start 2026-07-27 --end 2026-07-29
    python scripts/xfp/capture_upcoming_starts.py --no-observed    # API only
    python scripts/xfp/capture_upcoming_starts.py --no-write       # preview only
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from plv_clone.mlb_stats import get_schedule, get_team_pitchers  # noqa: E402

OUT_DIR = ROOT / "data" / "research" / "probables_snapshots"
RP3_CSV = ROOT / "data" / "outputs" / "xfp_rp3_projections.csv"
OBSERVED_CSV = OUT_DIR / "observed_probables.csv"

FIELDS = [
    "captured_at", "date", "first_pitch_et", "pitcher_name", "pitcher_id",
    "team", "opp", "home_away", "park", "game_pk", "game_state",
    "source", "observed_source", "rp3_rank", "rp3_per_start", "dq",
]

# Scoreboard apps use a few legacy abbreviations; the API is authoritative.
ABBR_ALIASES = {"CHW": "CWS", "ARI": "AZ", "WAS": "WSH", "OAK": "ATH",
                "SDP": "SD", "SFG": "SF", "TBR": "TB", "KCR": "KC"}

# Sorts TBD sides last within a day without pretending they have a time.
_LATE = (99, 99)


def load_rp3(path: Path = RP3_CSV) -> dict[int, dict]:
    """MLBAM id -> {rank, per_start, dq}. Empty dict when the model CSV is absent."""
    if not path.exists():
        print(f"WARN rp3 annotation skipped: {path} not found", file=sys.stderr)
        return {}
    out: dict[int, dict] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                pid = int(float(row["pitcher"]))
            except (KeyError, TypeError, ValueError):
                continue
            per_start = row.get("xfp_rp3_per_start") or ""
            try:
                per_start = f"{float(per_start):.2f}"
            except ValueError:
                per_start = ""
            out[pid] = {
                "rank": row.get("rank", ""),
                "per_start": per_start,
                "dq": row.get("data_quality_tag", ""),
            }
    return out


def norm_abbr(abbr: str | None) -> str:
    a = (abbr or "").strip().upper()
    return ABBR_ALIASES.get(a, a)


def load_observed(path: Path = OBSERVED_CSV) -> dict[tuple[str, str], dict]:
    """(date, team_abbr) -> observed row. Absent file = no overlay, not an error."""
    if not path.exists():
        return {}
    out: dict[tuple[str, str], dict] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("observed_name") or "").strip()
            if not name or name == "-":
                continue
            out[((row.get("date") or "").strip(), norm_abbr(row.get("team")))] = row
    return out


def resolve_observed_name(
    name: str,
    team_abbr: str,
    *,
    roster_fetch=get_team_pitchers,
) -> tuple[int | None, str]:
    """'M. Liberatore' + 'STL' -> (682243, 'Matthew Liberatore').

    Matches last name + first initial against THAT TEAM's pitchers only, and
    returns (None, name) when the match is absent or ambiguous — an unresolved
    observation is captured as-is, never guessed (gotcha #10).
    """
    parts = [p for p in name.replace(".", " ").split() if p]
    if not parts:
        return None, name
    last = parts[-1].casefold()
    initial = parts[0][0].casefold() if len(parts) > 1 else ""
    hits = []
    for p in roster_fetch(team_abbr):
        full = p.get("full_name") or ""
        toks = full.split()
        if not toks or toks[-1].casefold() != last:
            continue
        if initial and toks[0][:1].casefold() != initial:
            continue
        hits.append(p)
    if len(hits) != 1:
        return None, name
    return hits[0]["id"], hits[0]["full_name"]


def _et_sort_key(et: str | None) -> tuple[int, int]:
    """'7:40PM' -> (19, 40) for chronological sort; TBD sorts last."""
    if not et:
        return _LATE
    try:
        clock, mer = et[:-2], et[-2:].upper()
        hh, mm = (int(x) for x in clock.split(":"))
    except (ValueError, IndexError):
        return _LATE
    if mer == "PM" and hh != 12:
        hh += 12
    elif mer == "AM" and hh == 12:
        hh = 0
    return (hh, mm)


def build_rows(
    games: list[dict],
    *,
    captured_at: str,
    rp3: dict[int, dict],
    observed: dict[tuple[str, str], dict] | None = None,
    roster_fetch=get_team_pitchers,
) -> list[dict]:
    """One row per probable SIDE of every game — including sides with no probable.

    `observed` fills BLANK API sides only (never overrides a confirmed one) and
    marks them `source=observed`.
    """
    observed = observed or {}
    rows: list[dict] = []
    for g in games:
        if g.get("game_type") != "R":  # regular season only; spring/post are separate slates
            continue
        for side, opp_side in (("away", "home"), ("home", "away")):
            pid = g.get(f"{side}_probable_id")
            name = g.get(f"{side}_probable_name") or ""
            team = norm_abbr(g.get(f"{side}_abbr"))
            source, obs_source = ("mlb_api" if pid else ""), ""
            if not pid:
                obs = observed.get((g.get("date"), team))
                if obs:
                    pid, name = resolve_observed_name(
                        obs["observed_name"], team, roster_fetch=roster_fetch)
                    source = "observed"
                    obs_source = (obs.get("source") or "").strip()
            ann = rp3.get(int(pid), {}) if pid else {}
            rows.append({
                "captured_at": captured_at,
                "date": g.get("date"),
                "first_pitch_et": g.get("first_pitch_et") or "",
                "pitcher_name": name or "-",
                "pitcher_id": pid or "",
                "team": team,
                "opp": norm_abbr(g.get(f"{opp_side}_abbr")),
                "home_away": "home" if side == "home" else "away",
                "park": norm_abbr(g.get("home_abbr")),
                "game_pk": g.get("game_pk"),
                "game_state": g.get("game_state"),
                "source": source,
                "observed_source": obs_source,
                "rp3_rank": ann.get("rank", ""),
                "rp3_per_start": ann.get("per_start", ""),
                "dq": ann.get("dq", ""),
            })
    rows.sort(key=lambda r: (r["date"], _et_sort_key(r["first_pitch_et"]),
                            r["park"] or "", r["home_away"]))
    return rows


def render_md(rows: list[dict], *, start: str, end: str, captured_at: str) -> str:
    api = [r for r in rows if r["source"] == "mlb_api"]
    obs = [r for r in rows if r["source"] == "observed"]
    lines = [
        f"# Upcoming SP starts — {start} .. {end}",
        "",
        f"Captured {captured_at} via `plv_clone.mlb_stats.get_schedule`. "
        f"{len(api)} probables confirmed by the MLB Stats API across "
        f"{len(rows) // 2} games; {len(obs)} filled from the observed overlay; "
        f"{len(rows) - len(api) - len(obs)} side(s) still TBD.",
        "",
        "`rp3` = rank / per-start from `xfp_rp3_projections.csv`, joined on MLBAM id. "
        "A `marcel_il` dq is a SUPPRESSED prior, not a real read (gotcha #1). "
        "**†** = observed/projected only, NOT confirmed by the MLB feed.",
    ]
    for day in sorted({r["date"] for r in rows}):
        lines += ["", f"## {day}", "",
                  "| ET | Pitcher | Team | Opp | Park | rp3 | per_start | dq |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in (x for x in rows if x["date"] == day):
            vs = f"{'vs' if r['home_away'] == 'home' else '@'} {r['opp']}"
            mark = " †" if r["source"] == "observed" else ""
            lines.append(
                f"| {r['first_pitch_et'] or 'TBD'} | {r['pitcher_name']}{mark} | {r['team']} "
                f"| {vs} | {r['park']} | {r['rp3_rank'] or '—'} "
                f"| {r['rp3_per_start'] or '—'} | {r['dq'] or '—'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", help="window start YYYY-MM-DD (default today)")
    ap.add_argument("--end", help="window end YYYY-MM-DD (default start + --days - 1)")
    ap.add_argument("--days", type=int, default=3,
                    help="window length when --end is omitted (default 3)")
    ap.add_argument("--observed", default=str(OBSERVED_CSV),
                    help=f"observed-probables overlay CSV (default {OBSERVED_CSV.name})")
    ap.add_argument("--no-observed", action="store_true",
                    help="MLB-API-confirmed probables only; ignore the overlay")
    ap.add_argument("--no-write", action="store_true", help="print only, write nothing")
    args = ap.parse_args(argv)

    start = date.fromisoformat(args.start) if args.start else date.today()
    end = (date.fromisoformat(args.end) if args.end
           else start + timedelta(days=max(1, args.days) - 1))
    if end < start:
        ap.error("--end precedes --start")

    now = datetime.now(timezone.utc)
    captured_at = now.isoformat(timespec="seconds")
    games = get_schedule(start, end)
    if not games:
        print("ERROR no games returned — API fetch failed or window has no games; "
              "nothing captured", file=sys.stderr)
        return 1

    observed = {} if args.no_observed else load_observed(Path(args.observed))
    rows = build_rows(games, captured_at=captured_at, rp3=load_rp3(),
                      observed=observed)
    md = render_md(rows, start=start.isoformat(), end=end.isoformat(),
                   captured_at=captured_at)
    print(md)

    if args.no_write:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"upcoming_starts_{start}_{end}_{now.strftime('%Y-%m-%d-%H%M')}"
    csv_path = OUT_DIR / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    md_path = OUT_DIR / f"{stem}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"wrote {csv_path.relative_to(ROOT)}\nwrote {md_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
