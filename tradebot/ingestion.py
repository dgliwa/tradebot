from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import duckdb

from tradebot.config import Settings
from tradebot.db.writer import WriteResult, write_raw_records
from tradebot.fetchers.insider import fetch_insider
from tradebot.fetchers.political import ManualCSVProvider, import_political_batch
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


def _record_coverage(conn: duckdb.DuckDBPyConnection, result: FetchResult) -> None:
    for ticker in result.tickers:
        errors = [*result.errors, *ticker.errors]
        identifier = hashlib.sha256(
            f"{result.source}:{ticker.ticker}:{result.checked_at.isoformat()}".encode()
        ).hexdigest()[:24]
        conn.execute(
            """INSERT INTO source_coverage
               (id, source, ticker, checked_through, checked_at, status, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
            [identifier, result.source, ticker.ticker, ticker.freshness_date, result.checked_at,
             "valid" if ticker.is_valid and not result.errors else "invalid", json.dumps(errors)],
        )


def ingest_prices(
    conn: duckdb.DuckDBPyConnection, settings: Settings, *,
    universe: list[str] | None = None, now: datetime | None = None,
) -> IngestionSummary:
    tickers = universe or settings.universe
    records, result = fetch_prices(tickers, **({"now": now} if now else {}))
    if not result.is_valid:
        _record_coverage(conn, result)
        return _summary(result)
    written = write_raw_records(conn, "raw_prices", records)
    _record_coverage(conn, result)
    return _summary(result, written)


def ingest_insider(
    conn: duckdb.DuckDBPyConnection, settings: Settings, *,
    universe: list[str] | None = None, now: datetime | None = None,
) -> IngestionSummary:
    tickers = universe or settings.universe
    records, result = fetch_insider(
        tickers, user_agent=settings.sec_user_agent, **({"now": now} if now else {})
    )
    if not result.is_valid:
        _record_coverage(conn, result)
        return _summary(result)
    written = write_raw_records(conn, "raw_insider", records)
    _record_coverage(conn, result)
    return _summary(result, written)


def ingest_political_csv(
    conn: duckdb.DuckDBPyConnection, path: Path, coverage_through: date,
) -> IngestionSummary:
    batch = ManualCSVProvider(path, coverage_through).load()
    inserted, skipped = import_political_batch(conn, batch)
    return IngestionSummary(
        source=batch.source, fetched=len(batch.records), inserted=inserted, skipped=skipped,
        freshness=coverage_through.isoformat(),
    )
