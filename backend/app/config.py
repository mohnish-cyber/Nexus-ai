"""Application configuration.

All configuration comes from environment variables (optionally loaded from a
`.env` file in the repository root or the backend directory). Secrets are never
hard-coded and never sent to the frontend - the frontend only ever learns
whether a given integration is *configured*.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [v.strip() for v in value if v and v.strip()]
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime -----------------------------------------------------------
    nexus_env: Literal["development", "production", "test"] = "development"
    nexus_host: str = "127.0.0.1"
    nexus_port: int = 8000
    log_level: str = "INFO"
    nexus_data_dir: Path = BACKEND_DIR / "data"
    # Used to encrypt secrets stored through the Settings UI. Auto-generated
    # (and persisted with 0600 permissions) in development if missing.
    nexus_secret_key: SecretStr | None = None
    default_timezone: str | None = None

    # --- Database ----------------------------------------------------------
    # SQLite for zero-config local use; point this at Supabase/PostgreSQL with
    # postgresql+asyncpg://user:pass@host:5432/db for production.
    database_url: str | None = None

    # --- Auth --------------------------------------------------------------
    # local:    single-user mode for a personal machine (binds to localhost,
    #           protected by Host + Origin checks).
    # supabase: multi-user mode; every request needs a Supabase access token.
    auth_mode: Literal["local", "supabase"] = "local"
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_jwt_secret: SecretStr | None = None
    supabase_jwt_audience: str = "authenticated"
    nexus_admin_emails: str = ""

    # --- HTTP security ------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    allowed_hosts: str = "localhost,127.0.0.1,[::1],testserver"
    rate_limit_chat_per_minute: int = 30
    rate_limit_default_per_minute: int = 240
    max_upload_mb: int = 25

    # --- AI provider -------------------------------------------------------
    ai_provider: Literal["anthropic", "openai_compatible", "mock"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    ai_model: str = "claude-opus-5"
    # Effort used for normal answers vs. fast internal routing/planning calls.
    ai_effort_default: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    ai_effort_routing: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    # Server-side refusal fallback (routes a declined request to Anthropic's
    # recommended fallback model instead of failing the turn).
    anthropic_refusal_fallback: bool = True
    ai_max_output_tokens: int = 16000
    openai_compat_base_url: str | None = None
    openai_compat_api_key: SecretStr | None = None
    openai_compat_model: str | None = None

    # --- Web search -------------------------------------------------------
    search_provider: Literal["auto", "tavily", "brave", "searxng"] = "auto"
    tavily_api_key: SecretStr | None = None
    brave_search_api_key: SecretStr | None = None
    searxng_url: str | None = None

    # --- Voice -------------------------------------------------------------
    stt_provider: Literal["auto", "openai", "local", "none"] = "auto"
    openai_api_key: SecretStr | None = None
    openai_stt_model: str = "whisper-1"
    local_whisper_model: str = "base"
    tts_provider: Literal["browser", "openai", "elevenlabs"] = "browser"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "nova"
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str | None = None

    # --- Computer / workspace ---------------------------------------------
    # None = enabled only in local auth mode (never let remote users drive the
    # server machine by default).
    computer_control_enabled: bool | None = None
    # Directories NEXUS may read (and, with approval, modify). Users can add
    # more from Settings in local mode.
    workspace_roots: str = ""

    # --- Background jobs ---------------------------------------------------
    # embedded: scheduler runs inside the API process (convenient for dev)
    # external: run `python -m app.worker` as a separate process
    scheduler_mode: Literal["embedded", "external", "disabled"] = "embedded"
    scheduler_poll_seconds: int = Field(default=20, ge=5, le=3600)

    # ----------------------------------------------------------------------
    @field_validator("nexus_data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()

    @property
    def is_production(self) -> bool:
        return self.nexus_env == "production"

    @property
    def is_test(self) -> bool:
        return self.nexus_env == "test"

    @property
    def cors_origin_list(self) -> list[str]:
        return _csv(self.cors_origins)

    @property
    def allowed_host_list(self) -> list[str]:
        return _csv(self.allowed_hosts)

    @property
    def admin_email_list(self) -> list[str]:
        return [e.lower() for e in _csv(self.nexus_admin_emails)]

    @property
    def workspace_root_list(self) -> list[Path]:
        return [Path(p).expanduser().resolve() for p in _csv(self.workspace_roots)]

    @property
    def computer_control(self) -> bool:
        if self.computer_control_enabled is None:
            return self.auth_mode == "local"
        return self.computer_control_enabled

    @property
    def uploads_dir(self) -> Path:
        return self.nexus_data_dir / "uploads"

    @property
    def screenshots_dir(self) -> Path:
        return self.nexus_data_dir / "screenshots"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            url = self.database_url
            # Supabase/Heroku style URLs -> async driver
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://") :]
            elif url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://") :]
            return url
        return f"sqlite+aiosqlite:///{self.nexus_data_dir / 'nexus.db'}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.nexus_data_dir, self.uploads_dir, self.screenshots_dir):
            d.mkdir(parents=True, exist_ok=True)
            try:
                d.chmod(0o700)
            except OSError:
                pass

    def secret_key(self) -> str:
        """Return the master key used to encrypt stored secrets.

        In production it must be provided. In development a random key is
        generated once and stored in the data directory with 0600 permissions.
        """
        if self.nexus_secret_key is not None:
            return self.nexus_secret_key.get_secret_value()
        if self.is_production:
            raise RuntimeError("NEXUS_SECRET_KEY must be set in production.")
        self.ensure_dirs()
        key_file = self.nexus_data_dir / ".secret_key"
        if key_file.exists():
            return key_file.read_text().strip()
        key = secrets.token_urlsafe(48)
        key_file.write_text(key)
        key_file.chmod(0o600)
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
