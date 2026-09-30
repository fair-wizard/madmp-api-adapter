"""SQLAlchemy ORM model for the materialised maDMP projection.

The adapter shares the default schema with whatever else lives in its
database (the Wizard, other gateway apps), so every object it creates is
named with the configurable ``table_prefix``: the table is
``<prefix>dmp`` and the migration log ``<prefix>schema_migrations``
(created by :mod:`madmp_api.store.migrate`).
:func:`row_model` maps :class:`MadmpRow` onto the prefixed table.
"""

import re
from datetime import datetime
from functools import cache
from typing import Any

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from madmp_api.config import TABLE_PREFIX_PATTERN


class Base(DeclarativeBase):
    pass


def _array() -> Mapped[list[str]]:
    return mapped_column(ARRAY(Text), nullable=False, default=list)


_TABLE = 'dmp'


def table_name(prefix: str) -> str:
    return f'{prefix}{_TABLE}'


class MadmpRow(Base):
    """One materialised maDMP document plus denormalised filter columns.

    ``data`` holds the canonical maDMP ``dmp`` object (served wrapped as
    ``{id, dmp: data}``). Every other column is derived from ``data`` at
    upsert time to support the RDA list filters/sort without scanning the
    JSONB on each query.

    Rows are keyed by ``(tenant, id)``: ``tenant`` is the Wizard tenant host
    (empty in single-tenant mode). ``id_base_url`` records the DMP id base
    the document was synthesised with, so a row built for another public
    URL is re-mapped instead of served with foreign identifiers.

    Abstract: use :func:`row_model` for the class mapped to a table.
    """

    __abstract__ = True

    tenant: Mapped[str] = mapped_column(Text, primary_key=True, default='')
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    id_base_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default='',
    )
    wizard_project_uuid: Mapped[str] = mapped_column(
        Text,
        index=True,
        nullable=False,
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Scalar / sortable fields
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(Text, nullable=False)
    ethical_issues_exist: Mapped[str] = mapped_column(Text, nullable=False)
    wizard_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default='',
    )

    # Array filter columns (GIN-indexed in the migration)
    dataset_ids: Mapped[list[str]] = _array()
    contributor_ids: Mapped[list[str]] = _array()
    contact_ids: Mapped[list[str]] = _array()
    dmp_ids: Mapped[list[str]] = _array()
    dmp_alternate_identifiers: Mapped[list[str]] = _array()
    host_ids: Mapped[list[str]] = _array()
    funder_ids: Mapped[list[str]] = _array()
    grant_ids: Mapped[list[str]] = _array()
    metadata_standard_ids: Mapped[list[str]] = _array()
    license_refs: Mapped[list[str]] = _array()
    distribution_formats: Mapped[list[str]] = _array()
    distribution_data_access: Mapped[list[str]] = _array()
    funding_status: Mapped[list[str]] = _array()
    dataset_personal_data: Mapped[list[str]] = _array()
    dataset_sensitive_data: Mapped[list[str]] = _array()


@cache
def row_model(prefix: str) -> type[MadmpRow]:
    """The :class:`MadmpRow` subclass mapped to ``<prefix>dmp``."""
    if not re.match(TABLE_PREFIX_PATTERN, prefix):
        msg = f'invalid table prefix: {prefix!r}'
        raise ValueError(msg)
    return type(
        f'MadmpRow_{prefix or "unprefixed"}',
        (MadmpRow,),
        {'__tablename__': table_name(prefix)},
    )
