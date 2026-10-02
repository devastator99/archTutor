"""The FastAPI application factory.

Kept as a factory so tests can build an isolated app instance rather than
importing a module-level singleton.

Wiring only. The interesting decisions live in the modules this file connects:
:mod:`app.api.security` for input limits and safe errors,
:mod:`app.core.logging` for structured events, and
:mod:`app.api.routes.exercises` for the request flow.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import measurement_error_handler
from app.api.routes import exercises, health, measurements
from app.api.security import RequestSizeLimitMiddleware, safe_error_response
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.measurement.errors import MeasurementError

logger = get_logger("http")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="ArchTutor API",
        version="0.2.0",
        description=(
            "Drafting practice and feedback for B.Arch students. "
            "Deterministic code owns every measurement; the tutor only explains."
        ),
    )

    # Body size is checked before routing, so a 500 MB body to /validate is
    # rejected without being parsed. Added first so CORS wraps it: a rejected
    # body must still reach the browser with CORS headers, or the student sees
    # an opaque network error instead of "too large".
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    # Domain errors -> HTTP. Registered here so the domain stays HTTP-free.
    app.add_exception_handler(MeasurementError, measurement_error_handler)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        """Tag every request so a log line can be traced back to a request.

        Honours an inbound ``x-request-id`` so a trace survives a proxy hop.
        """
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        """No stack trace, no path, no library version reaches the client.

        The correlation id goes in the response and in the log line, so a
        student can quote it and an operator can find the failure, without the
        response itself describing the server.
        """
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        logger.log(
            logging.ERROR,
            "http.unhandled_error",
            extra={"fields": {"request_id": request_id, "error": type(exc).__name__}},
        )
        response = safe_error_response(exc, request_id=request_id)
        # The response is built here rather than returned by the middleware
        # above, which is bypassed entirely when an exception propagates past
        # it. Without this the student gets a correlation id in the body but not
        # in the headers, and quoting it to support still finds nothing to grep.
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(measurements.router)
    app.include_router(exercises.router)

    return app


app = create_app()
