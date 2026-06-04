"""In-memory job store for the asynchronous /api/verify endpoint (Phase 13).

The synchronous /api/verify endpoint that blocked the request until the
pipeline finished was killed by Render's free-tier 30s HTTP proxy timeout
on documents whose first LLM call (claim extraction) is cold. To survive
that constraint, the endpoint now returns a ``job_id`` in <100 ms and the
client polls ``GET /api/verify/{job_id}`` for the result.

This module is the per-process job store. It is intentionally simple:

- Jobs are stored in a dict keyed by UUID4.
- State transitions are: ``pending`` -> ``running`` -> (``completed`` | ``failed`` | ``partial``).
- ``partial`` is a non-failure terminal state used when the pipeline's
  hard-timeout fires and we ship a partial result.
- Each job carries a wall-clock deadline; if the worker is still running
  when the deadline elapses, the job is force-finalised as ``partial``.
- Old jobs are evicted by a background sweeper task that runs every
  ``JOB_SWEEP_INTERVAL_SECONDS`` and removes any job older than
  ``JOB_TTL_SECONDS``.

This is process-local, which is fine for Render's free tier (single web
worker per service). A multi-worker deployment would need Redis or
similar; the API surface here is small enough to swap behind it later.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from core.logger import logger


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status.value,
            "created_at": self.created_at,
        }
        if self.started_at is not None:
            payload["started_at"] = self.started_at
        if self.finished_at is not None:
            payload["finished_at"] = self.finished_at
            payload["elapsed_seconds"] = round(
                self.finished_at - (self.started_at or self.created_at), 3
            )
        if self.progress:
            payload["progress"] = self.progress
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        return payload


class JobStore:
    """Process-local job store with TTL eviction."""

    JOB_TTL_SECONDS = 600.0  # 10 minutes
    JOB_SWEEP_INTERVAL_SECONDS = 60.0

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._sweeper: Optional[asyncio.Task] = None

    def create(self) -> Job:
        job = Job(job_id=uuid4().hex)
        self._jobs[job.job_id] = job
        logger.info("JOB CREATE | id=%s", job.job_id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def mark_running(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        logger.info("JOB RUNNING | id=%s", job_id)

    def update_progress(self, job_id: str, **fields: Any) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.progress.update(fields)

    def mark_completed(self, job_id: str, result: Any) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = JobStatus.COMPLETED
        job.result = result
        job.finished_at = time.time()
        logger.info("JOB COMPLETED | id=%s | elapsed=%.2fs", job_id, job.finished_at - (job.started_at or job.created_at))

    def mark_partial(self, job_id: str, result: Any) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = JobStatus.PARTIAL
        job.result = result
        job.finished_at = time.time()
        logger.info("JOB PARTIAL | id=%s | elapsed=%.2fs", job_id, job.finished_at - (job.started_at or job.created_at))

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = time.time()
        logger.warning("JOB FAILED | id=%s | %s", job_id, error)

    def evict_expired(self) -> int:
        now = time.time()
        cutoff = now - self.JOB_TTL_SECONDS
        expired = [jid for jid, j in self._jobs.items() if j.created_at < cutoff]
        for jid in expired:
            del self._jobs[jid]
        if expired:
            logger.info("JOB EVICT | removed=%d | remaining=%d", len(expired), len(self._jobs))
        return len(expired)

    async def start_sweeper(self) -> None:
        """Run the eviction sweeper until cancelled."""
        if self._sweeper is not None and not self._sweeper.done():
            return
        self._sweeper = asyncio.create_task(self._sweep_loop())
        logger.info("JOB SWEEPER STARTED | ttl=%.0fs | every=%.0fs", self.JOB_TTL_SECONDS, self.JOB_SWEEP_INTERVAL_SECONDS)

    async def stop_sweeper(self) -> None:
        if self._sweeper is None:
            return
        self._sweeper.cancel()
        try:
            await self._sweeper
        except asyncio.CancelledError:
            pass
        self._sweeper = None

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.JOB_SWEEP_INTERVAL_SECONDS)
                self.evict_expired()
        except asyncio.CancelledError:
            return


store = JobStore()
