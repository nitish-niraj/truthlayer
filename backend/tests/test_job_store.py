"""Tests for the in-memory job store (Phase 13)."""

import asyncio
import time

import pytest

from services.job_store import JobStatus, JobStore


def _new_store() -> JobStore:
    return JobStore()


def test_create_returns_unique_ids():
    s = _new_store()
    a = s.create()
    b = s.create()
    assert a.job_id != b.job_id
    assert a.status == JobStatus.PENDING
    assert b.status == JobStatus.PENDING


def test_lifecycle_pending_running_completed():
    s = _new_store()
    job = s.create()
    assert s.get(job.job_id) is job

    s.mark_running(job.job_id)
    assert job.status == JobStatus.RUNNING
    assert job.started_at is not None

    s.update_progress(job.job_id, stage="extraction", claims=3)
    assert job.progress == {"stage": "extraction", "claims": 3}

    s.mark_completed(job.job_id, {"summary": "ok"})
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"summary": "ok"}
    assert job.finished_at is not None


def test_lifecycle_partial():
    s = _new_store()
    job = s.create()
    s.mark_running(job.job_id)
    s.mark_partial(job.job_id, {"summary": "partial"})
    assert job.status == JobStatus.PARTIAL
    assert job.result == {"summary": "partial"}


def test_lifecycle_failed():
    s = _new_store()
    job = s.create()
    s.mark_running(job.job_id)
    s.mark_failed(job.job_id, "boom")
    assert job.status == JobStatus.FAILED
    assert job.error == "boom"


def test_to_dict_shape():
    s = _new_store()
    job = s.create()
    s.mark_running(job.job_id)
    s.update_progress(job.job_id, done=2, total=5)
    s.mark_completed(job.job_id, {"x": 1})
    d = job.to_dict()
    assert d["job_id"] == job.job_id
    assert d["status"] == "completed"
    assert d["result"] == {"x": 1}
    assert d["progress"] == {"done": 2, "total": 5}
    assert d["elapsed_seconds"] is not None


def test_evict_expired_removes_old_jobs(monkeypatch):
    s = _new_store()
    job = s.create()
    # Backdate the job past the TTL.
    job.created_at = time.time() - (s.JOB_TTL_SECONDS + 10)
    evicted = s.evict_expired()
    assert evicted == 1
    assert s.get(job.job_id) is None


def test_evict_expired_keeps_recent_jobs():
    s = _new_store()
    job = s.create()
    evicted = s.evict_expired()
    assert evicted == 0
    assert s.get(job.job_id) is job


def test_sweeper_runs_and_cancels_cleanly():
    async def _run():
        s = _new_store()
        s.JOB_SWEEP_INTERVAL_SECONDS = 0.05
        await s.start_sweeper()
        await asyncio.sleep(0.15)
        await s.stop_sweeper()

    asyncio.run(_run())
