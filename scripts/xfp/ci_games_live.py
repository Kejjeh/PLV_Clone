#!/usr/bin/env python3
"""ci_games_live.py — game-gate for the hourly live-matchup CI job.

Queries the MLB Stats API schedule and decides whether any game is CURRENTLY
in progress. This is what lets the `live-matchup` workflow run hourly *only
while games are live*: the first live game flips the gate on, and once the
last game goes Final the gate flips off — i.e. it "starts when games start
and stops when they end."

Behaviour:
  * Looks at the US-Eastern slate for both yesterday and today, so a
    west-coast game that started ~10pm ET and is still going after midnight
    UTC is still counted as live.
  * "Live" == MLB `status.abstractGameState == 'Live'` (covers In Progress /
    Manager challenge / Warmup transitions). Preview and Final do not count.
  * Writes `live=true|false` to $GITHUB_OUTPUT (GitHub Actions step output)
    and prints a human-readable summary. Always exits 0 — gating is via the
    output value, not the exit code.
  * On any API/parse error it FAILS OPEN (`live=true`) so a transient MLB
    outage never silently freezes the live dashboard during game hours.

Local use:
  python scripts/xfp/ci_games_live.py            # prints summary + live=...
  python scripts/xfp/ci_games_live.py --date 2026-06-16
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from urllib.request import urlopen, Request

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

API = ("https://statsapi.mlb.com/api/v1/schedule"
       "?sportId=1&startDate={start}&endDate={end}")

LIVE_STATES = {"Live"}  # abstractGameState that counts as "in progress"


def _eastern_today() -> date:
    """Today's date on the US-Eastern MLB slate (falls back to UTC if no tz)."""
    if ZoneInfo is not None:
        from datetime import datetime
        return datetime.now(ZoneInfo("America/New_York")).date()
    from datetime import datetime, timezone
    # crude EDT fallback (UTC-4) so a late game isn't mis-dated
    return (datetime.now(timezone.utc) - timedelta(hours=4)).date()


def _set_output(live: bool) -> None:
    """Emit `live=true|false` as a GitHub Actions step output if running in CI."""
    out = os.environ.get("GITHUB_OUTPUT")
    val = "true" if live else "false"
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"live={val}\n")
    print(f"live={val}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="anchor date YYYY-MM-DD (default: ET today)")
    args = ap.parse_args()

    # Manual override (workflow_dispatch force input) — skip the API entirely.
    if os.environ.get("FORCE_LIVE", "").lower() == "true":
        print("  FORCE_LIVE set — gate forced open.")
        _set_output(True)
        return 0

    if args.date:
        anchor = date.fromisoformat(args.date)
    else:
        anchor = _eastern_today()
    start = (anchor - timedelta(days=1)).isoformat()  # catch midnight-spanning games
    end = anchor.isoformat()

    url = API.format(start=start, end=end)
    try:
        req = Request(url, headers={"User-Agent": "plv-clone-ci-gate/1.0"})
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # fail open
        print(f"  ⚠ MLB schedule fetch failed ({e}); failing OPEN (live=true).")
        _set_output(True)
        return 0

    live = preview = final = other = 0
    for d in data.get("dates", []):
        for g in d.get("games", []):
            state = (g.get("status") or {}).get("abstractGameState", "")
            if state in LIVE_STATES:
                live += 1
            elif state == "Preview":
                preview += 1
            elif state == "Final":
                final += 1
            else:
                other += 1

    total = live + preview + final + other
    print(f"  MLB slate {start}..{end}: {total} games "
          f"| live={live} preview={preview} final={final} other={other}")
    _set_output(live > 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
