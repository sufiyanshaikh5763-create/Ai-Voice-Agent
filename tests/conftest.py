"""Test setup. Requires PostgreSQL (composite FKs / JSONB): set TEST_DATABASE_URL."""
import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_calling_test")
from sqlalchemy.engine import make_url  # noqa: E402

database_name = make_url(os.environ["DATABASE_URL"]).database or ""
if not any(marker in database_name.lower() for marker in ("test", "ci")):
    raise RuntimeError("TEST_DATABASE_URL must target a database with 'test' or 'ci' in its name")

os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
os.environ["SARVAM_WEBHOOK_SECRET"] = "test-sarvam-webhook-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.helpers import seed_default_plans  # noqa: E402


def _reset_public_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _reset_public_schema()
    Base.metadata.create_all(engine)
    yield
    _reset_public_schema()


@pytest.fixture(autouse=True)
def _clean_tables(_schema):
    with SessionLocal() as session:
        seed_default_plans(session)

    yield

    with engine.begin() as conn:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))

    with SessionLocal() as session:
        seed_default_plans(session)


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def anyio_backend():
    return "asyncio"
