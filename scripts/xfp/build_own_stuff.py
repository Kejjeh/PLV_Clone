"""Homegrown "Stuff+" pitch-quality model (PROTOTYPE).

Trains a per-pitch run-value model from physical pitch characteristics
(the Stuff+ / tjStuff methodology) on cached Statcast, aggregates to a
pitcher-season Stuff+ on a 100-mean / 10-SD scale (HIGHER = BETTER), and
validates against FanGraphs full-season Stuff+ on holdout years 2024/2025.

Goal: r >= 0.85 vs FanGraphs Stuff+ to justify dropping the FG scrape.

Methodology ref: https://medium.com/@thomasjamesnestico/modelling-tjstuff-d9a451765484

Notes:
  - release_spin_rate is NOT in the cache; movement (pfx_x/pfx_z) encodes
    most of the spin effect, so we skip it.
  - Handedness normalization: LHP pfx_x and release_pos_x flipped so
    arm-side is consistent across handedness (standard in stuff models).
  - TARGET = delta_run_exp. Positive = run expectancy increased = BAD for
    the pitcher. So Stuff+ negates the mean predicted xRV before scaling.

Run from repo root:  python scripts/xfp/build_own_stuff.py
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RAW_DIR = "data/raw"
OUT_DIR = "data/research/own_stuff"
FG_DIR = "data/outputs"

YEARS = [2021, 2022, 2023, 2024, 2025]
TRAIN_YEARS = [2021, 2022, 2023]   # 2024/2025 are holdout for validation
VAL_YEARS = [2024, 2025]

FB_TYPES = {"FF", "SI", "FC"}      # fastball family for the primary-FB anchor
MIN_PITCHES = 200                  # min pitches per (pitcher, year) to score
# Use the full train pool — subsampling to 1M cost ~0.04 r (0.63 -> 0.68).
# Set to a positive int to cap for a quick smoke run.
TRAIN_SUBSAMPLE = 0                 # 0 = use all train-year pitches
SEED = 42

NEEDED_COLS = [
    "release_speed", "pfx_x", "pfx_z",
    "release_pos_x", "release_pos_z", "release_extension",
    "pitch_type", "p_throws", "stand",
    "delta_run_exp", "pitcher", "game_date",
]

PHYS_FEATS = [
    "release_speed", "pfx_x", "pfx_z",
    "release_pos_x", "release_pos_z", "release_extension",
    "velo_diff", "pfxx_diff", "pfxz_diff",
]


# ---------------------------------------------------------------------------
# Step 1: load
# ---------------------------------------------------------------------------
def load_data() -> pd.DataFrame:
    frames = []
    for y in YEARS:
        path = os.path.join(RAW_DIR, f"statcast_{y}.parquet")
        df = pd.read_parquet(path, columns=NEEDED_COLS)
        df["year"] = y
        frames.append(df)
        print(f"  loaded {y}: {len(df):,} rows")
    df = pd.concat(frames, ignore_index=True)

    # cast nullable Float64/Int64 -> plain numpy floats for sklearn/lightgbm
    for c in ["release_speed", "pfx_x", "pfx_z", "release_pos_x",
              "release_pos_z", "release_extension", "delta_run_exp"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["pitcher"] = pd.to_numeric(df["pitcher"], errors="coerce").astype("Int64")

    before = len(df)
    df = df.dropna(subset=["release_speed", "pfx_x", "pfx_z",
                           "release_extension", "delta_run_exp", "pitcher"])
    print(f"  dropped {before - len(df):,} rows with NaN in core cols; "
          f"{len(df):,} remain")
    return df


# ---------------------------------------------------------------------------
# Step 2: handedness-normalize horizontal movement & release
# ---------------------------------------------------------------------------
def handedness_normalize(df: pd.DataFrame) -> pd.DataFrame:
    lhp = df["p_throws"].eq("L")
    df.loc[lhp, "pfx_x"] = df.loc[lhp, "pfx_x"] * -1.0
    df.loc[lhp, "release_pos_x"] = df.loc[lhp, "release_pos_x"] * -1.0
    return df


# ---------------------------------------------------------------------------
# Step 3: primary-fastball profile + differential features
# ---------------------------------------------------------------------------
def add_primary_fb_diffs(df: pd.DataFrame) -> pd.DataFrame:
    """Per (pitcher, year): primary FB = most-frequent of FF/SI/FC.
    velo_diff / pfxx_diff / pfxz_diff measured vs that anchor.
    """
    fb = df[df["pitch_type"].isin(FB_TYPES)].copy()

    # most-frequent FB type per pitcher-year
    fb_counts = (fb.groupby(["pitcher", "year", "pitch_type"])
                   .size().reset_index(name="n"))
    fb_counts = fb_counts.sort_values(["pitcher", "year", "n"],
                                      ascending=[True, True, False])
    primary_type = (fb_counts.drop_duplicates(["pitcher", "year"])
                             [["pitcher", "year", "pitch_type"]]
                             .rename(columns={"pitch_type": "primary_fb_type"}))

    fb = fb.merge(primary_type, on=["pitcher", "year"])
    prim = fb[fb["pitch_type"] == fb["primary_fb_type"]]
    prim_prof = (prim.groupby(["pitcher", "year"])
                     .agg(primary_velo=("release_speed", "mean"),
                          primary_pfxx=("pfx_x", "mean"),
                          primary_pfxz=("pfx_z", "mean"))
                     .reset_index())

    # pitchers with no FB: fall back to overall pitcher-year means
    overall = (df.groupby(["pitcher", "year"])
                 .agg(o_velo=("release_speed", "mean"),
                      o_pfxx=("pfx_x", "mean"),
                      o_pfxz=("pfx_z", "mean"))
                 .reset_index())

    df = df.merge(prim_prof, on=["pitcher", "year"], how="left")
    df = df.merge(overall, on=["pitcher", "year"], how="left")
    df["primary_velo"] = df["primary_velo"].fillna(df["o_velo"])
    df["primary_pfxx"] = df["primary_pfxx"].fillna(df["o_pfxx"])
    df["primary_pfxz"] = df["primary_pfxz"].fillna(df["o_pfxz"])
    df = df.drop(columns=["o_velo", "o_pfxx", "o_pfxz"])

    df["velo_diff"] = df["release_speed"] - df["primary_velo"]
    df["pfxx_diff"] = df["pfx_x"] - df["primary_pfxx"]
    df["pfxz_diff"] = df["pfx_z"] - df["primary_pfxz"]
    return df


# ---------------------------------------------------------------------------
# Step 4: build feature matrix
# ---------------------------------------------------------------------------
def build_features(df: pd.DataFrame):
    # ordinal-encode pitch_type and stand as category codes (lightgbm-native)
    pt = df["pitch_type"].fillna("UNK").astype("category")
    stand = df["stand"].fillna("R").astype("category")
    X = df[PHYS_FEATS].copy()
    X["pitch_type"] = pt.cat.codes.astype("int32")
    X["stand"] = stand.cat.codes.astype("int32")
    cat_idx = [X.columns.get_loc("pitch_type"), X.columns.get_loc("stand")]
    return X, cat_idx


# ---------------------------------------------------------------------------
# Step 5: train
# ---------------------------------------------------------------------------
def train_model(X_train, y_train, cat_idx):
    try:
        import lightgbm as lgb
        print("  using lightgbm")
        model = lgb.LGBMRegressor(
            n_estimators=800, learning_rate=0.03, num_leaves=127,
            min_child_samples=500, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, random_state=SEED, n_jobs=-1,
        )
        model.fit(X_train, y_train,
                  categorical_feature=cat_idx)
        return model, "lightgbm"
    except Exception as e:  # pragma: no cover
        from sklearn.ensemble import HistGradientBoostingRegressor
        print(f"  lightgbm unavailable ({e}); using HistGradientBoostingRegressor")
        cat_mask = [i in cat_idx for i in range(X_train.shape[1])]
        model = HistGradientBoostingRegressor(
            max_iter=800, learning_rate=0.03, max_leaf_nodes=127,
            min_samples_leaf=500, categorical_features=cat_mask,
            random_state=SEED,
        )
        model.fit(X_train, y_train)
        return model, "hgbr"


# ---------------------------------------------------------------------------
# Steps 6-8: aggregate, scale, validate, save
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("[1] loading parquets...")
    df = load_data()

    print("[2] handedness-normalizing...")
    df = handedness_normalize(df)

    print("[3] computing primary-FB diffs...")
    df = add_primary_fb_diffs(df)

    print("[4] building features...")
    X, cat_idx = build_features(df)
    y = df["delta_run_exp"].values

    train_mask = df["year"].isin(TRAIN_YEARS).values
    X_train_full = X[train_mask]
    y_train_full = y[train_mask]
    print(f"    train pool: {len(X_train_full):,} pitches "
          f"(years {TRAIN_YEARS})")

    if TRAIN_SUBSAMPLE and len(X_train_full) > TRAIN_SUBSAMPLE:
        rng = np.random.RandomState(SEED)
        idx = rng.choice(len(X_train_full), TRAIN_SUBSAMPLE, replace=False)
        X_train = X_train_full.iloc[idx]
        y_train = y_train_full[idx]
        print(f"    subsampled to {TRAIN_SUBSAMPLE:,}")
    else:
        X_train, y_train = X_train_full, y_train_full

    print("[5] training GBM...")
    model, backend = train_model(X_train, y_train, cat_idx)

    print("[5b] predicting per-pitch xRV on all years...")
    df["xrv"] = model.predict(X)

    print("[6] aggregating to pitcher-year...")
    agg = (df.groupby(["pitcher", "year"])
             .agg(mean_xrv=("xrv", "mean"), n_pitches=("xrv", "size"))
             .reset_index())
    agg = agg[agg["n_pitches"] >= MIN_PITCHES].copy()

    # negate (lower run value -> higher), then standardize WITHIN year to 100/10
    agg["neg_xrv"] = -agg["mean_xrv"]
    parts = []
    for yr, g in agg.groupby("year"):
        g = g.copy()
        mu, sd = g["neg_xrv"].mean(), g["neg_xrv"].std(ddof=0)
        g["own_stuff_plus"] = 100.0 + 10.0 * (g["neg_xrv"] - mu) / sd
        parts.append(g)
    agg = pd.concat(parts, ignore_index=True)

    # ---- feature importance ----
    print("[6b] feature importances:")
    feat_names = list(X.columns)
    if backend == "lightgbm":
        imp = model.feature_importances_
    else:
        imp = getattr(model, "feature_importances_", None)
    if imp is not None:
        order = np.argsort(imp)[::-1]
        for i in order:
            print(f"    {feat_names[i]:<20} {imp[i]:>12.1f}")

    # ---- Step 7: validate vs FanGraphs ----
    print("[7] validating vs FanGraphs Stuff+ (holdout years)...")
    results = {}
    pooled_x, pooled_y = [], []
    for yr in VAL_YEARS:
        fg = pd.read_csv(os.path.join(FG_DIR, f"fangraphs_pitchers_{yr}.csv"),
                         usecols=["mlb_id", "stuff_plus"])
        fg = fg.dropna(subset=["mlb_id", "stuff_plus"])
        mine = agg[agg["year"] == yr][["pitcher", "own_stuff_plus"]]
        m = mine.merge(fg, left_on="pitcher", right_on="mlb_id", how="inner")
        m = m.dropna(subset=["own_stuff_plus", "stuff_plus"])
        if len(m) >= 3:
            r, _ = pearsonr(m["own_stuff_plus"], m["stuff_plus"])
        else:
            r = float("nan")
        results[yr] = (r, len(m))
        pooled_x.extend(m["own_stuff_plus"].tolist())
        pooled_y.extend(m["stuff_plus"].tolist())
        print(f"    {yr}: r = {r:.4f}   (n = {len(m)} matched pitcher-seasons)")

    if len(pooled_x) >= 3:
        pooled_r, _ = pearsonr(pooled_x, pooled_y)
    else:
        pooled_r = float("nan")
    print(f"    pooled: r = {pooled_r:.4f}   (n = {len(pooled_x)})")

    # ---- Step 8: save ----
    print("[8] writing outputs...")
    out = agg[["pitcher", "year", "own_stuff_plus", "n_pitches"]].copy()
    for yr in YEARS:
        sub = out[out["year"] == yr].sort_values("own_stuff_plus",
                                                 ascending=False)
        path = os.path.join(OUT_DIR, f"own_stuff_{yr}.csv")
        sub.to_csv(path, index=False)
        print(f"    wrote {path}  ({len(sub)} pitcher-seasons)")

    print("\n=== SUMMARY ===")
    print(f"backend: {backend}")
    for yr in VAL_YEARS:
        r, n = results[yr]
        print(f"  {yr}: r={r:.4f}  n={n}")
    print(f"  pooled: r={pooled_r:.4f}  n={len(pooled_x)}")
    return results, pooled_r


if __name__ == "__main__":
    main()
