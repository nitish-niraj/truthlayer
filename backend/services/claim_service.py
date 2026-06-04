"""Claim-extraction service (Phase 3 + Phase 11.5).

Responsibility: take raw document text and return a list of structured
``ExtractedClaim`` records. Never raises — any failure (LLM error, malformed
JSON, per-item validation) returns ``[]`` so the router always responds
with a 200 + a valid (possibly empty) list.

Phase 11.5 additions:
- ``_parse_json_array`` now scans the LLM response for the **first balanced
  JSON array** it can successfully parse, instead of naively slicing from
  the first ``[`` to the last ``]``. This recovers from common failure modes
  where the model emits preamble, prose, trailing commentary, or multiple
  JSON snippets in a single response.
- Logs the offending prefix (truncated) at WARNING level so QA can see what
  the model is actually returning, without dumping the whole response.
"""

import asyncio
import json
import re
import time
from typing import Any, List

import openai
from pydantic import ValidationError

from core.config import settings
from core.llm_client import MODEL_NAME, get_llm_client
from core.logger import logger
from models.schemas import ExtractedClaim

# Claim extraction — model and provider configuration
# Model:         moonshotai/kimi-k2.6 (NVIDIA Inference API, OpenAI-compatible)
# Base URL:      https://integrate.api.nvidia.com/v1  (see core.llm_client)
CLAIM_EXTRACTION_TEMPERATURE = settings.CLAIM_EXTRACTION_TEMPERATURE
CLAIM_EXTRACTION_MAX_TOKENS = settings.CLAIM_EXTRACTION_MAX_TOKENS
CLAIM_EXTRACTION_TIMEOUT_SECONDS = settings.CLAIM_EXTRACTION_TIMEOUT_SECONDS
CLAIM_EXTRACTION_TOP_P = 1.0
CLAIM_EXTRACTION_THINKING = False
CLAIM_SLOW_THRESHOLD_SECONDS = 20.0

CLAIM_EXTRACTION_PROMPT = """You are a fact-checking assistant. Read the following document text carefully and extract ALL specific verifiable claims.

Extract claims of these types:
- Statistics and percentages (e.g. "73% of users prefer...")
- Financial figures and revenue numbers (e.g. "Revenue reached $4.2B in 2023")
- Dates, years, and timelines (e.g. "Launched in Q3 2021")
- Technical metrics (e.g. "Model achieved 94.2% accuracy")
- Named attributions with measurable facts (e.g. "According to WHO, 2.3 million...")

Do NOT extract:
- Opinions or subjective statements
- Generic marketing language
- Predictions or forecasts
- Vague statements without measurable facts

Return ONLY a valid JSON array. No explanation. No markdown. No preamble.
Format:
[
  {{
    "claim": "exact claim text",
    "type": "statistic|financial|date|technical|attribution",
    "source_sentence": "full sentence containing the claim"
  }}
]

Document text:
{text}"""


def _strip_markdown_fence(raw: str) -> str:
    """Strip a leading ````json ... ```` fence if present."""
    cleaned = raw.strip()
    if not cleaned.startswith("```"):
        return cleaned
    parts = cleaned.split("```")
    if len(parts) < 2:
        return cleaned
    inner = parts[1]
    if inner.startswith("json"):
        inner = inner[4:]
    return inner.strip()


def _balanced_json_candidates(raw: str) -> List[str]:
    """Return every balanced top-level ``[...]`` substring found in ``raw``.

    Uses a simple bracket-depth counter and respects string literals so we
    don't mis-count brackets that appear inside JSON string values. The
    returned substrings are extracted **as they appear in the original
    string** so each candidate can be parsed independently.
    """
    candidates: List[str] = []
    depth = 0
    start = -1
    in_string = False
    escape = False
    for idx, ch in enumerate(raw):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "[":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "]":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(raw[start : idx + 1])
                start = -1
    return candidates


def _parse_json_array(raw: str) -> List[Any]:
    """Best-effort JSON-array extraction from an LLM response.

    Recovery strategy, in order:
      1. Strip a leading ```` ```json ... ``` ```` fence.
      2. If the response starts with ``[``, find every balanced
         ``[...]`` substring and try parsing each — first one that parses
         as a JSON array wins. This handles prose around the array and
         multiple ``[...]`` blocks (e.g. when the model emits a second
         "reasoning" array after the real one).
      3. Fall back to the legacy "first ``[`` to last ``]``" slice for
         single-array responses.
    """
    cleaned = _strip_markdown_fence(raw)
    if not cleaned:
        raise ValueError("Empty LLM response")

    if cleaned.startswith("["):
        for candidate in _balanced_json_candidates(cleaned):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                return parsed
        # Fall through to the legacy slice.

    # Legacy fallback: first '[' to last ']'.
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found in response")
    return json.loads(cleaned[start : end + 1])


async def extract_claims(text: str) -> List[ExtractedClaim]:
    logger.info("Claim extraction started")
    start = time.perf_counter()
    truncated = text[:8000]

    try:
        client = get_llm_client()
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL_NAME,
            messages=[{"role": "user", "content": CLAIM_EXTRACTION_PROMPT.format(text=truncated)}],
            temperature=CLAIM_EXTRACTION_TEMPERATURE,
            top_p=CLAIM_EXTRACTION_TOP_P,
            max_tokens=CLAIM_EXTRACTION_MAX_TOKENS,
            stream=False,
            timeout=CLAIM_EXTRACTION_TIMEOUT_SECONDS,
            extra_body={"chat_template_kwargs": {"thinking": CLAIM_EXTRACTION_THINKING}},
        )
    except openai.APITimeoutError as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            f"Extraction timeout after {elapsed:.2f}s (cap={CLAIM_EXTRACTION_TIMEOUT_SECONDS}s): {exc}"
        )
        return []
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(f"LLM extraction failed after {elapsed:.2f}s: {exc}")
        return []

    elapsed = time.perf_counter() - start
    logger.info(f"Claim extraction completed in {elapsed:.2f} seconds")
    if elapsed > CLAIM_SLOW_THRESHOLD_SECONDS:
        logger.warning(
            f"Extraction exceeded {CLAIM_SLOW_THRESHOLD_SECONDS:.0f} seconds ({elapsed:.2f}s)"
        )

    raw = response.choices[0].message.content
    reasoning = getattr(response.choices[0].message, "reasoning_content", None)
    if reasoning:
        logger.debug(f"LLM reasoning trace: {reasoning[:500]}")

    try:
        data = _parse_json_array(raw)
    except Exception as exc:
        preview = (raw or "").strip()[:200]
        logger.warning(
            f"JSON parse failure: {exc}; response preview: {preview!r}"
        )
        return []

    claims: List[ExtractedClaim] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            claims.append(ExtractedClaim(**item))
        except ValidationError as exc:
            logger.warning(f"Skipping invalid claim: {exc}")
            continue

    logger.info(f"Claims extracted: {len(claims)}")
    return claims
