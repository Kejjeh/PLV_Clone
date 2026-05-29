"""Shared loaders for methodology tests D-H.

Pure research code — does NOT touch any production model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HITTER_CSV = REPO / "data" / "research" / "hitter_ratings_master.csv"
SP_CSV = REPO / "data" / "research" / "sp_ratings_master.csv"
PARK_CSV = REPO / "data" / "research" / "xfp_cache" / "park_factors_2018_2026.csv"

# Sub-domain feature lists (per spec)
HIT_SUBS = [
    "Z_CONTACT", "O_CONTACT", "K_AVOIDANCE", "CONTACT_QUALITY",
    "SPRAY_PROFILE", "RAW_POWER", "LAUNCH_OPTIM", "DAMAGE_PROD",
    "PATIENCE", "AGGRESSION", "SPEED_TOOL", "SB_CONVERSION",
]
SP_SUBS = [
    "SWING_MISS", "CALLED_STRIKE", "DAMAGE_SUPP",
    "GB_TENDENCY", "WALK_AVOID", "STRIKE_THROWING",
]


def load_hitters() -> pd.DataFrame:
    df = pd.read_csv(HITTER_CSV)
    return df


def load_sps() -> pd.DataFrame:
    df = pd.read_csv(SP_CSV)
    return df


def build_horizon_panel(df: pd.DataFrame, id_col: str, y_col: str, horizons=(1, 2, 3)) -> pd.DataFrame:
    """Add fp_t1, fp_t2, fp_t3 columns by shifting within each player.

    Requires sort by (id, year). Forward-leak safe because shift(-h) reads future row.
    """
    df = df.sort_values([id_col, "year"]).reset_index(drop=True)
    for h in horizons:
        df[f"fp_t{h}"] = df.groupby(id_col)[y_col].shift(-h)
        # Also need horizon to land on a real subsequent year (no big gaps)
        df[f"year_t{h}"] = df.groupby(id_col)["year"].shift(-h)
        # Only valid if the future year is exactly year + h (no big gap)
        df[f"valid_t{h}"] = (df[f"year_t{h}"] == df["year"] + h)
        df.loc[~df[f"valid_t{h}"].fillna(False), f"fp_t{h}"] = np.nan
    return df


def r2_score_safe(y_true, y_pred) -> float:
    from sklearn.metrics import r2_score
    return float(r2_score(y_true, y_pred))


def fit_linear_report(X_train, y_train, X_test, y_test):
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score, mean_absolute_error
    m = LinearRegression().fit(X_train, y_train)
    yp = m.predict(X_test)
    return {
        "r2": float(r2_score(y_test, yp)),
        "mae": float(mean_absolute_error(y_test, yp)),
        "coef": dict(zip(X_train.columns, m.coef_.tolist())),
        "intercept": float(m.intercept_),
        "model": m,
        "y_pred": yp,
    }
