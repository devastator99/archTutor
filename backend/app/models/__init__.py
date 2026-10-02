"""ORM models.

Deliberately only two tables at this stage:

* ``Exercise``      -- the specification a student is asked to draw.
* ``ExerciseAttempt`` -- one student's submitted geometry and its validation
  result.

Geometry and validation results are stored as JSONB. The MVP does not
normalise them: the shapes are still moving, and a premature schema would
encode guesses about a domain the team has not finished modelling. PostGIS is
not used; the coordinates involved are a handful of wall segments.
"""

from __future__ import annotations

from app.models.attempt import ExerciseAttempt
from app.models.exercise import Exercise

__all__ = ["Exercise", "ExerciseAttempt"]
