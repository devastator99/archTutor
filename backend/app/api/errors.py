"""Translation of domain errors into HTTP responses.

The dependency arrow points inward: the domain raises :class:`MeasurementError`
and knows nothing about HTTP. This module is where that becomes a 422.
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.measurement.errors import MeasurementError


async def measurement_error_handler(
    request: Request, exc: MeasurementError
) -> JSONResponse:
    """Return 422 with the domain's own message.

    The message is the domain's, not a rewritten one: "a length cannot be
    negative, got -1" is more useful to a caller than a generic "invalid
    request", and losing that detail here would throw away work the engine did.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(exc), "error": type(exc).__name__},
    )
