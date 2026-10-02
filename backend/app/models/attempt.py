"""A single student's submission against an exercise.

    exercise_id, student_geometry, submitted_at, validation_result
    attempt_number, progress, learning, completed

``student_geometry`` is what the student actually drew, and it is the authority
on that. The validation engine reads it and compares; it never overwrites it,
and the exercise never overrides it. That ordering is the whole product: the
drawing is the evidence.

``validation_result`` is the deterministic engine's structured output, stored
verbatim as produced. It is not re-summarised or prettified on the way in, so
what is persisted is exactly what was computed -- reproducibility depends on
it.

THE LEARNING COLUMNS
---------------------
``progress`` and ``learning`` exist so that a student's history is countable
rather than merely readable. Without them, the only way to ask "does this student
confuse scales?" is to re-read every attempt's prose, and a database that can
only be read cannot inform anything.

    progress.remaining   the full current verdict
    progress.resolved    what this attempt fixed
    progress.new         what this attempt introduced
    learning.categories  {"SCALE_CONVERSION": 2, ...} mistake taxonomy counts

These are derived at write time and stored, rather than recomputed on read. That
is a deliberate trade: a stored derivation can go stale if the taxonomy is ever
redefined, so ``version`` is kept alongside them, and a reader that cares can
detect a mismatch instead of silently trusting a number computed under old rules.

A student may retry, so an attempt is one turn of the loop, not one pass/fail.
``attempt_number`` counts the loop, and ``completed`` records the moment it ended
in a clean verdict.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.exercise import Exercise


class ExerciseAttempt(Base):
    """One draw -> validate -> correct cycle."""

    __tablename__ = "exercise_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )

    student_geometry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_result: Mapped[dict | None] = mapped_column(JSONB)

    # --- The retry loop --------------------------------------------------
    # 1 for the first submission, 2 for the retry, and so on. Counted per
    # exercise, so two exercises attempted in parallel do not interfere.
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # The attempt this one is compared against. Nullable: the first attempt has
    # no predecessor, and claiming otherwise would invent a history.
    previous_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exercise_attempts.id", ondelete="SET NULL")
    )

    # resolved / remaining / new findings, as whole findings. Stored as the
    # engine's output so the diff can be read back without replaying validation,
    # which would require keeping every earlier drawing interpretable forever.
    progress: Mapped[dict | None] = mapped_column(JSONB)

    # Mistake taxonomy counts for this attempt. See app.learning.taxonomy.
    learning: Mapped[dict | None] = mapped_column(JSONB)

    # Schema version of the derived columns above, so a stored derivation made
    # under different rules can be identified rather than trusted silently.
    learning_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    exercise: Mapped[Exercise] = relationship(lazy="joined")
    previous_attempt: Mapped["ExerciseAttempt | None"] = relationship(
        lazy="select", remote_side="ExerciseAttempt.id"
    )

    __table_args__ = (
        Index("ix_attempts_exercise_submitted", "exercise_id", "submitted_at"),
        # One row per (exercise, attempt number). Enforced in the database so a
        # double-submit cannot produce two "attempt 3" rows and make the retry
        # history incoherent.
        Index(
            "uq_attempts_exercise_number",
            "exercise_id",
            "attempt_number",
            unique=True,
        ),
    )
