"""Measurement: units, scale, and tolerances.

The deterministic core of ArchTutor and the only place a unit conversion or a
scale calculation may happen. Depends on nothing outside the standard library
and this package. No LLM, no web framework, no geometry library.

    >>> actual_to_drawing(4200, 50)
    Decimal('84.0')
    >>> actual_to_drawing(230, 50)
    Decimal('4.6')
    >>> drawing_to_actual(4.6, 50)
    Decimal('230.0')
"""

from app.measurement.errors import (
    InvalidDimensionError,
    InvalidScaleError,
    InvalidToleranceError,
    InvalidUnitError,
    MeasurementError,
)
from app.measurement.scale import (
    DRAWING_READING_RESOLUTION_MM,
    MIN_SCALE_DENOMINATOR,
    SUPPORTED_SCALES,
    actual_to_drawing,
    calculate_scale,
    drawing_to_actual,
    format_scale,
    validate_scale,
    within_tolerance,
)
from app.measurement.units import (
    MM_PER_UNIT,
    SUPPORTED_UNITS,
    Unit,
    convert_unit,
    mm,
    to_actual_mm,
    to_decimal,
    validate_unit,
)

__all__ = [
    # errors
    "MeasurementError",
    "InvalidUnitError",
    "InvalidScaleError",
    "InvalidDimensionError",
    "InvalidToleranceError",
    # units
    "Unit",
    "SUPPORTED_UNITS",
    "MM_PER_UNIT",
    "convert_unit",
    "to_actual_mm",
    "to_decimal",
    "validate_unit",
    "mm",
    # scale
    "SUPPORTED_SCALES",
    "MIN_SCALE_DENOMINATOR",
    "DRAWING_READING_RESOLUTION_MM",
    "actual_to_drawing",
    "drawing_to_actual",
    "calculate_scale",
    "within_tolerance",
    "format_scale",
    "validate_scale",
]
