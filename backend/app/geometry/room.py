"""Rooms and dimensions.

A room's boundary is an ordered tuple of corner points. The MVP supports
rectangular rooms only, and that is *checked*, not assumed: a five-sided or
skewed boundary is rejected at construction rather than producing a plausible
looking area that is quietly wrong.

Boundary points may be given in any rotational order and any winding
direction; the room works out its own extent. What it will not do is accept a
boundary that is not a closed axis-aligned rectangle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.geometry.errors import InvalidRoomError
from app.geometry.primitives import Point, distance


@dataclass(frozen=True, slots=True)
class Room:
    """A rectangular room defined by its boundary corners."""

    id: uuid.UUID
    boundary: tuple[Point, ...]
    name: str | None = None

    def __init__(
        self,
        boundary,
        name: str | None = None,
        id: uuid.UUID | None = None,
    ) -> None:
        if isinstance(boundary, (list, tuple)):
            corners = tuple(boundary)
        else:
            raise InvalidRoomError("boundary must be a sequence of Points")
        if len(corners) != 4:
            raise InvalidRoomError(
                f"the MVP supports rectangular rooms: expected 4 boundary points, "
                f"got {len(corners)}"
            )
        for corner in corners:
            if not isinstance(corner, Point):
                raise InvalidRoomError("every boundary point must be a Point")
        if len(set(corners)) != 4:
            raise InvalidRoomError("boundary points must be distinct")

        xs = {corner.x for corner in corners}
        ys = {corner.y for corner in corners}
        if len(xs) != 2 or len(ys) != 2:
            raise InvalidRoomError(
                f"boundary must be an axis-aligned rectangle, got x={sorted(xs)} "
                f"y={sorted(ys)}"
            )

        object.__setattr__(self, "id", id or uuid.uuid4())
        object.__setattr__(self, "boundary", corners)
        object.__setattr__(self, "name", name)

    # --- Extent ---------------------------------------------------------
    @property
    def min_x(self) -> Decimal:
        return min(corner.x for corner in self.boundary)

    @property
    def max_x(self) -> Decimal:
        return max(corner.x for corner in self.boundary)

    @property
    def min_y(self) -> Decimal:
        return min(corner.y for corner in self.boundary)

    @property
    def max_y(self) -> Decimal:
        return max(corner.y for corner in self.boundary)

    @property
    def centre(self) -> Point:
        return Point(
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
        )

    @property
    def corners_in_order(self) -> tuple[Point, Point, Point, Point]:
        """Boundary points ordered anticlockwise from the minimum corner.

        Winding order is a rendering and area-sign convention. Normalising it
        here means a room built from corners listed clockwise behaves
        identically to one listed anticlockwise.
        """
        min_x, min_y = self.min_x, self.min_y
        return (
            Point(min_x, min_y),
            Point(self.max_x, min_y),
            Point(self.max_x, self.max_y),
            Point(min_x, self.max_y),
        )

    def corner_at(self, corner: Point) -> Decimal:
        return distance(self.centre, corner)


@dataclass(frozen=True, slots=True)
class Dimension:
    """A measured span between two points, with the value it represents.

    ``actual_value_mm`` is what the dimension is *meant* to say, kept alongside
    the geometry rather than derived from it, because a dimension line and a
    measured length are different things: the error this product exists to catch
    is precisely the distance between them.
    """

    start: Point
    end: Point
    actual_value_mm: Decimal

    def __init__(self, start: Point, end: Point, actual_value_mm) -> None:
        for name, value in (("start", start), ("end", end)):
            if not isinstance(value, Point):
                raise InvalidRoomError(f"dimension {name} must be a Point")
        if start == end:
            raise InvalidRoomError("a dimension must span two distinct points")
        value = Decimal(str(actual_value_mm))
        if not value.is_finite() or value < 0:
            raise InvalidRoomError(
                f"dimension value must be a non-negative finite length, got {value}"
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "actual_value_mm", value)

    @property
    def measured_mm(self) -> Decimal:
        """The length the geometry actually spans."""
        return distance(self.start, self.end)

    @property
    def deviation_mm(self) -> Decimal:
        """``measured - actual``. Positive means drawn too long."""
        return self.measured_mm - self.actual_value_mm
