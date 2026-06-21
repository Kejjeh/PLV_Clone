"""verdict_tiers — the canonical Sustainability-bucket vocabulary + classifier.

CONTEXT.md defines the **Sustainability bucket** as a domain concept, but it lived
as string literals + a duplicated if/elif chain in both pitcher_sustainability and
hitter_sustainability (identical structure; only the fp_delta threshold differed —
2.0 fp/start for SP, 0.5 fp/game for H). This is the one home for it.

A *toolkit*, not an orchestrator (ADR-0001): pure functions + name constants the
engines compose. Consumers import ``SUSTAINABILITY_TIERS`` instead of literal-
matching tier strings, so a rename is one edit.
"""
from __future__ import annotations

# Canonical Sustainability-bucket names (CONTEXT.md "Sustainability bucket").
SUSTAINABILITY_TIERS = {
    "LEGIT", "IMPROVING", "NOISE", "REGRESS", "BAD_LUCK", "STABLE", "MIXED",
}


def classify_sustainability(fp_delta: float, n_material: int,
                            fp_threshold: float) -> str:
    """Bucket a (fp_delta, n_material) pair into a Sustainability tier.

    Shared by the pitcher (fp_threshold=2.0, FP/start) and hitter
    (fp_threshold=0.5, FP/game) sustainability engines — same logic, the scale
    is the only difference, so it is a parameter, not a fork.

      LEGIT     — production up (>= threshold) AND >=7/9 markers favorable
      IMPROVING — up AND 5-6 favorable
      NOISE     — up AND <=3 favorable (production not skill-backed)
      REGRESS   — production down (<= -threshold) AND <=2 favorable
      BAD_LUCK  — down AND skills holding
      STABLE    — |change| < threshold (no real story)
      MIXED     — up with markers in the 4-marker gap (fall-through)
    """
    if fp_delta >= fp_threshold and n_material >= 7:
        return "LEGIT"
    if fp_delta >= fp_threshold and n_material >= 5:
        return "IMPROVING"
    if fp_delta >= fp_threshold and n_material <= 3:
        return "NOISE"
    if fp_delta <= -fp_threshold and n_material <= 2:
        return "REGRESS"
    if fp_delta <= -fp_threshold:
        return "BAD_LUCK"
    if abs(fp_delta) < fp_threshold:
        return "STABLE"
    return "MIXED"
