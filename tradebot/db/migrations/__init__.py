"""Versioned migration runner (D-08).

Discovers *.sql files in this directory by numeric prefix, applies each
migration exactly once, and records it in schema_versions.
"""
from __future__ import annotations
import re
from pathlib import Path
import duckdb

MIGRATIONS_DIR = Path(__file__).parent


def _applied_versions(conn: duckdb.DuckDBPyConnection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_versions ORDER BY version").fetchall()
    return {row[0] for row in rows}


def run_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply any un-applied *.sql migrations in numeric order."""
    applied = _applied_versions(conn)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = re.match(r"^(\d+)_", path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        if sql.strip():
            conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
            [version, path.name],
        )
