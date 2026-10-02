"""The student drawing: a complete, serialisable plan submission.

A drawing is what the student actually drew, and it is the authority on that.
The validator reads it and compares against an exercise; it never rewrites it.

SPACES
------
Everything in a drawing is in **drawing space** -- millimetres as measured on
the sheet, at the scale the student declared. Wall thicknesses, room spans and
opening widths are paper measurements, not building measurements. The exercise
holds building millimetres; converting between the two is
:mod:`app.measurement`'s job and nobody else's.

Keeping drawings in paper space is what makes scale a *checkable* property. If
submissions arrived in building millimetres, a student who drew at 1:100 while
claiming 1:50 would be indistinguishable from a correct answer, because both
describe the same building. In paper space the discrepancy is 42 mm versus
84 mm and cannot be hidden.

SERIALISATION
-------------
:func:`StudentDrawing.from_dict` is strict. Unknown keys are rejected and every
number is coerced through :func:`~app.measurement.units.to_decimal`, so a
malformed submission fails loudly at the boundary instead of producing a
drawing that validates against nonsense.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Literal

from app.geometry.errors import GeometryError
from app.geometry.primitives import Point
from app.geometry.room import Dimension, Room
from app.geometry.wall import (
    Door,
    Opening,
    OpeningKind,
    SwingDirection,
    Wall,
    Window,
)
from app.measurement.errors import MeasurementError
from app.measurement.scale import validate_scale
from app.measurement.units import to_decimal

RoomSide = Literal["north", "south", "east", "west"]

MIN_DRAWING_SCALE_DENOMINATOR = 2
"""A submitted drawing must be reduced.

``app.measurement`` accepts 1:1 because 1:1 is a real scale and reverse
conversion must round-trip it. A *submission* is different: at 1:1 the paper
millimetres equal the building millimetres, so declaring 1 would satisfy any
brief regardless of the geometry actually drawn, and the scale check -- the one
that catches a student working at the wrong size -- would be trivially defeated.
This mirrors ``PositiveScale`` in the exercise schema.
"""

_ID_NAMESPACE = uuid.UUID("1b4e28ba-2fa1-11d2-883f-0016d3cca427")
"""Fixed namespace for deriving identifiers from submission content.

Must never change. If it did, every derived id in every stored attempt would
change with it, and previously reproducible results would stop reproducing.
"""


def stable_id(*parts: str) -> uuid.UUID:
    """A UUID derived from content, so the same input always yields the same id.

    Reproducibility is why this exists. The domain types default to ``uuid4`` for
    the convenience of hand-built objects, but a submitted drawing is part of a
    verdict: if two runs over identical bytes produced different
    ``geometry_reference`` values, a finding could not be reproduced and a bug
    could not be distinguished from a mistake.
    """
    return uuid.uuid5(_ID_NAMESPACE, "|".join(parts))


class DrawingFormatError(ValueError):
    """A submitted drawing could not be read into the domain model."""


def _require(payload: dict, key: str, context: str) -> Any:
    if key not in payload:
        raise DrawingFormatError(f"{context}: missing required field {key!r}")
    return payload[key]


def _point(payload: dict, context: str) -> Point:
    return Point(
        to_decimal(_require(payload, "x", context)),
        to_decimal(_require(payload, "y", context)),
    )


@dataclass(frozen=True, slots=True)
class StudentDrawing:
    """A complete plan submission in drawing-space millimetres."""

    scale_denominator: int
    room: Room
    walls: tuple[Wall, ...] = field(default_factory=tuple)
    openings: tuple[Opening, ...] = field(default_factory=tuple)
    dimensions: tuple[Dimension, ...] = field(default_factory=tuple)

    def __init__(
        self,
        scale_denominator: int,
        room: Room,
        walls: Iterable[Wall] = (),
        openings: Iterable[Opening] = (),
        dimensions: Iterable[Dimension] = (),
    ) -> None:
        validate_scale(scale_denominator)
        if scale_denominator < MIN_DRAWING_SCALE_DENOMINATOR:
            raise DrawingFormatError(
                f"scale denominator must be >= {MIN_DRAWING_SCALE_DENOMINATOR}, "
                f"got {scale_denominator}"
            )
        if not isinstance(room, Room):
            raise DrawingFormatError("room must be a Room")
        object.__setattr__(self, "scale_denominator", scale_denominator)
        object.__setattr__(self, "room", room)
        object.__setattr__(self, "walls", tuple(walls))
        object.__setattr__(self, "openings", tuple(openings))
        object.__setattr__(self, "dimensions", tuple(dimensions))

    # --- Derived views --------------------------------------------------

    @property
    def room_width(self) -> Decimal:
        """East-west span of the room boundary, in drawing millimetres."""
        return self.room.max_x - self.room.min_x

    @property
    def room_height(self) -> Decimal:
        """North-south span of the room boundary, in drawing millimetres."""
        return self.room.max_y - self.room.min_y

    def wall_on_side_name(self, wall: Wall) -> str | None:
        """The side name of a wall, or ``None`` if it is not on the boundary."""
        for side in ("north", "south", "east", "west"):
            if self.wall_on_side(side) is wall:
                return side
        return None

    def wall_on_side(self, side: RoomSide) -> Wall | None:
        """The wall whose centreline lies on the room boundary for ``side``.

        ``north`` is the maximum y, ``south`` the minimum y, ``east`` the
        maximum x, ``west`` the minimum x.

        Note which axis each side implies. The north and south boundaries run
        east-west, so their walls are *horizontal*; the east and west boundaries
        run north-south, so their walls are *vertical*. Getting this pairing
        backwards is easy and silent -- it just makes every side lookup miss --
        so each predicate is spelled out rather than derived.
        """
        room = self.room
        if side == "north":
            return self._wall_on(
                lambda w: w.axis.value == "horizontal" and w.start.y == room.max_y
            )
        if side == "south":
            return self._wall_on(
                lambda w: w.axis.value == "horizontal" and w.start.y == room.min_y
            )
        if side == "east":
            return self._wall_on(
                lambda w: w.axis.value == "vertical" and w.start.x == room.max_x
            )
        if side == "west":
            return self._wall_on(
                lambda w: w.axis.value == "vertical" and w.start.x == room.min_x
            )
        raise DrawingFormatError(f"unknown room side {side!r}")

    def _wall_on(self, predicate) -> Wall | None:
        for wall in self.walls:
            if predicate(wall):
                return wall
        return None

    def openings_on(self, wall: Wall) -> tuple[Opening, ...]:
        return tuple(o for o in self.openings if o.host_wall_id == wall.id)

    def openings_of_kind(self, kind: OpeningKind) -> tuple[Opening, ...]:
        return tuple(o for o in self.openings if o.kind is kind)

    # --- Serialisation --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to plain JSON-compatible data, millimetres as strings.

        Dimensions are emitted as strings because a JSON number is a double,
        and a wall thickness of 4.6 mm must not become 4.5999999999999996 on
        the way back in.
        """
        return {
            "scale_denominator": self.scale_denominator,
            "room": {
                "boundary": [
                    {"x": str(point.x), "y": str(point.y)}
                    for point in self.room.corners_in_order
                ],
            },
            "walls": [
                {
                    "id": str(wall.id),
                    "start": {"x": str(wall.start.x), "y": str(wall.start.y)},
                    "end": {"x": str(wall.end.x), "y": str(wall.end.y)},
                    "thickness_mm": str(wall.thickness_mm),
                }
                for wall in self.walls
            ],
            "openings": [
                {
                    "id": str(opening.id),
                    "host_wall_id": str(opening.host_wall_id),
                    "offset_mm": str(opening.offset_mm),
                    "width_mm": str(opening.width_mm),
                    "kind": opening.kind.value,
                    **(
                        {"swing_direction": opening.swing_direction.value}
                        if isinstance(opening, Door)
                        else {}
                    ),
                }
                for opening in self.openings
            ],
            "dimensions": [
                {
                    "start": {"x": str(d.start.x), "y": str(d.start.y)},
                    "end": {"x": str(d.end.x), "y": str(d.end.y)},
                    "actual_value_mm": str(d.actual_value_mm),
                }
                for d in self.dimensions
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StudentDrawing":
        """Read a submitted drawing, rejecting anything malformed.

        Every failure is a :class:`DrawingFormatError` carrying the path that
        caused it, so a student is told *which* number was unreadable rather
        than being handed a generic "invalid geometry".
        """
        if not isinstance(payload, dict):
            raise DrawingFormatError("drawing must be an object")

        allowed = {"scale_denominator", "room", "walls", "openings", "dimensions"}
        unknown = set(payload) - allowed
        if unknown:
            raise DrawingFormatError(
                f"drawing has unknown field(s): {', '.join(sorted(unknown))}"
            )

        try:
            scale = _require(payload, "scale_denominator", "drawing")
            if isinstance(scale, bool) or not isinstance(scale, int):
                raise DrawingFormatError("scale_denominator must be an integer")
            validate_scale(scale)
            if scale < MIN_DRAWING_SCALE_DENOMINATOR:
                raise DrawingFormatError(
                    f"scale_denominator must be >= {MIN_DRAWING_SCALE_DENOMINATOR}, "
                    f"got {scale}"
                )

            room_payload = _require(payload, "room", "drawing")
            boundary = _require(room_payload, "boundary", "room")
            if not isinstance(boundary, list):
                raise DrawingFormatError("room.boundary must be a list")
            room = Room([_point(corner, "room.boundary") for corner in boundary])

            walls = tuple(
                _wall_from_dict(wall, f"walls[{index}]")
                for index, wall in enumerate(payload.get("walls", []))
            )
            openings = tuple(
                _opening_from_dict(opening, f"openings[{index}]", index)
                for index, opening in enumerate(payload.get("openings", []))
            )
            dimensions = tuple(
                _dimension_from_dict(dimension, f"dimensions[{index}]")
                for index, dimension in enumerate(payload.get("dimensions", []))
            )
        except (MeasurementError, GeometryError) as exc:
            raise DrawingFormatError(str(exc)) from exc

        return cls(
            scale_denominator=scale,
            room=room,
            walls=walls,
            openings=openings,
            dimensions=dimensions,
        )


def _wall_from_dict(payload: dict[str, Any], context: str) -> Wall:
    if not isinstance(payload, dict):
        raise DrawingFormatError(f"{context}: wall must be an object")
    unknown = set(payload) - {"id", "start", "end", "thickness_mm"}
    if unknown:
        raise DrawingFormatError(f"{context}: unknown field(s) {', '.join(sorted(unknown))}")
    # Walls require an explicit id: an opening's host_wall_id is a
    # reference, and a reference cannot point at an id the server invents
    # after the fact. Checked outside the try, because DrawingFormatError is a
    # ValueError and would otherwise be re-reported as a malformed id.
    if "id" not in payload:
        raise DrawingFormatError(f"{context}: missing required field 'id'")
    try:
        wall_id = uuid.UUID(str(payload["id"]))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DrawingFormatError(f"{context}.id must be a UUID") from exc
    try:
        return Wall(
            start=_point(_require(payload, "start", context), f"{context}.start"),
            end=_point(_require(payload, "end", context), f"{context}.end"),
            thickness_mm=to_decimal(
                _require(payload, "thickness_mm", context)
            ),
            id=wall_id,
        )
    except MeasurementError as exc:
        raise DrawingFormatError(f"{context}: {exc}") from exc


def _opening_from_dict(
    payload: dict[str, Any], context: str, index: int
) -> Opening:
    if not isinstance(payload, dict):
        raise DrawingFormatError(f"{context}: opening must be an object")
    allowed = {"id", "host_wall_id", "offset_mm", "width_mm", "kind", "swing_direction"}
    unknown = set(payload) - allowed
    if unknown:
        raise DrawingFormatError(f"{context}: unknown field(s) {', '.join(sorted(unknown))}")

    kind_raw = payload.get("kind", "door")
    try:
        kind = OpeningKind(kind_raw)
    except ValueError as exc:
        raise DrawingFormatError(f"{context}.kind must be 'door' or 'window'") from exc

    if "host_wall_id" not in payload:
        raise DrawingFormatError(
            f"{context}: missing required field 'host_wall_id'"
        )
    try:
        host_id = uuid.UUID(str(payload["host_wall_id"]))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DrawingFormatError(f"{context}.host_wall_id must be a UUID") from exc

    try:
        offset = to_decimal(_require(payload, "offset_mm", context))
        width = to_decimal(_require(payload, "width_mm", context))
    except MeasurementError as exc:
        raise DrawingFormatError(f"{context}: {exc}") from exc

    # An opening id may be supplied, but nothing references it, so when the
    # client omits one it is derived from content and position instead of
    # randomised -- findings reference it, so it has to be stable.
    identifier = payload.get("id")
    if identifier is not None:
        try:
            opening_id = uuid.UUID(str(identifier))
        except ValueError as exc:
            raise DrawingFormatError(f"{context}.id must be a UUID") from exc
    else:
        opening_id = stable_id(
            "opening", str(index), kind.value, str(host_id), str(offset), str(width)
        )

    common = dict(
        host_wall_id=host_id,
        offset_mm=offset,
        width_mm=width,
        id=opening_id,
    )
    if kind is OpeningKind.DOOR:
        swing_raw = payload.get("swing_direction", SwingDirection.LEFT.value)
        try:
            swing = SwingDirection(swing_raw)
        except ValueError as exc:
            raise DrawingFormatError(
                f"{context}.swing_direction must be one of "
                f"{', '.join(s.value for s in SwingDirection)}"
            ) from exc
        return Door(swing_direction=swing, **common)
    return Window(**common)


def _dimension_from_dict(payload: dict[str, Any], context: str) -> Dimension:
    if not isinstance(payload, dict):
        raise DrawingFormatError(f"{context}: dimension must be an object")
    unknown = set(payload) - {"start", "end", "actual_value_mm"}
    if unknown:
        raise DrawingFormatError(f"{context}: unknown field(s) {', '.join(sorted(unknown))}")
    try:
        return Dimension(
            start=_point(_require(payload, "start", context), f"{context}.start"),
            end=_point(_require(payload, "end", context), f"{context}.end"),
            actual_value_mm=to_decimal(
                _require(payload, "actual_value_mm", context)
            ),
        )
    except MeasurementError as exc:
        raise DrawingFormatError(f"{context}: {exc}") from exc
