"""Tutor service.

The only place an LLM is called, and it is a text generator, not a calculator.

It receives the feedback the deterministic backend has already assembled from
:mod:`app.validation` findings, and turns it into prose a B.Arch student can act
on. It must never produce a dimension, a scale conversion, a coordinate, a
tolerance or a verdict of its own.

THREE MODULES, THREE JOBS
-------------------------
:mod:`app.tutor.service`  calls a provider, times it, and falls back
:mod:`app.tutor.guard`    rejects any number the engine did not produce
:mod:`app.tutor.prompts`  asks for the explanation, and forbids the arithmetic

The product does not depend on any of them. With no provider configured, with a
provider down, or with a provider that invents a figure, the student still gets a
complete what/where/expected/actual/difference/why/how panel from
:mod:`app.learning.explanations`. The tutor is an enhancement over a working
floor, never a component the floor depends on.
"""

from app.tutor.guard import allowed_numbers, numbers_in, unsupported_numbers
from app.tutor.service import (
    TutorExplanation,
    deterministic_explanation,
    explain_issue,
    tutor_configured,
)

__all__ = [
    "TutorExplanation",
    "allowed_numbers",
    "deterministic_explanation",
    "explain_issue",
    "numbers_in",
    "tutor_configured",
    "unsupported_numbers",
]
