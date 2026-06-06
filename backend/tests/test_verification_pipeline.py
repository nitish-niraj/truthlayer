"""Unit tests for the end-to-end verification pipeline (Phase 6 + 11.5)."""

import asyncio
import json
import logging

import pytest

from models.schemas import (
    ClaimType,
    ClaimVerification,
    ExtractedClaim,
    SearchResult,
    SummaryStats,
    VerdictType,
)
from services import verification_pipeline
from services.search_service import SearchOutcome, SearchStatus
from services.verification_pipeline import (
    MAX_CONCURRENT_CLAIMS,
    PIPELINE_FALLBACK_EXPLANATION,
    verify_document,
)


def _claim(text: str = "Apple revenue reached $394B in 2022", id: int = 1) -> ExtractedClaim:
    return ExtractedClaim(
        claim=text, type=ClaimType.financial, source_sentence=text + "."
    )


def _evidence(url: str = "https://www.reuters.com/article/1") -> list[SearchResult]:
    return [SearchResult(title="T", url=url, content="C")]


def _verif(
    verdict: str = "verified",
    explanation: str = "ok",
    correct_fact: str = "",
    source_url: str = "https://www.reuters.com/article/1",
) -> ClaimVerification:
    return ClaimVerification(
        verdict=VerdictType(verdict),
        explanation=explanation,
        correct_fact=correct_fact,
        source_url=source_url,
    )


def _patch(monkeypatch, claims=None, evidence=None, verif=None, exc=None):
    """Patch the three service functions the pipeline calls.

    If `exc` is set, search_claim_with_status raises it (used to exercise the
    defensive fallback path). Otherwise it returns a SearchOutcome wrapping
    `evidence or _evidence()`.
    """
    if claims is not None:
        async def fake_extract(_text):
            return claims
        monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)

    if exc is not None:
        def fake_search(_claim, metrics=None):
            raise exc
    else:
        ev = evidence if evidence is not None else _evidence()
        def fake_search(_claim, metrics=None):
            status = SearchStatus.SUCCESS if ev else SearchStatus.EMPTY
            return SearchOutcome(status=status, results=ev)
    monkeypatch.setattr(
        verification_pipeline, "search_claim_with_status", fake_search
    )

    if verif is None:
        async def fake_verdict(_claim, _evidence, _status=None, _metrics=None):
            return _verif()
    else:
        async def fake_verdict(_claim, _evidence, _status=None, _metrics=None):
            return verif
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_normal_workflow_with_three_claims(monkeypatch):
    claims = [_claim("Apple revenue reached $394B in 2022"), _claim("Tesla delivered 1.8M vehicles in 2023"), _claim("Nvidia market cap $3T in 2024")]
    _patch(monkeypatch, claims=claims)

    result = asyncio.run(verify_document("doc text", "doc.pdf"))

    assert result.filename == "doc.pdf"
    assert result.summary.total == 3
    assert result.summary.verified == 3
    assert result.summary.inaccurate == 0
    assert result.summary.false == 0
    assert len(result.claims) == 3
    assert [c.id for c in result.claims] == [1, 2, 3]
    assert all(c.verdict == VerdictType.verified for c in result.claims)


def test_zero_claims_returns_empty_response(monkeypatch):
    _patch(monkeypatch, claims=[])

    result = asyncio.run(verify_document("doc text", "doc.pdf"))

    assert result.filename == "doc.pdf"
    assert result.summary == SummaryStats(total=0, verified=0, inaccurate=0, false=0)
    assert result.claims == []


def test_one_failed_claim_does_not_fail_document(monkeypatch, monkeypatch_caplog=None):
    # Two of three claims succeed; one raises inside search so the
    # defensive fallback kicks in for that one.
    claims = [
        _claim("A is true"),
        _claim("B is false"),  # this one will raise
        _claim("C is true"),
    ]
    # Use a list to control per-claim behaviour.
    call_count = {"n": 0}

    async def fake_extract(_text):
        return claims

    def fake_search(_claim, metrics=None):
        call_count["n"] += 1
        if "B is false" in _claim.claim:
            raise RuntimeError("Tavily down for this claim")
        return SearchOutcome(status=SearchStatus.SUCCESS, results=_evidence())

    async def fake_verdict(_claim, _evidence, _status=None, _metrics=None):
        return _verif()

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    monkeypatch.setattr(
        verification_pipeline, "search_claim_with_status", fake_search
    )
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)

    result = asyncio.run(verify_document("doc text", "doc.pdf"))

    assert result.summary.total == 3
    assert result.summary.verified == 2
    assert result.summary.false == 1
    failed = [c for c in result.claims if c.verdict == VerdictType.false]
    assert len(failed) == 1
    assert failed[0].explanation == PIPELINE_FALLBACK_EXPLANATION
    assert failed[0].correct_fact == ""
    assert failed[0].source_url == ""
    assert failed[0].id in (1, 2, 3)


def test_summary_counts_for_mixed_verdicts(monkeypatch):
    claims = [_claim(f"Claim {i}") for i in range(5)]
    verdicts = ["verified", "inaccurate", "false", "verified", "false"]

    async def fake_extract(_text):
        return claims

    def fake_search(_claim, metrics=None):
        return SearchOutcome(status=SearchStatus.SUCCESS, results=_evidence())

    async def fake_verdict(claim, _evidence, _status=None, _metrics=None):
        return _verif(verdict=verdicts[int(claim.claim.split()[-1])])

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    monkeypatch.setattr(
        verification_pipeline, "search_claim_with_status", fake_search
    )
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)

    result = asyncio.run(verify_document("doc", "doc.pdf"))

    assert result.summary.total == 5
    assert result.summary.verified == 2
    assert result.summary.inaccurate == 1
    assert result.summary.false == 2


def test_response_structure_matches_schema(monkeypatch):
    claims = [_claim("X")]
    _patch(monkeypatch, claims=claims)

    result = asyncio.run(verify_document("doc", "doc.pdf"))

    assert set(result.model_dump().keys()) == {"filename", "summary", "claims", "processing_time_seconds"}
    # processing_time_seconds is set by the router layer, not by the
    # pipeline itself. The pipeline must always leave it as None.
    assert result.processing_time_seconds is None
    assert set(result.summary.model_dump().keys()) == {"total", "verified", "inaccurate", "false"}
    assert set(result.claims[0].model_dump().keys()) == {
        "id", "claim", "type", "source_sentence", "verdict", "explanation", "correct_fact", "source_url"
    }


# ---------------------------------------------------------------------------
# Id assignment, caps, edge cases
# ---------------------------------------------------------------------------


def test_id_assignment_is_sequential_one_indexed(monkeypatch):
    claims = [_claim(f"Claim {i}") for i in range(4)]
    _patch(monkeypatch, claims=claims)

    result = asyncio.run(verify_document("doc", "doc.pdf"))

    assert [c.id for c in result.claims] == [1, 2, 3, 4]


def test_max_claims_is_enforced(monkeypatch, monkeypatch_value=None):
    # Set MAX_CLAIMS low so the test is fast and obvious.
    monkeypatch.setattr(verification_pipeline.settings, "MAX_CLAIMS", 3)

    claims = [_claim(f"Claim {i}") for i in range(10)]
    _patch(monkeypatch, claims=claims)

    result = asyncio.run(verify_document("doc", "doc.pdf"))

    assert len(result.claims) == 3
    assert result.summary.total == 3


def test_empty_evidence_short_circuits_to_false(monkeypatch):
    claims = [_claim("Unsupported claim")]

    async def fake_extract(_text):
        return claims

    def fake_search(_claim, metrics=None):
        return SearchOutcome(status=SearchStatus.EMPTY, results=[])

    async def fake_verdict(claim, evidence, status=None, metrics=None):
        # The real verdict_service short-circuits on empty evidence; mirror it.
        if not evidence:
            return ClaimVerification(
                verdict=VerdictType.false,
                explanation="No evidence found to evaluate this claim.",
                correct_fact="",
                source_url="",
            )
        return _verif()

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    monkeypatch.setattr(
        verification_pipeline, "search_claim_with_status", fake_search
    )
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)

    result = asyncio.run(verify_document("doc", "doc.pdf"))

    assert result.summary.false == 1
    assert "No evidence" in result.claims[0].explanation


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_performance_logging_emits_timings(monkeypatch, caplog):
    claims = [_claim("A"), _claim("B")]
    _patch(monkeypatch, claims=claims)

    with caplog.at_level(logging.INFO, logger="truthlayer"):
        asyncio.run(verify_document("doc", "doc.pdf"))

    messages = " | ".join(r.message for r in caplog.records)
    assert "VERIFY REQUEST RECEIVED" in messages
    assert "CLAIM EXTRACTION FINISHED" in messages
    assert "2 claims" in messages
    assert "VERIFICATION STARTED" in messages
    assert "VERIFICATION COMPLETED" in messages
    assert "total=2" in messages
    assert "verified=2" in messages
    assert "inaccurate=0" in messages
    assert "false=0" in messages
    assert "s/claim" in messages


def test_max_concurrent_claims_constant():
    # Sanity check — if someone bumps the cap, they should know.
    # Phase 12: lowered from 5 to 3 to stay under Render's 30s free-tier
    # proxy timeout on a typical 5-claim document.
    assert MAX_CONCURRENT_CLAIMS == 3


def test_hard_timeout_returns_partial_results(monkeypatch):
    """When the hard timeout elapses mid-pipeline, we ship the claims that
    have finished and replace the rest with defensive fallbacks."""
    claims = [_claim(f"Claim {i}") for i in range(4)]

    async def fake_extract(_text):
        return claims

    async def slow_verdict(_claim, _evidence, _status=None, _metrics=None):
        # Sleep longer than the budget we will pass.
        await asyncio.sleep(2.0)
        from models.schemas import ClaimVerification, VerdictType
        return ClaimVerification(
            verdict=VerdictType.verified,
            explanation="ok",
            correct_fact="",
            source_url="https://x",
        )

    def fake_search(_claim, metrics=None):
        return SearchOutcome(status=SearchStatus.SUCCESS, results=_evidence())

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    monkeypatch.setattr(
        verification_pipeline, "search_claim_with_status", fake_search
    )
    monkeypatch.setattr(verification_pipeline, "generate_verdict", slow_verdict)

    # 0.1s budget guarantees the per-claim stage cannot complete in time.
    result = asyncio.run(verify_document("doc", "doc.pdf", hard_timeout=0.1))

    # We still get a valid shape with 4 claims (3 fallback + 1 maybe-finished).
    assert result.summary.total == 4
    assert all(c.id in (1, 2, 3, 4) for c in result.claims)
    # At least one claim should be a defensive fallback.
    fallbacks = [c for c in result.claims if "Unable to verify" in c.explanation]
    assert len(fallbacks) >= 1
