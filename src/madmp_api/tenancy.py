"""Per-request tenant resolution.

Wizard resolves its tenant from nothing but the exact ``Host`` header of a
wizard-api request (matched against ``tenant.server_domain``, port
included) and ignores ``X-Forwarded-Host``. In ``multi`` mode the public
host a client used is therefore the tenant key, and it is replayed as the
``Host`` of every upstream call. Tokens are tenant-bound in the Wizard, so a
token presented on a foreign tenant's host is rejected upstream (401).
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase

from fastapi import Request

from madmp_api.config import Settings, WizardOverrides
from madmp_api.errors import TenantNotFoundError

# Tenant key of ``single`` mode (also the key pre-tenancy rows migrate to).
SINGLE_TENANT = ''


@dataclass(frozen=True)
class Tenant:
    key: str
    # Base URL of the wizard-api (including the ``/wizard-api`` suffix).
    api_url: str
    # Host to send upstream, when it differs from ``api_url``'s own.
    upstream_host: str | None
    default_km: str
    default_language: str
    dmp_id_base_url: str
    request_timeout_seconds: float


def _first_value(value: str) -> str:
    # X-Forwarded-Host may list every proxy hop; the first is the client's.
    return value.split(',', 1)[0].strip().lower()


def public_host(request: Request, settings: Settings) -> str:
    for name in settings.wizards.host_headers:
        value = request.headers.get(name)
        if value and _first_value(value):
            return _first_value(value)
    return ''


def _public_base_url(request: Request, host: str) -> str:
    # ``root_path`` carries the mount prefix (e.g. ``/gateway/madmp``)
    # when running inside an engine-gateway or behind ``--root-path``.
    root_path = request.scope.get('root_path', '').rstrip('/')
    return f'{request.url.scheme}://{host or request.url.netloc}{root_path}'


def _overrides(settings: Settings, host: str) -> WizardOverrides:
    for pattern, overrides in settings.wizards.overrides.items():
        if fnmatchcase(host, pattern.lower()):
            return overrides
    return WizardOverrides()


def _allowed(settings: Settings, host: str) -> bool:
    return bool(host) and any(
        fnmatchcase(host, pattern.lower())
        for pattern in settings.wizards.allowed_hosts
    )


def resolve_tenant(request: Request, settings: Settings) -> Tenant:
    host = public_host(request, settings)
    if settings.wizards.mode == 'single':
        return Tenant(
            key=SINGLE_TENANT,
            api_url=f'{settings.wizard_url.rstrip("/")}/wizard-api',
            upstream_host=None,
            default_km=settings.wizard_default_km,
            default_language=settings.default_language,
            dmp_id_base_url=settings.dmp_id_base_url
            or f'{_public_base_url(request, host)}/dmps',
            request_timeout_seconds=settings.request_timeout_seconds,
        )

    if not _allowed(settings, host):
        raise TenantNotFoundError
    overrides = _overrides(settings, host)
    template = settings.wizards.wizard_url_template
    if overrides.wizard_url:
        wizard_url, upstream_host = overrides.wizard_url, None
    elif template:
        wizard_url, upstream_host = template.format(host=host), None
    else:
        wizard_url, upstream_host = settings.wizard_url, host
    id_base = overrides.dmp_id_base_url or settings.dmp_id_base_url
    return Tenant(
        key=host,
        api_url=f'{wizard_url.rstrip("/")}/wizard-api',
        upstream_host=upstream_host,
        default_km=overrides.wizard_default_km or settings.wizard_default_km,
        default_language=overrides.default_language
        or settings.default_language,
        dmp_id_base_url=id_base.format(host=host)
        if id_base
        else f'{_public_base_url(request, host)}/dmps',
        request_timeout_seconds=settings.request_timeout_seconds,
    )
