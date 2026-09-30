"""Persistence + query logic for the materialised maDMP projection.

Every function takes the mapped ``model`` (see
:func:`madmp_api.store.models.row_model`), which carries the table name
for the configured prefix.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from madmp_api.madmp.models import DMPData, Host, Identifier
from madmp_api.store.models import MadmpRow
from madmp_api.store.query import ARRAY_FILTER_FIELDS, ListParams


def _ids(value: Identifier | list[Identifier]) -> list[str]:
    if isinstance(value, Identifier):
        return [value.identifier]
    return [item.identifier for item in value]


def _host_ids(host: Host | None) -> list[str]:
    if host is None or host.host_id is None:
        return []
    return [item.identifier for item in host.host_id]


def _index_fields(dmp: DMPData) -> dict[str, Any]:
    datasets = dmp.dataset
    distributions = [
        dist for ds in datasets for dist in (ds.distribution or [])
    ]
    fundings = [
        fund for proj in (dmp.project or []) for fund in (proj.funding or [])
    ]

    search_parts = [dmp.title, dmp.description or '']
    for ds in datasets:
        search_parts.extend([ds.title, ds.description or ''])
    for proj in dmp.project or []:
        search_parts.extend([proj.title, proj.description or ''])

    metadata_ids = [
        identifier
        for ds in datasets
        for meta in (ds.metadata or [])
        for identifier in _ids(meta.metadata_standard_id)
    ]

    return {
        'title': dmp.title,
        'description': dmp.description,
        'created': dmp.created,
        'modified': dmp.modified,
        'language': dmp.language,
        'ethical_issues_exist': str(dmp.ethical_issues_exist),
        'search_text': ' '.join(part for part in search_parts if part),
        'dataset_ids': [ds.dataset_id.identifier for ds in datasets],
        'contributor_ids': [
            identifier
            for con in (dmp.contributor or [])
            for identifier in _ids(con.contributor_id)
        ],
        'contact_ids': _ids(dmp.contact.contact_id),
        'dmp_ids': [dmp.dmp_id.identifier],
        'dmp_alternate_identifiers': [
            item.identifier for item in (dmp.alternate_identifier or [])
        ],
        'host_ids': [
            identifier
            for dist in distributions
            for identifier in _host_ids(dist.host)
        ],
        'funder_ids': [fund.funder_id.identifier for fund in fundings],
        'grant_ids': [
            fund.grant_id.identifier
            for fund in fundings
            if fund.grant_id is not None
        ],
        'metadata_standard_ids': metadata_ids,
        'license_refs': [
            lic.license_ref
            for dist in distributions
            for lic in (dist.license or [])
        ],
        'distribution_formats': [
            fmt for dist in distributions for fmt in (dist.format or [])
        ],
        'distribution_data_access': [
            str(dist.data_access) for dist in distributions
        ],
        'funding_status': [
            str(fund.funding_status)
            for fund in fundings
            if fund.funding_status is not None
        ],
        'dataset_personal_data': [str(ds.personal_data) for ds in datasets],
        'dataset_sensitive_data': [str(ds.sensitive_data) for ds in datasets],
    }


async def upsert(
    session: AsyncSession,
    model: type[MadmpRow],
    *,
    tenant: str,
    dmp_id: str,
    dmp: DMPData,
    id_base_url: str,
    wizard_project_uuid: str,
    wizard_updated_at: datetime,
) -> None:
    values: dict[str, Any] = {
        'tenant': tenant,
        'id': dmp_id,
        'id_base_url': id_base_url,
        'wizard_project_uuid': wizard_project_uuid,
        'wizard_updated_at': wizard_updated_at,
        'data': dmp.model_dump(mode='json'),
        **_index_fields(dmp),
    }
    stmt = pg_insert(model).values(**values)
    update_cols = {
        key: getattr(stmt.excluded, key)
        for key in values
        if key not in {'tenant', 'id'}
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[model.tenant, model.id],
        set_=update_cols,
    )
    await session.execute(stmt)
    await session.commit()


async def get(
    session: AsyncSession,
    model: type[MadmpRow],
    tenant: str,
    dmp_id: str,
) -> MadmpRow | None:
    # Upserts bypass the ORM, and sessions don't expire on commit, so a row
    # already in the identity map must be reloaded to see a fresh upsert.
    return await session.get(
        model,
        (tenant, dmp_id),
        populate_existing=True,
    )


async def delete(
    session: AsyncSession,
    model: type[MadmpRow],
    tenant: str,
    dmp_id: str,
) -> None:
    await session.execute(
        sa_delete(model).where(
            model.tenant == tenant,
            model.id == dmp_id,
        ),
    )
    await session.commit()


def _conditions(
    model: type[MadmpRow],
    tenant: str,
    params: ListParams,
) -> list[Any]:
    conditions: list[Any] = [model.tenant == tenant]
    if params.allowed_ids is not None:
        conditions.append(model.id.in_(params.allowed_ids))
    if params.created_before is not None:
        conditions.append(model.created <= params.created_before)
    if params.created_after is not None:
        conditions.append(model.created > params.created_after)
    if params.modified_before is not None:
        conditions.append(model.modified <= params.modified_before)
    if params.modified_after is not None:
        conditions.append(model.modified > params.modified_after)
    if params.languages:
        conditions.append(model.language.in_(params.languages))
    if params.ethical_issues_exist:
        conditions.append(
            model.ethical_issues_exist.in_(params.ethical_issues_exist),
        )
    for name in ARRAY_FILTER_FIELDS:
        values = getattr(params, name)
        if values:
            conditions.append(getattr(model, name).overlap(values))
    if params.query:
        tsv = func.to_tsvector('simple', model.search_text)
        conditions.append(
            or_(
                *(
                    tsv.op('@@')(func.websearch_to_tsquery('simple', term))
                    for term in params.query
                ),
            ),
        )
    return conditions


def _order_by(model: type[MadmpRow], params: ListParams) -> list[Any]:
    order: list[Any] = []
    for field_name, direction in params.sort:
        # Sort fields are validated against SORT_FIELDS (column names).
        column = getattr(model, field_name)
        order.append(
            column.desc() if direction == 'desc' else column.asc(),
        )
    if not order:
        order.append(model.created.desc())
    return order


async def query(
    session: AsyncSession,
    model: type[MadmpRow],
    tenant: str,
    params: ListParams,
) -> tuple[int, list[MadmpRow]]:
    conditions = _conditions(model, tenant, params)
    total = await session.scalar(
        select(func.count()).select_from(model).where(*conditions),
    )
    result = await session.scalars(
        select(model)
        .where(*conditions)
        .order_by(*_order_by(model, params))
        .offset(params.offset)
        .limit(params.count),
    )
    return total or 0, list(result.all())
