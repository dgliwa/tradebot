from __future__ import annotations
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from tradebot.fetchers.price import fetch_prices


def _make_mock_df(tickers: list[str], num_rows: int = 3) -> pd.DataFrame:
    """Create a MultiIndex DataFrame matching yfinance group_by='ticker' output."""
    dates = pd.date_range("2026-04-01", periods=num_rows, freq="B")
    columns = pd.MultiIndex.from_product(
        [tickers, ["Open", "High", "Low", "Close", "Volume"]],
        names=["Ticker", "Price"],
    )
    data = {
        (ticker, col): (
            [float(100 + i) for i in range(num_rows)]
            if col != "Volume"
            else [1_000_000 + i * 100 for i in range(num_rows)]
        )
        for ticker in tickers
        for col in ["Open", "High", "Low", "Close", "Volume"]
    }
    return pd.DataFrame(data, index=dates, columns=columns)


def test_fetch_prices_happy_path(monkeypatch):
    mock_df = _make_mock_df(["AAPL", "MSFT"], num_rows=3)
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: mock_df)

    records, result = fetch_prices(["AAPL", "MSFT"])

    assert len(records) == 6  # 3 rows x 2 tickers
    assert result.source == "yfinance"
    assert result.ticker == "universe"
    assert result.row_count == 6
    assert result.is_valid is True

    aapl_records = [r for r in records if r.ticker == "AAPL"]
    assert len(aapl_records) == 3
    assert all(r.source == "yfinance" for r in aapl_records)
    assert all(r.filed_at is None for r in aapl_records)
    assert all(isinstance(r.transaction_date, date) for r in aapl_records)
    assert all("open" in r.data for r in aapl_records)
    assert all("high" in r.data for r in aapl_records)
    assert all("low" in r.data for r in aapl_records)
    assert all("close" in r.data for r in aapl_records)
    assert all("volume" in r.data for r in aapl_records)
    assert all(isinstance(r.data["volume"], int) for r in aapl_records)


def test_fetch_prices_empty_response(monkeypatch):
    empty_df = pd.DataFrame(
        columns=pd.MultiIndex.from_tuples([], names=["Ticker", "Price"])
    )
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: empty_df)

    records, result = fetch_prices(["FAKE_TICKER"])

    assert records == []
    assert result.row_count == 0
    assert result.freshness_date is None
    assert result.is_valid is False


def test_fetch_prices_freshness_date(monkeypatch):
    mock_df = _make_mock_df(["AAPL"], num_rows=5)
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: mock_df)

    records, result = fetch_prices(["AAPL"])

    expected_freshness = max(r.transaction_date for r in records)
    assert result.freshness_date == expected_freshness


def test_fetch_prices_yfinance_exception(monkeypatch):
    def broken_download(**kw):
        raise ConnectionError("Yahoo blocked")

    monkeypatch.setattr("tradebot.fetchers.price.yf.download", broken_download)

    records, result = fetch_prices(["AAPL"])

    assert records == []
    assert result.is_valid is False


def test_fetch_prices_fetched_at_is_datetime(monkeypatch):
    mock_df = _make_mock_df(["NVDA"], num_rows=1)
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: mock_df)

    records, _ = fetch_prices(["NVDA"])

    assert len(records) == 1
    assert isinstance(records[0].fetched_at, datetime)
