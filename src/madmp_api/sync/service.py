"""Orchestration between the RDA API, the Wizard backend and the store.

Reads are served from the materialised store but validated live against
the Wizard: the caller's visible project set is the authorisation
boundary, and a project's ``updatedAt`` is the cache-freshness key. Writes
go to the Wizard first, then the affected projection is refreshed
immediately (write-through).

Wizard exposes ``createdAt`` / ``updatedAt`` only on the project *list*
endpoint, so summaries are the single source for both authorisation and
freshness. A project that is reachable but absent from the list (an edge
case) is still served — it is simply re-mapped on every read.
"""

import time
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from madmp_api.errors import ConflictError, UpstreamError
from madmp_api.madmp.models import DMPDocument
from madmp_api.store import repository
from madmp_api.store.models import MadmpRow
from madmp_api.store.query import ListParams
from madmp_api.tenancy import Tenant
from madmp_api.transform.profiles import ProjectContext, get_profile
from madmp_api.wizard.client import ProjectSummary, WizardClient, km_identifier

# Per-(tenant, token) cache of the caller's visible project summaries.
_CacheKey = tuple[str, str]
_SummaryCacheEntry = tuple[float, list[ProjectSummary]]
_summary_cache: dict[_CacheKey, _SummaryCacheEntry] = {}


def _invalidate(key: _CacheKey) -> None:
    _summary_cache.pop(key, None)


class SyncService:
    def __init__(
        self,
        session: AsyncSession,
        client: WizardClient,
        tenant: Tenant,
        authorization: str | None,
        *,
        model: type[MadmpRow],
        list_cache_ttl_seconds: int = 30,
    ) -> None:
        self._session = session
        self._model = model
        self._client = client
        self._tenant = tenant
        self._cache_key = (tenant.key, authorization or '')
        self._cache_ttl = list_cache_ttl_seconds

    def _fresh(self, row: MadmpRow | None, upstream: datetime | None) -> bool:
        return (
            row is not None
            and upstream is not None
            and row.wizard_updated_at == upstream
            and row.id_base_url == self._tenant.dmp_id_base_url
        )

    async def _cached(self, dmp_id: str) -> MadmpRow | None:
        return await repository.get(
            self._session,
            self._model,
            self._tenant.key,
            dmp_id,
        )

    # --- projection ------------------------------------------------------

    async def _materialise(
        self,
        summary: ProjectSummary,
        user: dict,
    ) -> MadmpRow:
        uuid = summary.uuid
        settings = await self._client.get_settings(uuid)
        questionnaire = await self._client.get_questionnaire(uuid)
        # Project settings carry the *full* KM package; the copies embedded
        # in project list/create payloads omit organizationId and kmId.
        km_id = (
            km_identifier(settings.get('knowledgeModelPackage'))
            or summary.km_id
        )
        ctx = ProjectContext(
            uuid=uuid,
            settings=settings,
            questionnaire=questionnaire,
            user=user,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            dmp_id_base_url=self._tenant.dmp_id_base_url,
            default_language=self._tenant.default_language,
        )
        dmp = get_profile(km_id).to_dmp(ctx)
        await repository.upsert(
            self._session,
            self._model,
            tenant=self._tenant.key,
            dmp_id=uuid,
            dmp=dmp,
            id_base_url=self._tenant.dmp_id_base_url,
            wizard_project_uuid=uuid,
            wizard_updated_at=summary.updated_at or dmp.modified,
        )
        row = await self._cached(uuid)
        if row is None:
            msg = 'failed to persist maDMP projection'
            raise UpstreamError(msg)
        return row

    async def _summary_for(self, dmp_id: str) -> ProjectSummary:
        for summary in await self._visible_summaries():
            if summary.uuid == dmp_id:
                return summary
        # Not in the list: confirm access directly (raises 404/403) and
        # fall back to a timestamp-less summary, forcing a re-map.
        project = await self._client.get_project(dmp_id)
        return ProjectSummary(
            uuid=dmp_id,
            name=project.get('name', ''),
            description=project.get('description'),
            created_at=None,
            updated_at=None,
            km_id=km_identifier(project.get('knowledgeModelPackage')),
        )

    async def _refresh(self, dmp_id: str) -> MadmpRow:
        _invalidate(self._cache_key)
        summary = await self._summary_for(dmp_id)
        user = await self._client.current_user()
        return await self._materialise(summary, user)

    # --- reads -----------------------------------------------------------

    async def get_dmp(self, dmp_id: str) -> MadmpRow:
        summary = await self._summary_for(dmp_id)
        row = await self._cached(dmp_id)
        if self._fresh(row, summary.updated_at) and row is not None:
            return row
        user = await self._client.current_user()
        return await self._materialise(summary, user)

    async def _visible_summaries(self) -> list[ProjectSummary]:
        now = time.monotonic()
        cached = _summary_cache.get(self._cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]
        summaries = await self._client.list_summaries()
        _summary_cache[self._cache_key] = (now + self._cache_ttl, summaries)
        return summaries

    async def list_dmps(
        self,
        params: ListParams,
    ) -> tuple[int, list[MadmpRow]]:
        summaries = await self._visible_summaries()
        stale = [
            summary
            for summary in summaries
            if not self._fresh(
                await self._cached(summary.uuid),
                summary.updated_at,
            )
        ]
        if stale:
            user = await self._client.current_user()
            for summary in stale:
                await self._materialise(summary, user)
        params.allowed_ids = {summary.uuid for summary in summaries}
        return await repository.query(
            self._session,
            self._model,
            self._tenant.key,
            params,
        )

    # --- writes ----------------------------------------------------------

    async def create_dmp(self, document: DMPDocument) -> MadmpRow:
        package = await self._client.resolve_km_package(
            self._tenant.default_km,
        )
        created = await self._client.create_project(
            name=document.dmp.title,
            km_package_uuid=str(package['uuid']),
        )
        uuid = str(created['uuid'])
        write = get_profile(km_identifier(package)).to_write(document.dmp)
        await self._client.update_settings(uuid, write.settings_payload)
        await self._client.apply_events(uuid, write.events)
        return await self._refresh(uuid)

    async def overwrite_dmp(
        self,
        dmp_id: str,
        document: DMPDocument,
        if_unmodified_since: datetime | None,
    ) -> MadmpRow:
        summary = await self._summary_for(dmp_id)
        _guard_unmodified(summary.updated_at, if_unmodified_since)
        settings = await self._client.get_settings(dmp_id)
        km_id = km_identifier(settings.get('knowledgeModelPackage'))
        write = get_profile(km_id).to_write(document.dmp)
        await self._client.update_settings(dmp_id, write.settings_payload)
        await self._client.apply_events(dmp_id, write.events)
        return await self._refresh(dmp_id)

    async def delete_dmp(self, dmp_id: str) -> None:
        await self._client.delete_project(dmp_id)
        await repository.delete(
            self._session,
            self._model,
            self._tenant.key,
            dmp_id,
        )
        _invalidate(self._cache_key)


def _guard_unmodified(
    modified: datetime | None,
    if_unmodified_since: datetime | None,
) -> None:
    if if_unmodified_since is None or modified is None:
        return
    # HTTP dates carry whole-second resolution (RFC 9110), while Wizard
    # timestamps have sub-second precision. Compare at second granularity
    # so a client echoing back our own Last-Modified is never rejected.
    if modified.replace(microsecond=0) > if_unmodified_since:
        msg = 'the DMP was modified after If-Unmodified-Since'
        raise ConflictError(msg)
