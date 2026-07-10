"""run_streamer_board.py — engine for the /streamer-precision-board skill.

Daily ranked SP streamer decision board over a date window. For EVERY confirmed
probable SP that is MINE or FA, emits one row reconciling the four lenses that
matter for a start/stream decision:

  MEAN   opponent-adjusted rp3 per_start (xfp_rp3_per_start_sched) + venue park adj
  ACTUAL season & L5 FP/start + empirical bust% (realized variance the model can't show)
  FADJ   floor_adjusted_xfp — the VALIDATED H2H risk-docked score (ranks the board)
  PROC   process percentile (SwStr) so a rich MEAN with weak process is flagged
  STACK  boom_stack 0-4 (skill_spike/recform_hot/opp_soft/park_friendly) + tier-aware
         expected boom% — the right-tail lens absorbed from stream_the_stack
         (P1 merge 2026-07-10). DISPLAY TAG only; FADJ still ranks the board.

The old /stream-the-stack view is now a filter over this board:
  python scripts/xfp/run_streamer_board.py --filter "boom>=2"

Rebuilt ad-hoc ~4x in one session (2026-07-03) — each rebuild risked re-introducing
the ATH park bug. This is the permanent home. **It OWNS nothing** — every shared fact
comes from its owner module (see .claude/skills/SKILL_REGISTRY.md):
  - park -> FP        : lib.extra_lenses.park_fp_adj      (VENUE_ERAS-aware)
  - floor-adjusted    : lib.extra_lenses.floor_adjusted_xfp / floor_lens / floor_flag
  - boom/bust cutoffs : lib.boom_bust.SP_BOOM / SP_BUST
  - name -> mlbam     : plv_clone.utils.name_match.resolve_pitcher_id
  - roster truth      : app.espn_connector.get_all_teams
  - decline tier      : sp_decline_model.build

Usage:
  python scripts/xfp/run_streamer_board.py                       # today .. today+2
  python scripts/xfp/run_streamer_board.py --start 2026-07-04 --end 2026-07-05
  python scripts/xfp/run_streamer_board.py --csv out.csv
  python scripts/xfp/run_streamer_board.py --filter "boom>=2"    # boom-shot shortlist
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
for p in (_ROOT, _ROOT / "src", _ROOT / "scripts" / "xfp"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.espn_connector import get_all_teams
from lib.boom_bust import SP_BOOM, SP_BUST
from lib.extra_lenses import floor_adjusted_xfp, floor_flag, floor_lens, park_fp_adj
from plv_clone.utils.name_match import resolve_pitcher_id

MY = "New York Ligers"
RP3_CSV = _ROOT / "data" / "outputs" / "xfp_rp3_projections.csv"
BOX = _ROOT / "data" / "research" / "xfp_cache" / "boxscore_pitchers.parquet"


# _nrm routed to the name_match owner (item 10, 2026-07-04). Self-consistent
# ownership join (the `rost` dict is built + looked up with this helper). join_key
# is order-independent — strictly correct (zero false-merge on the real universe).
from plv_clone.utils.name_match import join_key as _nrm  # noqa: E402


def build(start: str, end: str) -> pd.DataFrame:
    # Probables come from the OWNER (audit 2026-07-04) — never re-implement.
    from plv_clone.mlb_stats import get_probables
    slate = [{"date": p["date"], "nm": p["pitcher_name"], "id": p["pitcher_id"],
              "opp": p["opp_abbr"], "park": p["park_abbr"]}
             for p in get_probables(start, end)]
    teams = get_all_teams()
    rost = {_nrm(n): t for n, t in zip(teams["player_name"], teams["team_name"])}
    rp3 = pd.read_csv(RP3_CSV)
    RP = {int(r["pitcher"]): r for _, r in rp3.iterrows() if pd.notna(r.get("pitcher"))}
    box = pd.read_parquet(BOX)
    box = box[box["gs"] == 1].copy()
    box["game_date"] = pd.to_datetime(box["game_date"])
    try:
        from sp_decline_model import build as _bd
        dec, _ = _bd()
        DEC = {int(r["mlb_id"]): r for _, r in dec.iterrows()}
    except Exception:
        DEC = {}
    # boom_stack owner (P1 merge 2026-07-10 — absorbed from stream_the_stack).
    # Live compute per start; fail-soft so the board still ranks without it.
    try:
        from lib.boom_stack import compute_boom_stack as _boom
    except Exception:
        _boom = None

    rows = []
    for p in slate:
        own = rost.get(_nrm(p["nm"]))
        if own is not None and own != MY:
            continue  # other team's roster — not streamable
        r = RP.get(p["id"])
        if r is None or pd.isna(r.get("xfp_rp3_per_start")):
            continue
        sched = float(r["xfp_rp3_per_start_sched"]) if pd.notna(r.get("xfp_rp3_per_start_sched")) \
            else float(r["xfp_rp3_per_start"])
        padj = park_fp_adj(p["park"])            # OWNER: venue-aware park -> FP
        mean = round(sched + padj, 1)
        marcel = "marcel" in str(r.get("data_quality_tag"))

        g = box[box["mlbam_id"] == p["id"]].sort_values("game_date")
        f = g["fp_sp"].tolist()
        n = len(f)
        seas = round(float(np.mean(f)), 1) if f else None
        l5 = round(float(np.mean(f[-5:])), 1) if f else None
        ebust = round(100 * float(np.mean([x < SP_BUST for x in f]))) if f else None
        delta = round(mean - seas, 1) if seas is not None else None

        fl = floor_lens(p["nm"]) or {}
        bustp, ftier = fl.get("bust_prob"), fl.get("tier")
        fadj, pen = floor_adjusted_xfp(mean, bustp)   # OWNER: validated H2H score
        fflag = floor_flag(pen, ftier)

        drow = DEC.get(p["id"])
        sw = round(float(drow["swstr_pctl"])) if drow is not None and pd.notna(drow.get("swstr_pctl")) else None
        tier = str(drow["tier"]) if drow is not None else ""

        # boom_stack (OWNER: lib.boom_stack, tier-aware via rp3 rank). Fail-soft.
        stack = boom_pct = boom_tier = None
        boom_anti = False
        if _boom is not None:
            try:
                rfg = float(r["recency_form_gap"]) if pd.notna(r.get("recency_form_gap")) else None
                rk = int(r["rank"]) if pd.notna(r.get("rank")) else None
                bs = _boom(pitcher_id=p["id"], recency_form_gap=rfg,
                           next_opp_team=p["opp"], rp3_rank=rk)
                stack = int(bs["boom_stack"])
                boom_pct = round(100 * float(bs["boom_rate_expected"]), 1) \
                    if bs.get("boom_rate_expected") is not None else None
                boom_tier = bs.get("tier")
                boom_anti = bool(bs.get("skill_spike_anti_predictive"))
            except Exception:
                pass

        verdict = []
        if marcel:
            verdict.append("PRIOR-not-read")
        elif delta is not None and n >= 8:
            verdict.append("RICH" if delta >= 1.5 else ("LIGHT" if delta <= -1.5 else "FAIR"))
        elif n < 8:
            verdict.append(f"n={n}")
        if fflag:
            verdict.append(fflag)
        if tier and tier not in ("STABLE", ""):
            verdict.append(tier)
        if ebust is not None and ebust >= 30:
            verdict.append(f"bust{ebust}%")
        if stack is not None and stack >= 2:
            verdict.append(f"BOOM{stack}/4~{boom_pct}%")
        if boom_anti:
            verdict.append("⚠spike-anti")

        rows.append(dict(
            date=p["date"], own=("MINE" if own == MY else "FA"), pitcher=p["nm"], opp=p["opp"], park=p["park"],
            mean=mean, park_adj=padj, season=seas, l5=l5, n=n, delta=delta,
            bust_pct=ebust, floor_bustP=bustp, floor_tier=ftier, fadj=fadj,
            swstr_pctl=sw, marcel=marcel, boom_stack=stack, boom_pct=boom_pct,
            boom_tier=boom_tier, boom_anti=boom_anti, verdict=" ".join(verdict),
        ))
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["date", "fadj"], ascending=[True, False]).reset_index(drop=True)
    return df


def _render(df: pd.DataFrame) -> None:
    if not len(df):
        print("No MINE/FA probable SPs in window.")
        return
    for d, g in df.groupby("date"):
        print(f"\n===== {d} — MINE + FA SP streamers, ranked by FADJ (floor-adjusted) =====")
        print(f"{'own':<5}{'Pitcher':<19}{'@':<9}{'pk±':>6}{'MEAN':>6}{'seas(n)':>10}{'FADJ':>7}{'Sw%':>5}{'stk':>5}  verdict")
        for _, r in g.iterrows():
            sn = f"{r['season']}({r['n']})" if pd.notna(r["season"]) else "—"
            sw = f"{int(r['swstr_pctl'])}" if pd.notna(r["swstr_pctl"]) else "—"
            stk = f"{int(r['boom_stack'])}/4" if pd.notna(r.get("boom_stack")) else "—"
            fadj = float(r["fadj"]) if pd.notna(r["fadj"]) else float(r["mean"])
            print(f"{r['own']:<5}{str(r['pitcher'])[:19]:<19}{(r['opp']+'@'+r['park'])[:9]:<9}"
                  f"{r['park_adj']:>+6.1f}{r['mean']:>6.1f}{sn:>10}{fadj:>7.1f}{sw:>5}{stk:>5}  {r['verdict']}")


def _apply_filter(df: pd.DataFrame, expr: str) -> pd.DataFrame:
    """Apply a `--filter` expression. Supported: 'boom>=N' (the old stream-the-stack
    view — boom_stack tier shortlist). Unknown expressions raise."""
    import re
    m = re.fullmatch(r"\s*boom\s*>=\s*(\d+)\s*", expr)
    if not m:
        raise SystemExit(f"--filter: unsupported expression {expr!r} (expected 'boom>=N')")
    n = int(m.group(1))
    if not len(df) or "boom_stack" not in df.columns:
        return df.iloc[0:0]
    out = df[df["boom_stack"].notna() & (df["boom_stack"] >= n)].reset_index(drop=True)
    print(f"--filter boom>={n}: {len(df)} -> {len(out)} rows "
          f"(boom_stack is a DISPLAY TAG; FADJ still ranks within the shortlist)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=date.today().isoformat())
    ap.add_argument("--end", default=(date.today() + timedelta(days=2)).isoformat())
    ap.add_argument("--csv", default=None)
    ap.add_argument("--filter", default=None, dest="filter_expr", metavar="EXPR",
                    help="e.g. \"boom>=2\" — boom_stack shortlist (old /stream-the-stack view)")
    a = ap.parse_args()
    df = build(a.start, a.end)
    if a.filter_expr:
        df = _apply_filter(df, a.filter_expr)
    _render(df)
    if a.csv:
        df.to_csv(a.csv, index=False)
        print(f"\nwrote {a.csv} ({len(df)} rows)")


if __name__ == "__main__":
    main()
