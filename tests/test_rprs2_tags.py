"""Issue #30 — rprs2 tag columns must not collide with rp3's vocabulary.

The 08-18 change published prior-season lag availability under the
data_quality_tag name rp3 uses for CURRENT-season sample size — Jacob Latz
(25 SV in 2026) read as untrustworthy while a 4-appearance arm with a full
2025 read as data_driven, and skill consumers matched none of the values.
"""
import pandas as pd
import pytest

RP3_VOCAB = {'data_driven_full', 'data_driven_thin', 'marcel_no_data', 'marcel_il'}


@pytest.fixture(scope='module')
def df():
    return pd.read_csv('data/outputs/xfp_rprs2_projections.csv')


def test_lag_quality_is_its_own_column(df):
    assert 'lag_quality_tag' in df.columns
    assert set(df['lag_quality_tag'].unique()) <= {'lag_observed', 'lag_imputed'}
    # the lag tag tracks prior-season availability, exactly
    assert (df['role_lag1'].isna() == (df['lag_quality_tag'] == 'lag_imputed')).all()


def test_data_quality_tag_uses_rp3_vocabulary(df):
    assert set(df['data_quality_tag'].dropna().unique()) <= RP3_VOCAB


def test_current_season_workhorse_is_data_driven(df):
    """A reliever with a heavy 2026 workload must never read as untrustworthy."""
    heavy = df[df['g_to'].fillna(0) >= 20]
    assert not heavy.empty
    assert heavy['data_quality_tag'].str.startswith('data_driven').all()
