"""Exercise domain module.

Owns the exercise specification's behaviour and persistence access, keeping it
out of the HTTP layer. Routes call in here; this module never knows about
``fastapi``.

Difficulty is a fixed property of an authored brief, not a computed one.
"""

from app.exercises.repository import (
    create_exercise,
    get_by_slug,
    get_exercise,
    get_many,
    list_exercises,
    upsert_exercise,
)

__all__ = [
    "create_exercise",
    "get_exercise",
    "get_by_slug",
    "get_many",
    "list_exercises",
    "upsert_exercise",
]
