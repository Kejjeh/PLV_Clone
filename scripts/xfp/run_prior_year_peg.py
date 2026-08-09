"""run_prior_year_peg — is he climbing back to last year, or falling back to it?

THE QUESTION THIS ANSWERS
-------------------------
Every other board in this repo ranks a player against the FIELD — rh3 rank,
replacement delta, RoS FP/game. That is the right frame for "who is better."
It is the wrong frame for "is this real," because it cannot see the one
baseline that matters for mean-reversion: **the player's own prior-year level.**

Two hitters can post identical recent FP/g and be moving in opposite
directions. On 2026-08-09 that was literally true:

  Caleb Durbin   0.747 fp/PA post-ASG vs a 0.606 2025 level  -> ABOVE
  Jarren Duran   0.489 fp/PA post-ASG vs a 0.532 2025 level  -> BELOW

Ranked by projection and recent production, Durbin won on every axis and three
lenses agreed (rh3 #66 vs #142, 3.36 vs 2.00 FP/g, the optimizer). Pegged to
their own baselines the order REVERSED: Durbin was outproducing a process that
had decayed (hard-hit 26.8 -> 20.5, whiff and SwStr both worse than 2025,
+0.037 overperformance gap), while Duran was underproducing a process that had
held (xwOBACON flat 0.389 -> 0.387, K% now BETTER than 2025, -0.022 bounce
owed). Production above a decaying process regresses; production below an
intact process recovers.

THE FOUR REGIMES
----------------
                        process supports it   process contradicts it
  above prior level     SUSTAINED             OVEREXTENDED  (sell / fade)
  below prior level     RECOVERING (buy)      STALLED

WHAT COUNTS AS EVIDENCE
-----------------------
Only metrics readable in the window, gated on their own denominators via
plv_clone.stabilization — chase (150 OOZ), zone-swing (150 IZ), whiff (150
swings), SwStr (150 pitches), K% (50 PA), hard-hit (50 BIP). HR and ISO need
~275 PA and are never evidence here; they are the lagging indicator this whole
approach exists to route around.

Two prior-anchored checks carry extra weight because they are validated:

  * **xwOBACON YoY stability** — the repo's hitter-recovery rule (memory
    gotcha #8): when xwOBACON is STABLE year over year, prior recoveries
    predict this one; when it declines every year (the Turner pattern),
    recovery hits a lower ceiling than prior troughs. This is the single
    strongest RECOVERING-vs-STALLED discriminator.
  * **expected-vs-actual wOBA** — a positive gap on an ABOVE-prior player is
    the OVEREXTENDED tell; a negative gap on a BELOW-prior player is owed
    bounce.

RULE 13: context/awareness only. This never moves rh3 and never re-ranks a
model. It answers "which direction is this player travelling relative to
himself," and hands the answer to the verdict layer.

Usage
  python scripts/xfp/run_prior_year_peg.py "Jarren Duran" "Caleb Durbin"
  python scripts/xfp/run_prior_year_peg.py --roster
  python scripts/xfp/run_prior_year_peg.py --since 2026-06-01 "Bo Bichette"
"""
from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from plv_clone.stabilization import HITTER_MINS          # noqa: E402
from plv_clone.utils.name_match import resolve_batter_id  # noqa: E402
from run_window_split import MISS, SWING, resolve_asg_break  # noqa: E402

MULTIYR = ROOT / "data/research/xfp_cache/hitters_multiyr_2015_2026.csv"
STATCAST = ROOT / "data/research/xfp_cache/statcast_2026.parquet"

#: metric -> (+1 if higher is better, prior-year column in the multiyr cache)
METRICS = {
    "k_pct":    (-1, "k_pct"),
    "chase":    (-1, "chase_pct"),
    "zswing":   (+1, "z_swing_pct"),
    "whiff":    (-1, "whiff_pct"),
    "swstr":    (-1, "swstr_pct"),
    "hard_hit": (+1, "hard_hit_pct"),
}
#: fp/PA move (in either direction) below this is noise, not a regime
FLAT_BAND = 0.030

#: Per-metric NOISE FLOOR in percentage points: a delta smaller than this does
#: not vote in either direction. Set at 0.25 x the metric's own cross-player SD
#: on the 2026 panel (>=200 PA) — scaled per metric because their spreads差 by
#: more than 2x (hard-hit SD 7.9pp vs SwStr 3.5pp), so one uniform floor would
#: be simultaneously too strict for SwStr and too loose for hard-hit.
#:
#: Without this the vote counted NOISE AS EVIDENCE. Canonical (Eugenio Suárez,
#: 2026-08-09): chase -0.3pp and SwStr -0.0pp were both scored as "toward prior
#: level" and outvoted a +10.6pp K% collapse, returning RECOVERING for a hitter
#: every other lens had as a hard FADE. Magnitude has to clear noise before a
#: direction means anything.
NOISE_FLOOR_PP = {
    "k_pct": 1.56, "chase": 1.49, "zswing": 1.41,
    "whiff": 1.62, "swstr": 0.87, "hard_hit": 1.96,
}


@functools.lru_cache(maxsize=1)
def _boxscores() -> pd.DataFrame:
    """Hitter boxscore store, read once per process."""
    box = pd.read_parquet(ROOT / "data/research/xfp_cache/boxscore_hitters.parquet",
                          columns=["game_date", "mlbam_id", "fp_h"])
    box["game_date"] = pd.to_datetime(box["game_date"])
    return box


def window_metrics(d: pd.DataFrame) -> dict:
    """(metric -> (value, denominator)) for one pitch-level slice."""
    inz = d["zone"].between(1, 9)
    ooz = ~inz
    sw = d["description"].isin(SWING)
    miss = d["description"].isin(MISS)
    pa = d["events"].notna()
    bip = d[d["launch_speed"].notna() & d["events"].notna()]
    pct = lambda n, dn: (100.0 * n / dn) if dn else None      # noqa: E731
    out = {
        "chase": (pct((sw & ooz).sum(), ooz.sum()), int(ooz.sum())),
        "zswing": (pct((sw & inz).sum(), inz.sum()), int(inz.sum())),
        "whiff": (pct(miss.sum(), sw.sum()), int(sw.sum())),
        "swstr": (pct(miss.sum(), len(d)), int(len(d))),
        "k_pct": (pct((d["events"] == "strikeout").sum(), pa.sum()), int(pa.sum())),
        "hard_hit": ((100.0 * (bip["launch_speed"] >= 95).mean()) if len(bip) else None,
                     len(bip)),
    }
    return out


#: |xwOBACON YoY| under this reads as STABLE contact quality
XC_STABLE_BAND = 0.015


def classify(fp_gap: float, support: int, oppose: int,
             xc_yoy: float | None = None) -> tuple[str, str]:
    """(regime, one-line meaning) from the fp/PA gap, the process vote, and —
    ONLY to break a tied vote — xwOBACON YoY stability.

    The process vote counts only READABLE metrics that clear their noise floor,
    and counts them relative to the PRIOR YEAR — not to earlier this season. A
    player can be improving on his own bad first half and still be far below
    the level he needs to reach.

    xwOBACON is the tie-break rather than an ordinary vote because it is the
    VALIDATED recovery-template condition (memory gotcha #8): stable contact
    quality means prior recoveries predict this one, while contact declining
    every year (the Turner pattern) means the ceiling sits BELOW prior troughs.
    Documenting it as "the strongest discriminator" and then leaving it out of
    the classification — as this function originally did — let a 2/2 tie decide
    a verdict the strongest signal could already settle (Jarren Duran,
    2026-08-09: tied vote, xwOBACON flat at -0.002, so the recovery template
    applies and STALLED was the wrong call).

    Direction still comes from production alone; neither the vote nor the
    tie-break can move a player across the above/below line.
    """
    if abs(fp_gap) < FLAT_BAND:
        return "AT-LEVEL", "producing at his prior-year level"
    if fp_gap > 0:
        if support > oppose:
            return "SUSTAINED", "above prior level, and the process backs it"
        return "OVEREXTENDED", ("above prior level on a process that has NOT "
                                "improved — regression risk")
    if support > oppose:
        return "RECOVERING", "below prior level, but the process is climbing back"
    if support == oppose and xc_yoy is not None and abs(xc_yoy) < XC_STABLE_BAND:
        return "RECOVERING", ("below prior level on a tied process vote, but "
                              "contact quality held YoY — the validated "
                              "recovery-template condition")
    return "STALLED", "below prior level with no process recovery yet"


def peg(name: str, team: str | None, since: str, prior_year: int, cur_year: int,
        multiyr: pd.DataFrame, sc: pd.DataFrame) -> dict | None:
    pid = resolve_batter_id(name, team=team)
    if pid is None:
        return {"name": name, "error": "unresolved (pass --team for a collision)"}
    prior = multiyr[(multiyr["batter"] == pid) & (multiyr["year"] == prior_year)]
    cur = multiyr[(multiyr["batter"] == pid) & (multiyr["year"] == cur_year)]
    if prior.empty:
        return {"name": name, "error": f"no {prior_year} baseline (rookie / no MLB time)"}
    p, c = prior.iloc[0], (cur.iloc[0] if not cur.empty else None)

    d = sc[sc["batter"] == pid]
    win = d[d["game_date"] >= since]
    if win.empty:
        return {"name": name, "error": f"no {cur_year} pitches since {since}"}
    wm = window_metrics(win)

    n_pa = wm["k_pct"][1]
    fp_prior = float(p["fp_per_pa_actual"])
    # window fp/PA from the boxscore store (BrownU FP, same unit as the cache).
    # Cached: this used to re-read the parquet PER PLAYER, which is invisible on
    # a two-name compare and quadratic-feeling on a 150-name cohort sweep.
    box = _boxscores()
    g = box[(box["mlbam_id"] == pid) & (box["game_date"] >= since)]
    fp_win = (g["fp_h"].sum() / n_pa) if n_pa else float("nan")

    rows, support, oppose = [], 0, 0
    for met, (sign, prior_col) in METRICS.items():
        val, denom = wm[met]
        need, unit = HITTER_MINS[met]
        pv = float(p[prior_col]) * 100.0
        if val is None or denom < need:
            rows.append((met, pv, val, None, f"UNDER ({denom} of {need} {unit})"))
            continue
        delta = val - pv                      # window MINUS prior year
        if abs(delta) < NOISE_FLOOR_PP[met]:
            rows.append((met, pv, val, delta, "flat"))
            continue
        toward = sign * delta > 0
        if toward:
            support += 1
        else:
            oppose += 1
        rows.append((met, pv, val, delta, "toward" if toward else "away"))

    xc_prior = float(p["xwoba_on_contact"])
    xc_cur = float(c["xwoba_on_contact"]) if c is not None else float("nan")
    xw_cur = float(c["xwoba_per_pa"]) if c is not None else float("nan")
    regime, meaning = classify(fp_win - fp_prior, support, oppose,
                               xc_yoy=xc_cur - xc_prior)
    return {
        "name": name, "mlbam": pid, "n_pa": n_pa,
        "fp_prior": fp_prior, "fp_win": fp_win, "fp_gap": fp_win - fp_prior,
        "xc_prior": xc_prior, "xc_cur": xc_cur, "xc_yoy": xc_cur - xc_prior,
        "xwoba_cur": xw_cur, "rows": rows,
        "support": support, "oppose": oppose,
        "regime": regime, "meaning": meaning,
    }


def render(r: dict, prior_year: int, since: str) -> None:
    if r.get("error"):
        print(f"\n=== {r['name']} — {r['error']} ===")
        return
    print(f"\n=== {r['name']} — pegged to {prior_year} "
          f"(window from {since}, {r['n_pa']} PA) ===")
    print(f"  fp/PA   {prior_year}: {r['fp_prior']:.3f}   window: {r['fp_win']:.3f}   "
          f"gap: {r['fp_gap']:+.3f}")
    print(f"  {'metric':10s} {prior_year:>8d} {'window':>8s} {'delta':>8s}   direction")
    for met, pv, val, delta, note in r["rows"]:
        if delta is None:
            print(f"  {met:10s} {pv:8.1f} {'—':>8s} {'—':>8s}   NOT READABLE ({note})")
        elif note == "flat":
            print(f"  {met:10s} {pv:8.1f} {val:8.1f} {delta:+8.1f}   flat "
                  f"(< {NOISE_FLOOR_PP[met]:.2f}pp floor — no vote)")
        else:
            print(f"  {met:10s} {pv:8.1f} {val:8.1f} {delta:+8.1f}   {note} prior level")
    stab = ("STABLE" if abs(r["xc_yoy"]) < 0.015
            else ("DECLINING" if r["xc_yoy"] < 0 else "RISING"))
    print(f"  xwOBACON  {prior_year}: {r['xc_prior']:.3f} -> season {r['xc_cur']:.3f}"
          f"  ({r['xc_yoy']:+.3f}, {stab})")
    # The SAME xwOBACON reading means opposite things by direction, so never
    # print one gloss for both. Stable contact under a player who is BELOW his
    # level is the recovery-template condition; stable contact under a player
    # ABOVE his level says the extra output is not coming from better contact.
    below = r["fp_gap"] < 0
    if stab == "STABLE":
        print("    -> contact quality held YoY: "
              + ("prior recoveries are a valid template" if below
                 else "the surplus is NOT coming from better contact"))
    elif stab == "DECLINING":
        print("    -> contact quality eroding YoY: "
              + ("recovery ceiling is BELOW prior troughs (Turner pattern)" if below
                 else "output is running ahead of decaying contact — regression risk"))
    else:
        print("    -> contact quality RISING YoY: "
              + ("a real skill gain under the slump" if below
                 else "the surplus has contact support"))
    print(f"  process vote (readable only): {r['support']} toward / {r['oppose']} away")
    print(f"  >> {r['regime']} — {r['meaning']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--team", default=None, help="team hint for a colliding name")
    ap.add_argument("--since", default="asg",
                    help="'asg' (default) or YYYY-MM-DD — start of the window")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--prior", type=int, default=None, help="baseline year (default: year-1)")
    ap.add_argument("--roster", action="store_true", help="peg the whole live roster")
    a = ap.parse_args()

    prior_year = a.prior if a.prior is not None else a.year - 1
    since = a.since
    if since == "asg":
        # returns the first game-day AFTER the break (derived, not hardcoded)
        since = str(resolve_asg_break(a.year))

    names = list(a.names)
    if a.roster:
        from app.espn_connector import get_my_roster_with_injuries
        names += [r["player_name"] for _, r in get_my_roster_with_injuries().iterrows()]
    if not names:
        ap.error("pass player names or --roster")

    multiyr = pd.read_csv(MULTIYR)
    sc = pd.read_parquet(STATCAST, columns=["game_date", "batter", "zone",
                                            "description", "events", "launch_speed"])
    sc["game_date"] = pd.to_datetime(sc["game_date"])

    print("=== PRIOR-YEAR PEG — direction relative to the player's OWN baseline ===")
    print("    Ranks answer 'who is better'. This answers 'which way is he going'.")
    print("    HR/ISO are never evidence here (275 PA to stabilize); only readable")
    print("    metrics vote, gated on their own denominators.")
    out = []
    for nm in names:
        r = peg(nm, a.team, since, prior_year, a.year, multiyr, sc)
        if r:
            out.append(r)
            render(r, prior_year, since)

    good = [r for r in out if not r.get("error")]
    if len(good) > 1:
        print("\n=== SUMMARY ===")
        print(f"  {'player':22s} {'gap vs prior':>13s} {'vote':>7s}  regime")
        for r in sorted(good, key=lambda x: -x["fp_gap"]):
            print(f"  {r['name']:22s} {r['fp_gap']:+13.3f} "
                  f"{r['support']}/{r['oppose']:>5}  {r['regime']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
