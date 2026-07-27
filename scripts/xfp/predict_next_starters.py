"""
predict_next_starters.py — who starts on a date the slate hasn't posted yet.

Scoreboard apps and the MLB feed both go blank ~5 days out, but a rotation is a
cycle: the arm who started the team's 5th-previous GAME comes up next. Everything
needed to run that cycle forward is already known — actual starters for played
games plus posted/observed probables for the days in between.

    python scripts/xfp/predict_next_starters.py --date 2026-08-02
    python scripts/xfp/predict_next_starters.py --date 2026-08-02 --backtest
    python scripts/xfp/predict_next_starters.py --date 2026-08-02 --no-write

The rule (k=5) is MEASURED, not assumed. Swept over 8 clean dates x 30 teams
(2026-06-21 .. 2026-07-26), counting games back rather than calendar days so
off-days take care of themselves:

    k=5 (this rule) 63.7%   |   k=4  4.3%   |   k=6 16.3%
    fitting k per team from its own recent cycle: 57.8% — WORSE, don't.
    picking the most-rested arm: 50.4%   |   nearest-to-5-days-rest: 34.7%

The peak at exactly 5 is that sharp because every team runs a five-man rotation;
counting GAMES (not days) is what makes off-days a non-issue.

Two tiers, calibrated on the same sweep — HIGH is worth acting on, LOW is a
coin-flip you should not bench a real arm over:

    HIGH  73% exact (n=179, ~75% of sides): clean 5-man last turn, the arm has
          4-6 days rest and >=3 starts in the window.
    LOW   35% exact (n=61): anything else — a 6th starter, an opener, an arm
          just off the IL, or a rotation the break/deadline scrambled.

Known blind spot: the All-Star break resets rotations, so any target within ~2
days of the break scores ~20% regardless of tier (2026-07-20 and 07-21 measured
20%/20% and are excluded from the numbers above). Trades are the same class of
break — a deadline-day prediction deserves the LOW reading whatever the tier says.

An opener/bullpen day is a real rotation slot here: the cycle predicts whoever
holds the turn, which is the right answer for cap and streamer purposes even
when that arm throws two innings.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from plv_clone.mlb_stats import get_schedule  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "capture_upcoming_starts", Path(__file__).with_name("capture_upcoming_starts.py"))
cus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cus)

OUT_DIR = cus.OUT_DIR
LOOKBACK_DAYS = 35
CYCLE = 5                 # games back, swept — see module docstring
MIN_REST, MAX_REST = 4, 7  # a real turn; outside this the cycle arm is reassigned
IMPOSSIBLE_REST = 3        # started this recently => cannot hold the next turn

FIELDS = [
    "predicted_at", "date", "first_pitch_et", "team", "opp", "home_away", "park",
    "predicted_pitcher", "predicted_pitcher_id", "confidence", "rest_days",
    "starts_in_window", "clean_cycle", "last_start", "runner_up",
    "rp3_rank", "rp3_per_start", "dq",
]


def team_histories(rows: list[dict], before: str) -> dict[str, list[dict]]:
    """team -> its known starts strictly before `before`, oldest first."""
    hist: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["date"] < before and r["pitcher_id"]:
            hist[r["team"]].append(r)
    for team in hist:
        hist[team].sort(key=lambda r: (r["date"], cus._et_sort_key(r["first_pitch_et"])))
    return hist


def _rest(target: str, last_start: str) -> int:
    return (date.fromisoformat(target) - date.fromisoformat(last_start)).days


def _last_start_by_pitcher(history: list[dict]) -> dict[int, str]:
    out: dict[int, str] = {}
    for r in history:  # oldest first, so the last write wins
        out[int(r["pitcher_id"])] = r["date"]
    return out


def predict_team(history: list[dict], target: str) -> dict:
    """Next arm up for one team. {} when there is no usable history."""
    if not history:
        return {}
    lasts = _last_start_by_pitcher(history)
    starts = defaultdict(int)
    for r in history:
        starts[int(r["pitcher_id"])] += 1
    clean_cycle = len({r["pitcher_id"] for r in history[-CYCLE:]}) == CYCLE

    # Most recent appearance per pitcher, for reassignment + runner-up.
    latest: dict[int, dict] = {}
    for r in history:
        latest[int(r["pitcher_id"])] = r

    def eligible(exclude: int | None = None) -> list[dict]:
        return sorted(
            (r for pid, r in latest.items()
             if pid != exclude and MIN_REST <= _rest(target, lasts[pid]) <= MAX_REST),
            key=lambda r: abs(_rest(target, lasts[int(r["pitcher_id"])]) - CYCLE))

    row = history[-CYCLE] if len(history) >= CYCLE else history[-1]
    pid = int(row["pitcher_id"])
    note = ""
    if _rest(target, lasts[pid]) <= IMPOSSIBLE_REST:
        # The cycle arm pitched too recently to hold this turn (skipped turn,
        # doubleheader, IL shuffle) — hand it to the closest-to-a-real-turn arm.
        alts = eligible()
        if alts:
            row, pid = alts[0], int(alts[0]["pitcher_id"])
            note = "cycle arm reassigned: pitched within 3 days"

    rest = _rest(target, lasts[pid])
    conf = ("HIGH" if (clean_cycle and 4 <= rest <= 6 and starts[pid] >= 3 and not note)
            else "LOW")
    alts = eligible(exclude=pid)
    return {
        "pitcher_id": pid, "pitcher_name": row["pitcher_name"],
        "confidence": conf, "rest_days": rest, "starts_in_window": starts[pid],
        "clean_cycle": clean_cycle, "last_start": lasts[pid],
        "runner_up": alts[0]["pitcher_name"] if alts else "", "note": note,
    }


def build_predictions(rows: list[dict], target: str, *, rp3: dict[int, dict],
                      predicted_at: str, force_all: bool = False) -> list[dict]:
    """One prediction per target-date side that has no posted starter."""
    hist = team_histories(rows, target)
    out: list[dict] = []
    for r in rows:
        if r["date"] != target or (r["pitcher_id"] and not force_all):
            continue
        p = predict_team(hist.get(r["team"], []), target)
        if not p:
            continue
        ann = rp3.get(p["pitcher_id"], {})
        out.append({
            "predicted_at": predicted_at, "date": target,
            "first_pitch_et": r["first_pitch_et"], "team": r["team"], "opp": r["opp"],
            "home_away": r["home_away"], "park": r["park"],
            "predicted_pitcher": p["pitcher_name"],
            "predicted_pitcher_id": p["pitcher_id"],
            "confidence": p["confidence"], "rest_days": p["rest_days"],
            "starts_in_window": p["starts_in_window"],
            "clean_cycle": p["clean_cycle"], "last_start": p["last_start"],
            "runner_up": p["runner_up"],
            "rp3_rank": ann.get("rank", ""), "rp3_per_start": ann.get("per_start", ""),
            "dq": ann.get("dq", ""),
        })
    out.sort(key=lambda r: (cus._et_sort_key(r["first_pitch_et"]), r["park"],
                            r["home_away"]))
    return out


def backtest(target: str, *, lookback: int = LOOKBACK_DAYS) -> dict:
    """Re-run the identical logic on a past date, scored against what happened.

    Uses ONLY games before `target`, and no observed overlay, so the score can't
    borrow anything the live path wouldn't have had.
    """
    start = (date.fromisoformat(target) - timedelta(days=lookback)).isoformat()
    rows = cus.build_rows(get_schedule(start, target), captured_at="backtest",
                          rp3={}, observed={})
    actual = {r["team"]: (int(r["pitcher_id"]), r["pitcher_name"])
              for r in rows if r["date"] == target and r["pitcher_id"]}
    if not actual:
        return {"target": target, "n": 0, "note": "no actual starters that date"}
    preds = build_predictions(rows, target, rp3={}, predicted_at="backtest",
                              force_all=True)
    hits = 0
    by_conf: dict[str, list[int]] = defaultdict(list)
    misses: list[str] = []
    for p in preds:
        truth = actual.get(p["team"])
        if not truth:
            continue
        ok = truth[0] == p["predicted_pitcher_id"]
        hits += ok
        by_conf[p["confidence"]].append(int(ok))
        if not ok:
            misses.append(f"{p['team']} [{p['confidence']}]: "
                          f"{p['predicted_pitcher']} → actual {truth[1]}")
    n = sum(len(v) for v in by_conf.values())
    return {
        "target": target, "n": n, "hits": hits,
        "accuracy": round(hits / n, 3) if n else None,
        "by_confidence": {c: {"n": len(v), "acc": round(sum(v) / len(v), 3)}
                          for c, v in sorted(by_conf.items())},
        "misses": misses,
    }


def render_md(preds: list[dict], *, target: str, predicted_at: str,
              bts: list[dict]) -> str:
    hi = [p for p in preds if p["confidence"] == "HIGH"]
    lines = [
        f"# Predicted starters — {target}",
        "",
        f"Predicted {predicted_at} by walking each team's rotation cycle forward "
        f"(the arm who started its 5th-previous game) over everything known: API "
        f"finals, posted probables, and the observed overlay. {len(preds)} sides "
        f"predicted — no probable is posted for any of them. "
        f"{len(hi)} land in the HIGH tier.",
    ]
    for bt in bts:
        if bt.get("n"):
            conf = ", ".join(f"{c} {d['acc']:.0%} (n={d['n']})"
                             for c, d in bt["by_confidence"].items())
            lines += ["", f"**Backtest {bt['target']}: {bt['accuracy']:.0%} exact "
                          f"({bt['hits']}/{bt['n']})** — {conf}."]
    lines += [
        "", "Tier meaning (measured, see the script docstring): **HIGH ≈ 73%** exact, "
        "**LOW ≈ 35%** — a LOW call is a coin flip, not a reason to bench a real arm. "
        "`runner_up` is the next-most-plausible turn holder.",
        "", "| ET | Team | Opp | Predicted | Conf | Rest | Last | rp3 | per_start | Runner-up |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in preds:
        vs = f"{'vs' if p['home_away'] == 'home' else '@'} {p['opp']}"
        lines.append(
            f"| {p['first_pitch_et']} | {p['team']} | {vs} | {p['predicted_pitcher']} "
            f"| {p['confidence']} | {p['rest_days']}d | {p['last_start'][5:]} "
            f"| {p['rp3_rank'] or '—'} | {p['rp3_per_start'] or '—'} "
            f"| {p['runner_up'] or '—'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="target date YYYY-MM-DD")
    ap.add_argument("--lookback", type=int, default=LOOKBACK_DAYS)
    ap.add_argument("--backtest", action="store_true",
                    help="score the same logic on the two prior same-weekday dates")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    target = date.fromisoformat(args.date)
    now = datetime.now(timezone.utc)
    predicted_at = now.isoformat(timespec="seconds")

    rows = cus.build_rows(get_schedule(target - timedelta(days=args.lookback), target),
                          captured_at=predicted_at, rp3={}, observed=cus.load_observed())
    if not rows:
        print("ERROR no schedule rows — fetch failed", file=sys.stderr)
        return 1
    preds = build_predictions(rows, target.isoformat(), rp3=cus.load_rp3(),
                              predicted_at=predicted_at)

    bts: list[dict] = []
    if args.backtest:
        for back in (7, 14):
            bt = backtest((target - timedelta(days=back)).isoformat(),
                          lookback=args.lookback)
            bts.append(bt)
            print(f"BACKTEST {bt['target']}: {bt.get('hits')}/{bt.get('n')} "
                  f"{bt.get('by_confidence')}", file=sys.stderr)
            for miss in bt.get("misses", []):
                print(f"   MISS {miss}", file=sys.stderr)

    md = render_md(preds, target=target.isoformat(), predicted_at=predicted_at, bts=bts)
    print(md)
    if args.no_write:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"predicted_starters_{target}_{now.strftime('%Y-%m-%d-%H%M')}"
    with (OUT_DIR / f"{stem}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(preds)
    (OUT_DIR / f"{stem}.md").write_text(md, encoding="utf-8")
    print(f"wrote {(OUT_DIR / f'{stem}.csv').relative_to(ROOT)}\n"
          f"wrote {(OUT_DIR / f'{stem}.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
