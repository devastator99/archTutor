"""Request and response contracts for submitting and validating a drawing.

WHAT CHANGED, AND WHY
---------------------
This used to wrap submissions in ``{"data": {...}}`` and hand the inner object to
the validator untouched, because the drawing model had not been decided yet. It
has: :class:`app.geometry.drawing.StudentDrawing`.

The wrapper is gone. A submitted drawing is now the drawing, so ``geometry`` *is*
the drawing, and the endpoint documents its shape directly rather than describing
a guess. The payload is still typed as a plain dict here on purpose -- the
authoritative parser is :meth:`StudentDrawing.from_dict`, which rejects unknown
keys, coerces every number through ``to_decimal`` and names the path of whatever
it could not read. Duplicating those rules in Pydantic would create a second
parser to keep in step with the first, and two parsers disagreeing is exactly how
a submission passes a check it should have failed.

Validation results are carried through verbatim. Nothing in this module
summarises, reorders or rewords a finding.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.learning import IssueRead

NonNegativeMm = Annotated[
    Decimal, Field(ge=0, description="Tolerance in millimetres.")
]
"""Tolerance as ``Decimal``, not ``float``.

A float tolerance reintroduces exactly the binary rounding the measurement
engine exists to avoid: ``0.1`` is not representable, so a request for 0.1 mm
would compare against 0.1000000000000000055511151231257827 and a drawing
exactly on the limit would be marked wrong.
"""


class ToleranceOverride(BaseModel):
    """Per-quantity tolerance overrides. Every field defaults to strict."""

    model_config = ConfigDict(extra="forbid")

    room_dimension_mm: NonNegativeMm = Decimal(0)
    wall_thickness_mm: NonNegativeMm = Decimal(0)
    opening_width_mm: NonNegativeMm = Decimal(0)
    opening_placement_mm: NonNegativeMm = Decimal(0)
    dimension_mm: NonNegativeMm = Decimal(0)
    dimension_label_mm: NonNegativeMm = Decimal(0)
    """Tolerance on a dimension's *written* number, in real-world millimetres.

    Kept separate from ``dimension_mm`` because the two judge different units:
    ``dimension_mm`` forgives error in the line's span on the sheet, while this
    one forgives error in the figure written beside it. A label is a declared
    value, so this stays strict by default.
    """

    def to_policy_dict(self) -> dict[str, Any]:
        return {
            name: str(getattr(self, name))
            for name in type(self).model_fields
        }


class ValidateRequest(BaseModel):
    """Dry-run validation: check a drawing without persisting an attempt.

    ``tolerance`` is optional and defaults to exact. It is echoed in the response
    so a client can never mistake a forgiving verdict for a strict one.
    """

    model_config = ConfigDict(extra="forbid")

    geometry: dict[str, Any] = Field(
        description=(
            "The student's drawing in paper millimetres at their declared "
            "scale. See StudentDrawing.to_dict() for the exact shape."
        )
    )
    tolerance: ToleranceOverride | None = None


class FindingRead(BaseModel):
    """One structured discrepancy, exactly as the engine produced it."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str
    message: str
    expected: str | int | None = None
    actual: str | int | None = None
    difference: str | int | None = None
    unit: str
    geometry_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    error_count: int
    warning_count: int
    codes: dict[str, int]


class ValidationResultRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    findings: list[FindingRead]
    summary: ValidationSummaryRead
    scale_denominator: int
    tolerance: dict[str, str]


class ValidateResponse(BaseModel):
    """A dry run: the engine's findings, and the same teaching an attempt gives.

    Both shapes are returned because a student who presses "check" must get the
    same help as one who submits, and because the findings stay exactly as the
    engine produced them -- the stored result and this response are required to
    match byte for byte, and adding a presentation beside them changes nothing
    about that.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: uuid.UUID
    passed: bool
    findings: list[FindingRead]
    issues: list[IssueRead]
    summary: ValidationSummaryRead
    scale_denominator: int
    tolerance: dict[str, str]


class AttemptCreate(ValidateRequest):
    """An attempt is a validate request whose result is also stored.

    The stored representation of an attempt is :class:`app.schemas.learning.
    AttemptRead`, which carries the progress and learning layers this module
    knows nothing about. There is deliberately one response contract for an
    attempt rather than one per module that reads it.
    """
