# TruthLayer — Final Summary

> Final release candidate of **TruthLayer** — an AI-powered PDF fact
> verification platform.

---

## Project Overview

TruthLayer is a full-stack web app that reads a PDF document, extracts
every verifiable factual claim, retrieves live web evidence for each
claim, and asks an LLM to render an evidence-backed verdict
(`verified` / `inaccurate` / `false`).

The result is a structured report — one verdict per claim — with
plain-English explanations, the corrected fact (when applicable), and
the source URLs that informed each judgement.

**Why it matters:** long PDF reports (market research, compliance
filings, vendor whitepapers, internal audits) routinely contain stale
or incorrect figures. A human fact-check takes hours per document.
TruthLayer does the same audit in under a minute and produces a
shareable report.

---

## Architecture Summary

```
                   ┌────────────────────────────────────────────┐
                   │  Browser (React 18 + Vite + Tailwind)      │
                   │  Upload → Processing → Results → Export    │
                   └──────────────────┬─────────────────────────┘
                                      │  POST /api/verify
                                      │  (returns job_id in <100ms)
                                      ▼
                   ┌────────────────────────────────────────────┐
                   │  FastAPI backend (Render free tier)        │
                   │  ─────────────────                         │
                   │  1. extract_claims  (Kimi K2.6 + thinking) │
                   │  2. search_claim   (Tavily, top 5)         │
                   │  3. generate_verdict (Kimi K2.6, no think) │
                   │                                            │
                   │  Background-job pattern:                   │
                   │  POST returns job_id, client polls for     │
                   │  live progress and final result.           │
                   │  asyncio.Semaphore(3) + to_thread          │
                   │  for non-blocking LLM calls.               │
                   └──────────┬─────────────────────┬──────────┘
                              │                     │
                              ▼                     ▼
                   ┌──────────────────┐  ┌────────────────────┐
                   │  NVIDIA  /v1     │  │  Tavily search API │
                   │  (Kimi K2.6)     │  │  (advanced, top 5) │
                   └──────────────────┘  └────────────────────┘
```

Two independent deployable units — a **FastAPI** backend and a **Vite +
React** frontend — communicating over a typed JSON contract defined in
`backend/models/schemas.py`.

---

## Features

| Feature | Status |
|---|---|
| **PDF Upload** | Drag-and-drop with PDF-only validation and 10 MB size cap |
| **Text Extraction** | PyMuPDF, multi-page, validated against magic bytes |
| **Claim Extraction** | Kimi K2.6 with thinking, JSON-recovery, per-item validation |
| **Evidence Search** | Tavily advanced, top 5, dedupe, tier ranking, content truncation |
| **Verdict Generation** | Kimi K2.6 thinking-off, evidence-consensus reasoning, JSON-only output |
| **Verification Dashboard** | Per-claim verdicts with explanations, corrected facts, and source URLs |
| **Summary Statistics** | Total / verified / inaccurate / false counts |
| **Export Report** | Print-formatted verification report (View + Export) |
| **Production Monitoring** | Per-request timing, structured logs, `RunMetrics` per document |
| **Resilient Pipeline** | Tavily retry/backoff, LLM retry/backoff, defensive-fallback per claim |
| **Background Jobs** | POST returns `job_id` in <100 ms; pipeline runs out-of-band |
| **CORS** | Vercel + localhost allowed |
| **StrictMode Safe** | React StrictMode re-mounts are absorbed without firing duplicate requests |

---

## Deployment Links

| Surface | URL |
|---|---|
| **Frontend (live)** | [https://truthlayernitish.vercel.app](https://truthlayernitish.vercel.app) |
| **Backend (live)** | [https://truthlayer-backend-c6u0.onrender.com](https://truthlayer-backend-c6u0.onrender.com) |
| **API docs (live)** | [https://truthlayer-backend-c6u0.onrender.com/docs](https://truthlayer-backend-c6u0.onrender.com/docs) |
| **GitHub repo** | [https://github.com/nitish-niraj/truthlayer](https://github.com/nitish-niraj/truthlayer) |

### Deployment configuration

- **Backend** — Render free tier, single web worker, `uvicorn main:app
  --host 0.0.0.0 --port $PORT`. Configuration in `render.yaml`. Health
  check on `/api/health`.
- **Frontend** — Vercel, root `frontend/`, build `npm run build` →
  `dist/`. `VITE_API_URL` env points at the Render backend.
- **CI trigger** — `git push origin main` redeploys both services.

---

## Testing Summary

**Backend test suite:** `pytest tests/ -v` → **98 passed, 0 failed.**

Coverage by file:

| File | Cases | Covers |
|---|---|---|
| `test_upload.py` | 5 | PDF validation, magic bytes, size limits, empty PDFs |
| `test_claim_extraction.py` | 7 | LLM JSON parsing, fence stripping, mixed records |
| `test_claim_json_recovery.py` | 9 | Bracket-matching JSON recovery from prose |
| `test_search_service.py` | 11 | Tavily ranking, dedupe, truncation, exception handling |
| `test_search_outcome.py` | 16 | Outcome status + transient-error retry + metrics |
| `test_verdict_service.py` | 12 | LLM verdict parsing, safe-fallback, empty evidence |
| `test_verdict_retry.py` | 10 | LLM 5xx, 429, rate-limit retry, metrics |
| `test_verification_pipeline.py` | 11 | Concurrency, summary, defensive-fallback, hard timeout |
| `test_metrics.py` | 5 | `RunMetrics` aggregation |
| `test_job_store.py` | 8 | Job lifecycle, TTL eviction, sweeper |
| `test_verify_jobs.py` | 3 | Background-job endpoints (POST + GET + 404) |

**Frontend build:** `npm run build` → built cleanly with no warnings
related to the application code.

**Production smoke test:** the live deployment accepts a PDF, runs the
full pipeline, and returns a complete verdict report in under a minute.

---

## Deployment Summary

- **Backend cold start** — Render free tier sleeps after 15 min idle.
  First request takes ~30 s to wake; subsequent requests are fast.
- **Pipeline wall time** — typical 5-claim document finishes in 30-60 s
  end-to-end on a warm instance. The background-job pattern keeps the
  HTTP request <100 ms and the polling loop bridges the gap.
- **Frontend assets** — Vite bundle, gzip 152 kB JS / 4 kB CSS.
- **External dependencies** — NVIDIA Inference API (Kimi K2.6) +
  Tavily Search. Both have retry/backoff on transient failures.

---

## Lessons Learned

1. **Background jobs are non-negotiable on Render's free tier.** The
   synchronous `POST /api/verify` that blocked until the pipeline
   finished was killed by Render's 30 s reverse-proxy HTTP timeout
   whenever the LLM cold-start pushed the pipeline past that wall. The
   fix — POST returns a `job_id` in <100 ms and the client polls
   `GET /api/verify/{job_id}` for live progress and the final result —
   decouples the request lifetime from the pipeline lifetime.

2. **Blocking calls inside `async def` freeze the event loop.** The
   openai SDK's `client.chat.completions.create(...)` is synchronous.
   Calling it directly from an `async def` coroutine blocks the entire
   FastAPI event loop for 2-10 s, which in turn blocks every polling
   GET request from the same client. Wrapping the call in
   `asyncio.to_thread(...)` (with the `VERDICT_SEMAPHORE` still held
   for the duration) keeps the LLM slot count correct and frees the
   event loop for everything else.

3. **Defensive fallbacks at every layer.** The pipeline must never
   fail at the document level. A failed LLM call returns a
   `ClaimVerification(verdict="false", …)`, a failed search returns an
   `inaccurate` (not `false`) so a network outage doesn't get
   mislabelled as a fabricated claim, and a crashed `_run_verify_job`
   marks the job as `failed` with a human-readable error so the client
   can show something useful.

4. **Pydantic v2 + pydantic-settings + structured env files** give a
   cheap, type-safe configuration layer. The one-time settings load at
   import time means test fixtures have to set env vars *before* the
   import — `tests/conftest.py` does this with `os.environ.setdefault`.

5. **Tailwind v3 with `tailwind.config.cjs` + `postcss.config.cjs`**
   works exactly as expected. The Build Guide's mention of the v4
   `@tailwindcss/vite` plugin is stale; the v3 classic pipeline is
   the source of truth.

6. **In-memory state is fine for a single-worker demo, but breaks
   immediately when scaled out.** `JobStore` is process-local. Render
   free tier is one worker, so this is fine in production today, but
   the moment a multi-worker deployment is attempted, jobs disappear
   across requests. A swap-in for Redis would be a one-day refactor.

---

## Future Improvements

- **Streaming verification** — server-sent events so verdicts appear
  claim-by-claim instead of waiting for the full pipeline to finish.
- **Multi-document analysis** — drop several PDFs at once and compare
  claims across them.
- **Batch processing** — background queue for large document sets.
- **Team collaboration** — shared workspaces, comments, and
  verification history.
- **Persistent history** — per-user dashboards of past runs (currently
  in-memory; would need a database on Render).
- **Source-tier visualisation** — diversity score and tier badges on
  every evidence card.

---

## Author

**Nitish Kumar**

Final release candidate of TruthLayer.

- Live: [truthlayernitish.vercel.app](https://truthlayernitish.vercel.app)
- Repo: [github.com/nitish-niraj/truthlayer](https://github.com/nitish-niraj/truthlayer)
