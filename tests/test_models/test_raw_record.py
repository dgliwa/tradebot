"""FetchResult validity tests — DATA-03."""
from datetime import date
from tradebot.models.raw_record import FetchResult


def test_fetch_result_validity():
    today = date.today()
    assert FetchResult("yfinance", "AAPL", 100, today).is_valid is True
    assert FetchResult("yfinance", "AAPL", 0, today).is_valid is False
    assert FetchResult("yfinance", "AAPL", 100, None).is_valid is False
    assert FetchResult("yfinance", "AAPL", 0, None).is_valid is False


def test_fetch_result_fields():
    today = date.today()
    result = FetchResult("edgar", "MSFT", 5, today)
    assert result.source == "edgar"
    assert result.ticker == "MSFT"
    assert result.row_count == 5
    assert result.freshness_date == today
