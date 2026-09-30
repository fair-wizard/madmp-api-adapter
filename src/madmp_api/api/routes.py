"""RDA common-madmp-api routes (the 5 operations over /dmps)."""

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from madmp_api.api.http import (
    http_date,
    negotiate_content_type,
    parse_http_date,
    require_supported_body,
)
from madmp_api.api.params import parse_list_params
from madmp_api.madmp.models import DMPDocument
from madmp_api.store.db import get_session
from madmp_api.store.models import MadmpRow, row_model
from madmp_api.sync.service import SyncService
from madmp_api.tenancy import resolve_tenant
from madmp_api.wizard.client import WizardClient

router = APIRouter()

AcceptHeader = Annotated[str | None, Header()]
ContentTypeHeader = Annotated[str | None, Header()]
IfUnmodifiedSince = Annotated[str | None, Header()]


async def get_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[SyncService]:
    settings = request.app.state.settings
    tenant = resolve_tenant(request, settings)
    authorization = request.headers.get('Authorization')
    client = WizardClient(tenant, authorization)
    try:
        yield SyncService(
            session,
            client,
            tenant,
            authorization,
            model=row_model(settings.table_prefix),
            list_cache_ttl_seconds=settings.list_cache_ttl_seconds,
        )
    finally:
        await client.aclose()


ServiceDep = Annotated[SyncService, Depends(get_service)]


def _with_id(row: MadmpRow) -> dict[str, Any]:
    return {'id': row.id, 'dmp': row.data}


def _document_response(row: MadmpRow, accept: str | None) -> JSONResponse:
    return JSONResponse(
        content=_with_id(row),
        media_type=negotiate_content_type(accept),
        headers={'Last-Modified': http_date(row.modified)},
    )


@router.get('/dmps')
async def list_dmps(
    request: Request,
    service: ServiceDep,
    accept: AcceptHeader = None,
) -> JSONResponse:
    content_type = negotiate_content_type(accept)
    params = parse_list_params(request.query_params)
    total, rows = await service.list_dmps(params)
    body = {
        'total_count': total,
        'items': [_with_id(row) for row in rows],
    }
    return JSONResponse(content=body, media_type=content_type)


@router.post('/dmps')
async def create_dmp(
    document: DMPDocument,
    service: ServiceDep,
    accept: AcceptHeader = None,
    content_type: ContentTypeHeader = None,
) -> JSONResponse:
    require_supported_body(content_type)
    row = await service.create_dmp(document)
    return _document_response(row, accept)


@router.get('/dmps/{dmp_id}')
async def get_dmp(
    dmp_id: str,
    service: ServiceDep,
    accept: AcceptHeader = None,
) -> JSONResponse:
    row = await service.get_dmp(dmp_id)
    return _document_response(row, accept)


@router.put('/dmps/{dmp_id}')
async def put_dmp(
    dmp_id: str,
    document: DMPDocument,
    service: ServiceDep,
    accept: AcceptHeader = None,
    content_type: ContentTypeHeader = None,
    if_unmodified_since: IfUnmodifiedSince = None,
) -> JSONResponse:
    require_supported_body(content_type)
    row = await service.overwrite_dmp(
        dmp_id,
        document,
        parse_http_date(if_unmodified_since),
    )
    return _document_response(row, accept)


@router.delete('/dmps/{dmp_id}', status_code=HTTPStatus.NO_CONTENT)
async def delete_dmp(dmp_id: str, service: ServiceDep) -> Response:
    await service.delete_dmp(dmp_id)
    return Response(status_code=HTTPStatus.NO_CONTENT)
