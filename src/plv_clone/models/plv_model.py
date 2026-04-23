"""
PLVModel — staged expected-value orchestrator.

Composes the five trained sub-models and the count value table into the
full PLV computation:

    E_post = p_take  * (p_cs|take  * ev_cs + p_ball|take * ev_ball) +
             p_swing * (p_whiff|sw * ev_whiff +
                        p_contact|sw * (p_foul|ct  * ev_foul +
                                        p_ip|ct    * E[xwOBA|ip]))

    plv_raw   = count_baseline_ev - E_post   (higher = better for pitcher)
    plv       = affine_transform(plv_raw)    (0–10, league avg ≈ 5)

Scaling parameters are computed from the training-population distribution
of qualified pitchers and frozen at save time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from plv_clone.features.run_value_features import load_count_value_table, lookup_count_ev
from plv_clone.models.batted_ball_value_model import BattedBallValueModel
from plv_clone.models.called_strike_model import CalledStrikeModel
from plv_clone.models.contact_whiff_model import ContactModel
from plv_clone.models.foul_in_play_model import FoulModel
from plv_clone.models.swing_take_model import SwingModel
from plv_clone.utils.io import read_json, write_json
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_SCALING_PARAMS_FILE = "plv_scaling_params.json"


class PLVModel:
    """Staged expected-value PLV scorer.

    Load order (after training):
        model = PLVModel.load(models_dir)
        scored = model.score_pitches(feature_df)
    """

    def __init__(
        self,
        swing_model: SwingModel,
        cs_model: CalledStrikeModel,
        contact_model: ContactModel,
        foul_model: FoulModel,
        bbv_model: BattedBallValueModel,
        count_table: pd.DataFrame,
        scaling_params: dict[str, float] | None = None,
    ) -> None:
        self.swing_model = swing_model
        self.cs_model = cs_model
        self.contact_model = contact_model
        self.foul_model = foul_model
        self.bbv_model = bbv_model
        self.count_table = count_table
        # Scaling params: {"mean": float, "std": float, "target_avg": float}
        self.scaling_params: dict[str, float] = scaling_params or {}

    # ── Core computation ──────────────────────────────────────────────────

    def _pre_encode(self, df: pd.DataFrame) -> pd.DataFrame:
        """Pre-encode categorical columns once for all model predictions.

        Each sub-model's _prepare_features does a .copy() + astype on 4M+ rows.
        By pre-encoding once here, we avoid 5x redundant copies.
        """
        cat_cols = ["pitch_type", "pitch_group", "p_throws", "stand", "matchup", "zone_bin"]
        needs_encode = False
        for col in cat_cols:
            if col in df.columns:
                dtype = df[col].dtype
                if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                    needs_encode = True
                    break
        if not needs_encode:
            return df
        out = df.copy()
        for col in cat_cols:
            if col in out.columns:
                dtype = out[col].dtype
                if dtype == object or isinstance(dtype, pd.StringDtype) or str(dtype) in ("string", "str"):
                    out[col] = out[col].astype("category")
        return out

    def compute_e_post(self, df: pd.DataFrame) -> pd.Series:
        """Compute vectorised E_post for each pitch.

        Args:
            df: Feature-engineered pitch DataFrame (all pitches).

        Returns:
            Series of E_post values (expected post-pitch run value).
        """
        # Pre-encode categoricals once — avoids 5x redundant copies in sub-model predict calls
        df = self._pre_encode(df)

        # ── Sub-model predictions (vectorised) ────────────────────────────
        p_swing = pd.Series(self.swing_model.predict_proba(df), index=df.index)
        p_take = 1.0 - p_swing

        p_cs_given_take = pd.Series(self.cs_model.predict_proba(df), index=df.index)
        p_ball_given_take = 1.0 - p_cs_given_take

        p_contact_given_swing = pd.Series(self.contact_model.predict_proba(df), index=df.index)
        p_whiff_given_swing = 1.0 - p_contact_given_swing

        p_foul_given_contact = pd.Series(self.foul_model.predict_proba(df), index=df.index)
        p_in_play_given_contact = 1.0 - p_foul_given_contact

        e_xwoba_in_play = pd.Series(self.bbv_model.predict(df), index=df.index)

        # ── Count table EV lookups ────────────────────────────────────────
        balls = df["balls"].fillna(0).astype(int)
        strikes = df["strikes"].fillna(0).astype(int)

        ev_ball = _lookup_vec(self.count_table, balls, strikes, "ev_ball")
        ev_cs = _lookup_vec(self.count_table, balls, strikes, "ev_called_strike")
        ev_whiff = _lookup_vec(self.count_table, balls, strikes, "ev_whiff")
        ev_foul = _lookup_vec(self.count_table, balls, strikes, "ev_foul")

        # ── Staged E_post formula ─────────────────────────────────────────
        e_take_branch = p_cs_given_take * ev_cs + p_ball_given_take * ev_ball
        e_contact_branch = (
            p_foul_given_contact * ev_foul
            + p_in_play_given_contact * e_xwoba_in_play
        )
        e_swing_branch = p_whiff_given_swing * ev_whiff + p_contact_given_swing * e_contact_branch
        e_post = p_take * e_take_branch + p_swing * e_swing_branch

        return e_post

    def compute_plv_raw(self, df: pd.DataFrame) -> pd.Series:
        """PLV raw = pre-pitch count baseline EV minus E_post.

        A pitch that decreases expected hitter value more than baseline gets
        a higher (more positive) PLV raw score — better for the pitcher.
        """
        balls = df["balls"].fillna(0).astype(int)
        strikes = df["strikes"].fillna(0).astype(int)
        ev_pre = _lookup_vec(self.count_table, balls, strikes, "ev_pre")
        e_post = self.compute_e_post(df)
        return pd.Series(ev_pre.values - e_post.values, index=df.index)

    def transform_to_plv(self, plv_raw: pd.Series) -> pd.Series:
        """Affine transform: scale plv_raw to a 0–10 scale, avg ≈ 5.

        Uses scaling params frozen at training time.
        If scaling params not set, returns plv_raw unchanged.
        """
        if not self.scaling_params:
            logger.warning("No scaling params set — returning raw PLV values.")
            return plv_raw
        mean = self.scaling_params["mean"]
        std = self.scaling_params["std"]
        target_avg = self.scaling_params.get("target_avg", 5.0)
        target_std = self.scaling_params.get("target_std", 1.5)
        if std == 0:
            return pd.Series(target_avg, index=plv_raw.index)
        z = (plv_raw - mean) / std
        return pd.Series(z * target_std + target_avg, index=plv_raw.index)

    def score_pitches(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score all pitches and return a DataFrame with PLV columns.

        Adds the following columns to a copy of df:
          p_swing, p_cs_given_take, p_contact_given_swing,
          p_foul_given_contact, e_xwoba_in_play, e_post, plv_raw, plv
        """
        df = df.copy()

        df["p_swing"] = self.swing_model.predict_proba(df)
        df["p_take"] = 1.0 - df["p_swing"]
        df["p_cs_given_take"] = self.cs_model.predict_proba(df)
        df["p_contact_given_swing"] = self.contact_model.predict_proba(df)
        df["p_whiff_given_swing"] = 1.0 - df["p_contact_given_swing"]
        df["p_foul_given_contact"] = self.foul_model.predict_proba(df)
        df["p_in_play_given_contact"] = 1.0 - df["p_foul_given_contact"]
        df["e_xwoba_in_play"] = self.bbv_model.predict(df)

        df["e_post"] = self.compute_e_post(df)
        df["plv_raw"] = self.compute_plv_raw(df)
        df["plv"] = self.transform_to_plv(df["plv_raw"])

        logger.info(
            "score_pitches: %d pitches | plv mean=%.3f std=%.3f range=[%.3f, %.3f]",
            len(df),
            df["plv"].mean(),
            df["plv"].std(),
            df["plv"].min(),
            df["plv"].max(),
        )
        return df

    def fit_scaling_params(
        self,
        df: pd.DataFrame,
        min_pitches: int = 100,
        target_avg: float = 5.0,
        target_std: float = 1.5,
    ) -> None:
        """Compute and store scaling parameters from training population.

        Scaling is based on the **pitch-level** plv_raw distribution so that
        individual pitch PLV values are approximately in [0, 10].  Using
        pitcher-level averages as the scaling denominator amplifies per-pitch
        noise by ~100–200× (pitcher std ≈ 0.009 vs pitch std ≈ 0.054),
        producing a pitch-level PLV range of [-46, +49] — not a 0–10 scale.

        Pitcher-level qualification (min_pitches) is used only for logging;
        it does not affect the scaling parameters stored.

        Must be called AFTER training and BEFORE scoring.

        Args:
            df:           Training-set pitch DataFrame (already feature-engineered).
            min_pitches:  Minimum pitches per pitcher for qualification (logging only).
            target_avg:   Desired league-average PLV (typically 5.0).
            target_std:   Desired pitch-level PLV standard deviation (typically 1.5).
        """
        plv_raw = self.compute_plv_raw(df)

        # Pitch-level distribution — the denominator for per-pitch scaling
        mean = float(plv_raw.mean())
        std = float(plv_raw.std())

        # Pitcher-level stats for logging/reference only
        pitcher_avg = (
            df.assign(plv_raw=plv_raw)
            .groupby("pitcher")
            .agg(plv_mean=("plv_raw", "mean"), n_pitches=("plv_raw", "count"))
        )
        qualified = pitcher_avg[pitcher_avg["n_pitches"] >= min_pitches]["plv_mean"]
        n_qualified = len(qualified)

        self.scaling_params = {
            "mean": mean,
            "std": std,
            "target_avg": target_avg,
            "target_std": target_std,
            "n_qualified_pitchers": n_qualified,
        }
        logger.info(
            "PLV scaling params (pitch-level): mean=%.6f, std=%.6f "
            "(target avg=%.1f, std=%.1f | %d qualified pitchers for reference)",
            mean, std, target_avg, target_std, n_qualified,
        )

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self, models_dir: Path) -> None:
        models_dir = Path(models_dir)
        self.swing_model.save(models_dir)
        self.cs_model.save(models_dir)
        self.contact_model.save(models_dir)
        self.foul_model.save(models_dir)
        self.bbv_model.save(models_dir)
        write_json(self.scaling_params, models_dir / _SCALING_PARAMS_FILE)
        logger.info("PLVModel saved to %s", models_dir)

    @classmethod
    def load(cls, models_dir: Path) -> "PLVModel":
        models_dir = Path(models_dir)
        swing_model = SwingModel.load(models_dir)
        cs_model = CalledStrikeModel.load(models_dir)
        contact_model = ContactModel.load(models_dir)
        foul_model = FoulModel.load(models_dir)
        bbv_model = BattedBallValueModel.load(models_dir)
        count_table = load_count_value_table(models_dir)
        scaling_params = read_json(models_dir / _SCALING_PARAMS_FILE)
        logger.info("PLVModel loaded from %s", models_dir)
        return cls(
            swing_model=swing_model,
            cs_model=cs_model,
            contact_model=contact_model,
            foul_model=foul_model,
            bbv_model=bbv_model,
            count_table=count_table,
            scaling_params=scaling_params,
        )


# ── Vectorised count table lookup ────────────────────────────────────────────

def _lookup_vec(
    count_table: pd.DataFrame,
    balls: pd.Series,
    strikes: pd.Series,
    col: str,
    default: float = 0.0,
) -> pd.Series:
    """Vectorised lookup of *col* in *count_table* for (balls, strikes) pairs.

    Uses numpy fancy indexing via a flat lookup array — O(1) per row
    and fully vectorized across millions of rows.
    """
    # Build flat lookup: index = balls*4 + strikes (balls 0-3, strikes 0-2)
    n_balls, n_strikes = 4, 3
    flat = np.full(n_balls * n_strikes, default, dtype=float)
    for (b, s), v in count_table[col].items():
        if 0 <= b < n_balls and 0 <= s < n_strikes:
            flat[b * n_strikes + s] = float(v)
    idx = np.clip(balls.to_numpy(dtype=int), 0, n_balls - 1) * n_strikes + \
          np.clip(strikes.to_numpy(dtype=int), 0, n_strikes - 1)
    return pd.Series(flat[idx], index=balls.index)
