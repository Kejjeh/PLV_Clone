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

from plv_clone.league_config import SEASON_YEAR

LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", "0"))
# Default from league_config so a rollover is ONE bump; ESPN_YEAR still
# overrides for a historical pull (issue #59).
YEAR      = int(os.environ.get("ESPN_YEAR", str(SEASON_YEAR)))
SWID      = os.environ.get("ESPN_SWID", "")
ESPN_S2   = os.environ.get("ESPN_S2", "")


def _wrap_free_agents_with_snapshot(league) -> None:
    """Nightly-refresh network diet (audit 2026-07-19 F3).

    Every refresh step runs as its own subprocess, so the expensive paginated
    ``free_agents(size=2000)`` pull was re-fetched 5-6x per night (steps 0.7 /
    2a / 4 / 4.72a / 4.55 ...). When ``PLV_ESPN_SNAPSHOT=1`` — set ONLY by the
    refresh_dashboards driver — the plain big-pool pull is served from a
    short-TTL disk pickle so ONE live pull feeds the whole refresh (and every
    step sees the SAME consistent pool). Interactive/skill use never sets the
    env var and stays fully live.

    Fail-open by construction: any snapshot problem (missing dir, stale file,
    unpicklable objects after an espn_api upgrade) falls through to the live
    call. Filtered pulls (position/position_id kwargs) are never cached.
    TTL: ``PLV_ESPN_SNAPSHOT_TTL_MIN`` (default 180 min ~ one refresh run).
    """
    import pickle
    import time as _time

    live = league.free_agents
    snap_dir = Path(__file__).resolve().parents[2] / "data" / "research" / "espn_snapshot"
    ttl_s = float(os.environ.get("PLV_ESPN_SNAPSHOT_TTL_MIN", "180")) * 60

    def cached_free_agents(*args, **kwargs):
        # cache ONLY the canonical no-filter pull, keyed by size
        cacheable = not args and set(kwargs) <= {"size"}
        if not cacheable:
            return live(*args, **kwargs)
        size = kwargs.get("size", 50)
        p = snap_dir / f"free_agents_{size}.pkl"
        try:
            if p.exists() and (_time.time() - p.stat().st_mtime) < ttl_s:
                with open(p, "rb") as f:
                    return pickle.load(f)
        except Exception:
            pass
        fas = live(*args, **kwargs)
        try:
            snap_dir.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                pickle.dump(fas, f)
        except Exception:
            pass
        return fas

    league.free_agents = cached_free_agents


def _is_auth_error(exc_or_msg) -> bool:
    """True when an ESPN failure is a credential problem, not a transient one.

    Auth failures are the single most common ESPN error (cookies expire), and
    they are the one class that retrying can never fix — so the retry loop
    uses this to bail out immediately rather than burning 7s on three
    identically-doomed requests.
    """
    return any(tok in str(exc_or_msg).lower() for tok in _AUTH_ERROR_HINTS)


@lru_cache(maxsize=8)
def get_league(year: int | None = None):
    """Return an authenticated ESPN League for *year* (default: current season).

    The year-aware sibling of :func:`_get_league` — same credential check,
    same retry/backoff, same auth-error fast-fail — for callers that need a
    HISTORICAL season (the synthetic-calibration backfills fetch 2024/2025).
    Cached per year. The current-season path should keep using
    :func:`_get_league`: only that one gets the FA snapshot wrapper.
    """
    if not (LEAGUE_ID and SWID and ESPN_S2):
        raise RuntimeError(
            "ESPN credentials missing. Set ESPN_LEAGUE_ID, ESPN_SWID, ESPN_S2 "
            "(and optionally ESPN_YEAR) in your environment or in a `.env` file. "
            "See .env.example for the format."
        )
    if year is None:
        year = YEAR
    try:
        from espn_api.baseball import League
        # Retry with backoff (audit 2026-07-19 M3): the League constructor is
        # one big authenticated GET and the single most common transient
        # failure point — an ESPN 5xx here used to abort the whole engine.
        league = None
        for _attempt, _delay in ((1, 2), (2, 5), (3, None)):
            try:
                league = League(
                    league_id=LEAGUE_ID,
                    year=year,
                    espn_s2=ESPN_S2,
                    swid=SWID,
                )
                break
            except ImportError:
                raise
            except Exception as _le:
                # An expired cookie is not transient — retrying it just delays
                # the "refresh your cookies" message by 7 seconds.
                if _delay is None or _is_auth_error(_le):
                    raise
                import time as _t
                print(f"  espn: League construction failed "
                      f"({type(_le).__name__}: {_le}) — retry {_attempt}/2 "
                      f"in {_delay}s")
                _t.sleep(_delay)
        return league
    except ImportError:
        raise ImportError(
            "espn-api not installed. Run: pip install espn-api"
        )
    except Exception as e:
        msg = str(e).strip()
        msg_l = msg.lower()
        if _is_auth_error(msg_l):
            friendly = (
                "ESPN authentication failed. Refresh the espn_s2 and SWID cookies "
                "(ESPN_S2 / ESPN_SWID env or .env)."
            )
        else:
            friendly = f"ESPN API connection failed: {msg or e.__class__.__name__}"
        logger.error(friendly)
        raise RuntimeError(friendly) from e


@lru_cache(maxsize=1)
def _get_league():
    """Return the authenticated CURRENT-season League (process-lifetime cache).

    Thin wrapper over :func:`get_league` that adds the one current-season-only
    behavior: the optional disk FA-snapshot wrapper the nightly refresh
    enables via PLV_ESPN_SNAPSHOT=1.
    """
    league = get_league(YEAR)
    if os.environ.get("PLV_ESPN_SNAPSHOT") == "1":
        _wrap_free_agents_with_snapshot(league)
    return league
