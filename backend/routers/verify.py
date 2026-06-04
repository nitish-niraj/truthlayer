from fastapi import APIRouter, File, HTTPException, UploadFile

from models.schemas import (
    ClaimEvidence,
    ClaimVerification,
    ErrorResponse,
    ExtractedClaim,
    ExtractClaimsRequest,
    GenerateVerdictRequest,
    UploadResponse,
    VerifyClaimResponse,
    VerifyRequest,
    VerifyResponse,
)
from services.claim_service import extract_claims
from services.pdf_service import extract_text_from_pdf
from services.search_service import search_claim
from services.verdict_service import generate_verdict
from services.verification_pipeline import verify_document

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0"}


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
    "/verify",
    response_model=VerifyResponse,
    summary="Run the complete TruthLayer verification pipeline on document text",
    description=(
        "End-to-end orchestrator (Phase 6). Composes the per-claim services:\n\n"
        "1. `extract_claims(text)` — Kimi K2.6 (thinking off, 2048 max tokens, 60s timeout) extracts structured `ExtractedClaim` objects from the text.\n"
        "2. For each claim (concurrency cap = 5 via `asyncio.Semaphore`):\n"
        "   - `search_claim(claim)` — Tavily (advanced, top 5, dedupe, tier ranking) returns ranked `SearchResult` evidence.\n"
        "   - `generate_verdict(claim, evidence)` — Kimi K2.6 (thinking off, 1024 tokens) returns a `ClaimVerification`.\n"
        "3. Per-claim results are summarised into `SummaryStats {total, verified, inaccurate, false}` and ids 1..N are assigned.\n\n"
    "Latency scales with claim count: per-claim wall time ≈ Tavily search + LLM verdict, capped at `MAX_CLAIMS=20` "
    "claims and 3 concurrent pipelines (Phase 12: lowered from 5 to stay under Render's 30s free-tier proxy timeout). "
    "The pipeline has a hard server-side timeout (`VERIFY_HARD_TIMEOUT_SECONDS`, default 25s) — if it elapses, "
    "the response ships with whatever claims have finished and the rest are marked as 'Unable to verify claim.'.\n\n"
        "Failure policy: never returns 500. Empty text → 400. Zero claims extracted → 200 with a valid `VerifyResponse` "
        "of zero counts. Per-claim failures are absorbed and returned as a defensive-fallback `VerifiedClaim` "
        "(verdict='false', explanation='Unable to verify claim.'). 500 is reserved for truly unhandled router-level errors."
    ),
    responses={
        200: {"description": "Verification report (summary + per-claim verdicts, possibly empty claims list)"},
        400: {"model": ErrorResponse, "description": "`text` is required"},
        500: {"model": ErrorResponse, "description": "Reserved for unhandled router-level errors"},
    },
)
async def verify(req: VerifyRequest):
    if not req.text:
        raise HTTPException(status_code=400, detail="`text` is required")
    return await verify_document(req.text, req.filename)


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
