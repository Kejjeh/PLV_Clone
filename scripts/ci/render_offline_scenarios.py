"""Render the decision-layer surfaces OFFLINE in three data states.

No ESPN, no MLB API, no parquet: every input is a synthetic fixture built
here. The point is to SEE, in rendered HTML, how each surface reports a
player/artifact that is COMPLETE, STALE, or MISSING — and to pin that with
tests/test_offline_scenarios_render.py so the distinction cannot silently
collapse again (the 2026-09-18 audit found a hitter with no rh3 row rendering
exactly like a 60-day-IL player, and a 40-day-old projection labelled
"fresh").

Surfaces exercised (real production functions, synthetic data):
  * matchup team table   — build_matchup_dashboard.render_team_table over
                           project_player() output (badges: ≈ est, ⚠ no proj)
  * playoff-odds card    — build_matchup_dashboard.render_playoff_simulation
                           (fresh / periods-stale / missing payload)
  * roster-audit header  — run_roster_audit.projection_age_note (ages / MISSING)
  * optimizer payload    — run_weekly_optimizer.build_payload unscoreable_drops

Usage:
    python scripts/ci/render_offline_scenarios.py [--out DIR]
Default DIR: docs/audits/offline_scenarios_<today>/ (committed as review
evidence; contains NO real roster data — every name is synthetic).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from html import escape as h
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import build_matchup_dashboard as BMD
import run_roster_audit as RA
import run_weekly_optimizer as WO

TODAY, END = date(2026, 9, 19), date(2026, 9, 27)
NYY = 147
SCHED = {NYY: [{"date": d, "opp_team": "BOS", "is_home": True,
                "opp_probable_id": None, "opp_probable_name": None}
               for d in ("2026-09-19", "2026-09-20", "2026-09-22", "2026-09-24")]}
TS = {"BOS": {"bat_index": 1.02, "pit_index": 0.98}}


class _P:
    """Synthetic espn_api player."""

    def __init__(self, name, pos, inj="ACTIVE", points=0.0):
        self.name, self.position, self.proTeam = name, pos, "NYY"
        self.injuryStatus, self.points, self.playerId = inj, points, 1
        self.lineup_slot = "IL" if inj == "SIXTY_DAY_DL" else "BE"


def _today() -> date:
    return datetime.now(ZoneInfo('America/New_York')).date()


def _fixture(state: str):
    """(lineup, rh3_map, rp3_map, rprs2_map, sp_starts, ages, season_sim) per state."""
    nk = BMD._norm
    rh3 = {nk("Alpha Bat"): {"per_game": 2.6, "sigma": 3.2},
           nk("Beta Bat"): {"per_game": 1.9, "sigma": 3.2}}
    rp3 = {nk("Ace Starter"): {"per_start": 13.0, "per_start_sched": 13.0, "sigma": 5.5}}
    rprs2 = {nk("Closer Arm"): {"xfp_ros": 12.0, "xfp_full_year": 60.0,
                                "role": "closer", "sigma": 3.0, "mlbam": 3}}
    starts = {555: [{"date": "2026-09-20", "opp_team": "BOS", "confirmed": True},
                    {"date": "2026-09-25", "opp_team": "BOS", "confirmed": False}]}
    lineup = [_P("Alpha Bat", "OF", points=4.0), _P("Beta Bat", "2B"),
              _P("Ace Starter", "SP"), _P("Closer Arm", "RP"),
              _P("Hurt Bat", "1B", inj="SIXTY_DAY_DL")]
    ages = {"rh3": 0, "rp3": 0, "rprs2": 0}
    sim = {"generated": "2026-09-18", "period": 23, "sims": 5000,
           "josh": {"team": "Synthetic", "p_playoffs": 0.61, "p_title": 0.12}}
    if state == "stale":
        ages = {"rh3": 0, "rp3": 41, "rprs2": 3}
        sim = {"generated": "2026-07-30", "period": 17, "sims": 5000,
               "josh": {"team": "Synthetic", "p_playoffs": 0.97, "p_title": 0.14}}
    if state == "missing":
        rh3.pop(nk("Beta Bat"))                  # hitter with NO rh3 row
        rprs2 = {}                               # RP with NO rprs2 row
        rp3 = {}                                 # SP absent from rp3 -> ≈ est
        ages = {"rh3": 0, "rp3": None, "rprs2": 0}
        sim = None
    return lineup, rh3, rp3, rprs2, starts, ages, sim


def render(state: str, tmp_dir: Path) -> str:
    lineup, rh3, rp3, rprs2, starts, ages, sim = _fixture(state)
    # route synthetic pitchers without touching the network
    BMD._resolve_pitcher_mlbam = lambda name, **kw: 555 if "Starter" in name else 3
    BMD.detect_pitcher_role = lambda p, mlbam_id=None: "SP" if "Starter" in p.name else "RP"
    proj = {p.name: BMD.project_player(p, SCHED, starts, rh3, rp3, {}, rprs2, TS,
                                       TODAY, END, completed_games={})
            for p in lineup}
    table, _rest, _total = BMD.render_team_table("Synthetic Roster", lineup, 12.0, proj)

    sim_path = tmp_dir / f"season_sim_{state}.json"
    if sim is not None:
        sim_path.write_text(json.dumps(sim), encoding="utf-8")
    BMD.SEASON_SIM_JSON = sim_path
    playoff = BMD.render_playoff_simulation(current_period=23)

    age_note = RA.projection_age_note(ages)

    roster = [{"name": p.name, "mlbam": (None if (state == "missing" and p.name == "Beta Bat") else i + 1),
               "bucket": ("H" if p.position not in ("SP", "RP") else p.position),
               "on_il": p.injuryStatus == "SIXTY_DAY_DL"}
              for i, p in enumerate(lineup)]
    D = {"my_h": {f"id:{r['mlbam']}": {} for r in roster if r["bucket"] == "H" and r["mlbam"]},
         "my_rp": {f"id:{r['mlbam']}": {} for r in roster if r["bucket"] == "RP" and r["mlbam"]},
         "my_sp": [{"event": {"name": r["name"], "mlbam": r["mlbam"]}} for r in roster if r["bucket"] == "SP"]}
    if state == "missing":
        D["my_rp"] = {}                          # the RP never projected -> no draws
    unsc = WO.unscoreable_players(D, roster)
    plan = {"source": "hold", "total_dpwin": 0.0, "pwin_final": 0.5, "moves": []}
    payload = WO.build_payload(plan=plan, res={"rounds": [], "skipped": [], "pairs": []},
                               base_p=0.5, regime="CLOSE", period=23, sims=10, seed=1,
                               cap_remaining=8, wv={}, unscoreable=unsc)
    unsc_html = ("<p class=\"notes\">unscoreable_drops: <b>none</b></p>" if not payload["unscoreable_drops"]
                 else "<p class=\"notes\">unscoreable_drops: <b>"
                      + h(", ".join(f"{u['name']} ({u['bucket']})" for u in payload["unscoreable_drops"]))
                      + "</b> — never offered as drop legs; verify by hand.</p>")

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Offline scenario — {h(state)}</title>
<style>body{{font-family:system-ui;margin:24px;max-width:960px}} table{{border-collapse:collapse}}
td,th{{padding:4px 8px;border-bottom:1px solid #ddd}} .badge{{background:#fde68a;border-radius:4px;padding:0 4px;font-size:.85em}}
.notes{{color:#333}} .muted{{color:#777}} tr.breakdown td{{color:#666;font-size:.9em}}</style></head><body>
<h1>Offline rendered scenario: <code>{h(state)}</code></h1>
<p class="notes">Synthetic fixtures only (no real roster). Rendered by
<code>scripts/ci/render_offline_scenarios.py</code> on {_today().isoformat()} through the
production renderers. State semantics: <b>complete</b> = every input present and current;
<b>stale</b> = inputs present but aged past their thresholds; <b>missing</b> = inputs absent.</p>
<h2>Roster audit header</h2><p class="notes">{h(age_note)}</p>
<h2>Matchup team table</h2>{table}
{playoff}
<h2>Weekly optimizer payload</h2>{unsc_html}
</body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else ROOT / "docs" / "audits" / f"offline_scenarios_{_today().isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    for state in ("complete", "stale", "missing"):
        html = render(state, out)
        (out / f"{state}.html").write_text(html, encoding="utf-8")
        print(f"wrote {out / (state + '.html')}")
    for p in out.glob("season_sim_*.json"):
        p.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
