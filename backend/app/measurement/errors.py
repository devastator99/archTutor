"""Errors raised by the measurement engine.

All are subclasses of :class:`ValueError`, so generic ``except ValueError``
callers keep working, while callers that care can distinguish *why* a
measurement was rejected.

The engine rejects bad input rather than coercing it. A silently corrected
dimension is a silently wrong drawing.
"""

from __future__ import annotations


class MeasurementError(ValueError):
    """Base class for every measurement failure."""


class InvalidUnitError(MeasurementError):
    """A unit was not one of the supported architectural units."""


class InvalidScaleError(MeasurementError):
    """A scale denominator was non-positive or otherwise unusable."""


class InvalidDimensionError(MeasurementError):
    """A dimension was negative, non-finite, or zero where zero is meaningless."""


class InvalidToleranceError(MeasurementError):
    """A tolerance was negative or non-finite."""
