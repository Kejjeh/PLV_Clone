"""
Run-value and count-state expected-value features.

Three concepts — kept strictly separate:

  1. Pre-pitch count EV (ev_pre):
     Expected run value BEFORE the pitch is thrown, given (balls, strikes).
     This is the baseline from which PLV gain/loss is measured.

  2. Post-pitch state EV (ev_ball, ev_called_strike, ev_whiff, ev_foul):
     Expected run value AFTER transitioning to the next count state following
     each non-terminal outcome.

  3. Terminal event constants (TERMINAL_XWOBA in constants.py):
     Fixed xwOBA values for PA-ending events (walk, HBP, strikeout).
     NOT derived from the count table; set once in constants.py.

The count table is built ONLY from training data to prevent leakage.
It is saved to disk and loaded read-only at score time.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from plv_clone.utils.constants import COUNT_STATES, TERMINAL_XWOBA
from plv_clone.utils.io import read_json, write_json
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_COUNT_TABLE_FILE = "count_value_table.json"


def build_count_value_table(df: pd.DataFrame, models_dir: Path) -> pd.DataFrame:
    """Build and save the count value table from training data.

    Computes empirical mean `delta_run_exp` for each (balls, strikes) state
    and derives next-state transition values.

    MUST be called only on training data — never on validation or test sets.

    Args:
        df:          Cleaned pitch-level training DataFrame.
        models_dir:  Directory where the table JSON will be saved.

    Returns:
        DataFrame indexed by (balls, strikes) with EV columns.
    """
    logger.info("Building count value table from %d training pitches …", len(df))

    if "delta_run_exp" not in df.columns:
        raise ValueError("Column 'delta_run_exp' required to build count value table.")

    # ── Pre-pitch count EV ────────────────────────────────────────────────
    # Average delta_run_exp per count state.  Negative values = pitcher-
    # favourable outcomes on average; positive = hitter-favourable.
    pre_ev = (
        df.groupby(["balls", "strikes"])["delta_run_exp"]
        .mean()
        .rename("ev_pre")
        .reset_index()
    )

    # ── Post-pitch state EV by outcome type ───────────────────────────────
    # For each non-terminal outcome, compute mean delta_run_exp from training.
    def _outcome_ev(flag_col: str, name: str) -> pd.DataFrame:
        sub = df[df[flag_col].astype(bool)]
        if sub.empty:
            return pd.DataFrame(columns=["balls", "strikes", name])
        return (
            sub.groupby(["balls", "strikes"])["delta_run_exp"]
            .mean()
            .rename(name)
            .reset_index()
        )

    ev_ball = _outcome_ev("is_ball", "ev_ball")
    ev_cs = _outcome_ev("is_called_strike", "ev_called_strike")
    ev_whiff = _outcome_ev("is_whiff", "ev_whiff")
    ev_foul = _outcome_ev("is_foul", "ev_foul")
    ev_in_play = _outcome_ev("is_in_play", "ev_in_play")

    # ── Assemble table ────────────────────────────────────────────────────
    table = pre_ev.copy()
    for ev_df in [ev_ball, ev_cs, ev_whiff, ev_foul, ev_in_play]:
        if not ev_df.empty:
            table = table.merge(ev_df, on=["balls", "strikes"], how="left")

    # Fill any missing count states with a reasonable fallback (league mean)
    league_mean = df["delta_run_exp"].mean()
    for col in ["ev_ball", "ev_called_strike", "ev_whiff", "ev_foul", "ev_in_play"]:
        if col in table.columns:
            table[col] = table[col].fillna(league_mean)
        else:
            table[col] = league_mean

    # Add terminal event xwOBA constants as columns (informational)
    table["terminal_walk_xwoba"] = TERMINAL_XWOBA["walk"]
    table["terminal_strikeout_xwoba"] = TERMINAL_XWOBA["strikeout"]
    table["terminal_hbp_xwoba"] = TERMINAL_XWOBA["hbp"]

    logger.info(
        "Count value table: %d states. EV range: %.4f to %.4f (pre-pitch).",
        len(table),
        table["ev_pre"].min(),
        table["ev_pre"].max(),
    )

    # ── Persist ───────────────────────────────────────────────────────────
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    out_path = models_dir / _COUNT_TABLE_FILE
    write_json(
        {"count_table": table.to_dict(orient="records")},
        out_path,
    )
    logger.info("Count value table saved → %s", out_path)

    return table.set_index(["balls", "strikes"])


def load_count_value_table(models_dir: Path) -> pd.DataFrame:
    """Load the count value table artifact from disk.

    Returns a DataFrame indexed by (balls, strikes).
    Raises FileNotFoundError if the table has not been built yet.
    """
    path = Path(models_dir) / _COUNT_TABLE_FILE
    data = read_json(path)
    df = pd.DataFrame(data["count_table"])
    df["balls"] = df["balls"].astype(int)
    df["strikes"] = df["strikes"].astype(int)
    return df.set_index(["balls", "strikes"])


def lookup_count_ev(
    count_table: pd.DataFrame,
    balls: int | pd.Series,
    strikes: int | pd.Series,
    ev_col: str,
    default: float = 0.0,
) -> float | pd.Series:
    """Look up an EV column for a given (balls, strikes) state.

    Handles scalar and vectorised lookups.

    Args:
        count_table: DataFrame indexed by (balls, strikes).
        balls:       Scalar or Series of ball counts.
        strikes:     Scalar or Series of strike counts.
        ev_col:      Column to look up (e.g. 'ev_ball', 'ev_pre').
        default:     Value to return when a count state is not in the table.
    """
    if isinstance(balls, (int, np.integer)) and isinstance(strikes, (int, np.integer)):
        key = (int(balls), int(strikes))
        if key in count_table.index:
            return float(count_table.loc[key, ev_col])
        return default

    # Vectorised path
    keys = pd.MultiIndex.from_arrays([balls.astype(int), strikes.astype(int)])
    result = pd.Series(index=keys.to_frame().index, dtype=float)
    for key in keys:
        result.loc[key] = (
            float(count_table.loc[key, ev_col])
            if key in count_table.index
            else default
        )
    # Reindex to match original series index
    return count_table.reindex(keys)[ev_col].fillna(default).values


def add_count_ev_features(df: pd.DataFrame, count_table: pd.DataFrame) -> pd.DataFrame:
    """Merge pre-pitch EV and per-outcome EV columns into a pitch-level DataFrame.

    All EV columns are named `count_ev_*` to make their origin clear.

    Args:
        df:          Pitch-level DataFrame with `balls` and `strikes` columns.
        count_table: Indexed count value table from load_count_value_table().

    Returns:
        DataFrame with added `count_ev_*` columns.
    """
    df = df.copy()
    ct = count_table.reset_index()

    df = df.merge(
        ct.rename(columns=lambda c: f"count_ev_{c}" if c not in ("balls", "strikes") else c),
        on=["balls", "strikes"],
        how="left",
    )
    return df
