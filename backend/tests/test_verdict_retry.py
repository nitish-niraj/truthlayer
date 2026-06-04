"""Unit tests for the verdict service retry + rate-limit logic (Phase 11.5)."""

import asyncio
import json
from unittest.mock import MagicMock

import openai

from models.schemas import ClaimType, ExtractedClaim, SearchResult
from services import verdict_service
from services.verdict_service import (
    RATE_LIMITED_FALLBACK,
    SAFE_FALLBACK,
    SEARCH_FAILED_FALLBACK,
    generate_verdict,
)
from services.search_service import SearchStatus


def _claim(text: str = "OpenAI was founded in 2020") -> ExtractedClaim:
    return ExtractedClaim(claim=text, type=ClaimType.date, source_sentence=text + ".")


def _evidence() -> list[SearchResult]:
    return [SearchResult(title="T", url="https://www.reuters.com/x", content="C")]


def _make_429_error() -> openai.RateLimitError:
    """Build a synthetic RateLimitError matching the shape openai SDK raises."""
    import httpx

    response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions"),
    )
    body = {"status": 429, "title": "Too Many Requests"}
    return openai.RateLimitError("rate limited", response=response, body=body)


def _make_500_error() -> openai.InternalServerError:
    import httpx

    response = httpx.Response(
        status_code=500,
        request=httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions"),
    )
    body = {"status": 500, "title": "Internal Server Error"}
    return openai.InternalServerError("server error", response=response, body=body)


def _make_connection_error() -> openai.APIConnectionError:
    import httpx

    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return openai.APIConnectionError(message="connection reset", request=request)


def _patch_llm_responses(monkeypatch, responses: list) -> MagicMock:
    """Set up the LLM mock to return/side_effect in order across calls.

    Each entry is either a content string (return a successful response) or
    an Exception instance (raise it from chat.completions.create).
    """
    mock_client = MagicMock()

    def maybe_raise_or_return(*args, **kwargs):
        if not responses:
            raise RuntimeError("LLM called more times than expected")
        nxt = responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        mock_response = MagicMock()
        mock_response.choices[0].message.content = nxt
        return mock_response

    mock_client.chat.completions.create.side_effect = maybe_raise_or_return
    monkeypatch.setattr(verdict_service, "get_llm_client", lambda: mock_client)
    return mock_client


def _patch_sleep_zero(monkeypatch):
    """Replace ``asyncio.sleep`` with a near-zero version for retry tests.

    Capture the real sleep at call time so we don't recurse into the patched
    function (which would happen if the lambda called ``asyncio.sleep`` by
    name — that's now itself).
    """
    real_sleep = asyncio.sleep

    async def fast_sleep(*_args, **_kwargs):
        await real_sleep(0)

    monkeypatch.setattr(verdict_service.asyncio, "sleep", fast_sleep)


# ---------------------------------------------------------------------------
# Search-failed -> inaccurate (not false)
# ---------------------------------------------------------------------------


def test_search_failed_returns_inaccurate_fallback(monkeypatch):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    monkeypatch.setattr(verdict_service, "get_llm_client", lambda: mock_client)

    result = asyncio.run(
        generate_verdict(_claim(), [], search_status=SearchStatus.FAILED)
    )

    assert result.verdict.value == "inaccurate"
    assert "search providers" in result.explanation.lower()
    # LLM must NOT be called when the search itself failed
    mock_client.chat.completions.create.assert_not_called()


def test_search_failed_matches_search_failed_fallback_constant():
    assert SEARCH_FAILED_FALLBACK.verdict.value == "inaccurate"
    assert SEARCH_FAILED_FALLBACK.correct_fact == ""


# ---------------------------------------------------------------------------
# Rate-limit retry success
# ---------------------------------------------------------------------------


def test_rate_limit_then_success(monkeypatch):
    payload = json.dumps(
        {
            "verdict": "verified",
            "explanation": "ok",
            "correct_fact": "",
            "source_url": "https://www.reuters.com/x",
        }
    )
    _patch_llm_responses(monkeypatch, [_make_429_error(), payload])

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result.verdict.value == "verified"


# ---------------------------------------------------------------------------
# Rate-limit retries exhausted -> inaccurate rate-limited fallback
# ---------------------------------------------------------------------------


def test_rate_limit_exhausted_returns_inaccurate(monkeypatch):
    # Backoff is 1s + 2s + 4s = 7s. Patch the sleep to be near-zero.
    _patch_sleep_zero(monkeypatch)
    _patch_llm_responses(
        monkeypatch,
        [_make_429_error(), _make_429_error(), _make_429_error()],
    )

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result.verdict.value == "inaccurate"
    assert "temporarily unavailable" in result.explanation.lower()
    assert result is RATE_LIMITED_FALLBACK


# ---------------------------------------------------------------------------
# 5xx also retried
# ---------------------------------------------------------------------------


def test_5xx_then_success(monkeypatch):
    payload = json.dumps(
        {
            "verdict": "false",
            "explanation": "contradicted",
            "correct_fact": "fix",
            "source_url": "https://www.reuters.com/x",
        }
    )
    _patch_llm_responses(monkeypatch, [_make_500_error(), payload])

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result.verdict.value == "false"


def test_5xx_exhausted_returns_safe_fallback(monkeypatch):
    # No 429s, just 5xx exhaustion. Should be SAFE_FALLBACK (false), not rate-limited.
    _patch_sleep_zero(monkeypatch)
    _patch_llm_responses(
        monkeypatch,
        [_make_500_error(), _make_500_error(), _make_500_error()],
    )

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result is SAFE_FALLBACK
    assert result.verdict.value == "false"


# ---------------------------------------------------------------------------
# Non-retryable error path is unchanged
# ---------------------------------------------------------------------------


def test_non_retryable_error_returns_safe_fallback(monkeypatch):
    _patch_sleep_zero(monkeypatch)
    _patch_llm_responses(monkeypatch, [ValueError("bad payload")])

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result is SAFE_FALLBACK


# ---------------------------------------------------------------------------
# Connection error is retryable
# ---------------------------------------------------------------------------


def test_connection_error_retried(monkeypatch):
    payload = json.dumps(
        {
            "verdict": "verified",
            "explanation": "ok",
            "correct_fact": "",
            "source_url": "https://www.reuters.com/x",
        }
    )
    _patch_llm_responses(
        monkeypatch,
        [_make_connection_error(), payload],
    )

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result.verdict.value == "verified"


# ---------------------------------------------------------------------------
# Metrics recording
# ---------------------------------------------------------------------------


def test_metrics_records_429_count(monkeypatch):
    from core.metrics import RunMetrics

    payload = json.dumps(
        {
            "verdict": "verified",
            "explanation": "ok",
            "correct_fact": "",
            "source_url": "https://www.reuters.com/x",
        }
    )
    _patch_llm_responses(monkeypatch, [_make_429_error(), payload])
    metrics = RunMetrics(filename="x.pdf")

    asyncio.run(generate_verdict(_claim(), _evidence(), metrics=metrics))

    assert metrics.rate_limit_count == 1
    assert metrics.llm_failures == 0


def test_metrics_records_llm_failure_on_exhaustion(monkeypatch):
    from core.metrics import RunMetrics

    _patch_sleep_zero(monkeypatch)
    _patch_llm_responses(
        monkeypatch,
        [_make_500_error(), _make_500_error(), _make_500_error()],
    )
    metrics = RunMetrics(filename="x.pdf")

    asyncio.run(generate_verdict(_claim(), _evidence(), metrics=metrics))

    assert metrics.llm_failures == 1
    assert metrics.rate_limit_count == 0
