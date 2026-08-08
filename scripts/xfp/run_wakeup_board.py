"""run_wakeup_board — which FA hitters are WAKING UP, early enough to matter.

THE PROBLEM THIS SOLVES
-----------------------
The instinct is to spot a breakout by watching home runs pile up. That instinct
is right about the direction and wrong about the instrument: HR rate needs
**275 PA** to reach forward r >= 0.50 — roughly half a season. By the time a HR
run is long enough to BE a signal, it has been true for months and the league
has already repriced him.

The same underlying change is visible far earlier in metrics that stabilize
fast (2026-07-29 stabilization studies, 126,434 batter-days / 1,929
player-seasons):

    bat speed        25-30 swings   (~1 week)   <- r=.905 by 87 swings
    hard-hit/barrel  50 BIP         (~3 weeks)
    K%               50 PA          (~2 weeks)
    xwOBA/PA         225 PA
    ISO              275 AB          <- too slow
    HR rate          275 PA          <- too slow

So this board is built on bat speed, contact quality and K%, and DELIBERATELY
EXCLUDES HR and ISO. They are printed for colour only, never ranked on.

THE INVERSION THIS BOARD REFUSES TO MAKE
----------------------------------------
Bat speed is the only process metric that adds forward-FP signal BEYOND a
hitter's own FP level (+0.076 partial r; K%/xwOBACON/HardHit%/BB% are
redundant once you know the FP level). But it must be read as a LEVEL, with the
YoY step as context — never as a delta ranking.

Sorting by delta alone surfaces the player washing out a slow start (Bichette
2026: +1.87 mph, 25th-pctile level) as "the riser" and the genuinely elite bat
(Cam Smith: +0.01 in-season on a 98th-pctile level, +3.10 YoY) as boring —
exactly backwards. Ranking here is LEVEL-FIRST; a step only promotes a player
who already has a level worth having. STEP-ONLY rows are surfaced but tagged as
the trap, never sorted to the top.

Deltas are gated at trend_signal's 80/200-swing minimums (a YoY delta carries
~sqrt(2)x a level's noise, so the level curve does NOT license relaxing them).

RULE 13: awareness/context only. Never moves rh3, and the "score" here ranks
ATTENTION, not forward FP — rh3 rank is printed alongside so the two are never
confused.

Usage
  python scripts/xfp/run_wakeup_board.py
  python scripts/xfp/run_wakeup_board.py --min-pa-vol 2.0 --top 25
  python scripts/xfp/run_wakeup_board.py --include-rostered   # league-wide
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from plv_clone.utils.name_match import safe_name_key as nk  # noqa: E402

# Sample minimums, in each metric's OWN denominator (2026-07-29 study).
MIN_BIP_CONTACT = 50      # hard-hit / barrel
MIN_PA_K = 50             # K%
# Bat-speed delta gates are trend_signal's own (80 current / 200 baseline
# swings); a level needs far fewer but the delta guard must not be relaxed.
MIN_SW_LEVEL = 80
MIN_SW_DELTA = 200

# A level worth acting on. Below this a positive step is the Bichette trap:
# real movement from a hole, landing somewhere unremarkable.
LEVEL_PCTL_FLOOR = 60
STEP_MPH = 0.75           # a YoY step big enough to call a step


def _load_bat_speed() -> pd.DataFrame:
    t = pd.read_csv(ROOT / "data/research/bat_speed_trending_2026.csv")
    t = t.rename(columns={"Unnamed: 0": "batter"})
    t["batter"] = pd.to_numeric(t["batter"], errors="coerce")
    t = t.dropna(subset=["batter"])
    t["batter"] = t["batter"].astype(int)
    t["bs_pctl"] = (t["bat_speed"].rank(pct=True) * 100).round()
    return t


def _load_contact() -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data/research/xfp_cache/batter_rolling_features.csv")
    idc = "batter" if "batter" in d.columns else "mlbam_id"
    return d.rename(columns={idc: "batter"})


def classify(row) -> tuple[str, float]:
    """(tag, attention_score). LEVEL-FIRST — a step never rescues a poor level.

    Returns one of:
      LEVEL+STEP   elite-ish bat that ALSO stepped up YoY — the real find
      LEVEL        elite-ish bat, flat YoY — already good, may be underowned
      STEP-ONLY    rose YoY but from a poor level — the documented trap
      THIN         not enough swings to read anything
    """
    lvl = row.get("bs_pctl")
    step = row.get("d_bat_speed")
    n_sw = row.get("n_sw") or 0
    if pd.isna(lvl) or n_sw < MIN_SW_LEVEL:
        return "THIN", -1.0
    has_step = (pd.notna(step) and n_sw >= MIN_SW_DELTA and step >= STEP_MPH)
    if lvl >= LEVEL_PCTL_FLOOR:
        if has_step:
            # level carries the ranking; the step is a bounded bonus so it can
            # never lift a mediocre level above a strong one
            return "LEVEL+STEP", float(lvl) + min(float(step), 3.0) * 5.0
        return "LEVEL", float(lvl)
    if has_step:
        return "STEP-ONLY", float(lvl) - 100.0   # surfaced, never near the top
    return "THIN", -1.0


def build(min_pa_vol: float, include_rostered: bool) -> pd.DataFrame:
    from app import espn_connector as ec
    league = ec._get_league()

    bs = _load_bat_speed()
    con = _load_contact()
    rh3 = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv")
    vol = pd.read_csv(ROOT / "data/outputs/xfp_volume_projections.csv")
    vidc = "batter" if "batter" in vol.columns else "mlbam_id"
    vol = vol.rename(columns={vidc: "batter"})

    df = (rh3[["batter", "player_name", "rank", "xfp_rh3_per_pa"]]
          .merge(bs, on="batter", how="left", suffixes=("", "_bs"))
          .merge(con[[c for c in con.columns if c in (
              "batter", "barrel_pct", "hard_hit_pct", "k_pct", "ev90",
              "barrel_pct_l21d", "hard_hit_pct_l21d", "k_pct_l21d",
              "xwoba_on_contact", "xwoba_on_contact_l21d")]],
              on="batter", how="left")
          .merge(vol[["batter", "proj_ros_pa_per_teamgame"]], on="batter", how="left"))

    # Availability — FAs only unless asked otherwise. percent_owned is national
    # data and is NEVER a substitute for a live roster scan (Connelly Early).
    rostered = {nk(n) for n in ec.get_all_teams()["player_name"]}
    fa = {nk(p.name) for p in league.free_agents(size=2000)}
    df["key"] = df["player_name"].map(nk)
    df["is_fa"] = df["key"].isin(fa) & ~df["key"].isin(rostered)
    if not include_rostered:
        df = df[df["is_fa"]]

    df = df[df["proj_ros_pa_per_teamgame"].fillna(0) >= min_pa_vol]
    tags = df.apply(classify, axis=1, result_type="expand")
    df["tag"], df["attention"] = tags[0], tags[1]
    return df[df["tag"] != "THIN"].sort_values("attention", ascending=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-pa-vol", type=float, default=2.0,
                    help="min projected PA per team-game (playing-time floor)")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--include-rostered", action="store_true",
                    help="league-wide instead of FA-only")
    a = ap.parse_args()

    df = build(a.min_pa_vol, a.include_rostered)
    print("=== WAKE-UP BOARD — fast-stabilizing signals only ===")
    print(f"  bat speed (25-30 sw) + contact quality (50 BIP) + K% (50 PA).")
    print(f"  HR and ISO are EXCLUDED: both need ~275 PA to stabilize, so a "
          f"HR run is a lagging\n  indicator by construction. Rule 13 — this "
          f"ranks ATTENTION, not forward FP.\n")

    for tag in ("LEVEL+STEP", "LEVEL", "STEP-ONLY"):
        sub = df[df["tag"] == tag].head(a.top)
        if sub.empty:
            continue
        blurb = {
            "LEVEL+STEP": "a bat that is already good AND stepped up YoY — the real find",
            "LEVEL": "already-elite bat, flat YoY — may simply be underowned",
            "STEP-ONLY": ("rose YoY but from a POOR level — the documented trap "
                          "(real movement, unremarkable destination)"),
        }[tag]
        print(f"--- {tag} — {blurb} ---")
        cols = ["player_name", "rank", "bat_speed", "bs_pctl", "d_bat_speed",
                "n_sw", "barrel_pct_l21d", "k_pct_l21d",
                "proj_ros_pa_per_teamgame"]
        out = sub[[c for c in cols if c in sub.columns]].copy()
        for c in ("bat_speed", "d_bat_speed", "proj_ros_pa_per_teamgame"):
            if c in out:
                out[c] = out[c].astype(float).round(2)
        for c in ("barrel_pct_l21d", "k_pct_l21d"):
            if c in out:
                out[c] = (out[c].astype(float) * 100).round(1)
        print(out.to_string(index=False), "\n")

    outp = ROOT / "data/outputs/hitter_wakeup_board.csv"
    df.to_csv(outp, index=False)
    print(f"wrote {outp}  ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
