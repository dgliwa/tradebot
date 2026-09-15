from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime

import duckdb
import yfinance as yf

from tradebot.config import normalize_universe
from tradebot.fetchers.market import completed_sessions
from tradebot.models.raw_record import FetchResult, TickerFetchResult
from tradebot.models.validation import require_aware


@dataclass(frozen=True)
class CorporateAction:
    id: str
    ticker: str
    action_date: date
    action_type: str
    value: float
    source: str
    fetched_at: datetime


def _action_id(ticker: str, action_date: date, action_type: str) -> str:
    return hashlib.sha256(f"yfinance:{ticker}:{action_date}:{action_type}".encode()).hexdigest()[:24]


def fetch_corporate_actions(
    universe: list[str], *, now: datetime | None = None,
) -> tuple[list[CorporateAction], FetchResult]:
    now = now or datetime.now(UTC)
    require_aware(now)
    now = now.astimezone(UTC)
    universe = normalize_universe(universe)
    latest = completed_sessions(now)[-1]
    result = FetchResult("yfinance-actions", now)
    actions: list[CorporateAction] = []
    try:
        frame = yf.download(
            tickers=universe, period="1y", interval="1d", auto_adjust=False,
            actions=True, group_by="ticker", progress=False,
        )
    except Exception as exc:
        result.errors.append(f"Corporate-action download failed: {type(exc).__name__}: {exc}")
        return [], result

    for ticker in universe:
        status = TickerFetchResult(ticker)
        result.tickers.append(status)
        ticker_actions: list[CorporateAction] = []
        try:
            if frame is None or frame.empty:
                raise ValueError("No ticker data in download")
            if "Ticker" in frame.columns.names:
                if ticker not in frame.columns.get_level_values("Ticker"):
                    raise ValueError("No ticker data in download")
                data = frame[ticker]
            elif len(universe) == 1:
                data = frame
            else:
                raise ValueError("Unexpected Yahoo column layout")
            if latest not in {index.date() for index in data.index}:
                raise ValueError(f"History does not cover latest completed session {latest}")
            for timestamp, row in data.iterrows():
                action_date = timestamp.date()
                if action_date > latest:
                    continue
                for column, action_type in (("Dividends", "dividend"), ("Stock Splits", "split")):
                    value = row.get(column, 0)
                    if value is None or value != value or float(value) == 0:
                        continue
                    value = float(value)
                    if value <= 0:
                        raise ValueError(f"Invalid {action_type} value on {action_date}")
                    ticker_actions.append(CorporateAction(
                        _action_id(ticker, action_date, action_type), ticker, action_date,
                        action_type, value, "yfinance", now,
                    ))
            status.row_count = len(ticker_actions)
            status.freshness_date = latest
            actions.extend(ticker_actions)
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            status.errors.append(f"Invalid corporate-action history: {exc}")
    return actions, result


def write_corporate_actions(
    conn: duckdb.DuckDBPyConnection, actions: list[CorporateAction],
) -> tuple[int, int]:
    if not actions:
        return 0, 0
    for action in actions:
        require_aware(action.fetched_at)
        if action.ticker != action.ticker.strip().upper() or not action.ticker:
            raise ValueError("Corporate-action ticker must be normalized")
        if action.action_type not in {"dividend", "split"}:
            raise ValueError("Unsupported corporate-action type")
        if action.source != "yfinance" or not math.isfinite(action.value) or action.value <= 0:
            raise ValueError("Invalid corporate-action source or value")
    if len({action.id for action in actions}) != len(actions):
        raise ValueError("Corporate-action batch contains duplicate identities")
    conn.execute("BEGIN TRANSACTION")
    try:
        inserted = 0
        skipped = 0
        for action in actions:
            existing = conn.execute(
                """SELECT ticker,action_date,action_type,value,source
                   FROM corporate_actions WHERE id=?""", [action.id]
            ).fetchone()
            expected = (action.ticker, action.action_date, action.action_type, action.value, action.source)
            if existing is not None:
                if existing != expected:
                    raise ValueError(f"Corporate action changed at source: {action.id}")
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO corporate_actions VALUES (?,?,?,?,?,?,?)",
                [action.id, action.ticker, action.action_date, action.action_type,
                 action.value, action.source, action.fetched_at],
            )
            inserted += 1
        conn.execute("COMMIT")
        return inserted, skipped
    except Exception:
        conn.execute("ROLLBACK")
        raise
