# maDMP API console client

Small, dependency-light scripts for driving the maDMP API from a terminal:
a CLI over the five RDA operations, and three scripted workflows that walk
through reading, writing and failing.

They talk **only** to the maDMP API (`/dmps`), never to DSW directly — the
one exception is obtaining a token, which is a Wizard login.

## Prerequisites

```bash
cd example/wizard && docker compose up -d       # Wizard on :3000
cd ../.. && uv run python example/prepare.py --seed
make db && make migrate                         # the adapter's own store
MADMP_API_WIZARD_URL=http://localhost:3000 MADMP_API_WIZARD_DEFAULT_KM=dsw:root:2.7.0 make dev
```

## Configuration

All scripts read the same settings, in this order of precedence:

1. command-line flags (`--api-url`, `--token`)
2. real environment variables
3. `.env` files
4. built-in defaults (the example deployment)

Copy [`env.example`](env.example) to `.env` in this directory and it is
picked up automatically:

```bash
cp example/madmp-client/env.example example/madmp-client/.env
```

Another file can be layered on top with `--env-file PATH` (or the
`MADMP_ENV_FILE` variable). A path given explicitly must exist; a missing
`.env` is simply skipped. Every script prints the files it read as
`config: …`.

The adapter's own `madmp-api/.env` is **not** read — it configures the
server (`MADMP_API_*` variables), and its `MADMP_API_WIZARD_URL` is the URL
the *server* uses to reach the Wizard, which a client cannot always
resolve.

Recognised settings (all optional):

| Variable | Default | Meaning |
|---|---|---|
| `MADMP_API_URL` | `http://localhost:8000` | maDMP API base URL |
| `MADMP_TOKEN` | — | bearer token; when unset the scripts log in to the Wizard |
| `WIZARD_URL` | `http://localhost:3000` | Wizard base URL used for that login |
| `WIZARD_EMAIL` | `albert.einstein@example.com` | Wizard login |
| `WIZARD_PASSWORD` | `password` | Wizard password |
| `MADMP_ENV_FILE` | — | an extra `.env` file to read |
| `NO_COLOR` | — | disable ANSI colours (real environment only) |

`--api-url` and `--token` override the first two per invocation. `.env` is
gitignored; keep real credentials out of `env.example`.

## CLI

```bash
uv run python example/madmp-client/cli.py --help
```

```bash
uv run python example/madmp-client/cli.py token
uv run python example/madmp-client/cli.py list --count 5 --sort title,asc
uv run python example/madmp-client/cli.py list --query genome --language eng
uv run python example/madmp-client/cli.py list --all --json
uv run python example/madmp-client/cli.py get <dmp-id>
uv run python example/madmp-client/cli.py create --title "My DMP"
uv run python example/madmp-client/cli.py update <dmp-id> --set-title "New" --safe
uv run python example/madmp-client/cli.py delete <dmp-id> --yes
```

Notes:

- Every repeatable RDA filter has a flag (`--dataset-id`, `--funder-id`,
  `--license-ref`, `--personal-data`, …); pass it more than once for OR.
- `--rda-brackets` spells array parameters as `name[]=`, the way the RDA
  spec writes them. The API accepts both.
- `--vendor-media-type` sends
  `Accept: application/vnd.org.rd-alliance.dmp-common.v1.2+json`.
- `update` fetches the current document first, applies `--set-*`, and PUTs
  the whole thing back — `PUT` is a replacement, not a patch. `--safe` adds
  `If-Unmodified-Since` from the `Last-Modified` it just read.
- `delete` removes the underlying **DSW project**, not just the stored
  projection; it asks for confirmation unless you pass `--yes`.

## Workflows

Each script prints its requests (`→ GET …` / `← 200 …`) and reports the
outcome of every step.

| Script | Writes? | What it covers |
|---|---|---|
| `workflow_browse.py` | no | paging with `offset`/`count`, multi-key `sort`, every filter family, date windows, `name[]=` equivalence, walking all pages |
| `workflow_crud.py` | its own DMP only | `POST` from `sample-dmp.json`, read-back, appearing in listings, `PUT` with `If-Unmodified-Since`, a deliberate `409`, `DELETE` + 404 verification |
| `workflow_errors.py` | no successful write | `404 dmp_not_found`, `400 invalid_query_string`, `406 not_acceptable`, `415 unsupported_media_type`, `400 dmp_invalid`, `401 authentication_required` |

```bash
uv run python example/madmp-client/workflow_browse.py
uv run python example/madmp-client/workflow_crud.py          # --keep to not delete
uv run python example/madmp-client/workflow_errors.py        # exit != 0 on mismatch
```

`workflow_crud.py` creates a real DSW project through `POST /dmps` (using
the API's `MADMP_API_WIZARD_DEFAULT_KM`) and deletes it at the end. If it aborts
mid-run it prints the id it left behind.

## Files

| File | Role |
|---|---|
| `madmp_client.py` | `MadmpClient` — the five operations, query building, error mapping, request tracing |
| `console.py` | colours, tables, key/value output |
| `cli.py` | argparse front end |
| `sample-dmp.json` | an RDA maDMP document that round-trips through the `dsw:root` mapping |
| `env.example` | configuration template — copy to `.env` |

`sample-dmp.json` carries fields the request body requires (`dmp_id`,
`contact`, `created`, `modified`) even though the API regenerates them from
DSW — the create workflow prints the before/after so the difference is
visible.
