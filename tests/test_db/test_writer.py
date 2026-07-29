from __future__ import annotations
from datetime import date, datetime

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from tradebot.db.writer import _price_id, write_raw_records
from tradebot.models.raw_record import RawRecord


def _price_record(
    ticker: str = "AAPL",
    trade_date: date = date(2026, 5, 1),
    close: float = 175.0,
) -> RawRecord:
    return RawRecord(
        source="yfinance",
        ticker=ticker,
        fetched_at=datetime(2026, 7, 7, 12, 0, 0),
        transaction_date=trade_date,
        filed_at=None,
        data={
            "open": 174.0,
            "high": 176.0,
            "low": 173.0,
            "close": close,
            "volume": 50_000_000,
        },
    )


def _insider_record(
    ticker: str = "AAPL",
    accession: str = "0001140361-26-025622",
    idx: int = 0,
) -> RawRecord:
    return RawRecord(
        source="edgar",
        ticker=ticker,
        fetched_at=datetime(2026, 7, 7, 12, 0, 0),
        transaction_date=date(2026, 5, 15),
        filed_at=date(2026, 5, 16),
        data={
            "accession": accession,
            "transaction_index": idx,
            "filer_name": "Test Buyer",
            "transaction_code": "P",
            "shares": 1000.0,
            "price_per_share": 175.50,
        },
    )


def test_write_raw_prices_inserts_rows(db):
    records = [
        _price_record("AAPL", date(2026, 5, 1)),
        _price_record("AAPL", date(2026, 5, 2)),
        _price_record("MSFT", date(2026, 5, 1)),
    ]
    count = write_raw_records(db, "raw_prices", records)

    assert count == 3
    row_count = db.execute("SELECT COUNT(*) FROM raw_prices").fetchone()[0]
    assert row_count == 3


def test_write_raw_insider_inserts_rows(db):
    records = [
        _insider_record("AAPL", "0001140361-26-025622", 0),
        _insider_record("MSFT", "0001140361-26-099999", 0),
    ]
    count = write_raw_records(db, "raw_insider", records)

    assert count == 2
    row_count = db.execute("SELECT COUNT(*) FROM raw_insider").fetchone()[0]
    assert row_count == 2


def test_write_raw_prices_idempotent(db):
    records = [
        _price_record("AAPL", date(2026, 5, 1)),
        _price_record("AAPL", date(2026, 5, 2)),
    ]
    write_raw_records(db, "raw_prices", records)
    write_raw_records(db, "raw_prices", records)  # identical second write

    row_count = db.execute("SELECT COUNT(*) FROM raw_prices").fetchone()[0]
    assert row_count == 2  # not 4


def test_write_raw_insider_idempotent(db):
    records = [_insider_record("AAPL", "0001140361-26-025622", 0)]
    write_raw_records(db, "raw_insider", records)
    write_raw_records(db, "raw_insider", records)

    row_count = db.execute("SELECT COUNT(*) FROM raw_insider").fetchone()[0]
    assert row_count == 1  # not 2


def test_write_empty_records(db):
    result = write_raw_records(db, "raw_prices", [])
    assert result == 0
    row_count = db.execute("SELECT COUNT(*) FROM raw_prices").fetchone()[0]
    assert row_count == 0


def test_write_unsupported_table_raises(db):
    with pytest.raises(ValueError, match="Unsupported table"):
        write_raw_records(db, "signals", [_price_record()])


def test_write_raw_insider_id_format(db):
    record = _insider_record("AAPL", "0001140361-26-025622", 0)
    write_raw_records(db, "raw_insider", [record])

    row_id = db.execute("SELECT id FROM raw_insider").fetchone()[0]
    assert row_id == "0001140361-26-025622:0"


@given(
    ticker=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",))),
    trade_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
)
@h_settings(max_examples=200)
def test_price_id_deterministic(ticker, trade_date):
    assert _price_id(ticker, trade_date) == _price_id(ticker, trade_date)


@given(
    ticker=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",))),
    trade_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
)
@h_settings(max_examples=200)
def test_price_id_fits_bigint(ticker, trade_date):
    result = _price_id(ticker, trade_date)
    assert 0 <= result < 2**63
