from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import duckdb

from tradebot.config import Settings
from tradebot.fetchers.market import completed_sessions
from tradebot.ingestion import IngestionSummary, ingest_insider, ingest_prices
from tradebot.strategy.base import RecommendationResult, TradingStrategy
from tradebot.strategy.runs import finish_run, start_run


@dataclass(frozen=True)
class DailyResult:
    run_id: str
    session: date
    replayed: bool
    recommendations: tuple[RecommendationResult, ...]
    ingestion: tuple[IngestionSummary, ...] = ()


def effective_session(strategy: TradingStrategy, decision_at: datetime) -> date:
    sessions = completed_sessions(decision_at)
    if not sessions:
        raise ValueError("No completed market session available")
    local = decision_at.astimezone(ZoneInfo(strategy.schedule.timezone))
    scheduled = time(strategy.schedule.hour, strategy.schedule.minute)
    if sessions[-1] == local.date() and local.time().replace(tzinfo=None) < scheduled:
        if len(sessions) < 2:
            raise ValueError("No session is ready for evaluation")
        return sessions[-2]
    return sessions[-1]


def _stored_recommendations(conn: duckdb.DuckDBPyConnection, run_id: str) -> tuple[RecommendationResult, ...]:
    rows = conn.execute(
        """SELECT r.ticker,
                  max(CASE WHEN s.signal_type='momentum' THEN s.raw_value END),
                  max(CASE WHEN s.signal_type='insider' THEN s.raw_value END),
                  max(CASE WHEN s.signal_type='momentum' THEN s.score END),
                  max(CASE WHEN s.signal_type='insider' THEN s.score END),
                  r.composite_score, r.rank, r.selected
           FROM recommendations r JOIN signals s ON s.run_id=r.run_id AND s.ticker=r.ticker
           WHERE r.run_id=? GROUP BY r.ticker,r.composite_score,r.rank,r.selected ORDER BY r.rank""",
        [run_id],
    ).fetchall()
    return tuple(RecommendationResult(
        ticker=row[0], raw_values={"momentum": row[1], "insider": row[2]},
        scores={"momentum": row[3], "insider": row[4]}, composite_score=row[5],
        rank=row[6], selected=row[7],
    ) for row in rows)


def run_daily(
    conn: duckdb.DuckDBPyConnection, settings: Settings, strategy: TradingStrategy,
    *, decision_at: datetime | None = None, owned_tickers: set[str] | None = None,
) -> DailyResult:
    decision_at = (decision_at or datetime.now(UTC)).astimezone(UTC)
    session = effective_session(strategy, decision_at)
    run = start_run(conn, strategy, session, decision_at)
    if run.status == "completed":
        return DailyResult(run.id, session, True, _stored_recommendations(conn, run.id))
    try:
        candidates = strategy.build_candidates(conn, run.id, session, owned_tickers=owned_tickers)
        if not candidates:
            finish_run(conn, run.id)
            return DailyResult(run.id, session, False, ())
        tickers = [candidate.ticker for candidate in candidates]
        price = ingest_prices(conn, settings, universe=tickers, now=decision_at)
        insider = ingest_insider(conn, settings, universe=tickers, now=decision_at)
        ingestion = (price, insider)
        errors = [error for summary in ingestion for error in summary.errors]
        if errors:
            raise ValueError("; ".join(errors))
        recommendations = tuple(strategy.score(
            conn, run.id, session, decision_at, candidates
        ))
        finish_run(conn, run.id)
        return DailyResult(run.id, session, False, recommendations, ingestion)
    except Exception as exc:
        finish_run(conn, run.id, error=str(exc))
        raise
