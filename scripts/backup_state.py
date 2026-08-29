#!/usr/bin/env python3
"""Create a hashed GoldGuard SQLite backup. Operator-owned; no secrets in the archive."""

from __future__ import annotations

import argparse
from pathlib import Path

from goldguard.operations.backups import BackupService


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup GoldGuard SQLite")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--key", default="")
    args = parser.parse_args()
    forbidden = {Path("/"), Path.home()}
    if args.out.resolve() in forbidden or args.db.resolve() in forbidden:
        raise SystemExit("refusing to read or write a filesystem root")
    manifest = BackupService().create(args.db, args.out, key=args.key)
    print(f"backup {manifest.manifest_id} hash={manifest.source_db_hash}")


if __name__ == "__main__":
    main()
