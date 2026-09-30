"""Shared test fixtures.

Wizard is stubbed with respx (base URL ``http://dsw.test``); the intermediate
store uses the real Postgres from ``docker compose`` (skips if unreachable).
"""

import os

os.environ.setdefault("MADMP_API_WIZARD_URL", "http://dsw.test")
os.environ.setdefault("MADMP_API_WIZARD_DEFAULT_KM", "dsw:root:2.7.0")
os.environ.setdefault(
    "MADMP_API_DATABASE_URL",
    "postgresql+asyncpg://madmp:madmp@localhost:5440/madmp",
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from madmp_api.app import create_app  # noqa: E402
from madmp_api.config import Settings, load_settings  # noqa: E402
from madmp_api.store.db import get_session  # noqa: E402
from madmp_api.store import migrate  # noqa: E402
from madmp_api.store.models import row_model  # noqa: E402
from madmp_api.sync import service as sync_service  # noqa: E402
from tests.helpers import sample_dmp_document  # noqa: E402

# Tests configure themselves; never pick up a developer's local ``.env``.
Settings.model_config["env_file"] = None

# The default-prefix model every test app and repository test uses.
ROWS = row_model(load_settings().table_prefix)


@pytest.fixture
def make_document():
    return sample_dmp_document


@pytest.fixture
async def db_engine():
    # A fresh engine bound to the running test's event loop (asyncpg
    # connections cannot be shared across loops).
    engine = create_async_engine(load_settings().database_url)
    try:
        await migrate.upgrade(engine, load_settings().table_prefix)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {ROWS.__tablename__}"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"test database unavailable: {exc}")
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_summary_cache():
    sync_service._summary_cache.clear()
    yield
    sync_service._summary_cache.clear()


@pytest.fixture
def session_override(db_engine):
    """A ``get_session`` replacement bound to the test engine."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override_session():
        async with maker() as session:
            yield session

    return _override_session


@pytest.fixture
def make_client(session_override):
    """Build an API client for an app created with ``overrides``."""

    def _make(*, base_url="http://test", app=None, **overrides):
        if app is None:
            app = create_app(**overrides)
            app.dependency_overrides[get_session] = session_override
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url=base_url,
            headers={"Authorization": "Bearer test-token"},
        )

    return _make


@pytest.fixture
async def api_client(make_client):
    async with make_client() as client:
        yield client
