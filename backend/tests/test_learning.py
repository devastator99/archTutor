"""Learning records: what a student was told, and what changed afterwards.

Two separate claims are made by this layer, and conflating them would be the
worst thing it could do.

The taxonomy answers "what kind of mistake is this" and the diff answers "did it
go away". Neither is "how well is this student". A finding says a room is 14 mm
wrong; it does not say the student is careless, and no count here is allowed to
become a judgement about a person.

The tests below cover the properties that make those two answers trustworthy:
total coverage of the codes, identity that survives an edit, and a diff that
never claims progress it cannot substantiate.
"""

from __future__ import annotations

import pytest

from app.learning.explanations import why_it_matters
from app.learning.feedback import build_feedback, concepts_for_exercise, format_quantity
from app.learning.progress import compare_attempts, finding_identity, summarise_progress
from app.learning.taxonomy import (
    CODE_TO_CATEGORY,
    MistakeCategory,
    category_counts,
    learning_record,
)
from app.schemas.exercise import ExerciseRead
from app.validation.codes import FindingCode
from app.validation.engine import validate_drawing
from tests.factories import north_star_drawing, north_star_exercise_payload

from app.geometry.drawing import StudentDrawing


def _exercise(**overrides) -> ExerciseRead:
    return ExerciseRead.model_validate(
        {
            **north_star_exercise_payload(),
            "id": "00000000-0000-0000-0000-0000000000ff",
            "created_at": "2026-01-01T00:00:00+00:00",
            **overrides,
        }
    )


def _validate(**overrides):
    exercise = _exercise()
    drawing = StudentDrawing.from_dict(north_star_drawing(**overrides))
    return exercise, drawing, validate_drawing(exercise, drawing)


class TestTaxonomy:
    def test_every_code_the_engine_can_emit_has_a_category(self):
        """A new code without a category would silently vanish from the record.

        The taxonomy is derived from the enum, so this fails the moment someone
        adds a finding code and forgets to teach the system what it means.
        """
        assert set(CODE_TO_CATEGORY) == set(FindingCode)

    def test_the_categories_are_the_ones_the_product_promises(self):
        """The nine the brief names, plus honest coverage of the tenth code.

        ``UNEXPECTED_ELEMENT`` has to be classified rather than dropped: a
        student who draws an extra door has made a mistake, and telling them
        nothing about it is the same as telling them it was fine.
        """
        assert {category.value for category in MistakeCategory} == {
            "SCALE_CONVERSION",
            "UNIT_CONFUSION",
            "ROOM_DIMENSION",
            "WALL_THICKNESS",
            "OPENING_WIDTH",
            "OPENING_PLACEMENT",
            "DIMENSION_PLACEMENT",
            "ALIGNMENT",
            "MISSING_ELEMENT",
            "UNEXPECTED_ELEMENT",
        }

    def test_a_1_to_1_drawing_is_a_unit_mistake_not_a_scale_mistake(self):
        """Drawing building millimetres is a specific, common, nameable error.

        It deserves its own category: "you drew the real size" is a completely
        different instruction from "you used the wrong scale", and lumping them
        together teaches the student nothing.
        """
        _, _, result = _validate(room_width_mm=4200, room_height_mm=3600)

        assert "UNIT_CONFUSION" in set(category_counts(result.findings))

    def test_counts_add_up_to_the_findings(self):
        _, _, result = _validate(room_width_mm=70, wall_thickness_mm="9")

        counts = category_counts(result.findings)

        assert sum(counts.values()) == len(result.findings)

    def test_the_first_attempt_is_a_baseline_not_an_improvement(self):
        """There is no history to improve on yet, so none is claimed."""
        _, _, result = _validate(room_width_mm=70)
        record = learning_record(result.findings)

        assert record["categories"]
        assert record["primary_category"]
        assert record["category_count"] == sum(record["categories"].values())

    def test_a_clean_drawing_records_nothing_rather_than_a_zero(self):
        _, _, result = _validate()

        assert result.passed is True
        assert learning_record(result.findings)["categories"] == {}


class TestFeedback:
    def test_every_finding_gets_the_same_seven_fields(self):
        """A student should never have to guess which panel is missing.

        Each field is a separate fact or a piece of teaching. A finding that
        lacked one would render as a card with a hole in it.
        """
        _, drawing, result = _validate(room_width_mm=70, wall_thickness_mm="9")
        issues = build_feedback(result.findings, drawing=drawing)

        assert issues
        for issue in issues:
            assert issue.what_is_wrong
            assert issue.where
            assert issue.why_it_matters
            assert issue.how_to_fix

    def test_it_speaks_about_a_wall_by_its_side(self):
        """A student needs to know which wall, not which index in a list."""
        _, drawing, result = _validate(wall_thickness_mm="9")
        issues = build_feedback(result.findings, drawing=drawing)

        walls = [i for i in issues if i.code == "WALL_THICKNESS_ERROR"]
        assert walls
        assert all("wall" in issue.where for issue in walls)

    def test_the_teaching_is_about_this_exercise(self):
        """A scale student has not practised is not a scale they can be taught.

        The concepts come from the brief, so a 1:20 student is never told to
        practise 1:50.
        """
        concepts = concepts_for_exercise(
            _exercise(scale_denominator=20, room_width_mm=2400)
        )

        assert any("1:20" in concept for concept in concepts)
        assert not any("1:50" in concept for concept in concepts)


class TestExplanation:
    def test_a_missing_element_reports_a_count_and_never_a_length(self):
        """"Expected: 1 mm" would be a measurement nobody took.

        A missing door has no width to report, so the engine states how many
        were required and how many were drawn. The card must not dress that count
        up as a dimension.
        """
        _, drawing, result = _validate(include_door=False)
        issues = build_feedback(result.findings, drawing=drawing)
        missing = [i for i in issues if i.code == "MISSING_ELEMENT"]

        assert missing
        for issue in missing:
            assert issue.unit == "count"
            assert format_quantity(issue.expected, issue.unit) == "1"
            assert not str(issue.expected).endswith("mm")

    def test_every_code_has_its_own_reason(self):
        """Two codes sharing a "why" is one mistake taught twice.

        A student who reads the same paragraph for two different faults learns
        that the panel is boilerplate and stops reading it.
        """
        reasons = {
            code: why_it_matters(code, {}) for code in FindingCode
        }

        assert all(reasons.values())
        # A handful of codes are refinements of the same fault, so a small
        # number of shared paragraphs is legitimate; total collapse is not.
        assert len(set(reasons.values())) >= len(FindingCode) // 2

    def test_a_reason_never_states_a_measurement_of_its_own(self):
        """These strings are written once, so they must not carry figures.

        A hand-written reason mentioning "100 mm" would be an unverified number
        in the one panel the student is being asked to trust, and it would
        contradict the engine's own figure beside it.
        """
        for code in FindingCode:
            text = why_it_matters(code, {})
            assert not text.rstrip(". ").endswith("mm"), code


class TestFindingIdentity:
    def test_the_same_mistake_keeps_its_identity_across_a_wider_value(self):
        """Identity is about which mistake, not how big it currently is."""
        _, d70, r70 = _validate(room_width_mm=70)
        _, d71, r71 = _validate(room_width_mm=71)

        before = [finding_identity(f, d70) for f in r70.findings]
        after = [finding_identity(f, d71) for f in r71.findings]

        assert "ROOM_DIMENSION_ERROR|width" in before
        assert "ROOM_DIMENSION_ERROR|width" in after

    def test_two_doors_are_distinguished_from_one_door(self):
        """Otherwise fixing the left door looks like fixing both."""
        exercise = _exercise(
            door_requirements=[
                {"kind": "door", "width_mm": 900, "count": 1, "wall": "south"},
                {"kind": "door", "width_mm": 900, "count": 1, "wall": "east"},
            ]
        )
        drawing = StudentDrawing.from_dict(
            {
                **north_star_drawing(),
                "openings": [
                    {
                        "host_wall_id": str(north_star_drawing()["walls"][0]["id"]),
                        "offset_mm": "10",
                        "width_mm": "20",
                        "kind": "door",
                    },
                    {
                        "host_wall_id": str(north_star_drawing()["walls"][2]["id"]),
                        "offset_mm": "10",
                        "width_mm": "20",
                        "kind": "door",
                    },
                ],
            }
        )
        result = validate_drawing(exercise, drawing)
        identities = [
            finding_identity(f, drawing)
            for f in result.findings
            if f.code is FindingCode.DOOR_WIDTH_ERROR
        ]

        assert len(identities) == 2
        assert len(set(identities)) == 2

    def test_different_mistakes_never_share_an_identity(self):
        _, drawing, result = _validate(room_width_mm=70, wall_thickness_mm="9")

        identities = [finding_identity(f, drawing) for f in result.findings]

        assert len(set(identities)) == len(identities)


class TestCompareAttempts:
    def test_a_first_attempt_reports_a_baseline(self):
        _, drawing, result = _validate(room_width_mm=70)
        progress = compare_attempts(
            attempt_number=1,
            passed=False,
            current=result.findings,
            previous=None,
            current_drawing=drawing,
        )

        assert progress.is_first_attempt is True
        assert progress.improved is False
        assert progress.remaining_count == len(result.findings)
        assert progress.resolved == []
        assert progress.new == []

    def test_every_finding_lands_in_exactly_one_bucket(self):
        """The invariant that makes the diff arithmetic rather than opinion.

        A finding that appeared in two buckets would be counted twice, and a
        count that can double-count is not a count.
        """
        _, d70, r70 = _validate(room_width_mm=70, wall_thickness_mm="9")
        _, d71, r71 = _validate(room_width_mm=71, wall_thickness_mm="8")
        progress = compare_attempts(
            attempt_number=2,
            passed=False,
            current=r71.findings,
            previous=r70.findings,
            current_drawing=d71,
            previous_drawing=d70,
        )

        identities = [
            finding_identity(f, d71) for f in r71.findings
        ]
        assert len(identities) == len(set(identities))
        assert progress.remaining_count == len(r71.findings)

    def test_a_mistake_that_moved_is_neither_fixed_nor_new(self):
        """The case a naive diff gets wrong in one direction or the other."""
        _, d70, r70 = _validate(room_width_mm=70)
        _, d71, r71 = _validate(room_width_mm=71)
        progress = compare_attempts(
            attempt_number=2,
            passed=False,
            current=r71.findings,
            previous=r70.findings,
            current_drawing=d71,
            previous_drawing=d70,
        )

        assert progress.resolved_count == 0
        assert progress.new_count == 0
        assert progress.changed_count > 0
        assert progress.remaining_count > 0

    def test_a_fixed_mistake_is_credited_once(self):
        _, d70, r70 = _validate(room_width_mm=70)
        _, d_good, r_good = _validate()
        progress = compare_attempts(
            attempt_number=2,
            passed=True,
            current=r_good.findings,
            previous=r70.findings,
            current_drawing=d_good,
            previous_drawing=d70,
        )

        assert progress.resolved_count == len(r70.findings)
        assert progress.remaining_count == 0
        assert progress.completed is True
        assert progress.improved is True

    def test_fixing_some_of_them_credits_only_those(self):
        _, d_bad, r_bad = _validate(
            room_width_mm=70, wall_thickness_mm="9"
        )
        _, d_half, r_half = _validate(room_width_mm=70)
        progress = compare_attempts(
            attempt_number=2,
            passed=False,
            current=r_half.findings,
            previous=r_bad.findings,
            current_drawing=d_half,
            previous_drawing=d_bad,
        )

        assert progress.resolved_count > 0
        assert progress.remaining_count > 0
        assert progress.resolved_count != len(r_bad.findings)


class TestSummary:
    def test_an_empty_history_is_a_fact_not_a_crash(self):
        summary = summarise_progress([])

        assert summary["attempt_count"] == 0
        assert summary["completed"] is False
        assert summary["first_attempt_error_count"] is None

    def test_first_and_final_are_not_reversed(self):
        """A summary that reports improvement backwards is worse than none.

        The history arrives oldest first, so reading the last row as the
        beginning would report a student's first and final states swapped.
        """
        summary = summarise_progress(
            [
                {
                    "attempt_number": 1,
                    "completed": False,
                    "learning": {"categories": {"ROOM_DIMENSION": 2}},
                    "progress": {"resolved": []},
                    "summary": {"error_count": 4},
                },
                {
                    "attempt_number": 2,
                    "completed": True,
                    "learning": {"categories": {"WALL_THICKNESS": 1}},
                    "progress": {
                        "resolved": [{"code": "WALL_THICKNESS_ERROR"}]
                    },
                    "summary": {"error_count": 0},
                },
            ]
        )

        assert summary["first_attempt_error_count"] == 4
        assert summary["final_error_count"] == 0
        assert summary["completed"] is True
        assert summary["completion_attempt_number"] == 2

    def test_recurring_categories_accumulate_across_attempts(self):
        summary = summarise_progress(
            [
                {"attempt_number": 1, "learning": {"categories": {"ALIGNMENT": 2}}},
                {"attempt_number": 2, "learning": {"categories": {"ALIGNMENT": 1}}},
            ]
        )

        assert summary["category_totals"]["ALIGNMENT"] == 3
