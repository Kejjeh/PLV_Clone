"""
sp_stuff_alert.py — rolling STUFF-DECLINE alert layer for SPs.

NOT a ranker. Stuff is a stable trait, so rolling Stuff+ adds little to RoS
ranking (see fg_pitch_modeling_inseason validation) — its value is as a RISK
monitor: a recent drop in fastball velocity or whiff rate flags fatigue, injury,
or arsenal trouble that a season-to-date average masks.

Method (per SP in the 2026 FG SP pool):
  recent  = last RECENT_DAYS of available pitch data
  baseline= 2026 pitches before that window
  metrics = fastball velo (FF/SI/FC mean) + whiff% (swinging_strike / pitches)
  flag DECLINE if velo drop >= VELO_DROP mph OR whiff drop >= WHIFF_DROP pp
  flag SURGE   on the symmetric upside (buy-low confirmation)

Velocity-anchored on purpose: that signal needs no stuff MODEL and is the
best-established injury/fatigue red flag. Data is whatever is in
data/raw/statcast_2026.parquet — run refresh_xfp_statcast.py first for currency.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_stuff_model import ownership_map, _norm  # noqa: E402

RECENT_DAYS = 21
VELO_DROP, WHIFF_DROP = 0.8, 3.0   # mph, percentage points
MIN_RECENT, MIN_BASE = 120, 200    # pitch-count floors per window
FB = ["FF", "SI", "FC"]


def window_metrics(g):
    fb = g[g["pitch_type"].isin(FB)]
    velo = fb["release_speed"].mean() if len(fb) >= 20 else np.nan
    whiff = (g["description"] == "swinging_strike").mean() * 100
    return pd.Series({"velo": velo, "whiff": whiff, "n": len(g)})


def main():
    sc = pd.read_parquet(ROOT / "data" / "raw" / "statcast_2026.parquet",
                         columns=["game_date", "release_speed", "pitch_type",
                                  "description", "pitcher"])
    sc["game_date"] = pd.to_datetime(sc["game_date"])
    asof = sc["game_date"].max()
    cut = asof - pd.Timedelta(days=RECENT_DAYS)
    print(f"Statcast through {asof.date()} | recent window = last {RECENT_DAYS}d "
          f"(>= {cut.date()}) vs season-to-{cut.date()} baseline.")
    if (pd.Timestamp.today() - asof).days > 7:
        print(f"  ** WARNING: statcast is {(pd.Timestamp.today()-asof).days}d stale "
              f"— run scripts/xfp/refresh_xfp_statcast.py --year 2026 for current form. **")

    # restrict to the 2026 SP pool (relevance) + names for ownership
    fg = pd.read_csv(ROOT / "data" / "research" / "fg_asof" / "fg_pit_2026_current.csv")
    fg["gs"] = pd.to_numeric(fg["gs"], errors="coerce")
    sp = fg[fg["gs"] >= 5][["mlb_id", "player_name_fg"]].dropna()
    sp_ids = set(sp["mlb_id"].astype(int))
    sc = sc[sc["pitcher"].isin(sp_ids)]

    rec = sc[sc["game_date"] >= cut].groupby("pitcher").apply(window_metrics, include_groups=False)
    base = sc[sc["game_date"] < cut].groupby("pitcher").apply(window_metrics, include_groups=False)
    m = base.join(rec, lsuffix="_base", rsuffix="_rec")
    m = m[(m["n_rec"] >= MIN_RECENT) & (m["n_base"] >= MIN_BASE)].copy()
    m["d_velo"] = m["velo_rec"] - m["velo_base"]
    m["d_whiff"] = m["whiff_rec"] - m["whiff_base"]
    m = m.reset_index().merge(sp, left_on="pitcher", right_on="mlb_id", how="left")

    own = ownership_map()
    m["own"] = m["player_name_fg"].map(lambda n: own.get(_norm(n), "FA")) if own else ""

    def tag(r):
        if (r.d_velo <= -VELO_DROP) or (r.d_whiff <= -WHIFF_DROP):
            return "DECLINE"
        if (r.d_velo >= VELO_DROP) and (r.d_whiff >= 0):
            return "SURGE"
        return "stable"
    m["flag"] = m.apply(tag, axis=1)

    has_own = (m["own"] != "").any()
    fmt = lambda r: (f"{str(r.player_name_fg):<22}{(r.own if has_own else ''):<16}"
                     f"{r.velo_base:>7.1f}{r.velo_rec:>7.1f}{r.d_velo:>+7.1f}"
                     f"{r.whiff_base:>8.1f}{r.whiff_rec:>7.1f}{r.d_whiff:>+8.1f}")
    hdr = (f"{'pitcher':<22}{('owner' if has_own else ''):<16}{'vBase':>7}{'vRec':>7}"
           f"{'dVelo':>7}{'whBase':>8}{'whRec':>7}{'dWhiff':>8}")
    for flag, title in [("DECLINE", "STUFF DECLINING (velo/whiff drop — injury/fatigue risk)"),
                        ("SURGE", "STUFF SURGING (velo up — buy-low confirmation)")]:
        sub = m[m["flag"] == flag].sort_values("d_velo", ascending=(flag == "DECLINE"))
        print(f"\n=== {title} ===")
        if sub.empty:
            print("  (none)"); continue
        print(hdr); print("-" * len(hdr))
        for _, r in sub.iterrows():
            print(fmt(r))


if __name__ == "__main__":
    main()
