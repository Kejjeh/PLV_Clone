"""pl_streamer_backtest — Nick Pollack's streamer ranks vs our rp3, graded on actuals.

LEAKAGE CONTROL is the whole point. Our rp3 projection is read from
player_projection_history.parquet at the LATEST snapshot <= the start date, so
the number is the one we would actually have had that morning. The daily
refresh builds snapshot D from games through D-1, so snapshot D is the correct
as-of read for a start on D. Using today's xfp_rp3_projections.csv instead
would let the model see the very starts it is being graded on.

Both sides are scored against the same target: BrownU FP for that start,
recomputed from the boxscore rather than trusted from any board.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from plv_clone.utils.name_match import resolve_pitcher_id  # noqa: E402
from backfill_pl_streamers import iso_date  # noqa: E402
# Name join key — OWNER: name_match.safe_name_key. A local copy WILL drift:
# 127 hand-rolled variants once printed an opponent-rostered player as a
# free agent because one did not collapse a curly apostrophe.
from plv_clone.utils.name_match import safe_name_key as norm  # noqa: E402

TIER_CANON = {
    "AUTO": "Auto-Start", "AUTO-START": "Auto-Start", "AUTOSTART": "Auto-Start",
    "PROBABLY": "Probably Start", "PROBABLY START": "Probably Start",
    "QUESTIONABLE": "Questionable", "QUESTIONABLE START": "Questionable",
    "DO NOT START": "Do Not Start", "DNS": "Do Not Start", "DO-NOT-START": "Do Not Start",
}
TIER_ORDER = ["Auto-Start", "Probably Start", "Questionable", "Do Not Start"]


def canon_tier(t):
    if not t:
        return None
    return TIER_CANON.get(str(t).upper().strip(), str(t).strip())





def load_pl_editions() -> pd.DataFrame:
    """Every cached streamer edition -> one row per (date, pitcher, rank, tier).

    An edition covers 2-3 days. `ranks` is the primary day; `ranks_by_day`
    (when present) carries the others. Later-fetched editions win on a
    duplicate (date, pitcher) since PL revises ranks intraday.
    """
    rows = []
    files = (sorted(glob.glob(str(ROOT / "data/research/pl_cache/pl_sp_streamers*.json")))
             + sorted(glob.glob(str(ROOT / "data/research/pl_cache/streamer_backfill/*.json"))))
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        fetched = d.get("fetched")
        primary = d.get("primary_date") or d.get("date_covered")
        covers = d.get("covers_dates") or ([primary] if primary else [])

        def emit(date, ranks):
            for name, meta in (ranks or {}).items():
                if not isinstance(meta, dict):
                    continue
                # A per-entry 'date' overrides the block's day when present —
                # some editions tag each pitcher with his own game date.
                day = iso_date(meta.get("date")) or iso_date(date)
                if not day:
                    continue
                rows.append(dict(date=day, pl_name=name,
                                 pl_rank=meta.get("rank"),
                                 pl_tier=canon_tier(meta.get("tier")),
                                 opp=meta.get("opp"), fetched=fetched, src=Path(f).name))

        by_day = d.get("ranks_by_day") or {}
        if by_day:
            for day, ranks in by_day.items():
                emit(day, ranks)
        # `ranks` maps to the primary day (falls back to first covered date)
        emit(primary or (covers[0] if covers else None), d.get("ranks"))

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.dropna(subset=["pl_rank"])
    df["key"] = df["pl_name"].map(norm)
    df = (df.sort_values("fetched")
            .drop_duplicates(subset=["date", "key"], keep="last")
            .reset_index(drop=True))
    return df


def main():
    pl = load_pl_editions()
    print(f"PL streamer rows loaded: {len(pl)}  "
          f"({pl['date'].nunique()} distinct dates, "
          f"{pl['date'].min()} -> {pl['date'].max()})")

    # ---- actuals -----------------------------------------------------------
    box = pd.read_parquet(ROOT / "data/research/xfp_cache/boxscore_pitchers.parquet")
    box["game_date"] = pd.to_datetime(box["game_date"])
    st = box[box["gs"] > 0].copy()
    st["date"] = st["game_date"].dt.strftime("%Y-%m-%d")
    # Recompute FP rather than trusting the stored column.
    st["ipf"] = st["ip"].astype(float)
    st["fp"] = (st["so"] + st["ipf"] * 3.3 - st["h_allowed"] - 2 * st["er"]
                - st["bb_allowed"] - st.get("hbp_allowed", 0))
    actual = st[["date", "mlbam_id", "fp", "so", "ipf", "er"]]

    # ---- name -> mlbam (uses the collision-safe resolver) -------------------
    uniq = pl[["pl_name", "key"]].drop_duplicates()
    mp = {}
    unresolved = []
    for _, r in uniq.iterrows():
        pid = None
        try:
            pid = resolve_pitcher_id(r["pl_name"], role="SP")
        except Exception:
            pid = None
        if pid is None:
            unresolved.append(r["pl_name"])
        else:
            mp[r["key"]] = int(pid)
    pl["mlbam_id"] = pl["key"].map(mp)
    print(f"resolved {pl['mlbam_id'].notna().sum()}/{len(pl)} rows "
          f"({len(unresolved)} names unresolved)")
    if unresolved:
        print("  unresolved sample:", ", ".join(sorted(unresolved)[:12]))

    df = pl.dropna(subset=["mlbam_id"]).copy()
    df["mlbam_id"] = df["mlbam_id"].astype(int)
    df = df.merge(actual, on=["date", "mlbam_id"], how="inner")
    print(f"joined to a real start: {len(df)} pitcher-days")

    # ---- our as-of projection ---------------------------------------------
    hist = pd.read_parquet(ROOT / "data/research/player_projection_history.parquet")
    hist = hist[hist["player_type"] == "SP"].copy()
    hist["snapshot_date"] = pd.to_datetime(hist["snapshot_date"]).dt.strftime("%Y-%m-%d")
    hist = hist[["snapshot_date", "mlbam_id", "rank", "proj_per", "data_quality_tag"]]
    hist = hist.rename(columns={"rank": "our_rank", "proj_per": "our_proj"})
    hist["source"] = "logged"

    # Extend backwards with git-recovered snapshots. The logged store starts
    # 2026-06-04; the daily refresh committed xfp_rp3_projections.csv from
    # 2026-05-07, and a committed file cannot have seen the future. Logged wins
    # on any date it covers (canonical); git only fills dates it does not.
    gitp = ROOT / "data/research/rp3_git_snapshots.parquet"
    if gitp.exists():
        g = pd.read_parquet(gitp)[
            ["snapshot_date", "mlbam_id", "our_rank", "our_proj",
             "data_quality_tag", "source"]]
        have = set(hist["snapshot_date"].unique())
        g = g[~g["snapshot_date"].isin(have)]
        hist = pd.concat([hist, g], ignore_index=True)
        print(f"as-of source: {len(hist):,} rows | "
              f"{hist['snapshot_date'].nunique()} dates "
              f"({hist['snapshot_date'].min()} .. {hist['snapshot_date'].max()}) "
              f"| git-filled dates: {g['snapshot_date'].nunique()}")

    # merge_asof needs sorted datetimes; direction=backward => latest snapshot
    # on or before the start date (snapshot D is built from games through D-1).
    df["_d"] = pd.to_datetime(df["date"])
    hist["_d"] = pd.to_datetime(hist["snapshot_date"])
    df = df.sort_values("_d")
    hist = hist.sort_values("_d")
    out = pd.merge_asof(df, hist, on="_d", by="mlbam_id", direction="backward")
    out["asof_lag_days"] = (out["_d"] - pd.to_datetime(out["snapshot_date"])).dt.days

    graded = out.dropna(subset=["our_proj"]).copy()
    print(f"with an as-of rp3 snapshot: {len(graded)} pitcher-days "
          f"(median snapshot lag {graded['asof_lag_days'].median():.0f}d)")
    # Keep BOTH frames. Nick's own skill is measurable over the full season,
    # but the head-to-head can only run where an as-of snapshot exists — the
    # projection history starts 2026-06-04, so grading him only on that window
    # would throw away two-thirds of his record for no reason.
    out.to_csv(ROOT / "data/outputs/pl_backtest_full.csv", index=False)
    graded.to_csv(ROOT / "data/outputs/pl_vs_model_backtest.csv", index=False)
    return graded


if __name__ == "__main__":
    g = main()
    print("\nwrote data/outputs/pl_vs_model_backtest.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Grading
# ─────────────────────────────────────────────────────────────────────────────

SEED = 20260807
BOOT = 2000


def analyze(df, seed: int = SEED, boot: int = BOOT):
    """Score both sources on the same starts, with cluster-bootstrap CIs.

    Days are the resampling unit, not rows: pitchers on one slate share
    opponents and conditions, so row-level resampling understates the spread.
    Every marginal result found during development (an "Auto == Probably"
    tier collapse at n=150, a disagreement edge at n=18, a top-2 edge at
    n=1360) evaporated once the sample grew — so read a CI that barely
    excludes zero as noise until it survives more data.
    """
    from scipy import stats
    rng = np.random.default_rng(seed)
    df = df.dropna(subset=["fp", "pl_rank", "our_proj"]).copy()
    df["pl_score"] = -df["pl_rank"].astype(float)

    def boot_days(frame, fn):
        days = frame["date"].unique()
        by = {d: g for d, g in frame.groupby("date")}
        out = []
        for _ in range(boot):
            s = pd.concat([by[d] for d in rng.choice(days, len(days), True)],
                          ignore_index=True)
            try:
                out.append(fn(s))
            except Exception:
                pass
        return (np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5)) if out else (np.nan, np.nan)

    def sp(frame, col):
        return stats.spearmanr(frame[col], frame["fp"]).statistic

    print(f"n = {len(df)} pitcher-days | {df['date'].nunique()} slates | "
          f"{df['date'].min()} -> {df['date'].max()}")
    print("\n=== RANK SKILL vs actual FP (Spearman) ===")
    for label, col in [("Nick (PL streamer rank)", "pl_score"),
                       ("Ours (as-of rp3)", "our_proj")]:
        lo, hi = boot_days(df, lambda s, c=col: sp(s, c))
        print(f"  {label:26s} r = {sp(df, col):+.3f}  CI [{lo:+.3f}, {hi:+.3f}]")
    lo, hi = boot_days(df, lambda s: sp(s, "pl_score") - sp(s, "our_proj"))
    d = sp(df, "pl_score") - sp(df, "our_proj")
    print(f"  {'DIFFERENCE':26s} d = {d:+.3f}  CI [{lo:+.3f}, {hi:+.3f}]  "
          f"{'SEPARABLE' if (lo > 0 or hi < 0) else 'not separable'}")

    print("\n=== PL TIERS (mean actual FP) ===")
    for t in ["Auto-Start", "Probably Start", "Questionable", "Do Not Start"]:
        s = df[df["pl_tier"] == t]
        if len(s) < 10:
            continue
        lo, hi = boot_days(df[df["pl_tier"] == t], lambda x: x["fp"].mean())
        print(f"  {t:16s} n={len(s):4d}  {s['fp'].mean():6.2f} FP  "
              f"CI [{lo:5.2f},{hi:5.2f}]  bust {100*(s['fp']<5).mean():4.0f}%  "
              f"boom {100*(s['fp']>=17).mean():4.0f}%")

    print("\n=== TOP-K STREAMING SIM ===")
    for k in (1, 2, 3):
        rows = [dict(nick=g.nlargest(k, "pl_score")["fp"].mean(),
                     ours=g.nlargest(k, "our_proj")["fp"].mean(),
                     field=g["fp"].mean())
                for _, g in df.groupby("date") if len(g) >= k]
        r = pd.DataFrame(rows)
        diff = r["nick"] - r["ours"]
        bs = [rng.choice(diff.values, len(diff), True).mean() for _ in range(boot)]
        lo, hi = np.percentile(bs, [2.5, 97.5])
        print(f"  K={k}: Nick {r['nick'].mean():6.2f} | ours {r['ours'].mean():6.2f} | "
              f"field {r['field'].mean():6.2f} | d {diff.mean():+5.2f} "
              f"CI [{lo:+.2f},{hi:+.2f}] {'*' if (lo > 0 or hi < 0) else 'ns'}")

    p1 = df[df["pl_rank"] == 1]
    if len(p1):
        lo, hi = boot_days(p1, lambda x: x["fp"].mean())
        print(f"\n=== NICK'S #1 PICK: n={len(p1)}  {p1['fp'].mean():.2f} FP  "
              f"CI [{lo:.2f},{hi:.2f}]  bust {100*(p1['fp']<5).mean():.0f}%  "
              f"boom {100*(p1['fp']>=17).mean():.0f}%  (slate avg {df['fp'].mean():.2f})")
    return df


if __name__ == "__main__":
    graded = main()
    print()
    analyze(graded)
