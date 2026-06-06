"""Image claim verification service (V2 Phase 3).

Responsibility: take a list of ``ExtractedClaim`` (already extracted from an
image by :mod:`services.image_claim_service`) and run them through the SAME
search + verdict engine the PDF pipeline uses, concurrently.

Hard constraints for this phase:

- No new search engine. Uses :func:`services.search_service.search_claim_with_status`
  through the :func:`services.verification_pipeline.verify_single_claim` primitive.
- No new verdict engine. Uses :func:`services.verdict_service.generate_verdict`
  through the same primitive.
- No new summary code. Uses :func:`services.verification_pipeline.summarize_verified_claims`.

Failure policy: per-claim failures (timeout, search outage, LLM error) are
swallowed inside ``verify_single_claim`` and surfaced as defensive-fallback
``VerifiedClaim`` rows. The router therefore never has to handle per-claim
exceptions; an empty input list yields a zero-count response.
"""
import asyncio
import time
from typing import List

from core.logger import logger
from models.schemas import (
    ExtractedClaim,
    SummaryStats,
    VerifiedClaim,
)
from services.verification_pipeline import (
    summarize_verified_claims,
    verify_single_claim,
)

# Per-claim concurrency cap. Matches the PDF pipeline's MAX_CONCURRENT_CLAIMS
# in verification_pipeline so the LLM and Tavily providers see roughly the
# same load whether the input was a PDF or an image.
MAX_CONCURRENT_IMAGE_CLAIMS = 3


async def verify_image_claims(
    claims: List[ExtractedClaim],
) -> List[VerifiedClaim]:
    """Verify every claim concurrently and return the results in input order.

    Each claim is run through :func:`verify_single_claim`, which encapsulates
    the search + verdict stage with a per-claim timeout and a defensive
    fallback on any error. Concurrency is bounded by a local semaphore so
    we never queue more than ``MAX_CONCURRENT_IMAGE_CLAIMS`` claims in
    flight at once (the cross-pipeline ``VERDICT_SEMAPHORE`` inside
    ``verdict_service`` is the global LLM cap and is acquired downstream).

    The function never raises. An empty input list returns ``[]``.
    """
    if not claims:
        return []

    logger.info(
        "IMAGE VERIFICATION STARTED | %d claims | concurrency=%d",
        len(claims),
        MAX_CONCURRENT_IMAGE_CLAIMS,
    )
    t0 = time.perf_counter()

    sem = asyncio.Semaphore(MAX_CONCURRENT_IMAGE_CLAIMS)

    async def _bounded(claim: ExtractedClaim) -> VerifiedClaim:
        async with sem:
            return await verify_single_claim(claim)

    verified: List[VerifiedClaim] = list(
        await asyncio.gather(*(_bounded(c) for c in claims))
    )

    # Re-number the IDs 1..N in the same input order so the response matches
    # the contract used by the PDF pipeline (where verify_document does the
    # same renumbering at the end).
    for idx, vc in enumerate(verified, start=1):
        vc.id = idx

    elapsed = time.perf_counter() - t0
    summary = summarize_verified_claims(verified)
    logger.info(
        "IMAGE VERIFICATION COMPLETED | total=%d verified=%d inaccurate=%d "
        "false=%d | %.2fs (avg %.2fs/claim)",
        summary.total,
        summary.verified,
        summary.inaccurate,
        summary.false,
        elapsed,
        elapsed / max(len(claims), 1),
    )
    return verified


def summarize(claims: List[VerifiedClaim]) -> SummaryStats:
    """Thin alias so router code reads cleanly. Reuses the PDF pipeline's
    summary counter to guarantee a single source of truth for the math.
    """
    return summarize_verified_claims(claims)
