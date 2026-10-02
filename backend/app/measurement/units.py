"""Unit handling: millimetres, centimetres, metres.

PRECISION STRATEGY (documented, deliberate, and load-bearing)
--------------------------------------------------------------
ArchTutor has two coordinate spaces, and they do not share a resolution:

* **Actual space** (the building) -- the canonical unit is the integer
  millimetre, per the constitution. Architectural dimensions are whole
  millimetres: 4200, 3600, 230, 900.

* **Drawing space** (the paper) -- millimetres too, but *decimal*, because a
  draughtsman draws to a scale and reads with a scale rule. A 230 mm wall at
  1:50 is 4.6 mm on the sheet, not 5 mm. The finest increment that can
  actually be drawn and read is 0.1 mm, so drawing results are quantised to
  ``DRAWING_RESOLUTION_MM``.

This is why "integer millimetres everywhere" is not the whole rule. Rounding
4.6 to 5 would make a correct drawing fail validation by 4 mm of real
equivalent, which is the single most damaging bug this component could have.

All arithmetic uses :class:`decimal.Decimal`. Binary floating point is never
used for a dimension: 0.1 + 0.2 != 0.3 in ``float``, and a student who is told
their wall is 0.3 mm thick has been told a falsehood.

Quotients are **not** rounded. A conversion like 230 mm at 1:500 is exactly
0.46 mm, and rounding that to 0.5 mm invents 20 mm of building that does not
exist. Deciding how many decimals to *display* is a presentation concern and
belongs at the UI boundary; the engine's job is to be right, not tidy.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Final, Literal, get_args

from app.measurement.errors import InvalidDimensionError, InvalidUnitError

Unit = Literal["mm", "cm", "m"]
"""Supported architectural units. Millimetre-based; no imperial units."""

SUPPORTED_UNITS: Final[tuple[Unit, ...]] = get_args(Unit)

MM_PER_UNIT: Final[dict[Unit, Decimal]] = {
    "mm": Decimal(1),
    "cm": Decimal(10),
    "m": Decimal(1000),
}


def to_decimal(value: Decimal | int | float | str) -> Decimal:
    """Coerce to ``Decimal`` without inheriting binary float error.

    ``float`` input is routed through :func:`str` deliberately: ``Decimal(0.1)``
    is the exact binary expansion of the float 0.1, whereas ``Decimal("0.1")``
    is the number a human wrote. Floats are tolerated at the boundary; they
    never become the internal representation.
    """
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, bool):
        # bool is an int subclass; True must never become 1 mm.
        raise InvalidDimensionError("a boolean is not a dimension")
    elif isinstance(value, int):
        candidate = Decimal(value)
    elif isinstance(value, float):
        candidate = Decimal(str(value))
    elif isinstance(value, str):
        try:
            candidate = Decimal(value.strip())
        except InvalidOperation as exc:
            raise InvalidDimensionError(f"not a number: {value!r}") from exc
    else:
        raise InvalidDimensionError(f"not a number: {value!r}")

    if not candidate.is_finite():
        raise InvalidDimensionError(f"dimension must be finite, got {value!r}")
    return candidate


def validate_unit(unit: str) -> Unit:
    """Return the unit, or reject it with the list of supported units."""
    if unit not in MM_PER_UNIT:
        raise InvalidUnitError(
            f"unsupported unit {unit!r}; supported units: "
            f"{', '.join(SUPPORTED_UNITS)}"
        )
    return unit  # type: ignore[return-value]


def convert_unit(
    value: Decimal | int | float | str,
    from_unit: Unit,
    to_unit: Unit,
    *,
    allow_negative: bool = False,
) -> Decimal:
    """Convert a length between mm, cm and m.

    Exact, and deliberately unquantised: 1 cm to mm is 10, not 10.0 rounded to
    somewhere. Quantisation is a property of a *space* (see the module
    docstring) and is applied by the scale functions, not here.

    Zero is a valid length and is accepted. Negative lengths are not, unless a
    caller explicitly opts in (a signed offset is not a dimension).
    """
    source = validate_unit(from_unit)
    target = validate_unit(to_unit)

    amount = to_decimal(value)
    if amount < 0 and not allow_negative:
        raise InvalidDimensionError(f"a length cannot be negative, got {amount}")

    millimetres = amount * MM_PER_UNIT[source]
    return millimetres / MM_PER_UNIT[target]


def to_actual_mm(value: Decimal | int | float | str, unit: Unit = "mm") -> Decimal:
    """Normalise a length in any supported unit to actual millimetres."""
    return convert_unit(value, unit, "mm")


def mm(value: Decimal | int | float | str) -> int:
    """Round a length to a whole actual millimetre.

    Used where the result is a *specification* that must be stored and compared
    exactly, such as an exercise's room size. Ties round away from zero, which
    is what a person reading a dimension does. Never use this on drawing-space
    values -- see :data:`DRAWING_RESOLUTION_MM`.
    """
    amount = to_decimal(value)
    if amount < 0:
        raise InvalidDimensionError(f"a length cannot be negative, got {amount}")
    return int(amount.quantize(Decimal(1), rounding="ROUND_HALF_UP"))
