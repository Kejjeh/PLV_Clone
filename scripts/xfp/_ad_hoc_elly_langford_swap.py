"""Ad-hoc analysis: replace Elly (IL'd, in 2B/SS slot) and Langford (IL'd, in OF slot).

Pulls live roster, joins rh3 with (norm_name, pro_team) tuple key, identifies
bench candidates and (if needed) FA candidates, computes weekly FP gain.
"""
from __future__ import annotations

import sys
import unicodedata
import pandas as pd
from pathlib import Path

ROOT = Path(r"c:/Users/Joshua/plv_clone")
sys.path.insert(0, str(ROOT))

from app.espn_connector import (
    get_my_roster_with_injuries,
    get_all_teams,
    _get_league,
)


from plv_clone.utils.name_match import safe_name_key as norm  # noqa: E402  OWNER


def main() -> None:
    rh3 = pd.read_csv(ROOT / "data/outputs/xfp_rh3_projections.csv")
    rh3["nkey"] = rh3["player_name"].map(norm)
    rh3["tkey"] = rh3["team"].astype(str).str.upper().str.strip()
    # Build a (norm_name, pro_team) -> projection lookup; honor collisions.
    rh3_lookup = {(r.nkey, r.tkey): r for r in rh3.itertuples(index=False)}
    # Fallback by name only for non-colliding names
    name_counts = rh3.groupby("nkey").size()
    safe_by_name = {
        r.nkey: r for r in rh3.itertuples(index=False) if name_counts[r.nkey] == 1
    }

    def lookup(name: str, team: str):
        k = (norm(name), str(team).upper().strip())
        if k in rh3_lookup:
            return rh3_lookup[k]
        # only fall back if name is unique in rh3
        if norm(name) in safe_by_name:
            return safe_by_name[norm(name)]
        return None

    print("=" * 78)
    print("STEP 1 — ROSTER SNAPSHOT")
    print("=" * 78)
    roster = get_my_roster_with_injuries()
    cols = [
        "player_name", "position", "pro_team", "lineup_slot",
        "injured", "injury_status", "return_date", "days_until_return",
    ]
    avail_cols = [c for c in cols if c in roster.columns]
    roster_view = roster[avail_cols + ["eligible_slots"]].copy()

    def rh3_pg(r):
        rec = lookup(r["player_name"], r["pro_team"])
        return rec.xfp_rh3_per_game if rec is not None else None

    roster_view["rh3_pg"] = roster_view.apply(rh3_pg, axis=1)

    # Categorize by slot
    IL_SLOTS = {"IL"}
    BENCH_SLOTS = {"BE", "BN"}
    active = roster_view[~roster_view["lineup_slot"].isin(IL_SLOTS | BENCH_SLOTS)]
    bench = roster_view[roster_view["lineup_slot"].isin(BENCH_SLOTS)]
    il_slot = roster_view[roster_view["lineup_slot"].isin(IL_SLOTS)]

    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.width", 200)

    print("\nACTIVE SLOTS:")
    print(active[["player_name", "lineup_slot", "position", "pro_team", "injured",
                  "injury_status", "rh3_pg"]].to_string(index=False))
    print("\nBENCH (BE):")
    print(bench[["player_name", "lineup_slot", "position", "pro_team", "injured",
                 "injury_status", "rh3_pg"]].to_string(index=False))
    print("\nIL SLOTS (lineup_slot=='IL'):")
    if il_slot.empty:
        print(" (none)")
    else:
        print(il_slot[["player_name", "lineup_slot", "position", "pro_team",
                       "injury_status", "rh3_pg"]].to_string(index=False))

    print(f"\nIL slot usage: {len(il_slot)} / 3")
    print(f"Active slots: {len(active)} | Bench: {len(bench)}")

    # Step 2: Find Elly & Langford rows
    print("\n" + "=" * 78)
    print("STEP 2 — ELLY & LANGFORD CURRENT STATUS")
    print("=" * 78)
    targets = roster_view[
        roster_view["player_name"].str.contains("De La Cruz|Langford", case=False, na=False)
    ]
    print(targets[["player_name", "lineup_slot", "position", "pro_team", "injured",
                   "injury_status", "return_date", "days_until_return",
                   "rh3_pg", "eligible_slots"]].to_string(index=False))

    # Step 3: Bench candidates eligible for 2B/SS or OF, healthy
    print("\n" + "=" * 78)
    print("STEP 3 — HEALTHY BENCH CANDIDATES BY ELIGIBILITY")
    print("=" * 78)

    def eligible(row, slot_set):
        es = row.get("eligible_slots") or []
        return any(s in es for s in slot_set)

    def healthy(row):
        # Treat injured==False AND injury_status not in DTD/IL-10/IL-15/IL-60 as healthy
        if bool(row.get("injured")):
            return False
        status = str(row.get("injury_status") or "").upper()
        return status in ("", "ACTIVE", "NORMAL")

    bench_full = bench.copy()
    bench_full["healthy"] = bench_full.apply(healthy, axis=1)

    print("\n--- Bench candidates eligible for 2B or SS (Elly's slot) ---")
    for _, r in bench_full.iterrows():
        elig = r.get("eligible_slots") or []
        if "2B" in elig or "SS" in elig or "2B/SS" in elig:
            print(f"  {r['player_name']:25s} pos={r['position']:8s} "
                  f"slot={r['lineup_slot']:5s} healthy={r['healthy']} "
                  f"rh3={r['rh3_pg']} injury={r['injury_status']!r} elig={elig}")

    print("\n--- Bench candidates eligible for OF (Langford's slot) ---")
    for _, r in bench_full.iterrows():
        elig = r.get("eligible_slots") or []
        if "OF" in elig or "LF" in elig or "CF" in elig or "RF" in elig:
            print(f"  {r['player_name']:25s} pos={r['position']:8s} "
                  f"slot={r['lineup_slot']:5s} healthy={r['healthy']} "
                  f"rh3={r['rh3_pg']} injury={r['injury_status']!r} elig={elig}")

    # Also show all eligible_slots values present on bench (debugging)
    print("\n--- All bench eligible_slots (for debugging slot codes) ---")
    for _, r in bench.iterrows():
        print(f"  {r['player_name']:25s} elig={r.get('eligible_slots')}")

    # Step 4: FA scan — pull and rank by rh3 within 2B/SS/OF
    print("\n" + "=" * 78)
    print("STEP 4 — FA SCAN (size=2000) — top hitters by rh3 for 2B/SS and OF")
    print("=" * 78)
    league = _get_league()
    fas = league.free_agents(size=2000)

    hitter_pos = {"C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH"}
    fa_rows = []
    for p in fas:
        pos = getattr(p, "position", "")
        if pos not in hitter_pos:
            continue
        fa_rows.append({
            "player_name": p.name,
            "position": pos,
            "pro_team": getattr(p, "proTeam", ""),
            "eligible_slots": getattr(p, "eligibleSlots", []),
            "injured": bool(getattr(p, "injured", False)),
            "injury_status": getattr(p, "injuryStatus", "") or "",
            "percent_owned": getattr(p, "percent_owned", 0.0),
        })
    fa = pd.DataFrame(fa_rows)
    fa["rh3_pg"] = fa.apply(lambda r: (lookup(r["player_name"], r["pro_team"]) or type("x", (), {"xfp_rh3_per_game": None})).xfp_rh3_per_game, axis=1)
    fa["healthy"] = fa.apply(healthy, axis=1)

    def fa_eligible(row, codes):
        es = row.get("eligible_slots") or []
        return any(c in es for c in codes)

    # 2B/SS pool
    fa_inf = fa[fa.apply(lambda r: fa_eligible(r, ["2B", "SS"]) and r["healthy"], axis=1)].copy()
    fa_inf = fa_inf.sort_values("rh3_pg", ascending=False, na_position="last").head(8)
    print("\n--- Top FA hitters eligible for 2B/SS (healthy) ---")
    print(fa_inf[["player_name", "position", "pro_team", "rh3_pg", "percent_owned", "injury_status"]].to_string(index=False))

    fa_of = fa[fa.apply(lambda r: fa_eligible(r, ["OF", "LF", "CF", "RF"]) and r["healthy"], axis=1)].copy()
    fa_of = fa_of.sort_values("rh3_pg", ascending=False, na_position="last").head(8)
    print("\n--- Top FA hitters eligible for OF (healthy) ---")
    print(fa_of[["player_name", "position", "pro_team", "rh3_pg", "percent_owned", "injury_status"]].to_string(index=False))

    # Step 5: Long-term cross-check
    print("\n" + "=" * 78)
    print("STEP 5 — ELLY & LANGFORD long-term hold/drop math")
    print("=" * 78)
    for _, r in targets.iterrows():
        print(f"\n{r['player_name']} ({r['pro_team']}):")
        print(f"  injury_status: {r.get('injury_status')}")
        print(f"  return_date  : {r.get('return_date')}")
        print(f"  days_out     : {r.get('days_until_return')}")
        print(f"  rh3 per_game : {r.get('rh3_pg')}")


if __name__ == "__main__":
    main()
