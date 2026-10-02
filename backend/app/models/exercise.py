"""The exercise specification.

An exercise is a brief, not a drawing. It states what the student must produce
and in what units; it never contains the student's work, and it never contains
validation logic.

Two rules from the constitution shape this module:

* **The exercise does not validate.** Whether a submission is correct is
  decided by :mod:`app.validation`, which reads an exercise as input. Putting
  comparisons here would give the spec authority over the verdict, and the
  spec is authored content, not the authority.
* **No adaptive generation.** Exercises are authored and seeded, not
  generated. Difficulty is a fixed property of the brief.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Difficulty(str, enum.Enum):
    """How demanding a brief is.

    Two levels only. An ``ADVANCED`` level would be a label for exercises that
    do not exist, and an unexercised enum value is an unexercised branch.
    """

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"


class Exercise(Base):
    """A single drafting exercise.

    Every dimension is a **real-world millimetre**. The drawing the student
    produces is expected at ``scale_denominator``; nothing here is pre-divided
    by the scale, because pre-dividing would put a scale conversion in the
    database and there must be exactly one implementation of that arithmetic
    (:mod:`app.measurement`).

    Room geometry is an axis-aligned interior clear size, the only room shape
    the MVP asks for. The boundary check constraints keep the data honest at
    the storage layer, so a malformed exercise cannot be inserted even by code
    that skips the Pydantic schemas.
    """

    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # --- Room geometry, real-world millimetres --------------------------
    room_width_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    room_height_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    wall_thickness_mm: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Scale ----------------------------------------------------------
    scale_denominator: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Requirements ---------------------------------------------------
    # Lists of requirement objects; the authoritative shapes live in
    # app.schemas.exercise. JSONB rather than child tables because the
    # requirement vocabulary is still moving, and normalising it now would
    # encode guesses about a domain that is not finished.
    door_requirements: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    window_requirements: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    dimension_requirements: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(
            Difficulty,
            name="difficulty",
            native_enum=False,
            length=16,
            # Persist the enum *value* ("beginner"), not its member name
            # ("BEGINNER"), so the database and the API speak the same language.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=Difficulty.BEGINNER,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("room_width_mm > 0", name="ck_exercise_room_width_positive"),
        CheckConstraint("room_height_mm > 0", name="ck_exercise_room_height_positive"),
        CheckConstraint(
            "wall_thickness_mm > 0", name="ck_exercise_wall_thickness_positive"
        ),
        CheckConstraint(
            "scale_denominator > 1", name="ck_exercise_scale_positive"
        ),
    )
