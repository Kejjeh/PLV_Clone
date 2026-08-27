"""sp_regime_scan — find SPs whose season-to-date line averages two different pitchers.

CONTEXT-ONLY (CLAUDE.md #13). This NEVER moves rp3. It flags rows where the
season-to-date aggregate — which rp3 leans on via `fp_per_start_to` — spans a
structural break, so the projection describes nobody.

Two break types, deliberately kept apart because they carry different evidential
weight:

  ABSENCE  an inter-start gap >= GAP_DAYS. This is an OBJECTIVE event (IL stint,
           demotion, injury). No search is performed, so there is no multiple-
           testing penalty. Highest confidence.

  SEARCHED a changepoint found by scanning split points for the largest mean
           separation. This IS a search over ~N candidate splits per pitcher and
           WILL manufacture splits from noise. Lower confidence by construction;
           only reported when corroborated by prior year.

CORROBORATION is what separates signal from a hot streak: if the post-break K%
lands within K_TOL of the pitcher's PRIOR-YEAR K%, the post-break segment is a
return to an established level rather than a new run of luck. Prior-year level
is not a recency signal — it is already an rp3 input (`prior_fp_per_start`).

Canonical case (2026-08-26): Jacob Lopez, 40-day absence, pre 2.75 FP/start
(K% 15.7) vs post 14.76 (K% 29.6) against a 2025 K% of 27.7. rp3 projected 9.59
— the mean of two pitchers who never coexisted.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANEL = os.path.join(ROOT, "data/research/xfp_cache/sp_gamelogs_2017_2026.csv")
RP3 = os.path.join(ROOT, "data/outputs/xfp_rp3_projections.csv")
CONSOLE = os.path.join(ROOT, "data/outputs/console_data.json")
OUT = os.path.join(ROOT, "data/outputs/sp_regime_scan.csv")

YEAR, PRIOR = 2026, 2025
GAP_DAYS = 25          # absence long enough to be an IL stint / demotion
MIN_SIDE_ABSENCE = 4   # starts required each side of an absence break
MIN_SIDE_SEARCH = 6    # starts required each side of a searched break
MIN_STARTS = 8
K_TOL = 0.05           # post-break K% within 5pp of prior year = corroborated
MIN_CONTAM = 2.0       # |post - rp3| FP/start worth reporting

FIELDS = ["pitcher", "name", "owner", "break_type", "break_date", "gap_days",
          "n_pre", "n_post", "fp_pre", "fp_post", "k_pre", "k_post",
          "fp_prior", "k_prior", "corroborated", "rp3", "fp_season",
          "contamination", "direction", "is_on_il_at_split"]


def _d(s):
    y, m, dd = s.split("-")
    return (int(y), int(m), int(dd))


def _days(a, b):
    import datetime
    return (datetime.date(*_d(b)) - datetime.date(*_d(a))).days


def load_panel():
    by = defaultdict(list)
    with open(PANEL) as fh:
        for r in csv.DictReader(fh):
            by[(int(r["pitcher"]), int(r["year"]))].append(r)
    for k in by:
        by[k].sort(key=lambda r: r["game_date"])
    return by


def seg(rows):
    n = len(rows)
    fp = sum(float(r["fp"]) for r in rows) / n
    tbf = sum(float(r["tbf"]) for r in rows)
    k = sum(float(r["k"]) for r in rows)
    return n, fp, (k / tbf if tbf else float("nan"))


def find_absence(rows):
    best = None
    for i in range(1, len(rows)):
        g = _days(rows[i - 1]["game_date"], rows[i]["game_date"])
        if g >= GAP_DAYS and i >= MIN_SIDE_ABSENCE and len(rows) - i >= MIN_SIDE_ABSENCE:
            if best is None or g > best[1]:
                best = (i, g)
    return best


def find_searched(rows):
    """Largest absolute mean separation; a SEARCH, flagged as such."""
    best, bestsep = None, 0.0
    for i in range(MIN_SIDE_SEARCH, len(rows) - MIN_SIDE_SEARCH + 1):
        a = sum(float(r["fp"]) for r in rows[:i]) / i
        b = sum(float(r["fp"]) for r in rows[i:]) / (len(rows) - i)
        if abs(a - b) > bestsep:
            best, bestsep = i, abs(a - b)
    return best


def main() -> int:
    by = load_panel()
    rp3 = {}
    with open(RP3) as fh:
        for r in csv.DictReader(fh):
            nm = r["player_name"]
            rp3[int(r["pitcher"])] = r
    own = {}
    C = json.load(open(CONSOLE))
    for b in C["buckets"]:
        for p in b["players"]:
            if p.get("mlbam"):
                own[int(p["mlbam"])] = (p["name"], p["owner"])

    out = []
    for (pid, yr), rows in by.items():
        if yr != YEAR or len(rows) < MIN_STARTS:
            continue
        hit = find_absence(rows)
        if hit:
            idx, gap, btype = hit[0], hit[1], "ABSENCE"
        else:
            idx = find_searched(rows)
            if idx is None:
                continue
            gap, btype = 0, "SEARCHED"
        n_pre, fp_pre, k_pre = seg(rows[:idx])
        n_post, fp_post, k_post = seg(rows[idx:])
        pr = by.get((pid, PRIOR))
        if pr and len(pr) >= 5:
            _, fp_prior, k_prior = seg(pr)
        else:
            fp_prior = k_prior = float("nan")
        corro = (k_prior == k_prior and abs(k_post - k_prior) <= K_TOL)
        r3 = rp3.get(pid)
        proj = float(r3["xfp_rp3_per_start"]) if r3 else float("nan")
        contam = fp_post - proj if proj == proj else float("nan")
        if not (abs(contam) >= MIN_CONTAM):
            continue
        # a SEARCHED break with no prior-year corroboration is noise; drop it
        if btype == "SEARCHED" and not corro:
            continue
        nm, ow = own.get(pid, (r3["player_name"] if r3 else str(pid), ""))
        _, fp_season, _ = seg(rows)
        out.append({
            "pitcher": pid, "name": nm, "owner": ow, "break_type": btype,
            "break_date": rows[idx]["game_date"], "gap_days": gap,
            "n_pre": n_pre, "n_post": n_post,
            "fp_pre": round(fp_pre, 2), "fp_post": round(fp_post, 2),
            "k_pre": round(k_pre, 3), "k_post": round(k_post, 3),
            "fp_prior": round(fp_prior, 2) if fp_prior == fp_prior else "",
            "k_prior": round(k_prior, 3) if k_prior == k_prior else "",
            "corroborated": corro, "rp3": round(proj, 2),
            "fp_season": round(fp_season, 2),
            "contamination": round(contam, 2),
            "direction": "rp3 UNDERSTATES" if contam > 0 else "rp3 OVERSTATES",
            "is_on_il_at_split": (r3 or {}).get("is_on_il_at_split", ""),
        })

    out.sort(key=lambda r: -abs(r["contamination"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} flagged SPs -> {OUT}\n")

    for scope in ("MINE", "FA"):
        sub = [r for r in out if r["owner"] == scope]
        print(f"{'='*118}\n{scope} — {len(sub)} flagged\n{'='*118}")
        print(f"{'name':<20}{'brk':<9}{'date':<11}{'gap':>4}{'pre':>13}{'post':>13}"
              f"{'prior':>13}{'corr':>6}{'rp3':>7}{'contam':>8}  IL?")
        for r in sub:
            pre = f"{r['fp_pre']:.1f}/{r['k_pre']*100:.0f}%"
            post = f"{r['fp_post']:.1f}/{r['k_post']*100:.0f}%"
            pri = (f"{r['fp_prior']:.1f}/{r['k_prior']*100:.0f}%"
                   if r["fp_prior"] != "" else "—")
            print(f"{r['name']:<20}{r['break_type']:<9}{r['break_date']:<11}"
                  f"{r['gap_days']:>4}{pre:>13}{post:>13}{pri:>13}"
                  f"{'YES' if r['corroborated'] else '-':>6}{r['rp3']:>7.1f}"
                  f"{r['contamination']:>+8.1f}  {r['is_on_il_at_split']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
