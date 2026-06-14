"""vegas_markets_study.py — feasibility + (forward-only) integration scaffold for
adding Vegas / betting-market signals to the BrownU model.

WHAT THIS IS
------------
A collectability assessment + LIVE integration scaffold, NOT a historical
backtest. Historical closing lines (2021-2025) are gated behind paid APIs
(the-odds-api charges a 10x credit multiplier on historical endpoints AND
restricts them to paid plans), so there is no free path to a clean
pre-registered backtest. See the companion writeup:
  data/research/validation_runs/vegas_markets_2026-06-13.md

WHAT IT DOES
------------
1. Probes for an odds-API key (env ODDS_API_KEY / THE_ODDS_API_KEY). None is
   committed; absence is the expected default.
2. If a key is present: pulls CURRENT/upcoming MLB odds from the-odds-api v4
   (free tier, 500 credits/mo), for:
       - h2h (moneyline)            -> implied win probability
       - totals (game over/under)   -> game run environment
       - team_totals  (event endpt) -> per-team implied runs (THE signal)
       - pitcher_strikeouts (event) -> SP SO prop line + over/under price
   then maps team_total -> opp-offense multiplier and shows the adjustment
   it WOULD apply to a hitter/SP start, side-by-side with our internal
   xwOBA bat_index proxy (data/research/xfp_cache/team_strength_2026.csv).
3. If no key: prints the integration spec + budget math and exits 0
   (fail-soft, like the rest of the daily pipeline).

USAGE
-----
  python -X utf8 scripts/_oneoff/vegas_markets_study.py            # dry/spec mode
  ODDS_API_KEY=xxxx python -X utf8 scripts/_oneoff/vegas_markets_study.py
  ODDS_API_KEY=xxxx python -X utf8 scripts/_oneoff/vegas_markets_study.py --max-events 3

DESIGN NOTES
------------
- NO odds are fabricated. If the network/key is unavailable, the script
  prints the spec and the mapping math against a HYPOTHETICAL labelled
  example so the integration is reviewable, then exits without writing
  anything that looks like real data.
- Mapping anchor (league-average implied team total ~4.4 R in 2026; a
  hitter facing a 5.5-R-implied opponent = high-offense day, a 3.3-R
  opponent = soft day). The multiplier is centered at 1.0 so it slots
  straight into the existing bat_index convention used by stream_the_stack.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEAM_STRENGTH_CSV = _REPO_ROOT / "data" / "research" / "xfp_cache" / "team_strength_2026.csv"

_BASE = "https://api.the-odds-api.com/v4"
_SPORT = "baseball_mlb"
_REGION = "us"

# ---- mapping constants (forward-only signal; centered at 1.0 to match bat_index) ----
# League-average MLB implied team total in a normal run environment. Anchor only;
# refresh from the live slate median if you wire this in for real.
LEAGUE_AVG_TEAM_TOTAL = 4.40
# Sensitivity: how much a 1-run deviation in implied team total moves the
# opponent-offense multiplier. 0.10 => a 5.4-R team reads ~1.10 (like our
# hottest bat_index), a 3.4-R team ~0.90. Conservative, matches bat_index spread.
TEAM_TOTAL_SENSITIVITY = 0.10


def implied_prob_from_american(odds: int) -> float:
    """American moneyline -> implied win probability (no vig removal)."""
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def team_total_to_opp_offense_mult(implied_team_total: float) -> float:
    """Map a market-implied opponent team total to an offense multiplier
    centered at 1.0, matching the bat_index convention in team_strength_2026.csv.

    >1.0  => opponent expected to score more than average (BAD for the SP you
            are starting, GOOD for your hitters in that game).
    <1.0  => soft opponent offense.
    """
    dev = implied_team_total - LEAGUE_AVG_TEAM_TOTAL
    return round(1.0 + TEAM_TOTAL_SENSITIVITY * dev, 4)


def find_key() -> str | None:
    for var in ("ODDS_API_KEY", "THE_ODDS_API_KEY", "VEGAS_ODDS_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v
    return None


def _get(path: str, key: str, **params):
    params["apiKey"] = key
    r = requests.get(f"{_BASE}{path}", params=params, timeout=25)
    remaining = r.headers.get("x-requests-remaining")
    used = r.headers.get("x-requests-used")
    if r.status_code != 200:
        print(f"  [http {r.status_code}] {path}: {r.text[:160]}")
        return None, remaining, used
    return r.json(), remaining, used


def run_live(key: str, max_events: int) -> int:
    print("=== LIVE MODE: pulling current/upcoming MLB odds ===")

    # 1) game-level markets in one cheap call (cost = 2 markets x 1 region = 2 credits)
    games, rem, used = _get(
        f"/sports/{_SPORT}/odds", key,
        regions=_REGION, markets="h2h,totals", oddsFormat="american",
    )
    if games is None:
        print("  could not fetch game odds; aborting live mode.")
        return 1
    print(f"  game-odds call OK | credits used={used} remaining={rem} | {len(games)} games")

    # 2) events list is FREE (0 credits) — gives event ids for prop pulls
    events, _, _ = _get(f"/sports/{_SPORT}/events", key)
    event_ids = [e["id"] for e in (events or [])][:max_events]

    print("\n--- GAME-LEVEL SIGNAL (h2h + totals), first few games ---")
    for g in games[:5]:
        home, away = g.get("home_team"), g.get("away_team")
        ml = {}
        tot = None
        for bk in g.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] == "h2h":
                    for oc in mk["outcomes"]:
                        ml.setdefault(oc["name"], oc["price"])
                elif mk["key"] == "totals" and tot is None:
                    for oc in mk["outcomes"]:
                        if oc["name"] == "Over":
                            tot = oc.get("point")
        wp = {t: round(implied_prob_from_american(p), 3) for t, p in ml.items()}
        print(f"  {away} @ {home} | total={tot} | win%={wp}")

    # 3) team_totals + pitcher_strikeouts are 'additional markets' -> per-event endpoint
    #    cost = (unique markets returned) x regions. Pull a few events only to respect quota.
    print("\n--- PER-EVENT SIGNAL (team_totals + pitcher_strikeouts) ---")
    ts = None
    if _TEAM_STRENGTH_CSV.exists():
        import pandas as pd
        ts = pd.read_csv(_TEAM_STRENGTH_CSV).set_index("team")

    for eid in event_ids:
        data, rem, used = _get(
            f"/sports/{_SPORT}/events/{eid}/odds", key,
            regions=_REGION, markets="team_totals,pitcher_strikeouts",
            oddsFormat="american",
        )
        if not data:
            continue
        home, away = data.get("home_team"), data.get("away_team")
        print(f"\n  {away} @ {home}  (credits used={used} remaining={rem})")
        for bk in data.get("bookmakers", [])[:1]:  # one book is enough to demo
            for mk in bk.get("markets", []):
                if mk["key"] == "team_totals":
                    for oc in mk["outcomes"][:4]:
                        nm, pt = oc.get("description") or oc.get("name"), oc.get("point")
                        if oc.get("name") == "Over" and pt is not None:
                            mult = team_total_to_opp_offense_mult(pt)
                            print(f"    team_total {nm}: {pt} R  -> opp_offense_mult={mult}")
                elif mk["key"] == "pitcher_strikeouts":
                    for oc in mk["outcomes"][:6]:
                        print(f"    SO prop {oc.get('description')}: "
                              f"{oc.get('name')} {oc.get('point')} @ {oc.get('price')}")
    print("\n  (team_total -> opp_offense_mult is the value the model would consume; "
          "it slots into the bat_index slot used by stream_the_stack.py)")
    return 0


def run_spec_only() -> int:
    print("=== SPEC MODE (no odds key found — nothing fetched, nothing fabricated) ===\n")
    print("Set ODDS_API_KEY (free tier: https://the-odds-api.com, 500 credits/mo) to go live.\n")
    print("--- Forward-only integration spec ---")
    print(f"  base   : {_BASE}")
    print(f"  sport  : {_SPORT}   region: {_REGION}")
    print("  calls  :")
    print("    GET /sports/{sport}/odds?markets=h2h,totals      cost=2  -> ML + game total")
    print("    GET /sports/{sport}/events                       cost=0  -> event ids")
    print("    GET /sports/{sport}/events/{id}/odds")
    print("        ?markets=team_totals,pitcher_strikeouts      cost=2/event -> THE signals")
    print("\n  daily budget (15-game slate, 1 region, 1 props call/event):")
    print("    2 (game) + 15*2 (events) = 32 credits/day  ->  ~960/mo  (> 500 free)")
    print("    cheaper: pull props only for MY ~9 starts + opp SPs ~9  => ~2+18 = 20/day ~600/mo")
    print("    cheapest: game-level h2h+totals only (no per-event props) = 2/day ~60/mo  << 500")
    print("\n--- Mapping demo (HYPOTHETICAL labelled numbers — not live odds) ---")
    for tt in (3.4, 4.4, 5.5):
        print(f"    implied opp team total {tt} R -> opp_offense_mult="
              f"{team_total_to_opp_offense_mult(tt)}")
    print("\n  Compare vs our internal proxy (team_strength_2026.csv bat_index): "
          "min~0.95 / med~1.00 / max~1.10 — same scale, same slot.")
    print("\n  ML example: -150 fav -> win prob "
          f"{round(implied_prob_from_american(-150),3)};  +130 dog -> "
          f"{round(implied_prob_from_american(130),3)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-events", type=int, default=3,
                    help="cap per-event prop pulls to protect the free quota")
    args = ap.parse_args()

    key = find_key()
    if key:
        try:
            return run_live(key, args.max_events)
        except requests.RequestException as e:
            print(f"  network error in live mode ({e}); falling back to spec.")
            return run_spec_only()
    return run_spec_only()


if __name__ == "__main__":
    sys.exit(main())
