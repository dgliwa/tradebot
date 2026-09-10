"""Initialize the frozen v1 baseline, then apply versioned SQL upgrades."""
from __future__ import annotations

import duckdb

from tradebot.db import schema
from tradebot.db.migrations import run_migrations


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    run_migrations(conn)


def bind_mode(conn: duckdb.DuckDBPyConnection, mode: str) -> None:
    """Prevent paper/live reuse of the same database, including explicit paths."""
    if mode not in {"paper", "live"}:
        raise ValueError("Invalid database mode")
    row = conn.execute("SELECT value FROM database_metadata WHERE key = 'mode'").fetchone()
    if row:
        if row[0] != mode:
            raise ValueError("Database mode differs from TRADEBOT_MODE; use a separate database")
        return
    if any(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("orders", "trades")):
        raise ValueError("Legacy execution data has no mode; classify it manually before using this database")
    conn.execute("INSERT INTO database_metadata VALUES ('mode', ?)", [mode])
