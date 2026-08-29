#!/usr/bin/env python3
"""Restore a hashed GoldGuard backup into an empty target."""

from __future__ import annotations

import argparse
from pathlib import Path

from goldguard.operations.backups import BackupService


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore GoldGuard SQLite backup")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--key", default="")
    args = parser.parse_args()
    if args.target.resolve() in {Path("/"), Path.home()}:
        raise SystemExit("refusing to restore onto a filesystem root")
    BackupService().restore(args.archive, args.target, key=args.key)
    print(f"restored {args.target}")


if __name__ == "__main__":
    main()
