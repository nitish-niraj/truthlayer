import asyncio
import json
from unittest.mock import MagicMock

from services.claim_service import extract_claims


def _patch_llm_content(monkeypatch, content: str) -> None:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("services.claim_service.get_llm_client", lambda: mock_client)


def _patch_llm_error(monkeypatch, exc: Exception) -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = exc
    monkeypatch.setattr("services.claim_service.get_llm_client", lambda: mock_client)


def test_valid_json_output(monkeypatch):
    payload = json.dumps(
        [
            {
                "claim": "Apple revenue reached $394B in 2022",
                "type": "financial",
                "source_sentence": "Apple revenue reached $394B in 2022.",
            }
        ]
    )
    _patch_llm_content(monkeypatch, payload)

    claims = asyncio.run(extract_claims("Some long document text"))

    assert len(claims) == 1
    assert claims[0].claim == "Apple revenue reached $394B in 2022"
    assert claims[0].type.value == "financial"
    assert claims[0].source_sentence == "Apple revenue reached $394B in 2022."


def test_markdown_wrapped_json(monkeypatch):
    inner = json.dumps(
        [
            {
                "claim": "iPhone accounts for 52% of sales",
                "type": "statistic",
                "source_sentence": "The iPhone accounts for 52% of sales.",
            }
        ]
    )
    wrapped = f"```json\n{inner}\n```"
    _patch_llm_content(monkeypatch, wrapped)

    claims = asyncio.run(extract_claims("Some long document text"))

    assert len(claims) == 1
    assert claims[0].type.value == "statistic"


def test_invalid_json(monkeypatch):
    _patch_llm_content(monkeypatch, "Sorry, I cannot extract claims from this text.")

    claims = asyncio.run(extract_claims("Some long document text"))

    assert claims == []


def test_empty_response(monkeypatch):
    _patch_llm_content(monkeypatch, "[]")

    claims = asyncio.run(extract_claims("Some long document text"))

    assert claims == []


def test_mixed_valid_invalid_records(monkeypatch):
    payload = json.dumps(
        [
            {"claim": "Valid one", "type": "statistic", "source_sentence": "Valid one."},
            {"claim": "Missing type", "source_sentence": "Invalid."},
            "not a dict at all",
            {"claim": "Bad type", "type": "unknown", "source_sentence": "Invalid."},
            {"claim": "Another valid", "type": "date", "source_sentence": "Another valid."},
        ]
    )
    _patch_llm_content(monkeypatch, payload)

    claims = asyncio.run(extract_claims("Some long document text"))

    assert len(claims) == 2
    assert claims[0].claim == "Valid one"
    assert claims[1].claim == "Another valid"


def test_llm_call_failure(monkeypatch):
    _patch_llm_error(monkeypatch, RuntimeError("NVIDIA API down"))

    claims = asyncio.run(extract_claims("Some long document text"))

    assert claims == []


def test_input_is_truncated_to_8000_chars(monkeypatch):
    long_text = "x" * 10000
    captured: dict = {}

    def capture(**kwargs):
        captured["messages"] = kwargs.get("messages")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"
        return mock_response

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = capture
    monkeypatch.setattr("services.claim_service.get_llm_client", lambda: mock_client)

    asyncio.run(extract_claims(long_text))

    sent = captured["messages"][0]["content"]
    assert "x" * 8000 in sent
    assert "x" * 8001 not in sent
