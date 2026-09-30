"""``madmp-api`` command line: operational tasks outside the web process."""

import argparse
import asyncio

from madmp_api.config import load_settings
from madmp_api.store.db import Database


async def _migrate(url: str, table_prefix: str) -> None:
    database = Database(url, table_prefix)
    try:
        await database.ready()
    finally:
        await database.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='madmp-api')
    commands = parser.add_subparsers(dest='command', required=True)
    migrate_cmd = commands.add_parser(
        'migrate',
        help='apply pending store migrations (also done on startup)',
    )
    migrate_cmd.add_argument(
        '--config',
        help='YAML configuration file (default: $MADMP_API_CONFIG_PATH)',
    )
    args = parser.parse_args(argv)

    if args.command == 'migrate':
        settings = load_settings(args.config)
        asyncio.run(_migrate(settings.database_url, settings.table_prefix))


if __name__ == '__main__':
    main()
