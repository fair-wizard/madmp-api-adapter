"""Adapter configuration.

Settings are resolved per application instance (``create_app``), so the
same package can run standalone or be mounted — even more than once — in
an engine-gateway. Sources, highest precedence first:

1. keyword arguments passed to :func:`load_settings` (gateway ``kwargs``),
2. environment variables (nested keys use ``__``, e.g.
   ``MADMP_API_WIZARDS__MODE=multi``),
3. the ``.env`` file,
4. an optional YAML file (``config_path`` / ``MADMP_API_CONFIG_PATH``),
5. the defaults below.
"""

import os
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_PATH_ENV = 'MADMP_API_CONFIG_PATH'
# Lower-case SQL identifier start, short enough for prefixed index names.
TABLE_PREFIX_PATTERN = r'^([a-z_][a-z0-9_]{0,19})?$'


class WizardOverrides(BaseModel):
    """Per-host overrides; unset fields fall back to the global value."""

    # Upstream Wizard for this host, called without a Host override.
    wizard_url: str | None = None
    wizard_default_km: str | None = None
    default_language: str | None = None
    # May contain ``{host}``, replaced by the request host.
    dmp_id_base_url: str | None = None


class WizardsSettings(BaseModel):
    # ``single``: one Wizard at ``wizard_url`` (a plain installation,
    # which ignores Host). ``multi``: several Wizard APIs, selected by the
    # request host, which is forwarded as Host (how a cloud-mode Wizard
    # routes a request).
    mode: Literal['single', 'multi'] = 'single'
    # Request headers carrying the public host, first present wins. Put
    # the header your proxy sets first.
    host_headers: list[str] = Field(
        default_factory=lambda: ['x-original-host', 'x-forwarded-host', 'host'],
    )
    # ``multi`` only: glob patterns of hosts that may be served.
    allowed_hosts: list[str] = Field(default_factory=list)
    # ``multi`` only: public Wizard URL per host, e.g. ``https://{host}``.
    # When unset, ``wizard_url`` is called with the tenant host as Host.
    wizard_url_template: str | None = None
    # ``multi`` only: host glob pattern -> overrides, first match wins.
    overrides: dict[str, WizardOverrides] = Field(default_factory=dict)

    @model_validator(mode='after')
    def _multi_needs_hosts(self) -> Self:
        # Fail at startup rather than answer every request with a 404.
        if self.mode == 'multi' and not self.allowed_hosts:
            msg = 'wizards.allowed_hosts must be set in multi mode'
            raise ValueError(msg)
        return self


class Settings(BaseSettings):
    # Environment names are prefixed (``MADMP_API_WIZARD_URL``) so the
    # adapter never picks up another app's variables in a shared container,
    # such as an engine-gateway.
    model_config = SettingsConfigDict(
        env_prefix='MADMP_API_',
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        extra='ignore',
    )

    # DSW / FAIR Wizard backend (without the ``/wizard-api`` suffix). The
    # default KM accepts either a package UUID or an ``org:kmId:version``.
    wizard_url: str = 'http://localhost:3000'
    wizard_default_km: str = 'dsw:root:2.7.0'

    wizards: WizardsSettings = Field(default_factory=WizardsSettings)

    # Intermediate store. The adapter keeps to the default schema, so its
    # tables (``<prefix>dmp``, ``<prefix>schema_migrations``) and indexes
    # are prefixed to coexist with other applications in one database.
    database_url: str = 'postgresql+asyncpg://madmp:madmp@localhost:5440/madmp'
    table_prefix: str = Field('madmp_', pattern=TABLE_PREFIX_PATTERN)

    # maDMP synthesis defaults. Without an explicit DMP id base URL it is
    # derived from the request: ``<scheme>://<host><root_path>/dmps``.
    default_language: str = 'eng'
    dmp_id_base_url: str | None = None

    # Behaviour tuning
    list_cache_ttl_seconds: int = 30
    request_timeout_seconds: float = 60.0

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def load_settings(
    config_path: str | None = None,
    **overrides: object,
) -> Settings:
    path = config_path or os.environ.get(CONFIG_PATH_ENV)
    if not path:
        return Settings(**overrides)  # ty: ignore[invalid-argument-type]
    if not Path(path).is_file():
        msg = f'configuration file not found: {path}'
        raise FileNotFoundError(msg)
    # The YAML source reads its path from the model config, so bind it
    # through a throwaway subclass rather than mutating the shared class.
    bound = type(
        'FileSettings',
        (Settings,),
        {'model_config': {**Settings.model_config, 'yaml_file': path}},
    )
    return bound(**overrides)  # ty: ignore[invalid-argument-type]
