"""run_rating_arc.py — engine for the /rating-arc skill.

In-season rating-arc mover board: for every SP and hitter with enough 2026
sample, the arc on the role's VALIDATED load-bearing pillar (SP STUFF forward
r=.48 in-season / hitter CONTACT r=.29 — the 2026-07-04 study) over the last
~4 weeks, tagged RISER / FLAT / FALLER and MINE / FA / opponent.

The early-warning lens: process ratings move before results do. Rule 13 —
display/context only, never a ranker. Owner of the arc math: lib/rating_arc.

Usage:
  python scripts/xfp/run_rating_arc.py                 # both roles, MINE + FA movers
  python scripts/xfp/run_rating_arc.py --role sp
  python scripts/xfp/run_rating_arc.py --lookback 21 --top 15
  python scripts/xfp/run_rating_arc.py --names "Sheehan,Messick"
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

MY = "New York Ligers"


# _nrm routed to the name_match owner (item 10, 2026-07-04) — symmetric ownership/
# --names join key; join_key adds order/punctuation robustness.
from plv_clone.utils.name_match import join_key as _nrm  # noqa: E402


def _ownership():
    from app.espn_connector import get_all_teams
    teams = get_all_teams()
    return {_nrm(n): t for n, t in zip(teams["player_name"], teams["team_name"])}


def _own_tag(name, rost):
    t = rost.get(_nrm(name))
    if t == MY:
        return "MINE"
    return "FA" if t is None else "opp"


def _fmt_row(r, role):
    extra = (f"M {r['movement_then']}->{r['movement_now']}  C {r['control_then']}->{r['control_now']}"
             if role == "sp" else
             f"P {r['power_then']}->{r['power_now']}  D {r['discipline_then']}->{r['discipline_now']}")
    stale = " ⚠STALE-ARC (no recent sample — IL?)" if r.get("stale") else ""
    return (f"  {r['arc']:<7} {str(r['player_name'])[:22]:<22} {r['own']:<5}"
            f" {r['key_pillar']} {r[r['key_pillar'].lower() + '_then']:>2}->{r[r['key_pillar'].lower() + '_now']:<3}"
            f" ({r['key_delta']:+d})  OVR {r['overall_then']}->{r['overall_now']}  | {extra}"
            f"  [{r['date_then']}..{r['date_now']}]{stale}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="both", choices=["sp", "hitter", "both"])
    ap.add_argument("--lookback", type=int, default=28)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--names", default=None, help="comma-separated card mode")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    from lib.rating_arc import rating_arcs
    rost = _ownership()
    roles = ["sp", "hitter"] if a.role == "both" else [a.role]
    frames = []
    for role in roles:
        df = rating_arcs(role, lookback_days=a.lookback)
        if not len(df):
            print(f"({role}: no arcs computable)")
            continue
        df = df[df["player_name"].notna()].copy()   # unresolvable ids — no board value
        # An arc whose LATEST snapshot is itself old (IL / demoted) is history,
        # not a current read — tag it so nobody trades on an April arc.
        from datetime import date, timedelta
        stale_cut = (date.today() - timedelta(days=21)).isoformat()
        df["stale"] = df["date_now"] < stale_cut
        df["own"] = df["player_name"].map(lambda n: _own_tag(n, rost))
        df["role"] = role
        frames.append(df)

        if a.names:
            wanted = {_nrm(x) for x in a.names.split(",")}
            sub = df[df["player_name"].map(_nrm).isin(wanted)]
            if len(sub):
                print(f"\n===== {role.upper()} rating-arc cards =====")
                for _, r in sub.iterrows():
                    print(_fmt_row(r, role))
            continue

        key = df.iloc[0]["key_pillar"] if len(df) else "?"
        print(f"\n===== {role.upper()} rating arcs — key pillar {key}, last ~{a.lookback}d "
              f"(Rule 13: context only) =====")
        mine = df[df["own"] == "MINE"]
        if len(mine):
            print(f"-- MINE ({len(mine)}) --")
            for _, r in mine.iterrows():
                print(_fmt_row(r, role))
        fa = df[(df["own"] == "FA") & (~df["stale"])]   # stale arcs aren't add signals
        for tag, hdr in (("RISER", "FA RISERS"), ("FALLER", "FA FALLERS")):
            sub = fa[fa["arc"] == tag].head(a.top)
            if len(sub):
                print(f"-- {hdr} (top {len(sub)}) --")
                for _, r in sub.iterrows():
                    print(_fmt_row(r, role))

    if a.csv and frames:
        import pandas as pd
        pd.concat(frames).to_csv(a.csv, index=False)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
