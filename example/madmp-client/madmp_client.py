#!/usr/bin/env python3
"""Small console client for the maDMP API (RDA common-madmp-api v1.2).

Used by ``cli.py`` and the ``workflow_*.py`` scripts in this directory.
Every request is traced to stdout so the scripts double as a readable log
of what the API does.

Configuration comes from the environment or from a ``.env`` file:

    MADMP_API_URL    maDMP API base URL        (default http://localhost:8000)
    MADMP_TOKEN      bearer token to send; when unset the client logs in to
                     the Wizard and uses the token it returns (the adapter
                     forwards the Authorization header to DSW verbatim)
    WIZARD_URL       Wizard base URL           (default http://localhost:3000)
    WIZARD_EMAIL     Wizard login              (default the example account)
    WIZARD_PASSWORD  Wizard password           (default the example password)
    MADMP_ENV_FILE   an extra .env file to read

A ``.env`` next to these scripts is read automatically. Files given
explicitly (``--env-file`` / ``MADMP_ENV_FILE`` / ``load_env(path)``) are
read on top of it, and real environment variables win over every file. The
project root ``madmp-api/.env`` is *not* read: it configures the adapter
(``MADMP_API_*`` variables), and its ``MADMP_API_WIZARD_URL`` is the URL
the server uses, which is not always reachable from a client. See
``env.example``.
"""

from __future__ import annotations

import errno
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

import console

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_WIZARD_URL = "http://localhost:3000"
DEFAULT_EMAIL = "albert.einstein@example.com"
DEFAULT_PASSWORD = "password"  # noqa: S105  (documented demo credential)

CLIENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CLIENT_DIR.parents[1]
# Only the client's own file is discovered; the adapter's .env in
# PROJECT_DIR describes the *server* and is opt-in (--env-file ../../.env).
DEFAULT_ENV_FILES = (CLIENT_DIR / ".env",)

# Values read from .env files: consulted only when the real environment
# does not define the variable.
_file_env: dict[str, str] = {}
_loaded_files: list[Path] = []


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=value`` lines; supports ``export``, ``#`` and quotes."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.removeprefix("export ").partition("=")
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        quoted = len(value) > 1 and value[0] == value[-1]
        if quoted and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(
    *paths: str | Path | None,
    discover: bool = True,
) -> list[Path]:
    """Layer ``.env`` files into the client configuration.

    Reads the default location (unless ``discover=False``), then
    ``MADMP_ENV_FILE``, then any explicitly given paths — later files
    override earlier ones. Missing default files are skipped; a missing
    explicit file raises :class:`FileNotFoundError`. Returns the files read.
    """
    candidates: list[tuple[Path, bool]] = []
    if discover:
        candidates.extend((path, False) for path in DEFAULT_ENV_FILES)
        from_env = os.environ.get("MADMP_ENV_FILE")
        if from_env:
            candidates.append((Path(from_env), True))
    candidates.extend(
        (Path(path), True) for path in paths if path is not None
    )

    loaded: list[Path] = []
    for path, required in candidates:
        expanded = path.expanduser()
        if not expanded.is_file():
            if required:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "no such env file",
                    str(expanded),
                )
            continue
        _file_env.update(parse_env_file(expanded))
        loaded.append(expanded)
        if expanded not in _loaded_files:
            _loaded_files.append(expanded)
    return loaded


def setting(name: str, default: str = "") -> str:
    """Real environment first, then ``.env`` files, then the default."""
    return os.environ.get(name) or _file_env.get(name) or default


def loaded_env_files() -> list[Path]:
    return list(_loaded_files)


# Make ``import madmp_client`` alone honour the discoverable .env files;
# scripts call load_env() again to add an explicit --env-file on top.
load_env()

JSON_MEDIA_TYPE = "application/json"
VENDOR_MEDIA_TYPE = "application/vnd.org.rd-alliance.dmp-common.v1.2+json"

# ``GET /dmps`` parameters that may repeat; the RDA spec spells them with a
# ``[]`` suffix, which the adapter accepts alongside the plain name.
ARRAY_PARAMS = frozenset({
    "sort",
    "languages",
    "query",
    "ethical_issues_exist",
    "dataset_ids",
    "contributor_ids",
    "contact_ids",
    "dmp_ids",
    "dmp_alternate_identifier",
    "host_ids",
    "funder_ids",
    "grant_ids",
    "metadata_standard_ids",
    "license_refs",
    "distribution_formats",
    "distribution_data_access",
    "funding_status",
    "dataset_personal_data",
    "dataset_sensitive_data",
})


class ApiError(RuntimeError):
    """A non-2xx response, carrying the RDA ``error_code`` when present."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        method: str = "",
        url: str = "",
    ) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.method = method
        self.url = url


class ConnectionFailedError(RuntimeError):
    """The API (or the Wizard) could not be reached at all."""


@dataclass
class Dmp:
    """One ``{id, dmp}`` item as returned by the API."""

    id: str
    dmp: dict[str, Any]
    last_modified: str | None = None

    @property
    def title(self) -> str:
        return str(self.dmp.get("title", ""))

    @property
    def language(self) -> str:
        return str(self.dmp.get("language", ""))

    @property
    def modified(self) -> str:
        return str(self.dmp.get("modified", ""))

    @property
    def created(self) -> str:
        return str(self.dmp.get("created", ""))

    @property
    def dmp_id(self) -> str:
        identifier = self.dmp.get("dmp_id") or {}
        return str(identifier.get("identifier", ""))

    @property
    def datasets(self) -> list[dict[str, Any]]:
        return list(self.dmp.get("dataset") or [])

    @property
    def contributors(self) -> list[dict[str, Any]]:
        return list(self.dmp.get("contributor") or [])

    def document(self) -> dict[str, Any]:
        """The request body shape for POST / PUT (``{"dmp": …}``)."""
        return {"dmp": self.dmp}


@dataclass
class Page:
    total_count: int
    items: list[Dmp] = field(default_factory=list)


def login(
    wizard_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> str:
    """Obtain a Wizard access token (same call as ``example/prepare.py``)."""
    wizard_url = wizard_url or setting("WIZARD_URL", DEFAULT_WIZARD_URL)
    email = email or setting("WIZARD_EMAIL", DEFAULT_EMAIL)
    password = password or setting("WIZARD_PASSWORD", DEFAULT_PASSWORD)
    url = f"{wizard_url.rstrip('/')}/wizard-api/tokens"
    try:
        response = httpx.post(
            url,
            json={"email": email, "password": password},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        msg = f"cannot reach the Wizard at {wizard_url}: {exc}"
        raise ConnectionFailedError(msg) from exc
    if response.status_code >= 400:
        msg = f"Wizard login failed ({response.status_code}): {response.text}"
        raise ConnectionFailedError(msg)
    return str(response.json()["token"])


def resolve_token() -> str:
    """``MADMP_TOKEN`` when set, otherwise a freshly minted Wizard token."""
    return setting("MADMP_TOKEN") or login()


class MadmpClient:
    """The five RDA operations over ``/dmps``, with request tracing."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        accept: str | None = None,
        timeout: float = 60.0,
        brackets: bool = False,
        trace: bool = True,
    ) -> None:
        resolved = base_url or setting("MADMP_API_URL", DEFAULT_API_URL)
        self.base_url = resolved.rstrip("/")
        self.token = resolve_token() if token is None else token
        self.accept = accept
        self.brackets = brackets
        self.trace = trace
        # follow_redirects: a mistyped path (``/dmps/`` with an empty id)
        # otherwise comes back as a 307 that would read as success.
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
        )

    def __enter__(self) -> MadmpClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- plumbing --------------------------------------------------------

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.accept:
            headers["Accept"] = self.accept
        headers.update(extra or {})
        return headers

    def _params(self, filters: dict[str, Any]) -> list[tuple[str, str]]:
        """Flatten filters into query pairs, repeating array parameters."""
        pairs: list[tuple[str, str]] = []
        for name, value in filters.items():
            if value is None or value == []:
                continue
            values = value if isinstance(value, (list, tuple)) else [value]
            key = (
                f"{name}[]"
                if self.brackets and name in ARRAY_PARAMS
                else name
            )
            pairs.extend((key, str(item)) for item in values)
        return pairs

    def request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request = self._http.build_request(
            method,
            path,
            # A tuple, not the list: httpx types its pairs covariantly.
            params=tuple(params) if params is not None else None,
            json=json_body,
            headers=self._headers(headers),
        )
        if self.trace:
            console.trace(f"→ {method} {request.url}")
        started = time.perf_counter()
        try:
            response = self._http.send(request)
        except httpx.HTTPError as exc:
            msg = f"cannot reach the maDMP API at {self.base_url}: {exc}"
            raise ConnectionFailedError(msg) from exc
        elapsed = (time.perf_counter() - started) * 1000
        if self.trace:
            media = response.headers.get("content-type", "-").split(";")[0]
            console.trace(
                f"← {response.status_code} {media} ({elapsed:.0f} ms)",
            )
        if response.status_code >= 400:
            raise _api_error(response, method)
        return response

    # --- the five operations --------------------------------------------

    def list_dmps(self, **filters: Any) -> Page:
        response = self.request(
            "GET",
            "/dmps",
            params=self._params(filters),
        )
        body = response.json()
        return Page(
            total_count=int(body.get("total_count", 0)),
            items=[
                Dmp(id=str(item["id"]), dmp=item["dmp"])
                for item in body.get("items", [])
            ],
        )

    def get_dmp(self, dmp_id: str, *, accept: str | None = None) -> Dmp:
        headers = {"Accept": accept} if accept else None
        response = self.request("GET", f"/dmps/{dmp_id}", headers=headers)
        return _to_dmp(response)

    def create_dmp(
        self,
        document: dict[str, Any],
        *,
        content_type: str = JSON_MEDIA_TYPE,
    ) -> Dmp:
        response = self.request(
            "POST",
            "/dmps",
            json_body=document,
            headers={"Content-Type": content_type},
        )
        return _to_dmp(response)

    def replace_dmp(
        self,
        dmp_id: str,
        document: dict[str, Any],
        *,
        if_unmodified_since: str | None = None,
        content_type: str = JSON_MEDIA_TYPE,
    ) -> Dmp:
        headers = {"Content-Type": content_type}
        if if_unmodified_since:
            headers["If-Unmodified-Since"] = if_unmodified_since
        response = self.request(
            "PUT",
            f"/dmps/{dmp_id}",
            json_body=document,
            headers=headers,
        )
        return _to_dmp(response)

    def delete_dmp(self, dmp_id: str) -> None:
        self.request("DELETE", f"/dmps/{dmp_id}")

    # --- conveniences ----------------------------------------------------

    def iter_all(self, page_size: int = 20, **filters: Any) -> list[Dmp]:
        """Walk every page of ``GET /dmps`` (offset/count pagination)."""
        collected: list[Dmp] = []
        offset = 0
        while True:
            page = self.list_dmps(offset=offset, count=page_size, **filters)
            collected.extend(page.items)
            offset += page_size
            if offset >= page.total_count or not page.items:
                return collected


def _to_dmp(response: httpx.Response) -> Dmp:
    body = response.json()
    return Dmp(
        id=str(body["id"]),
        dmp=body["dmp"],
        last_modified=response.headers.get("Last-Modified"),
    )


def _api_error(response: httpx.Response, method: str) -> ApiError:
    code, message = "unknown_error", response.text[:300]
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code = str(body.get("error_code", code))
        message = str(body.get("error_message", message))
    return ApiError(
        response.status_code,
        code,
        message,
        method=method,
        url=str(response.request.url),
    )
