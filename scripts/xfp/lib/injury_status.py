"""injury_status — an offline name -> IL-status cache for triangulate.

The triangulate engine stays offline + deterministic, but its IL caveat needs a
current injury signal. This module is the seam: ``refresh_il_cache()`` pulls live
ESPN injury flags once (run by the daily pipeline) and writes a small JSON;
``load_il_map()`` / ``il_status_for()`` read it offline, keyed by the canonical
``name_match._normalize`` so lookups are order/format independent.

Cache shape: ``{"fetched": "YYYY-MM-DD", "il": {"<display name>": "IL60", ...}}``
(only injured players are stored). Lives at data/research/xfp_cache/injury_status.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run as a script (python scripts/xfp/lib/injury_status.py), sys.path[0] is this
# lib/ dir, so the function-level `from app.espn_connector import ...` can't find
# `app` (it lives at the repo root). Put the root on the path. This was the CI
# refresh step-4.05 `ModuleNotFoundError: No module named 'app'` (fail-soft, so the
# injury cache silently went stale on the self-hosted runner). (fix 2026-06-27)
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plv_clone.paths import CACHE
from plv_clone.utils.name_match import _normalize

INJURY_CACHE = CACHE / "injury_status.json"

# ESPN injury states that count as "on the IL" for the caveat (mirrors the
# matchup dashboard's IL_INJURY_STATES, minus DAY_TO_DAY which is not the IL).
_IL_STATES = frozenset({
    "TEN_DAY_DL", "FIFTEEN_DAY_DL", "SIXTY_DAY_DL", "INJURY_RESERVE", "OUT",
    "IL10", "IL15", "IL60", "IL",
})


def load_il_map(path: Path | str = INJURY_CACHE) -> dict:
    """Return ``{_normalize(name): status}`` from the cache, or ``{}`` if missing."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh).get("il", {})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return {_normalize(name): status for name, status in raw.items()}


def il_status_for(name: str, il_map: dict | None = None) -> str | None:
    """IL status for a player name, or None. Loads the cache if ``il_map`` is None."""
    if il_map is None:
        il_map = load_il_map()
    return il_map.get(_normalize(name))


def refresh_il_cache(path: Path | str = INJURY_CACHE) -> int:
    """Pull live ESPN injury flags for all rostered players and write the cache.

    Returns the number of injured players written. Live — run by the daily
    pipeline, not in tests.
    """
    import datetime
    from app.espn_connector import get_all_teams

    teams = get_all_teams()
    il: dict[str, str] = {}
    for _, row in teams.iterrows():
        status = str(row.get("injury_status") or "").upper()
        if row.get("injured") and status in _IL_STATES:
            name = row.get("player_name")
            if name:
                il[str(name)] = status
    payload = {
        "fetched": datetime.date.today().isoformat(),
        "il": il,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return len(il)


if __name__ == "__main__":
    print(f"  injury_status: cached {refresh_il_cache()} injured players -> {INJURY_CACHE.name}")
