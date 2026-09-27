"""Managing API keys from the command line.

utm-tracker create-key "Marketing team"
utm-tracker list-keys
utm-tracker revoke-key utm_AbCdEfGh
"""

import argparse
from datetime import UTC, datetime

from sqlalchemy import select

from utm_tracker.db import get_sessionmaker
from utm_tracker.models import ApiKey
from utm_tracker.security import create_api_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="utm-tracker")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-key", help="Create an API key and print it once.")
    create.add_argument("name")
    commands.add_parser("list-keys", help="List keys by prefix.")
    revoke = commands.add_parser("revoke-key", help="Revoke a key by its prefix.")
    revoke.add_argument("prefix")
    args = parser.parse_args(argv)

    with get_sessionmaker()() as session:
        if args.command == "create-key":
            row, key = create_api_key(session, args.name)
            print(f"Created key {row.prefix}... for {row.name!r}.")
            print(f"Store it now; it is not shown again:\n\n{key}")
            return 0

        if args.command == "list-keys":
            for row in session.scalars(select(ApiKey).order_by(ApiKey.id)):
                state = f"revoked {row.revoked_at:%Y-%m-%d}" if row.revoked_at else "active"
                print(f"{row.prefix}...  {row.name}  ({state})")
            return 0

        key_row = session.scalar(select(ApiKey).where(ApiKey.prefix == args.prefix))
        if key_row is None:
            print(f"No key with prefix {args.prefix}.")
            return 1
        key_row.revoked_at = datetime.now(UTC)
        session.commit()
        print(f"Revoked {key_row.prefix}...")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
