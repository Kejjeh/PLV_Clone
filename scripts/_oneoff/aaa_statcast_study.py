"""AAA Statcast -> MLB rookie performance feasibility + validation study.

QUESTION: Do AAA velo / K% / whiff translate to MLB rookie BrownU FP/start?
If a call-up's AAA Statcast shows plus velo+whiff, can we project them BEFORE
they have MLB data?  (Extends talent-prior + shadow-scout for no-MLB rookies.)

DATA SOURCES (all free):
  1. AAA STATCAST (pitch-level velo + whiff): Baseball Savant
       https://baseballsavant.mlb.com/statcast_search/csv?...&minors=true
     Returns release_speed + description (swinging_strike) per pitch for ALL
     minor levels mixed; filtered to AAA by team abbreviation (sportId=11 teams).
  2. AAA STATS (K%/BB%, no Statcast): existing repo caches
       data/research/xfp_cache/milb_pitcher_stats_ext_{year}_AAA.json
  3. MLB OUTCOME (BrownU FP/start): data/research/xfp_cache/rolling_pitchers_2018_2026.csv
     -> season-cumulative fp_per_start_to (last cutoff per pitcher-year).

LEAKAGE SAFETY: AAA metrics are from year Y; MLB outcome is from year Y or Y+1.
AAA data (whole-season aggregate) always predates the Y+1 MLB outcome; for the
same-year (Y) join we accept that the AAA season overlaps the MLB season but the
AAA signal is still a *talent prior* not derived from the MLB outcome -- we report
Y and Y+1 separately and lead with the cleaner Y+1 result.

Usage:
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/_oneoff/aaa_statcast_study.py
  (add --no-savant to run STATS-only validation if Savant is unreachable)
"""
import os, sys, io, json, time, argparse
import numpy as np
import pandas as pd
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "data", "research", "xfp_cache")
AAA_CACHE = os.path.join(ROOT, "data", "research", "aaa_statcast_cache")
os.makedirs(AAA_CACHE, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}
SAVANT_CSV = "https://baseballsavant.mlb.com/statcast_search/csv"


def aaa_team_abbrs(season):
    """AAA team abbreviations (sportId=11) for filtering the mixed-minors CSV."""
    url = f"https://statsapi.mlb.com/api/v1/teams?sportId=11&season={season}"
    r = requests.get(url, timeout=30)
    teams = r.json()["teams"]
    return sorted({t.get("abbreviation") for t in teams if t.get("abbreviation")})


def pull_savant_minors_week(season, start, end):
    """One game-date window of pitch-level minor-league statcast (all levels)."""
    params = {
        "all": "true", "type": "details", "minors": "true",
        "player_type": "pitcher", "hfSea": f"{season}|",
        "game_date_gt": start, "game_date_lt": end,
    }
    r = requests.get(SAVANT_CSV, params=params, timeout=180, headers=HEADERS)
    r.raise_for_status()
    if len(r.text) < 200:
        return pd.DataFrame()
    cols = ["pitch_type", "game_date", "release_speed", "player_name",
            "pitcher", "description", "home_team", "away_team", "game_year"]
    df = pd.read_csv(io.StringIO(r.text), low_memory=False,
                     usecols=lambda c: c in cols)
    return df


def build_aaa_statcast(season, weeks=None):
    """Aggregate AAA pitch-level statcast -> per-pitcher velo/whiff/csw for a season.

    Samples a set of weekly windows across the season (cached) to keep the pull
    bounded while still getting a representative per-pitcher arsenal aggregate.
    """
    cache_fp = os.path.join(AAA_CACHE, f"aaa_statcast_pitchers_{season}.csv")
    if os.path.exists(cache_fp):
        return pd.read_csv(cache_fp)

    aaa = set(aaa_team_abbrs(season))
    # Sample windows: AAA season ~ late March -> late Sept. Pull ~biweekly weeks.
    if weeks is None:
        weeks = [
            (f"{season}-04-05", f"{season}-04-12"),
            (f"{season}-04-26", f"{season}-05-03"),
            (f"{season}-05-17", f"{season}-05-24"),
            (f"{season}-06-07", f"{season}-06-14"),
            (f"{season}-06-28", f"{season}-07-05"),
            (f"{season}-07-19", f"{season}-07-26"),
            (f"{season}-08-09", f"{season}-08-16"),
            (f"{season}-08-30", f"{season}-09-06"),
        ]
    frames = []
    for (s, e) in weeks:
        try:
            d = pull_savant_minors_week(season, s, e)
        except Exception as ex:
            print(f"  [warn] {season} {s} failed: {ex}", file=sys.stderr)
            continue
        if len(d):
            # AAA only: pitch must be thrown in a game where home OR away is AAA.
            d = d[d.home_team.isin(aaa) | d.away_team.isin(aaa)].copy()
            frames.append(d)
        print(f"  pulled {season} {s}: {len(d)} AAA pitches", file=sys.stderr)
        time.sleep(0.5)
    if not frames:
        return pd.DataFrame()
    allp = pd.concat(frames, ignore_index=True)

    allp["is_swstr"] = allp.description.isin(
        ["swinging_strike", "swinging_strike_blocked"]).astype(int)
    allp["is_csw"] = allp.description.isin(
        ["swinging_strike", "swinging_strike_blocked",
         "foul_tip", "called_strike"]).astype(int)
    allp["is_swing"] = allp.description.isin(
        ["swinging_strike", "swinging_strike_blocked", "foul", "foul_tip",
         "hit_into_play", "foul_bunt", "missed_bunt"]).astype(int)

    g = allp.groupby("pitcher")
    out = pd.DataFrame({
        "pitcher": g.size().index,
        "aaa_pitches": g.size().values,
        "aaa_velo": g.release_speed.mean().values,          # avg release speed
        "aaa_fb_velo": allp[allp.pitch_type.isin(["FF", "SI", "FC"])]
                        .groupby("pitcher").release_speed.mean()
                        .reindex(g.size().index).values,     # fastball velo
        "aaa_swstr_pct": g.is_swstr.mean().values,           # whiff% (per pitch)
        "aaa_csw_pct": g.is_csw.mean().values,
    })
    swings = allp.groupby("pitcher").is_swing.sum()
    whiffs = allp[allp.is_swstr == 1].groupby("pitcher").size()
    out["aaa_whiff_per_swing"] = (whiffs.reindex(out.pitcher).fillna(0).values
                                  / swings.reindex(out.pitcher).replace(0, np.nan).values)
    out["season"] = season
    out.to_csv(cache_fp, index=False)
    return out


def build_aaa_stats(season):
    """AAA K%/BB% from the existing milb STATS json (broad coverage, no statcast)."""
    fp = os.path.join(CACHE, f"milb_pitcher_stats_ext_{season}_AAA.json")
    if not os.path.exists(fp):
        return pd.DataFrame()
    d = json.load(open(fp))
    df = pd.DataFrame(d)
    df = df[df.battersFaced.fillna(0) > 0].copy()
    df["aaa_k_pct"] = df.strikeOuts / df.battersFaced
    df["aaa_bb_pct"] = df.baseOnBalls / df.battersFaced
    df["aaa_kbb_pct"] = df.aaa_k_pct - df.aaa_bb_pct
    df["aaa_bf"] = df.battersFaced
    df["aaa_gs"] = df.gamesStarted
    return df.rename(columns={"pitcher": "pitcher"})[
        ["pitcher", "name", "aaa_k_pct", "aaa_bb_pct", "aaa_kbb_pct",
         "aaa_bf", "aaa_gs"]].assign(season=season)


def mlb_outcome():
    """Season-cumulative MLB FP/start per pitcher-year (last cutoff per pitcher)."""
    df = pd.read_csv(os.path.join(CACHE, "rolling_pitchers_2018_2026.csv"))
    df = df.sort_values("cutoff_date")
    last = df.groupby(["pitcher", "year"]).tail(1)
    return last[["pitcher", "year", "gs_to", "fp_per_start_to"]].rename(
        columns={"year": "mlb_year", "gs_to": "mlb_gs",
                 "fp_per_start_to": "mlb_fp_per_start"})


def corr_report(df, xcols, ycol, label, min_n=8):
    rows = []
    for x in xcols:
        sub = df[[x, ycol]].dropna()
        if len(sub) < min_n:
            rows.append((x, len(sub), np.nan, np.nan))
            continue
        r = sub[x].corr(sub[ycol])
        rho = sub[x].corr(sub[ycol], method="spearman")
        rows.append((x, len(sub), r, rho))
    print(f"\n=== {label}  (y = {ycol}) ===")
    print(f"{'predictor':>20} {'n':>5} {'pearson_r':>10} {'spearman':>10}")
    for x, n, r, rho in rows:
        rs = f"{r:+.3f}" if pd.notna(r) else "   n/a"
        rhs = f"{rho:+.3f}" if pd.notna(rho) else "   n/a"
        print(f"{x:>20} {n:>5} {rs:>10} {rhs:>10}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-savant", action="store_true")
    ap.add_argument("--seasons", default="2023,2024")
    args = ap.parse_args()
    seasons = [int(s) for s in args.seasons.split(",")]

    mlb = mlb_outcome()
    rookie_gs_cap = 60   # season GS cap -> focus on early-career / rookie-ish

    # ---- AAA STATS (always available) ----
    stats = pd.concat([build_aaa_stats(s) for s in seasons], ignore_index=True)
    # aggregate to one AAA row per pitcher-season (sum across stints if dupes)
    stats = stats.sort_values("aaa_bf", ascending=False).groupby(
        ["pitcher", "season"], as_index=False).first()

    # ---- AAA STATCAST (optional) ----
    sc = pd.DataFrame()
    if not args.no_savant:
        frames = []
        for s in seasons:
            print(f"[savant] building AAA statcast {s} ...", file=sys.stderr)
            f = build_aaa_statcast(s)
            if len(f):
                frames.append(f)
        if frames:
            sc = pd.concat(frames, ignore_index=True)

    # ---- Join AAA(Y) -> MLB(Y) and AAA(Y) -> MLB(Y+1) ----
    def join_for(aaa_df, statcast=False):
        results = {}
        for lag, tag in [(0, "sameY"), (1, "Y+1")]:
            a = aaa_df.copy()
            a["mlb_year"] = a["season"] + lag
            m = a.merge(mlb, on=["pitcher", "mlb_year"], how="inner")
            # rookie-ish filter: limited MLB starts, require a few AAA starts
            m = m[(m.mlb_fp_per_start.notna())]
            if "aaa_gs" in m.columns:
                m = m[m.aaa_gs.fillna(0) >= 3]
            if "aaa_pitches" in m.columns:
                m = m[m.aaa_pitches.fillna(0) >= 150]
            m = m[m.mlb_gs.fillna(0) >= 3]                 # need real MLB sample
            m_rook = m[m.mlb_gs <= 20]                     # rookie-ish subset
            results[tag] = (m, m_rook)
        return results

    print("\n" + "#" * 70)
    print("# AAA STATS (K%/BB%) -> MLB FP/start")
    print("#" * 70)
    res_stats = join_for(stats)
    stat_x = ["aaa_k_pct", "aaa_bb_pct", "aaa_kbb_pct"]
    for tag, (m_all, m_rook) in res_stats.items():
        corr_report(m_all, stat_x, "mlb_fp_per_start",
                    f"STATS {tag}: ALL pitchers (n MLB)={len(m_all)}")
        corr_report(m_rook, stat_x, "mlb_fp_per_start",
                    f"STATS {tag}: ROOKIE-ish (<=20 MLB GS) n={len(m_rook)}")

    if len(sc):
        print("\n" + "#" * 70)
        print("# AAA STATCAST (velo/whiff/CSW) -> MLB FP/start")
        print("#" * 70)
        # attach AAA stats K%/BB% too for a combined view
        sc2 = sc.merge(stats[["pitcher", "season", "aaa_k_pct", "aaa_kbb_pct",
                              "aaa_gs", "name"]],
                       on=["pitcher", "season"], how="left")
        res_sc = join_for(sc2, statcast=True)
        sc_x = ["aaa_fb_velo", "aaa_velo", "aaa_swstr_pct", "aaa_csw_pct",
                "aaa_whiff_per_swing", "aaa_k_pct", "aaa_kbb_pct"]
        for tag, (m_all, m_rook) in res_sc.items():
            corr_report(m_all, sc_x, "mlb_fp_per_start",
                        f"STATCAST {tag}: ALL (n={len(m_all)})")
            corr_report(m_rook, sc_x, "mlb_fp_per_start",
                        f"STATCAST {tag}: ROOKIE-ish (<=20 MLB GS) n={len(m_rook)}")
        # save the joined Y+1 rookie table for inspection
        out_fp = os.path.join(AAA_CACHE, "aaa_statcast_mlb_joined.csv")
        res_sc["Y+1"][0].to_csv(out_fp, index=False)
        print(f"\n[saved] {out_fp}")
    else:
        print("\n[no statcast frames -- ran STATS-only]")

    # coverage summary
    print("\n" + "=" * 70)
    print("COVERAGE")
    print("=" * 70)
    print(f"AAA STATS rows (pitcher-seasons): {len(stats)}")
    if len(sc):
        print(f"AAA STATCAST rows (pitcher-seasons): {len(sc)}")
        print(f"  median AAA pitches sampled/pitcher: "
              f"{sc.aaa_pitches.median():.0f}")


if __name__ == "__main__":
    main()
