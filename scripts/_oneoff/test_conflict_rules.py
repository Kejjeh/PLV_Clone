"""Empirically validate the 5 conflict resolution rules in the merge protocol.

For each rule:
  1. Synthesize the precondition from snapshot columns (proxies — see header
     of each test function for the mapping).
  2. For matching cases, compute two verdicts (naive vs rule-applied) and
     the forward 30-day FP outcome (target).
  3. A rule "wins" a case when the rule-applied verdict's FP outcome beats the
     naive verdict's FP outcome (BUY → prefer high target; FADE → prefer low
     target; HOLD → prefer mid). Concretely:
       - If rule says HOLD/SELL-HIGH and naive says DROP/FADE:
            win = target >= naive_dropped_threshold (rule kept a productive player)
       - If rule says FADE/SELL-HIGH and naive says BUY:
            win = target <= the player's recent hot streak avg (rule avoided regression)
  4. Net FP swing = mean(target | rule applied) - mean(target | naive applied),
     scoped by direction of the rule.

Outputs:
  data/research/validation_runs/conflict_rule_lift_2026-06-06.md
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SNAP_H = ROOT / "data/research/validation_runs/shrinkage_h_snap_2026-06-06.parquet"
SNAP_SP = ROOT / "data/research/validation_runs/shrinkage_sp_snap_2026-06-06.parquet"
OUT_MD = ROOT / "data/research/validation_runs/conflict_rule_lift_2026-06-06.md"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    h = pd.read_parquet(SNAP_H).dropna(subset=["pred_2yrK80", "prior_avg"]).copy()
    sp = pd.read_parquet(SNAP_SP).dropna(subset=["pred_k20", "prior_avg"]).copy()
    # Useful derived columns (proxies)
    # Hitter: model = pred_2yrK80 (Tier A blend proxy). Actuals = l21_avg.
    h["model"] = h["pred_2yrK80"]
    h["actuals_recent"] = h["l21_avg"]
    h["baseline_season"] = h["l42_avg"]
    h["prior_career"] = h["prior_avg"]
    # SP: model = pred_k20 (calibrated SP shrinkage).
    sp["model"] = sp["pred_k20"]
    sp["actuals_recent"] = sp["l21_avg"]
    sp["baseline_season"] = sp["l42_avg"]
    sp["prior_career"] = sp["prior_avg"]
    return h, sp


# ---------- Rule 1: Model FADE + L5 BUY -> sustainability NOISE/REGRESS -> trust model ----------
# Proxies:
#   model FADE              : model < (prior_career - 0.5 sd) -> Tier A says below career baseline
#   L5 BUY (hot streak)     : actuals_recent > baseline_season + sd_threshold
#   sustainability NOISE/REGRESS: actuals_recent >> prior_career AND
#                                 baseline_season ~ prior_career  (recent jump unsupported by season)
# We approximate sustainability bucket from how far L21 outran L42; if L21 - L42 is large
# AND L42 ~ prior, recent boom is "unanchored" = NOISE proxy. If L42 also rising, it's LEGIT.
def test_rule_1(h: pd.DataFrame, sp: pd.DataFrame) -> dict:
    # Pool both populations, scoring per-game so we treat hitter & SP separately.
    def _per_pop(df: pd.DataFrame, sd_hot: float, sd_fade: float, sd_noise_gap: float) -> dict:
        df = df.copy()
        # Build NOISE/LEGIT label from L42 vs prior
        # NOISE: l21 >> l42 AND l42 ~ prior -> recent boom is unanchored
        # LEGIT: l21 >> l42 AND l42 also > prior (sustained ramp)
        df["sus_label"] = np.where(
            (df["actuals_recent"] - df["baseline_season"] >= sd_hot)
            & (df["baseline_season"] - df["prior_career"] < sd_noise_gap),
            "NOISE",
            np.where(
                (df["actuals_recent"] - df["baseline_season"] >= sd_hot)
                & (df["baseline_season"] - df["prior_career"] >= sd_noise_gap),
                "LEGIT",
                "OTHER",
            ),
        )
        # Rule 1 precondition: model FADE + L5 BUY + sustainability NOISE
        precondition = (
            (df["model"] < df["prior_career"] - sd_fade)
            & (df["actuals_recent"] > df["baseline_season"] + sd_hot)
            & (df["sus_label"] == "NOISE")
        )
        match = df[precondition].copy()
        n = len(match)
        if n == 0:
            return {"n": 0}
        # Naive (just actuals): would say BUY -> expect target ~ actuals_recent
        # Rule-applied: trust model FADE -> expect target ~ model
        # Win = whichever side is closer to target
        naive_err = (match["actuals_recent"] - match["target"]).abs()
        rule_err = (match["model"] - match["target"]).abs()
        wins = (rule_err < naive_err).sum()
        win_rate = wins / n
        # Net FP swing: did fading the hot streak avoid a downturn?
        # If rule wins, the player's target was below the hot-streak actuals — fade worked
        # Net FP swing = mean (actuals_recent - target) — positive means hot streak regressed
        regression_amount = (match["actuals_recent"] - match["target"]).mean()
        # Lift in MAE of rule vs naive
        lift = naive_err.mean() - rule_err.mean()
        return {
            "n": n,
            "win_rate": win_rate,
            "lift_mae": lift,
            "regression_amount": regression_amount,
            "mean_target": match["target"].mean(),
            "mean_actuals_recent": match["actuals_recent"].mean(),
            "mean_model": match["model"].mean(),
        }

    h_res = _per_pop(h, sd_hot=0.5, sd_fade=0.2, sd_noise_gap=0.2)
    sp_res = _per_pop(sp, sd_hot=3.0, sd_fade=1.5, sd_noise_gap=1.5)
    return {"hitter": h_res, "sp": sp_res}


# ---------- Rule 2: CAP_FODDER + xwOBA gap < 0.020 -> HOLD ----------
# Proxies:
#   CAP_FODDER              : actuals_recent < (prior_career - sd)  -> recent bust look
#   xwOBA L21d gap < ±0.020 : baseline_season ~ prior_career         -> "process intact"
# Rule says HOLD instead of DROP. Outcome test: did player bounce back? (target near prior_career?)
def test_rule_2(h: pd.DataFrame, sp: pd.DataFrame) -> dict:
    def _per_pop(df: pd.DataFrame, sd_bust: float, sd_process_intact: float) -> dict:
        df = df.copy()
        precondition = (
            (df["actuals_recent"] < df["prior_career"] - sd_bust)
            & ((df["baseline_season"] - df["prior_career"]).abs() < sd_process_intact)
        )
        match = df[precondition].copy()
        n = len(match)
        if n == 0:
            return {"n": 0}
        # Naive (boom-bust says drop): expect target ~ actuals_recent (low)
        # Rule-applied (HOLD): expect target ~ prior_career (bounces back)
        naive_err = (match["actuals_recent"] - match["target"]).abs()
        rule_err = (match["prior_career"] - match["target"]).abs()
        wins = (rule_err < naive_err).sum()
        win_rate = wins / n
        # How much did targets bounce back vs the bust?
        bounce_amount = (match["target"] - match["actuals_recent"]).mean()
        lift = naive_err.mean() - rule_err.mean()
        return {
            "n": n,
            "win_rate": win_rate,
            "lift_mae": lift,
            "bounce_amount": bounce_amount,
            "mean_target": match["target"].mean(),
            "mean_actuals_recent": match["actuals_recent"].mean(),
            "mean_prior": match["prior_career"].mean(),
        }

    h_res = _per_pop(h, sd_bust=0.4, sd_process_intact=0.2)
    sp_res = _per_pop(sp, sd_bust=2.5, sd_process_intact=1.5)
    return {"hitter": h_res, "sp": sp_res}


# ---------- Rule 3: REAL_DECLINE L21d + RISING xwOBACON -> HOLD with sell-high optionality ----------
# Proxies:
#   REAL_DECLINE L21d : actuals_recent < (baseline_season - sd) -> falling vs season
#   RISING xwOBACON   : prior_career > prior2 (year-over-year improvement)
# This needs prior2_avg; subset where it exists.
# Rule: HOLD instead of DROP. Outcome: target ~ baseline_season (recovers somewhat).
def test_rule_3(h: pd.DataFrame, sp: pd.DataFrame) -> dict:
    def _per_pop(df: pd.DataFrame, sd_decline: float, sd_rise: float) -> dict:
        df = df.dropna(subset=["prior2_avg"]).copy()
        precondition = (
            (df["actuals_recent"] < df["baseline_season"] - sd_decline)
            & (df["prior_career"] > df["prior2_avg"] + sd_rise)
        )
        match = df[precondition].copy()
        n = len(match)
        if n == 0:
            return {"n": 0}
        # Naive (drop due to decline): target ~ actuals_recent
        # Rule-applied (HOLD): target ~ baseline_season (mean reverts)
        naive_err = (match["actuals_recent"] - match["target"]).abs()
        rule_err = (match["baseline_season"] - match["target"]).abs()
        wins = (rule_err < naive_err).sum()
        win_rate = wins / n
        recovery_amount = (match["target"] - match["actuals_recent"]).mean()
        lift = naive_err.mean() - rule_err.mean()
        return {
            "n": n,
            "win_rate": win_rate,
            "lift_mae": lift,
            "recovery_amount": recovery_amount,
            "mean_target": match["target"].mean(),
            "mean_actuals_recent": match["actuals_recent"].mean(),
            "mean_baseline": match["baseline_season"].mean(),
        }

    h_res = _per_pop(h, sd_decline=0.5, sd_rise=0.15)
    sp_res = _per_pop(sp, sd_decline=2.5, sd_rise=1.0)
    return {"hitter": h_res, "sp": sp_res}


# ---------- Rule 4: REGRESS + CAP_FODDER + replacement-level Blended xFP -> HIGH_CONFIDENCE drop ----------
# Proxies:
#   REGRESS (sus bucket)     : actuals_recent < baseline_season - sd (declining process)
#   CAP_FODDER (boom-bust)   : actuals_recent < prior_career - sd    (below career)
#   replacement-level xFP    : model < replacement-level threshold (bottom quartile)
# All 3 conditions agree -> DROP. Test: did the player actually decline forward?
def test_rule_4(h: pd.DataFrame, sp: pd.DataFrame) -> dict:
    def _per_pop(df: pd.DataFrame, sd_decline: float, sd_bust: float, q_replacement: float) -> dict:
        df = df.copy()
        repl_thresh = df["model"].quantile(q_replacement)
        precondition = (
            (df["actuals_recent"] < df["baseline_season"] - sd_decline)
            & (df["actuals_recent"] < df["prior_career"] - sd_bust)
            & (df["model"] < repl_thresh)
        )
        match = df[precondition].copy()
        n = len(match)
        if n == 0:
            return {"n": 0}
        # Naive (don't drop, hold and hope): target ~ prior_career (career baseline)
        # Rule-applied (DROP): expect target ~ model (low) — rule was correct if target stayed low
        # Win = target was indeed low (rule wisely dropped)
        # We compare: did rule's predicted low (model) beat naive's high (prior_career)?
        naive_err = (match["prior_career"] - match["target"]).abs()
        rule_err = (match["model"] - match["target"]).abs()
        wins = (rule_err < naive_err).sum()
        win_rate = wins / n
        below_prior = (match["target"] < match["prior_career"]).mean()
        lift = naive_err.mean() - rule_err.mean()
        return {
            "n": n,
            "win_rate": win_rate,
            "lift_mae": lift,
            "pct_below_prior": below_prior,
            "mean_target": match["target"].mean(),
            "mean_actuals_recent": match["actuals_recent"].mean(),
            "mean_model": match["model"].mean(),
            "mean_prior": match["prior_career"].mean(),
            "repl_thresh": repl_thresh,
        }

    h_res = _per_pop(h, sd_decline=0.4, sd_bust=0.4, q_replacement=0.25)
    sp_res = _per_pop(sp, sd_decline=2.0, sd_bust=2.0, q_replacement=0.25)
    return {"hitter": h_res, "sp": sp_res}


# ---------- Rule 5: Hot streak + capped discipline + RISING xwOBACON -> NARROW BREAKOUT, expect revert ----------
# Proxies:
#   Hot streak L5/L7     : actuals_recent > baseline_season + big sd
#   capped discipline    : NO sustained season rise (baseline_season ~ prior_career)
#   RISING xwOBACON      : prior_career > prior2_avg + sd
# Rule says: "expect revert toward L21 mean" -> verdict: NARROW BREAKOUT.
# Reality test: target should be ABOVE prior_career (rise real) but BELOW actuals_recent (revert).
def test_rule_5(h: pd.DataFrame, sp: pd.DataFrame) -> dict:
    def _per_pop(df: pd.DataFrame, sd_hot: float, sd_capped: float, sd_rise: float) -> dict:
        df = df.dropna(subset=["prior2_avg"]).copy()
        precondition = (
            (df["actuals_recent"] > df["baseline_season"] + sd_hot)
            & ((df["baseline_season"] - df["prior_career"]).abs() < sd_capped)
            & (df["prior_career"] > df["prior2_avg"] + sd_rise)
        )
        match = df[precondition].copy()
        n = len(match)
        if n == 0:
            return {"n": 0}
        # Naive (BUY on hot streak): expect target ~ actuals_recent (high)
        # Rule-applied (NARROW BREAKOUT, expect revert): expect target between baseline & actuals
        # Win = target is closer to (baseline + actuals)/2 than to pure actuals
        rule_midpoint = (match["baseline_season"] + match["actuals_recent"]) / 2
        naive_err = (match["actuals_recent"] - match["target"]).abs()
        rule_err = (rule_midpoint - match["target"]).abs()
        wins = (rule_err < naive_err).sum()
        win_rate = wins / n
        # Did targets actually revert below actuals_recent (a partial mean reversion)?
        pct_reverted = (match["target"] < match["actuals_recent"]).mean()
        # ...but stayed above prior_career (some real lift)?
        pct_above_prior = (match["target"] > match["prior_career"]).mean()
        lift = naive_err.mean() - rule_err.mean()
        return {
            "n": n,
            "win_rate": win_rate,
            "lift_mae": lift,
            "pct_reverted_below_hot": pct_reverted,
            "pct_stayed_above_prior": pct_above_prior,
            "mean_target": match["target"].mean(),
            "mean_actuals_recent": match["actuals_recent"].mean(),
            "mean_prior": match["prior_career"].mean(),
            "mean_rule_midpoint": rule_midpoint.mean(),
        }

    h_res = _per_pop(h, sd_hot=0.7, sd_capped=0.2, sd_rise=0.15)
    sp_res = _per_pop(sp, sd_hot=3.5, sd_capped=1.5, sd_rise=1.0)
    return {"hitter": h_res, "sp": sp_res}


def fmt_dict(d: dict, indent: int = 2) -> str:
    if d.get("n", 0) == 0:
        return " " * indent + "n=0 — no matching cases"
    lines = []
    for k, v in d.items():
        if isinstance(v, float):
            lines.append(f"{' ' * indent}- {k}: {v:.3f}")
        else:
            lines.append(f"{' ' * indent}- {k}: {v}")
    return "\n".join(lines)


def main() -> None:
    h, sp = load()
    print(f"Loaded: {len(h)} hitter snapshots, {len(sp)} SP snapshots")

    r1 = test_rule_1(h, sp)
    r2 = test_rule_2(h, sp)
    r3 = test_rule_3(h, sp)
    r4 = test_rule_4(h, sp)
    r5 = test_rule_5(h, sp)

    def verdict(rule_res: dict) -> str:
        # Aggregate hitter+SP win rate
        h_n = rule_res["hitter"].get("n", 0)
        s_n = rule_res["sp"].get("n", 0)
        if h_n + s_n == 0:
            return "INSUFFICIENT_N (no matches)"
        h_win = rule_res["hitter"].get("win_rate", 0) * h_n
        s_win = rule_res["sp"].get("win_rate", 0) * s_n
        pooled = (h_win + s_win) / (h_n + s_n)
        n_total = h_n + s_n
        if n_total < 10:
            return f"SMALL_N ({n_total}) — pooled win rate {pooled:.2%}"
        if pooled >= 0.55:
            return f"VALIDATED — pooled win rate {pooled:.2%} on n={n_total}"
        if pooled >= 0.50:
            return f"WEAK — pooled win rate {pooled:.2%} on n={n_total}"
        return f"REJECTED — pooled win rate {pooled:.2%} on n={n_total}"

    out_lines = [
        "# Conflict resolution rule lift test — 2026-06-06",
        "",
        "## Method",
        "",
        f"- Hitter snapshots: {len(h)}  |  SP snapshots: {len(sp)}",
        "- Source: `shrinkage_h_snap_2026-06-06.parquet` + `shrinkage_sp_snap_2026-06-06.parquet`",
        "- Forward outcome: `target` = mean BrownU FP/g (hitter, next 30d) or FP/start (SP, next 5 starts)",
        "- Tier B lenses (sustainability bucket, xwOBA L21d gap, xwOBACON YoY) are NOT in the parquets;",
        "  we approximate them from the L21/L42/prior/prior2 ladder. These are LOOKALIKE not exact matches.",
        "- Win = rule-applied verdict's predicted FP is closer to `target` than the naive verdict's.",
        "",
        "### Proxy mapping per rule",
        "- Rule 1: model FADE = model < prior - 0.2sd; L5 BUY = L21 > L42 + 0.5sd; NOISE = L21 hot but L42~prior",
        "- Rule 2: CAP_FODDER = L21 < prior - 0.4sd; xwOBA intact = |L42 - prior| < 0.2sd",
        "- Rule 3: REAL_DECLINE = L21 < L42 - 0.5sd; RISING xwOBACON = prior > prior2 + 0.15sd",
        "- Rule 4: REGRESS = L21 < L42 - 0.4sd; CAP_FODDER = L21 < prior - 0.4sd; repl-level = model in bottom Q",
        "- Rule 5: hot = L21 > L42 + 0.7sd; capped discipline = |L42 - prior| < 0.2sd; rising = prior > prior2 + 0.15sd",
        "",
        "## Rule 1: Model FADE + actuals BUY -> NOISE -> trust model (fade hot streak)",
        "",
        "**Verdict: " + verdict(r1) + "**",
        "",
        "### Hitter cases",
        fmt_dict(r1["hitter"]),
        "",
        "### SP cases",
        fmt_dict(r1["sp"]),
        "",
        "## Rule 2: CAP_FODDER + xwOBA gap intact -> HOLD (process trumps boom-bust)",
        "",
        "**Verdict: " + verdict(r2) + "**",
        "",
        "### Hitter cases",
        fmt_dict(r2["hitter"]),
        "",
        "### SP cases",
        fmt_dict(r2["sp"]),
        "",
        "## Rule 3: REAL_DECLINE L21d + RISING xwOBACON -> HOLD with sell-high optionality",
        "",
        "**Verdict: " + verdict(r3) + "**",
        "",
        "### Hitter cases",
        fmt_dict(r3["hitter"]),
        "",
        "### SP cases",
        fmt_dict(r3["sp"]),
        "",
        "## Rule 4: REGRESS + CAP_FODDER + replacement-level Blended xFP -> HIGH_CONFIDENCE drop",
        "",
        "**Verdict: " + verdict(r4) + "**",
        "",
        "### Hitter cases",
        fmt_dict(r4["hitter"]),
        "",
        "### SP cases",
        fmt_dict(r4["sp"]),
        "",
        "## Rule 5: Hot streak + capped discipline + RISING xwOBACON -> NARROW BREAKOUT (expect revert)",
        "",
        "**Verdict: " + verdict(r5) + "**",
        "",
        "### Hitter cases",
        fmt_dict(r5["hitter"]),
        "",
        "### SP cases",
        fmt_dict(r5["sp"]),
        "",
        "## Caveats",
        "",
        "1. **Lookalike, not exact.** The protocol's Tier B lenses (sustainability bucket label,",
        "   xwOBA L21d gap, xwOBACON YoY trajectory) are NOT in these parquets. We synthesize",
        "   from L21/L42/prior/prior2 FP rates. A real sus=NOISE/LEGIT label uses Statcast skill",
        "   markers, not FP rate ladders. So these tests bound the protocol's mechanical logic,",
        "   not its actual Tier B signal quality.",
        "2. **Forward target is 30 days, not season-EoY.** The 30d window can under-weight mean",
        "   reversion that plays out over 60+ days.",
        "3. **Small N for Rule 3 + 5** because prior2_avg is missing on 56% of hitter rows (rookies",
        "   + recent debuts). These are the rules most at risk of N=0.",
        "4. **Win metric is MAE-based.** A rule that's directionally right but quantitatively off",
        "   can still 'win' the case; we report mean target vs mean rule-predicted-FP alongside.",
        "5. **Bayes shrinkage as model proxy** under-states Tier A — the real Blended xFP includes",
        "   archetype + PL + multi-feature blend. So 'model FADE' here is conservative.",
        "",
    ]
    OUT_MD.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print()
    print("=== SUMMARY ===")
    for i, r in enumerate([r1, r2, r3, r4, r5], 1):
        print(f"Rule {i}: {verdict(r)}")


if __name__ == "__main__":
    main()
