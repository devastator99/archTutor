"""Measurement operations over the domain model.

The public surface of the geometry engine. Everything the validator will need
to measure a drawing is a function here, and every one of them is pure and
deterministic.

Functions that Shapely can answer more reliably than hand-rolled arithmetic
(area, perimeter) delegate to :mod:`app.geometry.shapely_adapter`. The rest are
exact on the axis-aligned geometry the MVP supports and do not need it.

No LLM, no web framework, no database.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.geometry.errors import UnknownWallError
from app.geometry.primitives import Line, Point, distance
from app.geometry.room import Dimension, Room
from app.geometry.wall import Axis, Door, Opening, Wall, Window


# --- Lines and walls ----------------------------------------------------


def wall_length(wall: Wall) -> Decimal:
    """Centreline length of a wall, in millimetres."""
    if not isinstance(wall, Wall):
        raise TypeError("wall_length expects a Wall")
    return wall.length_mm


def wall_axis(wall: Wall) -> Axis:
    """Whether a wall runs horizontally or vertically."""
    return wall.axis


def walls_total_length(walls: Iterable[Wall]) -> Decimal:
    """Combined centreline length of several walls."""
    return sum((wall_length(wall) for wall in walls), Decimal(0))


# --- Rooms --------------------------------------------------------------


def room_width(room: Room) -> Decimal:
    """Clear internal width: the east-west span of the boundary, in millimetres."""
    return room.max_x - room.min_x


def room_height(room: Room) -> Decimal:
    """Clear internal height: the north-south span of the boundary, in millimetres."""
    return room.max_y - room.min_y


def room_area(room: Room) -> Decimal:
    """Floor area in square millimetres. Delegates to the Shapely adapter."""
    from app.geometry import shapely_adapter

    return shapely_adapter.room_area_mm2(room)


def room_perimeter(room: Room) -> Decimal:
    """Boundary length in millimetres. Delegates to the Shapely adapter."""
    from app.geometry import shapely_adapter

    return shapely_adapter.room_perimeter_mm(room)


# --- Openings -----------------------------------------------------------


def opening_span(opening: Opening) -> tuple[Decimal, Decimal]:
    """The opening's (start offset, end offset) along its host wall."""
    return opening.offset_mm, opening.end_offset_mm


def opening_centre_offset(opening: Opening) -> Decimal:
    """Offset of the opening's midpoint along its host wall."""
    return opening.offset_mm + opening.width_mm / 2


def resolve_opening_wall(
    opening: Opening, walls: Iterable[Wall]
) -> Wall:
    """Find the wall that hosts ``opening``.

    Raises :class:`UnknownWallError` rather than returning ``None``: an opening
    pointing at a wall that is not there is a broken drawing, and the caller
    must not be tempted to treat it as a zero-length or unaligned opening.
    """
    for wall in walls:
        if wall.id == opening.host_wall_id:
            return wall
    raise UnknownWallError(
        f"opening {opening.id} references wall {opening.host_wall_id}, "
        "which is not in the drawing"
    )


def opening_segment(opening: Opening, walls: Iterable[Wall]) -> tuple[Point, Point]:
    """The opening's two centreline endpoints, in wall coordinates.

    Resolves the host wall and validates alignment, so a misaligned or orphaned
    opening raises here rather than producing a plausible-looking segment.
    """
    wall = resolve_opening_wall(opening, walls)
    return opening.segment_in(wall)


def is_aligned_with_room(opening: Opening, walls: Iterable[Wall]) -> bool:
    """Is the opening correctly hosted and fully within its wall's extent?"""
    try:
        wall = resolve_opening_wall(opening, walls)
        opening.validate_placement(wall)
    except Exception:
        return False
    return True


# --- Dimensions ---------------------------------------------------------


def dimension_for(start: Point, end: Point, actual_value_mm) -> Dimension:
    """Build a :class:`Dimension` spanning two points."""
    return Dimension(start, end, actual_value_mm)


__all__ = [
    "Axis",
    "Dimension",
    "Door",
    "Line",
    "Opening",
    "Point",
    "Room",
    "Wall",
    "Window",
    "distance",
    "dimension_for",
    "is_aligned_with_room",
    "opening_centre_offset",
    "opening_segment",
    "opening_span",
    "resolve_opening_wall",
    "room_area",
    "room_height",
    "room_perimeter",
    "room_width",
    "wall_axis",
    "wall_length",
    "walls_total_length",
]
