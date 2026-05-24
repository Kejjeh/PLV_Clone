"""Career-form-rank sweep: roster + FA hitters.

Writes data/research/career_form_rank_2026-05-24.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure `app/` is importable: we expect to be invoked with cwd=main repo,
# but in case sys.path doesn't include cwd (PYTHONDONTWRITEBYTECODE quirks),
# explicitly add the main repo root.
_MAIN_REPO_ROOT = Path("c:/Users/Joshua/plv_clone")
if str(_MAIN_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_MAIN_REPO_ROOT))
os.chdir(_MAIN_REPO_ROOT)

import duckdb
import pandas as pd

from plv_clone.league_state import LeagueState
from plv_clone.utils.name_match import resolve_batter_id, KNOWN_COLLISIONS, _normalize

REPO = Path(__file__).resolve().parents[1]
# When run from worktree, prefer the main repo data dir
MAIN_REPO = Path("c:/Users/Joshua/plv_clone")
CACHE_DIR = MAIN_REPO / "data/research/xfp_cache"
OUT_PATH = MAIN_REPO / "data/research/career_form_rank_2026-05-24.md"

MULTIYR_PATH = CACHE_DIR / "hitters_multiyr_2015_2026.csv"
RH3_PATH = MAIN_REPO / "data/outputs/xfp_rh3_projections.csv"

HITTER_POS = {"C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH", "UT"}

MIN_CAREER_PA = 300
MIN_CURRENT_L150_PA = 100
FA_MIN_CAREER_PA = 500


def is_hitter(pos: str) -> bool:
    if not pos:
        return False
    # ESPN can return slash-separated multi-eligibility, e.g. "OF/1B"
    parts = pos.replace(",", "/").split("/")
    return any(p.strip().upper() in HITTER_POS for p in parts)


def gather_universe():
    ls = LeagueState()
    roster = ls.my_roster()
    fa = ls.available_fa()

    roster_h = roster[roster["position"].apply(is_hitter)].copy()
    fa_h = fa[fa["position"].apply(is_hitter)].copy()

    roster_h["source"] = "roster"
    fa_h["source"] = "fa"

    # Dedupe: prefer roster entry
    fa_h = fa_h[~fa_h["player_name"].isin(roster_h["player_name"])]

    uni = pd.concat([roster_h, fa_h], ignore_index=True)
    return uni, roster_h, fa_h


def resolve_ids(uni: pd.DataFrame, multiyr: pd.DataFrame) -> pd.DataFrame:
    # Build a normalized-name → list of (year, team, batter) lookup as a
    # fallback for ESPN names with stripped accents / suffixes that don't
    # match the multiyr cache exactly.
    my_norm = multiyr.copy()
    my_norm["_norm"] = my_norm["player_name"].apply(_normalize)
    norm_groups = {k: v for k, v in my_norm.groupby("_norm")}

    def _fallback(name, team, pos):
        n = _normalize(name)
        sub = norm_groups.get(n)
        if sub is None or sub.empty:
            return None
        if team and "team" in sub.columns:
            t_sub = sub[sub["team"].str.upper() == team.upper()]
            if not t_sub.empty:
                sub = t_sub
        if "year" in sub.columns:
            sub = sub.sort_values("year", ascending=False)
        return int(sub.iloc[0]["batter"])

    rows = []
    for _, r in uni.iterrows():
        name = r["player_name"]
        team = r.get("pro_team", None) or None
        pos = r.get("position", None) or None
        # try resolver with hints
        bid = resolve_batter_id(name, team=team, position=pos, multiyr=multiyr)
        if bid is None and name not in KNOWN_COLLISIONS:
            # try without team hint via official resolver (exact-match fallback)
            bid = resolve_batter_id(name, multiyr=multiyr)
        if bid is None and name not in KNOWN_COLLISIONS:
            # normalized-name fallback (accents, suffixes, Last,First)
            bid = _fallback(name, team, pos)
        rows.append({**r.to_dict(), "batter_id": bid})
    return pd.DataFrame(rows)


def compute_career_stats(con, batter_ids: list[int]) -> pd.DataFrame:
    if not batter_ids:
        return pd.DataFrame()
    ids_csv = ",".join(str(int(b)) for b in batter_ids)
    parts = []
    for y in range(2015, 2027):
        p = CACHE_DIR / f"statcast_{y}.parquet"
        if not p.exists():
            continue
        parts.append(
            f"SELECT batter, game_date, estimated_woba_using_speedangle AS xwoba "
            f"FROM read_parquet('{p.as_posix()}') "
            f"WHERE batter IN ({ids_csv}) AND events IS NOT NULL AND events != '' "
            f"AND estimated_woba_using_speedangle IS NOT NULL"
        )
    union = " UNION ALL ".join(parts)

    sql = f"""
    WITH all_events AS ({union}),
    ranked AS (
      SELECT batter, game_date, xwoba,
             ROW_NUMBER() OVER (PARTITION BY batter ORDER BY game_date) AS rn,
             COUNT(*) OVER (PARTITION BY batter) AS total_pa
      FROM all_events
    ),
    rolling AS (
      SELECT batter, rn, total_pa,
             AVG(xwoba) OVER (PARTITION BY batter ORDER BY rn
                              ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS roll150
      FROM ranked
    ),
    summary AS (
      SELECT batter,
             ANY_VALUE(total_pa) AS total_pa,
             AVG(roll150)    FILTER (WHERE rn >= 150) AS career_mean,
             MEDIAN(roll150) FILTER (WHERE rn >= 150) AS career_median,
             MIN(roll150)    FILTER (WHERE rn >= 150) AS career_min,
             MAX(roll150)    FILTER (WHERE rn >= 150) AS career_max,
             MAX(CASE WHEN rn = total_pa THEN roll150 END) AS current_l150
      FROM rolling
      GROUP BY batter
    ),
    pct AS (
      SELECT r.batter,
             SUM(CASE WHEN r.roll150 < s.current_l150 THEN 1 ELSE 0 END) * 1.0
               / NULLIF(SUM(CASE WHEN r.rn >= 150 THEN 1 ELSE 0 END), 0) AS percentile
      FROM rolling r JOIN summary s USING (batter)
      WHERE r.rn >= 150
      GROUP BY r.batter
    )
    SELECT s.batter, s.total_pa, s.career_mean, s.career_median,
           s.career_min, s.career_max, s.current_l150, p.percentile
    FROM summary s LEFT JOIN pct p USING (batter)
    """
    return con.execute(sql).df()


def label(p):
    if pd.isna(p):
        return "n/a"
    if p >= 0.95:
        return "Career peak"
    if p >= 0.80:
        return "Peak form"
    if p >= 0.60:
        return "Above-median"
    if p >= 0.40:
        return "Typical"
    if p >= 0.20:
        return "Below-median"
    return "Slumping"


def fmt_pct(p):
    return f"{p*100:.0f}" if pd.notna(p) else "—"


def fmt_n(x, d=3):
    return f"{x:.{d}f}" if pd.notna(x) else "—"


def render_table(df, cols):
    headers = "| " + " | ".join(c[1] for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [headers, sep]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c[0]]) for c in cols) + " |")
    return "\n".join(lines)


def main():
    print("Loading league state...", file=sys.stderr)
    uni, roster_h, fa_h = gather_universe()
    print(f"  roster hitters: {len(roster_h)}, FA hitters: {len(fa_h)}", file=sys.stderr)

    multiyr = pd.read_csv(MULTIYR_PATH)
    print("Resolving IDs...", file=sys.stderr)
    resolved = resolve_ids(uni, multiyr)

    unresolved = resolved[resolved["batter_id"].isna()].copy()
    resolved_ok = resolved[resolved["batter_id"].notna()].copy()
    resolved_ok["batter_id"] = resolved_ok["batter_id"].astype(int)

    con = duckdb.connect()
    print(f"Computing career stats for {len(resolved_ok)} players...", file=sys.stderr)
    stats = compute_career_stats(con, resolved_ok["batter_id"].unique().tolist())

    df = resolved_ok.merge(stats, left_on="batter_id", right_on="batter", how="left")

    # Pull current L150 PA approximation: we already include only events with xwoba.
    # For sample threshold, use total_pa as career; for "current L150 PA" gate,
    # require at least MIN_CURRENT_L150_PA total events (close proxy when total>=150).
    df["has_current"] = df["current_l150"].notna() & (df["total_pa"] >= 150)

    # rh3 join for context
    try:
        rh3 = pd.read_csv(RH3_PATH)[["batter", "xfp_rh3_per_game", "rank"]]
        rh3 = rh3.rename(columns={"rank": "rh3_rank", "xfp_rh3_per_game": "rh3_pg"})
        df = df.merge(rh3, left_on="batter_id", right_on="batter", how="left", suffixes=("", "_rh3"))
    except Exception as e:
        print(f"  rh3 join failed: {e}", file=sys.stderr)
        df["rh3_pg"] = None
        df["rh3_rank"] = None

    # Categorise sample sufficiency
    df["sample_ok"] = (df["total_pa"] >= MIN_CAREER_PA) & df["has_current"]
    insufficient = df[~df["sample_ok"]].copy()
    main_df = df[df["sample_ok"]].copy()
    main_df["label"] = main_df["percentile"].apply(label)

    roster_main = main_df[main_df["source"] == "roster"].sort_values(
        ["percentile", "current_l150"], ascending=[False, False]
    )
    fa_main = main_df[
        (main_df["source"] == "fa") & (main_df["total_pa"] >= FA_MIN_CAREER_PA)
    ].sort_values("current_l150", ascending=False)

    # Roster floor: 25th percentile of roster current_l150 — used to filter FA upgrade lists
    roster_floor = (
        roster_main["current_l150"].quantile(0.25)
        if not roster_main.empty
        else 0.300
    )

    # Slumping cluster (your roster, percentile < 30)
    slumpers = roster_main[roster_main["percentile"] < 0.30].sort_values("percentile")
    peak_fa = fa_main[
        (fa_main["percentile"] >= 0.90) & (fa_main["current_l150"] > roster_floor)
    ].head(20)
    honest_pool = fa_main[
        (fa_main["percentile"] >= 0.50)
        & (fa_main["percentile"] < 0.80)
        & (fa_main["current_l150"] > roster_floor)
    ].sort_values("current_l150", ascending=False).head(20)

    # Anti-mirage cross check: bottom-3 by percentile -> 1-2 honest FAs above their current
    bottom3 = roster_main.head(0)
    if not roster_main.empty:
        bottom3 = roster_main.sort_values("percentile").head(3)

    # Render
    today = "2026-05-24"
    out = []
    out.append(f"# Career-form-rank sweep — {today}\n")
    out.append(
        f"Universe: BrownU roster ({len(roster_h)} hitters) + FA pool "
        f"({len(fa_h)} hitters). Cache: 2015-2026. Min career PA: {MIN_CAREER_PA}. "
        f"Min current L150 PA: {MIN_CURRENT_L150_PA}. Roster floor (P25 current_l150): "
        f"{roster_floor:.3f}.\n"
    )

    out.append("## Your hitters by current L150 xwOBA + career percentile\n")
    if roster_main.empty:
        out.append("_No roster hitters cleared sample thresholds._\n")
    else:
        view = roster_main.copy()
        view["Player"] = view["player_name"]
        view["Pos"] = view["position"]
        view["PA"] = view["total_pa"].astype(int).astype(str)
        view["Current L150"] = view["current_l150"].apply(fmt_n)
        view["Career median"] = view["career_median"].apply(fmt_n)
        view["Career max"] = view["career_max"].apply(fmt_n)
        view["Percentile"] = view["percentile"].apply(fmt_pct)
        view["Read"] = view["label"]
        view["rh3/g"] = view["rh3_pg"].apply(lambda x: fmt_n(x, 2))
        cols = [
            ("Player", "Player"), ("Pos", "Pos"), ("PA", "PA"),
            ("Current L150", "Curr L150"), ("Career median", "Career med"),
            ("Career max", "Career max"), ("Percentile", "Pct"),
            ("Read", "Read"), ("rh3/g", "rh3/g"),
        ]
        out.append(render_table(view, cols) + "\n")

    out.append(f"\n## All FAs (>= {FA_MIN_CAREER_PA} career PA) — current L150 + career percentile\n")
    if fa_main.empty:
        out.append("_No FA hitters cleared sample thresholds._\n")
    else:
        view = fa_main.head(50).copy()
        view["Player"] = view["player_name"]
        view["Pos"] = view["position"]
        view["PA"] = view["total_pa"].astype(int).astype(str)
        view["Current L150"] = view["current_l150"].apply(fmt_n)
        view["Career median"] = view["career_median"].apply(fmt_n)
        view["Career max"] = view["career_max"].apply(fmt_n)
        view["Percentile"] = view["percentile"].apply(fmt_pct)
        view["Own%"] = view["percent_owned"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
        view["rh3/g"] = view["rh3_pg"].apply(lambda x: fmt_n(x, 2))
        cols = [
            ("Player", "Player"), ("Pos", "Pos"), ("PA", "PA"),
            ("Current L150", "Curr L150"), ("Career median", "Career med"),
            ("Career max", "Career max"), ("Percentile", "Pct"),
            ("Own%", "Own%"), ("rh3/g", "rh3/g"),
        ]
        out.append(render_table(view, cols) + "\n")

    out.append("\n## Slumping cluster (your roster, percentile < 30)\n")
    if slumpers.empty:
        out.append("_None — no roster hitters below 30th percentile._\n")
    else:
        v = slumpers.copy()
        v["Player"] = v["player_name"]
        v["Pct"] = v["percentile"].apply(fmt_pct)
        v["Curr L150"] = v["current_l150"].apply(fmt_n)
        v["Career med"] = v["career_median"].apply(fmt_n)
        v["rh3/g"] = v["rh3_pg"].apply(lambda x: fmt_n(x, 2))
        cols = [
            ("Player", "Player"), ("Pct", "Pct"), ("Curr L150", "Curr L150"),
            ("Career med", "Career med"), ("rh3/g", "rh3/g"),
        ]
        out.append(render_table(v, cols) + "\n")

    out.append("\n## Peak-form FAs (>= 90th percentile, current > your roster floor) — MIRAGE PILE\n")
    if peak_fa.empty:
        out.append("_None._\n")
    else:
        v = peak_fa.copy()
        v["Player"] = v["player_name"]
        v["Pct"] = v["percentile"].apply(fmt_pct)
        v["Curr L150"] = v["current_l150"].apply(fmt_n)
        v["Career med"] = v["career_median"].apply(fmt_n)
        v["Own%"] = v["percent_owned"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
        cols = [
            ("Player", "Player"), ("Pct", "Pct"), ("Curr L150", "Curr L150"),
            ("Career med", "Career med"), ("Own%", "Own%"),
        ]
        out.append(render_table(v, cols) + "\n")
        out.append("_Do NOT recommend swapping into these — they're at career-peak and likely to revert._\n")

    out.append("\n## Honest upgrade pool (FAs in 50–80 percentile, current > your roster floor)\n")
    if honest_pool.empty:
        out.append("_None — no FA in that band cleared the floor._\n")
    else:
        v = honest_pool.copy()
        v["Player"] = v["player_name"]
        v["Pct"] = v["percentile"].apply(fmt_pct)
        v["Curr L150"] = v["current_l150"].apply(fmt_n)
        v["Career med"] = v["career_median"].apply(fmt_n)
        v["Own%"] = v["percent_owned"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
        v["rh3/g"] = v["rh3_pg"].apply(lambda x: fmt_n(x, 2))
        cols = [
            ("Player", "Player"), ("Pct", "Pct"), ("Curr L150", "Curr L150"),
            ("Career med", "Career med"), ("Own%", "Own%"), ("rh3/g", "rh3/g"),
        ]
        out.append(render_table(v, cols) + "\n")

    out.append("\n## Anti-mirage cross-check (bottom-3 roster slumpers → honest-pool FAs)\n")
    if bottom3.empty:
        out.append("_No roster slumpers to cross-check._\n")
    else:
        for _, slumper in bottom3.iterrows():
            curr = slumper["current_l150"]
            pct = slumper["percentile"]
            name = slumper["player_name"]
            pos = slumper["position"]
            out.append(
                f"\n### {name} ({pos}) — pct {fmt_pct(pct)}, curr_l150 {fmt_n(curr)}\n"
            )
            # honest FAs above their current
            cand = honest_pool[honest_pool["current_l150"] > curr].head(2)
            if cand.empty:
                out.append("_No honest-pool FA upgrade above this slumper's current L150._\n")
            else:
                for _, c in cand.iterrows():
                    out.append(
                        f"- **{c['player_name']}** ({c['position']}) — pct {fmt_pct(c['percentile'])}, "
                        f"curr {fmt_n(c['current_l150'])}, career med {fmt_n(c['career_median'])}, "
                        f"rh3/g {fmt_n(c['rh3_pg'], 2)}\n"
                    )

    # Recommendation
    out.append("\n## Recommendation\n")
    recs = []
    if not bottom3.empty and not honest_pool.empty:
        # pick at most 2 swap candidates: the worst slumper that has an honest upgrade above its current
        for _, slumper in bottom3.iterrows():
            cand = honest_pool[honest_pool["current_l150"] > slumper["current_l150"]].head(1)
            if not cand.empty:
                c = cand.iloc[0]
                # rh3 cross-check
                rh3_delta = (c["rh3_pg"] or 0) - (slumper["rh3_pg"] or 0)
                rh3_str = (
                    f"rh3/g Δ {rh3_delta:+.2f}"
                    if pd.notna(c["rh3_pg"]) and pd.notna(slumper["rh3_pg"])
                    else "rh3/g missing"
                )
                recs.append(
                    f"- **DROP {slumper['player_name']} ({slumper['position']}) → ADD "
                    f"{c['player_name']} ({c['position']}).** Slumper at "
                    f"{fmt_pct(slumper['percentile'])}th pct (career med "
                    f"{fmt_n(slumper['career_median'])} vs curr {fmt_n(slumper['current_l150'])}); "
                    f"FA at {fmt_pct(c['percentile'])}th pct (above-median but NOT peak-form), "
                    f"curr {fmt_n(c['current_l150'])}. {rh3_str}.\n"
                )
            if len(recs) >= 3:
                break
    if not recs:
        out.append("_No honest swap candidates — slumpers either lack an above-current FA in 50–80 pct band, or no slumpers exist. **HOLD.**_\n")
    else:
        out.extend(recs)

    # Unresolved appendix
    out.append("\n## Unresolved names\n")
    if unresolved.empty:
        out.append("_All names resolved._\n")
    else:
        for _, r in unresolved.iterrows():
            out.append(
                f"- {r['player_name']} ({r.get('position','')}, {r.get('pro_team','')}, src={r['source']})\n"
            )

    # Insufficient sample appendix
    insuf_main = insufficient[insufficient["source"] == "roster"]
    insuf_fa = insufficient[insufficient["source"] == "fa"]
    out.append("\n## Insufficient sample\n")
    out.append(f"- Roster: {len(insuf_main)} (< {MIN_CAREER_PA} career PA or < 150 PA total)\n")
    out.append(f"- FA: {len(insuf_fa)}\n")
    if not insuf_main.empty:
        names = ", ".join(insuf_main["player_name"].tolist())
        out.append(f"\nRoster names: {names}\n")

    OUT_PATH.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    print(f"  roster_analyzed={len(roster_main)} fa_analyzed={len(fa_main)} unresolved={len(unresolved)}", file=sys.stderr)


if __name__ == "__main__":
    main()
