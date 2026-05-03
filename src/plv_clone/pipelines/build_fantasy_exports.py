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

        try:
            _hbp_cache = cfg.models_dir / f"hbp_rates_{year}.csv"
            hbp_data = _compute_hbp_rates(year, cache_path=_hbp_cache)
            if not hbp_data.empty:
                hitters = hitters.merge(hbp_data[["batter", "hbp_per_pa_raw"]], on="batter", how="left")
        except Exception as e:
            logger.warning("Could not compute HBP rates for year=%d: %s", year, e)

        # Merge Pitcher List hitter metrics (pl_dv, pl_odv, pl_process) when available
        _pl_hitter_ref = Path("data/reference/pitcher_list") / f"pl_plv_hitters_{year}.xlsx"
        if _pl_hitter_ref.exists():
            try:
                _pl_h = pd.read_excel(_pl_hitter_ref, usecols=["MLBAMID", "Decision\nValue+", "oDV+", "Process+"])
                _pl_h.columns = [c.strip().replace("\n", " ") for c in _pl_h.columns]
                _pl_h = _pl_h.rename(columns={
                    "MLBAMID": "batter",
                    "Decision Value+": "pl_dv",
                    "oDV+": "pl_odv",
                    "Process+": "pl_process",
                })
                hitters = hitters.merge(_pl_h, on="batter", how="left")
                logger.info("Merged PL hitter metrics (pl_dv/pl_odv/pl_process) from %s", _pl_hitter_ref.name)
            except Exception as e:
                logger.warning("Could not merge PL hitter reference for year=%d: %s", year, e)

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

        # Merge pl_plv / pl_pla if available
        _pl_plv_path = cfg.outputs_dir / f"pl_plv_{year}.csv"
        if _pl_plv_path.exists():
            try:
                _pl_p = pd.read_csv(_pl_plv_path, usecols=["pitcher", "pl_plv", "pl_pla"])
                _pl_p["pitcher"] = _pl_p["pitcher"].astype(pitchers["pitcher"].dtype)
                pitchers = pitchers.merge(_pl_p, on="pitcher", how="left")
                logger.info(
                    "Merged pl_plv/pl_pla into pitcher fantasy from %s (%d matched)",
                    _pl_plv_path.name, pitchers["pl_plv"].notna().sum(),
                )
            except Exception as e:
                logger.warning("Could not merge pl_plv scores into pitcher fantasy: %s", e)

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


def _compute_hbp_rates(year: int, cache_path: Path | None = None) -> pd.DataFrame:
    """Fetch per-batter HBP and PA from MLB Stats API for *year*.

    Returns DataFrame with columns: batter (MLBAM ID), hbp_per_pa_raw, hbp, pa_ev.
    The caller (hitter_points.project) applies shrinkage toward league average
    (_HBP_SHRINK_PA = 250 PA) since HBP rate has YoY stability r=0.322.

    Cache is refreshed every 7 days for in-progress seasons.
    """
    import time as _time

    if cache_path is not None and cache_path.exists():
        use_cache = True
        import datetime as _dt3
        if year >= _dt3.date.today().year:
            age_days = (_time.time() - cache_path.stat().st_mtime) / 86400
            if age_days > 7:
                use_cache = False
                logger.info("HBP rate cache is %.1f days old — refreshing.", age_days)
        if use_cache:
            try:
                cached = pd.read_csv(cache_path)
                logger.info("HBP rates loaded from cache (%d players, year=%d).", len(cached), year)
                return cached[["batter", "hbp_per_pa_raw", "hbp", "pa_ev"]]
            except Exception as exc:
                logger.warning("HBP cache read failed (%s); re-fetching API.", exc)

    import requests
    url = (
        f"https://statsapi.mlb.com/api/v1/stats"
        f"?stats=season&group=hitting&season={year}&playerPool=ALL&limit=2000"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("MLB Stats API HBP fetch failed for year=%d: %s", year, e)
        return pd.DataFrame(columns=["batter", "hbp_per_pa_raw", "hbp", "pa_ev"])

    splits = resp.json().get("stats", [{}])[0].get("splits", [])
    rows = []
    for s in splits:
        p   = s.get("player", {})
        pid = p.get("id")
        st  = s.get("stat", {})
        hbp = int(st.get("hitByPitch", 0) or 0)
        pa  = int(st.get("plateAppearances", 0) or 0)
        if pid and pa > 0:
            rows.append({"batter": int(pid), "hbp": hbp, "pa_ev": pa})

    if not rows:
        logger.warning("No HBP data returned from MLB Stats API for year=%d.", year)
        return pd.DataFrame(columns=["batter", "hbp_per_pa_raw", "hbp", "pa_ev"])

    result = pd.DataFrame(rows)
    result["hbp_per_pa_raw"] = (result["hbp"] / result["pa_ev"]).round(5)
    logger.info("HBP rates loaded from MLB Stats API: %d players, year=%d", len(result), year)

    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            result[["batter", "hbp_per_pa_raw", "hbp", "pa_ev"]].to_csv(cache_path, index=False)
            logger.info("HBP rate snapshot saved → %s", cache_path.name)
        except Exception as exc:
            logger.warning("Could not save HBP rate snapshot: %s", exc)

    return result[["batter", "hbp_per_pa_raw", "hbp", "pa_ev"]]


def _write(df: pd.DataFrame, base_path: Path, fmt: str) -> None:
    if df.empty:
        return
    base_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("parquet", "both"):
        df.to_parquet(str(base_path) + ".parquet", index=False)
    if fmt in ("csv", "both"):
        df.to_csv(str(base_path) + ".csv", index=False)
    logger.debug("Wrote %s — %d rows", base_path.name, len(df))
