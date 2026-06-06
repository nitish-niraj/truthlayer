"""Image upload validation for TruthLayer V2.

Phase 1 scope: validate the upload, detect corruption, and return metadata.
No OCR, no vision, no claim extraction.

Exposes two entry points:

- :func:`validate_image_upload` — takes a FastAPI ``UploadFile`` (used by
  ``/api/upload-image``).
- :func:`validate_image_contents` — takes raw bytes plus the original
  filename/content_type. Used by ``/api/extract-image-claims`` so the
  endpoint can keep the bytes in memory and hand them to the vision
  service without a second read.
"""
import io

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from core.config import settings
from core.logger import logger
from models.schemas import ImageUploadResponse

ALLOWED_MIME_TYPES = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
}

EXTENSION_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _detect_mime(filename: str, content_type: str | None) -> str:
    """Resolve a canonical mime type from extension + content_type header.

    Trusts the filename extension over the client-supplied content_type so
    that a mismatched .png sent with ``application/octet-stream`` is still
    classified correctly. Returns an empty string when neither matches.
    """
    name = (filename or "").lower()
    ext = None
    for candidate in EXTENSION_TO_MIME:
        if name.endswith(candidate):
            ext = candidate
            break

    if ext:
        return EXTENSION_TO_MIME[ext]

    if content_type and content_type.lower() in ALLOWED_MIME_TYPES:
        return content_type.lower()

    return ""


def validate_image_contents(
    contents: bytes,
    filename: str,
    content_type: str | None,
) -> ImageUploadResponse:
    """Validate raw image bytes. Used by callers that already hold the bytes.

    Validation order:
        1. Extension + mime type allow-list (400 if unsupported)
        2. File size cap (413 if too large)
        3. Pillow can actually decode the bytes (400 if corrupted)
    """
    mime_type = _detect_mime(filename, content_type)

    if mime_type not in ALLOWED_MIME_TYPES:
        logger.warning("Rejected image upload: unsupported format (%s)", content_type)
        raise HTTPException(
            status_code=400,
            detail="Supported formats: PNG, JPG, JPEG, WEBP",
        )

    logger.info("Image uploaded: %s (%s, %d bytes)", filename, mime_type, len(contents))

    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        logger.warning(
            "Rejected image upload: too large (%d bytes > %d bytes)",
            len(contents),
            max_bytes,
        )
        raise HTTPException(
            status_code=413,
            detail="Image must be under 5MB",
        )

    try:
        with Image.open(io.BytesIO(contents)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.error("Invalid image file: %s (%s)", filename, exc)
        raise HTTPException(status_code=400, detail="Invalid image file") from exc

    return ImageUploadResponse(
        filename=filename,
        file_type="image",
        mime_type=mime_type,
        size_bytes=len(contents),
    )


async def validate_image_upload(file: UploadFile) -> ImageUploadResponse:
    """Read the upload into memory and validate it. Convenience wrapper."""
    contents = await file.read()
    return validate_image_contents(contents, file.filename, file.content_type)
