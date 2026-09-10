import duckdb
import pytest

from tradebot.db import init_db


@pytest.fixture
def empty_db():
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def db(empty_db):
    init_db(empty_db)
    return empty_db
