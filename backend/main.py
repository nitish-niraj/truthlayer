import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from core.logger import logger
from routers.verify import router as verify_router
from services.job_store import store as job_store

app = FastAPI(title="TruthLayer API", description="Automated PDF fact-checking backend")


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Note: the verify pipeline can take 20-30 s on a free Render instance. Render
# will close the upstream socket if the response hasn't started streaming
# before its HTTP timeout. The /api/verify endpoint was migrated to a
# background-job pattern in Phase 13 — POST returns a job_id in <100ms and
# the actual work runs in a background task — so this concern only applies
# to /api/upload and the legacy /api/verify-sync endpoint now.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


# ---------------------------------------------------------------------------
# Request-timing + access log middleware
# ---------------------------------------------------------------------------
class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
        request.state.request_id = request_id
        t0 = time.perf_counter()
        logger.info(
            "REQUEST START | id=%s | %s %s | origin=%s",
            request_id,
            request.method,
            request.url.path,
            request.headers.get("origin", "-"),
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.exception(
                "REQUEST CRASH | id=%s | %s %s | elapsed=%.2fs | %s",
                request_id,
                request.method,
                request.url.path,
                elapsed,
                exc,
            )
            raise
        elapsed = time.perf_counter() - t0
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "REQUEST END   | id=%s | %s %s | status=%d | elapsed=%.2fs",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response


app.add_middleware(RequestTimingMiddleware)


# ---------------------------------------------------------------------------
# Global exception handler — ensures EVERY error response goes back through
# CORSMiddleware with a JSON body. Without this, an unhandled exception can
# produce a Starlette default response that bypasses the CORS layer and the
# browser then reports "No Access-Control-Allow-Origin header" even though
# the middleware is configured correctly.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("UNHANDLED EXCEPTION | id=%s | %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred. Please retry.",
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# Explicit OPTIONS wildcard. CORSMiddleware already handles OPTIONS, but having
# an explicit handler means the route shows up in /docs and we have a single
# place to attach a CORS preflight log line for debugging.
# ---------------------------------------------------------------------------
@app.options("/{path:path}", include_in_schema=False)
async def options_handler(path: str, request: Request):
    origin = request.headers.get("origin", "*")
    logger.info("CORS PREFLIGHT | path=/%s | origin=%s", path, origin)
    return JSONResponse(status_code=200, content={"ok": True})


# ---------------------------------------------------------------------------
# Favicon — returns 204 No Content so the browser stops spamming the
# Network tab with 404s for /favicon.ico. We don't ship an icon yet.
# ---------------------------------------------------------------------------
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Lifecycle: start the job-store eviction sweeper on startup.
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    await job_store.start_sweeper()
    logger.info("APP STARTUP COMPLETE | FRONTEND_URL=%s", settings.FRONTEND_URL)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await job_store.stop_sweeper()
    logger.info("APP SHUTDOWN COMPLETE")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(verify_router)


@app.get("/")
async def root():
    return {
        "message": "TruthLayer backend. See /api/health",
        "endpoints": {
            "POST /api/upload": "Extract text from a PDF (synchronous, <5s)",
            "POST /api/verify": "Start a background verification job (returns job_id in <100ms)",
            "GET /api/verify/{job_id}": "Poll for job status and result",
            "GET /api/health": "Liveness probe",
        },
    }
