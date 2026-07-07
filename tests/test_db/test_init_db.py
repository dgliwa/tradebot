"""Idempotency tests for init_db() — success criteria 1 and 5."""


def test_init_db_idempotent(db):
    """Running init_db() twice produces no duplicate tables and no errors."""
    from tradebot.db import init_db
    init_db()
    init_db()
    rows = db.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchone()
    assert rows[0] > 0


def test_init_db_creates_all_tables(db):
    """init_db() creates every expected table in a single call."""
    from tradebot.db import init_db
    init_db()
    rows = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    expected = {
        "schema_versions",
        "instruments",
        "raw_prices",
        "raw_insider",
        "raw_congressional",
        "raw_macro",
        "signals",
        "recommendations",
        "orders",
        "trades",
        "universe_snapshots",
    }
    assert expected <= table_names
