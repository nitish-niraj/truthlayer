import fitz
from fastapi.testclient import TestClient

from core.config import settings


def make_pdf_bytes(text: str = "Hello world", pages: int = 1) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((50, 50), f"{text} page {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def make_empty_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def make_corrupted_pdf_bytes() -> bytes:
    return b"%PDF-1.4\nthis is not a real PDF body"


def test_valid_pdf_upload(client: TestClient):
    pdf_bytes = make_pdf_bytes("The sky is blue", pages=2)

    response = client.post(
        "/api/upload",
        files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "report.pdf"
    assert body["pages"] == 2
    assert "The sky is blue page 1" in body["text"]
    assert "The sky is blue page 2" in body["text"]


def test_invalid_extension(client: TestClient):
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"plain text content", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are accepted"


def test_file_too_large(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 0)

    pdf_bytes = make_pdf_bytes("anything")
    response = client.post(
        "/api/upload",
        files={"file": ("big.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 413
    assert "under" in response.json()["detail"]


def test_corrupted_pdf(client: TestClient):
    response = client.post(
        "/api/upload",
        files={"file": ("broken.pdf", make_corrupted_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code in (400, 500)
    assert response.json()["detail"] in ("Invalid PDF file", "Failed to parse PDF")


def test_empty_pdf(client: TestClient):
    response = client.post(
        "/api/upload",
        files={"file": ("blank.pdf", make_empty_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "PDF contains no readable text"
