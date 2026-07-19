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

# Anchor cwd to project root so config relative paths resolve correctly
# regardless of where `streamlit run` was invoked from.
os.chdir(ROOT)

from plv_clone.config import get_config
from plv_clone.utils.provenance import read_build_meta
from plv_clone.utils.season_stage import infer_stage, get_thresholds
from plv_clone.league_config import MY_TEAM_NAME


# ── Sample-warning row highlight ─────────────────────────────────────────────

def _style_low_sample(df_show: pd.DataFrame, warn: "pd.Series") -> "pd.io.formats.style.Styler":
    """Apply a subtle dark-amber border highlight to rows where warn is True (dark-theme safe)."""
    def _row(row):
        return (
            ["background-color: #2a2000; color: #e2e8f0"] * len(row)
            if warn.get(row.name, False)
            else [""] * len(row)
        )
    return df_show.style.apply(_row, axis=1)


# ── Signal badge + table renderer ────────────────────────────────────────────

_BADGE_CSS = {
    "Top Target": "background:#166534;color:#dcfce7",
    "Strong Add": "background:#365314;color:#d9f99d",
    "Watchlist":  "background:#713f12;color:#fef3c7",
    "Pass":       "background:#1f2937;color:#9ca3af",
    "Too Small":  "background:#111827;color:#4b5563;font-style:italic",
}


def _render_signal_table(df: pd.DataFrame, name_col: str, extra_cols: list) -> None:
    """st.dataframe with signal column styled by tier color."""
    if df.empty:
        st.info("No data.")
        return
    show = [c for c in [name_col, "signal"] + extra_cols if c in df.columns]
    display = df[show].reset_index(drop=True).copy()

    def _color_sig(val):
        return _BADGE_CSS.get(str(val), "")

    styler = display.style
    if "signal" in display.columns:
        styler = styler.map(_color_sig, subset=["signal"])
    st.dataframe(styler, use_container_width=True)


# ── ESPN cached fetchers ──────────────────────────────────────────────────────
if str(ROOT / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "app"))

_MY_TEAM = MY_TEAM_NAME


@st.cache_data(ttl=300)
def _load_espn_all_teams():
    try:
        from espn_connector import get_all_teams
        return get_all_teams(), None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


@st.cache_data(ttl=300)
def _load_espn_roster(team_name: str = _MY_TEAM):
    """Return roster for the given team name, filtered from the cached all-teams data."""
    all_df, err = _load_espn_all_teams()
    if err:
        return pd.DataFrame(), err
    if all_df.empty:
        return pd.DataFrame(), "No league data"
    _teams = all_df["team_name"].dropna().unique().tolist()
    _target = next(
        (t for t in _teams if team_name.lower() in t.lower() or t.lower() in team_name.lower()),
        _teams[0] if _teams else None,
    )
    if _target is None:
        return pd.DataFrame(), f"Team '{team_name}' not found in league"
    _cols = [c for c in ["player_name", "position", "pro_team"] if c in all_df.columns]
    return all_df[all_df["team_name"] == _target][_cols].drop_duplicates().reset_index(drop=True), None


@st.cache_data(ttl=300)
def _load_espn_free_agents(position=None, size=2000):
    # size=2000 is the documented-correct default (feedback_fa_pool_size_cap.md):
    # per-position size<2000 silently drops low-owned high-FP FAs (Sheehan/Connelly
    # -Early bug). Callers must NOT lower it. Mirrors league_state.available_fa's
    # _FA_POOL_SIZE. Audit 2026-07-03.
    try:
        from espn_connector import get_free_agents
        return get_free_agents(position=position, size=size), None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


@st.cache_data(ttl=300)
def _load_espn_standings():
    try:
        from espn_connector import get_league_standings
        return get_league_standings(), None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


def _fuzzy_merge(espn_df: pd.DataFrame, model_df: pd.DataFrame,
                 model_name_col: str = "player_name") -> pd.DataFrame:
    if espn_df.empty or model_df.empty:
        return pd.DataFrame()
    try:
        from espn_connector import merge_with_model
        return merge_with_model(espn_df, model_df, model_name_col=model_name_col)
    except Exception:
        return pd.DataFrame()


def _ros_games(yr: int = 2026) -> int:
    import datetime
    today = datetime.date.today()
    season_end = datetime.date(yr, 9, 28)
    days = max(0, (season_end - today).days)
    return int(days * 162 / 183)


def _sig_ord(sig: str) -> int:
    return {"Top Target": 0, "Strong Add": 1, "Watchlist": 2, "Pass": 3, "Too Small": 4}.get(str(sig), 5)


_SIG_RANK = {"Top Target": 4, "Strong Add": 3, "Watchlist": 2, "Pass": 1, "Too Small": 0}


def _waiver_score(df: pd.DataFrame, savant_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Compute a single add-urgency score for wire candidates.

    Components (0–100 scale):
      40pts  Signal rank   (Top Target=4 … Too Small=0) normalised to 0-40
      30pts  Availability  (1 - percent_owned/100) × 30
      30pts  Positional rank percentile (proc_plus_positional) × 30
         +bonus  xwOBA delta (Savant NOW-THEN) if available — adds up to 15pts

    Higher = stronger add.
    """
    out = df.copy()
    out["_sig_rank"] = out.get("signal", pd.Series(dtype=str)).map(_SIG_RANK).fillna(0)
    out["_avail"]    = (1 - out.get("percent_owned", pd.Series(0.0)).fillna(0) / 100)
    # Positional rank: normalise proc_plus_positional (mean≈100, std≈10) to 0-1
    if "proc_plus_positional" in out.columns:
        pmin, pmax = out["proc_plus_positional"].quantile(0.05), out["proc_plus_positional"].quantile(0.95)
        out["_pos_rank"] = ((out["proc_plus_positional"] - pmin) / max(pmax - pmin, 1)).clip(0, 1)
    else:
        out["_pos_rank"] = 0.5

    out["add_score"] = (
        out["_sig_rank"] / 4 * 40
        + out["_avail"] * 30
        + out["_pos_rank"] * 30
    ).round(1)

    # Optional Savant delta bonus (up to +15)
    if savant_df is not None and not savant_df.empty and "xwoba_delta" in savant_df.columns:
        sav_sub = savant_df[["player_name", "xwoba_delta"]].dropna()
        # Normalise delta to 0-1 across its distribution
        d_min, d_max = sav_sub["xwoba_delta"].quantile(0.05), sav_sub["xwoba_delta"].quantile(0.95)
        sav_sub = sav_sub.copy()
        sav_sub["_xw_bonus"] = ((sav_sub["xwoba_delta"] - d_min) / max(d_max - d_min, 0.01)).clip(0, 1) * 15
        name_col_wire = "player_name" if "player_name" in out.columns else out.columns[0]
        out = out.merge(sav_sub[["player_name", "_xw_bonus"]].rename(
            columns={"player_name": name_col_wire}), on=name_col_wire, how="left"
        )
        out["add_score"] = (out["add_score"] + out["_xw_bonus"].fillna(0)).round(1)
        out = out.drop(columns=["_xw_bonus"])

    out = out.drop(columns=["_sig_rank", "_avail", "_pos_rank"], errors="ignore")
    return out


# ── Sparkline helper ──────────────────────────────────────────────────────────

def _plot_sparklines(df: pd.DataFrame, ids: list, id_col: str,
                     name_col: str, value_col: str, color: str = "#22c55e") -> None:
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        for pid in ids:
            g = df[df[id_col] == pid].sort_values("date")
            if g.empty or value_col not in g.columns:
                continue
            name = g[name_col].iloc[-1] if name_col in g.columns else str(pid)
            fig.add_trace(go.Scatter(
                x=g["date"], y=g[value_col],
                mode="lines+markers", name=str(name).split()[-1],
                line=dict(color=color, width=2), opacity=0.8,
                hovertemplate=f"<b>{name}</b><br>%{{x}}<br>{value_col}: %{{y:.4f}}<extra></extra>",
            ))
        fig.update_layout(height=300, margin=dict(l=30, r=10, t=20, b=30),
                          showlegend=True, legend=dict(font=dict(size=9)),
                          yaxis_title=value_col)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.caption("Sparkline chart unavailable.")


# ── Quadrant scatter helpers ──────────────────────────────────────────────────

# Metrics where lower percentile rank = better outcome.
# swing_pct excluded: low swing rate is not universally better.
_LOW_IS_BETTER = {
    "chase_pct", "whiff_pct",
    "est_k_rate", "est_bb_per_ip", "est_er_per_ip", "est_h_per_ip",
    "rolling_k_pa", "rolling_bb_ip", "rolling_h_ip", "rolling_er_ip",
}


def _plotly_scatter(
    df: pd.DataFrame,
    xcol: str,
    ycol: str,
    name_col: str,
    *,
    xref: float | None = None,
    yref: float | None = None,
    title: str = "",
    top_n: int = 15,
    xtickfmt: str | None = None,
    ytickfmt: str | None = None,
    size_col: str | None = None,
) -> None:
    """Interactive Plotly scatter with reference lines, direction-aware top-N labels, and full hover."""
    try:
        import plotly.graph_objects as go

        plot_df = df[[c for c in [xcol, ycol, name_col, "pa", size_col] if c and c in df.columns]].copy()
        plot_df = plot_df.dropna(subset=[xcol, ycol])
        if plot_df.empty:
            st.info("No hitters match the current filters for this view.")
            return

        # Direction-aware top-N: invert rank for lower-is-better axes
        x_rank = plot_df[xcol].rank(pct=True)
        y_rank = plot_df[ycol].rank(pct=True)
        if xcol in _LOW_IS_BETTER:
            x_rank = 1 - x_rank
        if ycol in _LOW_IS_BETTER:
            y_rank = 1 - y_rank
        top_idx = (x_rank + y_rank).nlargest(min(top_n, len(plot_df))).index

        # Optional size encoding
        _fixed_size = 7
        base_sizes = _fixed_size
        top_sizes = 10
        if size_col and size_col in plot_df.columns:
            sz = plot_df[size_col].fillna(0)
            distinct = sz.nunique()
            if distinct >= 2:
                sz_norm = (sz - sz.min()) / (sz.max() - sz.min())
                base_sizes = (sz_norm * 13 + 5).round(1).tolist()
                top_sizes = (sz_norm.loc[top_idx] * 13 + 5).round(1).tolist()

        # Hover customdata: [full_name, pa, size_metric_or_blank]
        pa_col = plot_df["pa"].astype(int).astype(str) if "pa" in plot_df.columns else ["—"] * len(plot_df)
        sz_hover = (
            plot_df[size_col].round(2).astype(str)
            if (size_col and size_col in plot_df.columns)
            else pd.Series([""] * len(plot_df), index=plot_df.index)
        )
        hover_suffix = f"<br>{size_col}: %{{customdata[2]}}" if (size_col and size_col in plot_df.columns) else ""
        hover_tmpl = (
            "<b>%{customdata[0]}</b><br>"
            f"{xcol}: %{{x}}<br>{ycol}: %{{y}}<br>PA: %{{customdata[1]}}"
            + hover_suffix
            + "<extra></extra>"
        )

        customdata_all = list(zip(
            plot_df[name_col].fillna("?"),
            pa_col if isinstance(pa_col, list) else pa_col.tolist(),
            sz_hover.tolist(),
        ))
        customdata_top = [customdata_all[plot_df.index.get_loc(i)] for i in top_idx]

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=plot_df[xcol], y=plot_df[ycol],
            mode="markers",
            marker=dict(size=base_sizes, color="#888", opacity=0.45),
            customdata=customdata_all,
            hovertemplate=hover_tmpl,
            name="",
        ))

        top_df = plot_df.loc[top_idx]
        fig.add_trace(go.Scatter(
            x=top_df[xcol], y=top_df[ycol],
            mode="markers+text",
            marker=dict(size=top_sizes, color="#1565C0", opacity=0.85),
            text=top_df[name_col].apply(lambda n: str(n).split()[-1]),
            textposition="top center",
            textfont=dict(size=9),
            customdata=customdata_top,
            hovertemplate=hover_tmpl,
            name="",
        ))

        if xref is not None:
            fig.add_vline(x=xref, line_dash="dash", line_color="gray", line_width=1)
        if yref is not None:
            fig.add_hline(y=yref, line_dash="dash", line_color="gray", line_width=1)

        # ── r / r² annotation ─────────────────────────────────────────────
        try:
            from scipy.stats import pearsonr as _pearsonr
            _r_vals = plot_df[[xcol, ycol]].dropna()
            if len(_r_vals) >= 3:
                _r, _p = _pearsonr(_r_vals[xcol], _r_vals[ycol])
                _r2 = _r ** 2
                _p_str = f"p<0.001" if _p < 0.001 else f"p={_p:.3f}"
                _r_label = f"r = {_r:+.3f}   r² = {_r2:.3f}   {_p_str}   n={len(_r_vals)}"
                fig.add_annotation(
                    xref="paper", yref="paper",
                    x=0.01, y=0.99,
                    text=_r_label,
                    showarrow=False,
                    font=dict(size=11, color="#aaaaaa"),
                    align="left",
                    bgcolor="rgba(0,0,0,0.35)",
                    bordercolor="rgba(255,255,255,0.1)",
                    borderwidth=1,
                    borderpad=4,
                )
        except Exception:
            pass

        layout_kw: dict = dict(
            title=title,
            xaxis_title=xcol,
            yaxis_title=ycol,
            height=480,
            showlegend=False,
            margin=dict(l=50, r=30, t=50, b=50),
        )
        if xtickfmt:
            layout_kw["xaxis"] = dict(tickformat=xtickfmt, title=xcol)
        if ytickfmt:
            layout_kw["yaxis"] = dict(tickformat=ytickfmt, title=ycol)
        fig.update_layout(**layout_kw)
        st.plotly_chart(fig, use_container_width=True)

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

def _inject_primary_position(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure primary_position is always included in fantasy_positions.

    Fixes the case where a player's primary defensive position (e.g. C for a
    catcher getting DH starts) isn't in fantasy_positions because they haven't
    hit the games-started threshold yet.  Works from the CSV on disk without
    needing a pipeline re-run.
    """
    if "primary_position" not in df.columns or "fantasy_positions" not in df.columns:
        return df
    df = df.copy()

    def _fix_row(row):
        primary = str(row["primary_position"] or "").strip()
        fps = str(row["fantasy_positions"] or "").strip()
        if not primary or primary in ("nan", ""):
            return fps
        existing = set(fps.split("|")) if fps else set()
        if primary not in existing:
            existing.add(primary)
            # canonical order: C first, then infield, OF, DH
            _order = {"C": 0, "1B": 1, "2B": 2, "3B": 3, "SS": 4, "OF": 5, "DH": 6}
            return "|".join(sorted(existing, key=lambda p: _order.get(p, 99)))
        return fps

    df["fantasy_positions"] = df.apply(_fix_row, axis=1)
    if "fantasy_positions_display" in df.columns:
        df["fantasy_positions_display"] = df["fantasy_positions"].str.replace("|", ", ", regex=False)
    return df


@st.cache_data(ttl=300)
def load_hitters(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"master_hitter_{year}.csv"
    if not p.exists():
        return None
    return _inject_primary_position(pd.read_csv(p))


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
    if not p.exists():
        return None
    return _inject_primary_position(pd.read_csv(p))


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


@st.cache_data(ttl=3600)
def load_savant_rolling_batters(year: int) -> pd.DataFrame | None:
    """Load savant_rolling_batters_{year}.parquet — xwOBA NOW/THEN/delta by PA bucket."""
    cfg = get_config()
    p = cfg.outputs_dir / f"savant_rolling_batters_{year}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return None


@st.cache_data(ttl=3600)
def load_savant_rolling_pitchers(year: int) -> pd.DataFrame | None:
    """Load savant_rolling_pitchers_{year}.parquet — xwOBA against NOW/THEN/delta by BF bucket."""
    cfg = get_config()
    p = cfg.outputs_dir / f"savant_rolling_pitchers_{year}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return None




# ─── Target-board option dicts ────────────────────────────────────────────────
_ALL_BOARDS = {
    "Buy Targets (Process > xwOBA)": "hitter_buy_targets",
    "Breakout Flags (Emerging elite)": "hitter_breakout_flags",
    "Pre-Breakout (Decision + Blast)": "hitter_pre_breakout",
    "Regression Flags (Results > Process)": "hitter_regression_flags",
    "Discipline Leaders (Discipline+)": "hitter_discipline_targets",
    "Power Leaders (Power+)": "hitter_power_targets",
    "Pitcher PLV Targets": "pitcher_plv_targets",
    "Bat-Tracking Stars (Blast Rate + Speed)": "bat_tracking_stars",
}
_HITTER_BOARDS = {k: v for k, v in _ALL_BOARDS.items() if "pitcher" not in v.lower()}
_PITCHER_BOARDS = {"Pitcher PLV Targets": "pitcher_plv_targets"}


@st.cache_data(ttl=300)
def load_pitch_type_leaderboard(year: int):
    cfg = get_config()
    p = cfg.outputs_dir / f"review_{year}" / "pitch_type_leaderboard.csv"
    if p.exists():
        return pd.read_csv(p)
    # fall back to adjacent season
    for yr in [year + 1, year - 1]:
        p2 = cfg.outputs_dir / f"review_{yr}" / "pitch_type_leaderboard.csv"
        if p2.exists():
            return pd.read_csv(p2)
    return None


# ── Sidebar controls ──────────────────────────────────────────────────────────
st.sidebar.title("PLV + Process+")
st.sidebar.caption("Unofficial clone · public Statcast data")

year = st.sidebar.selectbox("Season", [2026, 2025, 2024, 2023, 2022, 2021], index=0)
tab_labels = ["Hitters", "Pitchers", "Trends & Signals", "Player View", "Waiver Wire", "My Team"]
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


if active_tab == "Hitters":
    _h_tabs = st.tabs(["Leaderboard", "Fantasy", "Targets"])
    with _h_tabs[0]:
        st.subheader(f"{year} Hitter Leaderboard — Process+")

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
            min_pa = st.number_input("Min PA", min_value=1, max_value=800, value=t.min_pa_for_boards, step=10)
        with col2:
            min_pp = st.number_input("Min Process+", min_value=0, max_value=160, value=95, step=1)
        with col3:
            _sort_opts_h = [c for c in [
                "process_plus", "proc_plus_positional", "discipline_plus", "k_avoidance_plus", "power_plus",
                "xwoba_on_contact", "blast_rate", "avg_swing_speed",
            ] if c in hitters.columns]
            sort_col = st.selectbox("Sort by", _sort_opts_h)
        with col4:
            n_rows = st.number_input("Show rows", min_value=10, max_value=413, value=50, step=10)

        df = hitters[(hitters["pa"] >= min_pa) & (hitters["process_plus"] >= min_pp)].copy()
        if sel_pos_h and "fantasy_positions" in df.columns:
            df = df[df["fantasy_positions"].fillna("").apply(
                lambda fps: any(p in fps.split("|") for p in sel_pos_h)
            )]
        scatter_df = df.copy()  # full filtered set (no row limit) — used by quadrant charts
        df = df.sort_values(sort_col, ascending=False).head(n_rows).reset_index(drop=True)
        df.index += 1

        display_cols = [name_col_h, "pa"]
        for c in ("primary_position", "fantasy_positions_display"):
            if c in df.columns:
                display_cols.append(c)
        display_cols += ["process_plus", "proc_plus_positional", "discipline_plus", "k_avoidance_plus", "power_plus"]
        for c in ("pl_process", "pl_dv", "pl_odv"):
            if c in df.columns:
                display_cols.append(c)
        for c in ("swing_pct", "chase_pct", "xwoba_on_contact", "xwoba_vs_expected"):
            if c in df.columns:
                display_cols.append(c)
        for c in ("blast_rate", "avg_swing_speed"):
            if c in df.columns:
                display_cols.append(c)
        for c in ("signal", "risk_flag", "sample_tier"):
            if c in df.columns:
                display_cols.append(c)
        df_show = df[[c for c in display_cols if c in df.columns]]

        # Format
        pct_cols = [c for c in df_show.columns if "pct" in c]
        float_cols = [c for c in df_show.columns if c.startswith("xwoba")]
        fmt = {c: "{:.1%}" for c in pct_cols}
        fmt.update({c: "{:.3f}" for c in float_cols})
        for c in ("process_plus", "proc_plus_positional", "discipline_plus", "k_avoidance_plus", "power_plus",
                   "pl_process", "pl_dv", "pl_odv"):
            if c in df_show.columns:
                fmt[c] = "{:.1f}"
        for c in ("blast_rate", "fast_swing_rate", "squared_up_rate"):
            if c in df_show.columns:
                fmt[c] = "{:.1%}"
        if "avg_swing_speed" in df_show.columns:
            fmt["avg_swing_speed"] = "{:.1f}"

        _h_warn = df["sample_warning"].fillna(False) if "sample_warning" in df.columns else pd.Series(False, index=df.index)
        st.dataframe(_style_low_sample(df_show, _h_warn).format(fmt, na_rep="—"), use_container_width=True)
        _n_warn_h = int(_h_warn.sum())
        _caption_h = f"{len(df)} hitters shown (filtered from {len(hitters)} qualified)"
        if _n_warn_h:
            _caption_h += f"  ·  ⚠ {_n_warn_h} highlighted: < 150 PA — high noise, use with caution"
        st.caption(_caption_h)

        # Distribution charts
        st.subheader("Component Distributions")
        try:
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 4, figsize=(14, 3))
            components = [
                ("process_plus",    "Process+",      "#9C27B0"),
                ("discipline_plus",   "Discipline+",     "#2196F3"),
                ("k_avoidance_plus","K-Avoidance+",  "#4CAF50"),
                ("power_plus",      "Power+",        "#FF9800"),
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

        # ── Quadrant Analysis ─────────────────────────────────────────────────────
        st.subheader("Quadrant Analysis")

        _h_roster_only = st.checkbox("My roster only", value=False, key="h_roster_only")
        _qs_df_h = scatter_df.copy()
        if _h_roster_only:
            _r_df, _r_err = _load_espn_roster()
            if _r_err:
                st.caption(f"ESPN roster unavailable: {_r_err}")
            elif not _r_df.empty:
                _r_hitters = _r_df[~_r_df["position"].isin({"SP", "RP", "P"})].copy()
                _r_merged = _fuzzy_merge(_r_hitters, _qs_df_h[[name_col_h]].drop_duplicates().rename(
                    columns={name_col_h: "player_name"}), model_name_col="player_name")
                if not _r_merged.empty and "model_name" in _r_merged.columns:
                    _keep_h = set(_r_merged["model_name"].dropna())
                    _qs_df_h = _qs_df_h[_qs_df_h[name_col_h].isin(_keep_h)]
                if _qs_df_h.empty:
                    st.info("No roster hitters matched current filters.")

        _presets: dict = {}
        if "discipline_plus" in scatter_df.columns and "power_plus" in scatter_df.columns:
            _presets["Discipline+ vs Power+"] = ("discipline_plus", "power_plus", 100, 100, None)
        if "k_avoidance_plus" in scatter_df.columns and "power_plus" in scatter_df.columns:
            _presets["K-Avoidance+ vs Power+"] = ("k_avoidance_plus", "power_plus", 100, 100, None)
        if "process_plus" in scatter_df.columns and "xwoba_on_contact" in scatter_df.columns:
            _presets["Process+ vs xwOBA (contact)"] = ("process_plus", "xwoba_on_contact", 100, 0.363, None)
        # Blast preset: column present AND has non-null values; dynamic cutoff = max(0.08, p75)
        if ("blast_rate" in scatter_df.columns and "discipline_plus" in scatter_df.columns
                and scatter_df["blast_rate"].notna().any()):
            _blast_q = scatter_df[scatter_df["blast_rate"].notna()]
            if "swing_count" in scatter_df.columns:
                _blast_q = _blast_q[_blast_q["swing_count"].ge(50)]
            _blast_xref = max(0.08, _blast_q["blast_rate"].quantile(0.75)) if not _blast_q.empty else 0.08
            _presets[f"Blast Rate vs Discipline+ (cutoff: {_blast_xref:.1%})"] = (
                "blast_rate", "discipline_plus", _blast_xref, 100, ".1%"
            )

        if _presets:
            _preset_choice = st.selectbox("Preset view", list(_presets.keys()), key="h_preset")
            _px, _py, _pxref, _pyref, _pxfmt = _presets[_preset_choice]
            _plotly_scatter(
                _qs_df_h, _px, _py, name_col_h,
                xref=_pxref, yref=_pyref,
                title=f"{_preset_choice}  ({len(_qs_df_h)} hitters)",
                xtickfmt=_pxfmt,
            )

        # ── Custom quadrant builder ───────────────────────────────────────────────
        with st.expander("Custom quadrant builder"):
            _num_cols = [c for c in _qs_df_h.select_dtypes(include="number").columns if c != "batter"]
            _col_a, _col_b = st.columns(2)
            with _col_a:
                _dyn_x = st.selectbox(
                    "X axis", _num_cols,
                    index=_num_cols.index("discipline_plus") if "discipline_plus" in _num_cols else 0,
                    key="dyn_x",
                )
                _dyn_xr_on = st.checkbox("X reference line", value=False, key="dyn_xr_on")
                _dyn_xref = st.number_input("X ref value", value=100.0, key="dyn_xref") if _dyn_xr_on else None
            with _col_b:
                _dyn_y = st.selectbox(
                    "Y axis", _num_cols,
                    index=_num_cols.index("power_plus") if "power_plus" in _num_cols else 0,
                    key="dyn_y",
                )
                _dyn_yr_on = st.checkbox("Y reference line", value=False, key="dyn_yr_on")
                _dyn_yref = st.number_input("Y ref value", value=100.0, key="dyn_yref") if _dyn_yr_on else None
            _col_c, _col_d, _col_e = st.columns(3)
            with _col_c:
                _dyn_topn = st.slider("Label top N", 5, 30, 15, key="dyn_topn")
            with _col_d:
                _dyn_size = st.selectbox("Size by (optional)", ["None"] + _num_cols, index=0, key="dyn_size")
            with _col_e:
                if _pos_opts_h:
                    _dyn_pos = st.multiselect("Position", _pos_opts_h, default=[], key="dyn_pos")
                else:
                    _dyn_pos = []
            _dyn_df = _qs_df_h.copy()
            if _dyn_pos and "fantasy_positions" in _dyn_df.columns:
                _dyn_df = _dyn_df[_dyn_df["fantasy_positions"].fillna("").apply(
                    lambda fps: any(p in fps.split("|") for p in _dyn_pos)
                )]
            _plotly_scatter(
                _dyn_df, _dyn_x, _dyn_y, name_col_h,
                xref=_dyn_xref, yref=_dyn_yref,
                title=f"{_dyn_x} vs {_dyn_y}  ({len(_dyn_df)} hitters)",
                top_n=_dyn_topn,
                size_col=_dyn_size if _dyn_size != "None" else None,
            )
            st.caption(
                "Inherits min PA, min Process+, and position filters from the leaderboard above. "
                "Position selector here adds a further filter."
            )

        # ── Bat-Tracking Detail ───────────────────────────────────────────────────
        _bt_cols = [c for c in ["blast_rate", "avg_swing_speed", "fast_swing_rate", "squared_up_rate", "swing_count"]
                    if c in scatter_df.columns]
        if _bt_cols:
            with st.expander("Bat-Tracking Detail (2023+)"):
                _bt_sort = (
                    "blast_rate"
                    if "blast_rate" in _bt_cols and scatter_df["blast_rate"].notna().any()
                    else _bt_cols[0]
                )
                _bt_show = [c for c in [name_col_h, "pa", "process_plus"] + _bt_cols if c in scatter_df.columns]
                _bt_fmt: dict = {
                    c: "{:.1%}" for c in ("blast_rate", "fast_swing_rate", "squared_up_rate") if c in _bt_cols
                }
                if "avg_swing_speed" in _bt_cols:
                    _bt_fmt["avg_swing_speed"] = "{:.1f}"
                st.dataframe(
                    scatter_df[_bt_show].sort_values(_bt_sort, ascending=False)
                    .reset_index(drop=True).style.format(_bt_fmt, na_rep="—"),
                    use_container_width=True,
                )
                st.caption(
                    f"Showing all {len(scatter_df)} hitters matching current filters "
                    "(position + min PA + min Process+). "
                    "Rates: blast = squared_up x bat_speed >= 164 threshold. swing_count = competitive swings."
                )

    with _h_tabs[1]:
        st.subheader(f"{year} Hitter Fantasy Projections")

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
            "process_plus", "discipline_plus", "k_avoidance_plus", "power_plus",
            "pl_process", "pl_dv", "pl_odv",
            "signal", "risk_flag", "sample_tier",
        ] if c in df_hf.columns]
        fmt_hf: dict = {
            "est_bb_rate": "{:.3f}", "est_k_rate": "{:.3f}",
            "est_tb_rate": "{:.3f}", "est_sb_rate": "{:.3f}",
            "core_fp_per_pa": "{:.3f}", "full_fp_per_pa": "{:.3f}",
            "fp_per_game": "{:.2f}",
            "process_plus": "{:.1f}", "discipline_plus": "{:.1f}",
            "k_avoidance_plus": "{:.1f}", "power_plus": "{:.1f}",
            "pl_process": "{:.1f}", "pl_dv": "{:.1f}", "pl_odv": "{:.1f}",
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

    with _h_tabs[2]:
        st.subheader(f"{year} Hitter Target Boards")
        _h_board_opts = {
            "Buy Targets (Process > xwOBA)": "hitter_buy_targets",
            "Breakout Flags (Emerging elite)": "hitter_breakout_flags",
            "Pre-Breakout (Decision + Blast)": "hitter_pre_breakout",
            "Regression Flags (Results > Process)": "hitter_regression_flags",
            "Discipline Leaders (Discipline+)": "hitter_discipline_targets",
            "Power Leaders (Power+)": "hitter_power_targets",
        }
        _h_board_sel = st.selectbox("Board", list(_h_board_opts.keys()), key="h_target_board")
        _h_board_name = _h_board_opts[_h_board_sel]
        _h_df_board = load_board(_h_board_name, year)
        if _h_df_board is None:
            st.info(f"{_h_board_name}_{year}.csv not found. Run: `plv build-target-boards {year}`")
        else:
            if "confidence" in _h_df_board.columns:
                _h_avail_tiers = sorted(_h_df_board["confidence"].dropna().unique().tolist())
                _h_tier_filter = st.multiselect("Confidence tier", _h_avail_tiers,
                                                default=_h_avail_tiers[:2] or _h_avail_tiers, key="h_tb_tier")
                _h_df_board = _h_df_board[_h_df_board["confidence"].isin(_h_tier_filter)]
            if "fantasy_positions" in _h_df_board.columns:
                _h_pos_opts = sorted({p for fps in _h_df_board["fantasy_positions"].dropna()
                                      for p in fps.split("|") if p})
                if _h_pos_opts:
                    _h_sel_pos = st.multiselect("Position", _h_pos_opts, default=[], key="h_tb_pos")
                    if _h_sel_pos:
                        _h_df_board = _h_df_board[_h_df_board["fantasy_positions"].fillna("").apply(
                            lambda fps: any(p in fps.split("|") for p in _h_sel_pos))]
            _h_df_board = _h_df_board.reset_index(drop=True)
            _h_df_board.index += 1
            _h_fmt_b: dict = {}
            for _hc in _h_df_board.columns:
                if "pct" in _hc: _h_fmt_b[_hc] = "{:.1%}"
                elif _hc.startswith("xwoba"): _h_fmt_b[_hc] = "{:.3f}"
                elif _hc in ("process_plus", "discipline_plus", "k_avoidance_plus", "power_plus"):
                    _h_fmt_b[_hc] = "{:.1f}"
            for _hc in ("blast_rate", "fast_swing_rate", "squared_up_rate"):
                if _hc in _h_df_board.columns: _h_fmt_b[_hc] = "{:.1%}"
            if "avg_swing_speed" in _h_df_board.columns: _h_fmt_b["avg_swing_speed"] = "{:.1f}"
            st.dataframe(_h_df_board.style.format(_h_fmt_b, na_rep="—"), use_container_width=True)
            st.caption(f"{len(_h_df_board)} players. Full board selector (incl. Bat-Tracking Stars) → Waiver Wire > Boards.")


elif active_tab == "Pitchers":
    _p_tabs = st.tabs(["Leaderboard", "Fantasy", "Targets", "SP Starts"])
    with _p_tabs[0]:
        st.subheader(f"{year} Pitcher Leaderboard — PLV")

        if pitchers is None:
            st.error(f"master_pitcher_{year}.csv not found. Run: `plv build-exports {year}`")
            st.stop()

        col1, col2, col3 = st.columns(3)
        with col1:
            min_pitches = st.number_input("Min pitches", min_value=50, max_value=3000, value=100, step=50)
        with col2:
            _sort_opts_p = [c for c in [
                "fp_per_ip", "plv", "plv_blended", "sv_hd_fp_per_162",
                "whiff_pct", "cs_pct", "xwoba_model",
            ] if c in pitchers.columns]
            sort_col_p = st.selectbox("Sort by", _sort_opts_p)
        with col3:
            n_rows_p = st.number_input("Show rows", min_value=10, max_value=800, value=50, step=10)

        df = pitchers[pitchers["pitches"] >= min_pitches].copy()
        df = df.sort_values(sort_col_p, ascending=(sort_col_p == "xwoba_model")).head(n_rows_p).reset_index(drop=True)
        df.index += 1

        display_cols_p = [name_col_p, "pitches", "pitcher_role", "plv", "plv_blended", "pl_plv", "pl_pla"]
        for c in ("swing_pct", "whiff_pct", "cs_pct", "xwoba_model"):
            if c in df.columns:
                display_cols_p.append(c)
        for c in ("fp_per_ip", "sv_hd_fp_per_162"):
            if c in df.columns:
                display_cols_p.append(c)
        for c in ("signal", "profile_flag", "sample_tier"):
            if c in df.columns:
                display_cols_p.append(c)
        df_show_p = df[[c for c in display_cols_p if c in df.columns]]

        pct_cols_p = [c for c in df_show_p.columns if "pct" in c]
        fmt_p = {c: "{:.1%}" for c in pct_cols_p}
        fmt_p.update({
            "plv": "{:.3f}", "plv_blended": "{:.3f}", "xwoba_model": "{:.3f}",
            "pl_plv": "{:.3f}", "pl_pla": "{:.3f}",
            "fp_per_ip": "{:.3f}", "sv_hd_fp_per_162": "{:.0f}",
        })
        _p_warn = df["sample_warning"].fillna(False) if "sample_warning" in df.columns else pd.Series(False, index=df.index)

        # Full filtered set for quadrant (before row-limit head())
        scatter_df_p = pitchers[pitchers["pitches"] >= min_pitches].copy()

        st.dataframe(_style_low_sample(df_show_p, _p_warn).format(fmt_p, na_rep="—"), use_container_width=True)
        _n_warn_p = int(_p_warn.sum())
        _caption_p = f"{len(df)} pitchers shown (filtered from {len(pitchers)} qualified)"
        if _n_warn_p:
            _caption_p += f"  ·  ⚠ {_n_warn_p} highlighted: < 200 pitches — high noise, use with caution"
        st.caption(_caption_p)

        # ── Pitcher Quadrant Analysis ─────────────────────────────────────────
        st.subheader("Quadrant Analysis")

        _p_roster_only = st.checkbox("My roster only", value=False, key="p_roster_only")
        _qs_df_p = scatter_df_p.copy()
        if _p_roster_only:
            _rp_df, _rp_err = _load_espn_roster()
            if _rp_err:
                st.caption(f"ESPN roster unavailable: {_rp_err}")
            elif not _rp_df.empty:
                _r_pitchers = _rp_df[_rp_df["position"].isin({"SP", "RP", "P"})].copy()
                _rp_merged = _fuzzy_merge(_r_pitchers, _qs_df_p[[name_col_p]].drop_duplicates().rename(
                    columns={name_col_p: "player_name"}), model_name_col="player_name")
                if not _rp_merged.empty and "model_name" in _rp_merged.columns:
                    _keep_p = set(_rp_merged["model_name"].dropna())
                    _qs_df_p = _qs_df_p[_qs_df_p[name_col_p].isin(_keep_p)]
                if _qs_df_p.empty:
                    st.info("No roster pitchers matched current filters.")

        _p_presets: dict = {}
        if "plv" in scatter_df_p.columns and "whiff_pct" in scatter_df_p.columns:
            _p_presets["PLV vs Whiff%"] = ("plv", "whiff_pct", 5.0, scatter_df_p["whiff_pct"].median(), None)
        if "plv" in scatter_df_p.columns and "xwoba_model" in scatter_df_p.columns:
            _p_presets["PLV vs xwOBA allowed"] = ("plv", "xwoba_model", 5.0, 0.320, None)
        if "fp_per_ip" in scatter_df_p.columns and "plv" in scatter_df_p.columns:
            _p_presets["FP/IP vs PLV"] = ("fp_per_ip", "plv", scatter_df_p["fp_per_ip"].median(), 5.0, None)
        if "fp_per_ip" in scatter_df_p.columns and "whiff_pct" in scatter_df_p.columns:
            _p_presets["FP/IP vs Whiff%"] = ("fp_per_ip", "whiff_pct", scatter_df_p["fp_per_ip"].median(), scatter_df_p["whiff_pct"].median(), None)
        if "plv_blended" in scatter_df_p.columns and "plv" in scatter_df_p.columns:
            _p_presets["PLV Blended vs Current (regression candidates)"] = ("plv_blended", "plv", 5.0, 5.0, None)
        if "est_k_per_ip" in scatter_df_p.columns and "est_bb_per_ip" in scatter_df_p.columns:
            _p_presets["K/IP vs BB/IP (command profile)"] = ("est_k_per_ip", "est_bb_per_ip", scatter_df_p["est_k_per_ip"].median(), scatter_df_p["est_bb_per_ip"].median(), None)

        if _p_presets:
            _p_preset_choice = st.selectbox("Preset view", list(_p_presets.keys()), key="p_preset")
            _ppx, _ppy, _ppxref, _ppyref, _ppxfmt = _p_presets[_p_preset_choice]
            _plotly_scatter(
                _qs_df_p, _ppx, _ppy, name_col_p,
                xref=_ppxref, yref=_ppyref,
                title=f"{_p_preset_choice}  ({len(_qs_df_p)} pitchers)",
            )

        with st.expander("Custom quadrant builder"):
            _p_num_cols = [c for c in _qs_df_p.select_dtypes(include="number").columns
                           if c not in ("pitcher",)]
            _pa_col, _pb_col = st.columns(2)
            with _pa_col:
                _p_dyn_x = st.selectbox(
                    "X axis", _p_num_cols,
                    index=_p_num_cols.index("plv") if "plv" in _p_num_cols else 0,
                    key="p_dyn_x",
                )
                _p_dyn_xr_on = st.checkbox("X reference line", value=False, key="p_dyn_xr_on")
                _p_dyn_xref = st.number_input("X ref value", value=5.0, key="p_dyn_xref") if _p_dyn_xr_on else None
            with _pb_col:
                _p_dyn_y = st.selectbox(
                    "Y axis", _p_num_cols,
                    index=_p_num_cols.index("whiff_pct") if "whiff_pct" in _p_num_cols else 0,
                    key="p_dyn_y",
                )
                _p_dyn_yr_on = st.checkbox("Y reference line", value=False, key="p_dyn_yr_on")
                _p_dyn_yref = st.number_input("Y ref value", value=0.25, key="p_dyn_yref") if _p_dyn_yr_on else None
            _pc_col, _pd_col, _pe_col = st.columns(3)
            with _pc_col:
                _p_dyn_topn = st.slider("Label top N", 5, 30, 15, key="p_dyn_topn")
            with _pd_col:
                _p_dyn_size = st.selectbox("Size by (optional)", ["None"] + _p_num_cols, index=0, key="p_dyn_size")
            with _pe_col:
                _p_role_filter = st.multiselect("Role", ["SP", "RP"], default=[], key="p_dyn_role")
            _p_dyn_df = _qs_df_p.copy()
            if _p_role_filter and "pitcher_role" in _p_dyn_df.columns:
                _p_dyn_df = _p_dyn_df[_p_dyn_df["pitcher_role"].isin(_p_role_filter)]
            _plotly_scatter(
                _p_dyn_df, _p_dyn_x, _p_dyn_y, name_col_p,
                xref=_p_dyn_xref, yref=_p_dyn_yref,
                title=f"{_p_dyn_x} vs {_p_dyn_y}  ({len(_p_dyn_df)} pitchers)",
                top_n=_p_dyn_topn,
                size_col=_p_dyn_size if _p_dyn_size != "None" else None,
            )
            st.caption(
                "Inherits min pitches filter from the leaderboard above. "
                "Role selector adds a further SP/RP filter."
            )

    with _p_tabs[1]:
        st.subheader(f"{year} Pitcher Fantasy Projections")

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

    **Relievers (RP):** fp_per_ip captures stuff quality per inning. **SV and HD are now modeled**
    via `sv_hd_fp_per_162` (role tier assigned by PLV percentile). Use both columns together for
    a complete RP picture. See the SV/HD expander below for tier definitions and caveats.

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
                "fp_per_ip", "fp_per_start", "fp_per_app", "sv_hd_fp_per_162",
                "est_k_per_ip", "est_bb_per_ip", "est_h_per_ip", "est_er_per_ip",
                "plv", "plv_blended",
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
            "player_name", "pitches", "pitcher_role", "plv", "plv_blended", "pl_plv", "pl_pla",
            "est_k_per_ip", "est_bb_per_ip", "est_h_per_ip", "est_er_per_ip",
            "fp_per_ip", "fp_per_start", "fp_per_app",
            "est_sv_per_162", "est_hd_per_162", "sv_hd_fp_per_162",
            "signal", "profile_flag", "sample_tier",
        ] if c in df_pf.columns]
        fmt_pf: dict = {
            "plv": "{:.3f}", "plv_blended": "{:.3f}", "pl_plv": "{:.3f}", "pl_pla": "{:.3f}",
            "est_k_per_ip": "{:.3f}", "est_bb_per_ip": "{:.3f}",
            "est_h_per_ip": "{:.3f}", "est_er_per_ip": "{:.3f}",
            "fp_per_ip": "{:.3f}", "fp_per_start": "{:.2f}", "fp_per_app": "{:.2f}",
            "est_sv_per_162": "{:.0f}", "est_hd_per_162": "{:.0f}", "sv_hd_fp_per_162": "{:.0f}",
        }
        st.dataframe(df_pf[show_cols_p].style.format(fmt_pf, na_rep="—"), use_container_width=True)
        st.caption(
            f"{len(df_pf)} pitchers shown. "
            "fp_per_start = fp_per_ip × 5.5 (SP). fp_per_app = fp_per_ip × 1.0 (stuff only). "
            "sv_hd_fp_per_162 adds estimated SV/HD value by role tier — add to fp_per_app for full RP picture."
        )

        # ── SV/HD note ────────────────────────────────────────────────────────
        with st.expander("SV/HD estimates — how they work"):
            st.markdown("""
    **est_sv_per_162**, **est_hd_per_162**, and **sv_hd_fp_per_162** are now modeled in the
    pipeline and shown in the table above. Tier assignment uses PLV percentile as a role proxy:

    | Tier | PLV percentile | est SV | est HD | FP/162 |
    |------|---------------|--------|--------|--------|
    | Closer | ≥ 85th | 28 | 0 | **140** |
    | Setup | 50th–84th | 2 | 18 | **64** |
    | Middle RP | < 50th | 0 | 8 | **24** |
    | SP | any | 0 | 0 | 0 |

    **Caveat:** PLV percentile proxies *stuff quality*, not actual roster role. A high-PLV
    pitcher on a team with an entrenched closer will be assigned closer-tier FP but may only
    accumulate holds. Cross-check against your league platform for confirmed save situations.

    **How to use:** For a full RP picture, add `sv_hd_fp_per_162 / 162 × G` to `fp_per_app`.
    Or sort the table by `sv_hd_fp_per_162` to surface closers quickly.
            """)

    with _p_tabs[2]:
        st.subheader(f"{year} Pitcher Target Boards")
        _p_df_board = load_board("pitcher_plv_targets", year)
        if _p_df_board is None:
            st.info(f"pitcher_plv_targets_{year}.csv not found. Run: `plv build-target-boards {year}`")
        else:
            if "confidence" in _p_df_board.columns:
                _p_avail_tiers = sorted(_p_df_board["confidence"].dropna().unique().tolist())
                _p_tier_filter = st.multiselect("Confidence tier", _p_avail_tiers,
                                                default=_p_avail_tiers[:2] or _p_avail_tiers, key="p_tb_tier")
                _p_df_board = _p_df_board[_p_df_board["confidence"].isin(_p_tier_filter)]
            _p_df_board = _p_df_board.reset_index(drop=True)
            _p_df_board.index += 1
            _p_fmt_b: dict = {}
            for _pc in _p_df_board.columns:
                if "pct" in _pc: _p_fmt_b[_pc] = "{:.1%}"
                elif _pc == "plv": _p_fmt_b[_pc] = "{:.3f}"
            st.dataframe(_p_df_board.style.format(_p_fmt_b, na_rep="—"), use_container_width=True)
            st.caption(f"{len(_p_df_board)} pitchers on PLV Targets board.")

    with _p_tabs[3]:
        st.subheader("SP Starts -- Streaming Targets")
        st.caption("Available SP free agents sorted by projected fantasy value.")

        pf_26 = load_pitcher_fantasy(year)
        _fa_all_sp, _fa_sp_err = _load_espn_free_agents()
        if _fa_sp_err:
            st.error(f"ESPN API: {_fa_sp_err}")
            st.stop()

        _fa_sp = _fa_all_sp[_fa_all_sp["position"] == "SP"].copy() if not _fa_all_sp.empty else pd.DataFrame()

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            _min_plv_sp = st.number_input("Min PLV blended", min_value=4.0, max_value=6.0, value=4.8, step=0.1, key="sp_plv")
        with col_s2:
            _min_own_sp = st.slider("Max % owned (streaming)", min_value=0, max_value=100, value=50, key="sp_own")
        with col_s3:
            _n_sp_rows = st.number_input("Show", min_value=5, max_value=50, value=20, step=5, key="sp_n")

        _two_start_only = st.checkbox("2-Start Streamers only (< 30% owned)", value=False, key="sp_2start")
        _week_dates = st.text_input("Upcoming start dates (comma-separated, e.g. 2026-05-01, 2026-05-04)", "", key="sp_dates")
        if _week_dates:
            st.caption("Date-based two-start detection coming soon. Currently flagging by ownership threshold.")

        if _fa_sp.empty:
            st.info("No SP free agents found.")
        elif pf_26 is None:
            st.error("pitcher_fantasy_2026.csv not found -- run `plv build-fantasy-exports 2026`.")
        else:
            _sp_merged = _fuzzy_merge(_fa_sp, pf_26)
            if _sp_merged.empty:
                st.info("No model matches for available SP.")
                st.dataframe(_fa_sp[["player_name", "pro_team", "percent_owned"]].head(30), use_container_width=True)
            else:
                if "pitcher_role" in _sp_merged.columns:
                    _sp_merged = _sp_merged[_sp_merged["pitcher_role"] == "SP"]
                if "plv_blended" in _sp_merged.columns:
                    _sp_merged = _sp_merged[_sp_merged["plv_blended"] >= _min_plv_sp]
                if "percent_owned" in _sp_merged.columns:
                    _sp_merged = _sp_merged[_sp_merged["percent_owned"] <= _min_own_sp]
                _sp_merged["two_start_candidate"] = _sp_merged.get("percent_owned", pd.Series(100.0, index=_sp_merged.index)).fillna(100) < 30
                if _two_start_only:
                    _sp_merged = _sp_merged[_sp_merged["two_start_candidate"]]
                _sp_sort_col = "fp_per_start" if "fp_per_start" in _sp_merged.columns else "plv_blended"
                _sp_merged = _sp_merged.sort_values(_sp_sort_col, ascending=False).head(_n_sp_rows).reset_index(drop=True)
                _sp_extra = [c for c in ["pro_team", "percent_owned", "two_start_candidate", "pitches",
                                          "plv", "plv_blended", "pl_plv", "pl_pla",
                                          "fp_per_ip", "fp_per_start",
                                          "est_k_per_ip", "est_bb_per_ip", "profile_flag", "sample_tier"] if c in _sp_merged.columns]
                _render_signal_table(_sp_merged, "player_name", _sp_extra)
                st.caption(f"{len(_sp_merged)} SP shown. two_start_candidate = % owned < 30 (proxy for streamers).")


elif active_tab == "Trends & Signals":
    st.header(f"{year} Rolling 30-Day Trends")

    subtab = st.radio("", ["Hitters (Process+)", "Pitchers (PLV)", "Rolling Fantasy", "xwOBA Trends (Savant)"], horizontal=True)

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

        sort_roll = st.selectbox("Sort by", ["discipline_value_mean", "contact_value_mean", "power_value_mean"])
        n_roll = st.number_input("Show", min_value=10, max_value=200, value=30, step=10)

        roll_cols = [name_col_h, "date", "pa"]
        for c in ("discipline_value_mean", "contact_value_mean", "power_value_mean"):
            if c in latest_h.columns:
                roll_cols.append(c)
        roll_cols = [c for c in roll_cols if c in latest_h.columns]

        top_roll = latest_h.sort_values(sort_roll, ascending=False).head(n_roll)[roll_cols].reset_index(drop=True)
        top_roll.index += 1
        fmt_r = {c: "{:.4f}" for c in ("discipline_value_mean", "contact_value_mean", "power_value_mean") if c in top_roll.columns}
        st.dataframe(top_roll.style.format(fmt_r, na_rep="—"), use_container_width=True)
        st.caption(f"Showing latest 30-day window per hitter. Date = window end date.")

        # ── Trend sparklines ──────────────────────────────────────────────
        _spark_val_h = sort_roll
        if _spark_val_h in rolling_h.columns:
            st.subheader(f"Trends — Top 10 Up / Down ({_spark_val_h})")
            _rh_s = rolling_h.copy()
            if name_col_h not in _rh_s.columns and hitters is not None and name_col_h in hitters.columns:
                _rh_s = _rh_s.merge(
                    hitters[["batter", name_col_h]].drop_duplicates(), on="batter", how="left"
                )
            if name_col_h not in _rh_s.columns:
                _rh_s[name_col_h] = _rh_s["batter"].astype(str)
            else:
                _rh_s[name_col_h] = _rh_s[name_col_h].fillna(_rh_s["batter"].astype(str))
            _slopes_h = (
                _rh_s.sort_values("date")
                .groupby("batter")[_spark_val_h]
                .apply(lambda s: float(np.polyfit(np.arange(len(s.dropna())), s.dropna(), 1)[0]) if len(s.dropna()) >= 2 else 0.0)
                .rename("slope").reset_index()
            )
            _w_min_h = _rh_s.groupby("batter").size()
            _slopes_h = _slopes_h[_slopes_h["batter"].isin(_w_min_h[_w_min_h >= 3].index)]
            if not _slopes_h.empty:
                _sc1, _sc2 = st.columns(2)
                with _sc1:
                    st.caption("Trending Up")
                    _plot_sparklines(_rh_s, _slopes_h.nlargest(10, "slope")["batter"].tolist(),
                                     "batter", name_col_h, _spark_val_h, color="#22c55e")
                with _sc2:
                    st.caption("Trending Down")
                    _plot_sparklines(_rh_s, _slopes_h.nsmallest(10, "slope")["batter"].tolist(),
                                     "batter", name_col_h, _spark_val_h, color="#ef4444")

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

        # ── Trend sparklines ──────────────────────────────────────────────
        _spark_val_p = "plv"
        if _spark_val_p in rolling_p.columns:
            st.subheader("Trends — Top 10 Up / Down (PLV)")
            _rp_s = rolling_p.copy()
            if name_col_p not in _rp_s.columns and pitchers is not None and name_col_p in pitchers.columns:
                _rp_s = _rp_s.merge(
                    pitchers[["pitcher", name_col_p]].drop_duplicates(), on="pitcher", how="left"
                )
            if name_col_p not in _rp_s.columns:
                _rp_s[name_col_p] = _rp_s["pitcher"].astype(str)
            else:
                _rp_s[name_col_p] = _rp_s[name_col_p].fillna(_rp_s["pitcher"].astype(str))
            _slopes_p = (
                _rp_s.sort_values("date")
                .groupby("pitcher")[_spark_val_p]
                .apply(lambda s: float(np.polyfit(np.arange(len(s.dropna())), s.dropna(), 1)[0]) if len(s.dropna()) >= 2 else 0.0)
                .rename("slope").reset_index()
            )
            _w_min_p = _rp_s.groupby("pitcher").size()
            _slopes_p = _slopes_p[_slopes_p["pitcher"].isin(_w_min_p[_w_min_p >= 3].index)]
            if not _slopes_p.empty:
                _sc1_p, _sc2_p = st.columns(2)
                with _sc1_p:
                    st.caption("Trending Up")
                    _plot_sparklines(_rp_s, _slopes_p.nlargest(10, "slope")["pitcher"].tolist(),
                                     "pitcher", name_col_p, _spark_val_p, color="#22c55e")
                with _sc2_p:
                    st.caption("Trending Down")
                    _plot_sparklines(_rp_s, _slopes_p.nsmallest(10, "slope")["pitcher"].tolist(),
                                     "pitcher", name_col_p, _spark_val_p, color="#ef4444")

    elif subtab == "Rolling Fantasy":
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

    # ── xwOBA Trends (Savant) ─────────────────────────────────────────────
    elif subtab == "xwOBA Trends (Savant)":
        st.subheader("xwOBA Trends — Baseball Savant Rolling Leaderboard")
        st.caption(
            "Source: baseballsavant.mlb.com/leaderboard/rolling · "
            "Run `python scripts/fetch_savant_rolling.py` to refresh. "
            "**NOW** = most recent window · **THEN** = prior window · **Delta** = NOW minus THEN."
        )

        _sav_bat = load_savant_rolling_batters(year)
        _sav_pit = load_savant_rolling_pitchers(year)

        _sav_tabs = st.tabs(["Batters", "Pitchers"])

        # ── Batters ───────────────────────────────────────────────────────
        with _sav_tabs[0]:
            if _sav_bat is None or _sav_bat.empty:
                st.warning(
                    f"savant_rolling_batters_{year}.parquet not found. "
                    "Run: `python scripts/fetch_savant_rolling.py --year {year}`"
                )
            else:
                _sb_cols = st.columns(3)
                with _sb_cols[0]:
                    _sb_sort = st.selectbox(
                        "Sort by",
                        ["xwoba_delta", "xwoba_l50", "xwoba_l100", "xwoba_l250"],
                        format_func=lambda c: {
                            "xwoba_delta": "Delta (NOW - THEN)",
                            "xwoba_l50": "xwOBA L50 PA",
                            "xwoba_l100": "xwOBA L100 PA",
                            "xwoba_l250": "xwOBA L250 PA",
                        }.get(c, c),
                        key="sav_bat_sort",
                    )
                with _sb_cols[1]:
                    _sb_dir = st.radio("View", ["Both", "Trending Up", "Trending Down"], horizontal=True, key="sav_bat_dir")
                with _sb_cols[2]:
                    _sb_n = st.number_input("Show (each list)", min_value=5, max_value=100, value=25, step=5, key="sav_bat_n")

                _sb_df = _sav_bat.copy()

                # Optional: cross-reference with ESPN roster
                _sb_my_only = st.checkbox("My roster only", value=False, key="sav_bat_roster")
                if _sb_my_only:
                    _sb_r, _sb_r_err = _load_espn_roster()
                    if not _sb_r_err and not _sb_r.empty:
                        _sb_hitters = _sb_r[~_sb_r["position"].isin({"SP", "RP", "P"})].copy()
                        _sb_matched = _fuzzy_merge(
                            _sb_hitters,
                            _sb_df[["player_name"]].drop_duplicates(),
                            model_name_col="player_name",
                        )
                        if not _sb_matched.empty and "model_name" in _sb_matched.columns:
                            _sb_df = _sb_df[_sb_df["player_name"].isin(set(_sb_matched["model_name"].dropna()))]

                _sb_display_cols = [c for c in [
                    "player_name", "xwoba_l50", "xwoba_l100", "xwoba_l250",
                    "xwoba_then", "xwoba_delta",
                ] if c in _sb_df.columns]
                _sb_fmt = {c: "{:.3f}" for c in _sb_display_cols if c != "player_name"}

                def _color_delta_bat(val):
                    if pd.isna(val):
                        return ""
                    return "color: #22c55e; font-weight:bold" if val > 0.03 else (
                        "color: #ef4444" if val < -0.03 else ""
                    )

                def _show_bat_table(df_sub, ascending):
                    _sorted = (
                        df_sub.dropna(subset=[_sb_sort])
                        .sort_values(_sb_sort, ascending=ascending)
                        .head(_sb_n)
                        .reset_index(drop=True)
                    )
                    _sorted.index += 1
                    _sty = _sorted[_sb_display_cols].style.format(_sb_fmt, na_rep="—")
                    if "xwoba_delta" in _sb_display_cols:
                        _sty = _sty.map(_color_delta_bat, subset=["xwoba_delta"])
                    st.dataframe(_sty, use_container_width=True)

                if _sb_dir == "Both":
                    _bc1, _bc2 = st.columns(2)
                    with _bc1:
                        st.caption(f"Trending Up — top {_sb_n} by {_sb_sort}")
                        _show_bat_table(_sb_df, ascending=False)
                    with _bc2:
                        st.caption(f"Trending Down — bottom {_sb_n} by {_sb_sort}")
                        _show_bat_table(_sb_df, ascending=True)
                elif _sb_dir == "Trending Up":
                    _show_bat_table(_sb_df, ascending=False)
                else:
                    _show_bat_table(_sb_df, ascending=True)

                if "fetch_date" in _sav_bat.columns:
                    _fd = _sav_bat["fetch_date"].iloc[0] if not _sav_bat.empty else "unknown"
                    st.caption(f"Data fetched: {_fd}  ·  {len(_sb_df)} batters in pool.")

                # ── Convergence Scatter ───────────────────────────────────
                st.divider()
                st.subheader("Process vs Results — Convergence Detector")
                st.caption(
                    "X = Positional Process+ (how good the *stuff* is) · "
                    "Y = xwOBA delta — NOW minus THEN (what's *trending*). "
                    "Top-right: strong process AND hot streak. "
                    "Top-left: hot streak but weaker process — potential regression. "
                    "Bottom-right: strong process, currently cold — potential buy."
                )
                _hf_conv = load_hitter_fantasy(year)
                if _hf_conv is not None and not _sb_df.empty:
                    _conv = _sb_df[["player_name", "xwoba_l50", "xwoba_delta"]].dropna(subset=["xwoba_delta"]).copy()
                    _hf_sub = _hf_conv[["batter_name", "proc_plus_positional", "signal", "percent_owned"]
                                       if "percent_owned" in _hf_conv.columns
                                       else ["batter_name", "proc_plus_positional", "signal"]].dropna(subset=["proc_plus_positional"]).copy()
                    # Fuzzy-merge Savant names onto model names via existing helper
                    _conv_merged = _fuzzy_merge(
                        _conv.rename(columns={"player_name": "player_name"}),
                        _hf_sub,
                        model_name_col="batter_name",
                    )
                    if not _conv_merged.empty:
                        # Mark ESPN free agents
                        _fa_conv, _ = _load_espn_free_agents()
                        _fa_names = set(_fa_conv["player_name"].dropna().tolist()) if not _fa_conv.empty else set()
                        _conv_merged["available"] = _conv_merged["player_name"].isin(_fa_names)

                        import plotly.express as _px_conv
                        _conv_fig = _px_conv.scatter(
                            _conv_merged,
                            x="proc_plus_positional",
                            y="xwoba_delta",
                            color="signal",
                            symbol="available",
                            symbol_map={True: "star", False: "circle"},
                            hover_name="player_name",
                            hover_data={"xwoba_l50": ":.3f", "proc_plus_positional": ":.1f",
                                        "xwoba_delta": ":.3f", "available": True},
                            color_discrete_map={
                                "Top Target": "#16a34a", "Strong Add": "#65a30d",
                                "Watchlist": "#d97706", "Pass": "#6b7280", "Too Small": "#374151",
                            },
                            title=f"Process+ vs xwOBA Trend  ({len(_conv_merged)} batters matched)",
                            labels={"proc_plus_positional": "Positional Process+",
                                    "xwoba_delta": "xwOBA Delta (NOW - THEN)"},
                        )
                        _conv_fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.4)
                        _conv_fig.add_vline(x=100, line_dash="dash", line_color="gray", opacity=0.4)
                        _conv_fig.update_layout(height=480, margin=dict(l=30, r=20, t=40, b=30))
                        st.plotly_chart(_conv_fig, use_container_width=True)
                        # Stars = free agents — call those out in a table
                        _fa_buys = _conv_merged[_conv_merged["available"] & (_conv_merged["proc_plus_positional"] >= 100)] \
                                   .sort_values("xwoba_delta", ascending=False).head(15)
                        if not _fa_buys.empty:
                            st.caption("Free agents with Process+ ≥ 100 (top-right quadrant candidates):")
                            _fb_cols = [c for c in ["player_name", "signal", "proc_plus_positional",
                                                     "xwoba_l50", "xwoba_delta"] if c in _fa_buys.columns]
                            st.dataframe(
                                _fa_buys[_fb_cols].reset_index(drop=True).style.format(
                                    {c: "{:.3f}" for c in ["xwoba_l50", "xwoba_delta"]},
                                    na_rep="—"
                                ),
                                use_container_width=True, hide_index=True,
                            )
                    else:
                        st.info("Not enough name matches to build convergence scatter.")
                else:
                    st.info("Load hitter fantasy data and Savant rolling to enable this view.")

        # ── Pitchers ──────────────────────────────────────────────────────
        with _sav_tabs[1]:
            if _sav_pit is None or _sav_pit.empty:
                st.warning(
                    f"savant_rolling_pitchers_{year}.parquet not found. "
                    "Run: `python scripts/fetch_savant_rolling.py --year {year}`"
                )
            else:
                _sp_cols = st.columns(3)
                with _sp_cols[0]:
                    _sp_val_opts = [c for c in ["xwoba_against_l100bf", "xwoba_against_l250bf", "xwoba_against_delta"]
                                    if c in _sav_pit.columns]
                    _sp_sort = st.selectbox(
                        "Sort by",
                        _sp_val_opts,
                        format_func=lambda c: {
                            "xwoba_against_delta":   "Delta (NOW - THEN, negative = improving)",
                            "xwoba_against_l100bf":  "xwOBA against L100 BF",
                            "xwoba_against_l250bf":  "xwOBA against L250 BF",
                        }.get(c, c),
                        key="sav_pit_sort",
                    )
                with _sp_cols[1]:
                    _sp_dir = st.radio("View", ["Both", "Improving", "Worsening"], horizontal=True, key="sav_pit_dir")
                with _sp_cols[2]:
                    _sp_n = st.number_input("Show (each list)", min_value=5, max_value=100, value=25, step=5, key="sav_pit_n")

                _sp_df = _sav_pit.copy()

                _sp_my_only = st.checkbox("My roster only", value=False, key="sav_pit_roster")
                if _sp_my_only:
                    _sp_r, _sp_r_err = _load_espn_roster()
                    if not _sp_r_err and not _sp_r.empty:
                        _sp_pitchers_r = _sp_r[_sp_r["position"].isin({"SP", "RP", "P"})].copy()
                        _sp_matched = _fuzzy_merge(
                            _sp_pitchers_r,
                            _sp_df[["player_name"]].drop_duplicates(),
                            model_name_col="player_name",
                        )
                        if not _sp_matched.empty and "model_name" in _sp_matched.columns:
                            _sp_df = _sp_df[_sp_df["player_name"].isin(set(_sp_matched["model_name"].dropna()))]

                _sp_display_cols = [c for c in [
                    "player_name", "xwoba_against_l100bf", "xwoba_against_l250bf",
                    "xwoba_against_then", "xwoba_against_delta",
                ] if c in _sp_df.columns]

                _sp_fmt = {c: "{:.3f}" for c in _sp_display_cols if c != "player_name"}

                def _color_delta_pit(val):
                    if pd.isna(val):
                        return ""
                    # For pitchers: negative delta (improving) = green
                    return "color: #22c55e; font-weight:bold" if val < -0.03 else (
                        "color: #ef4444" if val > 0.03 else ""
                    )

                def _show_pit_table(df_sub, ascending, label):
                    _srt = (
                        df_sub.dropna(subset=[_sp_sort])
                        .sort_values(_sp_sort, ascending=ascending)
                        .head(_sp_n)
                        .reset_index(drop=True)
                    )
                    _srt.index += 1
                    st.caption(label)
                    _sty = _srt[_sp_display_cols].style.format(_sp_fmt, na_rep="—")
                    if "xwoba_against_delta" in _sp_display_cols:
                        _sty = _sty.map(_color_delta_pit, subset=["xwoba_against_delta"])
                    st.dataframe(_sty, use_container_width=True)

                if _sp_dir == "Both":
                    _pc1, _pc2 = st.columns(2)
                    with _pc1:
                        _show_pit_table(_sp_df, ascending=True,
                                        label=f"Improving (lowest xwOBA against) — top {_sp_n}")
                    with _pc2:
                        _show_pit_table(_sp_df, ascending=False,
                                        label=f"Worsening (highest xwOBA against) — top {_sp_n}")
                elif _sp_dir == "Improving":
                    _show_pit_table(_sp_df, ascending=True,
                                    label=f"Improving — top {_sp_n} (negative delta = getting better)")
                else:
                    _show_pit_table(_sp_df, ascending=False,
                                    label=f"Worsening — top {_sp_n} (positive delta = getting worse)")

                if "fetch_date" in _sav_pit.columns:
                    _fd_p = _sav_pit["fetch_date"].iloc[0] if not _sav_pit.empty else "unknown"
                    st.caption(
                        f"Data fetched: {_fd_p}  ·  {len(_sp_df)} pitchers in pool.  "
                        "xwOBA against: lower = better. Negative delta = improving."
                    )


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

                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("PA", int(row.get("pa", 0)))
                m2.metric("Process+", f"{row.get('process_plus', float('nan')):.1f}")
                m3.metric("Pos. Process+", f"{row.get('proc_plus_positional', float('nan')):.1f}")
                m4.metric("K-Avoidance+", f"{row.get('k_avoidance_plus', float('nan')):.1f}")
                m5.metric("Power+", f"{row.get('power_plus', float('nan')):.1f}")
                m6.metric("Discipline+", f"{row.get('discipline_plus', float('nan')):.1f}")

                if "xwoba_on_contact" in row.index:
                    col_a, col_b = st.columns(2)
                    col_a.metric("xwOBA (contact)", f"{row['xwoba_on_contact']:.3f}")
                    if "xwoba_vs_expected" in row.index:
                        col_b.metric("xwOBA vs expected", f"{row['xwoba_vs_expected']:+.3f}")

                # Bat-tracking (2023+) — only rendered when data present for this player
                _pv_bt = [
                    ("Blast Rate",  "blast_rate",      "pct"),
                    ("Sq-Up Rate",  "squared_up_rate", "pct"),
                    ("Swing Speed", "avg_swing_speed", "mph"),
                    ("Fast Swing%", "fast_swing_rate", "pct"),
                ]
                _pv_bt_avail = [
                    (lbl, col, fmt) for lbl, col, fmt in _pv_bt
                    if col in row.index and pd.notna(row.get(col))
                ]
                if _pv_bt_avail:
                    st.divider()
                    _bt_m = st.columns(len(_pv_bt_avail))
                    for i, (lbl, col, fmt) in enumerate(_pv_bt_avail):
                        val = row[col]
                        _bt_m[i].metric(lbl, f"{val:.1%}" if fmt == "pct" else f"{val:.1f} mph")
                    if "swing_count" in row.index and pd.notna(row.get("swing_count")):
                        st.caption(f"Bat-tracking sample: {int(row['swing_count'])} competitive swings")

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
                        if "discipline_value_mean" in h_roll.columns:
                            st.subheader("30-Day Rolling Decision Value")
                            chart_data = h_roll.set_index("date")[["discipline_value_mean"]].rename(
                                columns={"discipline_value_mean": "Decision value (30d)"}
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

                # ── Multi-season career trajectory ────────────────────────
                st.divider()
                st.subheader("Career Trajectory (all seasons)")
                _career_rows = []
                for _cy in [2021, 2022, 2023, 2024, 2025, 2026]:
                    _cy_hf = load_hitter_fantasy(_cy)
                    if _cy_hf is None:
                        continue
                    _cy_nc = "batter_name" if "batter_name" in _cy_hf.columns else "batter"
                    _cy_mask = _cy_hf[_cy_nc].str.lower().str.contains(query.lower(), na=False) if not query.isdigit() \
                               else _cy_hf["batter"] == int(query)
                    _cy_rows = _cy_hf[_cy_mask]
                    if _cy_rows.empty:
                        continue
                    _cy_r = _cy_rows.iloc[0]
                    _career_rows.append({
                        "Season": _cy,
                        "PA": int(_cy_r.get("pa", 0)),
                        "Process+": round(float(_cy_r.get("process_plus", float("nan"))), 1),
                        "Pos. Rank": round(float(_cy_r.get("proc_plus_positional", float("nan"))), 1),
                        "Discipline+": round(float(_cy_r.get("discipline_plus", float("nan"))), 1),
                        "Power+": round(float(_cy_r.get("power_plus", float("nan"))), 1),
                        "K-Avoid+": round(float(_cy_r.get("k_avoidance_plus", float("nan"))), 1),
                        "Signal": str(_cy_r.get("signal", "")),
                    })
                if _career_rows:
                    try:
                        import plotly.graph_objects as _go
                    except Exception:
                        import plotly.graph_objects as _go
                    _career_df = pd.DataFrame(_career_rows).set_index("Season")
                    _traj_cols = [c for c in ["Process+", "Pos. Rank", "Discipline+", "Power+", "K-Avoid+"]
                                  if _career_df[c].notna().any()]
                    _tfig = _go.Figure()
                    for _tc in _traj_cols:
                        _tfig.add_trace(_go.Scatter(
                            x=_career_df.index,
                            y=_career_df[_tc],
                            mode="lines+markers",
                            name=_tc,
                        ))
                    _tfig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5,
                                    annotation_text="League avg (100)")
                    _tfig.update_layout(
                        height=320,
                        margin=dict(l=30, r=20, t=30, b=30),
                        legend=dict(orientation="h", y=-0.2),
                        xaxis=dict(tickmode="array", tickvals=list(_career_df.index)),
                        yaxis_title="Plus score",
                    )
                    st.plotly_chart(_tfig, use_container_width=True)
                    _career_table = _career_df.reset_index()
                    st.dataframe(
                        _career_table.style.format({c: "{:.1f}" for c in _traj_cols}, na_rep="—"),
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.caption("No multi-season data found for this player.")

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

                # ── Pitch Mix breakdown ───────────────────────────────────
                st.divider()
                st.subheader("Pitch Mix — PLV by Pitch Type")
                _pm_df = None
                _pm_df = load_pitch_type_leaderboard(year)
                if _pm_df is None:
                    st.info("Pitch mix data not available for this pitcher.")
                elif "pitcher" not in row_p.index:
                    st.info("Pitch mix data not available for this pitcher.")
                else:
                    _pm_pitcher_id = row_p["pitcher"]
                    _pm_player = _pm_df[_pm_df["pitcher"] == _pm_pitcher_id].copy()
                    if _pm_player.empty:
                        st.info("Pitch mix data not available for this pitcher.")
                    elif len(_pm_player) < 2:
                        st.dataframe(
                            _pm_player[[c for c in [
                                "pitch_type", "pitch_group", "pitches", "plv",
                                "avg_velo", "whiff_rate", "swing_rate", "e_xwoba_ip", "plv_pctile",
                            ] if c in _pm_player.columns]].style.format("{:.3f}", na_rep="—"),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        _pm_player = _pm_player.sort_values("pitches", ascending=False)
                        _pm_colors = {"Fastball": "#3b82f6", "Breaking": "#f97316", "Offspeed": "#22c55e"}
                        try:
                            import plotly.graph_objects as _pmgo
                            _pm_seen_groups: set = set()
                            _pm_fig = _pmgo.Figure()
                            for _, _pmr in _pm_player.iterrows():
                                _ptg = str(_pmr.get("pitch_group", ""))
                                _ptc = _pm_colors.get(_ptg, "#94a3b8")
                                _show_leg = _ptg not in _pm_seen_groups
                                _pm_seen_groups.add(_ptg)
                                _pm_fig.add_trace(_pmgo.Bar(
                                    y=[str(_pmr.get("pitch_type", ""))],
                                    x=[float(_pmr.get("plv", 0))],
                                    orientation="h",
                                    marker_color=_ptc,
                                    name=_ptg,
                                    text=[
                                        f"PLV {_pmr.get('plv', 0):.2f}  "
                                        f"{_pmr.get('avg_velo', 0):.1f}mph  "
                                        f"Whiff {_pmr.get('whiff_rate', 0):.1%}  "
                                        f"n={int(_pmr.get('pitches', 0))}"
                                    ],
                                    textposition="outside",
                                    showlegend=_show_leg,
                                ))
                            _pm_fig.add_vline(x=5.0, line_dash="dash", line_color="gray", opacity=0.5)
                            _pm_fig.update_layout(
                                height=350, margin=dict(l=30, r=20, t=40, b=30),
                                xaxis_title="PLV",
                                legend=dict(orientation="h", y=1.1),
                                xaxis=dict(range=[0, max(10, _pm_player["plv"].max() * 1.3)]),
                            )
                            st.plotly_chart(_pm_fig, use_container_width=True)
                        except Exception:
                            st.caption("Chart unavailable.")
                        _pm_table_cols = [c for c in [
                            "pitch_type", "pitch_group", "pitches", "plv", "avg_velo",
                            "whiff_rate", "swing_rate", "e_xwoba_ip", "plv_pctile",
                        ] if c in _pm_player.columns]
                        st.dataframe(
                            _pm_player[_pm_table_cols].style.format("{:.3f}", na_rep="—"),
                            use_container_width=True, hide_index=True,
                        )

                # ── Multi-season career trajectory (pitchers) ─────────────
                st.divider()
                st.subheader("Career Trajectory (all seasons)")
                _p_career_rows = []
                for _pcy in [2021, 2022, 2023, 2024, 2025, 2026]:
                    _pcy_pf = load_pitcher_fantasy(_pcy)
                    if _pcy_pf is None:
                        continue
                    _pcy_nc = "player_name" if "player_name" in _pcy_pf.columns else "pitcher"
                    _pcy_mask = _pcy_pf[_pcy_nc].str.lower().str.contains(query_p.lower(), na=False) \
                                if not query_p.isdigit() else _pcy_pf["pitcher"] == int(query_p)
                    _pcy_rows = _pcy_pf[_pcy_mask]
                    if _pcy_rows.empty:
                        continue
                    _pcy_r = _pcy_rows.iloc[0]
                    _p_career_rows.append({
                        "Season": _pcy,
                        "Pitches": int(_pcy_r.get("pitches", 0)),
                        "PLV": round(float(_pcy_r.get("plv", float("nan"))), 3),
                        "PLV Blended": round(float(_pcy_r.get("plv_blended", float("nan"))), 3),
                        "Whiff%": round(float(_pcy_r.get("whiff_pct", float("nan"))), 3),
                        "K/IP (est)": round(float(_pcy_r.get("est_k_per_ip", float("nan"))), 3),
                        "FP/IP": round(float(_pcy_r.get("fp_per_ip", float("nan"))), 3),
                        "Signal": str(_pcy_r.get("signal", "")),
                    })
                if _p_career_rows:
                    import plotly.graph_objects as _pgo
                    _p_career_df = pd.DataFrame(_p_career_rows).set_index("Season")
                    _p_traj_cols = [c for c in ["PLV", "PLV Blended", "Whiff%", "FP/IP"]
                                    if _p_career_df[c].notna().any()]
                    _p_tfig = _pgo.Figure()
                    for _ptc in _p_traj_cols:
                        _p_tfig.add_trace(_pgo.Scatter(
                            x=_p_career_df.index,
                            y=_p_career_df[_ptc],
                            mode="lines+markers",
                            name=_ptc,
                        ))
                    _p_tfig.add_hline(y=5.0, line_dash="dash", line_color="gray", opacity=0.5,
                                      annotation_text="Elite PLV (5.0)")
                    _p_tfig.update_layout(
                        height=300,
                        margin=dict(l=30, r=20, t=30, b=30),
                        legend=dict(orientation="h", y=-0.25),
                        xaxis=dict(tickmode="array", tickvals=list(_p_career_df.index)),
                    )
                    st.plotly_chart(_p_tfig, use_container_width=True)
                    st.dataframe(
                        _p_career_df.reset_index().style.format(
                            {c: "{:.3f}" for c in ["PLV", "PLV Blended", "Whiff%", "K/IP (est)", "FP/IP"]}, na_rep="—"
                        ),
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.caption("No multi-season data found for this pitcher.")


elif active_tab == "Waiver Wire":

    hf_26 = load_hitter_fantasy(year)
    pf_26 = load_pitcher_fantasy(year)
    _fa_all, _fa_err = _load_espn_free_agents()

    if _fa_err:
        st.error(f"ESPN API: {_fa_err}")
        st.stop()
    if _fa_all.empty:
        st.info("No free agents returned. Check ESPN credentials.")
        st.stop()

    _fa_pit_pos = {"SP", "RP", "P"}
    _fa_hitters_all = _fa_all[~_fa_all["position"].isin(_fa_pit_pos)].copy()
    _fa_sp_all     = _fa_all[_fa_all["position"] == "SP"].copy()
    _fa_rp_all     = _fa_all[_fa_all["position"].isin({"RP", "P"})].copy()

    _ww_tabs = st.tabs(["Hitters", "SP", "RP", "Boards"])

    with _ww_tabs[0]:
        st.subheader(f"Available Hitters ({len(_fa_hitters_all)})")

        # ── Merge with model data FIRST so position filter can use fantasy_positions ──
        _wh_merged = pd.DataFrame()
        if hf_26 is not None and not _fa_hitters_all.empty:
            _wh_merged = _fuzzy_merge(_fa_hitters_all, hf_26, model_name_col="batter_name")
            _wh_merged = _inject_primary_position(_wh_merged)

        # ── Build position options from fantasy_positions (model) or ESPN position ──
        _pos_order_wire = {"C": 0, "1B": 1, "2B": 2, "3B": 3, "SS": 4, "OF": 5, "DH": 6}
        if not _wh_merged.empty and "fantasy_positions" in _wh_merged.columns:
            _all_fps_wire: set[str] = set()
            for _fp in _wh_merged["fantasy_positions"].dropna():
                _all_fps_wire.update(str(_fp).split("|"))
            _all_fps_wire.discard("")
            _pos_opts_wire = sorted(_all_fps_wire, key=lambda p: _pos_order_wire.get(p, 99))
        elif "position" in _fa_hitters_all.columns:
            _pos_opts_wire = sorted(_fa_hitters_all["position"].dropna().unique().tolist())
        else:
            _pos_opts_wire = []

        _sel_pos_wire = st.multiselect("Filter by position", _pos_opts_wire, default=[], key="wire_h_pos") if _pos_opts_wire else []

        if not _wh_merged.empty:
            # Apply position filter on fantasy_positions (model-derived, corrected)
            if _sel_pos_wire:
                if "fantasy_positions" in _wh_merged.columns:
                    _wh_merged = _wh_merged[
                        _wh_merged["fantasy_positions"].fillna("").apply(
                            lambda fp: any(p in fp.split("|") for p in _sel_pos_wire)
                        )
                    ]
                else:
                    _wh_merged = _wh_merged[_wh_merged["position"].isin(_sel_pos_wire)]

            if _wh_merged.empty:
                st.info("No model matches for current position filter.")
                _disp_fa = _fa_hitters_all.copy()
                if _sel_pos_wire:
                    _disp_fa = _disp_fa[_disp_fa["position"].isin(_sel_pos_wire)]
                st.dataframe(_disp_fa[["player_name", "position", "pro_team", "percent_owned"]].head(50), use_container_width=True)
            else:
                _sav_bat_wire = load_savant_rolling_batters(year)
                _wh_merged = _waiver_score(_wh_merged, _sav_bat_wire)
                _wire_sort = st.radio("Sort by", ["Add Score", "Signal Tier", "Process+ (Positional)"], horizontal=True, key="wire_h_sort")
                if _wire_sort == "Add Score":
                    _wh_merged = _wh_merged.sort_values("add_score", ascending=False)
                elif _wire_sort == "Signal Tier":
                    _wh_merged = _wh_merged.sort_values("signal", key=lambda s: s.map(_sig_ord))
                else:
                    _wh_merged = _wh_merged.sort_values("proc_plus_positional", ascending=False)
                _wh_merged = _wh_merged.reset_index(drop=True)
                _wh_extra = [c for c in ["add_score", "fantasy_positions_display", "position", "pro_team",
                                          "percent_owned", "pa", "core_fp_per_pa", "proc_plus_positional",
                                          "process_plus", "pl_process", "pl_dv", "pl_odv",
                                          "risk_flag", "sample_tier"] if c in _wh_merged.columns]
                _render_signal_table(_wh_merged, "player_name", _wh_extra)
                st.caption("Add Score = signal tier (40) + availability (30) + positional rank (30) + xwOBA delta bonus (up to +15).")
        elif _fa_hitters_all.empty:
            st.info("No hitter free agents in current filter.")
        else:
            # No model data — ESPN-only fallback
            if _sel_pos_wire:
                _fa_hitters_all = _fa_hitters_all[_fa_hitters_all["position"].isin(_sel_pos_wire)]
            st.dataframe(_fa_hitters_all[["player_name", "position", "pro_team", "percent_owned"]].head(50), use_container_width=True)

    with _ww_tabs[1]:
        st.subheader(f"Available SP ({len(_fa_sp_all)})")
        if pf_26 is not None and not _fa_sp_all.empty:
            _wsp_merged = _fuzzy_merge(_fa_sp_all, pf_26)
            if _wsp_merged.empty:
                st.info("No model matches for available SP.")
                st.dataframe(_fa_sp_all[["player_name", "pro_team", "percent_owned"]].head(50), use_container_width=True)
            else:
                if "pitcher_role" in _wsp_merged.columns:
                    _wsp_merged = _wsp_merged[_wsp_merged["pitcher_role"] == "SP"]
                _wsp_merged = _wsp_merged.sort_values("signal", key=lambda s: s.map(_sig_ord)).reset_index(drop=True)
                _wsp_extra = [c for c in ["pro_team", "percent_owned", "pitches", "fp_per_ip",
                                           "fp_per_start", "plv", "plv_blended", "pl_plv", "pl_pla",
                                           "profile_flag", "sample_tier"] if c in _wsp_merged.columns]
                _render_signal_table(_wsp_merged, "player_name", _wsp_extra)
        elif _fa_sp_all.empty:
            st.info("No SP free agents found.")
        else:
            st.dataframe(_fa_sp_all[["player_name", "pro_team", "percent_owned"]].head(50), use_container_width=True)

    with _ww_tabs[2]:
        st.subheader(f"Available RP ({len(_fa_rp_all)})")
        if pf_26 is not None and not _fa_rp_all.empty:
            _wrp_merged = _fuzzy_merge(_fa_rp_all, pf_26)
            if _wrp_merged.empty:
                st.info("No model matches for available RP.")
                st.dataframe(_fa_rp_all[["player_name", "pro_team", "percent_owned"]].head(50), use_container_width=True)
            else:
                if "pitcher_role" in _wrp_merged.columns:
                    _wrp_merged = _wrp_merged[_wrp_merged["pitcher_role"] == "RP"]
                _wrp_merged = _wrp_merged.sort_values("signal", key=lambda s: s.map(_sig_ord)).reset_index(drop=True)
                _wrp_extra = [c for c in ["pro_team", "percent_owned", "pitches", "fp_per_app",
                                           "sv_hd_fp_per_162", "plv", "plv_blended", "pl_plv", "pl_pla",
                                           "profile_flag", "sample_tier"] if c in _wrp_merged.columns]
                _render_signal_table(_wrp_merged, "player_name", _wrp_extra)
        elif _fa_rp_all.empty:
            st.info("No RP free agents found.")
        else:
            st.dataframe(_fa_rp_all[["player_name", "pro_team", "percent_owned"]].head(50), use_container_width=True)

    with _ww_tabs[3]:
        st.subheader(f"{year} Fantasy Target Boards")
        st.caption("Generated by `plv build-target-boards`. Methodology: docs/fantasy_decision_framework.md")
        st.header(f"{year} Fantasy Target Boards")
        st.caption("Generated by `plv build-target-boards`. Methodology: docs/fantasy_decision_framework.md")

        board_options = {
            "Buy Targets (Process > xwOBA)": "hitter_buy_targets",
            "Breakout Flags (Emerging elite)": "hitter_breakout_flags",
            "Pre-Breakout (Decision + Blast)": "hitter_pre_breakout",
            "Regression Flags (Results > Process)": "hitter_regression_flags",
            "Discipline Leaders (Discipline+)": "hitter_discipline_targets",
            "Power Leaders (Power+)": "hitter_power_targets",
            "Pitcher PLV Targets": "pitcher_plv_targets",
            "Bat-Tracking Stars (Blast Rate + Speed)": "bat_tracking_stars",
        }

        board_label = st.selectbox("Board", list(board_options.keys()))
        board_name  = board_options[board_label]

        if board_name == "bat_tracking_stars":
            _bt_src = load_hitter_fantasy(year)
            if _bt_src is None or _bt_src.empty:
                st.error("hitter_fantasy_2026.csv not found. Run: `plv build-fantasy-exports 2026`")
                st.stop()
            _req_bt = ["blast_rate", "avg_swing_speed", "swing_count"]
            if not all(c in _bt_src.columns for c in _req_bt):
                st.warning(f"Bat-tracking columns missing: {[c for c in _req_bt if c not in _bt_src.columns]}")
                st.stop()
            _bt_elig = _bt_src[_bt_src["swing_count"].fillna(0) >= 50].copy()
            _bt_b75  = _bt_elig["blast_rate"].quantile(0.75)
            _bt_s70  = _bt_elig["avg_swing_speed"].quantile(0.70)
            _bt_board = _bt_src[
                (_bt_src["blast_rate"].fillna(0)       >= _bt_b75) &
                (_bt_src["avg_swing_speed"].fillna(0)  >= _bt_s70) &
                (_bt_src["sample_tier"].fillna("Too Small") != "Too Small")
            ].sort_values("blast_rate", ascending=False).reset_index(drop=True)
            _bt_cols = [c for c in [
                "batter_name", "signal", "blast_rate", "avg_swing_speed",
                "fast_swing_rate", "squared_up_rate", "swing_count",
                "process_plus", "core_fp_per_pa",
            ] if c in _bt_board.columns]
            _bt_fmt: dict = {}
            for _c in ("blast_rate", "fast_swing_rate", "squared_up_rate"):
                if _c in _bt_board.columns:
                    _bt_fmt[_c] = "{:.1%}"
            if "avg_swing_speed" in _bt_board.columns:
                _bt_fmt["avg_swing_speed"] = "{:.1f}"
            if "core_fp_per_pa" in _bt_board.columns:
                _bt_fmt["core_fp_per_pa"] = "{:.3f}"
            _bt_display = _bt_board[_bt_cols].copy()
            _bt_styler = _bt_display.style.format(_bt_fmt, na_rep="—")
            if "signal" in _bt_display.columns:
                _bt_styler = _bt_styler.map(lambda v: _BADGE_CSS.get(str(v), ""), subset=["signal"])
            st.dataframe(_bt_styler, use_container_width=True, hide_index=True)
            st.caption(
                f"{len(_bt_board)} players. "
                "Bat-tracking stars: top blast rate + swing speed. "
                "Predictive of power breakouts. Data: MLB Statcast bat-tracking sensors. "
                f"Thresholds: blast_rate ≥ {_bt_b75:.1%}, avg_swing_speed ≥ {_bt_s70:.1f} mph."
            )
            st.stop()

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
            elif c in ("process_plus", "discipline_plus", "k_avoidance_plus", "power_plus"):
                fmt_b[c] = "{:.1f}"
            elif c in ("rank_gap", "pp_rank", "xwoba_rank"):
                fmt_b[c] = "{:.3f}"
            elif c == "plv":
                fmt_b[c] = "{:.3f}"
        for c in ("blast_rate", "fast_swing_rate", "squared_up_rate"):
            if c in df_board.columns:
                fmt_b[c] = "{:.1%}"
        if "avg_swing_speed" in df_board.columns:
            fmt_b["avg_swing_speed"] = "{:.1f}"

        st.dataframe(df_board.style.format(fmt_b, na_rep="—"), use_container_width=True)
        st.caption(f"{len(df_board)} players on this board.")

        # Tag breakdown
        if "tag" in df_board.columns:
            with st.expander("Tag summary"):
                tag_counts = df_board["tag"].str.split(";").explode().str.strip().value_counts()
                st.bar_chart(tag_counts)


elif active_tab == "My Team":
    _mt_tabs = st.tabs(["Roster", "Matchup", "Trade Analyzer"])
    with _mt_tabs[0]:
        hf_26 = load_hitter_fantasy(year)
        pf_26 = load_pitcher_fantasy(year)

        # Load all teams once (cached) and let the user pick
        _all_t_df, _all_t_err = _load_espn_all_teams()
        if _all_t_err:
            st.error(f"ESPN API error: {_all_t_err}")
            st.stop()
        if _all_t_df.empty:
            st.info("No league data returned. Check ESPN credentials in app/espn_connector.py.")
            st.stop()

        _team_names = sorted(_all_t_df["team_name"].dropna().unique().tolist())
        _default_idx = next(
            (i for i, t in enumerate(_team_names)
             if _MY_TEAM.lower() in t.lower() or t.lower() in _MY_TEAM.lower()), 0
        )
        _selected_team = st.selectbox("Team", _team_names, index=_default_idx, key="my_team_sel")

        st.subheader(f"My Team — {_selected_team}")

        # Construct roster_df from all-teams data for the selected team
        _sel_cols = [c for c in ["player_name", "position", "pro_team"] if c in _all_t_df.columns]
        roster_df = _all_t_df[_all_t_df["team_name"] == _selected_team][_sel_cols].drop_duplicates().reset_index(drop=True)
        roster_err = None

        if roster_df.empty:
            st.info(f"No players found for {_selected_team}.")
            st.stop()

        _pit_pos = {"SP", "RP", "P"}
        _my_hitters = roster_df[~roster_df["position"].isin(_pit_pos)].copy()
        _my_pitchers = roster_df[roster_df["position"].isin(_pit_pos)].copy()

        st.subheader(f"Hitters ({len(_my_hitters)})")
        if hf_26 is not None and not _my_hitters.empty:
            _mh_merged = _fuzzy_merge(_my_hitters, hf_26, model_name_col="batter_name")
            if _mh_merged.empty:
                st.info("No hitter matches found in model data.")
                st.dataframe(_my_hitters[["player_name", "position", "pro_team"]], use_container_width=True)
            else:
                _mh_extra = [c for c in [
                    "position", "pro_team", "pa",
                    "core_fp_per_pa", "full_fp_per_pa",
                    "process_plus", "discipline_plus", "k_avoidance_plus", "power_plus",
                    "pl_process", "pl_dv", "pl_odv",
                    "risk_flag", "sample_tier",
                ] if c in _mh_merged.columns]
                _render_signal_table(_mh_merged, "player_name", _mh_extra)
        else:
            st.dataframe(_my_hitters[["player_name", "position", "pro_team"]], use_container_width=True)
            if hf_26 is None:
                st.caption("hitter_fantasy_2026.csv not found — run `plv build-fantasy-exports 2026`.")

        st.divider()
        st.subheader(f"Pitchers ({len(_my_pitchers)})")
        if pf_26 is not None and not _my_pitchers.empty:
            _mp_merged = _fuzzy_merge(_my_pitchers, pf_26)
            if _mp_merged.empty:
                st.info("No pitcher matches found in model data.")
                st.dataframe(_my_pitchers[["player_name", "position", "pro_team"]], use_container_width=True)
            else:
                _mp_extra = [c for c in [
                    "position", "pro_team", "pitches", "pitcher_role",
                    "fp_per_ip", "fp_per_start", "fp_per_app", "sv_hd_fp_per_162",
                    "plv", "plv_blended", "pl_plv", "pl_pla",
                    "profile_flag", "sample_tier",
                ] if c in _mp_merged.columns]
                _render_signal_table(_mp_merged, "player_name", _mp_extra)
        else:
            st.dataframe(_my_pitchers[["player_name", "position", "pro_team"]], use_container_width=True)
            if pf_26 is None:
                st.caption("pitcher_fantasy_2026.csv not found — run `plv build-fantasy-exports 2026`.")

        # ── ROS FP summary ────────────────────────────────────────────────────
        with st.expander("ROS FP estimate"):
            _ros_g = _ros_games(year)
            st.caption(f"Games remaining (approx): {_ros_g}")
            _ros_rows = []
            if hf_26 is not None and not _my_hitters.empty:
                _mh2 = _fuzzy_merge(_my_hitters, hf_26, model_name_col="batter_name")
                if not _mh2.empty and "core_fp_per_pa" in _mh2.columns:
                    _mh2["ros_fp_core"] = (_mh2["core_fp_per_pa"] * 3.5 * _ros_g).round(1)
                    for _, _r in _mh2[["player_name", "position", "ros_fp_core"]].iterrows():
                        _ros_rows.append({"name": _r["player_name"], "type": _r.get("position", "—"), "ros_fp": _r["ros_fp_core"]})
            if pf_26 is not None and not _my_pitchers.empty:
                _mp2 = _fuzzy_merge(_my_pitchers, pf_26)
                if not _mp2.empty and "fp_per_app" in _mp2.columns:
                    _apps = _mp2.apply(lambda r: 0.167 if r.get("pitcher_role") == "SP" else 0.333, axis=1)
                    _mp2["ros_fp"] = (_mp2["fp_per_app"] * _apps * _ros_g).round(1)
                    for _, _r in _mp2[["player_name", "pitcher_role", "ros_fp"]].iterrows():
                        _ros_rows.append({"name": _r["player_name"], "type": _r.get("pitcher_role", "RP"), "ros_fp": _r["ros_fp"]})
            if _ros_rows:
                _ros_df = pd.DataFrame(_ros_rows).sort_values("ros_fp", ascending=False).reset_index(drop=True)
                _ros_df.index += 1
                st.dataframe(_ros_df.style.format({"ros_fp": "{:.1f}"}, na_rep="--"), use_container_width=True)
                st.caption("ros_fp = core_fp_per_pa x 3.5 PA/game (hitters) or fp_per_app x apps/game (pitchers). Stuff-only, no SV/HD.")
            else:
                st.info("No model data to compute ROS estimates.")

    with _mt_tabs[1]:
        st.subheader("Matchup Analysis")
        _match_tabs = st.tabs(["Standings", "My Roster ROS"])

        with _match_tabs[0]:
            st.subheader("League Standings")
            _stand_df, _stand_err = _load_espn_standings()
            if _stand_err:
                st.error(f"ESPN API: {_stand_err}")
            elif _stand_df.empty:
                st.info("No standings data returned.")
            else:
                _stand_show = [c for c in ["team_name", "owner", "wins", "losses", "ties", "points_for", "points_against"] if c in _stand_df.columns]
                _stand_fmt  = {c: "{:.1f}" for c in ("points_for", "points_against") if c in _stand_df.columns}
                st.dataframe(_stand_df[_stand_show].style.format(_stand_fmt, na_rep="--"), use_container_width=True)

        with _match_tabs[1]:
            st.subheader("My Roster -- ROS Projections")
            hf_26 = load_hitter_fantasy(year)
            pf_26 = load_pitcher_fantasy(year)
            _ros_roster, _ros_r_err = _load_espn_roster()

            if _ros_r_err:
                st.error(f"ESPN API: {_ros_r_err}")
            elif _ros_roster.empty:
                st.info("No roster data.")
            else:
                _ros_g2 = _ros_games(year)
                st.caption(f"Approx. games remaining in 2026: **{_ros_g2}**")
                _ros_pit_pos = {"SP", "RP", "P"}
                _ros_my_h = _ros_roster[~_ros_roster["position"].isin(_ros_pit_pos)].copy()
                _ros_my_p = _ros_roster[_ros_roster["position"].isin(_ros_pit_pos)].copy()
                _ros_rows2 = []

                if hf_26 is not None and not _ros_my_h.empty:
                    _ros_mh = _fuzzy_merge(_ros_my_h, hf_26, model_name_col="batter_name")
                    if not _ros_mh.empty and "core_fp_per_pa" in _ros_mh.columns:
                        _ros_mh["ros_fp"] = (_ros_mh["core_fp_per_pa"] * 3.5 * _ros_g2).round(1)
                        _ros_mh["type"] = "H"
                        for _, _rr in _ros_mh[["player_name", "type", "ros_fp", "signal", "core_fp_per_pa", "process_plus"]].iterrows():
                            _ros_rows2.append(_rr.to_dict())

                if pf_26 is not None and not _ros_my_p.empty:
                    _ros_mp = _fuzzy_merge(_ros_my_p, pf_26)
                    if not _ros_mp.empty and "fp_per_app" in _ros_mp.columns:
                        _apps2 = _ros_mp.apply(lambda r: 0.167 if r.get("pitcher_role") == "SP" else 0.333, axis=1)
                        _ros_mp["ros_fp"] = (_ros_mp["fp_per_app"] * _apps2 * _ros_g2).round(1)
                        _ros_mp["type"] = _ros_mp.get("pitcher_role", pd.Series(["RP"] * len(_ros_mp), index=_ros_mp.index))
                        for _, _rr in _ros_mp[["player_name", "type", "ros_fp", "signal", "fp_per_app", "plv_blended"]].iterrows():
                            _ros_rows2.append(_rr.to_dict())

                if _ros_rows2:
                    _ros_summary = pd.DataFrame(_ros_rows2).sort_values("ros_fp", ascending=False).reset_index(drop=True)
                    _ros_summary.index += 1
                    _rs_fmt  = {"ros_fp": "{:.1f}", "core_fp_per_pa": "{:.3f}", "fp_per_app": "{:.3f}", "plv_blended": "{:.3f}", "process_plus": "{:.1f}"}
                    _rs_show = [c for c in ["player_name", "type", "ros_fp", "signal", "core_fp_per_pa", "process_plus", "fp_per_app", "plv_blended"] if c in _ros_summary.columns]
                    def _color_sig_ros(val):
                        return _BADGE_CSS.get(str(val), "")
                    _rs_styler = _ros_summary[_rs_show].style.format(_rs_fmt, na_rep="--")
                    if "signal" in _rs_show:
                        _rs_styler = _rs_styler.map(_color_sig_ros, subset=["signal"])
                    st.dataframe(_rs_styler, use_container_width=True)
                    _total_h = sum(r["ros_fp"] for r in _ros_rows2 if r.get("type") == "H" and pd.notna(r.get("ros_fp")))
                    _total_p = sum(r["ros_fp"] for r in _ros_rows2 if r.get("type") in ("SP", "RP") and pd.notna(r.get("ros_fp")))
                    st.metric("Total Hitter ROS FP", f"{_total_h:.0f}")
                    st.metric("Total Pitcher ROS FP", f"{_total_p:.0f}")
                    st.caption("Stuff-quality only -- add SV/HD premium manually for closers.")
                else:
                    st.info("No model data available to compute ROS projections.")

    with _mt_tabs[2]:
        st.subheader("Trade Analyzer")
        st.caption("Compare two groups of players using process model scores. Give = what you trade away. Receive = what you get back.")

        hf_26 = load_hitter_fantasy(year)
        pf_26 = load_pitcher_fantasy(year)
        _ta_all, _ta_err = _load_espn_all_teams()

        if _ta_err:
            st.error(f"ESPN API: {_ta_err}")
            st.stop()
        if _ta_all.empty:
            st.info("No league data. Check ESPN credentials in app/espn_connector.py.")
            st.stop()

        _ta_team_names = sorted(_ta_all["team_name"].dropna().unique().tolist())
        _ta_default = next((i for i, t in enumerate(_ta_team_names) if _MY_TEAM.lower() in t.lower()), 0)

        _ta_col1, _ta_col2 = st.columns(2)
        with _ta_col1:
            _give_team = st.selectbox("Give (your team)", _ta_team_names, index=_ta_default, key="ta_give_team")
            _give_players = sorted(_ta_all[_ta_all["team_name"] == _give_team]["player_name"].dropna().unique().tolist())
            _give_sel = st.multiselect("Players you give away", _give_players, key="ta_give_players")
        with _ta_col2:
            _recv_team = st.selectbox("Receive (other team)", _ta_team_names,
                                       index=min(1, len(_ta_team_names) - 1), key="ta_recv_team")
            _recv_players = sorted(_ta_all[_ta_all["team_name"] == _recv_team]["player_name"].dropna().unique().tolist())
            _recv_sel = st.multiselect("Players you receive", _recv_players, key="ta_recv_players")

        if not _give_sel and not _recv_sel:
            st.info("Select players from each side to compare.")
            st.stop()

        def _ta_build_side(names: list) -> pd.DataFrame:
            """Merge a list of player names against hitter + pitcher model data."""
            if not names:
                return pd.DataFrame()
            _df = pd.DataFrame({"player_name": names})
            rows = []
            _pit_pos = {"SP", "RP", "P"}
            for n in names:
                _row = {"player_name": n, "type": "?", "signal": "--", "proc_plus_positional": float("nan"),
                        "plv_blended": float("nan"), "core_fp_per_pa": float("nan"), "fp_per_app": float("nan"),
                        "sample_tier": "--"}
                # Try hitter
                if hf_26 is not None:
                    _hm = _fuzzy_merge(pd.DataFrame({"player_name": [n]}), hf_26, model_name_col="batter_name")
                    if not _hm.empty:
                        _hr = _hm.iloc[0]
                        _row.update({"type": "H", "signal": str(_hr.get("signal", "--")),
                                     "proc_plus_positional": _hr.get("proc_plus_positional", float("nan")),
                                     "core_fp_per_pa": _hr.get("core_fp_per_pa", float("nan")),
                                     "sample_tier": str(_hr.get("sample_tier", "--"))})
                        rows.append(_row)
                        continue
                # Try pitcher
                if pf_26 is not None:
                    _pm = _fuzzy_merge(pd.DataFrame({"player_name": [n]}), pf_26)
                    if not _pm.empty:
                        _pr = _pm.iloc[0]
                        role = str(_pr.get("pitcher_role", "P"))
                        _row.update({"type": role, "signal": str(_pr.get("signal", "--")),
                                     "plv_blended": _pr.get("plv_blended", float("nan")),
                                     "fp_per_app": _pr.get("fp_per_app", float("nan")),
                                     "sample_tier": str(_pr.get("sample_tier", "--"))})
                rows.append(_row)
            return pd.DataFrame(rows) if rows else pd.DataFrame()

        _give_df = _ta_build_side(_give_sel)
        _recv_df = _ta_build_side(_recv_sel)

        def _ta_agg(df: pd.DataFrame) -> dict:
            if df.empty:
                return {"signal_avg": 0, "top_add_count": 0, "fp_rate": 0.0}
            sig_vals = df["signal"].map(_SIG_RANK).fillna(0)
            fp_h = df[df["type"] == "H"]["core_fp_per_pa"].dropna().mean() or 0
            fp_p = df[df["type"].isin(["SP", "RP", "P"])]["fp_per_app"].dropna().mean() or 0
            return {
                "signal_avg": sig_vals.mean(),
                "top_add_count": int((sig_vals >= 3).sum()),
                "fp_rate": round((fp_h + fp_p) / max(1, (fp_h > 0) + (fp_p > 0)), 3),
            }

        _agg_give = _ta_agg(_give_df)
        _agg_recv = _ta_agg(_recv_df)

        _ta_disp_cols = [c for c in ["player_name", "type", "signal", "proc_plus_positional",
                                      "plv_blended", "core_fp_per_pa", "fp_per_app", "sample_tier"]]
        _ta_fmt = {"proc_plus_positional": "{:.1f}", "plv_blended": "{:.3f}",
                   "core_fp_per_pa": "{:.3f}", "fp_per_app": "{:.3f}"}

        st.divider()
        _tc1, _tc2 = st.columns(2)
        with _tc1:
            st.subheader(f"You Give ({len(_give_sel)} players)")
            if not _give_df.empty:
                _give_show = [c for c in _ta_disp_cols if c in _give_df.columns]
                def _cs_give(val): return _BADGE_CSS.get(str(val), "")
                _gs = _give_df[_give_show].style.format(_ta_fmt, na_rep="--")
                if "signal" in _give_show: _gs = _gs.map(_cs_give, subset=["signal"])
                st.dataframe(_gs, use_container_width=True, hide_index=True)
            else:
                st.info("No players selected.")
        with _tc2:
            st.subheader(f"You Receive ({len(_recv_sel)} players)")
            if not _recv_df.empty:
                _recv_show = [c for c in _ta_disp_cols if c in _recv_df.columns]
                def _cs_recv(val): return _BADGE_CSS.get(str(val), "")
                _rs = _recv_df[_recv_show].style.format(_ta_fmt, na_rep="--")
               