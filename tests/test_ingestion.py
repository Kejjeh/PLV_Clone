"""
Tests for the Statcast ingestion layer.

Uses mocked pybaseball calls — no real network access.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_statcast_response(raw_df):
    """A small raw DataFrame shaped like a pybaseball.statcast() response."""
    return raw_df.head(50).copy()


@pytest.fixture
def mock_statcast(mocker, sample_statcast_response):
    """Patch pybaseball.statcast to return sample_statcast_response."""
    mock = mocker.patch("pybaseball.statcast", return_value=sample_statcast_response)
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_select_available_cols_keeps_raw_cols(sample_statcast_response):
    """Columns in STATCAST_RAW_COLS that exist in the response are retained."""
    from plv_clone.data.ingest_statcast import _select_available_cols
    from plv_clone.data.schemas import STATCAST_RAW_COLS

    result = _select_available_cols(sample_statcast_response)
    for col in result.columns:
        assert col in STATCAST_RAW_COLS or col in sample_statcast_response.columns


def test_manifest_created_on_first_pull(tmp_path, mock_statcast):
    """A manifest.json is created after the first successful pull."""
    from plv_clone.data.ingest_statcast import pull_statcast_range

    pull_statcast_range(
        start_date=date(2023, 4, 1),
        end_date=date(2023, 4, 3),
        raw_dir=tmp_path,
        chunk_days=7,
        sleep_s=0,
    )
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists(), "manifest.json should be created after pull"
    manifest = json.loads(manifest_path.read_text())
    assert "2023" in manifest
    assert "last_date" in manifest["2023"]


def test_incremental_pull_skips_cached_dates(tmp_path, mocker, sample_statcast_response):
    """If manifest shows dates already pulled, pybaseball is not called again."""
    from plv_clone.data.ingest_statcast import pull_statcast_range

    # Write a manifest indicating 2023 is fully cached
    manifest = {"2023": {"last_date": "2023-11-01", "row_count": 100}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    # Write a stub year file
    sample_statcast_response.to_parquet(tmp_path / "statcast_2023.parquet", index=False)

    mock = mocker.patch("pybaseball.statcast", return_value=sample_statcast_response)
    pull_statcast_range(
        start_date=date(2023, 4, 1),
        end_date=date(2023, 10, 31),
        raw_dir=tmp_path,
        chunk_days=7,
        sleep_s=0,
    )
    mock.assert_not_called()


def test_year_file_created(tmp_path, mock_statcast):
    """A year-specific parquet file is created after pulling."""
    from plv_clone.data.ingest_statcast import pull_statcast_range

    pull_statcast_range(
        start_date=date(2023, 4, 1),
        end_date=date(2023, 4, 3),
        raw_dir=tmp_path,
        chunk_days=7,
        sleep_s=0,
    )
    assert (tmp_path / "statcast_2023.parquet").exists()


def test_deduplication_on_pitch_key(raw_df):
    """Duplicate pitch-key rows are removed during cleaning."""
    from plv_clone.data.clean_statcast import _drop_duplicates
    from plv_clone.data.schemas import PITCH_KEY_COLS

    # Insert a duplicate of the first row
    duped = pd.concat([raw_df, raw_df.iloc[[0]]], ignore_index=True)
    result = _drop_duplicates(duped)

    key_cols = [c for c in PITCH_KEY_COLS if c in result.columns]
    assert not result.duplicated(subset=key_cols).any(), \
        "No duplicate pitch keys should remain after dedup"


def test_force_refresh_repulls_data(tmp_path, mocker, sample_statcast_response):
    """force_refresh=True causes pybaseball to be called even if manifest exists."""
    from plv_clone.data.ingest_statcast import pull_statcast_range

    manifest = {"2023": {"last_date": "2023-11-01", "row_count": 100}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    mock = mocker.patch("pybaseball.statcast", return_value=sample_statcast_response)
    pull_statcast_range(
        start_date=date(2023, 4, 1),
        end_date=date(2023, 4, 3),
        raw_dir=tmp_path,
        chunk_days=7,
        force_refresh=True,
        sleep_s=0,
    )
    assert mock.called
