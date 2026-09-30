#!/usr/bin/env python3
"""Write workflow: create → read → update → conflict → delete.

Creates its **own** throwaway DMP (a real DSW project behind the scenes),
exercises the write path against it, and deletes it again at the end. It
never touches DMPs it did not create. Pass ``--keep`` to leave the created
DMP behind (then remove it yourself with ``cli.py delete <id>``).

Requires the API to run with a usable MADMP_API_WIZARD_DEFAULT_KM, because POST /dmps
creates the project from that knowledge model.

Usage:
    uv run python example/madmp-client/workflow_crud.py [--keep]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import console  # noqa: E402
from madmp_client import (  # noqa: E402
    ApiError,
    ConnectionFailedError,
    Dmp,
    MadmpClient,
    load_env,
)

SAMPLE = Path(__file__).resolve().parent / "sample-dmp.json"
PAST = "Thu, 01 Jan 1970 00:00:00 GMT"


def load_document(title: str) -> dict[str, Any]:
    document = json.loads(SAMPLE.read_text())
    document["dmp"]["title"] = title
    return document


def summarise(dmp: Dmp) -> None:
    console.kv("id", dmp.id)
    console.kv("title", dmp.title)
    console.kv("dmp_id", dmp.dmp_id)
    console.kv("contact", dmp.dmp["contact"]["mbox"])
    console.kv("modified", dmp.modified)
    console.kv("Last-Modified", dmp.last_modified or "-")
    console.kv(
        "datasets",
        ", ".join(str(ds.get("title")) for ds in dmp.datasets) or "-",
    )
    console.kv(
        "contributors",
        ", ".join(str(c.get("name")) for c in dmp.contributors) or "-",
    )


def create(client: MadmpClient, title: str) -> Dmp:
    console.step(1, "POST /dmps — create from sample-dmp.json")
    sent = load_document(title)
    created = client.create_dmp(sent)
    console.ok(f"created {created.id}")
    summarise(created)
    console.info(
        "the server owns the identity fields: dmp_id, contact, created and "
        "modified come from DSW, not from the request body",
    )
    console.info(
        f"sent dmp_id={sent['dmp']['dmp_id']['identifier']} → "
        f"stored dmp_id={created.dmp_id}",
    )
    return created


def read_back(client: MadmpClient, dmp_id: str) -> Dmp:
    console.step(2, "GET /dmps/{id} — read the stored projection back")
    fetched = client.get_dmp(dmp_id)
    summarise(fetched)
    return fetched


def find_in_list(client: MadmpClient, created: Dmp, baseline: int) -> None:
    console.step(3, "GET /dmps — the new DMP is listed and filterable")
    page = client.list_dmps(count=100)
    console.info(f"total_count {baseline} → {page.total_count}")
    hit = next((d for d in page.items if d.id == created.id), None)
    (console.ok if hit else console.fail)(
        "found in the listing" if hit else "missing from the listing",
    )
    page = client.list_dmps(dmp_ids=[created.dmp_id])
    console.info(f"dmp_ids=<its dmp_id> → total_count={page.total_count}")
    term = created.title.split()[-1]
    page = client.list_dmps(query=[term])
    console.info(f"query={term!r} → total_count={page.total_count}")


def update(client: MadmpClient, current: Dmp) -> Dmp:
    console.step(4, "PUT /dmps/{id} — full replacement, guarded by "
                    "If-Unmodified-Since")
    document = current.document()
    document["dmp"]["title"] = f"{current.title} (updated)"
    document["dmp"]["description"] = "Rewritten by workflow_crud.py"
    document["dmp"]["dataset"] = document["dmp"]["dataset"][:1]
    document["dmp"]["ethical_issues_exist"] = "yes"
    console.info(f"If-Unmodified-Since: {current.last_modified}")
    updated = client.replace_dmp(
        current.id, document, if_unmodified_since=current.last_modified,
    )
    console.ok("replaced")
    summarise(updated)
    console.info(
        "PUT is a replacement, not a patch: the dropped dataset is gone, and "
        "dataset identifiers are re-minted by DSW on every write",
    )
    return updated


def conflict(client: MadmpClient, current: Dmp) -> bool:
    console.step(5, "PUT with a stale If-Unmodified-Since → 409 conflict")
    try:
        client.replace_dmp(
            current.id, current.document(), if_unmodified_since=PAST,
        )
    except ApiError as exc:
        if exc.status == 409:  # noqa: PLR2004
            console.ok(f"rejected as expected: {exc.code} — {exc.message}")
            return True
        console.fail(f"unexpected error: {exc.status} {exc.code}")
        return False
    console.fail("the stale guard was accepted — the write went through")
    return False


def delete(client: MadmpClient, dmp_id: str, baseline: int) -> bool:
    console.step(6, "DELETE /dmps/{id} — and confirm it is gone")
    client.delete_dmp(dmp_id)
    console.ok(f"deleted {dmp_id} (the DSW project is removed too)")
    try:
        client.get_dmp(dmp_id)
    except ApiError as exc:
        if exc.status == 404:  # noqa: PLR2004
            console.ok(f"GET now returns {exc.status} {exc.code}")
        else:
            console.fail(f"unexpected error: {exc.status} {exc.code}")
            return False
    else:
        console.fail("the deleted DMP is still readable")
        return False
    total = client.list_dmps(count=1).total_count
    (console.ok if total == baseline else console.warn)(
        f"total_count back to {total} (baseline {baseline})",
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url")
    parser.add_argument("--token")
    parser.add_argument(
        "--env-file",
        type=Path,
        metavar="PATH",
        help="extra .env file, read on top of the discovered ones",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="do not delete the DMP this workflow creates",
    )
    args = parser.parse_args(argv)

    title = f"Console client CRUD run {uuid.uuid4().hex[:8]}"
    console.heading("maDMP API — CRUD workflow (creates and deletes one DMP)")
    created: Dmp | None = None
    try:
        for path in load_env(args.env_file):
            console.trace(f"config: {path}")
        with MadmpClient(
            base_url=args.api_url, token=args.token, trace=not args.quiet,
        ) as client:
            console.info(f"API: {client.base_url}")
            baseline = client.list_dmps(count=1).total_count
            console.info(f"baseline total_count={baseline}")

            created = create(client, title)
            fetched = read_back(client, created.id)
            find_in_list(client, created, baseline)
            updated = update(client, fetched)
            conflict(client, updated)
            if args.keep:
                console.warn(f"--keep: leaving {created.id} in place")
                return 0
            delete(client, created.id, baseline)
    except ApiError as exc:
        console.fail(f"{exc.status} {exc.code}: {exc.message}")
        if created is not None:
            console.warn(
                f"leftover DMP {created.id} — remove it with: "
                f"cli.py delete {created.id} --yes",
            )
        return 1
    except ConnectionFailedError as exc:
        console.fail(str(exc))
        return 2
    except FileNotFoundError as exc:
        console.fail(f"no such file: {exc.filename}")
        return 2
    console.heading("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
