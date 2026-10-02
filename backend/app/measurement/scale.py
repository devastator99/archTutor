"""Architectural scale: actual millimetres <-> drawing millimetres.

    drawing_mm = actual_mm / scale_denominator
    actual_mm  = drawing_mm * scale_denominator

    4200 mm at 1:50  = 84 mm
    3600 mm at 1:50  = 72 mm
     900 mm at 1:50  = 18 mm
     230 mm at 1:50  = 4.6 mm   <- not 5 mm

Scale is written ``1:N``. The scales a B.Arch student is actually asked to use
are in :data:`SUPPORTED_SCALES`, but they are a documented set, not an
allow-list: :func:`validate_scale` accepts any positive integer N by default,
so an unusual assignment is never rejected for being unusual. Offering the
named set exists for the UI, not for validation.

This module is the single source of truth for scale arithmetic. The LLM must
never perform it -- it receives results computed here. There is no LLM in this
package and there must never be one.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Final

from app.measurement.errors import (
    InvalidDimensionError,
    InvalidScaleError,
    InvalidToleranceError,
)
from app.measurement.units import to_decimal

SUPPORTED_SCALES: Final[tuple[int, ...]] = (20, 50, 100, 200, 500)
"""The scales a student is realistically set. Informational, not restrictive."""

MIN_SCALE_DENOMINATOR: Final[int] = 1
"""1:1 is the identity and is the smallest meaningful scale."""

DRAWING_READING_RESOLUTION_MM: Final[Decimal] = Decimal("0.1")
"""How precisely a *drawn* length can be read off the sheet with a scale rule.

Used only where a human reads a measurement: deriving a scale from a pair.
Never used to round a computed dimension -- see :func:`actual_to_drawing`.
"""


def validate_scale(denominator: int, *, restrict_to_supported: bool = False) -> int:
    """Return the scale denominator, or reject it.

    ``restrict_to_supported`` is off by default: rejecting 1:137 would be
    enforcing a guess about the course, not a fact about scale.
    """
    if isinstance(denominator, bool) or not isinstance(denominator, int):
        raise InvalidScaleError(f"scale denominator must be an int, got {denominator!r}")
    if denominator < MIN_SCALE_DENOMINATOR:
        raise InvalidScaleError(
            f"scale denominator must be >= {MIN_SCALE_DENOMINATOR}, got {denominator}"
        )
    if restrict_to_supported and denominator not in SUPPORTED_SCALES:
        raise InvalidScaleError(
            f"unsupported scale 1:{denominator}; supported: "
            f"{', '.join(f'1:{s}' for s in SUPPORTED_SCALES)}"
        )
    return denominator


def format_scale(denominator: int) -> str:
    """Render a denominator as it is written on a drawing: ``1:50``."""
    return f"1:{validate_scale(denominator)}"


def actual_to_drawing(
    actual_mm: Decimal | int | float | str, scale_denominator: int
) -> Decimal:
    """Convert a real-world millimetre length to its length on paper.

        drawing_mm = actual_mm / scale_denominator

    The result is **exact and unquantised**. This matters more than it looks:
    a 230 mm wall at 1:500 is 0.46 mm on the sheet, and rounding it to 0.5 mm
    would tell the student their wall is 250 mm.

    WHY THE ROUND TRIP IS LOSSLESS
    ------------------------------
    :class:`~decimal.Decimal` division is itself rounded, to the context
    precision (28 significant digits by default). For every scale in
    :data:`SUPPORTED_SCALES` that rounding never bites, because 20, 50, 100,
    200 and 500 all divide into powers of ten: 4200 / 50 is exactly 84, and
    84 * 50 is exactly 4200.

    At an arbitrary denominator whose quotient does not terminate -- 1:137,
    1:7 -- the quotient is rounded to 28 significant digits and the round trip
    returns something like 900.0000000000000000000000002. That residual is
    ~1e-25 relative, some twenty orders of magnitude below the finest thing
    anyone can draw or measure, and it is reported honestly rather than
    rounded away.
    """
    validate_scale(scale_denominator)
    actual = to_decimal(actual_mm)
    if actual < 0:
        raise InvalidDimensionError(f"a dimension cannot be negative, got {actual}")

    return actual / Decimal(scale_denominator)


def drawing_to_actual(
    drawing_mm: Decimal | int | float | str, scale_denominator: int
) -> Decimal:
    """Convert a paper millimetre length back to real-world millimetres.

    Not quantised to whole millimetres, on purpose. This value is what the
    student *actually drew*; rounding it away would destroy the very deviation
    the validator exists to report. 4.6 mm at 1:50 is exactly 230 mm, but
    4.7 mm at 1:50 is exactly 235 mm and that difference is the student's
    mistake, intact.
    """
    validate_scale(scale_denominator)
    drawing = to_decimal(drawing_mm)
    if drawing < 0:
        raise InvalidDimensionError(f"a dimension cannot be negative, got {drawing}")

    return drawing * Decimal(scale_denominator)


def calculate_scale(
    actual_mm: Decimal | int | float | str,
    drawing_mm: Decimal | int | float | str,
) -> int:
    """Derive the scale denominator N from a known actual/drawing pair.

    A candidate scale is accepted only if it reproduces the drawing within the
    drawing resolution. That makes the test independent of any arbitrary
    epsilon: 4200 mm drawn at 84 mm is 1:50 because 1:50 gives back 84.0 mm,
    and 4200 mm drawn at 80 mm is not 1:50 because 1:50 gives back 84.0 mm.
    """
    actual = to_decimal(actual_mm)
    drawing = to_decimal(drawing_mm)

    if drawing <= 0:
        # Zero has no reciprocal; a scale cannot be derived from it. A negative
        # drawing length is a negative length, which is its own error.
        #
        # Both values are named, not just the offending one: this message can
        # reach a student through the scale finding, and "a drawing length of
        # 0" on its own does not say which of the two numbers is wrong.
        raise InvalidDimensionError(
            f"cannot derive a scale from {actual} mm actual and {drawing} mm "
            f"drawn: the drawing length must be greater than 0"
        )
    if actual <= 0:
        raise InvalidDimensionError(
            f"cannot derive a scale from {actual} mm actual and {drawing} mm "
            f"drawn: the actual length must be greater than 0"
        )

    candidate = int((actual / drawing).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if candidate < MIN_SCALE_DENOMINATOR:
        raise InvalidScaleError(
            f"implied scale 1:{candidate} is not a usable scale "
            f"(actual {actual} mm, drawing {drawing} mm)"
        )

    reproduced = actual_to_drawing(actual, candidate)
    if abs(reproduced - drawing) > DRAWING_READING_RESOLUTION_MM:
        raise InvalidScaleError(
            f"no exact scale fits: {actual} mm at 1:{candidate} would draw "
            f"{reproduced} mm, not {drawing} mm"
        )
    return candidate


def within_tolerance(
    measured: Decimal | int | float | str,
    expected: Decimal | int | float | str,
    tolerance: Decimal | int | float | str,
) -> bool:
    """Is ``measured`` within ``tolerance`` of ``expected``?

    Tolerance is an absolute distance in millimetres, not a percentage, because
    that is how a marking tolerance is stated. The comparison is inclusive: a
    deviation of exactly the tolerance passes.

    The comparison is exact -- no implicit rounding. Float noise cannot reach
    it because :func:`to_decimal` routes floats through ``str``, so the float
    ``0.1`` arrives as exactly ``Decimal("0.1")`` rather than its binary
    expansion. Rounding here would instead invent agreement the drawing does
    not have, which is the failure this product exists to prevent.
    """
    limit = to_decimal(tolerance)
    if limit < 0:
        raise InvalidToleranceError(f"a tolerance cannot be negative, got {limit}")

    return abs(to_decimal(measured) - to_decimal(expected)) <= limit
