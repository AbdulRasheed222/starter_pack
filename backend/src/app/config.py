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

    # --- AI -------------------------------------------------------------------------------
    # "anthropic" (Claude), "openai" (any OpenAI-compatible server: OpenAI, Ollama, vLLM), or
    # "fake" (canned answers, no network; tests use it).
    ai_provider: str = "anthropic"
    ai_model: str = "claude-opus-5-5"
    # Claude only: low | medium | high | xhigh | max. Answering from a few passages rarely
    # needs more than low.
    ai_effort: str = "low"
    ai_max_tokens: int = 2048
    # Claude only: when a safety classifier declines, Anthropic re-runs the request on its
    # recommended fallback model instead of returning the refusal.
    ai_fallbacks: bool = True
    anthropic_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    # Prices in USD per million tokens, overriding the table in ai/pricing.py. Set both to 0
    # for a model you host yourself.
    ai_price_input_per_mtok: float | None = None
    ai_price_output_per_mtok: float | None = None
    # Spending cap per workspace per calendar month (UTC), unless the workspace has its own.
    ai_monthly_budget_usd: float = 5.0

    # Documents and retrieval. "fastembed" runs an open model on the CPU (downloaded on first
    # use); "hashing" matches words only and is for tests. Changing the model's dimension
    # needs a migration of the chunks.embedding column.
    embedder: str = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    embedding_cache_dir: str | None = None
    chunk_words: int = 220
    chunk_overlap_words: int = 40
    ai_passages: int = 6
    max_upload_mb: int = 10
    max_documents_per_workspace: int = 200

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
