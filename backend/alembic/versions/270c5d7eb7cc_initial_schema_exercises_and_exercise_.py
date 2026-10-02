"""initial schema: exercises and exercise_attempts

Revision ID: 270c5d7eb7cc
Revises:
Create Date: 2026-09-27 17:56:30.925858

Amended in place rather than superseded by a follow-up migration. The first
version of this file created ``instructions`` and ``submitted_geometry`` /
``created_at``, and the attempt columns were renamed to ``student_geometry`` /
``submitted_at`` when the drawing model was fixed. Those names only ever existed
in a local development database that had been built with ``create_all`` rather
than with this migration, so nothing depends on them, and no deployment exists.
Recording the rename as history would preserve a shape that was never actually
released. The alternative -- a second migration -- was rejected because it would
leave the local databases permanently out of step with the migrations that are
supposed to describe them.

Amended a second time for the same reason, to add the retry-loop and learning
columns (``attempt_number``, ``previous_attempt_id``, ``progress``, ``learning``,
``learning_version``, ``completed``, ``completed_at``) when the vertical slice
made attempt tracking a first-class requirement. Still no deployment, still only
local databases, still no released schema to migrate away from.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "270c5d7eb7cc"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("room_width_mm", sa.Integer(), nullable=False),
        sa.Column("room_height_mm", sa.Integer(), nullable=False),
        sa.Column("wall_thickness_mm", sa.Integer(), nullable=False),
        sa.Column("scale_denominator", sa.Integer(), nullable=False),
        sa.Column(
            "door_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "window_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "dimension_requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "difficulty",
            sa.Enum(
                "beginner",
                "intermediate",
                name="difficulty",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "room_height_mm > 0", name="ck_exercise_room_height_positive"
        ),
        sa.CheckConstraint("room_width_mm > 0", name="ck_exercise_room_width_positive"),
        # A brief must be a reduced drawing. 1:1 would make the paper
        # millimetres equal the building millimetres and defeat the scale check.
        sa.CheckConstraint("scale_denominator > 1", name="ck_exercise_scale_positive"),
        sa.CheckConstraint(
            "wall_thickness_mm > 0", name="ck_exercise_wall_thickness_positive"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "exercise_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column(
            "student_geometry", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # --- The retry loop -------------------------------------------
        # A student corrects and resubmits, so one attempt is one turn of the
        # loop rather than one final verdict. attempt_number counts the loop per
        # exercise, previous_attempt_id names what this one is compared against
        # (null on the first), and completed marks the turn that passed.
        sa.Column(
            "attempt_number", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("previous_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("learning", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "learning_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "completed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercises.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["previous_attempt_id"], ["exercise_attempts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Newest submission first is the order the product reads attempts in, so the
    # index leads with exercise_id and descends on submitted_at.
    op.create_index(
        "ix_attempts_exercise_submitted",
        "exercise_attempts",
        ["exercise_id", "submitted_at"],
        unique=False,
    )
    # One row per (exercise, attempt number). Enforced in the database rather
    # than only in the repository, so a concurrent double-submit cannot produce
    # two "attempt 3" rows and make the retry history incoherent.
    op.create_index(
        "uq_attempts_exercise_number",
        "exercise_attempts",
        ["exercise_id", "attempt_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_attempts_exercise_submitted", table_name="exercise_attempts")
    op.drop_table("exercise_attempts")
    op.drop_table("exercises")
