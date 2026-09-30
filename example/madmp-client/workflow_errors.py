#!/usr/bin/env python3
"""Error-path workflow: the RDA error codes, exercised one by one.

Every request here is either a read or a write the API is expected to
reject before it reaches DSW, so nothing is created, changed or deleted.
Each check prints the expected status/error_code against what came back and
the script exits non-zero if any check does not match.

Usage:
    uv run python example/madmp-client/workflow_errors.py [--api-url URL]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import console  # noqa: E402
from madmp_client import (  # noqa: E402
    VENDOR_MEDIA_TYPE,
    ApiError,
    ConnectionFailedError,
    MadmpClient,
    load_env,
)

SAMPLE = Path(__file__).resolve().parent / "sample-dmp.json"
MISSING_ID = str(uuid.UUID(int=0))


class Results:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def expect(
        self,
        label: str,
        status: int,
        code: str,
        call: Callable[[], object],
    ) -> None:
        console.info(label)
        try:
            call()
        except ApiError as exc:
            if exc.status == status and exc.code == code:
                self.passed += 1
                console.ok(f"{exc.status} {exc.code} — {exc.message}")
            else:
                self.failed += 1
                console.fail(
                    f"expected {status} {code}, got {exc.status} {exc.code} "
                    f"— {exc.message}",
                )
            return
        self.failed += 1
        console.fail(f"expected {status} {code}, but the request succeeded")

    def expect_ok(self, label: str, call: Callable[[], object]) -> None:
        console.info(label)
        try:
            call()
        except ApiError as exc:
            self.failed += 1
            console.fail(f"expected success, got {exc.status} {exc.code}")
            return
        self.passed += 1
        console.ok("succeeded as expected")


def not_found(client: MadmpClient, results: Results) -> None:
    console.step(1, "Unknown DMP → 404 dmp_not_found")
    results.expect(
        f"GET /dmps/{MISSING_ID}",
        404,
        "dmp_not_found",
        lambda: client.get_dmp(MISSING_ID),
    )


def bad_query(client: MadmpClient, results: Results) -> None:
    console.step(2, "Malformed query strings → 400 invalid_query_string")
    cases = [
        ("sort=created (no direction)", {"sort": ["created"]}),
        ("sort=nope,asc (unknown field)", {"sort": ["nope,asc"]}),
        ("count=0 (below the minimum)", {"count": 0}),
        ("count=1000 (above the cap of 100)", {"count": 1000}),
        ("offset=-1", {"offset": -1}),
        ("count=many (not an integer)", {"count": "many"}),
        ("created_after=yesterday", {"created_after": "yesterday"}),
    ]
    for label, params in cases:
        results.expect(
            f"GET /dmps?{label}",
            400,
            "invalid_query_string",
            lambda params=params: client.list_dmps(**params),
        )


def content_negotiation(client: MadmpClient, results: Results) -> None:
    console.step(3, "Content negotiation → 406 / 415")
    with MadmpClient(
        base_url=client.base_url,
        token=client.token,
        accept="text/csv",
        trace=client.trace,
    ) as csv_client:
        results.expect(
            "GET /dmps with Accept: text/csv",
            406,
            "not_acceptable",
            lambda: csv_client.list_dmps(count=1),
        )
    with MadmpClient(
        base_url=client.base_url,
        token=client.token,
        accept=VENDOR_MEDIA_TYPE,
        trace=client.trace,
    ) as vendor_client:
        results.expect_ok(
            f"GET /dmps with Accept: {VENDOR_MEDIA_TYPE}",
            lambda: vendor_client.list_dmps(count=1),
        )
    results.expect(
        "POST /dmps with Content-Type: application/vnd.other+json",
        415,
        "unsupported_media_type",
        lambda: client.create_dmp(
            json.loads(SAMPLE.read_text()),
            content_type="application/vnd.other+json",
        ),
    )


def invalid_body(client: MadmpClient, results: Results) -> None:
    console.step(4, "Invalid maDMP document → 400 dmp_invalid")
    missing_contact = json.loads(SAMPLE.read_text())
    del missing_contact["dmp"]["contact"]
    results.expect(
        "POST /dmps without dmp.contact",
        400,
        "dmp_invalid",
        lambda: client.create_dmp(missing_contact),
    )

    wrong_enum = json.loads(SAMPLE.read_text())
    wrong_enum["dmp"]["ethical_issues_exist"] = "maybe"
    results.expect(
        "POST /dmps with ethical_issues_exist=maybe",
        400,
        "dmp_invalid",
        lambda: client.create_dmp(wrong_enum),
    )

    results.expect(
        "PUT /dmps/{id} with an empty body object",
        400,
        "dmp_invalid",
        lambda: client.replace_dmp(MISSING_ID, {}),
    )


def unauthenticated(client: MadmpClient, results: Results) -> None:
    console.step(5, "No Authorization header → 401 authentication_required")
    console.info(
        "the adapter forwards the caller's token to DSW, so authorisation "
        "is DSW's answer, not a local check",
    )
    with MadmpClient(
        base_url=client.base_url, token="", trace=client.trace,
    ) as anonymous:
        results.expect(
            "GET /dmps with no token",
            401,
            "authentication_required",
            lambda: anonymous.list_dmps(count=1),
        )


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
    args = parser.parse_args(argv)

    console.heading("maDMP API — error-path workflow (no writes succeed)")
    results = Results()
    try:
        for path in load_env(args.env_file):
            console.trace(f"config: {path}")
        with MadmpClient(
            base_url=args.api_url, token=args.token, trace=not args.quiet,
        ) as client:
            console.info(f"API: {client.base_url}")
            not_found(client, results)
            bad_query(client, results)
            content_negotiation(client, results)
            invalid_body(client, results)
            unauthenticated(client, results)
    except ConnectionFailedError as exc:
        console.fail(str(exc))
        return 2
    except FileNotFoundError as exc:
        console.fail(f"no such file: {exc.filename}")
        return 2

    console.heading(f"{results.passed} passed, {results.failed} failed")
    return 1 if results.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
