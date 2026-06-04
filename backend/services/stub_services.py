"""Stub services used in Phase 1 (no business logic implemented).

As of Phase 6 these stubs are NO LONGER WIRED into the router. The real
`/api/verify` endpoint now calls `services.verification_pipeline.verify_document`.
This file is kept for historical reference only; do not import from here in
new code. The two functions below are dead and can be removed in a future
cleanup pass.
"""

from typing import Dict


def extract_text_stub(file_bytes: bytes, filename: str) -> Dict:
    # Intentionally minimal: do not implement PDF parsing in Phase 1
    return {"text": "", "pages": 0, "filename": filename}


def verify_text_stub(text: str, filename: str) -> Dict:
    # Return an empty verification result structure
    return {"filename": filename, "summary": {"total": 0, "verified": 0, "inaccurate": 0, "false": 0}, "claims": []}
