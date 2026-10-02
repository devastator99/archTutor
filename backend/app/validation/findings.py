"""Findings: the engine's only output.

FACTS, NOT PROSE
----------------
A finding is evidence. It says what was expected, what was drawn, by how much
they differ, and which piece of geometry the claim refers to. It does not say
why the student is wrong, because "why" is a teaching judgement and teaching is
the tutor's job, downstream, using these facts.

The engine therefore must never produce a sentence like "your room is wrong
because you forgot to divide by 50". It produces:

    ROOM_DIMENSION_ERROR, expected 84, actual 42, difference -42, mm, room-1

The tutor turns that into an explanation. The tutor cannot contradict it,
because the tutor never sees anything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.validation.codes import FindingCode, Severity


@dataclass(frozen=True, slots=True)
class Finding:
    """One precise, reproducible discrepancy.

    ``expected`` and ``actual`` are ``None`` when a quantity does not apply to
    this finding -- a missing element has no measured value, and inventing a
    zero for it would be a lie the tutor might then explain.
    """

    code: FindingCode
    severity: Severity
    message: str
    expected: Decimal | int | str | None = None
    actual: Decimal | int | str | None = None
    difference: Decimal | int | str | None = None
    unit: str = "mm"
    geometry_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage and transport.

        Decimals become strings for the same reason dimensions do elsewhere: a
        JSON number is a double, and ``4.6`` must not become
        ``4.5999999999999996`` before the tutor reads it.
        """
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "expected": _encode(self.expected),
            "actual": _encode(self.actual),
            "difference": _encode(self.difference),
            "unit": self.unit,
            "geometry_reference": self.geometry_reference,
            "metadata": {
                key: _encode(value) if isinstance(value, Decimal) else value
                for key, value in self.metadata.items()
            },
        }


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int):
        return value
    return value


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """Counts only. No prose, no advice, no interpretation."""

    total: int
    error_count: int
    warning_count: int
    codes: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "codes": dict(self.codes),
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The complete deterministic verdict."""

    passed: bool
    findings: tuple[Finding, ...]
    summary: ValidationSummary
    scale_denominator: int
    tolerance: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [finding.to_dict() for finding in self.findings],
            "summary": self.summary.to_dict(),
            "scale_denominator": self.scale_denominator,
            "tolerance": dict(self.tolerance),
        }
