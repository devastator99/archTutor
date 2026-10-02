"""The validation engine.

The authority on whether a drawing is correct. The tutor explains these
findings and may not contradict them; nothing downstream may alter them.

QUALITY BAR
-----------
Every function here is pure. No clock, no randomness, no network, no LLM, no
database. Given the same exercise, drawing and tolerance policy, the output is
byte-for-byte identical every time. That is what makes a finding defensible to
a student: it can be reproduced, and if it cannot be reproduced it is a bug.
"""

from __future__ import annotations

from collections import Counter
from typing import Sequence

from app.geometry.drawing import StudentDrawing
from app.schemas.exercise import ExerciseRead
from app.validation import checks
from app.validation.codes import FindingCode, Severity
from app.validation.findings import Finding, ValidationResult, ValidationSummary
from app.validation.tolerance import TolerancePolicy

# Every check, in a fixed order. Order is part of the contract: findings come
# back grouped by cause so a student reads them top to bottom, and two runs of
# the same input always produce the same list.
CHECKS = (
    checks.validate_scale,
    checks.validate_room,
    checks.validate_walls,
    checks.validate_openings,
    checks.validate_dimensions,
    checks.validate_alignment,
)


def aggregate_findings(findings: Sequence[Finding]) -> ValidationSummary:
    """Summarise findings as counts. No prose, no advice, no interpretation."""
    counts = Counter(finding.code.value for finding in findings)
    return ValidationSummary(
        total=len(findings),
        error_count=sum(1 for f in findings if f.severity is Severity.ERROR),
        warning_count=sum(1 for f in findings if f.severity is Severity.WARNING),
        codes=dict(sorted(counts.items())),
    )


def validate_drawing(
    exercise: ExerciseRead,
    drawing: StudentDrawing,
    policy: TolerancePolicy | None = None,
) -> ValidationResult:
    """Validate a drawing against an exercise and return the verdict.

    Runs every check regardless of what earlier ones found. A drawing at the
    wrong scale produces a SCALE_ERROR *and* the room errors that follow from
    it, because a student who drew at 1:100 needs to be told that, and also
    told what 1:50 would have required.
    """
    tolerance = policy or TolerancePolicy.strict()

    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(exercise, drawing, tolerance))

    summary = aggregate_findings(findings)
    return ValidationResult(
        passed=summary.error_count == 0,
        findings=tuple(findings),
        summary=summary,
        scale_denominator=drawing.scale_denominator,
        tolerance={k: str(v) for k, v in tolerance.to_dict().items()},
    )


def findings_by_code(result: ValidationResult) -> dict[str, list[Finding]]:
    """Group findings by code, for callers that need to react per category."""
    grouped: dict[str, list[Finding]] = {}
    for finding in result.findings:
        grouped.setdefault(finding.code.value, []).append(finding)
    return grouped


def has_code(result: ValidationResult, code: FindingCode) -> bool:
    return any(finding.code is code for finding in result.findings)


__all__ = [
    "CHECKS",
    "aggregate_findings",
    "findings_by_code",
    "has_code",
    "validate_drawing",
]
