"""Geometric primitives: points, lines, distance.

Coordinates are **millimetres**, as :class:`decimal.Decimal`, for the same
reason the measurement engine uses Decimal: an architectural coordinate that
passes through a binary float accumulates error, and a wall that is 0.0001 mm
off is a wall that fails validation for no reason a student could ever see or
fix.

Axis convention: ``x`` increases east, ``y`` increases north. Wall thickness is
always centred on the centreline, which is how a plan is drawn and what makes
the room's clear internal dimension equal to the boundary span.

The MVP supports horizontal and vertical walls only. That is a deliberate
limit, not a simplification to be quietly relaxed later: a diagonal wall would
require the trigonometry this module does not have, and admitting it silently
would let unvalidated geometry into the validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.geometry.errors import InvalidPointError

Coordinate = Decimal | int | float | str


def _coordinate(value: Coordinate, name: str) -> Decimal:
    """Coerce a coordinate to Decimal, rejecting non-finite values."""
    if isinstance(value, bool):
        raise InvalidPointError(f"{name} must be a number, got {value!r}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(str(value))
    else:
        result = Decimal(str(value).strip())
    if not result.is_finite():
        raise InvalidPointError(f"{name} must be finite, got {value!r}")
    return result


@dataclass(frozen=True, slots=True)
class Point:
    """A location in plan, in millimetres."""

    x: Decimal
    y: Decimal

    def __init__(self, x: Coordinate, y: Coordinate) -> None:
        object.__setattr__(self, "x", _coordinate(x, "x"))
        object.__setattr__(self, "y", _coordinate(y, "y"))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Point(x={self.x}, y={self.y})"


@dataclass(frozen=True, slots=True)
class Line:
    """A straight segment between two points."""

    start: Point
    end: Point

    def __init__(self, start: Point, end: Point) -> None:
        for name, value in (("start", start), ("end", end)):
            if not isinstance(value, Point):
                raise InvalidPointError(f"line {name} must be a Point")
        if start == end:
            raise InvalidPointError("a line must have two distinct endpoints")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def length(self) -> Decimal:
        return distance(self.start, self.end)


def distance(a: Point, b: Point) -> Decimal:
    """Euclidean distance between two points, in millimetres.

    Exact for the axis-aligned case the MVP supports, and correctly rounded
    (not truncated) for the general case, because Decimal's square root is
    correctly rounded.
    """
    for name, value in (("a", a), ("b", b)):
        if not isinstance(value, Point):
            raise InvalidPointError(f"{name} must be a Point")
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy).sqrt()


def is_horizontal(a: Point, b: Point) -> bool:
    """True if two points share a y coordinate."""
    return a.y == b.y


def is_vertical(a: Point, b: Point) -> bool:
    """True if two points share an x coordinate."""
    return a.x == b.x
