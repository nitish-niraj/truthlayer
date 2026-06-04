"""Unit tests for the search service (Phase 4)."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import Timeout as RequestsTimeout

from models.schemas import ClaimType, ExtractedClaim
from services import search_service
from services.search_service import search_claim


def _claim(text: str = "Apple revenue reached $394B in 2022") -> ExtractedClaim:
    return ExtractedClaim(claim=text, type=ClaimType.financial, source_sentence=text + ".")


def _make_raw(title: str = "T", url: str = "https://example.com", content: str = "C") -> dict:
    return {"title": title, "url": url, "content": content}


def _patch_tavily(monkeypatch, return_value=None, side_effect=None) -> MagicMock:
    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.search.side_effect = side_effect
    else:
        mock_client.search.return_value = return_value or {"results": []}
    monkeypatch.setattr(search_service, "get_tavily_client", lambda: mock_client)
    return mock_client


def test_normal_search_returns_results(monkeypatch):
    raws = [
        _make_raw("Apple FY22 Results", "https://www.apple.com/newsroom/2022", "Revenue was $394.3B."),
        _make_raw("Reuters on Apple", "https://www.reuters.com/article/apple-2022", "Apple reported $394.3B."),
        _make_raw("Random blog", "https://random-blog.example/post-1", "Some commentary."),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 3
    assert {r.url for r in results} == {r["url"] for r in raws}
    # Tier-1 (apple.com) should come before Tier-2 (reuters.com) which should come before Tier-3
    tiers = [search_service._tier_for(r.url) for r in results]
    assert tiers == sorted(tiers)


def test_empty_response_returns_empty_list(monkeypatch):
    _patch_tavily(monkeypatch, return_value={"results": []})

    results = search_claim(_claim())

    assert results == []


def test_duplicate_urls_are_deduplicated(monkeypatch):
    raws = [
        _make_raw("First", "https://www.reuters.com/article/1", "Content one"),
        _make_raw("Duplicate", "https://www.reuters.com/article/1", "Content two"),
        _make_raw("Second", "https://www.bbc.com/news/1", "Content three"),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 2
    assert results[0].title == "First"
    assert results[1].title == "Second"


def test_missing_title_filtered_out(monkeypatch):
    raws = [
        _make_raw(title="", url="https://www.reuters.com/a", content="Good content"),
        _make_raw(title="Valid", url="https://www.bbc.com/b", content="Valid content"),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 1
    assert results[0].title == "Valid"


def test_missing_url_filtered_out(monkeypatch):
    raws = [
        _make_raw(title="No URL", url="", content="Good content"),
        _make_raw(title="Valid", url="https://www.bbc.com/b", content="Valid content"),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 1
    assert results[0].url == "https://www.bbc.com/b"


def test_missing_content_filtered_out(monkeypatch):
    raws = [
        _make_raw(title="No content", url="https://www.reuters.com/a", content=""),
        _make_raw(title="Valid", url="https://www.bbc.com/b", content="Valid content"),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 1
    assert results[0].title == "Valid"


def test_ranking_orders_by_tier(monkeypatch):
    raws = [
        _make_raw("Blog post", "https://random-blog.example/x", "blog content"),
        _make_raw("Gov source", "https://www.sec.gov/filing", "official content"),
        _make_raw("News", "https://www.reuters.com/y", "news content"),
        _make_raw("University", "https://cs.stanford.edu/news", "academic content"),
        _make_raw("Official co", "https://www.apple.com/newsroom", "company content"),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())
    tiers = [search_service._tier_for(r.url) for r in results]

    # Tier 1: sec.gov (gov) + apple.com (official company)
    # Tier 2: reuters.com (reputable publication) + stanford.edu (university)
    # Tier 3: random-blog.example
    assert tiers == [1, 1, 2, 2, 3]
    assert results[0].url == "https://www.sec.gov/filing"


def test_exception_returns_empty_list(monkeypatch):
    _patch_tavily(monkeypatch, side_effect=RuntimeError("Tavily down"))

    results = search_claim(_claim())

    assert results == []


def test_timeout_returns_empty_list(monkeypatch):
    _patch_tavily(monkeypatch, side_effect=RequestsTimeout("read timed out"))

    results = search_claim(_claim())

    assert results == []


def test_content_truncated_to_1000_chars(monkeypatch):
    long_content = "x" * 2000
    raws = [_make_raw("Long", "https://www.reuters.com/long", long_content)]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 1
    assert len(results[0].content) == 1000
    assert results[0].content == "x" * 1000


def test_non_dict_entries_in_results_are_skipped(monkeypatch):
    raws = [
        "not a dict",
        None,
        _make_raw("Valid", "https://www.bbc.com/ok", "ok"),
    ]
    _patch_tavily(monkeypatch, return_value={"results": raws})

    results = search_claim(_claim())

    assert len(results) == 1
    assert results[0].url == "https://www.bbc.com/ok"


def test_tavily_called_with_expected_kwargs(monkeypatch):
    mock_client = _patch_tavily(monkeypatch, return_value={"results": []})

    search_claim(_claim("Tesla delivered 1.8M vehicles in 2023"))

    kwargs = mock_client.search.call_args.kwargs
    assert kwargs["query"] == "Tesla delivered 1.8M vehicles in 2023"
    assert kwargs["search_depth"] == "advanced"
    assert kwargs["include_answer"] is False
    assert kwargs["include_raw_content"] is False
    assert kwargs["max_results"] == pytest.approx(5)
    assert kwargs["timeout"] == pytest.approx(8)
