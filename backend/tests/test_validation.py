"""Tests for the deterministic validation engine.

The contract under test is the one the product makes to a student:

  1. a correct drawing passes, and passes with *no* findings
  2. every kind of mistake produces exactly the finding that describes it
  3. the same input always produces the same output

These tests assert on codes and numbers, not on prose. A message may be reworded
freely; a code or an ``expected``/``actual`` pair may not, because the tutor
keys off them.
"""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from app.geometry.drawing import DrawingFormatError, StudentDrawing, stable_id
from app.schemas.exercise import ExerciseRead
from app.validation import (
    TolerancePolicy,
    aggregate_findings,
    validate_alignment,
    validate_dimensions,
    validate_drawing,
    validate_openings,
    validate_room,
    validate_scale,
    validate_walls,
)
from app.validation.codes import FindingCode, Severity
from app.validation.findings import Finding
from tests.factories import (
    WALL_IDS,
    north_star_drawing,
    north_star_exercise_payload,
)

STRICT = TolerancePolicy.strict()


@pytest.fixture
def exercise() -> ExerciseRead:
    return _exercise()


def _drawing(payload: dict) -> StudentDrawing:
    return StudentDrawing.from_dict(payload)


def _exercise(**overrides) -> ExerciseRead:
    """Build a brief with fields replaced.

    Goes back through ``model_validate`` rather than ``model_copy(update=...)``,
    which does not validate: a raw requirement dict would survive as a dict and
    then fail on attribute access, testing the wrong thing.
    """
    return ExerciseRead.model_validate(
        {
            **north_star_exercise_payload(),
            "id": "00000000-0000-0000-0000-0000000000ff",
            "created_at": "2026-01-01T00:00:00+00:00",
            **overrides,
        }
    )


def _codes(findings) -> list[str]:
    return [f.code.value for f in findings]


def _only(findings) -> Finding:
    assert len(findings) == 1, [f.code.value for f in findings]
    return findings[0]


# --- The happy path ------------------------------------------------------


class TestCorrectDrawing:
    def test_correct_drawing_passes_with_no_findings(self, exercise):
        result = validate_drawing(exercise, _drawing(north_star_drawing()))

        assert result.passed is True
        assert result.findings == ()
        assert result.summary.total == 0
        assert result.summary.error_count == 0

    def test_every_individual_check_is_silent_on_a_correct_drawing(self, exercise):
        drawing = _drawing(north_star_drawing())

        assert validate_scale(exercise, drawing, STRICT) == []
        assert validate_room(exercise, drawing, STRICT) == []
        assert validate_walls(exercise, drawing, STRICT) == []
        assert validate_openings(exercise, drawing, STRICT) == []
        assert validate_dimensions(exercise, drawing, STRICT) == []
        assert validate_alignment(exercise, drawing, STRICT) == []


# --- 1. Scale ------------------------------------------------------------


class TestScale:
    def test_wrong_declared_scale_is_reported(self, exercise):
        payload = north_star_drawing(scale=100)
        # Drawn honestly at 1:100, so the only fault is the wrong scale.
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "42", "y": "0"},
            {"x": "42", "y": "36"},
            {"x": "0", "y": "36"},
        ]
        result = validate_drawing(exercise, _drawing(payload))
        finding = _only([f for f in result.findings if f.code is FindingCode.SCALE_ERROR])

        assert finding.severity is Severity.ERROR
        assert finding.expected == 50
        assert finding.actual == 100
        assert finding.difference == 50
        assert result.passed is False

    def test_scale_error_still_reports_the_room_errors_it_causes(self, exercise):
        """A wrong scale is one mistake with visible consequences, not one row.

        The student drew the right room at the wrong size. Telling them only
        "wrong scale" leaves them to work out how wrong everything else is.
        """
        payload = north_star_drawing(scale=100)
        result = validate_drawing(exercise, _drawing(payload))

        assert "ROOM_DIMENSION_ERROR" in _codes(result.findings)
        assert "SCALE_ERROR" in _codes(result.findings)

    def test_a_correct_label_does_not_excuse_wrong_geometry(self, exercise):
        """Declaring 1:50 while drawing 1:100 is still a scale error.

        This is the failure the whole paper-space design exists to catch: if
        submissions arrived in building millimetres, this drawing would be
        indistinguishable from a correct one.
        """
        payload = north_star_drawing(scale=50)
        # Same 84x72 room, but the student halved every dimension on the sheet.
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "42", "y": "0"},
            {"x": "42", "y": "36"},
            {"x": "0", "y": "36"},
        ]
        payload["walls"] = [
            {**wall, "start": payload["room"]["boundary"][i % 4],
             "end": payload["room"]["boundary"][(i + 1) % 4],
             "thickness_mm": "2.3"}
            for i, wall in enumerate(payload["walls"])
        ]

        result = validate_drawing(exercise, _drawing(payload))
        scale_findings = [f for f in result.findings if f.code is FindingCode.SCALE_ERROR]

        assert len(scale_findings) == 1
        # The label itself is right; it is the geometry that betrays it.
        assert scale_findings[0].expected == 50
        assert scale_findings[0].actual == 100
        assert scale_findings[0].difference == 50
        assert scale_findings[0].metadata["implied_scale_denominator"] == 100
        assert "drawn at 1:100" in scale_findings[0].message
        assert result.passed is False

    def test_correct_work_mislabelled_reports_only_the_label(self, exercise):
        """Geometry drawn correctly but labelled wrong: one scale fault, not two.

        The geometry here is a valid 1:50 drawing under a 1:100 label, so the
        student has exactly one thing to change. The scale check must say that
        rather than also accusing the label of disagreeing with the sheet --
        both would be the same mistake reported twice.
        """
        payload = north_star_drawing(scale=100)

        result = validate_drawing(exercise, _drawing(payload))
        scale_findings = [f for f in result.findings if f.code is FindingCode.SCALE_ERROR]

        assert len(scale_findings) == 1
        assert scale_findings[0].message == (
            "The sheet measures 84 mm where 1:50 requires 84 mm, so it is drawn "
            "at 1:50 -- not the 1:100 it is labelled."
        )
        assert scale_findings[0].expected == 100
        assert scale_findings[0].actual == 50
        # The other codes are the documented cascade of trusting the bad label,
        # not a second opinion about the scale. Every one of them disappears
        # once the label is corrected, which is what makes the single scale
        # finding the actionable one.
        assert set(_codes(result.findings)) >= {
            "SCALE_ERROR", "ROOM_DIMENSION_ERROR", "WALL_THICKNESS_ERROR",
            "DOOR_WIDTH_ERROR", "DIMENSION_ERROR",
        }
        assert validate_drawing(
            exercise, _drawing({**payload, "scale_denominator": 50})
        ).passed is True

    def test_honestly_wrong_scale_reports_only_the_wrong_scale(self, exercise):
        """Drawn at 1:100 and labelled 1:100: honest, and still not the brief.

        Here the label and the geometry agree, so there is nothing to say about
        them disagreeing -- only that 1:100 is not 1:50.
        """
        payload = north_star_drawing(scale=100)
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "42", "y": "0"},
            {"x": "42", "y": "36"},
            {"x": "0", "y": "36"},
        ]
        payload["walls"] = [
            {**wall, "start": payload["room"]["boundary"][i % 4],
             "end": payload["room"]["boundary"][(i + 1) % 4],
             "thickness_mm": "2.3"}
            for i, wall in enumerate(payload["walls"])
        ]

        result = validate_drawing(exercise, _drawing(payload))
        scale_findings = [f for f in result.findings if f.code is FindingCode.SCALE_ERROR]

        assert len(scale_findings) == 1
        assert scale_findings[0].message == (
            "Drawing is labelled 1:100; the brief requires 1:50."
        )
        assert scale_findings[0].metadata["implied_scale_denominator"] == 100

    def test_three_way_disagreement_reports_both_faults(self, exercise):
        """A third scale is wrong twice over, so both faults are reported.

        The geometry is neither the required scale nor the labelled one, so the
        student has to change the drawing *and* the title block.
        """
        payload = north_star_drawing(scale=100)
        # 4200/60 = 70 and 3600/60 = 60, so both axes agree: this really is a
        # 1:60 sheet. A sheet that were 70 x 72 would be 1:60 wide and 1:50 tall
        # at once, which is no scale at all.
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "70", "y": "0"},
            {"x": "70", "y": "60"},
            {"x": "0", "y": "60"},
        ]

        result = validate_drawing(exercise, _drawing(payload))
        scale_findings = [f for f in result.findings if f.code is FindingCode.SCALE_ERROR]

        assert len(scale_findings) == 2
        assert {f.message for f in scale_findings} == {
            "Drawing is labelled 1:100; the brief requires 1:50.",
            "The sheet measures 70 mm where 1:50 requires 84 mm, so it is drawn "
            "at 1:60 -- not the 1:100 it is labelled.",
        }

    def test_an_uncommon_scale_is_measured_not_rejected(self, exercise):
        """1:60 is a real scale, and being unusual is not itself an error.

        The brief asked for 1:50, so this is a scale finding -- but the reported
        cause is the scale the student actually drew at, not that it is odd.
        """
        payload = north_star_drawing(scale=50)
        # 4200/60 = 70 and 3600/60 = 60, so both axes agree: this really is a
        # 1:60 sheet. A sheet that were 70 x 72 would be 1:60 wide and 1:50 tall
        # at once, which is no scale at all.
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "70", "y": "0"},
            {"x": "70", "y": "60"},
            {"x": "0", "y": "60"},
        ]

        result = validate_drawing(exercise, _drawing(payload))
        scale_findings = [f for f in result.findings if f.code is FindingCode.SCALE_ERROR]

        assert len(scale_findings) == 1
        assert scale_findings[0].actual == 60
        assert scale_findings[0].message == (
            "The sheet measures 70 mm where 1:50 requires 84 mm, so it is drawn "
            "at 1:60."
        )

    def test_a_distorted_room_is_not_blamed_on_the_scale(self, exercise):
        """A sheet whose two axes disagree is at no scale, and must not be told it is.

        70 x 72 mm implies 1:60 from the width and 1:50 from the height. Naming
        either one would be inventing a scale the student never used, and
        telling them to "draw at 1:60" would not make the 72 mm height correct.
        The room is genuinely the wrong size, so the room check reports it and
        the scale check stays quiet.
        """
        payload = north_star_drawing(scale=50)
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "70", "y": "0"},
            {"x": "70", "y": "72"},
            {"x": "0", "y": "72"},
        ]

        result = validate_drawing(exercise, _drawing(payload))

        assert [f for f in result.findings if f.code is FindingCode.SCALE_ERROR] == []
        assert any(f.code is FindingCode.ROOM_DIMENSION_ERROR for f in result.findings)
        assert result.passed is False

    def test_a_scale_is_claimed_only_when_both_axes_agree(self, exercise):
        """The distinguishing property of a real scale: the whole sheet fits it.

        Every sheet below is wrong for the brief. Only the ones whose width and
        height imply the *same* denominator get a scale finding, so the student
        is never sent to fix a scale that does not exist on their paper.
        """
        consistent = {(70, 60): "1:60", (42, 36): "1:100", (168, 144): "1:25"}
        for (width, height), expected_scale in consistent.items():
            payload = north_star_drawing(scale=50)
            payload["room"]["boundary"] = [
                {"x": "0", "y": "0"},
                {"x": str(width), "y": "0"},
                {"x": str(width), "y": str(height)},
                {"x": "0", "y": str(height)},
            ]

            scale_findings = [
                f
                for f in validate_drawing(exercise, _drawing(payload)).findings
                if f.code is FindingCode.SCALE_ERROR
            ]

            assert len(scale_findings) == 1, (width, height)
            assert expected_scale in scale_findings[0].message, (width, height)

    def test_one_axis_at_the_right_scale_does_not_rescue_the_other(self, exercise):
        """A correct width with a wrong height is a distorted room, not 1:50.

        The mirror of the case above, and the one that catches a check reading
        only the width: 84 mm wide is exactly 1:50, so a width-only check would
        stay silent and tell the student their scale was fine.
        """
        payload = north_star_drawing(scale=50)
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "84", "y": "0"},
            {"x": "84", "y": "60"},
            {"x": "0", "y": "60"},
        ]

        result = validate_drawing(exercise, _drawing(payload))

        assert [f for f in result.findings if f.code is FindingCode.SCALE_ERROR] == []
        assert any(f.code is FindingCode.ROOM_DIMENSION_ERROR for f in result.findings)

    def test_a_room_that_is_not_another_scale_claims_nothing_about_scale(self, exercise):
        """When no scale fits the geometry, the finding would be an invention.

        70.5 mm is not 1:60 -- that would draw 70 mm -- and it is not 1:59
        either, so the drawing has no scale at all. The room check reports the
        real problem; the scale check stays quiet rather than inventing one.
        """
        payload = north_star_drawing(scale=50)
        payload["room"]["boundary"] = [
            {"x": "0", "y": "0"},
            {"x": "70.5", "y": "0"},
            {"x": "70.5", "y": "72"},
            {"x": "0", "y": "72"},
        ]

        result = validate_drawing(exercise, _drawing(payload))

        assert [f for f in result.findings if f.code is FindingCode.SCALE_ERROR] == []
        assert any(f.code is FindingCode.ROOM_DIMENSION_ERROR for f in result.findings)
        assert result.passed is False


# --- 2. Room dimensions --------------------------------------------------


class TestRoomDimensions:
    def test_wrong_width_reports_expected_and_actual_in_paper_mm(self, exercise):
        result = validate_drawing(
            exercise, _drawing(north_star_drawing(room_width_mm=70))
        )
        finding = _only(
            [f for f in result.findings if f.code is FindingCode.ROOM_DIMENSION_ERROR]
        )

        assert finding.expected == Decimal("84")
        assert finding.actual == Decimal("70")
        assert finding.difference == Decimal("-14")
        assert finding.unit == "mm"
        assert finding.geometry_reference == "room"

    def test_metadata_carries_the_building_millimetres_too(self, exercise):
        findings = validate_room(
            exercise, _drawing(north_star_drawing(room_width_mm=70)), STRICT
        )
        finding = _only(findings)

        assert finding.metadata["expected_actual_mm"] == 4200
        assert Decimal(finding.metadata["actual_actual_mm"]) == Decimal(3500)
        assert finding.metadata["axis"] == "width"

    def test_wrong_height_is_reported_independently(self, exercise):
        result = validate_drawing(
            exercise, _drawing(north_star_drawing(room_height_mm=60))
        )
        axes = {
            f.metadata["axis"]
            for f in result.findings
            if f.code is FindingCode.ROOM_DIMENSION_ERROR
        }

        assert axes == {"height"}

    def test_wrong_width_and_height_are_both_reported(self, exercise):
        result = validate_drawing(
            exercise,
            _drawing(north_star_drawing(room_width_mm=70, room_height_mm=60)),
        )
        room_findings = [
            f for f in result.findings if f.code is FindingCode.ROOM_DIMENSION_ERROR
        ]

        assert {f.metadata["axis"] for f in room_findings} == {"width", "height"}


# --- 3. Wall thickness ---------------------------------------------------


class TestWallThickness:
    def test_wrong_thickness_reports_every_offending_wall(self, exercise):
        payload = north_star_drawing()
        for wall in payload["walls"]:
            wall["thickness_mm"] = "5"

        findings = validate_walls(exercise, _drawing(payload), STRICT)

        assert len(findings) == 4
        assert {f.code for f in findings} == {FindingCode.WALL_THICKNESS_ERROR}
        assert all(f.expected == Decimal("4.6") for f in findings)
        assert all(f.actual == Decimal("5") for f in findings)

    def test_thickness_is_compared_in_paper_mm_not_building_mm(self, exercise):
        """230 mm at 1:50 is 4.6 mm; a student drawing 230 would be caught."""
        findings = validate_walls(
            exercise, _drawing(north_star_drawing(wall_thickness_mm=230)), STRICT
        )

        assert len(findings) == 4
        assert findings[0].metadata["expected_actual_mm"] == 230

    def test_metadata_converts_paper_back_to_building_by_multiplying(self, exercise):
        """5 mm on the sheet at 1:50 is 250 mm in the building, not 0.1 mm.

        The two conversions are inverses, and using the wrong one produces a
        number that is still plausible-looking, so the direction is pinned here.
        """
        findings = validate_walls(
            exercise, _drawing(north_star_drawing(wall_thickness_mm=5)), STRICT
        )

        assert Decimal(findings[0].metadata["actual_actual_mm"]) == Decimal(250)


# --- 4. Openings ---------------------------------------------------------


class TestOpenings:
    def test_missing_door_is_a_missing_element(self, exercise):
        findings = validate_openings(
            exercise, _drawing(north_star_drawing(include_door=False)), STRICT
        )

        assert _codes(findings) == ["MISSING_ELEMENT"]
        assert findings[0].metadata["required"] == 1
        assert findings[0].metadata["drawn"] == 0

    def test_wrong_door_width_is_a_door_width_error(self, exercise):
        finding = _only(
            validate_openings(
                exercise, _drawing(north_star_drawing(door_width_mm=25)), STRICT
            )
        )

        assert finding.code is FindingCode.DOOR_WIDTH_ERROR
        assert finding.expected == Decimal("18")
        assert finding.actual == Decimal("25")
        assert finding.metadata["expected_actual_mm"] == 900

    def test_door_on_the_wrong_wall_is_a_placement_error(self, exercise):
        finding = _only(
            validate_openings(
                exercise, _drawing(north_star_drawing(door_side="north")), STRICT
            )
        )

        assert finding.code is FindingCode.DOOR_PLACEMENT_ERROR
        assert finding.actual == "north"
        assert finding.metadata["required_sides"] == ["south"]

    def test_a_misplaced_door_is_reported_once_not_twice(self, exercise):
        """A door on the wrong wall is one error, not a placement plus a missing.

        The drawing does have a door, so the count is right and only the wall is
        wrong. Reporting a missing south door as well would show the student two
        errors for one mistake, and "add a door" is the wrong instruction when the
        door already exists.
        """
        findings = validate_openings(
            exercise, _drawing(north_star_drawing(door_side="north")), STRICT
        )

        assert _codes(findings) == ["DOOR_PLACEMENT_ERROR"]

    def test_a_missing_door_is_reported_once_not_twice(self, exercise):
        """Symmetrically, an absent door is one error, not a missing plus a count."""
        findings = validate_openings(
            exercise, _drawing(north_star_drawing(include_door=False)), STRICT
        )

        assert _codes(findings) == ["MISSING_ELEMENT"]

    def test_door_overhanging_its_wall_is_a_placement_error(self, exercise):
        """An 18 mm door on an 84 mm wall starting at 80 mm does not fit."""
        finding = _only(
            validate_openings(
                exercise,
                _drawing(north_star_drawing(door_offset_mm=80)),
                STRICT,
            )
        )

        assert finding.code is FindingCode.DOOR_PLACEMENT_ERROR
        assert finding.metadata["overhang_mm"] == "14"

    def test_extra_door_is_unexpected_not_accepted(self, exercise):
        payload = north_star_drawing()
        payload["openings"].append(
            {
                "host_wall_id": str(WALL_IDS["east"]),
                "offset_mm": "10",
                "width_mm": "18",
                "kind": "door",
            }
        )

        result = validate_drawing(exercise, _drawing(payload))
        assert "UNEXPECTED_ELEMENT" in _codes(result.findings)
        assert result.passed is False

    def test_a_window_never_reports_a_door_code(self, exercise):
        """Windows and doors have separate width codes; neither may borrow."""
        payload = north_star_drawing()
        payload["openings"].append(
            {
                "host_wall_id": str(WALL_IDS["north"]),
                "offset_mm": "10",
                "width_mm": "10",
                "kind": "window",
            }
        )
        exercise = _exercise(
            window_requirements=[
                {"kind": "window", "width_mm": 1200, "count": 1, "wall": "north"}
            ]
        )

        findings = validate_openings(exercise, _drawing(payload), STRICT)

        assert FindingCode.DOOR_WIDTH_ERROR not in _codes(findings)
        assert FindingCode.WINDOW_WIDTH_ERROR in _codes(findings)

    def test_opening_hosting_an_absent_wall_is_reported(self, exercise):
        """A dangling host reference is one error, not one per check that sees it."""
        payload = north_star_drawing()
        payload["openings"][0]["host_wall_id"] = (
            "00000000-0000-4000-8000-0000000000ff"
        )

        findings = validate_openings(exercise, _drawing(payload), STRICT)

        assert _codes(findings) == ["DOOR_PLACEMENT_ERROR"]
        assert findings[0].unit == "wall"


# --- 5. Dimensions -------------------------------------------------------


class TestDimensions:
    def test_missing_dimension_is_a_missing_element(self, exercise):
        finding = _only(
            validate_dimensions(
                exercise,
                _drawing(north_star_drawing(include_width_dimension=False)),
                STRICT,
            )
        )

        assert finding.code is FindingCode.MISSING_ELEMENT
        assert finding.metadata["axis"] == "width"

    def test_wrong_label_is_reported_separately_from_a_wrong_span(self, exercise):
        """A correct span with a wrong number is a different mistake to a wrong span.

        The line is drawn to the right length and the wrong figure was typed
        into it. Telling the student to re-measure the line would be noise.
        """
        finding = _only(
            validate_dimensions(
                exercise,
                _drawing(north_star_drawing(dimension_label_mm=3600)),
                STRICT,
            )
        )

        assert finding.code is FindingCode.DIMENSION_ERROR
        assert finding.metadata["label_mm"] == "3600"
        assert finding.metadata["span_mm"] == "84"

    def test_dimension_span_must_match_the_declared_scale(self, exercise):
        payload = north_star_drawing()
        payload["dimensions"][0]["end"] = {"x": "70", "y": "-10"}

        finding = _only(
            validate_dimensions(exercise, _drawing(payload), STRICT)
        )

        assert finding.code is FindingCode.DIMENSION_ERROR
        assert finding.metadata["span_mm"] == "70"
        assert finding.metadata["expected_actual_mm"] == 4200

    def test_vertical_dimension_is_matched_to_a_height_requirement(self, exercise):
        exercise = _exercise(
            dimension_requirements=[
                {"axis": "height", "value_mm": 3600, "on_wall": "west"}
            ]
        )
        drawing = _drawing(north_star_drawing(include_height_dimension=True))

        assert validate_dimensions(exercise, drawing, STRICT) == []

    def test_a_vertical_requirement_is_not_satisfied_by_a_horizontal_line(self, exercise):
        """A width dimension drawn sideways is not a height dimension."""
        exercise = _exercise(
            dimension_requirements=[
                {"axis": "height", "value_mm": 3600, "on_wall": "west"}
            ]
        )
        drawing = _drawing(north_star_drawing(include_height_dimension=False))

        findings = validate_dimensions(exercise, drawing, STRICT)

        assert _codes(findings) == ["MISSING_ELEMENT"]


# --- 6. Alignment --------------------------------------------------------


class TestAlignment:
    def test_missing_wall_is_an_alignment_error(self, exercise):
        payload = north_star_drawing()
        payload["walls"] = payload["walls"][:3]

        findings = validate_alignment(exercise, _drawing(payload), STRICT)

        assert "ALIGNMENT_ERROR" in _codes(findings)
        assert any(
            f.metadata.get("side") == "east" for f in findings
        ), "the absent wall's side must be named"

    def test_a_wrong_wall_count_is_reported(self, exercise):
        payload = north_star_drawing()
        payload["walls"] = payload["walls"][:3]

        findings = validate_alignment(exercise, _drawing(payload), STRICT)
        counts = [f for f in findings if f.metadata.get("wall_count") is not None]

        assert counts and counts[0].expected == 4
        assert counts[0].actual == 3

    def test_walls_forming_an_open_box_report_the_open_corner(self, exercise):
        """Two walls meeting at a corner is not a room."""
        payload = north_star_drawing()
        payload["walls"] = [
            payload["walls"][0],
            payload["walls"][2],
        ]

        findings = validate_alignment(exercise, _drawing(payload), STRICT)

        assert "ALIGNMENT_ERROR" in _codes(findings)

    def test_alignment_errors_do_not_suppress_the_measurement_errors(self, exercise):
        """Every check runs. A student gets every cause, not the first one."""
        payload = north_star_drawing(room_width_mm=70, wall_thickness_mm=9)
        payload["walls"] = payload["walls"][:3]

        result = validate_drawing(exercise, _drawing(payload))

        assert "ALIGNMENT_ERROR" in _codes(result.findings)
        assert "ROOM_DIMENSION_ERROR" in _codes(result.findings)
        assert "WALL_THICKNESS_ERROR" in _codes(result.findings)


# --- Tolerance -----------------------------------------------------------


class TestTolerance:
    def test_strict_default_forbids_a_sub_millimetre_shortfall(self, exercise):
        """84.05 mm where 84 mm is required is not 84 mm."""
        result = validate_drawing(
            exercise, _drawing(north_star_drawing(room_width_mm="84.05"))
        )

        assert result.passed is False
        assert "ROOM_DIMENSION_ERROR" in _codes(result.findings)

    def test_tolerance_can_be_configured(self, exercise):
        """Thickness is the clean lever: nothing else is coupled to it.

        Room width is not used here because the reference drawing's dimension
        line spans the room, so widening the room would trip the dimension check
        too and the test would be asserting two things at once.
        """
        drawing = _drawing(north_star_drawing(wall_thickness_mm=5))
        policy = TolerancePolicy(wall_thickness_mm=1)

        result = validate_drawing(exercise, drawing, policy)

        assert validate_walls(exercise, drawing, TolerancePolicy.strict())
        assert result.passed is True
        assert result.tolerance["wall_thickness_mm"] == "1"

    def test_tolerance_is_reported_so_a_lenient_verdict_is_visible(self, exercise):
        result = validate_drawing(
            exercise,
            _drawing(north_star_drawing(wall_thickness_mm=6)),
            TolerancePolicy(wall_thickness_mm=5),
        )

        assert result.passed is True
        assert result.tolerance == {
            "room_dimension_mm": "0",
            "wall_thickness_mm": "5",
            "opening_width_mm": "0",
            "opening_placement_mm": "0",
            "dimension_mm": "0",
            "dimension_label_mm": "0",
        }

    def test_negative_tolerance_is_rejected(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            TolerancePolicy.from_dict({"room_dimension_mm": -1})

    def test_misspelled_tolerance_field_is_rejected(self):
        with pytest.raises(ValueError, match="unknown tolerance field"):
            TolerancePolicy.from_dict({"room_dimention_mm": 5})


# --- Determinism ---------------------------------------------------------


class TestDeterminism:
    def test_identical_input_gives_identical_output(self, exercise):
        payload = north_star_drawing(room_width_mm=70, door_width_mm=25)
        first = validate_drawing(exercise, _drawing(copy.deepcopy(payload)))
        second = validate_drawing(exercise, _drawing(copy.deepcopy(payload)))

        assert first.to_dict() == second.to_dict()

    def test_omitted_opening_ids_are_derived_not_random(self, exercise):
        """A submission without opening ids must still reproduce exactly.

        The ids appear in ``geometry_reference``. If they were random, the same
        bytes would produce different references on each run and a finding could
        not be reproduced or appealed.
        """
        payload = north_star_drawing(room_width_mm=70, door_width_mm=25)
        assert "id" not in payload["openings"][0]

        first = validate_drawing(exercise, _drawing(copy.deepcopy(payload)))
        second = validate_drawing(exercise, _drawing(copy.deepcopy(payload)))

        assert first.to_dict() == second.to_dict()
        assert str(
            stable_id("opening", "0", "door", str(WALL_IDS["south"]), "30", "25")
        ) in {str(f.metadata.get("opening_id")) for f in first.findings}

    def test_summary_counts_agree_with_the_findings(self, exercise):
        result = validate_drawing(
            exercise,
            _drawing(north_star_drawing(room_width_mm=70, wall_thickness_mm=9)),
        )
        summary = aggregate_findings(result.findings)

        assert summary.total == len(result.findings)
        assert summary.error_count == sum(
            1 for f in result.findings if f.severity is Severity.ERROR
        )
        assert sum(summary.codes.values()) == summary.total

    def test_passed_is_true_only_when_there_are_no_errors(self, exercise):
        for kwargs in ({}, {"room_width_mm": 70}, {"wall_thickness_mm": 9}):
            result = validate_drawing(exercise, _drawing(north_star_drawing(**kwargs)))
            assert result.passed is (result.summary.error_count == 0)


# --- Findings are facts --------------------------------------------------


class TestFindingsAreFacts:
    def test_every_finding_carries_the_structured_fields(self, exercise):
        result = validate_drawing(
            exercise,
            _drawing(north_star_drawing(room_width_mm=70, door_width_mm=25)),
        )

        for finding in result.findings:
            assert finding.code is not None
            assert finding.severity in (Severity.ERROR, Severity.WARNING, Severity.INFO)
            assert isinstance(finding.metadata, dict)

    def test_codes_are_upper_case_on_the_wire(self, exercise):
        result = validate_drawing(
            exercise, _drawing(north_star_drawing(room_width_mm=70))
        )

        for finding in result.findings:
            assert finding.to_dict()["code"] == finding.code.name
            assert finding.to_dict()["severity"] in {"ERROR", "WARNING", "INFO"}

    def test_decimals_serialise_as_strings(self, exercise):
        """A JSON number is a double; 4.6 must not become 4.5999999999999996."""
        findings = validate_walls(
            exercise, _drawing(north_star_drawing(wall_thickness_mm=5)), STRICT
        )

        assert all(isinstance(f.to_dict()["expected"], str) for f in findings)
        assert findings[0].to_dict()["expected"] == "4.6"


# --- Boundary: malformed submissions -------------------------------------


class TestMalformedDrawings:
    def test_unknown_top_level_field_is_rejected(self, exercise):
        payload = north_star_drawing()
        payload["colour"] = "black"

        with pytest.raises(DrawingFormatError, match="unknown field"):
            _drawing(payload)

    def test_wall_without_an_id_is_rejected(self, exercise):
        """An opening references its wall by id, so a wall id cannot be invented."""
        payload = north_star_drawing()
        del payload["walls"][0]["id"]

        with pytest.raises(DrawingFormatError, match="missing required field 'id'"):
            _drawing(payload)

    def test_non_numeric_coordinate_is_rejected_by_path(self, exercise):
        payload = north_star_drawing()
        payload["walls"][0]["thickness_mm"] = "thick"

        with pytest.raises(DrawingFormatError, match=r"walls\[0\]"):
            _drawing(payload)

    def test_negative_thickness_is_rejected(self, exercise):
        payload = north_star_drawing()
        payload["walls"][0]["thickness_mm"] = "-4"

        with pytest.raises(DrawingFormatError):
            _drawing(payload)

    def test_malformed_drawing_never_reaches_the_checks(self, exercise):
        """A drawing that cannot be read is a 422, not a verdict of zero findings.

        Reporting "passed" for geometry the parser rejected would be the worst
        possible failure: it tells a student their drawing is correct when the
        server never understood it.
        """
        payload = north_star_drawing()
        payload["room"]["boundary"] = payload["room"]["boundary"][:3]

        with pytest.raises(DrawingFormatError):
            validate_drawing(exercise, _drawing(payload))
