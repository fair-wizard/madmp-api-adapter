from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from madmp_api.api.errors import register_error_handlers
from madmp_api.api.routes import router
from madmp_api.config import load_settings
from madmp_api.store.db import Database


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Only runs standalone: a mounted sub-application (engine-gateway)
    # never receives lifespan events, so nothing here may be essential.
    # Migrating eagerly just makes a broken store fail at boot; otherwise
    # the first request migrates (see Database.ready).
    await app.state.database.ready()
    try:
        yield
    finally:
        await app.state.database.dispose()


def create_app(config_path: str | None = None, **overrides: object) -> FastAPI:
    """Build the adapter app.

    ``config_path`` and ``overrides`` let an engine-gateway configure a
    mount through its ``kwargs``; otherwise the environment is used.
    """
    settings = load_settings(config_path, **overrides)
    app = FastAPI(
        title='maDMP API',
        version='0.1.0',
        description='RDA Common maDMP API adapter for DSW / FAIR Wizard',
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.database = Database(
        settings.database_url,
        settings.table_prefix,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        # Bearer tokens travel in a header, never cookies: no credentialed
        # CORS, which with '*' would reflect any requesting origin.
        allow_credentials=False,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    register_error_handlers(app)
    app.include_router(router)
    return app
