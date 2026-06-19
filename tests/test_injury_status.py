"""Tests for the offline injury-status cache (powers triangulate's IL caveat).

The cache is refreshed from ESPN by the daily pipeline; everything else reads it
offline by normalized name. Pure read/lookup is what we lock here.
"""
import json

from scripts.xfp.lib.injury_status import load_il_map, il_status_for
from plv_clone.utils.name_match import _normalize


def test_load_il_map_missing_file_is_empty(tmp_path):
    assert load_il_map(tmp_path / "nope.json") == {}


def test_load_il_map_reads_normalized_keys(tmp_path):
    p = tmp_path / "injury_status.json"
    p.write_text(json.dumps({
        "fetched": "2026-06-19",
        "il": {"Aaron Judge": "IL60", "Ronald Acuna Jr.": "IL10"},
    }), encoding="utf-8")
    m = load_il_map(p)
    # keys normalized via join_key so lookups are order/format independent
    assert m[_normalize("Aaron Judge")] == "IL60"
    assert m[_normalize("Acuna, Ronald")] == "IL10"


def test_il_status_for_lookup(tmp_path):
    m = {_normalize("Aaron Judge"): "IL60"}
    assert il_status_for("Aaron Judge", m) == "IL60"
    assert il_status_for("Judge, Aaron", m) == "IL60"   # order-independent
    assert il_status_for("Shohei Ohtani", m) is None
