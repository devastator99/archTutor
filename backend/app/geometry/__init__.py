"""The architectural 2D geometry model.

Minimal, deterministic, and deliberately not a CAD system.

    Point, Line, Wall, Opening, Door, Window, Room, Dimension

Two rules govern this package:

1. **The canvas does not define geometry.** This model does. The canvas will
   later render whatever these objects say, and must never be the source of a
   measurement.
2. **The domain is independent of third-party libraries.** No Shapely object
   appears in any signature, return value or stored payload.
   :mod:`app.geometry.shapely_adapter` is the single sanctioned boundary.

Scope is horizontal walls, vertical walls, rectangular rooms, wall thickness,
door placement, window placement and dimensions. A general CAD kernel,
arbitrary polygons, arcs, layers and constraints are all out of scope.
"""

from app.geometry.errors import (
    GeometryDependencyError,
    GeometryError,
    InvalidOpeningError,
    InvalidPointError,
    InvalidRoomError,
    InvalidWallError,
    MisalignedOpeningError,
    UnknownWallError,
)
from app.geometry.operations import (
    dimension_for,
    distance,
    is_aligned_with_room,
    opening_centre_offset,
    opening_segment,
    opening_span,
    resolve_opening_wall,
    room_area,
    room_height,
    room_perimeter,
    room_width,
    wall_axis,
    wall_length,
    walls_total_length,
)
from app.geometry.primitives import Line, Point, is_horizontal, is_vertical
from app.geometry.room import Dimension, Room
from app.geometry.wall import (
    Axis,
    Door,
    Opening,
    OpeningKind,
    SwingDirection,
    Wall,
    Window,
)

__all__ = [
    # domain objects
    "Point",
    "Line",
    "Wall",
    "Opening",
    "Door",
    "Window",
    "Room",
    "Dimension",
    "OpeningKind",
    "SwingDirection",
    "Axis",
    # operations
    "distance",
    "wall_length",
    "wall_axis",
    "walls_total_length",
    "room_width",
    "room_height",
    "room_area",
    "room_perimeter",
    "opening_span",
    "opening_centre_offset",
    "opening_segment",
    "resolve_opening_wall",
    "is_aligned_with_room",
    "dimension_for",
    "is_horizontal",
    "is_vertical",
    # errors
    "GeometryError",
    "InvalidPointError",
    "InvalidWallError",
    "InvalidRoomError",
    "InvalidOpeningError",
    "MisalignedOpeningError",
    "UnknownWallError",
    "GeometryDependencyError",
]
