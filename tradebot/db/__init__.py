"""Database package.

Public API:
    init_db() — create all tables (idempotent) and apply pending migrations.
"""
from tradebot.db import schema
from tradebot.db.connection import get_connection
from tradebot.db.migrations import run_migrations


def init_db() -> None:
    """Initialize the database: create all tables then run pending migrations.

    Safe to call multiple times — all DDL uses IF NOT EXISTS (D-06).
    """
    conn = get_connection()
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    run_migrations(conn)
