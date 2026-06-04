import fitz
from fastapi import HTTPException, UploadFile

from core.logger import logger
from models.schemas import UploadResponse
from utils.file_validation import (
    validate_extension,
    validate_file_size,
    validate_magic_bytes,
)


async def extract_text_from_pdf(file: UploadFile) -> UploadResponse:
    validate_extension(file.filename)

    contents = await file.read()
    logger.info(f"PDF uploaded: {file.filename}")

    validate_file_size(contents)
    validate_magic_bytes(contents)

    try:
        doc = fitz.open(stream=contents, filetype="pdf")
    except Exception:
        logger.error(f"Invalid PDF file: {file.filename}")
        raise HTTPException(status_code=400, detail="Invalid PDF file")

    try:
        page_count = doc.page_count
        page_texts = [doc.load_page(i).get_text() for i in range(page_count)]
    except Exception:
        logger.error(f"Failed to parse PDF: {file.filename}")
        raise HTTPException(status_code=500, detail="Failed to parse PDF")
    finally:
        doc.close()

    full_text = "\n".join(page_texts)
    logger.info(f"Pages extracted: {page_count}")

    if not full_text.strip():
        raise HTTPException(status_code=422, detail="PDF contains no readable text")

    return UploadResponse(filename=file.filename, pages=page_count, text=full_text)
