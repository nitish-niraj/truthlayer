"""Startup environment validation (V2 Phase 5).

The settings singleton validates Pydantic fields at construction time, but
that does not catch some common deployment mistakes:

- A test/dummy API key shipping to production
- A key with whitespace, accidental newlines, or the literal "your-key-here"
- NVIDIA URL typos in ``core.llm_client``
- A completely missing LLM client (no key, no client at all)

This module runs once at app startup and logs a structured warning for every
issue it finds. It never raises — the application should still come up in a
degraded state (search/vision surfaces return errors) rather than refuse to
boot, because Render's free tier can take a few seconds to inject env vars.

If the strict mode is desired (refuse to boot on misconfiguration), flip
``STRICT_STARTUP_VALIDATION`` to True via env var.
"""
from __future__ import annotations

import os
import re
from typing import List, Tuple

from core.config import settings
from core.llm_client import BASE_URL
from core.logger import logger


_DUMMY_KEY_PATTERNS = {
    "test-nvidia-key",
    "test-tavily-key",
    "your-key-here",
    "changeme",
    "",
}


def _looks_like_dummy_key(value: str, label: str) -> bool:
    if not value:
        return True
    cleaned = value.strip().lower()
    return cleaned in _DUMMY_KEY_PATTERNS


def _has_whitespace(value: str) -> bool:
    return any(ch.isspace() for ch in value)


def _validate_nvidia_key() -> List[str]:
    issues: List[str] = []
    key = settings.NVIDIA_API_KEY
    if _looks_like_dummy_key(key, "NVIDIA_API_KEY"):
        issues.append(
            "NVIDIA_API_KEY is missing or appears to be a placeholder; vision + verdict calls will fail"
        )
    elif _has_whitespace(key):
        issues.append(
            "NVIDIA_API_KEY contains whitespace; remove accidental newlines/spaces"
        )
    elif len(key) < 20:
        issues.append(
            f"NVIDIA_API_KEY is unexpectedly short ({len(key)} chars); expected an 'nvapi-...' key"
        )
    return issues


def _validate_tavily_key() -> List[str]:
    issues: List[str] = []
    key = settings.TAVILY_API_KEY
    if _looks_like_dummy_key(key, "TAVILY_API_KEY"):
        issues.append(
            "TAVILY_API_KEY is missing or appears to be a placeholder; live evidence search will fail"
        )
    elif _has_whitespace(key):
        issues.append(
            "TAVILY_API_KEY contains whitespace; remove accidental newlines/spaces"
        )
    elif not re.match(r"^tvly-[A-Za-z0-9_-]+$", key) and len(key) < 20:
        issues.append(
            "TAVILY_API_KEY does not look like a Tavily key (expected 'tvly-...')"
        )
    return issues


def _validate_llm_endpoint() -> List[str]:
    issues: List[str] = []
    if not BASE_URL.startswith("https://"):
        issues.append(
            f"NVIDIA base URL is not HTTPS ({BASE_URL!r}); production traffic must be encrypted"
        )
    if "integrate.api.nvidia.com" not in BASE_URL and "localhost" not in BASE_URL:
        issues.append(
            f"NVIDIA base URL looks unusual ({BASE_URL!r}); expected the NVIDIA Inference API"
        )
    return issues


def _validate_frontend_url() -> List[str]:
    issues: List[str] = []
    url = settings.FRONTEND_URL
    if not url:
        issues.append("FRONTEND_URL is empty; CORS will reject every browser request")
    elif not url.startswith(("http://", "https://")):
        issues.append(
            f"FRONTEND_URL is not a valid URL ({url!r}); CORS will reject every browser request"
        )
    return issues


def _validate_numeric_limits() -> List[str]:
    issues: List[str] = []
    if settings.MAX_CLAIMS <= 0 or settings.MAX_CLAIMS > 100:
        issues.append(
            f"MAX_CLAIMS={settings.MAX_CLAIMS} is out of expected range (1..100)"
        )
    if settings.MAX_FILE_SIZE_MB <= 0 or settings.MAX_FILE_SIZE_MB > 50:
        issues.append(
            f"MAX_FILE_SIZE_MB={settings.MAX_FILE_SIZE_MB} is out of expected range (1..50)"
        )
    if settings.MAX_IMAGE_SIZE_MB <= 0 or settings.MAX_IMAGE_SIZE_MB > 25:
        issues.append(
            f"MAX_IMAGE_SIZE_MB={settings.MAX_IMAGE_SIZE_MB} is out of expected range (1..25)"
        )
    if settings.VERIFY_HARD_TIMEOUT_SECONDS <= 0:
        issues.append(
            f"VERIFY_HARD_TIMEOUT_SECONDS={settings.VERIFY_HARD_TIMEOUT_SECONDS} must be > 0"
        )
    return issues


def collect_startup_issues() -> List[str]:
    """Return a flat list of human-readable startup issues.

    Order matters: NVIDIA key first, then Tavily, then endpoint, then
    frontend, then numeric limits. The list is empty when everything is
    healthy.
    """
    return (
        _validate_nvidia_key()
        + _validate_tavily_key()
        + _validate_llm_endpoint()
        + _validate_frontend_url()
        + _validate_numeric_limits()
    )


def run_startup_validation(raise_on_error: bool | None = None) -> Tuple[bool, List[str]]:
    """Run the startup checks and log the result. Returns ``(ok, issues)``.

    ``raise_on_error`` is read from the env var
    ``STRICT_STARTUP_VALIDATION`` when not provided explicitly:
    set it to "1" / "true" to abort the process if any issue is found.
    Useful for CI pipelines that should never pass with a broken
    configuration.
    """
    if raise_on_error is None:
        strict = os.getenv("STRICT_STARTUP_VALIDATION", "").lower() in {"1", "true", "yes"}
    else:
        strict = raise_on_error

    issues = collect_startup_issues()
    if not issues:
        logger.info("STARTUP VALIDATION | ok | all env vars and limits look healthy")
        return True, []

    for issue in issues:
        logger.warning("STARTUP VALIDATION | %s", issue)
    if strict:
        raise RuntimeError(
            "Startup validation failed (STRICT_STARTUP_VALIDATION=1): "
            + "; ".join(issues)
        )
    return False, issues


__all__ = ["collect_startup_issues", "run_startup_validation"]
