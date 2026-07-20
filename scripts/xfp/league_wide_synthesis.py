"""League-wide roster-deep-audit synthesis.

Reads `league_career_form_<today>.csv` (built by league_wide_career_form.py),
joins to rh3/rp3/rprs2 projections, builds:
  1. Per-team agreement matrix (career-form bucket × rh3 signal × recency_form_gap)
  2. Cross-team trade-target list (rivals' CONSENSUS_HOLD_BOUNCE / BUY-LOW)
  3. Power ranking by roster aggregate

Writes `data/research/roster_deep_audit_league_<date>.md`.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
from plv_clone.projections import PROJECTIONS
from plv_clone.league_config import MY_TEAM_NAME

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

MY_TEAM = MY_TEAM_NAME
TODAY = date.today().isoformat()


def cross_verdict(form: str, gap: float | None, signal: str | None) -> str:
    """Synthesize CROSS_VERDICT from career-form + recency-form-gap + signal.

    Mimics the /roster-deep-audit Step 7 logic without re-running the full
    sustainability sweep — we use rh3.recency_form_gap as the sustainability
    proxy (positive gap = hot/possible-sell; negative = cold/possible-bounce).
    """
    if form == "INSUFFICIENT":
        return "INSUFFICIENT_DATA"
    gap = gap if pd.notna(gap) else 0.0
    if form == "SLUMPING":
        if gap < -0.020:
            return "CONSENSUS_DROP"  # career floor + still cold
        if gap > 0.010:
            return "CONSENSUS_HOLD_BOUNCE"  # career floor but warming
        return "SLUMP_AMBIGUOUS"
    if form == "BELOW_MEDIAN":
        if gap < -0.020:
            return "FADING"
        if gap > 0.020:
            return "BOUNCING_BACK"
        return "CONSENSUS_HOLD_TYPICAL"
    if form == "TYPICAL":
        return "CONSENSUS_HOLD_TYPICAL"
    if form == "ABOVE_MEDIAN":
        if gap > 0.030:
            return "STRENGTHENING"
        return "STABLE_PRODUCER"
    if form == "HIGH":
        if gap < -0.020:
            return "PEAK_FADING"
        return "STABLE_HIGH"
    if form == "PEAK":
        if gap < -0.020:
            return "SELL_HIGH_WARNING"  # peak + cooling
        return "CONSENSUS_HOLD_PEAK"
    return "UNCLASSIFIED"


def main() -> None:
    cf = pd.read_csv(REPO / f"data/research/league_career_form_{TODAY}.csv")
    rh3 = PROJECTIONS.rh3()

    merged = cf.merge(
        rh3[["batter", "xfp_rh3_per_pa", "prior_fp_per_pa", "recency_form_gap",
             "signal", "rank", "replacement_delta"]],
        on="batter", how="left",
    )
    merged["cross_verdict"] = merged.apply(
        lambda r: cross_verdict(r["form_bucket"], r["recency_form_gap"], r.get("signal")),
        axis=1,
    )

    # Pitchers: pull rh3-sibling rp3 + rprs2 for power ranking only (no career-form on pitchers)
    teams_path = REPO / "data/research/league_career_form_{}.csv".format(TODAY)
    from plv_clone.league_state import LeagueState  # noqa: E402
    all_rosters = LeagueState().all_teams()
    pitchers = all_rosters[all_rosters["position"].isin(["SP", "RP"])].copy()
    rp3 = PROJECTIONS.rp3()
    rprs2 = PROJECTIONS.rprs2()

    # Fuzzy-join pitchers by name only (cheap; mlbam matching is overkill here)
    rp3_lookup = dict(zip(rp3["player_name"], rp3["xfp_rp3_per_start"]))
    rprs2_col = "xfp_ros" if "xfp_ros" in rprs2.columns else rprs2.columns[-1]
    rprs2_lookup = dict(zip(rprs2["name_api"], rprs2[rprs2_col]))

    def proj_for(row):
        n = row["player_name"]
        if row["position"] == "SP":
            return rp3_lookup.get(n)
        if row["position"] == "RP":
            return rprs2_lookup.get(n)
        return None

    pitchers["proj"] = pitchers.apply(proj_for, axis=1)

    # ── BUILD REPORT ──
    lines: list[str] = []
    lines.append(f"# League-wide roster deep audit — {TODAY}\n")
    lines.append(f"Universe: 8 BrownU teams ({len(merged)} hitters resolved, "
                 f"{len(pitchers)} pitchers).\n")

    # 1. Power ranking
    lines.append("## Power ranking (aggregate roster strength)\n")
    power = merged.groupby("team_name").agg(
        n_hitters=("batter", "count"),
        mean_percentile=("percentile", "mean"),
        median_percentile=("percentile", "median"),
        n_peak_or_high=("form_bucket", lambda s: ((s == "PEAK") | (s == "HIGH")).sum()),
        n_slumping=("form_bucket", lambda s: (s == "SLUMPING").sum()),
        mean_rh3=("xfp_rh3_per_pa", "mean"),
        sum_replacement_delta=("replacement_delta", "sum"),
    ).round(3)
    pitcher_strength = pitchers.dropna(subset=["proj"]).groupby("team_name")["proj"].sum().round(1)
    power["sp_rp_proj_total"] = pitcher_strength
    power = power.sort_values("mean_rh3", ascending=False)
    power.insert(0, "rank", range(1, len(power) + 1))
    lines.append(power.to_markdown())
    lines.append("")

    # 2. Per-team agreement matrix
    lines.append("\n## Per-team agreement matrix\n")
    for tname, grp in merged.groupby("team_name"):
        marker = " ← YOU" if tname == MY_TEAM else ""
        lines.append(f"\n### {tname}{marker}\n")
        tbl = grp.sort_values("percentile", ascending=False)[
            ["player_name", "position", "total_pa", "current_l150",
             "percentile", "form_bucket", "recency_form_gap",
             "xfp_rh3_per_pa", "signal", "cross_verdict"]
        ].rename(columns={"current_l150": "L150_xwoba",
                          "percentile": "career_%ile",
                          "recency_form_gap": "form_gap",
                          "xfp_rh3_per_pa": "rh3"})
        lines.append(tbl.round(3).to_markdown(index=False))
        lines.append("")

    # 3. Trade targets (rival rosters only)
    lines.append("\n## Trade-target list — rival players to buy\n")
    lines.append("Filter: not on YOUR roster + cross_verdict in {CONSENSUS_HOLD_BOUNCE, "
                 "BOUNCING_BACK, SLUMP_AMBIGUOUS} + rh3 above replacement.\n")
    targets = merged[
        (merged["team_name"] != MY_TEAM)
        & (merged["cross_verdict"].isin(["CONSENSUS_HOLD_BOUNCE", "BOUNCING_BACK", "SLUMP_AMBIGUOUS"]))
        & (merged["replacement_delta"] > 0.005)
    ].sort_values("replacement_delta", ascending=False).head(25)
    if len(targets):
        lines.append(targets[
            ["team_name", "player_name", "position", "career_mean", "current_l150",
             "percentile", "form_bucket", "recency_form_gap", "xfp_rh3_per_pa",
             "replacement_delta", "cross_verdict"]
        ].round(3).to_markdown(index=False))
    else:
        lines.append("_No qualifying trade targets._")
    lines.append("")

    # 4. Sell-high warnings on YOUR roster (peakers cooling)
    lines.append("\n## Sell-high candidates on YOUR roster\n")
    my_sell = merged[
        (merged["team_name"] == MY_TEAM)
        & (merged["cross_verdict"].isin(["SELL_HIGH_WARNING", "PEAK_FADING"]))
    ]
    if len(my_sell):
        lines.append(my_sell[
            ["player_name", "position", "percentile", "form_bucket",
             "recency_form_gap", "xfp_rh3_per_pa", "cross_verdict"]
        ].round(3).to_markdown(index=False))
    else:
        lines.append("_None — no peakers cooling on your roster._")

    # 5. Sell-high market across league (their peakers cooling = you offer)
    lines.append("\n## Rival peakers cooling — they may sell, you may buy cheap\n")
    rival_sell = merged[
        (merged["team_name"] != MY_TEAM)
        & (merged["cross_verdict"].isin(["SELL_HIGH_WARNING", "PEAK_FADING"]))
    ].sort_values("xfp_rh3_per_pa", ascending=False)
    if len(rival_sell):
        lines.append(rival_sell[
            ["team_name", "player_name", "position", "percentile",
             "form_bucket", "recency_form_gap", "xfp_rh3_per_pa", "cross_verdict"]
        ].round(3).to_markdown(index=False))
    else:
        lines.append("_None._")

    out_path = REPO / f"data/research/roster_deep_audit_league_{TODAY}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"  power ranking rows:        {len(power)}")
    print(f"  trade targets:             {len(targets)}")
    print(f"  your sell-high candidates: {len(my_sell)}")
    print(f"  rival peakers cooling:     {len(rival_sell)}")


if __name__ == "__main__":
    main()
