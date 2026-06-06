"""Structured HTTP error helpers (V2 Phase 5).

A consistent error envelope lets the frontend distinguish:
- ``error`` — short machine code (e.g. ``"file_too_large"``)
- ``detail`` — human-readable message for the UI
- ``request_id`` — propagation token so a user can quote it in a bug report

Every helper returns a :class:`fastapi.HTTPException` so it works inside
both sync and async route handlers and propagates through the global
exception handler cleanly.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException


def error_response(
    status_code: int,
    error: str,
    detail: str,
    request_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> HTTPException:
    """Build an HTTPException with a structured ``detail`` payload.

    Example::

        raise error_response(
            status_code=400,
            error="invalid_image",
            detail="The file is not a valid image.",
        )
    """
    payload: Dict[str, Any] = {"error": error, "detail": detail}
    if request_id:
        payload["request_id"] = request_id
    if extra:
        payload.update(extra)
    return HTTPException(status_code=status_code, detail=payload)


def format_http_exception_detail(detail: Any) -> Any:
    """Pass-through so the existing exception handler in main.py can log
    structured details consistently. Kept as a separate function for tests
    that want to assert on the shape.
    """
    if isinstance(detail, dict):
        return detail
    return {"detail": str(detail)}


__all__ = ["error_response", "format_http_exception_detail"]
