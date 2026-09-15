from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import duckdb

from tradebot.shadow.account import cash_balance


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: float
    average_cost: float
    opened_at: datetime


@dataclass(frozen=True)
class Portfolio:
    cash: float
    positions: tuple[Position, ...]
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    realized_pnl: float
    equity: float


def _position_ledger(
    conn: duckdb.DuckDBPyConnection, account_id: str, *, before: datetime | None = None,
) -> tuple[tuple[Position, ...], float]:
    fills = conn.execute(
        """SELECT f.ticker,f.side,f.quantity,f.price,f.filled_at,f.id
           FROM shadow_fills f JOIN shadow_orders o ON o.id=f.order_id
           WHERE o.account_id=?""", [account_id]
    ).fetchall()
    splits = conn.execute(
        """SELECT a.ticker,a.value,a.action_date,a.id FROM corporate_actions a
           JOIN applied_corporate_actions x ON x.action_id=a.id
           WHERE x.account_id=? AND a.action_type='split'""", [account_id]
    ).fetchall()
    events = [(row[4], row[5], "fill", row) for row in fills]
    events += [(datetime.combine(row[2], datetime.min.time(), tzinfo=UTC), row[3], "split", row) for row in splits]
    if before is not None:
        events = [event for event in events if event[0] < before]
    lots: dict[str, list[list]] = {}
    realized = 0.0
    for _, _, kind, row in sorted(events, key=lambda item: (item[0], item[1])):
        if kind == "split":
            ticker, ratio, _, _ = row
            for lot in lots.setdefault(ticker, []):
                lot[0] *= ratio
                lot[1] /= ratio
            continue
        ticker, side, quantity, price, filled_at, _ = row
        ticker_lots = lots.setdefault(ticker, [])
        if side == "buy":
            ticker_lots.append([float(quantity), float(price), filled_at])
            continue
        remaining = float(quantity)
        while remaining > 1e-8 and ticker_lots:
            consumed = min(remaining, ticker_lots[0][0])
            realized += consumed * (float(price) - ticker_lots[0][1])
            ticker_lots[0][0] -= consumed
            remaining -= consumed
            if ticker_lots[0][0] <= 1e-8:
                ticker_lots.pop(0)
        if remaining > 1e-8:
            raise ValueError(f"Sell fills exceed owned quantity for {ticker}")
    result = []
    for ticker, ticker_lots in lots.items():
        quantity = sum(lot[0] for lot in ticker_lots)
        if quantity > 1e-8:
            cost = sum(lot[0] * lot[1] for lot in ticker_lots) / quantity
            result.append(Position(ticker, quantity, cost, min(lot[2] for lot in ticker_lots)))
    return tuple(sorted(result, key=lambda item: item.ticker)), realized


def positions(conn: duckdb.DuckDBPyConnection, account_id: str) -> tuple[Position, ...]:
    return _position_ledger(conn, account_id)[0]


def positions_before(
    conn: duckdb.DuckDBPyConnection, account_id: str, day: date,
) -> tuple[Position, ...]:
    cutoff = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    return _position_ledger(conn, account_id, before=cutoff)[0]


def price_on(
    conn: duckdb.DuckDBPyConnection, ticker: str, session: date, field: str = "close",
) -> float:
    if field not in {"open", "close"}:
        raise ValueError("Price field must be open or close")
    row = conn.execute(
        f"""WITH snapshots AS (
              SELECT id,row_number() OVER (ORDER BY fetched_at DESC,id DESC) rank
              FROM price_snapshots WHERE ticker=? AND source='yfinance'
            )
            SELECT p.{field} FROM snapshots s JOIN raw_prices p ON p.snapshot_id=s.id
            WHERE s.rank=1 AND p.date=?""",
        [ticker, session],
    ).fetchone()
    if row is None:
        raise ValueError(f"No {field} price for {ticker} on {session}")
    return float(row[0])


def portfolio(conn: duckdb.DuckDBPyConnection, account_id: str, session: date) -> Portfolio:
    current, realized = _position_ledger(conn, account_id)
    cash = cash_balance(conn, account_id)
    market_value = sum(item.quantity * price_on(conn, item.ticker, session) for item in current)
    cost_basis = sum(item.quantity * item.average_cost for item in current)
    return Portfolio(
        cash, current, market_value, cost_basis, market_value - cost_basis, realized,
        cash + market_value,
    )
