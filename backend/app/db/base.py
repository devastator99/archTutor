"""Declarative base for all SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class. Imported by Alembic autogenerate and by the models package."""
