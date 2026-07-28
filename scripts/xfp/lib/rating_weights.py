"""rating_weights.py — the ONE owner of FPwt / OVERALL_FP composite weights.

Extracted verbatim (item 3, 2026-07-04) from
build_player_profiles_dashboard.annotate_overall_fp so every surface
(the profiles dashboard, /triangulate, /scouting-report, /fa-pickup-deep-dive)
computes the FP-faithful composite from ONE place instead of re-deriving the
weights. Registry rule: every shared fact has one owner module.

OVERALL_FP is a display/context construct (Rule 13): it NEVER moves the
rh3/rp3/rprs2/baseline xFP headline. The shipped OVERALL (which feeds
`arche_overall_prior` -> baseline xFP) is deliberately untouched — changing
its construction requires /validate-feature.

Weights cite the 2026-07-04 CV-by-year refit study (rating_reimagine memo):
  hitter  .58 CONTACT / .17 POWER / .17 SB / .08 DISCIPLINE
          (fwd .515 vs shipped OVERALL's .477 — shipped forward-predicts
          WORSE than simply carrying last year's FP)
  sp      .76 STUFF / .14 MOVEMENT / .10 CONTROL   (fwd .577 vs shipped .551)
  rp      role-first: .55 z(SV) + .35 STUFF + .10 z(FP/g)
          (r .558 vs FP-carry .508; CONTROL/BATTED_BALL fwd ~0 + anti-signal
          -> excluded)
"""
from __future__ import annotations

import statistics

# The two pillar-weighted roles (pure per-row). RP is population-relative
# (z-scored within year) and handled in annotate_overall_fp only.
WEIGHTS: dict[str, list[tuple[str, float]]] = {
    "hitter": [("CONTACT", .58), ("POWER", .17), ("SB", .17), ("DISCIPLINE", .08)],
    "sp": [("STUFF", .76), ("MOVEMENT", .14), ("CONTROL", .10)],
}


# Sub-rating-level FPwt (item 7, optional display variant). The rating_reimagine
# study found refit SUB-ratings forward-predict slightly better than the pillar
# composite (SP subs .590 vs pillars .577; hitter subs .548 vs pillars .515).
# Ridge sub-weights from the memo — SP is SWING_MISS-dominant; hitter keeps only
# the positive-signal leads (RAW_POWER, K_AVOIDANCE) and drops CONTACT_QUALITY
# (~-.001) / SPRAY_PROFILE (~0) as noise. Weights are normalized to sum 1 within
# each role so the output stays on the 20-80 pillar scale. Display/context only
# (Rule 13) — a diagnostic variant beside OVERALL_FP, never a projection number.
SUB_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    "sp": [("SWING_MISS", .174), ("velo_rating", .036), ("DAMAGE_SUPP", .034),
           ("WALK_AVOID", .026), ("STRIKE_THROWING", .021), ("CALLED_STRIKE", .018),
           ("GB_TENDENCY", .010)],
    "hitter": [("RAW_POWER", .007), ("K_AVOIDANCE", .005)],
}


def overall_fp_sub(role: str, row) -> int | None:
    """Sub-rating FPwt (20-80) for a single hitter/SP row, from the reweighted
    sub-ratings (item 7). Returns None if any required sub-rating is missing
    (never invents). Weights are normalized to sum 1."""
    weights = SUB_WEIGHTS.get(role)
    if not weights:
        return None
    vals = [(row.get(k), w) for k, w in weights]
    if any(v is None for v, _ in vals):
        return None
    wsum = sum(w for _, w in weights) or 1.0
    return int(round(sum(v * w for v, w in vals) / wsum))


def annotate_overall_fp_sub(records: list[dict], role: str) -> None:
    """Attach OVERALL_FP_SUB (20-80) to each hitter/SP record in place (item 7).
    None for any record missing a required sub-rating, or for roles without a
    defined sub set (e.g. RP)."""
    for r in records:
        r["OVERALL_FP_SUB"] = overall_fp_sub(role, r)


def overall_fp(role: str, row) -> int | None:
    """FPwt (20-80) for a single hitter/SP row. Returns None if any input
    pillar is missing (never invents a number). RP FPwt is population-relative
    (z within year) so a single row cannot be scored -> None; use
    annotate_overall_fp(records, 'rp') for relievers."""
    weights = WEIGHTS.get(role)
    if weights is None:
        return None
    vals = [(row.get(k), w) for k, w in weights]
    if any(v is None for v, _ in vals):
        return None
    return int(round(sum(v * w for v, w in vals)))


def annotate_overall_fp(records: list[dict], role: str) -> None:
    """Attach OVERALL_FP (20-80) to each record in place. Never invents: any
    missing input pillar -> None for that row. For hitter/SP this is the pure
    weighted sum; for RP it is the role-first z-blend within each year."""
    if role in WEIGHTS:
        for r in records:
            r["OVERALL_FP"] = overall_fp(role, r)
        return

    # RP: role-first — z of saves + STUFF + z of FP level, z within YEAR so the
    # 20-80 units match the pillar convention (mean 50 / sd 10, clipped).
    by_year: dict[int, list[dict]] = {}
    for r in records:
        if r.get("year") is not None:
            by_year.setdefault(int(r["year"]), []).append(r)

    def _z_rating(v, mean, sd):
        if v is None or sd == 0:
            return None
        return max(20.0, min(80.0, 50.0 + 10.0 * (float(v) - mean) / sd))

    for _, rows in by_year.items():
        svs = [float(r["sv"]) for r in rows if r.get("sv") is not None]
        fps = [float(r["fp_per_g"]) for r in rows if r.get("fp_per_g") is not None]
        if len(svs) < 5 or len(fps) < 5:
            for r in rows:
                r["OVERALL_FP"] = None
            continue
        sv_m, sv_s = statistics.mean(svs), statistics.pstdev(svs) or 1.0
        fp_m, fp_s = statistics.mean(fps), statistics.pstdev(fps) or 1.0
        for r in rows:
            role_r = _z_rating(r.get("sv"), sv_m, sv_s)
            fp_r = _z_rating(r.get("fp_per_g"), fp_m, fp_s)
            stuff = r.get("STUFF")
            if None in (role_r, fp_r, stuff):
                r["OVERALL_FP"] = None
            else:
                r["OVERALL_FP"] = int(round(.55 * role_r + .35 * float(stuff) + .10 * fp_r))
