"""Authoring and retrieving exercises.

An exercise is a brief. This module builds and stores briefs and hands them to
the validator as input. It never decides whether a submission is correct --
that authority belongs to :mod:`app.validation` alone, so that a brief can
never grade its own homework.

Exercises are **authored, not generated**. There is no adaptive generation, and
adding one would mean a brief whose difficulty depends on a student, which
would make "the same drawing is wrong for the same reason" untrue.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.exercise import Exercise
from app.schemas.exercise import (
    DimensionRequirement,
    ExerciseCreate,
    ExerciseRead,
    OpeningRequirement,
)


def list_exercises(
    db: Session, *, limit: int = 50, offset: int = 0
) -> tuple[list[ExerciseRead], int]:
    """Paginated exercises, oldest first so seeded content keeps a stable order."""
    total = db.execute(select(func.count()).select_from(Exercise)).scalar_one()
    rows = (
        db.execute(
            select(Exercise).order_by(Exercise.created_at).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return [ExerciseRead.model_validate(row) for row in rows], total


def get_exercise(db: Session, exercise_id: uuid.UUID) -> ExerciseRead | None:
    """One exercise as a domain object, or ``None``."""
    row = db.get(Exercise, exercise_id)
    return ExerciseRead.model_validate(row) if row is not None else None


def lock_exercise(db: Session, exercise_id: uuid.UUID) -> Exercise | None:
    """Take a row lock on the exercise, and return the row.

    Serialises attempt numbering per exercise. The lock belongs on the exercise
    rather than on the most recent attempt because the exercise always exists:
    locking the attempt row leaves the very first submission of an exercise
    completely unlocked, so two students racing each other on a new exercise
    would both be numbered 1.
    """
    return db.execute(
        select(Exercise)
        .where(Exercise.id == exercise_id)
        .with_for_update()
    ).scalar_one_or_none()


def get_by_slug(db: Session, slug: str) -> ExerciseRead | None:
    row = db.execute(select(Exercise).where(Exercise.slug == slug)).scalar_one_or_none()
    return ExerciseRead.model_validate(row) if row is not None else None


def get_many(db: Session, slugs: Sequence[str]) -> list[ExerciseRead]:
    rows = (
        db.execute(select(Exercise).where(Exercise.slug.in_(list(slugs))))
        .scalars()
        .all()
    )
    by_slug = {row.slug: row for row in rows}
    return [
        ExerciseRead.model_validate(by_slug[slug]) for slug in slugs if slug in by_slug
    ]


def create_exercise(db: Session, payload: ExerciseCreate) -> ExerciseRead:
    """Persist a new brief. The slug is unique, so a duplicate is a real error."""
    exercise = Exercise(**payload.model_dump(mode="json"))
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return ExerciseRead.model_validate(exercise)


def upsert_exercise(db: Session, payload: ExerciseCreate) -> ExerciseRead:
    """Create or replace by slug. Used by the seed script so it is re-runnable."""
    row = db.execute(
        select(Exercise).where(Exercise.slug == payload.slug)
    ).scalar_one_or_none()
    if row is None:
        return create_exercise(db, payload)
    for field, value in payload.model_dump(mode="json").items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return ExerciseRead.model_validate(row)
