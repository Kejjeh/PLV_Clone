#!/usr/bin/env python3
"""
Generate a standalone Process Report HTML file with real data injected.

Reads hitter / pitcher / target / rolling CSVs and injects:
    window.REPORT_META, window.HITTERS, window.SPARKS, window.DISTRIBUTIONS,
    window.PITCHERS, window.TARGETS, window.ROLLING, window.WAIVER
into app/reports/process_report_template.html, writing
data/outputs/process_report_{year}.html.

Usage:
    python scripts/generate_report.py [--year 2026]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT     = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app" / "reports" / "process_report_template.html"
OUT_DIR  = ROOT / "data" / "outputs"
APP_DIR  = ROOT / "app"

# Allow `from espn_connector import …`
for _p in (str(ROOT), str(APP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MIN_PA       = 10          # generous floor — UI filters scope the leaderboard
LEDE_MIN_PA  = 40          # leader pick for the top-of-page headline
TOP_N        = 9999        # effectively no cap — load everyone for Trends/search
SPARK_WEEKS  = 12
MIN_PITCHES  = 100
ROLLING_KEEP = 60          # last N daily points per player for Trends
WAIVER_MIN_PA      = 10    # ESPN free-agent hitters with this many PA make the wire
WAIVER_MIN_PITCHES = 50    # ESPN free-agent pitchers
WAIVER_TOP_N       = 9999  # show every ESPN free agent that joined master
ESPN_FA_SIZE       = 800   # how many free agents to pull from ESPN

# ESPN slots that aren't real fantasy positions for filtering
_ESPN_NON_POS = {"BE", "IL", "UTIL", "IF", "P"}


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _f(v, ndigits: int | None = None):
    """NaN/None -> '—'; otherwise number, optionally rounded."""
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(f):
        return "—"
    return round(f, ndigits) if ndigits is not None else f


def _s(v, default: str = "—") -> str:
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    s = str(v).strip()
    return s if s and s.lower() != "nan" else default


def _disambig_suffix(mlb_id) -> str:
    """Suffix appended to colliding names: '(#1970)' from MLB ID 571970."""
    try:
        return f"(#{str(int(mlb_id))[-4:]})"
    except Exception:
        return ""


# ─── HITTERS ──────────────────────────────────────────────────────────────────
def _detect_hitter_dups(master: pd.DataFrame) -> set[str]:
    """Names that map to multiple master rows (e.g. Max Muncy LAD vs A's)."""
    df = master[master["pa"].fillna(0) >= MIN_PA]
    counts = df.groupby("batter_name").size()
    return set(counts[counts > 1].index)


def _row_name(clean: str, mlb_id, dup_names: set[str], pro_team: str = "") -> str:
    """Append disambiguating suffix when a name collides.
    Prefers '(LAD)' when the ESPN proTeam is known, otherwise '(#1970)'."""
    if clean and clean in dup_names:
        if pro_team:
            return f"{clean} ({pro_team})"
        suf = _disambig_suffix(mlb_id)
        if suf:
            return f"{clean} {suf}"
    return clean




def build_hitters(master: pd.DataFrame,
                  dup_names: set[str] | None = None,
                  mlb_to_team: dict[int, str] | None = None) -> list[dict]:
    df = master.copy()
    df = df[df["pa"].fillna(0) >= MIN_PA]
    df = df.sort_values("process_plus", ascending=False, na_position="last").head(TOP_N).reset_index(drop=True)
    if dup_names is None:
        dup_names = _detect_hitter_dups(master)
    mlb_to_team = mlb_to_team or {}

    rows: list[dict] = []
    for i, r in df.iterrows():
        clean = _s(r.get("batter_name"))
        mlb_id = int(r["batter"]) if not pd.isna(r.get("batter")) else 0
        team = mlb_to_team.get(mlb_id, "")
        rows.append({
            "rank":      int(i) + 1,
            "name":      _row_name(clean, mlb_id, dup_names, team),
            "cleanName": clean,
            "mlbId":     mlb_id,
            "pa":        int(r["pa"]) if not pd.isna(r.get("pa")) else 0,
            "pos":       _s(r.get("primary_position")),
            "fpos":      _s(r.get("fantasy_positions_display")),
            "proc":      _f(r.get("process_plus"), 1),
            "procPos":   _f(r.get("proc_plus_positional"), 1),
            "kavoid":    _f(r.get("k_avoidance_plus"), 1),
            "power":     _f(r.get("power_plus"), 1),
            "swing":     _f((r.get("swing_pct") or 0) * 100, 1)
                         if not pd.isna(r.get("swing_pct")) else "—",
            "chase":     _f((r.get("chase_pct") or 0) * 100, 1)
                         if not pd.isna(r.get("chase_pct")) else "—",
            "mc":        _f(r.get("xwoba_on_contact"), 3),
            "mci":       _f(r.get("xwoba_vs_expected"), 3),
            "blast":     _f((r.get("blast_rate") or 0) * 100, 1)
                         if not pd.isna(r.get("blast_rate")) else "—",
            "ev":        _f(r.get("avg_swing_speed"), 1),
            "signal":    _s(r.get("signal")),
            "flag":      _s(r.get("risk_flag")),
            "sample":    _s(r.get("sample_tier")),
        })
    return rows


def build_sparks(targets: list[dict],
                 rolling: pd.DataFrame | None) -> dict[str, list[float]]:
    """Build 12-week trajectories for any name/proc dicts (top-50 + my-team)."""
    out: dict[str, list[float]] = {}
    if rolling is None or rolling.empty:
        for h in targets:
            proc = h["proc"] if isinstance(h["proc"], (int, float)) else 100.0
            out[h["name"]] = [float(proc)] * SPARK_WEEKS
        return out

    rolling = rolling.copy()
    rolling["date"] = pd.to_datetime(rolling["date"], errors="coerce")
    rolling = rolling.dropna(subset=["date"])
    rolling["weekly_score"] = (
        rolling["contact_value_mean"].fillna(0) + rolling["power_value_mean"].fillna(0)
    )

    for h in targets:
        if h["name"] in out:
            continue
        proc = float(h["proc"]) if isinstance(h["proc"], (int, float)) else 100.0
        # Use MLB ID for join when available — disambiguates same-named players.
        mlb_id = h.get("mlbId")
        if mlb_id:
            sub = rolling[rolling["batter"] == mlb_id].sort_values("date")
        else:
            sub = rolling[rolling["batter_name"] == h.get("cleanName") or h["name"]].sort_values("date")

        if sub.empty or sub["weekly_score"].dropna().empty:
            out[h["name"]] = [proc] * SPARK_WEEKS
            continue

        scores = sub["weekly_score"].tail(SPARK_WEEKS).tolist()
        if len(scores) < SPARK_WEEKS:
            pad = scores[0] if scores else 0.0
            scores = [pad] * (SPARK_WEEKS - len(scores)) + scores

        arr = np.asarray(scores, dtype=float)
        std = float(np.nanstd(arr))
        mean = float(np.nanmean(arr))
        if std > 1e-9:
            scaled = ((arr - mean) / std) * 15.0 + proc
        else:
            scaled = np.full_like(arr, proc)
        scaled = np.clip(scaled, 70.0, 170.0)
        out[h["name"]] = [round(float(x), 2) for x in scaled]

    return out


def build_distributions(master: pd.DataFrame) -> dict:
    # Distribution baseline uses the leaderboard-quality population (PA >= 40),
    # not the broader inclusion floor (MIN_PA), so league means stay meaningful.
    pop = master[master["pa"].fillna(0) >= LEDE_MIN_PA]

    def make(values: pd.Series, lo: float, hi: float, n_bins: int = 17) -> dict:
        v = pd.to_numeric(values, errors="coerce").dropna()
        if v.empty:
            return {"mean": 0, "bins": [0] * n_bins}
        counts, _ = np.histogram(v.values, bins=n_bins, range=(lo, hi))
        return {"mean": round(float(v.mean()), 1), "bins": [int(c) for c in counts]}

    swing_pct = pd.to_numeric(pop.get("swing_pct"), errors="coerce") * 100.0

    return {
        "proc":   make(pop.get("process_plus"),     70, 170),
        "kavoid": make(pop.get("k_avoidance_plus"), 60, 140),
        "power":  make(pop.get("power_plus"),       60, 170),
        "swing":  make(swing_pct,                   20, 60),
    }


# ─── PITCHERS ─────────────────────────────────────────────────────────────────
def build_pitchers(df: pd.DataFrame | None) -> list[dict]:
    if df is None or df.empty:
        return []
    qualified = df[df["pitches"].fillna(0) >= MIN_PITCHES].copy()
    qualified = qualified.sort_values("plv", ascending=False).reset_index(drop=True)
    out: list[dict] = []
    for i, r in qualified.iterrows():
        out.append({
            "rank":    int(i) + 1,
            "name":    _s(r.get("player_name")),
            "pitches": int(r["pitches"]) if not pd.isna(r.get("pitches")) else 0,
            "plv":     _f(r.get("plv"), 3),
            "plvStd":  _f(r.get("plv_std"), 3),
            "swing":   _f((r.get("swing_pct") or 0) * 100, 1)
                       if not pd.isna(r.get("swing_pct")) else "—",
            "whiff":   _f((r.get("whiff_pct") or 0) * 100, 1)
                       if not pd.isna(r.get("whiff_pct")) else "—",
            "cs":      _f((r.get("cs_pct") or 0) * 100, 1)
                       if not pd.isna(r.get("cs_pct")) else "—",
            "xwoba":   _f(r.get("xwoba_model"), 3),
            "contact": _f((r.get("contact_pct") or 0) * 100, 1)
                       if not pd.isna(r.get("contact_pct")) else "—",
            "pctile":  _f(r.get("plv_pctile"), 1),
        })
    return out


# ─── TARGETS ──────────────────────────────────────────────────────────────────
def _load_target_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    out: list[dict] = []
    for _, r in df.iterrows():
        out.append({
            "name":         _s(r.get("batter_name")),
            "pa":           int(r["pa"]) if not pd.isna(r.get("pa")) else 0,
            "pos":          _s(r.get("primary_position")),
            "fposDisplay":  _s(r.get("fantasy_positions_display")),
            "proc":         _f(r.get("process_plus"), 1),
            "power":        _f(r.get("power_plus"), 1),
            "kavoid":       _f(r.get("decision_plus"), 1),
            "confidence":   _s(r.get("confidence")),
            "rollingTrend": _s(r.get("rolling_trend")),
            "tag":          _s(r.get("tag"), default=""),
        })
    return out


def build_targets(year: int) -> dict:
    return {
        "buy":         _load_target_csv(OUT_DIR / f"hitter_buy_targets_{year}.csv"),
        "preBreakout": _load_target_csv(OUT_DIR / f"hitter_pre_breakout_{year}.csv"),
        "breakout":    _load_target_csv(OUT_DIR / f"hitter_breakout_flags_{year}.csv"),
    }


# ─── ROLLING (daily series for Trends tab) ────────────────────────────────────
def build_rolling(rolling: pd.DataFrame | None,
                  hitters: list[dict]) -> dict[str, list[dict]]:
    if rolling is None or rolling.empty:
        return {}

    df = rolling.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["raw"] = df["contact_value_mean"].fillna(0) + df["power_value_mean"].fillna(0)

    out: dict[str, list[dict]] = {}
    for h in hitters:
        name = h["name"]
        proc = float(h["proc"]) if isinstance(h["proc"], (int, float)) else 100.0
        # Prefer MLB ID join (disambiguates colliding names).
        mlb_id = h.get("mlbId")
        if mlb_id:
            sub = df[df["batter"] == mlb_id].sort_values("date")
        else:
            sub = df[df["batter_name"] == h.get("cleanName") or name].sort_values("date")
        if sub.empty:
            continue

        raw = sub["raw"].to_numpy(dtype=float)
        mu, sigma = float(np.nanmean(raw)), float(np.nanstd(raw))
        if sigma > 1e-9:
            scaled = ((raw - mu) / sigma) * 15.0 + proc
        else:
            scaled = np.full_like(raw, proc)
        scaled = np.clip(scaled, 70.0, 170.0)

        series = [
            {"date": d.strftime("%Y-%m-%d"), "score": round(float(s), 1)}
            for d, s in zip(sub["date"].tail(ROLLING_KEEP),
                             scaled[-ROLLING_KEEP:])
        ]
        if series:
            out[name] = series
    return out


# ─── ESPN fantasy bridge ──────────────────────────────────────────────────────
def _empty_fp() -> dict:
    return {
        "fpTotal": "—", "fpProj": "—", "fpPerGame": "—",
        "pctOwned": "—", "espnStatus": "—", "onTeam": "", "gp": 0,
        "espnFpos": "",
    }


def _clean_espn_slots(slots) -> list[str]:
    """Filter ESPN eligibleSlots to real position tokens, dedup + sort."""
    if not slots:
        return []
    keep: set[str] = set()
    for s in slots:
        if not s or s in _ESPN_NON_POS:
            continue
        # Split compound slots like "1B/3B" or "2B/SS" into both
        for part in str(s).split("/"):
            part = part.strip()
            if part and part not in _ESPN_NON_POS:
                keep.add(part)
    # Order: infield -> outfield -> DH/SP/RP, alphabetical within group
    order = {p: i for i, p in enumerate(
        ["C", "1B", "2B", "3B", "SS", "OF", "LF", "CF", "RF", "DH", "SP", "RP"])}
    return sorted(keep, key=lambda p: (order.get(p, 99), p))


def _player_fp(p, status: str, on_team: str = "") -> dict:
    """Extract fantasy-scoring fields from an espn_api Player object."""
    s0 = {}
    try:
        s0 = p.stats.get(0, {}).get("breakdown", {}) or {}
    except Exception:
        pass

    g = float(s0.get("G") or s0.get("GP") or 0) or 0.0
    fp_total = float(getattr(p, "total_points", 0) or 0)
    fp_proj  = float(getattr(p, "projected_total_points", 0) or 0)
    pct_own  = float(getattr(p, "percent_owned", 0) or 0)
    slots    = _clean_espn_slots(getattr(p, "eligibleSlots", None))
    pro_team = (getattr(p, "proTeam", "") or "").strip()

    return {
        "fpTotal":   round(fp_total, 1),
        "fpProj":    round(fp_proj, 1),
        "fpPerGame": round(fp_total / g, 2) if g > 0 else "—",
        "pctOwned":  round(pct_own, 1),
        "espnStatus": status or "—",
        "onTeam":    on_team or "",
        "gp":        int(g),
        "espnFpos":  ",".join(slots),  # e.g. "1B,DH" or "OF,RF"
        "proTeam":   pro_team,
    }


def _name_index(names: list[str], normalize_fn) -> dict[str, str]:
    """{normalized_name: original_name} for fast exact lookup."""
    return {normalize_fn(n): n for n in names if n}


def _last_token(norm_name: str) -> str:
    """Last surname token, treating hyphens as separators."""
    parts = norm_name.replace("-", " ").split()
    return parts[-1] if parts else ""


def _strict_match(espn_name: str, idx: dict[str, str], normalize_fn,
                  fuzzy_fn, cutoff: float = 0.78) -> str | None:
    """Exact-normalized lookup, with a last-name-guarded fuzzy fallback.

    The fallback only considers master names whose last surname token equals
    the ESPN last token, which prevents 'Michael Arroyo' fuzzy-matching to
    'Michael Harris' (same first name, different surname).
    """
    if not espn_name:
        return None
    nq = normalize_fn(espn_name)
    if nq in idx:
        return idx[nq]
    espn_last = _last_token(nq)
    if not espn_last:
        return None
    candidates = [orig for norm, orig in idx.items()
                  if _last_token(norm) == espn_last]
    if not candidates:
        return None
    return fuzzy_fn(espn_name, candidates, cutoff=cutoff)


def build_espn_data(master_hitter: pd.DataFrame,
                    master_pitcher: pd.DataFrame | None,
                    dup_hitter_names: set[str] | None = None) -> dict:
    """
    Single ESPN walk that produces:
      fp_by_hid:    {master batter (MLB id, int) -> fp dict}
      fp_by_pname:  {master player_name -> fp dict}        (pitchers — no known collisions)
      fa_hids:      set of master MLB ids that are ESPN free-agent hitters
      fa_pnames:    set of master player_name that are ESPN free-agent pitchers
      my_team:      {teamName, hitters[], pitchers[], error}

    Hitter lookups key on MLB id so name collisions (Max Muncy LAD vs A's,
    Gabriel Rodriguez, etc.) are disambiguated cleanly.
    """
    if dup_hitter_names is None:
        dup_hitter_names = _detect_hitter_dups(master_hitter)

    result = {
        "fp_by_hid": {}, "fp_by_pname": {},
        "fa_hids": set(), "fa_pnames": set(),
        "my_team": {"teamName": "", "hitters": [], "pitchers": [], "error": None},
    }

    try:
        from espn_connector import _get_league, _normalize, fuzzy_match_name  # type: ignore
    except Exception as e:
        result["my_team"]["error"] = f"espn_connector import failed: {e}"
        return result

    try:
        lg = _get_league()
    except Exception as e:
        result["my_team"]["error"] = f"ESPN auth failed: {e}"
        return result

    h_names = master_hitter["batter_name"].dropna().astype(str).tolist()
    p_names = (master_pitcher["player_name"].dropna().astype(str).tolist()
               if master_pitcher is not None else [])
    h_idx = _name_index(h_names, _normalize)
    p_idx = _name_index(p_names, _normalize)

    def _match_to_master(espn_name: str, is_pitcher: bool) -> str | None:
        """Strict last-name-guarded match; rejects same-first-name collisions."""
        idx = p_idx if is_pitcher else h_idx
        if not idx:
            return None
        return _strict_match(espn_name, idx, _normalize, fuzzy_match_name)

    def _resolve_hitter(clean_name: str, pro_team: str = "") -> tuple[int, pd.Series, str] | None:
        """For a clean batter_name, pick the best master row (MLB id, master row,
        disambiguated display name).  Resolves Max Muncy → LAD-vet by
        pa × proc_plus heuristic when the name collides."""
        sub = master_hitter[master_hitter["batter_name"] == clean_name]
        if sub.empty:
            return None
        if len(sub) == 1:
            r = sub.iloc[0]
        else:
            tmp = sub.copy()
            tmp["_score"] = tmp["pa"].fillna(0) * tmp["process_plus"].fillna(0)
            r = tmp.sort_values("_score", ascending=False).iloc[0]
        mlb_id = int(r["batter"]) if not pd.isna(r.get("batter")) else 0
        disambig = _row_name(clean_name, mlb_id, dup_hitter_names, pro_team)
        return mlb_id, r, disambig

    pitcher_pos = {"SP", "RP", "P"}

    # ── 1. Walk all rosters: build fp_map + my_team ──
    for team in lg.teams:
        tname = (getattr(team, "team_name", "") or "").strip()
        owner = (getattr(team, "owner", "") or "").lower()
        is_my = ("ligers"    in tname.lower()
                 or "libraries" in tname.lower()
                 or "josh"   in owner)
        for p in team.roster:
            espn_name = (getattr(p, "name", "") or "").strip()
            espn_pos  = (getattr(p, "position", "") or "").strip()
            pro_team  = (getattr(p, "proTeam", "") or "").strip()
            if not espn_name:
                continue

            is_pitcher = espn_pos in pitcher_pos
            matched_clean = _match_to_master(espn_name, is_pitcher)
            fp = _player_fp(p, "ROSTER", tname)

            if is_pitcher:
                if matched_clean:
                    result["fp_by_pname"][matched_clean] = fp
                if is_my:
                    mrow = (master_pitcher[master_pitcher["player_name"] == matched_clean].iloc[0]
                            if matched_clean is not None else None)
                    row = _pitcher_row(matched_clean or espn_name, espn_pos, pro_team, mrow)
                    row.update(fp)
                    result["my_team"]["pitchers"].append(row)
                    if not result["my_team"]["teamName"]:
                        result["my_team"]["teamName"] = tname
            else:
                resolved = _resolve_hitter(matched_clean, pro_team) if matched_clean else None
                if resolved:
                    mlb_id, mrow, disambig = resolved
                    result["fp_by_hid"][mlb_id] = fp
                else:
                    mlb_id, mrow, disambig = 0, None, espn_name
                if is_my:
                    row = _hitter_row(disambig, espn_pos, pro_team, mrow)
                    row.update(fp)
                    if fp.get("espnFpos"):
                        row["fpos"] = fp["espnFpos"]
                    result["my_team"]["hitters"].append(row)
                    if not result["my_team"]["teamName"]:
                        result["my_team"]["teamName"] = tname

    # ── 2. Free agents ──
    try:
        fas = lg.free_agents(size=ESPN_FA_SIZE)
    except Exception as e:
        print(f"  espn free_agents failed: {e}", file=sys.stderr)
        fas = []

    for p in fas:
        espn_name = (getattr(p, "name", "") or "").strip()
        espn_pos  = (getattr(p, "position", "") or "").strip()
        if not espn_name:
            continue
        is_pitcher = espn_pos in pitcher_pos
        matched_clean = _match_to_master(espn_name, is_pitcher)
        if not matched_clean:
            continue

        st = (getattr(p, "status", "") or "FREEAGENT")
        fp = _player_fp(p, st, "")

        if is_pitcher:
            if result["fp_by_pname"].get(matched_clean, {}).get("espnStatus") == "ROSTER":
                continue
            result["fp_by_pname"].setdefault(matched_clean, fp)
            result["fa_pnames"].add(matched_clean)
        else:
            fa_pro_team = (getattr(p, "proTeam", "") or "").strip()
            resolved = _resolve_hitter(matched_clean, fa_pro_team)
            if not resolved:
                continue
            mlb_id, _mrow, _disambig = resolved
            if result["fp_by_hid"].get(mlb_id, {}).get("espnStatus") == "ROSTER":
                continue
            result["fp_by_hid"].setdefault(mlb_id, fp)
            result["fa_hids"].add(mlb_id)

    return result


def attach_fantasy_by_id(rows: list[dict], fp_by_id: dict[int, dict]) -> None:
    """Attach fp fields to each hitter row by MLB id (disambiguates collisions).
    When ESPN reports richer multi-position eligibility (e.g. RF,OF,DH for Judge),
    promote it onto the `fpos` field."""
    for r in rows:
        fp = fp_by_id.get(r.get("mlbId"))
        if not fp:
            r.update(_empty_fp())
            continue
        r.update(fp)
        espn_fpos = fp.get("espnFpos") or ""
        if espn_fpos:
            r["fpos"] = espn_fpos


def attach_fantasy_by_name(rows: list[dict], fp_by_name: dict[str, dict]) -> None:
    """Pitcher-side variant — keys on `name` (no known collisions)."""
    for r in rows:
        fp = fp_by_name.get(r.get("name"))
        if not fp:
            r.update(_empty_fp())
            continue
        r.update(fp)
        espn_fpos = fp.get("espnFpos") or ""
        if espn_fpos:
            r["fpos"] = espn_fpos


def build_waiver_from_espn(master_hitter: pd.DataFrame,
                           fp_by_hid: dict[int, dict],
                           fa_hids: set[int],
                           dup_names: set[str],
                           mlb_to_team: dict[int, str],
                           fallback_hitters: list[dict]) -> list[dict]:
    """All ESPN free-agent hitters joined with master by MLB id, sorted by Proc+."""
    if not fa_hids:
        out = [h for h in fallback_hitters
               if h.get("signal") in ("Watch", "Too Small")
               or h.get("sample") in ("Too Small", "Small")]
        for h in out:
            h.setdefault("fpTotal", "—")
        return out

    rows: list[dict] = []
    for mlb_id in fa_hids:
        sub = master_hitter[master_hitter["batter"] == mlb_id]
        if sub.empty:
            continue
        r = sub.iloc[0]
        if (r.get("pa") or 0) < WAIVER_MIN_PA:
            continue
        clean = _s(r.get("batter_name"))
        team = mlb_to_team.get(mlb_id, "")
        disambig = _row_name(clean, mlb_id, dup_names, team)
        row = _hitter_row(disambig, _s(r.get("primary_position")), "", r)
        row["rank"] = 0
        fp = fp_by_hid.get(mlb_id, _empty_fp())
        row.update(fp)
        if fp.get("espnFpos"):
            row["fpos"] = fp["espnFpos"]
        rows.append(row)

    def _proc_key(r):
        v = r.get("proc")
        return v if isinstance(v, (int, float)) else -1.0

    rows.sort(key=_proc_key, reverse=True)
    return rows[:WAIVER_TOP_N]


# ─── MY TEAM (ESPN roster) ────────────────────────────────────────────────────
def _hitter_row(name: str, espn_pos: str, pro_team: str,
                master_row: pd.Series | None) -> dict:
    """Same shape as build_hitters output, with rank=0 + ESPN extras.

    `name` is expected to be the disambiguated display name (e.g. with `(#1970)`
    suffix when multiple master rows share the clean name). `cleanName` is the
    base name without suffix; `mlbId` is the MLB batter id from master.
    """
    if master_row is None:
        return {
            "rank": 0, "name": name, "cleanName": name, "mlbId": 0,
            "espnPos": espn_pos, "proTeam": pro_team,
            "pa": 0, "pos": espn_pos, "fpos": espn_pos,
            "proc": "—", "procPos": "—", "kavoid": "—", "power": "—",
            "swing": "—", "chase": "—", "mc": "—", "mci": "—",
            "blast": "—", "ev": "—",
            "signal": "—", "flag": "—", "sample": "Unmatched",
        }
    r = master_row
    return {
        "rank": 0, "name": name,
        "cleanName": _s(r.get("batter_name")),
        "mlbId":    int(r["batter"]) if not pd.isna(r.get("batter")) else 0,
        "espnPos": espn_pos, "proTeam": pro_team,
        "pa": int(r["pa"]) if not pd.isna(r.get("pa")) else 0,
        "pos": _s(r.get("primary_position")),
        "fpos": _s(r.get("fantasy_positions_display")),
        "proc": _f(r.get("process_plus"), 1),
        "procPos": _f(r.get("proc_plus_positional"), 1),
        "kavoid": _f(r.get("k_avoidance_plus"), 1),
        "power": _f(r.get("power_plus"), 1),
        "swing": _f((r.get("swing_pct") or 0) * 100, 1)
                 if not pd.isna(r.get("swing_pct")) else "—",
        "chase": _f((r.get("chase_pct") or 0) * 100, 1)
                 if not pd.isna(r.get("chase_pct")) else "—",
        "mc": _f(r.get("xwoba_on_contact"), 3),
        "mci": _f(r.get("xwoba_vs_expected"), 3),
        "blast": _f((r.get("blast_rate") or 0) * 100, 1)
                 if not pd.isna(r.get("blast_rate")) else "—",
        "ev": _f(r.get("avg_swing_speed"), 1),
        "signal": _s(r.get("signal")),
        "flag": _s(r.get("risk_flag")),
        "sample": _s(r.get("sample_tier")),
    }


def _pitcher_row(name: str, espn_pos: str, pro_team: str,
                 master_row: pd.Series | None) -> dict:
    """Same shape as build_pitchers output, rank=0 + ESPN extras."""
    if master_row is None:
        return {
            "rank": 0, "name": name, "espnPos": espn_pos, "proTeam": pro_team,
            "pitches": 0, "plv": "—", "plvStd": "—", "swing": "—",
            "whiff": "—", "cs": "—", "xwoba": "—", "contact": "—", "pctile": "—",
        }
    r = master_row
    return {
        "rank": 0, "name": name, "espnPos": espn_pos, "proTeam": pro_team,
        "pitches": int(r["pitches"]) if not pd.isna(r.get("pitches")) else 0,
        "plv": _f(r.get("plv"), 3),
        "plvStd": _f(r.get("plv_std"), 3),
        "swing": _f((r.get("swing_pct") or 0) * 100, 1)
                 if not pd.isna(r.get("swing_pct")) else "—",
        "whiff": _f((r.get("whiff_pct") or 0) * 100, 1)
                 if not pd.isna(r.get("whiff_pct")) else "—",
        "cs": _f((r.get("cs_pct") or 0) * 100, 1)
              if not pd.isna(r.get("cs_pct")) else "—",
        "xwoba": _f(r.get("xwoba_model"), 3),
        "contact": _f((r.get("contact_pct") or 0) * 100, 1)
                   if not pd.isna(r.get("contact_pct")) else "—",
        "pctile": _f(r.get("plv_pctile"), 1),
    }


# ─── META ─────────────────────────────────────────────────────────────────────
def build_meta(year: int) -> str:
    today = date.today()
    issue = today.timetuple().tm_yday // 7 + 1
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip().upper()
    except Exception:
        sha = "LOCAL"
    return f"Vol. II · No. {issue} · {year} Season · Build {sha}"


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    args = ap.parse_args()
    year = args.year

    master_path  = OUT_DIR / f"master_hitter_{year}.csv"
    rolling_path = OUT_DIR / f"process_plus_rolling_{year}.csv"
    pitcher_path = OUT_DIR / f"master_pitcher_{year}.csv"

    if not master_path.exists():
        print(f"ERROR: missing {master_path}", file=sys.stderr)
        return 1
    if not TEMPLATE.exists():
        print(f"ERROR: missing template {TEMPLATE}", file=sys.stderr)
        return 1

    master   = pd.read_csv(master_path)
    rolling  = pd.read_csv(rolling_path) if rolling_path.exists() else None
    pitchers = pd.read_csv(pitcher_path) if pitcher_path.exists() else None

    dup_names     = _detect_hitter_dups(master)
    distributions = build_distributions(master)
    pitchers_out  = build_pitchers(pitchers)
    targets       = build_targets(year)

    # ── ESPN: rosters + free agents + fantasy points (one network walk) ──
    espn = build_espn_data(master, pitchers, dup_hitter_names=dup_names)
    fp_by_h_id, fp_by_p_name = espn["fp_by_hid"], espn["fp_by_pname"]
    my_team = espn["my_team"]

    # Map MLB id -> ESPN proTeam for friendlier disambiguation labels.
    mlb_to_team = {mid: fp.get("proTeam", "")
                   for mid, fp in fp_by_h_id.items() if fp.get("proTeam")}

    # Build leaderboard hitters now that we know team labels for collisions.
    hitters = build_hitters(master, dup_names=dup_names, mlb_to_team=mlb_to_team)

    # Attach actual ESPN fantasy points (hitters by MLB id, pitchers by name)
    attach_fantasy_by_id(hitters,      fp_by_h_id)
    attach_fantasy_by_name(pitchers_out, fp_by_p_name)

    # Build ESPN-driven waiver wire (free agents only)
    waiver = build_waiver_from_espn(master, fp_by_h_id, espn["fa_hids"],
                                    dup_names, mlb_to_team, hitters)

    # Sparks + rolling cover top-50 + my-team + waiver hitters
    sparkable = hitters + my_team["hitters"] + waiver
    sparks       = build_sparks(sparkable, rolling)
    rolling_out  = build_rolling(rolling, sparkable)

    meta = build_meta(year)

    print(f"  hitters:     {len(hitters)}  (FP attached: {sum(1 for h in hitters if isinstance(h.get('fpTotal'), (int,float)))})")
    print(f"  sparks:      {len(sparks)}")
    print(f"  pitchers:    {len(pitchers_out)} (pitches >= {MIN_PITCHES})")
    print(f"  targets:     buy={len(targets['buy'])}, "
          f"preBreakout={len(targets['preBreakout'])}, "
          f"breakout={len(targets['breakout'])}")
    print(f"  rolling:     {len(rolling_out)} players (last {ROLLING_KEEP} days)")
    print(f"  waiver:      {len(waiver)} (ESPN free agents, pa>={WAIVER_MIN_PA})")
    print(f"  my_team:     {my_team['teamName'] or '(unavailable)'} - "
          f"{len(my_team['hitters'])} hitters, {len(my_team['pitchers'])} pitchers"
          + (f"  ({my_team['error']})" if my_team['error'] else ''))
    print(f"  dist mean:   proc={distributions['proc']['mean']}, "
          f"power={distributions['power']['mean']}")

    html = TEMPLATE.read_text(encoding="utf-8")

    blocks = [
        ("REPORT_META",   json.dumps(meta)),
        ("HITTERS",       json.dumps(hitters,       indent=2)),
        ("SPARKS",        json.dumps(sparks,        indent=2)),
        ("DISTRIBUTIONS", json.dumps(distributions, indent=2)),
        ("PITCHERS",      json.dumps(pitchers_out,  indent=2)),
        ("TARGETS",       json.dumps(targets,       indent=2)),
        ("ROLLING",       json.dumps(rolling_out,   indent=2)),
        ("WAIVER",        json.dumps(waiver,        indent=2)),
        ("MY_TEAM",       json.dumps(my_team,       indent=2)),
    ]
    body = "\n".join(f"window.{k} = {v};" for k, v in blocks)
    data_script = f"<script>\n{body}\n</script>"

    new_html, n = re.subn(
        r"<!-- DATA INJECTION POINT.*?</script>",
        lambda _m: data_script,
        html,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        print("ERROR: could not find data injection block in template", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"process_report_{year}.html"
    out_path.write_text(new_html, encoding="utf-8")
    print(f"Written: {out_path}  ({len(new_html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
