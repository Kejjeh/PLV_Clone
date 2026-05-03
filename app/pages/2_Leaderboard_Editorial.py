"""
Editorial Dense leaderboard — Variation E (HANDOFF.md).
Hybrid: editorial HTML chrome + native st.dataframe (LineChartColumn, ProgressColumn, on_select).
"""
from __future__ import annotations

import math
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit import column_config as cc

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent   # app/pages/
_APP  = _HERE.parent                       # app/
_ROOT = _APP.parent                        # repo root
for _p in (str(_APP), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from plv_clone.config import get_config
from plv_clone.utils.season_stage import infer_stage, get_thresholds

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="The Process Report",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Color palettes ────────────────────────────────────────────────────────────
_L = dict(
    bg="#f7f3ec", panel="#fdfaf3", stripe="#f3eee4", border="#e3dccb",
    text="#1a1815", dim="#7a7261", faint="#d4ccba",
    accent="#a8421f", pos="#56753f", neg="#9d3540", warn="#a8761f",
    hr=168, hg=66, hb=31, hmax=0.30,
)
_D = dict(
    bg="#1a1815", panel="#211e1a", stripe="#1d1b17", border="#34302a",
    text="#f5f1ea", dim="#8d8579", faint="#3a352e",
    accent="#d97757", pos="#7fb069", neg="#c1666b", warn="#d4a945",
    hr=217, hg=119, hb=87, hmax=0.40,
)

# ── Session-state defaults ────────────────────────────────────────────────────
_DEFS: dict = {
    "ed_dark": False, "ed_pinned": [], "ed_sel": None,
    "ed_pos": [], "ed_min_pa": None, "ed_min_proc": 95,
    "ed_sort": "process_plus", "ed_rows": 50,
    "ed_year": 2026,
}
for _k, _v in _DEFS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Data loaders ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _load_hitters(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"master_hitter_{year}.csv"
    return pd.read_csv(p) if p.exists() else None


@st.cache_data(ttl=300)
def _load_rolling(year: int) -> pd.DataFrame | None:
    cfg = get_config()
    p = cfg.outputs_dir / f"process_plus_rolling_{year}.csv"
    return pd.read_csv(p, parse_dates=["date"]) if p.exists() else None


@st.cache_data(ttl=300)
def _build_sparks(year: int) -> dict[int, list[float]]:
    df = _load_rolling(year)
    if df is None or df.empty or "contact_value_mean" not in df.columns:
        return {}
    df = df.copy()
    df["_p"] = df["contact_value_mean"].fillna(0) + df.get("power_value_mean", pd.Series(0, index=df.index)).fillna(0)
    df["_w"] = df["date"].dt.to_period("W")
    weekly = df.groupby(["batter", "_w"])["_p"].mean().reset_index().sort_values(["batter", "_w"])
    return {int(bid): grp["_p"].tail(12).tolist() for bid, grp in weekly.groupby("batter")}


# ── Top control bar (dark mode + season) ──────────────────────────────────────
_tc1, _tc2, _tc3 = st.columns([6, 1, 1])
with _tc2:
    _yr_opts = [2026, 2025, 2024, 2023, 2022]
    _yr_idx = _yr_opts.index(st.session_state.ed_year) if st.session_state.ed_year in _yr_opts else 0
    year = st.selectbox("Season", _yr_opts, index=_yr_idx, key="ed_year_sel",
                        label_visibility="collapsed")
    st.session_state.ed_year = year
with _tc3:
    dark = st.toggle("🌙 Dark", value=st.session_state.ed_dark, key="ed_dark_tog")
    st.session_state.ed_dark = dark

c = _D if dark else _L

# ── Fonts + global CSS ────────────────────────────────────────────────────────
st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;1,8..60,400;1,8..60,500&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
.stApp, section.main > div.block-container {{ background: {c['bg']} !important }}
div[data-testid="stMainBlockContainer"] {{ background: {c['bg']} }}
.block-container {{ padding-top: 0.5rem !important }}
/* editorial dataframe chrome */
[data-testid="stDataFrame"] {{ border: 1px solid {c['border']} !important; border-radius: 4px }}
[data-testid="stDataFrame"] th {{
  font-family: "IBM Plex Mono", ui-monospace, monospace !important;
  font-size: 10px !important; letter-spacing: .06em; text-transform: uppercase;
  background: {c['panel']} !important; color: {c['dim']} !important;
}}
[data-testid="stDataFrame"] td {{
  font-family: "IBM Plex Mono", ui-monospace, monospace !important;
  font-size: 11px !important; color: {c['text']} !important;
}}
/* sticky second column (player name) */
[data-testid="stDataFrame"] th:nth-child(2),
[data-testid="stDataFrame"] td:nth-child(2) {{
  position: sticky !important; left: 0; z-index: 2;
  background: {c['panel']} !important;
  font-family: "Source Serif 4", Georgia, serif !important;
  font-size: 13px !important;
}}
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
raw    = _load_hitters(year)
sparks = _build_sparks(year)
rolling = _load_rolling(year)

# ── Season stage detection (drives min-PA default) ────────────────────────────
_season_date = None
if rolling is not None and "date" in rolling.columns and not rolling.empty:
    _max = pd.to_datetime(rolling["date"]).max()
    if pd.notna(_max):
        _season_date = _max.date()
_stage = infer_stage(hitters=raw, pitchers=None, season_date=_season_date)
_thresh = get_thresholds(_stage)
# First load: snap min_pa to stage default
if st.session_state.ed_min_pa is None:
    st.session_state.ed_min_pa = int(_thresh.min_pa_for_boards)

try:
    _sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                   stderr=subprocess.DEVNULL).decode().strip().upper()
except Exception:
    _sha = "LOCAL"

_today     = date.today()
_issue_no  = _today.timetuple().tm_yday // 7 + 1
_issue_lbl = f"Vol. II · No. {_issue_no} · {_thresh.stage_label} · Build {_sha}"

# ── Masthead ──────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{c['panel']};border-bottom:2px solid {c['border']};
            padding:10px 20px 9px;display:flex;align-items:flex-end;
            justify-content:space-between;margin-bottom:0">
  <div>
    <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;
                letter-spacing:.12em;text-transform:uppercase;color:{c['dim']};font-weight:600">
      {_issue_lbl}
    </div>
    <div style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:28px;
                color:{c['text']};line-height:1.1;margin-top:2px">
      The Process Report
    </div>
  </div>
  <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;
              color:{c['dim']};text-align:right;padding-bottom:4px">
    Unofficial · public Statcast data<br>{year} season
  </div>
</div>
""", unsafe_allow_html=True)

# ── Section nav ───────────────────────────────────────────────────────────────
_nav_items = ["Hitters", "Pitchers", "Targets", "Trends", "Waiver", "My Team"]

def _nav_chip(label: str, active: bool) -> str:
    if active:
        style = (f"color:{c['text']};border-bottom:2px solid {c['accent']};"
                 f"font-weight:600;cursor:default")
    else:
        style = (f"color:{c['faint']};border-bottom:2px solid transparent;"
                 f"cursor:not-allowed;opacity:.55")
    return (f'<span style="font-family:\'IBM Plex Mono\',ui-monospace,monospace;'
            f'font-size:11px;letter-spacing:.06em;text-transform:uppercase;'
            f'padding:7px 14px;{style}">{label}</span>')

st.markdown(f"""
<div style="background:{c['panel']};border-bottom:1px solid {c['border']};
            display:flex;align-items:center;padding:0 8px;margin-bottom:6px">
  {''.join(_nav_chip(n, n == "Hitters") for n in _nav_items)}
</div>
""", unsafe_allow_html=True)

def _apply_preset(*, pos=None, min_proc=None, min_pa=None, sort=None) -> None:
    """Update both the canonical session-state keys and the widget keys."""
    if pos is not None:
        st.session_state.ed_pos = list(pos)
        st.session_state["ed_pos_ms"] = list(pos)
    if min_proc is not None:
        st.session_state.ed_min_proc = int(min_proc)
        st.session_state["ed_mpr"] = int(min_proc)
    if min_pa is not None:
        st.session_state.ed_min_pa = int(min_pa)
        st.session_state["ed_mpa"] = int(min_pa)
    if sort is not None:
        st.session_state.ed_sort = sort
        st.session_state["ed_sort_sel"] = sort

# Preset buttons (real Streamlit buttons — render before guards/data filters)
_pb1, _pb2, _pb3, _pb4, _pb5 = st.columns([1, 1, 1, 1, 6])
with _pb1:
    if st.button("Catchers", key="ed_pst_c", use_container_width=True):
        _apply_preset(pos=["C"])
        st.rerun()
with _pb2:
    if st.button("Outfielders", key="ed_pst_of", use_container_width=True):
        _apply_preset(pos=["OF"])
        st.rerun()
with _pb3:
    if st.button("Power+ > 130", key="ed_pst_pwr", use_container_width=True):
        _apply_preset(pos=[], min_proc=130, sort="power_plus")
        st.rerun()
with _pb4:
    if st.button("Reset", key="ed_pst_rst", use_container_width=True):
        _apply_preset(
            pos=[], min_proc=95,
            min_pa=int(_thresh.min_pa_for_boards),
            sort="process_plus",
        )
        st.rerun()

# ── Guard: need data ──────────────────────────────────────────────────────────
if raw is None or raw.empty:
    st.error(f"master_hitter_{year}.csv not found. Run: `plv build-master {year}`")
    st.stop()

df_all = raw.copy()

# ── Collect positions ─────────────────────────────────────────────────────────
_pos_order = {"C": 0, "1B": 1, "2B": 2, "3B": 3, "SS": 4, "OF": 5, "DH": 6}
_all_pos: list[str] = []
if "fantasy_positions" in df_all.columns:
    for _fp in df_all["fantasy_positions"].dropna():
        _all_pos.extend(str(_fp).split("|"))
    _all_pos = sorted(set(p for p in _all_pos if p),
                      key=lambda p: _pos_order.get(p, 99))

# ── Spotlight lede + 4 callouts ───────────────────────────────────────────────
_qual = (df_all[df_all["pa"] >= int(_thresh.min_pa_for_boards)].copy()
         if "pa" in df_all.columns else df_all.copy())

if not _qual.empty and "process_plus" in _qual.columns:
    _top  = _qual.nlargest(1, "process_plus").iloc[0]
    _tname, _tproc, _tpa = str(_top["batter_name"]), float(_top["process_plus"]), int(_top["pa"])
    _tpos  = str(_top.get("primary_position", "—"))
    _tsig  = str(_top.get("signal", ""))
    _tcav  = str(_top.get("sample_tier", ""))

    _caveat = (f"Early-season sample ({_tpa} PA) — treat with appropriate caution."
               if _tcav in ("Too Small", "Small") else
               f"{_tpa} PA through {_today.strftime('%b %d')}.")

    _power_row = _qual.nlargest(1, "power_plus").iloc[0] if "power_plus" in _qual.columns else None
    _kavd_row  = _qual.nlargest(1, "k_avoidance_plus").iloc[0] if "k_avoidance_plus" in _qual.columns else None

    _hot_name: str | None = None
    _hot_val: float | None = None
    if rolling is not None and not rolling.empty and "contact_value_mean" in rolling.columns:
        _anchor = pd.to_datetime(rolling["date"]).max()
        if pd.notna(_anchor):
            _cut = _anchor - pd.Timedelta(days=7)
            _rec = rolling[pd.to_datetime(rolling["date"]) >= _cut]
            if not _rec.empty:
                _grp = (_rec.assign(_px=_rec["contact_value_mean"].fillna(0))
                            .groupby("batter_name")["_px"].mean())
                if not _grp.empty:
                    _hot_name = str(_grp.idxmax())
                    _hot_val  = float(_grp.max())

    _stealth_name: str | None = None
    _stealth_val:  float | None = None
    if "proc_plus_positional" in _qual.columns and "signal" in _qual.columns:
        _st_df = _qual[~_qual["signal"].isin(["Top Target", "Strong Add"])]
        if not _st_df.empty:
            _st_top = _st_df.nlargest(1, "proc_plus_positional").iloc[0]
            _stealth_name = str(_st_top["batter_name"])
            _stealth_val  = float(_st_top["proc_plus_positional"])

    def _callout_html(label: str, value: str, name: str, sub: str = "") -> str:
        _dim, _acc, _txt = c["dim"], c["accent"], c["text"]
        _panel, _border = c["panel"], c["border"]
        _sub_html = (f'<div style="font-family:IBM Plex Mono,monospace;font-size:9px;'
                     f'color:{_dim}">{sub}</div>') if sub else ""
        return (
            f'<div style="background:{_panel};border:1px solid {_border};'
            f'border-radius:4px;padding:10px 12px;height:88px">'
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:9px;'
            f'letter-spacing:.1em;text-transform:uppercase;color:{_dim};font-weight:600">{label}</div>'
            f'<div style="font-family:Source Serif 4,Georgia,serif;font-style:italic;'
            f'font-size:22px;color:{_acc};line-height:1.1;margin-top:2px">{value}</div>'
            f'<div style="font-family:Source Serif 4,Georgia,serif;font-size:12px;color:{_txt}">{name}</div>'
            f'{_sub_html}</div>'
        )

    _lc, _rc = st.columns([1.4, 1])
    with _lc:
        st.markdown(f"""<div style="background:{c['panel']};border:1px solid {c['border']};
border-radius:4px;padding:16px 18px;height:100%">
  <div style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:19px;
              color:{c['text']};line-height:1.3">
    {_tname} tops the early-season leaderboard at {_tproc:.1f} Process+
  </div>
  <div style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:13px;
              color:{c['dim']};margin-top:6px;line-height:1.5">{_caveat}</div>
  <div style="margin-top:8px;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;
              color:{c['dim']};display:flex;gap:14px">
    <span>{_tpa} PA</span><span>{_tpos}</span>
    <span style="color:{c['warn']}">{_tsig}</span>
    <span style="color:{c['accent']}">Read full report →</span>
  </div>
</div>""", unsafe_allow_html=True)

    with _rc:
        _g1, _g2 = st.columns(2)
        with _g1:
            if _power_row is not None:
                st.markdown(_callout_html("Power+ Leader",
                    f"{_power_row['power_plus']:.0f}", str(_power_row["batter_name"])), unsafe_allow_html=True)
            if _hot_name is not None and _hot_val is not None:
                st.markdown(_callout_html("Hottest 7d",
                    f"{_hot_val:+.3f}", _hot_name, "rolling contact value"), unsafe_allow_html=True)
        with _g2:
            if _kavd_row is not None:
                st.markdown(_callout_html("K-Avoidance",
                    f"{_kavd_row['k_avoidance_plus']:.0f}", str(_kavd_row["batter_name"])), unsafe_allow_html=True)
            if _stealth_name is not None and _stealth_val is not None:
                st.markdown(_callout_html("Stealth",
                    f"{_stealth_val:.1f}", _stealth_name, "high ProcPos · low signal"), unsafe_allow_html=True)

st.markdown(f'<div style="height:8px"></div>', unsafe_allow_html=True)

# ── Watchlist chips ───────────────────────────────────────────────────────────
_pinned: list[str] = list(st.session_state.ed_pinned)
_all_names = df_all["batter_name"].dropna().tolist() if not df_all.empty else []

_chip_html = (
    f'<span style="font-family:\'IBM Plex Mono\',ui-monospace,monospace;font-size:10px;'
    f'letter-spacing:.08em;text-transform:uppercase;color:{c["dim"]};font-weight:600;'
    f'margin-right:10px">↟ Following</span>'
)
for _pn in _pinned:
    _pv = ""
    _pm = df_all[df_all["batter_name"] == _pn]["process_plus"] if "process_plus" in df_all.columns else pd.Series()
    if not _pm.empty:
        _pv = (f'<span style="color:{c["accent"]};font-style:italic;'
               f'font-family:\'Source Serif 4\',Georgia,serif"> {_pm.iloc[0]:.1f}</span>')
    _chip_html += (
        f'<span style="background:{c["panel"]};border:1px solid {c["border"]};'
        f'border-radius:12px;padding:3px 10px;margin-right:6px;'
        f'font-family:\'Source Serif 4\',Georgia,serif;font-style:italic;'
        f'font-size:12px;color:{c["text"]}">{_pn}{_pv}</span>'
    )
_chip_html += (
    f'<span style="border:1px dashed {c["border"]};border-radius:12px;padding:3px 10px;'
    f'font-family:\'IBM Plex Mono\',ui-monospace,monospace;font-size:10px;color:{c["dim"]}">+ follow</span>'
)

_wl1, _wl2 = st.columns([5, 1])
with _wl1:
    st.markdown(f'<div style="padding:5px 0">{_chip_html}</div>', unsafe_allow_html=True)
with _wl2:
    _add = st.selectbox("Follow", [""] + _all_names, key="ed_follow",
                        label_visibility="collapsed")
    if _add and _add not in _pinned:
        st.session_state.ed_pinned.append(_add)
        st.rerun()

if _pinned:
    _uf_cols = st.columns(min(len(_pinned), 8))
    for _i, _pn in enumerate(_pinned[:8]):
        with _uf_cols[_i]:
            if st.button(f"× {_pn}", key=f"unpin_{_pn}", help="Unfollow"):
                st.session_state.ed_pinned.remove(_pn)
                st.rerun()

st.markdown(f'<hr style="border:none;border-top:1px solid {c["border"]};margin:6px 0 10px">', unsafe_allow_html=True)

# ── Filters strip ─────────────────────────────────────────────────────────────
_lbl = (f"font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;"
        f"letter-spacing:.08em;text-transform:uppercase;font-weight:600;color:{c['dim']}")

_fc = st.columns([2, 1, 1, 2, 1])
with _fc[0]:
    st.markdown(f'<div style="{_lbl}">Position</div>', unsafe_allow_html=True)
    sel_pos = st.multiselect("pos", _all_pos, default=st.session_state.ed_pos,
                             label_visibility="collapsed", key="ed_pos_ms")
    st.session_state.ed_pos = sel_pos

with _fc[1]:
    st.markdown(f'<div style="{_lbl}">Min PA</div>', unsafe_allow_html=True)
    min_pa = int(st.number_input("min_pa", 0, 500, st.session_state.ed_min_pa,
                                 step=10, label_visibility="collapsed", key="ed_mpa"))
    st.session_state.ed_min_pa = min_pa

with _fc[2]:
    st.markdown(f'<div style="{_lbl}">Min Proc+</div>', unsafe_allow_html=True)
    min_proc = int(st.number_input("min_proc", 0, 200, st.session_state.ed_min_proc,
                                   step=5, label_visibility="collapsed", key="ed_mpr"))
    st.session_state.ed_min_proc = min_proc

with _fc[3]:
    st.markdown(f'<div style="{_lbl}">Sort</div>', unsafe_allow_html=True)
    _sort_opts = ["process_plus", "proc_plus_positional", "k_avoidance_plus",
                  "power_plus", "pa", "blast_rate", "avg_swing_speed"]
    _sort_idx = _sort_opts.index(st.session_state.ed_sort) if st.session_state.ed_sort in _sort_opts else 0
    sort_col = st.selectbox("sort", _sort_opts, index=_sort_idx,
                            label_visibility="collapsed", key="ed_sort_sel")
    st.session_state.ed_sort = sort_col

with _fc[4]:
    st.markdown(f'<div style="{_lbl}">Rows</div>', unsafe_allow_html=True)
    n_rows = int(st.selectbox("rows", [25, 50, 100, 250], index=1,
                              label_visibility="collapsed", key="ed_rows_sel"))
    st.session_state.ed_rows = n_rows

# ── Apply filters ─────────────────────────────────────────────────────────────
df = df_all.copy()
if min_pa > 0:
    df = df[df["pa"] >= min_pa]
if min_proc > 0 and "process_plus" in df.columns:
    df = df[df["process_plus"] >= min_proc]
if sel_pos and "fantasy_positions" in df.columns:
    df = df[df["fantasy_positions"].fillna("").apply(
        lambda fp: any(p in fp.split("|") for p in sel_pos))]
if sort_col in df.columns:
    df = df.sort_values(sort_col, ascending=False)
df = df.head(n_rows).reset_index(drop=True)

st.markdown(
    f'<div style="font-family:\'IBM Plex Mono\',ui-monospace,monospace;font-size:10px;'
    f'color:{c["dim"]};text-align:right;padding-bottom:4px">'
    f'{len(df)} / {len(df_all)} hitters</div>',
    unsafe_allow_html=True,
)

# ── § I Section heading ───────────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex;align-items:center;gap:12px;margin:8px 0 4px">
  <hr style="flex:1;border:none;border-top:1px solid {c['border']}">
  <span style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;
               font-size:16px;color:{c['text']};white-space:nowrap">
    § I &nbsp; The Leaderboard
  </span>
  <hr style="flex:1;border:none;border-top:1px solid {c['border']}">
  <span style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:9px;
               letter-spacing:.1em;text-transform:uppercase;color:{c['dim']};white-space:nowrap">
    RANKED BY {sort_col.upper().replace('_', ' ')}
  </span>
</div>
""", unsafe_allow_html=True)

# ── Build display DataFrame ───────────────────────────────────────────────────
_col_map = {
    "batter_name":               "Player",
    "pa":                        "PA",
    "primary_position":          "Pos",
    "fantasy_positions_display": "FPos",
    "process_plus":              "Proc+",
    "_spark":                    "12W",
    "proc_plus_positional":      "ProcPos",
    "k_avoidance_plus":          "K-Avd+",
    "power_plus":                "Power+",
    "swing_pct":                 "Swg%",
    "chase_pct":                 "Chs%",
    "xwoba_on_contact":          "MC",
    "xwoba_vs_expected":         "MCi",
    "blast_rate":                "Blast",
    "avg_swing_speed":           "EV",
    "signal":                    "Signal",
    "risk_flag":                 "Risk",
}

df_d = df.copy()
df_d["_spark"] = df_d["batter"].apply(lambda bid: sparks.get(int(bid), None))
keep = [k for k in _col_map if k in df_d.columns]
df_d = df_d[keep].rename(columns=_col_map)
df_d.index = range(1, len(df_d) + 1)  # 1-based rank

# Replace literal/string "None" in FPos and Pos with em-dash
for _txt_col in ("FPos", "Pos"):
    if _txt_col in df_d.columns:
        df_d[_txt_col] = (
            df_d[_txt_col].astype(object).where(df_d[_txt_col].notna(), "—")
                          .replace({"None": "—", "nan": "—", "": "—"})
        )

# Column config
_cfg: dict = {}
if "12W" in df_d.columns:
    _cfg["12W"] = cc.LineChartColumn("12W", width="small")
if "Power+" in df_d.columns:
    _cfg["Power+"] = cc.ProgressColumn("Power+", min_value=50, max_value=200, format="%.0f")
if "K-Avd+" in df_d.columns:
    _cfg["K-Avd+"] = cc.ProgressColumn("K-Avd+", min_value=50, max_value=200, format="%.0f")
if "Proc+" in df_d.columns:
    _cfg["Proc+"] = cc.NumberColumn("Proc+", format="%.1f")
if "ProcPos" in df_d.columns:
    _cfg["ProcPos"] = cc.NumberColumn("ProcPos", format="%.1f")
if "PA" in df_d.columns:
    _cfg["PA"] = cc.NumberColumn("PA", format="%d")
for _pct_col in ("Swg%", "Chs%", "Blast"):
    if _pct_col in df_d.columns:
        _cfg[_pct_col] = cc.NumberColumn(_pct_col, format="%.1%")
for _flt_col in ("MC", "MCi"):
    if _flt_col in df_d.columns:
        _cfg[_flt_col] = cc.NumberColumn(_flt_col, format="%.3f")
if "EV" in df_d.columns:
    _cfg["EV"] = cc.NumberColumn("EV", format="%.1f")
if "Signal" in df_d.columns:
    _cfg["Signal"] = cc.TextColumn("Signal")
if "Risk" in df_d.columns:
    _cfg["Risk"] = cc.TextColumn("Risk", width="medium")

# CSV export (before table so it sits above)
_dl_col, _info_col = st.columns([1, 5])
with _dl_col:
    st.download_button(
        "⬇ Export CSV",
        df.to_csv(index=False),
        file_name=f"process_report_{year}.csv",
        mime="text/csv",
        key="ed_csv",
    )

# Color-coded Risk / Signal cells via Styler
_SIGNAL_COLORS = {
    "Top Target":  c["pos"],
    "Strong Add":  c["pos"],
    "Add":         c["pos"],
    "Hold":        c["dim"],
    "Stash":       c["warn"],
    "Drop":        c["neg"],
    "Chase Risk":  c["warn"],
    "Power Flag":  c["accent"],
}
_RISK_COLORS = {
    "Too Small":   c["dim"],
    "Small":       c["dim"],
    "Chase Risk":  c["warn"],
    "Power Flag":  c["accent"],
    "K Risk":      c["neg"],
    "Reg Risk":    c["neg"],
}

def _chip_style(value, palette: dict) -> str:
    if pd.isna(value) or value in ("", "—"):
        return ""
    color = palette.get(str(value).strip(), c["text"])
    return (f"color:{color};font-weight:600;"
            f"font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;"
            f"letter-spacing:.04em;text-transform:uppercase")

_styler = df_d.style
if "Signal" in df_d.columns:
    _styler = _styler.map(lambda v: _chip_style(v, _SIGNAL_COLORS), subset=["Signal"])
if "Risk" in df_d.columns:
    _styler = _styler.map(lambda v: _chip_style(v, _RISK_COLORS), subset=["Risk"])

# Render table
_tbl_h = min(max(len(df_d) * 35 + 42, 200), 700)
try:
    _sel_state = st.dataframe(
        _styler,
        column_config=_cfg,
        on_select="rerun",
        selection_mode="single-row",
        use_container_width=True,
        hide_index=False,
        height=_tbl_h,
        key="ed_tbl",
    )
    if _sel_state.selection.rows:
        _row_idx = _sel_state.selection.rows[0]
        _new_sel = str(df_d.iloc[_row_idx]["Player"]) if "Player" in df_d.columns else None
        if _new_sel and _new_sel != st.session_state.ed_sel:
            st.session_state.ed_sel = _new_sel
            st.rerun()
except TypeError:
    st.dataframe(_styler, column_config=_cfg, use_container_width=True,
                 hide_index=False, height=_tbl_h)

_sel_player = st.session_state.ed_sel

# ── § II Distribution strip ───────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex;align-items:center;gap:12px;margin:16px 0 8px">
  <hr style="flex:1;border:none;border-top:1px solid {c['border']}">
  <span style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;
               font-size:16px;color:{c['text']};white-space:nowrap">
    § II &nbsp; Where {_sel_player or '…'} stands
  </span>
  <hr style="flex:1;border:none;border-top:1px solid {c['border']}">
</div>
""", unsafe_allow_html=True)

# Selected player values for highlighting
_sel_vals: dict[str, float | None] = {}
if _sel_player:
    _srow = df_all[df_all["batter_name"] == _sel_player]
    for _dc in ("process_plus", "k_avoidance_plus", "power_plus", "swing_pct"):
        if not _srow.empty and _dc in _srow.columns:
            _v = _srow.iloc[0][_dc]
            _sel_vals[_dc] = None if pd.isna(_v) else float(_v)

_dist_metrics = [
    ("process_plus",     "Process+"),
    ("k_avoidance_plus", "K-Avoidance+"),
    ("power_plus",       "Power+"),
    ("swing_pct",        "Swing%"),
]

_base_pop = df_all[df_all["pa"] >= 30] if "pa" in df_all.columns else df_all

def _altair_hist(col: str, label: str, sel_val: float | None) -> None:
    try:
        import altair as alt
        vals = _base_pop[col].dropna() if col in _base_pop.columns else pd.Series()
        if len(vals) < 10:
            return
        lo, hi = float(vals.min()), float(vals.max())
        bins_pd = pd.cut(vals, bins=25)
        counts  = bins_pd.value_counts().sort_index()
        rows = []
        for iv, cnt in counts.items():
            is_sel = (sel_val is not None and
                      iv.left <= sel_val <= iv.right)
            rows.append({"left": float(iv.left), "right": float(iv.right),
                         "count": int(cnt),
                         "color": c["accent"] if is_sel else c["faint"]})
        hdf = pd.DataFrame(rows)
        chart = (
            alt.Chart(hdf)
            .mark_bar(stroke=None)
            .encode(
                x=alt.X("left:Q", title=label,
                         axis=alt.Axis(labelFont="IBM Plex Mono", titleFont="IBM Plex Mono",
                                       labelFontSize=9, titleFontSize=9, grid=False)),
                x2="right:Q",
                y=alt.Y("count:Q", title="",
                         axis=alt.Axis(labels=False, ticks=False, grid=False)),
                color=alt.Color("color:N", scale=None),
                tooltip=[alt.Tooltip("left:Q", format=".1f", title=label),
                         alt.Tooltip("count:Q", title="n")],
            )
            .properties(height=80, width="container", background="transparent")
        )
        st.altair_chart(chart, use_container_width=True)
        if sel_val is not None:
            pct = float((vals <= sel_val).mean() * 100)
            st.caption(f"{label}: {sel_val:.1f} · {pct:.0f}th pctile")
    except Exception:
        if sel_val is not None:
            st.metric(label, f"{sel_val:.1f}")

_dc_cols = st.columns(len(_dist_metrics))
for _i, (_dcol, _dlbl) in enumerate(_dist_metrics):
    with _dc_cols[_i]:
        _altair_hist(_dcol, _dlbl, _sel_vals.get(_dcol))
