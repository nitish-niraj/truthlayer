from fastapi import HTTPException

from core.config import settings


def validate_extension(filename: str) -> None:
    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")


def validate_magic_bytes(contents: bytes) -> None:
    if not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF file")


def validate_file_size(contents: bytes) -> None:
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File must be under {settings.MAX_FILE_SIZE_MB}MB",
        )
