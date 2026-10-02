"""Walls and the openings hosted in them.

A wall is a centreline segment plus a thickness. The thickness is centred on
the centreline, so the drawn faces sit ``thickness / 2`` either side of it and
the clear internal span of a room is the span of its boundary.

An opening (a door or a window) is placed by **offset along its host wall**,
measured from the wall's start point, plus a **width**. It is not placed by
absolute coordinates. That is deliberate: it makes "is this door on the wall,
and does it fit?" a check the backend can answer exactly, and it means a
student who moves a wall does not silently detach its door.

Units are millimetres. Offsets and widths are Decimals, because a door width
divided by a scale is 18.0 mm on paper but the 900 mm real dimension must never
be 899.9999999.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.geometry.errors import (
    GeometryError,
    InvalidOpeningError,
    InvalidWallError,
    MisalignedOpeningError,
)
from app.geometry.primitives import Line, Point, is_horizontal, is_vertical


class Axis(str, enum.Enum):
    """The axis a wall runs along."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


def _to_decimal(value, name: str, error: type[GeometryError]) -> Decimal:
    """Coerce to Decimal, reporting unparseable input as a domain error.

    ``Decimal("thick")`` raises ``decimal.InvalidOperation``, which is neither a
    ``GeometryError`` nor a ``MeasurementError``. Letting it escape would turn a
    student's malformed submission into a 500 rather than a rejected drawing.
    """
    if isinstance(value, bool):
        raise error(f"{name} must be a number, got {value!r}")
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise error(f"{name} must be a number, got {value!r}") from exc
    if not result.is_finite():
        raise error(f"{name} must be finite, got {value!r}")
    return result


def _positive(value, name: str, error: type[GeometryError] = InvalidWallError) -> Decimal:
    result = _to_decimal(value, name, error)
    if result <= 0:
        raise error(f"{name} must be greater than zero, got {result}")
    return result


def _non_negative(
    value, name: str, error: type[GeometryError] = InvalidOpeningError
) -> Decimal:
    result = _to_decimal(value, name, error)
    if result < 0:
        raise error(f"{name} cannot be negative, got {result}")
    return result


@dataclass(frozen=True, slots=True)
class Wall:
    """A wall: a centreline from ``start`` to ``end``, with a thickness.

    Constrained to horizontal or vertical. A diagonal wall is rejected rather
    than approximated, because the MVP's measurements depend on the axis.
    """

    id: uuid.UUID
    start: Point
    end: Point
    thickness_mm: Decimal

    def __init__(
        self,
        start: Point,
        end: Point,
        thickness_mm,
        id: uuid.UUID | None = None,
    ) -> None:
        if not isinstance(start, Point) or not isinstance(end, Point):
            raise InvalidWallError("wall start and end must be Points")
        if start == end:
            raise InvalidWallError("a wall must have two distinct endpoints")
        if not (is_horizontal(start, end) or is_vertical(start, end)):
            raise InvalidWallError(
                f"walls must be horizontal or vertical, got {start} to {end}"
            )
        object.__setattr__(self, "id", id or uuid.uuid4())
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "thickness_mm", _positive(thickness_mm, "thickness"))

    @property
    def axis(self) -> Axis:
        return Axis.HORIZONTAL if is_horizontal(self.start, self.end) else Axis.VERTICAL

    @property
    def centreline(self) -> Line:
        return Line(self.start, self.end)

    @property
    def length_mm(self) -> Decimal:
        """Centreline length in millimetres. Exact: one axis is constant."""
        if self.axis is Axis.HORIZONTAL:
            return abs(self.end.x - self.start.x)
        return abs(self.end.y - self.start.y)

    @property
    def direction(self) -> int:
        """+1 if the wall runs in the positive axis direction, else -1.

        Needed because a wall may be defined right-to-left or bottom-to-top, and
        an opening's offset is always measured from ``start``.
        """
        if self.axis is Axis.HORIZONTAL:
            return 1 if self.end.x > self.start.x else -1
        return 1 if self.end.y > self.start.y else -1

    def point_at(self, offset_mm) -> Point:
        """The point on the centreline ``offset_mm`` from ``start``.

        Direction-aware: a wall defined right-to-left still resolves offsets
        along its own direction.
        """
        offset = _non_negative(offset_mm, "offset")
        step = Decimal(self.direction) * offset
        if self.axis is Axis.HORIZONTAL:
            return Point(self.start.x + step, self.start.y)
        return Point(self.start.x, self.start.y + step)


class OpeningKind(str, enum.Enum):
    DOOR = "door"
    WINDOW = "window"


class SwingDirection(str, enum.Enum):
    """Which way a door leaf swings. A drawing convention, not a measurement."""

    LEFT = "left"
    RIGHT = "right"
    INWARD = "inward"
    OUTWARD = "outward"


@dataclass(frozen=True, slots=True)
class Opening:
    """A void in a wall: a door or a window.

    Positioned by ``offset_mm`` from the host wall's ``start`` and a ``width_mm``.
    """

    id: uuid.UUID
    host_wall_id: uuid.UUID
    offset_mm: Decimal
    width_mm: Decimal
    kind: OpeningKind

    def __init__(
        self,
        host_wall_id: uuid.UUID,
        offset_mm,
        width_mm,
        kind: OpeningKind = OpeningKind.DOOR,
        id: uuid.UUID | None = None,
    ) -> None:
        if not isinstance(host_wall_id, uuid.UUID):
            raise InvalidOpeningError("host_wall_id must be a UUID")
        object.__setattr__(self, "id", id or uuid.uuid4())
        object.__setattr__(self, "host_wall_id", host_wall_id)
        object.__setattr__(self, "offset_mm", _non_negative(offset_mm, "offset_mm"))
        object.__setattr__(
            self,
            "width_mm",
            _positive(width_mm, "width_mm", InvalidOpeningError),
        )
        object.__setattr__(self, "kind", kind)

    @property
    def end_offset_mm(self) -> Decimal:
        """Offset just past the opening's far edge."""
        return self.offset_mm + self.width_mm

    def fits_in(self, wall: Wall) -> bool:
        """Does the opening lie entirely within the wall's extent?"""
        return self.offset_mm >= 0 and self.end_offset_mm <= wall.length_mm

    def validate_placement(self, wall: Wall) -> None:
        """Raise unless this opening is correctly hosted and aligned in ``wall``."""
        if wall.id != self.host_wall_id:
            raise MisalignedOpeningError(
                f"opening {self.id} is hosted by {self.host_wall_id}, not {wall.id}"
            )
        if not self.fits_in(wall):
            raise MisalignedOpeningError(
                f"opening at offset {self.offset_mm} mm with width "
                f"{self.width_mm} mm does not fit in a wall of length "
                f"{wall.length_mm} mm"
            )

    def segment_in(self, wall: Wall) -> tuple[Point, Point]:
        """The two centreline points bounding the opening, in wall coordinates.

        Requires a valid placement; call :meth:`validate_placement` first if the
        input is untrusted.
        """
        self.validate_placement(wall)
        return wall.point_at(self.offset_mm), wall.point_at(self.end_offset_mm)


@dataclass(frozen=True, slots=True)
class Door(Opening):
    """An opening that is a door, with a swing direction."""

    swing_direction: SwingDirection = SwingDirection.LEFT

    def __init__(
        self,
        host_wall_id: uuid.UUID,
        offset_mm,
        width_mm,
        swing_direction: SwingDirection = SwingDirection.LEFT,
        id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            host_wall_id=host_wall_id,
            offset_mm=offset_mm,
            width_mm=width_mm,
            kind=OpeningKind.DOOR,
            id=id,
        )
        if not isinstance(swing_direction, SwingDirection):
            raise InvalidOpeningError(
                f"swing_direction must be a SwingDirection, got {swing_direction!r}"
            )
        object.__setattr__(self, "swing_direction", swing_direction)

    @property
    def centre_point(self) -> Point:
        return Point(self.offset_mm + self.width_mm / 2, Decimal(0))


@dataclass(frozen=True, slots=True)
class Window(Opening):
    """An opening that is a window.

    Carries no extra geometry in the MVP: width, offset and host wall are all a
    window needs. Sill height and opening area are later concerns, and adding
    empty fields now would be modelling a guess.
    """

    def __init__(
        self,
        host_wall_id: uuid.UUID,
        offset_mm,
        width_mm,
        id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            host_wall_id=host_wall_id,
            offset_mm=offset_mm,
            width_mm=width_mm,
            kind=OpeningKind.WINDOW,
            id=id,
        )
