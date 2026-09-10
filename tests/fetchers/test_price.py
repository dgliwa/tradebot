from datetime import UTC, datetime

import pandas as pd
import pytest

from tradebot.fetchers.market import completed_sessions
from tradebot.fetchers.price import fetch_prices

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def frame(tickers, *, sessions=None):
    sessions = sessions or completed_sessions(NOW)[-50:]
    columns = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]], names=["Ticker", "Price"])
    values = {(ticker, field): [1_000_000 + i if field == "Volume" else 100. + i for i in range(len(sessions))]
              for ticker in tickers for field in ("Open", "High", "Low", "Close", "Volume")}
    return pd.DataFrame(values, index=pd.to_datetime(sessions), columns=columns)


def test_complete_histories_are_valid(monkeypatch):
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **_: frame(["AAPL", "MSFT"]))
    records, result = fetch_prices([" aapl ", "MSFT"], now=NOW)
    assert result.is_valid
    assert result.row_count == 100
    assert result.freshness_date == completed_sessions(NOW)[-1]
    assert all(record.fetched_at == NOW for record in records)
    assert all(type(record.data["volume"]) is int for record in records)


def test_missing_ticker_is_explicit_partial_failure(monkeypatch):
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **_: frame(["AAPL"]))
    records, result = fetch_prices(["AAPL", "MSFT"], now=NOW)
    assert len(records) == 50
    assert not result.is_valid
    assert result.tickers[1].ticker == "MSFT"
    assert "No ticker data" in result.tickers[1].errors[0]


def test_stale_or_short_history_is_invalid(monkeypatch):
    sessions = completed_sessions(NOW)[-49:]
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **_: frame(["AAPL"], sessions=sessions))
    records, result = fetch_prices(["AAPL"], now=NOW)
    assert records == []
    assert not result.is_valid
    assert "Missing 1 required sessions" in result.tickers[0].errors[0]


@pytest.mark.parametrize("field,value", [("Close", float("nan")), ("Low", 200.), ("Volume", 1.5)])
def test_bad_values_reject_entire_ticker(monkeypatch, field, value):
    data = frame(["AAPL"])
    if field == "Volume":
        data[("AAPL", field)] = data[("AAPL", field)].astype(float)
    data.loc[data.index[-1], ("AAPL", field)] = value
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **_: data)
    records, result = fetch_prices(["AAPL"], now=NOW)
    assert records == []
    assert not result.is_valid


def test_in_progress_daily_bar_is_excluded(monkeypatch):
    before_close = datetime(2026, 7, 8, 18, tzinfo=UTC)
    completed = completed_sessions(before_close)
    sessions = completed[-50:] + [before_close.date()]
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **_: frame(["AAPL"], sessions=sessions))
    records, result = fetch_prices(["AAPL"], now=before_close)
    assert result.is_valid
    assert all(record.transaction_date != before_close.date() for record in records)


def test_download_error_has_source_diagnostic(monkeypatch):
    def fail(**_):
        raise ConnectionError("Yahoo blocked")
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", fail)
    records, result = fetch_prices(["AAPL"], now=NOW)
    assert records == []
    assert not result.is_valid
    assert "Yahoo blocked" in result.errors[0]
