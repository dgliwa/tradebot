from datetime import UTC, date, datetime

from tradebot.models.raw_record import FetchResult, TickerFetchResult


def test_successful_empty_disclosure_window_is_valid():
    result = FetchResult('edgar', datetime.now(UTC), [TickerFetchResult('AAPL', 0, date(2026, 7, 8))])
    assert result.is_valid
    assert result.row_count == 0


def test_partial_failure_invalidates_aggregate():
    result = FetchResult('yfinance', datetime.now(UTC), [
        TickerFetchResult('AAPL', 60, date(2026, 7, 7)),
        TickerFetchResult('MSFT', errors=['missing data']),
    ])
    assert not result.is_valid
    assert result.freshness_date is None
    assert result.row_count == 60


def test_empty_universe_and_source_error_invalid():
    assert not FetchResult('edgar', datetime.now(UTC)).is_valid
    assert not FetchResult('edgar', datetime.now(UTC), [TickerFetchResult('AAPL', 0, date.today())], ['network']).is_valid
