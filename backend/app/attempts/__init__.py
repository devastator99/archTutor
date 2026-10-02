"""Attempt domain module.

Storage and retrieval only. Grading belongs to :mod:`app.validation` and
nothing else, so that an attempt cannot be persisted without a real verdict.
"""

from app.attempts.repository import create_attempt, get_attempt, list_attempts

__all__ = ["create_attempt", "get_attempt", "list_attempts"]
