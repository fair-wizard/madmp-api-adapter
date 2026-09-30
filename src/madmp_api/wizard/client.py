"""Async httpx client for the DSW / FAIR Wizard ``wizard-api``.

The caller's ``Authorization`` header is forwarded verbatim (per-user
pass-through), so every call acts as the authenticated Wizard user. Wizard HTTP
error statuses are translated into the adapter error hierarchy.

Shapes here were verified against a live Wizard 4.33 instance (see
``example/``). Two quirks drive the design:

* ``createdAt`` / ``updatedAt`` are exposed **only by the project list**
  endpoint — neither ``GET /projects/{uuid}`` nor ``.../settings`` carries
  them, so the list is the sole source of cache-freshness timestamps.
* Errors nest ``message`` as an object (``code`` / ``defaultMessage``).

In multi-tenant deployments the tenant's public host is sent as ``Host``
(see :mod:`madmp_api.tenancy`), which is all Wizard uses to pick the tenant.
"""

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Self

import httpx

from madmp_api.errors import (
    AuthenticationRequiredError,
    ConflictError,
    DMPNotFoundError,
    InsufficientPermissionsError,
    UpstreamError,
)
from madmp_api.tenancy import Tenant

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_CONFLICT = 409
_PAGE_SIZE = 100
_UUID_LENGTH = 36
_UUID_DASHES = 4
# Wizard's own 404 text embeds tenant/uuid internals; keep them out of the
# public RDA response.
_NOT_FOUND_MESSAGE = 'the requested DMP does not exist'


@dataclass
class ProjectSummary:
    uuid: str
    name: str
    description: str | None
    created_at: datetime | None
    updated_at: datetime | None
    km_id: str | None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def km_identifier(package: dict[str, Any] | None) -> str | None:
    """Build the ``org:kmId:version`` identifier of a KM package."""
    if not package:
        return None
    org = package.get('organizationId')
    km_id = package.get('kmId')
    version = package.get('version')
    if not (org and km_id and version):
        return None
    return f'{org}:{km_id}:{version}'


def _summary(project: dict[str, Any]) -> ProjectSummary:
    return ProjectSummary(
        uuid=project['uuid'],
        name=project.get('name', ''),
        description=project.get('description'),
        created_at=parse_dt(project.get('createdAt')),
        updated_at=parse_dt(project.get('updatedAt')),
        km_id=km_identifier(project.get('knowledgeModelPackage')),
    )


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if not isinstance(body, dict):
        return str(body)
    message = body.get('message')
    if isinstance(message, dict):
        template = message.get('defaultMessage')
        params = message.get('params')
        if isinstance(template, str) and isinstance(params, list):
            try:
                return template % tuple(params)
            except TypeError:
                return template
        return str(template or message.get('code') or message)
    return str(message or body.get('error') or body)


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    status = response.status_code
    detail = _detail(response)
    if status == _HTTP_UNAUTHORIZED:
        raise AuthenticationRequiredError(detail)
    if status == _HTTP_FORBIDDEN:
        raise InsufficientPermissionsError(detail)
    if status == _HTTP_NOT_FOUND:
        raise DMPNotFoundError(_NOT_FOUND_MESSAGE)
    if status == _HTTP_CONFLICT:
        raise ConflictError(detail)
    msg = f'Wizard responded {status}: {detail}'
    raise UpstreamError(msg)


class WizardClient:
    def __init__(self, tenant: Tenant, authorization: str | None) -> None:
        headers = {'Authorization': authorization} if authorization else {}
        if tenant.upstream_host:
            headers['Host'] = tenant.upstream_host
        self._client = httpx.AsyncClient(
            base_url=tenant.api_url,
            headers=headers,
            timeout=tenant.request_timeout_seconds,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        json: object | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method,
                url,
                params=params,
                json=json,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(str(exc)) from exc
        _raise_for_status(response)
        return response

    async def current_user(self) -> dict[str, Any]:
        response = await self._request('GET', '/users/current')
        return response.json()

    async def list_projects(
        self,
        *,
        page: int = 0,
        size: int = _PAGE_SIZE,
        sort: str = 'updatedAt,desc',
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            'page': page,
            'size': size,
            'sort': sort,
        }
        response = await self._request('GET', '/projects', params=params)
        return response.json()

    async def list_summaries(self) -> list[ProjectSummary]:
        summaries: list[ProjectSummary] = []
        page = 0
        while True:
            data = await self.list_projects(page=page)
            projects = data.get('_embedded', {}).get('projects', [])
            summaries.extend(_summary(proj) for proj in projects)
            total_pages = data.get('page', {}).get('totalPages', 1)
            if not projects or page + 1 >= total_pages:
                break
            page += 1
        return summaries

    async def get_project(self, uuid: str) -> dict[str, Any]:
        """Fetch a single project; raises 404/403 when inaccessible."""
        response = await self._request('GET', f'/projects/{uuid}')
        return response.json()

    async def get_settings(self, uuid: str) -> dict[str, Any]:
        response = await self._request('GET', f'/projects/{uuid}/settings')
        return response.json()

    async def get_questionnaire(self, uuid: str) -> dict[str, Any]:
        response = await self._request(
            'GET',
            f'/projects/{uuid}/questionnaire',
        )
        return response.json()

    async def resolve_km_package(self, reference: str) -> dict[str, Any]:
        """Look up a KM package by UUID or ``org:kmId:version`` id.

        Returns the full package (unlike the trimmed variant embedded in
        project payloads, which omits ``organizationId`` / ``kmId``).
        """
        is_uuid = (
            len(reference) == _UUID_LENGTH
            and reference.count('-') == _UUID_DASHES
        )
        response = await self._request(
            'GET',
            '/knowledge-model-packages',
            params={'size': _PAGE_SIZE},
        )
        packages = (
            response.json()
            .get('_embedded', {})
            .get('knowledgeModelPackages', [])
        )
        for package in packages:
            matches = (
                str(package.get('uuid')) == reference
                if is_uuid
                else km_identifier(package) == reference
            )
            if matches:
                return package
        msg = f'knowledge model package not found: {reference}'
        raise UpstreamError(msg)

    async def create_project(
        self,
        *,
        name: str,
        km_package_uuid: str,
    ) -> dict[str, Any]:
        payload = {
            'name': name,
            'knowledgeModelPackageUuid': km_package_uuid,
            'questionTagUuids': [],
            'sharing': 'RestrictedProjectSharing',
            'visibility': 'PrivateProjectVisibility',
        }
        response = await self._request('POST', '/projects', json=payload)
        return response.json()

    async def update_settings(
        self,
        uuid: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            'PUT',
            f'/projects/{uuid}/settings',
            json=payload,
        )
        return response.json()

    async def apply_events(
        self,
        uuid: str,
        events: list[dict[str, Any]],
    ) -> None:
        """Apply questionnaire reply events in a single batch."""
        if not events:
            return
        await self._request(
            'PUT',
            f'/projects/{uuid}/content',
            json={'events': events},
        )

    async def delete_project(self, uuid: str) -> None:
        await self._request('DELETE', f'/projects/{uuid}')
