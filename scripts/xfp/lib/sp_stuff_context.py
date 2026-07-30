"""sp_stuff_context — Statcast three-axis context (stuff / command / contact)
for SP the in-season model can't score (``talent_prior`` rows).

DISPLAY / CONTEXT ONLY (Rule 13). Tested out-of-sample, none of these three
adds forward-FP signal beyond rp3 — rp3 already owns stuff + command — so they
never move a headline number. They earn their place only as *diagnosis* and for
arms whose ``per_start`` is a suppressed Marcel prior (``talent_prior``), where
recent Statcast is the only real read.

Three orthogonal axes:
  - StuffFP (stuff)   = validated composite of CSW/SwStr/Whiff, fit on
                        2021-2026 to forward FP/start, in FP units.
  - K-BB%   (command) = (K - BB) / batters faced; best standalone forward
                        predictor, fast-stabilizing.
  - xwOBAcon(contact) = expected wOBA on balls in play (lower = better); the one
                        axis independent of stuff & command.

Weights are the firmed pooled 2021-2026 fit (raw percentage-point inputs):
    StuffFP = -6.12 + 0.483*CSW + 1.095*SwStr - 0.368*Whiff
StuffFP and K-BB% stabilize in ~3-4 starts; xwOBAcon needs many balls in play,
so treat the contact number as directional under THIN_STARTS.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .bucket_dispatch import _flip_lastfirst as _flip  # shared 'Last, First' flip (audit item 9)

ROOT = Path(__file__).resolve().parents[3]
STATCAST = ROOT / "data" / "research" / "xfp_cache" / "statcast_2026.parquet"

# firmed multi-year (2021-2026) forward-FP composite weights; raw % inputs.
_B0, _W_CSW, _W_SWSTR, _W_WHIFF = -6.12, 0.483, 1.095, -0.368

_WH = {"swinging_strike", "swinging_strike_blocked"}
_CS = {"called_strike", "automatic_strike"}
_SWG = _WH | {"foul", "foul_tip", "bunt_foul_tip", "hit_into_play",
              "foul_bunt", "missed_bunt"}
_K = {"strikeout", "strikeout_double_play"}
_BB = {"walk", "intent_walk"}

MIN_START_PITCHES = 25   # an outing this size counts as a start-like sample
THIN_STARTS = 4          # below this, xwOBAcon is unstable (flag it)


def stufffp(csw, swstr, whiff):
    """Firmed StuffFP composite from raw percentage-point rates (or None)."""
    if csw is None or swstr is None or whiff is None:
        return None
    return round(_B0 + _W_CSW * csw + _W_SWSTR * swstr + _W_WHIFF * whiff, 1)


# Name join key — OWNER: plv_clone.utils.name_match.safe_name_key. Order-
# PRESERVING, space-separated ("kyle schwarber"), collapses curly-vs-straight
# apostrophes, C.J./CJ and hyphens. NEVER re-derive locally: a local copy
# mis-keyed Ryan O'Hearn's U+2019 apostrophe and printed an opponent's player
# as a FREE AGENT (2026-07-28). NOT join_key — that one sorts tokens and drops
# separators, which is a different (order-independent) key.
from plv_clone.utils.name_match import safe_name_key as _norm  # noqa: E402


@lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    return pd.read_parquet(STATCAST, columns=[
        "game_date", "pitcher", "player_name", "description", "events",
        "estimated_woba_using_speedangle"])


def _agg(d: pd.DataFrame) -> dict | None:
    """Pooled three-axis read over a set of start outings."""
    p = int(d["pit"].sum())
    if p == 0:
        return None
    csw = round(100 * (d["wh"].sum() + d["cs"].sum()) / p, 1)
    swstr = round(100 * d["wh"].sum() / p, 1)
    whiff = round(100 * d["wh"].sum() / d["sw"].sum(), 1) if d["sw"].sum() else None
    pa = int(d["pa"].sum())
    kbb = round(100 * (d["k"].sum() - d["bb"].sum()) / pa, 1) if pa else None
    xwc = round(d.loc[d["xwc"].notna(), "xwc"].mean(), 3) if d["xwc"].notna().any() else None
    return {"stufffp": stufffp(csw, swstr, whiff), "kbb": kbb, "xwc": xwc}


@lru_cache(maxsize=1)
def _by_pitcher() -> dict:
    """mlbam -> {starts, low_conf, 's': season read, 'l3': last-3 read}."""
    df = _load().copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["wh"] = df["description"].isin(_WH)
    df["cs"] = df["description"].isin(_CS)
    df["sw"] = df["description"].isin(_SWG)
    df["k"] = df["events"].isin(_K)
    df["bb"] = df["events"].isin(_BB)
    df["pa"] = df["events"].notna()
    df["xwc"] = df["estimated_woba_using_speedangle"].where(
        df["description"].eq("hit_into_play"))
    g = (df.groupby(["pitcher", "game_date"])
           .agg(pit=("description", "size"), wh=("wh", "sum"), cs=("cs", "sum"),
                sw=("sw", "sum"), k=("k", "sum"), bb=("bb", "sum"),
                pa=("pa", "sum"), xwc=("xwc", "mean"))
           .reset_index())
    g = g[g["pit"] >= MIN_START_PITCHES].sort_values(["pitcher", "game_date"])
    out = {}
    for pid, d in g.groupby("pitcher"):
        out[int(pid)] = {"starts": len(d), "low_conf": len(d) < THIN_STARTS,
                         "s": _agg(d), "l3": _agg(d.tail(3))}
    return out


@lru_cache(maxsize=1)
def _name_map() -> dict:
    """Normalized 'First Last' -> set of mlbam. Collision-safe for pitchers
    (only pitchers appear in a pitching Statcast parquet); a shared full name
    yields a >1 set and is treated as unresolvable rather than guessed."""
    df = _load()
    m: dict[str, set] = {}
    for pid, nm in (df.dropna(subset=["player_name"])
                      .groupby("pitcher")["player_name"].first().items()):
        m.setdefault(_norm(_flip(nm)), set()).add(int(pid))
    return m


def context_for(name: str, team: str | None = None) -> dict | None:
    """Three-axis context for a pitcher by name, or None if unresolved / no
    2026 Statcast. Resolves via the collision-safe full-name map; an ambiguous
    (shared full name) match returns None rather than a wrong join."""
    ids = _name_map().get(_norm(name))
    if not ids or len(ids) != 1:
        return None
    return _by_pitcher().get(next(iter(ids)))
