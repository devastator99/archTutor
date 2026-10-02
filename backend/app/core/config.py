from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database -------------------------------------------------------
    postgres_user: str = "archtutor"
    postgres_password: str = "archtutor"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "archtutor"

    # --- HTTP -----------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # --- Tutor (LLM) ---------------------------------------------------
    # OpenAI-compatible endpoint. No default provider is assumed: the tutor
    # service falls back to a deterministic offline explainer when unset.
    tutor_base_url: str | None = None
    tutor_api_key: str | None = None
    tutor_model: str | None = None
    # Optional. Sent as ``reasoning_effort`` to reasoning models (Groq's
    # gpt-oss family, OpenAI's o-series). "low" is what a tutor wants: the work
    # of reasoning about a wall thickness was done by the validator, and the
    # budget belongs to the sentence the student reads. Leave unset for
    # providers that would reject the field -- an unknown parameter is a 400,
    # and a 400 falls back to the deterministic explanation.
    tutor_reasoning_effort: str | None = None

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
