"""Shared test setup.

Environment is pinned *before* any `app` module is imported, because
`app.core.config.settings` and the SQLAlchemy engine are built at import
time. In particular DATABASE_URL is always replaced: tests truncate every
tenant table between runs, so they must never be able to reach the dev
(Supabase) database from `.env`.

Database tests need TEST_DATABASE_URL (env var, or `.env.test` at the repo
root) pointing at a Postgres with pgvector whose database name contains
"test". Without it, DB tests are skipped and the pure unit tests still run.
See tests/README.md.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _database_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?", 1)[0]


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _read_env_file(
    REPO_ROOT / ".env.test"
).get("TEST_DATABASE_URL")
if TEST_DATABASE_URL and "test" not in _database_name(TEST_DATABASE_URL).lower():
    # the suite TRUNCATEs tables -- refuse anything that isn't obviously a
    # throwaway test database
    raise RuntimeError(
        f"TEST_DATABASE_URL must point at a database whose name contains 'test' "
        f"(got {_database_name(TEST_DATABASE_URL)!r})"
    )

# Port 1 on localhost: guaranteed-unreachable placeholder, so with no test DB
# configured an accidental DB access fails fast instead of hitting .env's DB.
_UNREACHABLE_DB = "postgresql+psycopg://unconfigured:unconfigured@127.0.0.1:1/unconfigured_test"

os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL or _UNREACHABLE_DB,
        # a non-working key: any code path that slips past the fakes and
        # tries OpenAI fails loudly instead of spending money
        "OPENAI_API_KEY": "sk-test-invalid-key",
        "EMBEDDING_DIMENSIONS": "1536",
        "JWT_SECRET": "test-jwt-secret-not-for-production",
        "JWT_ALGORITHM": "HS256",
        "BCRYPT_ROUNDS": "4",
        "SUPERADMIN_EMAIL": "superadmin@example.com",
        "SUPERADMIN_PASSWORD": "superadmin-test-password",
        "EMAIL_BACKEND": "console",
        "CLIENT_DASHBOARD_URL": "https://dashboard.example.com",
        "PROJECT_HOME": str(REPO_ROOT),
        # never trace test runs to LangSmith
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }
)
os.environ.pop("LANGSMITH_API_KEY", None)

# psycopg's async driver can't run on Windows' default Proactor loop (same
# reason as the policy in app/main.py)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# app imports only below this line --------------------------------------------

from fakes import CapturingEmailSender, fake_embed_texts  # noqa: E402
from sqlalchemy import text  # noqa: E402

# ---- offline guarantees -----------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _fake_embeddings():
    """Every embedding goes through the deterministic fake -- publish,
    retrieval, everything. Individual tests may re-patch to simulate an
    embedding failure."""
    from app.components.rag import hybrid_rag, naive_rag

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(hybrid_rag, "embed_texts", fake_embed_texts)
        mp.setattr(naive_rag, "embed_texts", fake_embed_texts)
        yield


@pytest.fixture(autouse=True)
def outbox(monkeypatch) -> list:
    """Captures every email the code under test sends, instead of logging
    or SMTP-ing it. Returns the list of SentEmail."""
    sender = CapturingEmailSender()
    from app.api.auth import router as auth_router
    from app.api.superadmin import tenants as superadmin_tenants
    from app.services import bot_tools

    monkeypatch.setattr(bot_tools, "get_email_sender", lambda: sender)
    monkeypatch.setattr(superadmin_tenants, "get_email_sender", lambda: sender)
    monkeypatch.setattr(auth_router, "_email_sender", sender)
    return sender.outbox


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """The bot's burst limiters are process-wide; start every test empty."""
    from app.services import rate_limit

    rate_limit.per_user.reset()
    rate_limit.per_tenant.reset()


# ---- database ---------------------------------------------------------------


def _ensure_database_exists(url: str) -> None:
    """CREATE DATABASE on first run, via the server's maintenance DB."""
    import psycopg

    plain = url.replace("postgresql+psycopg://", "postgresql://")
    name = _database_name(plain)
    maintenance = plain.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(maintenance, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Brings the test database to `alembic upgrade head` once per run --
    the real migrations, so a broken migration fails the suite too."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured (see tests/README.md)")

    from alembic import command
    from alembic.config import Config

    _ensure_database_exists(TEST_DATABASE_URL)
    # no ini file on purpose: env.py only runs logging.fileConfig when there
    # is one, and that would disable every logger created before it
    config = Config()
    config.set_main_option("script_location", str(REPO_ROOT / "database" / "alembic"))
    command.upgrade(config, "head")


async def _truncate_all() -> None:
    from app.db.session import engine

    # every tenant-owned table has an FK chain back to tenants, so CASCADE
    # clears the lot (alembic_version is untouched)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE tenants CASCADE"))


@pytest_asyncio.fixture(scope="session")
async def _engine(migrated_db):
    from app.db.session import engine

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_engine):
    """Request this (directly or via `session`/`client`) in any test that
    touches the database: starts and ends the test with empty tables and a
    cold settings cache."""
    from app.services import settings_resolver

    await _truncate_all()
    settings_resolver.invalidate()
    yield
    settings_resolver.invalidate()
    await _truncate_all()


@pytest_asyncio.fixture
async def session(db):
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client(db):
    """An httpx client wired straight into the FastAPI app (no network, no
    lifespan). The lifespan's Postgres checkpointer is replaced with an
    in-memory one."""
    import httpx
    from langgraph.checkpoint.memory import InMemorySaver

    from app.main import app

    app.state.checkpointer = InMemorySaver()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # tag every DB-backed test so `pytest -m "not db"` runs the offline set
    for item in items:
        if {"db", "session", "client"} & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.db)
