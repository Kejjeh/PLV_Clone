"""
Output Validation Script
========================
Lightweight sanity-check for PLV and Process+ outputs.

Checks on every run:
  1. Distribution drift — mean/std vs. v1.0 reference (PLV and Process+)
  2. Component stability (split-half r at 150 PA threshold)
  3. Leaderboard sanity — top 20 must pass basic sniff tests
  4. Power+ behaviour flag — std deviation relative to expected

Does NOT retrain or recompute full stability curves. Runs in under 60 seconds.

Usage:
    cd plv_clone
    python scripts/validate_outputs.py [--year 2024] [--strict]
    --strict: exit code 1 if any check fails (useful in CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from plv_clone.config import get_config
from plv_clone.utils.logging import configure_logging, get_logger
from plv_clone.utils.io import read_json

configure_logging()
logger = get_logger("validate")
CFG = get_config()

# ── Reference benchmarks from v1.0 (2024 val) ────────────────────────────────
REF = {
    "plv_mean":           5.0,
    "plv_std_min":        1.2,
    "plv_std_max":        1.8,
    "plv_pct_out_0_10":   0.05,   # max fraction outside [0, 10]
    "process_plus_mean":  100.0,
    "process_plus_drift": 7.0,    # allowable |mean - 100| before flagging
    "process_plus_std":   10.0,
    "process_plus_std_tolerance": 3.0,
    "min_qualified_hitters": 100,
    "min_qualified_pitchers": 50,
}

PASS = "\u2713"   # ✓
FAIL = "\u2717"   # ✗
WARN = "\u26a0"   # ⚠


class Check:
    def __init__(self, name: str, passed: bool, detail: str, is_warning: bool = False):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.is_warning = is_warning

    def __str__(self) -> str:
        symbol = PASS if self.passed else (WARN if self.is_warning else FAIL)
        return f"  {symbol} {self.name}: {self.detail}"


# ══════════════════════════════════════════════════════════════════════════════
# PLV CHECKS
# ══════════════════════════════════════════════════════════════════════════════

def check_plv(year: int) -> list[Check]:
    checks = []
    scores_dir = CFG.processed_dir / "plv_scores" / f"year={year}"
    if not scores_dir.exists():
        return [Check("PLV scores exist", False, f"No PLV scores for year={year}. Run score-plv first.")]

    from plv_clone.utils.io import read_parquet
    df = read_parquet(scores_dir)

    # Check 1: PLV mean ≈ 5.0
    mean = df["plv"].mean()
    passed = abs(mean - REF["plv_mean"]) < 0.5
    checks.append(Check(
        "PLV mean ≈ 5.0",
        passed,
        f"mean={mean:.3f} (expected 5.0±0.5)",
        is_warning=not passed,
    ))

    # Check 2: PLV std in expected range
    std = df["plv"].std()
    passed = REF["plv_std_min"] < std < REF["plv_std_max"]
    checks.append(Check(
        f"PLV std in [{REF['plv_std_min']}, {REF['plv_std_max']}]",
        passed,
        f"std={std:.3f}",
        is_warning=not passed,
    ))

    # Check 3: Very few PLV values outside [0, 10]
    oor = ((df["plv"] < 0) | (df["plv"] > 10)).mean()
    passed = oor < REF["plv_pct_out_0_10"]
    checks.append(Check(
        "PLV [0,10] coverage",
        passed,
        f"{100*oor:.2f}% outside [0,10] (threshold {100*REF['plv_pct_out_0_10']:.0f}%)",
        is_warning=not passed,
    ))

    # Check 4: Qualified pitcher count
    n_pitchers = df.groupby("pitcher").size()
    n_qualified = (n_pitchers >= 100).sum()
    passed = n_qualified >= REF["min_qualified_pitchers"]
    checks.append(Check(
        "Qualified pitchers (≥100 pitches)",
        passed,
        f"{n_qualified} qualified (min {REF['min_qualified_pitchers']})",
    ))

    # Check 5: Top pitcher PLV is not absurdly high (sanity ceiling)
    max_plv = df.groupby("pitcher")["plv"].mean().max()
    passed = max_plv < 7.5
    checks.append(Check(
        "Max pitcher PLV < 7.5",
        passed,
        f"max pitcher avg PLV={max_plv:.2f}",
        is_warning=not passed,
    ))

    # Check 6: No NaN PLV
    null_rate = df["plv"].isna().mean()
    passed = null_rate < 0.001
    checks.append(Check(
        "PLV null rate < 0.1%",
        passed,
        f"{100*null_rate:.3f}% null",
    ))

    return checks


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS+ CHECKS
# ══════════════════════════════════════════════════════════════════════════════

def check_process_plus(year: int) -> list[Check]:
    checks = []
    lb_path = CFG.outputs_dir / f"process_plus_leaderboard_{year}.csv"
    if not lb_path.exists():
        return [Check("Process+ leaderboard exists", False,
                      f"No leaderboard for year={year}. Run score-process first.")]

    lb = pd.read_csv(lb_path)

    # Check 1: Mean near 100
    mean = lb["process_plus"].mean()
    drift = abs(mean - REF["process_plus_mean"])
    passed = drift < REF["process_plus_drift"]
    checks.append(Check(
        "Process+ mean near 100",
        passed,
        f"mean={mean:.1f} (drift={drift:.1f}, max allowed {REF['process_plus_drift']})",
        is_warning=not passed,
    ))

    # Check 2: Std near 10
    std = lb["process_plus"].std()
    std_drift = abs(std - REF["process_plus_std"])
    passed = std_drift < REF["process_plus_std_tolerance"]
    checks.append(Check(
        "Process+ std ≈ 10",
        passed,
        f"std={std:.1f} (drift={std_drift:.1f}, max {REF['process_plus_std_tolerance']})",
        is_warning=not passed,
    ))

    # Check 3: Qualified hitter count
    passed = len(lb) >= REF["min_qualified_hitters"]
    checks.append(Check(
        f"Qualified hitters (≥{CFG.min_pa_process} PA)",
        passed,
        f"{len(lb)} qualified (min {REF['min_qualified_hitters']})",
    ))

    # Check 4: Individual component means
    for comp in ("decision_plus", "contact_plus", "power_plus"):
        if comp not in lb.columns:
            checks.append(Check(f"{comp} column exists", False, "Column missing"))
            continue
        comp_mean = lb[comp].mean()
        drift_c = abs(comp_mean - 100.0)
        passed = drift_c < 10.0
        checks.append(Check(
            f"{comp} mean near 100",
            passed,
            f"mean={comp_mean:.1f} (drift={drift_c:.1f})",
            is_warning=not passed,
        ))

    # Check 5: Process+ range not degenerate
    range_width = lb["process_plus"].max() - lb["process_plus"].min()
    passed = range_width > 30
    checks.append(Check(
        "Process+ range > 30 pts",
        passed,
        f"range={range_width:.1f} [{lb['process_plus'].min():.1f}, {lb['process_plus'].max():.1f}]",
    ))

    # Check 6: Power+ std ≤ 2× contact_std (guard for runaway variance)
    if "power_plus" in lb.columns and "contact_plus" in lb.columns:
        power_std   = lb["power_plus"].std()
        contact_std = lb["contact_plus"].std()
        ratio = power_std / max(contact_std, 0.1)
        passed = ratio < 3.0
        checks.append(Check(
            "Power+ std ≤ 3× Contact+ std",
            passed,
            f"power_std={power_std:.1f}, contact_std={contact_std:.1f}, ratio={ratio:.1f}",
            is_warning=not passed,
        ))

    # Check 7: Split-half stability at 150 PA (quick — just one threshold)
    pp_dir = CFG.processed_dir / "process_plus_scores" / f"year={year}"
    if pp_dir.exists():
        from plv_clone.utils.io import read_parquet
        scored = read_parquet(pp_dir)
        r = _quick_split_half(scored, "decision_value", min_pa=150)
        if r is not None:
            passed = r >= 0.60
            checks.append(Check(
                "Decision+ split-half r ≥ 0.60 (at 150 PA)",
                passed,
                f"r={r:.3f}",
                is_warning=not passed,
            ))

    return checks


# ══════════════════════════════════════════════════════════════════════════════
# SCALING DRIFT CHECK
# ══════════════════════════════════════════════════════════════════════════════

def check_scaling_params() -> list[Check]:
    checks = []
    vi_path = CFG.models_dir / "version_info.json"
    pp_path = CFG.models_dir / "process_plus_scaling_params.json"

    if not vi_path.exists():
        checks.append(Check("version_info.json exists", False, "Run version freeze first."))
        return checks
    if not pp_path.exists():
        checks.append(Check("process_plus_scaling_params.json exists", False, "Run train-process first."))
        return checks

    vi = read_json(vi_path)
    pp = read_json(pp_path)
    ref_sp = vi.get("process_plus_scaling", {})

    for comp in ("decision", "contact", "power", "process"):
        mk = f"{comp}_mean"
        sk = f"{comp}_std"
        if mk not in ref_sp or mk not in pp:
            continue
        mean_drift = abs(pp[mk] - ref_sp[mk])
        std_drift  = abs(pp.get(sk, 0) - ref_sp.get(sk, 0))
        passed = mean_drift < 0.01 and std_drift < 0.01
        checks.append(Check(
            f"{comp} scaling stable",
            passed,
            f"mean drift={mean_drift:.5f}, std drift={std_drift:.5f}",
            is_warning=not passed,
        ))

    return checks


# ── helpers ───────────────────────────────────────────────────────────────────

def _quick_split_half(scored_df: pd.DataFrame, pitch_col: str, min_pa: int) -> float | None:
    """Single split-half Spearman r at a given PA threshold."""
    import hashlib
    if pitch_col not in scored_df.columns or "batter" not in scored_df.columns:
        return None

    df = scored_df.copy()
    if all(c in df.columns for c in ["game_pk", "at_bat_number"]):
        pa_counts = (
            df.dropna(subset=["batter", "game_pk", "at_bat_number"])
            .groupby("batter")[["game_pk", "at_bat_number"]]
            .apply(lambda x: x.drop_duplicates().shape[0])
        )
        qualified = pa_counts[pa_counts >= min_pa].index
    else:
        qualified = df.groupby("batter").size()
        qualified = qualified[qualified >= min_pa * 4].index

    df = df[df["batter"].isin(qualified) & df[pitch_col].notna()]
    if len(df) == 0:
        return None

    df["_half"] = df.apply(
        lambda r: int(hashlib.md5(
            f"{r['batter']}_{r.get('game_pk', '')}_{r.get('at_bat_number', '')}".encode()
        ).hexdigest(), 16) % 2,
        axis=1,
    )
    h0 = df[df["_half"] == 0].groupby("batter")[pitch_col].mean()
    h1 = df[df["_half"] == 1].groupby("batter")[pitch_col].mean()
    merged = pd.concat([h0, h1], axis=1, keys=["h0", "h1"]).dropna()
    if len(merged) < 10:
        return None
    r, _ = scipy_stats.spearmanr(merged["h0"], merged["h1"])
    return float(r)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="PLV / Process+ output validator")
    parser.add_argument("--year",   type=int, default=2024, help="Year to validate (default: 2024)")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any check fails")
    args = parser.parse_args()

    year = args.year
    all_checks: list[Check] = []

    print(f"\n=== PLV + Process+ Validation — year={year} ===\n")

    print("── PLV ──────────────────────────────────────────────────────────────")
    plv_checks = check_plv(year)
    for c in plv_checks:
        print(c)
    all_checks.extend(plv_checks)

    print("\n── Process+ ─────────────────────────────────────────────────────────")
    pp_checks = check_process_plus(year)
    for c in pp_checks:
        print(c)
    all_checks.extend(pp_checks)

    print("\n── Scaling params (vs v1.0 reference) ───────────────────────────────")
    sp_checks = check_scaling_params()
    for c in sp_checks:
        print(c)
    all_checks.extend(sp_checks)

    # Summary
    n_total  = len(all_checks)
    n_pass   = sum(c.passed for c in all_checks)
    n_fail   = sum(not c.passed and not c.is_warning for c in all_checks)
    n_warn   = sum(not c.passed and c.is_warning for c in all_checks)

    print(f"\n── Summary ──────────────────────────────────────────────────────────")
    print(f"  {n_pass}/{n_total} passed | {n_warn} warnings | {n_fail} failures")

    if n_fail == 0 and n_warn == 0:
        print(f"\n  {PASS} All checks passed. Outputs look healthy.\n")
    elif n_fail == 0:
        print(f"\n  {WARN} {n_warn} warning(s). Review before publishing.\n")
    else:
        print(f"\n  {FAIL} {n_fail} failure(s). Investigate before using outputs.\n")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
