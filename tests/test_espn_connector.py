"""Regression tests for ESPN connector error handling."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "app"))

import espn_connector  # noqa: E402
from plv_clone import espn as plv_espn  # noqa: E402


def _fake_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the module real-looking credentials.

    The credential constants are bound at import time, so a bare env var will
    not reach them. Without this these tests only exercise the error-mapping
    path on a machine that happens to have a populated `.env` — everywhere
    else `_get_league` short-circuits on "credentials missing" and the
    assertions test nothing. (Found 2026-08-27.)
    """
    monkeypatch.setattr(plv_espn, "LEAGUE_ID", 123456)
    monkeypatch.setattr(plv_espn, "SWID", "{FAKE-SWID}")
    monkeypatch.setattr(plv_espn, "ESPN_S2", "FAKE_S2")


def _install_fake_espn(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    """Inject a fake ``espn_api.baseball`` module whose League ctor raises ``exc``."""
    _fake_creds(monkeypatch)
    pkg = types.ModuleType("espn_api")
    baseball = types.ModuleType("espn_api.baseball")

    calls = []

    def _league(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        raise exc

    baseball.League = _league  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "espn_api", pkg)
    monkeypatch.setitem(sys.modules, "espn_api.baseball", baseball)
    return calls


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
        monkeypatch.setattr("time.sleep", lambda _s: None)

        with pytest.raises(RuntimeError) as excinfo:
            espn_connector._get_league()

        assert str(excinfo.value) == "ESPN API connection failed: request timed out"

    def test_missing_credentials_reported_before_any_request(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The credentials check must precede the network path."""
        calls = _install_fake_espn(monkeypatch, ValueError("should not be reached"))
        monkeypatch.setattr(plv_espn, "ESPN_S2", "")

        with pytest.raises(RuntimeError, match="ESPN credentials missing"):
            espn_connector._get_league()
        assert calls == []

    def test_auth_failure_is_not_retried(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An expired cookie is permanent — retrying only delays the message.

        The constructor retries 3x with 2s/5s backoff for transient ESPN 5xx.
        Auth failures used to ride that path too, so the single most common
        ESPN error (stale cookies) cost 7s of sleep and two extra doomed
        requests before surfacing. (Fixed 2026-08-27.)
        """
        calls = _install_fake_espn(
            monkeypatch, RuntimeError("401 Unauthorized: invalid espn_s2 cookie")
        )
        slept = []
        monkeypatch.setattr("time.sleep", slept.append)

        with pytest.raises(RuntimeError, match="ESPN authentication failed"):
            espn_connector._get_league()

        assert len(calls) == 1, f"auth failure retried {len(calls)}x"
        assert slept == [], f"slept {slept} on a permanent failure"

    def test_transient_failure_is_still_retried(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The 5xx retry the backoff was built for must survive the fix."""
        calls = _install_fake_espn(monkeypatch, RuntimeError("502 Bad Gateway"))
        slept = []
        monkeypatch.setattr("time.sleep", slept.append)

        with pytest.raises(RuntimeError, match="ESPN API connection failed"):
            espn_connector._get_league()

        assert len(calls) == 3, f"expected 3 attempts, got {len(calls)}"
        assert slept == [2, 5]
