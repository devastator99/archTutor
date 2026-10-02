"""Geometry errors."""

from __future__ import annotations


class GeometryError(ValueError):
    """Base class for every geometry failure."""


class InvalidPointError(GeometryError):
    """A point was non-finite or otherwise unusable."""


class InvalidWallError(GeometryError):
    """A wall was degenerate, zero-thickness, or not axis-aligned."""


class InvalidRoomError(GeometryError):
    """A room boundary was not a closed axis-aligned rectangle."""


class InvalidOpeningError(GeometryError):
    """An opening had non-positive width, a negative offset, or was not hosted."""


class MisalignedOpeningError(InvalidOpeningError):
    """An opening does not fit within the wall that hosts it."""


class UnknownWallError(GeometryError):
    """An opening referenced a wall that is not present."""


class GeometryDependencyError(GeometryError):
    """The optional geometry backend could not satisfy the operation."""
