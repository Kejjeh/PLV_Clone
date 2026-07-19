"""League-wide career-form computation for all rostered hitters.

Resolves names → batter IDs (collision-safe), pulls 2015-2026 PA events
from the statcast parquets, computes rolling-150 PA xwOBA, surfaces
current L150 + career percentile per player. Writes
`data/research/league_career_form_<date>.csv`.

Single-pass: 230 rostered players → one DuckDB UNION ALL across years,
one rolling-window pass, percentile per batter. Much cheaper than
running the per-player skill 8× (once per fantasy team).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import unicodedata
from plv_clone.utils.name_match import lookup_batter_id_cached  # noqa: E402


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _resolve(name: str, team: str, pos: str):
    bid = lookup_batter_id_cached(name, team=team, position=pos)
    if bid is not None:
        return bid
    stripped = _strip_accents(name)
    if stripped != name:
        bid = lookup_batter_id_cached(stripped, team=team, position=pos)
        if bid is not None:
            return bid
    # Try Jr/period variants
    for variant in [name.replace(" Jr.", ""), name.replace(".", ""), stripped.replace(" Jr.", "")]:
        if variant != name:
            bid = lookup_batter_id_cached(variant, team=team, position=pos)
            if bid is not None:
                return bid
    return None

from plv_clone.league_state import LeagueState  # noqa: E402


def main() -> None:
    teams = LeagueState().all_teams()
    hitters = teams[~teams["position"].isin(["SP", "RP", "P"])].copy()
    print(f"[1/4] {len(hitters)} rostered hitters across {hitters['team_id'].nunique()} teams")

    # Resolve batter IDs (collision-safe via cache + KNOWN_COLLISIONS fallback)
    hitters["batter"] = hitters.apply(
        lambda r: _resolve(r["player_name"], r["pro_team"], r["position"]),
        axis=1,
    )
    unresolved = hitters[hitters["batter"].isna()]
    if len(unresolved):
        print(f"  [warn] {len(unresolved)} unresolved:")
        for _, r in unresolved.iterrows():
            print(f"    - {r['player_name']} ({r['pro_team']}, {r['position']})")
    hitters = hitters.dropna(subset=["batter"]).copy()
    hitters["batter"] = hitters["batter"].astype(int)
    print(f"[2/4] {len(hitters)} resolved")

    ids = sorted(hitters["batter"].unique().tolist())
    ids_csv = ",".join(str(b) for b in ids)
    years = range(2015, 2027)
    union = " UNION ALL ".join(
        f"SELECT batter, game_date, estimated_woba_using_speedangle AS xwoba "
        f"FROM read_parquet('{(REPO / f'data/research/xfp_cache/statcast_{y}.parquet').as_posix()}') "
        f"WHERE batter IN ({ids_csv}) AND events IS NOT NULL AND events != '' "
        f"AND estimated_woba_using_speedangle IS NOT NULL"
        for y in years
    )

    print(f"[3/4] DuckDB rolling-150 over {len(years)} year parquets...")
    con = duckdb.connect()
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
    per_batter AS (
      SELECT batter, total_pa,
             AVG(roll150)    FILTER (WHERE rn >= 150) AS career_mean,
             MEDIAN(roll150) FILTER (WHERE rn >= 150) AS career_median,
             MIN(roll150)    FILTER (WHERE rn >= 150) AS career_min,
             MAX(roll150)    FILTER (WHERE rn >= 150) AS career_max,
             MAX(roll150)    FILTER (WHERE rn = total_pa) AS current_l150
      FROM rolling GROUP BY batter, total_pa
    ),
    percentile AS (
      SELECT r.batter,
             SUM(CASE WHEN r.roll150 < p.current_l150 THEN 1 ELSE 0 END) * 1.0
               / NULLIF(COUNT(*), 0) AS percentile
      FROM rolling r JOIN per_batter p USING (batter)
      WHERE r.rn >= 150 GROUP BY r.batter
    )
    SELECT b.*, pc.percentile
    FROM per_batter b LEFT JOIN percentile pc USING (batter)
    """
    res = con.execute(sql).df()
    print(f"  [ok] {len(res)} batters processed")

    out = hitters.merge(res, on="batter", how="left")

    def bucket(p):
        if pd.isna(p):
            return "INSUFFICIENT"
        if p >= 0.90:
            return "PEAK"
        if p >= 0.80:
            return "HIGH"
        if p >= 0.60:
            return "ABOVE_MEDIAN"
        if p >= 0.40:
            return "TYPICAL"
        if p >= 0.20:
            return "BELOW_MEDIAN"
        return "SLUMPING"

    out["form_bucket"] = out["percentile"].apply(bucket)
    today = date.today().isoformat()
    out_path = REPO / f"data/research/league_career_form_{today}.csv"
    out.to_csv(out_path, index=False)
    print(f"[4/4] wrote {out_path}")
    print(out.groupby(["team_name", "form_bucket"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
