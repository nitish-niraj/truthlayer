# AGENTS.md — TruthLayer

Working guide for AI agents (Claude Code, Cursor, Copilot, opencode, etc.) working on this repo. Read fully before touching any file.

> **Repo state:** Phases 1–6 are **done**.
> - Phase 1: scaffold
> - Phase 2: `/api/upload` — PDF validation (extension, size, magic bytes) + PyMuPDF text extraction → `{filename, pages, text}`
> - Phase 3: `/api/extract-claims` — LLM (moonshotai/kimi-k2.6 with thinking enabled) extracts `List[ExtractedClaim]` from raw text, with markdown-fence stripping, mixed-record validation, and graceful `[]` on any failure
> - Phase 4: `/api/search-claim` — Tavily (advanced, top 5, dedupe, tier ranking, content truncation) returns `ClaimEvidence` of ranked `SearchResult` objects. Pure evidence retrieval — no verdict.
> - Phase 5: `/api/generate-verdict` and `/api/verify-claim` — LLM evaluates a claim against the evidence consensus and returns `ClaimVerification(verdict, explanation, correct_fact, source_url)`. `verify-claim` is the full single-claim pipeline (search + verdict). Service never raises; SAFE_FALLBACK `ClaimVerification(verdict="false", …)` on any failure.
> - Phase 6: `/api/verify` — end-to-end orchestrator. `extract_claims` → (search_claim + generate_verdict) per claim with Semaphore(5) + `asyncio.to_thread` for blocking searches. Returns `VerifyResponse` with `SummaryStats` and per-claim `VerifiedClaim` (id 1..N). Enforces `MAX_CLAIMS=20`. Never raises; per-claim failures get a defensive-fallback `VerifiedClaim` (verdict=false, explanation="Unable to verify claim.").
>
> The dark "Intelligence Terminal" UI, the four React screens, and the trap-PDF fixture are **not yet implemented** — they are specified in `docs/TruthLayer_Build_Guide.md` and `docs/4_UIUX_Brief.md`. Phase 7+ = frontend work.

---

## Project Summary

TruthLayer is a full-stack web app:

1. User uploads a PDF in the browser.
2. Backend extracts text (PyMuPDF).
3. LLM (`z-ai/glm-5.1` via NVIDIA OpenAI-compatible API) extracts verifiable factual claims.
4. Each claim is searched live via Tavily (top 3 results).
5. LLM produces a verdict per claim: `verified` / `inaccurate` / `false`.

Two independent deployable units: `backend/` (FastAPI → Render) and `frontend/` (React + Vite → Vercel).

---

## Monorepo Structure (actual + planned)

```
truthlayer/
├── backend/                          ← FastAPI (Render)
│   ├── main.py                       ← CORS + include_router; NO /api/health here
│   ├── Procfile                      ← web: uvicorn main:app --host 0.0.0.0 --port $PORT
│   ├── requirements.txt              ← pinned versions (see Tech Stack)
│   ├── .env.example                  ← keys template (never commit .env)
│   ├── routers/
│   │   └── verify.py                 ← /api/health, /api/upload, /api/verify
│   ├── services/
│   │   ├── pdf_service.py            ← extract_text_from_pdf() — PyMuPDF (Phase 2)
│   │   ├── claim_service.py          ← extract_claims() — LLM, JSON cleanup (Phase 3)
│   │   ├── search_service.py         ← search_claim() — Tavily, tier ranking, dedupe (Phase 4)
│   │   ├── verdict_service.py        ← generate_verdict() — LLM, evidence-consensus reasoning, SAFE_FALLBACK (Phase 5)
│   │   ├── verification_pipeline.py  ← verify_document() — async orchestrator, Semaphore(5), asyncio.gather (Phase 6)
│   │   └── stub_services.py          ← verify_text_stub — DEAD CODE as of Phase 6; do not import in new code
│   ├── models/
│   │   └── schemas.py                ← all Pydantic models — DO complete
│   ├── utils/
│   │   └── file_validation.py        ← validate_extension / magic_bytes / file_size
│   ├── tests/
│   │   ├── conftest.py               ← sets env vars before app import
│   │   ├── test_upload.py            ← 5 pytest cases for /api/upload
│   │   └── test_claim_extraction.py  ← 7 pytest cases for /api/extract-claims (LLM mocked)
│   └── core/
│       ├── config.py                 ← pydantic-settings Settings singleton
│       ├── logger.py                 ← "truthlayer" logger, [ts] LEVEL msg format
│       └── llm_client.py             ← OpenAI(NVIDIA) singleton
│
├── frontend/                         ← React + Vite (Vercel)
│   ├── vite.config.js                ← React plugin only (NO @tailwindcss/vite yet)
│   ├── tailwind.config.cjs           ← v3 content paths, empty theme.extend
│   ├── postcss.config.cjs            ← tailwindcss + autoprefixer
│   ├── .env.example                  ← VITE_API_URL template
│   ├── index.html                    ← no Google Fonts link yet
│   └── src/
│       ├── main.jsx                  ← React.StrictMode root
│       ├── App.jsx                   ← Header + Home — NOT a state machine yet
│       ├── index.css                 ← Tailwind directives only — no CSS vars
│       ├── components/Header.jsx     ← gray-900 nav (temporary)
│       ├── pages/Home.jsx, Upload.jsx← minimal Upload form (calls /api/upload)
│       ├── hooks/useUpload.js        ← bare useState hook
│       ├── services/api.js           ← axios instance (NOT src/api/index.js)
│       ├── utils/format.js           ← short() helper
│       └── assets/logo.svg
│   [PLANNED] components: UploadScreen, ProcessingScreen, ClaimCard, ResultsDashboard
│
├── AGENTS.md                         ← you are here
├── README.md                         ← "Phase 1 scaffold"
├── .gitignore                        ← ignores venv, node_modules, dist, .env
└── ../docs/                          ← PRD, TRD, AppFlow, UIUX, BackendSchema, ImplementationPlan, TruthLayer_Build_Guide.md
```

---

## Tech Stack (pinned)

### Backend (`backend/requirements.txt`)
| Tool | Version | Purpose |
|---|---|---|
| fastapi | 0.116.1 | Web framework |
| uvicorn[standard] | 0.48.0 | ASGI server |
| python-multipart | 0.0.29 | multipart upload |
| python-dotenv | 1.2.2 | env loading |
| pydantic | 2.13.0 | data models |
| pydantic-settings | 2.14.1 | Settings class |
| openai | 2.36.0 | NVIDIA GLM client (OpenAI-compatible) |
| tavily-python | 0.7.24 | live web search |
| pymupdf | ≥1.24.10 | PDF parsing (Phase 2) |
| pytest | 8.4.2 | test runner (Phase 2) |
| httpx | 0.28.1 | TestClient dependency (Phase 2) |

### Frontend (`frontend/package.json`)
| Tool | Version | Purpose |
|---|---|---|
| react / react-dom | 18.2.x | UI |
| vite | 5.x | dev server + build |
| @vitejs/plugin-react | 4.x | React fast refresh |
| tailwindcss | **3.5.x** (NOT v4) | styling — utilities only, no design tokens yet |
| postcss / autoprefixer | 8.x / 10.x | Tailwind pipeline |
| axios | 1.4.x | HTTP |
| framer-motion | 11.x | animations (declared, not used yet) |
| react-dropzone | 14.x | PDF drag-drop (used in `pages/Upload.jsx`) |
| lucide-react | 0.383.0 | icons |

> **Tailwind v3, not v4.** The Build Guide mentions `@tailwindcss/vite` (v4) — ignore that, `package.json` pins v3 with the classic `tailwind.config.cjs` + `postcss.config.cjs` setup.

---

## Environment Variables

### `backend/.env` (from `backend/.env.example`)
```
NVIDIA_API_KEY=nvapi-...
TAVILY_API_KEY=tvly-...
FRONTEND_URL=http://localhost:5173
MAX_FILE_SIZE_MB=10
MAX_CLAIMS=20
MAX_SEARCH_RESULTS=5
SEARCH_TIMEOUT_SECONDS=15
```
Read via `from core.config import settings` → `settings.NVIDIA_API_KEY`, etc. Never `os.getenv()` directly. Never instantiate `Settings()` in a service.

### `frontend/.env`
```
VITE_API_URL=http://localhost:8000
```
Read via `import.meta.env.VITE_API_URL` (already wired in `src/services/api.js`).

**Rules:** never hardcode keys; never commit `.env`; `.env` is in `.gitignore`.

---

## How to Run Locally

```bash
# Terminal 1 — backend
cd backend
python -m venv venv
venv\Scripts\activate         # Windows; macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

CORS in `main.py` already permits `http://localhost:5173`, so both must be up for end-to-end testing.

---

## API Contract (from `backend/models/schemas.py`)

### `POST /api/upload` — multipart/form-data
- Form field name: **`file`** (Phase 2 spec). `frontend/src/pages/Upload.jsx` already updated to match.
- Validates in order: `.pdf` extension → file size (`MAX_FILE_SIZE_MB` * 1024²) → `b"%PDF"` magic bytes.
- Extracts text from all pages with PyMuPDF (`fitz`), joins with `\n`.
- Returns `UploadResponse`: `{filename, pages, text}`.
- Errors: 400 (bad extension or magic bytes — `"Only PDF files are accepted"` / `"Invalid PDF file"`), 413 (`"File must be under {N}MB"`), 422 (`"PDF contains no readable text"`), 500 (`"Failed to parse PDF"`).
- Logging: every upload logs `INFO PDF uploaded: <name>` and `INFO Pages extracted: <n>`; errors log at `ERROR`.

### `POST /api/verify` — JSON body (Phase 6, end-to-end pipeline)
- Body: `VerifyRequest {text, filename}`.
- Returns `VerifyResponse {filename, summary: SummaryStats, claims: List[VerifiedClaim]}`.
- Calls `services/verification_pipeline.verify_document(text, filename)`:
  1. `extract_claims(text)` — Kimi K2.6 (thinking on) → `List[ExtractedClaim]`. Truncated to `MAX_CLAIMS=20` (logs `WARNING` if the cap kicks in).
  2. For each claim, in parallel up to 5 concurrent pipelines: `await asyncio.to_thread(search_claim, claim)` (Tavily, top 5 ranked) → `await generate_verdict(claim, evidence)` (Kimi, thinking off, 1024 tokens).
  3. Ids 1..N assigned in pipeline order. `SummaryStats {total, verified, inaccurate, false}` computed from the results.
  4. Returns the `VerifyResponse`.
- Empty text → 400 (`\`text\` is required`).
- Zero extracted claims → 200 with `VerifyResponse` of zero counts (no LLM/search calls, no `500`).
- Per-claim failures (any exception during search/verdict) → defensive-fallback `VerifiedClaim(id=-1, verdict="false", explanation="Unable to verify claim.", correct_fact="", source_url="")`. The id is reassigned 1..N in pipeline output order; the `false` verdict counts toward `summary.false`.
- Latency: per-claim wall time ≈ Tavily search + LLM verdict. Worst case (20 claims, 5 concurrent) ≈ 4 × 18 s ≈ 72 s.

### `GET /api/health` — defined in `routers/verify.py`
- Returns `{"status": "ok", "version": "1.0"}` (note: not `"1.0.0"` — this differs from the Build Guide's example).

### `POST /api/extract-claims` — JSON body (Phase 3, temp endpoint)
- Body: `ExtractClaimsRequest {text: str}`. Pydantic requires `text`; empty string still passes and returns `[]`.
- Calls `services/claim_service.extract_claims(text)` which truncates to first 8000 chars and sends to `moonshotai/kimi-k2.6` with `thinking=True` enabled (temperature 1.0, top_p 1.0, max_tokens 16384, stream=False).
- Response: `List[ExtractedClaim]` directly (not wrapped) — each item is `{claim, type, source_sentence}`.
- Failure policy: LLM exception → `[]`; JSON parse failure → `[]`; per-item Pydantic validation failure → item skipped, valid items still returned. The endpoint never returns 5xx for these cases.

### `POST /api/search-claim` — JSON body (Phase 4, temp endpoint)
- Body: full `ExtractedClaim` (claim, type, source_sentence). Service only uses `claim` for the query — type/source_sentence are not used for ranking yet, but the body shape lets a frontend pipe the output of `/api/extract-claims` straight in.
- Calls `services/search_service.search_claim(claim)` → Tavily `client.search(query=claim.claim, search_depth="advanced", max_results=MAX_SEARCH_RESULTS, include_answer=False, include_raw_content=False, timeout=SEARCH_TIMEOUT_SECONDS)`.
- Response: `ClaimEvidence {claim, evidence: List[SearchResult]}` — `SearchResult` is `{title, url, content}`. `content` truncated to 1000 chars. Results are deduplicated by URL, empties dropped, ranked by tier.
- Failure policy: Tavily exception, timeout, or any other error → `[]`. The endpoint never returns 5xx for these cases (500 is reserved in OpenAPI for truly unhandled router-level errors).
- **No verdict, no scoring, no judgement** — pure evidence retrieval. Verdict engine (Phase 5) will consume the same shape and add the labelling.

### `POST /api/generate-verdict` — JSON body (Phase 5, temp endpoint)
- Body: `GenerateVerdictRequest {claim: ExtractedClaim, evidence: List[SearchResult]}`.
- Calls `services/verdict_service.generate_verdict(claim, evidence)` → Kimi with `temperature=0.1, top_p=1.0, max_tokens=1024, stream=False, thinking=False`. The prompt explicitly tells the model to evaluate **all** evidence as a consensus and not to trust the top source.
- Response: `ClaimVerification {verdict, explanation, correct_fact, source_url}`. `verdict` is one of `verified` / `inaccurate` / `false`. `correct_fact` is `""` when `verdict == verified`.
- Failure policy: LLM exception, JSON parse failure, or Pydantic validation error → returns `SAFE_FALLBACK` (`verdict="false", explanation="Unable to verify claim due to processing failure.", correct_fact="", source_url=""`). The service never raises. The endpoint never returns 5xx for these cases.
- Empty evidence → short-circuits to a `false` fallback without calling the LLM (`explanation="No evidence found to evaluate this claim."`).

### `POST /api/verify-claim` — JSON body (Phase 5, full single-claim pipeline)
- Body: `ExtractedClaim` (same shape as `/api/search-claim`).
- Composes: `search_claim(req)` (sync, ~5–15 s, blocks the event loop) → `generate_verdict(req, evidence)` (async LLM call, ~2–3 s) → returns `VerifyClaimResponse {claim, verdict}`.
- Same failure policy as `/api/generate-verdict` — the verdict is always a valid `ClaimVerification` (safe-fallback on any failure).
- Latency dominated by Tavily + LLM. If multi-claim latency becomes a concern, hoist `search_claim` to `asyncio.to_thread` in Phase 6.

### Pydantic models to keep stable (`models/schemas.py`)
`ClaimType` (statistic|financial|date|technical|attribution), `VerdictType` (verified|inaccurate|false), `ExtractedClaim`, `SearchResult`, `ClaimVerification`, `ClaimEvidence`, `GenerateVerdictRequest`, `VerifyClaimResponse`, `VerifyRequest`, `VerifiedClaim`, `SummaryStats`, `UploadResponse`, `VerifyResponse`, `ErrorResponse`. Any new field → update schema, frontend API handler, and consumer component in one PR.

---

## LLM Configuration

- **Model:** `moonshotai/kimi-k2.6` (with **thinking enabled** via `chat_template_kwargs={"thinking": True}`)
- **Provider:** NVIDIA via OpenAI-compatible SDK
- **Base URL:** `https://integrate.api.nvidia.com/v1` (in `core/llm_client.py`)
- **Model name & defaults:** constants `MODEL_NAME`, `DEFAULT_TEMPERATURE`, `DEFAULT_TOP_P`, `DEFAULT_MAX_TOKENS`, `THINKING_ENABLED` in `core/llm_client.py` — services import these, do not hardcode.

**Temperature:** `1.0` is the default and is intentional — Kimi K2.6's thinking mode is tuned for it. Lowering to `0.1` collapses the reasoning trace and degrades structured-JSON output quality. Do not lower below `0.6` while thinking is on.

**Streaming:** always `stream=False` in the backend. Streaming is frontend-only if ever added.

**Token limits:**
- Claim extraction: `max_tokens=16384` (large enough to absorb thinking tokens + JSON output)
- Verdict generation: `max_tokens=1024` (overrides the earlier 8192 plan — verdict is a small structured object, thinking is off)
- Truncate input text to first **8000** characters before claim extraction.

---

## LLM Response Handling

Both LLM calls return JSON. The model sometimes wraps output in ` ```json ... ``` ` fences. Always strip before parsing:

```python
raw = response.choices[0].message.content.strip()
if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
raw = raw.strip()
data = json.loads(raw)
```

Failure policy:
- `claim_service.py` → on JSON parse failure return `[]`, do not raise.
- `search_service.py` → on Tavily failure, timeout, or malformed response return `[]`, do not raise.
- `verdict_service.py` → on LLM error, JSON parse failure, or Pydantic validation error return `SAFE_FALLBACK` (`ClaimVerification(verdict="false", …)`). Do not raise.

---

## Data Flow (planned, once services are built)

```
UploadScreen → POST /api/upload (field "file")
   → pdf_service.extract_text_from_pdf → {text, pages, filename}
   → state holds text, screen → "processing"
ProcessingScreen → POST /api/verify {text, filename}                [Phase 6 ✓]
   → claim_service.extract_claims(text)            [LLM #1, Phase 3 ✓]
   → for each claim (Semaphore(5), asyncio.to_thread for blocking search):
        search_service.search_claim(claim)         [Tavily, top 5 ranked, Phase 4 ✓]
        verdict_service.generate_verdict(claim, results)  [LLM #2, Phase 5 ✓]
   → VerifyResponse with summary counts
   → screen → "results"
ResultsDashboard renders ClaimCard[] with verdict colors
```

> Phase 3 has a temporary `POST /api/extract-claims` endpoint for isolated testing of the LLM claim-extraction step. Once Phase 4+ land, this endpoint should be removed and the claim extraction should be invoked from inside the `/api/verify` router only.

**Thinking-mode response handling:** Kimi K2.6 with `thinking=True` returns the reasoning trace in `choices[0].message.reasoning_content` and the visible answer in `choices[0].message.content`. Only `.content` is parsed for JSON; `.reasoning_content` is logged at `DEBUG` for observability (do not include in API responses).

---

## Frontend State Machine (planned)

`App.jsx` will own `screen: "upload" | "processing" | "results" | "error"`. Currently it just renders `<Header /><Home />`. Wiring rules when you build it:

- `/api/upload` is called **only** from `UploadScreen.jsx`.
- `/api/verify` is called **only** from `ProcessingScreen.jsx`.
- Error screen must have a Retry button that resets to `"upload"`.
- Use `framer-motion` `AnimatePresence mode="wait"` for screen transitions.

---

## Design System Rules (planned, in `index.css`)

Use these CSS variables (do not hardcode hex in components):

```css
var(--bg-base)        /* #0A0C0F  page background */
var(--bg-surface)     /* #111318  cards */
var(--bg-elevated)    /* #1A1D24  hover */
var(--bg-border)      /* #2A2D36  dividers */
var(--text-primary)   /* #F0F2F5 */
var(--text-secondary) /* #8B909E */
var(--text-muted)     /* #4A4F5E */
var(--accent)         /* #F5A623  amber — CTAs only */
var(--verified)       /* #22C55E  green */
var(--inaccurate)     /* #F59E0B  amber */
var(--false)          /* #EF4444  red */
```

**Fonts:** Syne (headings 600–800), IBM Plex Sans (body), IBM Plex Mono (claim text, verdicts, code). Never Inter/Roboto/Arial. Add Google Fonts `<link>` to `index.html`.

**Verdict color maps** (keep centralized in `ClaimCard.jsx`):
```js
const verdictColor = { verified: 'var(--verified)', inaccurate: 'var(--inaccurate)', false: 'var(--false)' }
const verdictBg    = { verified: 'var(--verified-bg)', inaccurate: 'var(--inaccurate-bg)', false: 'var(--false-bg)' }
```

**Animations** (Framer Motion + CSS keyframes in `index.css`):
- `slideUp`: `opacity 0, y 16` → `opacity 1, y 0`, 0.3s
- Stagger claim cards: 0.08s per card
- `pulseGlow`: amber shadow on the active processing step
- No looping decorative animations outside the processing screen.

---

## Coding Conventions

### Python (backend)
- `async def` for route handlers and LLM calls.
- `def` (sync) is fine for the Tavily call — it's blocking but acceptable at this scale.
- Services return typed Pydantic objects from `models/schemas.py` — never raw dicts.
- Import settings only from `core.config`; only one `settings` instance.
- Use `get_llm_client()` — never `OpenAI(...)` in a service.
- `HTTPException` codes must match the contract in `docs/2_TRD.md` §9.
- Validate PDF **magic bytes** `b"%PDF"` in addition to extension.

### JavaScript (frontend)
- Functional components only.
- State lives in `App.jsx`; children receive data + callbacks via props.
- All HTTP goes through `src/services/api.js` (the current axios instance) — no direct `axios` calls in components.
- Base URL: `import.meta.env.VITE_API_URL` (already wired, with `http://localhost:8000` fallback).
- Define Framer Motion variants at the top of the file, not inline.

---

### Backend
- `pdf_service` (Phase 2) → raises `HTTPException` with the codes above; logs at INFO/ERROR.
- `claim_service` (Phase 3) → catches **all** failures (LLM error, JSON parse error, per-item validation) and returns `[]`. The service never raises. Logs `INFO Starting claim extraction` / `INFO Claims extracted: N` on success; `ERROR LLM extraction failed` / `ERROR JSON parse failure` / `WARNING Skipping invalid claim` on failure modes.
- `search_service` (Phase 4) → catches all exceptions (Tavily errors, `requests.Timeout`, malformed responses), returns `[]`. The service never raises. Logs `INFO Searching claim: …` / `INFO Search results found: N` / `INFO Results after filtering: N` on success; `ERROR Tavily request failed: …` / `ERROR Search timeout after Ns` on failure modes. Tier ranking + dedupe + content truncation are the only "intelligence" here — no verdict logic.
- `verdict_service` (Phase 5) → catches all exceptions (LLM error, JSON parse failure, Pydantic validation error), returns `SAFE_FALLBACK` `ClaimVerification(verdict="false", explanation="Unable to verify claim due to processing failure.", correct_fact="", source_url="")`. The service never raises. Empty evidence → short-circuits to a `false` fallback without calling the LLM. Logs `INFO Starting verdict generation: …` / `INFO Verdict generated: <verdict> (<explanation>)` on success; `ERROR Verdict parsing failed: …` / `ERROR LLM request failed: …` on failure modes. Thinking OFF, max_tokens=1024.
- `verification_pipeline` (Phase 6) → orchestrates `extract_claims` → (search + verdict) per claim with `asyncio.Semaphore(MAX_CONCURRENT_CLAIMS=5)` and `asyncio.to_thread` for blocking search calls. Never raises. Per-claim failures (unexpected exceptions despite service-level catches) return a defensive-fallback `VerifiedClaim(id=-1, verdict="false", explanation="Unable to verify claim.", correct_fact="", source_url="")`; ids are reassigned 1..N in pipeline order. Enforces `settings.MAX_CLAIMS=20` after `extract_claims` (logs `WARNING` on truncation). Empty `extract_claims` output → 200 with zero-count `VerifyResponse` and no LLM/search calls. Latency formula: per-claim ≈ Tavily + LLM; worst case 20 claims / 5 concurrent ≈ 72 s. Logs `INFO Document received: …` → `INFO Claims extracted: N` → `INFO Verification started` → `INFO Verification completed: total=… verified=… inaccurate=… false=… in N.NNs (avg N.NNs/claim)`.
- `routers/verify.py` → if claims list is empty, return a valid `VerifyResponse` with zero counts (NOT 500).

### Tests (`backend/tests/`)
- Run from `backend/` directory: `pytest tests/ -v`. 12 cases, all passing.
- `conftest.py` sets dummy `NVIDIA_API_KEY` / `TAVILY_API_KEY` env vars at module load so `Settings()` doesn't fail without a real `.env`.
- `test_upload.py` uses `fitz` to build minimal valid PDFs in-memory — no fixture files on disk.
- `test_claim_extraction.py` uses `monkeypatch` to replace `services.claim_service.get_llm_client` with a `MagicMock` that returns a stub `chat.completions.create` response. Tests are sync and call the async function via `asyncio.run()` — no `pytest-asyncio` needed.

## What NOT to Do

| ❌ Don't | ✅ Do |
|---|---|
| Hardcode API keys in source | Use `.env` + `settings` / `import.meta.env` |
| Use Kimi thinking at `temperature < 0.6` | Use `1.0` (default) — lower collapses the thinking trace |
| `stream=True` in backend LLM calls | `stream=False` |
| Add verdict logic inside `search_service.py` | `search_service` is evidence-only; verdicts belong to `verdict_service` |
| Raise from `verdict_service.py` | Always return a `ClaimVerification`; use `SAFE_FALLBACK` for any failure |
| Block on a single claim at a time in the pipeline | Use `asyncio.gather` with `asyncio.Semaphore(5)` to process up to 5 claims concurrently; offload the blocking `search_claim` call to `asyncio.to_thread` |
| Bias the search query ("fact check:", "true or false") | Query is the bare `claim.claim` |
| Save the uploaded PDF to disk | Process in memory, discard after response |
| Call `/api/verify` from `UploadScreen` | Call it only from `ProcessingScreen` |
| Use Inter/Roboto/Arial | Use Syne + IBM Plex Sans/Mono |
| Hardcode hex colors in components | Use CSS variables |
| Return a raw dict from a service | Return a Pydantic model |
| Use localStorage / sessionStorage | React state only |
| Leave `print()` debug calls | Remove before commit |

---

## Error Handling Rules

### Backend
- `pdf_service` → raises `HTTPException` with correct status codes (400/413/422/500).
- `claim_service` → catches JSON parse error, returns `[]`.
- `search_service` → catches all exceptions, returns `[]`.
- `verdict_service` → catches all exceptions, returns `SAFE_FALLBACK` `ClaimVerification(verdict="false", …)`. Never raises.
- `verification_pipeline` → catches all exceptions, returns a defensive-fallback `VerifiedClaim` per failed claim, never raises from the document level.
- `routers/verify.py` → if claims list is empty, return a valid `VerifyResponse` with zero counts (NOT 500).

### Frontend
- All axios calls wrapped in `try/catch`.
- On error: call `onError(message)` prop → error screen.
- Never show raw error objects — show a human-readable string.
- Error screen has a Retry button that resets to upload.

---

## Adding a New Feature — Checklist

1. New endpoint? → add route in `routers/verify.py` + schema in `models/schemas.py`.
2. New LLM prompt? → add to the relevant service file; keep `temperature=0.1`, `stream=False`.
3. New UI screen? → add a `screen` value to the `App.jsx` state machine + create the component in `src/components/`.
4. New env var? → add to `.env.example`, `core/config.py` (and `frontend/.env.example` if frontend), plus Render + Vercel env panels.
5. API response shape change? → update the Pydantic schema AND the frontend consumer AND any component that renders the field — in one PR.

---

## Deployment

| Service | Platform | Trigger | Root dir | Start |
|---|---|---|---|---|
| Backend | Render (free) | push to `main` | `backend/` | `uvicorn main:app --host 0.0.0.0 --port $PORT` (Procfile) |
| Frontend | Vercel (free) | push to `main` | `frontend/` | `npm run build` → `dist` |

- Render free tier sleeps after 15min idle — first request takes ~30s to wake. Add a warm-up note in the UI.
- Render `FRONTEND_URL` env must **exactly** match the deployed Vercel URL — update and redeploy if the Vercel domain changes.
- CORS origins in `main.py` are `[settings.FRONTEND_URL, "http://localhost:5173"]` — both must remain.

---

## Testing the Pipeline

### Health
```bash
curl http://localhost:8000/api/health
# → {"status":"ok","version":"1.0"}
```

### Upload (any real PDF, returns extracted text)
```bash
curl -X POST http://localhost:8000/api/upload -F "file=@any.pdf"
# → {"filename":"any.pdf","pages":N,"text":"..."}
```

### Verify
```bash
curl -X POST http://localhost:8000/api/verify \
  -H "Content-Type: application/json" \
  -d '{"text":"Apple revenue reached $394B in FY2022.","filename":"test.pdf"}'
```

### Trap Document (planned — fixture doesn't exist yet)
Once `create_trap_pdf.py` (per Build Guide Phase 8) lands, expected verdicts:

| Claim | Expected |
|---|---|
| 9 billion without clean water | ❌ false |
| ChatGPT 100M users | ⚠️ inaccurate |
| Python used by 12% of devs | ❌ false |
| OpenAI founded in 2020 | ❌ false |
| EV market 7M units 2022 | ⚠️ inaccurate |
| Netflix 150M subscribers | ❌ false |
| India most populous 2023 | ✅ verified |
| Tesla 1.8M deliveries 2023 | ✅ verified |

> If >2 false/inaccurate claims come back verified → the verdict prompt needs tightening. Do not just lower temperature further — add stricter instructions to the prompt first.

---

## Common Gotchas

- **Field name is `file`, not `pdf`.** Phase 2 finalized this. Backend router (`routers/verify.py`) and `frontend/src/pages/Upload.jsx` both use `file`. (TRD §4 still says `pdf` — TRD is stale, code wins.)
- **`stub_services.py` still exists** but is now **fully dead code** as of Phase 6. The header comment explicitly warns not to import from it. The real `/api/verify` calls `services/verification_pipeline.verify_document`. `extract_text_stub` and `verify_text_stub` are both unused. Safe to delete in a future cleanup pass.
- **All pinned versions in `requirements.txt` are current as of Phase 2 upgrade** (fastapi 0.116.1, openai 2.36.0, pydantic 2.13.0, pydantic-settings 2.14.1, pymupdf ≥1.24.10, etc.). The `openai` SDK is on the 2.x line — the `from openai import OpenAI` + `OpenAI(base_url=..., api_key=...)` API surface used in `core/llm_client.py` is unchanged from 1.x. If you see `ResolutionImpossible` errors, the pins may have rotted; re-check.
- **Class-based `Config` in `core/config.py`** triggers a Pydantic v2 deprecation warning. Harmless; fix by migrating to `model_config = SettingsConfigDict(...)` when convenient.
- **`get /api/health` is on the router, not in `main.py`.** Don't add a duplicate in `main.py`.
- **CORS allow-list is hardcoded with localhost.** When pointing the deployed frontend at a real Render URL, the Vercel URL must be set as Render's `FRONTEND_URL` env var, not edited into source.
- **Settings reload on every import.** `core/config.py` instantiates `Settings()` at module load — backend tests need env vars set before import. `tests/conftest.py` does this with `os.environ.setdefault` at module top. Don't reorder imports.
- **Tailwind v3, not v4.** Don't add `@tailwindcss/vite` to `vite.config.js` — that breaks the existing PostCSS pipeline.
- **There is no design system in `index.css` yet.** The CSS-variable/IBM-Plex rules in this file are the *target*. The current file is just `@tailwind base/components/utilities` + minimal resets.

---

## Where to Read More

- `docs/1_PRD.md` — product requirements, success metrics
- `docs/2_TRD.md` — technical requirements, prompt specs, error matrix (⚠️ temperature example is stale: says 0.2, intent is 0.1)
- `docs/3_AppFlow.md` — screen-by-screen UX flow
- `docs/4_UIUX_Brief.md` — visual design
- `docs/5_BackendSchema.md` — schema rationale
- `docs/6_ImplementationPlan.md` — phase plan
- `docs/TruthLayer_Build_Guide.md` — **the canonical phase-by-phase build spec**, including the exact Claude prompts to use for each phase
- `README.md` — confirms Phase 1 scaffold status
