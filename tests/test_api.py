"""End-to-end API tests: real Postgres store + respx-stubbed Wizard."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker

from madmp_api.madmp.models import DMPData
from madmp_api.store import repository
from tests.conftest import ROWS
from tests.helpers import WIZARD_BASE, sample_dmp_document

pytestmark = pytest.mark.asyncio

_USER = {
    'uuid': 'u1',
    'firstName': 'Ada',
    'lastName': 'Lovelace',
    'email': 'ada@example.org',
}
# Wizard returns the *full* package only from /knowledge-model-packages and
# project settings; project list/create payloads carry a trimmed copy
# without organizationId/kmId. Profile selection must cope with both.
_KM = {
    'uuid': 'km-uuid-1',
    'name': 'Common DSW Knowledge Model',
    'organizationId': 'dsw',
    'kmId': 'root',
    'version': '2.7.0',
}
_KM_SIMPLE = {
    'uuid': 'km-uuid-1',
    'name': 'Common DSW Knowledge Model',
    'version': '2.7.0',
}
_UPDATED = '2024-06-01T00:00:00+00:00'


def _project(uuid: str, updated_at: str = _UPDATED) -> dict:
    return {
        'uuid': uuid,
        'name': f'Project {uuid}',
        'description': 'desc',
        'createdAt': '2024-01-01T00:00:00+00:00',
        'updatedAt': updated_at,
        'knowledgeModelPackage': _KM_SIMPLE,
    }


def _mock_wizard(
    mock: respx.Router,
    *,
    projects: list[dict] | None = None,
) -> None:
    """Stub the full Wizard surface the adapter touches."""
    projects = projects if projects is not None else []
    mock.get(f'{WIZARD_BASE}/users/current').mock(
        return_value=httpx.Response(200, json=_USER),
    )
    mock.get(f'{WIZARD_BASE}/projects').mock(
        return_value=httpx.Response(
            200,
            json={
                '_embedded': {'projects': projects},
                'page': {
                    'size': 100,
                    'totalElements': len(projects),
                    'totalPages': 1,
                    'number': 0,
                },
            },
        ),
    )
    for proj in projects:
        uuid = proj['uuid']
        mock.get(f'{WIZARD_BASE}/projects/{uuid}/settings').mock(
            return_value=httpx.Response(
                200,
                json={
                    'name': proj['name'],
                    'description': proj.get('description'),
                    'knowledgeModelPackage': _KM,
                },
            ),
        )
        mock.get(f'{WIZARD_BASE}/projects/{uuid}/questionnaire').mock(
            return_value=httpx.Response(200, json={'replies': {}}),
        )


async def test_list_materialises_and_authorises(api_client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[_project('p1'), _project('p2')])
        resp = await api_client.get('/dmps')

    assert resp.status_code == 200
    body = resp.json()
    assert body['total_count'] == 2
    assert {item['id'] for item in body['items']} == {'p1', 'p2'}
    assert all('dmp' in item for item in body['items'])
    # created/modified come from the project list timestamps.
    first = body['items'][0]['dmp']
    assert first['created'].startswith('2024-01-01')


async def test_list_excludes_non_visible_cached_rows(api_client, db_engine):
    # Pre-seed a projection the caller is NOT authorised to see.
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        await repository.upsert(
            session,
            ROWS,
            tenant='',
            dmp_id='secret',
            dmp=DMPData.model_validate(sample_dmp_document()['dmp']),
            id_base_url='http://test/dmps',
            wizard_project_uuid='secret',
            wizard_updated_at=datetime(2024, 6, 1, tzinfo=UTC),
        )

    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[_project('p1')])
        resp = await api_client.get('/dmps')

    ids = {item['id'] for item in resp.json()['items']}
    assert ids == {'p1'}


async def test_get_returns_last_modified(api_client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[_project('p1')])
        resp = await api_client.get('/dmps/p1')

    assert resp.status_code == 200
    assert 'Last-Modified' in resp.headers
    assert resp.json()['id'] == 'p1'


async def test_get_not_found(api_client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[])
        # Absent from the list -> direct lookup decides; Wizard says 404.
        mock.get(f'{WIZARD_BASE}/projects/missing').mock(
            return_value=httpx.Response(
                404,
                json={
                    'message': {
                        'code': 'error.database.entity_not_found',
                        'defaultMessage': 'does not exist',
                    },
                    'status': 404,
                },
            ),
        )
        resp = await api_client.get('/dmps/missing')

    assert resp.status_code == 404
    assert resp.json()['error_code'] == 'dmp_not_found'
    # The nested Wizard message object is unwrapped, not stringified as a dict.
    assert '{' not in resp.json()['error_message']


async def test_create_round_trip(api_client, make_document):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[_project('new-1')])
        mock.get(f'{WIZARD_BASE}/knowledge-model-packages').mock(
            return_value=httpx.Response(
                200,
                json={'_embedded': {'knowledgeModelPackages': [_KM]}},
            ),
        )
        create = mock.post(f'{WIZARD_BASE}/projects').mock(
            return_value=httpx.Response(
                201,
                json={'uuid': 'new-1', 'knowledgeModelPackage': _KM_SIMPLE},
            ),
        )
        settings = mock.put(f'{WIZARD_BASE}/projects/new-1/settings').mock(
            return_value=httpx.Response(200, json={}),
        )
        content = mock.put(f'{WIZARD_BASE}/projects/new-1/content').mock(
            return_value=httpx.Response(200, json={}),
        )
        resp = await api_client.post('/dmps', json=make_document())

    assert resp.status_code == 200
    assert resp.json()['id'] == 'new-1'
    assert settings.called
    # Reply events are pushed for the dsw:root knowledge model.
    assert content.called
    body = create.calls[0].request.read().decode()
    assert 'knowledgeModelPackageUuid' in body


async def test_put_conflict_on_stale_precondition(api_client, make_document):
    with respx.mock(assert_all_called=False) as mock:
        # Wizard says the project changed in June 2024...
        _mock_wizard(mock, projects=[_project('p1')])
        # ...but the client claims it was unmodified since January.
        resp = await api_client.put(
            '/dmps/p1',
            json=make_document(),
            headers={'If-Unmodified-Since': 'Mon, 01 Jan 2024 00:00:00 GMT'},
        )

    assert resp.status_code == 409
    assert resp.json()['error_code'] == 'conflict'


async def test_put_accepts_echoed_last_modified(api_client, make_document):
    """A client echoing our own Last-Modified must not hit a 409.

    Wizard timestamps carry microseconds while HTTP dates are whole seconds,
    so the precondition has to be compared at second granularity.
    """
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(
            mock,
            projects=[
                _project('p1', updated_at='2024-06-01T10:00:00.654321+00:00')
            ],
        )
        mock.put(f'{WIZARD_BASE}/projects/p1/settings').mock(
            return_value=httpx.Response(200, json={}),
        )
        mock.put(f'{WIZARD_BASE}/projects/p1/content').mock(
            return_value=httpx.Response(200, json={}),
        )
        get_resp = await api_client.get('/dmps/p1')
        last_modified = get_resp.headers['Last-Modified']
        resp = await api_client.put(
            '/dmps/p1',
            json=make_document(),
            headers={'If-Unmodified-Since': last_modified},
        )

    assert resp.status_code == 200


async def test_put_succeeds_with_fresh_precondition(api_client, make_document):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[_project('p1')])
        mock.put(f'{WIZARD_BASE}/projects/p1/settings').mock(
            return_value=httpx.Response(200, json={}),
        )
        mock.put(f'{WIZARD_BASE}/projects/p1/content').mock(
            return_value=httpx.Response(200, json={}),
        )
        resp = await api_client.put(
            '/dmps/p1',
            json=make_document(),
            headers={'If-Unmodified-Since': 'Tue, 01 Jul 2025 00:00:00 GMT'},
        )

    assert resp.status_code == 200
    assert resp.json()['id'] == 'p1'


async def test_delete(api_client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, projects=[_project('p1')])
        delete = mock.delete(f'{WIZARD_BASE}/projects/p1').mock(
            return_value=httpx.Response(204),
        )
        resp = await api_client.delete('/dmps/p1')

    assert resp.status_code == 204
    assert delete.called


async def test_not_acceptable(api_client):
    resp = await api_client.get('/dmps', headers={'Accept': 'text/html'})
    assert resp.status_code == 406
    assert resp.json()['error_code'] == 'not_acceptable'
