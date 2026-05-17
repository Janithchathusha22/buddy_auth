from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


class MissingConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str | None = None
    supabase_jwt_audience: str = "authenticated"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )

    @property
    def auth_issuer(self) -> str:
        return f"{self.supabase_url}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.auth_issuer}/.well-known/jwks.json"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingConfigError(f"Missing required environment variable: {name}")
    return value


def _required_secret_env(name: str) -> str:
    value = _required_env(name)
    placeholders = {
        "your-service-role-key",
        "your-anon-or-publishable-key",
        "your-supabase-url",
    }
    if value in placeholders:
        raise MissingConfigError(
            f"{name} is still a placeholder. Replace it with the real Supabase value."
        )
    return value


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default

    return tuple(item.strip() for item in value.split(",") if item.strip())


def get_cors_origins() -> tuple[str, ...]:
    load_dotenv()

    return _csv_env(
        "CORS_ORIGINS",
        (
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ),
    )


@lru_cache
def get_settings() -> Settings:
    load_dotenv()

    return Settings(
        supabase_url=_required_env("SUPABASE_URL").rstrip("/"),
        supabase_anon_key=_required_secret_env("SUPABASE_ANON_KEY"),
        supabase_service_role_key=_required_secret_env("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET") or None,
        supabase_jwt_audience=os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"),
        cors_origins=get_cors_origins(),
    )
