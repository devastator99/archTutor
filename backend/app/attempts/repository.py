"""Persistence for attempts.

An attempt stores what the student drew, what the engine said about it, and what
changed since the attempt before. The geometry is never rewritten after
validation: if the stored drawing and the stored result ever disagreed, one of
them would be a lie, and the result is the part that must be defensible.

ATTEMPT NUMBERING IS SERIALISED BY THE CALLER
---------------------------------------------
``attempt_number`` is allocated by the route under a row lock on the exercise,
so two concurrent submissions cannot both be told they are attempt 3. The unique
index on ``(exercise_id, attempt_number)`` is the backstop; the lock is what
turns a constraint violation into a correct answer instead of an error a student
sees at the worst possible moment.

This module therefore does not allocate numbers. Numbering is deliberately not
offered as a helper here: an unlocked read of the latest attempt cannot be made
safe by any function of its own, because the row it would need to lock does not
exist for the first attempt of an exercise. The lock belongs on a row that is
always there.

The lock is scoped to a single row and held across one read and one insert, so
this does not introduce a queue, a worker or a bottleneck. It is the smallest
mechanism that makes the number correct.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attempt import ExerciseAttempt

LEARNING_SCHEMA_VERSION = 1
"""Bump when the taxonomy or the progress shape changes meaning."""


def create_attempt(
    db: Session,
    *,
    exercise_id: uuid.UUID,
    student_geometry: dict[str, Any],
    validation_result: dict[str, Any],
    attempt_number: int,
    progress: dict[str, Any] | None = None,
    learning: dict[str, Any] | None = None,
    completed: bool = False,
    previous_attempt_id: uuid.UUID | None = None,
) -> ExerciseAttempt:
    attempt = ExerciseAttempt(
        exercise_id=exercise_id,
        student_geometry=student_geometry,
        validation_result=validation_result,
        attempt_number=attempt_number,
        progress=progress,
        learning=learning,
        learning_version=LEARNING_SCHEMA_VERSION,
        completed=completed,
        # The clock is started here rather than by the caller so the timestamp
        # cannot disagree with the flag beside it.
        completed_at=datetime.now(UTC) if completed else None,
        previous_attempt_id=previous_attempt_id,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def list_attempts(
    db: Session, exercise_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> list[ExerciseAttempt]:
    """Newest first: the most recent submission is the one being discussed."""
    return list(
        db.execute(
            select(ExerciseAttempt)
            .where(ExerciseAttempt.exercise_id == exercise_id)
            .order_by(ExerciseAttempt.submitted_at.desc(), ExerciseAttempt.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )


def get_attempt(db: Session, attempt_id: uuid.UUID) -> ExerciseAttempt | None:
    return db.get(ExerciseAttempt, attempt_id)


def latest_attempt(
    db: Session, exercise_id: uuid.UUID
) -> ExerciseAttempt | None:
    """The attempt a new submission should be compared against."""
    return db.execute(
        select(ExerciseAttempt)
        .where(ExerciseAttempt.exercise_id == exercise_id)
        .order_by(ExerciseAttempt.attempt_number.desc())
        .limit(1)
    ).scalar_one_or_none()


def attempt_history(
    db: Session, exercise_id: uuid.UUID, *, limit: int = 200
) -> list[dict[str, Any]]:
    """Attempts oldest first, shaped for a learning summary."""
    rows = db.execute(
        select(ExerciseAttempt)
        .where(ExerciseAttempt.exercise_id == exercise_id)
        .order_by(ExerciseAttempt.attempt_number.asc())
        .limit(limit)
    ).scalars()

    return [
        {
            "attempt_number": row.attempt_number,
            "completed": row.completed,
            "summary": (row.validation_result or {}).get("summary", {}),
            "learning": row.learning or {},
            "progress": row.progress or {},
        }
        for row in rows
    ]
