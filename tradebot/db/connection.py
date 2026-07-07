from __future__ import annotations
import duckdb

_connection: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        from tradebot.config import settings
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _connection = duckdb.connect(database=str(settings.db_path))
    return _connection


def _reset_connection() -> None:
    """Close and clear the singleton. Used only in tests."""
    global _connection
    if _connection is not None:
        _connection.close()
    _connection = None
