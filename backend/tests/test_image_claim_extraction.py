"""Tests for POST /api/extract-image-claims (V2 Phase 2)."""
import asyncio
import io
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from services.image_claim_service import (
    VisionServiceError,
    extract_claims_from_image,
)


def make_png_bytes(color: str = "red", size=(16, 16)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _patch_llm_content(content: str) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response.choices[0].message.reasoning_content = None
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    import services.image_claim_service as mod
    mod.get_llm_client = lambda: mock_client


def _patch_llm_error(exc: Exception) -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = exc

    import services.image_claim_service as mod
    mod.get_llm_client = lambda: mock_client


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_extract_claims_from_image_happy_path(monkeypatch):
    payload = json.dumps(
        [
            {
                "claim": "ChatGPT has 100 million users.",
                "type": "statistic",
                "source_sentence": "ChatGPT has 100 million users.",
            },
            {
                "claim": "OpenAI was founded in 2020.",
                "type": "date",
                "source_sentence": "OpenAI was founded in 2020.",
            },
        ]
    )
    _patch_llm_content(payload)

    claims = asyncio.run(
        extract_claims_from_image(
            make_png_bytes(), "shot.png", "image/png"
        )
    )

    assert len(claims) == 2
    assert claims[0].claim == "ChatGPT has 100 million users."
    assert claims[0].type.value == "statistic"
    assert claims[1].type.value == "date"


def test_extract_claims_markdown_fence(monkeypatch):
    inner = json.dumps(
        [
            {
                "claim": "iPhone accounts for 52% of sales.",
                "type": "statistic",
                "source_sentence": "The iPhone accounts for 52% of sales.",
            }
        ]
    )
    wrapped = f"```json\n{inner}\n```"
    _patch_llm_content(wrapped)

    claims = asyncio.run(
        extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
    )

    assert len(claims) == 1
    assert claims[0].claim.startswith("iPhone")


def test_extract_claims_empty_array(monkeypatch):
    _patch_llm_content("[]")

    claims = asyncio.run(
        extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
    )

    assert claims == []


def test_extract_claims_malformed_json(monkeypatch):
    _patch_llm_content("Sorry, I cannot analyze this image.")

    claims = asyncio.run(
        extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
    )

    assert claims == []


def test_extract_claims_mixed_valid_invalid(monkeypatch):
    payload = json.dumps(
        [
            {
                "claim": "Valid claim",
                "type": "statistic",
                "source_sentence": "Valid claim.",
            },
            {"bad": "no claim field", "type": "statistic"},
            "not a dict",
        ]
    )
    _patch_llm_content(payload)

    claims = asyncio.run(
        extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
    )

    assert len(claims) == 1
    assert claims[0].claim == "Valid claim"


def test_extract_claims_unknown_type_coerced(monkeypatch):
    """Model sometimes returns types outside the enum — coerce to a safe default."""
    payload = json.dumps(
        [
            {
                "claim": "Model X achieved 99.9% accuracy.",
                "type": "performance_metric",  # not in the enum
                "source_sentence": "Model X achieved 99.9% accuracy.",
            }
        ]
    )
    _patch_llm_content(payload)

    claims = asyncio.run(
        extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
    )

    assert len(claims) == 1
    assert claims[0].type.value == "statistic"  # safe fallback


def test_extract_visions_service_error_raised_on_timeout(monkeypatch):
    import openai
    _patch_llm_error(openai.APITimeoutError("vision timeout"))

    with pytest.raises(VisionServiceError):
        asyncio.run(
            extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
        )


def test_extract_visions_service_error_raised_on_generic_failure(monkeypatch):
    _patch_llm_error(RuntimeError("network blip"))

    with pytest.raises(VisionServiceError):
        asyncio.run(
            extract_claims_from_image(make_png_bytes(), "x.png", "image/png")
        )


# ---------------------------------------------------------------------------
# Endpoint-level tests
# ---------------------------------------------------------------------------


def test_endpoint_returns_extracted_claims(client: TestClient, monkeypatch):
    payload = json.dumps(
        [
            {
                "claim": "Tesla delivered 1.8M vehicles in 2023.",
                "type": "financial",
                "source_sentence": "Tesla delivered 1.8M vehicles in 2023.",
            }
        ]
    )
    _patch_llm_content(payload)

    response = client.post(
        "/api/extract-image-claims",
        files={"file": ("chart.png", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "chart.png"
    assert len(body["claims"]) == 1
    assert body["claims"][0]["claim"] == "Tesla delivered 1.8M vehicles in 2023."
    assert body["claims"][0]["type"] == "financial"


def test_endpoint_returns_empty_list_when_no_claims(client: TestClient, monkeypatch):
    _patch_llm_content("[]")

    response = client.post(
        "/api/extract-image-claims",
        files={"file": ("blank.png", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "blank.png"
    assert body["claims"] == []


def test_endpoint_returns_503_on_vision_failure(client: TestClient, monkeypatch):
    import openai
    _patch_llm_error(openai.APITimeoutError("vision timeout"))

    response = client.post(
        "/api/extract-image-claims",
        files={"file": ("chart.png", make_png_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Vision service unavailable"


def test_endpoint_rejects_unsupported_format(client: TestClient):
    response = client.post(
        "/api/extract-image-claims",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Supported formats: PNG, JPG, JPEG, WEBP"


def test_endpoint_rejects_corrupted_image(client: TestClient):
    response = client.post(
        "/api/extract-image-claims",
        files={"file": ("bad.png", b"\x89PNG\r\n\x1a\nnot a real png", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image file"
