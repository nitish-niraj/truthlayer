"""Unit tests for the RunMetrics observability layer (Phase 11.5)."""

import logging

from core.metrics import RunMetrics


def test_runmetrics_defaults_are_zero():
    m = RunMetrics(filename="x.pdf")
    assert m.filename == "x.pdf"
    assert m.claim_extraction_seconds == 0.0
    assert m.search_seconds == 0.0
    assert m.verdict_seconds == 0.0
    assert m.total_seconds == 0.0
    assert m.search_failures == 0
    assert m.llm_failures == 0
    assert m.rate_limit_count == 0
    assert m.claims_total == 0


def test_runmetrics_finish_records_total_seconds():
    m = RunMetrics(filename="x.pdf")
    m.start()
    m.finish()
    assert m.total_seconds >= 0.0


def test_runmetrics_log_summary_emits_expected_fields(caplog):
    m = RunMetrics(filename="doc.pdf")
    m.claim_extraction_seconds = 0.5
    m.search_seconds = 1.2
    m.verdict_seconds = 2.3
    m.total_seconds = 4.0
    m.search_failures = 1
    m.llm_failures = 0
    m.rate_limit_count = 2
    m.claims_total = 5
    m.claims_verified = 3
    m.claims_inaccurate = 1
    m.claims_false = 1

    with caplog.at_level(logging.INFO, logger="truthlayer"):
        m.log_summary()

    text = " | ".join(r.message for r in caplog.records)
    assert "RunSummary" in text
    assert "file=doc.pdf" in text
    assert "claims=5" in text
    assert "V=3" in text
    assert "I=1" in text
    assert "F=1" in text
    assert "search_failures=1" in text
    assert "rate_limits=2" in text
    assert "avg=0.80s/claim" in text


def test_runmetrics_log_summary_uses_zero_avg_when_no_claims(caplog):
    m = RunMetrics(filename="empty.pdf")
    m.claims_total = 0
    m.total_seconds = 0.5

    with caplog.at_level(logging.INFO, logger="truthlayer"):
        m.log_summary()

    text = " | ".join(r.message for r in caplog.records)
    assert "avg=0.00s/claim" in text


def test_runmetrics_finish_is_idempotent():
    m = RunMetrics(filename="x.pdf")
    m.start()
    m.finish()
    total_first = m.total_seconds
    m.finish()
    # Second finish() should not move total_seconds backward by re-reading perf_counter
    assert m.total_seconds >= total_first
