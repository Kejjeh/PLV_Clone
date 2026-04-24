"""
PLV + Process+ Fantasy Dashboard — Streamlit app.

Unofficial public-data clone. Not affiliated with Pitcher List.

Launch:
    streamlit run app/dashboard.py

Reads from data/outputs/ — run `plv build-exports <year>` and
`plv build-target-boards <year>` first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import os

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Anchor cwd to project root so config relative paths resolve correctly
# regardless of where `streamlit run` was invoked from.
os.chdir(ROOT)

from plv_clone.config import get_config
from plv_clone.utils.provenance import read_build_meta
from plv_clone.utils.season_stage import infer_stage, get_thresholds


# ── Scatter helper ────────────────────────────────────────────────────────────
def _scatter_hitters(h: pd.DataFrame, name_col: str) -> None:
    if "decision_plus" not in h.columns or "power_plus" not in h.columns:
        return
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 6))
        ax.scatter(h["decision_plus"], h["power_plus"], alpha=0.35, s=18, color="#555", zorder=2)
        top_label = h.nlargest(12, "process_plus")
        for _, r in top_label.iterrows():
            nm = str(r.get(name_col, r.get("batter", "?"))).split()[-1]
            ax.annotate(nm, (r["decision_plus"], r["power_plus"]), fontsize=7, alpha=0.85,
                        ha="center", va="bottom")
        ax.axvline(100, color="gray", linestyle="--", linewidth=0.8)
        ax.axhline(100, color="gray", linestyle="--", linewidth=0.8)
        ax.set_xlabel("Decision+ (swing/take quality)")
        ax.set_ylabel("Power+ (xwOBA above expectation)")
        ax.set_title("Decision+ vs Power+ quadrant")
        for (x, y, txt) in [(87, 128, "Raw power\n(chaser)"), (113, 128, "Elite"),
                             (87, 73, "Weak all-around"), (113, 73, "Disciplined\n(low pop)")]:
            ax.text(x, y, txt, fontsize=8, color="#aaa", ha="center", style="italic")
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
    except Exception:
        st.caption("Scatter chart unavailable.")


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PLV + Process+ Dashboard",
    page_icon=":baseball:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Disclaimer banner ─────────────────────────────────────────────────────────
st.warning(
    "**Unofficial public-data clone.** Outputs are NOT official Pitcher List PLV or Process+ metrics. "
    "Built from public Statcast data only (pybaseball). Calibrated on 2021–2024 data.",
    icon="⚠️",
)

# ── Config & data loaders ─────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_hitters(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"master_hitter_{year}.csv"
    return pd.read_csv(p) if p.exists() else None


@st.cache_data(ttl=300)
def load_pitchers(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"master_pitcher_{year}.csv"
    return pd.read_csv(p) if p.exists() else None


@st.cache_data(ttl=300)
def load_rolling_hitters(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"process_plus_rolling_{year}.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else None


@st.cache_data(ttl=300)
def load_rolling_pitchers(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"plv_rolling_{year}.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else None


@st.cache_data(ttl=300)
def load_board(name: str, year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"{name}_{year}.csv"
    return pd.read_csv(p) if p.exists() else None


@st.cache_data(ttl=300)
def load_hitter_fantasy(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"hitter_fantasy_{year}.csv"
    return pd.read_csv(p) if p.exists() else None


@st.cache_data(ttl=300)
def load_pitcher_fantasy(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"pitcher_fantasy_{year}.csv"
    return pd.read_csv(p) if p.exists() else None


@st.cache_data(ttl=300)
def load_scoring():
    """Load league scoring weights; return default LeagueScoring if file missing."""
    cfg = get_config()
    from plv_clone.fantasy.scoring import LeagueScoring
    scoring_path = cfg.models_dir / "league_scoring.json"
    return LeagueScoring.load(scoring_path) if scoring_path.exists() else LeagueScoring()


# ── Sidebar controls ──────────────────────────────────────────────────────────
st.sidebar.title("PLV + Process+")
st.sidebar.caption("Unofficial clone · public Statcast data")

year = st.sidebar.selectbox("Season", [2026, 2025, 2024, 2023, 2022, 2021], index=0)
tab_labels = ["Hitters", "Pitchers", "Rolling Trends", "Target Boards", "Player View",
               "Hitter Fantasy", "Pitcher Fantasy"]
active_tab = st.sidebar.radio("View", tab_labels)

# ── Load data ─────────────────────────────────────────────────────────────────
hitters  = load_hitters(year)
pitchers = load_pitchers(year)
rolling_h = load_rolling_hitters(year)
rolling_p = load_rolling_pitchers(year)

name_col_h = "batter_name" if hitters is not None and "batter_name" in hitters.columns else "batter"
name_col_p = "player_name" if pitchers is not None and "player_name" in pitchers.columns else "pitcher"

# ── Season stage detection & sidebar selector ─────────────────────────────────
# Derive season_date from rolling data (actual game dates, unbiased by PA filter).
# Falls back to PA-based inference when rolling data is unavailable.
_season_date = None
if rolling_h is not None and "date" in rolling_h.columns and not rolling_h.empty:
    _max_date = pd.to_datetime(rolling_h["date"]).max()
    if pd.notna(_max_date):
        _season_date = _max_date.date()
elif rolling_p is not None and "date" in rolling_p.columns and not rolling_p.empty:
    _max_date = pd.to_datetime(rolling_p["date"]).max()
    if pd.notna(_max_date):
        _season_date = _max_date.date()

_detected_stage = infer_stage(
    hitters=hitters if hitters is not None else None,
    pitchers=pitchers if pitchers is not None else None,
    season_date=_season_date,
)
_STAGE_OPTIONS = {
    f"Auto-detect ({_detected_stage})": _detected_stage,
    "Early  (< 150 PA median)": "early",
    "Mid    (150–320 PA median)": "mid",
    "Mature (> 320 PA median)": "mature",
}
_stage_choice = st.sidebar.selectbox("Season Stage", list(_STAGE_OPTIONS.keys()), index=0)
active_stage = _STAGE_OPTIONS[_stage_choice]
t = get_thresholds(active_stage)

_STAGE_COLOR = {"early": "orange", "mid": "blue", "mature": "green"}
st.sidebar.markdown(
    f"**Stage:** :{_STAGE_COLOR[active_stage]}[{t.stage_label}]"
)

# ── Freshness indicator ───────────────────────────────────────────────────────
_meta = read_build_meta(get_config().outputs_dir, year)
if _meta:
    _built_at = _meta.get("built_at", "")
    _rolling_max = _meta.get("hitter_rolling_max_date") or _meta.get("pitcher_rolling_max_date", "")
    st.sidebar.caption(
        f"Exports built: {_built_at[:10] if _built_at else '?'}  \n"
        f"Latest data: {_rolling_max or '?'}"
    )
else:
    st.sidebar.caption("No build metadata found — run `plv build-exports` to populate.")

# Show warning banner for non-mature stages
if t.stage_warning:
    st.warning(t.stage_warning, icon="ℹ️")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: HITTERS
# ─────────────────────────────────────────────────────────────────────────────
if active_tab == "Hitters":
    st.header(f"{year} Hitter Leaderboard — Process+")

    if hitters is None:
        st.error(f"master_hitter_{year}.csv not found. Run: `plv build-exports {year}`")
        st.stop()

    # Position filter
    _pos_opts_h = []
    if "fantasy_positions" in hitters.columns:
        _pos_opts_h = sorted({
            p for fps in hitters["fantasy_positions"].dropna()
            for p in fps.split("|") if p
        })
    if _pos_opts_h:
        sel_pos_h = st.multiselect("Position", _pos_opts_h, default=[], key="h_pos",
                                    help="Filter by fantasy position. Leave empty for all.")
    else:
        sel_pos_h = []

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_pa = st.number_input("Min PA", min_value=1, max_value=800, value=150, step=10)
    with col2:
        min_pp = st.number_input("Min Process+", min_value=80, max_value=160, value=95, step=1)
    with col3:
        _sort_opts_h = [c for c in ["process_plus", "decision_plus", "contact_plus", "power_plus", "xwoba_actual"] if c in hitters.columns]
        sort_col = st.selectbox("Sort by", _sort_opts_h)
    with col4:
        n_rows = st.number_input("Show rows", min_value=10, max_value=413, value=50, step=10)

    df = hitters[(hitters["pa"] >= min_pa) & (hitters["process_plus"] >= min_pp)].copy()
    if sel_pos_h and "fantasy_positions" in df.columns:
        df = df[df["fantasy_positions"].fillna("").apply(
            lambda fps: any(p in fps.split("|") for p in sel_pos_h)
        )]
    df = df.sort_values(sort_col, ascending=False).head(n_rows).reset_index(drop=True)
    df.index += 1

    display_cols = [name_col_h, "pa"]
    for c in ("primary_position", "fantasy_positions_display"):
        if c in df.columns:
            display_cols.append(c)
    display_cols += ["process_plus", "decision_plus", "contact_plus", "power_plus"]
    for c in ("swing_pct", "chase_pct", "xwoba_actual", "xwoba_vs_expected"):
        if c in df.columns:
            display_cols.append(c)
    df_show = df[[c for c in display_cols if c in df.columns]]

    # Format
    pct_cols = [c for c in df_show.columns if "pct" in c]
    float_cols = [c for c in df_show.columns if c.startswith("xwoba")]
    fmt = {c: "{:.1%}" for c in pct_cols}
    fmt.update({c: "{:.3f}" for c in float_cols})
    for c in ("process_plus", "decision_plus", "contact_plus", "power_plus"):
        if c in df_show.columns:
            fmt[c] = "{:.1f}"

    st.dataframe(df_show.style.format(fmt, na_rep="—"), use_container_width=True)
    st.caption(f"{len(df)} hitters shown (filtered from {len(hitters)} qualified)")

    # Distribution charts
    st.subheader("Component Distributions")
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 4, figsize=(14, 3))
        components = [
            ("process_plus",  "Process+",  "#9C27B0"),
            ("decision_plus", "Decision+", "#2196F3"),
            ("contact_plus",  "Contact+",  "#4CAF50"),
            ("power_plus",    "Power+",    "#FF9800"),
        ]
        for ax, (col, label, color) in zip(axes, components):
            if col in hitters.columns:
                vals = hitters[col].dropna()
                ax.hist(vals, bins=25, color=color, alpha=0.75, edgecolor="white")
                ax.axvline(100, color="black", linestyle="--", linewidth=1)
                ax.set_title(f"{label}\nmean={vals.mean():.1f}", fontsize=9)
                ax.tick_params(labelsize=8)
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
    except Exception:
        st.caption("Chart unavailable — matplotlib error.")

    # Decision+ vs Power+ scatter
    st.subheader("Decision+ vs Power+ (quadrant view)")
    _scatter_hitters(hitters, name_col_h)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: PITCHERS
# ─────────────────────────────────────────────────────────────────────────────
elif active_tab == "Pitchers":
    st.header(f"{year} Pitcher Leaderboard — PLV")

    if pitchers is None:
        st.error(f"master_pitcher_{year}.csv not found. Run: `plv build-exports {year}`")
        st.stop()

    col1, col2, col3 = st.columns(3)
    with col1:
        min_pitches = st.number_input("Min pitches", min_value=50, max_value=3000, value=100, step=50)
    with col2:
        _sort_opts_p = [c for c in ["plv", "whiff_pct", "cs_pct", "xwoba_model"] if c in pitchers.columns]
        sort_col_p = st.selectbox("Sort by", _sort_opts_p)
    with col3:
        n_rows_p = st.number_input("Show rows", min_value=10, max_value=800, value=50, step=10)

    df = pitchers[pitchers["pitches"] >= min_pitches].copy()
    df = df.sort_values(sort_col_p, ascending=(sort_col_p == "xwoba_model")).head(n_rows_p).reset_index(drop=True)
    df.index += 1

    display_cols_p = [name_col_p, "pitches", "plv"]
    for c in ("swing_pct", "whiff_pct", "cs_pct", "xwoba_model"):
        if c in df.columns:
            display_cols_p.append(c)
    df_show_p = df[[c for c in display_cols_p if c in df.columns]]

    pct_cols_p = [c for c in df_show_p.columns if "pct" in c]
    fmt_p = {c: "{:.1%}" for c in pct_cols_p}
    fmt_p.update({"plv": "{:.3f}", "xwoba_model": "{:.3f}"})
    st.dataframe(df_show_p.style.format(fmt_p, na_rep="—"), use_container_width=True)
    st.caption(f"{len(df)} pitchers shown (filtered from {len(pitchers)} qualified)")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: ROLLING TRENDS
# ─────────────────────────────────────────────────────────────────────────────
elif active_tab == "Rolling Trends":
    st.header(f"{year} Rolling 30-Day Trends")

    subtab = st.radio("", ["Hitters (Process+)", "Pitchers (PLV)", "Rolling Fantasy"], horizontal=True)

    if subtab == "Hitters (Process+)":
        if rolling_h is None:
            st.error(f"process_plus_rolling_{year}.csv not found.")
            st.stop()

        latest_h = rolling_h.sort_values("date").groupby("batter").last().reset_index()
        # rolling CSV already carries batter_name — use it; enrich from hitters where available
        if name_col_h not in latest_h.columns:
            latest_h[name_col_h] = latest_h["batter"].astype(str)
        if hitters is not None and name_col_h in hitters.columns:
            names_df = hitters[["batter", name_col_h]].drop_duplicates().rename(columns={name_col_h: "_hn"})
            latest_h = latest_h.merge(names_df, on="batter", how="left")
            latest_h[name_col_h] = latest_h["_hn"].fillna(latest_h[name_col_h])
            latest_h = latest_h.drop(columns=["_hn"])
        latest_h[name_col_h] = latest_h[name_col_h].fillna(latest_h["batter"].astype(str))

        sort_roll = st.selectbox("Sort by", ["decision_value_mean", "contact_value_mean", "power_value_mean"])
        n_roll = st.number_input("Show", min_value=10, max_value=200, value=30, step=10)

        roll_cols = [name_col_h, "date", "pa"]
        for c in ("decision_value_mean", "contact_value_mean", "power_value_mean"):
            if c in latest_h.columns:
                roll_cols.append(c)
        roll_cols = [c for c in roll_cols if c in latest_h.columns]

        top_roll = latest_h.sort_values(sort_roll, ascending=False).head(n_roll)[roll_cols].reset_index(drop=True)
        top_roll.index += 1
        fmt_r = {c: "{:.4f}" for c in ("decision_value_mean", "contact_value_mean", "power_value_mean") if c in top_roll.columns}
        st.dataframe(top_roll.style.format(fmt_r, na_rep="—"), use_container_width=True)
        st.caption(f"Showing latest 30-day window per hitter. Date = window end date.")

    elif subtab == "Pitchers (PLV)":
        if rolling_p is None:
            st.error(f"plv_rolling_{year}.csv not found.")
            st.stop()

        latest_p = rolling_p.sort_values("date").groupby("pitcher").last().reset_index()
        if name_col_p not in latest_p.columns:
            latest_p[name_col_p] = latest_p["pitcher"].astype(str)
        if pitchers is not None and name_col_p in pitchers.columns:
            names_df_p = pitchers[["pitcher", name_col_p]].drop_duplicates().rename(columns={name_col_p: "_pn"})
            latest_p = latest_p.merge(names_df_p, on="pitcher", how="left")
            latest_p[name_col_p] = latest_p["_pn"].fillna(latest_p[name_col_p])
            latest_p = latest_p.drop(columns=["_pn"])
        latest_p[name_col_p] = latest_p[name_col_p].fillna(latest_p["pitcher"].astype(str))

        n_roll_p = st.number_input("Show", min_value=10, max_value=200, value=30, step=10, key="np")
        roll_cols_p = [c for c in [name_col_p, "date", "pitches", "plv", "plv_raw"] if c in latest_p.columns]
        top_roll_p = latest_p.sort_values("plv", ascending=False).head(n_roll_p)[roll_cols_p].reset_index(drop=True)
        top_roll_p.index += 1
        st.dataframe(top_roll_p.style.format({"plv": "{:.3f}", "plv_raw": "{:.4f}"}, na_rep="—"), use_container_width=True)

    else:
        # ── Rolling Fantasy ───────────────────────────────────────────────
        st.subheader("Rolling Fantasy (30-day event rates)")
        st.caption(
            "FP computed from actual events in each rolling window — this is **recent production**, "
            "not a projection. Run `plv build-exports <year>` to populate rolling rate columns."
        )
        scoring_rf = load_scoring()
        rf_subtab = st.radio("", ["Hitters", "Pitchers"], horizontal=True, key="rf_sub")

        if rf_subtab == "Hitters":
            if rolling_h is None:
                st.error(f"process_plus_rolling_{year}.csv not found.")
                st.stop()

            rh = rolling_h.copy()
            # Resolve names
            if name_col_h not in rh.columns:
                rh[name_col_h] = rh["batter"].astype(str)
            if hitters is not None and name_col_h in hitters.columns:
                ndf = hitters[["batter", name_col_h]].drop_duplicates().rename(columns={name_col_h: "_hn"})
                rh = rh.merge(ndf, on="batter", how="left")
                rh[name_col_h] = rh["_hn"].fillna(rh[name_col_h])
                rh = rh.drop(columns=["_hn"])
            rh[name_col_h] = rh[name_col_h].fillna(rh["batter"].astype(str))

            # Compute rolling FP from event rates if columns are present
            rate_cols = ["rolling_tb_pa", "rolling_bb_pa", "rolling_k_pa"]
            has_rates = all(c in rh.columns for c in rate_cols)
            if has_rates:
                hbp_r  = rh["rolling_hbp_pa"] if "rolling_hbp_pa" in rh.columns else 0.009
                sb_r   = rh["rolling_sb_pa"]  if "rolling_sb_pa"  in rh.columns else 0.0
                rh["rolling_core_fp_pa"] = (
                    scoring_rf.tb      * rh["rolling_tb_pa"].fillna(0)
                    + scoring_rf.bb_bat  * rh["rolling_bb_pa"].fillna(0)
                    + scoring_rf.k_bat   * rh["rolling_k_pa"].fillna(0)
                    + scoring_rf.hbp_bat * (hbp_r if isinstance(hbp_r, float) else hbp_r.fillna(0.009))
                    + scoring_rf.sb      * (sb_r  if isinstance(sb_r,  float) else sb_r.fillna(0.0))
                ).round(4)
                if "rolling_h_pa" in rh.columns:
                    hbp_ser = rh["rolling_hbp_pa"].fillna(0.009) if "rolling_hbp_pa" in rh.columns else 0.009
                    obp_r = (rh["rolling_h_pa"].fillna(0) + rh["rolling_bb_pa"].fillna(0) +
                             (hbp_ser if isinstance(hbp_ser, float) else hbp_ser)).clip(lower=0.15)
                    r_r   = 0.37 * obp_r
                    rbi_r = 0.24 * rh["rolling_tb_pa"].fillna(0) + 0.06 * obp_r
                    rh["rolling_full_fp_pa"] = (
                        rh["rolling_core_fp_pa"]
                        + scoring_rf.r   * r_r
                        + scoring_rf.rbi * rbi_r
                    ).round(4)

            latest_rh = rh.sort_values("date").groupby("batter").last().reset_index()
            _rfh_sort_opts = [c for c in [
                "rolling_core_fp_pa", "rolling_full_fp_pa",
                "rolling_k_pa", "rolling_bb_pa", "rolling_tb_pa", "rolling_sb_pa",
            ] if c in latest_rh.columns]
            _rfh_sort_fallback = ["pa", "date"]
            rf_sort_h = (
                st.selectbox("Sort by", _rfh_sort_opts, key="rfh_sort")
                if _rfh_sort_opts
                else next((c for c in _rfh_sort_fallback if c in latest_rh.columns), None)
            )
            n_rfh = st.number_input("Show", min_value=10, max_value=200, value=30, step=10, key="rfh_n")

            show_rh = [c for c in [
                name_col_h, "date", "pa",
                "rolling_core_fp_pa", "rolling_full_fp_pa",
                "rolling_tb_pa", "rolling_bb_pa", "rolling_k_pa", "rolling_sb_pa",
            ] if c in latest_rh.columns]
            # For hitters, lower K/PA is better (fewer strikeouts = better plate skill).
            _rfh_low_is_better = {"rolling_k_pa"}
            if rf_sort_h and rf_sort_h in latest_rh.columns:
                _rfh_asc = rf_sort_h in _rfh_low_is_better
                top_rh = latest_rh.sort_values(rf_sort_h, ascending=_rfh_asc).head(n_rfh)[show_rh].reset_index(drop=True)
            else:
                top_rh = latest_rh.head(n_rfh)[show_rh].reset_index(drop=True)
            top_rh.index += 1
            fmt_rh = {c: "{:.4f}" for c in show_rh if c not in (name_col_h, "date", "pa")}
            st.dataframe(top_rh.style.format(fmt_rh, na_rep="—"), use_container_width=True)
            if not has_rates:
                st.info("Rolling rate columns not found. Re-run `plv build-exports` to populate them.")
            st.caption("rolling_core_fp_pa = TB+BB+K+HBP+SB from events in window. "
                       "rolling_full_fp_pa adds estimated R/RBI. Date = window end.")

        else:
            if rolling_p is None:
                st.error(f"plv_rolling_{year}.csv not found.")
                st.stop()

            rp = rolling_p.copy()
            if name_col_p not in rp.columns:
                rp[name_col_p] = rp["pitcher"].astype(str)
            if pitchers is not None and name_col_p in pitchers.columns:
                ndf_p = pitchers[["pitcher", name_col_p]].drop_duplicates().rename(columns={name_col_p: "_pn"})
                rp = rp.merge(ndf_p, on="pitcher", how="left")
                rp[name_col_p] = rp["_pn"].fillna(rp[name_col_p])
                rp = rp.drop(columns=["_pn"])
            rp[name_col_p] = rp[name_col_p].fillna(rp["pitcher"].astype(str))

            rate_cols_p = ["rolling_k_ip", "rolling_bb_ip", "rolling_h_ip", "rolling_er_ip"]
            has_rates_p = all(c in rp.columns for c in rate_cols_p)
            if has_rates_p:
                rp["rolling_fp_from_events"] = (
                    scoring_rf.ip
                    + scoring_rf.h_pit  * rp["rolling_h_ip"].fillna(0)
                    + scoring_rf.er     * rp["rolling_er_ip"].fillna(0)
                    + scoring_rf.bb_pit * rp["rolling_bb_ip"].fillna(0)
                    + scoring_rf.hb_pit * 0.033
                    + scoring_rf.k_pit  * rp["rolling_k_ip"].fillna(0)
                ).round(4)

            latest_rp = rp.sort_values("date").groupby("pitcher").last().reset_index()
            _rfp_sort_opts = [c for c in [
                "rolling_fp_from_events", "rolling_k_ip", "rolling_bb_ip",
                "rolling_h_ip", "rolling_er_ip", "plv",
            ] if c in latest_rp.columns]
            _rfp_sort_fallback = ["plv", "pitches", "date"]
            rf_sort_p = (
                st.selectbox("Sort by", _rfp_sort_opts, key="rfp_sort")
                if _rfp_sort_opts
                else next((c for c in _rfp_sort_fallback if c in latest_rp.columns), None)
            )
            n_rfp = st.number_input("Show", min_value=10, max_value=200, value=30, step=10, key="rfp_n")

            show_rp = [c for c in [
                name_col_p, "date", "pitches", "plv",
                "rolling_fp_from_events",
                "rolling_k_ip", "rolling_bb_ip", "rolling_h_ip", "rolling_er_ip",
            ] if c in latest_rp.columns]
            # For pitchers, lower BB/IP, H/IP, and ER/IP is better.
            _rfp_low_is_better = {"rolling_bb_ip", "rolling_h_ip", "rolling_er_ip"}
            if rf_sort_p and rf_sort_p in latest_rp.columns:
                _rfp_asc = rf_sort_p in _rfp_low_is_better
                top_rp = latest_rp.sort_values(rf_sort_p, ascending=_rfp_asc).head(n_rfp)[show_rp].reset_index(drop=True)
            else:
                top_rp = latest_rp.head(n_rfp)[show_rp].reset_index(drop=True)
            top_rp.index += 1
            fmt_rp = {c: "{:.4f}" if "ip" in c else "{:.3f}" for c in show_rp if c not in (name_col_p, "date", "pitches")}
            st.dataframe(top_rp.style.format(fmt_rp, na_rep="—"), use_container_width=True)
            if not has_rates_p:
                st.info("Rolling rate columns not found. Re-run `plv build-exports` to populate them.")
            st.caption("rolling_fp_from_events = FP/IP from events in window (no SV/HD). Date = window end.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: TARGET BOARDS
# ─────────────────────────────────────────────────────────────────────────────
elif active_tab == "Target Boards":
    st.header(f"{year} Fantasy Target Boards")
    st.caption("Generated by `plv build-target-boards`. Methodology: docs/fantasy_decision_framework.md")

    board_options = {
        "Buy Targets (Process > xwOBA)": "hitter_buy_targets",
        "Breakout Flags (Emerging elite)": "hitter_breakout_flags",
        "Regression Flags (Results > Process)": "hitter_regression_flags",
        "Discipline Leaders (Decision+)": "hitter_discipline_targets",
        "Power Leaders (Power+)": "hitter_power_targets",
        "Pitcher PLV Targets": "pitcher_plv_targets",
    }

    board_label = st.selectbox("Board", list(board_options.keys()))
    board_name  = board_options[board_label]
    df_board    = load_board(board_name, year)

    if df_board is None:
        st.error(f"{board_name}_{year}.csv not found. Run: `plv build-target-boards {year}`")
        st.stop()

    # Confidence filter — labels are stage-aware
    if "confidence" in df_board.columns:
        available_tiers = sorted(df_board["confidence"].dropna().unique().tolist())
        tier_labels = list(t.hitter_tier_labels) if "hitter" in board_name else list(t.pitcher_tier_labels)
        default_tiers = [lbl for lbl in tier_labels[:2] if lbl in available_tiers] or available_tiers[:2]
        tier_filter = st.multiselect("Confidence tier", available_tiers, default=default_tiers)
        df_board = df_board[df_board["confidence"].isin(tier_filter)]

    # Position filter (hitter boards only)
    if "hitter" in board_name and "fantasy_positions" in df_board.columns:
        _pos_opts_tb = sorted({
            p for fps in df_board["fantasy_positions"].dropna()
            for p in fps.split("|") if p
        })
        if _pos_opts_tb:
            sel_pos_tb = st.multiselect("Position", _pos_opts_tb, default=[], key="tb_pos",
                                         help="Filter by fantasy position. Leave empty for all.")
            if sel_pos_tb:
                df_board = df_board[df_board["fantasy_positions"].fillna("").apply(
                    lambda fps: any(p in fps.split("|") for p in sel_pos_tb)
                )]

    df_board = df_board.reset_index(drop=True)
    df_board.index += 1

    # Format numeric columns
    fmt_b: dict = {}
    for c in df_board.columns:
        if "pct" in c:
            fmt_b[c] = "{:.1%}"
        elif c.startswith("xwoba"):
            fmt_b[c] = "{:.3f}"
        elif c in ("process_plus", "decision_plus", "contact_plus", "power_plus"):
            fmt_b[c] = "{:.1f}"
        elif c in ("rank_gap", "pp_rank", "xwoba_rank"):
            fmt_b[c] = "{:.3f}"
        elif c == "plv":
            fmt_b[c] = "{:.3f}"

    st.dataframe(df_board.style.format(fmt_b, na_rep="—"), use_container_width=True)
    st.caption(f"{len(df_board)} players on this board.")

    # Tag breakdown
    if "tag" in df_board.columns:
        with st.expander("Tag summary"):
            tag_counts = df_board["tag"].str.split(";").explode().str.strip().value_counts()
            st.bar_chart(tag_counts)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: PLAYER VIEW
# ─────────────────────────────────────────────────────────────────────────────
elif active_tab == "Player View":
    st.header("Single Player Breakdown")

    subtab_pv = st.radio("", ["Hitter", "Pitcher"], horizontal=True)

    if subtab_pv == "Hitter":
        if hitters is None:
            st.error(f"master_hitter_{year}.csv not found.")
            st.stop()

        query = st.text_input("Search hitter (name or MLBAM ID)", "Aaron Judge")
        if query:
            mask = hitters[name_col_h].str.lower().str.contains(query.lower(), na=False) if not query.isdigit() else hitters["batter"] == int(query)
            rows = hitters[mask]
            if len(rows) == 0:
                st.warning(f"No hitter found matching: {query}")
            else:
                row = rows.iloc[0]
                name = row.get(name_col_h, str(row.get("batter", "?")))
                pos_display = row.get("fantasy_positions_display", "") or row.get("primary_position", "")
                header_txt = f"{name}  —  {pos_display}" if pos_display else name
                st.subheader(header_txt)

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("PA", int(row.get("pa", 0)))
                m2.metric("Process+", f"{row.get('process_plus', float('nan')):.1f}")
                m3.metric("Decision+", f"{row.get('decision_plus', float('nan')):.1f}")
                m4.metric("Contact+", f"{row.get('contact_plus', float('nan')):.1f}")
                m5.metric("Power+", f"{row.get('power_plus', float('nan')):.1f}")

                if "xwoba_actual" in row.index:
                    col_a, col_b = st.columns(2)
                    col_a.metric("xwOBA", f"{row['xwoba_actual']:.3f}")
                    if "xwoba_vs_expected" in row.index:
                        col_b.metric("xwOBA vs expected", f"{row['xwoba_vs_expected']:+.3f}")

                if "swing_pct" in row.index:
                    col_c, col_d = st.columns(2)
                    col_c.metric("Swing%", f"{row['swing_pct']:.1%}")
                    if "chase_pct" in row.index:
                        col_d.metric("Chase%", f"{row['chase_pct']:.1%}")

                # Rolling sparklines
                if rolling_h is not None and "batter" in row.index:
                    batter_id = row["batter"]
                    h_roll = rolling_h[rolling_h["batter"] == batter_id].sort_values("date")
                    if len(h_roll) > 1:
                        if "decision_value_mean" in h_roll.columns:
                            st.subheader("30-Day Rolling Decision Value")
                            chart_data = h_roll.set_index("date")[["decision_value_mean"]].rename(
                                columns={"decision_value_mean": "Decision value (30d)"}
                            )
                            st.line_chart(chart_data)
                        # Rolling fantasy rates if available
                        rate_avail = [c for c in ["rolling_tb_pa", "rolling_bb_pa", "rolling_k_pa"] if c in h_roll.columns]
                        if rate_avail:
                            st.subheader("30-Day Rolling Fantasy Rates")
                            chart_rates = h_roll.set_index("date")[rate_avail].rename(columns={
                                "rolling_tb_pa": "TB/PA (30d)",
                                "rolling_bb_pa": "BB/PA (30d)",
                                "rolling_k_pa":  "K/PA (30d)",
                            })
                            st.line_chart(chart_rates)

    else:
        if pitchers is None:
            st.error(f"master_pitcher_{year}.csv not found.")
            st.stop()

        query_p = st.text_input("Search pitcher (name or MLBAM ID)", "Zack Wheeler")
        if query_p:
            mask_p = pitchers[name_col_p].str.lower().str.contains(query_p.lower(), na=False) if not query_p.isdigit() else pitchers["pitcher"] == int(query_p)
            rows_p = pitchers[mask_p]
            if len(rows_p) == 0:
                st.warning(f"No pitcher found matching: {query_p}")
            else:
                row_p = rows_p.iloc[0]
                pname = row_p.get(name_col_p, str(row_p.get("pitcher", "?")))
                st.subheader(pname)

                pm1, pm2, pm3, pm4 = st.columns(4)
                pm1.metric("Pitches", int(row_p.get("pitches", 0)))
                pm2.metric("PLV", f"{row_p.get('plv', float('nan')):.3f}")
                if "whiff_pct" in row_p.index:
                    pm3.metric("Whiff%", f"{row_p['whiff_pct']:.1%}")
                if "xwoba_model" in row_p.index:
                    pm4.metric("xwOBA (model)", f"{row_p['xwoba_model']:.3f}")

                if rolling_p is not None and "pitcher" in row_p.index:
                    pitcher_id = row_p["pitcher"]
                    p_roll = rolling_p[rolling_p["pitcher"] == pitcher_id].sort_values("date")
                    if len(p_roll) > 1:
                        if "plv" in p_roll.columns:
                            st.subheader("30-Day Rolling PLV")
                            chart_data_p = p_roll.set_index("date")[["plv"]].rename(
                                columns={"plv": "PLV (30d)"}
                            )
                            st.line_chart(chart_data_p)
                        # Rolling K/IP and BB/IP if available
                        pitcher_rate_avail = [c for c in ["rolling_k_ip", "rolling_bb_ip"] if c in p_roll.columns]
                        if pitcher_rate_avail:
                            st.subheader("30-Day Rolling K/IP and BB/IP")
                            chart_p_rates = p_roll.set_index("date")[pitcher_rate_avail].rename(columns={
                                "rolling_k_ip":  "K/IP (30d)",
                                "rolling_bb_ip": "BB/IP (30d)",
                            })
                            st.line_chart(chart_p_rates)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: HITTER FANTASY
# ─────────────────────────────────────────────────────────────────────────────
elif active_tab == "Hitter Fantasy":
    st.header(f"{year} Hitter Fantasy Projections")

    hf = load_hitter_fantasy(year)
    if hf is None:
        st.error(
            f"hitter_fantasy_{year}.csv not found. "
            f"Run: `plv build-fantasy-exports {year}` "
            f"(and `plv calibrate-fantasy` first if needed)"
        )
        st.stop()

    # ── View selector (core vs full) ──────────────────────────────────────
    view_mode = st.radio(
        "Ranking mode",
        ["core_fp_per_pa (skill: TB+BB+K+HBP+SB)", "full_fp_per_pa (context: adds R+RBI)"],
        horizontal=True, key="hf_view",
    )
    primary_fp = "core_fp_per_pa" if "core" in view_mode else "full_fp_per_pa"

    # ── Caveats ───────────────────────────────────────────────────────────
    with st.expander("Accuracy caveats — read before acting"):
        st.markdown("""
**Most reliable:** K/PA (R²=0.71), TB/PA (R²=0.66), BB/PA (R²=0.49)

**core_fp_per_pa** — uses only skill-driven components. Use this as your default ranking.

**full_fp_per_pa** — adds R and RBI via empirical multipliers. R/RBI are lineup-context
dependent (batting order, team quality) and have meaningful noise. Use for directional context only.

**SB** — estimated via shrinkage toward league average (0.020/PA).
Formula: `(observed_sb/pa × pa + 0.020 × 150) / (pa + 150)`. Speed players with
real SB production will have their estimate pulled up; average players will land near 0.02.
This is not a sprint-speed model — it responds to actual SB events in our data.
Add manually for elite speed players you know well.

**R and RBI** — context-sensitive. A .400 OBP hitter batting 8th scores far fewer runs
than the same player batting 3rd. These estimates assume average lineup context.
        """)

    # ── Position filter ───────────────────────────────────────────────────
    _pos_opts_hf = []
    if "fantasy_positions" in hf.columns:
        _pos_opts_hf = sorted({
            p for fps in hf["fantasy_positions"].dropna()
            for p in fps.split("|") if p
        })
    if _pos_opts_hf:
        sel_pos_hf = st.multiselect("Position", _pos_opts_hf, default=[], key="hf_pos",
                                     help="Filter by fantasy position. Leave empty for all.")
    else:
        sel_pos_hf = []

    # ── Filters ───────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        min_pa_f = st.number_input("Min PA", min_value=1, max_value=800, value=100, step=25,
                                    key="hf_mpa")
    with col2:
        sort_fp_options = [c for c in [
            "core_fp_per_pa", "full_fp_per_pa", "fp_per_game",
            "est_tb_rate", "est_bb_rate", "est_k_rate", "est_sb_rate", "process_plus",
        ] if c in hf.columns]
        sort_fp = st.selectbox("Sort by", sort_fp_options,
                               index=sort_fp_options.index(primary_fp) if primary_fp in sort_fp_options else 0,
                               key="hf_sort")
    with col3:
        n_hf = st.number_input("Show", min_value=10, max_value=400, value=50, step=10,
                                key="hf_n")
    pa_game_input = st.slider("PA/game assumption", min_value=2.0, max_value=5.0, value=3.5,
                               step=0.5, key="hf_pag")

    df_hf = hf[hf["pa"] >= min_pa_f].copy()
    if sel_pos_hf and "fantasy_positions" in df_hf.columns:
        df_hf = df_hf[df_hf["fantasy_positions"].fillna("").apply(
            lambda fps: any(p in fps.split("|") for p in sel_pos_hf)
        )]
    if "full_fp_per_pa" in df_hf.columns:
        df_hf["fp_per_game"] = (df_hf["full_fp_per_pa"] * pa_game_input).round(3)
    elif "fp_per_pa" in df_hf.columns:
        df_hf["fp_per_game"] = (df_hf["fp_per_pa"] * pa_game_input).round(3)

    df_hf = df_hf.sort_values(sort_fp, ascending=False).head(n_hf).reset_index(drop=True)
    df_hf.index += 1

    show_cols = [c for c in [
        "batter_name", "pa", "primary_position", "fantasy_positions_display",
        "core_fp_per_pa", "full_fp_per_pa", "fp_per_game",
        "est_tb_rate", "est_bb_rate", "est_k_rate", "est_sb_rate",
        "process_plus", "decision_plus", "power_plus",
    ] if c in df_hf.columns]
    fmt_hf: dict = {
        "est_bb_rate": "{:.3f}", "est_k_rate": "{:.3f}",
        "est_tb_rate": "{:.3f}", "est_sb_rate": "{:.3f}",
        "core_fp_per_pa": "{:.3f}", "full_fp_per_pa": "{:.3f}",
        "fp_per_game": "{:.2f}",
        "process_plus": "{:.1f}", "decision_plus": "{:.1f}", "power_plus": "{:.1f}",
    }
    st.dataframe(df_hf[show_cols].style.format(fmt_hf, na_rep="—"), use_container_width=True)
    st.caption(
        f"{len(df_hf)} hitters shown. "
        f"fp_per_game = full_fp_per_pa × {pa_game_input:.1f} PA/game. "
        "core_fp = TB+BB+K+HBP+SB (skill); full_fp adds context-dependent R+RBI."
    )

    # ── League average reference ──────────────────────────────────────────
    with st.expander("League average reference"):
        st.markdown("""
| Stat | League avg rate | Fantasy weight | Avg FP contribution/PA | In core? |
|------|----------------|----------------|------------------------|---------|
| BB   | 8.5% | +1 | +0.085 | Yes |
| K    | 22.8% | −1 | −0.228 | Yes |
| TB   | 0.365/PA | +1 | +0.365 | Yes |
| HBP  | 0.9% | +1 | +0.009 | Yes |
| SB   | ~2.0% | +1 | +0.020 | Yes (estimated) |
| R    | ~10.5% | +1 | +0.105 | No — context |
| RBI  | ~9.5% | +1 | +0.095 | No — context |
| **core total** | | | **≈ +0.251/PA** | |
| **full total** | | | **≈ +0.451/PA** | |

SB estimated via shrinkage formula. Add premium for known speed players.
R and RBI assume average lineup context — adjust for batting order, team.
        """)


# ─────────────────────────────────────────────────────────────────────────────
# TAB: PITCHER FANTASY
# ─────────────────────────────────────────────────────────────────────────────
elif active_tab == "Pitcher Fantasy":
    st.header(f"{year} Pitcher Fantasy Projections")

    pf = load_pitcher_fantasy(year)
    if pf is None:
        st.error(
            f"pitcher_fantasy_{year}.csv not found. "
            f"Run: `plv build-fantasy-exports {year}`"
        )
        st.stop()

    # ── Caveats ───────────────────────────────────────────────────────────
    with st.expander("Accuracy caveats — read before acting"):
        st.markdown("""
**Most reliable:** K/IP (R²=0.37), BB/IP (R²=0.27)

**K/IP** — best pitcher fantasy signal. Whiff rate + PLV carry real predictive content.
Use for ranking starting pitchers and high-leverage relievers.

**BB/IP** — called-strike rate has genuine walk-prevention signal. Useful for separating
pitchers with control problems.

**H/IP** (R²=0.20) and **ER/IP** (R²=0.16) — noisy. BABIP and ERA have substantial
luck components year-to-year. Use for relative ranking (elite vs. poor), not as absolute expectations.

**Relievers (RP):** fp_per_ip captures quality innings pitched, but **SV and HD are not modeled**.
RP fantasy value is heavily role-dependent. fp_per_app for RP is incomplete without
save/hold context. See docs/reliever_role_model_future_work.md.

**IP per start (5.5) and IP per app (1.0)** are defaults — adjust for workload expectations.
        """)

    # ── Role filter ───────────────────────────────────────────────────────
    role_filter = st.radio("Role", ["All", "SP", "RP"], horizontal=True, key="pf_role")
    df_pf = pf.copy()
    if role_filter != "All" and "pitcher_role" in df_pf.columns:
        df_pf = df_pf[df_pf["pitcher_role"] == role_filter]

    col1p, col2p, col3p = st.columns(3)
    with col1p:
        min_pit_f = st.number_input("Min pitches", min_value=50, max_value=3000, value=100, step=50,
                                     key="pf_mpit")
    with col2p:
        sort_pf_opts = [c for c in [
            "fp_per_ip", "fp_per_start", "fp_per_app",
            "est_k_per_ip", "est_bb_per_ip", "est_h_per_ip", "est_er_per_ip", "plv",
        ] if c in df_pf.columns]
        sort_pf = st.selectbox("Sort by", sort_pf_opts, key="pf_sort")
    with col3p:
        n_pf = st.number_input("Show", min_value=10, max_value=800, value=50, step=10,
                                key="pf_n")

    df_pf = df_pf[df_pf["pitches"] >= min_pit_f].copy()
    asc_pf = sort_pf in ("est_er_per_ip", "est_h_per_ip", "est_bb_per_ip")
    df_pf = df_pf.sort_values(sort_pf, ascending=asc_pf).head(n_pf).reset_index(drop=True)
    df_pf.index += 1

    show_cols_p = [c for c in [
        "player_name", "pitches", "pitcher_role", "plv",
        "est_k_per_ip", "est_bb_per_ip", "est_h_per_ip", "est_er_per_ip",
        "fp_per_ip", "fp_per_start", "fp_per_app",
    ] if c in df_pf.columns]
    fmt_pf: dict = {
        "plv": "{:.3f}",
        "est_k_per_ip": "{:.3f}", "est_bb_per_ip": "{:.3f}",
        "est_h_per_ip": "{:.3f}", "est_er_per_ip": "{:.3f}",
        "fp_per_ip": "{:.3f}", "fp_per_start": "{:.2f}", "fp_per_app": "{:.2f}",
    }
    st.dataframe(df_pf[show_cols_p].style.format(fmt_pf, na_rep="—"), use_container_width=True)
    st.caption(
        f"{len(df_pf)} pitchers shown. "
        "fp_per_start = fp_per_ip × 5.5 (SP). fp_per_app = fp_per_ip × 1.0 (RP, no SV/HD). "
        "RP values are incomplete for role-sensitive leagues — see caveats above."
    )

    # ── SV/HD note ────────────────────────────────────────────────────────
    with st.expander("SV/HD upside guide (manual adjustment)"):
        sv_w = 5.0; hd_w = 3.0
        st.markdown(f"""
SV and HD are **not included** in fp_per_ip or fp_per_app. They depend entirely on role
and cannot be predicted from pitch quality alone.

| Role | Typical rate | FP/app from SV/HD |
|------|-------------|-------------------|
| Closer | ~0.15 SV/app | +{0.15*sv_w:.2f}/app |
| Setup/hold | ~0.25 HD/app | +{0.25*hd_w:.2f}/app |
| Other RP | ~0.05 HD/app | +{0.05*hd_w:.2f}/app |

**How to use:** Take fp_per_app from the table, then add SV/HD based on role from your
league platform. A closer with fp_per_app = 2.5 + 0.75 SV = ~3.25/app total.

See docs/reliever_role_model_future_work.md for planned improvements.
        """)
