# Example Deployment for Testing

This is a minimal Wizard deployment for testing the maDMP API.

- It does not include any data.
- It does not use mailer nor document worker services.
- It does not use S3 storage.
- It is intended only for testing Projects and their manipulation through maDMP API.

## Default Credentials

- email: `albert.einstein@example.com`
- password: `password`

## Quick start

```bash
cd example/wizard && docker compose up -d      # Wizard on :3000, client on :8080
cd ../.. && uv run python example/prepare.py --seed
```

`prepare.py` is idempotent: it logs in, imports the bundled knowledge model
(`dsw:root:2.7.0`) if missing, and with `--seed` creates a demo project with
questionnaire replies. Use `--print-token` to get an access token for `curl`.

Then run the maDMP API against it:

```bash
MADMP_API_WIZARD_URL=http://localhost:3000 MADMP_API_WIZARD_DEFAULT_KM=dsw:root:2.7.0 make dev
```

The maDMP API forwards your `Authorization` header to the Wizard, so use the
Wizard token as the RDA API bearer token:

```bash
TOKEN=$(uv run python example/prepare.py --print-token | tail -1)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/dmps
```

Note the store needs its own PostgreSQL (`make db`; its schema is created on
startup) — separate
from the Wizard's database, which uses port 5432 here.

## Console client

[`madmp-client/`](madmp-client/) holds a small console client for the maDMP
API itself: a CLI over the five RDA operations and three scripted workflows
(browsing/filtering, a full CRUD round trip, and the error paths).

```bash
cp example/madmp-client/env.example example/madmp-client/.env   # optional
uv run python example/madmp-client/cli.py list --count 5 --sort title,asc
uv run python example/madmp-client/workflow_browse.py     # read-only
uv run python example/madmp-client/workflow_crud.py       # creates + deletes its own DMP
uv run python example/madmp-client/workflow_errors.py     # asserts the RDA error codes
```

See [`madmp-client/README.md`](madmp-client/README.md) for the details.

## Preparation

API specs: `http://localhost:3000/wizard-api/swagger-ui/`

1. `POST /tokens` to obtain an access token
2. `POST /knowledge-model-packages/bundle` to import knowledge models
3. `POST /projects` to create a new project using the imported knowledge models
4. `GET /projects/{uuid}/questionnaire` to obtain the questionnaire
5. `POST /projects/{uuid}/events` to send events (replies) to the questionnaire

### API details verified against this deployment (DSW 4.33)

These shapes drive the adapter's DSW client and are easy to get wrong:

- `POST /tokens` returns `{"token": …, "expiresAt": …}`.
- `POST /projects` requires **`knowledgeModelPackageUuid`** (a UUID — not the
  `org:kmId:version` string) plus `name`, `visibility`, `sharing`,
  `questionTagUuids`.
- `PUT /projects/{uuid}/settings` requires `name`, `projectTags`, `isTemplate`.
- **`createdAt` / `updatedAt` are returned only by the project *list***
  (`GET /projects`); neither `GET /projects/{uuid}` nor `.../settings` has them.
- The `knowledgeModelPackage` embedded in project payloads is a trimmed copy
  (`name`, `uuid`, `version`); `organizationId` and `kmId` — needed to identify
  the knowledge model — appear only in `GET /projects/{uuid}/settings` and
  `GET /knowledge-model-packages`.
- Replies are keyed by a dot-joined UUID path: `chapter.question`, or
  `chapter.list.item.question` for list items. Values are tagged, e.g.
  `{"type": "StringReply", "value": …}`, `{"type": "AnswerReply", "value": …}`,
  `{"type": "ItemListReply", "value": [itemUuid, …]}`.
- `POST /projects/{uuid}/events` takes a **single** event object;
  `PUT /projects/{uuid}/content` takes `{"events": [...]}` and is used by the
  adapter to apply a whole maDMP in one request.
- Errors nest `message` as an object (`code`, `defaultMessage`, `params`).

## Knowledge model mapping

`dsw:root` question identifiers used by the adapter live in
[`src/madmp_api/transform/dsw_root.py`](../src/madmp_api/transform/dsw_root.py);
the bidirectional mapping is in `transform/profiles.py` (`DSWRootProfile`).
Currently mapped: datasets (title, description, identifier + type, personal /
sensitive data), contributors (name, e-mail, roles), research projects
(title, abstract, start/end, funding, costs) and ethical issues.
