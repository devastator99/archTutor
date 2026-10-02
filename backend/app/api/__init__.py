"""HTTP layer: routers only. No domain logic lives here."""

from app.api.routes import exercises, health

__all__ = ["health", "exercises"]
