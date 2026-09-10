from __future__ import annotations

from datetime import UTC, datetime

import yfinance as yf

from tradebot.config import normalize_universe
from tradebot.fetchers.market import completed_sessions
from tradebot.models.raw_record import FetchResult, RawRecord, TickerFetchResult
from tradebot.models.validation import require_aware, validate_record


def fetch_prices(universe: list[str], *, now: datetime | None = None, min_history: int = 50) -> tuple[list[RawRecord], FetchResult]:
    now = now or datetime.now(UTC)
    require_aware(now)
    now = now.astimezone(UTC)
    universe = normalize_universe(universe)
    sessions = completed_sessions(now)
    if not 1 <= min_history <= len(sessions):
        raise ValueError("min_history must fit the 180-day calendar window")
    required = set(sessions[-min_history:])
    latest = sessions[-1]
    result = FetchResult("yfinance", now)
    records: list[RawRecord] = []
    try:
        df = yf.download(tickers=universe, period="3mo", interval="1d", auto_adjust=True,
                         group_by="ticker", progress=False)
    except Exception as exc:
        result.errors.append(f"Price download failed: {type(exc).__name__}: {exc}")
        return [], result

    for ticker in universe:
        status = TickerFetchResult(ticker)
        result.tickers.append(status)
        ticker_records = []
        try:
            if df is None or df.empty or "Ticker" not in df.columns.names or ticker not in df.columns.get_level_values("Ticker"):
                raise ValueError("No ticker data in download")
            frame = df[ticker].dropna(how="all")
            seen = set()
            for ts, row in frame.iterrows():
                day = ts.date()
                if day > latest:
                    continue  # Never snapshot an in-progress daily candle.
                if day not in sessions:
                    raise ValueError(f"Unexpected non-session bar: {day}")
                if day in seen:
                    raise ValueError(f"Duplicate bar: {day}")
                seen.add(day)
                volume = float(row["Volume"])
                if not volume.is_integer() or volume < 0:
                    raise ValueError(f"Invalid volume on {day}")
                record = RawRecord("yfinance", ticker, now,
                                   {**{k.lower(): float(row[k]) for k in ("Open", "High", "Low", "Close")},
                                    "volume": int(volume)}, day)
                validate_record(record, "raw_prices")
                ticker_records.append(record)
            missing = sorted(required - seen)
            if missing:
                raise ValueError(f"Missing {len(missing)} required sessions; latest required is {latest}")
            status.freshness_date = latest
            status.row_count = len(ticker_records)
            records.extend(ticker_records)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            status.errors.append(f"Invalid price history: {exc}")
    return records, result
