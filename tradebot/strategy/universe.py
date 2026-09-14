from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from tradebot.strategy.config import Strategy


@dataclass(frozen=True)
class Candidate:
    ticker: str
    political_score: float
    latest_filed_at: date | None
    disclosure_ids: tuple[str, ...]


def _id(run_id: str, ticker: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{run_id}:{ticker}".encode()).digest()[:8], "big") & ((1 << 63) - 1)


def _direction(transaction_type: str, asset_type: str, option_type: str | None) -> int:
    purchase = transaction_type == "purchase"
    if asset_type == "stock" or option_type == "call":
        return 1 if purchase else -1
    if option_type == "put":
        return -1 if purchase else 1
    return 0


def build_universe(
    conn: duckdb.DuckDBPyConnection, strategy: Strategy, run_id: str, session: date,
    *, owned_tickers: set[str] | None = None,
) -> list[Candidate]:
    coverage = conn.execute("SELECT max(coverage_through) FROM congressional_imports").fetchone()[0]
    if coverage is None or coverage < session:
        raise ValueError(f"Congressional coverage is stale; required {session}, found {coverage}")
    start = session - timedelta(days=strategy.universe.lookback_days)
    tracked = {name.casefold() for name in strategy.universe.tracked_politicians}
    rows = conn.execute(
        """SELECT id, ticker, member_name, transaction_type, asset_type, option_type,
                  amount_min, amount_max, filed_at
           FROM raw_congressional
           WHERE filed_at BETWEEN ? AND ? ORDER BY filed_at, id""",
        [start, session],
    ).fetchall()
    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        if (row[2] or "").casefold() in tracked:
            grouped.setdefault(row[1], []).append(row)
    candidates = []
    for ticker, disclosures in grouped.items():
        score = sum(
            _direction(row[3], row[4], row[5])
            * ((row[6] + row[7]) / 2)
            * math.exp(-(session - row[8]).days / 90)
            for row in disclosures
        )
        if score > 0:
            candidates.append(Candidate(ticker, score, max(row[8] for row in disclosures), tuple(row[0] for row in disclosures)))
    existing = {candidate.ticker for candidate in candidates}
    for ticker in sorted((owned_tickers or set()) - existing - {strategy.benchmark}):
        candidates.append(Candidate(ticker, 0.0, None, ()))
    candidates.sort(key=lambda item: (-item.political_score, item.ticker))
    for candidate in candidates:
        reason = json.dumps({"political_score": candidate.political_score, "disclosure_ids": candidate.disclosure_ids})
        conn.execute(
            """INSERT INTO universe_snapshots (id, run_date, week_start, ticker, run_id, reason, source_filed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
            [_id(run_id, candidate.ticker), session, session - timedelta(days=session.weekday()),
             candidate.ticker, run_id, reason, candidate.latest_filed_at],
        )
    return candidates
