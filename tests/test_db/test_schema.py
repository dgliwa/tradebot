"""Schema-level tests covering DATA-01 through DATA-05."""
import pytest


def test_schema_table_separation(db):
    """DATA-01: Raw, signal, and execution tables are separate (not collapsed)."""
    rows = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert {"raw_prices", "raw_insider", "raw_congressional", "raw_macro"} <= table_names
    assert {"signals", "recommendations", "universe_snapshots"} <= table_names
    assert {"orders", "trades"} <= table_names


def test_raw_prices_immutable(db):
    """DATA-02: raw_prices PRIMARY KEY prevents overwriting existing rows (immutable append)."""
    db.execute(
        "INSERT INTO raw_prices VALUES "
        "(1, 'AAPL', '2024-01-02', 180.0, 182.0, 179.0, 181.0, 1000000, "
        "'2024-01-03 10:00:00+00', 'yfinance')"
    )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO raw_prices VALUES "
            "(1, 'AAPL', '2024-01-02', 999.0, 999.0, 999.0, 999.0, 0, "
            "'2024-01-04 10:00:00+00', 'yfinance')"
        )
    row = db.execute("SELECT close FROM raw_prices WHERE id = 1").fetchone()
    assert row[0] == 181.0


def test_disclosure_dates(db):
    """DATA-03 / SIGNAL-02: transaction_date and filed_at are separate columns."""
    db.execute(
        "INSERT INTO raw_insider VALUES "
        "('tx1', 'MSFT', 'Jane Smith', '2024-01-10', '2024-01-15', "
        "500.0, 300.0, 'Form4', 'P', '2024-01-15 12:00:00+00')"
    )
    row = db.execute(
        "SELECT transaction_date, filed_at FROM raw_insider WHERE id = 'tx1'"
    ).fetchone()
    assert str(row[0]) == "2024-01-10"
    assert str(row[1]) == "2024-01-15"
    assert row[0] != row[1]


def test_instruments_options_aware(db):
    """DATA-04: instruments table accepts NULL expiry/strike for stocks, non-NULL for options."""
    db.execute(
        "INSERT INTO instruments VALUES ('AAPL', 'AAPL', 'stock', NULL, NULL, now())"
    )
    db.execute(
        "INSERT INTO instruments VALUES "
        "('AAPL_20251219_C200', 'AAPL', 'call', '2025-12-19', 200.0, now())"
    )
    stock = db.execute(
        "SELECT expiry, strike FROM instruments WHERE id = 'AAPL'"
    ).fetchone()
    assert stock[0] is None and stock[1] is None

    opt = db.execute(
        "SELECT expiry, strike FROM instruments WHERE id = 'AAPL_20251219_C200'"
    ).fetchone()
    assert opt[0] is not None and opt[1] == 200.0


def test_universe_snapshots_queryable(db):
    """DATA-05 / DATA-06: universe_snapshots is queryable by week_start date."""
    db.execute(
        "INSERT INTO universe_snapshots VALUES (1, '2024-01-08', '2024-01-08', 'AAPL', now())"
    )
    db.execute(
        "INSERT INTO universe_snapshots VALUES (2, '2024-01-08', '2024-01-08', 'MSFT', now())"
    )
    db.execute(
        "INSERT INTO universe_snapshots VALUES (3, '2024-01-15', '2024-01-15', 'GOOGL', now())"
    )
    week1 = db.execute(
        "SELECT ticker FROM universe_snapshots WHERE week_start = '2024-01-08' ORDER BY ticker"
    ).fetchall()
    assert [r[0] for r in week1] == ["AAPL", "MSFT"]

    week2 = db.execute(
        "SELECT ticker FROM universe_snapshots WHERE week_start = '2024-01-15'"
    ).fetchall()
    assert [r[0] for r in week2] == ["GOOGL"]
