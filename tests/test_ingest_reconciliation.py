"""
Tests for --reconcile-days / bounded backfill reconciliation (P1.5).

Tests the manifest rollback logic directly — no real network calls, no disk I/O
beyond a tmp_path manifest file.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from plv_clone.data.ingest_statcast import _apply_reconciliation_window


class TestApplyReconciliationWindow:
    """Unit tests for _apply_reconciliation_window() — the pure manifest logic."""

    def _manifest(self, year_dates: dict) -> dict:
        """Build a minimal manifest dict: {year_str: {last_date: str}}."""
        return {str(yr): {"last_date": str(d), "row_count": 100}
                for yr, d in year_dates.items()}

    def test_no_overlap_leaves_manifest_unchanged(self):
        """Dates well before the reconcile window are not touched."""
        m = self._manifest({2024: date(2024, 4, 1)})
        result = _apply_reconciliation_window(m, end_date=date(2024, 10, 31), reconcile_days=14)
        assert result["2024"]["last_date"] == "2024-04-01"

    def test_last_date_within_window_is_rolled_back(self):
        """last_date inside the window is rolled back to one day before cutoff."""
        end = date(2024, 10, 31)
        reconcile_days = 14
        cutoff = end - timedelta(days=reconcile_days - 1)  # 2024-10-18

        m = self._manifest({2024: date(2024, 10, 25)})
        result = _apply_reconciliation_window(m, end_date=end, reconcile_days=reconcile_days)

        expected = str(cutoff - timedelta(days=1))  # 2024-10-17
        assert result["2024"]["last_date"] == expected

    def test_last_date_exactly_at_cutoff_is_rolled_back(self):
        """last_date == cutoff (boundary) triggers rollback."""
        end = date(2024, 10, 31)
        reconcile_days = 7
        cutoff = end - timedelta(days=reconcile_days - 1)  # 2024-10-25

        m = self._manifest({2024: cutoff})
        result = _apply_reconciliation_window(m, end_date=end, reconcile_days=reconcile_days)

        assert result["2024"]["last_date"] == str(cutoff - timedelta(days=1))

    def test_last_date_one_day_before_cutoff_is_not_rolled_back(self):
        """last_date strictly before cutoff is left alone."""
        end = date(2024, 10, 31)
        reconcile_days = 7
        cutoff = end - timedelta(days=reconcile_days - 1)

        m = self._manifest({2024: cutoff - timedelta(days=1)})
        result = _apply_reconciliation_window(m, end_date=end, reconcile_days=reconcile_days)

        assert result["2024"]["last_date"] == str(cutoff - timedelta(days=1))

    def test_multiple_years_only_affected_year_rolled_back(self):
        """Only the year whose last_date is in the window is touched."""
        end = date(2025, 5, 15)
        reconcile_days = 10
        cutoff = end - timedelta(days=reconcile_days - 1)  # 2025-05-06

        m = self._manifest({2024: date(2024, 10, 31), 2025: date(2025, 5, 10)})
        result = _apply_reconciliation_window(m, end_date=end, reconcile_days=reconcile_days)

        assert result["2024"]["last_date"] == "2024-10-31", "2024 should be untouched"
        assert result["2025"]["last_date"] == str(cutoff - timedelta(days=1))

    def test_missing_last_date_entry_is_preserved(self):
        """A year with no last_date key is passed through unchanged."""
        m = {"2024": {"row_count": 50}}  # no last_date
        result = _apply_reconciliation_window(m, end_date=date(2024, 10, 31), reconcile_days=7)
        assert result["2024"] == {"row_count": 50}

    def test_meta_keys_are_preserved(self):
        """Underscore-prefixed meta keys (e.g. _reconcile_last_run) survive."""
        m = {
            "_reconcile_last_run": "2024-10-01",
            "_reconcile_days": 7,
            "2024": {"last_date": "2024-04-01"},
        }
        result = _apply_reconciliation_window(m, end_date=date(2024, 10, 31), reconcile_days=7)
        assert result["_reconcile_last_run"] == "2024-10-01"
        assert result["_reconcile_days"] == 7

    def test_result_is_a_copy_not_mutating_original(self):
        """Original manifest is not mutated."""
        m = self._manifest({2024: date(2024, 10, 31)})
        original_last = m["2024"]["last_date"]
        _apply_reconciliation_window(m, end_date=date(2024, 10, 31), reconcile_days=7)
        assert m["2024"]["last_date"] == original_last


class TestReconcileMetadataWritten:
    """After a reconcile run, the manifest records reconcile provenance."""

    def test_manifest_records_reconcile_metadata(self, tmp_path, monkeypatch):
        """pull_statcast_range with reconcile_days writes _reconcile_last_run to manifest."""
        from plv_clone.data import ingest_statcast as ing

        # Stub network + disk I/O so the test stays fast
        monkeypatch.setattr(ing, "_pull_chunk_with_retry", lambda *a, **kw: None)
        monkeypatch.setattr(ing, "_load_date_range", lambda *a, **kw: __import__("pandas").DataFrame())

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        ing.pull_statcast_range(
            start_date=date(2024, 10, 25),
            end_date=date(2024, 10, 31),
            raw_dir=raw_dir,
            reconcile_days=7,
            sleep_s=0,
        )

        manifest_path = raw_dir / "manifest.json"
        assert manifest_path.exists(), "manifest.json must be written"
        manifest = json.loads(manifest_path.read_text())
        assert "_reconcile_last_run" in manifest, "manifest must record reconcile run date"
        assert manifest["_reconcile_days"] == 7


class TestReconcileDedup:
    """End-to-end integration: reconcile does not leave duplicate pitch keys."""

    def _make_pitches(self, game_pk: int, n: int, speed: float) -> "pd.DataFrame":
        """Return a minimal pitch DataFrame with PITCH_KEY_COLS + a STATCAST_RAW_COLS field.

        release_speed is in STATCAST_RAW_COLS so it survives _select_available_cols
        and can be used to verify that reconciled rows replaced original rows.
        """
        import pandas as pd
        return pd.DataFrame({
            "game_pk":        [game_pk] * n,
            "at_bat_number":  list(range(1, n + 1)),
            "pitch_number":   [1] * n,
            "pitcher":        [100] * n,
            "batter":         [200] * n,
            "game_date":      [date(2024, 10, 28)] * n,
            "release_speed":  [speed] * n,
        })

    def test_reconcile_does_not_duplicate_pitch_keys(self, tmp_path, monkeypatch):
        """
        Scenario:
          1. Initial pull writes 5 pitches for game_pk=1 on 2024-10-28.
          2. Reconcile re-pulls the same date with updated plv values.
          3. After re-pull, each pitch key appears exactly once and holds
             the new value (keep='last' semantics).
        """
        import pandas as pd
        from plv_clone.data import ingest_statcast as ing
        from plv_clone.data.schemas import PITCH_KEY_COLS

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        original_pitches = self._make_pitches(game_pk=1, n=5, speed=90.0)
        updated_pitches  = self._make_pitches(game_pk=1, n=5, speed=95.5)  # corrected upstream value

        pull_calls = []

        def fake_pull(start, end, retries=3):
            pull_calls.append((start, end))
            if start <= date(2024, 10, 28) <= end:
                # Second call (reconcile) returns updated data
                return updated_pitches if len(pull_calls) > 1 else original_pitches
            return pd.DataFrame()

        monkeypatch.setattr(ing, "_pull_chunk_with_retry", fake_pull)

        # ── Step 1: initial pull ──────────────────────────────────────────
        ing.pull_statcast_range(
            start_date=date(2024, 10, 25),
            end_date=date(2024, 10, 31),
            raw_dir=raw_dir,
            sleep_s=0,
        )

        year_file = raw_dir / "statcast_2024.parquet"
        assert year_file.exists()
        after_initial = pd.read_parquet(year_file)
        assert len(after_initial) == 5

        # ── Step 2: reconcile re-pull ─────────────────────────────────────
        ing.pull_statcast_range(
            start_date=date(2024, 10, 25),
            end_date=date(2024, 10, 31),
            raw_dir=raw_dir,
            reconcile_days=7,
            sleep_s=0,
        )

        after_reconcile = pd.read_parquet(year_file)

        # No duplicate pitch keys
        key_cols = [c for c in PITCH_KEY_COLS if c in after_reconcile.columns]
        n_dupes = after_reconcile.duplicated(subset=key_cols).sum()
        assert n_dupes == 0, f"Found {n_dupes} duplicate pitch key(s) after reconcile"

        # Row count unchanged (dedup removed the originals)
        assert len(after_reconcile) == 5, (
            f"Expected 5 rows after reconcile dedup, got {len(after_reconcile)}"
        )

        # Reconciled values are present (keep='last' → re-pulled data wins).
        # release_speed is in STATCAST_RAW_COLS so it survives _select_available_cols.
        assert (after_reconcile["release_speed"] == 95.5).all(), (
            "Reconciled release_speed values should replace original values"
        )
