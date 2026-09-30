#!/usr/bin/env python3
"""Prepare the example Wizard deployment for the maDMP API.

Idempotent: obtains a token, imports the bundled knowledge model (if it is
not present yet), and optionally seeds a demo project with replies so the
maDMP API has something to serve.

Usage:
    uv run python example/prepare.py [--seed] [--print-token]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BASE = "http://localhost:3000/wizard-api"
EMAIL = "albert.einstein@example.com"
PASSWORD = "password"  # noqa: S105  (documented demo credential)
KM_FILE = Path(__file__).parent / "knowledge-models" / "dsw_root_2.7.0.km"
KM_ID = "dsw:root:2.7.0"

# Question identifiers of the Common DSW Knowledge Model.
CH_COLLECT = "b1df3c74-0b1f-4574-81c4-4cc2d780c1af"
Q_ETHICAL = "ebcbf4c6-ce25-4a0b-9e82-039a88498203"
A_ETHICAL_NO = "579c0a9a-29f0-4ab8-991d-bc4f55f2e4b8"
CH_PRESERVE = "d5b27482-b598-4b8c-b534-417d4ad27394"
Q_DATASETS = "4e0c1edf-660c-4ebf-81f5-9fa959dead30"
Q_DS_TITLE = "b0949d09-d179-4491-9fb4-14b0deb9f862"
Q_DS_DESCRIPTION = "205a886d-83d7-4359-ae63-7103e05357c3"
Q_DS_PERSONAL = "a1d76760-053c-4706-80a2-cfb6c6a061f3"
A_PERSONAL_NO = "4b2a08c7-4942-41fc-8114-d3868c882624"
Q_DS_SENSITIVE = "cc95b399-7d8d-4232-bccf-686f78c91bff"
A_SENSITIVE_NO = "60de66a3-d303-4784-8931-bc58f8a3e747"


def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: Any = None,
    raw: bytes | None = None,
    content_type: str | None = None,
) -> Any:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(  # noqa: S310
        f"{BASE}{path}", data=data, method=method, headers=headers,
    )
    with urllib.request.urlopen(req) as response:  # noqa: S310
        payload = response.read()
    return json.loads(payload) if payload else None


def login() -> str:
    result = request(
        "POST", "/tokens", body={"email": EMAIL, "password": PASSWORD},
    )
    return str(result["token"])


def find_km(token: str) -> dict[str, Any] | None:
    result = request("GET", "/knowledge-model-packages?size=100", token=token)
    packages = result.get("_embedded", {}).get("knowledgeModelPackages", [])
    for package in packages:
        ident = (
            f"{package.get('organizationId')}:"
            f"{package.get('kmId')}:{package.get('version')}"
        )
        if ident == KM_ID:
            return package
    return None


def import_km(token: str) -> dict[str, Any]:
    existing = find_km(token)
    if existing:
        print(f"  knowledge model {KM_ID} already imported")
        return existing
    boundary = f"----madmp{uuid.uuid4().hex}"
    payload = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; '
        f'filename="{KM_FILE.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + KM_FILE.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request(
        "POST",
        "/knowledge-model-packages/bundle",
        token=token,
        raw=payload,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    package = find_km(token)
    if package is None:
        msg = "knowledge model import did not register the package"
        raise RuntimeError(msg)
    print(f"  imported knowledge model {KM_ID}")
    return package


def set_reply(path: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "SetReplyEvent",
        "uuid": str(uuid.uuid4()),
        "path": path,
        "value": value,
    }


def seed_project(token: str, km_uuid: str) -> str:
    project = request(
        "POST",
        "/projects",
        token=token,
        body={
            "name": "Example maDMP Project",
            "knowledgeModelPackageUuid": km_uuid,
            "questionTagUuids": [],
            "sharing": "RestrictedProjectSharing",
            "visibility": "PrivateProjectVisibility",
        },
    )
    uuid_ = str(project["uuid"])
    request(
        "PUT",
        f"/projects/{uuid_}/settings",
        token=token,
        body={
            "name": "Example maDMP Project",
            "description": "Seeded by example/prepare.py",
            "isTemplate": False,
            "projectTags": [],
        },
    )
    item = str(uuid.uuid4())
    ds_list = f"{CH_PRESERVE}.{Q_DATASETS}"
    base = f"{ds_list}.{item}"
    events = [
        set_reply(ds_list, {"type": "ItemListReply", "value": [item]}),
        set_reply(
            f"{base}.{Q_DS_TITLE}",
            {"type": "StringReply", "value": "Sequencing reads"},
        ),
        set_reply(
            f"{base}.{Q_DS_DESCRIPTION}",
            {"type": "StringReply", "value": "Raw FASTQ files"},
        ),
        set_reply(
            f"{base}.{Q_DS_PERSONAL}",
            {"type": "AnswerReply", "value": A_PERSONAL_NO},
        ),
        set_reply(
            f"{base}.{Q_DS_SENSITIVE}",
            {"type": "AnswerReply", "value": A_SENSITIVE_NO},
        ),
        set_reply(
            f"{CH_COLLECT}.{Q_ETHICAL}",
            {"type": "AnswerReply", "value": A_ETHICAL_NO},
        ),
    ]
    request(
        "PUT", f"/projects/{uuid_}/content", token=token,
        body={"events": events},
    )
    print(f"  seeded project {uuid_}")
    return uuid_


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed", action="store_true", help="create a demo project",
    )
    parser.add_argument(
        "--print-token", action="store_true", help="print the access token",
    )
    args = parser.parse_args()

    try:
        token = login()
    except urllib.error.URLError as exc:
        print(f"cannot reach the Wizard at {BASE}: {exc}", file=sys.stderr)
        print("start it with: cd example/wizard && docker compose up -d")
        return 1

    print("Wizard is up")
    package = import_km(token)
    if args.seed:
        seed_project(token, str(package["uuid"]))
    if args.print_token:
        print(token)
    else:
        print("\nRun the maDMP API against it with:")
        print(f"  MADMP_API_WIZARD_URL=http://localhost:3000 "
              f"MADMP_API_WIZARD_DEFAULT_KM={KM_ID} make dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
