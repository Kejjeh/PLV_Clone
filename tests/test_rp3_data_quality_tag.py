"""rp3 data_quality_tag — behavioral spec (issue #13).

`is_on_il_at_split` is a genuine per-(pitcher, split_day) feature, not
exclusive to the synthetic IL-vet fallback rows — it's carried through on
real `prior_source == 'rp3_model'` rows too. Before the fix, ANY row with
`is_on_il_at_split == 1` was tagged `marcel_il` (a suppressed-prior label),
even a pitcher with real accumulated starts and a genuine Ridge-model
prediction who simply happened to be on the IL at his most recent snapshot.
Downstream consumers following the documented rule ("marcel_il arms: rank
by Stuff+, not rp3 — not a real read") would then discard a genuinely
trustworthy projection.
"""
import numpy as np
import pandas as pd

from plv_clone.models.xfp.rp3 import assign_data_quality_tag


def _pool(rows):
    return pd.DataFrame(rows, columns=["gs_to", "prior_source", "is_on_il_at_split"])


def test_currently_il_with_real_starts_is_not_marcel_il():
    """A pitcher with real accumulated starts (gs_to=10) and a genuine
    Ridge-model prediction (prior_source='rp3_model') who is on the IL at
    his most recent snapshot must NOT read as a suppressed marcel_il prior
    — his projection is real, data-driven signal."""
    pool = _pool([(10, "rp3_model", 1)])
    tags = assign_data_quality_tag(pool)
    assert tags.iloc[0] == "data_driven_full"


def test_true_suppressed_prior_still_tags_marcel_il():
    """The genuine suppressed-prior case (zero real starts, IL-vet Marcel
    fallback) must still tag marcel_il — this is the fix's negative case."""
    pool = _pool([(0, "marcel_il", 1)])
    tags = assign_data_quality_tag(pool)
    assert tags.iloc[0] == "marcel_il"


def test_currently_il_with_zero_starts_and_real_prior_source_is_marcel_il():
    """Currently on IL AND no real accumulated signal (gs_to=0) is still a
    suppressed read even if prior_source somehow isn't literally
    'marcel_il' — the OR-with-zero-starts branch of the fix."""
    pool = _pool([(0, "rp3_model", 1)])
    tags = assign_data_quality_tag(pool)
    assert tags.iloc[0] == "marcel_il"


def test_thin_data_currently_il_is_not_marcel_il():
    """A pitcher on IL with SOME real starts (below the full threshold) is
    thin data, not a suppressed prior — he still has a real, if limited,
    2026-informed read."""
    pool = _pool([(5, "rp3_model", 1)])
    tags = assign_data_quality_tag(pool)
    assert tags.iloc[0] == "data_driven_thin"


def test_healthy_pitcher_tags_unaffected_by_fix():
    """Non-IL rows are untouched by the fix — full/thin/no-data buckets by
    gs_to alone, exactly as before."""
    pool = _pool([
        (10, "rp3_model", 0),  # full
        (5, "rp3_model", 0),   # thin
        (0, "rp3_model", 0),   # marcel_no_data
    ])
    tags = assign_data_quality_tag(pool)
    assert list(tags) == ["data_driven_full", "data_driven_thin", "marcel_no_data"]
