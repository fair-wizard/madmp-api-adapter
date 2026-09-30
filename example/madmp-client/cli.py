#!/usr/bin/env python3
"""Console CLI for the maDMP API — the five RDA operations over /dmps.

Examples:
    uv run python example/madmp-client/cli.py token
    uv run python example/madmp-client/cli.py list --count 5 --sort title,asc
    uv run python example/madmp-client/cli.py list --query genome --json
    uv run python example/madmp-client/cli.py get <dmp-id>
    uv run python example/madmp-client/cli.py create --file sample-dmp.json
    uv run python example/madmp-client/cli.py update <dmp-id> --set-title New
    uv run python example/madmp-client/cli.py delete <dmp-id> --yes

Configuration is read from the environment or a .env file (MADMP_API_URL,
MADMP_TOKEN, WIZARD_URL, WIZARD_EMAIL, WIZARD_PASSWORD); see env.example
and madmp_client.py. Command-line flags beat environment variables, which
beat .env files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import console  # noqa: E402
from madmp_client import (  # noqa: E402
    VENDOR_MEDIA_TYPE,
    ApiError,
    ConnectionFailedError,
    Dmp,
    MadmpClient,
    load_env,
    login,
)

SAMPLE = Path(__file__).resolve().parent / "sample-dmp.json"

# CLI flag -> RDA query parameter for the repeatable list filters.
LIST_FILTERS = {
    "sort": "sort",
    "query": "query",
    "language": "languages",
    "ethical_issues_exist": "ethical_issues_exist",
    "dataset_id": "dataset_ids",
    "contributor_id": "contributor_ids",
    "contact_id": "contact_ids",
    "dmp_id": "dmp_ids",
    "alternate_identifier": "dmp_alternate_identifier",
    "host_id": "host_ids",
    "funder_id": "funder_ids",
    "grant_id": "grant_ids",
    "metadata_standard_id": "metadata_standard_ids",
    "license_ref": "license_refs",
    "format": "distribution_formats",
    "data_access": "distribution_data_access",
    "funding_status": "funding_status",
    "personal_data": "dataset_personal_data",
    "sensitive_data": "dataset_sensitive_data",
}

SCALAR_FILTERS = {
    "created_before": "created_before",
    "created_after": "created_after",
    "modified_before": "modified_before",
    "modified_after": "modified_after",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-url", help="maDMP API base URL")
    parser.add_argument("--token", help="bearer token (default: Wizard login)")
    parser.add_argument(
        "--env-file",
        type=Path,
        metavar="PATH",
        help="extra .env file, read on top of the discovered ones",
    )
    parser.add_argument(
        "--vendor-media-type",
        action="store_true",
        help=f"send Accept: {VENDOR_MEDIA_TYPE}",
    )
    parser.add_argument(
        "--rda-brackets",
        action="store_true",
        help="spell array parameters the RDA way (name[]=…)",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="do not trace requests",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("token", help="print a Wizard access token")

    listing = sub.add_parser("list", help="GET /dmps (filter, sort, paginate)")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--count", type=int, default=20, help="page size")
    listing.add_argument(
        "--all",
        action="store_true",
        help="walk every page instead of a single one",
    )
    for flag in LIST_FILTERS:
        listing.add_argument(
            f"--{flag.replace('_', '-')}",
            action="append",
            metavar="VALUE",
            help="repeatable RDA filter",
        )
    for flag in SCALAR_FILTERS:
        listing.add_argument(
            f"--{flag.replace('_', '-')}", metavar="ISO8601",
        )
    listing.add_argument("--json", action="store_true", help="raw JSON output")

    getter = sub.add_parser("get", help="GET /dmps/{id}")
    getter.add_argument("dmp_id")
    getter.add_argument("--json", action="store_true")

    creator = sub.add_parser("create", help="POST /dmps")
    creator.add_argument(
        "--file",
        type=Path,
        default=SAMPLE,
        help=f"maDMP document to send (default: {SAMPLE.name})",
    )
    creator.add_argument("--title", help="override dmp.title before sending")
    creator.add_argument("--json", action="store_true")

    updater = sub.add_parser("update", help="PUT /dmps/{id}")
    updater.add_argument("dmp_id")
    updater.add_argument(
        "--file",
        type=Path,
        help="full replacement document (default: the current one, edited)",
    )
    updater.add_argument("--set-title")
    updater.add_argument("--set-description")
    updater.add_argument(
        "--safe",
        action="store_true",
        help="send If-Unmodified-Since from the current Last-Modified",
    )
    updater.add_argument(
        "--if-unmodified-since", metavar="HTTP_DATE",
    )
    updater.add_argument("--json", action="store_true")

    deleter = sub.add_parser("delete", help="DELETE /dmps/{id}")
    deleter.add_argument("dmp_id")
    deleter.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt",
    )
    return parser


def wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def make_client(args: argparse.Namespace) -> MadmpClient:
    return MadmpClient(
        base_url=args.api_url,
        token=args.token,
        accept=VENDOR_MEDIA_TYPE if args.vendor_media_type else None,
        brackets=args.rda_brackets,
        # --json keeps stdout machine-readable: no traces, no status lines.
        trace=not (args.quiet or wants_json(args)),
    )


def show_dmp(dmp: Dmp, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"id": dmp.id, "dmp": dmp.dmp}, indent=2))
        return
    console.kv("id", dmp.id)
    console.kv("title", dmp.title)
    console.kv("dmp_id", dmp.dmp_id)
    console.kv("language", dmp.language)
    console.kv("created", dmp.created)
    console.kv("modified", dmp.modified)
    console.kv("Last-Modified", dmp.last_modified or "-")
    console.kv("ethical_issues_exist", dmp.dmp.get("ethical_issues_exist"))
    console.kv(
        "datasets",
        ", ".join(str(ds.get("title")) for ds in dmp.datasets) or "-",
    )
    console.kv(
        "contributors",
        ", ".join(str(c.get("name")) for c in dmp.contributors) or "-",
    )


def cmd_list(client: MadmpClient, args: argparse.Namespace) -> int:
    filters: dict[str, Any] = {}
    for flag, param in LIST_FILTERS.items():
        filters[param] = getattr(args, flag)
    for flag, param in SCALAR_FILTERS.items():
        filters[param] = getattr(args, flag)

    if args.all:
        items = client.iter_all(page_size=args.count, **filters)
        total = len(items)
    else:
        page = client.list_dmps(offset=args.offset, count=args.count, **filters)
        items, total = page.items, page.total_count

    if args.json:
        print(json.dumps(
            {
                "total_count": total,
                "items": [{"id": d.id, "dmp": d.dmp} for d in items],
            },
            indent=2,
        ))
        return 0

    console.info(f"total_count={total}, shown={len(items)}")
    console.table(
        ["id", "title", "lang", "datasets", "modified"],
        [
            [d.id, d.title, d.language, len(d.datasets), d.modified]
            for d in items
        ],
    )
    return 0


def cmd_get(client: MadmpClient, args: argparse.Namespace) -> int:
    show_dmp(client.get_dmp(args.dmp_id), as_json=args.json)
    return 0


def cmd_create(client: MadmpClient, args: argparse.Namespace) -> int:
    document = json.loads(args.file.read_text())
    if args.title:
        document["dmp"]["title"] = args.title
    created = client.create_dmp(document)
    if not args.json:
        console.ok(f"created {created.id}")
    show_dmp(created, as_json=args.json)
    return 0


def cmd_update(client: MadmpClient, args: argparse.Namespace) -> int:
    current = client.get_dmp(args.dmp_id)
    if args.file:
        document = json.loads(args.file.read_text())
    else:
        document = current.document()
    if args.set_title:
        document["dmp"]["title"] = args.set_title
    if args.set_description:
        document["dmp"]["description"] = args.set_description
    guard = args.if_unmodified_since
    if args.safe and not guard:
        guard = current.last_modified
        if not args.json:
            console.info(f"If-Unmodified-Since: {guard}")
    updated = client.replace_dmp(
        args.dmp_id, document, if_unmodified_since=guard,
    )
    if not args.json:
        console.ok(f"updated {updated.id}")
    show_dmp(updated, as_json=args.json)
    return 0


def cmd_delete(client: MadmpClient, args: argparse.Namespace) -> int:
    if not args.yes:
        console.warn(
            "DELETE removes the underlying DSW project, not just the "
            "projection.",
        )
        if not console.confirm(f"delete {args.dmp_id}?"):
            console.info("aborted")
            return 1
    client.delete_dmp(args.dmp_id)
    console.ok(f"deleted {args.dmp_id}")
    return 0


COMMANDS = {
    "list": cmd_list,
    "get": cmd_get,
    "create": cmd_create,
    "update": cmd_update,
    "delete": cmd_delete,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # ``list`` has a --dmp-id *filter*; only these take a positional id.
    if args.command in {"get", "update", "delete"} and not args.dmp_id.strip():
        console.fail("the DMP id is empty")
        return 2
    try:
        for path in load_env(args.env_file):
            if not (args.quiet or wants_json(args)):
                console.trace(f"config: {path}")
        if args.command == "token":
            print(args.token or login())
            return 0
        with make_client(args) as client:
            return COMMANDS[args.command](client, args)
    except ApiError as exc:
        console.fail(f"{exc.status} {exc.code}: {exc.message}")
        return 1
    except ConnectionFailedError as exc:
        console.fail(str(exc))
        console.info(
            "start the stack: cd example/wizard && docker compose up -d, "
            "then MADMP_API_WIZARD_URL=http://localhost:3000 make dev",
        )
        return 2
    except FileNotFoundError as exc:
        console.fail(f"no such file: {exc.filename}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
