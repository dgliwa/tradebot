from __future__ import annotations
from datetime import datetime

import yfinance as yf

from tradebot.models.raw_record import FetchResult, RawRecord


def fetch_prices(universe: list[str]) -> tuple[list[RawRecord], FetchResult]:
    """Fetch 90-day OHLCV price history for all tickers in universe.

    Returns (list[RawRecord], FetchResult). FetchResult.is_valid is True when
    at least one row was returned. Caller provides universe; no settings import here.
    """
    fetched_at = datetime.utcnow()
    records: list[RawRecord] = []
    freshness_date = None

    try:
        df = yf.download(
            tickers=universe,
            period="3mo",
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
        )
    except Exception:
        return [], FetchResult(
            source="yfinance",
            ticker="universe",
            row_count=0,
            freshness_date=None,
        )

    for ticker in universe:
        if ticker not in df.columns.get_level_values("Ticker"):
            continue

        ticker_df = df[ticker].dropna(how="all")

        for ts, row in ticker_df.iterrows():
            trade_date = ts.date()
            volume_raw = row["Volume"]
            volume = int(volume_raw) if volume_raw == volume_raw else None

            records.append(
                RawRecord(
                    source="yfinance",
                    ticker=ticker,
                    fetched_at=fetched_at,
                    transaction_date=trade_date,
                    filed_at=None,
                    data={
                        "open": row["Open"],
                        "high": row["High"],
                        "low": row["Low"],
                        "close": row["Close"],
                        "volume": volume,
                    },
                )
            )

            if freshness_date is None or trade_date > freshness_date:
                freshness_date = trade_date

    return records, FetchResult(
        source="yfinance",
        ticker="universe",
        row_count=len(records),
        freshness_date=freshness_date,
    )
