import pytest

from tradebot.db import bind_mode, init_db, schema
from tradebot.db.connection import open_database
from tradebot.db.migrations import run_migrations


def test_init_db_from_empty_database(empty_db):
    init_db(empty_db)
    init_db(empty_db)
    names = {r[0] for r in empty_db.execute("SHOW TABLES").fetchall()}
    assert {"raw_prices", "legacy_raw_prices", "price_snapshots", "latest_prices", "raw_insider", "orders", "trades"} <= names
    assert empty_db.execute("SELECT version FROM schema_versions ORDER BY version").fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,), (7,), (8,)]


def test_upgrade_preserves_legacy_data(empty_db):
    for ddl in schema.ALL_TABLES:
        empty_db.execute(ddl)
    empty_db.execute("INSERT INTO schema_versions (version, name) VALUES (1, '001_initial.sql')")
    empty_db.execute("INSERT INTO raw_prices VALUES (1, 'AAPL', '2024-01-02', 1, 2, 1, 2, 100, now(), 'yfinance')")
    empty_db.execute("INSERT INTO raw_insider VALUES ('a:0', 'AAPL', 'Buyer', '2024-01-02', '2024-01-03', 1, 2, 'Form4', 'P', now())")
    init_db(empty_db)
    init_db(empty_db)
    assert empty_db.execute("SELECT close FROM legacy_raw_prices").fetchone() == (2,)
    assert empty_db.execute("SELECT id, raw_xml FROM raw_insider").fetchone() == ('a:0', None)
    assert empty_db.execute("SELECT count(*) FROM latest_prices").fetchone() == (0,)
    insider_type = {row[0]: row[1] for row in empty_db.execute("DESCRIBE raw_insider").fetchall()}
    assert insider_type["fetched_at"] == "TIMESTAMP WITH TIME ZONE"


def test_failed_migration_rolls_back_schema_and_version(empty_db, tmp_path):
    empty_db.execute(schema.SCHEMA_VERSIONS)
    migration = tmp_path / "001_test.sql"
    migration.write_text("CREATE TABLE test (id INTEGER); INSERT INTO missing VALUES (1);")
    with pytest.raises(Exception):
        run_migrations(empty_db, tmp_path)
    assert ('test',) not in empty_db.execute("SHOW TABLES").fetchall()
    assert empty_db.execute("SELECT count(*) FROM schema_versions").fetchone() == (0,)
    migration.write_text("CREATE TABLE test (id INTEGER);")
    run_migrations(empty_db, tmp_path)
    run_migrations(empty_db, tmp_path)
    assert empty_db.execute("SELECT count(*) FROM schema_versions").fetchone() == (1,)


def test_migration_order_is_numeric(empty_db, tmp_path):
    empty_db.execute(schema.SCHEMA_VERSIONS)
    (tmp_path / "2_first.sql").write_text("CREATE TABLE test (id INTEGER);")
    (tmp_path / "10_second.sql").write_text("INSERT INTO test VALUES (10);")
    run_migrations(empty_db, tmp_path)
    assert empty_db.execute("SELECT * FROM test").fetchall() == [(10,)]


def test_duplicate_versions_rejected(empty_db, tmp_path):
    empty_db.execute(schema.SCHEMA_VERSIONS)
    for name in ("1_a.sql", "01_b.sql"):
        (tmp_path / name).write_text("-- empty")
    with pytest.raises(ValueError, match="Duplicate"):
        run_migrations(empty_db, tmp_path)


def test_mode_is_bound_to_database(db):
    bind_mode(db, "paper")
    bind_mode(db, "paper")
    with pytest.raises(ValueError, match="mode differs"):
        bind_mode(db, "live")


def test_legacy_execution_requires_manual_classification(db):
    db.execute("INSERT INTO orders (id,ticker,side,qty) VALUES ('o','AAPL','buy',1)")
    with pytest.raises(ValueError, match="Legacy execution"):
        bind_mode(db, "paper")


def test_file_database_can_be_reopened(tmp_path):
    path = tmp_path / "nested" / "test.duckdb"
    with open_database(path) as conn:
        init_db(conn)
        bind_mode(conn, "paper")
    with open_database(path) as conn:
        init_db(conn)
        bind_mode(conn, "paper")
