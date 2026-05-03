"""Regression tests for ESPN connector error handling."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "app"))

import espn_connector  # noqa: E402


def _install_fake_espn(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    """Inject a fake ``espn_api.baseball`` module whose League ctor raises ``exc``."""
    pkg = types.ModuleType("espn_api")
    baseball = types.ModuleType("espn_api.baseball")

    def _league(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise exc

    baseball.League = _league  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "espn_api", pkg)
    monkeypatch.setitem(sys.modules, "espn_api.baseball", baseball)


class TestEspnConnectorErrors:
    def setup_method(self) -> None:
        espn_connector._get_league.cache_clear()

    def teardown_method(self) -> None:
        espn_connector._get_league.cache_clear()

    def test_auth_failures_raise_clear_cookie_refresh_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_fake_espn(monkeypatch, RuntimeError("401 Unauthorized: invalid espn_s2 cookie"))

        with pytest.raises(RuntimeError) as excinfo:
            espn_connector._get_league()

        msg = str(excinfo.value)
        assert "ESPN authentication failed" in msg
        assert "espn_s2" in msg
        assert "SWID" in msg

    def test_generic_failures_raise_connection_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_fake_espn(monkeypatch, ValueError("request timed out"))

        with pytest.raises(RuntimeError) as excinfo:
            espn_connector._get_league()

        assert str(excinfo.value) == "ESPN API connection failed: request timed out"
