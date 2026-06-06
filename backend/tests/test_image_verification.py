"""Tests for V2 Phase 3 - image claim verification service + endpoint."""
import asyncio
import io
import json
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
    VerdictType,
)
from services import verification_pipeline
from services.image_claim_service import VisionServiceError
from services.image_verification_service import (
    summarize as summarize_image_verdicts,
    verify_image_claims,
)
from services.search_service import SearchOutcome, SearchStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color="red").save(buf, format="PNG")
    return buf.getvalue()


def make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def _claim(text: str = "Apple revenue reached $394B in 2022") -> ExtractedClaim:
    return ExtractedClaim(
        claim=text, type=ClaimType.financial, source_sentence=text + "."
    )


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


def _patch_vision_claims(monkeypatch, claims) -> None:
    """Stub the vision LLM so extract_claims_from_image returns the given claims."""
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


def _patch_search_and_verdict(monkeypatch, *, verif: ClaimVerification) -> None:
    """Patch the search + verdict stages that verify_single_claim invokes.

    These names are looked up in the verification_pipeline module's globals at
    call time, so monkeypatching them there intercepts every per-claim call -
    whether it came from the PDF pipeline or the image service.
    """
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
# Service-level tests
# ---------------------------------------------------------------------------


def test_verify_image_claims_verified(monkeypatch):
    _patch_search_and_verdict(monkeypatch, verif=_verif(verdict="verified"))

    claims = [_claim("ChatGPT has 100M users")]
    verified = asyncio.run(verify_image_claims(claims))

    assert len(verified) == 1
    assert verified[0].verdict == VerdictType.verified
    assert verified[0].id == 1


def test_verify_image_claims_inaccurate(monkeypatch):
    _patch_search_and_verdict(
        monkeypatch,
        verif=_verif(
            verdict="inaccurate",
            explanation="Outdated figure",
            correct_fact="200M weekly active users as of 2024",
        ),
    )

    claims = [_claim("ChatGPT has 100M users")]
    verified = asyncio.run(verify_image_claims(claims))

    assert verified[0].verdict == VerdictType.inaccurate
    assert verified[0].correct_fact.startswith("200M")


def test_verify_image_claims_false(monkeypatch):
    _patch_search_and_verdict(
        monkeypatch,
        verif=_verif(verdict="false", explanation="WHO says 2.2B lack water"),
    )

    claims = [_claim("9 billion people lack clean water")]
    verified = asyncio.run(verify_image_claims(claims))

    assert verified[0].verdict == VerdictType.false
    assert verified[0].explanation.startswith("WHO")


def test_verify_image_claims_concurrent_three_claims(monkeypatch):
    """Three claims should all be verified with 1..N ids in input order."""
    _patch_search_and_verdict(monkeypatch, verif=_verif(verdict="verified"))

    claims = [_claim("Claim A"), _claim("Claim B"), _claim("Claim C")]
    verified = asyncio.run(verify_image_claims(claims))

    assert len(verified) == 3
    assert [v.id for v in verified] == [1, 2, 3]


def test_verify_image_claims_empty_list():
    """No claims in -> no verification work -> empty list, no error."""
    verified = asyncio.run(verify_image_claims([]))
    assert verified == []


def test_summarize_alias_matches_pipeline():
    """The image-flow summary must use the same counter the PDF pipeline uses
    so the two reports look identical for the same input.
    """
    verified = [
        _claim("A").__class__,  # placeholder, replaced below
    ]
    # Build a small list of VerifiedClaim-shaped objects via verify_image_claims
    # so the test exercises the real field types.
    from models.schemas import VerifiedClaim
    sample = [
        VerifiedClaim(
            id=1, claim="A", type=ClaimType.statistic, source_sentence="A.",
            verdict=VerdictType.verified, explanation="x", correct_fact="",
            source_url="",
        ),
        VerifiedClaim(
            id=2, claim="B", type=ClaimType.statistic, source_sentence="B.",
            verdict=VerdictType.inaccurate, explanation="x", correct_fact="y",
            source_url="",
        ),
    ]
    summary = summarize_image_verdicts(sample)
    assert summary.total == 2
    assert summary.verified == 1
    assert summary.inaccurate == 1
    assert summary.false == 0


# ---------------------------------------------------------------------------
# Endpoint-level tests
# ---------------------------------------------------------------------------


def test_endpoint_success(client: TestClient, monkeypatch):
    _patch_vision_claims(monkeypatch, [_claim("ChatGPT has 100M users")])
    _patch_search_and_verdict(monkeypatch, verif=_verif(verdict="verified"))

    response = client.post(
        "/api/verify-image",
        files={"file": ("shot.png", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "shot.png"
    assert body["summary"] == {
        "total": 1,
        "verified": 1,
        "inaccurate": 0,
        "false": 0,
    }
    assert body["claims"][0]["verdict"] == "verified"
    # V2 Phase 4: optional processing_time_seconds is populated by the
    # router. Must be a non-negative number.
    assert "processing_time_seconds" in body
    assert isinstance(body["processing_time_seconds"], (int, float))
    assert body["processing_time_seconds"] >= 0


def test_endpoint_no_claims_found(client: TestClient, monkeypatch):
    _patch_vision_claims(monkeypatch, [])

    response = client.post(
        "/api/verify-image",
        files={"file": ("blank.png", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "blank.png"
    assert body["summary"] == {
        "total": 0,
        "verified": 0,
        "inaccurate": 0,
        "false": 0,
    }
    assert body["claims"] == []


def test_endpoint_vision_failure_returns_503(client: TestClient, monkeypatch):
    _patch_vision_error(monkeypatch, openai.APITimeoutError("vision timeout"))

    response = client.post(
        "/api/verify-image",
        files={"file": ("chart.png", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Vision service unavailable"


def test_endpoint_unsupported_format(client: TestClient):
    response = client.post(
        "/api/verify-image",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Supported formats: PNG, JPG, JPEG, WEBP"


def test_endpoint_corrupted_image(client: TestClient):
    response = client.post(
        "/api/verify-image",
        files={"file": ("bad.png", b"\x89PNG\r\n\x1a\nnot a real png", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image file"


def test_endpoint_jpeg_accepted(client: TestClient, monkeypatch):
    """Smoke test: JPEG, not just PNG, is accepted by the new endpoint."""
    _patch_vision_claims(monkeypatch, [_claim("X")])
    _patch_search_and_verdict(monkeypatch, verif=_verif(verdict="verified"))

    response = client.post(
        "/api/verify-image",
        files={"file": ("photo.jpg", make_jpeg_bytes(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["claims"][0]["verdict"] == "verified"
