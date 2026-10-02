"""API contract tests.

These pin the shape of the HTTP surface and the database contract, so the next
milestone cannot quietly change them.

The validate/attempt tests matter more than their size suggests. An endpoint that
returned ``passed: true`` for a drawing it never understood would tell a student
their work was correct; the tests below therefore cover malformed input, unknown
exercises and round-tripped storage as carefully as the happy path.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.attempt import ExerciseAttempt
from app.models.exercise import Difficulty, Exercise
from app.schemas.exercise import ExerciseCreate, OpeningRequirement
from tests.factories import north_star_drawing, north_star_exercise_payload


def _seed_exercise(db) -> Exercise:
    """The north-star exercise, seeded directly through the model."""
    exercise = Exercise(
        slug="room-4200x3600-1-50",
        title="Draw a 4200 x 3600 mm room at 1:50 with 230 mm walls and a 900 mm door",
        description=(
            "Draw a 4200 x 3600 mm room at 1:50. Use 230 mm walls. Add a 900 mm door."
        ),
        room_width_mm=4200,
        room_height_mm=3600,
        wall_thickness_mm=230,
        scale_denominator=50,
        door_requirements=[
            OpeningRequirement(kind="door", width_mm=900, count=1, wall="south").model_dump(
                mode="json"
            )
        ],
        window_requirements=[],
        dimension_requirements=[
            {"axis": "width", "value_mm": 4200, "on_wall": "south"}
        ],
        difficulty=Difficulty.BEGINNER,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def _client_with_broken_route(db):
    """A client with one route that raises, to exercise the generic handler.

    The route is added directly to the app, after it has been created, so the
    failure happens inside a real request travelling through the real
    middleware stack. Mocking a repository instead would only prove that the
    mock raises.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    @app.get("/__broken", include_in_schema=False)
    def _boom() -> None:
        raise RuntimeError("a secret-looking internal detail: /Users/someone/app/x.py")

    return TestClient(app, raise_server_exceptions=False)


class TestHealth:
    def test_health_reports_ok_with_a_reachable_database(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"

    def test_health_reports_degraded_when_the_database_is_down(self, db):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.session import get_db
        from app.main import create_app

        # Point at a closed port so the failure happens on execute(), inside the
        # route, rather than while resolving the dependency. A dependency that
        # raises would bypass the route entirely and test nothing.
        dead_engine = create_engine(
            "postgresql+psycopg://nobody:nobody@127.0.0.1:1/absent",
            pool_pre_ping=True,
            connect_args={"connect_timeout": 1},
        )
        dead_session = sessionmaker(bind=dead_engine, expire_on_commit=False)()

        app = create_app()
        app.dependency_overrides[get_db] = lambda: dead_session
        with TestClient(app) as client:
            response = client.get("/health")
        app.dependency_overrides.clear()
        dead_session.close()
        dead_engine.dispose()

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["database"] == "unavailable"


class TestExerciseEndpoints:
    def test_list_exercises_is_empty_on_a_fresh_database(self, client):
        response = client.get("/exercises")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_get_exercise_returns_the_stored_specification(self, client, db):
        exercise = _seed_exercise(db)
        response = client.get(f"/exercises/{exercise.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["room_width_mm"] == 4200
        assert body["room_height_mm"] == 3600
        assert body["wall_thickness_mm"] == 230
        assert body["scale_denominator"] == 50
        assert body["door_requirements"][0]["width_mm"] == 900

    def test_get_exercise_returns_404_for_an_unknown_id(self, client):
        response = client.get(f"/exercises/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_exercise_rejects_a_malformed_uuid(self, client):
        response = client.get("/exercises/not-a-uuid")
        assert response.status_code == 422


class TestExercisePersistence:
    def test_an_exercise_round_trips_through_postgres(self, db):
        created = _seed_exercise(db)
        db.expire_all()
        loaded = db.get(Exercise, created.id)
        assert loaded is not None
        assert loaded.room_width_mm == 4200
        assert loaded.door_requirements[0]["kind"] == "door"
        assert loaded.difficulty is Difficulty.BEGINNER

    def test_difficulty_is_stored_as_its_lowercase_value(self, db):
        # Regression: SQLAlchemy's Enum persists the member NAME by default,
        # which would store "BEGINNER" while the API contract says "beginner".
        _seed_exercise(db)
        raw = db.execute(text("SELECT difficulty FROM exercises")).scalar_one()
        assert raw == "beginner"

    def test_a_non_positive_dimension_is_rejected_by_the_database(self, db):
        db.add(
            Exercise(
                slug="bad",
                title="Bad",
                room_width_mm=0,
                room_height_mm=3600,
                wall_thickness_mm=230,
                scale_denominator=50,
                door_requirements=[],
                window_requirements=[],
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestValidationEndpoint:
    """``POST /exercises/{id}/validate`` -- grade without storing anything."""

    def test_a_correct_drawing_passes(self, client, db):
        exercise = _seed_exercise(db)

        response = client.post(
            f"/exercises/{exercise.id}/validate",
            json={"geometry": north_star_drawing()},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["passed"] is True
        assert body["findings"] == []
        assert body["summary"]["total"] == 0
        assert body["exercise_id"] == str(exercise.id)

    def test_a_wrong_drawing_returns_structured_findings(self, client, db):
        exercise = _seed_exercise(db)

        response = client.post(
            f"/exercises/{exercise.id}/validate",
            json={"geometry": north_star_drawing(room_width_mm=70)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["passed"] is False
        codes = {f["code"] for f in body["findings"]}
        assert "ROOM_DIMENSION_ERROR" in codes
        assert body["summary"]["codes"]["ROOM_DIMENSION_ERROR"] == 1
        assert body["summary"]["error_count"] == len(body["findings"])

    def test_a_check_teaches_as_well_as_reports(self, client, db):
        """A student who only checks must not learn less than one who submits.

        The dry run returns the learning layer's issues beside the raw findings,
        so the help on screen does not depend on whether the attempt was stored.
        """
        exercise = _seed_exercise(db)

        body = client.post(
            f"/exercises/{exercise.id}/validate",
            json={"geometry": north_star_drawing(room_width_mm=70, door_width_mm=25)},
        ).json()

        assert len(body["issues"]) == len(body["findings"])
        for issue in body["issues"]:
            assert issue["what_is_wrong"]
            assert issue["where"]
            assert issue["why_it_matters"]
            assert issue["how_to_fix"]
            assert issue["category_label"]

    def test_a_check_says_the_same_thing_as_the_attempt_it_previews(self, client, db):
        """The same drawing must not be explained twice in two different ways.

        This is the invariant that keeps a student from being shown one location
        while checking and a vaguer one after submitting: the stored finding has
        to carry enough of the drawing's structure in its metadata to name the
        thing it is about without the drawing itself.
        """
        exercise = _seed_exercise(db)
        payload = {"geometry": north_star_drawing(room_width_mm=70, door_width_mm=25)}

        dry_run = client.post(f"/exercises/{exercise.id}/validate", json=payload).json()
        stored = client.post(
            f"/exercises/{exercise.id}/attempts", json=payload
        ).json()

        compared = (
            "code",
            "category",
            "category_label",
            "severity",
            "what_is_wrong",
            "where",
            "expected",
            "actual",
            "difference",
            "unit",
            "why_it_matters",
            "how_to_fix",
            "geometry_reference",
        )
        assert [tuple(issue[key] for key in compared) for issue in dry_run["issues"]] == [
            tuple(issue[key] for key in compared)
            for issue in stored["progress"]["remaining"]
        ]
        assert dry_run["findings"] == stored["validation_result"]["findings"]

    def test_finding_codes_are_upper_case_on_the_wire(self, client, db):
        exercise = _seed_exercise(db)

        body = client.post(
            f"/exercises/{exercise.id}/validate",
            json={"geometry": north_star_drawing(wall_thickness_mm=9)},
        ).json()

        assert body["findings"]
        for finding in body["findings"]:
            assert finding["code"] == finding["code"].upper()
            assert finding["severity"] == "ERROR"

    def test_a_malformed_drawing_is_422_not_a_verdict(self, client, db):
        """The most important assertion here.

        A drawing the parser cannot read has no verdict. Reporting ``passed``
        would tell a student their work is correct when the server never
        understood it.
        """
        exercise = _seed_exercise(db)
        payload = north_star_drawing()
        del payload["walls"][0]["id"]

        response = client.post(
            f"/exercises/{exercise.id}/validate", json={"geometry": payload}
        )

        assert response.status_code == 422
        assert "id" in response.json()["detail"]

    def test_an_empty_geometry_object_is_422(self, client, db):
        exercise = _seed_exercise(db)

        response = client.post(
            f"/exercises/{exercise.id}/validate", json={"geometry": {}}
        )

        assert response.status_code == 422

    def test_validation_stores_nothing(self, client, db):
        exercise = _seed_exercise(db)

        client.post(
            f"/exercises/{exercise.id}/validate",
            json={"geometry": north_star_drawing()},
        )

        assert client.get(f"/exercises/{exercise.id}/attempts").json() == []

    def test_an_unknown_exercise_is_404(self, client):
        response = client.post(
            f"/exercises/{uuid.uuid4()}/validate",
            json={"geometry": north_star_drawing()},
        )
        assert response.status_code == 404

    def test_tolerance_is_echoed_back(self, client, db):
        exercise = _seed_exercise(db)

        body = client.post(
            f"/exercises/{exercise.id}/validate",
            json={
                "geometry": north_star_drawing(wall_thickness_mm=6),
                "tolerance": {"wall_thickness_mm": 5},
            },
        ).json()

        assert body["passed"] is True
        assert body["tolerance"]["wall_thickness_mm"] == "5"

    def test_a_misspelled_tolerance_field_is_422(self, client, db):
        """Honouring neither a typo nor its correction would silently re-tighten."""
        exercise = _seed_exercise(db)

        response = client.post(
            f"/exercises/{exercise.id}/validate",
            json={
                "geometry": north_star_drawing(),
                "tolerance": {"wall_thickness": 5},
            },
        )

        assert response.status_code == 422

    def test_a_negative_tolerance_is_422(self, client, db):
        exercise = _seed_exercise(db)

        response = client.post(
            f"/exercises/{exercise.id}/validate",
            json={
                "geometry": north_star_drawing(),
                "tolerance": {"wall_thickness_mm": -1},
            },
        )

        assert response.status_code == 422

    def test_repeated_calls_return_an_identical_body(self, client, db):
        """Same request, same verdict -- byte for byte."""
        exercise = _seed_exercise(db)
        payload = {"geometry": north_star_drawing(room_width_mm=70, door_width_mm=25)}

        first = client.post(f"/exercises/{exercise.id}/validate", json=payload).json()
        second = client.post(f"/exercises/{exercise.id}/validate", json=payload).json()

        assert first == second


class TestAttemptEndpoint:
    """``POST /exercises/{id}/attempts`` -- grade and store."""

    def test_an_attempt_is_created_with_its_result(self, client, db):
        exercise = _seed_exercise(db)

        response = client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing()},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["exercise_id"] == str(exercise.id)
        assert body["validation_result"]["passed"] is True
        assert body["validation_result"]["findings"] == []
        assert body["submitted_at"]

    def test_a_retry_reports_which_mistakes_were_fixed(self, client, db):
        """The whole point of storing attempts: the second answer is a diff.

        The retry loop depends on this being right, so it is checked end to end
        through the API rather than against the diff function alone.
        """
        exercise = _seed_exercise(db)
        base = f"/exercises/{exercise.id}/attempts"

        first = client.post(base, json={"geometry": north_star_drawing()})
        assert first.status_code == 201
        assert first.json()["progress"]["is_first_attempt"] is True
        assert first.json()["progress"]["remaining_count"] == 0

        second = client.post(
            base, json={"geometry": north_star_drawing(room_width_mm=70)}
        )
        assert second.status_code == 201
        body = second.json()
        assert body["attempt_number"] == 2
        assert body["previous_attempt_id"] == first.json()["id"]
        assert body["progress"]["remaining_count"] > 0
        assert body["progress"]["new_count"] == body["progress"]["remaining_count"]

        third = client.post(base, json={"geometry": north_star_drawing()})
        body = third.json()
        assert body["progress"]["remaining_count"] == 0
        assert body["progress"]["resolved_count"] == second.json()["progress"][
            "remaining_count"
        ]
        assert body["progress"]["new_count"] == 0
        assert body["completed"] is True
        assert body["completed_at"] is not None

    def test_a_mistake_that_moved_is_not_reported_as_fixed(self, client, db):
        """Nudging a still-wrong value is neither progress nor a fresh mistake.

        A diff keyed on the numbers alone would call this resolved; a diff keyed
        on identity alone would call it unchanged. Either way the student is told
        something false about their own work.
        """
        exercise = _seed_exercise(db)
        base = f"/exercises/{exercise.id}/attempts"

        client.post(base, json={"geometry": north_star_drawing(room_width_mm=70)})
        second = client.post(
            base, json={"geometry": north_star_drawing(room_width_mm=71)}
        )
        progress = second.json()["progress"]

        assert progress["remaining_count"] > 0
        assert progress["resolved_count"] == 0
        assert progress["new_count"] == 0
        assert progress["changed_count"] > 0

    def test_the_response_never_leaks_internal_detail_on_failure(self, client, db):
        """A student must not be handed a traceback or a path to the server.

        The generic handler has to stay generic: the correlation id is the only
        thing the client is given, and it has to be the same one the client sent
        so an operator can join the two records.
        """
        client = _client_with_broken_route(db)
        request_id = "test-correlation-id"
        response = client.get("/__broken", headers={"x-request-id": request_id})

        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "internal server error"
        assert body["request_id"] == request_id
        assert response.headers["x-request-id"] == request_id
        serialised = json.dumps(body)
        for leak in ("Traceback", "/Users/", "app/", "sqlalchemy", ".py"):
            assert leak not in serialised, leak

    def test_an_oversized_request_is_refused_before_it_is_parsed(self, client, db):
        """A student cannot make the server allocate whatever they like.

        Rejection happens on the declared length, so the body is never read and
        a hostile payload cannot become a memory problem first.
        """
        payload = {
            "geometry": north_star_drawing(),
            "padding": "x" * (512 * 1024 + 1),
        }

        response = client.post(
            f"/exercises/{uuid.UUID(int=0)}/attempts", json=payload
        )

        assert response.status_code == 413
        assert "large" in response.json()["detail"].lower()

    def test_fixing_one_of_two_mistakes_credits_only_that_one(self, client, db):
        """A partial fix has to read as a partial fix.

        The door moves to the right wall but stays too wide. The wall error is
        genuinely resolved; the width error is the same mistake as before with a
        different number, so it stays in remaining rather than being reported as
        both fixed and newly introduced.
        """
        exercise = _seed_exercise(db)
        base = f"/exercises/{exercise.id}/attempts"

        client.post(
            base,
            json={
                "geometry": north_star_drawing(door_width_mm=20, door_side="north")
            },
        )
        response = client.post(
            base,
            json={
                "geometry": north_star_drawing(door_width_mm=21, door_side="south")
            },
        )
        progress = response.json()["progress"]

        assert progress["remaining_count"] == 1
        assert progress["resolved_count"] == 1
        assert progress["changed_count"] == 1
        assert progress["new_count"] == 0

    def test_the_stored_geometry_is_the_students_own(self, client, db):
        """Not the exercise, and not a re-derived "corrected" version.

        The stored form is the canonical serialisation, so it carries the
        identifiers the parser derived, but every measurement is the student's.
        """
        exercise = _seed_exercise(db)
        drawing = north_star_drawing(room_width_mm=70)

        body = client.post(
            f"/exercises/{exercise.id}/attempts", json={"geometry": drawing}
        ).json()
        stored = body["student_geometry"]

        assert stored["scale_denominator"] == drawing["scale_denominator"]
        assert stored["room"] == drawing["room"]
        assert stored["walls"] == drawing["walls"]
        assert stored["dimensions"] == drawing["dimensions"]
        assert stored["openings"][0]["width_mm"] == "18"
        assert stored["openings"][0]["host_wall_id"] == (
            drawing["openings"][0]["host_wall_id"]
        )

    def test_a_derived_opening_id_is_stable_across_attempts(self, client, db):
        """Two identical submissions must reference openings identically.

        Findings quote ``geometry_reference`` values, so if the id moved between
        submissions a student could not match a finding to their own drawing.
        """
        exercise = _seed_exercise(db)
        payload = {"geometry": north_star_drawing(room_width_mm=70)}

        first = client.post(
            f"/exercises/{exercise.id}/attempts", json=payload
        ).json()
        second = client.post(
            f"/exercises/{exercise.id}/attempts", json=payload
        ).json()

        assert first["id"] != second["id"]
        assert (
            first["student_geometry"]["openings"][0]["id"]
            == second["student_geometry"]["openings"][0]["id"]
        )

    def test_millimetres_are_stored_as_exact_strings(self, client, db):
        """4.6 in a JSON number column would come back 4.5999999999999996."""
        exercise = _seed_exercise(db)

        body = client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing()},
        ).json()

        assert body["student_geometry"]["walls"][0]["thickness_mm"] == "4.6"

    def test_a_failed_attempt_is_stored_with_its_findings(self, client, db):
        exercise = _seed_exercise(db)

        body = client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing(room_width_mm=70)},
        ).json()

        assert body["validation_result"]["passed"] is False
        assert any(
            f["code"] == "ROOM_DIMENSION_ERROR"
            for f in body["validation_result"]["findings"]
        )

    def test_a_malformed_drawing_is_not_persisted(self, client, db):
        """No half-written attempt, and certainly no attempt claiming to pass."""
        exercise = _seed_exercise(db)
        payload = north_star_drawing()
        payload["scale_denominator"] = "half"

        response = client.post(
            f"/exercises/{exercise.id}/attempts", json={"geometry": payload}
        )

        assert response.status_code == 422
        assert client.get(f"/exercises/{exercise.id}/attempts").json() == []

    def test_attempts_are_listed_newest_first(self, client, db):
        exercise = _seed_exercise(db)
        client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing()},
        )
        client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing(room_width_mm=70)},
        )

        attempts = client.get(f"/exercises/{exercise.id}/attempts").json()

        assert len(attempts) == 2
        assert attempts[0]["validation_result"]["passed"] is False

    def test_attempts_survive_a_fresh_read_from_postgres(self, client, db):
        exercise = _seed_exercise(db)
        created = client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing()},
        ).json()
        db.expire_all()

        stored = db.get(ExerciseAttempt, uuid.UUID(created["id"]))

        assert stored is not None
        assert stored.student_geometry["scale_denominator"] == 50
        assert stored.validation_result["passed"] is True

    def test_an_unknown_exercise_is_404(self, client):
        response = client.post(
            f"/exercises/{uuid.uuid4()}/attempts",
            json={"geometry": north_star_drawing()},
        )
        assert response.status_code == 404

    def test_the_result_matches_the_dry_run_verbatim(self, client, db):
        """The stored verdict and the computed one must not differ.

        A student appealing against a stored result is judged against the bytes
        in this column, so it has to be the same object the engine produced.
        """
        exercise = _seed_exercise(db)
        payload = {"geometry": north_star_drawing(room_width_mm=70, door_width_mm=25)}

        dry_run = client.post(
            f"/exercises/{exercise.id}/validate", json=payload
        ).json()
        stored = client.post(
            f"/exercises/{exercise.id}/attempts", json=payload
        ).json()["validation_result"]

        assert stored["findings"] == dry_run["findings"]
        assert stored["summary"] == dry_run["summary"]
        assert stored["passed"] == dry_run["passed"]

    def test_the_summary_reports_the_concepts_a_pass_demonstrated(self, client, db):
        """The completion screen must not have to invent its own praise.

        Every concept in the summary is a requirement from the brief, so if the
        exercise is passed each of them is a fact the validator confirmed. The
        frontend renders this list verbatim after "Exercise complete." and
        nothing else.
        """
        exercise = _seed_exercise(db)
        client.post(
            f"/exercises/{exercise.id}/attempts",
            json={"geometry": north_star_drawing()},
        )

        summary = client.get(f"/exercises/{exercise.id}/summary").json()

        assert summary["completed"] is True
        assert summary["completion_attempt_number"] == 1
        concepts = summary["concepts"]
        assert any("1:50" in concept for concept in concepts)
        assert any("4200 x 3600" in concept for concept in concepts)
        assert any("230 mm walls" in concept for concept in concepts)
        assert any("900 mm door" in concept for concept in concepts)
        assert all(isinstance(concept, str) and concept for concept in concepts)
