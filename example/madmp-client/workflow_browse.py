#!/usr/bin/env python3
"""Read-only workflow: list, paginate, sort and filter ``GET /dmps``.

Touches nothing — every request is a GET, so it is safe to run against any
deployment you can read. It discovers filter values from the first DMP the
API returns, so it works with whatever the Wizard happens to hold.

Usage:
    uv run python example/madmp-client/workflow_browse.py [--api-url URL]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import console  # noqa: E402
from madmp_client import (  # noqa: E402
    ApiError,
    ConnectionFailedError,
    Dmp,
    MadmpClient,
    Page,
    load_env,
)


def show(page: Page) -> None:
    console.info(f"total_count={page.total_count}, items={len(page.items)}")
    console.table(
        ["id", "title", "lang", "datasets", "modified"],
        [
            [d.id, d.title, d.language, len(d.datasets), d.modified]
            for d in page.items
        ],
    )


def browse_first_page(client: MadmpClient) -> Page:
    console.step(1, "First page (defaults: offset=0, count=20, created desc)")
    page = client.list_dmps()
    show(page)
    if not page.items:
        console.warn(
            "no DMPs visible — seed one with: "
            "uv run python example/prepare.py --seed",
        )
    return page


def paginate(client: MadmpClient, total: int) -> None:
    console.step(2, "Pagination with offset / count (one item per page)")
    for offset in range(min(total, 3)):
        page = client.list_dmps(offset=offset, count=1)
        titles = ", ".join(d.title for d in page.items) or "-"
        console.info(f"offset={offset} count=1 → {titles}")
    console.info(
        "count is capped at 100; count=0 or a negative offset is a 400",
    )


def sorting(client: MadmpClient) -> None:
    console.step(3, "Sorting (sort=field,direction — repeatable)")
    for spec in ("title,asc", "title,desc", "modified,desc"):
        page = client.list_dmps(sort=[spec], count=5)
        titles = " | ".join(d.title for d in page.items) or "-"
        console.info(f"sort={spec:<14} → {titles}")
    page = client.list_dmps(sort=["language,asc", "title,asc"], count=5)
    console.info(f"multi-key sort returned {len(page.items)} item(s)")


def filtering(client: MadmpClient, sample: Dmp) -> None:
    console.step(4, "Filtering (values taken from the first DMP)")

    page = client.list_dmps(languages=[sample.language])
    console.info(f"languages={sample.language} → {page.total_count}")

    term = next(
        (word for word in sample.title.split() if len(word) > 3),
        sample.title,
    )
    page = client.list_dmps(query=[term])
    console.info(f"query={term!r} (full-text over title/description/datasets)"
                 f" → {page.total_count}")

    page = client.list_dmps(dmp_ids=[sample.dmp_id])
    console.info(f"dmp_ids=<its own dmp_id> → {page.total_count}")

    if sample.datasets:
        dataset_id = sample.datasets[0]["dataset_id"]["identifier"]
        page = client.list_dmps(dataset_ids=[dataset_id])
        console.info(f"dataset_ids={dataset_id} → {page.total_count}")

    contact_id = sample.dmp["contact"]["contact_id"]["identifier"]
    page = client.list_dmps(contact_ids=[contact_id])
    console.info(f"contact_ids=<the DSW user> → {page.total_count}")

    for value in ("yes", "no", "unknown"):
        page = client.list_dmps(ethical_issues_exist=[value])
        console.info(f"ethical_issues_exist={value:<8} → {page.total_count}")

    page = client.list_dmps(
        dataset_personal_data=["no"], dataset_sensitive_data=["no"],
    )
    console.info(f"personal_data=no AND sensitive_data=no → {page.total_count}")


def date_windows(client: MadmpClient, sample: Dmp) -> None:
    console.step(5, "Date windows (ISO 8601, inclusive *_before, exclusive *_after)")
    console.info(f"reference DMP modified at {sample.modified}")
    page = client.list_dmps(modified_before=sample.modified)
    console.info(f"modified_before={sample.modified} → {page.total_count}")
    page = client.list_dmps(modified_after=sample.modified)
    console.info(f"modified_after={sample.modified}  → {page.total_count}")
    page = client.list_dmps(created_before="1970-01-01T00:00:00+00:00")
    console.info(f"created_before=epoch (expects 0)  → {page.total_count}")


def bracket_syntax(client: MadmpClient, sample: Dmp) -> None:
    console.step(6, "RDA bracket syntax: languages[]= is the same filter")
    plain = client.list_dmps(languages=[sample.language]).total_count
    with MadmpClient(
        base_url=client.base_url,
        token=client.token,
        brackets=True,
        trace=client.trace,
    ) as bracketed:
        rda = bracketed.list_dmps(languages=[sample.language]).total_count
    verdict = console.ok if plain == rda else console.fail
    verdict(f"languages= → {plain}, languages[]= → {rda}")


def walk_everything(client: MadmpClient) -> None:
    console.step(7, "Walking every page (client-side pagination helper)")
    items = client.iter_all(page_size=2)
    console.ok(f"collected {len(items)} DMP(s) across pages of 2")


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

    console.heading("maDMP API — browse workflow (read-only)")
    try:
        for path in load_env(args.env_file):
            console.trace(f"config: {path}")
        with MadmpClient(
            base_url=args.api_url, token=args.token, trace=not args.quiet,
        ) as client:
            console.info(f"API: {client.base_url}")
            page = browse_first_page(client)
            if not page.items:
                return 1
            sample = page.items[0]
            paginate(client, page.total_count)
            sorting(client)
            filtering(client, sample)
            date_windows(client, sample)
            bracket_syntax(client, sample)
            walk_everything(client)
    except ApiError as exc:
        console.fail(f"{exc.status} {exc.code}: {exc.message}")
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
