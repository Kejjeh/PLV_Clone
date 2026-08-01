"""rp3 projections name completeness — behavioral spec.

The writer attaches player_name by left-merging two name sources (sp_multiyr,
then the MiLB priors). A pitcher present in the rolling substrate but absent from
BOTH sources ships with a null name, and every name-keyed board join then misses
him — worse, the FA snapshot's `_norm(nan) -> ''` collapses all such rows onto a
single empty key, so they overwrite each other rather than merely being skipped.

The names are recoverable from the boxscore store the same nightly chain writes,
so the writer must resolve them from the mlbam id — and must announce any id it
still cannot resolve rather than shipping a blank cell silently.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

from plv_clone.models.xfp import rp3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
from build_fa_snapshot import _norm  # noqa: E402  — the real consumer's key fn


PROJ_CSV = Path(rp3.PROJ_CSV)


def unreachable_rows(csv_path):
    """Rows a name-keyed board join cannot reach, split by failure mode.

    build_fa_snapshot builds its SP lookup as `{_norm(player_name): row}` — a
    plain dict, last writer wins — so a row is lost if its key is empty (a blank
    name; `_norm(nan) == ''`) or if it shares a key with another row. The blank
    case is the worse of the two: it is a silent MERGE, not a conservative miss,
    because every blank row collapses onto the same '' key and overwrites the
    others.

    Returns (blank, colliding) frames.
    """
    df = pd.read_csv(csv_path)
    keys = df["player_name"].map(_norm)
    blank = df[keys == ""]
    colliding = df[(keys != "") & keys.duplicated(keep=False)]
    return blank, colliding


def _store(tmp_path):
    """A boxscore store with two appearances for one pitcher, names differing."""
    p = tmp_path / "boxscore_pitchers.parquet"
    pd.DataFrame([
        {"mlbam_id": 663947, "player_name": "T. Holton", "game_date": "2026-03-26"},
        {"mlbam_id": 663947, "player_name": "Tyler Holton", "game_date": "2026-07-30"},
        {"mlbam_id": 700842, "player_name": "Eduardo Rivera", "game_date": "2026-04-22"},
    ]).to_parquet(p, index=False)
    return p


def test_names_absent_from_both_sources_are_resolved_from_the_mlbam_id(
        tmp_path, monkeypatch):
    """A pitcher the name sources miss still ships with his name; an id nothing
    knows stays blank rather than being guessed at."""
    monkeypatch.setattr(rp3, "BOXSCORE_PITCHERS", _store(tmp_path))
    df = pd.DataFrame({
        "pitcher": [543037, 663947, 700842, 999999],
        "player_name": ["Gerrit Cole", None, None, None],
    })

    out = rp3.fill_missing_player_names(df)

    assert len(out) == len(df)
    named = out.set_index("pitcher")["player_name"]
    assert named[543037] == "Gerrit Cole"        # existing name never overwritten
    assert named[663947] == "Tyler Holton"       # most recent appearance wins
    assert named[700842] == "Eduardo Rivera"
    assert pd.isna(named[999999])                # unresolvable stays null


def test_missing_store_leaves_the_frame_untouched(tmp_path, monkeypatch):
    """The fallback is additive: no store means no names, not a crash."""
    monkeypatch.setattr(rp3, "BOXSCORE_PITCHERS", tmp_path / "absent.parquet")
    df = pd.DataFrame({"pitcher": [1, 2], "player_name": ["A", None]})

    out = rp3.fill_missing_player_names(df)

    assert out["player_name"].tolist()[0] == "A"
    assert pd.isna(out["player_name"].tolist()[1])


def test_a_row_that_stays_unnamed_is_announced_not_shipped_silently(capsys):
    """The writer warns and names the ids it could not resolve."""
    rp3.report_name_completeness(
        pd.DataFrame({"pitcher": [1, 700842], "player_name": ["A", None]}))
    out = capsys.readouterr().out
    assert "WARNING" in out and "700842" in out, out


def test_a_complete_frame_says_nothing(capsys):
    """No warning when every row is named — the signal stays meaningful."""
    rp3.report_name_completeness(
        pd.DataFrame({"pitcher": [1, 2], "player_name": ["A", "B"]}))
    assert capsys.readouterr().out == ""


@pytest.mark.skipif(not PROJ_CSV.exists(), reason="projections not built")
def test_the_whole_shipped_pool_is_reachable_by_a_name_keyed_board():
    """The headline contract: a board joining the starter pool by name reaches
    every projected pitcher.

    Asserted against the artifact that actually ships, because that is what the
    boards read. This is the check the existing collision guard in
    tests/test_no_new_normalizers.py cannot make — it calls `.dropna()` on this
    same file and column first, so the blank-name rows are excluded from the
    collision test by construction and a silent merge survives it.
    """
    blank, colliding = unreachable_rows(PROJ_CSV)

    assert blank.empty, (
        f"{len(blank)} row(s) carry no usable name and collapse onto the same "
        f"empty lookup key, overwriting each other: "
        f"{blank['pitcher'].tolist()}")
    assert colliding.empty, (
        "rows share a normalized name key and silently overwrite each other: "
        f"{colliding[['pitcher', 'player_name']].values.tolist()}")


def test_the_reachability_contract_catches_a_blank_name_pool(tmp_path):
    """The contract is not vacuous: it fails on the shape that shipped before
    the fix — two rows whose blank names collapse onto one key."""
    csv = tmp_path / "rp3.csv"
    pd.DataFrame({
        "pitcher": [543037, 700842, 663947],
        "player_name": ["Gerrit Cole", None, None],
    }).to_csv(csv, index=False)

    blank, colliding = unreachable_rows(csv)

    assert sorted(blank["pitcher"].tolist()) == [663947, 700842]
    assert colliding.empty


@pytest.mark.skipif(not PROJ_CSV.exists(), reason="projections not built")
def test_every_unnamed_row_in_the_shipped_pool_is_now_resolvable():
    """The fallback closes the live gap, not just a synthetic one: every pitcher
    the shipped CSV left unnamed is resolved by the writer's new tier, so the
    next refresh reaches him by name."""
    shipped = pd.read_csv(PROJ_CSV)
    blank = shipped[shipped["player_name"].isna()]
    if blank.empty:
        pytest.skip("shipped pool already complete")
    if not Path(rp3.BOXSCORE_PITCHERS).exists():
        pytest.skip("boxscore store not built")

    healed = rp3.fill_missing_player_names(blank[["pitcher", "player_name"]].copy())

    assert healed["player_name"].notna().all(), (
        "still unresolvable: "
        f"{healed[healed['player_name'].isna()]['pitcher'].tolist()}")


def test_blank_and_whitespace_names_are_backfilled_too(tmp_path, monkeypatch):
    """Review round (2026-08-01): the resolver gated on isna().sum() == 0 and
    filled with fillna(), so a name written as '' or '   ' — what a CSV with
    na_rep='' produces — was never backfilled, while report_name_completeness
    counted exactly those rows as missing and warned about them. The two must
    agree on what 'no name' means."""
    box = pd.DataFrame({
        "mlbam_id": [663947, 700842],
        "player_name": ["Tyler Holton", "Eduardo Rivera"],
        "game_date": pd.to_datetime(["2026-07-30", "2026-07-30"]),
    })
    bp = tmp_path / "boxscore_pitchers.parquet"
    box.to_parquet(bp, index=False)
    monkeypatch.setattr(rp3, "BOXSCORE_PITCHERS", bp)

    valid = pd.DataFrame({
        "pitcher": [663947, 700842, 111],
        "player_name": ["", "   ", "Already Named"],
    })
    out = rp3.fill_missing_player_names(valid)
    assert out.loc[0, "player_name"] == "Tyler Holton"
    assert out.loc[1, "player_name"] == "Eduardo Rivera"
    assert out.loc[2, "player_name"] == "Already Named"   # never overwritten
    assert rp3.report_name_completeness(out) == 0
