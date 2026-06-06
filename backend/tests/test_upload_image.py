"""Tests for POST /api/upload-image (V2 Phase 1 — upload + validation only)."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from core.config import settings


def make_png_bytes(color: str = "red", size=(8, 8), fmt: str = "PNG") -> bytes:
    """Create a real, decodable image in memory."""
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    return buf.getvalue()


def make_jpeg_bytes() -> bytes:
    return make_png_bytes(fmt="JPEG")


def make_webp_bytes() -> bytes:
    return make_png_bytes(fmt="WEBP")


def make_corrupted_image_bytes() -> bytes:
    """PNG magic bytes followed by garbage that Pillow cannot decode."""
    return b"\x89PNG\r\n\x1a\nthis is not a real PNG body"


def test_valid_png_upload(client: TestClient):
    png_bytes = make_png_bytes()

    response = client.post(
        "/api/upload-image",
        files={"file": ("screenshot.png", png_bytes, "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "screenshot.png"
    assert body["file_type"] == "image"
    assert body["mime_type"] == "image/png"
    assert body["size_bytes"] == len(png_bytes)


def test_valid_jpeg_upload(client: TestClient):
    jpeg_bytes = make_jpeg_bytes()

    response = client.post(
        "/api/upload-image",
        files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mime_type"] == "image/jpeg"
    assert body["size_bytes"] == len(jpeg_bytes)


def test_valid_webp_upload(client: TestClient):
    webp_bytes = make_webp_bytes()

    response = client.post(
        "/api/upload-image",
        files={"file": ("graphic.webp", webp_bytes, "image/webp")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mime_type"] == "image/webp"


def test_jpeg_extension_with_jpeg_mime(client: TestClient):
    jpeg_bytes = make_jpeg_bytes()

    response = client.post(
        "/api/upload-image",
        files={"file": ("photo.jpeg", jpeg_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mime_type"] == "image/jpeg"


def test_unsupported_format(client: TestClient):
    """GIF is a real image but not in the V2 Phase 1 allow-list."""
    gif_bytes = make_png_bytes(fmt="GIF")

    response = client.post(
        "/api/upload-image",
        files={"file": ("anim.gif", gif_bytes, "image/gif")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Supported formats: PNG, JPG, JPEG, WEBP"


def test_pdf_rejected_on_image_endpoint(client: TestClient):
    response = client.post(
        "/api/upload-image",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Supported formats: PNG, JPG, JPEG, WEBP"


def test_file_too_large(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 0)

    png_bytes = make_png_bytes()
    response = client.post(
        "/api/upload-image",
        files={"file": ("big.png", png_bytes, "image/png")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Image must be under 5MB"


def test_corrupted_image(client: TestClient):
    response = client.post(
        "/api/upload-image",
        files={"file": ("broken.png", make_corrupted_image_bytes(), "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image file"


def test_corrupted_image_no_extension_match(client: TestClient):
    """A file with no extension that isn't a real image is rejected."""
    response = client.post(
        "/api/upload-image",
        files={"file": ("mystery", b"plain text bytes", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Supported formats: PNG, JPG, JPEG, WEBP"
