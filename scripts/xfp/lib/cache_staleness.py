"""Shared current-season cache staleness rule (issue #40).

One threshold for every scraper cache that includes the in-progress season,
so the FG-leverage and BRef-IR joins in build_rp_archetypes can never
disagree about what "current" means.
"""
import datetime as _dt

CURRENT_SEASON_MAX_AGE_DAYS = 7


def current_season_stale(path, years) -> bool:
    """True if `years` includes the in-progress season and `path` is missing
    or older than CURRENT_SEASON_MAX_AGE_DAYS. Completed seasons never go
    stale. A missing cache is stale (=> do the full pull), never a crash."""
    this_year = _dt.date.today().year
    if this_year not in years:
        return False
    if not path.exists():
        return True
    age_days = (_dt.datetime.now()
                - _dt.datetime.fromtimestamp(path.stat().st_mtime)).days
    return age_days > CURRENT_SEASON_MAX_AGE_DAYS
