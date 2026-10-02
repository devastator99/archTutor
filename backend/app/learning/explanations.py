"""Deterministic explanations: the feedback a student can always rely on.

THIS IS NOT THE AI
------------------
The product's promise is that a student can always be told what is wrong, where,
what was expected, what was drawn, why it matters and how to fix it. If that
depends on an LLM being reachable and well-behaved, the promise has a single
point of failure, and it is the part the student cannot work around.

So every one of those fields is produced here, from the finding, with no model
in the loop. The tutor in :mod:`app.tutor` may *add* an explanation on top. It
may not replace this one, and it may not contradict it.

A RULE THIS MODULE FOLLOWS
--------------------------
**No new numbers.** Every quantity stated here is either taken verbatim from the
finding or expressed without a figure at all. This module never performs a
calculation, because a calculation it performed would be a second source of
truth for measurement -- the exact duplication of
:mod:`app.measurement` that the whole architecture exists to prevent.

Where a fix needs a figure, the figure is the finding's own ``expected`` value,
which the engine already computed and the UI already shows. Restating it cannot
introduce a disagreement; recomputing it could.
"""

from __future__ import annotations

from typing import Any

from app.geometry.drawing import StudentDrawing
from app.learning.taxonomy import MistakeCategory, describe_category
from app.validation.codes import FindingCode
from app.validation.findings import Finding

# --- Why it matters ------------------------------------------------------
# One per category. The teaching point, not the arithmetic: the student already
# has the arithmetic, stated exactly, in expected/actual/difference.

_WHY: dict[MistakeCategory, str] = {
    MistakeCategory.SCALE_CONVERSION: (
        "Scale is not a label on a drawing, it is the contract between the "
        "sheet and the building. Everything measured on a sheet at the wrong "
        "scale is wrong by the same factor, so the whole drawing misreports its "
        "own size. A plan that is internally consistent but drawn at 1:100 is "
        "still a 1:100 plan, and on site it would be twice the size of the room "
        "it describes."
    ),
    MistakeCategory.UNIT_CONFUSION: (
        "Real-world millimetres and sheet millimetres are two different "
        "quantities that happen to share a unit. This is the most common early "
        "mistake, and it is worth recognising by name: you have drawn the room "
        "at full size on the sheet. The number you measured is a real length "
        "that has not been converted, so it is not yet a drawing at all."
    ),
    MistakeCategory.ROOM_DIMENSION: (
        "The room's clear internal size is what the space actually is. It "
        "governs floor area, furniture layout and whether the room works, and "
        "it is the first thing a checker measures. A plan can be beautifully "
        "drafted around a room of the wrong size and still be wrong."
    ),
    MistakeCategory.WALL_THICKNESS: (
        "Wall thickness is structure. It sets the clear internal dimension, the "
        "face dimensions outside it, and where an opening can physically sit. "
        "Drawing walls at a different thickness changes the building, not just "
        "the drawing of it."
    ),
    MistakeCategory.OPENING_WIDTH: (
        "An opening's width is a manufactured size, not a free choice. A door "
        "leaf, a frame and a structural opening are all made to standard widths, "
        "and a door drawn at the wrong width will not be built. This is also the "
        "figure a client reads first when they walk into the room."
    ),
    MistakeCategory.OPENING_PLACEMENT: (
        "Where an opening sits determines whether the room works. A door that "
        "does not meet the wall, or that lands where a piece of furniture has "
        "to go, is a design fault rather than a drafting one -- so this is "
        "corrected by moving the opening, not by adjusting a number."
    ),
    MistakeCategory.DIMENSION_PLACEMENT: (
        "A dimension has two independent parts: the line that spans the thing, "
        "and the number written beside it. Both must agree with the building. "
        "The span is read off the drawing, so it carries the scale error of the "
        "line itself; the number is stated by the student and is never scaled. "
        "Dimensioning is how a drawing is checked without a ruler, so if the "
        "two disagree, neither can be trusted."
    ),
    MistakeCategory.ALIGNMENT: (
        "Walls must meet to close the room. If they do not share corners or do "
        "not sit on the room boundary, the space being described does not exist "
        "as drawn, and every other measurement in the plan is measuring an "
        "ambiguous shape. Alignment is checked first for that reason."
    ),
    MistakeCategory.MISSING_ELEMENT: (
        "A brief lists what must be present. Something absent is not a smaller "
        "problem than something wrong: an unshown door leaves the circulation of "
        "the room undesigned, and an unshown dimension leaves the room "
        "undimensioned for the next person who reads it."
    ),
    MistakeCategory.UNEXPECTED_ELEMENT: (
        "A brief is a specification, not a suggestion. Adding something the "
        "brief did not ask for changes the design, and it will be marked as "
        "departing from the brief however well drawn it is."
    ),
}

# --- How to fix ----------------------------------------------------------
# Concrete, ordered steps. Written per code where the fix differs by mistake,
# falling back to the category.

_HOW: dict[FindingCode, tuple[str, ...]] = {
    FindingCode.ROOM_DIMENSION_ERROR: (
        "Check the scale you are working at against the brief.",
        "Convert the required real-world dimension to the sheet by dividing by "
        "the scale.",
        "Redraw the room boundary at that size, or correct the boundary you have.",
    ),
    FindingCode.WALL_THICKNESS_ERROR: (
        "Convert the required wall thickness to the sheet by dividing by the scale.",
        "Set every wall to that thickness, including corners, so the envelope "
        "stays consistent.",
    ),
    FindingCode.DOOR_WIDTH_ERROR: (
        "Convert the required door width to the sheet by dividing by the scale.",
        "Resize the door to that width. If it is close but not exact, check "
        "which end of the wall you are measuring from.",
    ),
    FindingCode.WINDOW_WIDTH_ERROR: (
        "Convert the required window width to the sheet by dividing by the scale.",
        "Resize the window to that width, keeping its host wall the same length.",
    ),
    FindingCode.DOOR_PLACEMENT_ERROR: (
        "Confirm the door is hosted on the wall the brief names.",
        "Move it along that wall until it sits fully inside the wall's length.",
        "Check its offset from the wall's start, measured along the wall.",
    ),
    FindingCode.OPENING_PLACEMENT_ERROR: (
        "Confirm the window is hosted on the wall the brief names.",
        "Move it along that wall until it sits fully inside the wall's length.",
        "Check its offset from the wall's start, measured along the wall.",
    ),
    FindingCode.DIMENSION_ERROR: (
        "Separate the two halves of the problem: the line's span, and the "
        "number written beside it.",
        "The span must equal the required dimension converted to the sheet.",
        "The written number is a real-world millimetre value and is never "
        "divided by the scale.",
    ),
    FindingCode.MISSING_ELEMENT: (
        "Add the element the brief lists and the finding names.",
        "Place it on the wall or axis the brief specifies, at the size the brief "
        "gives.",
    ),
    FindingCode.UNEXPECTED_ELEMENT: (
        "Remove the element the brief does not ask for.",
        "If the brief genuinely needs a different number of these, that is a "
        "brief to be corrected, not a drawing.",
    ),
    FindingCode.ALIGNMENT_ERROR: (
        "Start from the room boundary and place each wall on one of its four sides.",
        "Make the walls share corners exactly, so each corner is met by two walls.",
        "A rectangular room has exactly four walls; check none is duplicated "
        "or omitted.",
    ),
}

_HOW_BY_CATEGORY: dict[MistakeCategory, tuple[str, ...]] = {
    MistakeCategory.SCALE_CONVERSION: (
        "Decide the scale the brief asks for, and write it in the title block.",
        "Convert every real-world dimension to the sheet by dividing by that scale.",
        "Re-measure one known length on your sheet to confirm the scale you "
        "actually drew at matches the scale you declared.",
    ),
    MistakeCategory.UNIT_CONFUSION: (
        "Pick up the real-world dimension from the brief, for example the room width.",
        "Divide it by the scale denominator to get the length on the sheet.",
        "Draw that sheet length, not the real-world one. If your sheet length "
        "is larger than the room itself, the conversion has been skipped.",
    ),
    MistakeCategory.WALL_THICKNESS: (
        "Convert the required thickness to the sheet by dividing by the scale.",
        "Apply it to every wall, including the ones at the corners.",
    ),
    MistakeCategory.OPENING_WIDTH: (
        "Convert the required opening width to the sheet by dividing by the scale.",
        "Set the opening to that width and leave its host wall unchanged.",
    ),
    MistakeCategory.OPENING_PLACEMENT: (
        "Find which wall the brief names for this opening.",
        "Host the opening on that wall, with its offset plus width inside the "
        "wall's length.",
    ),
    MistakeCategory.DIMENSION_PLACEMENT: (
        "Draw the dimension line across the thing being dimensioned, at the "
        "correct scale.",
        "Write the real-world millimetre value beside it, unscaled.",
    ),
    MistakeCategory.ALIGNMENT: (
        "Place four walls, one on each side of the room boundary.",
        "Make each corner shared by exactly two walls, at identical coordinates.",
    ),
    MistakeCategory.MISSING_ELEMENT: (
        "Work down the brief's list and check off each required element.",
        "Add anything missing at the size and position the brief states.",
    ),
    MistakeCategory.UNEXPECTED_ELEMENT: (
        "Compare the drawing against the brief's list, element by element.",
        "Remove anything not on the list.",
    ),
}

# --- Where ---------------------------------------------------------------

_SIDE_NAMES = {
    "north": "the north wall (top)",
    "south": "the south wall (bottom)",
    "east": "the east wall (right)",
    "west": "the west wall (left)",
}


def describe_location(
    code: FindingCode,
    metadata: dict[str, Any],
    geometry_reference: str | None = None,
    drawing: StudentDrawing | None = None,
) -> str:
    """Where on the sheet this finding is about, in words a student can use.

    Prefers structured metadata over the raw ``geometry_reference`` string, so
    the student is told "the north wall" rather than "wall:9f1c...". Wall ids are
    an internal handle for openings to reference, not something a student drew
    or needs to read.
    """
    reference = geometry_reference or ""

    if code is FindingCode.ROOM_DIMENSION_ERROR:
        return "the room outline"
    if code is FindingCode.SCALE_ERROR:
        return "the whole sheet"
    if code is FindingCode.WALL_THICKNESS_ERROR:
        side = metadata.get("side")
        if side is None and drawing is not None:
            side = _side_of_wall_id(drawing, metadata.get("wall_id"))
        if side in _SIDE_NAMES:
            return _SIDE_NAMES[side]
        return "a wall"
    if code in (FindingCode.DOOR_WIDTH_ERROR, FindingCode.WINDOW_WIDTH_ERROR):
        return _opening_location(metadata, drawing, code is FindingCode.DOOR_WIDTH_ERROR)
    if code in (FindingCode.DOOR_PLACEMENT_ERROR, FindingCode.OPENING_PLACEMENT_ERROR):
        return _opening_location(
            metadata, drawing, code is FindingCode.DOOR_PLACEMENT_ERROR
        )
    if code is FindingCode.DIMENSION_ERROR:
        axis = metadata.get("axis")
        return f"the {axis} dimension line" if axis else "a dimension line"
    if code in (FindingCode.MISSING_ELEMENT, FindingCode.UNEXPECTED_ELEMENT):
        kind = metadata.get("kind")
        if kind:
            noun = "door" if kind == "door" else "window"
            verb = "missing" if code is FindingCode.MISSING_ELEMENT else "not required"
            return f"the {noun} ({verb} from the brief)" if verb == "missing" else f"an extra {noun}"
        axis = metadata.get("axis")
        if axis:
            return f"the {axis} dimension (missing from the brief)"
        return "the drawing as a whole"
    if code is FindingCode.ALIGNMENT_ERROR:
        if reference.startswith("wall:"):
            side = reference.split(":", 1)[1]
            if side in _SIDE_NAMES:
                return _SIDE_NAMES[side]
        if reference.startswith("corner:"):
            return "a room corner"
        if "wall_count" in metadata:
            return "the set of walls"
        return "the room outline"
    return geometry_reference or "the drawing"


def _side_of_wall_id(drawing: StudentDrawing, wall_id: Any) -> str | None:
    if wall_id is None:
        return None
    for side in ("north", "south", "east", "west"):
        wall = drawing.wall_on_side(side)
        if wall is not None and str(wall.id) == str(wall_id):
            return side
    return None


def _opening_location(
    metadata: dict[str, Any], drawing: StudentDrawing | None, is_door: bool
) -> str:
    noun = "door" if is_door else "window"
    side = metadata.get("actual_side")
    if side in _SIDE_NAMES:
        return f"the {noun} on {_SIDE_NAMES[side]}"
    if side is None and drawing is not None:
        side = _side_of_opening(drawing, metadata.get("opening_id"))
        if side in _SIDE_NAMES:
            return f"the {noun} on {_SIDE_NAMES[side]}"
    host = metadata.get("host_wall_id")
    if host is not None:
        resolved = _side_of_wall_id(drawing, host) if drawing is not None else None
        if resolved in _SIDE_NAMES:
            return f"the {noun} on {_SIDE_NAMES[resolved]}"
        return f"a {noun} on a wall that is not in the drawing"
    return f"a {noun}"


def _side_of_opening(drawing: StudentDrawing, opening_id: Any) -> str | None:
    if opening_id is None:
        return None
    for opening in drawing.openings:
        if str(opening.id) != str(opening_id):
            continue
        for side in ("north", "south", "east", "west"):
            wall = drawing.wall_on_side(side)
            if wall is not None and wall.id == opening.host_wall_id:
                return side
    return None


def why_it_matters(code: FindingCode, metadata: dict[str, Any] | None = None) -> str:
    """The teaching point for a finding, with no figures invented."""
    from app.learning.taxonomy import category_for

    return _WHY.get(
        category_for(code, metadata or {}), "This is a deviation from the brief."
    )


def how_to_fix(
    code: FindingCode, metadata: dict[str, Any] | None = None
) -> list[str]:
    """Ordered, concrete steps for correcting a finding.

    Never states a dimension. The figure the student needs is already in the
    finding's ``expected`` field, shown alongside this list, and copying it here
    would only create a second place for it to be wrong.
    """
    from app.learning.taxonomy import category_for

    steps = _HOW.get(code) or _HOW_BY_CATEGORY.get(category_for(code, metadata or {}))
    if not steps:
        return ["Compare the drawing against the brief and correct the difference."]
    return list(steps)
