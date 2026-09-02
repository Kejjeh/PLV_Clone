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


def _base_beat_rate(bucket_df: pd.DataFrame) -> float | None:
    """Fraction of ALL settled records in a bucket that beat +threshold.

    THE COMPARISON THAT MAKES A HIT RATE READABLE (issue #53).

    A "hit" is the player beating HIS OWN projection by a threshold, not
    beating the field — so a calibrated model scores well under 50% by
    construction, because the threshold sits outside the median. Quoted alone,
    the number reads as "the process is wrong two times in three"; measured
    2026-08-27, hitter BUY beat 23.1% against an all-verdict base of 23.0%,
    i.e. an edge of +0.1pp, which is the honest statement.

    Every verdict counts here, including HOLD/CAUTION/MIXED: the question is
    what the residual distribution does on this population, independent of
    what we said about anyone.
    """
    if not len(bucket_df):
        return None
    thr = bucket_df["threshold"].iloc[0] if "threshold" in bucket_df else None
    if thr is None or pd.isna(thr):
        return None
    return float((bucket_df["residual"] > float(thr)).mean())


def build_ladder(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # Per-bucket base rate, computed ONCE over every settled record in the
    # bucket so each verdict row can be read against it (issue #53).
    base_by_bucket = {b: _base_beat_rate(g) for b, g in df.groupby("bucket")}
    for (bkt, v), g in df.groupby(["bucket", "verdict"]):
        _hr = _hit_rate(g) if v in ("BUY", "FADE") else None
        _base = base_by_bucket.get(bkt)
        rows.append(dict(
            bucket=bkt, verdict=v, n=len(g),
            n_players=g["player"].nunique(),
            base_beat_rate=(round(_base, 3) if _base is not None else None),
            # The actual claim: hit rate MINUS what the bucket does anyway.
            hit_rate_edge=(round(_hr - _base, 3)
                           if (_hr is not None and _base is not None) else None),
            mean_actual=round(float(g["actual"].mean()), 3),
            median_actual=round(float(g["actual"].median()), 3),
            mean_proj_per=round(float(g["proj_per"].mean()), 3),
            mean_residual=round(float(g["residual"].mean()), 3),
            hit_rate=(round(_hr, 3) if _hr is not None else None),
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

    # ── §7-9: DECISION accounting (C6, 2026-07-29) ───────────────────────────
    # Everything above grades PROJECTIONS: was the number right? These three
    # grade CHOICES: of the options on the table, was the one taken the best?
    # A projection can be well calibrated while every decision made from it is
    # wrong, and vice versa — so this is a genuinely separate scoreboard, not a
    # restatement of the one above.
    _decision_sections(today)

    # ── §10: CLAIM accounting (2026-08-05) ───────────────────────────────────
    # The third and last scoreboard. §1-6 grade the projection, §7-9 grade the
    # choice, §10 grades the CLAIM — what was actually said, with a number and
    # a deadline attached before the outcome was known.
    _prediction_section(today)

    ladder.to_csv(a.out, index=False)
    print(f"\nwrote {a.out} ({len(ladder)} rows)")
    print("\nRule 13: scoreboard only — never moves rh3/rp3/rprs2 or any verdict.")
    return 0


def _load_records_where(keep) -> list:
    """Every decision record satisfying `keep`, mirror-authoritative.

    The settled/ mirror and the dated source tree can both hold the same
    decision_id; sorted() puts 'settled' after the dates, so the later read
    wins and the graded copy is the one returned.
    """
    from plv_clone.decisions.logger import DecisionRecord
    root = Path(DECISIONS_ROOT) if not isinstance(DECISIONS_ROOT, Path) else DECISIONS_ROOT
    out, seen = [], set()
    if not root.exists():
        return out
    for p in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        try:
            rec = DecisionRecord(**payload)
        except TypeError:
            continue
        if not keep(rec):
            continue
        if rec.decision_id in seen:
            out = [r for r in out if r.decision_id != rec.decision_id]
        seen.add(rec.decision_id)
        out.append(rec)
    return out


def _load_paired_records(today: date) -> list:
    """Every v3 record carrying a paired settlement, from both trees.

    Terminal ungradeable blocks (issue #54: never-pairable records marked so
    they stop looking "awaiting window") are excluded — they carry no
    fp_gained, so including them would only flip the "no paired settlements
    yet" guidance while adding nothing to §7-§9.
    """
    return _load_records_where(
        lambda r: bool(getattr(r, "counterfactual_settlement", None))
        and not (getattr(r, "counterfactual_settlement") or {}).get("ungradeable"))


def _load_prediction_records() -> list:
    """Every v4 record carrying a claim — settled OR still open.

    Open claims are loaded deliberately: a book that only showed resolved
    predictions would let an unflattering outstanding claim quietly vanish
    until it happened to settle well.
    """
    return _load_records_where(lambda r: bool(getattr(r, "prediction", None)))


#: below this many resolved claims, a hit rate is noise dressed as a record
_MIN_BOOK_FOR_RATE = 10


def _prediction_section(today: date) -> None:
    """§10 — was the stated CLAIM right?

    The third scoreboard. §1-6 grade projections, §7-9 grade choices, this
    grades claims: a number and a deadline written down before the outcome
    was known. It is the only one of the three that can hold an advisor to
    account for what they actually said out loud.

    Open claims are listed with their deadlines, not just resolved ones. A
    book that reported only settled predictions would let a claim heading for
    a miss stay invisible until it settled, which is the failure this whole
    ledger exists to prevent.
    """
    from plv_clone.decisions.prediction import HIT, MISS, PENDING, score_book

    recs = _load_prediction_records()
    print("\n" + "=" * 78)
    print("CLAIM ACCOUNTING — was the stated CLAIM right? (grades what was said)")
    print("=" * 78)
    if not recs:
        print("  no predictions logged yet.")
        print("  Log one at verdict time with scripts/xfp/log_prediction.py —")
        print("  a claim needs a number and a deadline, or it cannot be wrong.")
        return

    settlements, open_claims = [], []
    for r in recs:
        ps = getattr(r, "prediction_settlement", None)
        if ps:
            settlements.append(dict(ps, _rec=r))
        else:
            settlements.append({"status": PENDING})
            open_claims.append(r)

    s = score_book([{k: v for k, v in x.items() if k != "_rec"}
                    for x in settlements])
    print(f"\n--- §10 The prediction book (n={s['n_total']}) ---")
    print(f"  resolved {s['n_resolved']} | open {s['n_pending']} | "
          f"unsettleable {s['n_unsettleable']}")
    if s["hit_rate"] is None:
        print("  hit rate: n/a — nothing has resolved yet.")
    elif s["n_resolved"] < _MIN_BOOK_FOR_RATE:
        print(f"  hit rate: {s['hit_rate']:.0%} on only {s['n_resolved']} "
              f"resolved — too few to read as skill; reported for completeness.")
    else:
        print(f"  hit rate: {s['hit_rate']:.0%} ({s['n_hit']}/{s['n_resolved']}), "
              f"mean margin {s['mean_margin']:+.1f} FP")

    # split by author: the point is telling whose calls hold up
    by_author: dict[str, list] = {}
    for x in settlements:
        rec = x.get("_rec")
        who = ((getattr(rec, "prediction", None) or {}).get("made_by")
               if rec else None) or "unknown"
        by_author.setdefault(who, []).append(x)
    if len(by_author) > 1 or s["n_resolved"]:
        print(f"\n  {'author':<12}{'resolved':>9}{'hit':>6}{'rate':>8}")
        for who, xs in sorted(by_author.items()):
            res = [x for x in xs if x.get("status") in (HIT, MISS)]
            nh = sum(1 for x in res if x["status"] == HIT)
            rate = f"{nh/len(res):.0%}" if res else "—"
            print(f"  {who:<12}{len(res):>9}{nh:>6}{rate:>8}")

    if open_claims:
        print(f"\n  OPEN CLAIMS ({len(open_claims)}) — these settle themselves, "
              f"whether or not anyone brings them up:")
        for r in sorted(open_claims,
                        key=lambda x: x.prediction.get("horizon_end", "")):
            p = r.prediction
            due = p.get("horizon_end", "?")
            try:
                days = (date.fromisoformat(due) - today).days
                when = f"{due} ({days:+d}d)"
            except ValueError:
                when = due
            print(f"    {when:<22} [{p.get('made_by', '?'):<6}] {p.get('claim')}")

    misses = [x for x in settlements if x.get("status") == MISS and x.get("_rec")]
    if misses:
        print(f"\n  MISSES ({len(misses)}) — stated, then wrong:")
        for x in sorted(misses, key=lambda y: y.get("margin", 0.0)):
            p = x["_rec"].prediction
            print(f"    {x.get('margin', 0.0):>+7.1f} FP short of "
                  f"{x.get('threshold')}  {p.get('claim')}")


def _decision_sections(today: date) -> None:
    from plv_clone.decisions import counterfactual as CF

    recs = _load_paired_records(today)
    print("\n" + "=" * 78)
    print("DECISION ACCOUNTING — was the CHOICE right? (grades moves, not projections)")
    print("=" * 78)
    if not recs:
        print("  no paired settlements yet.")
        print("  This fills in as executed moves ripen (H 21d / SP+RP 35d) and")
        print("  requires a dpwin surface to have existed BEFORE the move — run")
        print("  /matchup-leverage or the weekly optimizer before executing so the")
        print("  alternative you passed on is on the record.")
        return

    summ = CF.summarize(recs)

    print(f"\n--- §7 Decision regret by bucket (n={summ['n_settled']}) ---")
    print(f"{'bucket':<8}{'n':>4}{'RIGHT':>7}{'WRONG':>7}{'WASH':>6}"
          f"{'hit%':>7}{'mean FP':>9}{'median':>9}{'total FP':>10}")
    for b, e in sorted(summ["by_bucket"].items()):
        hr = f"{e['hit_rate']*100:.0f}%" if e["hit_rate"] is not None else "—"
        print(f"{b:<8}{e['n']:>4}{e[CF.RIGHT_CALL]:>7}{e[CF.WRONG_CALL]:>7}"
              f"{e[CF.WASH]:>6}{hr:>7}{e['fp_gained_mean']:>9.1f}"
              f"{e['fp_gained_median']:>9.1f}{e['fp_gained_total']:>10.1f}")
    if summ["n_low_sample"]:
        print(f"  [{summ['n_low_sample']} of {summ['n_settled']} are low-sample — "
              f"flagged, not excluded: sometimes the thin sample IS the outcome "
              f"(the alternative got hurt or benched)]")

    print(f"\n--- §8 Cumulative FP vs the road not taken ---")
    tot = summ["total_fp_gained"]
    verdict = ("the process is AHEAD" if tot > 0 else
               "the process is BEHIND" if tot < 0 else "dead even")
    print(f"  {tot:+.1f} FP across {summ['n_settled']} settled decisions — {verdict}")
    print(f"  This is the single number that says whether the whole apparatus is")
    print(f"  earning anything: sum of realized(chosen) - realized(rejected).")
    if summ["n_settled"] < 20:
        print(f"  [EARLY READ at n={summ['n_settled']} — a handful of decisions is "
              f"mostly variance; treat the sign as provisional]")

    res = CF.dpwin_resolution(recs)
    print(f"\n--- §9 Does Delta-P(win) have RESOLUTION? ---")
    if res["status"] == "EARLY_READ":
        print(f"  {res['note']}")
        print(f"  (the honest test of whether the surface predicts outcomes at all,")
        print(f"   rather than merely being internally consistent)")
    else:
        rates = res["tercile_win_rates"]
        print(f"  P(fp_gained>0) by ascending dpwin_gap tercile: {rates}  "
              f"(n={res['n']})")
        if res["monotone"]:
            print(f"  MONOTONE — a bigger predicted edge really did produce a better")
            print(f"  realized outcome. The dpwin surface has resolution.")
        else:
            print(f"  NOT monotone — the surface's confidence is not tracking")
            print(f"  realized outcomes. Treat dpwin magnitudes as ordinal at best")
            print(f"  until this turns over.")


if __name__ == "__main__":
    sys.exit(main())
