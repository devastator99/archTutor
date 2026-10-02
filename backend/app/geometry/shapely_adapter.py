"""Shapely adapter.

OSS CHECK
---------
Shapely 2.1.2, **BSD 3-Clause**. Permissive, commercially safe, and the
current release. The same 2.1 series supports the operations used here.

WHY THIS FILE EXISTS
--------------------
This is the *only* module in the codebase permitted to import Shapely, and no
Shapely object may appear in a signature, a return value, a stored payload or a
field of a domain object.

The constitution requires the domain model to stay independent of third-party
libraries so that the geometry engine can be replaced or upgraded without
touching the validator, the API or the database. That is only true if the
leak is contained here: the cost of the adapter is one file, and the benefit is
that swapping the library is a one-file change.

PRECISION
---------
Shapely computes in IEEE-754 doubles. Millimetre coordinates below 2^53 are
exactly representable, so integer-millimetre geometry -- which is the whole of
the MVP -- passes through exactly. Decimal coordinates are converted via
``float(str(value))`` to avoid widening a binary artifact, and results are
quantised to :data:`RESULT_QUANTUM` to strip the double's trailing noise before
a Decimal ever sees it.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from app.geometry.errors import GeometryDependencyError

if TYPE_CHECKING:  # pragma: no cover
    from app.geometry.room import Room

RESULT_QUANTUM = Decimal("0.001")
"""Results are quantised to 0.001 mm / mm² to discard double noise."""

try:
    from shapely import Polygon as _ShapelyPolygon
except ImportError as exc:  # pragma: no cover - exercised only without Shapely
    raise GeometryDependencyError(
        "Shapely is required for room area and perimeter. "
        "Install it with: pip install shapely"
    ) from exc


def _to_float(value: Decimal) -> float:
    """Decimal millimetres to a double, without widening float artefacts."""
    return float(str(value))


def _quantize(value: float) -> Decimal:
    return Decimal(str(value)).quantize(RESULT_QUANTUM, rounding=ROUND_HALF_UP)


def _boundary_polygon(room: "Room") -> Any:
    """Build a Shapely polygon from a room. Private: never leaves this module."""
    corners = room.corners_in_order
    return _ShapelyPolygon([(_to_float(p.x), _to_float(p.y)) for p in corners])


def room_area_mm2(room: "Room") -> Decimal:
    """Enclosed floor area in square millimetres."""
    return _quantize(_boundary_polygon(room).area)


def room_perimeter_mm(room: "Room") -> Decimal:
    """Total boundary length in millimetres.

    For a rectangle this is the sum of the four sides, i.e. an internal
    dimension. It is *not* the external face dimension and is not adjusted for
    wall thickness; the clear internal span is the meaningful figure.
    """
    return _quantize(_boundary_polygon(room).length)


def shapely_version() -> str:
    """The Shapely version in use, for diagnostics and startup logging."""
    try:
        from shapely import __version__ as version
    except ImportError:  # pragma: no cover
        return "unavailable"
    return version
