from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta

import duckdb

from tradebot.strategy.base import RecommendationResult
from tradebot.strategy.config import Strategy
from tradebot.strategy.universe import Candidate


def _id(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(":".join(parts).encode()).digest()[:8], "big") & ((1 << 63) - 1)


def _centered_ranks(values: dict[str, float]) -> dict[str, float]:
    unique = sorted(set(values.values()))
    if len(unique) == 1:
        return {ticker: 0.0 for ticker in values}
    scores = {value: -1 + 2 * index / (len(unique) - 1) for index, value in enumerate(unique)}
    return {ticker: scores[value] for ticker, value in values.items()}


def _price_closes(
    conn: duckdb.DuckDBPyConnection, ticker: str, session: date, decision_at: datetime,
) -> list[tuple[date, float]]:
    return conn.execute(
        """WITH snapshots AS (
            SELECT id, row_number() OVER (ORDER BY fetched_at DESC, id DESC) AS rank
            FROM price_snapshots WHERE ticker = ? AND source = 'yfinance' AND fetched_at <= ?
        )
        SELECT p.date, p.close FROM snapshots s
        JOIN raw_prices p ON p.snapshot_id = s.id
        WHERE s.rank = 1 AND p.date <= ? ORDER BY p.date""",
        [ticker, decision_at, session],
    ).fetchall()


def _momentum(closes: list[tuple[date, float]], strategy: Strategy) -> tuple[float, dict]:
    if len(closes) < 64:
        raise ValueError(f"Need 64 completed price sessions, found {len(closes)}")
    current = closes[-1][1]
    return_21 = current / closes[-22][1] - 1
    return_63 = current / closes[-64][1] - 1
    raw = strategy.signals.momentum_21_weight * return_21 + strategy.signals.momentum_63_weight * return_63
    return raw, {"return_21": return_21, "return_63": return_63, "last_price_date": closes[-1][0].isoformat()}


def _insider(
    conn: duckdb.DuckDBPyConnection, ticker: str, session: date, strategy: Strategy,
) -> tuple[float, dict]:
    start = session - timedelta(days=90)
    rows = conn.execute(
        """SELECT filer_name, shares, price_per_share, filed_at FROM raw_insider
           WHERE ticker = ? AND transaction_code = 'P' AND filed_at BETWEEN ? AND ?""",
        [ticker, start, session],
    ).fetchall()
    value = sum((shares or 0) * (price or 0) for _, shares, price, _ in rows)
    buyers = len({name for name, _, _, _ in rows if name})
    recency = max((math.exp(-(session - filed).days / 30) for *_, filed in rows), default=0.0)
    value_component = min(1.0, math.log1p(value) / math.log1p(1_000_000))
    buyer_component = min(1.0, buyers / 3)
    raw = (
        strategy.signals.insider_value_weight * value_component
        + strategy.signals.insider_buyers_weight * buyer_component
        + strategy.signals.insider_recency_weight * recency
    )
    return raw, {
        "purchase_value": value, "distinct_buyers": buyers, "filing_count": len(rows),
        "recency": recency,
    }


def score_candidates(
    conn: duckdb.DuckDBPyConnection, strategy: Strategy, run_id: str,
    session: date, decision_at: datetime, candidates: list[Candidate],
) -> list[RecommendationResult]:
    if not candidates:
        return []
    momentum_raw: dict[str, float] = {}
    insider_raw: dict[str, float] = {}
    details: dict[str, dict] = {}
    for candidate in candidates:
        momentum_raw[candidate.ticker], momentum_details = _momentum(
            _price_closes(conn, candidate.ticker, session, decision_at), strategy
        )
        insider_raw[candidate.ticker], insider_details = _insider(conn, candidate.ticker, session, strategy)
        details[candidate.ticker] = {
            "momentum": momentum_details,
            "insider": insider_details,
            "political_score": candidate.political_score,
            "political_filed_at": candidate.latest_filed_at.isoformat() if candidate.latest_filed_at else None,
        }
    momentum_scores = _centered_ranks(momentum_raw)
    insider_scores = _centered_ranks(insider_raw)
    composites = {
        ticker: strategy.signals.momentum_weight * momentum_scores[ticker]
        + strategy.signals.insider_weight * insider_scores[ticker]
        for ticker in momentum_raw
    }
    ordering = sorted(composites, key=lambda ticker: (-composites[ticker], ticker))
    candidate_by_ticker = {candidate.ticker: candidate for candidate in candidates}
    ranked = []
    for rank, ticker in enumerate(ordering, start=1):
        selected = rank <= strategy.capital.max_new_positions
        previous = conn.execute(
            """SELECT r.rank,u.source_filed_at FROM recommendations r
               JOIN strategy_runs sr ON sr.id=r.run_id
               JOIN universe_snapshots u ON u.run_id=r.run_id AND u.ticker=r.ticker
               WHERE r.ticker=? AND sr.effective_session < ? AND sr.status='completed'
               ORDER BY sr.effective_session DESC LIMIT 1""", [ticker, session]
        ).fetchone()
        source_filed_at = candidate_by_ticker[ticker].latest_filed_at
        new_disclosure = previous is None or (
            source_filed_at is not None and (previous[1] is None or source_filed_at > previous[1])
        )
        improved = previous is not None and previous[0] - rank >= strategy.universe.rank_improvement_threshold
        entry_reason = "new_disclosure" if new_disclosure else "rank_improvement" if improved else None
        item = RecommendationResult(
            ticker=ticker, composite_score=composites[ticker], rank=rank, selected=selected,
            raw_values={"momentum": momentum_raw[ticker], "insider": insider_raw[ticker]},
            scores={"momentum": momentum_scores[ticker], "insider": insider_scores[ticker]},
            entry_signal=selected and entry_reason is not None,
            entry_reason=entry_reason if selected else None,
        )
        ranked.append(item)
        for signal_type, raw, score in (
            ("momentum", item.raw_values["momentum"], item.scores["momentum"]),
            ("insider", item.raw_values["insider"], item.scores["insider"]),
        ):
            conn.execute(
                """INSERT INTO signals (id, ticker, run_date, signal_type, score, run_id, raw_value, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                [_id(run_id, ticker, signal_type), ticker, session, signal_type, score, run_id, raw,
                 json.dumps(details[ticker][signal_type], sort_keys=True)],
            )
        explanation = {**details[ticker], "weights": {
            "momentum": strategy.signals.momentum_weight, "insider": strategy.signals.insider_weight,
        }}
        conn.execute(
            """INSERT INTO recommendations
               (id,ticker,run_date,composite_score,rank,run_id,selected,explanation,entry_signal,entry_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
            [_id(run_id, ticker, "recommendation"), ticker, session, item.composite_score,
             rank, run_id, selected, json.dumps(explanation, sort_keys=True),
             item.entry_signal, item.entry_reason],
        )
    return ranked
