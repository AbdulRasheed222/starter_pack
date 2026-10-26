import os

# Settings and the database engine are created at import time, so the test environment must be
# in place before any app module is imported. Tests run on Postgres, like production; start it
# with `docker compose up -d` from the repository root.
os.environ.update(
    {
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app_test"
        ),
        "ENVIRONMENT": "development",
        "CLERK_ISSUER": "https://clerk.example.test",
        "CORS_ORIGINS": "http://localhost:3000",
        "SITE_URL": "http://localhost:3000",
        # No network in tests: canned answers and word-matching embeddings.
        "AI_PROVIDER": "fake",
        "EMBEDDER": "hashing",
        "AI_MONTHLY_BUDGET_USD": "5",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import auth, models  # noqa: E402, F401
from app.api import app  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from tests.support import KEY  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clerk_keys(monkeypatch):
    """Tokens in tests are signed with a local key instead of Clerk's."""
    monkeypatch.setattr(auth, "signing_key", lambda settings, token: KEY.public_key())


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s
