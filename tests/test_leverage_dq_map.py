"""One NaN `pitcher` cell must not wipe the whole data_quality_tag map.

Defect (found 2026-09-18): build_state did ``astype(int)`` over the full rp3
`pitcher` column inside a bare ``except`` that returned ``{}`` — so a single
unparsable id silently emptied the marcel_il guard (gotcha #1) for EVERY SP.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "xfp"))

import scripts.xfp.lib.leverage_engine as E  # tracked source: a hard import, never a guard


def test_bad_row_is_skipped_not_fatal(tmp_path):
    p = tmp_path / "rp3.csv"
    pd.DataFrame({"pitcher": [101, None, 103, "x"],
                  "data_quality_tag": ["data_driven_full", "marcel_il",
                                       "marcel_il", "data_driven_thin"]}).to_csv(p, index=False)
    assert E.load_dq_by_mlbam(p) == {101: "data_driven_full", 103: "marcel_il"}


def test_missing_file_is_empty(tmp_path):
    assert E.load_dq_by_mlbam(tmp_path / "nope.csv") == {}
