"""Tests for the exercise engine.

An exercise is a brief, and its only job is to be an unambiguous input to the
validator. These tests therefore care about three things: that a brief round-trips
through the database unchanged, that its requirements survive that trip, and that
the shipped seed data is realistic enough to teach from.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.exercises import repository
from app.geometry.drawing import StudentDrawing
from app.models.exercise import Difficulty
from app.schemas.exercise import (
    DimensionRequirement,
    ExerciseCreate,
    ExerciseRead,
    OpeningRequirement,
)
from app.validation import validate_drawing
from app.validation.codes import FindingCode
from scripts.seed_dev_exercises import ALL_EXERCISES
from tests.factories import correct_drawing_for, north_star_exercise_payload

VALID_PAYLOAD = north_star_exercise_payload()


@pytest.fixture(scope="module")
def seeds() -> list[ExerciseCreate]:
    return [builder() for builder in ALL_EXERCISES]


def _payload(**overrides) -> dict:
    return {**VALID_PAYLOAD, **overrides}


class TestExerciseSchema:
    def test_a_minimal_brief_is_accepted(self):
        exercise = ExerciseCreate.model_validate(
            _payload(
                door_requirements=[],
                window_requirements=[],
                dimension_requirements=[],
            )
        )

        assert exercise.difficulty is Difficulty.BEGINNER

    @pytest.mark.parametrize("field", ["room_width_mm", "room_height_mm", "wall_thickness_mm"])
    def test_zero_dimensions_are_rejected(self, field):
        """A room with no width is not a room, and a zero would divide by scale."""
        with pytest.raises(ValidationError):
            ExerciseCreate.model_validate(_payload(**{field: 0}))

    def test_negative_dimensions_are_rejected(self):
        with pytest.raises(ValidationError):
            ExerciseCreate.model_validate(_payload(room_width_mm=-100))

    def test_a_scale_of_one_is_rejected(self):
        """1:1 is not a drawing brief, and 1:0 would be a division by zero."""
        with pytest.raises(ValidationError):
            ExerciseCreate.model_validate(_payload(scale_denominator=1))

    def test_unknown_fields_are_rejected(self):
        """Silently dropping a requirement would produce a brief that under-tests."""
        with pytest.raises(ValidationError):
            ExerciseCreate.model_validate(_payload(wall_heights_mm=[3000]))

    def test_an_unknown_wall_side_is_rejected(self):
        with pytest.raises(ValidationError):
            OpeningRequirement(kind="door", width_mm=800, wall="upstairs")

    def test_an_unknown_opening_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            OpeningRequirement(kind="hatch", width_mm=800)

    def test_dimension_axis_is_restricted(self):
        with pytest.raises(ValidationError):
            DimensionRequirement(axis="depth", value_mm=3600)

    def test_opening_width_must_be_positive(self):
        with pytest.raises(ValidationError):
            OpeningRequirement(kind="door", width_mm=0)

    def test_opening_count_must_be_at_least_one(self):
        """A requirement for zero doors is expressed by omitting it entirely."""
        with pytest.raises(ValidationError):
            OpeningRequirement(kind="door", width_mm=800, count=0)


class TestExercisePersistence:
    def test_create_then_read_round_trips(self, db):
        created = repository.create_exercise(
            db, ExerciseCreate.model_validate(VALID_PAYLOAD)
        )

        loaded = repository.get_exercise(db, created.id)

        assert loaded is not None
        assert loaded.slug == created.slug
        assert loaded.room_width_mm == 4200
        assert loaded.scale_denominator == 50

    def test_requirements_survive_the_jsonb_round_trip(self, db):
        created = repository.create_exercise(
            db, ExerciseCreate.model_validate(VALID_PAYLOAD)
        )
        loaded = repository.get_exercise(db, created.id)

        assert loaded.door_requirements == [
            OpeningRequirement(kind="door", width_mm=900, count=1, wall="south")
        ]
        assert loaded.dimension_requirements == [
            DimensionRequirement(axis="width", value_mm=4200, on_wall="south")
        ]

    def test_window_requirements_round_trip(self, db):
        created = repository.create_exercise(
            db,
            ExerciseCreate.model_validate(
                _payload(
                    window_requirements=[
                        {
                            "kind": "window",
                            "width_mm": 1500,
                            "count": 2,
                            "wall": "north",
                            "sill_height_mm": 900,
                        }
                    ]
                )
            ),
        )
        loaded = repository.get_exercise(db, created.id)

        window = loaded.window_requirements[0]
        assert window.count == 2
        assert window.wall == "north"
        assert window.sill_height_mm == 900

    def test_duplicate_slug_is_rejected(self, db):
        repository.create_exercise(db, ExerciseCreate.model_validate(VALID_PAYLOAD))

        with pytest.raises(IntegrityError):
            repository.create_exercise(
                db, ExerciseCreate.model_validate(_payload(title="Copy"))
            )
        db.rollback()

    def test_missing_exercise_is_none_not_an_exception(self, db):
        import uuid

        assert repository.get_exercise(db, uuid.uuid4()) is None

    def test_listing_reports_a_total(self, db):
        repository.create_exercise(db, ExerciseCreate.model_validate(VALID_PAYLOAD))
        repository.create_exercise(
            db, ExerciseCreate.model_validate(_payload(slug="second-4200x3600-1-50"))
        )

        items, total = repository.list_exercises(db)

        assert len(items) == 2
        assert total == 2

    def test_upsert_is_idempotent(self, db):
        """The seed script runs on every setup, so re-running must not duplicate."""
        first = repository.upsert_exercise(
            db, ExerciseCreate.model_validate(VALID_PAYLOAD)
        )
        second = repository.upsert_exercise(
            db, ExerciseCreate.model_validate(_payload(title="Renamed"))
        )

        assert first.id == second.id
        assert repository.list_exercises(db)[1] == 1
        assert repository.get_exercise(db, second.id).title == "Renamed"

    def test_lookup_by_slug(self, db):
        repository.create_exercise(db, ExerciseCreate.model_validate(VALID_PAYLOAD))

        found = repository.get_by_slug(db, VALID_PAYLOAD["slug"])

        assert found is not None
        assert found.room_width_mm == 4200


class TestSeedData:
    """The shipped briefs are teaching material, so they are held to a standard."""

    def test_at_least_five_beginner_exercises_are_shipped(self, seeds):
        """One exercise is not a curriculum; a student needs something to graduate to."""
        assert len(seeds) >= 5

    def test_every_seed_is_beginner(self, seeds):
        assert all(seed.difficulty is Difficulty.BEGINNER for seed in seeds)

    def test_slugs_are_unique(self, seeds):
        slugs = [seed.slug for seed in seeds]
        assert len(set(slugs)) == len(slugs)

    def test_the_curriculum_is_big_enough_to_practise(self, seeds):
        """A student needs somewhere to graduate to.

        Twenty briefs across four scales and rooms from 2100 to 7200 mm wide is
        enough range to expose a student to the mistake classes below without
        pretending to be a full course.
        """
        assert len(seeds) >= 20, "the brief asked for at least 20 exercises"

    def test_a_slug_that_advertises_dimensions_matches_them(self, seeds):
        """The slug is the URL and the student's first sanity check.

        A ``pantry-2100x1800`` slug on a 2100 x 2400 room is worse than no
        slug: it makes the listing and the brief disagree, and the student has
        no way to tell which one the app believes.
        """
        for seed in seeds:
            match = re.search(r"(\\d+)x(\\d+)", seed.slug)
            if not match:
                continue
            assert int(match.group(1)) == seed.room_width_mm, seed.slug
            assert int(match.group(2)) == seed.room_height_mm, seed.slug

    def test_room_dimensions_are_plausible(self, seeds):
        """Between 2 m and 10 m on both axes.

        Anything outside that is not a room a student will ever be asked to
        draft, and training on it teaches nothing transferable.
        """
        for seed in seeds:
            assert 2000 <= seed.room_width_mm <= 10000, seed.slug
            assert 2000 <= seed.room_height_mm <= 10000, seed.slug

    def test_room_dimensions_are_round_numbers(self, seeds):
        """A student must be able to divide by the scale in their head.

        4371 mm at 1:50 is 87.42 mm, and no student can check that. 4200 gives
        84, which they can. Wall thickness is exempt: 115 is a real partition
        and is pinned separately.
        """
        for seed in seeds:
            assert seed.room_width_mm % 100 == 0, seed.slug
            assert seed.room_height_mm % 100 == 0, seed.slug

    def test_every_opening_width_is_a_real_manufactured_width(self, seeds):
        standard = {600, 800, 900, 1000, 1200, 1500, 1800, 2400}
        for seed in seeds:
            for requirement in (*seed.door_requirements, *seed.window_requirements):
                assert requirement.width_mm in standard, seed.slug

    def test_wall_thicknesses_are_real_constructions(self, seeds):
        """100/115 light partitions, 200/230 masonry. Nothing in between."""
        assert {seed.wall_thickness_mm for seed in seeds} <= {100, 115, 200, 230}

    def test_scales_cover_more_than_one_value(self, seeds):
        """A student who only ever draws 1:50 has not practised choosing a scale."""
        assert len({seed.scale_denominator for seed in seeds}) >= 3

    def test_every_dimension_requirement_names_a_required_room_axis(self, seeds):
        for seed in seeds:
            for requirement in seed.dimension_requirements:
                expected = (
                    seed.room_width_mm
                    if requirement.axis == "width"
                    else seed.room_height_mm
                )
                assert requirement.value_mm == expected, seed.slug

    def test_every_opening_fits_on_its_wall(self, seeds):
        """A brief that demands an impossible door is worse than no brief."""
        for seed in seeds:
            for requirement in (*seed.door_requirements, *seed.window_requirements):
                if requirement.wall in ("north", "south"):
                    length = seed.room_width_mm
                elif requirement.wall in ("east", "west"):
                    length = seed.room_height_mm
                else:
                    continue
                assert requirement.width_mm * requirement.count <= length, seed.slug

    def test_seeds_are_storable(self, db, seeds):
        """Each seed must survive an actual insert, not just validation."""
        for seed in seeds:
            repository.upsert_exercise(db, seed)

        items, total = repository.list_exercises(db)

        assert total == len(seeds)
        assert {item.slug for item in items} == {seed.slug for seed in seeds}


class TestSeedsAreSatisfiable:
    """A brief no drawing can satisfy is indistinguishable from a stuck student.

    The validator would report findings that no amount of correct work could
    clear, and the student would have no way to tell that from their own mistake.
    """

    @pytest.mark.parametrize("builder", ALL_EXERCISES, ids=lambda b: b.__name__)
    def test_a_correct_drawing_passes_the_brief(self, builder):
        seed = builder()
        exercise = ExerciseRead.model_validate(
            {**seed.model_dump(mode="json"), "id": "00000000-0000-0000-0000-0000000000ff",
             "created_at": "2026-01-01T00:00:00+00:00"}
        )

        result = validate_drawing(
            exercise, StudentDrawing.from_dict(correct_drawing_for(exercise))
        )

        assert result.passed is True, [f.message for f in result.findings]
        assert result.findings == ()

    @pytest.mark.parametrize("builder", ALL_EXERCISES, ids=lambda b: b.__name__)
    def test_a_drawing_at_the_wrong_scale_fails_the_brief(self, builder):
        """Every brief must be capable of catching the mistake it exists to catch."""
        seed = builder()
        exercise = ExerciseRead.model_validate(
            {**seed.model_dump(mode="json"), "id": "00000000-0000-0000-0000-0000000000ff",
             "created_at": "2026-01-01T00:00:00+00:00"}
        )
        drawing = correct_drawing_for(exercise)
        # Relabel the same sheet at half the scale it was drawn to.
        drawing["scale_denominator"] = seed.scale_denominator * 2

        result = validate_drawing(exercise, StudentDrawing.from_dict(drawing))

        assert result.passed is False
        assert FindingCode.SCALE_ERROR in {f.code for f in result.findings}
