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
from plv_clone.il_states import IL_STATES_STRICT as _IL_STATES  # issue #28


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

    2026-07-11 (A2/E1.5b): also fetches per-player ``injury_details`` (ESPN
    estimated return_date, injury_type, status_code) for the INJURED subset
    only (~30-80 bounded GETs — the full ~1500-player universe would blow the
    step budget; league_state.injury_details is one GET per player). Written
    under ``details`` keyed by ESPN player_id, each record carrying the
    display name so offline consumers (snapshot logger) can join by
    normalized name. This is the daily ESPN return-date ESTIMATE log that the
    E1.5b estimate-vs-actual calibration study needs. Fail-soft: a details
    fetch error still writes the flag cache.
    """
    import datetime
    from plv_clone.league_state import default_state

    state = default_state()
    teams = state.all_teams()
    il: dict[str, str] = {}
    il_ids: dict[int, str] = {}          # espn player_id -> display name
    for _, row in teams.iterrows():
        status = str(row.get("injury_status") or "").upper()
        if row.get("injured") and status in _IL_STATES:
            name = row.get("player_name")
            if name:
                il[str(name)] = status
                pid = row.get("player_id")
                if pid is not None and not (isinstance(pid, float) and pid != pid):
                    il_ids[int(pid)] = str(name)

    details: dict[str, dict] = {}
    try:
        det = state.injury_details(sorted(il_ids))
        for _, r in det.iterrows():
            pid = r.get("player_id")
            if pid is None or (isinstance(pid, float) and pid != pid):
                continue
            pid = int(pid)
            rd = r.get("return_date")
            details[str(pid)] = {
                "name": il_ids.get(pid),
                "status": il.get(il_ids.get(pid, ""), None),
                "return_date": str(rd) if rd is not None and str(rd) != "NaT" and rd == rd else None,
                "days_until_return": (int(r["days_until_return"])
                                      if r.get("days_until_return") is not None
                                      and r.get("days_until_return") == r.get("days_until_return")
                                      else None),
                "injury_type": r.get("injury_type") if r.get("injury_type") == r.get("injury_type") else None,
                "status_code": r.get("status_code") if r.get("status_code") == r.get("status_code") else None,
            }
    except Exception as exc:  # fail-soft: flag cache must still land
        print(f"  ! injury_details fetch failed ({type(exc).__name__}: {exc}) — "
              f"details section omitted, flag cache still written")

    payload = {
        "fetched": datetime.date.today().isoformat(),
        "il": il,
        "details": details,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return len(il)


def load_injury_details(path: Path | str = INJURY_CACHE) -> tuple[dict, str | None]:
    """Return ``({_normalize(name): detail_record}, fetched_date)`` from the cache.

    Records whose normalized name is ambiguous (two injured players normalize
    identically — the Max Muncy class) are DROPPED rather than guessed
    (feedback_player_name_collisions). Returns ``({}, None)`` if the cache is
    missing or predates the ``details`` section.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}, None
    fetched = raw.get("fetched")
    out: dict[str, dict] = {}
    ambiguous: set[str] = set()
    for rec in (raw.get("details") or {}).values():
        name = rec.get("name")
        if not name:
            continue
        key = _normalize(name)
        if key in out:
            ambiguous.add(key)
            continue
        out[key] = rec
    for key in ambiguous:
        out.pop(key, None)
    return out, fetched


if __name__ == "__main__":
    print(f"  injury_status: cached {refresh_il_cache()} injured players -> {INJURY_CACHE.name}")
