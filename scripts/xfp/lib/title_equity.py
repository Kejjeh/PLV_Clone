"""title_equity — convert a period-level Delta-P(win) into championship equity.

THE QUESTION THIS ANSWERS
-------------------------
The optimizer can tell you a move is worth +8.75pp of P(win) THIS PERIOD. That
is the right objective for the week in front of you, but it is not the objective
of the season, and the two can diverge sharply — because not every week is worth
the same amount of title probability.

``run_season_sim.py`` already computes exactly the missing multiplier: a
value-of-a-win curve, ``P(title | win period p) - P(title | lose period p)``,
estimated on common random numbers so the difference has low MC noise. This
module is the (deliberately thin) bridge:

    dtitle_equity_pp = dpwin x dtitle_pp(current period)

WHY IT MATTERS MORE THAN IT LOOKS
---------------------------------
The curve is far from flat. In the 2026 payload, winning period 15 was worth
**2.67pp** of title probability while period 17 was worth **0.88pp** — a 3x
difference. So the same +8.75pp weekly edge is worth ~0.23pp of championship
equity in one week and ~0.08pp in another. That is the difference between
"spend a churn move here" and "save it", and no amount of weekly P(win) analysis
can see it.

HOW IT DEGRADES, AND WHY IT DEGRADES RATHER THAN REFUSING
---------------------------------------------------------
``season_sim.json`` is regenerated on its own cadence, so it is routinely a
period or two behind the live matchup. Three cases, all handled explicitly:

  * **exact period match** -> ``fresh``
  * **curve has the period but the payload was generated earlier** -> ``stale``,
    with the gap reported. The number is still the right KIND of quantity (a
    forward-looking leverage weight); it is simply estimated from older
    standings. It is surfaced WITH its staleness rather than suppressed, because
    this is a DISPLAY conversion under Rule 13 — dpwin remains the sort key — and
    silently dropping the column would hide real strategic information.
  * **curve has an INTERIOR hole at the period** (``josh_sensitivities`` skips
    periods whose conditioning sample is under 50 sims) -> fall back to the mean
    of the adjacent periods and mark ``interpolated``.
  * **the period is OUTSIDE the curve entirely** -> refuse: ``dtitle_pp`` is
    None and ``status`` is ``out_of_range``. See below.

WHY EXTRAPOLATION IS REFUSED (audit 2026-08-14)
-----------------------------------------------
The hole branch used to fire for ANY missing period, including ones past the end
of the curve, and averaged whatever neighbours existed — which for a
past-the-end ask means the single last row. In the live 2026 payload the curve
covers [19, 20] while the period board asks for 20-23, so periods 21/22/23 (the
PLAYOFF ROUNDS) were being assigned period 20's weight of 0.30pp and labelled
``interpolated``.

That is a category error, not a precision loss. With P(playoffs) already 1.00, a
regular-season week is worth almost nothing; a playoff round is worth a large
fraction of the title. The two live on opposite sides of a regime boundary, and
no amount of averaging regular-season rows estimates a playoff row. Interpolating
an interior hole is estimating a quantity we bracketed on both sides;
extrapolating past the end is inventing one — and doing it under a label that
reads as "estimated".

So: interior holes interpolate, exterior asks refuse. Callers already handle
``dtitle_pp is None`` (that is the documented unavailable path), and the return
carries ``curve_periods`` so a caller can explain the gap and name the fix.

What we never do is multiply against the WRONG period's weight while claiming it
is the right one. Every return carries ``status`` and ``source_period`` so the
caller cannot accidentally launder a stale number as fresh.

``dtitle_mean_plus2_pp`` (title pp per +2 FP/week of roster quality) is returned
as CONTEXT for moves whose value persists past this week — a roster upgrade vs a
one-week streamer — but deliberately not folded into the sort.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from plv_clone.paths import ROOT

SEASON_SIM_JSON = ROOT / 'data' / 'outputs' / 'season_sim.json'

# Beyond this many periods behind, the weight is too stale to display without a
# hard warning. Three periods is roughly three weeks of standings movement.
#
# (STALE_PERIOD_WARN = 1 lived here until 2026-08-01. It was exported and
# documented but referenced nowhere, and it could not become referenced: the
# severity branch it would have gated already sits inside `if gap > 0`, so
# `gap >= 1` is unconditionally true there. Removed rather than left as a
# decorative export.)
STALE_PERIOD_HARD = 3


def load_payload(path: Path | None = None) -> Optional[dict]:
    """Read season_sim.json, or None when absent/unreadable.

    None is a legitimate state (the sim may never have run), and the caller
    degrades to 'no title equity available' rather than failing — this is a
    display layer, not a correctness-critical path.
    """
    p = Path(path) if path is not None else SEASON_SIM_JSON
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None


def win_value(period: int, payload: dict | None = None,
              path: Path | None = None) -> dict:
    """Title-probability value of winning ``period``.

    -> {'dtitle_pp', 'dplayoffs_pp', 'p_win_week', 'status', 'source_period',
        'payload_period', 'periods_stale', 'note', 'plus2_pp'}

    ``dtitle_pp`` is None when nothing usable exists; ``status`` is one of
    ``fresh`` / ``stale`` / ``interpolated`` / ``out_of_range`` /
    ``unknown_staleness`` / ``unavailable``. ``unknown_staleness`` means the
    payload carried no ``period``, so the weight is displayed but its age is
    undeterminable — it is deliberately NOT collapsed into ``fresh``.
    ``out_of_range`` means the period sits outside the curve and would require
    EXTRAPOLATION (see the module docstring); the weight is refused, not guessed.
    ``curve_periods`` reports the curve's (min, max) so a caller can say which
    periods the sim actually covers.
    """
    pay = payload if payload is not None else load_payload(path)
    out = {'dtitle_pp': None, 'dplayoffs_pp': None, 'p_win_week': None,
           'status': 'unavailable', 'source_period': None,
           'payload_period': None, 'periods_stale': None, 'note': '',
           'plus2_pp': None, 'curve_periods': None}
    if not pay:
        out['note'] = ('season_sim.json missing — run /season-sim to enable '
                       'title-equity conversion')
        return out

    josh = pay.get('josh') or {}
    curve = josh.get('value_of_win_curve') or []
    out['payload_period'] = pay.get('period')
    out['plus2_pp'] = (josh.get('sensitivity') or {}).get('dtitle_mean_plus2_pp')
    if not curve:
        out['note'] = 'value_of_win_curve empty (sim ran but produced no rows)'
        return out

    by_period = {int(r['period']): r for r in curve if r.get('period') is not None}
    if by_period:
        out['curve_periods'] = (min(by_period), max(by_period))
    row = by_period.get(int(period))

    if row is not None:
        out.update(dtitle_pp=row.get('dtitle_pp'),
                   dplayoffs_pp=row.get('dplayoffs_pp'),
                   p_win_week=row.get('p_win_week'),
                   source_period=int(period))
    else:
        # josh_sensitivities skips a period whose conditioning sample is < 50
        # sims, so an INTERIOR hole is expected rather than exceptional. A
        # period outside the curve is a different animal — see the module
        # docstring — and is refused rather than extrapolated.
        lo = [p for p in by_period if p < period]
        hi = [p for p in by_period if p > period]
        if not (lo and hi):
            c_lo, c_hi = (out['curve_periods'] or (None, None))
            out['status'] = 'out_of_range'
            out['note'] = (
                f'period {period} is outside the value-of-win curve '
                f'[{c_lo}, {c_hi}] — a weight here would be EXTRAPOLATED, not '
                f'interpolated. Regular-season and playoff-round win values sit '
                f'on opposite sides of a regime boundary, so neighbouring rows '
                f'do not estimate this one. Re-run /season-sim to extend the '
                f'curve through period {period}.')
            return out
        neigh = [by_period[max(lo)], by_period[min(hi)]]
        vals = [r.get('dtitle_pp') for r in neigh if r.get('dtitle_pp') is not None]
        if not vals:
            out['note'] = f'adjacent curve rows carry no dtitle_pp for period {period}'
            return out
        out.update(dtitle_pp=sum(vals) / len(vals),
                   source_period=[int(r['period']) for r in neigh],
                   status='interpolated',
                   note=(f'period {period} absent from the curve (conditioning '
                         f'sample likely < 50 sims); using the mean of periods '
                         f'{[int(r["period"]) for r in neigh]}'))

    pp = out['payload_period']
    if pp is not None:
        gap = int(period) - int(pp)
        out['periods_stale'] = gap
        if out['status'] != 'interpolated':
            out['status'] = 'fresh' if gap <= 0 else 'stale'
        if gap > 0:
            sev = 'HARD-STALE' if gap >= STALE_PERIOD_HARD else 'stale'
            extra = (f'season_sim.json was generated at period {pp}, now period '
                     f'{period} ({gap} behind, {sev}) — the leverage weight is '
                     f'estimated from older standings. Re-run /season-sim to '
                     f'refresh.')
            out['note'] = (out['note'] + ' | ' + extra) if out['note'] else extra
    elif out['status'] != 'interpolated':
        # AUDIT T21 (2026-08-01): this used to say 'fresh'. A payload carrying no
        # 'period' does not tell us the weight is CURRENT — it tells us we cannot
        # date it at all, and reporting that with the same word as a
        # generated-this-period weight is exactly the laundering this module's
        # contract forbids. Keep the number (degrade, never refuse); label the
        # ignorance.
        out['status'] = 'unknown_staleness'
        extra = ('season_sim payload carries no period — the weight\'s age could '
                 'not be determined; it may be current or many periods old. '
                 'Re-run /season-sim to get a datable weight.')
        out['note'] = (out['note'] + ' | ' + extra) if out['note'] else extra
    return out


def equity(dpwin: float, period: int, payload: dict | None = None,
           path: Path | None = None) -> dict:
    """Convert one dpwin into title-equity pp.

    -> {'dtitle_equity_pp', 'dtitle_pp_per_win', 'status', 'note', ...}

    ``dtitle_equity_pp`` is None whenever the weight is unavailable — never 0.0,
    which would read as "this move is worth nothing" rather than "we cannot say".
    That distinction matters: a silent zero here is the same class of error as a
    silent-zero feature fill.
    """
    wv = win_value(period, payload=payload, path=path)
    d = wv.get('dtitle_pp')
    out = dict(wv)
    out['dtitle_pp_per_win'] = d
    out['dtitle_equity_pp'] = (None if (d is None or dpwin is None)
                               else round(float(dpwin) * float(d), 4))
    return out


def annotate(moves: list[dict], period: int, *, dpwin_key: str = 'dpwin',
             payload: dict | None = None, path: Path | None = None) -> dict:
    """Attach title-equity fields to a list of move dicts, in place.

    Returns the shared ``win_value`` block so a caller can print the staleness
    banner ONCE rather than per row. Deliberately does NOT re-sort: dpwin remains
    the ranking key (Rule 13 — this is a displayed conversion, and the weight is
    a per-period constant anyway, so it cannot reorder within a period).
    """
    wv = win_value(period, payload=payload, path=path)
    d = wv.get('dtitle_pp')
    for m in moves:
        dp = m.get(dpwin_key)
        m['dtitle_pp_per_win'] = d
        m['dtitle_equity_pp'] = (None if (d is None or dp is None)
                                 else round(float(dp) * float(d), 4))
    return wv


def banner(wv: dict) -> str:
    """One-line human summary of the weight actually applied."""
    if wv.get('dtitle_pp') is None:
        return f'title equity: UNAVAILABLE — {wv.get("note") or "no weight"}'
    src = wv.get('source_period')
    bits = [f'winning period {src if not isinstance(src, list) else src} is worth '
            f'{wv["dtitle_pp"]:.2f}pp of title probability']
    if wv.get('status') == 'unknown_staleness':
        bits.append('weight age UNKNOWN (payload undated)')
    if wv.get('p_win_week') is not None:
        bits.append(f'sim P(win wk) {wv["p_win_week"]:.3f}')
    if wv.get('plus2_pp') is not None:
        bits.append(f'+2 FP/wk of roster quality ~ {wv["plus2_pp"]:.2f}pp')
    line = 'title equity [' + str(wv.get('status')).upper() + ']: ' + '; '.join(bits)
    if wv.get('note'):
        line += f'\n    NOTE: {wv["note"]}'
    return line


def dtitle_for_ros_delta(ros_fp_delta: float, *, remaining_weeks: float,
                         payload: dict | None = None,
                         path: Path | None = None) -> dict:
    """ΔP(title) for a rest-of-season FP delta — linearized v1 (2026-08-12).

    Converts a move's ΔRoS FP into weekly roster quality and applies the sim's
    own sensitivity (``dtitle_mean_plus2_pp`` = title pp per +2 FP/wk). Built
    when P(playoffs) hit 1.0 and regular-season win value collapsed (period 20
    = 0.30pp): from there, roster quality flows to the title almost entirely
    through playoff rounds, which the sensitivity already aggregates. The
    joint bracket MC (seeding, byes, opponent-conditional draws) is the
    registered upgrade; this stays honest by returning None — never 0.0 —
    when the sim payload can't support the conversion.
    """
    out = {'dtitle_pp': None, 'status': 'unavailable', 'note': ''}
    pay = payload if payload is not None else load_payload(path)
    if not pay:
        out['note'] = 'season_sim.json missing — run /season-sim'
        return out
    plus2 = ((pay.get('josh') or {}).get('sensitivity') or {}).get('dtitle_mean_plus2_pp')
    if plus2 is None:
        out['note'] = 'sim payload carries no sensitivity — re-run /season-sim'
        return out
    if remaining_weeks <= 0:
        out['note'] = 'no remaining weeks'
        return out
    per_week = ros_fp_delta / remaining_weeks
    out['dtitle_pp'] = (per_week / 2.0) * plus2
    out['status'] = 'linearized_v1'
    return out


__all__ = ['SEASON_SIM_JSON', 'load_payload', 'win_value', 'equity',
           'annotate', 'banner', 'STALE_PERIOD_HARD', 'dtitle_for_ros_delta']
