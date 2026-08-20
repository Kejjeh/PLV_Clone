"""Trailing-stabilization-window xwOBA leaderboard - engine for /xwoba-l225.

WHY A PA WINDOW AND NOT A CALENDAR WINDOW
-----------------------------------------
Calendar windows (L7/L21/L42) do not stabilize for xwOBA. On the 2026 FA pool
the median PA per window is 8 / 28 / 53 against a required 225 - so every
short-window xwOBA read is noise BY CONSTRUCTION. This engine instead walks
back a fixed number of PA (the stabilization minimum, owned by
``plv_clone.stabilization``), crossing into the prior season when the current
one is short. Every row therefore carries the SAME denominator, which is what
makes the ranking legitimate.

The trade-off is honest and reported per row: a window that reaches back into
last season mixes two run environments, so ``pa_prior_in_window`` is emitted
and consumers are expected to discount rows that lean on it.

OWNER MODULES (registry rule: call, never re-derive)
  stabilization minimum   plv_clone.stabilization.minimum('xwoba_ppa', 'H')
  name -> join key        plv_clone.utils.name_match.join_key
  live roster / FA truth  app.espn_connector

xwOBA CONSTRUCTION
  xwOBA is per-PA, so it is NOT ``estimated_woba_using_speedangle`` (that is
  xwOBACON - contact only, and it silently drops the strikeouts and walks that
  dominate the metric). Savant's method, reproduced here: over rows with
  ``woba_denom == 1``, the numerator is xwOBAcon on batted balls and the actual
  wOBA linear weight otherwise (BB .69 / HBP .72 / K 0).

Outputs
  data/outputs/xwoba_l225.csv           (latest - stable path for consumers)
  data/outputs/xwoba_l225_<date>.csv    (dated snapshot)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from plv_clone import stabilization                      # noqa: E402
from plv_clone.utils.name_match import join_key, team_key  # noqa: E402

CACHE = ROOT / "data" / "research" / "xfp_cache"
OUT = ROOT / "data" / "outputs"
HIT_POS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH", "UTIL"}
SC_COLS = [
    "game_date", "batter", "woba_value", "woba_denom",
    "estimated_woba_using_speedangle",
]


def window_size() -> int:
    """The trailing-PA window = the xwOBA stabilization minimum (owner module)."""
    n, denom = stabilization.minimum("xwoba_ppa", side="H")
    assert denom == "pa", f"xwoba_ppa denominator changed to {denom!r}"
    return int(n)


def name_to_mlbam() -> dict[str, list[tuple[str, int]]]:
    """join_key -> [(team, mlbam), ...] from the already-mlbam-keyed model tables.

    Deliberately NOT from statcast ``player_name``: on pitch-level rows that
    column is the PITCHER, which matched 16/972 hitters when tried.

    Returns EVERY id per name, not the first one. A ``setdefault`` here silently
    collapses same-name pairs onto whichever row happened to sort first - the
    canonical Max Muncy failure (LAD 571970 rh3 #84 vs ATH 691777 rh3 #457).
    Disambiguation is the caller's job, using team (see ``resolve_one``).
    """
    out: dict[str, list[tuple[str, int]]] = {}
    seen: set[tuple[str, int]] = set()
    for fname, idcol in (
        ("xfp_rh3_projections.csv", "batter"),
        ("xfp_volume_projections.csv", "mlbam_id"),
    ):
        path = OUT / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if idcol not in df.columns or "player_name" not in df.columns:
            continue
        teams = df["team"] if "team" in df.columns else pd.Series([""] * len(df))
        for nm, mid, tm in zip(df["player_name"], df[idcol], teams):
            if pd.isna(mid):
                continue
            k, mid = join_key(nm), int(mid)
            if (k, mid) in seen:
                continue
            seen.add((k, mid))
            out.setdefault(k, []).append((str(tm or ""), mid))
    return out


def resolve_one(k: str, team: str, cands: list[tuple[str, int]]) -> int | None:
    """Pick the mlbam for one player, refusing to guess on an ambiguous name."""
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][1]
    want = team_key(team)
    hits = [mid for tm, mid in cands if tm and team_key(tm) == want]
    if len(hits) == 1:
        return hits[0]
    # Ambiguous and team did not separate them: skip rather than guess wrong.
    print(f"  ! AMBIGUOUS name {k!r} (team {team!r}) -> {cands} - skipped")
    return None


def load_pa(years: list[int], keep: set[int]) -> pd.DataFrame:
    """PA-ending rows with an xwOBA numerator, for the given batters."""
    parts = []
    for y in years:
        path = CACHE / f"statcast_{y}.parquet"
        if not path.exists():
            print(f"  ! statcast_{y}.parquet missing - window cannot reach {y}")
            continue
        d = pd.read_parquet(path, columns=SC_COLS)
        d = d[(d["woba_denom"] == 1) & d["batter"].isin(keep)].copy()
        d["season"] = y
        parts.append(d)
    if not parts:
        return pd.DataFrame(columns=SC_COLS + ["season"])
    pa = pd.concat(parts, ignore_index=True)
    pa["game_date"] = pd.to_datetime(pa["game_date"])
    # Savant's xwOBA numerator: xwOBAcon on batted balls, else the wOBA weight.
    # ACTUAL wOBA over the same PA rows. `woba_value` is the realised linear
    # weight per PA, so a plain mean over woba_denom==1 rows IS wOBA. Emitted
    # beside xwOBA so the luck gap (woba - xwoba) is readable directly: a bat
    # can be under- or over-performing its contact quality, and the xwOBA
    # column alone cannot show which.
    pa["wnum"] = pa["woba_value"]
    pa["xnum"] = pa["estimated_woba_using_speedangle"].where(
        pa["estimated_woba_using_speedangle"].notna(), pa["woba_value"]
    )
    return pa[pa["xnum"].notna()].sort_values(["batter", "game_date"])


def population(scope: str) -> dict[tuple[str, str], dict]:
    """(join_key, team_key) -> player meta over the requested scope.

    Keyed by name+TEAM, not name alone: three same-name FA hitters (incl. the
    canonical Max Muncy ATH, whose namesake is on Josh's roster) were being
    silently dropped by a name-only ``k in rostered`` test.
    """
    from app.espn_connector import get_all_teams
    import app.espn_connector as ec

    pop: dict[tuple[str, str], dict] = {}
    teams = get_all_teams()
    rostered = {(join_key(n), team_key(t))
                for n, t in zip(teams["player_name"], teams["pro_team"])}

    if scope in ("roster", "league", "all"):
        for _, r in teams.iterrows():
            if r["position"] not in HIT_POS:
                continue
            k = (join_key(r["player_name"]), team_key(r["pro_team"]))
            mine = "Liger" in str(r["team_name"])
            if scope == "roster" and not mine:
                continue
            pop[k] = {
                "name": r["player_name"], "pos": r["position"],
                "tm": r["pro_team"], "own": np.nan,
                "inj": r.get("injury_status") or "", "owner": r["team_name"],
                "is_mine": mine,
            }

    if scope in ("fa", "league", "all"):
        # gotcha #6: ONE size=2000 pull, then filter - never per-position caps.
        for p in ec._get_league().free_agents(size=2000):
            k = (join_key(p.name), team_key(p.proTeam))
            if k in rostered:          # gotcha #4: live availability, not memory
                continue
            elig = {str(s) for s in (getattr(p, "eligibleSlots", []) or [])}
            if not (p.position in HIT_POS or (elig & HIT_POS)):
                continue
            pop[k] = {
                "name": p.name, "pos": p.position, "tm": p.proTeam,
                "own": float(getattr(p, "percent_owned", 0) or 0),
                "inj": str(getattr(p, "injuryStatus", "") or ""),
                "owner": "FA", "is_mine": False,
            }
    return pop


def build(scope: str, season: int) -> pd.DataFrame:
    N = window_size()
    print(f"  window = trailing {N} PA "
          f"({stabilization.describe('xwoba_ppa', side='H')})")

    pop = population(scope)
    print(f"  population ({scope}): {len(pop)} hitters")

    ids = name_to_mlbam()
    by_id: dict[int, tuple[str, str]] = {}
    ambiguous = 0
    claims: dict[int, list[tuple[str, str]]] = {}
    for k, meta in pop.items():
        nk = k[0]
        mid = resolve_one(nk, meta.get("tm") or "", ids.get(nk, []))
        if mid is None:
            ambiguous += len(ids.get(nk, [])) > 1
            continue
        claims.setdefault(mid, []).append(k)

    # Two population entries claiming ONE mlbam means a same-name pair where the
    # model tables only carry one of them. Last-writer-wins would silently graft
    # the modelled player's stats onto his namesake (canonical: an unrostered
    # "Julio Rodriguez" inheriting the SEA star's line and topping the FA board).
    # Keep only the entry whose team matches the model row; if none does, drop
    # every claimant rather than guess.
    for mid, ks in claims.items():
        if len(ks) == 1:
            by_id[mid] = ks[0]
            continue
        model_teams = {team_key(t) for t, m in
                       (tm for cand in ids.values() for tm in cand) if m == mid}
        keep = [k for k in ks if k[1] in model_teams]
        if len(keep) == 1:
            by_id[mid] = keep[0]
            print(f"  ! same-name pair on mlbam {mid}: kept "
                  f"{keep[0]}, dropped {[k for k in ks if k != keep[0]]}")
        else:
            ambiguous += len(ks)
            print(f"  ! same-name pair on mlbam {mid} unresolvable by team "
                  f"({ks}) - ALL dropped")
    print(f"  resolved to mlbam: {len(by_id)}"
          + (f"  ({ambiguous} skipped as ambiguous)" if ambiguous else ""))
    if not by_id:
        return pd.DataFrame()

    pa = load_pa([season - 1, season], set(by_id))
    if pa.empty:
        return pd.DataFrame()
    cur = pa[pa["season"] == season]
    asof = cur["game_date"].max() if len(cur) else pa["game_date"].max()
    print(f"  statcast through {asof.date()} | {len(pa):,} PA rows")

    rows = []
    for bid, d in pa.groupby("batter"):
        d = d.sort_values("game_date")
        w = d.tail(N)
        d_cur = d[d["season"] == season]
        d_pri = d[d["season"] == season - 1]
        rows.append({
            "mlbam": bid,
            "xwoba_window": w["xnum"].mean(),
            "woba_window": w["wnum"].mean(),
            "luck_gap": w["wnum"].mean() - w["xnum"].mean(),
            "pa_window": len(w),
            "pa_current_in_window": int((w["season"] == season).sum()),
            "pa_prior_in_window": int((w["season"] == season - 1).sum()),
            "window_from": w["game_date"].min().date().isoformat(),
            "window_to": w["game_date"].max().date().isoformat(),
            "xwoba_current": d_cur["xnum"].mean() if len(d_cur) else np.nan,
            "woba_current": d_cur["wnum"].mean() if len(d_cur) else np.nan,
            "pa_current": len(d_cur),
            "xwoba_prior": d_pri["xnum"].mean() if len(d_pri) else np.nan,
            "woba_prior": d_pri["wnum"].mean() if len(d_pri) else np.nan,
            "days_since_last_pa": int((asof - d["game_date"].max()).days),
        })
    x = pd.DataFrame(rows)
    x["window_full"] = x["pa_window"] >= N
    x["k"] = x["mlbam"].map(by_id)
    for col in ("name", "pos", "tm", "own", "inj", "owner", "is_mine"):
        x[col] = x["k"].map(lambda z, c=col: pop[z][c])
    # NOT "asof": DataFrame.asof is a real method, so df.asof silently returns
    # the bound method instead of the column and breaks consumers.
    x["asof_date"] = asof.date().isoformat()
    x["window_pa_target"] = N
    x = x.sort_values("xwoba_window", ascending=False).reset_index(drop=True)
    x["rank_full_window"] = np.where(
        x["window_full"], x["window_full"].cumsum(), np.nan)
    return x


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", choices=["all", "fa", "roster", "league"],
                    default="all")
    ap.add_argument("--season", type=int, default=date.today().year)
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()

    print("=== xwOBA trailing-stabilization-window leaderboard ===")
    x = build(a.scope, a.season)
    if x.empty:
        print("  no rows produced")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    x.to_csv(OUT / "xwoba_l225.csv", index=False)
    x.to_csv(OUT / f"xwoba_l225_{x["asof_date"].iloc[0]}.csv", index=False)
    full = int(x["window_full"].sum())
    print(f"  wrote {len(x)} rows ({full} with a full window) -> "
          f"data/outputs/xwoba_l225.csv")

    if a.top <= 0:          # nightly mode: write only, no console table
        return 0
    show = x[x["window_full"]].head(a.top)
    cols = ["rank_full_window", "name", "pos", "tm", "owner", "inj",
            "xwoba_window", "woba_window", "luck_gap",
            "pa_current_in_window", "pa_prior_in_window",
            "xwoba_current", "xwoba_prior"]
    with pd.option_context("display.width", 400, "display.max_rows", 400):
        print(show[cols].round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
