"""
Model evaluation helpers for the PLV Clone pipeline.

Always reports model metrics alongside naive-baseline comparisons.
Never silently skips diagnostics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)

from plv_clone.utils.logging import get_logger

logger = get_logger(__name__)


def evaluate_classifier(
    y_true: pd.Series | np.ndarray,
    y_prob: np.ndarray,
    label: str = "",
    verbose: bool = True,
) -> dict[str, float]:
    """Evaluate a binary classifier against a naive baseline.

    Naive baseline: predicts the marginal positive rate for every sample.

    Args:
        y_true: True binary labels.
        y_prob: Predicted positive-class probabilities.
        label:  Description for logging.
        verbose: If True, print a summary table.

    Returns:
        Dict with keys: log_loss, brier_score, auc_roc, ece,
        baseline_log_loss, baseline_brier, beats_baseline_ll, beats_baseline_bs.
    """
    y_true = np.asarray(y_true).astype(float)
    y_prob = np.clip(np.asarray(y_prob).astype(float), 1e-7, 1 - 1e-7)

    marginal_rate = y_true.mean()
    baseline_prob = np.full_like(y_prob, marginal_rate)

    model_ll = log_loss(y_true, y_prob)
    baseline_ll = log_loss(y_true, baseline_prob)
    model_bs = brier_score_loss(y_true, y_prob)
    baseline_bs = brier_score_loss(y_true, baseline_prob)

    try:
        auc = roc_auc_score(y_true, y_prob)
    except Exception:
        auc = float("nan")

    ece = _expected_calibration_error(y_true, y_prob)

    results = {
        "log_loss": model_ll,
        "brier_score": model_bs,
        "auc_roc": auc,
        "ece": ece,
        "baseline_log_loss": baseline_ll,
        "baseline_brier": baseline_bs,
        "beats_baseline_ll": model_ll < baseline_ll,
        "beats_baseline_bs": model_bs < baseline_bs,
        "n": len(y_true),
        "positive_rate": marginal_rate,
    }

    if verbose:
        prefix = f"[{label}] " if label else ""
        logger.info(
            "%slog_loss: %.4f (baseline %.4f, %s) | brier: %.4f (baseline %.4f, %s) | "
            "AUC: %.4f | ECE: %.4f | n=%d",
            prefix,
            model_ll, baseline_ll, "✓" if results["beats_baseline_ll"] else "✗",
            model_bs, baseline_bs, "✓" if results["beats_baseline_bs"] else "✗",
            auc, ece, len(y_true),
        )
    return results


def evaluate_regression(
    y_true: pd.Series | np.ndarray,
    y_pred: np.ndarray,
    label: str = "",
    verbose: bool = True,
) -> dict[str, float]:
    """Evaluate a regression model against a predict-mean baseline.

    Args:
        y_true: True continuous targets.
        y_pred: Model predictions.
        label:  Description for logging.

    Returns:
        Dict with keys: rmse, mae, r2, spearman_r, baseline_rmse, beats_baseline.
    """
    y_true = np.asarray(y_true).astype(float)
    y_pred = np.asarray(y_pred).astype(float)

    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true, y_pred = y_true[mask], y_pred[mask]

    if len(y_true) == 0:
        logger.warning("[%s] No valid samples for regression evaluation.", label)
        return {}

    mean_baseline = np.full_like(y_pred, y_true.mean())

    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    baseline_rmse = np.sqrt(mean_squared_error(y_true, mean_baseline))
    spearman_r, _ = scipy_stats.spearmanr(y_true, y_pred)

    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    results = {
        "rmse": rmse,
        "mae": mae,
        "r2": r2,
        "spearman_r": spearman_r,
        "baseline_rmse": baseline_rmse,
        "beats_baseline": rmse < baseline_rmse,
        "n": len(y_true),
    }

    if verbose:
        prefix = f"[{label}] " if label else ""
        logger.info(
            "%sRMSE: %.4f (baseline %.4f, %s) | MAE: %.4f | R²: %.4f | Spearman: %.4f | n=%d",
            prefix,
            rmse, baseline_rmse, "✓" if results["beats_baseline"] else "✗",
            mae, r2, spearman_r, len(y_true),
        )
    return results


def evaluate_player_stability(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    player_col: str,
    metric_col: str,
    min_count: int = 100,
    label: str = "",
) -> dict[str, Any]:
    """Compute year-over-year Spearman correlation for a player-level metric.

    Args:
        df_a:       Player-level DataFrame for year A (e.g. 2023).
        df_b:       Player-level DataFrame for year B (e.g. 2024).
        player_col: Column identifying players.
        metric_col: Metric to correlate.
        min_count:  Minimum qualifying sample count column, if present.
        label:      Description for logging.

    Returns:
        Dict with keys: spearman_r, n_players, p_value.
    """
    merged = df_a[[player_col, metric_col]].merge(
        df_b[[player_col, metric_col]],
        on=player_col,
        suffixes=("_a", "_b"),
    ).dropna()

    if len(merged) < 5:
        logger.warning("[%s] Too few players for stability analysis (%d).", label, len(merged))
        return {"spearman_r": float("nan"), "n_players": len(merged)}

    r, p = scipy_stats.spearmanr(merged[f"{metric_col}_a"], merged[f"{metric_col}_b"])
    result = {"spearman_r": r, "p_value": p, "n_players": len(merged)}

    logger.info(
        "[%s] YoY stability: Spearman r=%.3f (p=%.4f, n=%d players)",
        label, r, p, len(merged),
    )
    return result


def _expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE).

    Computed directly with np.digitize so the weights and calibration
    averages are guaranteed to be aligned (avoids sklearn bin-edge drift).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    # Use 1.0 + 1e-8 upper edge so probabilities of exactly 1.0 fall in-range
    bin_edges = np.linspace(0.0, 1.0 + 1e-8, n_bins + 1)
    binids = np.digitize(y_prob, bin_edges) - 1  # 0-indexed
    bin_total = np.bincount(binids, minlength=n_bins)
    bin_true = np.bincount(binids, weights=y_true, minlength=n_bins)
    bin_pred = np.bincount(binids, weights=y_prob, minlength=n_bins)
    total = bin_total.sum()
    if total == 0:
        return float("nan")
    nonzero = bin_total > 0
    fraction_positive = bin_true[nonzero] / bin_total[nonzero]
    mean_predicted = bin_pred[nonzero] / bin_total[nonzero]
    weights = bin_total[nonzero] / total
    return float(np.sum(weights * np.abs(fraction_positive - mean_predicted)))


def calibration_plot_data(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> pd.DataFrame:
    """Return calibration curve data as a DataFrame for plotting."""
    fraction_pos, mean_pred = calibration_curve(
        y_true, y_prob, n_bins=n_bins, strategy="uniform"
    )
    return pd.DataFrame({"mean_predicted": mean_pred, "fraction_positive": fraction_pos})
