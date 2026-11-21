"""Offline-safe SQLite backup verification helpers for native Windows operation."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from marketintel.config import Settings
from marketintel.storage import Store


def verify_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    if integrity is None or integrity[0] != "ok" or foreign_keys:
        raise RuntimeError("Database integrity verification failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Intelligence database maintenance")
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup = subcommands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    verify = subcommands.add_parser("verify")
    verify.add_argument("database", type=Path)
    args = parser.parse_args()
    if args.command == "backup":
        Store(Settings().database_path).backup_to(args.destination)
        verify_database(args.destination)
    else:
        verify_database(args.database)


if __name__ == "__main__":
    main()
