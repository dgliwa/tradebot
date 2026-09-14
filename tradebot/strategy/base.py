from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

import duckdb


@dataclass(frozen=True)
class RecommendationResult:
    ticker: str
    composite_score: float
    rank: int
    selected: bool
    raw_values: dict[str, float]
    scores: dict[str, float]
    entry_signal: bool = False
    entry_reason: str | None = None


@runtime_checkable
class TradingStrategy(Protocol):
    """Research logic consumed by the strategy-agnostic trading pipeline."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def benchmark(self) -> str: ...

    @property
    def config_hash(self) -> str: ...

    @property
    def canonical_json(self) -> str: ...

    @property
    def schedule(self) -> Any: ...

    @property
    def capital(self) -> Any: ...

    @property
    def risk(self) -> Any: ...

    @property
    def execution(self) -> Any: ...

    @property
    def paper(self) -> Any: ...

    @property
    def evaluation(self) -> Any: ...

    def build_candidates(
        self, conn: duckdb.DuckDBPyConnection, run_id: str, session: date,
        *, owned_tickers: set[str] | None = None,
    ) -> list[Any]: ...

    def score(
        self, conn: duckdb.DuckDBPyConnection, run_id: str, session: date,
        decision_at: datetime, candidates: list[Any],
    ) -> list[RecommendationResult]: ...
