"""ArchTutor backend.

Layering, outermost first: ``api`` (HTTP) -> domain modules (``exercises``,
``validation``, ``tutor``) -> ``geometry`` / ``measurement`` (deterministic
core) -> ``db`` (persistence). Dependencies point inward only.
"""
