from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class ClaimType(str, Enum):
    statistic = "statistic"
    financial = "financial"
    date = "date"
    technical = "technical"
    attribution = "attribution"


class VerdictType(str, Enum):
    verified = "verified"
    inaccurate = "inaccurate"
    false = "false"


class ExtractedClaim(BaseModel):
    claim: str
    type: ClaimType
    source_sentence: str


class SearchResult(BaseModel):
    title: str
    url: str
    content: str


class ClaimEvidence(BaseModel):
    claim: str
    evidence: List[SearchResult]


class ClaimVerification(BaseModel):
    verdict: VerdictType
    explanation: str
    correct_fact: str
    source_url: str


class GenerateVerdictRequest(BaseModel):
    claim: ExtractedClaim
    evidence: List[SearchResult]


class VerifyClaimResponse(BaseModel):
    claim: str
    verdict: ClaimVerification


class VerifyRequest(BaseModel):
    text: str
    filename: str


class ExtractClaimsRequest(BaseModel):
    text: str


class VerifiedClaim(BaseModel):
    id: int
    claim: str
    type: ClaimType
    source_sentence: str
    verdict: VerdictType
    explanation: str
    correct_fact: str
    source_url: str


class SummaryStats(BaseModel):
    total: int
    verified: int
    inaccurate: int
    false: int


class UploadResponse(BaseModel):
    text: str
    pages: int
    filename: str


class ImageUploadResponse(BaseModel):
    filename: str
    file_type: str
    mime_type: str
    size_bytes: int


class ImageClaimsResponse(BaseModel):
    filename: str
    claims: List[ExtractedClaim]


class ImageVerificationResponse(BaseModel):
    filename: str
    summary: SummaryStats
    claims: List[VerifiedClaim]
    # Optional wall-clock duration of the full verification run, measured at
    # the router layer. None when the timing is not available (e.g. legacy
    # callers, mocked tests, or when the run aborted before completion).
    processing_time_seconds: Optional[float] = None


class VerifyResponse(BaseModel):
    filename: str
    summary: SummaryStats
    claims: List[VerifiedClaim]
    # Optional wall-clock duration of the full verification run, measured at
    # the router layer. None when the timing is not available.
    processing_time_seconds: Optional[float] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
