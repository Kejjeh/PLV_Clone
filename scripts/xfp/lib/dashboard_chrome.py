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


# ---------------------------------------------------------------------------
# Shared theming (2026-07-23). Single-sources the light/dark palette + toggle
# so every dashboard supports both themes from one place instead of the old
# situation: only index.html had a light mode (and it didn't even persist),
# the other 5 pages were hardcoded-dark, and nothing shared a preference.
#
# Contract (same as topnav_css): every function below returns a PLAIN string
# with SINGLE braces. Embed it as an f-string VALUE (`{theme_css()}`) or a
# `.replace()` placeholder. NEVER pass these through `str.format()` — the CSS
# braces would blow up. Module stays stdlib-only so the cloud light-build
# (live-matchup) can import it with no extra deps.
# ---------------------------------------------------------------------------

THEME_KEY = "xfp_theme"   # the ONE localStorage key every page reads/writes

# Canonical dark palette — byte-identical to what the static pages already
# ship, EXCEPT --dim is brightened #a89e8a -> #b3a996 (the WCAG contrast fix;
# the smallest uppercase-mono microcopy was borderline). Dark is the default
# (`:root`), so a no-JS / cleared-storage load looks like today.
_DARK = {
    '--bg': '#1a1815', '--panel': '#211e1a', '--stripe': '#1d1b17',
    '--border': '#34302a', '--text': '#f5f1ea', '--dim': '#b3a996',
    '--faint': '#3a352e', '--accent': '#d97757', '--pos': '#7fb069',
    '--neg': '#c1666b', '--warn': '#d4a945', '--info': '#8aa8c4',
    '--mine': '#2a3320', '--mine-hover': '#33401f',
}
# Light palette — derived from index.html's existing light theme, with
# pos/neg/warn/info darkened for readable contrast on the cream --bg.
_LIGHT = {
    '--bg': '#f7f3ec', '--panel': '#fdfaf3', '--stripe': '#f3eee4',
    '--border': '#e3dccb', '--text': '#1a1815', '--dim': '#6e6654',
    '--faint': '#d4ccba', '--accent': '#a8421f', '--pos': '#56753f',
    '--neg': '#9d3540', '--warn': '#8f6a1a', '--info': '#46697f',
    '--mine': '#e7ecd9', '--mine-hover': '#dde5c8',
}


def _vars_block(selector: str, base: dict, extra: dict | None) -> str:
    merged = dict(base)
    if extra:
        merged.update(extra)
    body = ' '.join(f'{k}:{v};' for k, v in merged.items())
    return f'{selector} {{ {body} }}'


def theme_css(extra_dark: dict | None = None, extra_light: dict | None = None) -> str:
    """Canonical theme CSS: dark `:root` default + `html[data-theme="light"]`
    override, plus the shared component styles (theme toggle, methodology
    `details.note` expander, `.colpick` column picker). Drop it into any page's
    `<style>` in place of its hand-rolled `:root` block.

    `extra_dark` / `extra_light` merge page-specific tokens (e.g. xfp_board's
    `--mine`) into the respective palette so the page keeps its extra vars.
    """
    dark = _vars_block(':root', _DARK, extra_dark)
    light = _vars_block('html[data-theme="light"]', _LIGHT, extra_light)
    return f"""
{dark}
{light}
:root {{ color-scheme: dark; }}
html[data-theme="light"] {{ color-scheme: light; }}

.theme-toggle {{ font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.7em;
  text-transform:uppercase; letter-spacing:.12em; color:var(--dim); background:transparent;
  border:1px solid var(--border); border-radius:3px; padding:.35em .7em; cursor:pointer;
  margin-left:.5em; }}
.theme-toggle:hover {{ color:var(--text); background:var(--panel); border-color:var(--accent); }}

details.note {{ background:var(--panel); border:1px solid var(--border); border-radius:6px;
  margin:1em 0; padding:0; max-width:95ch; font-size:.84em; color:var(--dim); line-height:1.6; }}
details.note > summary {{ cursor:pointer; padding:.7em 1.1em; color:var(--text);
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.9em; letter-spacing:.03em;
  user-select:none; }}
details.note[open] > summary {{ border-bottom:1px solid var(--border); }}
details.note .note-body {{ padding:.8em 1.2em 1em; }}
details.note .note-body ul {{ margin:.3em 0; padding-left:1.2em; }}
details.note .note-body li {{ margin:.3em 0; }}
details.note .note-body b {{ color:var(--text); }}

.colpick {{ position:relative; display:inline-block; margin:0 0 .6em;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.72em; }}
.colpick > summary {{ cursor:pointer; color:var(--dim); list-style:none; user-select:none;
  padding:.25em .7em; border:1px solid var(--border); border-radius:3px; display:inline-block;
  text-transform:uppercase; letter-spacing:.1em; }}
.colpick > summary::-webkit-details-marker {{ display:none; }}
.colpick > summary:hover {{ color:var(--text); background:var(--panel); }}
.colpick[open] > summary {{ color:var(--accent); border-color:var(--accent); }}
.colpick-body {{ position:absolute; z-index:30; margin-top:.3em; background:var(--panel);
  border:1px solid var(--border); border-radius:5px; padding:.5em .8em; max-height:60vh;
  overflow:auto; box-shadow:0 6px 22px rgba(0,0,0,.35); min-width:190px; }}
.colpick-body label {{ display:block; padding:.18em 0; color:var(--text); white-space:nowrap;
  cursor:pointer; text-transform:none; letter-spacing:0; }}
.colpick-body input {{ margin-right:.55em; }}
"""


def theme_boot_js() -> str:
    """FOUC-safe inline `<script>` for the `<head>` (place right after
    `</style>`). Applies the saved theme before first paint and defines
    `window.__xfpToggleTheme()` for the toggle button. Absent/garbage key ->
    dark (the `:root` default). All storage access is try/caught.

    Contains none of the matchup publish-guard markers ('<p class="muted">
    error:', '>error: name', 'NameError') — keep it that way if you edit it.
    """
    return (
        "<script>(function(){try{var t=localStorage.getItem('" + THEME_KEY + "');"
        "if(t==='light'){document.documentElement.setAttribute('data-theme','light');}"
        "}catch(e){}"
        "window.__xfpToggleTheme=function(){var el=document.documentElement,"
        "isLight=el.getAttribute('data-theme')==='light';"
        "if(isLight){el.removeAttribute('data-theme');}else{el.setAttribute('data-theme','light');}"
        "try{localStorage.setItem('" + THEME_KEY + "',isLight?'dark':'light');}catch(e){}};})();"
        "</script>"
    )


def theme_toggle_html() -> str:
    """Self-contained toggle button (handler lives in `theme_boot_js`). Uses a
    \\u25d0 glyph via escape so the module source stays ASCII."""
    return ('<button class="theme-toggle" type="button" onclick="__xfpToggleTheme()" '
            'aria-label="Toggle light or dark theme">◐ theme</button>')


def details_note(summary: str, body_html: str, open: bool = False) -> str:
    """A collapsible methodology/legend block — replaces the dense always-open
    `.note` walls of text. `body_html` is already-escaped HTML (typically a
    `<ul>` of bullets)."""
    op = ' open' if open else ''
    return (f'<details class="note"{op}><summary>{summary}</summary>'
            f'<div class="note-body">{body_html}</div></details>')


def column_toggle_js(page_key: str) -> str:
    """Generic, framework-free column show/hide control. Enhances every
    `<table data-cols="ID">` on the page: builds a "Columns" dropdown of
    per-column checkboxes, persists the hidden set to
    `xfp_cols::{page_key}::{ID}`, and hides via `display:none` (cells stay in
    the DOM, so positional-index sort JS keeps working).

    Safety: only single-`<thead>`-row tables are enhanced; any body/footer row
    whose cell count != the header count (colspan/breakdown rows) is skipped.
    First `data-col-lock` columns (default 2 = rank+name) are never hideable.
    Contains none of the matchup publish-guard error markers.
    """
    return (
        "<script>(function(){\n"
        "var PAGE=" + repr(str(page_key)) + ";\n"
        "function keyFor(id){return 'xfp_cols::'+PAGE+'::'+id;}\n"
        "function headRow(t){var h=t.tHead;if(!h||h.rows.length!==1)return null;"
        "return Array.prototype.slice.call(h.rows[0].cells);}\n"
        "function labels(cells){var seen={},out=[];cells.forEach(function(c,i){"
        "var s=(c.textContent||'').trim().replace(/\\s+/g,' ');if(!s)s='(col '+(i+1)+')';"
        "seen[s]=(seen[s]||0)+1;out.push(s+'#'+seen[s]);});return out;}\n"
        "function apply(t,hidden){var cells=headRow(t);if(!cells)return;var n=cells.length;"
        "var lb=labels(cells);var hide={};lb.forEach(function(l,i){if(hidden.indexOf(l)>=0)hide[i]=true;});"
        "Array.prototype.forEach.call(t.querySelectorAll('tr'),function(r){"
        "if(r.cells.length!==n)return;for(var i=0;i<n;i++){r.cells[i].style.display=hide[i]?'none':'';}});}\n"
        "function build(t,idx){var id=t.getAttribute('data-cols')||('t'+idx);"
        "var lock=parseInt(t.getAttribute('data-col-lock')||'2',10);var cells=headRow(t);if(!cells)return;"
        "var lb=labels(cells);var stored=[];try{stored=JSON.parse(localStorage.getItem(keyFor(id))||'[]');}catch(e){}\n"
        "var det=document.createElement('details');det.className='colpick';"
        "var sum=document.createElement('summary');sum.textContent='Columns';det.appendChild(sum);"
        "var box=document.createElement('div');box.className='colpick-body';det.appendChild(box);\n"
        "lb.forEach(function(l,i){if(i<lock)return;var lab=document.createElement('label');"
        "var cb=document.createElement('input');cb.type='checkbox';cb.checked=stored.indexOf(l)<0;"
        "cb.setAttribute('data-lb',l);cb.addEventListener('change',function(){var h=[];"
        "Array.prototype.forEach.call(box.querySelectorAll('input'),function(x){if(!x.checked)h.push(x.getAttribute('data-lb'));});"
        "try{localStorage.setItem(keyFor(id),JSON.stringify(h));}catch(e){}apply(t,h);});"
        "lab.appendChild(cb);lab.appendChild(document.createTextNode(' '+cells[i].textContent.trim()));"
        "box.appendChild(lab);});\n"
        "t.parentNode.insertBefore(det,t);apply(t,stored);}\n"
        "function init(){Array.prototype.forEach.call(document.querySelectorAll('table[data-cols]'),build);}\n"
        "if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',init);}else{init();}\n"
        "})();</script>"
    )
