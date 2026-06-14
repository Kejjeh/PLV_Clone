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

  SUPPLEMENTARY FLAG (data/research/validation_runs/velo_signal_2026-06-13.md):
  YEAR-OVER-YEAR velo loss (current cumulative velo vs PRIOR-season-END velo) is
  a DISTINCT, validated leading-decline construct — NOT the rejected within-season
  L21 delta, and orthogonal to the velo LEVEL already in the blend. Monotonic
  forward-FP gradient (gain +0.5 -> 11.32; loss >=1.5 mph -> 9.44) + bust-risk tilt
  (partial-r -0.090 over the level base; OOS bust-AUC beats stuff WITHIN the
  high-Stuff cohort, where stuff alone is ~useless at 0.519). Surfaced as the
  vYoY ▼/▼▼/▲ FLAG only — it RAISES decline conviction and is a /sp-floor tilt,
  but does NOT move the validated whiff/K-level headline (lens_value_add_2026-06-11).

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


# YoY velo-loss flag thresholds (validated velo_signal_2026-06-13.md).
# Year-over-year velo loss vs PRIOR-season-end is a LEADING decline construct,
# distinct from the velo LEVEL already in the blend and from the (rejected)
# within-season L21 delta. Monotonic forward-FP gradient (gain +0.5 -> 11.32 FP;
# loss >=1.5 -> 9.44) and a bust-risk tilt (partial-r -0.090 over the level base,
# OOS bust-AUC beats stuff WITHIN the high-Stuff cohort). Surfaced as a FLAG only,
# NOT folded into the validated whiff/K-level headline (lens_value_add_2026-06-11).
VELO_YOY_SOFT = -0.7    # >= this much below 2025 season-end velo -> 'velo v' soft fade
VELO_YOY_HARD = -1.5    # >= this much -> 'velo VV' warn (worst forward-FP band)
VELO_YOY_RISE = 0.5     # gaining velo vs last year -> mild tailwind

# In-season velo-drop flag (validated velo_signal_2026-06-13.md, cutoff slice).
# The within-season drop is the construct the decline backtest REJECTED — but only
# because it pooled noisy 1-start samples. Conditioned correctly it is a PEER of YoY:
#   * measured vs the pitcher's own SEASON-PEAK cumulative velo (not warmup-confounded
#     early-season, not the self-contaminated to-date),
#   * GATED on BF in the L21 window. Signal climbs monotonically with the gate
#     (>=40 BF +0.060 -> >=80 +0.084 -> >=100 +0.102); 80 BF is the signal/coverage
#     knee (n=9263). Below it -> noise (<25 BF partial-r -0.002, INVERTED bust gap).
#     Most potent before ~Aug (a drop needs RoS runway). Relative-% adds nothing over
#     absolute mph (+0.076 vs +0.075). Persistence adds nothing over the gate.
# Coverage complement to YoY: fires for arms with no 2025 velo (rookies / post-TJ).
VELO_IN_BF_GATE = 80    # min batters faced in L21 (sweep knee — cleaner than 75)
VELO_IN_SOFT = -0.5     # bust STEPS at ~-0.5 off season-peak (27% -> 34%) -> 'vIn v'
VELO_IN_HARD = -1.5     # FP-severity tail (down to 9.67 FP by -2 mph) -> 'vIn VV'

# DOUBLE-FADE escalation (cutoff E): YoY drop AND in-season drop both firing is the
# strongest cutoff found — forward FP 9.02 / bust 49.5% (2.1x the no-drop 23.1%),
# far beyond either flag alone. Tagged SEVERE.
# LOW-VELO tilt (cutoff D): a velo drop bites ~2x harder for sub-median-velo (finesse)
# arms (bust +13.3pp vs +5.4pp for high-velo) — no margin. Escalated below the pool
# median velo.

# MULTI-YEAR fade (cutoff K): the 2-year velo Δ (vs 2-years-ago season-end) is the
# single STRONGEST velo construct — partial-r +0.175 vs +0.101 for 1-year. A sustained
# two-season downtrend filters single-year blips and captures genuine erosion/aging.
# Slow (updates yearly) + lower coverage (needs two prior seasons), so it's a
# high-conviction confirming flag, not a primary trigger.
VELO_2Y_SOFT = -1.0     # >= this much below 2024 season-end -> 'v2y v' sustained fade
VELO_2Y_HARD = -2.0     # >= this much -> 'v2y VV' steep multi-year erosion


def _load_velo_2026() -> pd.DataFrame:
    """Latest-split-day 2026 velo diagnostics per SP, keyed by mlb_id:
      avg_velo_to  — cumulative FB velo LEVEL (the light third lens in the blend)
      velo_yoy / velo_flag — current vs PRIOR-year (2025) season-end (leading flag)
      velo_in / velo_in_flag — current L21 vs 2026 SEASON-PEAK, gated >=80 BF L21
                               (in-season sustained drop; coverage complement to YoY)
      velo_2y / velo_2y_flag — current vs 2-YEARS-AGO (2024) season-end (strongest
                               construct, partial-r +0.175; slow/lower coverage)
    Missing velo simply drops out of the blend / flags.
    """
    cols = ["pitcher", "year", "split_day", "avg_velo_to", "avg_velo_last21", "tbf_last21"]
    out_cols = ["mlb_id", "avg_velo_to", "velo_yoy", "velo_flag",
                "velo_in", "velo_in_flag", "velo_2y", "velo_2y_flag"]
    try:
        r = pd.read_csv(ROLLING, usecols=cols)
    except Exception:
        return pd.DataFrame(columns=out_cols)
    cur = r[r["year"] == 2026].sort_values("split_day").copy()
    if cur.empty:
        return pd.DataFrame(columns=out_cols)
    # running SEASON-PEAK cumulative velo per pitcher (as-of, no leakage)
    cur["peak_velo_to"] = cur.groupby("pitcher")["avg_velo_to"].cummax()
    latest = (cur.groupby("pitcher").tail(1)
              .rename(columns={"pitcher": "mlb_id"})
              [["mlb_id", "avg_velo_to", "avg_velo_last21", "tbf_last21", "peak_velo_to"]])

    def _season_end(yr, name):
        s = r[r["year"] == yr]
        if s.empty:
            return None
        return (s.sort_values("split_day").groupby("pitcher").tail(1)
                .rename(columns={"pitcher": "mlb_id", "avg_velo_to": name})[["mlb_id", name]])

    # --- YoY flag (vs 2025 season-end) ---
    p25 = _season_end(2025, "velo_2025")
    if p25 is not None:
        latest = latest.merge(p25, on="mlb_id", how="left")
        latest["velo_yoy"] = latest["avg_velo_to"] - latest["velo_2025"]
    else:
        latest["velo_yoy"] = np.nan
    latest["velo_flag"] = latest["velo_yoy"].map(_velo_flag)
    # --- in-season drop flag (L21 vs season-peak, gated on L21 sample) ---
    drop = latest["avg_velo_last21"] - latest["peak_velo_to"]
    latest["velo_in"] = np.where(latest["tbf_last21"] >= VELO_IN_BF_GATE, drop, np.nan)
    latest["velo_in_flag"] = latest["velo_in"].map(_velo_in_flag)
    # --- multi-year fade (vs 2024 season-end) — strongest construct (cutoff K) ---
    p24 = _season_end(2024, "velo_2024")
    if p24 is not None:
        latest = latest.merge(p24, on="mlb_id", how="left")
        latest["velo_2y"] = latest["avg_velo_to"] - latest["velo_2024"]
    else:
        latest["velo_2y"] = np.nan
    latest["velo_2y_flag"] = latest["velo_2y"].map(_velo_2y_flag)
    return latest[out_cols]


def _velo_flag(yoy: float) -> str:
    if pd.isna(yoy):
        return ""
    if yoy <= VELO_YOY_HARD:
        return "VV"   # >=1.5 mph below last year -> strong fade tilt
    if yoy <= VELO_YOY_SOFT:
        return "v"    # soft fade
    if yoy >= VELO_YOY_RISE:
        return "^"    # gaining velo -> mild tailwind
    return ""


def _velo_in_flag(drop: float) -> str:
    """In-season drop off season-peak (already gated to >=80 BF L21 in the loader)."""
    if pd.isna(drop):
        return ""
    if drop <= VELO_IN_HARD:
        return "VV"
    if drop <= VELO_IN_SOFT:
        return "v"
    return ""


def _velo_2y_flag(two_yr: float) -> str:
    """Sustained 2-year velo decline vs 2024 season-end (strongest construct)."""
    if pd.isna(two_yr):
        return ""
    if two_yr <= VELO_2Y_HARD:
        return "VV"
    if two_yr <= VELO_2Y_SOFT:
        return "v"
    return ""


def _decline_tier(level_pctl: float, gap: float) -> str:
    if level_pctl <= LOW_LEVEL_PCTL and gap >= GAP_DECLINE:
        return "DECLINE-RISK"
    if gap <= GAP_RISING:
        return "RISING"
    return "STABLE"


def _build_core():
    """Decline diagnostics for the 2026 SP pool WITHOUT the (slow, live) ESPN
    ownership join. Returns the DataFrame. Reused by build() (which appends
    ownership) and by decline_lens_map() (the lightweight join helper that other
    skills — e.g. /triangulate — import to surface the velo/decline lens)."""
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

    # --- velo composite reads (cutoffs D + E, velo_signal_2026-06-13.md) ---
    yoy_dn = d["velo_flag"].isin(["VV", "v"])
    in_dn = d["velo_in_flag"].isin(["VV", "v"])
    # (E) DOUBLE-FADE: both lines drop -> 49.5% bust / 9.02 FP (2.1x base). SEVERE.
    d["velo_double"] = yoy_dn & in_dn
    # (D) LOW-VELO tilt: a drop bites ~2x harder for sub-(pool-)median-velo arms.
    velo_med = d["avg_velo_to"].median()
    d["velo_lowtilt"] = (yoy_dn | in_dn) & (d["avg_velo_to"] < velo_med)
    d["velo_severity"] = np.where(
        d["velo_double"], "SEVERE",
        np.where(d["velo_lowtilt"], "LOW-VELO", ""))
    return d


def build():
    """Return (DataFrame of 2026 SPs with decline diagnostics + ownership, n_pool)."""
    d = _build_core()
    own = ownership_map()
    team_col = next((c for c in ("team", "Team", "tm", "Tm", "team_fg") if c in d.columns), None)
    d["own"] = (
        d.apply(lambda r: own_tag(own, r["player_name_fg"],
                                  r[team_col] if team_col else None), axis=1)
        if own else ""
    )
    return d, len(d)


_LENS_CACHE = None


def decline_lens_map():
    """Public join helper for other skills (parallel of rp_decline.tier_map()).

    Returns {mlb_id(int): {tier, decline_gap, stuff_level_pctl, velo_yoy, velo_flag,
    velo_in, velo_in_flag, velo_2y, velo_2y_flag, velo_double, velo_severity}} for
    every 2026 SP (>=MIN_GS GS). No ESPN call. Cached per-process; degrades to {}
    if the pool/rolling cache is unavailable so callers never break."""
    global _LENS_CACHE
    if _LENS_CACHE is not None:
        return _LENS_CACHE
    try:
        d = _build_core()
    except Exception:
        _LENS_CACHE = {}
        return _LENS_CACHE
    out = {}
    for _, r in d.iterrows():
        mid = r.get("mlb_id")
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            continue
        out[mid] = {
            "tier": r.get("tier"),
            "decline_gap": float(r["decline_gap"]) if pd.notna(r.get("decline_gap")) else None,
            "stuff_level_pctl": float(r["stuff_level_pctl"]) if pd.notna(r.get("stuff_level_pctl")) else None,
            "velo_yoy": float(r["velo_yoy"]) if pd.notna(r.get("velo_yoy")) else None,
            "velo_flag": r.get("velo_flag") or "",
            "velo_in": float(r["velo_in"]) if pd.notna(r.get("velo_in")) else None,
            "velo_in_flag": r.get("velo_in_flag") or "",
            "velo_2y": float(r["velo_2y"]) if pd.notna(r.get("velo_2y")) else None,
            "velo_2y_flag": r.get("velo_2y_flag") or "",
            "velo_double": bool(r.get("velo_double")),
            "velo_severity": r.get("velo_severity") or "",
        }
    _LENS_CACHE = out
    return out


def _fmt_row(r, has_own):
    owner = (r.own if has_own else str(r.get("team", "")))[:15]
    velo = f"{r.avg_velo_to:>6.1f}" if pd.notna(r.avg_velo_to) else f"{'--':>6}"
    yoy = f"{r.velo_yoy:>+5.1f}" if pd.notna(r.get("velo_yoy")) else f"{'--':>5}"
    flag = {"VV": "▼▼", "v": " ▼", "^": " ▲"}.get(r.get("velo_flag", ""), "  ")
    vin = f"{r.velo_in:>+5.1f}" if pd.notna(r.get("velo_in")) else f"{'--':>5}"
    iflag = {"VV": "▼▼", "v": " ▼"}.get(r.get("velo_in_flag", ""), "  ")
    v2y = f"{r.velo_2y:>+5.1f}" if pd.notna(r.get("velo_2y")) else f"{'--':>5}"
    f2y = {"VV": "▼▼", "v": " ▼"}.get(r.get("velo_2y_flag", ""), "  ")
    return (f"{r.player_name_fg:<20}{owner:<16}{int(r.gs):>3}"
            f"{r.k_pct*100:>6.1f}{r.swstr_pct*100:>7.1f}{velo}"
            f"{yoy}{flag}{vin}{iflag}{v2y}{f2y}"
            f"{r.stuff_level_pctl:>7.0f}{r.curfp_pctl:>7.0f}{r.decline_gap:>+7.0f}  {r.tier}")


HDR = (f"{'pitcher':<20}{'owner':<16}{'GS':>3}{'K%':>6}{'SwStr':>7}{'velo':>6}"
       f"{'vYoY':>5}{'':>2}{'vIn':>5}{'':>2}{'v2y':>5}{'':>2}"
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
        mine_velo = mine[mine["velo_flag"].isin(["VV", "v"])]
        if len(mine_velo):
            tags = ", ".join(f"{r.player_name_fg} ({r.velo_yoy:+.1f})"
                             for _, r in mine_velo.iterrows())
            print(f"  VELO FADE (vs 2025 season-end, leading flag): {tags} "
                  f"— raises decline conviction + bust-risk tilt (velo_signal_2026-06-13).")
        mine_vin = mine[mine["velo_in_flag"].isin(["VV", "v"]) & ~mine["velo_flag"].isin(["VV", "v"])]
        if len(mine_vin):
            tags = ", ".join(f"{r.player_name_fg} ({r.velo_in:+.1f})"
                             for _, r in mine_vin.iterrows())
            print(f"  IN-SEASON VELO DROP (vs 2026 peak, >=80 BF L21): {tags} "
                  f"— sustained dip not (yet) in the YoY line; same bust-risk tilt.")
        mine_2y = mine[mine["velo_2y_flag"].isin(["VV", "v"])]
        if len(mine_2y):
            tags = ", ".join(f"{r.player_name_fg} ({r.velo_2y:+.1f})"
                             for _, r in mine_2y.iterrows())
            print(f"  MULTI-YEAR VELO DECLINE (vs 2024 season-end): {tags} "
                  f"— strongest velo construct (partial-r +0.175); sustained erosion, "
                  f"not a blip.")
        mine_sev = mine[mine["velo_double"]]
        if len(mine_sev):
            print(f"  ⚠ SEVERE VELO FADE (YoY + in-season BOTH down): "
                  f"{', '.join(mine_sev.player_name_fg)} — ~49% forward bust rate "
                  f"(2.1x base), -2.5 FP/start. Strongest velo cutoff (E).")
        mine_lv = mine[(mine["velo_severity"] == "LOW-VELO")]
        if len(mine_lv):
            print(f"  LOW-VELO TILT (sub-median velo + a drop): "
                  f"{', '.join(mine_lv.player_name_fg)} — finesse arms have no margin; "
                  f"the drop bites ~2x harder (cutoff D).")

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
