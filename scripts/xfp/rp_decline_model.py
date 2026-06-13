"""
rp_decline_model.py — RELIEVER role-loss / FP-crater CONVERGENCE WATCH board.

The "is my closer about to lose the job" lens. RP value is opportunity-dominated
(rprs2 r~0.87 vs rp3 0.55 — saves/holds = role, not per-batter skill), so the
decline that matters for an RP is a ROLE crater, not rate regression. This board
flags the relievers most at risk of that crater.

VALIDATED BASIS — read both before trusting a flag:
  data/research/validation_runs/rp_decline_stuff_velo_2026-06-13.md
    * VELO DECLINE (YoY, vs prior-season-end) is the strongest STUFF predictor of
      RP RoS-FP decline: partial-r +0.112 [+.052,+.166]. This REVERSES the SP
      finding (SP = whiff/K LEVEL +0.235). It is specifically the radar-gun DROP —
      swStr-YoY and K-YoY decline are NOT significant; velo LEVEL alone is weak
      (+0.064). Modest (~half the SP signal) and 56% coverage (needs a prior MLB
      season of velo). xwoba-LEVEL (-0.107) is the best contact-quality companion.
  data/research/validation_runs/rp_decline_role_leverage_2026-06-13.md
    * ROLE LOSS is the MECHANISM: save+hold share drop -> FP craters 4.01 -> 2.49
      /app (-38%). But the role TREND barely predicts (ΔAUC +0.013, leakage-prone)
      and role loss is only AUC 0.683 (~1/3 manager-driven noise). Causal chain:
      SKILL/VELO EROSION -> manager strips the role -> FP craters. Skill markers
      predict role-loss BETTER than the role trend (skill-only AUC 0.652 vs
      role-trend 0.604). The ONLY config beating base is the TWO-LENS CONVERGENCE
      (eroding velo/skill AND early role-share slippage).

THEREFORE the signal here is a CONVERGENCE WATCH, not a confident point forecast:
  ROLE-RISK = velo DECLINING YoY  AND  (whiff/K skill eroding OR role-share slipping)
  WATCH     = one leg present (velo down, OR skill/role slipping) but not converged
  SECURE    = velo stable/up and skill/role intact
  NA-VELO   = no prior-season velo -> can't fire the PRIMARY signal -> do NOT
              false-SECURE; mark the velo gap explicitly.

HONEST CONFIDENCE (encoded in the output): this is WEAKER + NOISIER than
/sp-decline. velo-decline +0.112 vs SP whiff/K-level +0.235; role loss is ~1/3
manager-driven (AUC 0.683) and only modestly forecastable from the pitcher's own
line. It is a conviction / watch gate, NOT a confident call. Headline RP value
STAYS rprs2 (role/opportunity); this NEVER moves it (CLAUDE.md #13 — Tier-B flag).

Single-lens risk board — feed any flagged name into /triangulate for the full stack.

CLI:
  python rp_decline_model.py                 # league-wide board + MINE + FA sections
  python rp_decline_model.py --players "A,B" # focus list
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_stuff_model import ownership_map, own_tag, _norm  # noqa: E402  two-pass ownership

ROOT = Path(__file__).resolve().parents[2]
ROLLING = ROOT / "data" / "research" / "xfp_cache" / "rolling_relievers_2018_2026.csv"
RPRS2 = ROOT / "data" / "outputs" / "xfp_rprs2_projections.csv"

# --- Thresholds (explicit + defensible) ----------------------------------------
# PRIMARY signal = velo YoY decline (validated partial-r +0.112, the radar-gun drop).
# Full-fit coef +0.168 (velo gain -> higher RoS FP). We treat a meaningful YoY drop
# as the necessary leg of the convergence. RP velo is noisier than SP, so the soft
# gate is a touch wider than /sp-decline's -0.7.
VELO_YOY_SOFT = -0.8    # >= this far below 2025 season-end velo -> velo declining
VELO_YOY_HARD = -1.5    # >= this -> strong velo fade (worst forward band)
VELO_YOY_RISE = 0.5     # gaining velo vs last year -> tailwind (suppresses ROLE-RISK)

# SKILL-erosion leg (the leading indicator of role loss; skill-only AUC 0.652).
# YoY skill DELTAS were n.s. (swStr-YoY +0.033, K-YoY +0.020) so we use a LEVEL
# read instead: a below-average whiff/K LEVEL is the "weak stuff" condition under
# which a velo drop is most likely to cost the role. xwoba-LEVEL (-0.107) is the
# best contact-quality companion — soft contact-quality LEVEL also counts as skill
# erosion. (These are LEVELS within the 2026 RP pool, leakage-safe.)
SKILL_LOW_PCTL = 40.0   # whiff/K LEVEL at/below the pool 40th pctl = eroding/weak stuff
XWOBA_SOFT_PCTL = 60.0  # xwoba-against LEVEL at/above 60th pctl (worse) = contact slipping

# ROLE-SHARE slippage leg (the early mechanism). The role TREND is leakage-prone
# (do NOT use as a standalone point term — report #2), so we use the current
# role-SHARE STATE relative to having-a-role: a closer/setup whose save+hold share
# has thinned. We compute the recent vs to-date sv+hld share slip from the rolling
# cache (as-of, two-pass differenced) and gate it on actually having had a role.
ROLE_FLOOR_SVHLD = 0.12   # to-date sv+hld per appearance to count as "has a role to lose"
ROLE_SLIP_FRAC = -0.25    # recent sv+hld share >=25% below to-date -> early slippage

MIN_G = 8   # min 2026 appearances to be in the pool (matches the backtest filter)


def _pctl(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) * 100


def _load_rolling_2026():
    """Latest-split 2026 per-RP line + 2025 season-end velo (YoY) + recent-window
    role-share slip. Keyed by mlb_id (`pitcher`). Returns one row per RP.

    Coverage notes:
      * velo_yoy needs a 2025 season-end velo row -> ~56-77% coverage. Missing ->
        NaN (the NA-VELO path, never a false SECURE).
      * recent-window role-share = differencing the cumulative sv+hld _to value vs
        ~2 splits prior (the as-of recent read used in the role-erosion backtest).
    """
    cols = ["pitcher", "year", "split_day", "avg_velo_to", "swstr_pct_to",
            "k_pct_to", "xwoba_per_pa_to", "tbf_to", "g_to",
            "sv_plus_hld_to", "sv_to", "hld_to"]
    r = pd.read_csv(ROLLING, usecols=cols)
    cur = r[r["year"] == 2026].sort_values(["pitcher", "split_day"]).copy()
    if cur.empty:
        return pd.DataFrame()

    latest = cur.groupby("pitcher").tail(1).copy()

    # recent-window role-share slip: sv+hld per appearance, recent (~2 splits) vs to-date.
    cur["svhld_per_g_to"] = cur["sv_plus_hld_to"] / cur["g_to"].replace(0, np.nan)
    prev = cur.groupby("pitcher").nth(-3)  # ~2 splits back (28d) where available
    prev = prev[["pitcher", "sv_plus_hld_to", "g_to"]].rename(
        columns={"sv_plus_hld_to": "svhld_prev", "g_to": "g_prev"})
    latest = latest.merge(prev, on="pitcher", how="left")
    rec_svhld = latest["sv_plus_hld_to"] - latest["svhld_prev"]
    rec_g = latest["g_to"] - latest["g_prev"]
    latest["svhld_per_g_to"] = latest["sv_plus_hld_to"] / latest["g_to"].replace(0, np.nan)
    latest["svhld_per_g_rec"] = rec_svhld / rec_g.replace(0, np.nan)
    # share slip fraction (recent vs to-date), only where there was a role + recent apps
    has_role = latest["svhld_per_g_to"] >= ROLE_FLOOR_SVHLD
    slip = (latest["svhld_per_g_rec"] - latest["svhld_per_g_to"]) / latest["svhld_per_g_to"].replace(0, np.nan)
    latest["role_slip_frac"] = np.where(has_role & rec_g.notna() & (rec_g > 0), slip, np.nan)
    latest["has_role"] = has_role

    # 2025 season-end velo -> YoY delta
    prior = r[r["year"] == 2025].sort_values("split_day").groupby("pitcher").tail(1)
    prior = prior[["pitcher", "avg_velo_to"]].rename(columns={"avg_velo_to": "velo_2025"})
    latest = latest.merge(prior, on="pitcher", how="left")
    latest["velo_yoy"] = latest["avg_velo_to"] - latest["velo_2025"]

    return latest.rename(columns={"pitcher": "mlb_id"})


def _velo_flag(yoy: float) -> str:
    if pd.isna(yoy):
        return "NA"   # no prior-season velo -> primary signal can't fire
    if yoy <= VELO_YOY_HARD:
        return "VV"
    if yoy <= VELO_YOY_SOFT:
        return "v"
    if yoy >= VELO_YOY_RISE:
        return "^"
    return ""


def build():
    """Return (DataFrame of 2026 RPs with convergence-watch diagnostics, n_pool)."""
    roll = _load_rolling_2026()
    roll = roll[roll["g_to"] >= MIN_G].copy()
    if roll.empty:
        raise SystemExit("No 2026 reliever rows in rolling cache.")

    # join rprs2 role-share STATE + names (by mlb_id)
    rp = pd.read_csv(RPRS2)
    rp = rp.rename(columns={"pitcher": "mlb_id", "name_api": "name"})
    keep = ["mlb_id", "name", "role_lag1", "sv_to", "hld_to", "gf_pct_to",
            "sv_per_g_to", "xfp_ros"]
    d = roll.merge(rp[keep], on="mlb_id", how="left", suffixes=("", "_rp"))
    # name fallback for RPs not in rprs2 (no name there) -> drop unnamed (can't tag)
    d = d[d["name"].notna()].copy()

    # percentiles within the 2026 RP pool (leakage-safe LEVELS)
    d["swstr_pctl"] = _pctl(d["swstr_pct_to"])
    d["k_pctl"] = _pctl(d["k_pct_to"])
    d["xwoba_pctl"] = _pctl(d["xwoba_per_pa_to"])  # higher pctl = WORSE (more contact damage)
    d["skill_pctl"] = (d["swstr_pctl"] + d["k_pctl"]) / 2  # whiff/K LEVEL

    # --- the three convergence legs ---
    d["velo_flag"] = d["velo_yoy"].map(_velo_flag)
    velo_down = d["velo_flag"].isin(["v", "VV"])
    velo_na = d["velo_flag"] == "NA"

    skill_eroding = (d["skill_pctl"] <= SKILL_LOW_PCTL) | (d["xwoba_pctl"] >= XWOBA_SOFT_PCTL)
    role_slipping = d["role_slip_frac"] <= ROLE_SLIP_FRAC

    d["leg_velo"] = velo_down
    d["leg_skill"] = skill_eroding
    d["leg_role"] = role_slipping.fillna(False)

    # --- tier: convergence WATCH logic ---
    # ROLE-RISK = velo declining AND (skill eroding OR role slipping) — the only
    # config validated to beat base — AND the RP actually HAS A ROLE TO LOSE
    # (to-date sv+hld/app >= ROLE_FLOOR_SVHLD, the report's closer/setup tier).
    # A `middle` mop-up arm can't suffer a role-loss crater; eroding velo+skill on
    # such an arm is a fade (WATCH), not the validated role-loss event. WATCH = one
    # leg present (or converged-but-no-role) but not a role-loss setup. NA-VELO = no
    # prior velo (primary can't fire) -> WATCH if a secondary leg fires, else NA
    # (unknown, NOT a clean bill).
    def tier(r):
        converged = r.leg_velo and (r.leg_skill or r.leg_role)
        if r.velo_na:
            if r.leg_skill or r.leg_role:
                return "WATCH"
            return "NA-VELO"
        if converged and r.has_role:
            return "ROLE-RISK"
        if r.leg_velo or r.leg_skill or r.leg_role:
            return "WATCH"
        return "SECURE"

    d["velo_na"] = velo_na
    d["tier"] = d.apply(tier, axis=1)

    # convergence count (0-3) for sorting / conviction
    d["legs"] = d[["leg_velo", "leg_skill", "leg_role"]].sum(axis=1)

    own = ownership_map()
    team_col = next((c for c in ("team_abbr", "team", "Team") if c in d.columns), None)
    d["own"] = (
        d.apply(lambda r: own_tag(own, r["name"],
                                  r[team_col] if team_col else None), axis=1)
        if own else ""
    )
    return d, len(d)


def tier_map():
    """Public join helper for OTHER skills/engines (trade-target-scan, fa-rp-pool,
    roster-audit). Returns {norm_name: {tier, role, legs, velo_yoy, velo_flag,
    svhld_per_g, role_slip_frac, has_role}} for every 2026 RP in the pool.

    Keyed by `_norm(name)` (the same accent-stripped lower-case key the ownership
    two-pass uses) so callers can join by name without re-deriving the convergence.
    This NEVER carries a point projection — it is the Tier-B context tier ONLY
    (CLAUDE.md #13). Returns {} (never raises) if the rolling cache is unavailable,
    so consumers degrade gracefully exactly like the ESPN-ownership tags do.
    """
    try:
        d, _ = build()
    except SystemExit:
        return {}
    except Exception:
        return {}
    out = {}
    for _, r in d.iterrows():
        out[_norm(str(r["name"]))] = {
            "tier": r["tier"],
            "role": str(r.get("role_lag1", "") or ""),
            "legs": int(r["legs"]),
            "velo_yoy": (float(r["velo_yoy"]) if pd.notna(r["velo_yoy"]) else None),
            "velo_flag": r["velo_flag"],
            "svhld_per_g": (float(r["svhld_per_g_to"]) if pd.notna(r["svhld_per_g_to"]) else None),
            "role_slip_frac": (float(r["role_slip_frac"]) if pd.notna(r["role_slip_frac"]) else None),
            "has_role": bool(r["has_role"]),
        }
    return out


# Sort key: ROLE-RISK first, then by legs desc, then velo_yoy asc (most fade first).
_TIER_ORDER = {"ROLE-RISK": 0, "WATCH": 1, "NA-VELO": 2, "SECURE": 3}


def _sort(d):
    d = d.copy()
    d["_t"] = d["tier"].map(_TIER_ORDER).fillna(9)
    return d.sort_values(["_t", "legs", "velo_yoy"], ascending=[True, False, True])


HDR = (f"{'reliever':<20}{'owner':<16}{'role':<9}{'G':>3}{'K%':>6}{'SwStr':>7}"
       f"{'velo':>6}{'vYoY':>6}{'':>3}{'skl%':>6}{'svhld/g':>8}{'slip':>7}"
       f"  legs  tier")


def _fmt(r, has_own):
    owner = (r.own if has_own else str(r.get("team_abbr", "")))[:15]
    role = str(r.get("role_lag1", "") or "")[:8]
    velo = f"{r.avg_velo_to:>6.1f}" if pd.notna(r.avg_velo_to) else f"{'--':>6}"
    yoy = f"{r.velo_yoy:>+6.1f}" if pd.notna(r.velo_yoy) else f"{'--':>6}"
    vf = {"VV": "▼▼", "v": " ▼", "^": " ▲", "NA": "na"}.get(r.velo_flag, "  ")
    svhld = f"{r.svhld_per_g_to:>8.2f}" if pd.notna(r.svhld_per_g_to) else f"{'--':>8}"
    slip = f"{r.role_slip_frac*100:>+6.0f}%" if pd.notna(r.role_slip_frac) else f"{'--':>7}"
    legmark = "".join(m for m, on in
                      [("V", r.leg_velo), ("S", r.leg_skill), ("R", r.leg_role)] if on) or "-"
    return (f"{str(r['name']):<20}{owner:<16}{role:<9}{int(r.g_to):>3}"
            f"{r.k_pct_to*100:>6.1f}{r.swstr_pct_to*100:>7.1f}{velo}{yoy}{vf:>3}"
            f"{r.skill_pctl:>6.0f}{svhld}{slip}  {legmark:<4}  {r.tier}")


def _board(d, has_own):
    print(HDR); print("-" * len(HDR))
    for _, r in _sort(d).iterrows():
        print(_fmt(r, has_own))


def main(players=None):
    d, n = build()
    has_own = (d["own"] != "").any()
    cov = d["velo_yoy"].notna().mean() * 100
    print(f"2026 RP pool: {n} (>= {MIN_G} G). CONVERGENCE WATCH — velo-decline (primary, "
          f"validated partial-r +0.112) AND (skill-LEVEL eroding OR early role-share slip).")
    print(f"Velo-YoY coverage {cov:.0f}% (needs a 2025 velo; no-velo -> NA-VELO, never false-SECURE).")
    print("Legs: V=velo down YoY | S=whiff/K LEVEL weak or contact soft | R=sv+hld share slipping.")
    print("Tiers: ROLE-RISK (V + S/R converge — the only config that beats base) | "
          "WATCH (one leg) | NA-VELO (no prior velo) | SECURE.")
    print("HONEST: weaker + noisier than /sp-decline (velo +0.112 vs SP whiff/K +0.235; role "
          "loss ~1/3 manager-driven, AUC 0.683). A watch/conviction gate, NOT a confident call.")
    print("Headline RP value STAYS rprs2 (role/opportunity) — this NEVER moves it. Feed flags -> /triangulate.\n")

    if players:
        want = {_norm(p) for p in players}
        sub = d[d["name"].map(lambda x: _norm(x) in want)]
        miss = want - {_norm(x) for x in sub["name"]}
        print(f"=== FOCUS LIST ({len(sub)} found) ===")
        _board(sub, has_own)
        if miss:
            print(f"\n  not in pool (no rolling/rprs2 row or < {MIN_G} G): {sorted(miss)}")
        return

    risk = d[d["tier"] == "ROLE-RISK"]
    print(f"=== ROLE-RISK BOARD (league-wide, {len(risk)}) — velo-decline CONVERGING with skill/role ===")
    _board(risk, has_own)

    if has_own:
        mine = d[d["own"] == "MINE"]
        print(f"\n=== YOUR RP STAFF ({len(mine)}) — ranked by role-loss convergence ===")
        _board(mine, has_own)
        mr = mine[mine["tier"] == "ROLE-RISK"]
        if len(mr):
            print(f"  ROLE-RISK WATCH: {', '.join(mr['name'])} — velo down AND skill/role slipping. "
                  f"Conviction gate, NOT a confident call (role loss ~1/3 manager-driven). "
                  f"Cross-check /pitcher-sustainability + /triangulate before a sell/drop.")
        mv = mine[mine["velo_flag"].isin(["v", "VV"]) & (mine["tier"] != "ROLE-RISK")]
        if len(mv):
            tags = ", ".join(f"{r['name']} ({r.velo_yoy:+.1f})" for _, r in mv.iterrows())
            print(f"  VELO FADE (primary leg only, no converged skill/role yet): {tags} "
                  f"— watch for role slippage to follow (skill->role->FP chain).")
        mna = mine[mine["tier"] == "NA-VELO"]
        if len(mna):
            print(f"  NA-VELO (no 2025 velo — primary signal blind, NOT a clean bill): "
                  f"{', '.join(mna['name'])}.")

        fa_risk = d[(d["own"] == "FA") & (d["tier"] == "ROLE-RISK")]
        print(f"\n=== FA ROLE-RISK ({len(fa_risk)}) — do NOT chase these saves; the role is fragile ===")
        _board(_sort(fa_risk).head(12), has_own)


if __name__ == "__main__":
    args = sys.argv[1:]
    plist = None
    if "--players" in args:
        i = args.index("--players")
        if i + 1 < len(args):
            plist = [p.strip() for p in args[i + 1].split(",") if p.strip()]
    main(plist)
