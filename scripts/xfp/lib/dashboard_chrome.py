"""dashboard_chrome.py — the ONE owner of the cross-dashboard top navigation.

Recreates the C3 seam (originally 2026-06-12, since reverted) so the GitHub-Pages
dashboards share a SINGLE nav source instead of 5 hand-copied `<nav>` blocks that
drift. As of 2026-07-04 the `xfp_board.html` link was present on the matchup nav
but MISSING from index / triangulate / profiles / live — the exact drift this
owner prevents. Every builder calls `topnav(<key>)`; adding a page = one edit here.
"""
from __future__ import annotations

# Ordered canonical page registry: (key, href, label). The order is the nav order.
PAGES: list[tuple[str, str, str]] = [
    ("index",           "index.html",           "XFP"),
    ("matchup",         "matchup.html",         "Matchup"),
    ("live",            "live_dashboard.html",  "Live"),
    ("xfp_board",       "xfp_board.html",       "xFP Board"),
    ("player_profiles", "player_profiles.html", "Profiles"),
    ("triangulate",     "triangulate.html",     "Triangulate"),
]

PAGE_KEYS = frozenset(k for k, _, _ in PAGES)


def topnav(current: str) -> str:
    """Return the shared `<nav class="topnav">…</nav>` HTML. `current` is the key
    of the active page (rendered as `<a class="current">` with no href). An
    unknown key raises — a typo must fail loud, not silently drop the highlight."""
    if current not in PAGE_KEYS:
        raise ValueError(f"dashboard_chrome.topnav: unknown page key {current!r}; "
                         f"valid keys: {sorted(PAGE_KEYS)}")
    links = []
    for key, href, label in PAGES:
        if key == current:
            links.append(f'<a class="current">{label}</a>')
        else:
            links.append(f'<a href="{href}">{label}</a>')
    return '<nav class="topnav">' + ''.join(links) + '</nav>'
