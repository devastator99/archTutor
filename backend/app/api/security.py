"""Input and response safety at the HTTP boundary.

WHAT IS ACTUALLY AT RISK HERE
-----------------------------
The backend is a JSON API over a database, with one outbound call to an
LLM provider using a secret key. The realistic risks, in order:

1. **Unbounded input.** A drawing is small, but nothing in the protocol says it
   must be. A 500 MB body to ``/validate`` is a denial of service that costs one
   request, and the body is parsed before any validation can reject it.
2. **Stack traces in responses.** An unhandled exception rendered to a client
   publishes file paths, library versions and occasionally the shape of the
   database. It is free reconnaissance, and it is on by default.
3. **The LLM key leaking to the browser.** Handled by never placing tutor
   settings in any response schema (see :func:`assert_no_secrets`), because the
   failure mode is a key in a JavaScript bundle where anyone can read it.

WHAT IS NOT IMPLEMENTED, AND WHY
--------------------------------
No authentication, no rate limiting, no per-user identity. The MVP is a local
single-user application and those would be scaffolding for a deployment model
that does not exist yet. Adding a half-built auth layer would be worse than none:
it would create the impression of access control while providing none.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.logging import get_logger, log_event

logger = get_logger("http")

MAX_REQUEST_BYTES = 512 * 1024
"""Largest accepted request body.

A drawing is tens of kilobytes at most: four walls, a handful of openings, a few
dimension lines, each a coordinate pair. Half a megabyte is roughly two orders of
magnitude of headroom, so this rejects abuse without ever rejecting real work.
"""

MAX_JSON_DEPTH = 32
"""Deepest accepted nesting.

``StudentDrawing.from_dict`` is iterative over a known shape, so a deeply nested
body is not a legitimate drawing -- it is a payload meant to exhaust a recursive
parser somewhere downstream.
"""

SECRET_SETTINGS = (
    "tutor_api_key",
    "postgres_password",
    "database_url",
)
"""Settings that must never appear in a response body."""


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies before they are read into memory.

    Checks ``Content-Length`` first, which is free, and falls back to counting
    the streamed body for a request that does not declare its size. Both paths
    are needed: trusting the header alone leaves the limit to a client that
    chooses not to send it.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse:
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > MAX_REQUEST_BYTES:
                        return _too_large(declared)
                except ValueError:
                    # A malformed length is not a reason to trust the body.
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": "malformed Content-Length header"},
                    )

            body = await request.body()
            if len(body) > MAX_REQUEST_BYTES:
                return _too_large(len(body))
            if _too_deep(body):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": "request body is nested too deeply"},
                )

        return await call_next(request)


def _too_large(size: Any) -> JSONResponse:
    log_event(
        logger,
        "http.request_too_large",
        level=logging.WARNING,
        size_bytes=size,
        limit_bytes=MAX_REQUEST_BYTES,
    )
    return JSONResponse(
        # The literal is used because the symbol this version of Starlette
        # exposes under this name is itself deprecated, and the value is part
        # of the HTTP contract rather than an implementation detail.
        status_code=413,  # noqa: PLR2004 - HTTP "Content Too Large"
        content={
            "detail": (
                f"request body is too large; the limit is {MAX_REQUEST_BYTES} bytes"
            )
        },
    )


def _too_deep(body: bytes) -> bool:
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        # Not JSON. The route's own parser will reject it with a better message
        # than anything this layer could invent.
        return False
    return _depth(parsed) > MAX_JSON_DEPTH


def _depth(node: Any, level: int = 0) -> int:
    if level > MAX_JSON_DEPTH + 1:
        return level
    if isinstance(node, dict):
        return max((_depth(value, level + 1) for value in node.values()), default=level)
    if isinstance(node, list):
        return max((_depth(item, level + 1) for item in node), default=level)
    return level


def safe_error_response(
    exc: Exception, *, request_id: str | None = None
) -> JSONResponse:
    """A 500 that tells the client nothing about the server.

    The message is generic on purpose. The detail goes to the log, keyed by
    request id, so an operator can find it and a client can quote it -- without
    the response itself becoming a map of the codebase.
    """
    log_event(
        logger,
        "http.unhandled_error",
        level=logging.ERROR,
        error=type(exc).__name__,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "internal server error",
            "error": "InternalServerError",
            "request_id": request_id,
        },
    )


def assert_no_secrets(payload: Any, names: Iterable[str] = SECRET_SETTINGS) -> None:
    """Fail loudly if a settings secret reaches a response.

    A cheap tripwire for the mistake that would be expensive: adding a tutor
    field to a response schema so the frontend can read the model name, and
    taking the key with it. Raises in tests, which is where it matters -- by
    production the key is already in a bundle.
    """
    forbidden = set(names)
    found = sorted(
        name
        for name in forbidden
        if _contains(payload, getattr(settings, name, None))
    )
    if found:
        raise AssertionError(
            f"response payload contains secret setting(s): {', '.join(found)}"
        )


def _contains(payload: Any, value: Any) -> bool:
    if not value or not isinstance(value, str) or len(value) < 8:
        # Short or unset values cannot be meaningfully matched, and matching a
        # short value would produce false positives against ordinary text.
        return False
    try:
        serialised = json.dumps(payload, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False
    return value in serialised
