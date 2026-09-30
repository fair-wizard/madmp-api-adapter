"""Deployment modes: config sources, tenant resolution, mounting."""

import asyncio
from typing import Any

import httpx
from httpx import ASGITransport, AsyncClient
import pytest
import respx
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from madmp_api.app import create_app
from madmp_api.cli import main as cli_main
from madmp_api.config import load_settings
from madmp_api.errors import TenantNotFoundError
from madmp_api.store import migrate
from madmp_api.store.db import get_session
from madmp_api.tenancy import resolve_tenant
from tests.conftest import ROWS

_USER = {'uuid': 'u1', 'firstName': 'Ada', 'lastName': 'Lovelace'}
_KM = {'organizationId': 'dsw', 'kmId': 'root', 'version': '2.7.0'}
_MULTI: dict[str, Any] = {
    'wizard_url': 'http://dsw.test',
    'wizards': {'mode': 'multi', 'allowed_hosts': ['*.example.org']},
}


def _request(
    headers: dict[str, str],
    *,
    root_path: str = '',
    scheme: str = 'https',
) -> Request:
    return Request(
        {
            'type': 'http',
            'method': 'GET',
            'scheme': scheme,
            'server': ('internal', 8000),
            'path': f'{root_path}/dmps',
            'root_path': root_path,
            'query_string': b'',
            'headers': [
                (key.lower().encode(), value.encode())
                for key, value in headers.items()
            ],
        },
    )


def _mock_wizard(mock: respx.Router, base: str, name: str) -> None:
    project = {
        'uuid': 'p1',
        'name': name,
        'createdAt': '2024-01-01T00:00:00+00:00',
        'updatedAt': '2024-06-01T00:00:00+00:00',
    }
    mock.get(f'{base}/users/current').mock(
        return_value=httpx.Response(200, json=_USER),
    )
    mock.get(f'{base}/projects').mock(
        return_value=httpx.Response(
            200,
            json={
                '_embedded': {'projects': [project]},
                'page': {'totalPages': 1},
            },
        ),
    )
    mock.get(f'{base}/projects/p1/settings').mock(
        return_value=httpx.Response(
            200,
            json={'name': name, 'knowledgeModelPackage': _KM},
        ),
    )
    mock.get(f'{base}/projects/p1/questionnaire').mock(
        return_value=httpx.Response(200, json={'replies': {}}),
    )


# --- configuration sources ---------------------------------------------


def test_yaml_then_env_then_kwargs(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    config.write_text(
        'request_timeout_seconds: 7\n'
        'default_language: deu\n'
        'wizards:\n'
        '  mode: multi\n'
        '  allowed_hosts: ["*.example.org"]\n',
    )
    monkeypatch.setenv('MADMP_API_DEFAULT_LANGUAGE', 'ces')

    settings = load_settings(str(config), list_cache_ttl_seconds=5)

    assert settings.request_timeout_seconds == 7
    assert settings.default_language == 'ces'  # env beats YAML
    assert settings.list_cache_ttl_seconds == 5  # kwargs beat env
    assert settings.wizards.mode == 'multi'
    assert settings.wizards.allowed_hosts == ['*.example.org']


def test_nested_env_overrides_yaml_section(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    config.write_text('wizards:\n  allowed_hosts: ["a.example.org"]\n')
    monkeypatch.setenv('MADMP_API_WIZARDS__MODE', 'multi')

    settings = load_settings(str(config))

    assert settings.wizards.mode == 'multi'
    assert settings.wizards.allowed_hosts == ['a.example.org']


def test_only_prefixed_environment_is_read(monkeypatch):
    # In a shared container (engine-gateway) other apps own DATABASE_URL.
    monkeypatch.setenv('DATABASE_URL', 'postgresql+asyncpg://other/app')
    monkeypatch.setenv('MADMP_API_TABLE_PREFIX', 'mine_')

    settings = load_settings()

    assert settings.database_url != 'postgresql+asyncpg://other/app'
    assert settings.table_prefix == 'mine_'


def test_config_path_from_environment(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    config.write_text('request_timeout_seconds: 9\n')
    monkeypatch.setenv('MADMP_API_CONFIG_PATH', str(config))

    assert load_settings().request_timeout_seconds == 9


def test_multi_mode_requires_allowed_hosts():
    with pytest.raises(ValueError, match='allowed_hosts'):
        load_settings(wizards={'mode': 'multi'})


@pytest.mark.parametrize('prefix', ['Madmp_', 'madmp-', '1madmp_', 'x' * 21])
def test_invalid_table_prefix_is_rejected(prefix):
    with pytest.raises(ValueError, match='table_prefix'):
        load_settings(table_prefix=prefix)


def test_missing_config_file_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(str(tmp_path / 'absent.yaml'))


# --- tenant resolution --------------------------------------------------


def test_single_mode_derives_public_id_base():
    settings = load_settings(wizard_url='http://server:3000')
    tenant = resolve_tenant(
        _request({'host': 'dsw.local'}, root_path='/madmp-api'),
        settings,
    )

    assert tenant.key == ''
    assert tenant.api_url == 'http://server:3000/wizard-api'
    assert tenant.upstream_host is None
    assert tenant.dmp_id_base_url == 'https://dsw.local/madmp-api/dmps'


def test_single_mode_explicit_id_base_wins():
    settings = load_settings(dmp_id_base_url='https://ids.example/dmps')
    tenant = resolve_tenant(_request({'host': 'dsw.local'}), settings)

    assert tenant.dmp_id_base_url == 'https://ids.example/dmps'


def test_forwarded_host_first_hop_is_used():
    settings = load_settings()
    tenant = resolve_tenant(
        _request(
            {'host': 'gateway:8080', 'x-forwarded-host': 'A.dsw.org, p1'},
        ),
        settings,
    )

    assert tenant.dmp_id_base_url == 'https://a.dsw.org/dmps'


def test_multi_mode_forwards_tenant_host_to_internal_url():
    settings = load_settings(**_MULTI)
    tenant = resolve_tenant(
        _request({'host': 'gw', 'x-original-host': 't1.example.org'}),
        settings,
    )

    assert tenant.key == 't1.example.org'
    assert tenant.api_url == 'http://dsw.test/wizard-api'
    assert tenant.upstream_host == 't1.example.org'


def test_multi_mode_url_template_calls_public_wizard():
    settings = load_settings(
        wizards={
            'mode': 'multi',
            'allowed_hosts': ['*.example.org'],
            'wizard_url_template': 'https://{host}',
        },
    )
    tenant = resolve_tenant(_request({'host': 't1.example.org'}), settings)

    assert tenant.api_url == 'https://t1.example.org/wizard-api'
    assert tenant.upstream_host is None


def test_multi_mode_tenant_overrides_first_match():
    settings = load_settings(
        wizards={
            'mode': 'multi',
            'allowed_hosts': ['*.example.org'],
            'overrides': {
                'special.example.org': {
                    'wizard_default_km': 'org:special:1.0.0',
                    'wizard_url': 'http://other-dsw:3000',
                    'dmp_id_base_url': 'https://ids.example/{host}',
                },
                '*': {'wizard_default_km': 'org:fallback:1.0.0'},
            },
        },
    )
    special = resolve_tenant(
        _request({'host': 'special.example.org'}),
        settings,
    )
    other = resolve_tenant(_request({'host': 'x.example.org'}), settings)

    assert special.default_km == 'org:special:1.0.0'
    assert special.api_url == 'http://other-dsw:3000/wizard-api'
    assert special.upstream_host is None
    assert special.dmp_id_base_url == 'https://ids.example/special.example.org'
    assert other.default_km == 'org:fallback:1.0.0'


@pytest.mark.parametrize('host', ['evil.test', 'example.org', ''])
def test_multi_mode_rejects_unlisted_hosts(host):
    settings = load_settings(**_MULTI)
    with pytest.raises(TenantNotFoundError):
        resolve_tenant(_request({'host': host}), settings)


# --- end to end ---------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_mode_sends_tenant_host_upstream(make_client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, 'http://dsw.test/wizard-api', 'Tenant One')
        async with make_client(
            base_url='http://t1.example.org',
            **_MULTI,
        ) as client:
            resp = await client.get('/dmps/p1')
        hosts = {call.request.headers['host'] for call in mock.calls}

    assert resp.status_code == 200
    assert hosts == {'t1.example.org'}
    dmp_id = resp.json()['dmp']['dmp_id']['identifier']
    assert dmp_id == 'http://t1.example.org/dmps/p1'


@pytest.mark.asyncio
async def test_multi_mode_unknown_host_is_404(make_client):
    async with make_client(base_url='http://evil.test', **_MULTI) as client:
        resp = await client.get('/dmps')

    assert resp.status_code == 404
    assert resp.json()['error_code'] == 'generic_error'


@pytest.mark.asyncio
async def test_tenants_do_not_share_cached_rows(make_client, db_engine):
    # The same project UUID seen through two tenants (Wizard never produces
    # this, but the store must not rely on it) yields two separate rows.
    with respx.mock(assert_all_called=False) as mock:
        for host, name in (('a', 'Tenant A'), ('b', 'Tenant B')):
            base = f'http://{host}.dsw.test/wizard-api'
            _mock_wizard(mock, base, name)
        # Each tenant host is pointed at its own stubbed Wizard.
        multi = {
            'wizards': {
                'mode': 'multi',
                'allowed_hosts': ['*.example.org'],
                'overrides': {
                    f'{host}.example.org': {
                        'wizard_url': f'http://{host}.dsw.test',
                    }
                    for host in ('a', 'b')
                },
            },
        }
        titles = {}
        for host in ('a', 'b'):
            async with make_client(
                base_url=f'http://{host}.example.org',
                **multi,
            ) as client:
                resp = await client.get('/dmps')
            items = resp.json()['items']
            titles[host] = [item['dmp']['title'] for item in items]

    assert titles == {'a': ['Tenant A'], 'b': ['Tenant B']}
    maker = async_sessionmaker(db_engine)
    async with maker() as session:
        tenants = await session.scalars(
            select(ROWS.tenant).order_by(ROWS.tenant),
        )
        assert list(tenants) == ['a.example.org', 'b.example.org']


@pytest.mark.asyncio
async def test_new_public_url_remaps_cached_row(make_client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, 'http://dsw.test/wizard-api', 'P')
        ids = []
        for base_url in ('http://direct:8000', 'https://dsw.example'):
            async with make_client(base_url=base_url) as client:
                resp = await client.get('/dmps/p1')
            ids.append(resp.json()['dmp']['dmp_id']['identifier'])

    assert ids == [
        'http://direct:8000/dmps/p1',
        'https://dsw.example/dmps/p1',
    ]


@pytest.mark.asyncio
async def test_mounted_like_engine_gateway(make_client, session_override):
    """engine-gateway = FastAPI(root_path=...) + ``mount(path, factory())``."""
    app = create_app(config_path=None)
    app.dependency_overrides[get_session] = session_override
    gateway = FastAPI(root_path='/gateway')
    gateway.mount('/madmp', app)

    with respx.mock(assert_all_called=False) as mock:
        _mock_wizard(mock, 'http://dsw.test/wizard-api', 'Mounted')
        async with make_client(
            base_url='https://dsw.example',
            app=gateway,
        ) as client:
            resp = await client.get('/gateway/madmp/dmps/p1')

    assert resp.status_code == 200
    dmp_id = resp.json()['dmp']['dmp_id']['identifier']
    assert dmp_id == 'https://dsw.example/gateway/madmp/dmps/p1'


# --- migrations ---------------------------------------------------------


async def _drop(engine, prefix):
    async with engine.begin() as conn:
        await conn.execute(
            text(f'DROP TABLE IF EXISTS {prefix}dmp, {prefix}schema_migrations'),
        )


@pytest.mark.asyncio
async def test_migrations_apply_once(db_engine):
    await _drop(db_engine, 'once_')
    try:
        assert await migrate.upgrade(db_engine, 'once_') == ['0001']
        assert await migrate.upgrade(db_engine, 'once_') == []
    finally:
        await _drop(db_engine, 'once_')


@pytest.mark.asyncio
async def test_concurrent_instances_migrate_once(db_engine):
    # Separate engines stand in for gateway workers starting together.
    url = load_settings().database_url
    engines = [create_async_engine(url) for _ in range(3)]
    await _drop(db_engine, 'race_')
    try:
        results = await asyncio.gather(
            *(migrate.upgrade(engine, 'race_') for engine in engines),
        )
        assert sorted(results) == [[], [], ['0001']]
    finally:
        for engine in engines:
            await engine.dispose()
        await _drop(db_engine, 'race_')


@pytest.mark.asyncio
async def test_first_request_migrates_without_lifespan(db_engine):
    """Mounted apps get no startup events; the first request migrates."""
    await _drop(db_engine, 'lazy_')
    app = create_app(table_prefix='lazy_')
    gateway = FastAPI()
    gateway.mount('/madmp', app)  # lifespan events never reach ``app``
    try:
        with respx.mock(assert_all_called=False) as mock:
            _mock_wizard(mock, 'http://dsw.test/wizard-api', 'Lazy')
            async with AsyncClient(
                transport=ASGITransport(app=gateway),
                base_url='http://test',
                headers={'Authorization': 'Bearer t'},
            ) as client:
                resp = await client.get('/madmp/dmps')

        assert resp.json()['total_count'] == 1
        async with db_engine.connect() as conn:
            version = await conn.scalar(
                text('SELECT version FROM lazy_schema_migrations'),
            )
        assert version == '0001'
    finally:
        await app.state.database.dispose()
        await _drop(db_engine, 'lazy_')


@pytest.mark.asyncio
async def test_custom_table_prefix_end_to_end(make_client, db_engine):
    """Migrations and queries both follow ``table_prefix``."""
    await _drop(db_engine, 'alt_')
    await migrate.upgrade(db_engine, 'alt_')
    try:
        with respx.mock(assert_all_called=False) as mock:
            _mock_wizard(mock, 'http://dsw.test/wizard-api', 'Prefixed')
            async with make_client(table_prefix='alt_') as client:
                resp = await client.get('/dmps')

        assert resp.json()['total_count'] == 1
        async with db_engine.connect() as conn:
            rows = await conn.scalar(text('SELECT count(*) FROM alt_dmp'))
        assert rows == 1
    finally:
        await _drop(db_engine, 'alt_')


# --- CLI ----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures('db_engine')
async def test_cli_migrate_is_idempotent():
    # The CLI runs its own event loop, so keep it off the test's loop.
    await asyncio.to_thread(cli_main, ['migrate'])
    await asyncio.to_thread(cli_main, ['migrate'])
