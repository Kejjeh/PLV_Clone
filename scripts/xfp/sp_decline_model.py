"""
sp_decline_model.py — SP rest-of-season FP DECLINE-RISK board.

The "catch a Framber before the results crater" lens. Complements:
  /sp-stuff-board  -> the MEAN level (Stuff+-anchored RoS FP projection)
  /sp-floor        -> per-START bust probability (downside of a single game)
  THIS             -> RoS DECLINE risk (results regressing DOWN toward the
                      whiff/K *level* they're not yet backed by)

VALIDATED SIGNAL (data/research/validation_runs/sp_decline_stuff_decay_2026-06-13.md):
  The reliable forward-decline predictor is the CURRENT-SEASON whiff/K
  LEVEL, NOT the in-season change/decay.
    swstr_z_pop (SwStr% level)  partial-r +0.235 over the to-date FP base
    k_z_pop     (K%    level)   partial-r +0.234, AUC ~0.72
    velo_recent (FB velo level) partial-r +0.16  (light third lens)
  REJECTED as noise (do NOT use): within-season recency *deltas* of
  whiff/K/velo (L21-to-date, all partial-r <0.05, ΔAUC~0); contact-quality;
  archetype; age. The decay-delta framing is the seductive-but-noisy version.

The actionable read = the LEVEL-vs-FP GAP. When an SP's whiff/K *level*
sits LOW (low percentile) but his FP/results are still propped up (high FP
percentile), his RoS FP is likely to regress DOWN toward the whiff/K-implied
level. That is the Framber Valdez 2026 pattern (K% 18.6% / SwStr 9.1% =
below-average levels while results hadn't fully cratered).

Headline number here is the DECLINE risk (decline_gap + level percentile),
NOT a point projection. Single-lens risk board — feed picks into /triangulate.

CLI:
  python sp_decline_model.py                 # league-wide decline board + MINE/opp/FA
  python sp_decline_model.py --players "A,B" # focus list
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_stuff_model import (  # noqa: E402  reuse validated loaders + ownership two-pass
    load_2026, ownership_map, own_tag, brownu_fp_per_start, MIN_GS, _norm,
)

ROOT = Path(__file__).resolve().parents[2]
ROLLING = ROOT / "data" / "research" / "xfp_cache" / "rolling_pitchers_2018_2026.csv"

# stuff_level weighting per backtest: whiff/K dominate (~0.23 each), velo light (~0.16).
W_SWSTR, W_K, W_VELO = 0.40, 0.40, 0.20

# Tier thresholds (explicit + defensible; percentiles within the 2026 SP pool).
# The VALIDATED predictor is the whiff/K LEVEL itself (partial-r +0.235 over the
# to-date FP base), so a below-average whiff/K LEVEL is the primary decline gate —
# NOT only the gap. The gap is the *severity* dial: a low-stuff arm whose FP is
# still propped above his stuff (gap>0) is the highest-risk "hasn't fallen yet"
# case (Framber pattern); a low-stuff arm whose FP has ALREADY dropped to its
# level is still a decline candidate (the level predicts continued RoS regression),
# just further along. We flag both; the board sorts by gap so the still-propped
# ones surface at the top.
#   DECLINE-RISK : below-average whiff/K LEVEL (lvlPct<=LOW) AND FP not yet below it
#                  (gap>=GAP_DECLINE) — i.e. stuff is weak and results haven't (fully)
#                  caught down.
#   RISING       : whiff/K LEVEL is well ahead of FP (sustainable / buy-low-safe).
#   STABLE       : otherwise (incl. strong-stuff arms — their level supports the FP).
LOW_LEVEL_PCTL = 45.0    # stuff_level at/below the pool's 45th pctl = below-average stuff
GAP_DECLINE    = -10.0   # include arms already mid-crater (FP up to 10pts under level)
GAP_RISING     = -20.0   # stuff level sits >=20 pts above FP percentile


def _load_velo_2026() -> pd.DataFrame:
    """Latest-split-day cumulative FB velo per 2026 SP, keyed by mlb_id.

    Velo is the light third lens; SwStr%/K% (from the FG current CSV) are the
    two dominant signals. Missing velo simply drops out of the blend.
    """
    try:
        r = pd.read_csv(ROLLING, usecols=["pitcher", "year", "split_day", "avg_velo_to"])
    except Exception:
        return pd.DataFrame(columns=["mlb_id", "avg_velo_to"])
    r = r[r["year"] == 2026]
    if r.empty:
        return pd.DataFrame(columns=["mlb_id", "avg_velo_to"])
    latest = r.sort_values("split_day").groupby("pitcher").tail(1)
    return latest.rename(columns={"pitcher": "mlb_id"})[["mlb_id", "avg_velo_to"]]


def _decline_tier(level_pctl: float, gap: float) -> str:
    if level_pctl <= LOW_LEVEL_PCTL and gap >= GAP_DECLINE:
        return "DECLINE-RISK"
    if gap <= GAP_RISING:
        return "RISING"
    return "STABLE"


def build():
    """Return (DataFrame of 2026 SPs with decline diagnostics, n_pool)."""
    d = load_2026().copy()  # gs>=MIN_GS, has swstr_pct / k_pct / pre_fp
    d = d.dropna(subset=["swstr_pct", "k_pct", "pre_fp"]).copy()

    velo = _load_velo_2026()
    d = d.merge(velo, on="mlb_id", how="left")

    # percentile-rank within the 2026 SP pool (higher pctl = better/more FP)
    d["swstr_pctl"] = d["swstr_pct"].rank(pct=True) * 100
    d["k_pctl"]     = d["k_pct"].rank(pct=True) * 100
    d["velo_pctl"]  = d["avg_velo_to"].rank(pct=True) * 100
    d["curfp_pctl"] = d["pre_fp"].rank(pct=True) * 100

    # combined whiff/K stuff LEVEL percentile (velo light, only where present)
    has_v = d["velo_pctl"].notna()
    base_lvl = (W_SWSTR * d["swstr_pctl"] + W_K * d["k_pctl"]) / (W_SWSTR + W_K)
    full_lvl = W_SWSTR * d["swstr_pctl"] + W_K * d["k_pctl"] + W_VELO * d["velo_pctl"]
    d["stuff_level_pctl"] = np.where(has_v, full_lvl, base_lvl)

    # the actionable gap: FP percentile sitting ABOVE the whiff/K stuff level
    d["decline_gap"] = d["curfp_pctl"] - d["stuff_level_pctl"]
    d["tier"] = [
        _decline_tier(lp, g) for lp, g in zip(d["stuff_level_pctl"], d["decline_gap"])
    ]

    own = ownership_map()
    team_col = next((c for c in ("team", "Team", "tm", "Tm", "team_fg") if c in d.columns), None)
    d["own"] = (
        d.apply(lambda r: own_tag(own, r["player_name_fg"],
                                  r[team_col] if team_col else None), axis=1)
        if own else ""
    )
    return d, len(d)


def _fmt_row(r, has_own):
    owner = (r.own if has_own else str(r.get("team", "")))[:15]
    velo = f"{r.avg_velo_to:>6.1f}" if pd.notna(r.avg_velo_to) else f"{'--':>6}"
    return (f"{r.player_name_fg:<20}{owner:<16}{int(r.gs):>3}"
            f"{r.k_pct*100:>6.1f}{r.swstr_pct*100:>7.1f}{velo}"
            f"{r.stuff_level_pctl:>7.0f}{r.curfp_pctl:>7.0f}{r.decline_gap:>+7.0f}  {r.tier}")


HDR = (f"{'pitcher':<20}{'owner':<16}{'GS':>3}{'K%':>6}{'SwStr':>7}{'velo':>6}"
       f"{'lvlPct':>7}{'fpPct':>7}{'gap':>7}  tier")


def _print_board(d, has_own):
    print(HDR); print("-" * len(HDR))
    for _, r in d.iterrows():
        print(_fmt_row(r, has_own))


def main(players: list[str] | None = None):
    d, n = build()
    has_own = (d["own"] != "").any()
    print(f"2026 SP pool: {n} (>= {MIN_GS} GS). Decline risk = LOW whiff/K LEVEL "
          f"+ FP propped above it (validated 2026-06-13, partial-r ~0.235).")
    print(f"Tiers: DECLINE-RISK (lvlPct<={LOW_LEVEL_PCTL:.0f} & gap>={GAP_DECLINE:+.0f}) | "
          f"RISING (gap<={GAP_RISING:.0f}) | STABLE. Single-lens -> feed into /triangulate.\n")

    if players:
        want = {_norm(p) for p in players}
        sub = d[d["player_name_fg"].map(lambda x: _norm(x) in want)]
        miss = want - {_norm(x) for x in sub["player_name_fg"]}
        print(f"=== FOCUS LIST ({len(sub)} found) ===")
        _print_board(sub.sort_values("decline_gap", ascending=False), has_own)
        if miss:
            print(f"\n  not in pool (no FG row / < {MIN_GS} GS): {sorted(miss)}")
        return

    risk = d[d["tier"] == "DECLINE-RISK"].sort_values("decline_gap", ascending=False)
    print(f"=== DECLINE-RISK BOARD (league-wide, {len(risk)}) — top of list = most propped ===")
    _print_board(risk, has_own)

    if has_own:
        mine = d[d["own"] == "MINE"].sort_values("decline_gap", ascending=False)
        print(f"\n=== YOUR SP STAFF ({len(mine)}) — ranked by decline risk (gap desc) ===")
        _print_board(mine, has_own)
        mine_risk = mine[mine["tier"] == "DECLINE-RISK"]
        if len(mine_risk):
            print(f"  FADE WATCH: {', '.join(mine_risk.player_name_fg)} "
                  f"— whiff/K level says RoS FP regresses down. Cross-check /sp-stuff-board §2.")

        fa_risk = d[(d["own"] == "FA") & (d["tier"] == "DECLINE-RISK")]
        print(f"\n=== FA DECLINE-RISK ({len(fa_risk)}) — do NOT stream these; results are propped ===")
        _print_board(fa_risk.sort_values("decline_gap", ascending=False).head(12), has_own)

    rising = d[d["tier"] == "RISING"].sort_values("decline_gap").head(12)
    print(f"\n=== RISING (whiff/K level AHEAD of FP — sustainable / buy-low-safe) ===")
    _print_board(rising, has_own)


if __name__ == "__main__":
    args = sys.argv[1:]
    plist = None
    if "--players" in args:
        i = args.index("--players")
        if i + 1 < len(args):
            plist = [p.strip() for p in args[i + 1].split(",") if p.strip()]
    main(plist)
