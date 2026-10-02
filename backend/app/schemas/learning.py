"""Response contracts for the vertical slice: feedback, progress and tutoring.

These are the shapes the UI renders. Three rules govern them:

* **No secret may appear here.** The tutor is configured server-side; no schema
  in this module carries a key, and :func:`app.api.security.assert_no_secrets`
  enforces it in tests.
* **Deterministic fields are always present.** ``expected``, ``actual`` and
  ``difference`` appear on every issue, as ``None`` when the quantity does not
  apply. A client that had to test for their absence would eventually test
  wrong, and the field would go missing for exactly the findings where a zero
  would be a lie -- a missing element has no measured value.
* **Progress is stored, presented on read.** The diff is persisted as engine
  output and the what/where/why/how fields are regenerated when read, so
  improving the wording improves every historical attempt without a migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

Quantity = str | int | None


class IssueRead(BaseModel):
    """One issue, complete. This is the what/where/why/how contract.

    ``what_is_wrong``, ``expected``, ``actual`` and ``difference`` are the
    engine's own values, restated and never recomputed.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    category: str
    category_label: str
    severity: str

    what_is_wrong: str
    where: str
    expected: Quantity = None
    actual: Quantity = None
    difference: Quantity = None
    unit: str

    why_it_matters: str
    how_to_fix: list[str]

    geometry_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TutorExplanationRead(BaseModel):
    """The tutor panel's contents.

    ``source`` is shown to the student. When it reads ``deterministic`` they know
    the text did not come from a model, which is a claim about reliability and
    should not be hidden.
    """

    model_config = ConfigDict(extra="forbid")

    explanation: str
    source: str
    blocked_numbers: list[str] = Field(default_factory=list)
    model: str | None = None
    latency_ms: float | None = None


class ExplainRequest(BaseModel):
    """Ask for one issue to be explained.

    A single issue, identified by its position in the attempt's feedback. A
    student clicks one mistake at a time, and explaining the whole set at once
    would produce a wall of prose with no focus.
    """

    model_config = ConfigDict(extra="forbid")

    issue_index: Annotated[int, Field(ge=0, le=500)]


class ExplainResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: uuid.UUID
    issue_index: int
    issue: IssueRead
    tutor: TutorExplanationRead


class LearningRead(BaseModel):
    """The structured, countable record of what went wrong."""

    model_config = ConfigDict(extra="forbid")

    categories: dict[str, int] = Field(default_factory=dict)
    category_count: int = 0
    primary_category: str | None = None


class ProgressRead(BaseModel):
    """How the latest attempt compares with the one before it.

    The three lists are whole issues, not codes: "the north wall is now the right
    thickness" is worth more than "one finding resolved", and a count cannot say
    which mistake was fixed.
    """

    model_config = ConfigDict(extra="forbid")

    attempt_number: int
    passed: bool
    completed: bool
    is_first_attempt: bool
    improved: bool
    remaining_count: int
    resolved_count: int
    new_count: int
    changed_count: int = 0
    remaining: list[IssueRead] = Field(default_factory=list)
    resolved: list[IssueRead] = Field(default_factory=list)
    new: list[IssueRead] = Field(default_factory=list)
    changed: list[IssueRead] = Field(default_factory=list)


class AttemptRead(BaseModel):
    """A stored attempt, with everything the retry loop needs to show."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    exercise_id: uuid.UUID
    attempt_number: int
    previous_attempt_id: uuid.UUID | None = None
    student_geometry: dict[str, Any]
    validation_result: dict[str, Any]
    learning: LearningRead
    progress: ProgressRead
    completed: bool
    submitted_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def of(cls, attempt, feedback_from_stored) -> "AttemptRead":
        """Build from a model row, regenerating the presentation.

        ``feedback_from_stored`` is injected rather than imported so this stays a
        transport concern: it decides how a stored row becomes a response, and
        nothing about how an issue is explained.
        """
        stored_progress = attempt.progress or {}
        stored_learning = attempt.learning or {}

        return cls(
            id=attempt.id,
            exercise_id=attempt.exercise_id,
            attempt_number=attempt.attempt_number,
            previous_attempt_id=attempt.previous_attempt_id,
            student_geometry=attempt.student_geometry,
            validation_result=attempt.validation_result or {},
            learning=LearningRead(
                categories=stored_learning.get("categories", {}),
                category_count=stored_learning.get(
                    "category_count", len(stored_learning.get("categories", {}))
                ),
                primary_category=stored_learning.get("primary_category"),
            ),
            progress=ProgressRead(
                attempt_number=stored_progress.get(
                    "attempt_number", attempt.attempt_number
                ),
                passed=bool(stored_progress.get("passed", False)),
                completed=bool(stored_progress.get("completed", attempt.completed)),
                is_first_attempt=bool(stored_progress.get("is_first_attempt", True)),
                improved=bool(stored_progress.get("improved", False)),
                remaining_count=int(stored_progress.get("remaining_count", 0)),
                resolved_count=int(stored_progress.get("resolved_count", 0)),
                new_count=int(stored_progress.get("new_count", 0)),
                changed_count=int(stored_progress.get("changed_count", 0)),
                remaining=_issues(stored_progress.get("remaining", []), feedback_from_stored),
                resolved=_issues(stored_progress.get("resolved", []), feedback_from_stored),
                new=_issues(stored_progress.get("new", []), feedback_from_stored),
                changed=_issues(stored_progress.get("changed", []), feedback_from_stored),
            ),
            completed=attempt.completed,
            submitted_at=attempt.submitted_at,
            completed_at=attempt.completed_at,
        )


def _issues(rows, feedback_from_stored) -> list[IssueRead]:
    return [
        IssueRead.model_validate(feedback_from_stored(row).to_dict())
        for row in rows
    ]


class ExerciseSummaryRead(BaseModel):
    """Aggregate learning across one exercise's attempts.

    The foundation for adaptive learning: what recurs, and whether the student
    finished. Countable and model-free, so it can be aggregated further without
    first having to interpret prose.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: uuid.UUID
    attempt_count: int
    completed: bool
    completion_attempt_number: int | None = None
    category_totals: dict[str, int] = Field(default_factory=dict)
    resolved_totals: dict[str, int] = Field(default_factory=dict)
    first_attempt_error_count: int | None = None
    final_error_count: int | None = None
    concepts: list[str] = Field(default_factory=list)
