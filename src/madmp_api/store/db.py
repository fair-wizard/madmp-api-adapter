"""Async SQLAlchemy engine/session wiring for the intermediate store.

The engine belongs to the application instance and is created lazily on
first use, so importing or mounting the app never touches the database.
That first use also migrates the schema: it is the one hook every
deployment has, as a mounted app (e.g. in an engine-gateway) never
receives startup events.
"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from madmp_api.store import migrate


class Database:
    def __init__(self, url: str, table_prefix: str) -> None:
        self._url = url
        self._table_prefix = table_prefix
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._ready = False
        self._lock = asyncio.Lock()

    def _engine_or_create(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(self._url)
        return self._engine

    async def ready(self) -> async_sessionmaker[AsyncSession]:
        """Return the sessionmaker, migrating the schema the first time."""
        if not self._ready:
            async with self._lock:
                if not self._ready:
                    engine = self._engine_or_create()
                    await migrate.upgrade(engine, self._table_prefix)
                    self._sessionmaker = async_sessionmaker(
                        engine,
                        expire_on_commit=False,
                    )
                    self._ready = True
        if self._sessionmaker is None:  # pragma: no cover - set above
            msg = 'database is not initialised'
            raise RuntimeError(msg)
        return self._sessionmaker

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None
        self._ready = False


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    database: Database = request.app.state.database
    session = (await database.ready())()
    try:
        yield session
    finally:
        await session.close()
