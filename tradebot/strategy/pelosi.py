from __future__ import annotations

from datetime import date, datetime

import duckdb

from tradebot.signals.scorer import score_candidates
from tradebot.strategy.base import RecommendationResult
from tradebot.strategy.config import Strategy as PelosiConfig
from tradebot.strategy.universe import Candidate, build_universe


class PelosiStrategy:
    """Politician-led candidate selection with momentum and corporate-insider ranking."""

    def __init__(self, config: PelosiConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def version(self) -> str:
        return self.config.version

    @property
    def benchmark(self) -> str:
        return self.config.benchmark

    @property
    def config_hash(self) -> str:
        return self.config.config_hash

    @property
    def canonical_json(self) -> str:
        return self.config.canonical_json

    @property
    def schedule(self):
        return self.config.schedule

    @property
    def capital(self):
        return self.config.capital

    @property
    def universe(self):
        return self.config.universe

    @property
    def signals(self):
        return self.config.signals

    @property
    def risk(self):
        return self.config.risk

    @property
    def execution(self):
        return self.config.execution

    @property
    def paper(self):
        return self.config.paper

    @property
    def evaluation(self):
        return self.config.evaluation

    def build_candidates(
        self, conn: duckdb.DuckDBPyConnection, run_id: str, session: date,
        *, owned_tickers: set[str] | None = None,
    ) -> list[Candidate]:
        return build_universe(conn, self.config, run_id, session, owned_tickers=owned_tickers)

    def score(
        self, conn: duckdb.DuckDBPyConnection, run_id: str, session: date,
        decision_at: datetime, candidates: list[Candidate],
    ) -> list[RecommendationResult]:
        return score_candidates(conn, self.config, run_id, session, decision_at, candidates)
