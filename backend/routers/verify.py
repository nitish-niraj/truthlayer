import time

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from core.config import settings
from core.llm_client import BASE_URL, get_llm_client
from core.logger import logger
from models.schemas import (
    ClaimEvidence,
    ClaimVerification,
    ErrorResponse,
    ExtractedClaim,
    ExtractClaimsRequest,
    GenerateVerdictRequest,
    ImageClaimsResponse,
    ImageUploadResponse,
    ImageVerificationResponse,
    UploadResponse,
    VerifyClaimResponse,
    VerifyRequest,
    VerifyResponse,
)
from services import job_store
from services.claim_service import extract_claims
from services.image_claim_service import (
    VisionServiceError,
    extract_claims_from_image,
)
from services.image_service import validate_image_contents, validate_image_upload
from services.image_verification_service import (
    summarize as summarize_image_verdicts,
    verify_image_claims,
)
from services.job_store import JobStatus, store as job_store_singleton
from services.pdf_service import extract_text_from_pdf
from services.search_service import search_claim
from services.verdict_service import generate_verdict
from services.verification_pipeline import verify_document

router = APIRouter(prefix="/api")

API_VERSION = "2.0"


def _llm_configured() -> bool:
    """True iff the NVIDIA API key is present and the LLM client can be
    instantiated. We do NOT issue a real LLM call from the health probe —
    health checks must always be sub-100ms.
    """
    key = (settings.NVIDIA_API_KEY or "").strip()
    if not key or key == "test-nvidia-key":
        return False
    try:
        client = get_llm_client()
        return client is not None
    except Exception as exc:
        logger.warning("LLM client construction failed during health check: %s", exc)
        return False


def _tavily_configured() -> bool:
    key = (settings.TAVILY_API_KEY or "").strip()
    if not key or key == "test-tavily-key":
        return False
    # Tavily is invoked from search_service; if the import works and the
    # key looks plausible, mark it available. We do NOT make a real call.
    try:
        from tavily import TavilyClient  # type: ignore
        return True
    except Exception:
        return False


@router.get("/health")
async def health():
    """Liveness + dependency status.

    Returns the configured/unconfigured state of every downstream service so a
    monitoring tool can flag a degraded environment without making a real API
    call. Always returns 200 so the service still serves traffic when an
    optional dependency is missing — the dependency flags are advisory.
    """
    vision_ok = _llm_configured()
    search_ok = _tavily_configured()
    status = "ok" if (vision_ok and search_ok) else "degraded"
    return {
        "status": status,
        "version": API_VERSION,
        "vision": "available" if vision_ok else "unconfigured",
        "search": "available" if search_ok else "unconfigured",
        "model": "moonshotai/kimi-k2.6",
        "base_url": BASE_URL,
    }


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a PDF and extract readable text",
    description=(
        "Accepts a multipart/form-data upload of a PDF file, validates the extension, "
        "size, and magic bytes, then extracts text from all pages using PyMuPDF. "
        "Returns the original filename, the page count, and the concatenated text."
    ),
    responses={
        200: {"description": "PDF processed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid PDF (bad extension or missing magic bytes)"},
        413: {"model": ErrorResponse, "description": "File exceeds MAX_FILE_SIZE_MB"},
        422: {"model": ErrorResponse, "description": "PDF contains no readable text"},
        500: {"model": ErrorResponse, "description": "Failed to parse PDF"},
    },
)
async def upload_file(file: UploadFile = File(...)):
    return await extract_text_from_pdf(file)


@router.post(
    "/upload-image",
    response_model=ImageUploadResponse,
    summary="Upload an image and return its metadata (V2 Phase 1)",
    description=(
        "Accepts a multipart/form-data upload of an image file (PNG, JPG, "
        "JPEG, or WEBP), validates the format, size, and integrity, and "
        "returns basic metadata. Phase 1 only — no OCR, no vision, no "
        "claim extraction. Up to 5MB."
    ),
    responses={
        200: {"description": "Image validated successfully"},
        400: {
            "model": ErrorResponse,
            "description": "Unsupported format or corrupted image",
        },
        413: {"model": ErrorResponse, "description": "Image exceeds MAX_IMAGE_SIZE_MB"},
    },
)
async def upload_image(file: UploadFile = File(...)):
    return await validate_image_upload(file)


@router.post(
    "/extract-image-claims",
    response_model=ImageClaimsResponse,
    summary="Extract verifiable factual claims from an image (V2 Phase 2)",
    description=(
        "Accepts a multipart/form-data upload of an image file (PNG, JPG, "
        "JPEG, or WEBP), validates it, and asks Kimi K2.6 vision to extract "
        "every verifiable factual claim visible in the image. Returns the "
        "extracted claims in the same ``ExtractedClaim`` shape used by the "
        "text-based claim extractor. No web search, no verdict generation. "
        "Up to 5MB."
    ),
    responses={
        200: {"description": "Claims extracted (possibly empty list)"},
        400: {
            "model": ErrorResponse,
            "description": "Unsupported format or corrupted image",
        },
        413: {"model": ErrorResponse, "description": "Image exceeds MAX_IMAGE_SIZE_MB"},
        503: {"model": ErrorResponse, "description": "Vision service unavailable"},
    },
)
async def extract_image_claims(file: UploadFile = File(...)):
    contents = await file.read()
    meta = validate_image_contents(contents, file.filename, file.content_type)
    try:
        claims = await extract_claims_from_image(
            contents, meta.filename, meta.mime_type
        )
    except VisionServiceError as exc:
        logger.error("Vision service unavailable for %s: %s", file.filename, exc)
        raise HTTPException(status_code=503, detail="Vision service unavailable")
    return ImageClaimsResponse(filename=meta.filename, claims=claims)


@router.post(
    "/verify-image",
    response_model=ImageVerificationResponse,
    summary="Verify every claim extracted from an image (V2 Phase 3)",
    description=(
        "Accepts a multipart/form-data upload of an image file (PNG, JPG, "
        "JPEG, or WEBP), validates it, extracts verifiable factual claims "
        "with Kimi Vision, then runs every claim through the same search + "
        "verdict pipeline used for PDFs. Returns the full report in the "
        "shape of ``ImageVerificationResponse``. No new verification engine — "
        "the image flow reuses ``search_service``, ``verdict_service``, and "
        "the ``verify_single_claim`` primitive from ``verification_pipeline``. "
        "Up to 5MB."
    ),
    responses={
        200: {"description": "Verification report (summary + per-claim verdicts)"},
        400: {
            "model": ErrorResponse,
            "description": "Unsupported format or corrupted image",
        },
        413: {"model": ErrorResponse, "description": "Image exceeds MAX_IMAGE_SIZE_MB"},
        503: {"model": ErrorResponse, "description": "Vision service unavailable"},
    },
)
async def verify_image(file: UploadFile = File(...)):
    contents = await file.read()
    meta = validate_image_contents(contents, file.filename, file.content_type)
    t0 = time.perf_counter()
    try:
        claims = await extract_claims_from_image(
            contents, meta.filename, meta.mime_type
        )
    except VisionServiceError as exc:
        logger.error("Vision service unavailable for %s: %s", file.filename, exc)
        raise HTTPException(status_code=503, detail="Vision service unavailable")

    verified = await verify_image_claims(claims)
    summary = summarize_image_verdicts(verified)
    elapsed = round(time.perf_counter() - t0, 3)
    return ImageVerificationResponse(
        filename=meta.filename,
        summary=summary,
        claims=verified,
        processing_time_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Background-job verify (Phase 13)
# ---------------------------------------------------------------------------
# The synchronous /api/verify endpoint was killed by Render's 30s free-tier
# proxy timeout whenever the LLM cold-start pushed the pipeline past that
# wall. The new pattern: POST returns a job_id in <100ms, the client polls
# GET /api/verify/{job_id} for progress and the final result. The actual
# work runs as a background task that is allowed up to 120s (well past the
# Render 30s HTTP window, but still bounded for safety).
JOB_VERIFY_WALL_BUDGET_SECONDS = 120.0


@router.post(
    "/verify",
    response_model=None,
    summary="Start a background verification job (returns job_id immediately)",
    description=(
        "Accepts a JSON body ``{text, filename}`` and starts a background "
        "verification job. Returns ``{job_id, status: \"pending\"}`` in "
        "less than 100ms. The client should poll ``GET /api/verify/{job_id}`` "
        "every 1-2 seconds until ``status`` becomes ``completed``, ``partial``, "
        "or ``failed``. The ``partial`` terminal state means the pipeline "
        "exceeded its wall-clock budget and the response contains the claims "
        "that did finish. This is the new pattern that survives Render's 30s "
        "free-tier proxy timeout — the old synchronous endpoint that blocked "
        "the request until the pipeline finished was killed whenever the LLM "
        "cold-start pushed the pipeline past that wall."
    ),
    status_code=202,
    responses={
        202: {"description": "Job accepted; body is {job_id, status}"},
        400: {"model": ErrorResponse, "description": "`text` is required"},
    },
)
async def start_verify(req: VerifyRequest, background_tasks: BackgroundTasks):
    if not req.text:
        raise HTTPException(status_code=400, detail="`text` is required")
    job = job_store_singleton.create()
    background_tasks.add_task(
        _run_verify_job, job.job_id, req.text, req.filename
    )
    return {"job_id": job.job_id, "status": JobStatus.PENDING.value}


@router.get(
    "/verify/{job_id}",
    response_model=None,
    summary="Poll a background verification job for status and result",
    description=(
        "Returns the current state of a job created by ``POST /api/verify``. "
        "The ``status`` field is one of: ``pending`` (not started yet), "
        "``running`` (in progress, see ``progress`` for claim counts), "
        "``completed`` (full result in ``result``), ``partial`` (budget "
        "exceeded; partial result in ``result``), or ``failed`` (see "
        "``error``). Results are kept in memory for 10 minutes after "
        "creation."
    ),
    responses={
        200: {"description": "Current job state"},
        404: {"model": ErrorResponse, "description": "No such job_id (expired or never existed)"},
    },
)
async def get_verify_job(job_id: str):
    job = job_store_singleton.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found or expired")
    return job.to_dict()


async def _run_verify_job(job_id: str, text: str, filename: str) -> None:
    """Background-task entry point. Runs the pipeline and updates the job."""
    from core.config import settings
    from core.logger import logger

    job_store_singleton.mark_running(job_id)

    async def _progress(fields: dict) -> None:
        job_store_singleton.update_progress(job_id, **fields)

    try:
        t0 = time.perf_counter()
        result = await verify_document(
            text=text,
            filename=filename,
            hard_timeout=JOB_VERIFY_WALL_BUDGET_SECONDS,
            progress_cb=_progress,
        )
        result.processing_time_seconds = round(time.perf_counter() - t0, 3)
        result_dict = result.model_dump()
        if result.summary.total == 0:
            job_store_singleton.mark_completed(job_id, result_dict)
        else:
            # Treat any zero-claim-result or budget-exceeded as partial. The
            # pipeline itself signals partial via the per-claim explanation
            # note; we mirror that by re-checking whether any claim carries
            # the partial note.
            from services.verification_pipeline import PARTIAL_RESULT_NOTE
            is_partial = any(PARTIAL_RESULT_NOTE in (c.explanation or "") for c in result.claims)
            if is_partial:
                job_store_singleton.mark_partial(job_id, result_dict)
            else:
                job_store_singleton.mark_completed(job_id, result_dict)
    except Exception as exc:  # defensive — verify_document already swallows
        logger.exception("Background verify job %s crashed: %s", job_id, exc)
        job_store_singleton.mark_failed(job_id, str(exc))


# ---------------------------------------------------------------------------
# Legacy / synchronous helpers (kept for tests and direct API access). These
# are NOT registered under /api/verify anymore (the new background-job route
# replaced them) but are still exposed under /api/verify-sync for diagnostic
# use and integration tests.
# ---------------------------------------------------------------------------


@router.post(
    "/verify-sync",
    response_model=VerifyResponse,
    summary="[Internal] Synchronous verify — DEPRECATED, use POST /api/verify",
    description=(
        "Synchronous version of /api/verify. Blocks until the pipeline "
        "finishes. Suitable for local development and integration tests "
        "only. WILL time out on Render's free tier for any non-trivial "
        "document. Prefer the async /api/verify + /api/verify/{job_id} "
        "pattern in production."
    ),
    responses={
        200: {"description": "Verification report (summary + per-claim verdicts)"},
        400: {"model": ErrorResponse, "description": "`text` is required"},
    },
)
async def verify_sync(req: VerifyRequest):
    if not req.text:
        raise HTTPException(status_code=400, detail="`text` is required")
    t0 = time.perf_counter()
    result = await verify_document(req.text, req.filename)
    result.processing_time_seconds = round(time.perf_counter() - t0, 3)
    return result


@router.post(
    "/extract-claims",
    response_model=list[ExtractedClaim],
    summary="Extract structured factual claims from text",
    description=(
        "Sends the provided text to the LLM (moonshotai/kimi-k2.6) with thinking disabled and a 60s request timeout, "
        "and returns a list of structured factual claims with type and source sentence. "
        "Input is truncated to the first 8000 characters. Returns 200 with an empty list "
        "on parse failure or LLM error; 500 is reserved for unhandled router-level errors."
    ),
    responses={
        200: {"description": "Claims extracted (possibly empty list)"},
        500: {"model": ErrorResponse, "description": "Claim extraction failed unexpectedly"},
    },
)
async def extract_claims_endpoint(req: ExtractClaimsRequest):
    return await extract_claims(req.text)


@router.post(
    "/search-claim",
    response_model=ClaimEvidence,
    summary="Search web evidence for a claim",
    description=(
        "Search internet sources related to a claim and return up to "
        "MAX_SEARCH_RESULTS ranked evidence sources (title, url, content). "
        "Results are deduplicated by URL, filtered for completeness, and "
        "ranked by source quality (Tier 1: government / international / "
        "official; Tier 2: research and reputable publications; Tier 3: "
        "other). This endpoint returns evidence only — no verdict, no "
        "scoring, no fact-check judgement."
    ),
    responses={
        200: {"description": "Evidence retrieved (possibly empty list)"},
        500: {"model": ErrorResponse, "description": "Search failed unexpectedly"},
    },
)
async def search_claim_endpoint(req: ExtractedClaim) -> ClaimEvidence:
    evidence = search_claim(req)
    return ClaimEvidence(claim=req.claim, evidence=evidence)


@router.post(
    "/generate-verdict",
    response_model=ClaimVerification,
    summary="Generate a verdict for a claim given evidence",
    description=(
        "Takes a claim and pre-collected web evidence (SearchResult list) and "
        "asks the LLM to evaluate the claim against the evidence consensus. "
        "Returns a ClaimVerification (verdict, explanation, correct_fact, "
        "source_url). The service never raises — LLM errors, malformed JSON, "
        "and validation failures all return a safe-fallback "
        "ClaimVerification(verdict='false', explanation='Unable to verify claim "
        "due to processing failure.', correct_fact='', source_url=''). "
        "Temperature 0.1, max_tokens 1024, thinking off."
    ),
    responses={
        200: {"description": "Verdict generated (always 200; SAFE_FALLBACK on any failure)"},
        500: {"model": ErrorResponse, "description": "Reserved for unhandled router-level errors"},
    },
)
async def generate_verdict_endpoint(req: GenerateVerdictRequest) -> ClaimVerification:
    return await generate_verdict(req.claim, req.evidence)


@router.post(
    "/verify-claim",
    response_model=VerifyClaimResponse,
    summary="Full single-claim pipeline: search + verdict",
    description=(
        "Takes a single claim (ExtractedClaim) and runs the full evidence-and-"
        "verdict pipeline: search_claim() collects web evidence, generate_verdict() "
        "evaluates the claim against the evidence consensus, and a "
        "VerifyClaimResponse is returned. Latency is dominated by Tavily search "
        "(up to SEARCH_TIMEOUT_SECONDS) plus the LLM verdict call. The service "
        "never raises — on any failure the verdict will be a safe-fallback "
        "false with an explanation."
    ),
    responses={
        200: {"description": "Claim verified (verdict may be safe-fallback 'false')"},
        500: {"model": ErrorResponse, "description": "Reserved for unhandled router-level errors"},
    },
)
async def verify_claim_endpoint(req: ExtractedClaim) -> VerifyClaimResponse:
    evidence = search_claim(req)
    verdict = await generate_verdict(req, evidence)
    return VerifyClaimResponse(claim=req.claim, verdict=verdict)
