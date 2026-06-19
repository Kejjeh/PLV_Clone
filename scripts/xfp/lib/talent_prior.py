"""Talent-prior fallback for players the in-season models can't score.

The xFP models are in-season-form-driven, so a player who's missed most of 2026
(Greene, Snell, Judge, Elly, Robert...) either vanishes from rh3 or carries a
flagged rp3 marcel value. This lib gives an honest, on-scale "if-healthy" talent
estimate so those elites can still be RANKED (clearly tagged LOW-CONF):

  HITTER: Marcel-weighted (2025/24/23 = 5/4/3) fp_per_pa from the multiyr cache,
          PA-weighted + regressed to league mean, then linearly CALIBRATED to the
          validated rh3 per_game scale (fit on the ~299 hitters in both).
  SP:     handled in-board by using rp3's marcel xfp_rp3_per_start (already on
          the rp3 scale) once the "Last, First" name format is flipped.

PRODUCTION NOTE (moved 2026-06-11 from scripts/_oneoff/talent_prior.py into
scripts/xfp/lib/ for the build_xfp_boards engine). ROOT now resolves via
parents[3] because this file sits 3 levels under the repo root
(scripts/xfp/lib/). The original one-off copy is left in place.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd, numpy as np
from plv_clone.projections import PROJECTIONS

# scripts/xfp/lib/talent_prior.py -> parents[3] == repo root (plv_clone)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

_MU = None
_CALIB = None          # (intercept a, slope b) for rh3_pg = a + b*raw_pg
_LGF = None
W = {2025: 5, 2024: 4, 2023: 3}
PA_PER_G = 4.1
REG_PA = 200


def flip_name(s):
    """'Snell, Blake' -> 'Blake Snell'; pass through 'First Last'."""
    s = str(s)
    if "," in s:
        p = [x.strip() for x in s.split(",", 1)]
        if len(p) == 2 and p[0] and p[1]:
            return f"{p[1]} {p[0]}"
    return s


MIN_TOT_PA = 250   # need a real multi-year track record, else the prior is noise
MIN_MAX_PA = 200   # ...including at least one near-full season


def _raw_pg(bid):
    s = _MU[(_MU["batter"] == bid) & (_MU["year"].isin(W))]
    if not len(s):
        return None
    if s["pa"].sum() < MIN_TOT_PA or s["pa"].max() < MIN_MAX_PA:
        return None    # fringe / small-sample — not a trustworthy talent prior
    num, den = REG_PA * _LGF, REG_PA
    for _, r in s.iterrows():
        w = W[int(r["year"])] * max(r["pa"], 0)
        num += w * r["fp_per_pa_actual"]; den += w
    return num / den * PA_PER_G


def _load():
    global _MU, _CALIB, _LGF
    if _CALIB is not None:
        return
    _MU = pd.read_csv(ROOT / "data/research/xfp_cache/hitters_multiyr_2015_2026.csv")
    lg = _MU[_MU["year"].between(2023, 2025)]
    _LGF = float(np.average(lg["fp_per_pa_actual"], weights=lg["pa"].clip(lower=1)))
    rh3 = PROJECTIONS.rh3()
    xs, ys = [], []
    for _, r in rh3.iterrows():
        rp = _raw_pg(r["batter"])
        if rp is not None and pd.notna(r["xfp_rh3_per_game"]):
            xs.append(rp); ys.append(r["xfp_rh3_per_game"])
    b, a = np.polyfit(np.array(xs), np.array(ys), 1)
    _CALIB = (float(a), float(b))


def hitter_prior_pg(bid):
    """Calibrated (rh3-scale) per_game talent prior for a batter id, or None."""
    if bid is None or (isinstance(bid, float) and np.isnan(bid)):
        return None
    _load()
    rp = _raw_pg(int(bid))
    if rp is None:
        return None
    a, b = _CALIB
    return round(a + b * rp, 2)


def calib():
    _load()
    return _CALIB
