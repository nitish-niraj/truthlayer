"""Search & evidence service (Phase 4 + Phase 11.5 + 11.6).

Responsibility: take a single ExtractedClaim and return ranked web evidence.
Has no knowledge of verdicts, scoring, or confidence — that is Phase 5's job.

Phase 11.5 additions:
- A ``SearchStatus`` enum and a ``SearchOutcome`` dataclass let callers
  distinguish ``success`` (we got N results), ``empty`` (Tavily worked but
  returned no useful hits), and ``failed`` (Tavily errored or timed out).
  Previously both empty and failed returned ``[]``; the verdict service now
  needs to know which is which so that a real search outage doesn't get
  labelled as a "false" claim.
- ``search_claim_with_status`` is the new internal entry point used by the
  pipeline. ``search_claim`` is preserved as a thin wrapper for the legacy
  ``/api/search-claim`` endpoint so its public contract is unchanged.

Phase 11.6 additions:
- Tavily calls are now retried with exponential backoff on transient errors
  (connection reset, connection aborted, timeout, socket-level errors). The
  retry uses the same 1s/2s/4s schedule as the LLM retries. Non-transient
  errors (auth, bad request, malformed response) still fail immediately so
  we don't waste time on unrecoverable problems.
- After all retries are exhausted the function returns ``SearchStatus.FAILED``
  and the verdict service maps that to ``SEARCH_FAILED_FALLBACK`` (inaccurate,
  "Unable to retrieve sufficient evidence from search providers.") instead
  of labelling the claim ``false``.
"""

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import List
from urllib.parse import urlparse

import requests
from tavily import TavilyClient

from core.config import settings
from core.logger import logger
from core.metrics import RunMetrics
from models.schemas import ExtractedClaim, SearchResult

CONTENT_MAX_CHARS = 1000

# Phase 11.6: Tavily retry policy. Same 1s/2s/4s backoff as the LLM retries
# (verdict_service.MAX_VERDICT_ATTEMPTS / RETRY_BACKOFF_SECONDS).
SEARCH_MAX_ATTEMPTS = 3
SEARCH_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)

# Exceptions we treat as transient and worth retrying. Anything outside this
# tuple (RuntimeError, ValueError, auth errors, etc.) fails immediately.
SEARCH_TRANSIENT_EXCEPTIONS: tuple = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    TimeoutError,
    OSError,  # parent of the socket-level errors above; catch-all for network
)

TIER1_DOMAINS = frozenset(
    {
        "apple.com",
        "microsoft.com",
        "sec.gov",
        "who.int",
        "worldbank.org",
        "imf.org",
        "oecd.org",
        "bea.gov",
        "bls.gov",
        "census.gov",
        "nasa.gov",
        "nih.gov",
        "thelancet.com",
        "nejm.org",
        "nature.com",
        "science.org",
    }
)

TIER2_DOMAINS = frozenset(
    {
        "nytimes.com",
        "reuters.com",
        "bbc.com",
        "bbc.co.uk",
        "wsj.com",
        "theguardian.com",
        "bloomberg.com",
        "forbes.com",
        "ft.com",
        "economist.com",
        "apnews.com",
        "ieee.org",
        "acm.org",
        "arxiv.org",
        "github.com",
        "stackoverflow.com",
    }
)

_TIER1_TLD_RE = re.compile(r"\.(gov|int)$", re.IGNORECASE)
_TIER1_GOV_SUBDOMAIN_RE = re.compile(r"\.(gov|int)\.", re.IGNORECASE)
_TIER2_TLD_RE = re.compile(r"\.(edu)$", re.IGNORECASE)

_tavily_client: TavilyClient | None = None


class SearchStatus(str, Enum):
    """Outcome of a Tavily search for a single claim."""

    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"


@dataclass
class SearchOutcome:
    """Result of a single Tavily search, including the failure status.

    ``results`` is always a (possibly empty) list. ``status`` is one of:
      - SUCCESS: at least one usable result was returned
      - EMPTY:   Tavily worked but the query produced no usable hits
      - FAILED:  Tavily raised, timed out, or returned a malformed response
    """

    status: SearchStatus
    results: List[SearchResult]

    @property
    def ok(self) -> bool:
        return self.status == SearchStatus.SUCCESS


def get_tavily_client() -> TavilyClient:
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    return _tavily_client


def _registrable_domain(url: str) -> str:
    """Return the lowercased host (eTLD+1 simplification: just the last two labels).

    Good enough for matching against our hand-curated domain allow-lists.
    """
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    host = host.lower().strip()
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _tier_for(url: str) -> int:
    """1 = authoritative, 2 = reputable, 3 = everything else."""
    domain = _registrable_domain(url)
    if not domain:
        return 3
    if domain in TIER1_DOMAINS or _TIER1_TLD_RE.search(domain) or _TIER1_GOV_SUBDOMAIN_RE.search(domain):
        return 1
    if domain in TIER2_DOMAINS or _TIER2_TLD_RE.search(domain):
        return 2
    return 3


def _is_valid(result: SearchResult) -> bool:
    return bool(result.title and result.title.strip()) and bool(
        result.url and result.url.strip()
    ) and bool(result.content and result.content.strip())


def _truncate(text: str) -> str:
    if len(text) > CONTENT_MAX_CHARS:
        return text[:CONTENT_MAX_CHARS]
    return text


def _normalize(raw: dict) -> SearchResult | None:
    title = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    content = (raw.get("content") or "").strip()
    if not title or not url or not content:
        return None
    return SearchResult(title=title, url=url, content=_truncate(content))


def _rank(results: List[SearchResult]) -> List[SearchResult]:
    return sorted(results, key=lambda r: _tier_for(r.url))


def _is_transient_search_error(exc: BaseException) -> bool:
    """Return True for the transient network errors we want to retry."""
    if isinstance(exc, SEARCH_TRANSIENT_EXCEPTIONS):
        return True
    # Belt and braces: some Tavily/httpx wrappers expose the underlying
    # socket error via __cause__ or as a string in the message. Catch the
    # ConnectionResetError-by-string case for completeness.
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and isinstance(cause, SEARCH_TRANSIENT_EXCEPTIONS):
        return True
    msg = repr(exc).lower()
    return any(
        marker in msg
        for marker in (
            "connection reset",
            "connection aborted",
            "connection refused",
            "remote disconnected",
            "timed out",
        )
    )


def _search_sleep(seconds: float) -> None:
    """Indirection so tests can monkeypatch the retry backoff to zero."""
    time.sleep(seconds)


def _execute_tavily_query(claim: ExtractedClaim):
    """Single Tavily query. Raises whatever the SDK raises on failure."""
    client = get_tavily_client()
    return client.search(
        query=claim.claim,
        search_depth="advanced",
        max_results=settings.MAX_SEARCH_RESULTS,
        include_answer=False,
        include_raw_content=False,
        timeout=settings.SEARCH_TIMEOUT_SECONDS,
    )


def search_claim_with_status(
    claim: ExtractedClaim,
    metrics: RunMetrics | None = None,
) -> SearchOutcome:
    """Search the web for evidence and report the outcome status.

    Returns a :class:`SearchOutcome` whose ``status`` distinguishes
    ``success`` / ``empty`` / ``failed``. ``metrics`` is optional; when
    provided, ``search_seconds`` and ``search_failures`` are updated.
    Never raises.

    Phase 11.6: transient Tavily errors (ConnectionResetError, etc.) are
    retried up to ``SEARCH_MAX_ATTEMPTS`` times with the
    ``SEARCH_RETRY_BACKOFF_SECONDS`` schedule (1s, 2s, 4s). Non-transient
    errors fail immediately. After all retries are exhausted the function
    returns ``SearchStatus.FAILED``.
    """
    query = claim.claim
    logger.info(f"Searching claim: {query[:60]}")
    t0 = time.perf_counter()

    response = None
    last_exc: BaseException | None = None
    for attempt in range(1, SEARCH_MAX_ATTEMPTS + 1):
        try:
            response = _execute_tavily_query(claim)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            transient = _is_transient_search_error(exc)
            if not transient or attempt >= SEARCH_MAX_ATTEMPTS:
                # Either non-transient (no point retrying) or out of attempts.
                if "timeout" in repr(exc).lower() or "Timeout" in type(exc).__name__:
                    logger.error(f"Search timeout after {settings.SEARCH_TIMEOUT_SECONDS}s")
                else:
                    logger.error(f"Tavily request failed: {exc}")
                if metrics is not None:
                    metrics.search_failures += 1
                    metrics.search_seconds += time.perf_counter() - t0
                return SearchOutcome(status=SearchStatus.FAILED, results=[])

            backoff = SEARCH_RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                f"Search attempt {attempt}/{SEARCH_MAX_ATTEMPTS} failed; "
                f"retrying in {backoff:.1f}s: {exc}"
            )
            _search_sleep(backoff)

    if response is None:
        # Defensive: should be unreachable (the loop either returns FAILED
        # or sets response), but keep a safety net so we never crash.
        logger.error(f"Tavily request failed after retries: {last_exc}")
        if metrics is not None:
            metrics.search_failures += 1
            metrics.search_seconds += time.perf_counter() - t0
        return SearchOutcome(status=SearchStatus.FAILED, results=[])

    raw_results = (response or {}).get("results") or []
    logger.info(f"Search results found: {len(raw_results)}")

    normalized: List[SearchResult] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        item = _normalize(raw)
        if item is not None:
            normalized.append(item)

    seen_urls: set[str] = set()
    deduped: List[SearchResult] = []
    for item in normalized:
        if item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        if _is_valid(item):
            deduped.append(item)

    ranked = _rank(deduped)
    logger.info(f"Results after filtering: {len(ranked)}")

    if metrics is not None:
        metrics.search_seconds += time.perf_counter() - t0

    if not ranked:
        return SearchOutcome(status=SearchStatus.EMPTY, results=[])

    return SearchOutcome(status=SearchStatus.SUCCESS, results=ranked)


def search_claim(claim: ExtractedClaim) -> List[SearchResult]:
    """Backwards-compatible wrapper returning just the result list.

    Preserves the Phase 4 contract used by ``/api/search-claim``. New code
    should call :func:`search_claim_with_status` instead so the failure
    status is preserved.
    """
    outcome = search_claim_with_status(claim)
    return outcome.results
