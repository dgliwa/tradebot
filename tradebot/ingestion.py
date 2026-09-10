from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from tradebot.config import Settings
from tradebot.db.writer import WriteResult, write_raw_records
from tradebot.fetchers.insider import fetch_insider
from tradebot.fetchers.price import fetch_prices
from tradebot.models.raw_record import FetchResult


@dataclass(frozen=True)
class IngestionSummary:
    source: str
    fetched: int
    inserted: int
    skipped: int
    freshness: str | None
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return not self.errors


def _errors(result: FetchResult) -> list[str]:
    errors = list(result.errors)
    errors.extend(f"{ticker.ticker}: {error}" for ticker in result.tickers for error in ticker.errors)
    return errors


def _summary(result: FetchResult, write: WriteResult = WriteResult()) -> IngestionSummary:
    return IngestionSummary(
        source=result.source,
        fetched=result.row_count,
        inserted=write.inserted,
        skipped=write.skipped,
        freshness=result.freshness_date.isoformat() if result.freshness_date else None,
        errors=_errors(result),
    )


def ingest_prices(conn: duckdb.DuckDBPyConnection, settings: Settings) -> IngestionSummary:
    records, result = fetch_prices(settings.universe)
    if not result.is_valid:
        return _summary(result)
    return _summary(result, write_raw_records(conn, "raw_prices", records))


def ingest_insider(conn: duckdb.DuckDBPyConnection, settings: Settings) -> IngestionSummary:
    records, result = fetch_insider(settings.universe, user_agent=settings.sec_user_agent)
    if not result.is_valid:
        return _summary(result)
    return _summary(result, write_raw_records(conn, "raw_insider", records))
