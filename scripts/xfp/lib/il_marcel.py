"""il_marcel — an honest per-start projection for a pitcher rp3 cannot read.

WHY THIS EXISTS
rp3 tags an IL'd starter `data_quality_tag='marcel_il'` and hands back a
SUPPRESSED Marcel prior with `gs_to=0`. That number is not a forecast of what
the pitcher will do when he returns — it is a placeholder that says "no
in-season signal". Ranking a stash pool by it puts Corbin Burnes below a
replacement-level arm, which is how the 2026-08-05 stash board came out.

This module answers the question rp3 declines to: **given what this pitcher did
in prior SEASONS, what is his BrownU FP per start when he comes back?**

METHOD (deliberately plain — a Marcel, not a model)
  * BrownU SP FP/start per season = (K + IP*3.3 - H - 2*ER - BB - HBP) / GS.
  * Recent seasons weighted 5/4/3 (t-1, t-2, t-3), each also weighted by that
    season's GS so a 4-start cameo cannot outvote a 30-start year.
  * Regressed toward the league mean by adding REGRESS_STARTS worth of average
    starts. With few career starts the estimate collapses to league average,
    which is the honest answer for a pitcher with no track record.
  * NO age curve, NO injury-severity term. Both would be guesses; the point of
    a Marcel is that every input is observable.

WHAT IT IS NOT
Not a replacement for rp3 on healthy pitchers — rp3 is validated and uses
in-season process. This only fills the hole where rp3 reports it has nothing.
Rule 13: it never edits an rp3 row, it stands beside one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# League-average BrownU FP per start. Anchor for regression; the 2026 pool's
# prior-career mean is 11.03 (pitcher_prior_career.csv), so this is measured,
# not assumed.
LEAGUE_FP_PER_START = 11.0
# Starts of league-average pulled toward the estimate. Chosen so ~10 career
# starts still sits near league average and ~60 starts is mostly the pitcher.
REGRESS_STARTS = 30.0
# Marcel recency weights for t-1, t-2, t-3.
YEAR_WEIGHTS = (5.0, 4.0, 3.0)


@dataclass(frozen=True)
class SeasonLine:
    season: int
    gs: int
    ip: float
    k: int
    h: int
    er: int
    bb: int
    hbp: int

    @property
    def fp(self) -> float:
        return (self.k + self.ip * 3.3 - self.h - 2 * self.er
                - self.bb - self.hbp)

    @property
    def fp_per_start(self) -> Optional[float]:
        return self.fp / self.gs if self.gs else None


@dataclass(frozen=True)
class IlMarcel:
    fp_per_start: float
    effective_starts: float      # GS-weighted, recency-weighted sample behind it
    seasons_used: int
    raw_fp_per_start: Optional[float]   # before regression; None if no starts
    confidence: str              # HIGH / MEDIUM / LOW / NONE


def project(lines: Iterable[SeasonLine], as_of_season: int,
            min_gs: int = 3) -> IlMarcel:
    """Project FP/start for *as_of_season* from prior seasons only.

    Seasons at or after *as_of_season* are ignored entirely — including the
    current one — so the estimate cannot borrow the very sample the IL wiped
    out. A caller with real pre-injury starts this year should pass them as a
    SeasonLine for as_of_season - 0.5 is NOT supported; use `blend_current`.
    """
    prior = sorted([l for l in lines if l.season < as_of_season and l.gs >= min_gs],
                   key=lambda l: -l.season)
    num = den = 0.0
    used = 0
    for i, line in enumerate(prior[:len(YEAR_WEIGHTS)]):
        fps = line.fp_per_start
        if fps is None:
            continue
        w = YEAR_WEIGHTS[i] * line.gs
        num += fps * w
        den += w
        used += 1
    if den == 0:
        return IlMarcel(LEAGUE_FP_PER_START, 0.0, 0, None, 'NONE')
    raw = num / den
    # effective starts = recency-weighted GS, normalised by the top weight so
    # "30 starts last year" reads as 30, not 150.
    eff = den / YEAR_WEIGHTS[0]
    proj = ((raw * eff) + (LEAGUE_FP_PER_START * REGRESS_STARTS)) / (eff + REGRESS_STARTS)
    conf = ('HIGH' if eff >= 45 else 'MEDIUM' if eff >= 20
            else 'LOW' if eff >= 8 else 'NONE')
    return IlMarcel(round(proj, 2), round(eff, 1), used, round(raw, 2), conf)


def blend_current(base: IlMarcel, current: Optional[SeasonLine],
                  current_weight: float = 5.0) -> IlMarcel:
    """Fold THIS season's pre-injury starts into a prior-seasons projection.

    A pitcher who made 8 good starts before getting hurt is telling you
    something rp3 threw away. Weighted like a t-1 season (the top Marcel
    weight), because it is the most recent evidence there is.
    """
    if current is None or not current.gs or current.fp_per_start is None:
        return base
    w_cur = current_weight * current.gs
    w_base = YEAR_WEIGHTS[0] * base.effective_starts
    if w_cur + w_base == 0:
        return base
    raw = ((current.fp_per_start * w_cur)
           + ((base.raw_fp_per_start if base.raw_fp_per_start is not None
               else LEAGUE_FP_PER_START) * w_base)) / (w_cur + w_base)
    eff = base.effective_starts + current.gs
    proj = ((raw * eff) + (LEAGUE_FP_PER_START * REGRESS_STARTS)) / (eff + REGRESS_STARTS)
    conf = ('HIGH' if eff >= 45 else 'MEDIUM' if eff >= 20
            else 'LOW' if eff >= 8 else 'NONE')
    return IlMarcel(round(proj, 2), round(eff, 1), base.seasons_used + 1,
                    round(raw, 2), conf)


# ── HITTERS ──────────────────────────────────────────────────────────────────
# Same idea, different denominator. A hitter's IL'd season is destroyed the same
# way a pitcher's is, and rh3 has the same nothing to say about it.
#
# League BrownU FP/PA, measured off MLB team totals: .4738 (2024), .4840 (2025),
# .4865 (2026). Flat enough to use one anchor.
LEAGUE_FP_PER_PA = 0.484
# PA of league-average pulled toward the estimate. ~200 PA is the usual Marcel
# scale for a rate this noisy and keeps a 100-PA cameo near the prior.
REGRESS_PA = 200.0


@dataclass(frozen=True)
class BatterSeason:
    season: int
    g: int
    pa: int
    r: int
    tb: int
    rbi: int
    bb: int
    hbp: int
    sb: int
    k: int

    @property
    def fp(self) -> float:
        return self.r + self.tb + self.rbi + self.bb + self.hbp + self.sb - self.k

    @property
    def fp_per_pa(self) -> Optional[float]:
        return self.fp / self.pa if self.pa else None


def _tier(eff: float, hi: float, med: float, lo: float) -> str:
    return ('HIGH' if eff >= hi else 'MEDIUM' if eff >= med
            else 'LOW' if eff >= lo else 'NONE')


def project_hitter(lines: Iterable[BatterSeason], as_of_season: int,
                   min_pa: int = 40) -> IlMarcel:
    """FP/PA for *as_of_season* from prior seasons only. `effective_starts`
    carries effective PA here — same field, denominator named by the caller."""
    prior = sorted([l for l in lines if l.season < as_of_season and l.pa >= min_pa],
                   key=lambda l: -l.season)
    num = den = 0.0
    used = 0
    for i, line in enumerate(prior[:len(YEAR_WEIGHTS)]):
        rate = line.fp_per_pa
        if rate is None:
            continue
        w = YEAR_WEIGHTS[i] * line.pa
        num += rate * w
        den += w
        used += 1
    if den == 0:
        return IlMarcel(LEAGUE_FP_PER_PA, 0.0, 0, None, 'NONE')
    raw = num / den
    eff = den / YEAR_WEIGHTS[0]
    proj = ((raw * eff) + (LEAGUE_FP_PER_PA * REGRESS_PA)) / (eff + REGRESS_PA)
    return IlMarcel(round(proj, 4), round(eff, 1), used, round(raw, 4),
                    _tier(eff, 400, 180, 60))


def blend_current_hitter(base: IlMarcel, current: Optional[BatterSeason],
                         current_weight: float = 5.0) -> IlMarcel:
    """Fold this season's pre-injury PA into a prior-seasons projection."""
    if current is None or not current.pa or current.fp_per_pa is None:
        return base
    w_cur = current_weight * current.pa
    w_base = YEAR_WEIGHTS[0] * base.effective_starts
    if w_cur + w_base == 0:
        return base
    prior_raw = (base.raw_fp_per_start if base.raw_fp_per_start is not None
                 else LEAGUE_FP_PER_PA)
    raw = ((current.fp_per_pa * w_cur) + (prior_raw * w_base)) / (w_cur + w_base)
    eff = base.effective_starts + current.pa
    proj = ((raw * eff) + (LEAGUE_FP_PER_PA * REGRESS_PA)) / (eff + REGRESS_PA)
    return IlMarcel(round(proj, 4), round(eff, 1), base.seasons_used + 1,
                    round(raw, 4), _tier(eff, 400, 180, 60))


__all__ = ['SeasonLine', 'BatterSeason', 'IlMarcel', 'project', 'blend_current',
           'project_hitter', 'blend_current_hitter',
           'LEAGUE_FP_PER_START', 'REGRESS_STARTS', 'YEAR_WEIGHTS',
           'LEAGUE_FP_PER_PA', 'REGRESS_PA']
