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


def topnav_css() -> str:
    """Canonical CSS for the shared `.topnav` (see `topnav()`).

    The nav HTML owner historically shipped no CSS, so each page hand-copied the
    `.topnav` rules into its own `<style>` — and drifted: `xfp_board.html` shipped
    the nav markup with NO matching CSS, so its nav fell back to raw browser links
    (audit 2026-07-23). Owning the CSS here too closes that drift: a builder emits
    `{topnav_css()}` inside its `<style>` and gets identical, on-theme nav styling.

    Consumes the standard theme vars every dashboard already defines
    (`--dim`, `--text`, `--border`, `--panel`, `--accent`). Plain CSS (single
    braces) — safe to interpolate into an f-string template; do NOT wrap in a
    `str.format()` call.
    """
    return """
nav.topnav { display: flex; align-items: center; gap: 0;
             font-family: 'IBM Plex Mono', ui-monospace, monospace;
             font-size: .72em; text-transform: uppercase; letter-spacing: .15em;
             margin-top: .4em; }
nav.topnav a { color: var(--dim); text-decoration: none; padding: .35em .9em;
               border: 1px solid var(--border); border-right: 0; cursor: pointer; }
nav.topnav a:first-child { border-radius: 3px 0 0 3px; }
nav.topnav a:last-child  { border-radius: 0 3px 3px 0; border-right: 1px solid var(--border); }
nav.topnav a:hover { color: var(--text); background: var(--panel); }
nav.topnav a.current { color: var(--accent); background: var(--panel); border-color: var(--accent); }
@media (max-width: 640px) {
  nav.topnav { font-size: .65em; flex-wrap: wrap; }
  nav.topnav a { padding: .3em .65em; }
}
"""
