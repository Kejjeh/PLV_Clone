"""Regression: RP cards must get a real K%/SwStr% sustainability lens.

Pure relievers are absent from sp_multiyr (gs>=10 filter), so the old
sustainability_sp returned INSUFFICIENT_DATA for every closer. sustainability_rp
reads relievers_multiyr and must return a real verdict with the SAME key shape.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "xfp"))
import pandas as pd
from lib.sustainability_lens import sustainability_rp, sustainability_sp


def _a_2026_rp_id():
    rp = pd.read_csv(Path(__file__).resolve().parent.parent
                     / "data/research/xfp_cache/relievers_multiyr_2018_2026.csv")
    return int(rp[rp["year"] == 2026]["pitcher"].dropna().astype(int).iloc[0])


def test_rp_gets_real_verdict_not_insufficient():
    pid = _a_2026_rp_id()
    r = sustainability_rp(pid)
    assert r["bucket"] == "RP"
    assert r["process_verdict"] != "INSUFFICIENT_DATA"
    assert r["k_pct_26"] is not None


def test_rp_return_keys_match_sp_contract():
    # render branch is shared — keys must match sustainability_sp exactly
    rp_keys = set(sustainability_rp(_a_2026_rp_id()).keys())
    sp_keys = set(sustainability_sp(664285).keys())   # Framber (a real SP)
    assert rp_keys == sp_keys
