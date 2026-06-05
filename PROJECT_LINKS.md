# TruthLayer — Project Links

Single source of truth for every live URL that ships TruthLayer.

---

## Project

**TruthLayer** — AI-powered PDF fact verification platform.

Drop a PDF, get every factual claim cross-referenced against live web
sources, and a colour-coded verdict for each one (`verified` /
`inaccurate` / `false`).

---

## Live Application

**Frontend (Vercel):**
**[https://truthlayernitish.vercel.app](https://truthlayernitish.vercel.app)**

---

## GitHub Repository

**[https://github.com/nitish-niraj/truthlayer](https://github.com/nitish-niraj/truthlayer)**

Includes:

- Source code (frontend + backend)
- API documentation
- Deployment configuration (`render.yaml`)
- Screenshots and demo video under `docs/`
- Submission package under `submission/`

---

## Backend API

**Backend (Render):**
**[https://truthlayer-backend-c6u0.onrender.com](https://truthlayer-backend-c6u0.onrender.com)**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | `GET` | Liveness check |
| `/api/upload` | `POST` | Upload PDF, extract text |
| `/api/verify` | `POST` | Start a background verify job |
| `/api/verify/{job_id}` | `GET` | Poll job status + result |
| `/api/extract-claims` | `POST` | Extract claims (LLM #1) |
| `/api/search-claim` | `POST` | Search evidence (Tavily) |
| `/api/generate-verdict` | `POST` | Generate verdict (LLM #2) |
| `/api/verify-claim` | `POST` | Single-claim full pipeline |

Interactive docs: **`https://truthlayer-backend-c6u0.onrender.com/docs`**

---

## Quick links

- **README** — [`README.md`](README.md)
- **Screenshots** — [`docs/screenshots/`](docs/screenshots/)
- **Demo video** — [`docs/demo/truth-layers.mp4`](docs/demo/truth-layers.mp4)
- **Final summary** — [`FINAL_SUMMARY.md`](FINAL_SUMMARY.md)
- **Submission package** — [`submission/`](submission/)

---

## Author

**Nitish Kumar**

- GitHub: [@nitish-niraj](https://github.com/nitish-niraj)
