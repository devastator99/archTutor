"""Pydantic schemas for the exercise specification.

The single owner of the requirement object shapes stored in the exercise's
JSONB columns. ``dimension_requirements`` is declared here for the same reason
as the door and window lists: one place decides what a requirement means.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.exercise import Difficulty

PositiveMm = Annotated[int, Field(gt=0, description="Real-world millimetres.")]
PositiveScale = Annotated[int, Field(gt=1, description="Scale denominator, e.g. 50.")]

OpeningKind = Literal["door", "window"]

WallSide = Literal["north", "south", "east", "west"]
"""Which side of the room an opening belongs to.

Plan convention with ``y`` increasing north: ``north`` is the wall at the
maximum y, ``south`` at the minimum y, ``east`` at the maximum x, ``west`` at
the minimum x. Defined once here because the validator maps student wall
geometry onto these names.
"""


class OpeningRequirement(BaseModel):
    """One opening the exercise requires."""

    model_config = ConfigDict(extra="forbid")

    kind: OpeningKind
    width_mm: PositiveMm
    count: Annotated[int, Field(ge=1)] = 1
    wall: WallSide | None = None
    offset_mm: Annotated[int, Field(ge=0)] | None = None
    sill_height_mm: Annotated[int, Field(ge=0)] | None = None
    notes: str | None = None


class DimensionRequirement(BaseModel):
    """A dimension the drawing must carry.

    ``axis`` names the span; ``value_mm`` is the real-world length it must
    state. ``on_wall`` optionally pins it to one side, which is what makes a
    beginner's job unambiguous: a 4200 mm width belongs on the north or south
    wall, not floating in the middle of the room.
    """

    model_config = ConfigDict(extra="forbid")

    axis: Literal["width", "height"]
    value_mm: PositiveMm
    on_wall: WallSide | None = None
    label: str | None = None


class ExerciseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Annotated[str, Field(min_length=1, max_length=64)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None

    room_width_mm: PositiveMm
    room_height_mm: PositiveMm
    wall_thickness_mm: PositiveMm
    scale_denominator: PositiveScale

    door_requirements: list[OpeningRequirement] = Field(default_factory=list)
    window_requirements: list[OpeningRequirement] = Field(default_factory=list)
    dimension_requirements: list[DimensionRequirement] = Field(default_factory=list)
    difficulty: Difficulty = Difficulty.BEGINNER


class ExerciseCreate(ExerciseBase):
    pass


class ExerciseRead(ExerciseBase):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    created_at: datetime


class ExerciseListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExerciseRead]
    total: Annotated[int, Field(ge=0)]
