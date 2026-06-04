"""Per-document observability for the verification pipeline (Phase 11.5).

A ``RunMetrics`` instance is created at the top of ``verify_document`` and is
mutated by the search and verdict services as each claim flows through the
pipeline. At the end of the run, the pipeline calls ``RunMetrics.log_summary``
to emit a single structured log line with the document filename, claim counts,
timings, and failure counters.

Design notes:
- This is **per-run**, not process-global. A new instance is created for every
  request, which is what the user-facing log line needs.
- All fields are best-effort; services only observe if a metrics object is
  passed to them. Existing call sites that don't yet pass metrics will simply
  record zero for those fields.
- No external dependency (Prometheus, statsd, etc.) — we log to the existing
  ``truthlayer`` logger and let whatever log pipeline Render/Vercel provides
  aggregate the values.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from core.logger import logger


@dataclass
class RunMetrics:
    """Mutable bag of counters and timers for one verify_document invocation."""

    filename: str

    claim_extraction_seconds: float = 0.0
    search_seconds: float = 0.0
    verdict_seconds: float = 0.0
    total_seconds: float = 0.0

    search_failures: int = 0
    llm_failures: int = 0
    rate_limit_count: int = 0

    claims_total: int = 0
    claims_verified: int = 0
    claims_inaccurate: int = 0
    claims_false: int = 0

    # Internal: wall-clock for total_seconds. Set automatically on first touch.
    _t0: Optional[float] = field(default=None, init=False, repr=False)

    def start(self) -> None:
        """Mark the start of the run. Idempotent — safe to call multiple times."""
        if self._t0 is None:
            self._t0 = time.perf_counter()

    def finish(self) -> None:
        """Record total_seconds if not already set, based on the start timestamp."""
        if self._t0 is None:
            self._t0 = time.perf_counter()
        self.total_seconds = time.perf_counter() - self._t0

    def log_summary(self) -> None:
        """Emit a single structured log line describing this run."""
        avg = (self.total_seconds / self.claims_total) if self.claims_total else 0.0
        logger.info(
            "RunSummary | file=%s | claims=%d (V=%d I=%d F=%d) "
            "| extract=%.2fs search=%.2fs verdict=%.2fs total=%.2fs "
            "(avg=%.2fs/claim) | search_failures=%d llm_failures=%d rate_limits=%d",
            self.filename,
            self.claims_total,
            self.claims_verified,
            self.claims_inaccurate,
            self.claims_false,
            self.claim_extraction_seconds,
            self.search_seconds,
            self.verdict_seconds,
            self.total_seconds,
            avg,
            self.search_failures,
            self.llm_failures,
            self.rate_limit_count,
        )


__all__ = ["RunMetrics"]
