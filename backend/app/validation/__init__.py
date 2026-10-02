"""Deterministic validation.

The single source of truth for whether a drawing is correct, and the authority
the tutor works from.

ARCHITECTURAL PRINCIPLE
-----------------------
Deterministic code is the source of truth. The LLM must never calculate or
invent dimensions, scale conversions, geometry, coordinates, tolerances or
validation results, and must never override a verdict. This package produces
those results; :mod:`app.tutor` receives them and explains them.

THE CONTRACT
------------
A finding is a **fact**, not an explanation::

    code, severity, expected, actual, difference, unit, geometry_reference,
    metadata

``ROOM_DIMENSION_ERROR, expected 84, actual 42, difference -42, unit mm,
geometry_reference "room"`` is a complete, checkable claim. "Your room is wrong
because you forgot to divide by 50" is not: it is a guess about the student's
reasoning, and reasoning is what the tutor is for.

Reproducibility is a hard requirement. Same exercise, same drawing, same
tolerance, same findings, in the same order, every time.
"""

from app.validation.checks import (
    validate_alignment,
    validate_dimensions,
    validate_openings,
    validate_room,
    validate_scale,
    validate_walls,
)
from app.validation.codes import FindingCode, Severity
from app.validation.engine import (
    CHECKS,
    aggregate_findings,
    findings_by_code,
    has_code,
    validate_drawing,
)
from app.validation.findings import Finding, ValidationResult, ValidationSummary
from app.validation.tolerance import TolerancePolicy

__all__ = [
    # pipeline
    "validate_scale",
    "validate_room",
    "validate_walls",
    "validate_openings",
    "validate_dimensions",
    "validate_alignment",
    "CHECKS",
    "aggregate_findings",
    "validate_drawing",
    "findings_by_code",
    "has_code",
    # vocabulary
    "Finding",
    "FindingCode",
    "Severity",
    "ValidationResult",
    "ValidationSummary",
    "TolerancePolicy",
]
