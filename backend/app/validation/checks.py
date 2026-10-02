"""The validation checks.

Each function takes an exercise, a drawing and a tolerance policy, and returns
a list of :class:`~app.validation.findings.Finding`. Pure, deterministic, no
I/O, no randomness, no LLM. Same input, same output, always.

UNITS
-----
An exercise states **building** millimetres. A drawing states **paper**
millimetres at the student's declared scale. Every comparison therefore passes
through :func:`app.measurement.actual_to_drawing` to bring the exercise into
the drawing's space.

A finding's ``expected``/``actual``/``difference`` are **paper** millimetres,
because that is the number on the sheet the student can act on. The equivalent
building-space figures go in ``metadata``, since "you drew 42 mm instead of
84 mm" is only meaningful beside "which is 2100 mm instead of 4200 mm".

Checks are independent and all of them run. A drawing at the wrong scale gets a
SCALE_ERROR *and* the room errors that follow from it: the student needs every
cause, not the first one found.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from app.geometry.drawing import StudentDrawing
from app.geometry.primitives import is_horizontal, is_vertical
from app.geometry.wall import Opening, OpeningKind, Wall
from app.measurement.scale import (
    actual_to_drawing,
    calculate_scale,
    drawing_to_actual,
)
from app.schemas.exercise import DimensionRequirement, ExerciseRead
from app.validation.codes import FindingCode, Severity
from app.validation.findings import Finding
from app.validation.tolerance import TolerancePolicy

FindingList = list[Finding]


def _error(
    code: FindingCode,
    message: str,
    *,
    expected: Decimal | int | str | None = None,
    actual: Decimal | int | str | None = None,
    difference: Decimal | int | str | None = None,
    unit: str = "mm",
    geometry_reference: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        code=code,
        severity=Severity.ERROR,
        message=message,
        expected=expected,
        actual=actual,
        difference=difference,
        unit=unit,
        geometry_reference=geometry_reference,
        metadata=metadata or {},
    )


def expected_paper_mm(
    exercise: ExerciseRead, drawing: StudentDrawing, actual_mm: int
) -> Decimal:
    """The exercise's real length expressed on the student's sheet."""
    return actual_to_drawing(actual_mm, drawing.scale_denominator)


def _outside(value: Decimal, expected: Decimal, tolerance: Decimal) -> bool:
    return abs(value - expected) > tolerance


# --- 1. Scale ------------------------------------------------------------


def validate_scale(
    exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Is the declared scale the scale the drawing was actually made at?

    A declared scale is only a label until the geometry is measured against it.
    If the sheet shows 42 mm where 1:50 demands 84 mm, the drawing was made at
    1:100, and declaring 1:50 does not make it otherwise. This is the most
    common drafting error, and it is invisible unless the label is checked
    against the geometry rather than trusted.

    Two independent defects are distinguished, because they are two different
    things to fix:

    1. the drawing is not at the scale the brief asked for;
    2. the label does not describe the geometry, so the title block and the
       sheet disagree with each other.

    A drawing can fail either alone. Geometry at 1:50 under a 1:100 label is
    correct work mislabelled; geometry drawn at 1:100 and labelled 1:100 is
    honestly wrong work. The student needs to be told which one they did.

    The two are not reported separately when they are the same mistake. A 1:50
    drawing labelled 1:100 fails both, but the student only has one thing to
    change, so it is reported once, as the label being wrong.

    When no scale fits the geometry at all -- the room is simply the wrong size,
    and not at some other scale -- nothing is claimed about the scale. The room
    check reports that, and guessing a scale from a drawing that has none would
    replace a true statement with a false one.
    """
    declared = drawing.scale_denominator
    required = exercise.scale_denominator
    findings: FindingList = []

    # Both axes must agree before any scale is claimed.
    #
    # A single axis is not enough, and reading one is how this check used to
    # accuse students of a scale they were never working at. A sheet 70 mm wide
    # and 72 mm tall implies 1:60 from the width and 1:50 from the height: the
    # two disagree, so the drawing is not at any consistent scale and the honest
    # answer is to say nothing about scale at all. The room check reports the
    # size that is actually wrong. Reading the width alone would have reported
    # "drawn at 1:60", which is a false statement about a sheet on which nothing
    # is at 1:60.
    implied: int | None = _consistent_implied_scale(exercise, drawing)

    metadata = {
        "required_scale_denominator": required,
        "declared_scale_denominator": declared,
        "implied_scale_denominator": implied,
        "room_width_expected_mm": str(
            actual_to_drawing(exercise.room_width_mm, required)
        ),
        "room_width_drawn_mm": str(drawing.room_width),
    }

    def label_disagrees_with_geometry() -> Finding:
        return _error(
            FindingCode.SCALE_ERROR,
            (
                f"The sheet measures {drawing.room_width} mm where 1:{required} "
                f"requires {actual_to_drawing(exercise.room_width_mm, required)} mm, "
                f"so it is drawn at 1:{implied}"
                + (
                    f" -- not the 1:{declared} it is labelled."
                    if declared != required
                    else "."
                )
            ),
            expected=declared,
            actual=implied,
            difference=implied - declared,
            unit="scale",
            geometry_reference="room",
            metadata=metadata,
        )

    if declared != required:
        if implied == required:
            # The geometry is right; only the title block is wrong. One fault.
            return [label_disagrees_with_geometry()]
        findings.append(
            _error(
                FindingCode.SCALE_ERROR,
                f"Drawing is labelled 1:{declared}; the brief requires 1:{required}.",
                expected=required,
                actual=declared,
                difference=declared - required,
                unit="scale",
                geometry_reference="drawing",
                metadata=metadata,
            )
        )
        # Only worth a second finding if the label is wrong independently of the
        # brief: geometry at some third scale, so label and sheet disagree too.
        if implied is not None and implied != declared:
            findings.append(label_disagrees_with_geometry())
        return findings

    if implied is not None and implied != declared:
        return [label_disagrees_with_geometry()]
    return []


def _consistent_implied_scale(
    exercise: ExerciseRead, drawing: StudentDrawing
) -> int | None:
    """The scale the whole sheet agrees on, or ``None`` if the axes disagree.

    A scale is a property of the sheet, not of one measurement, so it may only be
    named when every available axis implies the same denominator. Returning
    ``None`` means "this drawing is at no consistent scale", which is a
    statement the caller is expected to honour by not blaming the scale.
    """
    candidates: list[int] = []
    for actual_mm, drawn_mm in (
        (exercise.room_width_mm, drawing.room_width),
        (exercise.room_height_mm, drawing.room_height),
    ):
        try:
            candidates.append(calculate_scale(actual_mm, drawn_mm))
        except Exception:  # noqa: BLE001 - any unusable axis vetoes the claim
            return None

    # More than one distinct denominator means the sheet has no single scale.
    return candidates[0] if len(set(candidates)) == 1 else None


# --- 2. Room -------------------------------------------------------------


def validate_room(
    exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Are the room's clear internal dimensions correct at the declared scale?"""
    findings: FindingList = []
    scale = drawing.scale_denominator

    for axis, actual_mm, drawn_mm in (
        ("width", exercise.room_width_mm, drawing.room_width),
        ("height", exercise.room_height_mm, drawing.room_height),
    ):
        expected_paper = expected_paper_mm(exercise, drawing, actual_mm)
        if not _outside(drawn_mm, expected_paper, policy.room_dimension_mm):
            continue
        findings.append(
            _error(
                FindingCode.ROOM_DIMENSION_ERROR,
                (
                    f"Room {axis} is {drawn_mm} mm on the sheet; 1:{scale} "
                    f"requires {expected_paper} mm."
                ),
                expected=expected_paper,
                actual=drawn_mm,
                difference=drawn_mm - expected_paper,
                geometry_reference="room",
                metadata={
                    "axis": axis,
                    "expected_actual_mm": actual_mm,
                    "actual_actual_mm": str(drawing_to_actual(drawn_mm, scale)),
                    "scale_denominator": scale,
                },
            )
        )
    return findings


# --- 3. Walls ------------------------------------------------------------


def _side_of_wall(drawing: StudentDrawing, wall_id) -> str | None:
    """Which room side's boundary wall this is, if any."""
    for side in ("north", "south", "east", "west"):
        wall = drawing.wall_on_side(side)
        if wall is not None and wall.id == wall_id:
            return side
    return None


def validate_walls(
    exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Is every wall drawn at the specified thickness?"""
    findings: FindingList = []
    scale = drawing.scale_denominator
    expected_paper = expected_paper_mm(exercise, drawing, exercise.wall_thickness_mm)

    for wall in drawing.walls:
        if not _outside(wall.thickness_mm, expected_paper, policy.wall_thickness_mm):
            continue
        findings.append(
            _error(
                FindingCode.WALL_THICKNESS_ERROR,
                (
                    f"Wall {wall.id} is {wall.thickness_mm} mm thick on the sheet; "
                    f"the brief requires {exercise.wall_thickness_mm} mm, which is "
                    f"{expected_paper} mm at 1:{scale}."
                ),
                expected=expected_paper,
                actual=wall.thickness_mm,
                difference=wall.thickness_mm - expected_paper,
                geometry_reference=f"wall:{wall.id}",
                metadata={
                    "wall_id": str(wall.id),
                    # The side is carried in the finding so the UI can say
                    # "the north wall" without holding the drawing, and so the
                    # stored finding still reads in human terms after the
                    # drawing it came from is gone.
                    "side": _side_of_wall(drawing, wall.id),
                    "expected_actual_mm": exercise.wall_thickness_mm,
                    "actual_actual_mm": str(
                        drawing_to_actual(wall.thickness_mm, scale)
                    ),
                    "axis": wall.axis.value,
                },
            )
        )
    return findings


# --- 4. Openings ---------------------------------------------------------


def _validate_opening_count(
    drawing: StudentDrawing, requirements: Sequence[Any], kind: OpeningKind
) -> FindingList:
    """Too few or too many of an opening.

    This is the only place absence is reported. The side check below deliberately
    does not also report a missing door on a required wall: that is the same
    single mistake, and reporting it twice would make a one-error drawing look
    like a two-error one.
    """
    required = sum(requirement.count for requirement in requirements)
    drawn = len(drawing.openings_of_kind(kind))
    if drawn == required:
        return []

    if drawn < required:
        return [
            _error(
                FindingCode.MISSING_ELEMENT,
                (
                    f"The brief requires {required} {kind.value}(s); the drawing "
                    f"has {drawn}."
                ),
                expected=required,
                actual=drawn,
                difference=drawn - required,
                unit="count",
                geometry_reference=kind.value,
                metadata={"kind": kind.value, "required": required, "drawn": drawn},
            )
        ]

    return [
        _error(
            FindingCode.UNEXPECTED_ELEMENT,
            (
                f"The brief requires {required} {kind.value}(s); the drawing has "
                f"{drawn}."
            ),
            expected=required,
            actual=drawn,
            difference=drawn - required,
            unit="count",
            geometry_reference=kind.value,
            metadata={"kind": kind.value, "required": required, "drawn": drawn},
        )
    ]


def _validate_opening_widths(
    exercise: ExerciseRead,
    drawing: StudentDrawing,
    requirements: Sequence[Any],
    kind: OpeningKind,
    policy: TolerancePolicy,
) -> FindingList:
    """Match each drawn opening to a required width and report the differences.

    Openings are paired with requirements in submission order. Pairing by value
    instead would report the same mistake once per candidate requirement, and
    pairing by set membership would lose track of *which* opening is wrong,
    which is the part a student has to act on.
    """
    code = (
        FindingCode.DOOR_WIDTH_ERROR
        if kind is OpeningKind.DOOR
        else FindingCode.WINDOW_WIDTH_ERROR
    )
    scale = drawing.scale_denominator
    required_widths: list[int] = []
    for requirement in requirements:
        required_widths.extend([requirement.width_mm] * requirement.count)

    findings: FindingList = []
    for opening, expected_actual in zip(
        drawing.openings_of_kind(kind), required_widths, strict=False
    ):
        expected_paper = actual_to_drawing(expected_actual, scale)
        if not _outside(opening.width_mm, expected_paper, policy.opening_width_mm):
            continue
        findings.append(
            _error(
                code,
                (
                    f"{kind.value.capitalize()} is {opening.width_mm} mm wide on the "
                    f"sheet; the brief requires {expected_actual} mm, which is "
                    f"{expected_paper} mm at 1:{scale}."
                ),
                expected=expected_paper,
                actual=opening.width_mm,
                difference=opening.width_mm - expected_paper,
                geometry_reference=f"{kind.value}:{opening.id}",
                metadata={
                    "opening_id": str(opening.id),
                    # The side is recorded so the stored finding can still name
                    # where it is once the drawing is gone. Without it, a student
                    # re-reading a stored attempt is told only "a door".
                    "actual_side": _side_of_host(drawing, opening),
                    "host_wall_id": str(opening.host_wall_id),
                    "expected_actual_mm": expected_actual,
                    "actual_actual_mm": str(drawing_to_actual(opening.width_mm, scale)),
                },
            )
        )
    return findings


def _side_of_host(drawing: StudentDrawing, opening: Opening) -> str | None:
    """The room side whose boundary wall hosts this opening."""
    for side in ("north", "south", "east", "west"):
        wall = drawing.wall_on_side(side)
        if wall is not None and wall.id == opening.host_wall_id:
            return side
    return None


def _validate_opening_sides(
    exercise: ExerciseRead,
    drawing: StudentDrawing,
    requirements: Sequence[Any],
    kind: OpeningKind,
) -> FindingList:
    """Match each drawn opening to a required side and report the ones that fail.

    Openings are matched against required slots in submission order, which is
    what lets a door be told apart from a door in the wrong place. Both are
    visible in the drawing, but they need opposite corrections: move this one,
    or add another. Reporting the first when the second happened would send a
    student to do work that changes nothing.

    A required wall with no opening on it is *not* reported here. That is the
    count check's finding, and saying it twice would inflate the error count a
    student is shown.
    """
    code = (
        FindingCode.DOOR_PLACEMENT_ERROR
        if kind is OpeningKind.DOOR
        else FindingCode.OPENING_PLACEMENT_ERROR
    )
    required_sides: list[str] = []
    for requirement in requirements:
        if requirement.wall is not None:
            required_sides.extend([requirement.wall] * requirement.count)

    # An opening whose host wall is absent from the drawing has no side. That is
    # a dangling reference, which the fit check reports; deciding here as well
    # would raise one fault to two findings.
    known_walls = {wall.id for wall in drawing.walls}

    findings: FindingList = []
    outstanding = list(required_sides)
    for opening in drawing.openings_of_kind(kind):
        if opening.host_wall_id not in known_walls:
            continue
        side = _side_of_host(drawing, opening)
        if side is not None and side in outstanding:
            outstanding.remove(side)
            continue
        findings.append(
            _error(
                code,
                (
                    f"The {kind.value} is drawn on the {side or 'unplaced'} side; "
                    f"the brief requires it on the "
                    f"{', '.join(sorted(set(required_sides))) or 'unspecified'} side."
                ),
                expected=None,
                actual=side,
                unit="side",
                geometry_reference=f"{kind.value}:{opening.id}",
                metadata={
                    "opening_id": str(opening.id),
                    "actual_side": side,
                    "required_sides": sorted(set(required_sides)),
                    "outstanding_sides": sorted(set(outstanding)),
                },
            )
        )
    return findings


def _validate_opening_fit(
    drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Does every opening actually sit inside the wall that hosts it?

    A door and a window that both hang off the end of their wall are the same
    structural fault, but they are corrected separately, so they keep separate
    codes rather than sharing a generic one.
    """
    findings: FindingList = []
    walls_by_id = {wall.id: wall for wall in drawing.walls}

    for opening in drawing.openings:
        code = (
            FindingCode.DOOR_PLACEMENT_ERROR
            if opening.kind is OpeningKind.DOOR
            else FindingCode.OPENING_PLACEMENT_ERROR
        )
        host = walls_by_id.get(opening.host_wall_id)
        if host is None:
            findings.append(
                _error(
                    code,
                    f"A {opening.kind.value} references a wall that is not in the drawing.",
                    unit="wall",
                    geometry_reference=f"{opening.kind.value}:{opening.id}",
                    metadata={
                        "opening_id": str(opening.id),
                        "host_wall_id": str(opening.host_wall_id),
                    },
                )
            )
            continue

        overhang = opening.end_offset_mm - host.length_mm
        if overhang <= policy.opening_placement_mm:
            continue
        findings.append(
            _error(
                code,
                (
                    f"The {opening.kind.value} at offset {opening.offset_mm} mm with "
                    f"width {opening.width_mm} mm runs {overhang} mm past the end of "
                    f"its {host.length_mm} mm wall."
                ),
                expected=host.length_mm,
                actual=opening.end_offset_mm,
                difference=overhang,
                geometry_reference=f"{opening.kind.value}:{opening.id}",
                metadata={
                    "opening_id": str(opening.id),
                    "actual_side": _side_of_host(drawing, opening),
                    "host_wall_id": str(host.id),
                    "wall_length_mm": str(host.length_mm),
                    "overhang_mm": str(overhang),
                },
            )
        )
    return findings


def validate_openings(
    exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Do the doors and windows match the brief in number, width, side and fit?"""
    findings: FindingList = []
    findings += _validate_opening_fit(drawing, policy)
    for kind, requirements in (
        (OpeningKind.DOOR, exercise.door_requirements),
        (OpeningKind.WINDOW, exercise.window_requirements),
    ):
        findings += _validate_opening_count(drawing, requirements, kind)
        findings += _validate_opening_widths(
            exercise, drawing, requirements, kind, policy
        )
        findings += _validate_opening_sides(exercise, drawing, requirements, kind)
    return findings


# --- 5. Dimensions -------------------------------------------------------


def _spans_for(drawing: StudentDrawing, axis: str) -> list:
    """Dimension lines running along ``axis``.

    ``width`` dimensions are horizontal lines (measuring east-west), ``height``
    dimensions are vertical ones.
    """
    spans = []
    for dimension in drawing.dimensions:
        if axis == "width" and is_horizontal(dimension.start, dimension.end):
            spans.append(dimension)
        elif axis == "height" and is_vertical(dimension.start, dimension.end):
            spans.append(dimension)
    return spans


def _validate_one_dimension(
    exercise: ExerciseRead,
    drawing: StudentDrawing,
    requirement: DimensionRequirement,
    policy: TolerancePolicy,
) -> FindingList:
    scale = drawing.scale_denominator
    expected_paper = expected_paper_mm(exercise, drawing, requirement.value_mm)
    spans = _spans_for(drawing, requirement.axis)
    findings: FindingList = []

    if not spans:
        findings.append(
            _error(
                FindingCode.MISSING_ELEMENT,
                f"The brief requires a {requirement.axis} dimension; the drawing has none.",
                expected=expected_paper,
                unit="mm",
                geometry_reference=f"dimension:{requirement.axis}",
                metadata={
                    "axis": requirement.axis,
                    "expected_actual_mm": requirement.value_mm,
                },
            )
        )
        return findings

    for dimension in spans:
        span = dimension.measured_mm

        # 1. Does the dimension line span the right distance on the sheet?
        if _outside(span, expected_paper, policy.dimension_mm):
            findings.append(
                _error(
                    FindingCode.DIMENSION_ERROR,
                    (
                        f"The {requirement.axis} dimension line spans {span} mm; "
                        f"{requirement.value_mm} mm is {expected_paper} mm at 1:{scale}."
                    ),
                    expected=expected_paper,
                    actual=span,
                    difference=span - expected_paper,
                    geometry_reference=f"dimension:{requirement.axis}",
                    metadata={
                        "axis": requirement.axis,
                        "span_mm": str(span),
                        "expected_actual_mm": requirement.value_mm,
                        "span_actual_mm": str(drawing_to_actual(span, scale)),
                    },
                )
            )

        # 2. Is it labelled with the right number?
        # A wrong label and a wrong span are different mistakes, and a student
        # who made one has usually not made the other.
        #
        # The label is compared in REAL-WORLD millimetres, because that is what
        # the student typed: a dimension reading "3600" states a real dimension
        # and is never scaled. Judging it with the paper-space tolerance would
        # forgive 50x too much at 1:50 -- a tolerance that silently marks wrong
        # work right, which is the one failure this product must not make.
        label_difference = dimension.actual_value_mm - Decimal(requirement.value_mm)
        if abs(label_difference) > policy.dimension_label_mm:
            findings.append(
                _error(
                    FindingCode.DIMENSION_ERROR,
                    (
                        f"A {requirement.axis} dimension is labelled "
                        f"{dimension.actual_value_mm} mm; the brief requires "
                        f"{requirement.value_mm} mm."
                    ),
                    expected=Decimal(requirement.value_mm),
                    actual=dimension.actual_value_mm,
                    difference=label_difference,
                    unit="mm",
                    geometry_reference=(
                        f"dimension:{dimension.start.x},{dimension.start.y}"
                    ),
                    metadata={
                        "axis": requirement.axis,
                        "label_mm": str(dimension.actual_value_mm),
                        "span_mm": str(span),
                    },
                )
            )
    return findings


def validate_dimensions(
    exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Are the required dimension lines present, correctly spanning and labelled?"""
    findings: FindingList = []
    for requirement in exercise.dimension_requirements:
        findings += _validate_one_dimension(
            exercise, drawing, requirement, policy
        )
    return findings


# --- 6. Alignment --------------------------------------------------------


def _touches(wall: Wall, point) -> bool:
    """Does a wall's centreline endpoint coincide with this point?"""
    return point in (wall.start, wall.end)


def validate_alignment(
    exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy
) -> FindingList:
    """Do the walls form a closed rectangle that matches the room boundary?

    Walls are measured centreline to centreline, so the room's clear internal
    dimension is the span of the boundary. If the walls do not close, or do not
    sit on that boundary, every other measurement in the drawing is describing a
    shape that does not exist -- so this is reported alongside them rather than
    instead of them.
    """
    findings: FindingList = []

    if len(drawing.walls) != 4:
        findings.append(
            _error(
                FindingCode.ALIGNMENT_ERROR,
                (
                    f"A rectangular room needs 4 walls; the drawing has "
                    f"{len(drawing.walls)}, so they do not form a closed rectangle."
                ),
                expected=4,
                actual=len(drawing.walls),
                difference=len(drawing.walls) - 4,
                unit="count",
                geometry_reference="room",
                metadata={"wall_count": len(drawing.walls)},
            )
        )

    for side in ("north", "south", "east", "west"):
        if drawing.wall_on_side(side) is None:
            findings.append(
                _error(
                    FindingCode.ALIGNMENT_ERROR,
                    f"No wall lies on the {side} boundary of the room.",
                    expected=side,
                    unit="side",
                    geometry_reference=f"wall:{side}",
                    metadata={"side": side},
                )
            )

    for corner in drawing.room.corners_in_order:
        touching = [wall for wall in drawing.walls if _touches(wall, corner)]
        if len(touching) < 2:
            findings.append(
                _error(
                    FindingCode.ALIGNMENT_ERROR,
                    (
                        f"Corner ({corner.x}, {corner.y}) is met by "
                        f"{len(touching)} wall(s); a closed room needs 2."
                    ),
                    expected=2,
                    actual=len(touching),
                    difference=len(touching) - 2,
                    unit="count",
                    geometry_reference=f"corner:{corner.x},{corner.y}",
                    metadata={"corner": {"x": str(corner.x), "y": str(corner.y)}},
                )
            )

    return findings
