"""Issue #32 — lag imputation must be self-consistent and rebuild-stable."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts' / 'xfp') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'xfp'))

from enrich_rolling_relievers import lag_imputation_means

THIS_YEAR = 2026


@pytest.fixture()
def multiyr():
    return pd.DataFrame({
        'year':      [2019, 2020, 2024, 2025, THIS_YEAR],
        'g':         [50,   20,   60,   50,   30],
        'sv':        [5,    1,    6,    5,    2],
        'hld':       [10,   2,    12,   10,   5],
        'ip':        [50.0, 20.0, 60.0, 50.0, 30.0],
        'fp':        [100., 40.,  120., 100., 60.],
        'fp_per_g':  [2.0,  2.0,  2.0,  2.0,  2.0],
    })


def test_rate_equals_imputed_counts_quotient(multiyr):
    """A lag-missing row must not tell the ridge two different save rates:
    the imputed rate is exactly imputed_sv / imputed_g (ratio of means),
    not the 13%-lower mean of per-player ratios."""
    mu = lag_imputation_means(multiyr, current_year=THIS_YEAR)
    assert mu['sv_per_g_lag1'] == pytest.approx(mu['sv_lag1'] / mu['g_lag1'])
    assert mu['hld_per_g_lag1'] == pytest.approx(mu['hld_lag1'] / mu['g_lag1'])


def test_short_and_partial_seasons_excluded(multiyr):
    """2020 (60-game season) and the in-progress year must not shape the
    constants — otherwise imputed values drift every nightly rebuild with
    no new information about the player."""
    mu = lag_imputation_means(multiyr, current_year=THIS_YEAR)
    full = multiyr[~multiyr['year'].isin([2020, THIS_YEAR])]
    assert mu['g_lag1'] == pytest.approx(full['g'].mean())
    assert mu['sv_lag1'] == pytest.approx(full['sv'].mean())
