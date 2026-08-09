"""expected_stats — expected-vs-actual (luck) lens.

The depth audit (2026-06-21) found xwOBA/xwOBACON are computed internally and
drive rh3/sustainability, but are never DISPLAYED as an expected-vs-actual
percentile panel — the canonical "is this real or luck" view. Only the external
/savant-compare WebFetch showed it. This is the one internal home.

xwOBA is built the standard way: estimated_woba_using_speedangle on balls in
play, the actual woba_value on non-BIP outcomes (BB/HBP/K), over woba_denom.
The gap (actual wOBA − xwOBA) sizes regression. CONTEXT-ONLY (feedback #13): it
informs conviction / regression direction, it never moves rh3/rp3.

THE PERSONAL BASELINE (added 2026-08-09)
----------------------------------------
The +/-0.020 threshold is calibrated to the FIELD, whose gap centers on zero
and mean-reverts. Some hitters' personal mean is not zero — Jose Altuve beat
his xwOBA in 10 of 11 full seasons at a PA-weighted +0.030 — because xwOBA is
built from exit velocity and launch angle alone and is structurally blind to
where a ball is hit and who is running. Judging such a hitter against zero
manufactures a regression warning out of his normal operating level, which is
exactly what happened to Altuve on 2026-08-09.

Validated on the `hitter_luck_seasons` cache (leave-one-season-out: predict a
season's gap from ALL prior seasons; n=1583 player-seasons, >=3 prior seasons
and >=1000 prior PA):

    r = 0.334  [0.288, 0.379]      slope = 0.527  [0.452, 0.604]

so the trait is real and repeatable, but it also REGRESSES — which is why the
baseline is SHRUNK by that slope rather than applied at face value. The
shrinkage is load-bearing, not decoration:

    MAE vs field zero      0.0164
    MAE vs full personal   0.0164     <- no better than ignoring it entirely
    MAE vs shrunk baseline 0.0154     <- the only one that helps

Passing a hitter's own baseline is therefore OPT-IN and defaults to the old
field-relative behaviour, so callers without history are unaffected.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from plv_clone.paths import ROOT

CACHE = ROOT / "data" / "research" / "xfp_cache"
#: Season these lenses read. Named once so the personal-baseline callers and
#: the statcast default cannot drift apart.
CURRENT_SEASON = 2026
LUCK_SEASONS = CACHE / "hitter_luck_seasons.csv"

#: Empirical shrink applied to a hitter's prior-seasons gap before it is used
#: as his reference. This IS the fitted leave-one-season-out slope (0.527,
#: 95% CI [0.452, 0.604]) — the best linear predictor of the current gap from
#: prior ones. Applying the raw career gap instead scores no better than using
#: zero; see the module docstring.
LUCK_SHRINK = 0.53
#: Sample gates for trusting a personal baseline at all — the gates the
#: validation above was run under. Below these, fall back to the field zero.
LUCK_MIN_SEASONS = 3
LUCK_MIN_PA = 1000
#: A shrunk baseline at least this far from zero earns a persistence LABEL.
#: Anchored at half of luck_threshold: below it the personal baseline cannot
#: move a reading by even half a tier, so naming a "profile" would be noise.
PERSISTENT_BAND = 0.010
#: UNIT HARMONISATION. The baseline is built from Savant's published expected
#: line; the current-season gap is computed locally by `_xwoba_woba`. The two
#: xwOBA implementations track each other closely but are OFFSET: measured on
#: 2026 (n=290 hitters, 200+ PA) the local gap runs
#:     mean +0.0069 hotter, sd 0.0051, correlation 0.973
#: Subtracting a Savant-units baseline from a local-units gap without this
#: correction biases every excess upward by ~0.007 — enough to change a tier.
#: Canonical: Altuve's local gap +0.039 against a +0.016 baseline gives excess
#: +0.023 (OVERPERFORMING); harmonised it is +0.016 (ALIGNED), and the
#: harmonised figure is the one that matches his Savant season gap of +0.030.
#: RE-DERIVE THIS if `_xwoba_woba` changes or Savant revises its model.
LUCK_SOURCE_OFFSET = 0.0069


def personal_luck_baseline(seasons, *, shrink: float = LUCK_SHRINK,
                           min_seasons: int = LUCK_MIN_SEASONS,
                           min_pa: int = LUCK_MIN_PA) -> dict | None:
    """Pure: a hitter's own expected-vs-actual reference from PRIOR seasons.

    ``seasons`` is an iterable of (pa, gap) for seasons BEFORE the one being
    judged — never including it, or the baseline would partly explain itself.
    Returns None when the sample gates are not met, which callers must read as
    "use the field zero", not as "no tendency".

    ``baseline`` is the shrunk value and is the one to compare against;
    ``career_gap`` is the raw PA-weighted mean and is for display only.
    """
    rows = [(float(pa), float(gap)) for pa, gap in seasons
            if pa is not None and gap is not None
            and not (np.isnan(pa) or np.isnan(gap)) and pa > 0]
    total_pa = sum(pa for pa, _ in rows)
    if len(rows) < min_seasons or total_pa < min_pa:
        return None
    career = sum(pa * gap for pa, gap in rows) / total_pa
    gaps = np.array([g for _, g in rows])
    baseline = shrink * career
    if baseline >= PERSISTENT_BAND:
        profile = "PERSISTENT-BEATER"
    elif baseline <= -PERSISTENT_BAND:
        profile = "PERSISTENT-UNDER"
    else:
        profile = "FIELD-NORMAL"
    return {"baseline": baseline, "career_gap": career, "shrink": shrink,
            "n_seasons": len(rows), "pa": int(total_pa),
            "seasons_beat": int((gaps > 0).sum()),
            "sd": float(gaps.std(ddof=1)) if len(gaps) > 1 else None,
            "profile": profile}


def hitter_luck_baseline(batter_id: int, year: int,
                         seasons_df: pd.DataFrame | None = None, **kw) -> dict | None:
    """``personal_luck_baseline`` for one hitter, read off the season cache.

    Only seasons strictly BEFORE ``year`` are used. Returns None if the cache
    is missing (it is built by scripts/xfp/build_hitter_luck_baseline.py) so a
    caller degrades to field-relative rather than failing.
    """
    if seasons_df is None:
        if not LUCK_SEASONS.exists():
            return None
        seasons_df = pd.read_csv(LUCK_SEASONS)
    d = seasons_df[(seasons_df["batter"] == batter_id) & (seasons_df["year"] < year)]
    if d.empty:
        return None
    return personal_luck_baseline(zip(d["pa"], d["gap"]), **kw)


def expected_vs_actual(xwoba, woba, *, pctl=None, luck_threshold: float = 0.020,
                       own_baseline: float | None = None) -> dict:
    """Pure: compare expected (xwoba) to actual (woba).

    gap = woba − xwoba (positive = overperforming / due for negative regression;
    negative = underperforming / bounce due). Returns regression tier + optional
    xwoba percentile. None-safe.

    ``own_baseline`` is the hitter's SHRUNK personal reference from
    ``personal_luck_baseline``. When given, the tier is judged on the EXCESS
    over that reference rather than over zero — a persistent xwOBA-beater
    sitting at his usual gap is ALIGNED, not overperforming. When omitted the
    reference is zero and the behaviour is exactly as before.
    """
    if xwoba is None or woba is None:
        return {"xwoba": xwoba, "woba": woba, "gap": None, "own_baseline": own_baseline,
                "excess": None, "regression": "UNKNOWN", "xwoba_pctl": pctl}
    gap = woba - xwoba
    ref = 0.0 if own_baseline is None else float(own_baseline)
    excess = gap - ref
    if excess > luck_threshold:
        reg = "OVERPERFORMING"
    elif excess < -luck_threshold:
        reg = "UNDERPERFORMING"
    else:
        reg = "ALIGNED"
    return {"xwoba": xwoba, "woba": woba, "gap": gap, "own_baseline": own_baseline,
            "excess": excess, "regression": reg, "xwoba_pctl": pctl}


def _xwoba_woba(df: pd.DataFrame) -> tuple:
    """(xwoba, woba, denom) over a set of PA rows. xwOBA = estimated on BIP +
    actual woba_value on non-BIP, all over woba_denom."""
    pa = df[df["events"].notna() & (df["events"] != "")]
    denom = pa["woba_denom"].fillna(0).sum()
    if denom <= 0:
        return None, None, 0
    bip = pa["estimated_woba_using_speedangle"].notna()
    x_num = (pa.loc[bip, "estimated_woba_using_speedangle"].sum()
             + pa.loc[~bip, "woba_value"].fillna(0).sum())
    woba = pa["woba_value"].fillna(0).sum() / denom
    return x_num / denom, woba, int(denom)


_COLS = ["batter", "pitcher", "events", "woba_value", "woba_denom",
         "estimated_woba_using_speedangle"]
# extra handedness cols for the by-split variants
_COLS_SPLIT = _COLS + ["stand", "p_throws"]


def _expected_by_split(df: pd.DataFrame, split_col: str, floor: int,
                       pitcher: bool = False) -> dict:
    """expected-vs-actual per handedness side. ``split_col`` = 'p_throws' for a
    hitter's vs-LHP/RHP, 'stand' for a pitcher's vs-LHB/RHB."""
    out = {}
    for side, key in (("L", "vs_L"), ("R", "vs_R")):
        s = df[df[split_col] == side]
        xw, wo, denom = _xwoba_woba(s)
        if xw is None or denom < floor:
            out[key] = None
            continue
        r = expected_vs_actual(float(round(xw, 3)), float(round(wo, 3)))
        if pitcher and r["gap"] is not None:  # flip: allowing LESS than expected = lucky
            r["regression"] = ("OVERPERFORMING" if r["gap"] < -0.020
                               else "UNDERPERFORMING" if r["gap"] > 0.020 else "ALIGNED")
        r["pa"] = denom
        out[key] = r
    return out


def _population_pctl(values: pd.Series, v: float) -> int | None:
    if v is None or values.empty:
        return None
    return int(round((values < v).mean() * 100))


def hitter_expected(batter_id: int, statcast_df: pd.DataFrame | None = None,
                    pa_floor: int = 50, *, year: int | None = None,
                    seasons_df: pd.DataFrame | None = None) -> dict | None:
    """Expected-vs-actual wOBA for one hitter.

    Pass ``year`` to judge him against his OWN prior-seasons baseline instead
    of the field zero (see the module docstring). Without it, or when he has
    too little history, the reading stays field-relative.
    """
    if statcast_df is None:
        p = CACHE / f"statcast_{CURRENT_SEASON}.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS)
    d = statcast_df[statcast_df["batter"] == batter_id]
    xw, wo, denom = _xwoba_woba(d)
    if xw is None or denom < pa_floor:
        return None
    b = hitter_luck_baseline(batter_id, year, seasons_df) if year is not None else None
    # The gap about to be measured is in LOCAL units; b["baseline"] is in Savant
    # units. Shift the reference into local units before differencing them.
    ref = (b["baseline"] + LUCK_SOURCE_OFFSET) if b else None
    r = expected_vs_actual(float(round(xw, 3)), float(round(wo, 3)), own_baseline=ref)
    r["luck_profile"] = b["profile"] if b else None
    r["baseline_savant"] = b["baseline"] if b else None
    r["source_offset"] = LUCK_SOURCE_OFFSET if b else None
    return r


def sp_expected(pitcher_id: int, statcast_df: pd.DataFrame | None = None,
                bf_floor: int = 80) -> dict | None:
    """Expected-vs-actual wOBA-ALLOWED for a pitcher (lower xwoba = better)."""
    if statcast_df is None:
        p = CACHE / f"statcast_{CURRENT_SEASON}.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS)
    d = statcast_df[statcast_df["pitcher"] == pitcher_id]
    xw, wo, denom = _xwoba_woba(d)
    if xw is None or denom < bf_floor:
        return None
    # For pitchers, OVERPERFORMING = allowing LESS than expected (lucky) — flip sign
    r = expected_vs_actual(float(round(xw, 3)), float(round(wo, 3)))
    if r["gap"] is not None:
        r["regression"] = ("OVERPERFORMING" if r["gap"] < -0.020
                           else "UNDERPERFORMING" if r["gap"] > 0.020 else "ALIGNED")
    return r


def hitter_expected_by_split(batter_id: int, statcast_df: pd.DataFrame | None = None,
                             pa_floor: int = 40) -> dict | None:
    """Hitter expected-vs-actual wOBA split vs LHP / RHP (by pitcher hand)."""
    if statcast_df is None:
        p = CACHE / f"statcast_{CURRENT_SEASON}.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS_SPLIT)
    d = statcast_df[statcast_df["batter"] == batter_id]
    if d.empty:
        return None
    return _expected_by_split(d, "p_throws", pa_floor, pitcher=False)


def sp_expected_by_split(pitcher_id: int, statcast_df: pd.DataFrame | None = None,
                         bf_floor: int = 40) -> dict | None:
    """Pitcher expected-vs-actual wOBA-allowed split vs LHB / RHB (by batter stand)."""
    if statcast_df is None:
        p = CACHE / f"statcast_{CURRENT_SEASON}.parquet"
        if not p.exists():
            return None
        statcast_df = pd.read_parquet(p, columns=_COLS_SPLIT)
    d = statcast_df[statcast_df["pitcher"] == pitcher_id]
    if d.empty:
        return None
    return _expected_by_split(d, "stand", bf_floor, pitcher=True)
