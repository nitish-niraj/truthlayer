"""Unit tests for robust JSON-array recovery in claim extraction (Phase 11.5)."""

import asyncio
import json

from services.claim_service import _parse_json_array


def _claim_payload() -> str:
    return json.dumps(
        [
            {"claim": "C1", "type": "statistic", "source_sentence": "C1."},
        ]
    )


# ---------------------------------------------------------------------------
# Bracket-matching recovery
# ---------------------------------------------------------------------------


def test_parse_recovers_from_prose_preamble():
    raw = "Sure! Here are the claims I found:\n" + _claim_payload()
    data = _parse_json_array(raw)
    assert len(data) == 1
    assert data[0]["claim"] == "C1"


def test_parse_recovers_from_trailing_commentary():
    raw = _claim_payload() + "\n\nHope this helps!"
    data = _parse_json_array(raw)
    assert len(data) == 1


def test_parse_recovers_from_prose_on_both_sides():
    raw = (
        "Here is my answer:\n"
        + _claim_payload()
        + "\nLet me know if you need more."
    )
    data = _parse_json_array(raw)
    assert len(data) == 1


def test_parse_picks_first_array_when_multiple_present():
    payload_1 = json.dumps([{"a": 1}])
    payload_2 = json.dumps([{"b": 2}])
    raw = f"{payload_1} and {payload_2}"
    data = _parse_json_array(raw)
    # The first balanced [...] wins, which is {"a": 1}
    assert data == [{"a": 1}]


def test_parse_handles_nested_brackets():
    raw = json.dumps(
        [{"claim": "C", "type": "statistic", "source_sentence": "S", "extra": {"a": 1}}]
    )
    data = _parse_json_array(raw)
    assert len(data) == 1


def test_parse_handles_markdown_fence_with_prose():
    raw = "```json\n" + _claim_payload() + "\n```"
    data = _parse_json_array(raw)
    assert len(data) == 1


def test_parse_handles_markdown_fence_with_prose_around():
    raw = "Here is the answer:\n```json\n" + _claim_payload() + "\n```\nDone."
    data = _parse_json_array(raw)
    assert len(data) == 1


def test_parse_returns_empty_list_for_clean_empty():
    assert _parse_json_array("[]") == []


def test_parse_raises_for_unparseable_response():
    import pytest

    with pytest.raises(ValueError):
        _parse_json_array("No JSON here at all.")
