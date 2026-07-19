"""build_statcast_gf_bridge — fill the statcast lag with Savant /gf provisional pitches.

pybaseball.statcast() pulls Savant's finalized search CSV (~1-2 day lag), so the models
run a day behind even though the boxscore store gives same-day FP actuals. This bridge
fetches Savant's per-game feed (/gf) for the days the CSV hasn't reached yet, maps each
pitch into the statcast_2026 schema (lib/gf_statcast), reconstructs xwOBA-on-contact from
an EV x LA lookup fit on our own history, and appends the rows PROVISIONALLY
(source='gf_provisional') so the model builders become same-day current.

Composition with the canonical pull (refresh_xfp_statcast):
  - this bridge writes with keep='first' so it NEVER overwrites a canonical row — it only
    fills (game_pk, at_bat_number, pitch_number) keys not already present;
  - it first drops any prior gf_provisional rows, so provisional data never staleness-
    accumulates — it is rebuilt for the current gap each run;
  - the daily pybaseball pull writes with keep='last', so once a day finalizes in the CSV
    its canonical rows overwrite the provisional ones.

Run after refresh_xfp_statcast in the daily chain.
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "research" / "xfp_cache"
STATCAST = CACHE / "statcast_2026.parquet"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gf_statcast import map_gf_pitch, build_xwoba_lookup  # noqa: E402

MLB = "https://statsapi.mlb.com/api/v1"
GF = "https://baseballsavant.mlb.com/gf"


def _get(url, params=None, retries=3):
    for i in range(retries):
        try:
            return requests.get(url, params=params, timeout=20).json()
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1.5)


def game_pks_for_date(d: date):
    """Regular-season Final game_pks for a date (+ team abbrev map)."""
    data = _get(f"{MLB}/schedule", {"sportId": 1, "date": d.isoformat()})
    out = []
    for dd in data.get("dates", []):
        for g in dd.get("games", []):
            if (g.get("status", {}).get("abstractGameState") == "Final"
                    and g.get("gameType") == "R"):
                out.append(g["gamePk"])
    return out


def _abbrev(gf, side):
    """Team abbreviation for 'home'/'away' from the gf payload."""
    td = gf.get(f"{side}_team_data") or {}
    return td.get("abbreviation") or td.get("triCode") or td.get("teamName")


def gf_rows_for_game(pk, lookup):
    """All mapped statcast-schema rows for one game from /gf."""
    gf = _get(GF, {"game_pk": pk})
    if not gf:
        return []
    gd = str(gf.get("game_date") or gf.get("gameDate") or "")[:10]
    meta = {
        "game_pk": pk,
        "game_date": gd or None,
        "game_year": int(gd[:4]) if gd[:4].isdigit() else None,
        "game_type": "R",
        "home_team": _abbrev(gf, "home"),
        "away_team": _abbrev(gf, "away"),
    }
    rows = []
    for side in ("team_home", "team_away"):
        pitches = gf.get(side) or []
        # gf tags the PA outcome on every pitch; the terminal pitch of each at-bat is
        # the one with the max pitch_number, so events/woba land only there.
        max_pn = {}
        for p in pitches:
            ab = p.get("ab_number")
            pn = p.get("pitch_number")
            try:
                pn = int(pn)
            except (TypeError, ValueError):
                continue
            if ab is not None and pn > max_pn.get(ab, -1):
                max_pn[ab] = pn
        for p in pitches:
            try:
                pn = int(p.get("pitch_number"))
            except (TypeError, ValueError):
                pn = None
            is_term = (p.get("ab_number") in max_pn and pn == max_pn[p["ab_number"]])
            try:
                rows.append(map_gf_pitch(p, meta, lookup, is_terminal=is_term))
            except Exception:
                _DROPPED[0] += 1
                continue
    return rows


# Silent-drop tripwire (audit 2026-07-19 R4): the per-pitch except above used
# to swallow EVERY mapping error invisibly — a gf schema drift would drop the
# whole provisional day and the models would silently lose their same-day
# bridge. Count drops and warn loudly past a threshold.
_DROPPED = [0]


def report_drops(n_mapped: int) -> None:
    d = _DROPPED[0]
    total = n_mapped + d
    if not total:
        return
    frac = d / total
    print(f"  gf pitch-mapping drops: {d}/{total} ({frac:.1%})")
    if frac > 0.20:
        print(f"  !! WARNING: {frac:.0%} of gf pitches failed to map — "
              f"likely a game-feed schema drift; the provisional bridge is "
              f"degraded (models fall back to the 1-2 day canonical lag).")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", help="fill through this date (default: yesterday)")
    ap.add_argument("--start", help="force gap start (default: canonical max + 1)")
    args = ap.parse_args()

    if not STATCAST.exists():
        print(f"no statcast cache at {STATCAST} — run refresh_xfp_statcast first")
        return
    sc = pd.read_parquet(STATCAST)
    if "source" not in sc.columns:
        sc["source"] = pd.NA  # existing rows are canonical
    sc["game_date"] = pd.to_datetime(sc["game_date"])

    # Drop prior provisional rows so they never staleness-accumulate.
    canonical = sc[sc["source"] != "gf_provisional"].copy()
    n_prior_prov = len(sc) - len(canonical)

    canon_max = canonical["game_date"].max().date()
    start = (datetime.strptime(args.start, "%Y-%m-%d").date() if args.start
             else canon_max + timedelta(days=1))
    through = (datetime.strptime(args.through, "%Y-%m-%d").date() if args.through
               else date.today() - timedelta(days=1))
    print(f"canonical statcast through {canon_max}; filling gap {start} -> {through} "
          f"(dropped {n_prior_prov} prior provisional rows)")
    if start > through:
        # Nothing to fill; still persist the provisional-cleared frame if it changed.
        if n_prior_prov:
            _write(canonical, sc.columns)
        print("  gap empty — models already current")
        return

    # xwOBA-on-contact lookup from our own (canonical) history.
    lookup = build_xwoba_lookup(canonical[["launch_speed", "launch_angle",
                                           "estimated_woba_using_speedangle"]])

    existing_keys = set(map(tuple, canonical[["game_pk", "at_bat_number",
                                              "pitch_number"]].dropna().values.tolist()))
    new_rows, games = [], 0
    d = start
    while d <= through:
        pks = game_pks_for_date(d)
        print(f"  {d}: {len(pks)} final games")
        for pk in pks:
            for r in gf_rows_for_game(pk, lookup):
                key = (r.get("game_pk"), r.get("at_bat_number"), r.get("pitch_number"))
                if None in key or key in existing_keys:
                    continue  # canonical wins; never overwrite
                new_rows.append(r)
            games += 1
        d += timedelta(days=1)

    report_drops(len(new_rows))
    if not new_rows:
        if n_prior_prov:
            _write(canonical, sc.columns)
        print("  no new provisional pitches")
        return

    gf_df = pd.DataFrame(new_rows)
    # Align to the canonical schema: keep every statcast column, fill missing with NA.
    for c in sc.columns:
        if c not in gf_df.columns:
            gf_df[c] = pd.NA
    gf_df = gf_df[sc.columns]
    gf_df["game_date"] = pd.to_datetime(gf_df["game_date"])

    combined = pd.concat([canonical, gf_df], ignore_index=True)
    _write(combined, sc.columns)
    print(f"  appended {len(gf_df)} provisional pitches from {games} games "
          f"-> {STATCAST.name} ({len(combined)} rows total)")
    print(f"  new max date: {combined['game_date'].max().date()}")


def _write(df, cols):
    df = df[cols].copy()
    tmp = STATCAST.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(STATCAST)


if __name__ == "__main__":
    main()
