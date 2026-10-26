from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" relaxes checks that need real secrets; anything else enforces them.
    environment: str = "development"

    # Postgres everywhere, tests included, so what passes locally passes in production.
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"

    # Origins allowed to call the API from a browser, comma separated. Sign-in tokens must also
    # have been issued to one of these.
    cors_origins: str = "http://localhost:3000"
    # The web app, for links such as invites.
    site_url: str = "http://localhost:3000"

    # Clerk's Frontend API URL, e.g. https://clerk.example.com. Its keys are read from
    # <issuer>/.well-known/jwks.json. Unset means nobody can sign in.
    clerk_issuer: str | None = None

    max_workspaces_per_user: int = 5
    invite_days: int = 7
    # Accept an invite only when the signed-in email matches the invited one. Needs an "email"
    # claim in Clerk's session token (see docs/clerk.md). Turning it off makes the invite link
    # alone enough to join, so anyone it is forwarded to can use it.
    invite_requires_email_match: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
