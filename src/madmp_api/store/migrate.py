"""Schema migrations: numbered SQL scripts applied on first database use.

The scripts live in ``madmp_api/store/sql`` as ``NNNN_description.sql`` and
use a ``{prefix}`` placeholder for the configured table prefix. Each is
applied once, in order, and recorded in ``<prefix>schema_migrations``.

The whole run is one transaction guarded by a Postgres advisory lock, so
several processes starting at once (workers, replicas, gateway instances)
migrate exactly once: the others wait, then find nothing left to apply.
DDL in Postgres is transactional, so a failing script leaves no trace.
"""

import zlib
from importlib.resources import files

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from madmp_api.store.models import row_model

_SQL_PACKAGE = 'madmp_api.store.sql'


def scripts() -> list[tuple[str, str]]:
    """``(version, sql)`` of every bundled script, in version order."""
    found = [
        (entry.name.split('_', 1)[0], entry.read_text(encoding='utf-8'))
        for entry in files(_SQL_PACKAGE).iterdir()
        if entry.name.endswith('.sql')
    ]
    return sorted(found)


def _lock_key(prefix: str) -> int:
    # A stable 32-bit key per prefix; fits pg_advisory_xact_lock(bigint).
    return zlib.crc32(f'madmp-api:{prefix}'.encode())


async def _apply(conn: AsyncConnection, prefix: str) -> list[str]:
    await conn.execute(
        text('SELECT pg_advisory_xact_lock(:key)'),
        {'key': _lock_key(prefix)},
    )
    # ``prefix`` is validated (TABLE_PREFIX_PATTERN), safe to interpolate.
    versions = f'{prefix}schema_migrations'
    await conn.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS {versions} ('
            'version text PRIMARY KEY, '
            'applied_at timestamptz NOT NULL DEFAULT now())',
        ),
    )
    select_sql = f'SELECT version FROM {versions}'  # ruff: ignore[hardcoded-sql-expression]
    insert_sql = f'INSERT INTO {versions} (version) VALUES (:version)'  # ruff: ignore[hardcoded-sql-expression]
    applied = set(await conn.scalars(text(select_sql)))
    raw = await conn.get_raw_connection()
    driver = raw.driver_connection
    if driver is None:
        msg = 'database connection is not available'
        raise RuntimeError(msg)
    done = []
    for version, sql in scripts():
        if version in applied:
            continue
        # asyncpg runs a parameterless multi-statement script as-is, inside
        # the transaction SQLAlchemy opened on this connection.
        await driver.execute(sql.replace('{prefix}', prefix))
        await conn.execute(
            text(insert_sql),
            {'version': version},
        )
        done.append(version)
    return done


async def upgrade(engine: AsyncEngine, prefix: str) -> list[str]:
    """Apply pending scripts; returns the versions applied now."""
    row_model(prefix)  # validates the prefix before it reaches any SQL
    async with engine.begin() as conn:
        return await _apply(conn, prefix)
