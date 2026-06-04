# TruthLayer

> AI-powered PDF fact-checking. Upload a document, get every factual claim
> verified, sourced, and labeled **verified** / **inaccurate** / **false** in
> under a minute.

Repository: [https://github.com/nitish-niraj/truthlayer](https://github.com/nitish-niraj/truthlayer)

Future frontend: [https://truthlayernitish.vercel.app](https://truthlayernitish.vercel.app)

[![Status](https://img.shields.io/badge/status-v1.0-22C55E)](#what-is-truthlayer)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688)](#tech-stack)
[![Frontend](https://img.shields.io/badge/frontend-React%2018%20%2B%20Vite-61DAFB)](#tech-stack)
[![Tests](https://img.shields.io/badge/tests-86%20passed-22C55E)](#testing)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](#tech-stack)
[![License](https://img.shields.io/badge/license-pending-yellow)](#license)

---

## Table of contents
- [What is TruthLayer?](#what-is-truthlayer)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [API endpoints](#api-endpoints)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Deployment](#deployment)
- [How a claim is verified](#how-a-claim-is-verified)
- [Screenshots](#screenshots)
- [Roadmap](#roadmap)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## What is TruthLayer?

TruthLayer is an **end-to-end fact-verification pipeline** for PDF documents.
It reads a document, extracts every factual claim it contains, retrieves live
web evidence for each claim, and asks an LLM to render a verdict.

The result is a structured report — one verdict per claim — with explanations,
correct facts (when applicable), and the source URLs that informed each
judgement.

It is built for:
- **Researchers and journalists** who need to audit long reports quickly.
- **Product, legal, and compliance teams** that want a second pair of eyes on
  vendor / partner / market-research documents.
- **Anyone** who has ever finished a 60-page PDF and wondered *"wait, is that
  number actually true?"*

---

## Features

- **One-click PDF upload** — drag-drop a PDF, watch the analysis run.
- **Live web evidence** — every claim is cross-referenced against fresh web
  results from Tavily before a verdict is rendered.
- **Per-claim verdicts** — `verified` (green) / `inaccurate` (amber) /
  `false` (red), with plain-English explanations and source URLs.
- **Tier-ranked sources** — government, international, and academic sources
  are ranked above general news, which is ranked above the long tail.
- **Resilient pipeline** — Tavily and LLM calls retry on transient errors
  with exponential backoff; a search outage does not get mislabelled as
  "false".
- **Strict-mode safe** — React StrictMode duplicate mounts are absorbed
  without firing duplicate requests.
- **Clean dashboard** — summary statistics, per-claim cards, shareable
  verification report export.
- **QA harness** — 86 pytest cases covering every service, retry path, and
  pipeline edge case.

---

## Architecture

```
                  ┌────────────────────────────────────────────┐
                  │  Browser (React 18 + Vite + Tailwind)      │
                  │  Upload → Processing → Results → Export    │
                  └──────────────────┬─────────────────────────┘
                                     │  POST /api/verify
                                     ▼
                  ┌────────────────────────────────────────────┐
                  │  FastAPI backend                           │
                  │  ─────────────────                         │
                  │  1. extract_claims  (Kimi K2.6 + thinking) │
                  │  2. search_claim   (Tavily, top 5)         │
                  │  3. generate_verdict (Kimi K2.6, no think) │
                  │                                            │
                  │  Semaphore(5) + asyncio.to_thread          │
                  │  for blocking Tavily calls                 │
                  └──────────┬─────────────────────┬──────────┘
                             │                     │
                             ▼                     ▼
                  ┌──────────────────┐  ┌────────────────────┐
                  │  NVIDIA  /v1     │  │  Tavily search API │
                  │  (Kimi K2.6)     │  │  (advanced, top 5) │
                  └──────────────────┘  └────────────────────┘
```

Two independent deployable units: a **FastAPI** backend and a **Vite + React**
frontend, communicating over a typed JSON contract defined in
`backend/models/schemas.py`.

---

## Tech stack

### Backend
| Tool | Version | Purpose |
|---|---|---|
| FastAPI | 0.116.1 | Web framework |
| Uvicorn | 0.48.0 | ASGI server |
| Pydantic | 2.13.0 | Data models & validation |
| Pydantic-Settings | 2.14.1 | Environment configuration |
| OpenAI SDK | 2.36.0 | NVIDIA OpenAI-compatible LLM client |
| Tavily Python | 0.7.24 | Live web search |
| PyMuPDF | ≥ 1.24.10 | PDF text extraction |
| pytest | 8.4.2 | Test runner |
| httpx | 0.28.1 | TestClient backend |

### Frontend
| Tool | Version | Purpose |
|---|---|---|
| React / React DOM | 18.2 | UI library |
| Vite | 5.x | Dev server & build |
| Tailwind CSS | 3.5 | Styling (utility-first) |
| Framer Motion | 11.x | Animations |
| Axios | 1.4 | HTTP client |
| react-dropzone | 14.x | PDF drag-drop |
| lucide-react | 0.383 | Icons |

---

## Local setup

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** and **npm**
- API keys for [NVIDIA](https://build.nvidia.com/) (Kimi K2.6) and
  [Tavily](https://tavily.com/).

### 1. Clone the repository
```bash
git clone https://github.com/nitish-niraj/truthlayer.git
cd truthlayer
```

### 2. Backend
```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env          # then edit with your real API keys
uvicorn main:app --reload --port 8000
```

Backend now serves on `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

### 3. Frontend
```bash
cd ../frontend
npm install
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm run dev
```

Frontend now serves on `http://localhost:5173` and talks to the backend
automatically.

---

## Environment variables

### `backend/.env`
| Key | Description | Example |
|---|---|---|
| `NVIDIA_API_KEY` | NVIDIA / Kimi K2.6 API key | `nvapi-...` |
| `TAVILY_API_KEY` | Tavily search API key | `tvly-...` |
| `FRONTEND_URL` | Allowed CORS origin | `http://localhost:5173` |
| `MAX_FILE_SIZE_MB` | Upload size cap | `10` |
| `MAX_CLAIMS` | Max claims processed per document | `20` |
| `MAX_SEARCH_RESULTS` | Tavily results per claim | `5` |
| `SEARCH_TIMEOUT_SECONDS` | Tavily per-claim timeout | `15` |
| `CLAIM_EXTRACTION_MAX_TOKENS` | LLM token cap (claim extraction) | `2048` |
| `CLAIM_EXTRACTION_TIMEOUT_SECONDS` | LLM timeout (claim extraction) | `60` |
| `CLAIM_EXTRACTION_TEMPERATURE` | LLM temperature (claim extraction) | `0.1` |

> **Security:** `backend/.env` is git-ignored. Never commit real keys. The
> repository ships with `backend/.env.example` and `frontend/.env.example`
> containing placeholders only.

### `frontend/.env`
| Key | Description | Example |
|---|---|---|
| `VITE_API_URL` | Backend base URL | `http://localhost:8000` |

---

## API endpoints

All endpoints are defined in `backend/routers/verify.py` and return typed
Pydantic models from `backend/models/schemas.py`.

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | Liveness check — returns `{"status":"ok","version":"1.0"}` |
| `POST` | `/api/upload` | Upload a PDF, extract its text (PyMuPDF) |
| `POST` | `/api/extract-claims` | LLM: extract `ExtractedClaim[]` from text |
| `POST` | `/api/search-claim` | Tavily: ranked evidence for a single claim |
| `POST` | `/api/generate-verdict` | LLM: verdict for a claim + evidence list |
| `POST` | `/api/verify-claim` | Pipeline: search + verdict for a single claim |
| `POST` | `/api/verify` | **Pipeline: end-to-end verification for a document** |

`/api/verify` accepts `{ "text": "...", "filename": "..." }` and returns a
`VerifyResponse` with summary statistics and per-claim `VerifiedClaim`
records.

---

## Project structure

```
truthlayer/
├── backend/                          ← FastAPI (Python)
│   ├── main.py                       ← CORS + include_router
│   ├── Procfile                      ← Render start command
│   ├── requirements.txt              ← pinned versions
│   ├── .env.example                  ← placeholder env (committed)
│   ├── core/
│   │   ├── config.py                 ← pydantic-settings Settings
│   │   ├── logger.py                 ← "[ts] LEVEL msg" logger
│   │   ├── llm_client.py             ← OpenAI(NVIDIA) singleton
│   │   ├── rate_limit.py             ← asyncio Semaphore wrapper
│   │   └── metrics.py                ← per-run RunMetrics
│   ├── routers/
│   │   └── verify.py                 ← all /api/* routes
│   ├── services/
│   │   ├── pdf_service.py            ← PyMuPDF extraction
│   │   ├── claim_service.py          ← LLM claim extraction + JSON recovery
│   │   ├── search_service.py         ← Tavily search + retry/backoff
│   │   ├── verdict_service.py        ← LLM verdict + retry/backoff
│   │   └── verification_pipeline.py  ← async orchestrator (Semaphore(5))
│   ├── models/
│   │   └── schemas.py                ← all Pydantic models
│   ├── utils/
│   │   └── file_validation.py        ← extension, magic bytes, size
│   └── tests/                        ← 86 pytest cases
│
├── frontend/                         ← React 18 + Vite (JavaScript)
│   ├── vite.config.js
│   ├── tailwind.config.cjs
│   ├── postcss.config.cjs
│   ├── .env.example
│   ├── package.json
│   ├── package-lock.json
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                   ← screen state machine
│       ├── index.css                 ← Tailwind + design tokens
│       ├── components/               ← UI primitives
│       ├── screens/                  ← Upload / Processing / Results / Error
│       ├── services/api.js           ← axios instance
│       ├── data/                     ← test cases
│       ├── utils/                    ← formatters / metrics
│       ├── layouts/                  ← shared layouts
│       ├── lib/                      ← small helpers
│       └── assets/                   ← logo + icons
│
├── scripts/
│   └── test_kimi_latency.py          ← smoke test for the LLM provider
│
├── AGENTS.md                         ← repo conventions for AI agents
├── README.md                         ← you are here
├── .gitignore                        ← covers Python, Node, IDE, OS, secrets
├── package-lock.json
└── requirements.txt
```

---

## Testing

```bash
# Backend — 86 pytest cases
cd backend
.\venv\Scripts\python.exe -m pytest tests/ -v
# or, on macOS / Linux:
# venv/bin/python -m pytest tests/ -v
```

```bash
# Frontend — production build
cd frontend
npm run build
```

The backend suite covers:
- `test_upload.py` — PDF validation, magic bytes, empty PDFs, size limits
- `test_claim_extraction.py` — LLM JSON parsing, fence stripping, mixed records
- `test_claim_json_recovery.py` — bracket-matching JSON recovery from prose
- `test_search_service.py` — Tavily ranking, dedupe, truncation
- `test_search_outcome.py` — outcome status + transient-error retry
- `test_verdict_service.py` — LLM verdict parsing, safe-fallback
- `test_verdict_retry.py` — LLM 5xx, 429, rate-limit retry
- `test_verification_pipeline.py` — concurrency, summary, defensive-fallback
- `test_metrics.py` — RunMetrics aggregation

---

## Deployment

TruthLayer is prepared for public GitHub publication first. Deployment configs
are intentionally not committed in this phase.

Planned public URLs:
- GitHub repository: [https://github.com/nitish-niraj/truthlayer](https://github.com/nitish-niraj/truthlayer)
- Future frontend: [https://truthlayernitish.vercel.app](https://truthlayernitish.vercel.app)

Recommended runtime settings:
- Backend: `NVIDIA_API_KEY`, `TAVILY_API_KEY`, and `FRONTEND_URL`.
- Frontend: `VITE_API_URL`.

The backend CORS allowlist already supports local development on port 5173.

---

## How a claim is verified

1. **Extract** — The full document text is sent to Kimi K2.6 (thinking on,
   `temperature=0.1`, 60 s timeout) which returns a list of structured claims
   `{claim, type, source_sentence}`.
2. **Search** — For each claim, the bare `claim.claim` string is sent to
   Tavily (advanced, top 5). Results are deduplicated by URL, filtered for
   completeness, and ranked by source tier (Tier 1: government / official /
   peer-reviewed; Tier 2: reputable publications; Tier 3: everything else).
3. **Verify** — The claim and the ranked evidence are sent back to Kimi K2.6
   (thinking off, 1024 tokens). The model evaluates the *consensus* across
   the evidence, not the top source, and returns one of:
   - `verified` — evidence strongly supports the claim
   - `inaccurate` — claim is partially right or out of date
   - `false` — evidence contradicts the claim
4. **Report** — Per-claim verdicts are aggregated into a `SummaryStats`
   `{total, verified, inaccurate, false}` and rendered in the dashboard.

### Failure policy

- **Tavily transient errors** (connection reset, timeout): retried up to 3
  times with 1 s / 2 s / 4 s backoff. Exhaustion → claim is labelled
  `inaccurate` ("Unable to retrieve sufficient evidence from search
  providers."), not `false`.
- **LLM 5xx / timeouts**: retried up to 3 times with the same backoff.
- **LLM 429 rate-limit**: backoff doubles (1 s / 2 s / 4 s), counted in
  metrics; exhaustion → claim is labelled `inaccurate`, not `false`.
- **Non-retryable errors** (auth, validation): fail fast, return the safe
  fallback.
- **Per-claim defensive fallback**: any unexpected exception in the
  pipeline is absorbed and surfaces as a `VerifiedClaim(verdict="false",
  explanation="Unable to verify claim.")`. The document is never lost.

---

## Screenshots

Screenshots will be added after the public deployment is live. The current UI is
implemented in `frontend/src/screens/` and `frontend/src/components/`.

---

## Roadmap

- Multi-document queue and persistent run history
- PDF rendering preview with per-claim highlights
- Source-tier visualization and evidence diversity score
- Authentication and per-user run history
- WebSocket streaming for live progress on long documents

---

## License

Add your chosen license file before public release. This repository is being
prepared for GitHub publication and does not currently include a license file.

---

## Acknowledgements

- **NVIDIA** — Kimi K2.6 inference via the OpenAI-compatible API
- **Tavily** — high-quality web search with structured results
- **Vercel** and **Render** — for the free tiers that make the public demo
  possible
- The open-source community behind **FastAPI**, **React**, **Tailwind CSS**,
  **Framer Motion**, and every other library listed in
  [Tech stack](#tech-stack)
