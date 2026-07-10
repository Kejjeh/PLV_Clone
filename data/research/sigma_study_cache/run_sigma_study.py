"""rp3 sigma single-start coverage study (pre-registered 2026-07-10).

See data/research/validation_runs/rp3_sigma_singlestart_2026-07-10.md.
Measurement only; prints the full results block. Does NOT touch
sigma_calibration.json (that decision is made by the operator per the
pre-registered rule after reading the output).
"""
import glob
import os
import re

import numpy as np
import pandas as pd

ROOT = r"C:\Users\Joshua\plv_clone"
CACHE = os.path.join(ROOT, "data", "research", "sigma_study_cache")
Z25, Z10 = 0.6745, 1.2816
MAX_GAP_DAYS = 10


def load_snapshots(prefix, cols):
    frames = []
    for path in sorted(glob.glob(os.path.join(CACHE, f"{prefix}_*.csv"))):
        d = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path)).group(1)
        df = pd.read_csv(path)
        keep = [c for c in cols if c in df.columns]
        df = df[keep].copy()
        df["snap_date"] = pd.Timestamp(d)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def coverage_row(sub, lo_col, hi_col, act_col="actual"):
    n = len(sub)
    if n == 0:
        return {"n": 0, "cov": np.nan}
    cov = ((sub[act_col] >= sub[lo_col]) & (sub[act_col] <= sub[hi_col])).mean()
    return {"n": n, "cov": round(float(cov) * 100, 1)}


def fmt(label, d):
    print(f"  {label:<38} n={d['n']:>5}  cov={d['cov']}%")


# ---------------------------------------------------------------- rp3 primary
snap = load_snapshots("rp3", [
    "pitcher", "player_name", "data_quality_tag", "xfp_rp3_per_start",
    "xfp_rp3_sigma", "xfp_rp3_sigma_raw", "xfp_rp3_p25", "xfp_rp3_p75",
])
print(f"rp3 snapshots: {snap['snap_date'].nunique()} dates "
      f"{snap['snap_date'].min().date()} .. {snap['snap_date'].max().date()}, "
      f"{len(snap)} rows")

snap = snap[snap["data_quality_tag"] != "marcel_il"]
snap = snap.dropna(subset=["xfp_rp3_per_start", "xfp_rp3_p25", "xfp_rp3_p75",
                           "xfp_rp3_sigma", "xfp_rp3_sigma_raw"])
# per-snapshot-date per_start terciles
snap["tier"] = (snap.groupby("snap_date")["xfp_rp3_per_start"]
                .transform(lambda s: pd.qcut(s, 3, labels=["T3_low", "T2_mid", "T1_high"])))
print(f"rp3 snapshot rows after exclusions: {len(snap)}")

box = pd.read_parquet(os.path.join(ROOT, "data", "research", "xfp_cache",
                                   "boxscore_pitchers.parquet"))
starts = box[box["gs"] == 1][["game_pk", "game_date", "mlbam_id", "fp_sp"]].copy()
starts["game_date"] = pd.to_datetime(starts["game_date"])
starts = starts.rename(columns={"mlbam_id": "pitcher", "fp_sp": "actual"})
starts = starts.sort_values("game_date")

snap_sorted = snap.sort_values("snap_date")
pairs = pd.merge_asof(
    starts, snap_sorted, by="pitcher",
    left_on="game_date", right_on="snap_date",
    allow_exact_matches=False,  # strictly after D
    tolerance=pd.Timedelta(days=MAX_GAP_DAYS), direction="backward",
)
pairs = pairs.dropna(subset=["snap_date"])
# merge_asof already gives the LATEST snapshot before each start; each
# (pitcher, game_pk) appears once because starts rows are unique.
assert not pairs.duplicated(["pitcher", "game_pk"]).any()
pairs["gap_days"] = (pairs["game_date"] - pairs["snap_date"]).dt.days
pairs["gap_bucket"] = pd.cut(pairs["gap_days"], [0, 2, 5, 10],
                             labels=["1-2d", "3-5d", "6-10d"])
pairs["err"] = pairs["actual"] - pairs["xfp_rp3_per_start"]
pairs["p10"] = pairs["xfp_rp3_per_start"] - Z10 * pairs["xfp_rp3_sigma"]
pairs["p90"] = pairs["xfp_rp3_per_start"] + Z10 * pairs["xfp_rp3_sigma"]

n = len(pairs)
print(f"\n=== rp3 PRIMARY: {n} (pitcher, start) pairs ===")
fmt("[p25,p75] overall (target 50%)",
    coverage_row(pairs, "xfp_rp3_p25", "xfp_rp3_p75"))
fmt("[p10,p90] derived (target 80%)", coverage_row(pairs, "p10", "p90"))

mean_err = float(pairs["err"].mean())
med_err = float(pairs["err"].median())
print(f"  point bias: mean(actual-pred) = {mean_err:+.3f}  "
      f"median = {med_err:+.3f}  sd(err) = {pairs['err'].std():.3f}")

# recentered coverage (shift both edges by pooled median error)
pairs["p25_rc"] = pairs["xfp_rp3_p25"] + med_err
pairs["p75_rc"] = pairs["xfp_rp3_p75"] + med_err
fmt("[p25,p75] RECENTERED by median err",
    coverage_row(pairs, "p25_rc", "p75_rc"))

print("\n  --- slices [p25,p75] ---")
for tier, sub in pairs.groupby("tier", observed=True):
    fmt(f"tier {tier}", coverage_row(sub, "xfp_rp3_p25", "xfp_rp3_p75"))
for tag, sub in pairs.groupby("data_quality_tag"):
    fmt(f"tag {tag}", coverage_row(sub, "xfp_rp3_p25", "xfp_rp3_p75"))
for gb, sub in pairs.groupby("gap_bucket", observed=True):
    fmt(f"gap {gb}", coverage_row(sub, "xfp_rp3_p25", "xfp_rp3_p75"))

# implied alpha via the SAME mechanism as 2026-06-03
alpha_implied = float(pairs["err"].std() / pairs["xfp_rp3_sigma_raw"].mean())
print(f"\n  implied alpha (std(err)/mean(sigma_raw)) = {alpha_implied:.3f} "
      f"(current 2.41)")

# train/holdout split by snapshot date (first 80% / last 20%) — reported
# regardless; ACTED ON only if the decision rule fires.
dates = sorted(pairs["snap_date"].unique())
cut = dates[int(len(dates) * 0.8) - 1]
tr, te = pairs[pairs["snap_date"] <= cut], pairs[pairs["snap_date"] > cut]
alpha_tr = float(tr["err"].std() / tr["xfp_rp3_sigma_raw"].mean())
for name, sub in (("train(first 80% dates)", tr), ("holdout(last 20%)", te)):
    lo = sub["xfp_rp3_per_start"] - Z25 * alpha_tr * sub["xfp_rp3_sigma_raw"]
    hi = sub["xfp_rp3_per_start"] + Z25 * alpha_tr * sub["xfp_rp3_sigma_raw"]
    cov = ((sub["actual"] >= lo.clip(lower=0)) & (sub["actual"] <= hi)).mean()
    print(f"  refit-alpha {alpha_tr:.3f} on {name:<22} n={len(sub):>5} "
          f"cov={cov*100:.1f}%")
print(f"  (holdout current-alpha cov: "
      f"{coverage_row(te, 'xfp_rp3_p25', 'xfp_rp3_p75')})")

# ------------------------------------------------------------- rh3 secondary
hsnap = load_snapshots("rh3", [
    "batter", "player_name", "xfp_rh3_per_pa", "xfp_rh3_per_game",
    "xfp_rh3_sigma", "xfp_rh3_p25", "xfp_rh3_p75",
])
hsnap = hsnap.dropna(subset=["xfp_rh3_per_pa", "xfp_rh3_p25", "xfp_rh3_p75"])
print(f"\nrh3 snapshots: {hsnap['snap_date'].nunique()} dates, {len(hsnap)} rows")

hbox = pd.read_parquet(os.path.join(ROOT, "data", "research", "xfp_cache",
                                    "boxscore_hitters.parquet"))
games = hbox[["game_pk", "game_date", "mlbam_id", "fp_h"]].copy()
games["game_date"] = pd.to_datetime(games["game_date"])
games = games.rename(columns={"mlbam_id": "batter"}).sort_values("game_date")

sc = pd.read_parquet(os.path.join(ROOT, "data", "research", "xfp_cache",
                                  "statcast_2026.parquet"),
                     columns=["game_pk", "batter", "at_bat_number"])
pa = (sc.groupby(["game_pk", "batter"])["at_bat_number"].nunique()
      .rename("pa_game").reset_index())
games = games.merge(pa, on=["game_pk", "batter"], how="inner")
games = games[games["pa_game"] > 0]

hpairs = pd.merge_asof(
    games, hsnap.sort_values("snap_date"), by="batter",
    left_on="game_date", right_on="snap_date",
    allow_exact_matches=False,
    tolerance=pd.Timedelta(days=MAX_GAP_DAYS), direction="backward",
)
hpairs = hpairs.dropna(subset=["snap_date"])
# keep only each batter's NEXT game after his latest snapshot: merge_asof
# attaches the latest snapshot to EVERY game within 10d; dedup to the
# FIRST game per (batter, snap_date) = the next single game.
hpairs = (hpairs.sort_values("game_date")
          .drop_duplicates(["batter", "snap_date"], keep="first"))
hpairs["rate"] = hpairs["fp_h"] / hpairs["pa_game"]
hpairs["err_pa"] = hpairs["rate"] - hpairs["xfp_rh3_per_pa"]
hpairs["gap_days"] = (hpairs["game_date"] - hpairs["snap_date"]).dt.days
hpairs["tier"] = (hpairs.groupby("snap_date")["xfp_rh3_per_game"]
                  .transform(lambda s: pd.qcut(s, 3, labels=["T3_low", "T2_mid", "T1_high"])))

print(f"\n=== rh3 SECONDARY (measurement only): {len(hpairs)} (batter, next-game) pairs ===")
print("  units: bands are PER-PA; game covered iff fp_h/PA in [p25,p75]")
fmt("[p25,p75] per-PA vs next-game rate",
    coverage_row(hpairs, "xfp_rh3_p25", "xfp_rh3_p75", act_col="rate"))
print(f"  point bias per-PA: mean = {hpairs['err_pa'].mean():+.4f}  "
      f"median = {hpairs['err_pa'].median():+.4f}")
for tier, sub in hpairs.groupby("tier", observed=True):
    fmt(f"tier {tier}",
        coverage_row(sub, "xfp_rh3_p25", "xfp_rh3_p75", act_col="rate"))
med_h = float(hpairs["err_pa"].median())
hpairs["p25_rc"] = hpairs["xfp_rh3_p25"] + med_h
hpairs["p75_rc"] = hpairs["xfp_rh3_p75"] + med_h
fmt("[p25,p75] RECENTERED by median err",
    coverage_row(hpairs, "p25_rc", "p75_rc", act_col="rate"))

pairs.to_csv(os.path.join(CACHE, "rp3_pairs.csv"), index=False)
hpairs.to_csv(os.path.join(CACHE, "rh3_pairs.csv"), index=False)
print("\npairs written to sigma_study_cache/{rp3,rh3}_pairs.csv")
