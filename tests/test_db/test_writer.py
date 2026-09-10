from datetime import UTC, date, datetime, timedelta

import pytest

from tradebot.db.writer import WriteResult, write_raw_records
from tradebot.models.raw_record import RawRecord

NOW = datetime(2026, 7, 8, 12, tzinfo=UTC)


def price(ticker="AAPL", day=date(2026, 7, 6), close=100., fetched_at=NOW):
    return RawRecord("yfinance", ticker, fetched_at,
                     dict(open=close, high=close, low=close, close=close, volume=100), day)


def insider(accession="a", day=date(2026, 7, 6)):
    return RawRecord("edgar", "AAPL", NOW,
                     dict(accession=accession, transaction_index=0, shares=10.,
                          price_per_share=None, transaction_code="P", raw_xml="<ownershipDocument/>",
                          document_url="https://www.sec.gov/example.xml"), day, date(2026, 7, 7))


@pytest.mark.parametrize("table,record", [("raw_prices", price()), ("raw_insider", insider())])
def test_idempotent_actual_counts(db, table, record):
    assert write_raw_records(db, table, [record]) == WriteResult(1, 0)
    assert write_raw_records(db, table, [record]) == WriteResult(0, 1)


def test_latest_view_selects_one_coherent_snapshot(db):
    write_raw_records(db, "raw_prices", [price(day=date(2026, 7, 3), close=200), price(close=200)])
    write_raw_records(db, "raw_prices", [price(close=100, fetched_at=NOW + timedelta(days=1))])
    assert db.execute("SELECT date, close FROM latest_prices").fetchall() == [(date(2026, 7, 6), 100.)]
    assert db.execute("SELECT count(*) FROM raw_prices").fetchone() == (3,)
    assert db.execute("SELECT count(*) FROM price_snapshots").fetchone() == (2,)


def test_invalid_record_rejects_entire_batch(db):
    with pytest.raises(ValueError, match="transaction_date"):
        write_raw_records(db, "raw_insider", [insider(), insider("bad", None)])
    assert db.execute("SELECT count(*) FROM raw_insider").fetchone() == (0,)


def test_database_failure_rolls_back_entire_batch(db):
    bad = insider("bad")
    bad.data["filer_name"] = object()
    with pytest.raises(Exception):
        write_raw_records(db, "raw_insider", [insider(), bad])
    assert db.execute("SELECT count(*) FROM raw_insider").fetchone() == (0,)


def test_conflicting_snapshot_rolls_back_prior_group(db):
    write_raw_records(db, "raw_prices", [price()])
    with pytest.raises(ValueError, match="timestamp"):
        write_raw_records(db, "raw_prices", [price(ticker="MSFT"), price(close=200)])
    assert db.execute("SELECT ticker FROM price_snapshots").fetchall() == [("AAPL",)]


def test_same_timestamp_different_timezone_is_same_snapshot(db):
    from datetime import timezone
    record = price()
    write_raw_records(db, "raw_prices", [record])
    record.fetched_at = NOW.astimezone(timezone(timedelta(hours=-4)))
    assert write_raw_records(db, "raw_prices", [record]) == WriteResult(0, 1)


@pytest.mark.parametrize("key,value", [("close", float('nan')), ("open", -1), ("volume", 1.5), ("high", 1)])
def test_invalid_price_rejected(db, key, value):
    record = price()
    record.data[key] = value
    with pytest.raises(ValueError):
        write_raw_records(db, "raw_prices", [record])


def test_naive_timestamp_rejected(db):
    with pytest.raises(ValueError, match="timezone-aware"):
        write_raw_records(db, "raw_prices", [price(fetched_at=NOW.replace(tzinfo=None))])


def test_unsupported_empty_table_rejected(db):
    with pytest.raises(ValueError, match="Unsupported"):
        write_raw_records(db, "signals", [])
    assert write_raw_records(db, "raw_prices", []) == WriteResult()


def test_insider_provenance_stored(db):
    write_raw_records(db, "raw_insider", [insider()])
    assert db.execute("SELECT raw_xml, document_url FROM raw_insider").fetchone() == (
        "<ownershipDocument/>", "https://www.sec.gov/example.xml")
