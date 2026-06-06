"""Decision logger + settler — PR 5 sub-actions 2-3.

Public API:
    DecisionRecord
    log_decision
    from_triangulate_result
    settle_decision
    SETTLEMENT_WINDOWS
    DECISIONS_ROOT

Captures VERDICT-level decisions (BUY/HOLD/CAUTION/FADE/MIXED) from
triangulate so we can later score whether our verdicts pay off. The
projection-input audit trail lives separately in
`data/research/player_projection_history.parquet` (PR 5 sub-action 1).
"""

from .logger import (
    DECISIONS_ROOT,
    DecisionRecord,
    from_triangulate_result,
    log_decision,
)

__all__ = [
    "DecisionRecord",
    "log_decision",
    "from_triangulate_result",
    "DECISIONS_ROOT",
]

# Settler is added by PR 5 sub-action 3 (next commit). Try-import so the
# intermediate commit stays runnable, and SETTLEMENT_WINDOWS / settle_decision
# become available once settler.py lands.
try:
    from .settler import SETTLEMENT_WINDOWS, settle_decision  # noqa: F401

    __all__ += ["settle_decision", "SETTLEMENT_WINDOWS"]
except ImportError:
    pass
