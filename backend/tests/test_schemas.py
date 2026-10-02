"""Exercise schema tests: the JSONB payload shape has a single owner."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.exercise import ExerciseCreate, OpeningRequirement


class TestOpeningRequirement:
    def test_a_door_requirement_carries_width_and_host_wall(self):
        req = OpeningRequirement(kind="door", width_mm=900, count=1, wall="north")
        assert req.kind == "door"
        assert req.width_mm == 900
        assert req.wall == "north"

    def test_count_defaults_to_one(self):
        assert OpeningRequirement(kind="window", width_mm=1200).count == 1

    def test_a_window_may_declare_a_sill_height(self):
        req = OpeningRequirement(kind="window", width_mm=1500, sill_height_mm=900)
        assert req.sill_height_mm == 900

    @pytest.mark.parametrize("bad_width", [0, -900])
    def test_non_positive_width_is_rejected(self, bad_width):
        with pytest.raises(ValidationError):
            OpeningRequirement(kind="door", width_mm=bad_width)

    def test_unknown_field_is_rejected_rather_than_silently_dropped(self):
        # Silently ignoring an unrecognised requirement would let an exercise
        # author ship a door spec that is never validated.
        with pytest.raises(ValidationError):
            OpeningRequirement(kind="door", width_mm=900, colour="red")


class TestExerciseCreate:
    def _valid_payload(self) -> dict:
        return {
            "slug": "room-4200x3600-1-50",
            "title": "Room at 1:50",
            "room_width_mm": 4200,
            "room_height_mm": 3600,
            "wall_thickness_mm": 230,
            "scale_denominator": 50,
        }

    def test_a_minimal_valid_exercise(self):
        exercise = ExerciseCreate(**self._valid_payload())
        assert exercise.room_width_mm == 4200
        assert exercise.scale_denominator == 50
        assert exercise.door_requirements == []
        assert exercise.window_requirements == []

    @pytest.mark.parametrize("field", ["room_width_mm", "room_height_mm", "wall_thickness_mm"])
    def test_non_positive_dimensions_are_rejected(self, field):
        payload = self._valid_payload()
        payload[field] = 0
        with pytest.raises(ValidationError):
            ExerciseCreate(**payload)

    def test_scale_denominator_must_be_above_one(self):
        payload = self._valid_payload()
        payload["scale_denominator"] = 1
        with pytest.raises(ValidationError):
            ExerciseCreate(**payload)

    def test_uncommon_scale_is_accepted(self):
        payload = self._valid_payload()
        payload["scale_denominator"] = 137
        assert ExerciseCreate(**payload).scale_denominator == 137

    def test_payload_round_trips_through_json_for_jsonb_storage(self):
        exercise = ExerciseCreate(**self._valid_payload())
        dumped = exercise.model_dump(mode="json")
        assert ExerciseCreate(**dumped) == exercise
