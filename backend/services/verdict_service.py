"""Verdict generation service (Phase 5 + Phase 11.5).

Responsibility: take a single ExtractedClaim plus the web evidence collected in
Phase 4 and return a ClaimVerification (verdict, explanation, correct_fact,
source_url). Has no knowledge of how evidence was collected and no opinion on
the claim beyond what the evidence consensus supports.

The service never raises. Any failure (LLM error, malformed JSON, Pydantic
validation, exhausted retries) returns a safe-fallback ``ClaimVerification``
so the router can always respond with a 200 + a valid verdict.

Phase 11.5 additions:
- Retries the LLM call with exponential backoff (1s, 2s, 4s) on transient
  failures: HTTP 429, HTTP 5xx, and connection/timeout errors.
- Honours a global :data:`core.rate_limit.VERDICT_SEMAPHORE` so concurrent
  verdicts never exceed ``VERDICT_SEMAPHORE_PERMITS`` in flight.
- If the search itself failed, returns ``inaccurate`` (not ``false``) so a
  network outage does not get mislabelled as a fabricated claim.
- On exhausted retries, returns a dedicated rate-limited fallback
  (``inaccurate``) — distinct from the LLM-error SAFE_FALLBACK (``false``).
- Records per-claim timings and 429 counts into the optional ``metrics``
  argument.
"""

import asyncio
import json
import time
from typing import List, Optional

import openai
from pydantic import ValidationError

from core.llm_client import MODEL_NAME, get_llm_client
from core.logger import logger
from core.metrics import RunMetrics
from core.rate_limit import VERDICT_SEMAPHORE
from models.schemas import ClaimVerification, ExtractedClaim, SearchResult
from services.search_service import SearchStatus

VERDICT_TEMPERATURE = 0.1
VERDICT_TOP_P = 1.0
VERDICT_MAX_TOKENS = 1024
VERDICT_THINKING = False

# Retry policy (Phase 11.5)
MAX_VERDICT_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)

# LLM-error fallback: the model returned something we can't trust.
SAFE_FALLBACK = ClaimVerification(
    verdict="false",
    explanation="Unable to verify claim due to processing failure.",
    correct_fact="",
    source_url="",
)

# Search-failed fallback: the network/provider failed. We don't know if the
# claim is true, so label it as inaccurate (needs more evidence) rather than
# false (which implies fabrication).
SEARCH_FAILED_FALLBACK = ClaimVerification(
    verdict="inaccurate",
    explanation="Unable to retrieve sufficient evidence from search providers.",
    correct_fact="",
    source_url="",
)

# Rate-limit fallback: the LLM kept returning 429. Distinct explanation so the
# UI can communicate that the service is currently overloaded, not that the
# claim is fabricated.
RATE_LIMITED_FALLBACK = ClaimVerification(
    verdict="inaccurate",
    explanation="Verification service temporarily unavailable.",
    correct_fact="",
    source_url="",
)

VERDICT_PROMPT = """You are a professional fact-checker. You are given a claim and a set of web evidence sources.

CRITICAL RULES:
- Do NOT trust the claim. The claim is a hypothesis, not a fact.
- Do NOT trust any single source, including the first one. Evaluate the evidence as a whole.
- Look for consensus across the sources. If sources disagree, prefer authoritative and recent ones.
- If the evidence is absent or irrelevant, the claim is unsupported.

VERDICT DEFINITIONS (pick exactly one):
- "verified":    current evidence strongly supports the claim; the statement matches what reliable sources say NOW.
- "inaccurate":  the claim contains partially correct information but is outdated (old statistics, old user counts, old market sizes, superseded figures). It was once true but is no longer accurate.
- "false":       the claim is unsupported, directly contradicted by evidence, or clearly fabricated.

OUTPUT FORMAT — return ONLY this JSON object, no markdown, no preamble, no commentary:
{{
  "verdict": "verified" | "inaccurate" | "false",
  "explanation": "<one to three sentences explaining your reasoning>",
  "correct_fact": "<empty string if verdict is verified; otherwise the corrected/updated information>",
  "source_url": "<URL of the most relevant source from the evidence, or empty string if no source supports a verdict>"
}}

CLAIM:
{claim}

EVIDENCE:
{evidence}
"""


def _format_evidence(results: List[SearchResult]) -> str:
    if not results:
        return "No evidence found."
    blocks: List[str] = []
    for idx, r in enumerate(results, start=1):
        content = r.content if len(r.content) <= 1000 else r.content[:1000]
        blocks.append(
            f"Source {idx}:\nTitle: {r.title}\nURL: {r.url}\nContent: {content}"
        )
    return "\n\n".join(blocks)


def _parse_json_object(raw: str) -> dict | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            cleaned = inner.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _is_retryable(exc: BaseException) -> bool:
    """Return True for HTTP 429, HTTP 5xx, and connection/timeout errors.

    Everything else (auth errors, bad-request errors, JSON parse errors)
    is treated as a hard failure that retrying cannot fix.
    """
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.InternalServerError):
        return True
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    return False


def _record_rate_limit(metrics: Optional[RunMetrics]) -> None:
    if metrics is not None:
        metrics.rate_limit_count += 1


async def _call_llm_with_retries(
    prompt: str,
    metrics: Optional[RunMetrics],
) -> tuple[ClaimVerification | None, bool]:
    """Call the LLM with retry/backoff.

    Returns a tuple of ``(verification, saw_rate_limit)``. When every attempt
    failed, ``verification`` is ``None`` and ``saw_rate_limit`` is ``True`` if
    at least one of those failures was a 429 (so the caller can return
    :data:`RATE_LIMITED_FALLBACK` instead of :data:`SAFE_FALLBACK`).
    """
    last_exc: BaseException | None = None
    saw_rate_limit = False
    for attempt in range(1, MAX_VERDICT_ATTEMPTS + 1):
        try:
            async with VERDICT_SEMAPHORE:
                client = get_llm_client()
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=VERDICT_TEMPERATURE,
                    top_p=VERDICT_TOP_P,
                    max_tokens=VERDICT_MAX_TOKENS,
                    stream=False,
                    extra_body={"chat_template_kwargs": {"thinking": VERDICT_THINKING}},
                )
        except Exception as exc:
            last_exc = exc
            is_rate_limit = isinstance(exc, openai.RateLimitError) or (
                getattr(exc, "status_code", None) == 429
            )
            if is_rate_limit:
                saw_rate_limit = True
                _record_rate_limit(metrics)

            if not _is_retryable(exc) or attempt >= MAX_VERDICT_ATTEMPTS:
                if metrics is not None:
                    metrics.llm_failures += 1
                logger.error(
                    f"LLM request failed (attempt {attempt}/{MAX_VERDICT_ATTEMPTS}, "
                    f"non-retryable or attempts exhausted): {exc}"
                )
                return None, saw_rate_limit

            backoff = RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                f"LLM request failed (attempt {attempt}/{MAX_VERDICT_ATTEMPTS}); "
                f"retrying in {backoff:.1f}s: {exc}"
            )
            await asyncio.sleep(backoff)
            continue

        raw = response.choices[0].message.content
        data = _parse_json_object(raw)
        if data is None:
            logger.error("Verdict parsing failed: no valid JSON object in response")
            return None, saw_rate_limit

        try:
            return ClaimVerification(**data), saw_rate_limit
        except ValidationError as exc:
            logger.error(f"Verdict parsing failed: {exc}")
            return None, saw_rate_limit

    if last_exc is not None:
        logger.error(f"LLM retries exhausted: {last_exc}")
    return None, saw_rate_limit


async def generate_verdict(
    claim: ExtractedClaim,
    search_results: List[SearchResult],
    search_status: SearchStatus = SearchStatus.SUCCESS,
    metrics: Optional[RunMetrics] = None,
) -> ClaimVerification:
    """Generate a verdict for a claim based on the provided web evidence.

    Never raises. Returns one of:
      - ``ClaimVerification`` on success
      - ``SEARCH_FAILED_FALLBACK`` (inaccurate) if the upstream search failed
      - ``SAFE_FALLBACK`` (false) if the LLM errored or returned malformed JSON
      - ``RATE_LIMITED_FALLBACK`` (inaccurate) if every retry attempt got 429

    ``search_status`` lets the caller (the pipeline) tell the verdict service
    whether the evidence list is empty because the search failed (network
    outage) or because the query really had no hits. In the former case we
    must NOT label the claim as ``false`` — that would be misinformation.
    """
    logger.info(f"Starting verdict generation: {claim.claim[:60]}")

    if search_status == SearchStatus.FAILED:
        logger.warning("Search provider failed; returning SEARCH_FAILED_FALLBACK")
        return SEARCH_FAILED_FALLBACK

    if not search_results:
        logger.info("No evidence provided; returning false fallback without LLM call")
        return ClaimVerification(
            verdict="false",
            explanation="No evidence found to evaluate this claim.",
            correct_fact="",
            source_url="",
        )

    prompt = VERDICT_PROMPT.format(
        claim=claim.claim,
        evidence=_format_evidence(search_results),
    )

    t0 = time.perf_counter()
    verification, saw_rate_limit = await _call_llm_with_retries(prompt, metrics)
    if metrics is not None:
        metrics.verdict_seconds += time.perf_counter() - t0

    if verification is not None:
        logger.info(
            f"Verdict generated: {verification.verdict} ({verification.explanation[:60]})"
        )
        return verification

    # All retries exhausted (or the response was unparseable). Differentiate
    # 429-exhaustion from a generic LLM error so the UI sees a meaningful
    # explanation.
    if saw_rate_limit:
        return RATE_LIMITED_FALLBACK
    return SAFE_FALLBACK
