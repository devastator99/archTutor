"""HTTP routes for the vertical slice: brief -> draw -> check -> correct.

Thin by rule: parse, delegate, serialise. No measurement, no geometry, no
validation logic in this file.

The only judgements exercised here are whether a request is well formed -- an
unknown exercise is a 404, an unreadable drawing a 422 -- and, in
:func:`submit_attempt`, how this attempt compares with the one before it, which
is delegated whole to :func:`app.learning.progress.compare_attempts`. Deciding
whether a drawing is *correct* is one call to :func:`validate_drawing`, and its
verdict is returned without modification. A route that adjusted a result would
make the stored result differ from the computed one, and the stored result is
the one a student would appeal against.

SYNCHRONOUS BY DESIGN
---------------------
The validate and attempt paths do no network I/O, so they are ordinary
synchronous handlers. The one outbound call in the product -- the tutor, on the
explain path -- is also synchronous, behind a short timeout and a deterministic
fallback. There is no queue, no worker and no background task, because at this
volume a queue would add latency, a failure mode and a deployment to remove them.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.attempts import repository as attempts_repository
from app.core.logging import get_logger, log_event, timed
from app.db.session import get_db
from app.exercises import repository
from app.geometry.drawing import DrawingFormatError, StudentDrawing
from app.learning.feedback import (
    build_feedback,
    concepts_for_exercise,
    feedback_from_stored,
)
from app.learning.progress import compare_attempts, summarise_progress
from app.learning.taxonomy import learning_record
from app.schemas.attempt import (
    AttemptCreate,
    FindingRead,
    ValidationSummaryRead,
    ValidateRequest,
    ValidateResponse,
)
from app.schemas.exercise import ExerciseListRead, ExerciseRead
from app.schemas.learning import (
    AttemptRead,
    ExplainRequest,
    ExplainResponse,
    ExerciseSummaryRead,
    IssueRead,
    TutorExplanationRead,
)
from app.tutor.service import explain_issue
from app.validation.engine import validate_drawing
from app.validation.tolerance import TolerancePolicy

router = APIRouter(prefix="/exercises", tags=["exercises"])
logger = get_logger("validation")


def _load_exercise(exercise_id: uuid.UUID, db: Session) -> ExerciseRead:
    exercise = repository.get_exercise(db, exercise_id)
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "exercise not found")
    return exercise


def _parse(payload: ValidateRequest) -> StudentDrawing:
    """Read the submitted drawing, or fail the request as malformed.

    ``StudentDrawing.from_dict`` is the one parser. Its errors name the offending
    field, which is a far more useful 422 body than a generic rejection.
    """
    try:
        return StudentDrawing.from_dict(payload.geometry)
    except DrawingFormatError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"malformed drawing: {exc}"
        ) from exc


def _policy(payload: ValidateRequest) -> TolerancePolicy:
    try:
        return TolerancePolicy.from_dict(
            payload.tolerance.to_policy_dict() if payload.tolerance else None
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid tolerance: {exc}"
        ) from exc


def _findings(result) -> list[FindingRead]:
    return [FindingRead.model_validate(f.to_dict()) for f in result.findings]


def _validate(exercise: ExerciseRead, drawing: StudentDrawing, policy: TolerancePolicy):
    """Run the engine, timed, and log how it went.

    The duration is the number that matters for the "must be fast" requirement,
    so it is measured on every call rather than inferred. Finding counts are
    logged because a spike means a content or engine change, not a student
    problem.
    """
    with timed(logger, "validation.completed", exercise_id=str(exercise.id)):
        result = validate_drawing(exercise, drawing, policy)
    log_event(
        logger,
        "validation.result",
        exercise_id=str(exercise.id),
        passed=result.passed,
        error_count=result.summary.error_count,
        total=result.summary.total,
    )
    return result


@router.get("", response_model=ExerciseListRead)
def list_exercises(
    limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
) -> ExerciseListRead:
    rows, total = repository.list_exercises(db, limit=limit, offset=offset)
    return ExerciseListRead(items=rows, total=total)


@router.get("/{exercise_id}", response_model=ExerciseRead)
def get_exercise(exercise_id: uuid.UUID, db: Session = Depends(get_db)) -> ExerciseRead:
    return _load_exercise(exercise_id, db)


@router.post("/{exercise_id}/validate", response_model=ValidateResponse)
def validate_exercise_drawing(
    exercise_id: uuid.UUID, payload: ValidateRequest, db: Session = Depends(get_db)
) -> ValidateResponse:
    """Check a drawing and return the verdict, without storing anything.

    The feedback panel is rendered from the same findings, so a dry run shows the
    student exactly what a stored attempt would -- there is no "preview" verdict
    that differs from the real one. Teaching is included too: a student who is
    only checking should not be told to learn less than one who is submitting.
    """
    exercise = _load_exercise(exercise_id, db)
    drawing = _parse(payload)
    result = _validate(exercise, drawing, _policy(payload))
    return ValidateResponse(
        exercise_id=exercise_id,
        passed=result.passed,
        findings=_findings(result),
        issues=[
            IssueRead.model_validate(issue.to_dict())
            for issue in build_feedback(result.findings, drawing=drawing)
        ],
        summary=ValidationSummaryRead.model_validate(result.summary.to_dict()),
        scale_denominator=result.scale_denominator,
        tolerance=result.tolerance,
    )


@router.post(
    "/{exercise_id}/attempts", response_model=AttemptRead, status_code=201
)
def submit_attempt(
    exercise_id: uuid.UUID, payload: AttemptCreate, db: Session = Depends(get_db)
) -> AttemptRead:
    """Store the drawing, the verdict it received, and how it compares.

    Validation runs before the insert and cannot be skipped, so every stored
    attempt has a real result attached to it. The comparison against the previous
    attempt is made here but is not judgement about the drawing: it is arithmetic
    over two stored results, and the drawing itself is never touched.

    The exercise row is locked before the attempt number is read, so two
    submissions landing at the same moment are numbered 1 and 2 rather than
    both 1. The unique index would catch the loser, but it can only do that by
    failing, and a student should not get an error for pressing Check twice.
    """
    exercise = _load_exercise(exercise_id, db)
    drawing = _parse(payload)
    result = _validate(exercise, drawing, _policy(payload))

    repository.lock_exercise(db, exercise_id)

    previous = attempts_repository.latest_attempt(db, exercise_id)
    previous_result, previous_drawing = _previous_findings(previous)

    progress = compare_attempts(
        attempt_number=previous.attempt_number + 1 if previous else 1,
        passed=result.passed,
        current=result.findings,
        previous=previous_result,
        current_drawing=drawing,
        # Without the previous drawing, every door finding on both sides would
        # share the "?" identity and two different doors would look like one
        # recurring mistake. The geometry is stored precisely so it can be
        # replayed here.
        previous_drawing=previous_drawing,
    )
    learning = learning_record(result.findings)

    with timed(
        logger, "attempts.completed", exercise_id=str(exercise_id)
    ) as outcome:
        attempt = attempts_repository.create_attempt(
            db,
            exercise_id=exercise_id,
            student_geometry=drawing.to_dict(),
            validation_result=result.to_dict(),
            attempt_number=progress.attempt_number,
            progress=progress.to_dict(),
            learning=learning,
            completed=result.passed,
            previous_attempt_id=previous.id if previous else None,
        )
    outcome["attempt_number"] = progress.attempt_number

    if result.passed:
        log_event(
            logger,
            "exercise.completed",
            exercise_id=str(exercise_id),
            attempt_number=progress.attempt_number,
            attempts_to_complete=progress.attempt_number,
            error_count=result.summary.error_count,
        )

    return AttemptRead.of(attempt, feedback_from_stored)


def _previous_findings(previous) -> tuple[tuple | None, StudentDrawing | None]:
    """Rehydrate the previous attempt for comparison: its findings and its drawing.

    Returns ``(None, None)`` for a first attempt so progress is reported as a
    baseline rather than as an improvement against a history that does not exist.
    A previous row whose geometry no longer parses still contributes its
    findings, just without the opening ordinals.
    """
    if previous is None or not previous.validation_result:
        return None, None
    return (
        _findings_from_dicts(previous.validation_result.get("findings", [])),
        _drawing_from_dicts(previous.student_geometry),
    )


def _drawing_from_dicts(payload: dict | None) -> StudentDrawing | None:
    """Rebuild a stored drawing, or ``None`` if it cannot be trusted.

    Opening identity depends on counting the openings in the drawing, so a
    geometry that no longer parses degrades the diff to a code-level comparison
    rather than failing the student's submission outright.
    """
    if not payload:
        return None
    try:
        return StudentDrawing.from_dict(payload)
    except DrawingFormatError:
        return None


def _findings_from_dicts(rows) -> tuple:
    from app.validation.codes import FindingCode, Severity
    from app.validation.findings import Finding

    rebuilt = []
    for row in rows:
        try:
            code = FindingCode(row["code"])
        except (KeyError, ValueError):
            # A stored finding whose code no longer exists must not break a
            # student's next submission. It is dropped from the comparison and
            # therefore cannot be claimed as resolved, which is the safe
            # direction to fail in.
            continue
        rebuilt.append(
            Finding(
                code=code,
                severity=Severity(row.get("severity", "ERROR")),
                message=row.get("message", ""),
                expected=row.get("expected"),
                actual=row.get("actual"),
                difference=row.get("difference"),
                unit=row.get("unit", "mm"),
                geometry_reference=row.get("geometry_reference"),
                metadata=row.get("metadata") or {},
            )
        )
    return tuple(rebuilt)


@router.get("/{exercise_id}/attempts", response_model=list[AttemptRead])
def list_attempts(
    exercise_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[AttemptRead]:
    _load_exercise(exercise_id, db)
    return [
        AttemptRead.of(row, feedback_from_stored)
        for row in attempts_repository.list_attempts(
            db, exercise_id, limit=limit, offset=offset
        )
    ]


@router.post(
    "/{exercise_id}/attempts/{attempt_id}/explain", response_model=ExplainResponse
)
def explain_attempt_issue(
    exercise_id: uuid.UUID,
    attempt_id: uuid.UUID,
    payload: ExplainRequest,
    db: Session = Depends(get_db),
) -> ExplainResponse:
    """Explain one issue from a stored attempt.

    Reads the stored result rather than revalidating, so the explanation always
    matches the attempt the student is looking at. Re-running validation here
    would risk explaining a different verdict than the one on screen if anything
    about the engine or the tolerance had changed since.
    """
    _load_exercise(exercise_id, db)
    attempt = attempts_repository.get_attempt(db, attempt_id)
    if attempt is None or attempt.exercise_id != exercise_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attempt not found")

    rows = (attempt.validation_result or {}).get("findings", [])
    if payload.issue_index >= len(rows):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"issue {payload.issue_index} not found; this attempt has "
            f"{len(rows)} issue(s)",
        )

    issue = IssueRead.model_validate(
        feedback_from_stored(rows[payload.issue_index]).to_dict()
    )
    explanation = explain_issue(issue.model_dump())

    return ExplainResponse(
        attempt_id=attempt.id,
        issue_index=payload.issue_index,
        issue=issue,
        tutor=TutorExplanationRead.model_validate(explanation.to_dict()),
    )


@router.get("/{exercise_id}/summary", response_model=ExerciseSummaryRead)
def exercise_summary(
    exercise_id: uuid.UUID, db: Session = Depends(get_db)
) -> ExerciseSummaryRead:
    """Aggregate learning across every attempt at this exercise."""
    exercise = _load_exercise(exercise_id, db)
    history = attempts_repository.attempt_history(db, exercise_id)
    summary = summarise_progress(history)
    # The concepts come from the brief, and every one of them is a fact the
    # validator has just confirmed by passing, so the completion screen can
    # state them without praising anything unverified.
    return ExerciseSummaryRead(
        exercise_id=exercise_id,
        concepts=concepts_for_exercise(exercise),
        **summary,
    )
