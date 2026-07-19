"""run_conviction_scan.py — engine for the /conviction-scan skill.

League-wide model-vs-process divergence board. For every 2026 player with both
a validated model projection AND a current rating, compares the percentile of
the VALIDATED key pillar (SP STUFF, hitter CONTACT — the only ratings carrying
forward-FP signal, 2026-07-04 study) against the percentile of the model
projection (rp3 per_start / rh3 per_game):

    divergence = rating_pct − model_pct     (percentage points)

  ≥ +25pp  →  PROCESS>MODEL  (patience / buy-low WATCH — the rating says the
              arm/bat is better than results; SP flavor mirrors the validated
              Stuff+ buy-low; hitter flavor is CONTEXT-ONLY, hitter buy-low was
              REJECTED as an additive signal)
  ≤ −25pp  →  MODEL>PROCESS  (distrust / sell-high WATCH — production above
              the process; regression candidate)

Rule 13: divergence NEVER moves rh3/rp3 and never re-ranks. It sets conviction
and routes to /triangulate. Headline number stays the model.

Usage:
  python scripts/xfp/run_conviction_scan.py                # MINE + FA + opp
  python scripts/xfp/run_conviction_scan.py --role sp --top 12
  python scripts/xfp/run_conviction_scan.py --csv out.csv
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from plv_clone.league_config import MY_TEAM_NAME

_ROOT = Path(__file__).resolve().parents[2]
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

MY = MY_TEAM_NAME
RES = _ROOT / "data" / "research"
OUT = _ROOT / "data" / "outputs"

CFG = {
    "sp": dict(master=RES / "sp_ratings_master.csv", id_master="pitcher",
               pillar="STUFF", proj=OUT / "xfp_rp3_projections.csv",
               id_proj="pitcher", val="xfp_rp3_per_start", min_n=("gs", 5)),
    "hitter": dict(master=RES / "hitter_ratings_master.csv", id_master="batter",
                   pillar="CONTACT", proj=OUT / "xfp_rh3_projections.csv",
                   id_proj="batter", val="xfp_rh3_per_game", min_n=("pa", 100)),
}
DIVERGENCE_PP = 25


# _nrm routed to the name_match owner (item 10, 2026-07-04). Used only as a
# symmetric ownership-join key (roster tag); join_key is order-independent so it
# subsumes the old explicit "Last, First" flip natively.
from plv_clone.utils.name_match import join_key as _nrm  # noqa: E402


def scan(role: str) -> pd.DataFrame:
    c = CFG[role]
    m = pd.read_csv(c["master"])
    m = m[m["year"] == m["year"].max()].copy()
    ncol, nmin = c["min_n"]
    if ncol in m.columns:
        m = m[m[ncol] >= nmin]
    proj = pd.read_csv(c["proj"]).dropna(subset=[c["id_proj"], c["val"]])
    df = m.merge(proj[[c["id_proj"], c["val"]]],
                 left_on=c["id_master"], right_on=c["id_proj"], how="inner")
    if not len(df):
        return df
    # marcel-suppressed priors are not a real model read — exclude from divergence
    if "data_quality_tag" in proj.columns:
        tags = proj.set_index(c["id_proj"])["data_quality_tag"].astype(str).to_dict()
        df = df[~df[c["id_master"]].map(lambda i: "marcel" in tags.get(i, ""))]
    df["rating_pct"] = df[c["pillar"]].rank(pct=True) * 100
    df["model_pct"] = df[c["val"]].rank(pct=True) * 100
    df["divergence"] = (df["rating_pct"] - df["model_pct"]).round(0)
    df["tag"] = df["divergence"].map(
        lambda d: "PROCESS>MODEL" if d >= DIVERGENCE_PP
        else ("MODEL>PROCESS" if d <= -DIVERGENCE_PP else ""))
    df["role"] = role
    df["pillar_val"] = df[c["pillar"]]
    df["model_val"] = df[c["val"]]
    keep = [c["id_master"], "player_name", "role", "pillar_val", "rating_pct",
            "model_val", "model_pct", "divergence", "tag"]
    return df[keep].rename(columns={c["id_master"]: "mlbam"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="both", choices=["sp", "hitter", "both"])
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    from app.espn_connector import get_all_teams
    teams = get_all_teams()
    rost = {_nrm(n): t for n, t in zip(teams["player_name"], teams["team_name"])}

    def own(name):
        t = rost.get(_nrm(name))
        return "MINE" if t == MY else ("FA" if t is None else f"opp:{t[:14]}")

    # freshness banner — the SP master inherits the multiyr input's as-of date
    src = RES / "xfp_cache" / "sp_multiyr_2015_2025.csv"
    if src.exists():
        from datetime import datetime
        print(f"(SP ratings input as-of {datetime.fromtimestamp(src.stat().st_mtime):%Y-%m-%d} "
              f"— if stale, the parallel multiyr fix refreshes it)")

    frames = []
    for role in (["sp", "hitter"] if a.role == "both" else [a.role]):
        df = scan(role)
        if not len(df):
            print(f"({role}: nothing joinable)")
            continue
        df["own"] = df["player_name"].map(own)
        frames.append(df)
        key = CFG[role]["pillar"]
        print(f"\n===== {role.upper()} conviction scan — {key} pct vs model pct "
              f"(Rule 13: context only) =====")
        for tag, hdr in (("PROCESS>MODEL", f"PROCESS>MODEL (patience/buy-low watch"
                          f"{' — CONTEXT-ONLY, hitter buy-low REJECTED' if role=='hitter' else ''})"),
                         ("MODEL>PROCESS", "MODEL>PROCESS (distrust/sell-high watch)")):
            sub = df[df["tag"] == tag].sort_values(
                "divergence", ascending=(tag == "MODEL>PROCESS"))
            sub = pd.concat([sub[sub["own"] == "MINE"], sub[sub["own"] != "MINE"]]).head(a.top + 4)
            if not len(sub):
                continue
            print(f"-- {hdr} --")
            for _, r in sub.iterrows():
                # per-player crash guard (audit 2026-07-19 item 22, collect_cards
                # pattern): one bad row (NaN cast etc.) must not kill the board.
                try:
                    print(f"  {str(r['player_name'])[:22]:<22} {r['own']:<18} {key} {int(r['pillar_val']):>2} "
                          f"(p{r['rating_pct']:.0f})  model {r['model_val']:.2f} (p{r['model_pct']:.0f})  "
                          f"div {r['divergence']:+.0f}pp")
                except Exception as e:
                    print(f"  WARN conviction row {r.get('player_name', '?')}: "
                          f"{type(e).__name__}: {e} — skipped")
    if a.csv and frames:
        pd.concat(frames).to_csv(a.csv, index=False)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
