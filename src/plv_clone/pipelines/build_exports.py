"""
Pipeline: Build clean leaderboard exports for pitchers and hitters.

Produces the following outputs under data/outputs/:

  Pitcher exports (from PLV scores):
    plv_leaderboard_{year}.csv / .parquet          -- season averages (existing)
    plv_by_pitch_type_{year}.csv / .parquet        -- per pitch type (existing)
    plv_rolling_{year}.csv / .parquet              -- 30-day rolling PLV trends

  Hitter exports (from Process+ scores):
    process_plus_leaderboard_{year}.csv / .parquet -- season averages (existing)
    process_plus_rolling_{year}.csv / .parquet     -- 30-day rolling trends

  Unified master export:
    master_hitter_{year}.csv / .parquet            -- Process+ joined with batting surface stats
    master_pitcher_{year}.csv / .parquet           -- PLV joined with plate-discipline surface stats

Usage:
    from plv_clone.pipelines.build_exports import run
    exports = run(year=2024, config=cfg)
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pandas as pd

from plv_clone.config import PipelineConfig, get_config
from plv_clone.data.player_positions import (
    PositionConfig,
    build_position_map,
    enrich_hitters,
    enrich_pitchers,
    validate_positions,
)
from plv_clone.utils.io import read_parquet
from plv_clone.utils.logging import get_logger
from plv_clone.utils.provenance import write_build_meta

logger = get_logger(__name__)

# Rolling window for trend outputs (calendar days)
_ROLLING_DAYS = 30
# Minimum pitches in a rolling window to report a value
_ROLLING_MIN_PITCHES = 20
# Minimum PA in a rolling window for hitters
_ROLLING_MIN_PA = 10

# ── Event sets for rolling fantasy rate computation ───────────────────────────
_K_EVENTS_RFP  = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
_SB_EVENTS_RFP = {"stolen_base_2b", "stolen_base_3b", "stolen_base_home"}
_H_EVENTS_RFP  = {"single", "double", "triple", "home_run"}
_TB_MAP_RFP    = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
_NON_PA_RFP    = {
    "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "wild_pitch", "passed_ball", "balk",
}
_PITCHES_PER_IP_RFP = 15.0
_FIP_CONSTANT_RFP   = 3.17


def run(
    year: int,
    config: PipelineConfig | None = None,
    output_format: str = "both",
) -> dict[str, pd.DataFrame]:
    """Build all leaderboard and trend exports for *year*.

    Args:
        year:          Season year (e.g. 2024).
        config:        PipelineConfig instance (uses get_config() if None).
        output_format: 'parquet', 'csv', or 'both'.

    Returns:
        Dict mapping export name → DataFrame.
    """
    cfg = config or get_config()
    exports: dict[str, pd.DataFrame] = {}

    # ── Position map (fetched once per year, cached in models_dir) ────────
    # Refresh the cache weekly for in-progress seasons so position changes
    # (e.g. new call-ups, role switches) appear in exports without a manual
    # cache deletion.
    _cache_age_days = 7 if year >= _dt.date.today().year else None
    try:
        position_map = build_position_map(
            year,
            config=PositionConfig(),
            cache_dir=cfg.models_dir,
            max_cache_age_days=_cache_age_days,
        )
    except Exception as e:
        logger.warning("Position map build failed for year=%d: %s", year, e)
        position_map = None

    # ── Pitcher exports ───────────────────────────────────────────────────
    plv_dir = cfg.processed_dir / "plv_scores" / f"year={year}"
    if plv_dir.exists():
        logger.info("Building pitcher exports for year=%d …", year)
        plv_df = read_parquet(plv_dir)
        plv_df = _ensure_game_date(plv_df)

        rolling_pitcher = build_rolling_plv(plv_df, window_days=_ROLLING_DAYS)
        exports["plv_rolling"] = rolling_pitcher
        _write(rolling_pitcher, cfg.outputs_dir / f"plv_rolling_{year}", output_format)

        _pitcher_cache = cfg.models_dir / f"pitcher_names_{year}.json"
        _pitcher_cache_age = 7 if year >= _dt.date.today().year else None
        pitcher_name_map = _build_pitcher_name_map(
            plv_df["pitcher"].dropna().astype(int).unique().tolist(),
            cache_path=_pitcher_cache,
            max_cache_age_days=_pitcher_cache_age,
        )
        master_pitcher = build_master_pitcher(
            plv_df,
            min_pitches=cfg.min_pitches_plv,
            position_map=position_map,
            pitcher_name_map=pitcher_name_map,
        )
        exports["master_pitcher"] = master_pitcher
        _write(master_pitcher, cfg.outputs_dir / f"master_pitcher_{year}", output_format)
    else:
        logger.warning("No PLV scores found for year=%d. Skipping pitcher exports.", year)

    # ── Hitter exports ────────────────────────────────────────────────────
    pp_dir = cfg.processed_dir / "process_plus_scores" / f"year={year}"
    if pp_dir.exists():
        logger.info("Building hitter exports for year=%d …", year)
        pp_df = read_parquet(pp_dir)
        pp_df = _ensure_game_date(pp_df)

        # Build player name map once for all unique batters (used in both rolling and master)
        _name_cache = cfg.models_dir / f"batter_names_{year}.json"
        _name_cache_age = 7 if year >= _dt.date.today().year else None
        batter_name_map = _build_batter_name_map(
            pp_df["batter"].dropna().astype(int).unique().tolist(),
            cache_path=_name_cache,
            max_cache_age_days=_name_cache_age,
        )

        rolling_hitter = build_rolling_process_plus(pp_df, window_days=_ROLLING_DAYS, batter_name_map=batter_name_map)
        exports["process_plus_rolling"] = rolling_hitter
        _write(rolling_hitter, cfg.outputs_dir / f"process_plus_rolling_{year}", output_format)

        master_hitter = build_master_hitter(pp_df, min_pa=cfg.min_pa_process, batter_name_map=batter_name_map, position_map=position_map)

        exports["master_hitter"] = master_hitter
        if master_hitter.empty:
            logger.info(
                "No hitters qualify at min_pa=%d for year=%d — writing empty export. "
                "Re-run build-exports once enough PA accumulates.",
                cfg.min_pa_process, year,
            )
            # Write explicitly even when empty so any stale artifact on disk
            # is overwritten. The dashboard treats a 0-row CSV as "no data"
            # rather than falling back to a prior run's metrics.
            cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
            master_hitter.to_csv(
                cfg.outputs_dir / f"master_hitter_{year}.csv", index=False
            )
        else:
            _write(master_hitter, cfg.outputs_dir / f"master_hitter_{year}", output_format)
    else:
        logger.warning("No Process+ scores found for year=%d. Skipping hitter exports.", year)

    # Validate name resolution and warn on unresolved IDs
    validate_player_names(
        master_hitter=exports.get("master_hitter"),
        master_pitcher=exports.get("master_pitcher"),
    )

    # Validate position enrichment quality
    mh = exports.get("master_hitter")
    if mh is not None and "primary_position" in mh.columns:
        validate_positions(mh, id_col="batter")

    # ── Provenance sidecar ────────────────────────────────────────────────
    _source_dates: dict = {}
    if "master_hitter" in exports and not exports["master_hitter"].empty:
        _mh = exports["master_hitter"]
        if "game_date" in _mh.columns:
            _source_dates["hitter_date_min"] = str(_mh["game_date"].min())
            _source_dates["hitter_date_max"] = str(_mh["game_date"].max())
    if "master_pitcher" in exports and not exports["master_pitcher"].empty:
        _mp = exports["master_pitcher"]
        if "game_date" in _mp.columns:
            _source_dates["pitcher_date_min"] = str(_mp["game_date"].min())
            _source_dates["pitcher_date_max"] = str(_mp["game_date"].max())
    # rolling exports carry a date column — use it for freshness
    for _key, _date_key in (("process_plus_rolling", "hitter_rolling_max_date"),
                             ("plv_rolling", "pitcher_rolling_max_date")):
        _rdf = exports.get(_key)
        if _rdf is not None and not _rdf.empty and "date" in _rdf.columns:
            _source_dates[_date_key] = str(pd.to_datetime(_rdf["date"]).max().date())

    write_build_meta(
        cfg.outputs_dir,
        year,
        exports=list(exports.keys()),
        extra={
            "min_pa_process": cfg.min_pa_process,
            "min_pitches_plv": cfg.min_pitches_plv,
            "rolling_days": _ROLLING_DAYS,
            **_source_dates,
        },
        models_dir=cfg.models_dir,
    )

    logger.info("Exports written to %s", cfg.outputs_dir)
    return exports


# ── Pitcher: rolling PLV ──────────────────────────────────────────────────────

def build_rolling_plv(
    plv_df: pd.DataFrame,
    window_days: int = 30,
    min_pitches: int = _ROLLING_MIN_PITCHES,
) -> pd.DataFrame:
    """Build rolling *window_days*-day PLV for each pitcher.

    Returns a long DataFrame with one row per (pitcher, date_window_end).
    """
    if "game_date" not in plv_df.columns:
        logger.warning("game_date missing from PLV scores; skipping rolling PLV.")
        return pd.DataFrame()

    plv_df = plv_df.copy()
    plv_df["game_date"] = pd.to_datetime(plv_df["game_date"])

    rows = []
    dates = plv_df["game_date"].sort_values().unique()

    for pitcher_id, grp in plv_df.groupby("pitcher"):
        grp = grp.sort_values("game_date")
        name = grp["player_name"].iloc[0] if "player_name" in grp.columns else str(pitcher_id)

        for window_end in dates:
            window_start = window_end - pd.Timedelta(days=window_days - 1)
            window = grp[(grp["game_date"] >= window_start) & (grp["game_date"] <= window_end)]
            if len(window) < min_pitches:
                continue
            row: dict = {
                "pitcher": pitcher_id,
                "player_name": name,
                "date": window_end,
                "pitches": len(window),
                "plv": round(window["plv"].mean(), 3),
                "plv_raw": round(window["plv_raw"].mean(), 5),
                "swing_rate": round(window["p_swing"].mean(), 4) if "p_swing" in window.columns else None,
                "whiff_rate": round(window["p_whiff_given_swing"].mean(), 4) if "p_whiff_given_swing" in window.columns else None,
                "called_strike_rate": round(window["p_cs_given_take"].mean(), 4) if "p_cs_given_take" in window.columns else None,
            }
            # Rolling event-based rate stats for fantasy computation
            if "events" in window.columns:
                ev_all = window.dropna(subset=["events"])
                ev_all = ev_all[ev_all["events"].astype(str).str.strip() != ""]
                ev = ev_all[~ev_all["events"].isin(_NON_PA_RFP)]
                ip_est = max(len(window) / _PITCHES_PER_IP_RFP, 0.1)
                k_cnt   = ev["events"].isin(_K_EVENTS_RFP).sum()
                bb_cnt  = ev["events"].isin({"walk", "intent_walk"}).sum()
                hbp_cnt = (ev["events"] == "hit_by_pitch").sum()
                h_cnt   = ev["events"].isin(_H_EVENTS_RFP).sum()
                hr_cnt  = (ev["events"] == "home_run").sum()
                fip = (13 * hr_cnt / ip_est + 3 * (bb_cnt + hbp_cnt) / ip_est
                       - 2 * k_cnt / ip_est + _FIP_CONSTANT_RFP)
                row["rolling_k_ip"]  = round(k_cnt  / ip_est, 4)
                row["rolling_bb_ip"] = round(bb_cnt / ip_est, 4)
                row["rolling_h_ip"]  = round(h_cnt  / ip_est, 4)
                row["rolling_er_ip"] = round(max(fip / 9, 0.0), 4)
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    logger.info("Rolling PLV: %d pitcher-window rows (window=%d days)", len(df), window_days)
    return df


# ── Hitter: rolling Process+ ──────────────────────────────────────────────────

def build_rolling_process_plus(
    pp_df: pd.DataFrame,
    window_days: int = 30,
    min_pa: int = _ROLLING_MIN_PA,
    batter_name_map: dict | None = None,
) -> pd.DataFrame:
    """Build rolling *window_days*-day Process+ for each hitter.

    Returns a long DataFrame with one row per (batter, date_window_end).
    """
    if "game_date" not in pp_df.columns:
        logger.warning("game_date missing from Process+ scores; skipping rolling trends.")
        return pd.DataFrame()

    pp_df = pp_df.copy()
    pp_df["game_date"] = pd.to_datetime(pp_df["game_date"])

    rows = []
    dates = pp_df["game_date"].sort_values().unique()

    for batter_id, grp in pp_df.groupby("batter"):
        grp = grp.sort_values("game_date")
        name = (batter_name_map or {}).get(int(batter_id), str(batter_id))

        for window_end in dates:
            window_start = window_end - pd.Timedelta(days=window_days - 1)
            window = grp[(grp["game_date"] >= window_start) & (grp["game_date"] <= window_end)]

            # Approximate PA count from unique (game_pk, at_bat_number)
            if "game_pk" in window.columns and "at_bat_number" in window.columns:
                pa = window[["game_pk", "at_bat_number"]].drop_duplicates().shape[0]
            else:
                pa = max(1, len(window) // 4)

            if pa < min_pa:
                continue

            row: dict = {
                "batter": batter_id,
                "batter_name": name,
                "date": window_end,
                "pa": pa,
                "pitches": len(window),
            }
            for comp in ("discipline_value", "contact_value", "power_value"):
                if comp in window.columns:
                    vals = window[comp].dropna()
                    row[f"{comp}_mean"] = round(float(vals.mean()), 5) if len(vals) > 0 else None

            # Rolling event-based rate stats for fantasy computation
            if "events" in window.columns:
                ev_all = window.dropna(subset=["events"])
                ev_all = ev_all[ev_all["events"].astype(str).str.strip() != ""]
                sb_cnt = ev_all["events"].isin(_SB_EVENTS_RFP).sum()
                ev = ev_all[~ev_all["events"].isin(_NON_PA_RFP)]
                pa_ev = max(len(ev), 1)
                row["rolling_k_pa"]   = round(ev["events"].isin(_K_EVENTS_RFP).sum() / pa_ev, 4)
                row["rolling_bb_pa"]  = round(ev["events"].isin({"walk", "intent_walk"}).sum() / pa_ev, 4)
                row["rolling_hbp_pa"] = round((ev["events"] == "hit_by_pitch").sum() / pa_ev, 4)
                row["rolling_sb_pa"]  = round(sb_cnt / pa_ev, 4)
                row["rolling_tb_pa"]  = round(ev["events"].map(_TB_MAP_RFP).fillna(0).sum() / pa_ev, 4)
                row["rolling_h_pa"]   = round(ev["events"].isin(_H_EVENTS_RFP).sum() / pa_ev, 4)
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    logger.info(
        "Rolling Process+: %d hitter-window rows (window=%d days)", len(df), window_days
    )
    return df


# ── Master pitcher leaderboard ────────────────────────────────────────────────

def build_master_pitcher(
    plv_df: pd.DataFrame,
    min_pitches: int = 100,
    position_map=None,
    pitcher_name_map: dict | None = None,
) -> pd.DataFrame:
    """Season-level pitcher leaderboard with PLV + plate-discipline surface stats.

    Includes: PLV, Swing%, Whiff%, CS%, xwOBA-in-play, pitch mix.
    """
    import duckdb

    plv_df = plv_df.copy()
    conn = duckdb.connect()
    conn.register("plv", plv_df)

    lb = conn.execute(f"""
        SELECT
            pitcher,
            ANY_VALUE(player_name)                     AS player_name,
            COUNT(*)                                   AS pitches,
            AVG(plv)                                   AS plv,
            STDDEV(plv)                                AS plv_std,
            AVG(plv_raw)                               AS plv_raw,
            AVG(p_swing)                               AS swing_pct,
            AVG(p_whiff_given_swing)                   AS whiff_pct,
            AVG(p_cs_given_take)                       AS cs_pct,
            AVG(e_xwoba_in_play)                       AS xwoba_model,
            AVG(p_contact_given_swing)                 AS contact_pct,
            PERCENT_RANK() OVER (ORDER BY AVG(plv))    AS plv_pctile
        FROM plv
        GROUP BY pitcher
        HAVING COUNT(*) >= {min_pitches}
        ORDER BY plv DESC
    """).df()
    conn.close()

    # Round display columns
    for col in ("plv", "plv_std", "plv_raw", "swing_pct", "whiff_pct", "cs_pct",
                "xwoba_model", "contact_pct"):
        if col in lb.columns:
            lb[col] = lb[col].round(3)
    lb["plv_pctile"] = lb["plv_pctile"].mul(100).round(1)

    # Apply pre-built name map if provided (avoids live API call on re-runs)
    import re as _re
    if pitcher_name_map:
        lb["player_name"] = lb.apply(
            lambda r: pitcher_name_map.get(int(r["pitcher"]), r["player_name"]),
            axis=1,
        )

    # Fix any remaining null or numeric player_name via MLB Stats API fallback
    null_mask = lb["player_name"].isna() | lb["player_name"].astype(str).str.match(r"^\d+$")
    if null_mask.any():
        missing_ids = lb.loc[null_mask, "pitcher"].astype(int).tolist()
        logger.info("Fixing %d pitcher(s) with missing player_name via MLB Stats API.", len(missing_ids))
        try:
            import requests
            ids_param = ",".join(str(i) for i in missing_ids)
            url = (f"https://statsapi.mlb.com/api/v1/people"
                   f"?personIds={ids_param}&fields=people,id,fullName")
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            api_map = {
                int(p["id"]): p["fullName"]
                for p in resp.json().get("people", [])
                if p.get("id") and p.get("fullName")
            }
            lb["player_name"] = lb.apply(
                lambda r: api_map.get(int(r["pitcher"]), r["player_name"])
                if (pd.isna(r["player_name"]) or _re.match(r"^\d+$", str(r["player_name"])))
                else r["player_name"],
                axis=1,
            )
            logger.info("Resolved %d pitcher name(s) via MLB Stats API.", len(api_map))
        except Exception as e:
            logger.warning("Pitcher name MLB Stats API fallback failed: %s", e)

    lb = enrich_pitchers(lb, id_col="pitcher")

    logger.info("Master pitcher leaderboard: %d qualified pitchers", len(lb))
    return lb


# ── Master hitter leaderboard ─────────────────────────────────────────────────

def build_master_hitter(
    pp_df: pd.DataFrame,
    min_pa: int = 150,
    batter_name_map: dict | None = None,
    position_map=None,
) -> pd.DataFrame:
    """Season-level hitter leaderboard with Process+ components + surface stats.

    Includes: Process+, Discipline+, Contact+, Power+, contact rate, chase rate,
    swing rate, xwOBA actual vs expected.
    """
    from plv_clone.models.process_plus_model import ProcessPlusModel
    from plv_clone.config import get_config

    cfg = get_config()
    pp_model = ProcessPlusModel.load(cfg.models_dir)
    hitter_lb = pp_model.aggregate_hitters(pp_df, min_pa=min_pa)

    # Surface stats from pitch data
    if "game_pk" in pp_df.columns and "at_bat_number" in pp_df.columns:
        pa_counts = (
            pp_df.dropna(subset=["batter", "game_pk", "at_bat_number"])
            .groupby("batter")[["game_pk", "at_bat_number"]]
            .apply(lambda x: x.drop_duplicates().shape[0])
            .rename("pa_pitches")
            .reset_index()
        )
    else:
        pa_counts = pd.DataFrame({"batter": [], "pa_pitches": []})

    surface_cols = ["batter"]
    for col in ("is_swing", "batter_chase_rate", "batter_contact_rate",
                 "estimated_woba_using_speedangle",
                 "is_in_play", "is_whiff"):
        if col in pp_df.columns:
            surface_cols.append(col)

    surface = pp_df[surface_cols].groupby("batter").agg(
        **{
            col: (col, "mean") for col in surface_cols if col != "batter"
        }
    ).reset_index()

    # xwOBA actual from in-play pitches only
    if "estimated_woba_using_speedangle" in pp_df.columns and "is_in_play" in pp_df.columns:
        xwoba_ip = (
            pp_df[pp_df["is_in_play"].astype(bool) & pp_df["estimated_woba_using_speedangle"].notna()]
            .groupby("batter")["estimated_woba_using_speedangle"]
            .mean()
            .rename("xwoba_actual")
            .reset_index()
        )
        surface = surface.drop(columns=["estimated_woba_using_speedangle"], errors="ignore")
        surface = surface.merge(xwoba_ip, on="batter", how="left")

    # Rename surface stats for clarity
    rename_map = {
        "is_swing": "swing_pct",
        "batter_chase_rate": "chase_pct",
        "batter_contact_rate": "contact_pct",
        "is_in_play": "in_play_pct",
        "is_whiff": "whiff_pct",
    }
    surface = surface.rename(columns=rename_map)

    # Merge everything
    master = hitter_lb.merge(surface, on="batter", how="left")
    master = master.merge(pa_counts, on="batter", how="left")

    # xwOBA above expected = power_raw (mean of actual-expected xwOBA on in-play)
    if "power_raw" in master.columns:
        master["xwoba_vs_expected"] = master["power_raw"].round(3)

    # Round surface stat columns
    for col in ("swing_pct", "chase_pct", "contact_pct", "xwoba_actual",
                "xwoba_model", "in_play_pct", "whiff_pct", "xwoba_vs_expected"):
        if col in master.columns:
            master[col] = master[col].round(3)

    # Add batter names from pre-built map (avoids redundant pybaseball call).
    # Be robust to both int-keyed and str-keyed maps (JSON cache always loads as str-keyed).
    name_map = batter_name_map or {}
    if name_map:
        # Detect key type and normalize to a single int-keyed dict for the .map() below
        sample_key = next(iter(name_map.keys()))
        if isinstance(sample_key, str):
            name_map = {int(k): v for k, v in name_map.items() if str(k).lstrip('-').isdigit()}
    master["batter_name"] = master["batter"].astype(int).map(name_map).fillna(master["batter"].astype(str))

    # Enrich with position data
    if position_map is not None and not position_map.empty:
        master = enrich_hitters(master, position_map, id_col="batter")

    # Put name first
    pos_cols_order = ["primary_position", "fantasy_positions", "fantasy_positions_display",
                      "is_multi_position", "position_count"]
    front = ["batter_name"] + [c for c in pos_cols_order if c in master.columns]
    rest  = [c for c in master.columns if c not in front]
    master = master[front + rest]

    master = master.sort_values("process_plus", ascending=False).reset_index(drop=True)
    logger.info("Master hitter leaderboard: %d qualified hitters", len(master))
    return master


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_batter_name_map(
    batter_ids: list[int],
    cache_path: Path | None = None,
    max_cache_age_days: int | None = None,
) -> dict[int, str]:
    """Return {mlbam_id: 'First Last'} for all provided batter IDs.

    Primary source: Chadwick Bureau register via pybaseball.
    Fallback for any missing IDs: MLB Stats API (handles recent debuts).

    If *cache_path* is given, the resolved map is persisted there as JSON.
    On subsequent calls with the same path, the cache is used if it is
    younger than *max_cache_age_days* (or always, if that is None).
    This makes export re-runs reproducible without repeated API calls.
    """
    import time as _time

    # ── Load from cache if fresh ──────────────────────────────────────────
    if cache_path is not None and cache_path.exists():
        use_cache = True
        if max_cache_age_days is not None:
            age_days = (_time.time() - cache_path.stat().st_mtime) / 86400
            if age_days > max_cache_age_days:
                use_cache = False
                logger.info("Batter name cache is %.1f days old — refreshing.", age_days)
        if use_cache:
            try:
                cached = {int(k): v for k, v in json.loads(cache_path.read_text()).items()}
                logger.info("Batter names loaded from cache (%d entries).", len(cached))
                return cached
            except Exception as exc:
                logger.warning("Cache read failed (%s); re-resolving names.", exc)

    name_map: dict[int, str] = {}

    # ── Primary: Chadwick register ────────────────────────────────────────
    try:
        from pybaseball import playerid_reverse_lookup
        logger.info("Gathering player lookup table. This may take a moment.")
        lookup = playerid_reverse_lookup(batter_ids, key_type="mlbam")
        lookup["batter_name"] = lookup["name_first"].str.title() + " " + lookup["name_last"].str.title()
        name_map.update(dict(zip(lookup["key_mlbam"].astype(int), lookup["batter_name"])))
    except Exception as e:
        logger.warning("Chadwick player lookup failed: %s", e)

    # ── Fallback: MLB Stats API for IDs not in Chadwick ───────────────────
    missing = [bid for bid in batter_ids if bid not in name_map]
    if missing:
        logger.info("Looking up %d player(s) not in Chadwick via MLB Stats API.", len(missing))
        try:
            import requests
            ids_param = ",".join(str(i) for i in missing)
            url = f"https://statsapi.mlb.com/api/v1/people?personIds={ids_param}&fields=people,id,fullName"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            for person in resp.json().get("people", []):
                pid = person.get("id")
                name = person.get("fullName")
                if pid and name:
                    name_map[int(pid)] = name
        except Exception as e:
            logger.warning("MLB Stats API fallback failed: %s", e)

    # ── Persist snapshot so future re-runs are reproducible ──────────────
    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({str(k): v for k, v in name_map.items()}, indent=2))
            logger.info("Batter name snapshot saved → %s", cache_path.name)
        except Exception as exc:
            logger.warning("Could not save batter name snapshot: %s", exc)

    return name_map


def _build_pitcher_name_map(
    pitcher_ids: list[int],
    cache_path: Path | None = None,
    max_cache_age_days: int | None = None,
) -> dict[int, str]:
    """Return {mlbam_id: 'First Last'} for all provided pitcher IDs.

    Primary source: Chadwick Bureau register via pybaseball.
    Fallback for any missing IDs: MLB Stats API.

    Cache behaviour mirrors _build_batter_name_map — see its docstring.
    """
    import time as _time

    if cache_path is not None and cache_path.exists():
        use_cache = True
        if max_cache_age_days is not None:
            age_days = (_time.time() - cache_path.stat().st_mtime) / 86400
            if age_days > max_cache_age_days:
                use_cache = False
                logger.info("Pitcher name cache is %.1f days old — refreshing.", age_days)
        if use_cache:
            try:
                cached = {int(k): v for k, v in json.loads(cache_path.read_text()).items()}
                logger.info("Pitcher names loaded from cache (%d entries).", len(cached))
                return cached
            except Exception as exc:
                logger.warning("Pitcher name cache read failed (%s); re-resolving.", exc)

    name_map: dict[int, str] = {}

    try:
        from pybaseball import playerid_reverse_lookup
        logger.info("Gathering pitcher lookup table via Chadwick register.")
        lookup = playerid_reverse_lookup(pitcher_ids, key_type="mlbam")
        lookup["player_name"] = lookup["name_first"].str.title() + " " + lookup["name_last"].str.title()
        name_map.update(dict(zip(lookup["key_mlbam"].astype(int), lookup["player_name"])))
    except Exception as e:
        logger.warning("Chadwick pitcher lookup failed: %s", e)

    missing = [pid for pid in pitcher_ids if pid not in name_map]
    if missing:
        logger.info("Looking up %d pitcher(s) not in Chadwick via MLB Stats API.", len(missing))
        try:
            import requests
            ids_param = ",".join(str(i) for i in missing)
            url = f"https://statsapi.mlb.com/api/v1/people?personIds={ids_param}&fields=people,id,fullName"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            for person in resp.json().get("people", []):
                pid = person.get("id")
                name = person.get("fullName")
                if pid and name:
                    name_map[int(pid)] = name
        except Exception as e:
            logger.warning("MLB Stats API pitcher fallback failed: %s", e)

    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({str(k): v for k, v in name_map.items()}, indent=2))
            logger.info("Pitcher name snapshot saved → %s", cache_path.name)
        except Exception as exc:
            logger.warning("Could not save pitcher name snapshot: %s", exc)

    return name_map


def validate_player_names(
    master_hitter: pd.DataFrame | None = None,
    master_pitcher: pd.DataFrame | None = None,
    threshold: float = 0.05,
    strict: bool = False,
) -> dict:
    """Check for unresolved player IDs (numeric strings in name columns).

    Parameters
    ----------
    master_hitter  : DataFrame with batter_name column.
    master_pitcher : DataFrame with player_name column.
    threshold      : Fraction of unresolved IDs that triggers a warning.
    strict         : If True, raises ValueError when threshold is exceeded.

    Returns dict with counts: unresolved_hitters, total_hitters,
    unresolved_pitchers, total_pitchers.
    """
    import re as _re
    results: dict = {}

    if master_hitter is not None and "batter_name" in master_hitter.columns:
        numeric_mask = master_hitter["batter_name"].astype(str).str.match(r"^\d+$")
        n_bad   = int(numeric_mask.sum())
        n_total = len(master_hitter)
        results["unresolved_hitters"] = n_bad
        results["total_hitters"]      = n_total
        if n_bad > 0:
            ids = master_hitter.loc[numeric_mask, "batter"].tolist()
            logger.warning("Unresolved hitter IDs: %d/%d (%.1f%%) — %s",
                           n_bad, n_total, 100 * n_bad / max(n_total, 1), ids[:20])
            if strict and n_bad > threshold * n_total:
                raise ValueError(f"Too many unresolved hitter IDs: {n_bad}/{n_total}")

    if master_pitcher is not None and "player_name" in master_pitcher.columns:
        numeric_mask = master_pitcher["player_name"].astype(str).str.match(r"^\d+$")
        n_bad   = int(numeric_mask.sum())
        n_total = len(master_pitcher)
        results["unresolved_pitchers"] = n_bad
        results["total_pitchers"]      = n_total
        if n_bad > 0:
            ids = master_pitcher.loc[numeric_mask, "pitcher"].tolist()
            logger.warning("Unresolved pitcher IDs: %d/%d (%.1f%%) — %s",
                           n_bad, n_total, 100 * n_bad / max(n_total, 1), ids[:20])
            if strict and n_bad > threshold * n_total:
                raise ValueError(f"Too many unresolved pitcher IDs: {n_bad}/{n_total}")

    return results


def _ensure_game_date(df: pd.DataFrame) -> pd.DataFrame:
    if "game_date" not in df.columns:
        logger.warning("game_date column not found. Rolling exports will be empty.")
    return df


def _write(df: pd.DataFrame, base_path: Path, fmt: str) -> None:
    if df.empty:
        return
    base_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("parquet", "both"):
        df.to_parquet(str(base_path) + ".parquet", index=False)
    if fmt in ("csv", "both"):
        df.to_csv(str(base_path) + ".csv", index=False)
    logger.debug("Wrote %s (.%s) — %d rows", base_path.name, fmt, len(df))
