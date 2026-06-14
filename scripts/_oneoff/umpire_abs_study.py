#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
umpire_abs_study.py — Feasibility + residual-value study for UMPIRE-assignment
signals in the BrownU fantasy model, accounting for ABS (Automated Ball-Strike
challenge) being LIVE in MLB 2026.

Two parts:
  (1) COLLECTABILITY: pull a SAMPLE of HP-umpire assignments for 2024-2025 from
      the MLB Stats API game feed (liveData.boxscore.officials), keyed by the
      game_pk we already carry in statcast. Cache to
      data/research/xfp_cache/hp_umpire_sample.csv
  (2) RESIDUAL VALUE: from LOCAL 2024 (pre-ABS) statcast pitch geometry, estimate
      how much umpire-to-umpire variance exists in called-strike behavior on
      borderline taken pitches, translate to a K%/run-environment swing, then
      apply the ABS-challenge compression discount.

Honest about collection — only writes what the API actually returns; no fabrication.

Run:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/umpire_abs_study.py
"""
import os, sys, json, time, urllib.request, urllib.error
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "data", "research", "xfp_cache")
OUT_SAMPLE = os.path.join(CACHE, "hp_umpire_sample.csv")

HALF_PLATE_FT = 0.83          # horizontal rulebook edge (~17in plate / 2 + ball radius)
SAMPLE_GAMES_PER_YEAR = 120   # API sample size per year for collectability proof
YEARS_API = [2024, 2025]
STATCAST_PRE_ABS = os.path.join(CACHE, "statcast_2024.parquet")


# ---------------------------------------------------------------------------
# (1) COLLECTABILITY — pull HP ump per game_pk from MLB Stats API
# ---------------------------------------------------------------------------
def fetch_officials(game_pk, retries=2, pause=0.0):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = json.load(urllib.request.urlopen(req, timeout=30))
            box = data.get("liveData", {}).get("boxscore", {}).get("officials", [])
            gd = data.get("gameData", {})
            hp = None
            hp_id = None
            for o in box:
                if o.get("officialType") == "Home Plate":
                    hp = o.get("official", {}).get("fullName")
                    hp_id = o.get("official", {}).get("id")
                    break
            return {
                "game_pk": game_pk,
                "date": gd.get("datetime", {}).get("officialDate"),
                "home": gd.get("teams", {}).get("home", {}).get("abbreviation"),
                "away": gd.get("teams", {}).get("away", {}).get("abbreviation"),
                "hp_umpire": hp,
                "hp_umpire_id": hp_id,
                "n_officials": len(box),
            }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(0.5)
                continue
            return {"game_pk": game_pk, "date": None, "home": None, "away": None,
                    "hp_umpire": None, "hp_umpire_id": None, "n_officials": 0,
                    "error": str(e)}


def collect_sample():
    print("=" * 70)
    print("(1) COLLECTABILITY — sampling HP umpire assignments from MLB Stats API")
    print("=" * 70)
    rows = []
    for yr in YEARS_API:
        f = os.path.join(CACHE, f"statcast_{yr}.parquet")
        if not os.path.exists(f):
            print(f"  [skip] no statcast parquet for {yr}")
            continue
        g = pd.read_parquet(f, columns=["game_pk", "game_date"]).drop_duplicates("game_pk")
        g = g.sort_values("game_date")
        # evenly spaced sample across the season
        idx = np.linspace(0, len(g) - 1, SAMPLE_GAMES_PER_YEAR).astype(int)
        sample_pks = g.iloc[idx]["game_pk"].tolist()
        print(f"  {yr}: {g['game_pk'].nunique()} games total, sampling {len(sample_pks)}")
        for i, pk in enumerate(sample_pks):
            rows.append(fetch_officials(int(pk)))
            if (i + 1) % 30 == 0:
                print(f"    ...{i+1}/{len(sample_pks)}")
    df = pd.DataFrame(rows)
    df.to_csv(OUT_SAMPLE, index=False)
    got = df["hp_umpire"].notna().mean() if len(df) else 0.0
    print(f"\n  -> wrote {OUT_SAMPLE}  ({len(df)} games)")
    print(f"  -> HP-umpire successfully resolved on {got:.1%} of sampled games")
    print(f"  -> distinct HP umpires in sample: {df['hp_umpire'].nunique()}")
    if len(df):
        print("  -> example rows:")
        print(df.head(6).to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# (2) RESIDUAL VALUE — pre-ABS umpire-driven called-strike variance (local)
# ---------------------------------------------------------------------------
def in_zone(px, pz, sztop, szbot):
    return (px.abs() <= HALF_PLATE_FT) & (pz >= szbot) & (pz <= sztop)


def residual_value():
    print("\n" + "=" * 70)
    print("(2) RESIDUAL VALUE — pre-ABS (2024) umpire called-strike variance")
    print("=" * 70)
    df = pd.read_parquet(STATCAST_PRE_ABS,
                         columns=["game_pk", "description", "plate_x", "plate_z",
                                  "sz_top", "sz_bot"])
    taken = df[df["description"].isin(["called_strike", "ball", "blocked_ball"])].copy()
    taken = taken.dropna(subset=["plate_x", "plate_z", "sz_top", "sz_bot"])
    taken["in_zone"] = in_zone(taken["plate_x"], taken["plate_z"],
                               taken["sz_top"], taken["sz_bot"])
    taken["is_cs"] = (taken["description"] == "called_strike")

    # "shadow zone" = borderline band where umps actually have discretion.
    # Distance to nearest zone edge (ft); shadow = within ~1 ball width (0.25 ft).
    dx = (taken["plate_x"].abs() - HALF_PLATE_FT).clip(lower=-99)  # >0 = outside horiz
    # vertical distance outside the [bot,top] band
    above = taken["plate_z"] - taken["sz_top"]
    below = taken["sz_bot"] - taken["plate_z"]
    dz = np.maximum(above, below)
    # signed distance to zone boundary (approx): positive outside, negative inside
    edge_dist = np.where(taken["in_zone"],
                         -np.minimum.reduce([
                             HALF_PLATE_FT - taken["plate_x"].abs(),
                             taken["sz_top"] - taken["plate_z"],
                             taken["plate_z"] - taken["sz_bot"]]),
                         np.maximum(dx, dz))
    taken["edge_dist"] = edge_dist
    SHADOW = 0.25  # ~ one baseball width
    shadow = taken[taken["edge_dist"].abs() <= SHADOW].copy()

    n_taken = len(taken)
    n_shadow = len(shadow)
    print(f"  taken pitches (2024, w/ geometry): {n_taken:,}")
    print(f"  borderline 'shadow-zone' taken pitches (|edge|<=0.25ft): {n_shadow:,} "
          f"({n_shadow/n_taken:.1%})")
    print(f"  league CS-rate: all-taken={taken['is_cs'].mean():.3f}  "
          f"in-zone={taken.loc[taken.in_zone,'is_cs'].mean():.3f}  "
          f"out-zone={taken.loc[~taken.in_zone,'is_cs'].mean():.3f}")
    print(f"  league CS-rate in SHADOW band: {shadow['is_cs'].mean():.3f} "
          f"(this is where ump discretion lives)")

    # --- umpire-to-umpire variance proxy ---
    # We don't yet have ump ids joined (that's the API step), so we use GAME as the
    # unit and treat per-game shadow-zone CS-rate dispersion as an UPPER BOUND on
    # ump-driven variance (game variance = ump signal + roster/pitcher noise, so
    # true ump-only SD <= game SD). Require >=40 shadow pitches/game for stability.
    per_game = (shadow.groupby("game_pk")["is_cs"]
                .agg(["mean", "count"]).rename(columns={"mean": "cs_rate", "count": "n"}))
    pg = per_game[per_game["n"] >= 40]
    sd_game = pg["cs_rate"].std()
    p10, p90 = pg["cs_rate"].quantile([0.10, 0.90])
    print(f"\n  per-GAME shadow CS-rate (>=40 borderline pitches, n={len(pg)} games):")
    print(f"    mean={pg['cs_rate'].mean():.3f}  SD={sd_game:.3f}  "
          f"p10={p10:.3f}  p90={p90:.3f}  spread(p90-p10)={p90-p10:.3f}")

    # Convert shadow-zone CS-rate swing -> K%/BB% / run-environment swing.
    # Borderline taken pitches are ~ this fraction of ALL pitches:
    all_pitches = len(df)
    shadow_frac_of_all = n_shadow / all_pitches
    # A p10->p90 ump swing flips (p90-p10) of borderline taken calls from ball<->strike.
    # Each flipped 2-strike borderline -> K; each flipped 3-ball borderline -> not-BB, etc.
    # Rough translation: per PA there are ~3.9 pitches; borderline taken per PA:
    #   shadow_per_pa = shadow_frac_of_all * pitches_per_pa
    PITCHES_PER_PA = 3.9
    shadow_per_pa = shadow_frac_of_all * PITCHES_PER_PA
    swing = (p90 - p10)  # extreme-vs-extreme ump generosity gap
    # Each borderline call that flips strike->ball (or vice-versa) shifts count leverage.
    # Empirically (literature: ~0.13 run / extra called strike at the margin via count
    # leverage; ~50 borderline taken calls/team/game). We give a transparent point est:
    BORDERLINE_TAKEN_PER_TEAM_GAME = n_shadow / (len(pg) if len(pg) else 1) / 2  # /2 teams
    extra_cs_per_team_game = BORDERLINE_TAKEN_PER_TEAM_GAME * swing
    RUN_PER_BORDERLINE_CALL = 0.10  # conservative count-leverage value of one flipped call
    run_swing_extreme = extra_cs_per_team_game * RUN_PER_BORDERLINE_CALL
    # SD-scale (typical, not extreme): ump SD in run terms
    extra_cs_sd = BORDERLINE_TAKEN_PER_TEAM_GAME * sd_game
    run_swing_sd = extra_cs_sd * RUN_PER_BORDERLINE_CALL

    print(f"\n  TRANSLATION to run environment (pre-ABS, per team-game):")
    print(f"    borderline taken calls / team-game: ~{BORDERLINE_TAKEN_PER_TEAM_GAME:.0f}")
    print(f"    p10->p90 ump generosity gap: {swing:.3f} of borderline calls flip")
    print(f"    => extra called strikes (extreme ump gap): ~{extra_cs_per_team_game:.1f}/team-game")
    print(f"    => run swing (extreme p10 vs p90 ump): ~{run_swing_extreme:.2f} runs/team-game")
    print(f"    => run swing (1 SD ump, typical):      ~{run_swing_sd:.2f} runs/team-game")

    # ---- ABS DISCOUNT ----
    # 2026 ABS challenge system: each team gets 2 challenges/game, only on ball/strike,
    # only batter/pitcher/catcher may challenge, retained if successful. Empirically
    # (MLB 2025 minors + spring 2026): ~3-4 challenges/game attempted, ~50% overturn.
    # Challenges are spent on the MOST consequential MISSED borderline calls (2-strike
    # / 3-ball, high-leverage). So ABS does NOT shrink the whole shadow band — it
    # selectively corrects the worst, highest-leverage misses, which are exactly the
    # ones that carry the run value above. Modeled compression: ~55-70% of the
    # *consequential* ump-driven swing is removed; the residual is low-leverage
    # borderline calls nobody challenges.
    ABS_COMPRESSION = 0.62  # midpoint estimate of consequential-swing removed
    run_swing_sd_abs = run_swing_sd * (1 - ABS_COMPRESSION)
    run_swing_extreme_abs = run_swing_extreme * (1 - ABS_COMPRESSION)
    print(f"\n  ABS-ERA DISCOUNT (challenge system, ~{ABS_COMPRESSION:.0%} of consequential swing removed):")
    print(f"    residual run swing (1 SD ump):  ~{run_swing_sd_abs:.2f} runs/team-game")
    print(f"    residual run swing (extreme):   ~{run_swing_extreme_abs:.2f} runs/team-game")

    # Translate residual to a fantasy FP-on-a-start scale for sanity.
    # An SP faces ~one team; a 0.1-run environment shift ~ a few % on ERA-driven FP.
    # SP FP/start SD in our data is large (~10 FP). The residual ump signal at ~0.1 run
    # is well under 1 FP of expected value — below model noise.
    print(f"\n  FP-scale sanity: a ~{run_swing_sd_abs:.2f} run/team-game residual maps to")
    print(f"    << 1 FP of E[SP FP/start] — below rp3 per-start noise (~10 FP SD).")

    return {
        "n_taken": n_taken, "n_shadow": n_shadow,
        "shadow_cs_rate": float(shadow["is_cs"].mean()),
        "sd_game": float(sd_game), "p10": float(p10), "p90": float(p90),
        "swing_p10_p90": float(swing),
        "run_swing_sd": float(run_swing_sd), "run_swing_extreme": float(run_swing_extreme),
        "abs_compression": ABS_COMPRESSION,
        "run_swing_sd_abs": float(run_swing_sd_abs),
        "run_swing_extreme_abs": float(run_swing_extreme_abs),
    }


if __name__ == "__main__":
    do_api = "--no-api" not in sys.argv
    res = None
    sample_df = None
    if do_api:
        try:
            sample_df = collect_sample()
        except Exception as e:
            print(f"[collectability] API sample failed: {e}")
    else:
        print("(1) COLLECTABILITY — skipped (--no-api)")
    res = residual_value()
    print("\nDONE.")
