"""Tests for the PL streamer backfill + backtest harness.

The load-bearing risk here is SILENT SAMPLE LOSS, not a crash. A day whose
date token fails to normalize, or a rank table whose tier banner is not
recognised, simply drops out of the join — and the backtest still prints a
confident-looking result on a smaller sample than you think you have. During
development a date-format leak ('8/6' vs ISO) silently halved the sample and
the run reported success both times.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

from backfill_pl_streamers import iso_date, parse_rank_tables  # noqa: E402


# ── date normalization ───────────────────────────────────────────────────────
# PL day tokens are inconsistent WITHIN one cache: '2026-06-27', '6/28' and
# '7-4' all appear. Anything not normalized to ISO fails the join to actuals
# and drops that whole slate.

def test_iso_date_accepts_every_observed_token_form():
    assert iso_date("2026-06-27") == "2026-06-27"
    assert iso_date("6/28") == "2026-06-28"
    assert iso_date("7-4") == "2026-07-04"
    assert iso_date("8/6") == "2026-08-06"
    assert iso_date("12/1") == "2026-12-01"


def test_iso_date_pads_single_digits():
    """'6/2' must become 2026-06-02, not 2026-6-2 — the join is a string
    compare against boxscore dates, so an unpadded month silently matches
    nothing."""
    assert iso_date("6/2") == "2026-06-02"
    assert iso_date("4/9") == "2026-04-09"


def test_iso_date_refuses_garbage_rather_than_guessing():
    for bad in (None, "", "not-a-date", "tuesday"):
        assert iso_date(bad) is None


def test_iso_date_season_is_parameterised():
    assert iso_date("4/1", season=2025) == "2025-04-01"


# ── rank-table parsing ───────────────────────────────────────────────────────

TIER_ROW = '<tr><td colspan="4">{tier}</td></tr>'
PLAYER_ROW = (
    '<tr><td>{rank}</td>'
    '<td><a class="player-tag" href="https://pitcherlist.com/players/x/">{name}</a></td>'
    '<td>{opp}</td><td>45%</td></tr>'
)


def _table(rows):
    head = "<tr><th>Rank</th><th>Pitcher</th><th>Matchup</th><th>Rostership</th></tr>"
    return "<table>" + head + "".join(rows) + "</table>"


def test_parses_ranks_tiers_and_opponent():
    page = _table([
        TIER_ROW.format(tier="Auto Start"),
        PLAYER_ROW.format(rank=1, name="Drew Rasmussen", opp="@ SEA"),
        PLAYER_ROW.format(rank=2, name="Zack Wheeler", opp="vs TOR"),
        TIER_ROW.format(tier="Do Not Start"),
        PLAYER_ROW.format(rank=3, name="Chase Petty", opp="@ WSH"),
    ])
    (rows,) = parse_rank_tables(page)
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert [r["name"] for r in rows] == ["Drew Rasmussen", "Zack Wheeler", "Chase Petty"]
    # A tier banner applies to every row BELOW it until the next banner.
    assert [r["tier"] for r in rows] == ["Auto-Start", "Auto-Start", "Do Not Start"]
    assert rows[0]["opp"] == "@ SEA"


def test_all_four_tier_banners_are_recognised():
    """An unrecognised banner leaves tier=None, which silently drops those
    pitchers from every tier-level statistic while still counting them in n."""
    page = _table([
        TIER_ROW.format(tier="Auto Start"),
        PLAYER_ROW.format(rank=1, name="A A", opp="vs X"),
        TIER_ROW.format(tier="Probably Start"),
        PLAYER_ROW.format(rank=2, name="B B", opp="vs X"),
        TIER_ROW.format(tier="Questionable Start"),
        PLAYER_ROW.format(rank=3, name="C C", opp="vs X"),
        TIER_ROW.format(tier="Do Not Start"),
        PLAYER_ROW.format(rank=4, name="D D", opp="vs X"),
    ])
    (rows,) = parse_rank_tables(page)
    assert [r["tier"] for r in rows] == [
        "Auto-Start", "Probably Start", "Questionable", "Do Not Start"]
    assert all(r["tier"] is not None for r in rows)


def test_matchup_grid_table_is_not_mistaken_for_ranks():
    """Every edition also carries an offence-strength grid with no player-tag
    anchors. Parsing it as a rank table would inject junk rows."""
    grid = ("<table><tr><th>Top</th><th>Solid</th></tr>"
            "<tr><td>ARI (vL)</td><td>ATL</td></tr></table>")
    assert parse_rank_tables(grid) == []


def test_two_day_tables_stay_separate_and_ordered():
    """Each edition exposes day 1 and day 2 as separate tables (day 3 is
    PL-Pro gated). Table order IS day order — collapsing them would assign
    day 2's ranks to day 1."""
    day1 = _table([TIER_ROW.format(tier="Auto Start"),
                   PLAYER_ROW.format(rank=1, name="Day One Guy", opp="vs A")])
    day2 = _table([TIER_ROW.format(tier="Auto Start"),
                   PLAYER_ROW.format(rank=1, name="Day Two Guy", opp="vs B")])
    tables = parse_rank_tables(day1 + day2)
    assert len(tables) == 2
    assert tables[0][0]["name"] == "Day One Guy"
    assert tables[1][0]["name"] == "Day Two Guy"


def test_accented_names_survive_entity_decoding():
    """PL emits HTML entities; a mangled name fails mlbam resolution and the
    pitcher-day is dropped from the sample."""
    page = _table([TIER_ROW.format(tier="Auto Start"),
                   PLAYER_ROW.format(rank=1, name="Jos&eacute; Soriano", opp="@ PHI")])
    (rows,) = parse_rank_tables(page)
    assert rows[0]["name"] == "José Soriano"


def test_row_without_a_rank_number_is_skipped():
    page = _table([
        TIER_ROW.format(tier="Auto Start"),
        '<tr><td></td><td><a class="player-tag" href="#">No Rank</a></td>'
        '<td>vs X</td><td>1%</td></tr>',
        PLAYER_ROW.format(rank=1, name="Real Guy", opp="vs Y"),
    ])
    (rows,) = parse_rank_tables(page)
    assert [r["name"] for r in rows] == ["Real Guy"]
