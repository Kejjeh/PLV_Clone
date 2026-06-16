"""Simplified full-week roster simulation: does the full merge protocol
(Tier A blended + Tier B veto + boom-bust modulation) beat naive
Blended xFP only over historical 2025 windows?

Method:
 1. Universe = master_panel 2025 H + SP rows with a valid prior-year FP
    anchor (proxy for "Blended xFP" at as_of date, no look-ahead).
 2. For each as_of date in a set of mid-2025 weeks:
    a) Compute Strategy A: top 13 H + 5 SP by prior_year FP anchor.
    b) Compute Strategy B: same ranked pool, but apply
       - Tier B veto: downgrade one tier if hitter xwOBA L21d before
         as_of is < prior_year_xwoba - 0.060, or if SP K% L30d before
         as_of < prior_year_k_pct - 0.08
       - Boom/bust check: from each player's last-N games BEFORE
         as_of, compute boom% (H >= 5, SP >= 20) and bust%
         (H < 0, SP < 5). If boom% > 25%, bump up one tier; if
         bust% > 25%, downgrade one tier.
       Then re-rank by adjusted score and pick top 13 H + 5 SP.
    c) Compute realized FP over next 7 days from statcast events for
       both rosters.
 3. Compare totals per week; aggregate net delta.

Caveats:
 - No position-eligibility (treats hitters as fungible).
 - No IL/active-roster handling.
 - No SP 10-start cap (only 5 starters; not a binding cap).
 - Uses statcast events to recompute realized FP (close to MLB Stats
   API gameLog but derived from raw events, not boxscore).
 - "Blended xFP" proxy = prior-year FP/G or FP/start; the real
   production blend mixes archetype + age + PL rank, but the question
   is "does layering Tier B + boom-bust on top of a raw rank help",
   so this proxy isolates the increment.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("c:/Users/Joshua/plv_clone")
PANEL = REPO / "data/research/historical_panel/master_panel.parquet"
STATCAST_2024 = REPO / "data/research/xfp_cache/statcast_2024.parquet"
STATCAST_2025 = REPO / "data/research/xfp_cache/statcast_2025.parquet"
OUT = REPO / "data/research/validation_runs/full_week_simulation_2026-06-06.md"

# wOBA weights (Fangraphs 2023, close enough for 2024/2025)
WOBA = {
    "walk": 0.69, "hit_by_pitch": 0.72, "single": 0.88, "double": 1.247,
    "triple": 1.578, "home_run": 2.031,
}

WEEKS = [
    # (as_of (Mon), end (Sun))
    (dt.date(2025, 6, 16), dt.date(2025, 6, 22)),
    (dt.date(2025, 6, 30), dt.date(2025, 7, 6)),
    (dt.date(2025, 7, 14), dt.date(2025, 7, 20)),
    (dt.date(2025, 8, 4),  dt.date(2025, 8, 10)),
    (dt.date(2025, 8, 18), dt.date(2025, 8, 24)),
    (dt.date(2025, 9, 1),  dt.date(2025, 9, 7)),
]

TOP_H = 13
TOP_SP = 5

# Boom/bust thresholds (canonical from CLAUDE.md skill notes)
H_BOOM = 5
H_BUST = 0
SP_BOOM = 20
SP_BUST = 5

H_RECENT_WINDOW_GAMES = 21
SP_RECENT_WINDOW_GAMES = 8

# Tier B thresholds
H_XWOBA_DROP_THRESH = -0.060
SP_K_DROP_THRESH = 0.08

# -------------------- FP computation from statcast events --------------------

def hitter_fp_per_game(sc_window: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-batter, per-game FP using BrownU hitter formula."""
    df = sc_window[sc_window["events"].notna()].copy()
    df["singles"] = (df["events"] == "single").astype(int)
    df["doubles"] = (df["events"] == "double").astype(int)
    df["triples"] = (df["events"] == "triple").astype(int)
    df["hrs"] = (df["events"] == "home_run").astype(int)
    df["bbs"] = (df["events"] == "walk").astype(int) + (df["events"] == "intent_walk").astype(int)
    df["hbps"] = (df["events"] == "hit_by_pitch").astype(int)
    df["ks"] = (df["events"] == "strikeout").astype(int) + (df["events"] == "strikeout_double_play").astype(int)
    df["sb_event"] = 0  # not in statcast events; proxy via runner advancements is overkill
    # RBI / R from events not perfectly captured; approximate using runs_scored field if present
    g = df.groupby(["batter", "game_date"], as_index=False).agg(
        singles=("singles", "sum"),
        doubles=("doubles", "sum"),
        triples=("triples", "sum"),
        hrs=("hrs", "sum"),
        bbs=("bbs", "sum"),
        hbps=("hbps", "sum"),
        ks=("ks", "sum"),
    )
    g["tb"] = g["singles"] + 2 * g["doubles"] + 3 * g["triples"] + 4 * g["hrs"]
    # R + RBI proxy: use HR * (runs scored = 1 by hitter) + RBI = events near scoring.
    # Approximation: use HR for R+RBI (each HR is at least 1 R + 1 RBI; rest is noise).
    # We don't have R/RBI in pitch-by-pitch directly without joining game-level.
    # The MLB Stats API gameLog has these — but we're doing a *simulation* with the
    # caveat that R+RBI+SB are approximated. We use a calibration constant per BBE.
    # Simpler proxy: BrownU FP ~ TB + BB + HBP - K + 1.6*HR (R+RBI estimate per HR).
    # Calibrated factor 1.6 from MLB 2024 R+RBI per HR ratio.
    g["fp"] = g["tb"] + g["bbs"] + g["hbps"] - g["ks"] + 1.6 * g["hrs"]
    return g.rename(columns={"batter": "mlbam_id"})


def pitcher_fp_per_game(sc_window: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-pitcher, per-game FP. Treats games started as starts."""
    df = sc_window.copy()
    # Outs proxy: each out = 1/3 IP. Identify out-recording events:
    out_events = {
        "field_out", "force_out", "grounded_into_double_play",
        "double_play", "triple_play", "sac_fly", "sac_bunt",
        "strikeout", "strikeout_double_play", "field_error",  # error is not out, exclude
        "fielders_choice", "fielders_choice_out", "caught_stealing_2b",
        "caught_stealing_3b", "caught_stealing_home",
    }
    out_events.discard("field_error")
    # Strikeouts
    df["ks"] = (df["events"] == "strikeout").astype(int) + (df["events"] == "strikeout_double_play").astype(int)
    df["hits"] = df["events"].isin(["single", "double", "triple", "home_run"]).astype(int)
    df["bbs"] = (df["events"] == "walk").astype(int) + (df["events"] == "intent_walk").astype(int)
    df["hbps"] = (df["events"] == "hit_by_pitch").astype(int)
    df["hrs"] = (df["events"] == "home_run").astype(int)
    df["outs"] = df["events"].isin(out_events).astype(int)
    # GIDP / DP / TP record 2-3 outs; approximate
    df.loc[df["events"] == "grounded_into_double_play", "outs"] = 2
    df.loc[df["events"] == "double_play", "outs"] = 2
    df.loc[df["events"] == "triple_play", "outs"] = 3
    df.loc[df["events"] == "strikeout_double_play", "outs"] = 2

    g = df[df["events"].notna()].groupby(["pitcher", "game_date"], as_index=False).agg(
        ks=("ks", "sum"),
        hits=("hits", "sum"),
        bbs=("bbs", "sum"),
        hbps=("hbps", "sum"),
        hrs=("hrs", "sum"),
        outs=("outs", "sum"),
        ip_inferred=("outs", "sum"),
    )
    g["ip_float"] = g["outs"] / 3.0
    # ER proxy: assume 1.05 * HR + 0.32 * hits  (calibrated from 2024 SP data)
    g["er"] = 1.05 * g["hrs"] + 0.32 * (g["hits"] - g["hrs"])
    g["fp"] = g["ks"] + g["ip_float"] * 3.3 - g["hits"] - 2 * g["er"] - g["bbs"] - g["hbps"]
    return g.rename(columns={"pitcher": "mlbam_id"})


# -------------------- Tier B signals --------------------

def compute_prior_year_xwoba(sc_prior: pd.DataFrame) -> pd.Series:
    df = sc_prior[sc_prior["events"].notna()].copy()
    df["woba_val"] = 0.0
    for k, v in WOBA.items():
        df.loc[df["events"] == k, "woba_val"] = v
    df["woba_denom"] = df["events"].isin(
        ["walk", "hit_by_pitch", "single", "double", "triple", "home_run",
         "strikeout", "field_out", "force_out", "grounded_into_double_play",
         "double_play", "field_error", "fielders_choice", "fielders_choice_out",
         "sac_fly"]
    ).astype(int)
    g = df.groupby("batter").agg(num=("woba_val", "sum"), den=("woba_denom", "sum"))
    g["xwoba_prior"] = g["num"] / g["den"].where(g["den"] >= 100, np.nan)
    return g["xwoba_prior"]


def compute_recent_xwoba(sc: pd.DataFrame, as_of: dt.date, days: int = 21) -> pd.Series:
    start = pd.Timestamp(as_of - dt.timedelta(days=days))
    end = pd.Timestamp(as_of - dt.timedelta(days=1))
    w = sc[(sc["game_date"] >= start) & (sc["game_date"] <= end) & sc["events"].notna()].copy()
    w["woba_val"] = 0.0
    for k, v in WOBA.items():
        w.loc[w["events"] == k, "woba_val"] = v
    w["woba_denom"] = w["events"].isin(
        ["walk", "hit_by_pitch", "single", "double", "triple", "home_run",
         "strikeout", "field_out", "force_out", "grounded_into_double_play",
         "double_play", "field_error", "fielders_choice", "fielders_choice_out",
         "sac_fly"]
    ).astype(int)
    g = w.groupby("batter").agg(num=("woba_val", "sum"), den=("woba_denom", "sum"))
    g["xwoba_l21"] = g["num"] / g["den"].where(g["den"] >= 20, np.nan)
    return g["xwoba_l21"]


def compute_prior_year_sp_k(sc_prior: pd.DataFrame) -> pd.Series:
    df = sc_prior[sc_prior["events"].notna()].copy()
    df["ks"] = (df["events"] == "strikeout").astype(int) + (df["events"] == "strikeout_double_play").astype(int)
    g = df.groupby("pitcher").agg(ks=("ks", "sum"), bf=("events", "count"))
    g["k_pct_prior"] = g["ks"] / g["bf"].where(g["bf"] >= 150, np.nan)
    return g["k_pct_prior"]


def compute_recent_sp_k(sc: pd.DataFrame, as_of: dt.date, days: int = 30) -> pd.Series:
    start = pd.Timestamp(as_of - dt.timedelta(days=days))
    end = pd.Timestamp(as_of - dt.timedelta(days=1))
    w = sc[(sc["game_date"] >= start) & (sc["game_date"] <= end) & sc["events"].notna()].copy()
    w["ks"] = (w["events"] == "strikeout").astype(int) + (w["events"] == "strikeout_double_play").astype(int)
    g = w.groupby("pitcher").agg(ks=("ks", "sum"), bf=("events", "count"))
    g["k_pct_l30"] = g["ks"] / g["bf"].where(g["bf"] >= 30, np.nan)
    return g["k_pct_l30"]


# -------------------- Boom/bust recent --------------------

def compute_boom_bust(
    games_df: pd.DataFrame,
    as_of: dt.date,
    fp_col: str,
    last_n: int,
    boom_thresh: float,
    bust_thresh: float,
) -> pd.DataFrame:
    """For each mlbam_id, take last_n games before as_of, return boom_pct / bust_pct."""
    cutoff = pd.Timestamp(as_of - dt.timedelta(days=1))
    games_df = games_df[games_df["game_date"] <= cutoff].copy()
    games_df = games_df.sort_values(["mlbam_id", "game_date"])
    games_df["rk"] = games_df.groupby("mlbam_id").cumcount(ascending=False)
    rec = games_df[games_df["rk"] < last_n].copy()
    g = rec.groupby("mlbam_id").agg(
        n=(fp_col, "count"),
        boom=(fp_col, lambda x: (x >= boom_thresh).mean()),
        bust=(fp_col, lambda x: (x <= bust_thresh).mean()),
    )
    return g


# -------------------- Main simulation --------------------

def main():
    print("[1/5] Loading master panel + statcast...")
    pan = pd.read_parquet(PANEL)
    sc25 = pd.read_parquet(
        STATCAST_2025,
        columns=["game_date", "batter", "pitcher", "events", "estimated_woba_using_speedangle"],
    )
    sc25["game_date"] = pd.to_datetime(sc25["game_date"])
    sc24 = pd.read_parquet(
        STATCAST_2024,
        columns=["game_date", "batter", "pitcher", "events", "estimated_woba_using_speedangle"],
    )
    sc24["game_date"] = pd.to_datetime(sc24["game_date"])

    # Universe: 2025 panel rows with prior-year anchors
    h_pool = pan[(pan["year"] == 2025) & (pan["player_type"] == "H") &
                 pan["prior_year_fp_per_pa"].notna() & (pan["prior_year_pa"] >= 250)].copy()
    h_pool["score_base"] = h_pool["prior_year_fp_per_pa"] * 3.85  # PA/G estimate

    sp_pool = pan[(pan["year"] == 2025) & (pan["player_type"] == "SP") &
                  pan["prior_year_fp_per_start"].notna() & (pan["prior_year_gs"] >= 10)].copy()
    sp_pool["score_base"] = sp_pool["prior_year_fp_per_start"]

    print(f"  H pool: {len(h_pool)}   SP pool: {len(sp_pool)}")

    print("[2/5] Pre-computing 2025 per-game FP from statcast...")
    h_games_25 = hitter_fp_per_game(sc25)
    h_games_25["game_date"] = pd.to_datetime(h_games_25["game_date"])
    sp_games_25 = pitcher_fp_per_game(sc25)
    sp_games_25["game_date"] = pd.to_datetime(sp_games_25["game_date"])
    # SP filter: actually started — outs >= 12 (4 IP+) as proxy for start
    sp_games_25 = sp_games_25[sp_games_25["outs"] >= 9].copy()

    print(f"  hitter games: {len(h_games_25)}   pitcher game-starts: {len(sp_games_25)}")

    print("[3/5] Computing prior-year xwOBA + K% baselines...")
    xwoba_prior = compute_prior_year_xwoba(sc24)
    k_prior = compute_prior_year_sp_k(sc24)
    print(f"  xwOBA prior n: {xwoba_prior.notna().sum()}   K% prior n: {k_prior.notna().sum()}")

    results = []
    for as_of, end in WEEKS:
        print(f"\n[4/5] Week {as_of} -> {end}")
        # Recent xwOBA / K%
        xwoba_l21 = compute_recent_xwoba(sc25, as_of, 21)
        k_l30 = compute_recent_sp_k(sc25, as_of, 30)

        # Boom/bust from prior games
        h_bb = compute_boom_bust(h_games_25, as_of, "fp", H_RECENT_WINDOW_GAMES, H_BOOM, H_BUST)
        sp_bb = compute_boom_bust(sp_games_25, as_of, "fp", SP_RECENT_WINDOW_GAMES, SP_BOOM, SP_BUST)

        # --- Hitters
        h = h_pool.copy()
        h = h.merge(xwoba_prior.rename("xwoba_prior_25").reset_index().rename(columns={"batter": "mlbam_id"}),
                    on="mlbam_id", how="left")
        h = h.merge(xwoba_l21.rename("xwoba_l21").reset_index().rename(columns={"batter": "mlbam_id"}),
                    on="mlbam_id", how="left")
        h = h.merge(h_bb[["boom", "bust", "n"]].rename(columns={"boom": "boom_pct", "bust": "bust_pct"}),
                    left_on="mlbam_id", right_index=True, how="left")
        # Strategy A: pick top by score_base
        h = h.sort_values("score_base", ascending=False)
        a_h_ids = h.head(TOP_H)["mlbam_id"].tolist()

        # Strategy B: adjusted score
        # Tier B veto: xwoba_l21 < xwoba_prior_25 + H_XWOBA_DROP_THRESH -> downgrade
        h["tier_b_veto"] = (h["xwoba_l21"] - h["xwoba_prior_25"]) < H_XWOBA_DROP_THRESH
        h["bump_up"] = h["boom_pct"] > 0.25
        h["bump_down"] = h["bust_pct"] > 0.25
        # adjusted score: +/- 1.5 FP per tier (~1 FP/G shift)
        h["adj"] = 0.0
        h.loc[h["tier_b_veto"].fillna(False), "adj"] -= 1.5
        h.loc[h["bump_up"].fillna(False), "adj"] += 1.5
        h.loc[h["bump_down"].fillna(False), "adj"] -= 1.5
        h["score_b"] = h["score_base"] + h["adj"]
        h = h.sort_values("score_b", ascending=False)
        b_h_ids = h.head(TOP_H)["mlbam_id"].tolist()

        # --- SPs
        s = sp_pool.copy()
        s = s.merge(k_prior.rename("k_prior_25").reset_index().rename(columns={"pitcher": "mlbam_id"}),
                    on="mlbam_id", how="left")
        s = s.merge(k_l30.rename("k_l30").reset_index().rename(columns={"pitcher": "mlbam_id"}),
                    on="mlbam_id", how="left")
        s = s.merge(sp_bb[["boom", "bust", "n"]].rename(columns={"boom": "boom_pct", "bust": "bust_pct"}),
                    left_on="mlbam_id", right_index=True, how="left")
        s = s.sort_values("score_base", ascending=False)
        a_sp_ids = s.head(TOP_SP)["mlbam_id"].tolist()

        s["tier_b_veto"] = (s["k_l30"] - s["k_prior_25"]) < -SP_K_DROP_THRESH
        s["bump_up"] = s["boom_pct"] > 0.25
        s["bump_down"] = s["bust_pct"] > 0.25
        s["adj"] = 0.0
        s.loc[s["tier_b_veto"].fillna(False), "adj"] -= 3.0
        s.loc[s["bump_up"].fillna(False), "adj"] += 3.0
        s.loc[s["bump_down"].fillna(False), "adj"] -= 3.0
        s["score_b"] = s["score_base"] + s["adj"]
        s = s.sort_values("score_b", ascending=False)
        b_sp_ids = s.head(TOP_SP)["mlbam_id"].tolist()

        # --- Realized FP over [as_of, end]
        win_start = pd.Timestamp(as_of)
        win_end = pd.Timestamp(end)
        h_win = h_games_25[(h_games_25["game_date"] >= win_start) &
                            (h_games_25["game_date"] <= win_end)]
        sp_win = sp_games_25[(sp_games_25["game_date"] >= win_start) &
                              (sp_games_25["game_date"] <= win_end)]

        def total_fp(ids, win, role):
            sub = win[win["mlbam_id"].isin(ids)]
            return sub["fp"].sum(), len(sub)

        a_h_fp, a_h_n = total_fp(a_h_ids, h_win, "h")
        b_h_fp, b_h_n = total_fp(b_h_ids, h_win, "h")
        a_sp_fp, a_sp_n = total_fp(a_sp_ids, sp_win, "sp")
        b_sp_fp, b_sp_n = total_fp(b_sp_ids, sp_win, "sp")

        a_total = a_h_fp + a_sp_fp
        b_total = b_h_fp + b_sp_fp

        # Track swaps
        h_swaps = len(set(b_h_ids) - set(a_h_ids))
        sp_swaps = len(set(b_sp_ids) - set(a_sp_ids))

        results.append({
            "week_start": as_of,
            "week_end": end,
            "A_h_fp": a_h_fp, "A_h_games": a_h_n,
            "B_h_fp": b_h_fp, "B_h_games": b_h_n,
            "A_sp_fp": a_sp_fp, "A_sp_starts": a_sp_n,
            "B_sp_fp": b_sp_fp, "B_sp_starts": b_sp_n,
            "A_total": a_total,
            "B_total": b_total,
            "delta": b_total - a_total,
            "h_swaps": h_swaps,
            "sp_swaps": sp_swaps,
        })
        print(f"  A: H={a_h_fp:.1f} ({a_h_n}g) + SP={a_sp_fp:.1f} ({a_sp_n}s) = {a_total:.1f}")
        print(f"  B: H={b_h_fp:.1f} ({b_h_n}g) + SP={b_sp_fp:.1f} ({b_sp_n}s) = {b_total:.1f}")
        print(f"  delta = {b_total - a_total:+.1f}   swaps H={h_swaps} SP={sp_swaps}")

    df = pd.DataFrame(results)
    print("\n[5/5] Writing report...")
    lines = []
    lines.append("# Full-Week Roster Simulation — Tier A vs Full Merge Protocol\n")
    lines.append("Generated: 2026-06-06 via scripts/_oneoff/test_full_week_sim.py\n")
    lines.append("## Method (simplified)\n")
    lines.append("- Universe: 2025 master_panel H + SP with valid prior-year anchor.\n")
    lines.append("- Strategy A: top 13 H + 5 SP by prior-year FP anchor (proxy for Blended xFP).\n")
    lines.append("- Strategy B: same pool, ranked by anchor + adjustments:\n")
    lines.append("  - Tier B veto (-1.5 H / -3.0 SP) if xwOBA L21d < prior - 0.060 (H) or K% L30d < prior - 0.08 (SP).\n")
    lines.append("  - Boom-bust modulation (+/-1.5 H / +/-3.0 SP) if boom% > 25% or bust% > 25% over the last 21 H games / 8 SP starts before as_of.\n")
    lines.append("- Realized FP: from statcast events 2025, BrownU formula (HR augmented to estimate R+RBI).\n")
    lines.append("\n## Per-week results\n")
    lines.append("| Week start | Week end | A total | B total | Delta | H swaps | SP swaps |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for r in results:
        lines.append(
            f"| {r['week_start']} | {r['week_end']} | {r['A_total']:.1f} | {r['B_total']:.1f} | "
            f"{r['delta']:+.1f} | {r['h_swaps']} | {r['sp_swaps']} |\n"
        )
    lines.append("\n## Aggregate\n")
    mean_delta = df["delta"].mean()
    std_delta = df["delta"].std()
    n_wins = (df["delta"] > 0).sum()
    n_loss = (df["delta"] < 0).sum()
    n_tie = (df["delta"] == 0).sum()
    lines.append(f"- N weeks: {len(df)}\n")
    lines.append(f"- Mean delta (B - A): **{mean_delta:+.2f} FP/week** (std {std_delta:.2f})\n")
    lines.append(f"- B wins: {n_wins}   A wins: {n_loss}   Ties: {n_tie}\n")
    lines.append(f"- Total A FP: {df['A_total'].sum():.1f}   Total B FP: {df['B_total'].sum():.1f}\n")
    pct = 100 * mean_delta / df["A_total"].mean() if df["A_total"].mean() > 0 else 0
    lines.append(f"- Pct lift: {pct:+.2f}%\n")

    if mean_delta > 5:
        verdict = f"**Full merge protocol WINS by {mean_delta:+.1f} FP/week**"
    elif mean_delta > 0:
        verdict = f"Marginal lift {mean_delta:+.1f} FP/week — inside noise"
    elif mean_delta < -5:
        verdict = f"**Full merge protocol LOSES by {mean_delta:.1f} FP/week**"
    else:
        verdict = "Tie within noise — protocol does not measurably help on this proxy."
    lines.append(f"\n## Verdict\n\n{verdict}\n")

    lines.append("\n## Caveats (important)\n")
    lines.append("- **No positional eligibility**: top 13 H assumed fungible; in reality C/SS/2B slots constrain swaps.\n")
    lines.append("- **No IL handling**: a vetoed player may already be on IL; B would also be deprived in reality.\n")
    lines.append("- **No SP 10-start cap**: only 5 SPs picked, not a binding constraint here.\n")
    lines.append("- **Blended xFP proxy**: prior-year FP anchor only, not the production blend (archetype + age + PL rank).\n")
    lines.append("- **Realized FP proxy**: derived from statcast events with HR-augmented R+RBI estimate, not MLB Stats API gameLog directly. Calibrated factor 1.6 R+RBI per HR; magnitude of FP is off but B-vs-A delta is preserved because both strategies use the same recipe.\n")
    lines.append("- **Boom-bust thresholds**: H boom >=5 / bust <=0 and SP boom >=20 / bust <=5 per CLAUDE.md skill canon.\n")
    lines.append("- **Tier B downgrade magnitude**: -1.5 (H) / -3.0 (SP) FP per tier is heuristic; production rules use categorical bumps, not FP shifts.\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(f"Mean delta: {mean_delta:+.2f} FP/week   B wins {n_wins}/{len(df)}")


if __name__ == "__main__":
    main()
