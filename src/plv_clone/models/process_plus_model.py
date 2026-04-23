"""
ProcessPlusModel — hitter-centric expected-value scorer.

Reuses the five trained PLV sub-models to produce three non-overlapping
per-pitch value components, then aggregates to a hitter-season leaderboard
with +metric normalization (100 = league average, 10 = 1 SD).

Components
----------
Decision+  (all pitches)
    decision_value = EV(actual_choice) - EV(counterfactual_choice)
    Measures whether the hitter swung at the right pitches.

Contact+   (all swings)
    contact_value = actual_swing_ev - expected_swing_ev
    Measures contact/whiff and foul/in-play execution.
    Uses model-predicted xwOBA for in-play so there is no overlap with Power+.

Power+     (in-play pitches with non-null xwOBA)
    power_value = actual_xwoba - expected_xwoba_from_bbv_model
    Measures batted-ball damage above pitch expectation.

Process+   = Decision+ + Contact+ + Power+  (all normalised to 100-scale)

Scaling parameters are computed from the training-population distribution
of qualified hitters (min_pa_process) and frozen at save time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from plv_clone.models.hitter_decision_model import compute_decision_values
from plv_clone.models.hitter_contact_model import compute_contact_values
from plv_clone.models.hitter_power_model import compute_power_values
from plv_clone.models.plv_model import PLVModel
from plv_clone.utils.io import read_json, write_json
from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)

_SCALING_PARAMS_FILE = "process_plus_scaling_params.json"


class ProcessPlusModel:
    """Hitter Process+ scorer built on top of a trained PLVModel.

    Load order (after training):
        pp_model = ProcessPlusModel.load(models_dir)
        scored   = pp_model.score_pitches(feature_df)
        hitters  = pp_model.aggregate_hitters(scored, min_pa=150)
    """

    def __init__(
        self,
        plv_model: PLVModel,
        scaling_params: dict[str, Any] | None = None,
    ) -> None:
        self.plv_model = plv_model
        self.scaling_params: dict[str, Any] = scaling_params or {}

    # ── Per-pitch scoring ─────────────────────────────────────────────────

    def score_pitches(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute per-pitch component values and return an annotated DataFrame.

        Adds the following columns to a copy of df:
          decision_value, contact_value, power_value

        decision_value is defined for all pitches.
        contact_value is NaN for takes.
        power_value is NaN for non-in-play pitches.
        """
        df = df.copy()

        df["decision_value"] = compute_decision_values(df, self.plv_model)
        df["contact_value"]  = compute_contact_values(df, self.plv_model)
        df["power_value"]    = compute_power_values(df, self.plv_model)

        logger.info(
            "score_pitches: %d pitches | "
            "decision mean=%.4f | contact mean=%.4f (n=%d) | power mean=%.4f (n=%d)",
            len(df),
            df["decision_value"].mean(),
            df["contact_value"].mean(),
            df["contact_value"].notna().sum(),
            df["power_value"].mean(),
            df["power_value"].notna().sum(),
        )
        return df

    # ── Hitter aggregation ────────────────────────────────────────────────

    def aggregate_hitters(
        self,
        scored_df: pd.DataFrame,
        min_pa: int = 150,
    ) -> pd.DataFrame:
        """Aggregate per-pitch scores to hitter-season +metrics.

        Aggregation rules:
          - decision_raw  : mean(decision_value)  over all pitches
          - contact_raw   : mean(contact_value)   over swings only
          - power_raw     : mean(power_value)      over in-play pitches only
          - process_raw   : decision_raw + contact_raw + power_raw

        Qualification: min_pa plate appearances.

        +metric normalization uses scaling params frozen at training time.

        Args:
            scored_df: Output of score_pitches().
            min_pa:    Minimum PA for qualification.

        Returns:
            DataFrame with one row per qualified hitter, sorted by process_plus desc.
        """
        if not self.scaling_params:
            logger.warning("No scaling params set — returning raw component values.")

        # ── Infer PA count from pitch data ────────────────────────────────
        # A plate appearance ends when is_in_play, is_walk, is_terminal_k,
        # or is_hbp is True. Easiest proxy: count unique (game_pk, at_bat_number)
        # per batter.
        pa_cols = ["game_pk", "at_bat_number", "batter"]
        has_pa_cols = all(c in scored_df.columns for c in pa_cols)

        if has_pa_cols:
            pa_count = (
                scored_df.dropna(subset=["game_pk", "at_bat_number", "batter"])
                .groupby("batter")[["game_pk", "at_bat_number"]]
                .apply(lambda x: x.drop_duplicates().shape[0])
                .rename("pa")
                .reset_index()
            )
        else:
            # Fallback: approximate PA from pitch count / ~4 pitches per PA
            pa_count = (
                scored_df.groupby("batter")
                .size()
                .rename("pa")
                .apply(lambda n: max(1, n // 4))
                .reset_index()
            )
            logger.warning("PA key columns not found; approximating PA from pitch count.")

        # ── Per-component means ───────────────────────────────────────────
        decision_agg = (
            scored_df.groupby("batter")["decision_value"]
            .mean()
            .rename("decision_raw")
            .reset_index()
        )
        contact_agg = (
            scored_df[scored_df["contact_value"].notna()]
            .groupby("batter")["contact_value"]
            .mean()
            .rename("contact_raw")
            .reset_index()
        )
        power_agg = (
            scored_df[scored_df["power_value"].notna()]
            .groupby("batter")["power_value"]
            .mean()
            .rename("power_raw")
            .reset_index()
        )
        pitch_count = (
            scored_df.groupby("batter")
            .size()
            .rename("pitches")
            .reset_index()
        )

        # ── Display name ──────────────────────────────────────────────────
        if "batter_name" in scored_df.columns:
            names = (
                scored_df.groupby("batter")["batter_name"]
                .first()
                .reset_index()
            )
        else:
            names = None

        # ── Merge ─────────────────────────────────────────────────────────
        hitters = (
            pa_count
            .merge(pitch_count, on="batter", how="left")
            .merge(decision_agg, on="batter", how="left")
            .merge(contact_agg,  on="batter", how="left")
            .merge(power_agg,    on="batter", how="left")
        )
        if names is not None:
            hitters = hitters.merge(names, on="batter", how="left")

        # ── Quality filter ────────────────────────────────────────────────
        hitters = hitters[hitters["pa"] >= min_pa].copy()

        # ── Combined raw score ────────────────────────────────────────────
        # Components are additive; fill missing components with 0 so the
        # combined score is still meaningful for hitters with no in-play events.
        hitters["process_raw"] = (
            hitters["decision_raw"].fillna(0.0) +
            hitters["contact_raw"].fillna(0.0) +
            hitters["power_raw"].fillna(0.0)
        )

        # ── +metric normalization ─────────────────────────────────────────
        hitters = self._apply_plus_metrics(hitters)

        # ── Sort ──────────────────────────────────────────────────────────
        hitters = hitters.sort_values("process_plus", ascending=False).reset_index(drop=True)

        logger.info(
            "aggregate_hitters: %d qualified hitters (min_pa=%d) | "
            "Process+ range: %.1f – %.1f",
            len(hitters), min_pa,
            hitters["process_plus"].min() if len(hitters) > 0 else 0.0,
            hitters["process_plus"].max() if len(hitters) > 0 else 0.0,
        )
        return hitters

    def _apply_plus_metrics(self, hitters: pd.DataFrame) -> pd.DataFrame:
        """Apply +metric normalization to all four raw component columns."""
        sp = self.scaling_params
        center = sp.get("center", 100.0)
        std_scale = sp.get("std_scale", 10.0)

        for component in ("decision", "contact", "power", "process"):
            raw_col  = f"{component}_raw"
            plus_col = f"{component}_plus"
            mean_key = f"{component}_mean"
            std_key  = f"{component}_std"

            if raw_col not in hitters.columns:
                continue

            if mean_key in sp and std_key in sp:
                mean = sp[mean_key]
                std  = sp[std_key]
                if std > 0:
                    hitters[plus_col] = (
                        (hitters[raw_col] - mean) / std * std_scale + center
                    ).round(1)
                else:
                    hitters[plus_col] = center
            else:
                # No scaling params: just copy raw
                hitters[plus_col] = hitters[raw_col]

        return hitters

    # ── Scaling param fitting ─────────────────────────────────────────────

    def fit_scaling_params(
        self,
        train_df: pd.DataFrame,
        min_pa: int = 150,
        center: float = 100.0,
        std_scale: float = 10.0,
    ) -> None:
        """Compute and store scaling parameters from training population.

        For each component and the combined process score, computes the
        mean and std of hitter-level averages (qualified hitters only).

        Must be called after the PLVModel is fully trained.

        Args:
            train_df:  Training-set pitch DataFrame (feature-engineered).
            min_pa:    Minimum PA for qualification (default: 150).
            center:    Desired +metric center (default: 100).
            std_scale: Desired +metric std (default: 10).
        """
        logger.info("Computing Process+ scaling params (min_pa=%d) …", min_pa)

        scored = self.score_pitches(train_df)
        hitters_raw = self._aggregate_raw_only(scored, min_pa=min_pa)

        sp: dict[str, Any] = {"center": center, "std_scale": std_scale}

        for component in ("decision", "contact", "power", "process"):
            raw_col = f"{component}_raw"
            if raw_col not in hitters_raw.columns:
                continue
            vals = hitters_raw[raw_col].dropna()
            if len(vals) < 2:
                logger.warning("Too few qualified hitters for %s scaling.", component)
                continue
            mean = float(vals.mean())
            std  = float(vals.std())
            sp[f"{component}_mean"] = mean
            sp[f"{component}_std"]  = std
            logger.info(
                "  %-10s: n=%d  mean=%.6f  std=%.6f",
                component, len(vals), mean, std,
            )

        sp["n_qualified_hitters"] = len(hitters_raw)
        self.scaling_params = sp

        logger.info(
            "Process+ scaling params frozen (%d qualified hitters).",
            len(hitters_raw),
        )

    def _aggregate_raw_only(
        self,
        scored_df: pd.DataFrame,
        min_pa: int,
    ) -> pd.DataFrame:
        """Aggregate hitter raw scores without applying +metrics (used during fitting)."""
        pa_cols = ["game_pk", "at_bat_number", "batter"]
        has_pa_cols = all(c in scored_df.columns for c in pa_cols)
        if has_pa_cols:
            pa_count = (
                scored_df.dropna(subset=["game_pk", "at_bat_number", "batter"])
                .groupby("batter")[["game_pk", "at_bat_number"]]
                .apply(lambda x: x.drop_duplicates().shape[0])
                .rename("pa")
                .reset_index()
            )
        else:
            pa_count = (
                scored_df.groupby("batter")
                .size()
                .rename("pa")
                .apply(lambda n: max(1, n // 4))
                .reset_index()
            )

        decision_agg = (
            scored_df.groupby("batter")["decision_value"]
            .mean().rename("decision_raw").reset_index()
        )
        contact_agg = (
            scored_df[scored_df["contact_value"].notna()]
            .groupby("batter")["contact_value"]
            .mean().rename("contact_raw").reset_index()
        )
        power_agg = (
            scored_df[scored_df["power_value"].notna()]
            .groupby("batter")["power_value"]
            .mean().rename("power_raw").reset_index()
        )

        hitters = (
            pa_count
            .merge(decision_agg, on="batter", how="left")
            .merge(contact_agg,  on="batter", how="left")
            .merge(power_agg,    on="batter", how="left")
        )
        hitters = hitters[hitters["pa"] >= min_pa].copy()
        hitters["process_raw"] = (
            hitters["decision_raw"].fillna(0.0) +
            hitters["contact_raw"].fillna(0.0) +
            hitters["power_raw"].fillna(0.0)
        )
        return hitters

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self, models_dir: Path) -> None:
        """Save scaling parameters.

        The PLVModel itself is saved separately via PLVModel.save().
        """
        models_dir = Path(models_dir)
        write_json(self.scaling_params, models_dir / _SCALING_PARAMS_FILE)
        logger.info("ProcessPlusModel scaling params saved → %s", models_dir)

    @classmethod
    def load(cls, models_dir: Path) -> "ProcessPlusModel":
        """Load ProcessPlusModel from disk.

        Loads the underlying PLVModel and the Process+ scaling parameters.
        """
        models_dir = Path(models_dir)
        plv_model = PLVModel.load(models_dir)

        scaling_path = models_dir / _SCALING_PARAMS_FILE
        if scaling_path.exists():
            scaling_params = read_json(scaling_path)
        else:
            logger.warning(
                "Process+ scaling params not found at %s. "
                "Run `plv train-process` first.",
                scaling_path,
            )
            scaling_params = {}

        logger.info("ProcessPlusModel loaded from %s", models_dir)
        return cls(plv_model=plv_model, scaling_params=scaling_params)
