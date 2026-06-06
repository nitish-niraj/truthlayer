"""Tests for V2 Phase 5 production hardening: health endpoint, startup
validation, and structured error helpers."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core import startup
from utils.error_responses import error_response, format_http_exception_detail


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_dependencies():
    client = TestClient(__import__("main", fromlist=["app"]).app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    # Required keys per Phase 5 spec
    assert "status" in body
    assert "version" in body
    assert "vision" in body
    assert "search" in body
    assert body["vision"] in {"available", "unconfigured"}
    assert body["search"] in {"available", "unconfigured"}
    # Status is the union of both: ok if both available, else degraded.
    if body["vision"] == "available" and body["search"] == "available":
        assert body["status"] == "ok"
    else:
        assert body["status"] == "degraded"


def test_health_reports_unconfigured_when_keys_are_dummy(monkeypatch):
    """When the test fixtures inject dummy keys, /api/health should report
    the dependencies as unconfigured (not crashed).
    """
    client = TestClient(__import__("main", fromlist=["app"]).app)
    response = client.get("/api/health")
    body = response.json()
    # The conftest.py sets NVIDIA_API_KEY='test-nvidia-key' and
    # TAVILY_API_KEY='test-tavily-key' for the test env. Both should be
    # flagged as unconfigured without crashing the endpoint.
    assert body["status"] == "degraded"
    assert body["vision"] == "unconfigured"
    assert body["search"] == "unconfigured"
    # Health is advisory — endpoint still returns 200
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------


def test_collect_startup_issues_empty_when_keys_look_real(monkeypatch):
    """Fake real-looking keys; expect zero issues."""
    monkeypatch.setattr(
        startup.settings,
        "NVIDIA_API_KEY",
        "nvapi-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    )
    monkeypatch.setattr(
        startup.settings,
        "TAVILY_API_KEY",
        "tvly-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    )
    monkeypatch.setattr(startup.settings, "FRONTEND_URL", "https://truthlayer.app")
    issues = startup.collect_startup_issues()
    assert issues == []


def test_collect_startup_issues_flags_dummy_nvidia_key(monkeypatch):
    monkeypatch.setattr(startup.settings, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(
        startup.settings, "TAVILY_API_KEY", "tvly-abcdefghijklmnopqrstuvwxyz012345"
    )
    issues = startup.collect_startup_issues()
    assert any("NVIDIA_API_KEY" in i for i in issues)


def test_collect_startup_issues_flags_dummy_tavily_key(monkeypatch):
    monkeypatch.setattr(
        startup.settings,
        "NVIDIA_API_KEY",
        "nvapi-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    )
    monkeypatch.setattr(startup.settings, "TAVILY_API_KEY", "")
    issues = startup.collect_startup_issues()
    assert any("TAVILY_API_KEY" in i for i in issues)


def test_collect_startup_issues_flags_whitespace_in_key(monkeypatch):
    monkeypatch.setattr(
        startup.settings,
        "NVIDIA_API_KEY",
        "nvapi-abc def\nghi",
    )
    issues = startup.collect_startup_issues()
    assert any("whitespace" in i.lower() for i in issues)


def test_collect_startup_issues_flags_short_nvidia_key(monkeypatch):
    monkeypatch.setattr(startup.settings, "NVIDIA_API_KEY", "nvapi-x")
    issues = startup.collect_startup_issues()
    assert any("short" in i for i in issues)


def test_collect_startup_issues_flags_bad_frontend_url(monkeypatch):
    monkeypatch.setattr(startup.settings, "FRONTEND_URL", "")
    issues = startup.collect_startup_issues()
    assert any("FRONTEND_URL" in i for i in issues)


def test_collect_startup_issues_flags_out_of_range_limits(monkeypatch):
    monkeypatch.setattr(startup.settings, "MAX_CLAIMS", 0)
    issues = startup.collect_startup_issues()
    assert any("MAX_CLAIMS" in i for i in issues)


def test_run_startup_validation_logs_warnings(monkeypatch, caplog):
    """With bad env, validation logs each issue as a warning and does not
    raise (non-strict default)."""
    monkeypatch.setattr(startup.settings, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(startup.settings, "TAVILY_API_KEY", "")
    monkeypatch.setattr(startup.settings, "FRONTEND_URL", "")

    import logging
    with caplog.at_level(logging.INFO, logger="truthlayer"):
        ok, issues = startup.run_startup_validation(raise_on_error=False)

    assert ok is False
    assert len(issues) >= 3
    text = " | ".join(r.message for r in caplog.records)
    assert "STARTUP VALIDATION" in text
    assert "NVIDIA_API_KEY" in text
    assert "TAVILY_API_KEY" in text
    assert "FRONTEND_URL" in text


def test_run_startup_validation_strict_raises(monkeypatch):
    monkeypatch.setattr(startup.settings, "NVIDIA_API_KEY", "")
    with pytest.raises(RuntimeError) as exc:
        startup.run_startup_validation(raise_on_error=True)
    assert "Startup validation failed" in str(exc.value)


def test_run_startup_validation_strict_via_env(monkeypatch):
    """STRICT_STARTUP_VALIDATION=1 in the env forces strict mode."""
    monkeypatch.setenv("STRICT_STARTUP_VALIDATION", "1")
    monkeypatch.setattr(startup.settings, "NVIDIA_API_KEY", "")
    with pytest.raises(RuntimeError):
        startup.run_startup_validation()


# ---------------------------------------------------------------------------
# Structured error helpers
# ---------------------------------------------------------------------------


def test_error_response_builds_structured_detail():
    exc = error_response(
        status_code=413,
        error="file_too_large",
        detail="File must be under 5MB",
    )
    assert exc.status_code == 413
    assert exc.detail == {
        "error": "file_too_large",
        "detail": "File must be under 5MB",
    }


def test_error_response_optional_request_id_and_extra():
    exc = error_response(
        status_code=503,
        error="vision_unavailable",
        detail="Vision service unavailable",
        request_id="req-abc",
        extra={"retry_after_seconds": 30},
    )
    assert exc.detail["request_id"] == "req-abc"
    assert exc.detail["retry_after_seconds"] == 30


def test_format_http_exception_detail_passthrough_for_strings():
    assert format_http_exception_detail("oops") == {"detail": "oops"}


def test_format_http_exception_detail_passthrough_for_dicts():
    d = {"error": "x", "detail": "y"}
    assert format_http_exception_detail(d) is d
