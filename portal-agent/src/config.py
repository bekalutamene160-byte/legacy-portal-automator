"""
Legacy Portal Automator - Configuration Layer
=============================================

Loads settings from .env using pydantic-settings. Provides a singleton
`settings` object that the rest of the codebase imports.

Usage:
    from src.config import settings
    print(settings.groq_api_key.get_secret_value())  # SecretStr - never logged
    print(settings.groq_model)                        # plain string
    print(settings.headless)                          # bool

Design decisions:
- groq_api_key uses SecretStr so it NEVER appears in logs or repr output
- All fields have sensible defaults EXCEPT groq_api_key (required - fails fast)
- Settings are immutable at runtime (frozen=True) to prevent accidental mutation
- .env file is loaded from project root (two levels up from src/)
"""

from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root = two levels up from src/ (i.e., portal-agent/)
# .env file lives at the project root (legacy-portal-automator/.env)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from .env file.

    All fields can be overridden by environment variables (useful for CI/CD).
    Field names are case-insensitive (GROQ_API_KEY == groq_api_key).
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        frozen=True,  # Settings are immutable at runtime
        extra="ignore",  # Ignore unknown env vars (future-proof)
    )

    # === Groq API ===
    groq_api_key: SecretStr = Field(
        ...,
        description="Groq API key from https://console.groq.com/keys",
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model name (text-only by default)",
    )

    # === Browser Settings ===
    headless: bool = Field(
        default=True,
        description="Run browser invisibly (set False for demo video)",
    )
    use_vision: bool = Field(
        default=False,
        description="Use screenshot grounding (requires vision-capable model)",
    )

    # === Proxy (optional) ===
    proxy_url: str = Field(
        default="",
        description="Optional proxy URL (http://user:pass@host:port)",
    )

    # === Paths ===
    download_dir: str = Field(
        default="./downloads",
        description="Where downloaded files are saved",
    )

    # === Agent Limits ===
    max_steps: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Maximum agent actions per run (safety cap)",
    )
    agent_timeout: int = Field(
        default=180,
        ge=10,
        le=600,
        description="Hard timeout in seconds",
    )

    # === Demo Portal Settings ===
    portal_host: str = Field(default="localhost")
    portal_port: int = Field(default=8001, ge=1, le=65535)

    # === Validators ===
    @field_validator("groq_api_key")
    @classmethod
    def validate_groq_key(cls, v: SecretStr) -> SecretStr:
        """Ensure the API key is not the placeholder value."""
        value = v.get_secret_value()
        if not value or value == "your-groq-api-key-here":
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Copy .env.example to .env and paste your real Groq API key "
                "from https://console.groq.com/keys"
            )
        if not value.startswith("gsk_"):
            raise ValueError(
                f"GROQ_API_KEY should start with 'gsk_' (got '{value[:4]}...'). "
                "Verify you copied the key correctly from console.groq.com"
            )
        return v

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy(cls, v: str) -> str:
        """Empty string means no proxy; non-empty must look like a URL."""
        if not v:
            return v
        if not v.startswith(("http://", "https://", "socks5://")):
            raise ValueError(
                f"PROXY_URL must start with http://, https://, or socks5:// (got '{v}')"
            )
        return v

    # === Computed Properties ===
    @property
    def portal_url(self) -> str:
        """Full URL of the demo portal."""
        return f"http://{self.portal_host}:{self.portal_port}"

    @property
    def download_path(self) -> Path:
        """Download directory as a Path object (created on demand)."""
        p = Path(self.download_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


# Singleton instance - imported everywhere as `from src.config import settings`
settings = Settings()