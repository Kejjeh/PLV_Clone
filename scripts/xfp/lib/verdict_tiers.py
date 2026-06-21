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


# Bull/base/bear probability mass per Sustainability bucket — shared by both
# sustainability engines (pitcher used an if/elif chain, hitter a dict; identical
# values). Unknown / non-sentinel buckets fall back to the symmetric default.
ROS_BUCKET_P = {
    "LEGIT":     (0.40, 0.45, 0.15),
    "IMPROVING": (0.25, 0.50, 0.25),
    "MIXED":     (0.20, 0.40, 0.40),
    "NOISE":     (0.10, 0.30, 0.60),
    "STABLE":    (0.20, 0.60, 0.20),
    "BAD_LUCK":  (0.40, 0.40, 0.20),
    "REGRESS":   (0.10, 0.30, 0.60),
}
_ROS_DEFAULT = (0.25, 0.50, 0.25)


def ros_expectation(bucket: str, fp_cur: float, fp_prior: float) -> dict:
    """Bayesian rest-of-season expectation (bull/base/bear) from a bucket.

    Scale-free positional scalars: fp_cur/fp_prior are FP/start (SP) or FP/game
    (H). bull = form sustains, bear = full revert to prior, base = halfway. The
    caller pre-checks sentinel buckets (NO_2026_DATA / NO_BASELINE) and returns {}.
    """
    p = ROS_BUCKET_P.get(bucket, _ROS_DEFAULT)
    bull, base, bear = fp_cur, 0.5 * fp_cur + 0.5 * fp_prior, fp_prior
    ev = p[0] * bull + p[1] * base + p[2] * bear
    return {"bull": bull, "base": base, "bear": bear,
            "p_bull": p[0], "p_base": p[1], "p_bear": p[2], "ev": ev}


def divergence_signal(my_ev: float, model_value: float, bucket: str, *,
                      threshold: float, model_label: str) -> tuple[str, str]:
    """Read the gap between sustainability E[ROS] and the validated model number.

    Shared by both engines; ``threshold`` is the per-role scale (1.5 FP/start SP,
    0.4 FP/game H) and ``model_label`` is woven into the interpretation text
    ('rp3' / 'rh3'). ``model_value`` must be non-None — the caller emits the
    NO_<MODEL> signal for a missing projection (the one role-specific fork).
    """
    gap = my_ev - model_value
    if abs(gap) < threshold:
        if bucket in ("LEGIT", "IMPROVING"):
            return ("AGREE_BULLISH", f"sustainability + {model_label} both bullish")
        if bucket in ("REGRESS", "NOISE"):
            return ("AGREE_BEARISH", f"sustainability + {model_label} both bearish")
        return ("AGREE", f"sustainability + {model_label} within noise")
    if gap > threshold:
        if bucket in ("LEGIT", "IMPROVING"):
            return ("BUY_LOW", f"skill signals strong but {model_label} conservative — "
                                "model may be lagging the breakout")
        if bucket == "NOISE":
            return ("SELL_HIGH", f"production up but skills do not support — "
                                 f"{model_label} already conservative, regression coming")
        if bucket == "BAD_LUCK":
            return ("BUY_LOW", f"production down but skills holding — "
                               f"{model_label} may catch the bounce")
        return ("DISAGREE", f"sustainability E[ROS]={my_ev:.2f} "
                            f">> {model_label}={model_value:.2f} — investigate")
    if bucket == "REGRESS":
        return ("SELL_HIGH", f"skill regression real but {model_label} still bullish — "
                             "sell now before model catches up")
    return ("DISAGREE", f"sustainability E[ROS]={my_ev:.2f} "
                        f"<< {model_label}={model_value:.2f} — investigate")
