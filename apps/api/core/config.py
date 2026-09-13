"""
AIDSE Platform — Application Settings
Section 23.4: Configuration is environment-variable-driven via pydantic-settings.
All secrets are loaded from environment, never hardcoded.
"""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration.

    Values are loaded from environment variables (case-insensitive).
    In development, they are read from a .env file automatically.
    In production, they must be injected via the deployment environment.

    References: Section 13 (Security), Section 23.4 (Coding Standards)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    # Echo every SQL statement to the console — off by default (log noise)
    SQL_ECHO: bool = False
    # Run AutoML training in-process. This is the only way the desktop build
    # trains: the Celery worker it used to dispatch to needed a Redis broker,
    # which no desktop install has. Turned off in the test suite so creating an
    # experiment does not fit real models.
    LOCAL_TRAINING_FALLBACK: bool = True
    # Brute-force protection on auth endpoints (Section 13.6)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_REFRESH: str = "30/minute"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://aidse:aidse_dev_password@localhost:5432/aidse"
    )

    # ── JWT (RS256) ───────────────────────────────────────────────────────────
    # Paths to PEM files (resolved relative to repo root).
    # In production, set JWT_PRIVATE_KEY / JWT_PUBLIC_KEY env vars directly
    # containing the PEM content (with \n for line breaks).
    JWT_PRIVATE_KEY_PATH: str = "./keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = "./keys/public.pem"
    JWT_PRIVATE_KEY: str = ""   # Overrides path if set directly
    JWT_PUBLIC_KEY: str = ""    # Overrides path if set directly
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Security ─────────────────────────────────────────────────────────────
    BCRYPT_ROUNDS: int = 12
    SECRET_KEY: str = "change-me-in-production"  # Used for misc HMAC operations

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000"

    # ── LLM Provider (recommendation explanations, AI analyst) ──────────────
    # "none" keeps every feature fully functional with deterministic
    # template-based narration. No dataset rows are ever sent to a provider —
    # only aggregate profile statistics.
    LLM_PROVIDER: str = "none"  # none | openai | anthropic
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""         # provider default when empty
    LLM_BASE_URL: str = ""      # OpenAI-compatible override endpoint
    LLM_TIMEOUT_SECONDS: int = 20

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    def enforce_production_safety(self) -> None:
        """
        Fail-fast guard: refuse to boot in production with default/insecure
        secrets. Call from app startup (create_app / lifespan).
        """
        if self.APP_ENV != "production":
            return
        weak: list[str] = []
        if self.SECRET_KEY in ("change-me-in-production", "", None):
            weak.append("SECRET_KEY")
        if weak:
            raise RuntimeError(
                "Refusing to start in production with insecure defaults: "
                + ", ".join(weak)
                + ". Set real values via environment variables."
            )

    @property
    def jwt_private_key_pem(self) -> str:
        """Return private key PEM content (from env var or file)."""
        if self.JWT_PRIVATE_KEY:
            return self.JWT_PRIVATE_KEY.replace("\\n", "\n")
        path = Path(self.JWT_PRIVATE_KEY_PATH)
        if path.exists():
            return path.read_text()
        raise ValueError(
            "JWT private key not configured. "
            "Set JWT_PRIVATE_KEY env var or provide JWT_PRIVATE_KEY_PATH."
        )

    @property
    def jwt_public_key_pem(self) -> str:
        """Return public key PEM content (from env var or file)."""
        if self.JWT_PUBLIC_KEY:
            return self.JWT_PUBLIC_KEY.replace("\\n", "\n")
        path = Path(self.JWT_PUBLIC_KEY_PATH)
        if path.exists():
            return path.read_text()
        raise ValueError(
            "JWT public key not configured. "
            "Set JWT_PUBLIC_KEY env var or provide JWT_PUBLIC_KEY_PATH."
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton per process)."""
    if os.getenv("AIDSE_DESKTOP_MODE") == "1" and "DATABASE_URL" not in os.environ:
        from apps.api.core.storage import get_aidse_data_dir
        db_file = (get_aidse_data_dir() / "aidse.db").resolve()
        db_file_str = str(db_file).replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file_str}"
    return Settings()

