"""
Calibrate /triangulate 4th-lens override thresholds against historical data.

Backtests the 3 hand-tuned override rules (speed-profile HOLD, post-TJ ramp HOLD,
process-intact HOLD) against the archetype career panels. For each override:

  - Builds the trigger set (matches the override IF-clause).
  - Builds a comparison set (similar bearish trajectory, override does NOT fire).
  - Compares next_fp, beat-projection rate, archetype-upgrade rate.
  - Sweeps the key threshold parameter.

Reproducible: re-run as panels grow. Writes report to
docs/triangulate_calibration_2026.md.

Usage:
    python scripts/xfp/calibrate_overrides.py
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HIT_PANEL = ROOT / "data" / "research" / "hitter_archetype_career_panel.parquet"
SP_PANEL = ROOT / "data" / "research" / "sp_archetype_career_panel.parquet"
OUT_REPORT = ROOT / "docs" / "triangulate_calibration_2026.md"

# Archetype-tier ordering for "upgrade" comparison.
HITTER_TIER = {
    "BUST": 0, "FRINGE": 1, "BACKUP_BAT": 1, "K_PRONE_FILLER": 1,
    "GENERIC_NO_POWER": 2, "AVG_HACKER": 2, "SLAP_HITTER": 2,
    "NO_POWER_HACKER": 2, "ALL_OR_NOTHING": 2, "AVERAGE_HITTER": 3,
    "CONTACT_HACKER": 3, "PATIENT_K": 3, "SECONDARY_LEADOFF": 3,
    "PURE_HITTER": 4, "POWER_HITTER": 4, "BALANCED_EYE": 4,
    "CONTACT_EYE": 4, "POWER_EYE": 4, "CONTACT_POWER": 5,
    "GOAT_TIER": 6,
}
SP_TIER = {
    "LIABILITY": 0, "BAD_BIG_INNINGS": 0, "FRINGE": 1, "FILLER": 1,
    "PURE_STUFF_LIABILITY": 1, "WILD_MID": 2, "WILD_FIREBALLER": 2,
    "STUFF_MOVE_WILD": 2, "SINKER_WILD": 2, "MOVE_WILD": 2,
    "GENERIC_HR_PRONE": 2, "CTRL_HR_PRONE": 2, "SINKER_ONLY": 2,
    "JUNKBALLER": 3, "AVERAGE_4_5": 3, "PURE_CONTROL": 3,
    "PURE_MOVEMENT": 3, "PURE_STUFF": 3,
    "PIT_CHF": 4, "PIT_CHF_CTRL": 4, "STUFF_PLUS_MOVE": 4,
    "STUFF_PLUS_CTRL": 4, "MOVE_CTRL_ACE": 5, "MT_RUSHMORE": 6,
}


def _tier(label, mapping):
    if pd.isna(label):
        return np.nan
    return mapping.get(str(label), np.nan)


def _summary(df, label):
    df = df.dropna(subset=["next_fp", "t1_fp_projection"])
    if len(df) == 0:
        return {"label": label, "n": 0}
    beat = (df["next_fp"] > df["t1_fp_projection"]).mean()
    return {
        "label": label,
        "n": int(len(df)),
        "next_fp_mean": float(df["next_fp"].mean()),
        "t1_proj_mean": float(df["t1_fp_projection"].mean()),
        "beat_rate": float(beat),
        "upgrade_rate": float(df["upgraded"].mean()) if "upgraded" in df else np.nan,
    }


def _tag_upgrade(df, tier_map):
    cur = df["archetype"].map(lambda x: _tier(x, tier_map))
    nxt = df["next_arch"].map(lambda x: _tier(x, tier_map))
    df = df.copy()
    df["cur_tier"] = cur
    df["nxt_tier"] = nxt
    df["upgraded"] = (nxt > cur).astype(float)
    df.loc[nxt.isna() | cur.isna(), "upgraded"] = np.nan
    return df


# ----------------------------- OVERRIDE A: speed profile -----------------------------

def calibrate_override_A(hit):
    """Speed-profile HOLD (hitters): (SPEED ≥ 60 OR SB ≥ 60) AND traj in (TRENDING_DOWN, STABLE)."""
    df = hit[hit["next_fp"].notna() & hit["t1_fp_projection"].notna()].copy()
    df = _tag_upgrade(df, HITTER_TIER)
    bearish = df[df["traj_flag"].isin(["TRENDING_DOWN", "STABLE"])].copy()

    rows = []
    for thr in [50, 55, 60, 65, 70]:
        trig = bearish[(bearish["SPEED_TOOL"] >= thr) | (bearish["SB"] >= thr)]
        comp = bearish[~((bearish["SPEED_TOOL"] >= thr) | (bearish["SB"] >= thr))]
        rows.append({
            "threshold": thr,
            **{f"trig_{k}": v for k, v in _summary(trig, "trig").items() if k != "label"},
            **{f"comp_{k}": v for k, v in _summary(comp, "comp").items() if k != "label"},
        })
    sweep = pd.DataFrame(rows)

    # examples at production threshold (60)
    trig60 = bearish[(bearish["SPEED_TOOL"] >= 60) | (bearish["SB"] >= 60)]
    examples = (trig60[["name", "year", "SPEED_TOOL", "SB", "traj_flag",
                        "t1_fp_projection", "next_fp", "archetype", "next_arch"]]
                .sort_values("next_fp", ascending=False).head(8))
    return sweep, trig60, examples


# ----------------------------- OVERRIDE B: post-TJ ramp -----------------------------

def calibrate_override_B(sp):
    """Post-TJ ramp HOLD (SPs): CAREER_LOW + walk-driven label + (SwingMiss − WalkAvoid) ≥ 10 + career_yr ≥ 3.

    Better post-TJ proxy: gap year (player missing a year between prior and CAREER_LOW).
    """
    df = sp[sp["next_fp"].notna() & sp["t1_fp_projection"].notna()].copy()
    df = _tag_upgrade(df, SP_TIER)

    # gap-year flag: prior year present in panel?
    prior = df[["pitcher", "year"]].copy()
    prior["year_plus1"] = prior["year"] + 1
    present_prior = set(zip(prior["pitcher"], prior["year"]))
    df["has_prior_year"] = [(p, y - 1) in present_prior for p, y in zip(df["pitcher"], df["year"])]
    df["gap_year"] = ~df["has_prior_year"] & (df["career_year"] >= 2)

    walk_labels = ("WILD_MID", "WILD_FIREBALLER", "STUFF_MOVE_WILD",
                   "MOVE_WILD", "SINKER_WILD", "BAD_BIG_INNINGS", "LIABILITY")
    df["walk_driven"] = df["archetype"].isin(walk_labels)
    df["sm_minus_wa"] = df["SWING_MISS"] - df["WALK_AVOID"]

    base = df[(df["traj_flag"] == "CAREER_LOW") & (df["walk_driven"])
              & (df["career_year"] >= 3)].copy()

    rows = []
    for thr in [0, 5, 10, 15, 20]:
        trig = base[base["sm_minus_wa"] >= thr]
        comp = base[base["sm_minus_wa"] < thr]
        rows.append({
            "sm_minus_wa_thr": thr,
            **{f"trig_{k}": v for k, v in _summary(trig, "trig").items() if k != "label"},
            **{f"comp_{k}": v for k, v in _summary(comp, "comp").items() if k != "label"},
        })
    sweep = pd.DataFrame(rows)

    # Compare gap-year proxy vs career_yr proxy
    gap_trig = df[(df["traj_flag"] == "CAREER_LOW") & (df["walk_driven"])
                  & (df["gap_year"]) & (df["sm_minus_wa"] >= 10)]
    career_trig = df[(df["traj_flag"] == "CAREER_LOW") & (df["walk_driven"])
                     & (df["career_year"] >= 3) & (df["sm_minus_wa"] >= 10)]
    proxy_compare = pd.DataFrame([
        {"proxy": "career_yr>=3", **{k: v for k, v in _summary(career_trig, "x").items() if k != "label"}},
        {"proxy": "gap_year", **{k: v for k, v in _summary(gap_trig, "x").items() if k != "label"}},
    ])

    examples = (career_trig[["name", "year", "career_year", "gap_year", "archetype",
                              "SWING_MISS", "WALK_AVOID", "t1_fp_projection",
                              "next_fp", "next_arch"]]
                .sort_values("next_fp", ascending=False).head(8))
    return sweep, proxy_compare, career_trig, examples


# ----------------------------- OVERRIDE C: process intact -----------------------------

def calibrate_override_C(sp):
    """Process-intact HOLD (SPs): traj in (TRENDING_DOWN, CAREER_LOW) AND model_rank ≤ 50.

    Use rank_in_year as proxy for model_rank.
    """
    df = sp[sp["next_fp"].notna() & sp["t1_fp_projection"].notna()].copy()
    df = _tag_upgrade(df, SP_TIER)
    bearish = df[df["traj_flag"].isin(["TRENDING_DOWN", "CAREER_LOW"])].copy()

    rows = []
    for thr in [25, 50, 75, 100]:
        trig = bearish[bearish["rank_in_year"] <= thr]
        comp = bearish[bearish["rank_in_year"] > thr]
        rows.append({
            "rank_thr": thr,
            **{f"trig_{k}": v for k, v in _summary(trig, "trig").items() if k != "label"},
            **{f"comp_{k}": v for k, v in _summary(comp, "comp").items() if k != "label"},
        })
    sweep = pd.DataFrame(rows)

    # Alternative: OVERALL >= 55 proxy
    alt_rows = []
    for thr in [50, 55, 60, 65]:
        trig = bearish[bearish["OVERALL"] >= thr]
        comp = bearish[bearish["OVERALL"] < thr]
        alt_rows.append({
            "OVERALL_thr": thr,
            **{f"trig_{k}": v for k, v in _summary(trig, "trig").items() if k != "label"},
            **{f"comp_{k}": v for k, v in _summary(comp, "comp").items() if k != "label"},
        })
    alt_sweep = pd.DataFrame(alt_rows)

    trig50 = bearish[bearish["rank_in_year"] <= 50]
    examples = (trig50[["name", "year", "traj_flag", "rank_in_year", "OVERALL",
                        "t1_fp_projection", "next_fp", "archetype", "next_arch"]]
                .sort_values("next_fp", ascending=False).head(8))
    return sweep, alt_sweep, trig50, examples


# ----------------------------- report -----------------------------

def _md_table(df, floatfmt=3):
    if df is None or len(df) == 0:
        return "_(empty)_\n"
    return df.round(floatfmt).to_markdown(index=False) + "\n"


def main():
    hit = pd.read_parquet(HIT_PANEL)
    sp = pd.read_parquet(SP_PANEL)

    A_sweep, A_trig, A_ex = calibrate_override_A(hit)
    B_sweep, B_proxy, B_trig, B_ex = calibrate_override_B(sp)
    C_sweep, C_alt, C_trig, C_ex = calibrate_override_C(sp)

    def _bounce(df):
        df = df.dropna(subset=["next_fp", "t1_fp_projection"])
        if len(df) == 0:
            return float("nan")
        return float((df["next_fp"] > df["t1_fp_projection"]).mean())

    bearish_hit = hit[hit["traj_flag"].isin(["TRENDING_DOWN", "STABLE"])
                      & hit["next_fp"].notna() & hit["t1_fp_projection"].notna()]
    comp_A = bearish_hit[~((bearish_hit["SPEED_TOOL"] >= 60) | (bearish_hit["SB"] >= 60))]
    summ_rows = [
        {"override": "A: speed-profile HOLD",
         "n_trigger": int(len(A_trig.dropna(subset=["next_fp", "t1_fp_projection"]))),
         "bounce_trig": _bounce(A_trig),
         "bounce_comp": _bounce(comp_A),
         "lift_pp": _bounce(A_trig) - _bounce(comp_A)},
        {"override": "B: post-TJ ramp HOLD",
         "n_trigger": int(len(B_trig.dropna(subset=["next_fp", "t1_fp_projection"]))),
         "bounce_trig": _bounce(B_trig),
         "bounce_comp": np.nan,
         "lift_pp": np.nan},
        {"override": "C: process-intact HOLD",
         "n_trigger": int(len(C_trig.dropna(subset=["next_fp", "t1_fp_projection"]))),
         "bounce_trig": _bounce(C_trig),
         "bounce_comp": np.nan,
         "lift_pp": np.nan},
    ]
    summary = pd.DataFrame(summ_rows)

    # recommendations: decide from sweep deltas
    def _argmax_lift(sweep, thr_col):
        s = sweep.copy()
        s["lift"] = s["trig_beat_rate"] - s["comp_beat_rate"]
        if s["lift"].isna().all():
            return None, None
        i = s["lift"].idxmax()
        return s.loc[i, thr_col], s.loc[i, "lift"]

    A_best_thr, A_best_lift = _argmax_lift(A_sweep, "threshold")
    B_best_thr, B_best_lift = _argmax_lift(B_sweep, "sm_minus_wa_thr")
    C_best_thr, C_best_lift = _argmax_lift(C_sweep, "rank_thr")

    def _rec(prod_thr, best_thr, best_lift, n_at_prod, prod_lift, min_n=20):
        if n_at_prod < min_n:
            return f"INSUFFICIENT DATA (n={n_at_prod} < {min_n})"
        if best_lift is None or pd.isna(best_lift):
            return "INSUFFICIENT DATA"
        # If production threshold itself has near-zero or negative lift, REJECT.
        if prod_lift is not None and not pd.isna(prod_lift) and prod_lift < 0.01:
            if best_lift < 0.03:
                return (f"REJECT — production thr={prod_thr} shows {prod_lift*100:+.1f}pp lift; "
                        f"best alternative ({int(best_thr)}) only {best_lift*100:+.1f}pp")
            return (f"LOOSEN to {int(best_thr)} — production thr={prod_thr} is negative "
                    f"({prod_lift*100:+.1f}pp), best alt {best_lift*100:+.1f}pp")
        if best_lift < 0.02:
            return "REJECT — no measurable lift (<2pp) at any threshold"
        if best_thr == prod_thr:
            return f"KEEP at {prod_thr}"
        if best_thr > prod_thr:
            return f"TIGHTEN to {int(best_thr)} (lift {best_lift*100:.1f}pp vs current)"
        return f"LOOSEN to {int(best_thr)} (lift {best_lift*100:.1f}pp vs current)"

    def _lift_at(sweep, thr_col, prod_thr):
        s = sweep.copy()
        s["lift"] = s["trig_beat_rate"] - s["comp_beat_rate"]
        row = s[s[thr_col] == prod_thr]
        if len(row) == 0:
            return np.nan
        return float(row["lift"].iloc[0])

    A_prod_lift = _lift_at(A_sweep, "threshold", 60)
    B_prod_lift = _lift_at(B_sweep, "sm_minus_wa_thr", 10)
    C_prod_lift = _lift_at(C_sweep, "rank_thr", 50)

    rec_A = _rec(60, A_best_thr, A_best_lift, int(len(A_trig.dropna(subset=["next_fp"]))), A_prod_lift)
    rec_B = _rec(10, B_best_thr, B_best_lift, int(len(B_trig.dropna(subset=["next_fp"]))), B_prod_lift)
    # For C, smaller rank = stricter, so invert the direction semantics by passing negated thresholds
    rec_C = _rec(-50, -C_best_thr if C_best_thr is not None else None, C_best_lift,
                  int(len(C_trig.dropna(subset=["next_fp"]))), C_prod_lift)
    rec_C = rec_C.replace("-25", "25").replace("-50", "50")

    summary["recommendation"] = [rec_A, rec_B, rec_C]

    buf = io.StringIO()
    w = buf.write
    w("# /triangulate Override Calibration — 2026-05\n\n")
    w("Empirical backtest of the three 4th-lens overrides against the hitter "
      "(N=4,824) and SP (N=1,967) archetype career panels.\n\n")
    w("**Method.** For each override, build the trigger set (player-years matching "
      "the IF-clause) and a comparison set (similar bearish trajectory, override does "
      "NOT fire). Compare T+1 outcomes: actual `next_fp`, % beating `t1_fp_projection` "
      "(\"bounce rate\"), and % achieving an archetype upgrade. Sweep the key parameter "
      "to find the lift-maximising threshold.\n\n")
    w("## Executive Summary\n\n")
    w(_md_table(summary))
    w("\n*`bounce_trig` / `bounce_comp` = share of player-years where `next_fp > "
      "t1_fp_projection`. Lift is the percentage-point delta.*\n\n")

    # Override A
    w("---\n\n## Override A — Speed-profile HOLD (hitters)\n\n")
    w("**Rule.** `(SPEED_TOOL ≥ 60 OR SB ≥ 60) AND traj ∈ {TRENDING_DOWN, STABLE}` → HOLD\n\n")
    w("**Comparison set.** Same trajectory, fails the speed condition.\n\n")
    w("### Threshold sensitivity (SPEED_TOOL/SB cutoff)\n\n")
    w(_md_table(A_sweep))
    w(f"\n**Best lift at threshold = {A_best_thr}** "
      f"(lift = {A_best_lift*100:.1f}pp on beat-rate).\n\n")
    w(f"**Recommendation: {rec_A}**\n\n")
    w("### Named comp examples (top 8 by next_fp at threshold 60)\n\n")
    w(_md_table(A_ex, floatfmt=2))

    # Override B
    w("\n---\n\n## Override B — Post-TJ ramp HOLD (SPs)\n\n")
    w("**Rule.** `CAREER_LOW + walk-driven archetype + (SWING_MISS − WALK_AVOID) ≥ 10 "
      "+ career_yr ≥ 3` → HOLD\n\n")
    w("Walk-driven archetypes used: WILD_MID, WILD_FIREBALLER, STUFF_MOVE_WILD, "
      "MOVE_WILD, SINKER_WILD, BAD_BIG_INNINGS, LIABILITY.\n\n")
    w("### Threshold sensitivity (SWING_MISS − WALK_AVOID gap)\n\n")
    w(_md_table(B_sweep))
    w(f"\n**Best lift at SM−WA ≥ {B_best_thr}** (lift = "
      f"{(B_best_lift*100) if B_best_lift is not None and not pd.isna(B_best_lift) else float('nan'):.1f}pp).\n\n")
    w("### career_yr ≥ 3 vs gap-year proxy\n\n")
    w(_md_table(B_proxy))
    w("\n*Gap-year proxy = no prior-year row in the panel (a crude TJ/injury-year "
      "approximation). Compared head-to-head against the looser career_yr ≥ 3 rule.*\n\n")
    w(f"**Recommendation: {rec_B}**\n\n")
    w("### Named comp examples (career_yr ≥ 3 trigger, top 8 by next_fp)\n\n")
    w(_md_table(B_ex, floatfmt=2))

    # Override C
    w("\n---\n\n## Override C — Process-intact HOLD (SPs)\n\n")
    w("**Rule.** `traj ∈ {TRENDING_DOWN, CAREER_LOW} AND model_rank ≤ 50` → HOLD\n\n")
    w("Using panel `rank_in_year` as the model-rank proxy.\n\n")
    w("### Threshold sensitivity (rank_in_year)\n\n")
    w(_md_table(C_sweep))
    w(f"\n**Best lift at rank ≤ {C_best_thr}** "
      f"(lift = {(C_best_lift*100) if C_best_lift is not None and not pd.isna(C_best_lift) else float('nan'):.1f}pp).\n\n")
    w("### Alternative proxy — OVERALL rating cutoff\n\n")
    w(_md_table(C_alt))
    w(f"\n**Recommendation: {rec_C}**\n\n")
    w("### Named comp examples (rank ≤ 50 trigger, top 8 by next_fp)\n\n")
    w(_md_table(C_ex, floatfmt=2))

    # Code-change suggestions
    w("\n---\n\n## Suggested code changes to `apply_overrides()`\n\n")
    def _change_line(name, prod, rec):
        return f"- **{name}**: {rec}\n"
    w(_change_line("Override A (SPEED/SB threshold)", 60, rec_A))
    w(_change_line("Override B (SWING_MISS − WALK_AVOID gap)", 10, rec_B))
    w(_change_line("Override C (rank cutoff)", 50, rec_C))
    w("\nIf any line above reads REJECT or INSUFFICIENT DATA, leave the production "
      "threshold untouched and treat this as a known-limitation note rather than a code change.\n")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"Wrote {OUT_REPORT}")
    print("\n=== Executive summary ===")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
