"""Transactional, numerically ordered upgrades from the frozen v1 baseline."""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

MIGRATIONS_DIR = Path(__file__).parent


def run_migrations(conn: duckdb.DuckDBPyConnection, directory: Path = MIGRATIONS_DIR) -> None:
    migrations: dict[int, Path] = {}
    for path in directory.glob("*.sql"):
        match = re.fullmatch(r"(\d+)_.+\.sql", path.name)
        if not match:
            raise ValueError(f"Invalid migration filename: {path.name}")
        version = int(match[1])
        if version in migrations:
            raise ValueError(f"Duplicate migration version: {version}")
        migrations[version] = path

    applied = dict(conn.execute("SELECT version, name FROM schema_versions").fetchall())
    for version, name in applied.items():
        if version not in migrations or migrations[version].name != name:
            raise ValueError(f"Unknown or renamed applied migration: {version} ({name})")
    for version, path in sorted(migrations.items()):
        if version in applied:
            continue
        if applied and version < max(applied):
            raise ValueError(f"Out-of-order migration: {version}")
        conn.execute("BEGIN TRANSACTION")
        try:
            sql = path.read_text(encoding="utf-8")
            if sql.strip():
                conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
                [version, path.name],
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
