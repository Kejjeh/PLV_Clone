"""analyze_break_events — WHICH in-season events actually break a pitcher's line?

v3 established that only EVENT-triggered splits have any positive cells
(3/10 vs 0/60 for searched splits). It never asked WHICH events. This does.

THE QUESTION, ASKED DIRECTLY
For an event at date D, split the season into pre-D and post-D starts. If the
event genuinely breaks the line, then relative to a split at a random date:
  (a) the pre/post change in skill (|dK-BB%|) should be LARGER, and
  (b) the pre-segment should PREDICT the post-segment WORSE (higher MAE, lower r).

No re-anchoring estimator is involved. This measures whether the break exists,
which is upstream of whether it can be exploited.

THE CONTROL THAT MATTERS
Each event is matched to random split dates drawn at the SAME fractional
position in that same pitcher's season, under the same sample gates. Without it
you cannot separate "the trade mattered" from "it happened in August, when the
remaining sample is small and everything looks different."

TAXONOMY (derived, not assumed)
  TRADE / IL_SHORT (15-29d) / IL_MED (30-59d) / IL_LONG (60d+)
  ROLE_PEN (rotation -> bullpen) / ROLE_ROT (bullpen -> rotation)

Both segments must clear MIN_TBF_SIDE = SP_MINS['k_pct'] = 100 TBF, so each
side's K-BB% is a readable number rather than a rumour.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from plv_clone import stabilization as stab  # noqa: E402

PANEL = os.path.join(ROOT, "data/research/xfp_cache/sp_event_panel_2017_2026.csv")
OUT = os.path.join(ROOT, "data/outputs/break_event_analysis.csv")

MIN_TBF_SIDE, _U = stab.minimum("k_pct", "SP")   # 100 TBF, from the module
N_CONTROL = 30
SEED = 20260827


def D(s):
    return dt.date(*map(int, s.split("-")))


def load():
    by = defaultdict(list)
    with open(PANEL) as fh:
        for r in csv.DictReader(fh):
            by[(int(r["pitcher"]), int(r["year"]))].append(r)
    for k in by:
        by[k].sort(key=lambda r: r["game_date"])
    return by


def classify(app):
    """[(date, event_type)] — date is the first appearance AFTER the event."""
    ev = []
    for i in range(1, len(app)):
        gap = (D(app[i]["game_date"]) - D(app[i - 1]["game_date"])).days
        t0, t1 = app[i - 1].get("team_id"), app[i].get("team_id")
        if t0 and t1 and t0 != t1:
            ev.append((app[i]["game_date"], "TRADE"))
        if 15 <= gap < 30:
            ev.append((app[i]["game_date"], "IL_SHORT"))
        elif 30 <= gap < 60:
            ev.append((app[i]["game_date"], "IL_MED"))
        elif gap >= 60:
            ev.append((app[i]["game_date"], "IL_LONG"))
    gs = [int(a["gs"] or 0) for a in app]
    run = 0
    for i, g in enumerate(gs):
        if g == 0:
            run += 1
        else:
            if run >= 2:
                ev.append((app[i]["game_date"], "ROLE_ROT"))
            run = 0
    for i in range(2, len(gs)):
        if gs[i] == 0 and gs[i - 1] == 0 and gs[i - 2] == 1:
            ev.append((app[i - 1]["game_date"], "ROLE_PEN"))
    return ev


def split_at(app, date):
    """Pre/post summaries around `date`. None if either side is unreadable."""
    pre = [a for a in app if a["game_date"] < date]
    post = [a for a in app if a["game_date"] >= date]
    if not pre or not post:
        return None
    def s(rows):
        tbf = sum(float(a["tbf"]) for a in rows)
        k = sum(float(a["k"]) for a in rows)
        bb = sum(float(a["bb"]) for a in rows)
        st = [a for a in rows if int(a["gs"] or 0) == 1]
        return tbf, ((k - bb) / tbf if tbf else None), \
            (sum(float(a["fp"]) for a in st) / len(st) if st else None), len(st)
    t1, kbb1, fp1, n1 = s(pre)
    t2, kbb2, fp2, n2 = s(post)
    if t1 < MIN_TBF_SIDE or t2 < MIN_TBF_SIDE:
        return None
    if None in (kbb1, kbb2, fp1, fp2) or n1 < 3 or n2 < 3:
        return None
    return dict(dkbb=abs(kbb2 - kbb1), dfp=abs(fp2 - fp1),
                pre_fp=fp1, post_fp=fp2)


def main() -> int:
    by = load()
    rng = np.random.default_rng(SEED)
    rows = defaultdict(list)
    for key, app in by.items():
        if len([a for a in app if int(a["gs"] or 0) == 1]) < 12:
            continue
        d0, d1 = D(app[0]["game_date"]), D(app[-1]["game_date"])
        span = max((d1 - d0).days, 1)
        for date, kind in classify(app):
            r = split_at(app, date)
            if r is None:
                continue
            frac = (D(date) - d0).days / span
            ctl = []
            for _ in range(N_CONTROL):
                f = float(np.clip(rng.normal(frac, 0.05), 0.05, 0.95))
                cd = (d0 + dt.timedelta(days=int(f * span))).isoformat()
                cr = split_at(app, cd)
                if cr:
                    ctl.append(cr)
            if not ctl:
                continue
            rows[kind].append(dict(
                key=key, frac=frac, dkbb=r["dkbb"], dfp=r["dfp"],
                pre_fp=r["pre_fp"], post_fp=r["post_fp"],
                c_dkbb=float(np.mean([c["dkbb"] for c in ctl])),
                c_dfp=float(np.mean([c["dfp"] for c in ctl])),
            ))

    out = []
    print(f"\n{'='*116}")
    print("DO THE STATS ACTUALLY BREAK AT THIS EVENT?   (vs matched same-position random splits)")
    print(f"both sides gated at {MIN_TBF_SIDE} TBF (stabilization.SP_MINS['k_pct'])")
    print(f"{'='*116}")
    print(f"{'event':<11}{'n':>6}{'seasons':>8} | {'|dK-BB%|':>9}{'ctrl':>7}{'EXCESS':>8}{'t':>7}"
          f" | {'|dFP/st|':>9}{'ctrl':>7}{'EXCESS':>8}{'t':>7}")
    for kind, v in sorted(rows.items(), key=lambda x: -len(x[1])):
        if len(v) < 15:
            print(f"{kind:<11}{len(v):>6}   (too few)")
            continue
        seasons = len({x["key"] for x in v})
        bys_k, bys_f = defaultdict(list), defaultdict(list)
        for x in v:
            bys_k[x["key"]].append(x["dkbb"] - x["c_dkbb"])
            bys_f[x["key"]].append(x["dfp"] - x["c_dfp"])
        ek = np.array([np.mean(z) for z in bys_k.values()])
        ef = np.array([np.mean(z) for z in bys_f.values()])
        tk = ek.mean() / (ek.std(ddof=1) / np.sqrt(len(ek))) if len(ek) > 1 and ek.std(ddof=1) else np.nan
        tf = ef.mean() / (ef.std(ddof=1) / np.sqrt(len(ef))) if len(ef) > 1 and ef.std(ddof=1) else np.nan
        dk = np.mean([x["dkbb"] for x in v]) * 100
        ck = np.mean([x["c_dkbb"] for x in v]) * 100
        df = np.mean([x["dfp"] for x in v])
        cf = np.mean([x["c_dfp"] for x in v])
        print(f"{kind:<11}{len(v):>6}{seasons:>8} | {dk:>9.2f}{ck:>7.2f}{dk-ck:>+8.2f}{tk:>7.2f}"
              f" | {df:>9.2f}{cf:>7.2f}{df-cf:>+8.2f}{tf:>7.2f}")
        out.append(dict(event=kind, n=len(v), seasons=seasons,
                        dkbb_pct=dk, ctrl_dkbb_pct=ck, excess_dkbb_pct=dk - ck, t_dkbb=float(tk),
                        dfp=df, ctrl_dfp=cf, excess_dfp=df - cf, t_dfp=float(tf)))
    if out:
        with open(OUT, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
