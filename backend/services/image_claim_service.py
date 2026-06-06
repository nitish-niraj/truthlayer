"""Image claim extraction service (V2 Phase 2).

Responsibility: take a validated image (PNG / JPG / JPEG / WEBP) and ask Kimi
K2.6 vision to extract every verifiable factual claim visible in the image.

Hard constraints for this phase:

- No web search. No Tavily.
- No verdict generation.
- Returns the existing ``ExtractedClaim`` shape so downstream verification
  can consume it the same way it consumes text-derived claims.

Failure handling has two distinct outcomes:

- :class:`VisionServiceError` — raised when the vision LLM is unreachable,
  times out, or returns a malformed/empty body we cannot interpret. The
  router maps this to HTTP 503.
- Empty list ``[]`` — returned when the model succeeded but found no
  verifiable claims, or when the JSON output was malformed (per the
  project-wide "never raise from a service" rule for LLM extraction).
"""
import asyncio
import base64
import io
import json
import time
from typing import List

import openai
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from core.config import settings
from core.llm_client import MODEL_NAME, get_llm_client
from core.logger import logger
from models.schemas import ExtractedClaim
from services.claim_service import _parse_json_array

# Cap the longest side of the image so the base64 payload stays bounded.
# 1280px is large enough to keep infographics / screenshots legible while
# keeping a typical PNG well under ~2MB after base64.
IMAGE_MAX_DIMENSION = 1280

# Vision model and provider configuration — same client as the rest of
# the project. No second AI client.
VISION_TEMPERATURE = 0.1
VISION_TOP_P = 1.0
VISION_MAX_TOKENS = 4096
VISION_THINKING = False
VISION_TIMEOUT_SECONDS = 60
VISION_SLOW_THRESHOLD_SECONDS = 30.0

VISION_PROMPT = """You are a fact-checking assistant.

Analyze the image carefully.

Extract ALL verifiable factual claims shown in the image. This includes claims
visible in:
- Headlines and subheadings
- Body text
- Captions and annotations
- Charts (bar, line, pie, etc.) — read the values off the axes and labels
- Infographics and stat blocks
- Tables and spreadsheets
- Social media posts and screenshots
- Image alt text or overlay text

Focus on claims of these types:
- Statistics and percentages
- Revenue, financial, and market figures
- User counts and growth numbers
- Dates, years, timelines, and durations
- Technical metrics
- Named attributions with measurable facts (e.g. "According to WHO, ...")

Ignore:
- Opinions and subjective statements
- Marketing slogans and taglines
- Generic emotional language
- Vague statements without measurable facts

If the image contains NO verifiable factual claims, return an empty array.

# Chart, Infographic, Table & Visual-Data Extraction (V2 Phase 5)

When the image contains a chart, infographic, table, or any data visualization,
read the underlying data carefully and convert it into self-contained factual
sentences. The downstream fact-checker will search live web sources for each
claim, so every claim must stand on its own without the visual context.

## Bar / line / area / scatter charts
- Read the chart title and the axis labels (e.g. "Global EV Sales (millions)",
  x-axis "Year", y-axis "Units (M)").
- Read the value of each data point or bar that is legibly labeled.
- Emit ONE claim per data point, formatted as a full sentence. For example,
  a bar chart titled "Global EV Sales" with a 2022 bar labeled "7M" yields
  the claim: "Global EV sales reached 7 million units in 2022."
- If the chart implies a trend (e.g. "rising from 2020 to 2024"), emit the
  trend as a single claim like: "Global EV sales rose from 2020 to 2024."

## Pie / donut charts
- Read the chart title and each labeled slice percentage.
- Emit ONE claim per labeled slice as a full sentence. Example: "Renewables
  accounted for 38% of the energy mix in 2023."

## Infographics and stat blocks
- Read each callout, stat block, or pull-quote independently.
- Preserve the source year or date whenever it is visible.
- Example: an infographic with the block "9 in 10 CEOs expect revenue growth
  in 2024" yields the claim: "9 in 10 CEOs expect revenue growth in 2024."

## Tables
- Read each row that contains a verifiable figure.
- Emit a claim that captures the row's subject and value, e.g. "Apple's FY2022
  revenue was $394B per the company's annual report."

## Reports, white papers, and screenshots
- Treat the text in the image exactly like text from a PDF — every factual
  statement, attributed quote with a number, or measurable claim becomes one
  extracted claim.
- For social-media screenshots, attribute the claim to the visible author or
  handle when possible (use the "attribution" type).

## Quality rules for visual extraction
- Do NOT invent values that are not legibly visible.
- Do NOT include axis labels, legends, or units in the claim itself — fold
  the units into the sentence ("7 million units", not "7 M" or "y-axis: 7M").
- If a value is partially obscured or ambiguous, OMIT it rather than guess.
- Emit at most one claim per data point; do not duplicate the same figure
  across multiple sentences.
- Preserve the time period whenever the chart labels a year, quarter, or
  date range.

Return ONLY a valid JSON array. No explanation. No markdown. No preamble.
Format:
[
  {{
    "claim": "exact claim text as it appears in the image or as a full sentence derived from the chart/table",
    "type": "statistic|financial|date|technical|attribution",
    "source_sentence": "the full sentence or visible text fragment in the image that contains the claim"
  }}
]"""


class VisionServiceError(Exception):
    """Raised when the vision LLM cannot be reached or returns a hard error.

    Distinct from "the model ran successfully and found no claims" — the
    latter is a valid 200 response with an empty list.
    """


def _resize_if_needed(contents: bytes) -> bytes:
    """Re-encode the image at no more than IMAGE_MAX_DIMENSION on its longest
    side. Preserves the source format so the bytes stay a real PNG/JPG/WEBP
    the vision encoder can decode.
    """
    try:
        with Image.open(io.BytesIO(contents)) as img:
            width, height = img.size
            longest = max(width, height)
            if longest <= IMAGE_MAX_DIMENSION:
                return contents
            scale = IMAGE_MAX_DIMENSION / longest
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            resized = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            fmt = (img.format or "PNG").upper()
            save_format = "JPEG" if fmt == "JPEG" else fmt
            save_kwargs: dict = {"format": save_format}
            if save_format == "JPEG" and resized.mode in ("RGBA", "LA", "P"):
                resized = resized.convert("RGB")
            resized.save(buf, **save_kwargs)
            return buf.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        # If we can't decode, the caller already validated. Let the original
        # bytes through and let the vision LLM surface the error.
        return contents


def _build_messages(image_bytes: bytes, mime_type: str) -> list[dict]:
    """Build the OpenAI-compatible chat payload with the image as a
    ``data:`` URL content part.
    """
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                },
            ],
        }
    ]


def _coerce_claim_type(value: object) -> str:
    """Best-effort mapping of an LLM-emitted claim type into the enum.

    Falls back to ``statistic`` (the most common bucket for visual claims)
    when the model emits an unknown value. Keeps Pydantic validation from
    rejecting the whole item over a single bad enum value.
    """
    allowed = {"statistic", "financial", "date", "technical", "attribution"}
    if isinstance(value, str) and value.lower() in allowed:
        return value.lower()
    return "statistic"


async def extract_claims_from_image(
    image_bytes: bytes,
    filename: str,
    mime_type: str,
) -> List[ExtractedClaim]:
    """Send an image to Kimi K2.6 vision and return the extracted claims.

    Raises :class:`VisionServiceError` on hard LLM failures. Returns ``[]``
    on parse/validation failures and on the legitimate "no claims" case.
    """
    logger.info("Vision claim extraction started: %s", filename)
    start = time.perf_counter()
    resized = _resize_if_needed(image_bytes)
    messages = _build_messages(resized, mime_type)

    try:
        client = get_llm_client()
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL_NAME,
            messages=messages,
            temperature=VISION_TEMPERATURE,
            top_p=VISION_TOP_P,
            max_tokens=VISION_MAX_TOKENS,
            stream=False,
            timeout=VISION_TIMEOUT_SECONDS,
            extra_body={"chat_template_kwargs": {"thinking": VISION_THINKING}},
        )
    except openai.APITimeoutError as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            f"Vision timeout after {elapsed:.2f}s (cap={VISION_TIMEOUT_SECONDS}s): {exc}"
        )
        raise VisionServiceError("Vision service timeout") from exc
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(f"Vision LLM request failed after {elapsed:.2f}s: {exc}")
        raise VisionServiceError("Vision service unavailable") from exc

    elapsed = time.perf_counter() - start
    logger.info(f"Vision extraction completed in {elapsed:.2f} seconds")
    if elapsed > VISION_SLOW_THRESHOLD_SECONDS:
        logger.warning(
            f"Vision extraction exceeded {VISION_SLOW_THRESHOLD_SECONDS:.0f}s ({elapsed:.2f}s)"
        )

    raw = response.choices[0].message.content
    reasoning = getattr(response.choices[0].message, "reasoning_content", None)
    if reasoning:
        logger.debug(f"Vision reasoning trace: {reasoning[:500]}")

    if not raw or not raw.strip():
        logger.warning("Vision LLM returned empty content")
        return []

    try:
        data = _parse_json_array(raw)
    except Exception as exc:
        preview = (raw or "").strip()[:200]
        logger.warning(
            f"Vision JSON parse failure: {exc}; response preview: {preview!r}"
        )
        return []

    claims: List[ExtractedClaim] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        item["type"] = _coerce_claim_type(item.get("type"))
        try:
            claims.append(ExtractedClaim(**item))
        except ValidationError as exc:
            logger.warning(f"Skipping invalid vision claim: {exc}")
            continue

    logger.info(f"Vision claims extracted: {len(claims)}")
    return claims
