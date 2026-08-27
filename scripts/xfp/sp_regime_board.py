"""sp_regime_board — merged MINE-vs-FA starting-pitcher leaderboard, regime-aware.

CONTEXT-ONLY (CLAUDE.md #13). `adj` NEVER writes back into rp3.

Baseline is `xfp_rp3_per_start` (the validated SP RoS model) everywhere, so the
delta column is model-relative and not mixed with the console's Stuff+·vol
display rate — that rate is carried as a separate context column.

`adj` = rp3, EXCEPT where sp_regime_scan found a CORROBORATED **ABSENCE** break
(an objective >=25-day gap), in which case the post-break mean is shrunk toward
the pitcher's prior-year level with a W_PRIOR pseudo-start count.

SEARCHED breaks DO NOT MOVE THE NUMBER (added 2026-08-26 after backtest).
`backtest_sp_regime.py` showed the SEARCHED adjustment is actively HARMFUL and
consistently so — holdout MAE 3.08 -> 3.41 (+0.33 WORSE), r 0.499 -> 0.400,
and it beat the plain season-to-date level in only 38-44% of cases across every
slice (train/holdout x pooled/one-row). Root cause: `find_searched` has no
magnitude or significance gate, so it returns the max-separation split
unconditionally and "finds a break" in 80% of pitcher-seasons. It is not
detecting structure, it is splitting each season at its noisiest point.

ABSENCE, which has an objective trigger and fires on ~20% of seasons, backtests
POSITIVELY: holdout MAE 3.39 -> 3.17 (-0.22), r 0.453 -> 0.469. Independent-
sample n is still thin (23 train / 9 holdout pitcher-seasons), so this remains a
diagnostic, not a validated ranker.

SEARCHED rows are still surfaced as a flag for human review — they just never
move `adj`.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN = os.path.join(ROOT, "data/outputs/sp_regime_scan.csv")
RP3 = os.path.join(ROOT, "data/outputs/xfp_rp3_projections.csv")
CONSOLE = os.path.join(ROOT, "data/outputs/console_data.json")
PL = os.path.join(ROOT, "data/research/pl_cache/pl_sps_top100_2026-08-24.json")
OUT = os.path.join(ROOT, "data/outputs/sp_regime_board.csv")

W_PRIOR = 5.0
REPLACEMENT = 12.376   # replacement_xfp_per_start from the rp3 file


def N(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.replace(".", "").replace(",", "").lower().split())


def main() -> int:
    scan = {int(r["pitcher"]): r for r in csv.DictReader(open(SCAN))}
    rp3 = {}
    for r in csv.DictReader(open(RP3)):
        rp3[int(r["pitcher"])] = r
    plr = {N(k): v for k, v in json.load(open(PL))["ranks"].items()}

    rows = []
    C = json.load(open(CONSOLE))
    for b in C["buckets"]:
        if b["key"] != "SP":
            continue
        for p in b["players"]:
            pid = p.get("mlbam")
            if not pid or p["owner"] not in ("MINE", "FA"):
                continue
            pid = int(pid)
            r3 = rp3.get(pid)
            if not r3:
                continue
            base = float(r3["xfp_rp3_per_start"])
            # v2 (2026-08-26): `adj` ALWAYS equals rp3. Breaks are ANNOTATION ONLY.
            # A properly tested break (K% sup-z, permutation null, BH-FDR) occurs
            # in 0.22% of pitcher-seasons, and an event-triggered + z-gated
            # detector fires on 1/10,274 train and 2/3,406 holdout decision points
            # — because detection needs 100 TBF post-break, which arrives too late
            # in the season to act on. No version of this is usable as a number.
            s = scan.get(pid)
            adj = base
            if s and s["corroborated"] == "True":
                note = f"[{s['break_type'][:3]} {s['break_date'][5:]} annot]"
            else:
                note = ""
            rows.append(dict(
                pid=pid, name=p["name"], own=p["owner"], team=p["team"],
                rp3=base, adj=adj, delta=adj - base, note=note,
                stuff=p.get("rate"), pl=plr.get(N(p["name"])),
                dq=r3["data_quality_tag"], inj=p.get("inj") or "",
            ))

    rows.sort(key=lambda r: -r["adj"])
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_rp3 = {r["pid"]: i + 1 for i, r in enumerate(sorted(rows, key=lambda x: -x["rp3"]))}
    print(f"\n{'='*104}")
    print("REGIME-ADJUSTED SP LEADERBOARD — my staff vs free agents")
    print(f"baseline = rp3 per_start | adj = regime re-anchor where corroborated "
          f"| replacement = {REPLACEMENT}")
    print(f"{'='*104}")
    print(f"{'#':<4}{'':<2}{'pitcher':<20}{'tm':<5}{'rp3':>6}{'ADJ':>7}{'Δ':>7}"
          f"{'mv':>5}  {'break':<16}{'PL':>4}  {'flags'}")
    print("-" * 104)
    for i, r in enumerate(rows, 1):
        mv = by_rp3[r["pid"]] - i
        mvs = f"▲{mv}" if mv > 0 else (f"▼{-mv}" if mv < 0 else "—")
        tag = "★" if r["own"] == "MINE" else " "
        flags = []
        if r["inj"]:
            flags.append(r["inj"].replace("_DAY_DL", "d-IL"))
        if r["dq"] != "data_driven_full":
            flags.append(r["dq"])
        if r["adj"] < REPLACEMENT:
            flags.append("sub-repl")
        pl = f"#{r['pl']}" if r["pl"] else "—"
        print(f"{i:<4}{tag:<2}{r['name']:<20}{r['team']:<5}{r['rp3']:>6.1f}{r['adj']:>7.1f}"
              f"{r['delta']:>+7.1f}{mvs:>5}  {r['note']:<16}{pl:>4}  {' '.join(flags)}")
    print("-" * 104)
    print("★ = my roster.  mv = rank move vs the pure-rp3 ordering.")
    mine = [r for r in rows if r["own"] == "MINE"]
    fa = [r for r in rows if r["own"] == "FA"]
    print(f"\n{len(mine)} mine, {len(fa)} FA. "
          f"Best FA above my worst starter: "
          f"{sum(1 for f in fa if f['adj'] > min(m['adj'] for m in mine))}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
