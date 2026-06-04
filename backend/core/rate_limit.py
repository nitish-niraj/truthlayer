"""Cross-pipeline concurrency control for LLM-bound calls (Phase 11.5).

The NVIDIA Inference API throttles concurrent chat-completions requests; when
more than a handful of verdict calls are in flight at once, the provider returns
HTTP 429 and the calls have to be retried. Limiting concurrency at the
application level keeps us below the throttle ceiling even when many documents
are being verified in parallel.

This module is intentionally tiny: a single shared ``asyncio.Semaphore`` that
``verdict_service`` (and any other LLM call site) acquires before issuing a
chat-completions request. Because the openai SDK is blocking, the semaphore
also serialises the underlying LLM call effectively, even though Python only
sees the entry to the ``async with`` block.

Tuning:
- ``VERDICT_SEMAPHORE_PERMITS`` defaults to ``2`` — well under the observed
  NVIDIA 429 ceiling (~5 concurrent requests) and tuned to stay safe even when
  multiple FastAPI workers are running.
"""

from __future__ import annotations

import asyncio

VERDICT_SEMAPHORE_PERMITS = 2

VERDICT_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(VERDICT_SEMAPHORE_PERMITS)
