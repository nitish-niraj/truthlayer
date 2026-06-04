"""End-to-end verification pipeline (Phase 6 + Phase 11.5).

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

MAX_CONCURRENT_CLAIMS = 5

PIPELINE_FALLBACK_EXPLANATION = "Unable to verify claim."


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

    ``search_claim_with_status`` is synchronous; we offload it to a thread so
    that up to ``MAX_CONCURRENT_CLAIMS`` searches can be in flight
    simultaneously. The cross-pipeline ``VERDICT_SEMAPHORE`` (in
    ``core.rate_limit``) caps concurrent LLM calls separately.
    """
    async with sem:
        try:
            outcome = await asyncio.to_thread(
                search_claim_with_status, claim, metrics
            )
            verification = await generate_verdict(
                claim, outcome.results, outcome.status, metrics
            )
        except Exception as exc:
            logger.warning(f"Pipeline error for claim '{claim.claim[:60]}': {exc}")
            return _defensive_fallback_claim(claim)

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


async def verify_document(text: str, filename: str) -> VerifyResponse:
    """Run the full verification pipeline on extracted document text.

    Never raises. Returns a valid VerifyResponse in every case (including
    empty text, zero claims, and per-claim failures).
    """
    metrics = RunMetrics(filename=filename)
    metrics.start()
    logger.info(f"Document received: {filename} ({len(text)} chars)")

    t_extract_start = time.perf_counter()
    try:
        claims = await extract_claims(text)
    except Exception as exc:
        logger.warning(f"extract_claims raised unexpectedly: {exc}")
        claims = []
    metrics.claim_extraction_seconds = time.perf_counter() - t_extract_start

    if len(claims) > settings.MAX_CLAIMS:
        logger.warning(
            f"Claims truncated: extracted {len(claims)}, "
            f"capped at MAX_CLAIMS={settings.MAX_CLAIMS}"
        )
        claims = claims[: settings.MAX_CLAIMS]

    logger.info(f"Claims extracted: {len(claims)}")

    if not claims:
        logger.info("Verification skipped: no claims extracted")
        metrics.finish()
        metrics.log_summary()
        return VerifyResponse(
            filename=filename,
            summary=SummaryStats(total=0, verified=0, inaccurate=0, false=0),
            claims=[],
        )

    logger.info("Verification started")
    t_verify_start = time.perf_counter()

    sem = asyncio.Semaphore(MAX_CONCURRENT_CLAIMS)
    results: List[VerifiedClaim] = await asyncio.gather(
        *[_process_claim(c, sem, metrics) for c in claims]
    )

    verify_seconds = time.perf_counter() - t_verify_start
    avg_per_claim = verify_seconds / max(len(results), 1)

    for idx, vc in enumerate(results, start=1):
        vc.id = idx

    summary = _summary(results)
    _populate_summary_metrics(summary, metrics)
    metrics.finish()

    logger.info(
        f"Verification completed: total={summary.total} "
        f"verified={summary.verified} inaccurate={summary.inaccurate} "
        f"false={summary.false} in {metrics.total_seconds:.2f}s "
        f"(avg {avg_per_claim:.2f}s/claim)"
    )
    metrics.log_summary()

    return VerifyResponse(filename=filename, summary=summary, claims=results)
