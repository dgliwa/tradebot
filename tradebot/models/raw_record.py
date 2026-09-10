from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class RawRecord:
    source: str
    ticker: str
    fetched_at: datetime
    data: dict[str, Any]
    transaction_date: date | None = None
    filed_at: date | None = None


@dataclass
class TickerFetchResult:
    ticker: str
    row_count: int = 0
    # Prices: latest completed bar. Disclosures: date through which filings were scanned.
    freshness_date: date | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.row_count >= 0 and self.freshness_date is not None and not self.errors


@dataclass
class FetchResult:
    """Fetch health is coverage-based, not a count of matching insider purchases."""
    source: str
    checked_at: datetime
    tickers: list[TickerFetchResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return sum(t.row_count for t in self.tickers)

    @property
    def freshness_date(self) -> date | None:
        if not self.is_valid:
            return None
        return min(t.freshness_date for t in self.tickers)

    @property
    def is_valid(self) -> bool:
        return bool(self.tickers) and not self.errors and all(t.is_valid for t in self.tickers)
