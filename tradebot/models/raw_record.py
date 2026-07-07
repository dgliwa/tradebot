from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class RawRecord:
    """A single raw row from any data source before normalization.

    Carries both the raw payload (data dict) and parsed metadata fields
    so callers can inspect key dates without unpacking the dict.
    """
    source: str
    ticker: str
    fetched_at: datetime
    data: dict[str, Any]
    transaction_date: Optional[date] = None
    filed_at: Optional[date] = None


@dataclass
class FetchResult:
    """Summary of a fetch operation returned to the pipeline.

    is_valid gates downstream signal computation:
    a zero-row or dateless result blocks trade generation.
    """
    source: str
    ticker: str
    row_count: int
    freshness_date: Optional[date]

    @property
    def is_valid(self) -> bool:
        return self.row_count > 0 and self.freshness_date is not None
