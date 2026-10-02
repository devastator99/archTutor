"""Progress across attempts: what got fixed, what did not, what is new.

THE PROBLEM
-----------
A student submits a drawing, gets seven findings, fixes one, and submits again.
The verdict is now six findings. A naive diff says "one resolved" and stops, but
that is a lie by omission: the seventh finding may be a *different* one, and if
the student broke the width dimension while fixing the wall, they have made
progress and regressed simultaneously.

Reporting only a count would also be a lie in the other direction, because it
cannot say *which* mistake was fixed, and "fixed the wall thickness" is the only
thing that makes a retry feel like it worked.

So the comparison is over finding *identity*, not counts.

FINDING IDENTITY
----------------
A finding is identified by what it is about, not by its position in a list:

    ROOM_DIMENSION_ERROR  about the room outline        -> "ROOM_DIMENSION_ERROR|room|width"
    WALL_THICKNESS_ERROR  about the north wall          -> "WALL_THICKNESS_ERROR|wall|north"
    DOOR_WIDTH_ERROR      about the first door          -> "DOOR_WIDTH_ERROR|door|0"

Opening identity is by ordinal among openings of that kind, because the student
does not carry a stable id through their edits and the engine's content-derived
ids change whenever a coordinate moves. Two doors are told apart by which door
they are, and that is exactly what the student can act on.

Identity and *values* are tracked separately, because they answer different
questions. "Which mistake is this" is the identity. "Did it move" is the values.
Keeping them apart is what allows a still-wrong drawing to be reported as
still-wrong: a student who nudges the north wall from 3 mm to 5 mm too thick has
neither fixed nor created anything, and this layer says exactly that instead of
inventing progress or raising a false alarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Sequence

from app.geometry.drawing import StudentDrawing
from app.validation.findings import Finding

# --- Identity ------------------------------------------------------------


def finding_identity(
    finding: Finding, drawing: StudentDrawing | None = None
) -> str:
    """A stable key for "the same mistake", across two attempts.

    The key is derived from the finding alone wherever possible, so it can be
    recomputed from stored data years later without the original drawing. The
    drawing is used only to number openings, because that is the one thing a
    finding cannot express on its own.
    """
    code = finding.code.value
    metadata = finding.metadata
    reference = finding.geometry_reference or ""

    if code in ("DOOR_WIDTH_ERROR", "WINDOW_WIDTH_ERROR",
                "DOOR_PLACEMENT_ERROR", "OPENING_PLACEMENT_ERROR"):
        kind = metadata.get("kind") or _kind_from_code(code)
        ordinal = _number_opening(drawing, metadata.get("opening_id"), kind)
        return f"{code}|{kind}|{ordinal if ordinal is not None else '?'}"

    if code == "WALL_THICKNESS_ERROR":
        side = metadata.get("side") or reference.removeprefix("wall:")
        return f"{code}|{side}"

    if code == "ALIGNMENT_ERROR":
        if reference.startswith("wall:") and metadata.get("side"):
            return f"{code}|wall|{metadata['side']}"
        if reference.startswith("corner:"):
            return f"{code}|{reference}"
        return f"{code}|room"

    if code in ("ROOM_DIMENSION_ERROR", "DIMENSION_ERROR"):
        axis = metadata.get("axis")
        if axis:
            return f"{code}|{axis}"
        return f"{code}|{reference}"

    if code in ("MISSING_ELEMENT", "UNEXPECTED_ELEMENT"):
        kind = metadata.get("kind")
        if kind:
            return f"{code}|{kind}"
        axis = metadata.get("axis")
        if axis:
            return f"{code}|dimension|{axis}"
        return f"{code}|{reference}"

    return f"{code}|{reference}"


def _kind_from_code(code: str) -> str:
    return "door" if code.startswith("DOOR") else "window"


def _number_opening(
    drawing: StudentDrawing | None, opening_id: Any, kind: str | None
) -> str | None:
    """Which opening of its kind, in submission order, this is."""
    if drawing is None or opening_id is None:
        return None
    from app.geometry.wall import OpeningKind

    wanted = OpeningKind.DOOR if kind == "door" else OpeningKind.WINDOW
    same_kind = [opening for opening in drawing.openings if opening.kind is wanted]
    for index, opening in enumerate(same_kind):
        if str(opening.id) == str(opening_id):
            return str(index)
    return None


# --- The comparison ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AttemptProgress:
    """How this attempt compares with the one before it.

    ``remaining`` is the current verdict, in full. ``resolved`` and ``new`` are
    differences against the previous attempt, and they are stored as whole
    findings rather than codes, because "the north wall is now 2.3 mm too thick"
    is worth more to a student than "WALL_THICKNESS_ERROR resolved".

    ``changed`` is the case that a naive diff gets wrong in one direction or the
    other. A student who moves the north wall from 3 mm too thick to 5 mm too
    thick has neither fixed nor created anything: the same mistake is still
    there, with a different number. It stays in ``remaining`` and is reported
    as changed, so the student is told the truth ("still wrong, and different")
    instead of either a false credit or a false alarm.
    """

    attempt_number: int
    passed: bool
    completed: bool
    remaining: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    new: list[dict[str, Any]] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)
    remaining_count: int = 0
    resolved_count: int = 0
    new_count: int = 0
    changed_count: int = 0
    is_first_attempt: bool = True
    improved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "passed": self.passed,
            "completed": self.completed,
            "is_first_attempt": self.is_first_attempt,
            "improved": self.improved,
            "remaining_count": self.remaining_count,
            "resolved_count": self.resolved_count,
            "new_count": self.new_count,
            "changed_count": self.changed_count,
            "remaining": list(self.remaining),
            "resolved": list(self.resolved),
            "new": list(self.new),
            "changed": list(self.changed),
        }


def _num(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def compare_attempts(
    *,
    attempt_number: int,
    passed: bool,
    current: Sequence[Finding],
    previous: Sequence[Finding] | None,
    current_drawing: StudentDrawing | None = None,
    previous_drawing: StudentDrawing | None = None,
) -> AttemptProgress:
    """Compare a new verdict against the previous one.

    ``previous`` of ``None`` means this is the first attempt, and progress is
    reported as a baseline rather than as an improvement. Claiming improvement on
    the first attempt would be inventing a history.

    Every current finding lands in exactly one of resolved / changed / new, and
    ``remaining`` always equals the current verdict. Those two invariants are
    what keep the three buckets from double-counting a student who is simply
    still working.
    """
    remaining = [finding.to_dict() for finding in current]
    current_by_id = {finding_identity(f, current_drawing): f for f in current}

    if previous is None:
        return AttemptProgress(
            attempt_number=attempt_number,
            passed=passed,
            completed=passed,
            remaining=remaining,
            remaining_count=len(current),
            is_first_attempt=True,
            improved=False,
        )

    previous_by_id = {finding_identity(f, previous_drawing): f for f in previous}

    resolved: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []

    # Walk the current attempt in verdict order so the buckets read in the same
    # order a student would meet them in the issue list.
    for identity, finding in current_by_id.items():
        before = previous_by_id.get(identity)
        if before is None:
            new.append(finding.to_dict())
        elif _values_differ(before, finding):
            changed.append(finding.to_dict())

    for identity, finding in previous_by_id.items():
        if identity not in current_by_id:
            resolved.append(finding.to_dict())

    return AttemptProgress(
        attempt_number=attempt_number,
        passed=passed,
        completed=passed,
        remaining=remaining,
        resolved=resolved,
        new=new,
        changed=changed,
        remaining_count=len(current),
        resolved_count=len(resolved),
        new_count=len(new),
        changed_count=len(changed),
        is_first_attempt=False,
        improved=len(resolved) > 0 or (passed and len(previous) > 0),
    )


def _values_differ(before: Finding, after: Finding) -> bool:
    """True when the same issue is still present but the numbers moved.

    Compared on the numbers a student can see, not on the identity: a different
    expected value means the brief changed, and identical values with a changed
    difference means the drawing moved.
    """
    return (_num(before.expected), _num(before.actual), _num(before.difference)) != (
        _num(after.expected),
        _num(after.actual),
        _num(after.difference),
    )


def summarise_progress(
    attempts: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate an attempt history into a learning summary.

    ``attempts`` must be **oldest first**, which is the order
    :func:`app.attempts.repository.attempt_history` returns. The first and last
    rows are the baseline and the current state respectively, so getting this
    order wrong would report a student's improvement backwards.

    The foundation for adaptive learning: how many attempts, what recurs, and
    whether the student finished. Countable, no prose, no inference about the
    person beyond what the findings state.
    """
    rows = list(attempts)
    if not rows:
        return {
            "attempt_count": 0,
            "completed": False,
            "completion_attempt_number": None,
            "category_totals": {},
            "resolved_totals": {},
            "first_attempt_error_count": None,
            "final_error_count": None,
        }

    from app.learning.taxonomy import categories_of_dicts

    totals: dict[str, int] = {}
    resolved_totals: dict[str, int] = {}
    for row in rows:
        for category, count in (row.get("learning") or {}).get("categories", {}).items():
            totals[category] = totals.get(category, 0) + count
        # Stored findings are engine output, which carries no category: the
        # taxonomy is derived on read, so these counts reflect the current
        # mapping rather than whatever was in force when the attempt was made.
        for category in categories_of_dicts(
            row.get("progress", {}).get("resolved", [])
        ):
            resolved_totals[category.value] = (
                resolved_totals.get(category.value, 0) + 1
            )

    completion_attempt = next(
        (row.get("attempt_number") for row in rows if row.get("completed")), None
    )
    first = rows[0]
    final = rows[-1]

    return {
        "attempt_count": len(rows),
        "completed": completion_attempt is not None,
        "completion_attempt_number": completion_attempt,
        "category_totals": dict(sorted(totals.items())),
        "resolved_totals": dict(sorted(resolved_totals.items())),
        "first_attempt_error_count": first.get("summary", {}).get("error_count"),
        "final_error_count": final.get("summary", {}).get("error_count"),
    }
