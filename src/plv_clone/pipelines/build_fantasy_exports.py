"""
Pipeline: Build fantasy-point leaderboard exports.

Reads master_hitter / master_pitcher CSVs, applies the calibrated
fantasy projection models, and writes hitter and pitcher fantasy leaderboards.

Usage:
    from plv_clone.pipelines.build_fantasy_exports import run
    exports = run(year=2024, config=cfg)

    # First-time / annual calibration:
    from plv_clone.pipelines.build_fantasy_exports import calibrate_all
    calibrate_all(config=cfg)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.fantasy.scoring import LeagueScoring
from plv_clone.fantasy import hitter_points, pitcher_points
from plv_clone.utils.io import read_parquet
from plv_clone.utils.logging import get_logger
from plv_clone.utils.provenance import write_build_meta

logger = get_logger(__name__)

_SCORING_FILE = "league_scoring.json"


def calibrate_all(
    config: PipelineConfig | None = None,
    calibration_years: list[int] | None = None,
) -> None:
    """Run hitter and pitcher calibration. Saves JSON artifacts to models_dir."""
    cfg = config or get_config()
    hitter_points.calibrate(
        processed_dir=cfg.processed_dir,
        outputs_dir=cfg.outputs_dir,
        models_dir=cfg.models_dir,
        calibration_years=calibration_years,
    )
    pitcher_points.calibrate(
        processed_dir=cfg.processed_dir,
        outputs_dir=cfg.outputs_dir,
        models_dir=cfg.models_dir,
        calibration_years=calibration_years,
    )
    logger.info("Fantasy calibration complete.")


def run(
    year: int,
    config: PipelineConfig | None = None,
    scoring_path: str | Path | None = None,
    pa_per_game: float = 3.5,
    ip_per_start: float = 5.5,
    ip_per_app: float = 1.0,
    output_format: str = "both",
) -> dict[str, pd.DataFrame]:
    """Build fantasy-point leaderboard exports for *year*.

    Parameters
    ----------
    year         : Season year.
    config       : PipelineConfig (uses default if None).
    scoring_path : Path to league_scoring.json. Uses models_dir default if None.
    pa_per_game  : Playing-time assumption for hitters (default 3.5).
    ip_per_start : IP per start for SP fantasy projection (default 5.5).
    ip_per_app   : IP per appearance for RP fantasy projection (default 1.0).

    Returns dict mapping 'hitter_fantasy' and 'pitcher_fantasy' to DataFrames.
    """
    cfg = config or get_config()

    # ── Load scoring config ───────────────────────────────────────────────
    scoring_file = Path(scoring_path) if scoring_path else cfg.models_dir / _SCORING_FILE
    if scoring_file.exists():
        scoring = LeagueScoring.load(scoring_file)
        logger.info("Loaded league scoring from %s", scoring_file)
    else:
        scoring = LeagueScoring()
        scoring.save(scoring_file)
        logger.info("Created default league_scoring.json at %s", scoring_file)

    # ── Load calibration coefficients ─────────────────────────────────────
    h_coefs = hitter_points.load_calibration(cfg.models_dir)
    p_coefs = pitcher_points.load_calibration(cfg.models_dir)

    exports: dict[str, pd.DataFrame] = {}

    # ── Hitter fantasy ────────────────────────────────────────────────────
    hitter_path = cfg.outputs_dir / f"master_hitter_{year}.csv"
    if hitter_path.exists():
        logger.info("Building hitter fantasy export for year=%d …", year)
        hitters = pd.read_csv(hitter_path)

        # Fetch per-player SB rates; cache snapshot for reproducible re-runs
        try:
            _sb_cache = cfg.models_dir / f"sb_rates_{year}.csv"
            sb_data = _compute_sb_rates(year, cache_path=_sb_cache)
            if not sb_data.empty:
                hitters = hitters.merge(sb_data[["batter", "sb_per_pa_raw"]], on="batter", how="left")
        except Exception as e:
            logger.warning("Could not compute SB rates for year=%d: %s", year, e)

        hitters = hitter_points.project(hitters, scoring, coefs=h_coefs, pa_per_game=pa_per_game)
        hitters = hitters.sort_values("core_fp_per_pa", ascending=False).reset_index(drop=True)
        _write(hitters, cfg.outputs_dir / f"hitter_fantasy_{year}", output_format)
        exports["hitter_fantasy"] = hitters
        logger.info(
            "Hitter fantasy: %d players, core_fp range [%.3f, %.3f], full_fp range [%.3f, %.3f]",
            len(hitters),
            hitters["core_fp_per_pa"].min(), hitters["core_fp_per_pa"].max(),
            hitters["full_fp_per_pa"].min(), hitters["full_fp_per_pa"].max(),
        )
    else:
        logger.warning("master_hitter_%d.csv not found. Skipping hitter fantasy.", year)

    # ── Pitcher fantasy ───────────────────────────────────────────────────
    pitcher_path = cfg.outputs_dir / f"master_pitcher_{year}.csv"
    if pitcher_path.exists():
        logger.info("Building pitcher fantasy export for year=%d …", year)
        pitchers = pd.read_csv(pitcher_path)

        # Infer roles from PLV pitch data
        role_df = None
        plv_dir = cfg.processed_dir / f"plv_scores/year={year}"
        if plv_dir.exists():
            plv_df = read_parquet(plv_dir)
            role_df = pitcher_points.infer_roles(plv_df)

        rolling_p = None
        roll_path = cfg.outputs_dir / f"plv_rolling_{year}.csv"
        if roll_path.exists():
            rolling_p = pd.read_csv(roll_path, parse_dates=["date"])

        pitchers = pitcher_points.project(
            pitchers, rolling_p, scoring,
            coefs=p_coefs,
            ip_per_start=ip_per_start,
            ip_per_app=ip_per_app,
            role_df=role_df,
        )
        pitchers = pitchers.sort_values("fp_per_ip", ascending=False).reset_index(drop=True)
        _write(pitchers, cfg.outputs_dir / f"pitcher_fantasy_{year}", output_format)
        exports["pitcher_fantasy"] = pitchers
        logger.info("Pitcher fantasy: %d pitchers, fp_per_ip range [%.3f, %.3f]",
                    len(pitchers), pitchers["fp_per_ip"].min(), pitchers["fp_per_ip"].max())
    else:
        logger.warning("master_pitcher_%d.csv not found. Skipping pitcher fantasy.", year)

    # ── Provenance sidecar ────────────────────────────────────────────────
    write_build_meta(
        cfg.outputs_dir,
        year,
        suffix="_fantasy",
        exports=list(exports.keys()),
        extra={
            "pa_per_game": pa_per_game,
            "ip_per_start": ip_per_start,
            "ip_per_app": ip_per_app,
            "scoring_file": str(scoring_file),
        },
        models_dir=cfg.models_dir,
    )

    return exports


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_sb_rates(year: int, cache_path: Path | None = None) -> pd.DataFrame:
    """Fetch per-batter SB and PA from MLB Stats API for *year*.

    Returns DataFrame with columns: batter (MLBAM ID), sb_per_pa_raw, sb, pa_ev.
    The caller (project()) applies shrinkage toward league average.

    If *cache_path* is given, the result is persisted as a CSV there.
    On the next run with the same path, the cache is loaded instead of
    hitting the API — making fantasy export re-runs reproducible.
    For in-progress seasons the cache is refreshed if older than 7 days.
    """
    import time as _time

    if cache_path is not None and cache_path.exists():
        use_cache = True
        import datetime as _dt2
        if year >= _dt2.date.today().year:
            age_days = (_time.time() - cache_path.stat().st_mtime) / 86400
            if age_days > 7:
                use_cache = False
                logger.info("SB rate cache is %.1f days old — refreshing.", age_days)
        if use_cache:
            try:
                cached = pd.read_csv(cache_path)
                logger.info("SB rates loaded from cache (%d players, year=%d).", len(cached), year)
                return cached[["batter", "sb_per_pa_raw", "sb", "pa_ev"]]
            except Exception as exc:
                logger.warning("SB cache read failed (%s); re-fetching API.", exc)

    import requests
    url = (
        f"https://statsapi.mlb.com/api/v1/stats"
        f"?stats=season&group=hitting&season={year}&playerPool=ALL&limit=2000"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("MLB Stats API SB fetch failed for year=%d: %s", year, e)
        return pd.DataFrame(columns=["batter", "sb_per_pa_raw", "sb", "pa_ev"])

    splits = resp.json().get("stats", [{}])[0].get("splits", [])
    rows = []
    for s in splits:
        p   = s.get("player", {})
        pid = p.get("id")
        st  = s.get("stat", {})
        sb  = int(st.get("stolenBases", 0) or 0)
        pa  = int(st.get("plateAppearances", 0) or 0)
        if pid and pa > 0:
            rows.append({"batter": int(pid), "sb": sb, "pa_ev": pa})

    if not rows:
        logger.warning("No SB data returned from MLB Stats API for year=%d.", year)
        return pd.DataFrame(columns=["batter", "sb_per_pa_raw", "sb", "pa_ev"])

    result = pd.DataFrame(rows)
    result["sb_per_pa_raw"] = (result["sb"] / result["pa_ev"]).round(5)
    logger.info("SB rates loaded from MLB Stats API: %d players, year=%d", len(result), year)

    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            result[["batter", "sb_per_pa_raw", "sb", "pa_ev"]].to_csv(cache_path, index=False)
            logger.info("SB rate snapshot saved → %s", cache_path.name)
        except Exception as exc:
            logger.warning("Could not save SB rate snapshot: %s", exc)

    return result[["batter", "sb_per_pa_raw", "sb", "pa_ev"]]


def _write(df: pd.DataFrame, base_path: Path, fmt: str) -> None:
    if df.empty:
        return
    base_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("parquet", "both"):
        df.to_parquet(str(base_path) + ".parquet", index=False)
    if fmt in ("csv", "both"):
        df.to_csv(str(base_path) + ".csv", index=False)
    logger.debug("Wrote %s — %d rows", base_path.name, len(df))
