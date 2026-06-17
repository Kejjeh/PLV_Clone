"""ESPN authentication + the raw League factory — the single auth home.

This used to live in ``app/espn_connector.py``; it now lives in the package so
``league_state`` and any script depend on ONE auth source instead of reaching
"across" into app/. ``app/espn_connector.py`` re-exports these names, so its
existing importers and higher-level helpers are unaffected.

Credentials are read from the environment (set directly in CI, or loaded from a
``.env`` at the repo root for local dev). See ``.env.example``.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_AUTH_ERROR_HINTS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "authentication",
    "invalid session",
    "login",
    "cookie",
    "espn_s2",
    "swid",
)

# Best-effort .env loader so local dev doesn't need to export vars manually.
# Searches the repo root (src/plv_clone/espn.py -> parents[2]), the app/ dir,
# and the cwd, so creds load regardless of where the package sits relative to
# the caller. In CI the env vars are set directly and this is a no-op.
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[2]
    for _candidate in (_root / ".env", _root / "app" / ".env", Path.cwd() / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate)
            break
except ImportError:
    pass

LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", "0"))
YEAR      = int(os.environ.get("ESPN_YEAR", "2026"))
SWID      = os.environ.get("ESPN_SWID", "")
ESPN_S2   = os.environ.get("ESPN_S2", "")


@lru_cache(maxsize=1)
def _get_league():
    """Return authenticated ESPN League object (cached for process lifetime)."""
    if not (LEAGUE_ID and SWID and ESPN_S2):
        raise RuntimeError(
            "ESPN credentials missing. Set ESPN_LEAGUE_ID, ESPN_SWID, ESPN_S2 "
            "(and optionally ESPN_YEAR) in your environment or in a `.env` file. "
            "See .env.example for the format."
        )
    try:
        from espn_api.baseball import League
        return League(
            league_id=LEAGUE_ID,
            year=YEAR,
            espn_s2=ESPN_S2,
            swid=SWID,
        )
    except ImportError:
        raise ImportError(
            "espn-api not installed. Run: pip install espn-api"
        )
    except Exception as e:
        msg = str(e).strip()
        msg_l = msg.lower()
        if any(tok in msg_l for tok in _AUTH_ERROR_HINTS):
            friendly = (
                "ESPN authentication failed. Refresh the espn_s2 and SWID cookies "
                "(ESPN_S2 / ESPN_SWID env or .env)."
            )
        else:
            friendly = f"ESPN API connection failed: {msg or e.__class__.__name__}"
        logger.error(friendly)
        raise RuntimeError(friendly) from e
