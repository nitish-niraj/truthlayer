"""End-to-end verification pipeline (Phase 6 + Phase 11.5 + Phase 12).

Orchestrates the per-claim services into a single document-level workflow:

    text -> extract_claims -> (search_claim_with_status + generate_verdict) per claim
                                    -> VerifyResponse with summary counts
                                     + RunMetrics summary log

The pipeline is the only place where the pieces are composed. It never raises
on per-claim failures (defensive try/except wraps every claim) and never
raises on document-level edge cases (empty text, no claims). The router can
therefore always respond with 200 + a valid VerifyResponse, matching the
AGENTS.md rule that an empty claims list must NOT produce a 500.

Phase 11.5 additions:
- Uses ``search_claim_with_status`` so the verdict service can distinguish
  ``failed`` (network outage) from ``empty`` (Tavily returned nothing).
- Constructs a :class:`RunMetrics` for the document and threads it through
  the search and verdict services so timing and failure counters are
  populated. Calls ``RunMetrics.log_summary`` at the end of every run.
- The cross-pipeline ``VERDICT_SEMAPHORE`` is owned by
  :mod:`core.rate_limit` and is acquired inside ``verdict_service``; the
  pipeline simply delegates the call.

Phase 12 additions (production hardening for Render free tier):
- Concurrency cap reduced from 5 to 3 so we stay under Render's ~30s
  upstream HTTP timeout on a typical 5-claim document.
- Per-claim hard timeout via ``asyncio.wait_for`` so a single hung claim
  cannot block the whole response.
- Input text is truncated to ``settings.VERIFY_MAX_INPUT_CHARS`` before
  claim extraction so the LLM stage has a predictable cost.
- The ``verify_document`` coroutine also respects
  ``settings.VERIFY_HARD_TIMEOUT_SECONDS`` via ``asyncio.wait_for`` at the
  gather level — if the wall budget is exhausted, any claims already
  finished are returned (id-renumbered 1..N) and the rest are
  defensive-fallback "Unable to verify claim." rows.
- Diagnostic INFO logs at every stage boundary.
"""

import asyncio
import time
from typing import List

from core.config import settings
from core.logger import logger
from core.metrics import RunMetrics
from models.schemas import (
    ClaimType,
    ExtractedClaim,
    SummaryStats,
    VerdictType,
    VerifiedClaim,
    VerifyResponse,
)
from services.claim_service import extract_claims
from services.search_service import search_claim_with_status
from services.verdict_service import generate_verdict

# Phase 12: lowered from 5 -> 3 to keep wall time under Render's 30s free-tier
# proxy timeout on a 5-10 claim document. The verdict LLM dominates per-claim
# cost; 3 concurrent verdicts also keep us well under the NVIDIA 429 ceiling.
MAX_CONCURRENT_CLAIMS = 3

# Per-claim wall cap. A single search+verdict that takes longer than this is
# treated as a failure and a defensive-fallback VerifiedClaim is emitted in
# its place, so the rest of the document is not blocked.
PER_CLAIM_TIMEOUT_SECONDS = 15.0

PIPELINE_FALLBACK_EXPLANATION = "Unable to verify claim."

# Returned to the client when the overall verify_document call times out and
# we ship a partial result. The UI should treat this as informational, not an
# error — the document was processed, just not all of it.
PARTIAL_RESULT_NOTE = (
    "Analysis completed with partial results due to a server-side time "
    "budget. Some claims may not have been verified."
)


def _defensive_fallback_claim(claim: ExtractedClaim) -> VerifiedClaim:
    return VerifiedClaim(
        id=-1,
        claim=claim.claim,
        type=claim.type,
        source_sentence=claim.source_sentence,
        verdict=VerdictType.false,
        explanation=PIPELINE_FALLBACK_EXPLANATION,
        correct_fact="",
        source_url="",
    )


async def _process_claim(
    claim: ExtractedClaim,
    sem: asyncio.Semaphore,
    metrics: RunMetrics,
) -> VerifiedClaim:
    """Run search + verdict for one claim, gated by the concurrency semaphore.

    Wrapped in ``asyncio.wait_for`` so a single hung claim cannot exceed
    ``PER_CLAIM_TIMEOUT_SECONDS``. On timeout or any exception we emit a
    defensive-fallback claim so the document-level response still ships.

    ``search_claim_with_status`` is synchronous; we offload it to a thread so
    that up to ``MAX_CONCURRENT_CLAIMS`` searches can be in flight
    simultaneously. The cross-pipeline ``VERDICT_SEMAPHORE`` (in
    ``core.rate_limit``) caps concurrent LLM calls separately.
    """
    logger.info("CLAIM START | %s", claim.claim[:80])
    t0 = time.perf_counter()
    try:
        async with sem:
            try:
                outcome = await asyncio.wait_for(
                    asyncio.to_thread(search_claim_with_status, claim, metrics),
                    timeout=PER_CLAIM_TIMEOUT_SECONDS,
                )
                verification = await asyncio.wait_for(
                    generate_verdict(claim, outcome.results, outcome.status, metrics),
                    timeout=PER_CLAIM_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "CLAIM TIMEOUT | %.1fs cap | %s",
                    PER_CLAIM_TIMEOUT_SECONDS,
                    claim.claim[:80],
                )
                metrics.llm_failures += 1
                return _defensive_fallback_claim(claim)
    except Exception as exc:
        logger.warning("Pipeline error for claim '%s': %s", claim.claim[:60], exc)
        return _defensive_fallback_claim(claim)

    elapsed = time.perf_counter() - t0
    logger.info(
        "CLAIM END | verdict=%s | %.2fs | %s",
        verification.verdict,
        elapsed,
        claim.claim[:80],
    )
    return VerifiedClaim(
        id=-1,
        claim=claim.claim,
        type=claim.type,
        source_sentence=claim.source_sentence,
        verdict=verification.verdict,
        explanation=verification.explanation,
        correct_fact=verification.correct_fact,
        source_url=verification.source_url,
    )


def _summary(claims: List[VerifiedClaim]) -> SummaryStats:
    return SummaryStats(
        total=len(claims),
        verified=sum(1 for c in claims if c.verdict == VerdictType.verified),
        inaccurate=sum(1 for c in claims if c.verdict == VerdictType.inaccurate),
        false=sum(1 for c in claims if c.verdict == VerdictType.false),
    )


def _populate_summary_metrics(summary: SummaryStats, metrics: RunMetrics) -> None:
    metrics.claims_total = summary.total
    metrics.claims_verified = summary.verified
    metrics.claims_inaccurate = summary.inaccurate
    metrics.claims_false = summary.false


def _truncate_input(text: str) -> str:
    cap = settings.VERIFY_MAX_INPUT_CHARS
    if len(text) > cap:
        logger.warning(
            "Input text truncated for claim extraction: %d -> %d chars",
            len(text),
            cap,
        )
        return text[:cap]
    return text


async def _gather_with_budget(
    coros: List[asyncio.Task], budget_seconds: float
) -> tuple[list, list]:
    """Run ``coros`` with a hard wall-clock cap.

    Returns ``(done, pending)`` where ``pending`` is the list of unfinished
    tasks at the deadline. Pending tasks are cancelled so we never leak a
    coroutine past the response.
    """
    gathered = asyncio.gather(*coros, return_exceptions=False)
    try:
        results = await asyncio.wait_for(gathered, timeout=budget_seconds)
        return results, []
    except asyncio.TimeoutError:
        # Cancel any in-flight work and return whatever's done so far. We
        # don't rely on gather's internal cancellation — we cancel each task
        # explicitly so a long-running LLM call releases its semaphore.
        for task in coros:
            if not task.done():
                task.cancel()
        # Give the loop one tick to actually cancel, then collect results.
        done_results: list = []
        for task in coros:
            if task.done() and not task.cancelled():
                try:
                    done_results.append(task.result())
                except Exception:
                    done_results.append(None)
            else:
                done_results.append(None)
        return done_results, [t for t in coros if not t.done()]


async def verify_document(
    text: str,
    filename: str,
    hard_timeout: float | None = None,
) -> VerifyResponse:
    """Run the full verification pipeline on extracted document text.

    Never raises. Returns a valid VerifyResponse in every case (including
    empty text, zero claims, and per-claim failures). If the wall budget
    (``hard_timeout`` or ``settings.VERIFY_HARD_TIMEOUT_SECONDS``) elapses,
    the claims that have already finished are returned and the remainder
    are emitted as defensive-fallback claims with a partial-result note in
    the explanation.
    """
    metrics = RunMetrics(filename=filename)
    metrics.start()
    logger.info("VERIFY REQUEST RECEIVED | file=%s | chars=%d", filename, len(text))

    truncated = _truncate_input(text)

    t_extract_start = time.perf_counter()
    try:
        claims = await extract_claims(truncated)
    except Exception as exc:
        logger.warning("extract_claims raised unexpectedly: %s", exc)
        claims = []
    metrics.claim_extraction_seconds = time.perf_counter() - t_extract_start
    logger.info(
        "CLAIM EXTRACTION FINISHED | %d claims | %.2fs",
        len(claims),
        metrics.claim_extraction_seconds,
    )

    if len(claims) > settings.MAX_CLAIMS:
        logger.warning(
            "Claims truncated: extracted %d, capped at MAX_CLAIMS=%d",
            len(claims),
            settings.MAX_CLAIMS,
        )
        claims = claims[: settings.MAX_CLAIMS]

    if not claims:
        logger.info("Verification skipped: no claims extracted")
        metrics.finish()
        metrics.log_summary()
        return VerifyResponse(
            filename=filename,
            summary=SummaryStats(total=0, verified=0, inaccurate=0, false=0),
            claims=[],
        )

    logger.info("VERIFICATION STARTED | %d claims | concurrency=%d", len(claims), MAX_CONCURRENT_CLAIMS)
    t_verify_start = time.perf_counter()

    sem = asyncio.Semaphore(MAX_CONCURRENT_CLAIMS)
    tasks = [
        asyncio.create_task(_process_claim(c, sem, metrics), name=f"claim-{i}")
        for i, c in enumerate(claims)
    ]

    # Compute remaining wall budget for the per-claim gather stage. The
    # extraction stage already consumed some time; subtract it from the
    # hard cap so we never exceed the budget end-to-end.
    elapsed_so_far = time.perf_counter() - t_verify_start + metrics.claim_extraction_seconds
    budget = hard_timeout if hard_timeout is not None else settings.VERIFY_HARD_TIMEOUT_SECONDS
    remaining = max(0.5, budget - elapsed_so_far)

    results, pending = await _gather_with_budget(tasks, remaining)

    # Replace any unfinished / None slots with defensive-fallback claims so
    # the response shape is always valid.
    final_claims: List[VerifiedClaim] = []
    for claim, result in zip(claims, results):
        if result is None or isinstance(result, Exception):
            logger.warning(
                "Falling back claim (timeout or error): %s", claim.claim[:80]
            )
            final_claims.append(_defensive_fallback_claim(claim))
        else:
            final_claims.append(result)

    if pending:
        logger.warning(
            "VERIFY HARD TIMEOUT | %d of %d claims did not finish in %.1fs; "
            "returning partial result",
            len(pending),
            len(claims),
            remaining,
        )
        for vc in final_claims:
            if vc.explanation == PIPELINE_FALLBACK_EXPLANATION and vc.id == -1:
                vc.explanation = (
                    f"{PIPELINE_FALLBACK_EXPLANATION} ({PARTIAL_RESULT_NOTE})"
                )

    verify_seconds = time.perf_counter() - t_verify_start
    avg_per_claim = verify_seconds / max(len(claims), 1)

    for idx, vc in enumerate(final_claims, start=1):
        vc.id = idx

    summary = _summary(final_claims)
    _populate_summary_metrics(summary, metrics)
    metrics.finish()

    logger.info(
        "VERIFICATION COMPLETED | total=%d verified=%d inaccurate=%d false=%d "
        "| %.2fs (avg %.2fs/claim)",
        summary.total,
        summary.verified,
        summary.inaccurate,
        summary.false,
        metrics.total_seconds,
        avg_per_claim,
    )
    metrics.log_summary()
    logger.info("VERIFY RESPONSE RETURNED | file=%s | claims=%d", filename, summary.total)

    return VerifyResponse(filename=filename, summary=summary, claims=final_claims)
