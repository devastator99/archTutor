"""HTTP routes for the measurement engine.

Thin by rule: parse, delegate to :mod:`app.measurement`, serialise. Every
number this module returns was computed by deterministic code. There is no LLM
call on this path, and adding one would be a defect.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.measurement import actual_to_drawing, convert_unit, drawing_to_actual
from app.schemas.measurement import (
    ScaleConversionRequest,
    ScaleConversionResponse,
    UnitConversionRequest,
    UnitConversionResponse,
)

router = APIRouter(prefix="/measurements", tags=["measurements"])


@router.post("/convert", response_model=UnitConversionResponse)
def convert(request: UnitConversionRequest) -> UnitConversionResponse:
    """Convert a length between mm, cm and m."""
    return UnitConversionResponse(
        value=convert_unit(request.value, request.from_unit, request.to_unit),
        unit=request.to_unit,
    )


@router.post("/scale", response_model=ScaleConversionResponse)
def scale(request: ScaleConversionRequest) -> ScaleConversionResponse:
    """Convert a millimetre length between actual space and drawing space.

    ``actual_to_drawing`` divides by the denominator, ``drawing_to_actual``
    multiplies. Both are exact Decimals; the drawing-side result is quantised to
    0.1 mm, the finest a draughtsman can read.
    """
    if request.direction == "actual_to_drawing":
        value = actual_to_drawing(request.value, request.scale_denominator)
    else:
        value = drawing_to_actual(request.value, request.scale_denominator)

    return ScaleConversionResponse(
        value=value,
        direction=request.direction,
        scale_denominator=request.scale_denominator,
    )
