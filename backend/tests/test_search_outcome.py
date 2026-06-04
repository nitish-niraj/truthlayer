"""Unit tests for the search service's outcome-aware path (Phase 11.5)
and Tavily retry/backoff behavior (Phase 11.6).
"""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from models.schemas import ClaimType, ExtractedClaim
from services import search_service
from services.search_service import (
    SEARCH_MAX_ATTEMPTS,
    SearchOutcome,
    SearchStatus,
    search_claim_with_status,
)


def _claim(text: str = "Apple revenue reached $394B in 2022") -> ExtractedClaim:
    return ExtractedClaim(claim=text, type=ClaimType.financial, source_sentence=text + ".")


def _make_raw(title="T", url="https://example.com", content="C") -> dict:
    return {"title": title, "url": url, "content": content}


def _patch_tavily(monkeypatch, return_value=None, side_effect=None) -> MagicMock:
    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.search.side_effect = side_effect
    else:
        mock_client.search.return_value = return_value or {"results": []}
    monkeypatch.setattr(search_service, "get_tavily_client", lambda: mock_client)
    return mock_client


@pytest.fixture
def fast_sleep(monkeypatch):
    """Skip the retry backoff in every test that exercises a failing path.

    The real `_search_sleep` would block for 1s + 2s + 4s = 7s on a full
    retry sequence, which makes tests painfully slow. We patch it to a
    no-op and capture the requested backoff values in `sleep_calls` so
    individual tests can still assert the schedule.
    """
    sleep_calls: list[float] = []
    monkeypatch.setattr(search_service, "_search_sleep", lambda s: sleep_calls.append(s))
    return sleep_calls


# ---------------------------------------------------------------------------
# search_claim_with_status: status mapping
# ---------------------------------------------------------------------------


def test_with_status_returns_success_when_results_present(monkeypatch):
    raws = [_make_raw(url="https://www.reuters.com/x", content="ok")]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.SUCCESS
    assert len(outcome.results) == 1
    assert outcome.ok is True


def test_with_status_returns_empty_when_no_results(monkeypatch):
    _patch_tavily(monkeypatch, return_value={"results": []})

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.EMPTY
    assert outcome.results == []
    assert outcome.ok is False


def test_with_status_returns_empty_when_all_results_filtered(monkeypatch):
    # Missing title -> filtered out
    raws = [_make_raw(title=""), _make_raw(url="", content="x")]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.EMPTY
    assert outcome.results == []


def test_with_status_returns_failed_on_runtime_error(monkeypatch, fast_sleep):
    _patch_tavily(monkeypatch, side_effect=RuntimeError("Tavily down"))

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.FAILED
    assert outcome.results == []
    # Non-transient errors must not be retried.
    assert fast_sleep == []


def test_with_status_returns_failed_on_timeout(monkeypatch, fast_sleep):
    mock = _patch_tavily(monkeypatch, side_effect=RequestsTimeout("read timed out"))

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.FAILED
    # Retried until MAX_ATTEMPTS was reached.
    assert mock.search.call_count == SEARCH_MAX_ATTEMPTS
    # One sleep per retry (i.e. attempts - 1).
    assert len(fast_sleep) == SEARCH_MAX_ATTEMPTS - 1
    # Schedule is 1s, 2s, 4s.
    assert fast_sleep == [1.0, 2.0]


def test_with_status_returns_failed_on_connection_error(monkeypatch, fast_sleep):
    mock = _patch_tavily(
        monkeypatch, side_effect=RequestsConnectionError("ConnectionResetError")
    )

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.FAILED
    assert mock.search.call_count == SEARCH_MAX_ATTEMPTS
    assert len(fast_sleep) == SEARCH_MAX_ATTEMPTS - 1


# ---------------------------------------------------------------------------
# Phase 11.6 — Tavily retry on transient errors
# ---------------------------------------------------------------------------


def test_with_status_retries_on_transient_then_succeeds(monkeypatch, fast_sleep):
    # First call: transient timeout; second call: a valid response.
    raws = [_make_raw(url="https://www.reuters.com/x", content="ok")]
    mock = _patch_tavily(
        monkeypatch,
        side_effect=[RequestsTimeout("flaky"), {"results": raws}],
    )

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.SUCCESS
    assert len(outcome.results) == 1
    assert outcome.results[0].url == "https://www.reuters.com/x"
    assert mock.search.call_count == 2
    # Only one backoff sleep before the successful retry.
    assert fast_sleep == [1.0]


def test_with_status_retries_on_connection_reset_error(monkeypatch, fast_sleep):
    # Bare ConnectionResetError (the actual symptom in the production log).
    raws = [_make_raw(url="https://www.reuters.com/x", content="ok")]
    mock = _patch_tavily(
        monkeypatch,
        side_effect=[ConnectionResetError(10054, "An existing connection was forcibly closed"), {"results": raws}],
    )

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.SUCCESS
    assert mock.search.call_count == 2
    assert fast_sleep == [1.0]


def test_with_status_retries_three_times_then_fails(monkeypatch, fast_sleep):
    # Three consecutive transient failures should exhaust retries and
    # surface a FAILED outcome (verdict service then maps to inaccurate).
    mock = _patch_tavily(
        monkeypatch,
        side_effect=[
            RequestsConnectionError("first"),
            RequestsConnectionError("second"),
            RequestsConnectionError("third"),
        ],
    )

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.FAILED
    assert outcome.results == []
    assert mock.search.call_count == SEARCH_MAX_ATTEMPTS
    # 1s + 2s of backoff before the third attempt.
    assert fast_sleep == [1.0, 2.0]


def test_with_status_does_not_retry_on_non_transient(monkeypatch, fast_sleep):
    # RuntimeError is not a network error — fail fast.
    mock = _patch_tavily(monkeypatch, side_effect=RuntimeError("auth failed"))

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.FAILED
    assert mock.search.call_count == 1
    # No backoff sleep for non-transient errors.
    assert fast_sleep == []


def test_with_status_retries_on_oserror_subclass(monkeypatch, fast_sleep):
    # OSError is the parent of ConnectionResetError; it should be retried.
    raws = [_make_raw(url="https://www.reuters.com/x", content="ok")]
    mock = _patch_tavily(
        monkeypatch,
        side_effect=[OSError("broken pipe"), {"results": raws}],
    )

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.SUCCESS
    assert mock.search.call_count == 2
    assert fast_sleep == [1.0]


def test_with_status_does_not_retry_on_malformed_response(monkeypatch, fast_sleep):
    # A non-dict response should produce EMPTY (not a retry) because the
    # SDK call itself didn't raise — it just returned junk.
    _patch_tavily(monkeypatch, return_value=None)  # (None or {}).get("results") -> []

    outcome = search_claim_with_status(_claim())

    assert outcome.status == SearchStatus.EMPTY
    assert outcome.results == []
    assert fast_sleep == []


# ---------------------------------------------------------------------------
# Metrics observation
# ---------------------------------------------------------------------------


def test_with_status_increments_search_failures_on_failure(monkeypatch, fast_sleep):
    from core.metrics import RunMetrics

    _patch_tavily(monkeypatch, side_effect=RuntimeError("Tavily down"))
    metrics = RunMetrics(filename="x.pdf")

    search_claim_with_status(_claim(), metrics)

    assert metrics.search_failures == 1
    assert metrics.search_seconds >= 0


def test_with_status_does_not_increment_failures_on_success(monkeypatch):
    from core.metrics import RunMetrics

    raws = [_make_raw(url="https://www.reuters.com/x", content="ok")]
    _patch_tavily(monkeypatch, return_value={"results": raws})
    metrics = RunMetrics(filename="x.pdf")

    search_claim_with_status(_claim(), metrics)

    assert metrics.search_failures == 0
    assert metrics.search_seconds >= 0


def test_with_status_increments_failures_only_once_after_exhausting_retries(
    monkeypatch, fast_sleep
):
    # Three transient failures -> one metrics.search_failures bump, not three.
    from core.metrics import RunMetrics

    _patch_tavily(
        monkeypatch,
        side_effect=[
            RequestsConnectionError("a"),
            RequestsConnectionError("b"),
            RequestsConnectionError("c"),
        ],
    )
    metrics = RunMetrics(filename="x.pdf")

    search_claim_with_status(_claim(), metrics)

    assert metrics.search_failures == 1
    assert metrics.search_seconds >= 0


# ---------------------------------------------------------------------------
# Backwards-compat shim
# ---------------------------------------------------------------------------


def test_legacy_search_claim_returns_list(monkeypatch):
    raws = [_make_raw(url="https://www.reuters.com/x", content="ok")]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_service.search_claim(_claim())

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0].url == "https://www.reuters.com/x"
