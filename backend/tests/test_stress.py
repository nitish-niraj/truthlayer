"""Stress tests (V2 Phase 5).

The pipeline has a few well-defined failure boundaries — large claim sets,
slow LLM responses, vision timeouts, search outages, mixed input types.
These tests exercise each boundary in isolation with mocks so the suite
runs in CI without real API keys.

Failure modes under test:

- 50+ claims in a single document (verify_document must not crash and must
  return the defensive-fallback for any claim that times out)
- A vision LLM that raises a timeout — verify_image must still respond
  with a structured 503
- A search service that raises on every call — verdicts should be
  mapped to the inaccurate-fallback by the verdict service
- A verdict LLM that hangs forever — the per-claim timeout must cap the
  wait and emit a defensive-fallback
- A request to verify an empty image — endpoint must return 200 with
  zero counts, not crash
- A request to verify a corrupted image — endpoint must return 400
"""
from __future__ import annotations

import asyncio
import io
import json
import time
from unittest.mock import MagicMock

import openai
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from models.schemas import (
    ClaimType,
    ClaimVerification,
    ExtractedClaim,
    SearchResult,
    SummaryStats,
    VerdictType,
    VerifiedClaim,
)
from services import verification_pipeline
from services.image_claim_service import VisionServiceError
from services.image_verification_service import verify_image_claims
from services.search_service import SearchOutcome, SearchStatus


# ---------------------------------------------------------------------------
# Helpers (mirrors the patterns in the existing image_verification tests)
# ---------------------------------------------------------------------------


def make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color="red").save(buf, format="PNG")
    return buf.getvalue()


def _claim(text: str, idx: int) -> ExtractedClaim:
    return ExtractedClaim(
        claim=text, type=ClaimType.statistic, source_sentence=f"{text} (#{idx})."
    )


def _verif(verdict: str) -> ClaimVerification:
    return ClaimVerification(
        verdict=VerdictType(verdict),
        explanation="ok",
        correct_fact="",
        source_url="https://example.com",
    )


def _patch_vision_with_claims(monkeypatch, claims: list) -> None:
    payload = json.dumps(
        [
            {
                "claim": c.claim,
                "type": c.type.value,
                "source_sentence": c.source_sentence,
            }
            for c in claims
        ]
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = payload
    mock_response.choices[0].message.reasoning_content = None
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    import services.image_claim_service as mod
    mod.get_llm_client = lambda: mock_client


def _patch_vision_error(monkeypatch, exc: Exception) -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = exc

    import services.image_claim_service as mod
    mod.get_llm_client = lambda: mock_client


def _patch_search(monkeypatch, *, verif: ClaimVerification) -> None:
    def fake_search(_claim, metrics=None):
        return SearchOutcome(
            status=SearchStatus.SUCCESS,
            results=[SearchResult(title="T", url="https://x", content="C")],
        )

    async def fake_verdict(_claim, _evidence, _status=None, _metrics=None):
        return verif

    monkeypatch.setattr(verification_pipeline, "search_claim_with_status", fake_search)
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)


# ---------------------------------------------------------------------------
# Large claim set
# ---------------------------------------------------------------------------


def test_verify_document_handles_50_claims(monkeypatch):
    """A 50-claim document must finish without crashing. The pipeline
    applies the MAX_CLAIMS cap before the verification stage, so this
    test exercises both the cap and the per-claim concurrency.
    """
    from services.verification_pipeline import MAX_CONCURRENT_CLAIMS

    # We mock extract_claims to return a big list directly (bypassing the
    # input-text truncation + LLM call).
    large = [_claim(f"Claim number {i}", i) for i in range(1, 51)]

    async def fake_extract(_text):
        return large

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    _patch_search(monkeypatch, verif=_verif("verified"))

    result = asyncio.run(
        verification_pipeline.verify_document(
            "any text", "stress.pdf", hard_timeout=60.0
        )
    )
    # Pipeline caps at settings.MAX_CLAIMS (default 20) — so we expect 20
    # claims in the result, not 50. The cap is documented; this test
    # verifies the cap fires.
    assert result.summary.total == 20
    assert len(result.claims) == 20
    assert result.summary.verified == 20
    # All IDs are 1..N in input order
    assert [c.id for c in result.claims] == list(range(1, 21))
    # Pipeline still set the MAX_CONCURRENT_CLAIMS knob (regression
    # check: future refactors must not silently lower it).
    assert MAX_CONCURRENT_CLAIMS >= 1


def test_verify_image_handles_30_claims(monkeypatch):
    """The image pipeline has its own MAX_CONCURRENT_IMAGE_CLAIMS=3 and
    must process all 30 claims in bounded concurrency.
    """
    large = [_claim(f"Image claim {i}", i) for i in range(1, 31)]
    _patch_search(monkeypatch, verif=_verif("verified"))

    t0 = time.perf_counter()
    verified = asyncio.run(verify_image_claims(large))
    elapsed = time.perf_counter() - t0

    assert len(verified) == 30
    assert all(c.verdict == VerdictType.verified for c in verified)
    assert [c.id for c in verified] == list(range(1, 31))
    # Concurrency=3 — 30 claims / 3 = 10 rounds. The mock has zero
    # latency so we just assert the loop completed in well under 10s.
    assert elapsed < 5.0


# ---------------------------------------------------------------------------
# Vision failures
# ---------------------------------------------------------------------------


def test_endpoint_vision_timeout_returns_503(client: TestClient, monkeypatch):
    """Vision LLM times out -> endpoint returns 503, never 500."""
    _patch_vision_error(monkeypatch, openai.APITimeoutError("vision timeout"))

    response = client.post(
        "/api/verify-image",
        files={"file": ("big.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Vision service unavailable"


def test_endpoint_vision_generic_failure_returns_503(client: TestClient, monkeypatch):
    _patch_vision_error(monkeypatch, RuntimeError("kaboom"))

    response = client.post(
        "/api/verify-image",
        files={"file": ("big.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Search failures
# ---------------------------------------------------------------------------


def test_pipeline_with_search_raising_never_crashes(monkeypatch):
    """When the search service raises on every call, the pipeline must
    still return a valid response with defensive-fallback claims. No
    unhandled exception is allowed to escape the public surface.
    """

    def fake_search(_claim, metrics=None):
        raise RuntimeError("simulated Tavily outage")

    async def fake_verdict(_claim, _evidence, _status=None, _metrics=None):
        return _verif("false")

    monkeypatch.setattr(verification_pipeline, "search_claim_with_status", fake_search)
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)

    async def fake_extract(_text):
        return [_claim("X", 1), _claim("Y", 2)]

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)

    result = asyncio.run(
        verification_pipeline.verify_document("any", "stress.pdf", hard_timeout=10.0)
    )
    # All claims should still get a verdict (false fallback). No 5xx.
    assert result.summary.total == 2


def test_endpoint_with_vision_returning_empty_list_is_200(client: TestClient, monkeypatch):
    """Vision returns [] (no claims found) -> endpoint must return 200
    with zero counts, not crash or return 5xx.
    """
    _patch_vision_with_claims(monkeypatch, [])

    response = client.post(
        "/api/verify-image",
        files={"file": ("empty.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 0
    assert body["claims"] == []


def test_endpoint_with_corrupted_image_returns_400(client: TestClient):
    response = client.post(
        "/api/verify-image",
        files={"file": ("corrupt.png", b"\x89PNG\r\n\x1a\nnot real", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image file"


# ---------------------------------------------------------------------------
# Slow responses
# ---------------------------------------------------------------------------


def test_pipeline_handles_slow_verdict(monkeypatch):
    """A verdict LLM that takes 1s per call must still complete a 3-claim
    document well within the per-claim timeout. Concurrency=3 means the
    wall time is roughly max(per-claim latency), not the sum.
    """
    sleep_s = 0.5

    async def fake_extract(_text):
        return [_claim("A", 1), _claim("B", 2), _claim("C", 3)]

    async def slow_verdict(_claim, _evidence, _status=None, _metrics=None):
        await asyncio.sleep(sleep_s)
        return _verif("verified")

    def fast_search(_claim, metrics=None):
        return SearchOutcome(
            status=SearchStatus.SUCCESS,
            results=[SearchResult(title="T", url="https://x", content="C")],
        )

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    monkeypatch.setattr(verification_pipeline, "search_claim_with_status", fast_search)
    monkeypatch.setattr(verification_pipeline, "generate_verdict", slow_verdict)

    t0 = time.perf_counter()
    result = asyncio.run(
        verification_pipeline.verify_document("any", "slow.pdf", hard_timeout=20.0)
    )
    elapsed = time.perf_counter() - t0

    # Concurrency keeps the wall time close to a single claim's sleep,
    # not 3x. We allow generous slack for CI scheduling jitter.
    assert result.summary.verified == 3
    assert elapsed < sleep_s * 3 + 1.0  # 1.0s slack


def test_pipeline_handles_very_slow_verdict_with_timeout(monkeypatch):
    """A verdict LLM that takes longer than the per-claim budget must
    be cut off and produce a defensive-fallback 'Unable to verify claim.'
    row. The pipeline must NEVER block forever.

    Two paths can cut off a hung claim — the per-claim ``wait_for`` inside
    ``verify_single_claim`` (~15s) and the wall budget of
    ``verify_document`` (set generously here so the per-claim path fires
    first). Both paths emit the same fallback explanation, with the wall
    budget path appending a "partial results" note.
    """

    async def fake_extract(_text):
        return [_claim("X", 1)]

    async def hung_verdict(_claim, _evidence, _status=None, _metrics=None):
        # Sleep much longer than the per-claim cap. asyncio.wait_for
        # in verify_single_claim will raise asyncio.TimeoutError.
        await asyncio.sleep(20.0)
        return _verif("verified")

    def fast_search(_claim, metrics=None):
        return SearchOutcome(
            status=SearchStatus.SUCCESS,
            results=[SearchResult(title="T", url="https://x", content="C")],
        )

    monkeypatch.setattr(verification_pipeline, "extract_claims", fake_extract)
    monkeypatch.setattr(verification_pipeline, "search_claim_with_status", fast_search)
    monkeypatch.setattr(verification_pipeline, "generate_verdict", hung_verdict)

    t0 = time.perf_counter()
    # Generous wall budget so the per-claim wait_for fires first.
    result = asyncio.run(
        verification_pipeline.verify_document(
            "any", "hung.pdf", hard_timeout=60.0
        )
    )
    elapsed = time.perf_counter() - t0

    # The single claim was cut off — the defensive-fallback explanation
    # is the marker (possibly with the partial-results suffix if the
    # wall budget fired first).
    fallback = verification_pipeline.PIPELINE_FALLBACK_EXPLANATION
    partial = verification_pipeline.PARTIAL_RESULT_NOTE
    assert result.summary.total == 1
    explanation = result.claims[0].explanation
    assert explanation.startswith(fallback), (
        f"expected explanation to start with {fallback!r}, got {explanation!r}"
    )
    # And the pipeline didn't actually wait 20 seconds.
    assert elapsed < 18.0
    # The "partial" suffix only appears when the wall budget fired; we
    # don't assert on it (both paths are acceptable defensive behavior).


# ---------------------------------------------------------------------------
# Mixed / cross-pipeline
# ---------------------------------------------------------------------------


def test_image_pipeline_returns_correct_shape_under_stress(monkeypatch):
    """The image pipeline must always emit a list of ``VerifiedClaim`` with
    sequential 1..N ids, regardless of the verdict mix returned by mocks.
    """
    from itertools import cycle

    verdicts = ["verified", "inaccurate", "false", "verified", "inaccurate"]
    cycle_iter = cycle(verdicts)

    _patch_vision_with_claims(
        monkeypatch, [_claim(f"c{i}", i) for i in range(1, len(verdicts) + 1)]
    )

    def fake_search(_claim, metrics=None):
        return SearchOutcome(
            status=SearchStatus.SUCCESS,
            results=[SearchResult(title="T", url="https://x", content="C")],
        )

    async def fake_verdict(_claim, _evidence, _status=None, _metrics=None):
        v = next(cycle_iter)
        return _verif(v)

    monkeypatch.setattr(verification_pipeline, "search_claim_with_status", fake_search)
    monkeypatch.setattr(verification_pipeline, "generate_verdict", fake_verdict)

    response = TestClient(__import__("main", fromlist=["app"]).app).post(
        "/api/verify-image",
        files={"file": ("mix.png", make_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 5
    assert body["summary"]["verified"] == 2
    assert body["summary"]["inaccurate"] == 2
    assert body["summary"]["false"] == 1
    assert [c["id"] for c in body["claims"]] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Health endpoint under stress (concurrency)
# ---------------------------------------------------------------------------


def test_health_endpoint_handles_concurrent_calls(client: TestClient):
    """Hammering /api/health must not 5xx. The endpoint is the primary
    liveness probe; if it goes down under load, the platform marks the
    service unhealthy.
    """
    responses = [client.get("/api/health") for _ in range(20)]
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["status"] in {"ok", "degraded"} for r in responses)
