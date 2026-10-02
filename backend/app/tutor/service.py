"""The tutor: an LLM explanation with a deterministic floor underneath it.

THE CONTRACT
------------
The tutor explains findings. It does not compute, judge, or override them.

Everything the student is shown about *what is wrong* -- the message, the
expected value, the actual value, the difference -- comes from
:mod:`app.validation` and is assembled by :mod:`app.learning.feedback`. The tutor
is given that finished feedback and asked for prose about it. It cannot change
the numbers, because it is never asked to produce them.

IT IS OPTIONAL, AND THE PRODUCT IS NOT
--------------------------------------
Validation works with no LLM configured, no LLM reachable, and no LLM behaving.
In every one of those cases the student still gets a complete
what/where/expected/actual/difference/why/how panel from
:mod:`app.learning.explanations`, and the exercise is still completable.

That is the whole design reason the deterministic layer exists separately. If the
AI were load-bearing, an outage would become a teaching outage, and the failure
would land on a student who has no way to work around it.

WHEN THE MODEL IS WRONG, IT IS DISCARDED
-----------------------------------------
Not corrected, not footnoted, not shown with a warning. If
:mod:`app.tutor.guard` finds a number the engine did not produce, the text is
dropped and the deterministic explanation stands. A student cannot audit a
caveat, and "the AI might be wrong here" is not usable feedback about a wall
thickness. See :mod:`app.tutor.guard` for why this is the failure that matters.

LATENCY
-------
One synchronous call, with a short timeout. A student waiting on an explanation
has already done the hard part; the explanation must not become the slowest part
of the loop. On timeout the deterministic explanation is used and the failure is
logged. No queue, no retry loop, no background worker -- at this volume a
synchronous call is faster and simpler than the machinery to avoid one.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger, log_event
from app.tutor.guard import allowed_numbers, unsupported_numbers
from app.tutor.prompts import SYSTEM_PROMPT, user_prompt

logger = get_logger("tutor")

DEFAULT_TIMEOUT_SECONDS = 8.0
"""Short enough that a hanging provider cannot strand the student.

A student who has finished drawing and pressed "explain" is waiting to find out
what to fix. Eight seconds is long enough for a real completion and short enough
that falling back to the deterministic text is not worse than waiting.
"""

MAX_EXPLANATION_CHARS = 4000
"""Bound on the response before it reaches the guard.

A response far past this is not an explanation, and parsing an unbounded body is
how a provider turns a slow answer into a slow *crash*.
"""

MAX_COMPLETION_TOKENS = 1200
"""Generation budget for one explanation.

Sized for reasoning models, which spend part of this budget thinking before they
write. A budget of 600 was measured against a reasoning model on Groq: it used
437 of the tokens and still had a sentence to finish, so a tight budget makes
truncation the normal case rather than the rare one. The character cap above
still bounds what reaches the guard.
"""


@dataclass(frozen=True, slots=True)
class TutorExplanation:
    """What the student reads in the tutor panel.

    ``source`` is displayed. If it says ``deterministic`` the student knows the
    text is not from a model, which matters: it is a claim about reliability, and
    hiding it would be a small dishonesty about where the words came from.
    """

    explanation: str
    source: str
    """``"llm"`` or ``"deterministic"``."""
    blocked_numbers: list[str] = field(default_factory=list)
    """Numbers the model invented, kept for the log and for tests."""
    model: str | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "explanation": self.explanation,
            "source": self.source,
            "blocked_numbers": list(self.blocked_numbers),
            "model": self.model,
            "latency_ms": self.latency_ms,
        }


def deterministic_explanation(issue: dict[str, Any]) -> str:
    """The floor: a complete explanation with no model involved.

    Composed from the feedback's own fields rather than written here, so it
    cannot drift from the numbers it is describing. The prose is not written
    here either -- it comes from :mod:`app.learning.explanations` via
    :mod:`app.learning.feedback`, so the tutor cannot become a second source of
    teaching text that disagrees with the panel beside it.
    """
    why = issue.get("why_it_matters") or "This does not match the brief."
    steps = issue.get("how_to_fix") or [
        "Compare the drawing against the brief and correct the difference."
    ]
    expected = issue.get("expected")
    unit = issue.get("unit") or "mm"

    lines = [f"{issue.get('what_is_wrong', 'This does not match the brief.')}"]
    if expected is not None and unit == "mm":
        lines.append(
            f"Fix it to {expected} mm on the sheet, then check again to confirm "
            f"the change was measured."
        )
    lines.append(why)
    for step in steps:
        lines.append(f"- {step}")
    lines.append(
        f"Then check again: the same validator will measure what you changed, so "
        f"you will see this item resolved rather than having to look for it."
    )
    return "\n\n".join(lines)


def tutor_configured() -> bool:
    """Is there an endpoint, a key and a model to call?"""
    return bool(
        settings.tutor_base_url and settings.tutor_api_key and settings.tutor_model
    )


def explain_issue(issue: dict[str, Any]) -> TutorExplanation:
    """Explain one issue, falling back to deterministic prose on any failure.

    The fallback is the *default* path, not an error path. The model is the
    enhancement; a caller that cannot reach a model still gets a usable answer
    and never an exception.
    """
    if not tutor_configured():
        log_event(logger, "tutor.skipped", reason="not_configured", code=issue.get("code"))
        return TutorExplanation(
            explanation=deterministic_explanation(issue), source="deterministic"
        )

    payload = _issue_payload(issue)
    allowed = allowed_numbers(payload)

    started = time.perf_counter()
    try:
        text = _call_model(payload)
    except Exception as exc:  # noqa: BLE001 - every failure falls back
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        log_event(
            logger,
            "tutor.failure",
            level=logging.ERROR,
            latency_ms=latency_ms,
            error=type(exc).__name__,
            model=settings.tutor_model,
        )
        return TutorExplanation(
            explanation=deterministic_explanation(issue),
            source="deterministic",
            model=settings.tutor_model,
            latency_ms=latency_ms,
        )

    latency_ms = round((time.perf_counter() - started) * 1000, 3)

    blocked = unsupported_numbers(text, allowed)
    if blocked:
        log_event(
            logger,
            "tutor.blocked_unsupported_numbers",
            level=logging.WARNING,
            latency_ms=latency_ms,
            model=settings.tutor_model,
            code=issue.get("code"),
            blocked_numbers=blocked,
        )
        return TutorExplanation(
            explanation=deterministic_explanation(issue),
            source="deterministic",
            blocked_numbers=blocked,
            model=settings.tutor_model,
            latency_ms=latency_ms,
        )

    log_event(
        logger,
        "tutor.explained",
        latency_ms=latency_ms,
        model=settings.tutor_model,
        code=issue.get("code"),
    )
    return TutorExplanation(
        explanation=text,
        source="llm",
        model=settings.tutor_model,
        latency_ms=latency_ms,
    )


def _issue_payload(issue: dict[str, Any]) -> dict[str, Any]:
    """The exact evidence the model is shown.

    Only the fields relevant to explaining one issue. In particular the
    student's full drawing is not sent: it is not needed, and it is the student's
    own work rather than the tutor's to transmit to a third party.

    The engine's ``metadata`` is included whole rather than filtered to a
    chosen few keys, because those are the figures a tutor is allowed to
    restate: the 4200 mm the brief asked for, the 3500 mm the sheet currently
    means, the 1:50 in play. Withholding them would force any explanation that
    mentions them to be discarded by the numeric guard, which would make the
    guard suppress correct answers rather than invented ones.
    """
    return {
        "code": issue.get("code"),
        "category": issue.get("category"),
        "what_is_wrong": issue.get("what_is_wrong"),
        "where": issue.get("where"),
        "expected": issue.get("expected"),
        "actual": issue.get("actual"),
        "difference": issue.get("difference"),
        "unit": issue.get("unit"),
        "why_it_matters": issue.get("why_it_matters"),
        "how_to_fix": issue.get("how_to_fix"),
        "metadata": issue.get("metadata") or {},
        "scale_denominator": issue.get("metadata", {}).get("scale_denominator"),
    }


def _call_model(payload: dict[str, Any]) -> str:
    """One HTTP call to an OpenAI-compatible chat completions endpoint.

    Imported lazily so the module loads, and every deterministic path works,
    when ``httpx`` is unavailable or no provider is configured.
    """
    import httpx

    url = f"{str(settings.tutor_base_url).rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.tutor_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.tutor_model,
        "temperature": 0,
        "max_tokens": MAX_COMPLETION_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(payload)},
        ],
    }
    if settings.tutor_reasoning_effort:
        body["reasoning_effort"] = settings.tutor_reasoning_effort

    with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()

    return _content_of(data)[:MAX_EXPLANATION_CHARS]


class TutorResponseError(RuntimeError):
    """A provider answered, but not with an explanation.

    Raised rather than returned as empty text so that :func:`explain_issue`
    takes its ordinary fallback path and the failure is logged like any other.
    """


def _content_of(data: dict[str, Any]) -> str:
    """The assistant's text from a chat completion, or a reason it is missing.

    A reasoning model can return ``content: null`` when it spends its whole
    budget thinking, and some providers answer with an error object in a 200
    body. Both are read as "no explanation", never as the string ``None``: the
    deterministic fallback is a complete answer, and a student reading the word
    "None" would be shown a provider's failure as if it were teaching.
    """
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TutorResponseError(
            f"no choices in the response: {sorted(data) or 'empty body'}"
        ) from exc

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        finish = data["choices"][0].get("finish_reason", "unknown")
        raise TutorResponseError(
            f"empty content (finish_reason={finish}, "
            f"reasoning_chars={len(message.get('reasoning') or '')})"
        )
    return content.strip()
