"""build_xfp_board_dashboard.py — render the merged xFP boards as one HTML page.

Consumes build_xfp_boards.build_sp_board() + build_hitter_board() and renders a
single self-contained dark-theme page (matching the matchup/profiles dashboard
look) with:
  - SP board: two tables (rank by xFP RoS, rank by xFP Playoffs)
  - 5 hitter buckets (C, 1B/3B, 2B/SS, OF, UTIL) each with xFP_ros + xFP_po cols
  - MINE rows highlighted; talent_prior rows flagged LOW-CONF (badge) + legend
  - header with generation date + methodology note (windows + talent-prior caveat)

Writes to BOTH:
  data/outputs/xfp_board.html
  xfp-model/docs/xfp_board.html   (GitHub Pages — link added to index nav)

Run: python scripts/xfp/build_xfp_board_dashboard.py
"""
from __future__ import annotations
import sys
from datetime import datetime
from html import escape as h
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_xfp_boards as B

OUT = ROOT / "data" / "outputs"
XFP_DOCS = ROOT / "xfp-model" / "docs"

# Top-N caps per table (keeps the page readable; everything is in the CSVs).
SP_TABLE_N = 60
BUCKET_N = {"C": 20, "1B/3B": 25, "2B/SS": 25, "OF": 30, "UTIL": 50}


def _fmt(v, nd=0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if nd == 0:
        return f"{float(v):.0f}"
    return f"{float(v):.{nd}f}"


def _own_cell(r):
    o = r.get("own", "")
    if o == "" or o is None or (isinstance(o, float) and pd.isna(o)):
        return ""
    return f"{float(o):.0f}%"


def _name_cell(r):
    nm = h(str(r["name"]))
    low = str(r.get("src", "")).startswith("talent_prior")   # src may carry "·vol"
    badge = ' <span class="lc">LOW-CONF*</span>' if low else ""
    return f"{nm}{badge}"


def _vol_cell(r, nd=2):
    v = r.get("vol")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return '<td class="muted">—</td>'
    return f'<td class="vol">{float(v):.{nd}f}</td>'


def _row_class(r):
    cls = []
    if r.get("owner") == "MINE":
        cls.append("mine")
    if str(r.get("src", "")).startswith("talent_prior"):
        cls.append("lowconf")
    return " ".join(cls)


def _ret_cell(r):
    ret = r.get("ret", "")
    inj = r.get("inj", "")
    if ret == "" or ret is None or (isinstance(ret, float) and pd.isna(ret)):
        return ""
    label = h(str(ret))
    if inj:
        label = f'<span class="ret">{label}</span>'
    return label


def _topn_plus_mine(df: pd.DataFrame, sortcol: str, n: int) -> pd.DataFrame:
    """Top-N by sortcol, but always include MINE rows even if below the cut
    (so the user never loses sight of their own players — e.g. an IL'd
    talent-prior stash like Judge that ranks below the display threshold)."""
    s = df.sort_values(sortcol, ascending=False, na_position="last")
    top = s.head(n)
    extra = s[(s["owner"] == "MINE") & (~s.index.isin(top.index))]
    if len(extra):
        top = pd.concat([top, extra]).sort_values(sortcol, ascending=False, na_position="last")
    return top


def _sp_table(df: pd.DataFrame, sortcol: str, n: int) -> str:
    v = _topn_plus_mine(df, sortcol, n)
    head = (
        "<tr><th>#</th><th>Pitcher</th><th>Own</th><th>Team</th><th>Own%</th>"
        "<th>per_start</th><th>Stuff+</th><th>Src</th><th>Vol</th><th>Return</th>"
        "<th>xFP RoS</th><th>xFP PO</th></tr>"
    )
    body = []
    for i, (_, r) in enumerate(v.iterrows(), 1):
        owner = "MINE" if r["owner"] == "MINE" else "FA"
        body.append(
            f'<tr class="{_row_class(r)}">'
            f'<td class="muted">{i}</td>'
            f'<td>{_name_cell(r)}</td>'
            f'<td class="own-{owner.lower()}">{owner}</td>'
            f'<td class="muted">{h(str(r.get("team","") or ""))}</td>'
            f'<td class="muted">{_own_cell(r)}</td>'
            f'<td>{_fmt(r.get("per_start"), 2)}</td>'
            f'<td class="muted">{_fmt(r.get("stuff"))}</td>'
            f'<td class="src">{h(str(r.get("src","")))}</td>'
            f'{_vol_cell(r, 3)}'
            f'<td>{_ret_cell(r)}</td>'
            f'<td class="acc">{_fmt(r.get("xfp_ros"))}</td>'
            f'<td>{_fmt(r.get("xfp_po"))}</td>'
            f"</tr>"
        )
    return f"<table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


def _hitter_table(df: pd.DataFrame, n: int) -> str:
    v = _topn_plus_mine(df, "xfp_ros", n)
    head = (
        "<tr><th>#</th><th>Hitter</th><th>Own</th><th>Team</th><th>Own%</th>"
        "<th>per_game</th><th>rh3#</th><th>Src</th><th>Vol</th><th>Return</th>"
        "<th>xFP RoS</th><th>xFP PO</th></tr>"
    )
    body = []
    for i, (_, r) in enumerate(v.iterrows(), 1):
        owner = "MINE" if r["owner"] == "MINE" else "FA"
        rk = r.get("rank")
        rk_s = "—" if rk is None or (isinstance(rk, float) and pd.isna(rk)) else f"{int(rk)}"
        body.append(
            f'<tr class="{_row_class(r)}">'
            f'<td class="muted">{i}</td>'
            f'<td>{_name_cell(r)}</td>'
            f'<td class="own-{owner.lower()}">{owner}</td>'
            f'<td class="muted">{h(str(r.get("team","") or ""))}</td>'
            f'<td class="muted">{_own_cell(r)}</td>'
            f'<td>{_fmt(r.get("per_game"), 2)}</td>'
            f'<td class="muted">{rk_s}</td>'
            f'<td class="src">{h(str(r.get("src","")))}</td>'
            f'{_vol_cell(r, 2)}'
            f'<td>{_ret_cell(r)}</td>'
            f'<td class="acc">{_fmt(r.get("xfp_ros"))}</td>'
            f'<td>{_fmt(r.get("xfp_po"))}</td>'
            f"</tr>"
        )
    return f"<table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


def build_html() -> str:
    from lib.dashboard_chrome import topnav as _topnav  # unified nav owner (item 8)
    inputs = B.fetch_board_inputs()   # ONE roster + ONE free_agents(2000) pull for both boards
    sp = B.build_sp_board(roster=inputs["roster"], fas=inputs["fas"],
                          injury_details=inputs["injury_details"])
    hit = B.build_hitter_board(roster=inputs["roster"], fas=inputs["fas"],
                               injury_details=inputs["injury_details"])
    have = hit[hit["per_game"].notna()].copy()

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_sp_mine = int((sp["owner"] == "MINE").sum())
    n_hit_mine = int((have["owner"] == "MINE").sum())
    sp_src = sp["src"].astype(str)
    hit_src = have["src"].astype(str)
    n_tp_sp = int(sp_src.str.startswith("talent_prior").sum())
    n_tp_hit = int(hit_src.str.startswith("talent_prior").sum())
    n_vol_sp = int(sp_src.str.endswith("·vol").sum())
    n_vol_hit = int(hit_src.str.endswith("·vol").sum())
    n_dock_sp = int(sp_src.str.endswith("·flat↓").sum())
    n_dock_hit = int(hit_src.str.endswith("·flat↓").sum())
    sp_p75 = sp.attrs.get("flat_dock_p75")
    hit_p75 = hit.attrs.get("flat_dock_p75")

    # SP section
    sp_html = (
        f'<h2>Starting Pitchers <span class="totals">'
        f'{len(sp)} ranked · {n_sp_mine} MINE · {n_tp_sp} LOW-CONF · {n_vol_sp} ·vol · {n_dock_sp} ·flat↓</span></h2>'
        f'<h3>Rank by xFP — Rest of Season</h3>'
        f'{_sp_table(sp, "xfp_ros", SP_TABLE_N)}'
        f'<h3>Rank by xFP — Playoffs ({B.PLAYOFF_START.isoformat()}→{B.SEASON_END.isoformat()})</h3>'
        f'{_sp_table(sp, "xfp_po", SP_TABLE_N)}'
    )

    # Hitter buckets
    bucket_html = [
        f'<h2>Hitters <span class="totals">'
        f'{len(have)} ranked · {n_hit_mine} MINE · {n_tp_hit} LOW-CONF · {n_vol_hit} ·vol · {n_dock_hit} ·flat↓</span></h2>'
    ]
    for bkey, label in B.HITTER_BUCKETS:
        sub = have[have["buckets"].apply(lambda s: bkey in s)].copy()
        n_mine = int((sub["owner"] == "MINE").sum())
        n = BUCKET_N.get(bkey, 25)
        bucket_html.append(
            f'<h3>{h(label)} <span class="sub">'
            f'{len(sub)} ranked · {n_mine} MINE</span></h3>'
            f'{_hitter_table(sub, n)}'
        )

    method = (
        "Headline numbers: SP per_start (Stuff+ proj &gt; rp3 data-driven &gt; "
        "rp3 Marcel) and hitter per_game (rh3, MLBAM-id-joined collision-safe). "
        f"<b>xFP RoS</b> projects to season end ({B.SEASON_END.isoformat()}). "
        "<b>Volume-sourced rows (src ·vol)</b> use the validated forward-volume "
        "models (2026-07-09): hitter RoS = per_PA × projected PA/team-game × "
        "team games in window; SP RoS = per_start × projected starts/team-game "
        "× team games. The <b>Vol</b> column shows the per-teamgame number "
        f"(flat equivalents: hitter {B.FLAT_PA_PER_TEAMGAME} PA/tg, SP "
        f"{B.FLAT_GS_PER_TEAMGAME:.3f} GS/tg). Rows without a volume row keep "
        f"the flat rates — SP ≈ per_start × {B.RATE*7:.2f}/wk; hitter ≈ "
        f"per_game × {B.GPW} g/wk. "
        f"<b>xFP PO</b> = the {B.PLAYOFF_START.isoformat()}→{B.SEASON_END.isoformat()} "
        "fantasy-playoff window, availability-scaled. Live IL return dates "
        "(ESPN injury_details) are folded into availability; where no date "
        "exists a coarse status heuristic is used — <b>surgery / season-ending "
        "cases are over-estimated</b>, so treat long-IL rows as ranking aids."
    )
    legend = (
        '<span class="lc">LOW-CONF*</span> = talent-prior fallback (Marcel '
        'if-healthy estimate for players the in-season model can\'t score: '
        'Judge / Greene / Snell-class IL stashes). NOT a real in-season read — '
        'a conviction sorter, not a point forecast. '
        '<span class="own-mine">MINE</span> rows are highlighted. '
        '<span class="src">·vol</span> in Src = RoS/PO totals use the player\'s '
        'projected per-teamgame volume (Vol column) instead of the flat league rate. '
        '<span class="src">·flat↓</span> = IL / prior-only row with no volume '
        'projection, docked to the top-quartile (p75) volume ratio of modeled '
        'rows in its universe'
        + (f' (SP ×{sp_p75:.3f}' if sp_p75 is not None else ' (SP ×—')
        + (f', hitters ×{hit_p75:.3f})' if hit_p75 is not None else ', hitters ×—)')
        + ' so unmodeled stashes aren\'t credited more volume than any modeled player.'
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ligers · Merged xFP Boards</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#1a1815; --panel:#211e1a; --stripe:#1d1b17; --border:#34302a;
  --text:#f5f1ea; --dim:#a89e8a; --faint:#3a352e; --accent:#d97757;
  --pos:#7fb069; --neg:#c1666b; --warn:#d4a945; --mine:#2a3320;
}}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; padding:0; }}
body {{ font-family:'Source Serif 4','Iowan Old Style',Georgia,serif;
       background:var(--bg); color:var(--text); font-size:15px; line-height:1.55; }}
.wrap {{ max-width:1480px; margin:0 auto; padding:0 1.2em 4em 1.2em; }}
header {{ border-bottom:1px solid var(--border); padding:.9em 0 .6em; margin-bottom:1em; }}
h1 {{ color:var(--accent); margin:0; font-size:1.9em; font-weight:700; letter-spacing:.01em; }}
.gen {{ color:var(--dim); font-family:'IBM Plex Mono',monospace; font-size:.8em; margin-top:.2em; }}
h2 {{ color:var(--text); margin-top:2em; font-size:1.4em; font-weight:600;
     border-bottom:1px solid var(--border); padding-bottom:.35em; }}
h2 .totals {{ float:right; font-size:.55em; font-weight:400; color:var(--dim);
             font-family:'IBM Plex Mono',monospace; }}
h3 {{ color:var(--accent); margin-top:1.4em; margin-bottom:.4em; font-size:1.02em;
     font-weight:600; font-family:'IBM Plex Mono',monospace; letter-spacing:.04em; }}
h3 .sub {{ color:var(--dim); font-weight:400; font-size:.85em; margin-left:.5em; }}
.note {{ background:var(--panel); border:1px solid var(--border); border-radius:6px;
        padding:1em 1.2em; margin:1em 0; font-size:.84em; color:var(--dim);
        line-height:1.6; }}
.note b {{ color:var(--text); }}
.legend {{ font-size:.82em; color:var(--dim); margin:.6em 0 0; }}
table {{ border-collapse:collapse; width:100%; margin-bottom:1em;
        font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.82em; }}
th {{ background:var(--panel); padding:.5em .7em; text-align:left;
      border-bottom:1px solid var(--border); border-top:1px solid var(--border);
      font-weight:600; color:var(--dim); text-transform:uppercase;
      font-size:.78em; letter-spacing:.08em; }}
td {{ padding:.42em .7em; border-bottom:1px solid var(--faint);
      font-variant-numeric:tabular-nums; }}
tbody tr:nth-child(even) td {{ background:var(--stripe); }}
tbody tr:hover td {{ background:var(--panel); }}
tbody tr.mine td {{ background:var(--mine); }}
tbody tr.mine:hover td {{ background:#33401f; }}
.muted {{ color:var(--dim); }}
.acc {{ color:var(--accent); font-weight:600; }}
.src {{ color:var(--dim); font-size:.92em; }}
.vol {{ color:var(--pos); }}
.ret {{ color:var(--warn); }}
.own-mine {{ color:var(--pos); font-weight:600; }}
.own-fa {{ color:var(--dim); }}
.lc {{ display:inline-block; padding:0 5px; border-radius:2px; font-size:.78em;
      background:rgba(212,169,69,.20); color:var(--warn); font-weight:600;
      letter-spacing:.04em; }}
.meta {{ color:var(--dim); font-size:.78em; margin-top:2.5em; text-align:center;
        border-top:1px solid var(--border); padding-top:1em; }}
</style></head>
<body><div class="wrap">
<header>
  <h1>Merged xFP Boards</h1>
  {_topnav("xfp_board")}
  <div class="gen">Generated {h(gen)} · MINE + every FA · dual-ranked RoS / Playoffs</div>
</header>
<div class="note">{method}</div>
<div class="legend">{legend}</div>
{sp_html}
{''.join(bucket_html)}
<div class="meta">New York Ligers · plv_clone · engine: scripts/xfp/build_xfp_boards.py · skill: /xfp-board</div>
</div></body></html>
"""


def main():
    html = build_html()
    local = OUT / "xfp_board.html"
    local.write_text(html, encoding="utf-8")
    print(f"wrote {local}")
    if XFP_DOCS.exists():
        target = XFP_DOCS / "xfp_board.html"
        target.write_text(html, encoding="utf-8")
        print(f"wrote {target}")
    else:
        print(f"  ⚠ xfp-model docs not found at {XFP_DOCS} — skipped GH Pages copy")


if __name__ == "__main__":
    main()
