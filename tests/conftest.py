import pytest
import duckdb
from tradebot.db import schema


@pytest.fixture()
def db(monkeypatch):
    """In-memory DuckDB connection with all tables created.

    Monkeypatches tradebot.db.connection._connection so that any code
    calling get_connection() (including init_db()) receives this
    in-memory connection instead of opening the file-backed DB.
    """
    conn = duckdb.connect(database=":memory:")
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    monkeypatch.setattr("tradebot.db.connection._connection", conn)
    yield conn
    conn.close()
