"""Unit tests for the verdict service (Phase 5)."""

import asyncio
import json
from unittest.mock import MagicMock

from models.schemas import ClaimType, ExtractedClaim, SearchResult
from services import verdict_service
from services.verdict_service import SAFE_FALLBACK, generate_verdict


def _claim(text: str = "OpenAI was founded in 2020") -> ExtractedClaim:
    return ExtractedClaim(claim=text, type=ClaimType.date, source_sentence=text + ".")


def _evidence(*titles_urls_contents: tuple[str, str, str]) -> list[SearchResult]:
    if not titles_urls_contents:
        return [
            SearchResult(
                title="Default source",
                url="https://www.reuters.com/default",
                content="Default content for tests.",
            )
        ]
    return [
        SearchResult(title=t, url=u, content=c)
        for t, u, c in titles_urls_contents
    ]


def _patch_llm(monkeypatch, content: str | None = None, side_effect: Exception | None = None) -> MagicMock:
    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.chat.completions.create.side_effect = side_effect
    else:
        mock_response = MagicMock()
        mock_response.choices[0].message.content = content
        mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(verdict_service, "get_llm_client", lambda: mock_client)
    return mock_client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_verified_response(monkeypatch):
    payload = json.dumps(
        {
            "verdict": "verified",
            "explanation": "Apple reported revenue of $394.3B in FY2022.",
            "correct_fact": "",
            "source_url": "https://www.apple.com/newsroom/",
        }
    )
    _patch_llm(monkeypatch, content=payload)

    result = asyncio.run(generate_verdict(_claim("Apple revenue reached $394B in 2022"), _evidence()))

    assert result.verdict.value == "verified"
    assert result.correct_fact == ""
    assert result.source_url == "https://www.apple.com/newsroom/"


def test_inaccurate_response(monkeypatch):
    payload = json.dumps(
        {
            "verdict": "inaccurate",
            "explanation": "The figure was once true but has since been updated.",
            "correct_fact": "The 2023 figure is approximately 1.81 million vehicles.",
            "source_url": "https://www.cnbc.com/article",
        }
    )
    _patch_llm(monkeypatch, content=payload)

    result = asyncio.run(generate_verdict(_claim("Tesla delivered 1.5M vehicles in 2023"), _evidence()))

    assert result.verdict.value == "inaccurate"
    assert "1.81" in result.correct_fact
    assert result.source_url == "https://www.cnbc.com/article"


def test_false_response(monkeypatch):
    payload = json.dumps(
        {
            "verdict": "false",
            "explanation": "OpenAI was founded in December 2015, not 2020.",
            "correct_fact": "OpenAI was founded in December 2015.",
            "source_url": "https://openai.com/about",
        }
    )
    _patch_llm(monkeypatch, content=payload)

    result = asyncio.run(generate_verdict(_claim("OpenAI was founded in 2020"), _evidence()))

    assert result.verdict.value == "false"
    assert "2015" in result.correct_fact
    assert result.source_url == "https://openai.com/about"


# ---------------------------------------------------------------------------
# JSON recovery
# ---------------------------------------------------------------------------


def test_markdown_wrapped_json(monkeypatch):
    inner = json.dumps(
        {
            "verdict": "verified",
            "explanation": "Matches.",
            "correct_fact": "",
            "source_url": "https://x",
        }
    )
    wrapped = f"```json\n{inner}\n```"
    _patch_llm(monkeypatch, content=wrapped)

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result.verdict.value == "verified"


def test_extra_text_around_json(monkeypatch):
    inner = json.dumps(
        {
            "verdict": "false",
            "explanation": "Contradicted.",
            "correct_fact": "Correct fact.",
            "source_url": "https://x",
        }
    )
    noisy = f"Here is my verdict:\n{inner}\nHope this helps."
    _patch_llm(monkeypatch, content=noisy)

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result.verdict.value == "false"
    assert result.correct_fact == "Correct fact."


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_malformed_json_returns_safe_fallback(monkeypatch):
    _patch_llm(monkeypatch, content="I cannot determine the verdict from this evidence.")

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result == SAFE_FALLBACK
    assert result.verdict.value == "false"
    assert result.correct_fact == ""
    assert result.source_url == ""


def test_empty_response_returns_safe_fallback(monkeypatch):
    _patch_llm(monkeypatch, content="")

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result == SAFE_FALLBACK


def test_llm_call_failure_returns_safe_fallback(monkeypatch):
    _patch_llm(monkeypatch, side_effect=RuntimeError("NVIDIA API down"))

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result == SAFE_FALLBACK


def test_invalid_pydantic_shape_returns_safe_fallback(monkeypatch):
    # Missing required fields -> ValidationError
    payload = json.dumps({"verdict": "verified"})
    _patch_llm(monkeypatch, content=payload)

    result = asyncio.run(generate_verdict(_claim(), _evidence()))

    assert result == SAFE_FALLBACK


# ---------------------------------------------------------------------------
# Branch coverage
# ---------------------------------------------------------------------------


def test_empty_evidence_skips_llm_call(monkeypatch):
    mock_client = _patch_llm(monkeypatch, content="should not be called")

    result = asyncio.run(generate_verdict(_claim(), []))

    assert result.verdict.value == "false"
    assert "No evidence" in result.explanation
    mock_client.chat.completions.create.assert_not_called()


def test_prompt_contains_all_evidence_sources(monkeypatch):
    captured: dict = {}

    def capture(**kwargs):
        captured["messages"] = kwargs.get("messages")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            {
                "verdict": "verified",
                "explanation": "ok",
                "correct_fact": "",
                "source_url": "https://www.reuters.com/article/x",
            }
        )
        return mock_response

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = capture
    monkeypatch.setattr(verdict_service, "get_llm_client", lambda: mock_client)

    evidence = _evidence(
        ("Reuters says X", "https://www.reuters.com/article/x", "X is true"),
        ("CNBC says Y", "https://www.cnbc.com/article/y", "Y is also true"),
    )
    asyncio.run(generate_verdict(_claim("Test claim"), evidence))

    sent = captured["messages"][0]["content"]
    assert "Reuters says X" in sent
    assert "https://www.reuters.com/article/x" in sent
    assert "CNBC says Y" in sent
    assert "https://www.cnbc.com/article/y" in sent
    assert "Test claim" in sent


def test_llm_called_with_expected_kwargs(monkeypatch):
    mock_client = _patch_llm(
        monkeypatch,
        content=json.dumps(
            {"verdict": "verified", "explanation": "x", "correct_fact": "", "source_url": ""}
        ),
    )

    asyncio.run(generate_verdict(_claim(), _evidence()))

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.1
    assert kwargs["top_p"] == 1.0
    assert kwargs["max_tokens"] == 1024
    assert kwargs["stream"] is False
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"thinking": False}}
    assert kwargs["model"] == "moonshotai/kimi-k2.6"
