"""Assembling a finding into the feedback a student is shown.

    WHAT IS WRONG  ->  the finding's own message, verbatim
    WHERE          ->  a human location, never a wall id
    EXPECTED       ->  the engine's expected value, verbatim
    ACTUAL         ->  the engine's measured value, verbatim
    DIFFERENCE     ->  the engine's difference, verbatim
    WHY IT MATTERS ->  deterministic prose
    HOW TO FIX     ->  deterministic steps

The first six are facts. Only the last two are teaching, and they are teaching
*without a model*, so the panel is complete even when the tutor is unreachable.

Nothing here re-derives a number. If this module calculated an expected value it
would be a second implementation of :mod:`app.measurement`, and a disagreement
between the two would show a student a number the validator never produced.

BUILT FROM THE STORED SHAPE, NOT A LIVE FINDING
-----------------------------------------------
The input is the engine's serialised finding -- exactly what is persisted in an
attempt row. That is deliberate: a student revisiting an attempt from last term
gets the same panel, and gets it with wording that has since improved, rather
than the prose of the day it was submitted. The presentation can therefore be
revised without rewriting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from app.geometry.drawing import StudentDrawing
from app.learning.explanations import describe_location, how_to_fix, why_it_matters
from app.learning.taxonomy import category_for, describe_category
from app.validation.codes import FindingCode, Severity
from app.validation.findings import Finding


@dataclass(frozen=True, slots=True)
class IssueFeedback:
    """One issue, in the shape the UI renders. Complete with no AI."""

    code: str
    category: str
    category_label: str
    severity: str
    what_is_wrong: str
    where: str
    expected: str | int | None
    actual: str | int | None
    difference: str | int | None
    unit: str
    why_it_matters: str
    how_to_fix: list[str] = field(default_factory=list)
    geometry_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "category_label": self.category_label,
            "severity": self.severity,
            "what_is_wrong": self.what_is_wrong,
            "where": self.where,
            "expected": self.expected,
            "actual": self.actual,
            "difference": self.difference,
            "unit": self.unit,
            "why_it_matters": self.why_it_matters,
            "how_to_fix": list(self.how_to_fix),
            "geometry_reference": self.geometry_reference,
            "metadata": dict(self.metadata),
        }


_UNIT_LABELS = {
    "mm": "mm on the sheet",
    "count": "",
    "side": "",
    "scale": "",
    "wall": "",
}


def format_quantity(value: str | int | None, unit: str) -> str | None:
    """Render an engine value for display without altering it.

    Returns ``None`` for a quantity that does not apply, so the UI can leave the
    row out rather than showing a blank or a zero. A missing element has no
    measured value, and printing 0 for one would be a measurement that was never
    taken.
    """
    if value is None:
        return None
    suffix = _UNIT_LABELS.get(unit, unit)
    if not suffix:
        return str(value)
    return f"{value} {suffix}"


def assemble(
    *,
    code: str,
    severity: str,
    message: str,
    expected: str | int | None,
    actual: str | int | None,
    difference: str | int | None,
    unit: str,
    geometry_reference: str | None,
    metadata: Mapping[str, Any],
    drawing: StudentDrawing | None = None,
) -> IssueFeedback:
    """Build one issue from the engine's stored fields.

    ``metadata`` is used to name the thing in human terms. The drawing is
    optional and only sharpens a location that the metadata could not resolve on
    its own; it never affects a quantity, so omitting it can make a location
    vaguer but never wrong.
    """
    finding_code = FindingCode(code)
    category = category_for(finding_code, dict(metadata))
    return IssueFeedback(
        code=code,
        category=category.value,
        category_label=describe_category(category),
        severity=severity,
        what_is_wrong=message,
        where=describe_location(
            finding_code, dict(metadata), geometry_reference, drawing
        ),
        expected=expected,
        actual=actual,
        difference=difference,
        unit=unit,
        why_it_matters=why_it_matters(finding_code, dict(metadata)),
        how_to_fix=how_to_fix(finding_code, dict(metadata)),
        geometry_reference=geometry_reference,
        metadata=dict(metadata),
    )


def build_issue_feedback(
    finding: Finding, *, drawing: StudentDrawing | None = None
) -> IssueFeedback:
    """Feedback for a live engine finding."""
    return assemble(
        code=finding.code.value,
        severity=finding.severity.value,
        message=finding.message,
        expected=_scalar(finding.expected),
        actual=_scalar(finding.actual),
        difference=_scalar(finding.difference),
        unit=finding.unit,
        geometry_reference=finding.geometry_reference,
        metadata=_scalarise(finding.metadata),
        drawing=drawing,
    )


def feedback_from_stored(
    row: Mapping[str, Any], *, drawing: StudentDrawing | None = None
) -> IssueFeedback:
    """Feedback for a finding as it was persisted.

    The counterpart to :func:`build_issue_feedback` for historical attempts, and
    the reason a stored attempt stays readable as the presentation improves.
    """
    return assemble(
        code=row["code"],
        severity=row.get("severity", Severity.ERROR.value),
        message=row.get("message", ""),
        expected=row.get("expected"),
        actual=row.get("actual"),
        difference=row.get("difference"),
        unit=row.get("unit", "mm"),
        geometry_reference=row.get("geometry_reference"),
        metadata=row.get("metadata") or {},
        drawing=drawing,
    )


def build_feedback(
    findings, *, drawing: StudentDrawing | None = None
) -> list[IssueFeedback]:
    """Feedback for every finding, in engine order."""
    return [build_issue_feedback(finding, drawing=drawing) for finding in findings]


def feedback_from_stored_all(
    rows, *, drawing: StudentDrawing | None = None
) -> list[IssueFeedback]:
    return [feedback_from_stored(row, drawing=drawing) for row in rows]


def blocking_issues(feedback) -> list[IssueFeedback]:
    """Only the issues that must be fixed before the exercise is complete."""
    return [item for item in feedback if item.severity == Severity.ERROR.value]


def _scalar(value: Any) -> Any:
    """A Decimal becomes a string, so 4.6 stays 4.6 through JSON."""
    if isinstance(value, Decimal):
        return str(value)
    return value


def _scalarise(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _scalar(value) for key, value in metadata.items()
    }


def concepts_for_exercise(exercise) -> list[str]:
    """Concepts a completed exercise demonstrates.

    Built from the brief's own requirements, so the list describes what this
    exercise actually tested. Every one of them is a fact the validator just
    confirmed, which is why it can be shown on completion without any risk of
    praising something that was not correct.
    """
    demonstrated = [
        f"Work at 1:{exercise.scale_denominator} and convert every dimension "
        f"correctly",
        f"Set out a {exercise.room_width_mm} x {exercise.room_height_mm} mm room",
        f"Draw {exercise.wall_thickness_mm} mm walls",
        f"Close the room with correctly aligned walls",
    ]
    for requirement in exercise.door_requirements:
        demonstrated.append(_opening_phrase(requirement, "door"))
    for requirement in exercise.window_requirements:
        demonstrated.append(_opening_phrase(requirement, "window"))
    for requirement in exercise.dimension_requirements:
        demonstrated.append(
            f"Dimension the {requirement.axis} as {requirement.value_mm} mm"
        )
    return demonstrated


def _opening_phrase(requirement, kind: str) -> str:
    noun = "door" if kind == "door" else "window"
    count = requirement.count
    plural = noun if count == 1 else f"{noun}s"
    width = f"{requirement.width_mm} mm"
    if requirement.wall:
        where = f" on the {requirement.wall} wall"
    else:
        where = ""
    if count == 1:
        return f"Set out a {width} {noun}{where}"
    return f"Set out {count} {width} {plural}{where}"
