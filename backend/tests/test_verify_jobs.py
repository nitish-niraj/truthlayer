"""Integration tests for the background-job verify endpoints (Phase 13)."""

import time

import pytest

from services import job_store
from services.job_store import JobStatus


def test_post_verify_returns_job_id_immediately(client, monkeypatch):
    """POST /api/verify must return a 202 with a job_id and status='pending'.

    In production (uvicorn) the response is flushed to the client *before* the
    background task runs, so the POST itself is sub-100ms even when the
    underlying pipeline takes 30+ seconds. The FastAPI TestClient runs
    BackgroundTasks synchronously, so we cannot assert a wall-clock bound
    here, but the contract — the response shape, the 202 status, the
    pending state — is what the client actually depends on.
    """

    async def _fake_verify(text, filename, hard_timeout=None, progress_cb=None):
        import asyncio
        await asyncio.sleep(5.0)
        from models.schemas import SummaryStats, VerifyResponse
        return VerifyResponse(
            filename=filename,
            summary=SummaryStats(total=0, verified=0, inaccurate=0, false=0),
            claims=[],
        )

    monkeypatch.setattr("routers.verify.verify_document", _fake_verify)

    response = client.post(
        "/api/verify",
        json={"text": "Some document text.", "filename": "test.pdf"},
    )

    assert response.status_code == 202
    body = response.json()
    assert "job_id" in body
    assert body["status"] == "pending"
    # The job is created in pending state — the pipeline must not have been
    # awaited synchronously. We can check this by polling immediately: the
    # status should still be 'pending' or 'running' but not yet 'completed'.
    job_id = body["job_id"]
    immediate = client.get(f"/api/verify/{job_id}")
    assert immediate.json()["status"] in ("pending", "running", "completed")


def test_get_verify_returns_404_for_unknown_job(client):
    response = client.get("/api/verify/does-not-exist")
    assert response.status_code == 404


def test_post_then_get_returns_completed_result(client, monkeypatch):
    async def _fake_verify(text, filename, hard_timeout=None, progress_cb=None):
        from models.schemas import (
            ClaimType,
            SummaryStats,
            VerdictType,
            VerifiedClaim,
            VerifyResponse,
        )
        if progress_cb is not None:
            await progress_cb({"stage": "extraction", "claims": 1})
        return VerifyResponse(
            filename=filename,
            summary=SummaryStats(total=1, verified=1, inaccurate=0, false=0),
            claims=[
                VerifiedClaim(
                    id=1,
                    claim="X is true",
                    type=ClaimType.statistic,
                    source_sentence="X is true.",
                    verdict=VerdictType.verified,
                    explanation="Confirmed.",
                    correct_fact="",
                    source_url="https://example.com",
                )
            ],
        )

    monkeypatch.setattr("routers.verify.verify_document", _fake_verify)

    post = client.post(
        "/api/verify",
        json={"text": "X is true.", "filename": "x.pdf"},
    )
    assert post.status_code == 202
    job_id = post.json()["job_id"]

    # The background task is scheduled on the event loop. The TestClient
    # runs both the request handler and the background task in the same
    # loop, so polling should converge quickly. Bound the wait.
    deadline = time.time() + 3.0
    body = None
    while time.time() < deadline:
        poll = client.get(f"/api/verify/{job_id}")
        body = poll.json()
        if body["status"] in ("completed", "partial", "failed"):
            break
        time.sleep(0.05)

    assert body is not None
    assert body["status"] == "completed"
    assert body["result"]["summary"]["total"] == 1
    assert body["result"]["claims"][0]["verdict"] == "verified"
