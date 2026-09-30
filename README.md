# maDMP API Adapter

An adapter that exposes the RDA DMP Common
[**common-madmp-api**](https://github.com/RDA-DMP-Common/common-madmp-api)
in front of **Data Stewardship Wizard (DSW) / FAIR Wizard**. DMPs are served
and accepted as machine-actionable DMPs following the
[**RDA DMP Common Standard**](https://github.com/RDA-DMP-Common/RDA-DMP-Common-Standard).

The Wizard remains the system of record: projects are mapped to maDMP
documents on read (served from a materialised store) and maDMP writes are
propagated back to the Wizard API.

## Architecture

```mermaid
flowchart LR
    client["RDA maDMP client"]

    subgraph adapter["maDMP API"]
        api["RDA API<br/>/dmps"]
        sync["Sync service<br/>read-through · write-through"]
        transform["Mapping profiles<br/>replies ⇄ maDMP"]
        wclient["Wizard client"]
    end

    store[("PostgreSQL<br/>maDMP projection")]
    wizard["Wizard API<br/>/wizard-api"]

    client -- "Bearer: Wizard token" --> api
    api --> sync
    sync <--> transform
    sync <--> store
    sync --> wclient
    wclient -- "same Bearer token" --> wizard
```

- **Per-user pass-through auth.** The incoming `Authorization: Bearer …` is
  a Wizard token or API key, forwarded verbatim. Authorization is resolved
  live against the Wizard's visible-project set on every request — the
  store is a content cache only.
- **Read-through, validated by `updatedAt`.** Reads re-map only changed or
  missing projects, then run the RDA filters, sorting and pagination in
  PostgreSQL. Writes go to the Wizard first, then refresh the affected
  projection (write-through).
- **Custom mapping.** Wizard questionnaire replies ⇄ maDMP is handled by a
  knowledge-model-keyed
  [`MappingProfile`](src/madmp_api/transform/profiles.py); the base profile
  synthesises all fields the standard requires, with override hooks for
  knowledge-model-specific fidelity.

Package layout under `src/madmp_api/`: `api/` (routes, parameters, errors,
content negotiation), `madmp/` (Pydantic models of the standard),
`wizard/` (async Wizard API client), `transform/` (mapping profiles),
`store/` (models, repository, SQL migrations), `sync/` (orchestration),
`tenancy.py` (which Wizard API serves a request).

## Endpoints

The five operations of
[common-madmp-api](https://github.com/RDA-DMP-Common/common-madmp-api):
`GET /dmps` · `POST /dmps` · `GET /dmps/{id}` · `PUT /dmps/{id}` ·
`DELETE /dmps/{id}` — with offset/count pagination, `sort[]`, filters,
`{total_count, items}` lists, `Last-Modified` / `If-Unmodified-Since`
preconditions and `{error_code, error_message}` errors. Interactive
documentation is served at `/docs`.

## Try it end to end

[`example/`](example/README.md) contains a minimal Wizard deployment plus the
Common DSW Knowledge Model, enough to exercise the whole adapter locally:

```bash
cd example/wizard && docker compose up -d      # Wizard on :3000
cd ../.. && uv run python example/prepare.py --seed
make db                                        # the adapter's own store
MADMP_API_WIZARD_URL=http://localhost:3000 make dev
```

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/), Docker (for the local
PostgreSQL store) and a reachable DSW / FAIR Wizard instance.

```bash
make install            # sync dependencies
cp .env.example .env    # configure MADMP_API_WIZARD_URL, MADMP_API_DATABASE_URL, …
make db                 # start PostgreSQL (docker compose, host port 5440)
make dev                # run the API on http://localhost:8000
```

## Configuration

Settings come from, highest precedence first: `create_app` keyword
arguments (engine-gateway `kwargs`), environment variables, `.env`, and an
optional YAML file (`MADMP_API_CONFIG_PATH`). Every option is documented in
[config.example.yaml](config.example.yaml).

Environment variables (and `.env` keys) are the option names upper-cased
with the `MADMP_API_` prefix, so the adapter never reads another
application's variables when it shares a container: `wizard_url` is
`MADMP_API_WIZARD_URL`, nested keys use `__` and lists are JSON, e.g.
`MADMP_API_WIZARDS__ALLOWED_HOSTS='["*.example.org"]'`.

## Deployment

One package and one image cover three layouts; only configuration differs.

| | A: next to one Wizard | B: in an engine-gateway | C: standalone, several Wizard APIs |
|---|---|---|---|
| Runs as | own container | mount of the gateway app | own container |
| `wizards.mode` | `single` (default) | `multi` | `multi` |
| Wizard API | `wizard_url` | `wizard_url` + request host, or `wizard_url_template` | `wizard_url` + request host, or `wizard_url_template` |
| Public URL | `http(s)://<host>[/prefix]/dmps` | `https://<wizard-host>/gateway/madmp/dmps` | `https://<wizard-host>/<prefix>/dmps` |

### A: next to one Wizard

[example/wizard/docker-compose.yml](example/wizard/docker-compose.yml) has
the two services (`madmp-api`, `madmp-db`) behind the `madmp` profile:

```bash
cd example/wizard && docker compose --profile madmp up -d --build
```

Only `MADMP_API_WIZARD_URL` (the internal `http://server:3000`),
`MADMP_API_WIZARD_DEFAULT_KM` and `MADMP_API_DATABASE_URL` are needed.

### B: mounted in an engine-gateway

[example/gateway/](example/gateway/) builds a
[ds-wizard/engine-gateway](https://github.com/ds-wizard/engine-gateway)
image with the adapter installed and mounted:

```yaml
mounts:
  /madmp:
    module: madmp_api
    factory: create_app
```

The mount is configured through `MADMP_API_*` variables on the gateway, or
a YAML file (`MADMP_API_CONFIG_PATH` or `kwargs: {config_path: ...}`); see
[example/gateway/madmp/config.yaml](example/gateway/madmp/config.yaml). A
typical gateway serving several Wizard hosts needs:

```bash
MADMP_API_DATABASE_URL=postgresql+asyncpg://madmp:***@db-host:5432/db
MADMP_API_WIZARDS__MODE=multi
MADMP_API_WIZARDS__ALLOWED_HOSTS=["*.wizard.example.org"]
MADMP_API_WIZARDS__WIZARD_URL_TEMPLATE=https://{host}   # or MADMP_API_WIZARD_URL=<internal server>
```

### C: standalone, several Wizard APIs

Run the image behind every Wizard host (e.g. under `/madmp-api`) with the
same `MADMP_API_WIZARDS__*` settings as in B. Use `uvicorn --root-path
/madmp-api` if the proxy strips the prefix, so DMP ids keep it.

### Serving several Wizard APIs

```mermaid
flowchart LR
    c1["client of<br/>a.wizard.example.org"]
    c2["client of<br/>b.wizard.example.org"]
    proxy["reverse proxy<br/>keeps the public host"]
    adapter["maDMP API<br/>wizards.mode: multi"]
    wizard["Wizard<br/>(several host names)"]
    store[("PostgreSQL<br/>rows kept per host")]

    c1 --> proxy
    c2 --> proxy
    proxy -- "X-Forwarded-Host" --> adapter
    adapter -- "Host: the public host" --> wizard
    adapter --> store
```

With `wizards.mode: multi`, the host a client used selects the Wizard API:

- The adapter reads the public host from the first header present in
  `wizards.host_headers` (default `x-original-host`, `x-forwarded-host`,
  `host`), and serves only hosts matching `wizards.allowed_hosts` (globs;
  anything else is a 404).
- It calls `wizard_url` with that host as `Host`, which is how a Wizard
  serving several host names (`server.cloud.enabled`) routes a request —
  the Wizard ignores `X-Forwarded-Host`. Alternatively,
  `wizards.wizard_url_template` (e.g. `https://{host}`) calls each Wizard
  API at its public URL.
- Stored DMPs and caches are kept separate per host, and a Wizard token
  only works on the host it was issued for.
- `wizards.overrides` holds per-host settings: default knowledge model,
  language, DMP id base, or a separate `wizard_url`.

**The reverse proxy must pass the public host on.** Configure it to set
`X-Forwarded-Host` (or another header listed in `wizards.host_headers`) to
the host the client requested; many proxies and ingress controllers do so
by default.

### DMP identifiers

DMP ids default to `<scheme>://<host><root_path>/dmps/<uuid>`, derived per
request, so they follow the mount prefix and the proxy's public host. The
image trusts `X-Forwarded-Proto` from any peer (`FORWARDED_ALLOW_IPS=*`);
narrow it where the proxy address is known. Pin ids with
`MADMP_API_DMP_ID_BASE_URL` (may contain `{host}` in multi mode) when they
must not depend on the request.

### Database

The adapter needs a PostgreSQL database but can share one with other
applications: it keeps to the default schema and names everything it
creates with `table_prefix` (default `madmp_`) — the `madmp_dmp` table, its
indexes and the migration log `madmp_schema_migrations`. The stored DMPs
are a cache rebuilt from the Wizard on demand, so the database needs no
backup.

**Migrations run automatically.** Numbered SQL scripts in
[src/madmp_api/store/sql/](src/madmp_api/store/sql/) are applied at
startup when running standalone, and in any case before the first database
access, which covers mounted deployments that never receive startup
events. An advisory lock makes concurrently starting instances migrate
exactly once, in a single transaction, so the database user needs `CREATE`
on the default schema. `madmp-api migrate` applies them manually, e.g. to
prepare a database ahead of a deploy.

## Code quality & tests

```bash
make lint          # ruff check
make format        # ruff format
make typecheck     # ty check
make test          # pytest (needs the PostgreSQL store running)
```

Tests stub the Wizard with `respx` and run the store against the real
PostgreSQL from `docker compose`; DB-backed tests skip automatically if it
is unreachable. The API contract is checked against the
[common-madmp-api](https://github.com/RDA-DMP-Common/common-madmp-api)
OpenAPI description ([tests/data/madmp-openapi.yaml](tests/data/madmp-openapi.yaml)).

## License

[MIT](LICENSE). Bundled third-party files keep their own licenses: the
[common-madmp-api](https://github.com/RDA-DMP-Common/common-madmp-api)
OpenAPI description in `tests/data/` (CC0-1.0) and the Common DSW Knowledge
Model in `example/knowledge-models/` (Apache-2.0).
