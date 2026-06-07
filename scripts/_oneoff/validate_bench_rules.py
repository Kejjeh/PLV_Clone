"""
Empirically validate 4 proposed SP bench-decision rules.

Backtests against the per-start panel at
data/research/_boom_stack_per_start_panel_cache.parquet (2018-2025).
We focus on 2024-2025 starts (closest to today's environment).

Operationalization of the 4 rules using available per-start features
(rp3/blend/sustainability are point-in-time today and not historically
reconstructable, so we use the closest documented proxies):

  Rule 1 (Ace, never bench): boom_stack_pre >= 3  -> START
  Rule 2 (Mid, bench tough opp):
      boom_stack_pre == 2 AND opp_tertile == 3      -> BENCH
      (opp_tertile=3 == hardest-bat tertile == bat_index >= ~1.05)
  Rule 3 (Tier B FLAGGED, K%-drop proxy):
      boom_stack_pre in {0,1} AND
      (rolling K% over prior 5 starts is >= 8pp BELOW the player's
       L5-before-that K%, OR flag_skill_spike==0 sustained 0 over L5)
      Bench UNLESS opp_tertile == 1 (soft)
  Rule 4 (Cap-rental, L8 boom_rate=0):
      boom_stack_pre == 0 AND last-8 boom_outcome rate == 0
      AND has at least 8 prior starts in season  -> BENCH

A start is a "bust" if fp < 5.0  (per CLAUDE.md SP bust threshold).
A start is a "boom" if fp >= 20.

Outputs markdown report and prints summary.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("c:/Users/Joshua/plv_clone")
PANEL = ROOT / "data/research/_boom_stack_per_start_panel_cache.parquet"
OUT = ROOT / "data/research/validation_runs/bench_rule_validation_2026-06-06.md"

BUST_FP = 5.0
BOOM_FP = 20.0
REPLACEMENT_FP = 5.0  # cap-fodder streamer level; benching avoids <5 FP


def load_panel() -> pd.DataFrame:
    df = pd.read_parquet(PANEL).copy()
    df = df.sort_values(["pitcher", "year", "game_date"]).reset_index(drop=True)
    # restrict to 2024 + 2025 (closest to current env). Include 2023 as well so
    # sample size for rule 4 (needs >=8 prior starts) holds.
    df = df[df["year"].isin([2023, 2024, 2025])].copy()
    return df


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["pitcher", "year", "game_date"]).reset_index(drop=True)
    g = df.groupby(["pitcher", "year"], sort=False, group_keys=False)

    df["k_pct_l5"] = g["k_pct"].transform(lambda s: s.shift(1).rolling(5, min_periods=3).mean())
    df["k_pct_prior5"] = g["k_pct"].transform(lambda s: s.shift(6).rolling(5, min_periods=3).mean())
    df["boom_rate_l8"] = g["boom_outcome"].transform(lambda s: s.shift(1).rolling(8, min_periods=4).mean())
    df["n_starts_so_far"] = g.cumcount()
    return df


def apply_rules(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rule"] = ""
    df["verdict"] = "START"  # default

    # Rule 1: Ace, never bench
    r1 = df["boom_stack_pre"] >= 3
    df.loc[r1, "rule"] = "R1_ACE"
    # already default START

    # Rule 2: Mid + tough opp -> BENCH
    r2 = (df["rule"] == "") & (df["boom_stack_pre"] == 2) & (df["opp_tertile"] == 3.0)
    df.loc[r2, "rule"] = "R2_MID_TOUGH"
    df.loc[r2, "verdict"] = "BENCH"

    # Rule 3: K% drop >=8pp vs prior window  (boom_stack 0/1 only)
    k_drop = (df["k_pct_prior5"] - df["k_pct_l5"]) >= 0.08
    r3_cond = (
        (df["rule"] == "")
        & df["boom_stack_pre"].isin([0, 1])
        & k_drop.fillna(False)
        & (df["n_starts_so_far"] >= 10)
    )
    soft = df["opp_tertile"] == 1.0
    df.loc[r3_cond & ~soft, "rule"] = "R3_FLAGGED"
    df.loc[r3_cond & ~soft, "verdict"] = "BENCH"
    df.loc[r3_cond & soft, "rule"] = "R3_FLAGGED_SOFT"
    # leave R3_FLAGGED_SOFT as START

    # Rule 4: cap-rental streamer w/ L8 boom rate = 0 -> BENCH
    r4 = (
        (df["rule"] == "")
        & (df["boom_stack_pre"] == 0)
        & (df["boom_rate_l8"].fillna(1.0) == 0.0)
        & (df["n_starts_so_far"] >= 8)
    )
    df.loc[r4, "rule"] = "R4_CAP_RENTAL"
    df.loc[r4, "verdict"] = "BENCH"

    return df


def rule_stats(df: pd.DataFrame, rule_name: str, mean_all: float) -> dict:
    sub = df[df["rule"] == rule_name]
    if sub.empty:
        return dict(rule=rule_name, n=0)

    bench = sub[sub["verdict"] == "BENCH"]
    start = sub[sub["verdict"] == "START"]

    # for never-bench rules (R1, R3_SOFT) precision/recall aren't meaningful as bench
    if bench.empty:
        return dict(
            rule=rule_name,
            n=len(sub),
            verdict_breakdown=f"all START ({len(start)})",
            mean_fp_start=round(sub["fp"].mean(), 2),
            boom_rate_start=round((sub["fp"] >= BOOM_FP).mean(), 3),
            bust_rate_start=round((sub["fp"] < BUST_FP).mean(), 3),
        )

    bench_is_bust = bench["fp"] < BUST_FP
    precision = bench_is_bust.mean()  # of BENCH calls, what % were correctly low-FP
    # recall: of all bust starts in this rule's applicable subset, what % did we bench?
    all_busts_in_sub = (sub["fp"] < BUST_FP).sum()
    recall = bench_is_bust.sum() / all_busts_in_sub if all_busts_in_sub else float("nan")

    # Net FP swing: benching avoids the start's FP and substitutes REPLACEMENT_FP
    # (cap-fodder/handcuff baseline). Net per benched start = REPLACEMENT_FP - actual_fp.
    # Sum across all BENCH calls.
    saved = (REPLACEMENT_FP - bench["fp"]).sum()
    # If we had instead started everyone (naive), total FP = bench["fp"].sum().
    # Net FP swing of applying rule on bench cases = saved (positive = rule helped).

    # Distinguish "saved FP from correctly benched busts" vs "lost FP from incorrectly
    # benched good starts" for diagnostic insight.
    saved_from_busts = (REPLACEMENT_FP - bench.loc[bench_is_bust, "fp"]).sum()
    lost_from_goods = (bench.loc[~bench_is_bust, "fp"] - REPLACEMENT_FP).sum()

    return dict(
        rule=rule_name,
        n=len(sub),
        n_bench=len(bench),
        n_start=len(start),
        mean_fp_if_started=round(sub["fp"].mean(), 2),
        mean_fp_bench_cases=round(bench["fp"].mean(), 2),
        mean_fp_start_cases=round(start["fp"].mean(), 2) if len(start) else None,
        precision_bench_correct=round(precision, 3),
        recall_busts_caught=round(recall, 3) if not np.isnan(recall) else None,
        saved_from_busts=round(saved_from_busts, 1),
        lost_from_goods=round(lost_from_goods, 1),
        net_fp_swing=round(saved, 1),
        net_fp_swing_per_bench=round(saved / max(len(bench), 1), 2),
        boom_rate_among_bench=round((bench["fp"] >= BOOM_FP).mean(), 3),
        bust_rate_among_bench=round(bench_is_bust.mean(), 3),
    )


def main() -> int:
    df = load_panel()
    print(f"Loaded {len(df):,} starts ({df['year'].min()}-{df['year'].max()})")

    df = add_rolling_features(df)
    df = apply_rules(df)

    mean_all = df["fp"].mean()
    print(f"Overall mean FP: {mean_all:.2f}")
    print(df["rule"].value_counts(dropna=False).to_string())
    print(df["verdict"].value_counts().to_string())

    results = []
    for r in ["R1_ACE", "R2_MID_TOUGH", "R3_FLAGGED", "R3_FLAGGED_SOFT", "R4_CAP_RENTAL"]:
        results.append(rule_stats(df, r, mean_all))

    # Pooled: only BENCH calls (R2, R3, R4); R1 and R3_SOFT are pure START so they
    # contribute zero swing. Compare to naive "always start" baseline.
    bench_df = df[df["verdict"] == "BENCH"]
    pool_saved = (REPLACEMENT_FP - bench_df["fp"]).sum()
    pool_bust = (bench_df["fp"] < BUST_FP).mean()
    pool_n_bench = len(bench_df)
    pool_total_starts = len(df)
    pool_bust_all = (df["fp"] < BUST_FP).sum()
    pool_recall = ((bench_df["fp"] < BUST_FP).sum() / pool_bust_all) if pool_bust_all else float("nan")
    pool_per_start_lift = pool_saved / pool_total_starts

    lines = []
    lines.append("# Bench-Rule Validation 2026-06-06")
    lines.append("")
    lines.append(f"- Panel: `_boom_stack_per_start_panel_cache.parquet`")
    lines.append(f"- Years: 2023-2025 ({df['year'].min()}-{df['year'].max()})")
    lines.append(f"- Total starts: **{len(df):,}**")
    lines.append(f"- Overall mean FP: **{mean_all:.2f}**, bust rate (<{BUST_FP}): {(df['fp']<BUST_FP).mean():.3f}, boom rate (>={BOOM_FP}): {(df['fp']>=BOOM_FP).mean():.3f}")
    lines.append(f"- REPLACEMENT_FP (handcuff/cap-fodder baseline): {REPLACEMENT_FP}")
    lines.append("")
    lines.append("## Operationalization note")
    lines.append("")
    lines.append("Live rp3 / blend / sustainability tags are present-day snapshots and cannot")
    lines.append("be reconstructed point-in-time historically. We use the documented per-start")
    lines.append("proxies: `boom_stack_pre` (tier signal), `opp_tertile` (TOUGH=3 / SOFT=1),")
    lines.append("`k_pct` rolling 5+5 split (Rule 3 K%-drop), `boom_outcome` L8 (Rule 4).")
    lines.append("")
    lines.append("## Per-rule results")
    lines.append("")
    for r in results:
        lines.append(f"### {r['rule']}  (n={r.get('n',0)})")
        for k, v in r.items():
            if k in ("rule", "n"):
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.append("## Pooled outcomes if all 4 rules applied 2023-2025")
    lines.append("")
    lines.append(f"- BENCH calls (R2+R3+R4): **{pool_n_bench:,}** out of {pool_total_starts:,} starts ({pool_n_bench/pool_total_starts:.1%})")
    lines.append(f"- Bust rate among benched: **{pool_bust:.3f}**  (vs overall {(df['fp']<BUST_FP).mean():.3f})")
    lines.append(f"- Recall of all bust starts caught: **{pool_recall:.3f}**")
    lines.append(f"- Total FP swing: **{pool_saved:+,.1f} FP** across {pool_total_starts:,} starts")
    lines.append(f"- Per-start FP lift over naive (start everyone): **{pool_per_start_lift:+.3f} FP/start**")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    # build recommendations from results
    for r in results:
        if r.get("n", 0) == 0:
            lines.append(f"- **{r['rule']}**: zero applicable starts in panel — rule too restrictive or unobserved.")
            continue
        if "n_bench" not in r:
            lines.append(f"- **{r['rule']}**: pure START rule (n={r['n']}); mean FP {r.get('mean_fp_start')} -> {'SHIP' if r.get('mean_fp_start',0) > mean_all else 'ship cautiously'}.")
            continue
        net = r.get("net_fp_swing", 0)
        prec = r.get("precision_bench_correct", 0)
        if net > 0 and prec >= 0.45:
            verdict = "SHIP AS-IS"
        elif net > 0:
            verdict = "SHIP CAUTIOUS (positive swing but low precision)"
        elif net < 0 and prec < 0.30:
            verdict = "REJECT (negative swing, benching good starts)"
        else:
            verdict = "TUNE (marginal)"
        lines.append(f"- **{r['rule']}**: net {net:+.1f} FP across {r.get('n_bench')} BENCH calls (per-bench {r.get('net_fp_swing_per_bench')}). Precision {prec:.2f}, recall {r.get('recall_busts_caught')}. -> **{verdict}**")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- Top-rank sampling: panel includes every SP start, not just top-200-by-rp3.")
    lines.append("  For top-rank-only sampling, restrict to pitchers with prior-year fp_total >= ~250.")
    lines.append("- Replacement FP assumed = 5.0 (cap-fodder handcuff). True replacement varies by")
    lines.append("  league depth (BrownU 8-team: probably closer to 6-8 FP for actual streamers).")
    lines.append("- Rule 3's K%-drop proxy is mechanical; the spec's 'sustainability NOISE/REGRESS' is")
    lines.append("  not directly available historically. Live deployment should use that tag instead.")
    lines.append("- Rule 4 boom_outcome threshold is panel-defined (>=20 FP). Matches CLAUDE.md.")
    lines.append("- 2026 in-season starts excluded (not in panel cache). Re-run after refresh.")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT}")

    print("\n--- SUMMARY ---")
    for r in results:
        print(r)
    print(f"\nPOOLED: bench {pool_n_bench}/{pool_total_starts} starts, net {pool_saved:+.1f} FP, per-start lift {pool_per_start_lift:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
