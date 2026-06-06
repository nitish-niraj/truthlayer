"""End-to-end verification pipeline (Phase 6 + Phase 11.5 + Phase 12 + Phase 13).

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
- Concurrency cap of 3 to stay under Render's ~30s upstream HTTP timeout
  on a typical 5-claim document.
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

Phase 13 additions (background-job pattern):
- ``verify_document`` accepts an optional ``progress_cb`` coroutine
  callback that is invoked after each stage so the job store can publish
  live progress to polling clients.
- An additional ``deadline`` parameter lets the router cap wall time
  including the LLM extraction stage (which used to be unbounded).
- ``extract_claims`` is now wrapped in ``asyncio.wait_for`` so a hung LLM
  call cannot stall the background task past the deadline.

V2 Phase 3 additions (image verification reuse):
- ``verify_single_claim`` and ``summarize_verified_claims`` are now public
  primitives. The PDF pipeline still composes them internally, but the
  image flow imports them directly so there is exactly one verification
  engine in the codebase.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable, List, Optional

from core.config import settings
from core.logger import logger
from core.metrics import RunMetrics
from models.schemas import (
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

# Cap on the LLM call inside extract_claims. Cold-start on a free Render
# instance can take 25-35s for the first request; we hard-cap so the
# background task never exceeds its deadline.
CLAIM_EXTRACTION_STAGE_TIMEOUT_SECONDS = 20.0

PIPELINE_FALLBACK_EXPLANATION = "Unable to verify claim."

PARTIAL_RESULT_NOTE = (
    "Analysis completed with partial results due to a server-side time "
    "budget. Some claims may not have been verified."
)

ProgressCb = Callable[[dict], Awaitable[None]]


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


async def verify_single_claim(
    claim: ExtractedClaim,
    metrics: Optional[RunMetrics] = None,
) -> VerifiedClaim:
    """Run search + verdict for a single claim. Public primitive.

    This is the same per-claim logic the PDF pipeline runs; exposing it lets
    other entry points (e.g. :mod:`services.image_verification_service`) reuse
    the single verification engine without duplicating code.

    Wrapped in ``asyncio.wait_for`` so a single hung claim cannot exceed
    ``PER_CLAIM_TIMEOUT_SECONDS``. On timeout or any exception we emit a
    defensive-fallback claim so the caller never has to handle exceptions
    per claim. ``search_claim_with_status`` is synchronous and is offloaded to
    a thread so it does not block the event loop. The cross-pipeline
    ``VERDICT_SEMAPHORE`` (in :mod:`core.rate_limit`) caps concurrent LLM
    calls separately and is acquired inside ``verdict_service``.
    """
    logger.info("CLAIM START | %s", claim.claim[:80])
    t0 = time.perf_counter()
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
        if metrics is not None:
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


# Backwards-compatible alias for the old internal name. The PDF pipeline used
# to wrap this in an externally-supplied semaphore; the new
# :func:`verify_single_claim` no longer needs a semaphore argument because the
# cross-pipeline ``VERDICT_SEMAPHORE`` inside ``verdict_service`` is the
# single source of truth for LLM concurrency. Kept as an alias so external
# callers that still hold a reference don't break.
async def _process_claim(
    claim: ExtractedClaim,
    sem: asyncio.Semaphore,  # noqa: ARG001 — kept for signature compatibility
    metrics: RunMetrics,
) -> VerifiedClaim:
    return await verify_single_claim(claim, metrics)


def summarize_verified_claims(claims: List[VerifiedClaim]) -> SummaryStats:
    """Aggregate a list of ``VerifiedClaim`` into a ``SummaryStats``.

    Public primitive so the image flow can reuse the same counts the PDF
    pipeline emits. Renamed from the private ``_summary`` for V2 Phase 3.
    """
    return SummaryStats(
        total=len(claims),
        verified=sum(1 for c in claims if c.verdict == VerdictType.verified),
        inaccurate=sum(1 for c in claims if c.verdict == VerdictType.inaccurate),
        false=sum(1 for c in claims if c.verdict == VerdictType.false),
    )


# Internal alias so existing call sites in this module keep working without
# a sprawling rename.
_summary = summarize_verified_claims


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


async def _emit(progress_cb: Optional[ProgressCb], **fields: Any) -> None:
    if progress_cb is None:
        return
    try:
        await progress_cb(fields)
    except Exception as exc:
        logger.warning("Progress callback raised: %s", exc)


async def verify_document(
    text: str,
    filename: str,
    hard_timeout: Optional[float] = None,
    progress_cb: Optional[ProgressCb] = None,
) -> VerifyResponse:
    """Run the full verification pipeline on extracted document text.

    Never raises. Returns a valid VerifyResponse in every case (including
    empty text, zero claims, and per-claim failures). If the wall budget
    (``hard_timeout`` or ``settings.VERIFY_HARD_TIMEOUT_SECONDS``) elapses,
    the claims that have already finished are returned and the remainder
    are emitted as defensive-fallback claims with a partial-result note in
    the explanation.

    ``progress_cb`` is an optional coroutine invoked with keyword arguments
    at every stage boundary (e.g. ``stage="extraction"``, ``claims=4``).
    Used by the background-job router to publish live progress to polling
    clients. The callback is awaited but any exception in it is swallowed
    so it cannot break the pipeline.
    """
    metrics = RunMetrics(filename=filename)
    metrics.start()
    logger.info("VERIFY REQUEST RECEIVED | file=%s | chars=%d", filename, len(text))
    await _emit(progress_cb, stage="received", filename=filename, chars=len(text))

    truncated = _truncate_input(text)

    budget = hard_timeout if hard_timeout is not None else settings.VERIFY_HARD_TIMEOUT_SECONDS
    t_overall = time.perf_counter()

    # Stage 1: claim extraction. Capped explicitly so a hung LLM call
    # cannot block the background task past the deadline.
    t_extract_start = time.perf_counter()
    remaining_for_extraction = max(
        1.0,
        min(CLAIM_EXTRACTION_STAGE_TIMEOUT_SECONDS, budget * 0.6),
    )
    try:
        claims = await asyncio.wait_for(
            extract_claims(truncated),
            timeout=remaining_for_extraction,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "CLAIM EXTRACTION TIMEOUT | cap=%.1fs | returning empty result",
            remaining_for_extraction,
        )
        claims = []
    except Exception as exc:
        logger.warning("extract_claims raised unexpectedly: %s", exc)
        claims = []
    metrics.claim_extraction_seconds = time.perf_counter() - t_extract_start
    logger.info(
        "CLAIM EXTRACTION FINISHED | %d claims | %.2fs",
        len(claims),
        metrics.claim_extraction_seconds,
    )
    await _emit(
        progress_cb,
        stage="extraction",
        claims=len(claims),
        extraction_seconds=round(metrics.claim_extraction_seconds, 3),
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

    logger.info(
        "VERIFICATION STARTED | %d claims | concurrency=%d",
        len(claims),
        MAX_CONCURRENT_CLAIMS,
    )
    await _emit(progress_cb, stage="verification", claims=len(claims), concurrency=MAX_CONCURRENT_CLAIMS)

    # Per-claim concurrency is gated by the cross-pipeline VERDICT_SEMAPHORE
    # inside verdict_service; we still cap the in-flight task count at
    # MAX_CONCURRENT_CLAIMS to bound memory + the per-claim wait_for budget.
    sem = asyncio.Semaphore(MAX_CONCURRENT_CLAIMS)
    tasks = [
        asyncio.create_task(_process_claim(c, sem, metrics), name=f"claim-{i}")
        for i, c in enumerate(claims)
    ]

    # Remaining wall budget for the gather stage. Use the absolute deadline
    # rather than a "remaining" so we never overshoot the cap even if
    # extract_claims was faster than expected.
    remaining = max(0.5, budget - (time.perf_counter() - t_overall))
    results, pending = await _gather_with_budget_and_progress(
        tasks, remaining, progress_cb, total_claims=len(claims)
    )

    final_claims: List[VerifiedClaim] = []
    for claim, result in zip(claims, results):
        if result is None or isinstance(result, Exception):
            logger.warning(
                "Falling back claim (timeout or error): %s", claim.claim[:80]
            )
            final_claims.append(_defensive_fallback_claim(claim))
        else:
            final_claims.append(result)

    is_partial = bool(pending)
    if is_partial:
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

    for idx, vc in enumerate(final_claims, start=1):
        vc.id = idx

    summary = _summary(final_claims)
    _populate_summary_metrics(summary, metrics)
    metrics.finish()

    logger.info(
        "VERIFICATION COMPLETED | total=%d verified=%d inaccurate=%d false=%d "
        "| %.2fs (avg %.2fs/claim) | partial=%s",
        summary.total,
        summary.verified,
        summary.inaccurate,
        summary.false,
        metrics.total_seconds,
        metrics.total_seconds / max(len(claims), 1),
        is_partial,
    )
    metrics.log_summary()
    logger.info("VERIFY RESPONSE RETURNED | file=%s | claims=%d", filename, summary.total)
    await _emit(
        progress_cb,
        stage="done",
        partial=is_partial,
        claims=summary.total,
        total_seconds=round(metrics.total_seconds, 3),
    )

    return VerifyResponse(filename=filename, summary=summary, claims=final_claims)


async def _gather_with_budget_and_progress(
    tasks: List[asyncio.Task],
    budget_seconds: float,
    progress_cb: Optional[ProgressCb],
    total_claims: int,
) -> tuple[list, list]:
    """Run ``tasks`` with a hard wall-clock cap and report progress as they
    finish. Returns ``(results_in_order, pending_tasks)``.
    """
    deadline = time.perf_counter() + budget_seconds
    remaining_tasks = list(tasks)
    results: list = [None] * len(tasks)
    finished = 0

    while remaining_tasks:
        time_left = deadline - time.perf_counter()
        if time_left <= 0:
            break
        done, pending = await asyncio.wait(
            remaining_tasks,
            timeout=time_left,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            try:
                value = task.result()
            except Exception as exc:
                value = exc
            results[tasks.index(task)] = value
            finished += 1
            await _emit(
                progress_cb,
                stage="claim_done",
                done=finished,
                total=total_claims,
            )
        remaining_tasks = list(pending)
        if not pending:
            break

    pending_now = [t for t in remaining_tasks if not t.done()]
    for task in pending_now:
        task.cancel()
    if pending_now:
        # Allow cancellations to settle so event-loop state is clean.
        await asyncio.sleep(0)
    return results, pending_now
