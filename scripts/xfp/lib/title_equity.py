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
  * **curve has no row for the period** (``josh_sensitivities`` skips periods
    whose conditioning sample is under 50 sims) -> fall back to the mean of the
    adjacent periods and mark ``interpolated``.

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
    ``fresh`` / ``stale`` / ``interpolated`` / ``unknown_staleness`` /
    ``unavailable``. ``unknown_staleness`` means the payload carried no
    ``period``, so the weight is displayed but its age is undeterminable — it is
    deliberately NOT collapsed into ``fresh``.
    """
    pay = payload if payload is not None else load_payload(path)
    out = {'dtitle_pp': None, 'dplayoffs_pp': None, 'p_win_week': None,
           'status': 'unavailable', 'source_period': None,
           'payload_period': None, 'periods_stale': None, 'note': '',
           'plus2_pp': None}
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
    row = by_period.get(int(period))

    if row is not None:
        out.update(dtitle_pp=row.get('dtitle_pp'),
                   dplayoffs_pp=row.get('dplayoffs_pp'),
                   p_win_week=row.get('p_win_week'),
                   source_period=int(period))
    else:
        # josh_sensitivities skips a period whose conditioning sample is < 50
        # sims, so a hole is expected rather than exceptional.
        lo = [p for p in by_period if p < period]
        hi = [p for p in by_period if p > period]
        neigh = []
        if lo:
            neigh.append(by_period[max(lo)])
        if hi:
            neigh.append(by_period[min(hi)])
        if not neigh:
            out['note'] = (f'no curve row for period {period} and no adjacent '
                           f'periods to interpolate from')
            return out
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


__all__ = ['SEASON_SIM_JSON', 'load_payload', 'win_value', 'equity',
           'annotate', 'banner', 'STALE_PERIOD_HARD']
