"""run_verdict_scorecard.py — engine for the /verdict-scorecard skill.

DECISION-quality accountability, the sibling of /model-health (which measures
MODEL accuracy). Nothing else measures whether our VERDICTS — the BUY / HOLD /
CAUTION / FADE / MIXED synthesized by /triangulate and logged daily by the
decision chain (refresh steps 4.10a/b/c) — actually discriminate.

Data chain consumed (read-only):
  log_roster_decisions.py  -> data/research/decisions/{date}/{id}.json   (source)
  settle_decisions.py      -> data/research/decisions/settled/{date}/{id}.json
                              (realized FP/unit vs proj, classification)

Settlement semantics (settler.SETTLEMENT_WINDOWS):
  H  : 21d window, min 30 PA,  unit FP/PA,          hit threshold ±0.02
  SP : 35d window, min 5 GS,   unit FP/start,       hit threshold ±1.0
  RP : 35d window, min 10 app, unit FP/appearance,  hit threshold ±0.5
  BUY_HIT  = residual > +thr | FADE_HIT = residual < -thr | others *_MISS
  HOLD/CAUTION/MIXED settle as {verdict}_NEUTRAL (no directional claim).

What this engine reports (all settled decisions to date):
  1. Verdict ladder per bucket: n, unique players, mean/median realized
     FP-per-unit, matched projection, residual, directional hit rate.
  2. Monotonicity check: do realized outcomes order BUY > HOLD > CAUTION > FADE?
  3. BUY-vs-FADE discrimination (did BUYs out-realize FADEs?).
  4. Confidence calibration (the 0.25/0.5/0.75/1.0 confidence field).
  5. Worst calls — biggest verdict-vs-outcome misses, named (deduped by player).
  6. Honest power framing (Rule 5): settled n, effective n (unique players),
     EARLY-READ banner while n < 100 + the projected date it becomes powered.

KNOWN CAVEAT surfaced (not silently fixed): inputs['proj_per'] is unit-
inconsistent for H (rh3 FP/GAME vs settled FP/PA) and RP (rprs2 RoS TOTAL vs
FP/appearance) — so residual-based hit rates are only unit-honest for SP.
Realized-FP comparisons across verdicts (the ladder + BUY-vs-FADE test) are
unit-safe because they never touch proj_per. The engine prints the warning
whenever the projection/actual scale ratio betrays the mismatch.

Rule 13: this is a scoreboard, not a ranker — it never moves rh3/rp3/rprs2.

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/xfp/run_verdict_scorecard.py
  ... --today 2026-07-10        # override 'today' for the power projection
Output: console + data/outputs/verdict_scorecard.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plv_clone.decisions import DECISIONS_ROOT, SETTLEMENT_WINDOWS  # noqa: E402

DECISIONS = Path(DECISIONS_ROOT)
SETTLED = DECISIONS / "settled"
OUT_CSV = ROOT / "data" / "outputs" / "verdict_scorecard.csv"

VERDICT_LADDER = ["BUY", "HOLD", "CAUTION", "FADE"]  # expected realized order
ALL_VERDICTS = ["BUY", "HOLD", "CAUTION", "FADE", "MIXED"]
POWER_N = 100  # below this, present everything as an EARLY READ (Rule 5)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _load_json_tree(root: Path, skip: Path | None = None) -> list[dict]:
    out: list[dict] = []
    if not root.exists():
        return out
    skip_r = skip.resolve() if skip else None
    for p in sorted(root.rglob("*.json")):
        if skip_r is not None and skip_r in p.resolve().parents:
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  WARN corrupt JSON skipped: {p}")
            continue
        if isinstance(payload, dict) and payload.get("decision_id"):
            out.append(payload)  # only DecisionRecord-shaped payloads
    return out


def load_settled() -> pd.DataFrame:
    """One row per settled decision (authoritative: the settled/ mirror tree)."""
    recs = _load_json_tree(SETTLED)
    rows = []
    for r in recs:
        s = r.get("settlement") or {}
        if not r.get("settled_at") or not s:
            continue
        rows.append(dict(
            decision_id=r["decision_id"], snapshot_date=r["snapshot_date"],
            player=r["player_name"], mlbam_id=r.get("mlbam_id"),
            bucket=r["bucket"], verdict=r["verdict_top"],
            reason_tag=r.get("reason_tag"), confidence=r.get("confidence"),
            proj_per=s.get("proj_per"), actual=s.get("actual_fp_per_unit"),
            residual=s.get("residual"), n_events=s.get("n_events"),
            unit=s.get("event_unit"), classification=s.get("classification"),
            settled_at=r["settled_at"],
        ))
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates("decision_id").reset_index(drop=True)
    return df


def load_pending_ripe_dates() -> list[date]:
    """Ripe date (snapshot + window_days) for every UNSETTLED source record —
    used to project when total settled n crosses POWER_N."""
    settled_ids = set()
    for r in _load_json_tree(SETTLED):
        settled_ids.add(r.get("decision_id"))
    ripe: list[date] = []
    for r in _load_json_tree(DECISIONS, skip=SETTLED):
        if r.get("decision_id") in settled_ids:
            continue
        b = r.get("bucket")
        if b not in SETTLEMENT_WINDOWS:
            continue
        try:
            snap = date.fromisoformat(str(r.get("snapshot_date"))[:10])
        except ValueError:
            continue
        if snap.year == 2020:
            continue
        ripe.append(snap + timedelta(days=SETTLEMENT_WINDOWS[b]["days"]))
    return ripe


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _hit_rate(sub: pd.DataFrame) -> float | None:
    d = sub[sub["verdict"].isin(["BUY", "FADE"])]
    if not len(d):
        return None
    return float(d["classification"].str.endswith("_HIT").mean())


def build_ladder(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (bkt, v), g in df.groupby(["bucket", "verdict"]):
        rows.append(dict(
            bucket=bkt, verdict=v, n=len(g),
            n_players=g["player"].nunique(),
            mean_actual=round(float(g["actual"].mean()), 3),
            median_actual=round(float(g["actual"].median()), 3),
            mean_proj_per=round(float(g["proj_per"].mean()), 3),
            mean_residual=round(float(g["residual"].mean()), 3),
            hit_rate=(round(_hit_rate(g), 3) if v in ("BUY", "FADE") else None),
            unit=g["unit"].iloc[0],
        ))
    out = pd.DataFrame(rows)
    if len(out):
        order = {v: i for i, v in enumerate(ALL_VERDICTS)}
        out["_o"] = out["verdict"].map(order)
        out = out.sort_values(["bucket", "_o"]).drop(columns="_o").reset_index(drop=True)
    return out


def monotonicity(ladder: pd.DataFrame, bucket: str) -> tuple[str, list[str]]:
    """Check realized FP-per-unit ordering down the BUY>HOLD>CAUTION>FADE ladder
    (MIXED excluded — no directional claim). Returns (verdict, present_rungs)."""
    sub = ladder[(ladder["bucket"] == bucket) & ladder["verdict"].isin(VERDICT_LADDER)]
    rungs = [v for v in VERDICT_LADDER if v in set(sub["verdict"])]
    if len(rungs) < 2:
        return "NOT-TESTABLE (fewer than 2 directional/graded rungs settled)", rungs
    means = [float(sub[sub["verdict"] == v]["mean_actual"].iloc[0]) for v in rungs]
    ok = all(means[i] >= means[i + 1] for i in range(len(means) - 1))
    desc = " > ".join(f"{v} {m:.3f}" for v, m in zip(rungs, means))
    return (f"MONOTONIC ({desc})" if ok else f"NON-MONOTONIC ({desc})"), rungs


def buy_vs_fade(df: pd.DataFrame, bucket: str) -> str:
    b = df[(df["bucket"] == bucket) & (df["verdict"] == "BUY")]["actual"]
    f = df[(df["bucket"] == bucket) & (df["verdict"] == "FADE")]["actual"]
    if not len(b) or not len(f):
        return "NOT-TESTABLE (need settled BUYs and FADEs)"
    line = (f"BUY mean {b.mean():.3f} (n={len(b)}) vs FADE mean {f.mean():.3f} "
            f"(n={len(f)}) -> BUYs {'OUT-realized' if b.mean() > f.mean() else 'did NOT out-realize'} FADEs")
    try:
        from scipy.stats import mannwhitneyu
        _, pval = mannwhitneyu(b, f, alternative="greater")
        line += f" (Mann-Whitney one-sided p={pval:.3f})"
    except Exception:
        pass
    if min(len(b), len(f)) < 10:
        line += " [tiny n — direction only, not evidence]"
    return line


def confidence_calibration(df: pd.DataFrame) -> pd.DataFrame:
    """Higher confidence should mean better outcomes. Directional decisions get a
    hit-rate; every settled decision contributes realized-vs-median direction."""
    if "confidence" not in df.columns or df["confidence"].isna().all():
        return pd.DataFrame()
    rows = []
    for conf, g in df.groupby("confidence"):
        d = g[g["verdict"].isin(["BUY", "FADE"])]
        rows.append(dict(
            confidence=conf, n=len(g), n_directional=len(d),
            hit_rate=(round(float(d["classification"].str.endswith("_HIT").mean()), 3)
                      if len(d) else None),
            mean_actual=round(float(g["actual"].mean()), 3),
        ))
    return pd.DataFrame(rows).sort_values("confidence").reset_index(drop=True)


def worst_calls(df: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """Biggest verdict-vs-outcome misses, unit-safe: a BUY judged against the
    same-bucket BUY median realized FP/unit (low = miss), a FADE against the
    FADE median (high = miss). Deduped by player (worst instance kept)."""
    rows = []
    for bkt, g in df.groupby("bucket"):
        for v, sign in (("BUY", -1.0), ("FADE", +1.0)):
            sub = g[g["verdict"] == v].copy()
            if not len(sub):
                continue
            med = float(sub["actual"].median())
            sub["miss_score"] = sign * (sub["actual"] - med)
            sub = (sub.sort_values("miss_score", ascending=False)
                      .drop_duplicates("player"))
            for _, r in sub.head(k).iterrows():
                if r["miss_score"] <= 0:
                    continue
                rows.append(dict(
                    bucket=bkt, verdict=v, player=r["player"],
                    snapshot=r["snapshot_date"], actual=round(float(r["actual"]), 3),
                    verdict_median=round(med, 3),
                    gap=round(float(r["miss_score"]), 3), unit=r["unit"],
                    n_events=r["n_events"], reason=r["reason_tag"],
                ))
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("gap", ascending=False).head(2 * k).reset_index(drop=True)
    return out


def units_warnings(df: pd.DataFrame) -> list[str]:
    """Flag buckets whose proj/actual scale ratio betrays a units mismatch
    (proj_per logged in a different unit than the settlement actual)."""
    warns = []
    for bkt, g in df.groupby("bucket"):
        pa, aa = float(g["proj_per"].mean()), float(g["actual"].mean())
        if aa and abs(pa / aa) > 2.0:
            warns.append(
                f"bucket {bkt}: mean proj_per {pa:.2f} vs mean realized {aa:.2f} "
                f"{g['unit'].iloc[0]} (ratio {pa / aa:.1f}x) — proj_per is logged in a "
                f"DIFFERENT UNIT than the settlement actual. This bug was FIXED "
                f"2026-07-10 (logger schema v2 logs settlement units; the settler "
                f"converts legacy v1 H records /3.5 and marks v1 RP records "
                f"UNSETTLEABLE_V1_UNITS). If this warning fires on v2-era records, "
                f"the logger has REGRESSED — check triangulate_core proj_settle and "
                f"decisions/logger.py. Residual hit rates for this bucket are not "
                f"unit-honest until re-settled."
            )
    return warns


def power_projection(n_settled: int, ripe_dates: list[date], today: date) -> str:
    if n_settled >= POWER_N:
        return f"n={n_settled} settled — at/above the {POWER_N}-decision power floor."
    need = POWER_N - n_settled
    future = sorted(d for d in ripe_dates)
    if len(future) < need:
        return (f"EARLY READ: n={n_settled} settled (< {POWER_N}). Only {len(future)} "
                f"more records are in the pipeline — keep logging.")
    powered_on = future[need - 1]
    return (f"EARLY READ: n={n_settled} settled (< {POWER_N} power floor). "
            f"{len(future)} pending records; the {need}th ripens {powered_on.isoformat()} "
            f"— treat the scorecard as well-powered from ~{powered_on.isoformat()} "
            f"(assuming event-count gates pass).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--out", default=str(OUT_CSV))
    a = ap.parse_args()
    today = datetime.fromisoformat(a.today).date()

    df = load_settled()
    print("=" * 78)
    print(f"VERDICT SCORECARD — decision quality, all settled decisions to {today}")
    print("  (sibling of /model-health: that grades the MODELS, this grades the CALLS)")
    print("=" * 78)
    if not len(df):
        print("No settled decisions yet — nothing to score. "
              "Settlement starts 21d (H) / 35d (SP/RP) after the first logged snapshot.")
        return 0

    n_players = df["player"].nunique()
    span = f"{df['snapshot_date'].min()} .. {df['snapshot_date'].max()}"
    print(f"\nSettled decisions: {len(df)}  |  unique players: {n_players} "
          f"(repeated daily snapshots per player — effective n is closer to "
          f"{n_players})  |  snapshots {span}")
    ripe = load_pending_ripe_dates()
    print(power_projection(len(df), ripe, today))
    missing = sorted(set(ALL_VERDICTS) - set(df["verdict"]))
    if missing:
        print(f"Verdicts with ZERO settled decisions so far: {', '.join(missing)}")
    per_bucket = df.groupby("bucket").size().to_dict()
    unsettled_buckets = sorted(set(SETTLEMENT_WINDOWS) - set(per_bucket))
    if unsettled_buckets:
        print(f"Buckets with nothing settled yet: {', '.join(unsettled_buckets)} "
              f"(35d windows — first SP/RP settlements ripen "
              f"{(date.fromisoformat(df['snapshot_date'].min()) + timedelta(days=35)).isoformat()})")

    for w in units_warnings(df):
        print(f"\n⚠ UNITS WARNING — {w}")

    ladder = build_ladder(df)
    print("\n--- Verdict ladder (per bucket x verdict; realized FP-per-unit) ---")
    print(ladder.to_string(index=False))

    print("\n--- Monotonicity (expect realized BUY > HOLD > CAUTION > FADE) ---")
    for bkt in sorted(df["bucket"].unique()):
        verdict, _ = monotonicity(ladder, bkt)
        print(f"  {bkt}: {verdict}")

    print("\n--- BUY vs FADE discrimination ---")
    for bkt in sorted(df["bucket"].unique()):
        print(f"  {bkt}: {buy_vs_fade(df, bkt)}")

    cal = confidence_calibration(df)
    if len(cal):
        print("\n--- Confidence calibration (0.25/0.5/0.75/1.0 field) ---")
        print(cal.to_string(index=False))
        if cal["n_directional"].fillna(0).max() < 10:
            print("  [directional n per bin is tiny — calibration is an early read]")

    wc = worst_calls(df)
    if len(wc):
        print("\n--- Worst calls (verdict vs realized outcome, per-player deduped) ---")
        print(wc.to_string(index=False))

    ladder.to_csv(a.out, index=False)
    print(f"\nwrote {a.out} ({len(ladder)} rows)")
    print("\nRule 13: scoreboard only — never moves rh3/rp3/rprs2 or any verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
