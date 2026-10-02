"""Finding vocabulary.

Stable codes, fixed severities. A code is part of the API contract: the tutor
keys off it, tests assert on it, and it must not be renamed casually.

Values are the wire form and are upper case, because these strings are read by
JavaScript, asserted in tests and stored in attempt results. The member name and
the value are deliberately identical so a code read in a log is the code you
import.
"""

from __future__ import annotations

import enum


class Severity(str, enum.Enum):
    """How badly a finding fails the drawing."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class FindingCode(str, enum.Enum):
    """Every way a submission can be wrong.

    Grouped by what was misjudged rather than by which exercise produced it, so
    a new brief needs no new codes.
    """

    SCALE_ERROR = "SCALE_ERROR"
    ROOM_DIMENSION_ERROR = "ROOM_DIMENSION_ERROR"
    WALL_THICKNESS_ERROR = "WALL_THICKNESS_ERROR"
    DOOR_WIDTH_ERROR = "DOOR_WIDTH_ERROR"
    DOOR_PLACEMENT_ERROR = "DOOR_PLACEMENT_ERROR"
    WINDOW_WIDTH_ERROR = "WINDOW_WIDTH_ERROR"
    OPENING_PLACEMENT_ERROR = "OPENING_PLACEMENT_ERROR"
    DIMENSION_ERROR = "DIMENSION_ERROR"
    ALIGNMENT_ERROR = "ALIGNMENT_ERROR"
    MISSING_ELEMENT = "MISSING_ELEMENT"
    UNEXPECTED_ELEMENT = "UNEXPECTED_ELEMENT"
    """More of something than the brief asked for.

    Needed to close a silent pass: a second door, correctly sized and correctly
    placed, would otherwise be indistinguishable from a correct drawing, and the
    student would be told they were right.
    """
